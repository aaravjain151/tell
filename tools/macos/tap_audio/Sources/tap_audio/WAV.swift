import Foundation

/// Minimal 16 kHz mono 16-bit PCM WAV writer.
func wavData(pcm: Data, sampleRate: Int = 16000) -> Data {
    var d = Data()
    func u32(_ v: UInt32) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 4)) }
    func u16(_ v: UInt16) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 2)) }
    d.append(contentsOf: Array("RIFF".utf8)); u32(UInt32(36 + pcm.count))
    d.append(contentsOf: Array("WAVE".utf8)); d.append(contentsOf: Array("fmt ".utf8))
    u32(16); u16(1); u16(1); u32(UInt32(sampleRate)); u32(UInt32(sampleRate * 2)); u16(2); u16(16)
    d.append(contentsOf: Array("data".utf8)); u32(UInt32(pcm.count))
    d.append(pcm)
    return d
}

struct Stats {
    var peak: Float = 0
    var sumSq: Double = 0
    var n: Int = 0
    mutating func add(_ s: Int16) {
        let f = abs(Float(s) / 32768)
        if f > peak { peak = f }
        sumSq += Double(f) * Double(f)
        n += 1
    }
    var rms: Float { n == 0 ? 0 : Float((sumSq / Double(n)).squareRoot()) }
}
