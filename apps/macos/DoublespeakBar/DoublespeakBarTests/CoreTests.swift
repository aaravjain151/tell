import XCTest
@testable import Doublespeak

final class SSETests: XCTestCase {
    func feedAll(_ chunks: [String]) -> [String] {
        var p = SSEParser()
        return chunks.flatMap { p.feed($0.data(using: .utf8)!) }
    }

    func testSingleFrame() {
        XCTAssertEqual(feedAll(["data: {\"type\":\"ended\"}\n\n"]), ["{\"type\":\"ended\"}"])
    }
    func testFrameSplitAcrossChunksAndCRLF() {
        XCTAssertEqual(feedAll(["da", "ta: {\"a\":1}\r", "\n\r\n", "data: 2\n\n"]), ["{\"a\":1}", "2"])
    }
    func testCommentsAndKeepAliveIgnored() {
        XCTAssertEqual(feedAll([": ping\n\n", "data: x\n\n"]), ["x"])
    }
    func testMultiLineData() {
        XCTAssertEqual(feedAll(["data: a\ndata: b\n\n"]), ["a\nb"])
    }
    func testNoDispatchWithoutBlankLine() {
        XCTAssertEqual(feedAll(["data: pending\n"]), [])
    }
}

final class EventParseTests: XCTestCase {
    func testState() {
        XCTAssertEqual(LiveEvent.parse(#"{"type":"state","active":true,"source":"tap","elapsed_s":3.0,"listening":true}"#),
                       .state(active: true, listening: true, source: "tap"))
    }
    func testVerdictWithComboAndAlert() {
        let j = #"{"type":"verdict","tick":4,"elapsed_s":12,"verdict":{"quadrant":{"combo":"ai_scam","combo_label":"AI voice and scam pattern in what was said."}},"stable":{"tier":"scam","state":"escalated","alert":"amber","since_s":1,"reasons":[]}}"#
        XCTAssertEqual(LiveEvent.parse(j), .verdict(tick: 4, stable: StableInfo(tier: "scam", state: "escalated", alert: .amber),
                                                    comboLabel: "AI voice and scam pattern in what was said."))
    }
    func testVerdictWithoutQuadrant() {
        let j = #"{"type":"verdict","tick":1,"stable":{"tier":"warming_up","state":"warming","alert":"none"}}"#
        XCTAssertEqual(LiveEvent.parse(j), .verdict(tick: 1, stable: StableInfo(tier: "warming_up", state: "warming", alert: .none), comboLabel: nil))
    }
    func testEnded() { XCTAssertEqual(LiveEvent.parse(#"{"type":"ended","reason":"stop"}"#), .ended(reason: "stop")) }
    func testGarbageAndUnknownReturnNil() {
        XCTAssertNil(LiveEvent.parse("not json"))
        XCTAssertNil(LiveEvent.parse(#"{"type":"mystery"}"#))
        XCTAssertNil(LiveEvent.parse(#"{"type":"verdict"}"#))
        XCTAssertNil(LiveEvent.parse(#"[1,2]"#))
    }
    func testUnknownAlertIsNone() {
        let j = #"{"type":"verdict","tick":1,"stable":{"tier":"human","state":"steady","alert":"purple"}}"#
        if case let .verdict(_, s, _)? = LiveEvent.parse(j) { XCTAssertEqual(s.alert, .none) } else { XCTFail() }
    }
    func testReadyInfo() {
        let clean = #"{"ready":true,"privacy_posture":{"debug_save":false,"llm_provider_anthropic":false,"gradium_key_set":false}}"#.data(using: .utf8)!
        XCTAssertEqual(ReadyInfo.parse(clean), ReadyInfo(ready: true, privacyClean: true))
        let dirty = #"{"ready":false,"privacy_posture":{"debug_save":true}}"#.data(using: .utf8)!
        XCTAssertEqual(ReadyInfo.parse(dirty), ReadyInfo(ready: false, privacyClean: false))
        let none = #"{"ready":true}"#.data(using: .utf8)!
        XCTAssertEqual(ReadyInfo.parse(none)?.privacyClean, false)
    }
}

final class StateMachineTests: XCTestCase {
    let now = Date(timeIntervalSince1970: 1_000_000)
    func base() -> Inputs { var i = Inputs(); i.consentGiven = true; i.engine = .up; return i }
    func stable(_ a: AlertLevel) -> LiveEvent { .verdict(tick: 1, stable: StableInfo(tier: "scam", state: "escalated", alert: a), comboLabel: "x") }

    func testOffBeforeConsentOrWhenDisabled() {
        var i = base(); i.consentGiven = false
        XCTAssertEqual(Resolver.state(i, now: now), .off)
        i = base(); i.enabled = false
        XCTAssertEqual(Resolver.state(i, now: now), .off)
    }
    func testWaitingWhenArmedAndIdle() { XCTAssertEqual(Resolver.state(base(), now: now), .waiting) }
    func testListeningThenAlertsThenEnd() {
        var i = base()
        i.live.apply(.state(active: true, listening: true, source: "tap"))
        XCTAssertEqual(Resolver.state(i, now: now), .listening)
        i.live.apply(stable(.amber)); XCTAssertEqual(Resolver.state(i, now: now), .amber)
        i.live.apply(stable(.red)); XCTAssertEqual(Resolver.state(i, now: now), .red)
        i.live.apply(.ended(reason: "stop")); XCTAssertEqual(Resolver.state(i, now: now), .waiting)
        XCTAssertNil(i.live.comboLabel)
    }
    func testPausedWinsOverListeningAndExpires() {
        var i = base(); i.live.apply(stable(.none))
        i.pausedUntil = now.addingTimeInterval(60)
        XCTAssertEqual(Resolver.state(i, now: now), .paused)
        XCTAssertEqual(Resolver.state(i, now: now.addingTimeInterval(61)), .listening)
    }
    func testEngineProblem() {
        var i = base(); i.engine = .down
        XCTAssertEqual(Resolver.state(i, now: now), .engineProblem)
        i = base(); i.listenerGivenUp = true
        XCTAssertEqual(Resolver.state(i, now: now), .engineProblem)
    }
    func testCallKeepsShowingWhileEngineBlipsDown() {
        var i = base(); i.live.apply(stable(.none)); i.engine = .down
        XCTAssertEqual(Resolver.state(i, now: now), .listening)   // never hide a live call because one poll failed
    }
    func testNotifiesOnlyWhenAlertChangesToAmberOrRed() {
        var m = LiveModel()
        XCTAssertNil(m.apply(stable(.none)))
        XCTAssertEqual(m.apply(stable(.amber)), .amber)
        XCTAssertNil(m.apply(stable(.amber)))              // unchanged: no repeat
        XCTAssertEqual(m.apply(stable(.red)), .red)
        XCTAssertNil(m.apply(stable(.none)))               // going down never notifies
        XCTAssertEqual(m.apply(stable(.amber)), .amber)    // a new rise does
    }
    func testNotificationWordingIsFixedAndCarriesNoCallerText() {
        XCTAssertEqual(Wording.notification(for: .amber), "Possible scam call. Be careful with money and codes.")
        XCTAssertEqual(Wording.notification(for: .red), "Likely scam call. Do not share money, codes or passwords.")
        XCTAssertNil(Wording.notification(for: .none))
    }
    func testEveryStateHasASymbolAndAName() {
        XCTAssertEqual(Set(DisplayState.allCases.map(\.symbol)).count, DisplayState.allCases.count)   // shape, not colour only
        DisplayState.allCases.forEach { XCTAssertFalse($0.accessibilityName.isEmpty) }
    }
}

// MARK: supervisor with a fake child

final class FakeChild: ChildHandle {
    var isRunning = true
    var stopped: [Int32] = []
    var killed = false
    func stop(signal: Int32) { stopped.append(signal) }
    func kill() { killed = true; isRunning = false }
}

final class FakeLauncher: ChildLauncher {
    var children: [FakeChild] = []
    var exits: [(Int32) -> Void] = []
    var lines: [(String) -> Void] = []
    var failNext = false
    func launch(_ spec: LaunchSpec, onLine: @escaping (String) -> Void, onExit: @escaping (Int32) -> Void) throws -> ChildHandle {
        if failNext { failNext = false; throw NSError(domain: "x", code: 1, userInfo: [NSLocalizedDescriptionKey: "nope"]) }
        let c = FakeChild(); children.append(c); exits.append(onExit); lines.append(onLine)
        return c
    }
}

final class FakeScheduler: Scheduler {
    var now = Date(timeIntervalSince1970: 0)
    var pending: [(at: TimeInterval, id: Int, block: () -> Void)] = []
    var delays: [TimeInterval] = []
    private var nextId = 0
    func after(_ seconds: TimeInterval, _ block: @escaping () -> Void) -> () -> Void {
        delays.append(seconds); nextId += 1; let id = nextId
        pending.append((now.timeIntervalSince1970 + seconds, id, block))
        return { [weak self] in self?.pending.removeAll { $0.id == id } }
    }
    func advance(_ s: TimeInterval) {
        now = now.addingTimeInterval(s)
        let due = pending.filter { $0.at <= now.timeIntervalSince1970 }.sorted { $0.at < $1.at }
        pending.removeAll { p in due.contains { $0.id == p.id } }
        due.forEach { $0.block() }
    }
}

final class SupervisorTests: XCTestCase {
    let spec = LaunchSpec(name: "t", executable: "/bin/true", arguments: [], cwd: "/", environment: [:])

    /// The supervisor hops exit callbacks through DispatchQueue.main; spin the run loop so they land.
    func settle() { RunLoop.main.run(until: Date().addingTimeInterval(0.05)) }

    func make() -> (ProcessSupervisor, FakeLauncher, FakeScheduler) {
        let l = FakeLauncher(), s = FakeScheduler()
        return (ProcessSupervisor(spec: spec, launcher: l, scheduler: s), l, s)
    }

    func testStartsAndStopsWithSpecifiedSignal() {
        var sp = spec; sp.stopSignal = SIGINT
        let l = FakeLauncher()
        let sup = ProcessSupervisor(spec: sp, launcher: l, scheduler: FakeScheduler())
        sup.start()
        XCTAssertTrue(sup.isRunning)
        sup.stop()
        XCTAssertEqual(l.children[0].stopped, [SIGINT])
        XCTAssertEqual(sup.status, .stopped)
    }

    func testRestartsOnCrashWithGrowingBackoff() {
        let (sup, l, s) = make()
        sup.start()
        for expected in [1.0, 2.0, 4.0] {
            let n = l.children.count
            l.exits.last!(1); settle()
            XCTAssertEqual(s.delays.last, expected)
            XCTAssertEqual(sup.status, .backingOff(failures: Int(log2(expected)) + 1))
            s.advance(expected)
            XCTAssertEqual(l.children.count, n + 1, "relaunched after \(expected)s")
            XCTAssertTrue(sup.isRunning)
        }
    }

    func testBackoffCapsAndGivesUpFlagAfterFastFailures() {
        XCTAssertEqual(Backoff.delay(afterFailures: 10), 30)
        let (sup, l, s) = make()
        sup.start()
        for _ in 0..<4 { l.exits.last!(1); settle(); s.advance(60) }
        XCTAssertTrue(sup.gaveUp)
        XCTAssertGreaterThanOrEqual(sup.restarts, 4)
    }

    func testHealthyRunResetsBackoff() {
        let (sup, l, s) = make()
        sup.start()
        l.exits.last!(1); settle(); s.advance(1)            // 1 failure, relaunched
        s.advance(120)                                      // ran two minutes
        l.exits.last!(1); settle()
        XCTAssertEqual(s.delays.last, 1, "backoff restarted from the bottom")
    }

    func testStopCancelsPendingRestartAndIgnoresLateExit() {
        let (sup, l, s) = make()
        sup.start()
        l.exits[0](1); settle()
        sup.stop()
        s.advance(60)
        XCTAssertEqual(l.children.count, 1, "no relaunch after stop")
        l.exits[0](0); settle()
        XCTAssertEqual(sup.status, .stopped)
    }

    func testLaunchFailureBacksOffInsteadOfCrashing() {
        let (sup, l, s) = make()
        l.failNext = true
        sup.start()
        XCTAssertEqual(sup.status, .backingOff(failures: 1))
        s.advance(1)
        XCTAssertTrue(sup.isRunning)
    }

    func testStopKillsStubbornChildAfterGrace() {
        let (sup, l, s) = make()
        sup.start(); sup.stop()
        XCTAssertFalse(l.children[0].killed)
        s.advance(5)
        XCTAssertTrue(l.children[0].killed)
    }

    func testLinesPassThrough() {
        let (sup, l, _) = make()
        var got: [String] = []
        sup.onLine = { got.append($0) }
        sup.start()
        l.lines[0]("=== LISTENING (tap) ==="); settle()
        XCTAssertEqual(got, ["=== LISTENING (tap) ==="])
    }
}

final class LaunchPlanTests: XCTestCase {
    func testEngineArgumentsAndPellaEnv() {
        let s = LaunchPlan.engine(repo: "/r", port: 8010, weightsCached: true, envFileExists: true, home: "/h")
        XCTAssertEqual(s.executable, "/r/.venv/bin/python")
        XCTAssertEqual(s.arguments, ["-m", "uvicorn", "tell.main:app", "--host", "127.0.0.1", "--port", "8010", "--env-file", "/r/.env"])
        XCTAssertEqual(s.cwd, "/r/services/api")
        XCTAssertEqual(s.environment["PELLA_MODEL"], "Sadanie/pellav2-audio-deepfake-detector")
        XCTAssertEqual(s.environment["PELLA_DEVICE"], "mps")
    }
    func testNoWeightsNoEnvFile() {
        let s = LaunchPlan.engine(repo: "/r", port: 8000, weightsCached: false, envFileExists: false, home: "/h")
        XCTAssertNil(s.environment["PELLA_MODEL"]); XCTAssertNil(s.environment["PELLA_DEVICE"])
        XCTAssertFalse(s.arguments.contains("--env-file"))
    }
    func testListenerArguments() {
        let s = LaunchPlan.listener(repo: "/r", port: 8000, home: "/h")
        XCTAssertEqual(s.arguments, ["/r/tools/macos/listen.py", "--watch", "--i-understand", "--no-notify", "--url", "http://127.0.0.1:8000"])
        XCTAssertEqual(s.stopSignal, SIGINT)
        XCTAssertTrue(s.executable.hasPrefix("/"))
    }
    func testChildEnvironmentCarriesNoSecrets() {
        let s = LaunchPlan.engine(repo: "/r", port: 8000, weightsCached: true, envFileExists: true, home: "/h")
        XCTAssertEqual(Set(s.environment.keys), ["HOME", "PATH", "LANG", "PYTHONUNBUFFERED", "PELLA_MODEL", "PELLA_DEVICE"])
    }
    func testRepoProblemWording() {
        XCTAssertNotNil(LaunchPlan.repoProblem("/definitely/not/here"))
    }
    /// D-013: the engine package is `tell`; a checkout from before the rename only has `doublespeak` and must still start.
    func testEngineTargetFollowsTheCheckout() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("tell-target-\(UUID().uuidString)")
        defer { try? fm.removeItem(at: root) }
        let api = root.appendingPathComponent("services/api")
        try fm.createDirectory(at: api.appendingPathComponent("doublespeak"), withIntermediateDirectories: true)
        fm.createFile(atPath: api.appendingPathComponent("doublespeak/main.py").path, contents: Data())
        XCTAssertEqual(LaunchPlan.resolveTarget(repo: root.path), "doublespeak.main:app")
        try fm.createDirectory(at: api.appendingPathComponent("tell"), withIntermediateDirectories: true)
        fm.createFile(atPath: api.appendingPathComponent("tell/main.py").path, contents: Data())
        XCTAssertEqual(LaunchPlan.resolveTarget(repo: root.path), "tell.main:app")
        XCTAssertEqual(LaunchPlan.resolveTarget(repo: "/definitely/not/here"), "tell.main:app")
        let s = LaunchPlan.engine(repo: "/r", port: 8000, weightsCached: false, envFileExists: false, home: "/h",
                                  target: LaunchPlan.legacyTarget)
        XCTAssertEqual(s.arguments[2], "doublespeak.main:app")
    }
}

// MARK: static privacy checks (read the source tree and the built app's plist)

final class StaticChecksTests: XCTestCase {
    var sourceDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("DoublespeakBar")
    }
    func swiftFiles() -> [URL] {
        let e = FileManager.default.enumerator(at: sourceDir, includingPropertiesForKeys: nil)!
        return e.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
    }

    func testSourcesExist() { XCTAssertGreaterThan(swiftFiles().count, 8) }

    func testEveryURLInTheAppIsLoopback() throws {
        let re = try NSRegularExpression(pattern: #"https?://([A-Za-z0-9.\-_$\\()]+)"#)
        for f in swiftFiles() {
            let text = try String(contentsOf: f, encoding: .utf8)
            for m in re.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
                let host = String(text[Range(m.range(at: 1), in: text)!])
                XCTAssertTrue(host.hasPrefix("127.0.0.1") || host.hasPrefix("localhost"), "\(f.lastPathComponent) mentions non-loopback host \(host)")
            }
        }
    }

    func testNoAnalyticsOrThirdPartyStrings() throws {
        let banned = ["analytics", "telemetry", "firebase", "sentry", "mixpanel", "amplitude", "segment.io", "crashlytics",
                      "google-analytics", "appcenter", "bugsnag", "posthog", "datadog"]
        for f in swiftFiles() {
            let text = try String(contentsOf: f, encoding: .utf8).lowercased()
            // this very file lists the banned words; the other sources must not contain them
            if f.lastPathComponent == "CoreTests.swift" { continue }
            for w in banned { XCTAssertFalse(text.contains(w), "\(f.lastPathComponent) contains \(w)") }
        }
    }

    func testNoExternalDependenciesDeclared() throws {
        let yml = try String(contentsOf: sourceDir.deletingLastPathComponent().appendingPathComponent("project.yml"), encoding: .utf8)
        XCTAssertFalse(yml.contains("packages:"))
        XCTAssertFalse(yml.contains("sdk: "))
    }

    func testNoNetworkEntitlementBeyondClientAndNoServer() throws {
        // The app is not sandboxed, so there is no entitlements file to grant network access. If one is ever added it may
        // hold at most com.apple.security.network.client (loopback client calls) and never .server.
        let root = sourceDir.deletingLastPathComponent()
        let ents = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)!
            .compactMap { $0 as? URL }.filter { $0.pathExtension == "entitlements" }
        for u in ents {
            let text = try String(contentsOf: u, encoding: .utf8)
            XCTAssertFalse(text.contains("com.apple.security.network.server"))
            let keys = text.components(separatedBy: "com.apple.security.network.").dropFirst().map { String($0.prefix { $0.isLetter }) }
            XCTAssertTrue(Set(keys).isSubset(of: ["client"]), "\(u.lastPathComponent) grants \(keys)")
        }
    }

    func testBuiltAppHasNoNetworkEntitlementsAndIsMenuBarOnly() throws {
        let app = Bundle.main.bundleURL.path.hasSuffix("Tell.app") ? Bundle.main : Bundle(identifier: "dev.doublespeak.app.mac")
        let info = app?.infoDictionary ?? [:]
        XCTAssertEqual(info["LSUIElement"] as? Bool, true)
        XCTAssertNotNil(info["NSAudioCaptureUsageDescription"])
        XCTAssertNil(info["NSAppTransportSecurity"], "no ATS exceptions: loopback http works without any")
        XCTAssertNil(info["NSMicrophoneUsageDescription"], "the near-end microphone is never captured")
    }

    func testLoginItemUsesOnlySMAppService() throws {
        for f in swiftFiles() {
            let text = try String(contentsOf: f, encoding: .utf8)
            XCTAssertFalse(text.contains("LaunchAgents"), f.lastPathComponent)
            XCTAssertFalse(text.contains("LSSharedFileList"), f.lastPathComponent)
        }
    }

    func testAppNeverOpensDotEnv() throws {
        for f in swiftFiles() {
            let text = try String(contentsOf: f, encoding: .utf8)
            for line in text.split(separator: "\n") where line.contains(".env") {
                XCTAssertFalse(line.contains("contentsOf") || line.contains("FileHandle(forReading") || line.contains("contents(atPath"), "\(f.lastPathComponent): \(line)")
            }
        }
    }
}

// MARK: per-install API token (services/api/tell/api_token.py)

final class APITokenTests: XCTestCase {
    let tok = String(repeating: "a", count: 20) + "B_c-" + String(repeating: "9", count: 19)

    func testReadsTheEngineFileUnderApplicationSupport() throws {
        let home = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let dir = home.appendingPathComponent("Library/Application Support/Tell")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try (tok + "\n").write(to: dir.appendingPathComponent("api_token"), atomically: true, encoding: .ascii)
        XCTAssertEqual(APIToken.path(env: [:], home: home), dir.appendingPathComponent("api_token"))
        XCTAssertEqual(APIToken.load(env: [:], home: home), tok)
        XCTAssertNil(APIToken.load(env: [:], home: home.appendingPathComponent("nope")))
    }

    func testEnvOverridesAndBadTokensAreRefused() {
        XCTAssertEqual(APIToken.load(env: ["TELL_API_TOKEN": tok], home: URL(fileURLWithPath: "/nonexistent")), tok)
        XCTAssertFalse(APIToken.valid("short"))
        XCTAssertFalse(APIToken.valid(tok + " x"))
        XCTAssertTrue(APIToken.valid(tok))
    }

    func testPairURLPutsTheTokenInTheFragmentOnly() {
        let u = APIToken.pairURL(origin: LocalAPI.uiOrigin, token: tok)
        XCTAssertEqual(u.host, "localhost")
        XCTAssertEqual(u.fragment, "token=" + tok)
        XCTAssertNil(u.query)
        XCTAssertEqual(APIToken.pairURL(origin: LocalAPI.uiOrigin, token: nil).absoluteString, LocalAPI.uiOrigin)
    }
}
