"""Regression tests for the second review: decode DoS, upload-limit parsing, ffmpeg whitelist, privacy posture."""
from __future__ import annotations

import importlib
import io
import logging
import shutil
import struct
import tracemalloc
import wave

import numpy as np
import pytest

from doublespeak import audio, privacy


def make_wav(sr: int, frames: int, sw: int = 1, ch: int = 1) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes((b"\x80" if sw == 1 else b"\x00" * sw) * frames * ch)
    return b.getvalue()


def _refused_cheaply(fn) -> None:
    tracemalloc.start()
    try:
        with pytest.raises(audio.AudioDecodeError):
            fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 50 * 1024 * 1024


@pytest.mark.parametrize("sr", [1, 3999, 192_001])
def test_wav_bad_sample_rate_refused(sr):
    _refused_cheaply(lambda: audio.decode(make_wav(sr, 200_000)))


def test_wav_over_duration_cap_refused_before_alloc(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_MAX_AUDIO_S", "1")
    _refused_cheaply(lambda: audio.decode(make_wav(8000, 16_000)))   # 2 s > 1 s
    monkeypatch.setenv("DOUBLESPEAK_MAX_AUDIO_S", "bogus")           # tolerant parse -> default 180
    audio.decode(make_wav(8000, 8000))


def test_wav_too_many_channels_refused():
    _refused_cheaply(lambda: audio.decode(make_wav(8000, 100, ch=200)))


def test_wav_header_claiming_absurd_frames_stays_small():
    b = bytearray(make_wav(4000, 100))
    b[40:44] = struct.pack("<I", 0xFFFFFFFF)   # data chunk size
    b[4:8] = struct.pack("<I", 0xFFFFFFFF)
    tracemalloc.start()
    try:
        try:
            x, _, _ = audio.decode(bytes(b))
            assert len(x) < 1000
        except audio.AudioDecodeError:
            pass
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 50 * 1024 * 1024


def test_resample_refuses_huge_output_before_alloc():
    _refused_cheaply(lambda: audio.resample(np.zeros(1000, dtype=np.float32), 1))


def test_ffmpeg_command_has_pipe_only_whitelist():
    cmd = audio._ffmpeg_cmd("ffmpeg")
    i = cmd.index("-protocol_whitelist")
    assert cmd[i + 1] == "pipe"
    assert "-nostdin" in cmd
    assert i < cmd.index("-i")     # must precede the input to apply to it


def test_ffmpeg_output_is_bounded_by_cap(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_MAX_AUDIO_S", "10")
    cmd = audio._ffmpeg_cmd("ffmpeg")
    assert cmd[cmd.index("-t") + 1] == "11"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_playlist_and_concat_text_rejected(tmp_path):
    target = tmp_path / "x.wav"
    target.write_bytes(make_wav(8000, 8000))
    hls = f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://{target}\n#EXT-X-ENDLIST\n".encode()
    concat = f"ffconcat version 1.0\nfile '{target}'\n".encode()
    for payload in (hls, concat):
        with pytest.raises(audio.AudioDecodeError):
            audio.decode(payload)


def test_upload_mb_parsing_never_crashes_at_import(monkeypatch):
    from doublespeak import uploads
    try:
        for raw, expect_mb in (("12.5", 12.5), ("abc", 25), ("", 25)):
            monkeypatch.setenv("DOUBLESPEAK_MAX_UPLOAD_MB", raw)
            importlib.reload(uploads)
            assert uploads.keep_uploads_in_memory() >= int(expect_mb * 1024 * 1024)
    finally:
        monkeypatch.delenv("DOUBLESPEAK_MAX_UPLOAD_MB", raising=False)
        importlib.reload(uploads)


def test_main_imports_are_one_block():
    import doublespeak.main as m
    with open(m.__file__) as f:
        assert len([ln for ln in f.read().splitlines() if ln.startswith("from . import")]) == 1


def test_posture(monkeypatch):
    for k in ("DOUBLESPEAK_DEBUG_SAVE", "LLM_PROVIDER", "GRADIUM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert privacy.posture() == {"debug_save": False, "llm_provider_anthropic": False, "gradium_key_set": False}
    monkeypatch.setenv("DOUBLESPEAK_DEBUG_SAVE", "1")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("GRADIUM_API_KEY", "secret-key-value")
    p = privacy.posture()
    assert p == {"debug_save": True, "llm_provider_anthropic": True, "gradium_key_set": True}
    assert "secret-key-value" not in str(p)


def test_debug_save_warns_once(monkeypatch, caplog):
    from doublespeak import pipeline
    monkeypatch.setattr(pipeline, "_debug_warned", False)
    with caplog.at_level(logging.WARNING, logger="doublespeak.pipeline"):
        pipeline._warn_debug_save_once()
        pipeline._warn_debug_save_once()
    assert len([r for r in caplog.records if "DEBUG_SAVE" in r.getMessage()]) == 1
