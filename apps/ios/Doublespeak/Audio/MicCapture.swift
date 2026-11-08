import AVFoundation
import Foundation

enum MicAccess: Equatable { case unknown, granted, denied }

/// Raw microphone capture: .measurement mode switches off the system's voice processing (echo cancel, noise
/// suppression, AGC), which would rewrite the pauses and room noise the engine's detectors measure.
/// Frames go straight to `onFrame` (100 ms PCM16 16 kHz mono) and are not kept anywhere.
final class MicCapture {
    var onFrame: ((Data) -> Void)?
    var onInterruption: ((Bool) -> Void)?         // true = began, false = ended

    private let engine = AVAudioEngine()
    private var framer: PCMFramer?
    private var observers: [NSObjectProtocol] = []
    private(set) var running = false

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
        let s = AVAudioSession.sharedInstance()
        try s.setCategory(.playAndRecord, mode: .measurement, options: [.mixWithOthers])
        try s.setActive(true)
        let input = engine.inputNode
        let fmt = input.outputFormat(forBus: 0)
        guard fmt.sampleRate > 0, fmt.channelCount > 0 else {
            throw NSError(domain: "Doublespeak", code: 1, userInfo: [NSLocalizedDescriptionKey: "No microphone input"])
        }
        framer = PCMFramer(inputRate: fmt.sampleRate)
        input.installTap(onBus: 0, bufferSize: 2048, format: fmt) { [weak self] buf, _ in
            guard let self, let ch = buf.floatChannelData else { return }
            let n = Int(buf.frameLength), chans = Int(buf.format.channelCount)
            var mono = [Float](repeating: 0, count: n)
            if chans == 1 { mono = Array(UnsafeBufferPointer(start: ch[0], count: n)) }
            else {
                for c in 0..<chans { let p = ch[c]; for i in 0..<n { mono[i] += p[i] } }
                let k = 1 / Float(chans); for i in 0..<n { mono[i] *= k }
            }
            self.lock.lock()
            let frames = self.framer?.push(mono) ?? []
            self.lock.unlock()
            for f in frames { self.onFrame?(f) }
        }
        engine.prepare()
        try engine.start()
        running = true
        let nc = NotificationCenter.default
        observers.append(nc.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] n in
            let t = (n.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt).flatMap(AVAudioSession.InterruptionType.init(rawValue:))
            if t == .began { self?.onInterruption?(true) }
            else if t == .ended { self?.resumeAfterInterruption() }
        })
    }

    private let lock = NSLock()

    private func resumeAfterInterruption() {
        guard running else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        if !engine.isRunning { try? engine.start() }
        onInterruption?(false)
    }

    /// Stop wipes the partial frame and releases the microphone.
    func stop() {
        guard running else { return }
        running = false
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        lock.lock(); framer?.reset(); framer = nil; lock.unlock()
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
