"""Display-only scores: table tests, additive field, Tell.detail never serialised or signed, voice_windows merge."""
import pytest

from tell import pipeline, scorer
from tell.scores import confidence_label, scores_for
from tell.types import Tell, Verdict


def V(tier, p_ai=0.5, p_scam=0.0, conf=0.9, tells=None):
    return Verdict(tier=tier, p_ai=p_ai, p_scam=p_scam, confidence=conf, disclosed_ai=tier == "ai_disclosed", headline="h", advice="a",
                   tells=tells or [])


def VOTERS(*neural):
    """Two acoustic behavioural voters plus the given neural scores (onnx, hf, pella order)."""
    out = [Tell("pause_regularity", "acoustic", 0.5, 1.0, "e"), Tell("pitch_stability", "acoustic", 0.5, 1.0, "e")]
    for n, sc in zip(("neural_onnx", "neural_hf", "neural_pella"), neural):
        out.append(Tell(n, "acoustic", sc, 1.0, "e"))
    return out


@pytest.mark.parametrize("tier,p_ai,p_scam,level", [
    ("scam", 0.1, 0.9, "high"),
    ("ai_undisclosed", 0.80, 0.0, "high"),
    ("ai_undisclosed", 0.79, 0.0, "medium"),
    ("ai_undisclosed", 0.61, 0.0, "medium"),
    ("unsure", 0.5, 0.30, "medium"),
    ("unsure", 0.5, 0.29, "low"),
    ("ai_disclosed", 0.9, 0.0, "low"),
    ("ai_disclosed", 0.9, 0.3, "medium"),
    ("human", 0.1, 0.0, "low"),
])
def test_level_table(tier, p_ai, p_scam, level):
    assert scores_for(V(tier, p_ai, p_scam))["level"] == level


@pytest.mark.parametrize("conf,label", [(0.49, "low"), (0.50, "medium"), (0.79, "medium"), (0.80, "high"), (1.0, "high"), (0.0, "low")])
def test_confidence_bands(conf, label):
    assert confidence_label(conf) == label
    assert scores_for(V("human", p_ai=0.1, conf=conf, tells=VOTERS()))["confidence_label"] == label


def test_scores_shape_and_rounding():
    s = scores_for(V("scam", p_ai=0.756, p_scam=0.98, conf=0.99))
    assert s["scam"] == 98 and s["ai_voice"] == 76 and s["confidence"] == 99
    assert set(s) == {"scam", "ai_voice", "confidence", "confidence_label", "level", "level_reason",
                      "voice_sure", "voice_unresolved", "confidence_note"}
    assert all(isinstance(s[k], int) for k in ("scam", "ai_voice", "confidence"))


def test_wording_never_claims_safety_or_legality():
    for tier in ("human", "ai_disclosed", "ai_undisclosed", "scam", "unsure"):
        for p_ai in (0.1, 0.9):
            for p_scam in (0.0, 0.5):
                r = scores_for(V(tier, p_ai, p_scam))["level_reason"].lower()
                assert not any(w in r for w in ("safe", "legal", "illegal", "fraud", "confirmed"))


def test_additive_field_and_signature_unchanged():
    v = pipeline.analyze(None, "Please send gift cards right now, don't tell anyone, I am your grandson in trouble.")
    d = v.to_dict()
    assert d["scores"]["level"] == "high" or d["tier"] != "scam"
    for k in ("tier", "p_ai", "p_scam", "confidence", "tells", "signature", "egress", "reasons", "transcript"):
        assert k in d
    # the signed payload does not include scores: recomputing without them verifies
    from tell import privacy
    payload = {"tier": v.tier, "p_ai": round(v.p_ai, 3), "p_scam": round(v.p_scam, 3),
               "tells": [(t.name, round(t.score, 3)) for t in v.tells], "thresholds_version": v.thresholds_version}
    assert v.signature == privacy.sign(payload, privacy.audio_fingerprint(None))


def test_tell_detail_not_serialised():
    t = Tell("neural_pella", "acoustic", 0.7, 1.0, "e", detail={"windows": [{"t": 0.0, "p": 0.7}]})
    assert "detail" not in t.to_dict()
    assert "detail" not in Tell("x", "acoustic", 0.5, 1.0, "e").to_dict()


def test_scores_do_not_move_the_tier():
    a = scorer.fuse([Tell("a", "acoustic", 0.9, 1.0, "e")], [], [], False)
    b = scorer.fuse([Tell("a", "acoustic", 0.9, 1.0, "e", detail={"windows": [{"t": 0, "p": 0.1}]})], [], [], False)
    assert (a.tier, a.p_ai, a.p_scam, a.confidence) == (b.tier, b.p_ai, b.p_scam, b.confidence)


