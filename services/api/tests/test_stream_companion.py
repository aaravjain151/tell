"""The per-session WS verdict carries the full verdict for THAT session's own client (additive), so a companion app
(tools/ios/bridge.py) never needs the global /live/events feed, which carries every session."""
from tests.test_stream import _env, client, open_ws, pcm, pipeline, read_until, send_audio, sm  # noqa: F401 (fixtures)

FULL = {"tier": "scam", "p_ai": 0.7, "p_scam": 0.9, "confidence": 0.95, "headline": "Scam pattern",
        "transcript": "read me the code", "tells": [],
        "scores": {"scam": 90, "ai_voice": 70, "confidence": 95, "confidence_label": "high", "voice_unresolved": False},
        "quadrant": {"voice": "ai", "intent": "scam", "combo": "ai_scam", "combo_label": "x"}}


class _F:
    def to_dict(self):
        return dict(FULL)


def test_verdict_message_carries_full_verdict(client, monkeypatch):
    monkeypatch.setattr(pipeline, "analyze", lambda a, t, **kw: _F())
    ws, _ = open_ws(client, "far")
    send_audio(ws, pcm(4.0))
    v, _ = read_until(ws, lambda m: m["type"] == "verdict")
    assert v["verdict"]["transcript"] == "read me the code" and v["verdict"]["quadrant"]["combo"] == "ai_scam"
    assert v["verdict"]["scores"]["confidence_label"] == "high" and v["stable"]["tier"]
    assert v["tier"] == "scam" and v["seq"] == 1                              # the old fields are unchanged
    ws.__exit__(None, None, None)


def test_mix_cap_reaches_the_nested_scores(client, monkeypatch):
    monkeypatch.setattr(pipeline, "analyze", lambda a, t, **kw: _F())
    ws, _ = open_ws(client, "mix")
    send_audio(ws, pcm(4.0))
    v, _ = read_until(ws, lambda m: m["type"] == "verdict")
    assert v["confidence"] == sm.MIX_CONF_CAP and v["verdict"]["confidence"] == sm.MIX_CONF_CAP
    assert v["verdict"]["scores"]["confidence"] == 60 and v["verdict"]["scores"]["confidence_label"] == "medium"
    assert FULL["scores"]["confidence_label"] == "high"                       # the pipeline's own dict is untouched
    ws.__exit__(None, None, None)
