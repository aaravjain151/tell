"""Red-team sample endpoints: listing, serving, and strict path safety. Local files only, no network."""
import wave

import pytest
from fastapi.testclient import TestClient
from tests.conftest import AUTH

from tell.main import app

client = TestClient(app, headers=AUTH)


def _wav(path, frames=800):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * frames)
    return path


@pytest.fixture
def calls(tmp_path, monkeypatch):
    c = tmp_path / "calls"
    _wav(c / "gradium" / "scam_irs.wav")
    (c / "gradium" / "scam_irs.txt").write_text("This is the IRS. Pay now.", encoding="utf-8")
    _wav(c / "gradium" / "scam_irs.opus8k.wav", 400)
    _wav(c / "gradium" / "casual.wav")
    _wav(c / "elevenlabs" / "scam_irs.wav")
    _wav(c / "human" / "alex" / "scam_irs.wav")
    monkeypatch.setenv("TELL_CALLS_DIR", str(c))
    (tmp_path / "secret.wav").write_bytes(b"RIFFsecret")
    (tmp_path / "secret.txt").write_text("top secret")
    return c


def test_list(calls):
    r = client.get("/redteam/samples")
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == ["elevenlabs/scam_irs", "gradium/casual", "gradium/scam_irs", "human/alex__scam_irs"]
    irs = next(x for x in rows if x["id"] == "gradium/scam_irs")
    assert irs == {"id": "gradium/scam_irs", "engine": "gradium", "script": "scam_irs", "label": "ai", "has_text": True, "has_opus8k": True}
    assert next(x for x in rows if x["id"] == "gradium/casual")["has_text"] is False
    assert next(x for x in rows if x["id"] == "human/alex__scam_irs")["label"] == "human"
    assert not any("opus8k" in x["script"] for x in rows)
    assert str(calls) not in r.text


def test_clip_text_and_variant(calls):
    r = client.get("/redteam/clip/gradium/scam_irs")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
    deg = client.get("/redteam/clip/gradium/scam_irs?variant=opus8k")
    assert deg.status_code == 200 and len(deg.content) < len(r.content)
    assert client.get("/redteam/clip/gradium/casual?variant=opus8k").status_code == 404
    assert client.get("/redteam/clip/gradium/scam_irs?variant=nope").status_code == 404
    assert client.get("/redteam/clip/human/alex__scam_irs").status_code == 200
    t = client.get("/redteam/text/gradium/scam_irs")
    assert t.status_code == 200 and t.text == "This is the IRS. Pay now."
    assert client.get("/redteam/text/gradium/casual").status_code == 404


def test_missing_or_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TELL_CALLS_DIR", str(tmp_path / "nope"))
    assert client.get("/redteam/samples").json() == []
    assert client.get("/redteam/clip/gradium/x").status_code == 404
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("TELL_CALLS_DIR", str(tmp_path / "empty"))
    assert client.get("/redteam/samples").json() == []


def test_relative_env_is_repo_relative(monkeypatch):
    monkeypatch.setenv("TELL_CALLS_DIR", "does/not/exist")
    assert client.get("/redteam/samples").json() == []


def test_cap_200(tmp_path, monkeypatch):
    for i in range(205):
        _wav(tmp_path / "gradium" / f"s{i:03}.wav", 10)
    monkeypatch.setenv("TELL_CALLS_DIR", str(tmp_path))
    assert len(client.get("/redteam/samples").json()) == 200


@pytest.mark.parametrize("path", [
    "/redteam/clip/..%2f/secret",
    "/redteam/clip/gradium/..%2fsecret",
    "/redteam/clip/gradium/..%2f..%2fsecret",
    "/redteam/clip/%2e%2e/secret",
    "/redteam/clip/gradium/%2e%2e%2fsecret",
    "/redteam/clip/gradium/%2Fetc%2Fpasswd",
    "/redteam/clip/gradium//etc/passwd",
    "/redteam/clip/gradium/..",
    "/redteam/clip/../gradium/scam_irs",
    "/redteam/clip/gradium/scam_irs.wav",
    "/redteam/clip/gradium/scam_irs%00",
    "/redteam/clip/gradium/scam%5Cirs",
    "/redteam/clip/gradium/%2e%2e",
    "/redteam/clip/gradium/" + "a" * 65,
    "/redteam/text/gradium/..%2fsecret",
    "/redteam/text/..%2f/secret",
    "/redteam/text/gradium/%2Fetc%2Fpasswd",
])
def test_traversal_rejected(calls, path):
    r = client.get(path)
    assert r.status_code in (404, 405) and b"secret" not in r.content and b"root:" not in r.content


def test_dotdot_names_rejected_directly(calls):
    from fastapi import HTTPException

    from tell import redteam
    for e, s in [("..", "secret"), ("gradium", ".."), ("gradium", "a..b"), ("/etc", "passwd"), ("gradium", "/etc/passwd"), ("", "x")]:
        with pytest.raises(HTTPException) as ei:
            redteam._lookup(e, s)
        assert ei.value.status_code == 404


def test_symlinked_file_outside_is_ignored(calls, tmp_path):
    (calls / "gradium" / "leak.wav").symlink_to(tmp_path / "secret.wav")
    (calls / "gradium" / "casual.txt").symlink_to(tmp_path / "secret.txt")
    assert "gradium/leak" not in [x["id"] for x in client.get("/redteam/samples").json()]
    assert client.get("/redteam/clip/gradium/leak").status_code == 404
    assert client.get("/redteam/text/gradium/casual").status_code == 404
    casual = next(x for x in client.get("/redteam/samples").json() if x["id"] == "gradium/casual")
    assert casual["has_text"] is False


def test_symlinked_dir_outside_is_ignored(calls, tmp_path):
    out = tmp_path / "outside"
    _wav(out / "evil.wav")
    (calls / "evil").symlink_to(out, target_is_directory=True)
    assert not any(x["engine"] == "evil" for x in client.get("/redteam/samples").json())
    assert client.get("/redteam/clip/evil/evil").status_code == 404


def test_symlinked_opus_variant_outside_is_ignored(calls, tmp_path):
    (calls / "gradium" / "casual.opus8k.wav").symlink_to(tmp_path / "secret.wav")
    assert client.get("/redteam/clip/gradium/casual?variant=opus8k").status_code == 404
    casual = next(x for x in client.get("/redteam/samples").json() if x["id"] == "gradium/casual")
    assert casual["has_opus8k"] is False
