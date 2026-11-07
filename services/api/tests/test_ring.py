"""RAM ring buffer: wrap-around, cap, last(), wipe()."""
import numpy as np
import pytest

from doublespeak.ring import Ring

SR = 100   # tiny rate keeps the arrays readable


def ramp(a, b):
    return np.arange(a, b, dtype=np.float32)


def test_basic_write_and_last():
    r = Ring(1.0, sr=SR)           # 100 samples
    r.write(ramp(0, 30))
    assert r.total == 30 and r.available == 30
    assert np.array_equal(r.last(0.1), ramp(20, 30))
    assert np.array_equal(r.last(10), ramp(0, 30))     # asks for more than buffered -> what exists


def test_wrap_around_keeps_newest_in_order():
    r = Ring(1.0, sr=SR)
    r.write(ramp(0, 80))
    lost = r.write(ramp(80, 130))
    assert lost == 30 and r.total == 130 and r.available == 100
    assert np.array_equal(r.last(1.0), ramp(30, 130))
    assert np.array_equal(r.last(0.25), ramp(105, 130))


def test_single_write_larger_than_capacity_keeps_tail():
    r = Ring(1.0, sr=SR)
    assert r.write(ramp(0, 350)) == 250
    assert np.array_equal(r.last(1.0), ramp(250, 350))
    r.write(ramp(350, 360))
    assert np.array_equal(r.last(1.0), ramp(260, 360))


def test_many_small_writes_equal_one_big():
    r = Ring(0.5, sr=SR)
    for i in range(0, 333, 7):
        r.write(ramp(i, min(i + 7, 333)))
    assert np.array_equal(r.last(0.5), ramp(283, 333))


def test_last_returns_a_copy():
    r = Ring(1.0, sr=SR)
    r.write(ramp(0, 10))
    x = r.last(1)
    x[:] = -1
    assert np.array_equal(r.last(1), ramp(0, 10))


def test_wipe_zeroes_in_place_and_drops_reference():
    r = Ring(1.0, sr=SR)
    r.write(ramp(1, 101))
    buf = r._buf
    assert buf.any()
    r.wipe()
    assert not buf.any()                 # the very array that held audio is zero
    assert r._buf is None and r.wiped
    assert len(r.last(1)) == 0
    assert r.write(ramp(0, 5)) == 0      # writes after wipe are ignored, nothing resurrects
    assert len(r.last(1)) == 0
    r.wipe()                             # idempotent


def test_invalid_capacity():
    with pytest.raises(ValueError):
        Ring(0)
