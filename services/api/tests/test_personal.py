"""Personal alert sensitivity: bounded, never suppresses protected alerts, deterministic, encrypted at rest, wipeable, off by
default (live events bit-identical), and it never touches the stable view. No network, no keychain (fake key)."""
import asyncio
import itertools
import json
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient
from tests.conftest import AUTH

from tell import live, personal as pe, secure_store as ss
from tell.main import app

KEY = bytes(range(32))
ORIGIN = {"Origin": "http://localhost:5173"}
WORDS = " ".join(["word"] * 30)


def vd(tier="human", p_scam=0.1, p_ai=0.1, families=(), disclosed=False):
    tells = [{"name": n, "family": "intent", "score": 0.9, "weight": 1.0, "evidence": "x", "applicable": True} for n in families]
    return {"tier": tier, "p_ai": p_ai, "p_scam": p_scam, "confidence": 0.8, "disclosed_ai": disclosed, "headline": tier,
            "advice": "", "tells": tells, "reasons": ["fixed sentence"], "transcript": WORDS, "thresholds_version": "t",
            "egress": {"context": {"band_limited": True, "duration_s": 20.0, "shadow": {"snr_db": {"value": 18.0}}}},
            "signature": "", "cost": {}, "model_notes": []}


def feats(**kw) -> pe.CallFeatures:
    return pe.CallFeatures(**kw)


@pytest.fixture
def layer(tmp_path, monkeypatch):
    monkeypatch.setenv("TELL_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TELL_PERSONAL", "1")
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: KEY)
    return pe.PersonalLayer(seed=3)


def amber_disclosed(score=0.6):
    return feats(p_ai=0.8, p_scam=score, peak_scam=score, max_alert=1, disclosed=True, n_families=1, promotable=True)


def teach(p: pe.Personal, f: pe.CallFeatures, label: str, n: int):
    for _ in range(n):
        p.learn(f, label)


# ---------------------------------------------------------------- boundedness
def test_decide_is_bounded_and_clips_out_of_range_shifts():
    for level, score, ps, prot, prom in itertools.product((0, 1, 2), (0.0, 0.3, 0.46, 0.55, 0.62, 0.7, 0.9), (0.0, 0.6, 0.75, 0.95),
                                                           (False, True), (False, True)):
        for a, r in itertools.product((-5, -0.1, 0, 0.15, 5), (-5, -0.1, 0, 5)):
            out = pe.decide(level, score, ps, prot, prom, a, r)
            assert out in (0, 1, 2)
            assert out == pe.decide(level, score, ps, prot, prom, pe.clip(a, *pe.AMBER_RANGE), pe.clip(r, *pe.RED_RANGE))
            if level == 0 and a >= 0:
                assert out == 0                                          # no amber appears without a negative amber shift
            if out == 0 and level == 1:
                assert a > 0 and score < pe.AMBER_BASE + pe.clip(a, *pe.AMBER_RANGE)
            if level == 0 and out > 0:
                assert a < 0 and prom and score >= pe.AMBER_BASE + pe.clip(a, *pe.AMBER_RANGE)


def test_learner_shifts_never_leave_the_documented_range_under_adversarial_feedback():
    rng = np.random.default_rng(0)
    for learner in pe.LEARNERS:
        p = pe.Personal(seed=1, learner=learner)
        for i in range(600):
            f = feats(p_ai=float(rng.random()), p_scam=float(rng.random()), peak_scam=float(rng.random()),
                      peak_ai_undisclosed=float(rng.random()), max_alert=int(rng.integers(0, 3)),
                      n_families=int(rng.integers(0, 4)), payment_cred=bool(rng.random() < .3), disclosed=bool(rng.random() < .4),
                      duration_s=float(rng.integers(5, 300)), promotable=bool(rng.random() < .5))
            p.learn(f, "not_scam" if i < 300 else "scam")            # all-quiet then all-loud: the worst swings
            a, r = p.shifts_for(f)
            assert pe.AMBER_RANGE[0] <= a <= pe.AMBER_RANGE[1] and pe.RED_RANGE[0] <= r <= pe.RED_RANGE[1]
            assert all(abs(w) <= 3.0 for w in p.w) and abs(p.b) <= 3.0


def test_fresh_state_has_zero_shift_and_changes_nothing():
    p = pe.Personal(seed=0)
    for f in (amber_disclosed(), feats(max_alert=2, peak_scam=0.9), feats(peak_scam=0.5, promotable=True)):
        assert p.shifts_for(f) == (0.0, 0.0) and p.alert_level(f) == f.max_alert
    assert p.explain()[0] == pe.EXPLAIN_LEARNING


