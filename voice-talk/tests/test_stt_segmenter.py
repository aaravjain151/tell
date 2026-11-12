import numpy as np

from voice_talk.stt import MicSegmenter


def pcm(level, secs):
    return (np.ones(int(16000 * secs)) * level * 32767).astype("<i2").tobytes()


def test_open_mic_splits_on_pause_and_ignores_noise_blips():
    m = MicSegmenter("open", silence_ms=500)
    assert m.feed(pcm(0.0, 1)) == []
    assert m.feed(pcm(0.2, 1.0)) == []
    got = m.feed(pcm(0.0, 0.6))
    assert len(got) == 1 and 1.5 < len(got[0]) / 16000 < 2.7
    m.feed(pcm(0.2, 0.05))
    assert m.feed(pcm(0.0, 0.7)) == []  # too short to be speech


def test_ptt_collects_until_release():
    m = MicSegmenter("ptt")
    assert m.feed(pcm(0.2, 1)) == [] and m.feed(pcm(0.0, 2)) == []
    assert len(m.finish()[0]) == 48000 and m.finish() == []
