/* Display logic for a verdict. Mirrors apps/web/index.html (quadrantOf, scoresOf, plainReasons, buildMarks) so the phone
   and the laptop page never disagree. Pure; used by the page and the node tests. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DSVerdict = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var TIER = { human: "Human", ai_disclosed: "AI, said so", ai_undisclosed: "AI, didn't say so", scam: "Scam pattern", unsure: "Unsure" };
  var ORB_WORD = { human: "Human", ai_disclosed: "AI", ai_undisclosed: "AI", scam: "Scam", unsure: "Not sure" };
  var TEXT = {
    human: { h: "Sounds human", a: "No synthetic-voice tells found. If money or codes come up, hang up and call back on a number you already have." },
    ai_undisclosed: { h: "Likely synthetic, didn't say so", a: "Legitimate AI callers are required to identify themselves. Treat this as untrusted: hang up and call back on a number you already have." },
    ai_disclosed: { h: "AI, identified itself", a: "The caller said it's automated. Fine for appointment reminders; never share codes or payment with an automated caller." },
    scam: { h: "Scam pattern", a: "Hang up. Do not send money, cards, or codes. Call the person or organisation back on a number you already have." },
    unsure: { h: "Not sure yet", a: "Not enough to judge yet. Tell keeps listening." },
  };
  var NAMES = { urgency: "Urgency", payment_rails: "Payment asks", impersonation: "Impersonation", credential_ask: "Credential asks",
    secrecy: "Secrecy", ai_disclosure: "AI disclosure", llm_isms: "Assistant phrasing", disfluency: "Hesitations",
    sentence_uniformity: "Sentence rhythm", llm_scam_framing: "Scam framing", llm_assistant_style: "Scripted style" };
  var QL = { human_ok: "Human voice, no scam pattern heard.", human_scam: "Human voice, but scam pattern in what was said.",
    ai_ok: "AI voice, no scam pattern heard.", ai_scam: "AI voice and scam pattern in what was said." };
  var QV = { human: "Voice sounds human", ai: "Voice may be AI", unclear: "Voice unclear" };
  var QI = { scam: "Scam pattern in what was said", not_scam: "No scam pattern heard", unclear: "Scam pattern unclear" };
  var LEVELS = { low: "Low", medium: "Medium", high: "High" };
  var PLAIN = {
    payment_rails: "They asked you to pay or send money", secrecy: "They asked you to keep this secret",
    urgency: "They pressed you to act right now", impersonation: "They claimed to be someone you know or trust",
    credential_ask: "They asked for a code or a password",
    pause_regularity: "The voice may be an AI copy, not a real person", breath_proxy: "The voice may be an AI copy, not a real person",
    pitch_stability: "The voice may be an AI copy, not a real person", noise_floor: "The voice may be an AI copy, not a real person",
    neural_hf: "The voice may be an AI copy, not a real person", neural_onnx: "The voice may be an AI copy, not a real person",
    neural_pella: "The voice may be an AI copy, not a real person",
    llm_isms: "The wording sounds scripted", disfluency: "The wording sounds scripted", sentence_uniformity: "The wording sounds scripted",
  };

  function quadrantOf(v, pAiThr) {
    if (v.quadrant) return v.quadrant;
    var thr = pAiThr || 0.6, pa = v.p_ai, ps = v.p_scam, tl = v.tells || [];
    var noAudio = tl.length && !tl.some(function (t) { return t.family === "acoustic" && t.applicable && t.weight > 0; });
    var voice = v.disclosed_ai || pa >= thr ? "ai" : noAudio ? "unclear" : pa <= 0.4 ? "human" : "unclear";
    var intent = ps >= 0.55 ? "scam" : ps < 0.3 ? "not_scam" : "unclear";
    var combo = "unclear", label;
    if (voice !== "unclear" && intent !== "unclear") { combo = voice + (intent === "scam" ? "_scam" : "_ok"); label = QL[combo]; }
    else if (voice === "unclear" && intent === "scam") label = "Scam pattern. Voice unclear.";
    else if (voice === "unclear" && intent === "not_scam") label = "Voice unclear. No scam pattern heard.";
    else if (voice === "unclear") label = "Voice and scam pattern both unclear.";
    else label = QV[voice] + ". Scam pattern unclear.";
    return { voice: voice, voice_label: QV[voice], intent: intent, intent_label: QI[intent], combo: combo, combo_label: label,
      voice_note: v.disclosed_ai ? "The caller said it is automated." : noAudio ? "No audio was analysed, so the voice could not be judged."
        : voice === "unclear" ? "The voice signs are mixed." : "Based on how the voice and wording sounded." };
  }

  function scoresOf(v) {
    if (v.scores) return v.scores;
    var pc = function (x) { return Math.round(Math.max(0, Math.min(1, x || 0)) * 100); }, pa = v.p_ai, ps = v.p_scam, cf = v.confidence;
    var level = "low", why = "No synthetic-voice or scam signs were found in what we heard.";
    if (v.tier === "scam") { level = "high"; why = "Scam wording was detected on this call."; }
    else if (v.tier === "ai_undisclosed") { level = pa >= 0.8 ? "high" : "medium"; why = pa >= 0.8 ? "The voice looks synthetic and the caller did not say so." : "The voice may be synthetic and the caller did not say so."; }
    else if ((v.tier === "unsure" || v.tier === "ai_disclosed") && ps >= 0.3) { level = "medium"; why = "Some pressure or payment wording came up."; }
    else if (v.tier === "ai_disclosed") why = "The caller said it is automated, and no scam wording was found.";
    else if (v.tier === "unsure") why = "Not enough signal to judge, and no scam wording was found.";
    return { scam: pc(ps), ai_voice: pc(pa), confidence: pc(cf), confidence_label: cf >= 0.8 ? "high" : cf >= 0.5 ? "medium" : "low", level: level, level_reason: why };
  }

  /* The card shows the STABLE tier; if a tick disagrees, recompute so the 2x2 and scores never contradict the orb. */
  function stableView(v, st) {
    var o = Object.assign({}, v);
    if (st && st.tier && st.tier !== v.tier) {
      o.tier = st.tier; delete o.scores; delete o.quadrant;
      if (st.tier === "scam") o.p_scam = Math.max(o.p_scam || 0, 0.6);
      if (st.tier === "ai_disclosed") o.disclosed_ai = true;
    }
    if (st && Array.isArray(st.reasons) && st.reasons.length) o.reasons = st.reasons; else delete o.reasons;
    return o;
  }

  function plainReasons(v) {
    if (Array.isArray(v.reasons) && v.reasons.length) return v.reasons.filter(function (s) { return typeof s === "string"; }).slice(0, 4);
    var tells = (v.tells || []).filter(function (t) { return t.applicable && PLAIN[t.name] && t.score >= 0.5; });
    tells.sort(function (a, b) { return (b.score * (b.weight || 0)) - (a.score * (a.weight || 0)) || b.score - a.score; });
    var seen = {}, out = [];
    for (var i = 0; i < tells.length; i++) {
      var line = PLAIN[tells[i].name];
      if (seen[line]) continue;
      if (v.tier === "human" && v.p_ai < 0.5 && (line.indexOf("The voice") === 0 || line.indexOf("The wording") === 0)) continue;
      seen[line] = 1; out.push(line);
      if (out.length === 3) break;
    }
    return out;
  }

  function phrasesOf(t) {
    var out = [], re = /[“"]([^”"]{2,80})[”"]/g, m;
    while ((m = re.exec(t.evidence || ""))) out.push(m[1].replace(/[\s,.;:!?]+$/, ""));
    return out;
  }
  var norm = function (s) { return s.replace(/[‘’]/g, "'").toLowerCase(); };
  /* Ranges of the transcript where an intent/script tell quoted the caller's own words. */
  function buildMarks(transcript, tells) {
    var low = norm(transcript || ""), ranges = [];
    (tells || []).forEach(function (t) {
      if (!t.applicable || t.score < 0.4 || t.family === "acoustic") return;
      phrasesOf(t).forEach(function (ph) {
        var needle = norm(ph); if (!needle) return;
        var i = low.indexOf(needle);
        while (i >= 0) { ranges.push({ s: i, e: i + needle.length, t: t }); i = low.indexOf(needle, i + needle.length); }
      });
    });
    ranges.sort(function (a, b) { return a.s - b.s || b.e - a.e; });
    var kept = [], end = 0;
    ranges.forEach(function (r) { if (r.s >= end) { kept.push(r); end = r.e; } });
    return kept;
  }

  /* How many of the ring ticks light up: the larger of the scam and AI-voice scores. */
  function ringTicks(scores, n) {
    var x = Math.max(scores.scam || 0, scores.ai_voice || 0) / 100;
    return Math.round(Math.max(0, Math.min(1, x)) * (n || 48));
  }
  function mmss(s) { s = Math.max(0, s || 0); return Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0"); }

  return { TIER: TIER, ORB_WORD: ORB_WORD, TEXT: TEXT, NAMES: NAMES, LEVELS: LEVELS, quadrantOf: quadrantOf, scoresOf: scoresOf,
           stableView: stableView, plainReasons: plainReasons, buildMarks: buildMarks, ringTicks: ringTicks, mmss: mmss };
});
