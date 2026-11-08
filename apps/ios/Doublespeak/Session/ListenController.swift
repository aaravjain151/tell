import Foundation
import SwiftUI
import UIKit

enum Mode: Equatable { case offline, idle, listening, ended }
enum Sheet: String, Identifiable { case consent, speaker, connect, blocked; var id: String { rawValue } }

struct Notice: Equatable { var title: String; var body: String }

@MainActor
final class ListenController: ObservableObject {
    static let consentText = "Tell listens to this call through your microphone on your phone and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it."
    static let meterCells = 24

    @Published var mode: Mode = .offline
    @Published var engine: Protocol.EngineStatus?
    @Published var mic: MicAccess = MicCapture.access
    @Published var verdict: VerdictView?
    @Published var showAlert = false
    @Published var notice: Notice?
    @Published var levels = [Double](repeating: 0, count: ListenController.meterCells)
    @Published var elapsed: Double = 0
    @Published var micFlat = false
    @Published var interrupted = false
    @Published var callActive = false
    @Published var sheet: Sheet?
    @Published var listenerFailed: String?
    #if DEBUG
    let token: String = {
        let a = ProcessInfo.processInfo.arguments
        if let i = a.firstIndex(of: "-DSToken"), i + 1 < a.count { return PairingToken.normalize(a[i + 1]) }
        return PairingToken.generate()
    }()
    #else
    let token = PairingToken.generate()
    #endif

    private let server = LoopbackServer()
    private let capture = MicCapture()
    private var startedAt: Date?
    private var clock: Timer?
    private var silentFrames = 0
    private var redDismissed = false
    private var lastAlert = "none"
    private var pendingStartAfterConsent = false
    private var bridgeConnected = false
    #if DEBUG
    private let feeder = DebugWavFeeder()
    #endif

    var bridgeUp: Bool { mode != .offline }
    var consentAccepted: Bool {
        get { UserDefaults.standard.bool(forKey: "consentAccepted.v1") }
        set { UserDefaults.standard.set(newValue, forKey: "consentAccepted.v1") }
    }

    private let calls: CallObserving

    var callBanner: CallBanner? { CallBanner.current(callActive: callActive, listening: mode == .listening, interrupted: interrupted) }

    init(callObserver: CallObserving = SystemCallObserver()) {
        calls = callObserver
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-DSResetConsent") { consentAccepted = false }
        #endif
        server.onEvent = { [weak self] e in self?.handle(e) }
        capture.onFrame = { [weak self] f in self?.frame(f) }
        capture.onInterruption = { [weak self] began in Task { @MainActor in self?.interrupted = began } }
        #if DEBUG
        feeder.onFrame = { [weak self] f in self?.frame(f) }
        #endif
    }

    func boot() {
        observeCalls()
        server.start(token: token)
        mic = MicCapture.access
        if !consentAccepted { sheet = .consent }
        #if DEBUG
        DebugDemo.apply(to: self)
        #endif
    }

    // MARK: server events

