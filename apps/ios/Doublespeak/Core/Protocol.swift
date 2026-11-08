import Foundation

/// Messages between the phone (WebSocket server on the phone's loopback) and tools/ios/bridge.py on the Mac.
///
///   bridge -> phone   {"type":"auth","token":"XXXX-XXXX"}            first message, within 5 s
///   phone  -> bridge  {"type":"ready","app":"ios","v":1}            token accepted
///   phone  -> bridge  {"type":"started"}  then binary PCM16 16 kHz mono frames, 3200 bytes (100 ms) each
///   phone  -> bridge  {"type":"stopped"}  |  {"type":"dismiss"}
///   bridge -> phone   {"type":"engine","status":"up|down|busy|refused|error","detail":"..."}
///   bridge -> phone   {"type":"tick","tick":n,"elapsed_s":x,"verdict":{...},"stable":{...}}   (the engine's /live/events payload)
///   bridge -> phone   {"type":"ended","reason":"..."}
enum Protocol {
    #if DEBUG
    static let port: UInt16 = {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-DSPort"), i + 1 < a.count, let p = UInt16(a[i + 1]) { return p }
        return 8765
    }()
    #else
    static let port: UInt16 = 8765
    #endif
    static let version = 1
    static let maxTextBytes = 256 * 1024

    enum Outbound: Equatable {
        case ready, started, stopped, dismiss

        var json: String {
            switch self {
            case .ready: return "{\"type\":\"ready\",\"app\":\"ios\",\"v\":\(Protocol.version)}"
            case .started: return "{\"type\":\"started\"}"
            case .stopped: return "{\"type\":\"stopped\"}"
            case .dismiss: return "{\"type\":\"dismiss\"}"
            }
        }
    }

    enum EngineStatus: String, Equatable { case up, down, busy, refused, error }

    enum Inbound: Equatable {
        case auth(token: String)
        case engine(EngineStatus, detail: String)
        case tick(TickPayload)
        case ended(reason: String)
        case unknown

        static func == (l: Inbound, r: Inbound) -> Bool {
            switch (l, r) {
            case let (.auth(a), .auth(b)): return a == b
            case let (.engine(a, x), .engine(b, y)): return a == b && x == y
            case let (.tick(a), .tick(b)): return a.tick == b.tick
            case let (.ended(a), .ended(b)): return a == b
            case (.unknown, .unknown): return true
            default: return false
            }
        }
    }

    /// Lenient parse: bad JSON, oversize text and unknown types all come back as `.unknown`, never a crash.
    static func parse(_ text: String) -> Inbound {
        guard text.utf8.count <= maxTextBytes, let data = text.data(using: .utf8),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let type = obj["type"] as? String else { return .unknown }
        switch type {
        case "auth":
            return .auth(token: obj["token"] as? String ?? "")
        case "engine":
            let s = EngineStatus(rawValue: obj["status"] as? String ?? "") ?? .error
            return .engine(s, detail: obj["detail"] as? String ?? "")
        case "tick":
            guard let t = try? JSONDecoder().decode(TickPayload.self, from: data) else { return .unknown }
            return .tick(t)
        case "ended":
            return .ended(reason: obj["reason"] as? String ?? "ended")
        default:
            return .unknown
        }
    }
}
