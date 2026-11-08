import AVFoundation
import Foundation

enum MicAccess: Equatable { case unknown, granted, denied }

/// The bits of AVAudioSession + AVAudioEngine that capture uses, behind a seam so the start/rollback logic can be
/// unit tested with a fake (a simulator has no reliable way to make AVAudioEngine.start() throw on demand).
protocol CaptureBackend: AnyObject {
    func activateSession() throws                     // category .playAndRecord, mode .measurement, then active
    func deactivateSession()
    func inputFormat() -> (sampleRate: Double, channels: Int)
    func installTap(_ block: @escaping ([Float]) -> Void)
    func removeTap()
    func startEngine() throws
    func stopEngine()
    var engineRunning: Bool { get }
}

final class AVCaptureBackend: CaptureBackend {
    private let engine = AVAudioEngine()

    func activateSession() throws {
        let s = AVAudioSession.sharedInstance()
        try s.setCategory(.playAndRecord, mode: .measurement, options: [.mixWithOthers])
        try s.setActive(true)
    }

    func deactivateSession() { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }

    func inputFormat() -> (sampleRate: Double, channels: Int) {
        let f = engine.inputNode.outputFormat(forBus: 0)
        return (f.sampleRate, Int(f.channelCount))
    }

    func installTap(_ block: @escaping ([Float]) -> Void) {
        let input = engine.inputNode
        let fmt = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 2048, format: fmt) { buf, _ in
            guard let ch = buf.floatChannelData else { return }
            let n = Int(buf.frameLength), chans = Int(buf.format.channelCount)
            var mono = [Float](repeating: 0, count: n)
            if chans == 1 { mono = Array(UnsafeBufferPointer(start: ch[0], count: n)) }
            else {
                for c in 0..<chans { let p = ch[c]; for i in 0..<n { mono[i] += p[i] } }
                let k = 1 / Float(chans); for i in 0..<n { mono[i] *= k }
            }
            block(mono)
        }
    }

    func removeTap() { engine.inputNode.removeTap(onBus: 0) }
    func startEngine() throws { engine.prepare(); try engine.start() }
    func stopEngine() { engine.stop() }
    var engineRunning: Bool { engine.isRunning }
}

/// Raw microphone capture: .measurement mode switches off the system's voice processing (echo cancel, noise
/// suppression, AGC), which would rewrite the pauses and room noise the engine's detectors measure.
/// Frames go straight to `onFrame` (100 ms PCM16 16 kHz mono) and are not kept anywhere.
/// A failed start rolls back everything it did (tap, framer, session), so a retry starts clean and never double-installs.
final class MicCapture {
    var onFrame: ((Data) -> Void)?
    var onInterruption: ((Bool) -> Void)?         // true = began, false = ended

    private let backend: CaptureBackend
    private var framer: PCMFramer?
    private var observers: [NSObjectProtocol] = []
    private let lock = NSLock()
    private(set) var running = false
    private(set) var tapInstalled = false
    private(set) var sessionActive = false

    init(backend: CaptureBackend = AVCaptureBackend()) { self.backend = backend }

    static var access: MicAccess {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: return .granted
        case .denied: return .denied
        default: return .unknown
        }
    }

    static func request(_ done: @escaping (Bool) -> Void) {
        AVAudioApplication.requestRecordPermission { ok in DispatchQueue.main.async { done(ok) } }
    }

    func start() throws {
        guard !running else { return }
        do {
            try backend.activateSession()
            sessionActive = true
            let fmt = backend.inputFormat()
            guard fmt.sampleRate > 0, fmt.channels > 0 else {
                throw NSError(domain: "Doublespeak", code: 1, userInfo: [NSLocalizedDescriptionKey: "No microphone input"])
            }
            lock.lock(); framer = PCMFramer(inputRate: fmt.sampleRate); lock.unlock()
            if !tapInstalled {
                backend.installTap { [weak self] mono in
                    guard let self else { return }
                    self.lock.lock()
                    let frames = self.framer?.push(mono) ?? []
                    self.lock.unlock()
                    for f in frames { self.onFrame?(f) }
                }
                tapInstalled = true
            }
            try backend.startEngine()
        } catch {
            teardown()
            throw error
        }
        running = true
        let nc = NotificationCenter.default
        observers.append(nc.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            let t = (n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt).flatMap(AVAudioSession.InterruptionType.init(rawValue:))
            if t == .began { self?.onInterruption?(true) }
            else if t == .ended { self?.resume() }
        })
    }

    /// Safe resume attempt (the call ended). Stays interrupted if iOS still refuses.
    func resume() {
        guard running else { return }
        do {
            try backend.activateSession()
            sessionActive = true
            if !backend.engineRunning { try backend.startEngine() }
            onInterruption?(false)
        } catch { /* still interrupted; the interruption-ended notification or the call ending will try again */ }
    }

    /// Stop wipes the partial frame and releases the microphone. Safe to call in any state.
    func stop() {
        running = false
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
        teardown()
    }

    private func teardown() {
        if backend.engineRunning { backend.stopEngine() }
        if tapInstalled { backend.removeTap(); tapInstalled = false }
        lock.lock(); framer?.reset(); framer = nil; lock.unlock()
        if sessionActive { backend.deactivateSession(); sessionActive = false }
    }
}
