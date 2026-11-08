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


def test_qwen3_requests_no_thinking(monkeypatch):
    """Thinking tokens would blow the num_predict budget and the latency target."""
    import json as _json
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    seen = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"response": "{}", "prompt_eval_count": 1, "eval_count": 1}'

    def fake(req, timeout=0):
        seen["body"] = _json.loads(req.data)
        return R()
    import types
    from tell import localhost
    monkeypatch.setattr(localhost, "_OPENER", types.SimpleNamespace(open=fake))
    llm._ollama("hello world")
    assert seen["body"]["think"] is False
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    llm._ollama("hello world")
    assert "think" not in seen["body"]
