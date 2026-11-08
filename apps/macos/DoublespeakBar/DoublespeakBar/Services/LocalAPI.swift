import Foundation

struct ReadyInfo: Equatable {
    var ready: Bool
    var privacyClean: Bool      // every switch in privacy_posture is false
    static func parse(_ data: Data) -> ReadyInfo? {
        guard let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
        let posture = obj["privacy_posture"] as? [String: Any] ?? [:]
        let anyOn = posture.values.contains { ($0 as? Bool) == true }
        return ReadyInfo(ready: obj["ready"] as? Bool ?? false, privacyClean: !posture.isEmpty && !anyOn)
    }
}

/// The engine's per-install API token (services/api/tell/api_token.py): a 0600 file the engine creates on first start.
/// Every data route (the live feed included) needs it; /ready does not. Never logged or shown.
enum APIToken {
    static func path(env: [String: String] = ProcessInfo.processInfo.environment,
                     home: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
        if let p = env["TELL_API_TOKEN_FILE"], !p.isEmpty { return URL(fileURLWithPath: (p as NSString).expandingTildeInPath) }
        return home.appendingPathComponent("Library/Application Support/Tell/api_token")
    }
    static func load(env: [String: String] = ProcessInfo.processInfo.environment,
                     home: URL = FileManager.default.homeDirectoryForCurrentUser) -> String? {
        if let t = env["TELL_API_TOKEN"]?.trimmingCharacters(in: .whitespacesAndNewlines), !t.isEmpty { return t }
        guard let s = try? String(contentsOf: path(env: env, home: home), encoding: .ascii) else { return nil }
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return valid(t) ? t : nil
    }
    static func valid(_ t: String) -> Bool {
        t.count >= 32 && t.count <= 128 && t.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-" || $0 == "_") }
    }
    /// The page's one-time pairing link: the token rides in the fragment, which the browser never sends to a server.
    static func pairURL(origin: String, token: String?) -> URL {
        guard let t = token, valid(t) else { return URL(string: origin)! }
        return URL(string: origin + "/#token=" + t)!
    }
}

/// The only network code in the app. Every URL is built from 127.0.0.1 (see StaticChecksTests).
struct LocalAPI {
    var port: Int
    static let uiOrigin = "http://localhost:5173"

    var base: URL { URL(string: "http://127.0.0.1:\(port)")! }
    static let session: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 4
        c.waitsForConnectivity = false
        c.urlCache = nil
        return URLSession(configuration: c)
    }()

    /// nil = nothing answered (or not our engine).
    func ready() async -> ReadyInfo? {
        var req = URLRequest(url: base.appendingPathComponent("ready"))
        req.setValue(Self.uiOrigin, forHTTPHeaderField: "Origin")
        guard let (data, resp) = try? await Self.session.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return ReadyInfo.parse(data)
    }

    static func pageIsUp() async -> Bool {
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(LaunchPlan.uiPort)/")!)
        req.timeoutInterval = 1.5
        guard let (_, resp) = try? await session.data(for: req) else { return false }
        return (resp as? HTTPURLResponse) != nil
    }

    /// Streams GET /live/events until the connection drops. Calls `onEvent` on the main actor.
    func streamEvents(onEvent: @escaping @MainActor (LiveEvent) -> Void) async {
        var req = URLRequest(url: base.appendingPathComponent("live/events"))
        req.setValue(Self.uiOrigin, forHTTPHeaderField: "Origin")
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let t = APIToken.load() { req.setValue(t, forHTTPHeaderField: "X-Tell-Token") }
        req.timeoutInterval = 3600
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 3600
        cfg.urlCache = nil
        let s = URLSession(configuration: cfg)
        defer { s.invalidateAndCancel() }
        guard let (bytes, resp) = try? await s.bytes(for: req), (resp as? HTTPURLResponse)?.statusCode == 200 else { return }
        var parser = SSEParser()
        var chunk = Data()
        do {
            for try await b in bytes {
                chunk.append(b)
                if b == 0x0A {
                    for payload in parser.feed(chunk) {
                        if let e = LiveEvent.parse(payload) { await onEvent(e) }
                    }
                    chunk.removeAll(keepingCapacity: true)
                }
            }
        } catch { return }
    }
}
