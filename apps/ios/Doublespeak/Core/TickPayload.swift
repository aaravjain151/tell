import Foundation

/// One engine tick as relayed by the bridge (the engine's GET /live/events "verdict" event, unchanged).
/// Every field is optional on the wire; the decoder never throws for a missing or odd value, so a newer engine
/// that adds fields (or an older one without `confidence_label`) cannot break the screen.
struct TickPayload: Decodable {
    var tick: Int = 0
    var elapsedS: Double = 0
    var verdict = Verdict()
    var stable = Stable()

    enum CodingKeys: String, CodingKey { case tick, elapsedS = "elapsed_s", verdict, stable }

    init() {}
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        tick = (try? c.decode(Int.self, forKey: .tick)) ?? 0
        elapsedS = (try? c.decode(Double.self, forKey: .elapsedS)) ?? 0
        verdict = (try? c.decode(Verdict.self, forKey: .verdict)) ?? Verdict()
        stable = (try? c.decode(Stable.self, forKey: .stable)) ?? Stable()
    }
}

struct Stable: Decodable {
    var tier = "warming_up"
    var state = "warming"
    var alert = "none"
    var sinceS: Double = 0
    var reasons: [String] = []

    enum CodingKeys: String, CodingKey { case tier, state, alert, sinceS = "since_s", reasons }
    init() {}
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        tier = (try? c.decode(String.self, forKey: .tier)) ?? "warming_up"
        state = (try? c.decode(String.self, forKey: .state)) ?? "steady"
        alert = (try? c.decode(String.self, forKey: .alert)) ?? "none"
        sinceS = (try? c.decode(Double.self, forKey: .sinceS)) ?? 0
        reasons = (try? c.decode([String].self, forKey: .reasons)) ?? []
    }
}

struct Tell: Decodable {
    var name = "", family = "", evidence = ""
    var score: Double = 0, weight: Double = 0
    var applicable = true
    enum CodingKeys: String, CodingKey { case name, family, evidence, score, weight, applicable }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name = (try? c.decode(String.self, forKey: .name)) ?? ""
        family = (try? c.decode(String.self, forKey: .family)) ?? ""
        evidence = (try? c.decode(String.self, forKey: .evidence)) ?? ""
        score = (try? c.decode(Double.self, forKey: .score)) ?? 0
        weight = (try? c.decode(Double.self, forKey: .weight)) ?? 0
        applicable = (try? c.decode(Bool.self, forKey: .applicable)) ?? true
    }
}

/// `scores` block of the verdict (services/api/tell/scores.py). All 0...100 except the labels.
struct ScoresBlock: Decodable {
    var scam = 0, aiVoice = 0, confidence = 0
    var confidenceLabel: String?
    var level = "low", levelReason = ""
    var voiceUnresolved = false
    var confidenceNote = ""

    enum CodingKeys: String, CodingKey {
        case scam, aiVoice = "ai_voice", confidence, confidenceLabel = "confidence_label", level
        case levelReason = "level_reason", voiceUnresolved = "voice_unresolved", confidenceNote = "confidence_note"
    }
    init(scam: Int = 0, aiVoice: Int = 0, confidence: Int = 0, confidenceLabel: String? = nil, level: String = "low",
         levelReason: String = "", voiceUnresolved: Bool = false, confidenceNote: String = "") {
        self.scam = scam; self.aiVoice = aiVoice; self.confidence = confidence; self.confidenceLabel = confidenceLabel
        self.level = level; self.levelReason = levelReason; self.voiceUnresolved = voiceUnresolved
        self.confidenceNote = confidenceNote
    }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        func num(_ k: CodingKeys) -> Int { Int(((try? c.decode(Double.self, forKey: k)) ?? 0).rounded()) }
        scam = num(.scam); aiVoice = num(.aiVoice); confidence = num(.confidence)
        confidenceLabel = try? c.decode(String.self, forKey: .confidenceLabel)
        level = (try? c.decode(String.self, forKey: .level)) ?? "low"
        levelReason = (try? c.decode(String.self, forKey: .levelReason)) ?? ""
        voiceUnresolved = (try? c.decode(Bool.self, forKey: .voiceUnresolved)) ?? false
        confidenceNote = (try? c.decode(String.self, forKey: .confidenceNote)) ?? ""
    }
}

/// `quadrant` block (services/api/tell/quadrant.py): voice x content.
struct QuadrantBlock: Decodable, Equatable {
    var voice = "unclear", intent = "unclear", combo = "unclear"
    var comboLabel = ""
    enum CodingKeys: String, CodingKey { case voice, intent, combo, comboLabel = "combo_label" }
    init(voice: String = "unclear", intent: String = "unclear", combo: String = "unclear", comboLabel: String = "") {
        self.voice = voice; self.intent = intent; self.combo = combo; self.comboLabel = comboLabel
    }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        voice = (try? c.decode(String.self, forKey: .voice)) ?? "unclear"
        intent = (try? c.decode(String.self, forKey: .intent)) ?? "unclear"
        combo = (try? c.decode(String.self, forKey: .combo)) ?? "unclear"
        comboLabel = (try? c.decode(String.self, forKey: .comboLabel)) ?? ""
    }
}

struct Verdict: Decodable {
    var tier = "unsure"
    var pAi: Double = 0, pScam: Double = 0, confidence: Double = 0
    var disclosedAI = false
    var transcript = ""
    var tells: [Tell] = []
    var scores: ScoresBlock?
    var quadrant: QuadrantBlock?

    enum CodingKeys: String, CodingKey {
        case tier, pAi = "p_ai", pScam = "p_scam", confidence, disclosedAI = "disclosed_ai", transcript, tells, scores, quadrant
    }
    init() {}
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        tier = (try? c.decode(String.self, forKey: .tier)) ?? "unsure"
        pAi = (try? c.decode(Double.self, forKey: .pAi)) ?? 0
        pScam = (try? c.decode(Double.self, forKey: .pScam)) ?? 0
        confidence = (try? c.decode(Double.self, forKey: .confidence)) ?? 0
        disclosedAI = (try? c.decode(Bool.self, forKey: .disclosedAI)) ?? false
        transcript = (try? c.decode(String.self, forKey: .transcript)) ?? ""
        tells = (try? c.decode([Tell].self, forKey: .tells)) ?? []
        scores = try? c.decode(ScoresBlock.self, forKey: .scores)
        quadrant = try? c.decode(QuadrantBlock.self, forKey: .quadrant)
    }
}
