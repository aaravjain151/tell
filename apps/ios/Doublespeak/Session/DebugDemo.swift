#if DEBUG
import Foundation

/// DEBUG BUILDS ONLY. `-DSDemo warming|human|unsure|amber|red|ended|offline` shows a canned state without a bridge,
/// for screenshots and layout checks. The canned JSON is the same shape the bridge relays from the engine.
enum DebugDemo {
    static var requested: String? {
        let a = ProcessInfo.processInfo.arguments
        guard let i = a.firstIndex(of: "-DSDemo"), i + 1 < a.count else { return nil }
        return a[i + 1]
    }

    static func json(tier: String, state: String, alert: String, pAi: Double, pScam: Double, conf: Double,
                     label: String, unresolved: Bool, note: String, reasons: [String], transcript: String,
                     quadVoice: String, quadIntent: String, quadCombo: String, quadLabel: String, evidence: String) -> String {
        let rs = reasons.map { "\"\($0)\"" }.joined(separator: ",")
        return """
        {"type":"tick","tick":9,"elapsed_s":42.0,
         "verdict":{"tier":"\(tier)","p_ai":\(pAi),"p_scam":\(pScam),"confidence":\(conf),"disclosed_ai":false,
          "transcript":"\(transcript)",
          "tells":[{"name":"credential_ask","family":"intent","score":0.9,"weight":1,"applicable":true,"evidence":"\(evidence)"}],
          "scores":{"scam":\(Int(pScam * 100)),"ai_voice":\(Int(pAi * 100)),"confidence":\(Int(conf * 100)),"confidence_label":"\(label)",
                    "level":"low","level_reason":"","voice_unresolved":\(unresolved),"confidence_note":"\(note)"},
          "quadrant":{"voice":"\(quadVoice)","intent":"\(quadIntent)","combo":"\(quadCombo)","combo_label":"\(quadLabel)"}},
         "stable":{"tier":"\(tier)","state":"\(state)","alert":"\(alert)","since_s":12,"reasons":[\(rs)]}}
        """
    }

    @MainActor static func apply(to c: ListenController) {
        guard let d = requested else { return }
        c.consentAccepted = true
        c.sheet = nil
        if d == "offline" { return }
        c._setMode(.idle)
        if d == "idle" { return }
        c._setMode(.listening)
        c.elapsed = 42
        c.levels = (0..<ListenController.meterCells).map { i in 0.25 + 0.5 * abs(sin(Double(i) * 0.7)) }
        let t: String
        switch d {
        case "warming":
            t = json(tier: "warming_up", state: "warming", alert: "none", pAi: 0, pScam: 0, conf: 0, label: "low", unresolved: false, note: "",
                     reasons: [], transcript: "", quadVoice: "unclear", quadIntent: "unclear", quadCombo: "unclear", quadLabel: "", evidence: "")
        case "human":
            t = json(tier: "human", state: "steady", alert: "none", pAi: 0.12, pScam: 0.05, conf: 0.62, label: "medium", unresolved: false, note: "",
                     reasons: [], transcript: "Hi, it is Sam from the dentist, calling to confirm your appointment on Tuesday.",
                     quadVoice: "human", quadIntent: "not_scam", quadCombo: "human_ok", quadLabel: "Human voice, no scam pattern heard.", evidence: "")
        case "unsure":
            t = json(tier: "unsure", state: "steady", alert: "none", pAi: 0.45, pScam: 0.2, conf: 0.95, label: "high", unresolved: true,
                     note: "The voice checks disagree.", reasons: [], transcript: "Hello, how can I help you today.",
                     quadVoice: "unclear", quadIntent: "not_scam", quadCombo: "unclear", quadLabel: "Voice unclear. No scam pattern heard.", evidence: "")
        case "amber":
            t = json(tier: "ai_undisclosed", state: "escalated", alert: "amber", pAi: 0.78, pScam: 0.5, conf: 0.6, label: "medium", unresolved: false, note: "",
                     reasons: ["Part of this call sounds like a scam. Do not share money, codes or passwords.", "The voice has sounded automated for a while."],
                     transcript: "This is your bank. We noticed unusual activity. Please stay on the line.",
                     quadVoice: "ai", quadIntent: "unclear", quadCombo: "unclear", quadLabel: "Voice may be AI. Scam pattern unclear.", evidence: "")
        default:
            t = json(tier: "scam", state: "latched", alert: "red", pAi: 0.82, pScam: 0.93, conf: 0.6, label: "medium", unresolved: false, note: "",
                     reasons: ["Several scam warning signs showed up together, including a request for money or a code.", "The voice has sounded automated for a while."],
                     transcript: "Read me the code you just received and do not tell anyone, this is urgent.",
                     quadVoice: "ai", quadIntent: "scam", quadCombo: "ai_scam", quadLabel: "AI voice and scam pattern in what was said.",
                     evidence: "asked for “the code you just received”")
        }
        if case .tick(let p) = Protocol.parse(t) {
            c.apply(p)
            if d == "ended" { c._setMode(.ended) }
        }
    }
}
#endif
