import Foundation

/// Raw microphone samples -> the engine's wire format: PCM16 little-endian, 16 kHz, mono, 100 ms frames (3200 bytes).
/// Pure value logic so it can be unit tested without an audio device. Nothing here keeps audio longer than one frame.
enum PCM {
    static let sampleRate = 16_000
    static let frameSamples = 1_600          // 100 ms
    static let frameBytes = frameSamples * 2
    /// A frame whose peak is below this is treated as silence (same threshold as tools/macos/listen.py).
    static let silencePeak = 40

    static func int16(from f: Float) -> Int16 {
        let c = max(-1, min(1, f))
        return Int16((c * 32767).rounded())
    }

    /// Peak absolute sample of a PCM16-LE frame, 0...32768.
    static func peak(of frame: Data) -> Int {
        var p = 0
        frame.withUnsafeBytes { raw in
            let s = raw.bindMemory(to: Int16.self)
            for v in s { p = max(p, abs(Int(Int16(littleEndian: v)))) }
        }
        return p
    }

    /// 0...1 level for the meter. Perceptual (log) so quiet speech still moves the bars.
    static func level(ofPeak p: Int) -> Double {
        guard p > 0 else { return 0 }
        let db = 20 * log10(Double(p) / 32768.0)          // -90 ... 0
        return max(0, min(1, (db + 60) / 60))
    }
}

/// Streaming box-filter resampler + framer. Feed it float mono at any input rate; it returns whole 100 ms frames.
struct PCMFramer {
    let inputRate: Double
    private let ratio: Double
    private var pending: [Float] = []
    private var pos: Double = 0
    private var out: [Int16] = []

    init(inputRate: Double) {
        precondition(inputRate > 0)
        self.inputRate = inputRate
        self.ratio = inputRate / Double(PCM.sampleRate)
    }

    mutating func push(_ samples: [Float]) -> [Data] {
        pending.append(contentsOf: samples)
        while pos + ratio <= Double(pending.count) {
            let i0 = Int(pos)
            var i1 = Int(pos + ratio)
            if i1 <= i0 { i1 = i0 + 1 }
            var acc: Float = 0
            for i in i0..<i1 { acc += pending[i] }
            out.append(PCM.int16(from: acc / Float(i1 - i0)))
            pos += ratio
        }
        let drop = min(Int(pos), pending.count)
        if drop > 0 { pending.removeFirst(drop); pos -= Double(drop) }
        var frames: [Data] = []
        while out.count >= PCM.frameSamples {
            let chunk = Array(out.prefix(PCM.frameSamples))
            out.removeFirst(PCM.frameSamples)
            var d = Data(capacity: PCM.frameBytes)
            for s in chunk { var v = s.littleEndian; withUnsafeBytes(of: &v) { d.append(contentsOf: $0) } }
            frames.append(d)
        }
        return frames
    }

    /// Stop wipes everything still buffered (a partial frame is dropped, never sent later).
    mutating func reset() { pending.removeAll(); out.removeAll(); pos = 0 }
}