def W(name, pts):
    return Tell(name, "acoustic", 0.5, 1.0, "e", detail={"windows": [{"t": t, "p": p} for t, p in pts]})


def test_voice_windows_merge_ordered_by_time():
    out = pipeline.voice_windows([W("neural_hf", [(3.0, 0.2), (0.0, 0.1)]), W("neural_pella", [(2.0, 0.9), (0.0, 0.8)])])
    assert [w["t"] for w in out] == [0.0, 2.0, 3.0]
    assert out[0] == {"t": 0.0, "hf": 0.1, "pella": 0.8}
    assert out[1] == {"t": 2.0, "pella": 0.9} and out[2] == {"t": 3.0, "hf": 0.2}


def test_voice_windows_cap_keeps_first_and_last():
    out = pipeline.voice_windows([W("neural_pella", [(float(i), 0.5) for i in range(200)])])
    assert len(out) == pipeline.VOICE_WINDOW_CAP == 60
    assert out[0]["t"] == 0.0 and out[-1]["t"] == 199.0
    assert [w["t"] for w in out] == sorted(w["t"] for w in out)


def test_voice_windows_ignores_inapplicable_and_other_tells():
    na = W("neural_pella", [(0.0, 0.9)])
    na.applicable = False
    assert pipeline.voice_windows([na, W("pause_regularity", [(0.0, 0.9)]), Tell("neural_hf", "acoustic", 0.5, 1.0, "e")]) == []


# ---- honest "How sure" -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("p_ai,unresolved", [(0.29, False), (0.30, True), (0.59, True), (0.60, False)])
def test_band_boundaries(p_ai, unresolved):
    s = scores_for(V("human", p_ai=p_ai, conf=1.0, tells=VOTERS()))
    assert s["voice_unresolved"] is unresolved
    assert s["confidence_label"] == ("medium" if unresolved else "high")
    assert s["confidence_note"] == ("The voice check is not sure." if unresolved else "")


@pytest.mark.parametrize("a,b,disagree", [(0.50, 0.84, False), (0.50, 0.85, False), (0.50, 0.86, True)])
def test_disagreement_boundary(a, b, disagree):
    s = scores_for(V("human", p_ai=0.1, conf=1.0, tells=VOTERS(a, b)))
    assert s["voice_unresolved"] is disagree
    assert s["confidence_label"] == ("medium" if disagree else "high")
    assert s["confidence_note"] == ("The voice checks disagree." if disagree else "")


def test_disagree_in_band_is_low():
    s = scores_for(V("human", p_ai=0.45, conf=1.0, tells=VOTERS(0.1, 0.9)))
    assert s["confidence_label"] == "low" and s["confidence_note"] == "The voice checks disagree."


def test_too_few_voters_caps_medium():
    one = [Tell("pause_regularity", "acoustic", 0.9, 1.0, "e")]
    s = scores_for(V("ai_undisclosed", p_ai=0.9, conf=1.0, tells=one))
    assert s["confidence_label"] == "medium" and s["voice_unresolved"]
    off = one + [Tell("neural_onnx", "acoustic", 0.9, 1.0, "e", applicable=False)]
    assert scores_for(V("ai_undisclosed", p_ai=0.9, conf=1.0, tells=off))["confidence_label"] == "medium"
    assert scores_for(V("ai_undisclosed", p_ai=0.9, conf=1.0, tells=VOTERS()))["confidence_label"] == "high"


def test_disclosed_voice_is_resolved_by_words():
    assert scores_for(V("ai_disclosed", p_ai=0.45, conf=1.0))["confidence_label"] == "high"


def test_confidence_and_voice_sure_range_and_unchanged():
    s = scores_for(V("human", p_ai=0.45, conf=1.0, tells=VOTERS()))
    assert s["confidence"] == 100 and 0 <= s["voice_sure"] <= 40
    assert scores_for(V("ai_undisclosed", p_ai=0.95, conf=1.0, tells=VOTERS(0.9, 0.9, 0.9)))["voice_sure"] == 100


def test_new_wording_banned_words():
    for p in (0.1, 0.45, 0.9):
        for n in ((), (0.1, 0.9)):
            s = scores_for(V("human", p_ai=p, tells=VOTERS(*n)))
            assert not any(w in s["confidence_note"].lower() for w in ("safe", "legal", "illegal", "fraud", "confirmed"))
