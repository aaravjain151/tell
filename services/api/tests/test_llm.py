from tell import llm


def test_cap_words_keeps_the_tail():
    t = " ".join(str(i) for i in range(300))
    out = llm.cap_words(t, 120).split()
    assert len(out) == 120 and out[0] == "180" and out[-1] == "299"


def test_cap_words_short_unchanged():
    assert llm.cap_words("hello there", 120) == "hello there"


def test_to_tells_tolerates_junk_scores():
    tells = llm._to_tells({"assistant_style": "high", "scam_framing": None, "disclosed_ai": False}, "m")
    assert [t.score for t in tells] == [0.5, 0.0]


def test_scores_clamped():
    assert llm._score({"x": 7}, "x", 0.0) == 1.0
    assert llm._score({"x": -1}, "x", 0.0) == 0.0


def test_stub_provider_makes_no_calls(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert llm.interpret("anything")[1]["provider"] == "stub"
