"""Stream policy boundaries, state transitions, and pure-module contract."""
import ast
from dataclasses import replace
from pathlib import Path

import pytest

from tell.stabiliser import (
    POLICY_VERSION, RawTick, Stabiliser, StabiliserConfig, from_verdict,
)
from tell.types import Tell, Verdict


def tick(t=0, tier="human", **kwargs):
    return replace(RawTick(t, tier, 0.3, 0.2, 0.7, False, set(), 20, 40, []), **kwargs)


def test_warmup_is_not_a_verdict():
    s = Stabiliser()
    for t, speech, words in [(0, 0, 0), (1, 7.99, 20), (2, 8, 19)]:
        v = s.update(tick(t, speech_seconds=speech, words=words))
        assert v.shown_tier == "warming_up"
        assert v.alert is None
    assert s.update(tick(3, speech_seconds=8, words=20)).shown_tier == "human"
    s.reset()
    v = s.update(tick(0, "scam", p_scam=0.8, speech_seconds=0, words=0))
    assert (v.shown_tier, v.alert) == ("warming_up", None)          # one scam tick is never an alert
    v = s.update(tick(1, "scam", p_scam=0.8, speech_seconds=0, words=0))
    assert (v.shown_tier, v.alert) == ("scam", "red")                # red safety override beats warm-up


@pytest.mark.parametrize("families,probability,expected", [
    (set(), 0.7999, "amber"), ({"payment_rails"}, 0.7, "amber"),
    ({"urgency", "secrecy", "impersonation"}, 0.7, "amber"),
    ({"urgency", "payment_rails"}, 0.1, "red"),
    ({"secrecy", "credential_ask"}, 0.1, "red"), (set(), 0.8, "red"),
])
def test_red_needs_corroboration_or_high_pscam(families, probability, expected):
    s = Stabiliser()
    v = s.update(tick(0, tier="scam", intent_families=families, p_scam=probability))
    if expected == "amber" or not families:
        assert v.alert is None                                      # a lone tick without corroboration: nothing yet
        v = s.update(tick(1, tier="scam", intent_families=families, p_scam=probability))
    assert v.alert == expected
    assert v.alert_reason


def test_single_scam_tick_in_long_human_call_never_alerts():
    s = Stabiliser()
    for t in range(0, 600, 3):
        v = s.update(tick(t, "scam" if t == 300 else "human", p_scam=0.95 if t == 300 else 0.1))
        assert v.alert is None and v.shown_tier == "human"


def test_amber_is_held_then_clears():
    s = Stabiliser()
    s.update(tick(0, "scam"))
    assert s.update(tick(3, "scam")).alert == "amber"
    assert s.update(tick(6)).alert == "amber"                       # held: no notify flapping
    assert s.update(tick(18)).alert == "amber"
    assert s.update(tick(18.001)).alert is None


def test_dismiss_does_not_relatch_on_stale_evidence():
    s = Stabiliser()
    s.update(tick(0, "scam", intent_families={"urgency", "payment_rails"}))
    assert s.update(tick(3, "scam")).alert == "red"
    assert s.dismiss() is True
    assert s.dismiss() is False
    assert s.update(tick(6, "scam")).alert is None                  # needs fresh corroboration
    assert s.update(tick(9, "scam", intent_families={"urgency", "credential_ask"})).alert == "red"


@pytest.mark.parametrize("delay,expected", [(29.99, "red"), (30, "red"), (30.001, None)])
def test_amber_upgrades_to_red_within_30s(delay, expected):
    s = Stabiliser()
    s.update(tick(9, "scam", intent_families={"urgency"}))
    assert s.update(tick(10, "scam", intent_families={"urgency"})).alert == "amber"
    assert s.update(tick(11)).alert == "amber"             # held
    assert s.update(tick(28)).alert is None
    v = s.update(tick(10 + delay, intent_families={"payment_rails"}))
    assert v.alert == expected
    if expected:
        assert v.shown_tier == "scam"


