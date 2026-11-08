import Foundation

/// What the menu bar shows. One value, derived by `Resolver` from plain inputs, so it is testable without a UI.
enum DisplayState: String, CaseIterable, Equatable {
    case off, waiting, listening, amber, red, paused, engineProblem
}

enum AlertLevel: String, Equatable {
    case none, amber, red
    init(raw: String?) { self = AlertLevel(rawValue: raw ?? "none") ?? .none }
}

/// Fixed wording (same words as tools/macos/listen.py). Never any caller text.
enum Wording {
    static let consent = "Doublespeak listens to this call on your Mac only to warn you. Nothing is recorded or sent anywhere. Tell the other person if your state requires it."
    static let amber = "Possible scam call. Be careful with money and codes."
    static let red = "Likely scam call. Do not share money, codes or passwords."
    static let limits = "Works for calls played on this Mac (iPhone calls answered on the Mac via Calls on Other Devices, FaceTime, WhatsApp, Zoom)."
    static func notification(for level: AlertLevel) -> String? {
        switch level { case .amber: return amber; case .red: return red; case .none: return nil }
    }
}

struct StableInfo: Equatable {
    var tier: String
    var state: String
    var alert: AlertLevel
}

enum LiveEvent: Equatable {
    case state(active: Bool, listening: Bool, source: String)
    case verdict(tick: Int, stable: StableInfo, comboLabel: String?)
    case ended(reason: String)

    /// Parses one SSE `data:` payload. Unknown or malformed frames return nil (never crash on a bad feed).
    static func parse(_ payload: String) -> LiveEvent? {
        guard let data = payload.data(using: .utf8),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let type = obj["type"] as? String else { return nil }
        switch type {
        case "state":
            return .state(active: obj["active"] as? Bool ?? false,
                          listening: obj["listening"] as? Bool ?? false,
                          source: obj["source"] as? String ?? "")
        case "verdict":
            guard let st = obj["stable"] as? [String: Any] else { return nil }
            let stable = StableInfo(tier: st["tier"] as? String ?? "unsure",
                                    state: st["state"] as? String ?? "steady",
                                    alert: AlertLevel(raw: st["alert"] as? String))
            let quad = (obj["verdict"] as? [String: Any])?["quadrant"] as? [String: Any]
            return .verdict(tick: obj["tick"] as? Int ?? 0, stable: stable, comboLabel: quad?["combo_label"] as? String)
        case "ended":
            return .ended(reason: obj["reason"] as? String ?? "ended")
        default:
            return nil
        }
    }
}

/// Incremental Server-Sent-Events decoder. Feed raw bytes as they arrive; get complete `data:` payloads back.
struct SSEParser {
    private var line: [UInt8] = []
    private var data: [String] = []

    mutating func feed(_ bytes: Data) -> [String] {
        var out: [String] = []
        for b in bytes {
            if b == 0x0A {
                if let p = endLine() { out.append(p) }
            } else {
                line.append(b)
            }
        }
        return out
    }

    private mutating func endLine() -> String? {
        if line.last == 0x0D { line.removeLast() }
        let text = String(decoding: line, as: UTF8.self)
        line.removeAll(keepingCapacity: true)
        if text.isEmpty {                       // blank line = dispatch
            defer { data.removeAll() }
            return data.isEmpty ? nil : data.joined(separator: "\n")
        }
        if text.hasPrefix(":") { return nil }   // comment / keep-alive
        if text.hasPrefix("data:") {
            var v = text.dropFirst(5)
            if v.first == " " { v = v.dropFirst() }
            data.append(String(v))
        }
        return nil
    }
}

/// The live feed folded into what the UI needs. Pure value; `apply` reports a newly raised alert for notifications.
struct LiveModel: Equatable {
    var active = false
    var listening = false
    var alert: AlertLevel = .none
    var tier: String?
    var comboLabel: String?

    /// Returns the alert level to notify about, only when it CHANGED to amber or red.
    @discardableResult
    mutating func apply(_ e: LiveEvent) -> AlertLevel? {
        switch e {
        case let .state(a, l, _):
            active = a; listening = l
            if !a { reset() }
            return nil
        case let .verdict(_, stable, combo):
            let prev = alert
            active = true; listening = true
            alert = stable.alert; tier = stable.tier
            if let combo { comboLabel = combo }
            return (stable.alert != prev && stable.alert != .none) ? stable.alert : nil
        case .ended:
            active = false; listening = false; reset()
            return nil
        }
    }

    mutating func reset() { alert = .none; tier = nil; comboLabel = nil }
}

enum EngineHealth: Equatable { case unknown, up, down }

struct Inputs: Equatable {
    var consentGiven = false
    var enabled = true
    var pausedUntil: Date?
    var engine: EngineHealth = .unknown
    var engineGivenUp = false          // starting for too long, or crash-looping
    var listenerGivenUp = false
    var live = LiveModel()
}

enum Resolver {
    static func state(_ i: Inputs, now: Date) -> DisplayState {
        if !i.consentGiven || !i.enabled { return .off }
        if let until = i.pausedUntil, until > now { return .paused }
        if i.engineGivenUp || i.listenerGivenUp { return .engineProblem }
        if i.live.listening {
            switch i.live.alert { case .red: return .red; case .amber: return .amber; case .none: return .listening }
        }
        if i.engine == .down { return .engineProblem }
        return .waiting
    }
}
