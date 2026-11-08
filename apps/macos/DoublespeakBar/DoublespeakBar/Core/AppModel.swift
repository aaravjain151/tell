import Foundation
import SwiftUI

/// Owns the children, the health poll, the live feed and the pause timer. The menu reads only `display` and the text fields.
@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var inputs = Inputs()
    @Published private(set) var privacy: Bool?            // nil = unknown yet
    @Published private(set) var setupProblem: String?
    @Published private(set) var notifications: Notifier.Permission = .unknown
    @Published private(set) var loginItemOn = false
    @Published private(set) var loginItemNote: String?
    @Published var repoPath: String { didSet { prefs.repoPath = repoPath } }
    @Published var port: Int { didSet { prefs.port = port } }
    @Published var sound: Bool { didSet { prefs.sound = sound } }

    private var prefs = Prefs()
    private let launcher: ChildLauncher
    private let notifier = Notifier()
    private var engine: ProcessSupervisor?
    private var listener: ProcessSupervisor?
    private var page: ProcessSupervisor?
    private var tick: Timer?
    private var feed: Task<Void, Never>?
    private var engineStartedAt: Date?
    private var started = false
    private(set) var recentLines: [String] = []

    init(launcher: ChildLauncher = ProcessLauncher()) {
        self.launcher = launcher
        repoPath = prefs.repoPath
        port = prefs.port
        sound = prefs.sound
        inputs.consentGiven = prefs.consentGiven
        inputs.enabled = prefs.enabled
        loginItemOn = LoginItem.isOn
    }

    var display: DisplayState { Resolver.state(inputs, now: Date()) }
    var needsOnboarding: Bool { !inputs.consentGiven }
    var enabled: Bool { inputs.enabled }
    var pausedUntil: Date? { inputs.pausedUntil.flatMap { $0 > Date() ? $0 : nil } }
    var uiURL: URL { URL(string: LocalAPI.uiOrigin)! }

    #if DEBUG
    /// Test and snapshot hook: show a given state without starting anything.
    func debugShow(_ i: Inputs, privacy: Bool? = true) { inputs = i; self.privacy = privacy }
    #endif

    // MARK: lifecycle

    func launch() {
        Task { notifications = await notifier.current() }
        guard !started else { return }
        started = true
        tick = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.poll() }
        }
        Task { await poll() }
    }

    func quit() { NSApp.terminate(nil) }

    /// Stops both children (and the page server) and waits for them, so no stray process outlives the app.
    func stopForQuit() {
        tick?.invalidate()
        feed?.cancel()
        let all = [listener, engine, page].compactMap { $0 }
        all.forEach { $0.stop() }
        all.forEach { $0.waitForExit(timeout: 4) }    // SIGINT lets the listener wipe its RAM ring and close the tap
    }

    func acceptConsent() {
        prefs.consentGiven = true
        inputs.consentGiven = true
        Task { await poll() }
    }

    func setEnabled(_ on: Bool) {
        prefs.enabled = on
        inputs.enabled = on
        if !on { stopChildren() }
        Task { await poll() }
    }

    func pauseForOneHour() {
        inputs.pausedUntil = Date().addingTimeInterval(3600)
        listener?.stop(); listener = nil
        inputs.live = LiveModel()
    }

    func resume() {
        inputs.pausedUntil = nil
        Task { await poll() }
    }

    func restartAll() {
        stopChildren()
        inputs.engineGivenUp = false; inputs.listenerGivenUp = false
        Task { await poll() }
    }

    func requestNotifications() { Task { notifications = await notifier.request() } }

    func setLaunchAtLogin(_ on: Bool) {
        loginItemNote = LoginItem.set(on)
        loginItemOn = LoginItem.isOn
        if on && LoginItem.needsApproval { loginItemNote = "Approve Doublespeak in System Settings, Login Items." }
    }

    func openDoublespeak() {
        Task {
            if !(await LocalAPI.pageIsUp()) { await ensurePage() }
            NSWorkspace.shared.open(uiURL)
        }
    }

    // MARK: supervision

    private func stopChildren() {
        feed?.cancel(); feed = nil
        listener?.stop(); listener = nil
        engine?.stop(); engine = nil
        page?.stop(); page = nil
        inputs.live = LiveModel()
        inputs.engine = .unknown
        engineStartedAt = nil
    }

    private func remember(_ line: String) {
        recentLines.append(line)
        if recentLines.count > 40 { recentLines.removeFirst(recentLines.count - 40) }
    }

    private func make(_ spec: LaunchSpec) -> ProcessSupervisor {
        let s = ProcessSupervisor(spec: spec, launcher: launcher)
        s.onLine = { [weak self] line in self?.remember("[\(spec.name)] \(line)") }
        s.onChange = { [weak self] in self?.objectWillChange.send() }
        return s
    }

    private func ensurePage() async {
        guard page == nil, !(await LocalAPI.pageIsUp()) else { return }
        let s = make(LaunchPlan.page(repo: repoPath, home: NSHomeDirectory()))
        page = s
        s.start()
    }

    private func poll() async {
        if let until = inputs.pausedUntil, until <= Date() { inputs.pausedUntil = nil }
        objectWillChange.send()                              // refreshes "paused" countdowns and times
        guard inputs.consentGiven, inputs.enabled, pausedUntil == nil else { return }

        setupProblem = LaunchPlan.repoProblem(repoPath)
        guard setupProblem == nil else { inputs.engineGivenUp = true; return }

        let info = await LocalAPI(port: port).ready()
        if let info {
            inputs.engine = .up
            inputs.engineGivenUp = false
            engineStartedAt = nil
            privacy = info.privacyClean
            startListenerIfNeeded()
            startFeedIfNeeded()
            await ensurePage()
        } else {
            if inputs.engine == .up { inputs.engine = .down; inputs.live = LiveModel() }
            feed?.cancel(); feed = nil
            startEngineIfNeeded()
            if let t = engineStartedAt, Date().timeIntervalSince(t) > 120 { inputs.engineGivenUp = true }
            if engine?.gaveUp == true { inputs.engineGivenUp = true }
        }
        if listener?.gaveUp == true { inputs.listenerGivenUp = true }
    }

    private func startEngineIfNeeded() {
        if let e = engine, e.status != .stopped { return }
        let fm = FileManager.default
        let cached = fm.fileExists(atPath: LaunchPlan.hubCacheDir(home: NSHomeDirectory()))
        let envFile = fm.fileExists(atPath: repoPath + "/.env")      // existence only; never opened by this app
        let spec = LaunchPlan.engine(repo: repoPath, port: port, weightsCached: cached, envFileExists: envFile, home: NSHomeDirectory())
        let s = make(spec)
        engine = s
        engineStartedAt = Date()
        inputs.engine = .down
        s.start()
    }

    private func startListenerIfNeeded() {
        guard listener == nil else { return }
        let s = make(LaunchPlan.listener(repo: repoPath, port: port, home: NSHomeDirectory()))
        listener = s
        s.start()
    }

    private func startFeedIfNeeded() {
        guard feed == nil else { return }
        let api = LocalAPI(port: port)
        feed = Task { [weak self] in
            while !Task.isCancelled {
                await api.streamEvents { e in self?.handle(e) }
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if self?.feed == nil { return }
            }
        }
    }

    func handle(_ e: LiveEvent) {
        let notify = inputs.live.apply(e)
        if let level = notify, notifications == .allowed, pausedUntil == nil {
            notifier.post(level, sound: sound)
        }
    }

    // MARK: words for the menu

    var title: String {
        switch display {
        case .off: return needsOnboarding ? "Finish setup" : "Doublespeak is off"
        case .waiting: return "Waiting for a call"
        case .listening: return "Listening to this call"
        case .amber: return "Possible scam call"
        case .red: return "Likely scam call"
        case .paused: return "Paused"
        case .engineProblem: return "Engine problem"
        }
    }

    var detail: String {
        switch display {
        case .off: return needsOnboarding ? "Read the privacy note to turn it on." : "Turn it on to be warned about scam calls."
        case .waiting: return "It starts listening by itself when a call plays on this Mac."
        case .listening: return "Analysing on this Mac. Nothing is recorded or sent."
        case .amber: return "Be careful with money and codes."
        case .red: return "Do not share money, codes or passwords."
        case .paused:
            if let u = pausedUntil { return "Not listening until \(u.formatted(date: .omitted, time: .shortened))." }
            return "Not listening."
        case .engineProblem: return problemText
        }
    }

    var problemText: String {
        if let p = setupProblem { return p }
        let tail = recentLines.last { $0.hasPrefix("[engine]") } ?? recentLines.last ?? ""
        if tail.localizedCaseInsensitiveContains("address already in use") {
            return "Port \(port) is used by another program. Change the port in Settings or quit that program."
        }
        if listener?.gaveUp == true { return "The call listener keeps stopping. Try Restart." }
        return "The engine is not answering on port \(port). Try Restart, or open Settings to check the folder."
    }

    var verdictLine: String? {
        guard display == .listening || display == .amber || display == .red else { return nil }
        return inputs.live.comboLabel ?? "Still listening: not enough speech yet to judge."
    }

    var privacyRow: String {
        switch privacy {
        case .some(true): return "Privacy: 0 bytes sent"
        case .some(false): return "Privacy: a setting could send data out. Open Settings."
        case .none: return "Privacy: checking the engine"
        }
    }

    var stateDescription: String { display.rawValue }
}
