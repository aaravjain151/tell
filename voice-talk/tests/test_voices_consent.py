import json

import pytest

from conftest import REF_TEXT, make_wav
from voice_talk.voices import ATTESTATION, ConsentError, VoiceError, analyze_clip


def test_no_attestation_writes_nothing(store):
    with pytest.raises(ConsentError):
        store.create("bob", make_wav(), REF_TEXT, "Bob", False)
    assert not (store.root / "bob").exists()


def test_speaker_name_required(store):
    with pytest.raises(ConsentError):
        store.create("bob", make_wav(), REF_TEXT, "  ", True)


def test_consent_json_schema(good_voice):
    rec = json.loads((good_voice.root / "alice" / "consent.json").read_text())
    assert set(rec) == {"schema", "voice", "attestation", "speaker_name", "granted_at"}
    assert rec["schema"] == 1 and rec["voice"] == "alice" and rec["attestation"] == ATTESTATION
    assert rec["speaker_name"] == "Alice Example" and rec["granted_at"].endswith("+00:00")
    assert good_voice.consent("alice") == rec


def test_missing_or_tampered_consent_blocks_use(good_voice):
    p = good_voice.root / "alice" / "consent.json"
    assert good_voice.require_usable("alice")[1] == REF_TEXT
    p.unlink()
    with pytest.raises(ConsentError):
        good_voice.require_usable("alice")
    p.write_text(json.dumps({"schema": 1, "voice": "alice"}))
    with pytest.raises(ConsentError):
        good_voice.require_usable("alice")
    rec = {"schema": 1, "voice": "other", "attestation": ATTESTATION, "speaker_name": "x", "granted_at": "2026-01-01T00:00:00+00:00"}
    p.write_text(json.dumps(rec))
    with pytest.raises(ConsentError):
        good_voice.require_usable("alice")


def test_voice_dropped_in_by_hand_is_unusable_until_consent(store):
    d = store.root / "manual"
    d.mkdir(parents=True)
    (d / "ref.wav").write_bytes(make_wav())
    (d / "ref_text.txt").write_text(REF_TEXT)
    with pytest.raises(ConsentError):
        store.require_usable("manual")
    assert store.list()[0]["consent"] is False
    with pytest.raises(ConsentError):
        store.attach_consent("manual", "Me", False)
    store.attach_consent("manual", "Me", True)
    assert store.require_usable("manual")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "x" * 41])
def test_unsafe_names_rejected(store, bad):
    with pytest.raises(VoiceError):
        store.create(bad, make_wav(), REF_TEXT, "A", True)


def test_clip_validation():
    import numpy as np
    sr = 16000
    assert any("at least" in e for e in analyze_clip(np.ones(sr * 2, "float32") * 0.2, sr, "x y z")["errors"])
    assert any("at most" in e for e in analyze_clip(np.ones(sr * 31, "float32") * 0.2, sr, "x y z")["errors"])
    assert any("no speech" in e for e in analyze_clip(np.zeros(sr * 5, "float32"), sr, "a b c")["errors"])
    sound = (0.3 * np.sin(np.arange(sr * 10) / 9)).astype("float32")
    assert analyze_clip(sound, sr, "one two three four five six seven eight nine ten eleven twelve")["errors"] == []
    w = analyze_clip(sound, sr, "only three words")
    assert w["errors"] == [] and any("does not match" in x for x in w["warnings"])
    assert analyze_clip(sound, sr, "")["errors"]
