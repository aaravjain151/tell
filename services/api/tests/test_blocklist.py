"""Block list + feedback: normalisation, dedupe/reports, encryption at rest, limits, guards, no number in logs/verdicts."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from doublespeak import blocklist as bl, feedback as fb, main, secure_store as ss

KEY = bytes(range(32))
NUM = "+14155550123"
RAW_DIGITS = "4155550123"
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.delenv("DOUBLESPEAK_DEFAULT_REGION", raising=False)
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: KEY)
    bl.reset_rate_limits()
    yield tmp_path / "d"
    bl.reset_rate_limits()


@pytest.mark.parametrize("raw,want", [
    ("(415) 555-0123", NUM), ("415.555.0123", NUM), ("1 415 555 0123", NUM), ("+1 (415) 555-0123", NUM),
    ("415/555/0123", NUM), ("001 415 555 0123", NUM), ("+44 20 7946 0958", "+442079460958"),
    ("0044 20 7946 0958", "+442079460958"), ("+91 98765 43210", "+919876543210"), ("  +14155550123  ", NUM),
    ("415-555-012", None), ("155-555-0123", None), ("011-555-0123", None), ("1-800-FLOWERS", None),
    ("+0123456789", None), ("+123", None), ("+1234567890123456", None), ("", None), ("   ", None),
    ("++14155550123", None), ("4155550123 ext 5", None), ("911", None), ("\x00415", None), ("x" * 500, None),
    ("+1415555012٣", None), (None, None), (4155550123, None), (["+14155550123"], None), ({"a": 1}, None),
    (True, None), (b"+14155550123", None),
])
def test_normalise_table(raw, want):
    assert bl.normalise(raw) == want


def test_normalise_regions():
    assert bl.normalise("020 7946 0958", "GB") == "+442079460958"
    assert bl.normalise("09876543210", "IN") == "+919876543210"
    assert bl.normalise("0412 345 678", "AU") == "+61412345678"
    assert bl.normalise("4155550123", "DE") is None          # unknown region: refuse, never guess


def test_default_region_env(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_DEFAULT_REGION", "GB")
    assert bl.normalise("020 7946 0958") == "+442079460958"
    assert bl.normalise("4155550123") is None


def test_add_list_repeat_check_delete():
    r = client.post("/blocklist", json={"number": "(415) 555-0123", "label": "Robocall", "reason": "warranty"})
    assert r.status_code == 200
    item = r.json()
    assert set(item) == {"id", "number", "label", "reason", "added_at", "reports"}
    assert item["number"] == NUM and item["reports"] == 1 and item["label"] == "Robocall"
    again = client.post("/blocklist", json={"number": "+1 415 555 0123"}).json()
    assert again["id"] == item["id"] and again["reports"] == 2 and again["label"] == "Robocall"
    items = client.get("/blocklist").json()["items"]
    assert len(items) == 1 and items[0]["reports"] == 2
    assert client.post("/blocklist/check", json={"number": "415-555-0123"}).json()["blocked"] is True
    assert client.post("/blocklist/check", json={"number": "415-555-9999"}).json() == {"blocked": False}
    assert client.post("/blocklist/check", json={"number": "415-555-0123"}).json()["item"]["id"] == item["id"]
    assert client.delete(f"/blocklist/{item['id']}").json() == {"ok": True}
    assert client.delete(f"/blocklist/{item['id']}").status_code == 404
    assert client.get("/blocklist").json() == {"items": []}
    assert client.post("/blocklist/check", json={"number": NUM}).json() == {"blocked": False}


def test_bad_input_rejected_without_echo():
    for body in ({"number": "junk-9999"}, {"number": 4155550123}, {"number": None}, {}, {"number": NUM, "label": 5},
                 {"number": NUM, "label": "x" * 65}, {"number": NUM, "reason": "y" * 201}, [NUM]):
        r = client.post("/blocklist", json=body)
        assert r.status_code in (400, 422), body
        assert "415" not in r.text and "junk" not in r.text
    assert client.post("/blocklist", content=b"{not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.delete("/blocklist/..%2f..").status_code in (404, 405)
    assert client.get("/blocklist").json() == {"items": []}


def test_label_control_chars_stripped():
    it = client.post("/blocklist", json={"number": NUM, "label": "a\x00b\n\x1bc"}).json()
    assert it["label"] == "abc"


def test_oversized_body_413():
    r = client.post("/blocklist", content=b'{"number":"' + b"1" * 20000 + b'"}', headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert client.post("/feedback", content=b"x" * 20000, headers={"content-type": "application/json"}).status_code == 413


def test_list_cap(monkeypatch):
    monkeypatch.setattr(bl, "MAX_ITEMS", 2)
    assert client.post("/blocklist", json={"number": "415-555-0101"}).status_code == 200
    assert client.post("/blocklist", json={"number": "415-555-0102"}).status_code == 200
    assert client.post("/blocklist", json={"number": "415-555-0103"}).status_code == 409
    assert client.post("/blocklist", json={"number": "415-555-0102"}).json()["reports"] == 2   # repeat still fine


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(bl, "WRITES_PER_MIN", 3)
    codes = [client.post("/blocklist", json={"number": NUM}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert client.post("/blocklist", json={"number": NUM}).headers["retry-after"]


def test_encrypted_at_rest(store):
    client.post("/blocklist", json={"number": NUM, "label": "SENTINEL-LABEL-91", "reason": "SENTINEL-REASON-77"})
    client.post("/feedback", json={"label": "scam", "tick": 3})
    files = list(store.iterdir())
    assert {f.name for f in files} == {"blocklist.enc", "feedback.enc"}
    for f in files:
        raw = f.read_bytes()
        for needle in (NUM, NUM[1:], RAW_DIGITS, "5550123", "SENTINEL", b"scam".decode(), "415"):
            assert needle.encode() not in raw, (f.name, needle)
        assert (f.stat().st_mode & 0o777) == 0o600
    # and it does decrypt with the key
    doc = json.loads(ss._decrypt(KEY, (store / "blocklist.enc").read_text()))
    assert doc["items"][0]["number"] == NUM


def test_wrong_key_or_tamper_is_unavailable_not_leaky(store, monkeypatch):
    client.post("/blocklist", json={"number": NUM})
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: bytes(32))
    r = client.get("/blocklist")
    assert r.status_code == 503 and "415" not in r.text
    assert client.post("/blocklist", json={"number": NUM}).status_code == 503   # never overwrites what it cannot read


def test_keychain_unavailable_503(monkeypatch):
    def boom():
        raise ss.HistoryUnavailable("keychain unavailable (X)")
    monkeypatch.setattr(ss, "keyring_key_provider", boom)
    assert client.post("/blocklist", json={"number": NUM}).status_code == 503
    assert client.post("/feedback", json={"label": "scam"}).status_code == 503


def test_export_calldirectory_sorted_deduped():
    for n in ("+442079460958", "415-555-0123", "(212) 555-0100", "+1 415 555 0123", "+919876543210"):
        client.post("/blocklist", json={"number": n})
    r = client.get("/blocklist/export?format=calldirectory")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    nums = [int(x) for x in r.text.split()]
    assert nums == sorted(set(nums)) == [12125550100, 14155550123, 442079460958, 919876543210]
    assert client.get("/blocklist/export").text == r.text         # default format
    assert client.get("/blocklist/export?format=xml").status_code == 400


def test_export_empty_and_csv():
    assert client.get("/blocklist/export?format=calldirectory").text == ""
    client.post("/blocklist", json={"number": NUM, "label": "=HYPERLINK(1)", "reason": 'say "hi", ok'})
    t = client.get("/blocklist/export?format=csv")
    assert t.headers["content-type"].startswith("text/csv")
    lines = t.text.splitlines()
    assert lines[0] == "number,label,reason,added_at,reports"
    assert lines[1].startswith(NUM + ",'=HYPERLINK(1),")
    assert '"say ""hi"", ok"' in lines[1]


def test_guards():
    assert client.get("/blocklist", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/blocklist", json={"number": NUM}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/feedback", json={"label": "scam"}, headers={"Origin": "null"}).status_code == 403
    assert client.get("/blocklist", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/blocklist/export", headers={"Origin": "https://evil.example"}).status_code == 403
    ok = client.get("/blocklist", headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert client.get("/blocklist").json() == {"items": []}      # the refused writes stored nothing


def test_numbers_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/blocklist", json={"number": "(415) 555-0123", "label": "x"})
    client.post("/blocklist", json={"number": "415-555-0123"})
    client.post("/blocklist/check", json={"number": NUM})
    client.get("/blocklist"); client.get("/blocklist/export")
    client.post("/blocklist", json={"number": "bad 415 555 0123 number!"})
    client.post("/blocklist", content=b'{"number": "+14155550123"', headers={"content-type": "application/json"})
    client.post("/feedback", json={"label": "scam", "call_id": "abc"})
    out = "\n".join(r.getMessage() + str(r.args) for r in caplog.records)
    assert "5550123" not in out and "415" not in out


def test_numbers_not_in_logs_on_corrupt_file(store, caplog):
    client.post("/blocklist", json={"number": NUM})
    (store / "blocklist.enc").write_text("AAAA:BBBB\n")
    caplog.set_level(logging.DEBUG)
    assert client.get("/blocklist").status_code == 503
    assert "5550123" not in "\n".join(r.getMessage() for r in caplog.records)


def test_numbers_never_in_verdict_or_egress():
    from doublespeak import privacy
    client.post("/blocklist", json={"number": NUM})
    v = client.post("/analyze", data={"transcript": "hello this is a call from 415 555 0123 about your car warranty"})
    assert v.status_code == 200
    blob = json.dumps(client.get("/health").json()) + json.dumps(privacy.report())
    assert "5550123" not in blob and NUM not in blob
    for k in ("egress", "signature"):
        assert NUM[1:] not in json.dumps(v.json()[k])


def test_panic_wipes_lists(store):
    client.post("/blocklist", json={"number": NUM})
    client.post("/feedback", json={"label": "ai"})
    assert client.post("/panic").status_code == 200
    assert list(store.iterdir()) == []
    assert client.get("/blocklist").json() == {"items": []}
    assert fb.recent(5) == []


def test_feedback_roundtrip_and_validation():
    assert client.post("/feedback", json={"call_id": "call-1", "label": "scam", "tick": 4}).json() == {"ok": True}
    assert client.post("/feedback", json={"label": "human"}).json() == {"ok": True}
    assert client.post("/feedback", json={"label": "not_scam"}).json() == {"ok": True}
    rec = fb.recent(10)
    assert [r["label"] for r in rec] == ["not_scam", "human", "scam"]           # newest first
    assert set(rec[0]) == {"label", "tick", "ts"} and rec[2]["tick"] == 4
    assert len(rec[0]["ts"]) == len("2026-11-07T20+00:00") and rec[0]["ts"][13:16] == "+00"   # hour precision only
    assert fb.recent(1) == rec[:1] and fb.recent(0) == []
    assert fb.counters() == {"scam": 1, "not_scam": 1, "ai": 0, "human": 1}
    for bad in ({"label": "spam"}, {"label": 1}, {}, {"label": "scam", "tick": -1}, {"label": "scam", "tick": "3"},
                {"label": "scam", "tick": True}, {"label": "scam", "call_id": "../etc"}, {"label": "scam", "call_id": 5}):
        assert client.post("/feedback", json=bad).status_code == 422, bad


def test_feedback_stores_no_call_id(store):
    client.post("/feedback", json={"call_id": "CALLID-SENTINEL", "label": "scam"})
    doc = ss._decrypt(KEY, (store / "feedback.enc").read_text()).decode()
    assert "CALLID" not in doc


def test_feedback_cap(monkeypatch):
    monkeypatch.setattr(fb, "KEEP", 3)
    for _ in range(5):
        fb.record("scam")
    assert len(fb.recent(100)) == 3 and fb.counters()["scam"] == 5


def test_recent_safe_without_keychain(monkeypatch):
    def boom():
        raise ss.HistoryUnavailable("x")
    fb.record("scam")
    monkeypatch.setattr(ss, "keyring_key_provider", boom)
    assert fb.recent(5) == []
