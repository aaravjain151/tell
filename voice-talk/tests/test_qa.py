import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import qa_run  # noqa: E402
import qa_score  # noqa: E402
from conftest import FakeLLM, FakeSynth  # noqa: E402
from voice_talk import qa  # noqa: E402
from voice_talk.personas import DIR, load_persona  # noqa: E402


@pytest.mark.parametrize("url", ["https://api.example.com", "http://192.168.1.5:8000", "http://127.0.0.1@evil.example/",
                                 "http://127.0.0.1.evil.example:8000", "ftp://127.0.0.1", "http://10.0.0.1"])
def test_qa_score_refuses_non_loopback(url, tmp_path, capsys):
    called = []
    rc = qa_score.main([str(tmp_path), "--api", url], poster=lambda *a, **k: called.append(1))
    assert rc == 2 and not called and "loopback" in capsys.readouterr().err


def test_qa_score_accepts_loopback_and_prints_table(tmp_path, capsys):
    for name, exp in [("a_case", "scam"), ("b_case", "ai_disclosed")]:
        d = tmp_path / name
        d.mkdir()
        sf.write(d / "call.wav", np.zeros(1600, dtype="float32"), 16000)
        (d / "label.json").write_text(json.dumps({"scenario": name, "expected_tier": exp}))
    seen = []

    def poster(api, wav):
        seen.append(api)
        return {"tier": "scam", "p_ai": 0.9, "p_scam": 0.8, "confidence": 0.7}

    assert qa_score.main([str(tmp_path), "--api", "http://localhost:8000/"], poster=poster) == 0
    out = capsys.readouterr().out
    assert set(seen) == {"http://localhost:8000"} and "a_case" in out and "yes" in out and "NO" in out
    assert "1/2 correct" in out and "sanity check, not a measurement" in out
    for col in ["scenario", "expected", "got tier", "p_ai", "p_scam", "confidence", "correct?"]:
        assert col in out


def test_post_audio_itself_refuses_remote():
    with pytest.raises(qa_score.NotLoopback):
        qa_score.post_audio("http://example.com", b"x")


def test_qa_personas_are_marked_test_and_fictional():
    for sc in qa.SCENARIOS.values():
        p = load_persona(sc.persona, DIR / "qa")
        assert "TEST PERSONA" in (DIR / "qa" / f"{sc.persona}.md").read_text()
    scam = (DIR / "qa" / "scam_pattern_test.md").read_text()
    assert "FICTIONAL" in scam and "000-TEST" in scam
    import re
    assert not re.search(r"\d{3}[-. ]\d{3}[-. ]\d{4}", scam)  # no phone-number-like strings
    assert {s.expected_tier for s in qa.SCENARIOS.values()} <= set(qa.TIERS)


def test_run_scenario_and_save_with_fakes(tmp_path):
    sc = qa.SCENARIOS["disclosed_assistant"]
    llm = FakeLLM(["Okay, noted. Anything else?"])
    sy = FakeSynth()
    audio, sr, tr = qa.run_scenario(sc, llm, sy, "alice")
    assert tr[0] == {"speaker": "caller", "text": sc.opener}
    assert [t["speaker"] for t in tr].count("recipient") == len(sc.recipient)
    assert len(audio) > 0 and sr == 24000
    d = qa.save_run(tmp_path, sc, audio, sr, tr, "alice", {"llm": "fake"}, False)
    label = json.loads((d / "label.json").read_text())
    assert label["expected_tier"] == "ai_disclosed" and label["scenario"] == "disclosed_assistant"
    assert label["voice"] == "alice" and label["persona"] == "assistant_disclosed" and "llm" in label["models"]
    assert (d / "call.wav").exists() and d.parent == tmp_path


def test_qa_run_needs_ack_and_consent(tmp_path, store, capsys):
    assert qa_run.main(["--voice", "alice", "--out", str(tmp_path)]) == 2
    assert qa_run.main(["--voice", "ghost", "--ack-test-only", "--out", str(tmp_path)], chat=FakeLLM(), synth=FakeSynth(), voices=store) == 1
    assert not list(tmp_path.iterdir())


def test_qa_run_end_to_end_scripted_with_fakes(tmp_path, good_voice):
    rc = qa_run.main(["--voice", "alice", "--ack-test-only", "--scripted", "--scenario", "scam_pattern", "--out", str(tmp_path)],
                     chat=FakeLLM(), synth=FakeSynth(), voices=good_voice)
    assert rc == 0 and (tmp_path / "scam_pattern" / "call.wav").exists()