def test_escalate_two_ticks():
    s = Stabiliser()
    assert s.update(tick()).shown_tier == "human"
    assert s.update(tick(1, "ai_disclosed")).shown_tier == "human"
    assert s.update(tick(2, "ai_undisclosed")).shown_tier == "human"
    assert s.update(tick(3, "ai_undisclosed")).shown_tier == "ai_undisclosed"
    assert s.update(tick(4, "scam")).shown_tier == "ai_undisclosed"
    assert s.update(tick(5, "scam")).shown_tier == "scam"


def test_deescalate_slow_with_dwell():
    s = Stabiliser()
    s.update(tick(0, "scam"))
    s.update(tick(1, "scam"))
    for t in range(2, 7):
        assert s.update(tick(t)).shown_tier == "scam"
    assert s.update(tick(20.999)).shown_tier == "scam"
    assert s.update(tick(21)).shown_tier == "human"
    s.update(tick(22, "scam"))
    s.update(tick(23, "scam"))
    for t in range(50, 54):
        assert s.update(tick(t)).shown_tier == "scam"
    # A matching tick cancels the lower streak even after dwell expires.
    s.update(tick(54, "scam"))
    for t, tier in [(55, "human"), (56, "unsure"), (57, "ai_disclosed"), (58, "human")]:
        assert s.update(tick(t, tier)).shown_tier == "scam"
    assert s.update(tick(59, "unsure")).shown_tier == "unsure"


def test_evidence_is_sticky():
    s = Stabiliser()
    original = tick(intent_families={"urgency"})
    first = s.update(original)
    original.intent_families.clear()
    first.evidence.clear()
    s.update(tick(1, intent_families={"secrecy", "urgency"}))
    assert s.update(tick(1000)).evidence == ["secrecy", "urgency"]


def test_disclosure_floor_and_scam_override():
    s = Stabiliser()
    s.update(tick(0, "ai_undisclosed"))
    assert s.update(tick(1, "ai_undisclosed")).shown_tier == "ai_undisclosed"
    assert s.update(tick(2, disclosed_ai=True)).shown_tier == "ai_disclosed"
    for t in range(3, 10):
        v = s.update(tick(t, "ai_undisclosed", p_ai=1))
        assert (v.shown_tier, v.alert) == ("ai_disclosed", None)
    assert s.update(tick(10, "scam")).shown_tier == "ai_disclosed"
    assert s.update(tick(11, "scam")).shown_tier == "scam"
    for t in range(31, 35):
        assert s.update(tick(t)).shown_tier == "scam"
    assert s.update(tick(35)).shown_tier == "ai_disclosed"
    s.update(tick(36, "scam", p_scam=0.8))
    assert s.update(tick(37, "scam", p_scam=0.8)).alert == "red"


def test_red_latches_until_dismissed():
    s = Stabiliser()
    s.update(tick())
    s.update(tick(1, "scam", p_scam=0.8))
    red = s.update(tick(2, "scam", p_scam=0.8))
    red.alert_reason.clear()
    for t in range(3, 100):
        v = s.update(tick(t))
        assert (v.shown_tier, v.alert) == ("scam", "red")
        assert v.alert_reason == ["high_p_scam"]
    s.dismiss(1)  # Before this episode.
    s.dismiss(v.seq + 1)  # Not yet emitted.
    assert s.update(tick(100)).alert == "red"
    s.dismiss(red.seq)
    for t in range(101, 105):
        v = s.update(tick(t))
        assert (v.shown_tier, v.alert) == ("scam", None)
    assert s.update(tick(105)).shown_tier == "human"
    s.update(tick(106, "scam", p_scam=0.8))
    assert s.update(tick(107, "scam", p_scam=0.8)).alert == "red"
    s.dismiss(red.seq)  # Cannot acknowledge a newer episode.
    assert s.update(tick(108)).alert == "red"


@pytest.mark.parametrize("high", [False, True])
@pytest.mark.parametrize("step", [0.1, 1, 10])
def test_no_flap_on_alternating_ticks(high, step):
    s = Stabiliser()
    previous = s.update(tick()).shown_tier
    changes = []
    for i in range(1, 1201):
        v = s.update(tick(i * step, "scam" if i % 2 else "human", p_scam=0.9 if high else 0.5))
        if v.shown_tier != previous:
            changes.append(v.t)
        previous = v.shown_tier
    assert all(b - a >= 60 for a, b in zip(changes, changes[1:]))
    assert len(changes) <= 1


