"""Static checks for apps/ios: privacy posture of the iPhone app (no network permission beyond the loopback server, no
analytics or third-party SDK, no remote code), and that the Mac bridge and the app agree on the protocol."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IOS = ROOT / "apps" / "ios"


def _sources() -> list[Path]:
    return [p for p in IOS.rglob("*") if p.is_file() and p.suffix in {".swift", ".yml"}
            and "xcodeproj" not in p.parts]


def test_project_declares_only_microphone_and_audio_background():
    y = (IOS / "project.yml").read_text()
    assert "NSMicrophoneUsageDescription" in y and "UIBackgroundModes: [audio]" in y
    assert 'DEVELOPMENT_TEAM: ""' in y                       # no one's team id is committed
    for bad in ("NSAppTransportSecurity", "NSAllowsArbitraryLoads", "NSLocalNetworkUsageDescription", "NSBonjourServices",
                "NSLocationWhenInUseUsageDescription", "NSContactsUsageDescription", "NSCameraUsageDescription",
                "NSUserTrackingUsageDescription", "UIBackgroundModes: [audio, fetch", "remote-notification", "voip"):
        assert bad not in y, bad


def test_no_outbound_networking_or_analytics_or_third_party_sdk():
    src = "\n".join(p.read_text() for p in _sources())
    for bad in ("URLSession", "URLRequest", "NWConnection(host", "NWConnection(to", "NWBrowser", "WKWebView", "CFNetwork",
                "Firebase", "Crashlytics", "Sentry", "Amplitude", "Mixpanel", "Segment", "AppsFlyer", "Adjust", "Datadog",
                "GoogleAnalytics", "Bugsnag", "https://", "http://"):
        assert bad not in src, bad
    assert not (IOS / "Package.swift").exists() and not (IOS / "Podfile").exists() and not (IOS / "Cartfile").exists()
    assert "packages:" not in (IOS / "project.yml").read_text()


def test_server_is_loopback_only_and_requires_the_token_and_refuses_browsers():
    s = (IOS / "Doublespeak" / "Net" / "LoopbackServer.swift").read_text()
    assert "requiredInterfaceType = .loopback" in s
    assert ".ipv4(.loopback)" in s and ".ipv6(.loopback)" in s
    assert "PairingToken.matches" in s
    assert '"origin"' in s                                    # a web page cannot talk to it
    assert "guard client == nil" in s                         # one client only


def test_debug_only_helpers_are_compiled_out_of_release():
    for f in ("Audio/DebugWavFeeder.swift", "Session/DebugDemo.swift"):
        t = (IOS / "Doublespeak" / f).read_text()
        assert t.lstrip().startswith("#if DEBUG") and t.rstrip().endswith("#endif"), f
    for f in ("Core/Protocol.swift", "Session/ListenController.swift"):
        t = (IOS / "Doublespeak" / f).read_text()
        for m in re.finditer(r"-DS[A-Za-z]+", t):
            before = t[: m.start()]
            assert before.rfind("#if DEBUG") > before.rfind("#endif"), (f, m.group(0))


def test_consent_wording_is_the_fixed_text_and_bridge_port_matches():
    c = (IOS / "Doublespeak" / "Session" / "ListenController.swift").read_text()
    assert ("Doublespeak listens to this call through your microphone on your phone and sends the audio only to your own "
            "computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it.") in c
    assert "8765" in (IOS / "Doublespeak" / "Core" / "Protocol.swift").read_text()
    assert "PHONE_PORT = 8765" in (ROOT / "tools" / "ios" / "bridge.py").read_text()


def test_call_state_is_honest_callkit_only_and_no_text_implies_hearing_a_call_on_this_iphone():
    obs = (IOS / "Doublespeak" / "Session" / "CallObserver.swift").read_text()
    assert "CXCallObserver" in obs and "CXCallController" not in obs and "CXProvider" not in obs   # state only, no call control
    ui = "\n".join(p.read_text() for p in (IOS / "Doublespeak" / "UI").glob("*.swift"))
    assert "speakerphone" not in ui.lower()                    # the supported cases are another device or a recording
    assert "iOS does not let apps listen during a call" in obs
    assert "Calls on Other Devices" in obs
