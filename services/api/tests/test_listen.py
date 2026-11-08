"""tools/macos/listen.py: arg parsing, loopback refusal, watch state machine with a fake `tap_audio --list`. No audio."""
import importlib.util
import stat
from pathlib import Path

import pytest

P = Path(__file__).resolve().parents[3] / "tools" / "macos" / "listen.py"
spec = importlib.util.spec_from_file_location("listen_tool", P)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


def test_args_modes_are_exclusive_and_required():
    with pytest.raises(SystemExit):
        L.parse_args([])
    with pytest.raises(SystemExit):
        L.parse_args(["--now", "--watch"])
    a = L.parse_args(["--watch"])
    assert a.watch and a.call_process == list(L.DEFAULT_CALL_PROCESSES) and a.sound is False and a.silence_s == 90.0
    a = L.parse_args(["--now", "--call-process", "Foo", "--call-process", "Bar", "--sound", "--i-understand"])
    assert a.call_process == ["Foo", "Bar"] and a.sound and a.i_understand
    assert L.parse_args(["--file", "x.wav"]).file == "x.wav"
    with pytest.raises(SystemExit):
        L.parse_args(["--now", "--speed", "0"])


def test_defaults_do_not_include_music_or_browsers():
    low = " ".join(L.DEFAULT_CALL_PROCESSES).lower()
    for bad in ("music", "spotify", "chrome", "safari", "firefox", "arc", "youtube"):
        assert bad not in low
    assert {"FaceTime", "zoom.us", "callservicesd", "avconferenced", "WhatsApp", "Microsoft Teams", "Phone"} <= set(
        L.DEFAULT_CALL_PROCESSES)


@pytest.mark.parametrize("url,ok", [("http://127.0.0.1:8000", True), ("http://localhost:8000", True),
                                    ("http://[::1]:8000", True), ("http://192.168.1.5:8000", False),
                                    ("https://example.com", False), ("http://127.0.0.1.evil.com", False),
                                    ("ftp://127.0.0.1", False), ("", False)])
def test_loopback_check(url, ok):
    assert L.is_loopback_url(url) is ok


def test_main_refuses_non_loopback_url(capsys):
    assert L.main(["--file", __file__, "--url", "http://10.0.0.5:8000", "--i-understand"]) == 2
    assert "loopback" in capsys.readouterr().err