def test_ai_undisclosed_never_red():
    s = Stabiliser()
    for t, p, speech, alert in [(0, 0.9, 20, None), (1, 0.6, 20, None),
                               (2, 0.1, 14.99, None), (3, 0.6, 15, "amber"),
                               (4, 0.1, 20, None)]:
        v = s.update(tick(t, "ai_undisclosed", p_ai=p, p_scam=1, speech_seconds=speech,
                          intent_families={"urgency", "payment_rails"}))
        assert v.alert == alert


def test_reset_wipes_state():
    config = StabiliserConfig(p_ai_threshold=0.9)
    s = Stabiliser(config)
    s.update(tick(100, "scam", disclosed_ai=True, p_scam=1, intent_families={"urgency"}))
    s.reset()
    fresh = tick(0, speech_seconds=0, words=0)
    assert s.update(fresh) == Stabiliser(config).update(fresh)
    assert s.config == config
    assert s.update(tick(1)).shown_tier == "human"


def test_from_verdict_maps_intent_tells():
    tells = [Tell("urgency", "intent", 0.5, 0, ""),
             Tell("urgency", "intent", 1, 1, ""),
             Tell("payment_rails", "intent", 0.4999, 1, ""),
             Tell("credential_ask", "intent", 1, 1, "", applicable=False),
             Tell("secrecy", "script", 1, 1, ""),
             Tell("unknown", "intent", 1, 1, "")]
    v = Verdict("ai_disclosed", 0.8, 0.3, 0.9, True, "headline", "advice", tells)
    raw = from_verdict(v, 12, 8, 20)
    assert raw == RawTick(12, "ai_disclosed", 0.8, 0.3, 0.9, True, {"urgency"}, 8, 20, [])
    assert len(v.tells) == 6


def test_module_is_pure():
    source = Path(__file__).resolve().parents[1] / "tell" / "stabiliser.py"
    tree = ast.parse(source.read_text())
    banned = {"socket", "urllib", "http", "time", "os", "subprocess", "datetime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {alias.name.split(".")[0] for alias in node.names} & banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
        elif isinstance(node, ast.Call):
            assert not (isinstance(node.func, ast.Name) and node.func.id == "open")
            assert not (isinstance(node.func, ast.Attribute) and node.func.attr == "open")


def test_snapshot_metadata_and_determinism():
    a, b = Stabiliser(), Stabiliser()
    for i in range(10):
        raw = tick(i, degraded=["no_stt"])
        v = a.update(raw)
        assert v == b.update(raw)
        assert (v.seq, v.t, v.raw_tier, v.p_ai, v.p_scam, v.confidence) == (i + 1, i, "human", 0.3, 0.2, 0.7)
        assert v.policy_version == POLICY_VERSION
        raw.degraded.clear()
        assert v.degraded == ["no_stt"]


@pytest.mark.parametrize("bad_t", [-1, float("nan"), float("inf"), 9])
def test_invalid_time_does_not_mutate_state(bad_t):
    s = Stabiliser()
    s.update(tick(10))
    with pytest.raises(ValueError):
        s.update(tick(bad_t, "scam", p_scam=1))
    assert s.update(tick(10)).seq == 2


def test_config_controls_ai_threshold():
    s = Stabiliser(StabiliserConfig(p_ai_threshold=0.9))
    for i in range(3):
        assert s.update(tick(i, "ai_undisclosed", p_ai=0.8)).alert is None
    s.update(tick(3, "ai_undisclosed", p_ai=0.9))
    assert s.update(tick(4, "ai_undisclosed", p_ai=0.9)).alert == "amber"


@pytest.mark.parametrize("kwargs", [{"p_ai_threshold": 1.1}, {"escalation_ticks": 0},
                                    {"dwell_seconds": -1}, {"warmup_words": 1.5}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        StabiliserConfig(**kwargs)
