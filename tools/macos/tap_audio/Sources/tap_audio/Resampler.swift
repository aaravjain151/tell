import AVFoundation

/// Converts whatever the tap delivers to 16 kHz mono Int16 (mixing down stereo).
final class Resampler {
    private let converter: AVAudioConverter
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!
    let inFormat: AVAudioFormat

    init?(from format: AVAudioFormat) {
        guard let c = AVAudioConverter(from: format, to: outFormat) else { return nil }
        inFormat = format
        converter = c
    }

    func convert(_ input: AVAudioPCMBuffer) -> [Int16] {
        let ratio = 16000.0 / inFormat.sampleRate
        let cap = AVAudioFrameCount(Double(input.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: cap) else { return [] }
        var supplied = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if supplied { status.pointee = .noDataNow; return nil }
            supplied = true
            status.pointee = .haveData
            return input
        }
        guard err == nil, let p = out.int16ChannelData else { return [] }
        return Array(UnsafeBufferPointer(start: p[0], count: Int(out.frameLength)))
    }
}
