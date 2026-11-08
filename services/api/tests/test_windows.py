import numpy as np

from tell.signals.windows import SR, windows


def tone(seconds, amp=0.1):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_short_clip_is_one_window():
    w = windows(tone(3.0))
    assert len(w) == 1 and w[0][0] == 0.0 and len(w[0][1]) == 3 * SR


def test_silent_clip_has_no_windows():
    assert windows(np.zeros(10 * SR, dtype=np.float32)) == []
    assert windows(np.zeros(2 * SR, dtype=np.float32)) == []


def test_windows_are_four_seconds_with_two_second_hop():
    w = windows(tone(10.0), max_n=99)
    assert [s for s, _ in w] == [0.0, 2.0, 4.0, 6.0] and all(len(c) == 4 * SR for _, c in w)


def test_tail_is_covered_when_hop_does_not_land_on_the_end():
    w = windows(tone(9.0), max_n=99)
    assert w[-1][0] == 5.0 and len(w[-1][1]) == 4 * SR           # last window ends exactly at 9 s


def test_cap_keeps_evenly_spaced_windows_covering_the_call():
    w = windows(tone(60.0), max_n=3)
    starts = [s for s, _ in w]
    assert len(w) == 3 and starts[0] == 0.0 and starts[-1] == 56.0 and 20 < starts[1] < 36


def test_silence_inside_a_call_is_skipped():
    x = np.concatenate([tone(4.0), np.zeros(4 * SR, dtype=np.float32), tone(4.0)])
    starts = [s for s, _ in windows(x, max_n=99)]
    assert 4.0 not in starts and 0.0 in starts and 8.0 in starts
