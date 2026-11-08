import XCTest
@testable import Doublespeak

final class PCMTests: XCTestCase {
    func testFramesAre100msOf16kMonoPCM16() {
        var f = PCMFramer(inputRate: 48_000)
        let frames = f.push([Float](repeating: 0.5, count: 48_000))     // 1 s
        XCTAssertEqual(frames.count, 10)
        XCTAssertTrue(frames.allSatisfy { $0.count == 3200 })
    }

    func testResampleKeepsLevelAndIsLittleEndian() {
        var f = PCMFramer(inputRate: 48_000)
        let frames = f.push([Float](repeating: 0.5, count: 4_800))
        XCTAssertEqual(frames.count, 1)
        let b = [UInt8](frames[0])
        XCTAssertEqual(Int(b[0]) | (Int(b[1]) << 8), 16384, accuracy: 2)   // 0.5 * 32767
        XCTAssertEqual(PCM.peak(of: frames[0]), 16384, accuracy: 2)
    }

    func testOddRateStillProducesRightFrameCount() {
        var f = PCMFramer(inputRate: 44_100)
        var n = 0
        for _ in 0..<10 { n += f.push([Float](repeating: 0.1, count: 4_410)).count }    // 1 s in 100 ms chunks
        XCTAssertTrue((9...10).contains(n), "got \(n)")
    }

    func testPartialFrameIsHeldThenWipedOnReset() {
        var f = PCMFramer(inputRate: 16_000)
        XCTAssertTrue(f.push([Float](repeating: 0.2, count: 800)).isEmpty)
        f.reset()
        XCTAssertTrue(f.push([Float](repeating: 0.2, count: 800)).isEmpty, "a wiped half frame must not be completed later")
    }

    func testClipsAndSilence() {
        XCTAssertEqual(PCM.int16(from: 2), Int16.max)
        XCTAssertEqual(PCM.int16(from: -2), -Int16.max)
        var f = PCMFramer(inputRate: 16_000)
        let quiet = f.push([Float](repeating: 0.0005, count: 1_600))
        XCTAssertLessThan(PCM.peak(of: quiet[0]), PCM.silencePeak)
        XCTAssertEqual(PCM.level(ofPeak: 0), 0)
        XCTAssertGreaterThan(PCM.level(ofPeak: 8_000), PCM.level(ofPeak: 200))
    }
}

final class PairingTokenTests: XCTestCase {
    func testGeneratedTokensAreRandomAndUnambiguous() {
        let a = PairingToken.generate(), b = PairingToken.generate()
        XCTAssertEqual(a.count, 8)
        XCTAssertNotEqual(a, b)
        XCTAssertTrue(a.allSatisfy { PairingToken.alphabet.contains($0) })
        XCTAssertFalse(a.contains("0") || a.contains("O") || a.contains("1") || a.contains("I"))
    }

    func testDisplayAndMatching() {
        XCTAssertEqual(PairingToken.display("k7qm4txd"), "K7QM-4TXD")
        XCTAssertTrue(PairingToken.matches("k7qm-4txd", expected: "K7QM4TXD"))
        XCTAssertTrue(PairingToken.matches("K7QM 4TXD", expected: "K7QM4TXD"))
        XCTAssertFalse(PairingToken.matches("K7QM-4TXE", expected: "K7QM4TXD"))
        XCTAssertFalse(PairingToken.matches("", expected: "K7QM4TXD"))
        XCTAssertFalse(PairingToken.matches("K7QM4TXD9", expected: "K7QM4TXD"))
        XCTAssertFalse(PairingToken.matches("anything", expected: ""))
    }
}

final class ProtocolTests: XCTestCase {
    func testOutboundMessages() {
        XCTAssertEqual(Protocol.Outbound.started.json, "{\"type\":\"started\"}")
        XCTAssertEqual(Protocol.Outbound.dismiss.json, "{\"type\":\"dismiss\"}")
        XCTAssertEqual(Protocol.Outbound.stopped.json, "{\"type\":\"stopped\"}")
        XCTAssertTrue(Protocol.Outbound.ready.json.contains("\"ready\""))
    }