# ---------------------------------------------------------------- protected cases
def test_red_is_never_suppressed_for_any_state_or_shift():
    for a in (-0.1, 0, 0.15, 9):
        for r in (-0.1, 0, 9):
            for prot in (False, True):
                assert pe.decide(2, 0.0, 0.0, prot, False, a, r) == 2


def test_alert_on_undisclosed_payment_or_credential_call_is_never_lowered():
    quiet = pe.Personal(seed=2)
    teach(quiet, amber_disclosed(0.6), "not_scam", 80)
    for fam_payment in (True, False):
        f = feats(p_scam=0.58, peak_scam=0.58, max_alert=1, payment_cred=fam_payment, n_families=1, disclosed=False, promotable=True)
        for a in (0.15, 0.1, 0.05):
            lvl = pe.decide(1, f.score, f.peak_scam, f.protected, f.promotable, a, 0.0)
            assert lvl >= 1 if fam_payment else lvl == 0               # protected keeps amber; the unprotected one is quieted
        assert quiet.alert_level(f) >= 1 if fam_payment else True
    # and the protected flag really requires "disclosed nothing"
    assert feats(payment_cred=True, disclosed=False).protected and not feats(payment_cred=True, disclosed=True).protected


def test_quieted_learner_still_lets_corroborated_red_through():
    p = pe.Personal(seed=2)
    teach(p, feats(p_scam=0.9, peak_scam=0.9, max_alert=2, payment_cred=True, n_families=2), "not_scam", 80)
    red = feats(p_scam=0.95, peak_scam=0.95, max_alert=2, payment_cred=True, n_families=2)
    assert p.alert_level(red) == 2


# ---------------------------------------------------------------- learning, determinism, serialisation
def test_learns_to_alert_less_for_disclosed_automated_calls_and_says_so():
    p = pe.Personal(seed=5)
    f = amber_disclosed(0.6)
    assert p.alert_level(f) == 1
    teach(p, f, "not_scam", 40)
    assert p.alert_level(f) == 0
    assert "Tell has learned to alert you slightly less for automated appointment calls that say they are automated." in p.explain()
    assert p.explain()[-1] == pe.EXPLAIN_ALWAYS


def test_learns_to_alert_sooner_when_user_reports_missed_scams():
    for learner in pe.LEARNERS:
        p = pe.Personal(seed=5, learner=learner)
        soft = feats(p_ai=0.2, p_scam=0.47, peak_scam=0.47, max_alert=0, n_families=2, promotable=True)
        assert p.alert_level(soft) == 0
        teach(p, soft, "scam", 40)
        assert p.alert_level(soft) == 1, learner


def test_ai_label_on_a_disclosed_call_carries_no_information():
    p = pe.Personal(seed=0)
    assert p.learn(amber_disclosed(), "ai") is False
    assert p.learn(feats(p_ai=0.7), "ai") is True
    assert p.learn(feats(), "nonsense") is False


def test_old_feedback_fades():
    p = pe.Personal(seed=0)
    f = amber_disclosed()
    teach(p, f, "not_scam", 30)
    w0, n0 = p.prior["disclosed_benign"]
    teach(p, feats(p_ai=0.1), "human", 200)                         # unrelated context; decay still applies
    w1, n1 = p.prior["disclosed_benign"]
    assert n1 == pytest.approx(n0 * pe.DECAY ** 200, abs=1e-9) and n1 < 0.01 * n0


def test_deterministic_given_a_seed_and_serialisable():
    def run(seed):
        p = pe.Personal(seed=seed)
        for i in range(60):
            teach(p, amber_disclosed(0.6 + 0.001 * i), "not_scam" if i % 3 else "scam", 1)
        return p
    a, b = run(11), run(11)
    assert a.to_json() == b.to_json()
    c = pe.Personal.from_json(a.to_json())
    assert c.to_json() == a.to_json()
    f = amber_disclosed()
    assert c.shifts_for(f) == a.shifts_for(f)
    with pytest.raises(ValueError):
        pe.Personal.from_json(json.dumps({"v": "other"}))


def test_corrupted_state_cannot_exceed_range():
    p = pe.Personal(seed=0)
    d = json.loads(p.to_json())
    d["w"], d["b"], d["chosen"] = [9.0] * 7, 9.0, {c: 99 for c in pe.CONTEXTS}
    d["prior"] = {c: [1e9, 1.0] for c in pe.CONTEXTS}
    q = pe.Personal.from_json(json.dumps(d))
    a, r = q.shifts_for(amber_disclosed())
    assert pe.AMBER_RANGE[0] <= a <= pe.AMBER_RANGE[1] and pe.RED_RANGE[0] <= r <= pe.RED_RANGE[1]


