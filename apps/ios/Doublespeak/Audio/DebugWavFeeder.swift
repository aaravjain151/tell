#if DEBUG
import AVFoundation
import Foundation

/// DEBUG BUILDS ONLY (compiled out of release): `-DSInjectWAV /path/to/file.wav` feeds a file to the app instead of the
/// microphone, at real-time speed, through the same PCMFramer. Used to drive the simulator with a known call.
final class DebugWavFeeder {
    var onFrame: ((Data) -> Void)?
    private var timer: DispatchSourceTimer?
    private var frames: [Data] = []
    private var idx = 0
    private(set) var running = false

    static var path: String? {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: "-DSInjectWAV"), i + 1 < a.count else { return nil }
        return a[i + 1]
    }

    func start(path: String) throws {
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let fmt = file.processingFormat
        guard let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: AVAudioFrameCount(file.length)) else { return }
        try file.read(into: buf)
        guard let ch = buf.floatChannelData else { return }
        var mono = Array(UnsafeBufferPointer(start: ch[0], count: Int(buf.frameLength)))
        if fmt.channelCount > 1 {
            for c in 1..<Int(fmt.channelCount) { let p = ch[c]; for i in 0..<mono.count { mono[i] += p[i] } }
            let k = 1 / Float(fmt.channelCount); for i in 0..<mono.count { mono[i] *= k }
        }
        var framer = PCMFramer(inputRate: fmt.sampleRate)
        frames = framer.push(mono)
        idx = 0
        running = true
        let t = DispatchSource.makeTimerSource(queue: .global(qos: .userInitiated))
        t.schedule(deadline: .now(), repeating: .milliseconds(100), leeway: .milliseconds(5))
        t.setEventHandler { [weak self] in
            guard let self, self.running else { return }
            if self.idx < self.frames.count { self.onFrame?(self.frames[self.idx]); self.idx += 1 }
            else { self.stop() }
        }
        timer = t
        t.resume()
    }

    func stop() { running = false; timer?.cancel(); timer = nil; frames = [] }
}
#endif