    func testInboundAuthEngineEnded() {
        XCTAssertEqual(Protocol.parse("{\"type\":\"auth\",\"token\":\"K7QM-4TXD\"}"), .auth(token: "K7QM-4TXD"))
        XCTAssertEqual(Protocol.parse("{\"type\":\"engine\",\"status\":\"busy\",\"detail\":\"x\"}"), .engine(.busy, detail: "x"))
        XCTAssertEqual(Protocol.parse("{\"type\":\"ended\",\"reason\":\"stop\"}"), .ended(reason: "stop"))
    }

    func testGarbageNeverCrashes() {
        for s in ["", "nope", "[1,2]", "{}", "{\"type\":5}", "{\"type\":\"wat\"}", String(repeating: "x", count: 300_000)] {
            XCTAssertEqual(Protocol.parse(s), .unknown)
        }
    }

    func testTickDecodesHonestFieldsAndQuadrant() {
        let t = Protocol.parse(Fixtures.unsureHighRaw)
        guard case .tick(let p) = t else { return XCTFail("not a tick") }
        XCTAssertEqual(p.tick, 7)
        XCTAssertEqual(p.verdict.scores?.confidenceLabel, "medium")
        XCTAssertEqual(p.verdict.scores?.voiceUnresolved, true)
        XCTAssertEqual(p.verdict.scores?.confidenceNote, "The voice checks disagree.")
        XCTAssertEqual(p.verdict.quadrant?.combo, "unclear")
        XCTAssertEqual(p.stable.alert, "none")
    }

    func testOlderEngineWithoutNewFieldsStillDecodes() {
        let json = "{\"type\":\"tick\",\"tick\":1,\"verdict\":{\"tier\":\"human\",\"p_ai\":0.1,\"p_scam\":0.0,\"confidence\":0.9},\"stable\":{\"tier\":\"human\"}}"
        guard case .tick(let p) = Protocol.parse(json) else { return XCTFail() }
        XCTAssertNil(p.verdict.scores)
        let v = VerdictView.make(p)
        XCTAssertEqual(v.howSure, .high)               // no unresolved flag from an old engine, raw 0.9
        XCTAssertEqual(v.quadCell, "human_ok")
    }
}

final class VerdictViewTests: XCTestCase {
    private func view(_ json: String) -> VerdictView {
        guard case .tick(let p) = Protocol.parse(json) else { fatalError("bad fixture") }
        return VerdictView.make(p)
    }

    func testWarmingShowsListeningAndNoRing() {
        let v = view(Fixtures.warming)
        XCTAssertTrue(v.isWarming)
        XCTAssertEqual(v.orbWord, "Listening")
        XCTAssertEqual(v.litTicks, 0)
        XCTAssertEqual(v.reasons, [VerdictView.warmingSentence])
        XCTAssertNil(v.quadCell)
    }

    func testHonestHowSureNeverHighWhileVoiceUnresolved() {
        XCTAssertEqual(VerdictView.honestHowSure(label: "high", confidence: 100, unresolved: true), .medium)
        XCTAssertEqual(VerdictView.honestHowSure(label: nil, confidence: 100, unresolved: true), .medium)
        XCTAssertEqual(VerdictView.honestHowSure(label: "low", confidence: 100, unresolved: true), .low)
        XCTAssertEqual(VerdictView.honestHowSure(label: "high", confidence: 90, unresolved: false), .high)
        XCTAssertEqual(VerdictView.honestHowSure(label: nil, confidence: 55, unresolved: false), .medium)
    }