def test_consent_required_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(L.sys.stdin, "isatty", lambda: False)
    assert L.consent(L.parse_args(["--now"])) is False
    out = capsys.readouterr().out
    assert "analysed in memory" in out and "nothing is recorded" in out
    assert L.consent(L.parse_args(["--now", "--i-understand"])) is True
    monkeypatch.setattr(L.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert L.consent(L.parse_args(["--now"])) is True
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert L.consent(L.parse_args(["--now"])) is False


def test_parse_list_and_match():
    text = "Spotify\tcom.spotify.client\tpid 1\nFaceTime\tcom.apple.FaceTime\tpid 2\nGoogle Chrome\tcom.google.Chrome\tpid 3\n"
    listing = L.parse_list(text)
    assert listing[1] == ("FaceTime", "com.apple.FaceTime")
    assert L.match_call(listing, list(L.DEFAULT_CALL_PROCESSES)) == "FaceTime"
    assert L.match_call([listing[0], listing[2]], list(L.DEFAULT_CALL_PROCESSES)) is None      # music + browser: never
    assert L.match_call(listing, ["com.apple.facetime"]) == "FaceTime"
    assert L.match_call([("iPhone Mirroring", "x")], ["Phone"]) is None                         # exact match only


def test_watch_state_machine():
    w = L.WatchState(end_polls=3)
    assert w.update(None) is None
    assert w.update("FaceTime") == "arm" and w.armed == "FaceTime"
    assert w.update("FaceTime") is None
    assert w.update(None) is None and w.update(None) is None
    assert w.update("FaceTime") is None                      # a short silent gap does not end the call
    assert [w.update(None) for _ in range(3)] == [None, None, "stop"]
    assert w.armed is None
    assert w.update("zoom.us") == "arm"


def test_watch_with_fake_tap_list(tmp_path):
    state = tmp_path / "state"
    tap = tmp_path / "tap_audio"
    tap.write_text(f'#!/bin/sh\n[ "$1" = "--list" ] && cat {state}\n')
    tap.chmod(tap.stat().st_mode | stat.S_IEXEC)
    w = L.WatchState(end_polls=2)
    calls = ["Spotify\tcom.spotify.client\tpid 9\n", "Spotify\tcom.spotify.client\tpid 9\nzoom.us\tus.zoom.xos\tpid 4\n",
             "zoom.us\tus.zoom.xos\tpid 4\n", "", ""]
    seen = []
    for c in calls:
        state.write_text(c)
        seen.append(w.update(L.match_call(L.list_producing(str(tap)), L.parse_args(["--watch"]).call_process)))
    assert seen == [None, "arm", None, None, "stop"]
    assert L.list_producing(str(tmp_path / "missing")) == []


def test_notification_only_on_change_to_amber_or_red():
    n = L.notification_for
    assert n("none", "amber") == L.NOTIFY_TEXT["amber"]
    assert n("amber", "red") == L.NOTIFY_TEXT["red"]
    assert n("none", "none") is None and n("amber", "amber") is None and n("red", "none") is None
    assert n("red", "amber") == L.NOTIFY_TEXT["amber"]
    for t in L.NOTIFY_TEXT.values():                         # fixed wording, safe inside an AppleScript string
        assert '"' not in t and "\\" not in t


def test_silence_peak_and_status_line():
    assert L.peak(b"\x00\x00" * 100) == 0
    assert L.peak((1000).to_bytes(2, "little", signed=True) * 4) == 1000
    m = {"t": 12.0, "tier": "human", "p_scam": 0.1, "p_ai": 0.2,
         "stable": {"tier": "human", "state": "steady", "alert": "none"}}
    line = L.status_line(m, 1.234)
    assert line.startswith("LISTENING") and "lat=1.2s" in line and "alert=none" in line


# ---- opt-in labelled capture ----------------------------------------------------------------------------------
import json  # noqa: E402
import wave  # noqa: E402

FULL = ["--now", "--save-labeled", "OUT", "--label", "ai", "--speaker", "Sam", "--consent-note", "Sam agreed by text"]


def test_capture_is_off_by_default():
    a = L.parse_args(["--now"])
    assert a.save_labeled is None and a.label is None and a.speaker is None and a.consent_note is None
    assert L.save_error(a) is None


@pytest.mark.parametrize("drop", ["--save-labeled", "--label", "--speaker", "--consent-note"])
def test_refuses_without_each_required_flag(drop, tmp_path):
    argv = [x if x != "OUT" else str(tmp_path) for x in FULL]
    i = argv.index(drop)
    del argv[i:i + 2]
    err = L.save_error(L.parse_args(argv), mount_text="")
    assert err and drop in err


def test_refuses_blank_consent_and_bad_label(tmp_path):
    argv = [x if x != "OUT" else str(tmp_path) for x in FULL]
    argv[argv.index("Sam agreed by text")] = "   "
    assert "--consent-note" in L.save_error(L.parse_args(argv), mount_text="")
    with pytest.raises(SystemExit):
        L.parse_args(["--now", "--label", "robot"])


def test_main_refuses_before_listening(tmp_path, capsys):
    tap = tmp_path / "tap"
    tap.write_text("x")
    rc = L.main(["--now", "--tap", str(tap), "--label", "ai", "--i-understand"])
    assert rc == 2 and "--save-labeled" in capsys.readouterr().err


def test_network_mount_refused(tmp_path):
    mounts = f"//u@srv/share on {tmp_path.resolve()} (smbfs, nodev)\n/dev/disk3 on / (apfs, local)\n"
    argv = [x if x != "OUT" else str(tmp_path / "d") for x in FULL]
    assert "network" in L.save_error(L.parse_args(argv), mount_text=mounts)
    assert L.save_error(L.parse_args(argv), mount_text="/dev/disk3 on / (apfs, local)\n") is None


def test_saver_writes_wav_and_sidecar_0600(tmp_path):
    a = L.parse_args([x if x != "OUT" else str(tmp_path) for x in FULL])
    sv = L.LabeledSaver(a, "tap", now=L.datetime.datetime(2026, 11, 7, 12, 0, 1))
    sv.write(b"\x01\x00" * 16000)
    sv.tick({"t": 3.0, "window": [0, 3], "tier": "human", "p_ai": 0.3, "p_scam": 0.0, "stable": {"x": 1}})
    sv.close()
    wav, js = tmp_path / "ai" / "20261107T120001.wav", tmp_path / "ai" / "20261107T120001.json"
    with wave.open(str(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (16000, 1, 16000)
    side = json.loads(js.read_text())
    assert side["label"] == "ai" and side["speaker"] == "Sam" and side["consent_note"] == "Sam agreed by text"
    assert side["source"] == "tap" and side["ticks"][0]["p_ai"] == 0.3 and "stable" not in side["ticks"][0]
    assert stat.S_IMODE(wav.stat().st_mode) == 0o600 and stat.S_IMODE(js.stat().st_mode) == 0o600


def test_banner_and_status_line_show_saving(capsys):
    L.banner(True, "tap", saving=True)
    assert "SAVING AUDIO TO DISK" in capsys.readouterr().out
    assert "SAVING AUDIO TO DISK" in L.status_line({"t": 1}, None, saving=True)
    assert "SAVING" not in L.status_line({"t": 1}, None)
    L.banner(True, "tap")
    assert "SAVING" not in capsys.readouterr().out


def test_score_saved_loopback_only_and_table(tmp_path, capsys):
    spec2 = importlib.util.spec_from_file_location("score_saved", P.parents[1] / "score_saved.py")
    S = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(S)
    assert S.main([str(tmp_path), "--url", "http://10.0.0.5:8000"]) == 2
    (tmp_path / "ai").mkdir()
    (tmp_path / "ai" / "a.wav").write_bytes(b"RIFF")

    def fake(base, p):
        return {"p_ai": 0.3, "p_scam": 0.0, "tier": "human", "quadrant": {"combo_label": "Human voice, no scam pattern heard."}}

    assert S.main([str(tmp_path)], poster=fake) == 0
    out = capsys.readouterr().out
    assert "tier=human" in out and "sanity check" in out and "mean p_ai" in out
