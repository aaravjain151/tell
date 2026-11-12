import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_voice  # noqa: E402
from voice_talk.voices import VoiceStore  # noqa: E402

TEXT = ("Hello and welcome to the test recording. This first sentence is spoken quite clearly. "
        "Now there is a pause and the second part begins. It also has a few more words in it. "
        "Finally the last sentence closes out the whole recording nicely.")


def long_clip(path, sr=16000):
    rng = np.random.default_rng(0)
    parts = []
    for dur in (3.5, 4.0, 4.5, 3.0):  # four phrases separated by 0.6 s pauses
        t = np.arange(int(dur * sr)) / sr
        parts.append((0.3 * np.sin(2 * np.pi * 150 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype("float32"))
        parts.append((rng.normal(0, 0.001, int(0.6 * sr))).astype("float32"))
    sf.write(path, np.concatenate(parts), sr)


@pytest.fixture
def files(tmp_path):
    src, txt = tmp_path / "src.wav", tmp_path / "src.txt"
    long_clip(src)
    txt.write_text(TEXT)
    return src, txt, tmp_path / "voices"


def run(args):
    return import_voice.main([str(a) for a in args])


def base(files, **over):
    src, txt, vd = files
    a = {"--src": src, "--transcript": txt, "--name": "tester", "--speaker": "Test Person",
         "--attest": "Test Person said on 2026-01-01 that this clip may be used for local testing", "--voices-dir": vd}
    a.update(over)
    return [x for kv in a.items() for x in kv if x is not None]


def test_imports_a_5_to_15s_segment_and_records_only_the_given_attestation(files):
    assert run(base(files)) == 0
    vd = files[2]
    store = VoiceStore(vd)
    wav, text = store.require_usable("tester")
    info = sf.info(str(wav))
    assert info.samplerate == 24000 and 5.0 <= info.duration <= 15.0 and info.channels == 1
    rec = json.loads((vd / "tester" / "consent.json").read_text())
    assert rec["attestation"] == "Test Person said on 2026-01-01 that this clip may be used for local testing"
    assert rec["speaker_name"] == "Test Person" and rec["schema"] == 2
    assert text and set(text.split()) <= set(TEXT.split())


@pytest.mark.parametrize("missing", ["--speaker", "--attest"])
def test_refuses_without_speaker_or_attest(files, missing, capsys):
    args = base(files)
    i = args.index(missing)
    del args[i:i + 2]
    with pytest.raises(SystemExit):
        run(args)
    assert not (files[2] / "tester").exists()


@pytest.mark.parametrize("over", [{"--attest": "   "}, {"--speaker": " "}, {"--attest": "ok"}])
def test_empty_or_token_values_write_nothing(files, over):
    try:
        rc = run(base(files, **over))
    except SystemExit:
        rc = 2
    assert rc != 0
    assert not (files[2] / "tester").exists()


def test_no_default_attestation_in_source():
    src = (ROOT / "tools" / "import_voice.py").read_text()
    assert 'default=' not in src.split("--attest")[1].split("\n")[0]
    assert "--speaker" in src and "required=True" in src.split('"--speaker"')[1].split("\n")[0]


def test_never_modifies_the_source_recording(files):
    src = files[0]
    before = src.read_bytes()
    run(base(files))
    assert src.read_bytes() == before


def test_unreadable_or_silent_input_is_refused_cleanly(files, tmp_path):
    sf.write(tmp_path / "silent.wav", np.zeros(16000 * 8, dtype="float32"), 16000)
    assert run(base(files, **{"--src": tmp_path / "silent.wav"})) == 1
    assert not (files[2] / "tester").exists()


def test_pick_segment_cuts_at_pauses():
    sr = 16000
    p = Path(__file__).parent / "_tmp_seg.wav"
    try:
        long_clip(p, sr)
        a, _ = sf.read(str(p), dtype="float32")
    finally:
        p.unlink(missing_ok=True)
    seg = import_voice.pick_segment(a, sr, TEXT)
    assert 5 <= seg["end_s"] - seg["start_s"] <= 15 and seg["text"]