    func testUnresolvedVoiceShowsNoteAndNotHigh() {
        let v = view(Fixtures.unsureHighRaw)
        XCTAssertNotEqual(v.howSure, .high)
        XCTAssertEqual(v.howSureNote, "The voice checks disagree.")
        XCTAssertEqual(v.quadCell, nil)
        XCTAssertEqual(v.quadMaybe, ["human_ok", "ai_ok"])
    }

    func testRedScamMapsToQuadrantRingAndWording() {
        let v = view(Fixtures.red)
        XCTAssertEqual(v.alert, "red")
        XCTAssertEqual(v.headline, "Scam pattern")
        XCTAssertEqual(v.quadCell, "ai_scam")
        XCTAssertEqual(v.litTicks, Int((0.93 * 48).rounded()))
        XCTAssertEqual(v.reasons.count, 2)
        for t in [v.headline, v.advice, v.quadText] {
            for bad in ["safe", "illegal", "fraud", "confirmed"] { XCTAssertFalse(t.lowercased().contains(bad)) }
        }
    }

    func testStableTierWinsOverRawTierSoTheCardNeverContradictsItself() {
        var s = Fixtures.red
        s = s.replacingOccurrences(of: "\"tier\":\"scam\",\"p_ai\"", with: "\"tier\":\"human\",\"p_ai\"")   // raw says human
        let v = view(s)                                                                                      // stable still says scam
        XCTAssertEqual(v.tier, "scam")
        XCTAssertEqual(v.headline, "Scam pattern")
    }

    func testTranscriptMarksFollowQuotedEvidence() {
        let v = view(Fixtures.red)
        XCTAssertEqual(v.markedRanges.count, 1)
        let r = v.markedRanges[0]
        let chars = Array(v.transcript)
        XCTAssertEqual(String(chars[r]).lowercased(), "the code you just received")
    }
}

enum Fixtures {
    static func tick(tier: String, alert: String, state: String, verdictTier: String? = nil, extra: String, transcript: String = "", tells: String = "[]", reasons: String = "[]") -> String {
        """
        {"type":"tick","tick":7,"elapsed_s":30,"verdict":{"tier":"\(verdictTier ?? tier)","p_ai":0.4,"p_scam":0.2,"confidence":0.9,"disclosed_ai":false,
         "transcript":"\(transcript)","tells":\(tells),\(extra)},
         "stable":{"tier":"\(tier)","state":"\(state)","alert":"\(alert)","since_s":3,"reasons":\(reasons)}}
        """
    }
    static let warming = tick(tier: "warming_up", alert: "none", state: "warming", extra: "\"scores\":{\"scam\":0,\"ai_voice\":0,\"confidence\":0,\"confidence_label\":\"low\"}")
    static let unsureHighRaw = tick(tier: "unsure", alert: "none", state: "steady",
        extra: "\"scores\":{\"scam\":20,\"ai_voice\":40,\"confidence\":90,\"confidence_label\":\"medium\",\"voice_unresolved\":true,\"confidence_note\":\"The voice checks disagree.\"},\"quadrant\":{\"voice\":\"unclear\",\"intent\":\"not_scam\",\"combo\":\"unclear\",\"combo_label\":\"Voice unclear. No scam pattern heard.\"}")
    static let red = tick(tier: "scam", alert: "red", state: "latched",
        extra: "\"scores\":{\"scam\":93,\"ai_voice\":82,\"confidence\":60,\"confidence_label\":\"medium\",\"voice_unresolved\":false},\"quadrant\":{\"voice\":\"ai\",\"intent\":\"scam\",\"combo\":\"ai_scam\",\"combo_label\":\"AI voice and scam pattern in what was said.\"}",
        transcript: "Read me the code you just received now.",
        tells: "[{\"name\":\"credential_ask\",\"family\":\"intent\",\"score\":0.9,\"weight\":1,\"applicable\":true,\"evidence\":\"asked for \u{201C}the code you just received\u{201D}\"}]",
        reasons: "[\"Several scam warning signs showed up together, including a request for money or a code.\",\"The voice has sounded automated for a while.\"]")
}