    private func handle(_ e: LoopbackServer.Event) {
        switch e {
        case .listening: listenerFailed = nil
        case .failed(let why): listenerFailed = why
        case .clientAuthenticated:
            bridgeConnected = true
            if mode == .offline { mode = .idle }
            notice = nil
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-DSAutoStart") {
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in self?.startTapped() }
            }
            #endif
        case .clientGone:
            bridgeConnected = false
            if mode == .listening { stopCapture(); mode = .ended
                notice = Notice(title: "Lost contact with your computer", body: "Check the USB cable and that the bridge is still running. Listening stopped.")
            } else if mode != .ended { mode = .offline }
            engine = nil
        case .message(let m): inbound(m)
        }
    }

    func inbound(_ m: Protocol.Inbound) {
        switch m {
        case .engine(let st, let detail):
            engine = st
            if st != .up, mode == .listening {
                stopCapture(); mode = .ended
                switch st {
                case .busy: notice = Notice(title: "Another listening session is open", body: "Stop it on your computer, or wait a minute, then start again.")
                case .refused: notice = Notice(title: "The engine refused this connection", body: "Start the engine with make api, then try again.")
                default: notice = Notice(title: "The engine stopped answering", body: detail.isEmpty ? "Check that the engine is running on your computer." : detail)
                }
            }
        case .tick(let t): apply(t)
        case .ended(let reason):
            // The computer ended the session (panic, closed, longest time reached, engine gone, bridge stopped):
            // stop the microphone, leave the listening state and say why. The last verdict stays until Clear screen.
            guard mode == .listening else { break }
            stopCapture()
            mode = .ended
            showAlert = false
            notice = Notice(title: "Listening stopped on your computer", body: Self.endedText(reason))
        default: break
        }
    }

    func apply(_ t: TickPayload) {
        guard mode == .listening || mode == .ended else { return }
        let v = VerdictView.make(t)
        verdict = v
        if v.alert != lastAlert {
            if v.alert == "amber" { Haptics.amber() }
            if v.alert == "red" { Haptics.red() }
            lastAlert = v.alert
        }
        if v.alert != "red" { redDismissed = false }
        showAlert = v.alert == "red" && !redDismissed && mode == .listening
    }

    // MARK: user actions

    func observeCalls() {
        calls.onChange = { [weak self] active in Task { @MainActor in self?.callChanged(active: active) } }
        calls.start()
        callActive = calls.hasActiveCall
    }

    /// A call began or ended on this iPhone. During a call iOS keeps the microphone from apps; when it ends we try to resume.
    func callChanged(active: Bool) {
        callActive = active
        if !active && mode == .listening && interrupted { capture.resume() }
    }

    func startTapped() {
        guard mode == .idle || mode == .ended else { return }
        if callActive { return }
        if !consentAccepted { pendingStartAfterConsent = true; sheet = .consent; return }
        if mic == .denied { notice = nil; return }
        #if DEBUG
        if DebugWavFeeder.path != nil { begin(); return }
        #endif
        if MicCapture.access == .unknown {
            MicCapture.request { [weak self] ok in
                guard let self else { return }
                self.mic = ok ? .granted : .denied
                if ok { self.begin() }
            }
        } else if MicCapture.access == .granted { begin() }
        else { mic = .denied }
    }

    func consentGiven() {
        consentAccepted = true
        sheet = nil
        if pendingStartAfterConsent { pendingStartAfterConsent = false; startTapped() }
    }

    func consentDeclined() { pendingStartAfterConsent = false; sheet = nil }

    private func begin() {
        resetSession()
        server.send(.started)
        do {
            #if DEBUG
            if let p = DebugWavFeeder.path { try feeder.start(path: p) } else { try capture.start() }
            #else
            try capture.start()
            #endif
        } catch {
            notice = callActive ? nil : Notice(title: "Could not start the microphone", body: "Another app may be using it. Close it and try again.")
            server.send(.stopped)
            return
        }
        mode = .listening
        startedAt = Date()
        UIApplication.shared.isIdleTimerDisabled = true
        clock = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let s = self.startedAt else { return }
                self.elapsed = Date().timeIntervalSince(s)
            }
        }
    }

    func stopTapped() {
        guard mode == .listening else { return }
        server.send(.stopped)
        stopCapture()
        mode = .ended
        showAlert = false
    }

    func clearScreen() {
        verdict = nil; notice = nil; showAlert = false; elapsed = 0; micFlat = false
        mode = bridgeConnected ? .idle : .offline
    }

    func dismissAlert() {
        redDismissed = true
        showAlert = false
        server.send(.dismiss)
    }

    func recheckMic() { mic = MicCapture.access }

    func openSettings() {
        if let u = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(u) }
    }

    // MARK: audio

    nonisolated private func frame(_ f: Data) {
        server.sendFrame(f)
        let p = PCM.peak(of: f)
        Task { @MainActor in self.meter(p) }
    }

    private func meter(_ peak: Int) {
        guard mode == .listening else { return }
        levels.removeFirst()
        levels.append(PCM.level(ofPeak: peak))
        if peak < PCM.silencePeak { silentFrames += 1 } else { silentFrames = 0; micFlat = false }
        if silentFrames >= 80 { micFlat = true }
    }

    private func stopCapture() {
        capture.stop()
        #if DEBUG
        feeder.stop()
        #endif
        clock?.invalidate(); clock = nil; startedAt = nil
        UIApplication.shared.isIdleTimerDisabled = false
        levels = [Double](repeating: 0, count: ListenController.meterCells)   // buffers wiped
        interrupted = false
    }

    private func resetSession() {
        verdict = nil; notice = nil; showAlert = false; elapsed = 0; silentFrames = 0
        micFlat = false; redDismissed = false; lastAlert = "none"; engine = nil
    }

    static func endedText(_ reason: String) -> String {
        switch reason {
        case "panic": return "Everything was wiped on your computer. Start again when you are ready."
        case "deleted", "kill": return "The session was closed on your computer."
        case "max_length": return "The longest allowed listening time was reached. Start again to keep listening."
        case "heartbeat_timeout": return "Your computer stopped hearing from the phone. Check the USB cable."
        case "bridge stopped": return "The bridge on your computer was stopped."
        default: return "The engine on your computer ended the session. Check that it is still running."
        }
    }

    // test/demo seam
    func _setMode(_ m: Mode) { mode = m }
}

enum Haptics {
    static func amber() { UINotificationFeedbackGenerator().notificationOccurred(.warning) }
    static func red() { UINotificationFeedbackGenerator().notificationOccurred(.error) }
}
