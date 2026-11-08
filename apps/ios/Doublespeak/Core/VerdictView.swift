import Foundation

/// Everything the screen shows for one tick, as plain values. Mirrors apps/android/lib/verdict.js so the phones agree.
/// Wording rules (design/skills.md): never "safe", "illegal", "fraud", "confirmed".
struct VerdictView: Equatable {
    var tier: String                 // warming_up | human | unsure | ai_disclosed | ai_undisclosed | scam
    var isWarming: Bool
    var orbWord: String
    var headline: String
    var advice: String
    var litTicks: Int                // of 48
    var scam: Int, aiVoice: Int, confidencePct: Int
    var howSure: HowSure             // honest "How sure"
    var howSureNote: String          // "The voice check is not sure." etc., "" when resolved
    var quadCell: String?            // human_ok | human_scam | ai_ok | ai_scam when both axes are clear
    var quadMaybe: [String]          // cells to outline when one axis is unclear
    var quadText: String
    var reasons: [String]
    var alert: String                // none | amber | red
    var transcript: String
    var markedRanges: [Range<Int>]   // character ranges (of `transcript`) where a tell quoted the caller

    enum HowSure: String, Equatable { case low = "Low", medium = "Medium", high = "High" }

    static let ringTicks = 48
    static let warmingSentence = "Still listening: not enough speech yet to judge."

    static let words: [String: (orb: String, head: String, advice: String)] = [
        "human": ("Human", "Sounds human", "No synthetic-voice tells found. If money or codes come up, hang up and call back on a number you already have."),
        "ai_undisclosed": ("AI", "Likely synthetic, didn't say so", "Legitimate AI callers are required to identify themselves. Treat this as untrusted: hang up and call back on a number you already have."),
        "ai_disclosed": ("AI", "AI, identified itself", "The caller said it's automated. Fine for appointment reminders; never share codes or payment with an automated caller."),
        "scam": ("Scam", "Scam pattern", "Hang up. Do not send money, cards, or codes. Call the person or organisation back on a number you already have."),
        "unsure": ("Not sure", "Not sure yet", "Not enough to judge yet. Tell keeps listening."),
        "warming_up": ("Listening", "Listening", "Gathering the first few seconds before judging."),
    ]

    static let quadLabels = [
        "human_ok": "Human voice, no scam pattern heard.",
        "human_scam": "Human voice, but scam pattern in what was said.",
        "ai_ok": "AI voice, no scam pattern heard.",
        "ai_scam": "AI voice and scam pattern in what was said.",
    ]

    static func make(_ t: TickPayload) -> VerdictView {
        let st = t.stable
        var v = t.verdict
        var scores = v.scores
        var quad = v.quadrant
        // The card follows the STABLE tier; if a raw tick disagrees, recompute so the 2x2 and scores never contradict the orb.
        if st.tier != "warming_up", st.tier != v.tier {
            v.tier = st.tier; scores = nil; quad = nil
            if st.tier == "scam" { v.pScam = max(v.pScam, 0.6) }
            if st.tier == "ai_disclosed" { v.disclosedAI = true }
        }
        let sc = scores ?? fallbackScores(v)
        let q = quad ?? fallbackQuadrant(v)
        let warming = st.tier == "warming_up" && st.alert != "red"
        let key = words[st.tier] != nil ? st.tier : "unsure"
        let w = words[key]!
        let how = honestHowSure(label: sc.confidenceLabel, confidence: sc.confidence, unresolved: sc.voiceUnresolved)
        var note = sc.confidenceNote
        if sc.voiceUnresolved && note.isEmpty { note = "The voice check is not sure." }
        if !sc.voiceUnresolved { note = "" }

        var cell: String? = nil
        var maybe: [String] = []
        if q.voice != "unclear" && q.intent != "unclear" { cell = q.combo }
        else {
            if q.voice != "unclear" { maybe = ["\(q.voice)_ok", "\(q.voice)_scam"] }
            else if q.intent != "unclear" { let s = q.intent == "scam" ? "scam" : "ok"; maybe = ["human_\(s)", "ai_\(s)"] }
        }
        let lit = warming ? 0 : Int((Double(max(sc.scam, sc.aiVoice)) / 100 * Double(ringTicks)).rounded())
        let reasons = warming ? [warmingSentence] : Array(st.reasons.filter { !$0.isEmpty }.prefix(4))
        return VerdictView(
            tier: st.tier, isWarming: warming, orbWord: w.orb, headline: w.head, advice: w.advice,
            litTicks: max(0, min(ringTicks, lit)), scam: sc.scam, aiVoice: sc.aiVoice, confidencePct: sc.confidence,
            howSure: how, howSureNote: note, quadCell: warming ? nil : cell, quadMaybe: warming ? [] : maybe,
            quadText: warming ? warmingSentence : (q.comboLabel.isEmpty ? (quadLabels[q.combo] ?? "") : q.comboLabel),
            reasons: reasons, alert: st.alert, transcript: v.transcript, markedRanges: marks(v.transcript, v.tells))
    }