# ---------------------------------------------------------------- feedback intake
def test_sync_learns_each_record_once_and_inert_without_a_store(layer):
    fb = pe.FakeFeedback([{"id": f"r{i}", "label": "not_scam"} for i in range(6)])
    layer._fb = fb
    layer.set_enabled(True)
    trk = pe.CallTracker()
    for _ in range(4):
        trk.update(vd("scam", 0.6, 0.8, disclosed=True), "amber", "scam")
    layer.on_call_end(trk)                                          # syncs
    assert layer.status()["n_feedback"] == 6
    layer.sync(); layer.sync()
    assert layer.status()["n_feedback"] == 6                        # dedup by record id
    fb.records.append({"id": "r6", "label": "scam", "call_id": "unknown-id"})   # unknown call_id -> last finished call
    layer.sync()
    assert layer.status()["n_feedback"] == 7


def test_feedback_adapter_is_inert_until_the_real_module_exists():
    src = pe.feedback_adapter()
    assert src.recent(5) == [] or isinstance(src.recent(5), list)


# ---------------------------------------------------------------- opt-in, encryption at rest, wipe
def test_off_by_default_nothing_is_read_or_written(tmp_path, monkeypatch):
    monkeypatch.setenv("TELL_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("TELL_PERSONAL", raising=False)
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: (_ for _ in ()).throw(AssertionError("keychain touched")))
    lay = pe.PersonalLayer()
    assert lay.active() is False
    assert lay.on_tick(pe.CallTracker(), vd(), "none", "human") is None
    assert lay.set_enabled(True)["enabled"] is False                # env flag off: the toggle cannot enable it
    st = lay.status()
    assert st["enabled"] is False and st["n_feedback"] == 0 and st["explain"] == [pe.EXPLAIN_OFF]
    assert not (tmp_path / "d").exists()


def test_flag_on_but_user_not_opted_in_is_still_off(layer):
    assert layer.active() is False
    assert layer.on_tick(pe.CallTracker(), vd(), "none", "human") is None
    assert layer.status()["enabled"] is False


def test_state_is_encrypted_at_rest_and_wipe_removes_it(layer):
    layer._fb = pe.FakeFeedback([{"id": f"r{i}", "label": "not_scam"} for i in range(8)])
    layer.set_enabled(True)
    trk = pe.CallTracker()
    for _ in range(4):
        trk.update(vd("scam", 0.6, 0.8, disclosed=True), "amber", "scam")
    layer.on_call_end(trk)
    path = pe.state_path()
    raw = path.read_bytes()
    assert raw and b"beta" not in raw and b"prior" not in raw and b"disclosed_benign" not in raw and b'"n"' not in raw
    assert (path.stat().st_mode & 0o777) == 0o600
    plain = json.loads(ss._decrypt(KEY, raw.decode("ascii")))
    assert plain["n"] == 8 and plain["enabled"] is True and "transcript" not in json.dumps(plain)
    # a fresh layer (new process) restores the learned state from the encrypted file
    again = pe.PersonalLayer(seed=99)
    assert again.status()["n_feedback"] == 8 and again.status()["enabled"] is True
    assert layer.wipe() == {"wiped": True}
    assert not path.exists()
    assert pe.PersonalLayer().status()["n_feedback"] == 0 and layer.status()["enabled"] is False


def test_tampered_state_is_ignored_not_trusted(layer):
    layer.set_enabled(True)
    p = pe.state_path()
    p.write_bytes(p.read_bytes()[:-6] + b"AAAAAA")
    fresh = pe.PersonalLayer()
    assert fresh.status()["enabled"] is False and fresh.status()["n_feedback"] == 0


def test_unavailable_keychain_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("TELL_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TELL_PERSONAL", "1")

    def locked():
        raise ss.HistoryUnavailable("keychain locked")
    monkeypatch.setattr(ss, "keyring_key_provider", locked)
    lay = pe.PersonalLayer()
    st = lay.set_enabled(True)
    assert st["enabled"] is False and st["available"] is False and lay.active() is False


# ---------------------------------------------------------------- the stable view and live events are untouched
SEQ = ([vd("human")] * 5 + [vd("scam", 0.6, 0.8, ["urgency"], disclosed=True)] * 6 + [vd("scam", 0.9, 0.2, ["urgency"])] * 3
       + [vd("scam", 0.95, 0.2, ["urgency", "payment_rails"])] * 4)


def run_tracker():
    tr, out, pa = live.StableTracker(), [], []
    for i, d in enumerate(SEQ):
        out.append(json.dumps(tr.observe(d, max(0.0, 3.0 * (i + 1) - 10), 3.0 * (i + 1)), sort_keys=True))
        pa.append(tr.personal_alert)
    return out, pa


def test_stable_view_is_bit_identical_with_personal_off_and_on(layer, monkeypatch):
    monkeypatch.delenv("TELL_PERSONAL", raising=False)
    off, pa_off = run_tracker()
    assert set(pa_off) == {None}
    monkeypatch.setenv("TELL_PERSONAL", "1")
    monkeypatch.setattr(pe, "LAYER", layer)
    layer.set_enabled(True)
    p = layer._load()
    teach(p, amber_disclosed(0.6), "not_scam", 60)                  # a very quiet user
    teach(p, feats(p_ai=0.2, peak_scam=0.9, max_alert=2, n_families=2), "not_scam", 60)
    on, pa_on = run_tracker()
    assert on == off                                                # `stable` never changes
    assert set(pa_on) <= {"none", "amber", "red"} and None not in pa_on
    stable_alerts = [json.loads(s)["alert"] for s in on]
    assert all(pa == "red" for pa, sa in zip(pa_on, stable_alerts) if sa == "red")     # red never suppressed
    assert any(sa == "amber" and pa == "none" for pa, sa in zip(pa_on, stable_alerts))  # but a quiet user gets fewer ambers


def test_hub_event_has_no_personal_field_unless_active():
    hub = live.Hub()
    q = hub.subscribe()
    s = types.SimpleNamespace(id="x", closed=False, received_s=3.0)
    hub.sessions["x"] = s
    hub.on_tick(s, vd(), {"tier": "human", "state": "steady", "alert": "none", "since_s": 0, "reasons": []}, 1)
    ev = q.get_nowait()
    assert "personal_alert" not in ev and set(ev) == {"type", "tick", "elapsed_s", "verdict", "stable"}
    hub.on_tick(s, vd(), {"tier": "human", "state": "steady", "alert": "none", "since_s": 0, "reasons": []}, 2, "amber")
    assert q.get_nowait()["personal_alert"] == "amber"


# ---------------------------------------------------------------- HTTP contract
def test_http_contract_toggle_explain_wipe_and_guards(layer, monkeypatch):
    monkeypatch.setattr(pe, "LAYER", layer)
    c = TestClient(app, headers=AUTH)
    r = c.get("/personal", headers=ORIGIN)
    assert r.status_code == 200 and set(r.json()) >= {"enabled", "n_feedback", "sensitivity", "explain"} and r.json()["enabled"] is False
    r = c.post("/personal", json={"enabled": True}, headers=ORIGIN)
    assert r.json()["enabled"] is True and r.json()["n_feedback"] == 0
    assert r.json()["sensitivity"]["amber_range"] == list(pe.AMBER_RANGE) and r.json()["explain"][0] == pe.EXPLAIN_LEARNING
    assert c.post("/personal", json={"enabled": "maybe"}, headers=ORIGIN).status_code == 422
    assert c.delete("/personal", headers=ORIGIN).json() == {"wiped": True}
    assert c.get("/personal", headers=ORIGIN).json()["enabled"] is False
    # guards: foreign Origin, rebinding Host, non-loopback client
    assert c.get("/personal", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/personal", headers={"Host": "evil.example"}).status_code == 400
    far = TestClient(app, headers=AUTH, client=("203.0.113.9", 5000))
    for call in (lambda: far.get("/personal", headers=ORIGIN), lambda: far.post("/personal", json={"enabled": True}, headers=ORIGIN),
                 lambda: far.delete("/personal", headers=ORIGIN)):
        assert call().status_code == 403


def test_explain_wording_is_fixed_and_never_contains_call_content(layer):
    p = pe.Personal(seed=1)
    teach(p, amber_disclosed(), "not_scam", 40)
    teach(p, feats(p_scam=0.47, peak_scam=0.47, n_families=2, promotable=True), "scam", 40)
    allowed = {pe.EXPLAIN_ALWAYS, pe.EXPLAIN_LEARNING, pe.EXPLAIN_RED} | {pe.EXPLAIN_LESS.format(t) for t in pe.EXPLAIN_TOPIC.values()} \
        | {pe.EXPLAIN_SOONER.format(t) for t in pe.EXPLAIN_TOPIC.values()}
    assert set(p.explain()) <= allowed
    for s in p.explain():
        assert "safe" not in s.lower() and "illegal" not in s.lower()