    /// The honest rule: while the voice question is unresolved the label can never read "High",
    /// whatever the raw confidence says. The server already caps it; this is the belt to its braces.
    static func honestHowSure(label: String?, confidence: Int, unresolved: Bool) -> HowSure {
        var h: HowSure
        switch (label ?? "").lowercased() {
        case "high": h = .high
        case "medium": h = .medium
        case "low": h = .low
        default: h = confidence >= 80 ? .high : confidence >= 50 ? .medium : .low
        }
        if unresolved && h == .high { h = .medium }
        return h
    }

    static func fallbackScores(_ v: Verdict) -> ScoresBlock {
        func pc(_ x: Double) -> Int { Int((max(0, min(1, x)) * 100).rounded()) }
        let label = v.confidence >= 0.8 ? "high" : v.confidence >= 0.5 ? "medium" : "low"
        return ScoresBlock(scam: pc(v.pScam), aiVoice: pc(v.pAi), confidence: pc(v.confidence), confidenceLabel: label)
    }

    static func fallbackQuadrant(_ v: Verdict, aiThreshold: Double = 0.6) -> QuadrantBlock {
        let noAudio = !v.tells.isEmpty && !v.tells.contains { $0.family == "acoustic" && $0.applicable && $0.weight > 0 }
        let voice = (v.disclosedAI || v.pAi >= aiThreshold) ? "ai" : noAudio ? "unclear" : v.pAi <= 0.4 ? "human" : "unclear"
        let intent = v.pScam >= 0.55 ? "scam" : v.pScam < 0.3 ? "not_scam" : "unclear"
        var combo = "unclear"
        if voice != "unclear" && intent != "unclear" { combo = voice + (intent == "scam" ? "_scam" : "_ok") }
        let label: String
        if combo != "unclear" { label = quadLabels[combo] ?? "" }
        else if voice == "unclear" && intent == "scam" { label = "Scam pattern. Voice unclear." }
        else if voice == "unclear" && intent == "not_scam" { label = "Voice unclear. No scam pattern heard." }
        else if voice == "unclear" { label = "Voice and scam pattern both unclear." }
        else { label = (voice == "ai" ? "Voice may be AI" : "Voice sounds human") + ". Scam pattern unclear." }
        return QuadrantBlock(voice: voice, intent: intent, combo: combo, comboLabel: label)
    }

    // MARK: transcript marks (quoted phrases of non-acoustic tells that scored >= 0.4)

    static func quotedPhrases(_ evidence: String) -> [String] {
        var out: [String] = []
        let opens: Set<Character> = ["\u{201C}", "\""], closes: Set<Character> = ["\u{201D}", "\""]
        var cur: String? = nil
        for ch in evidence {
            if cur == nil { if opens.contains(ch) { cur = "" } }
            else if closes.contains(ch) {
                let p = cur!.trimmingCharacters(in: CharacterSet(charactersIn: " ,.;:!?\t"))
                if p.count >= 2 && p.count <= 80 { out.append(p) }
                cur = nil
            } else { cur!.append(ch) }
        }
        return out
    }

    static func marks(_ transcript: String, _ tells: [Tell]) -> [Range<Int>] {
        func norm(_ s: String) -> [Character] { Array(s.replacingOccurrences(of: "\u{2019}", with: "'").lowercased()) }
        let hay = norm(transcript)
        guard !hay.isEmpty else { return [] }
        var found: [Range<Int>] = []
        for t in tells where t.applicable && t.score >= 0.4 && t.family != "acoustic" {
            for ph in quotedPhrases(t.evidence) {
                let n = norm(ph)
                guard !n.isEmpty, n.count <= hay.count else { continue }
                var i = 0
                while i + n.count <= hay.count {
                    if Array(hay[i..<(i + n.count)]) == n { found.append(i..<(i + n.count)); i += n.count } else { i += 1 }
                }
            }
        }
        found.sort { $0.lowerBound != $1.lowerBound ? $0.lowerBound < $1.lowerBound : $0.upperBound > $1.upperBound }
        var kept: [Range<Int>] = [], end = 0
        for r in found where r.lowerBound >= end { kept.append(r); end = r.upperBound }
        return kept
    }
}

func clockString(_ seconds: Double) -> String {
    let s = Int(max(0, seconds))
    return String(format: "%d:%02d", s / 60, s % 60)
}
