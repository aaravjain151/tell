"""Offline checks for apps/android (the Android PWA / Capacitor shell). The logic tests are node tests; this file runs them
and checks the native manifest. No device, no network."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "android"
NATIVE = APP / "native" / "android" / "app" / "src" / "main"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_android_node_tests():
    r = subprocess.run(["node", "--test", str(APP / "tests" / "android.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]


def test_native_manifest_permissions_and_loopback_only_cleartext():
    m = (NATIVE / "AndroidManifest.xml").read_text()
    for p in ("RECORD_AUDIO", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_MICROPHONE", "POST_NOTIFICATIONS"):
        assert f"android.permission.{p}" in m
    assert 'android:foregroundServiceType="microphone"' in m
    assert 'android:usesCleartextTraffic="false"' in m
    nsc = (NATIVE / "res" / "xml" / "network_security_config.xml").read_text()
    assert '<base-config cleartextTrafficPermitted="false"' in nsc
    domains = re.findall(r"<domain[^>]*>([^<]+)</domain>", nsc)
    assert sorted(domains) == ["127.0.0.1", "localhost"]


def test_native_auto_listen_permissions_and_components():
    """Auto-listen (docs/android/ANDROID.md): READ_PHONE_STATE for the call state only, a microphone-type service,
    a PHONE_STATE receiver that is disabled until the user opts in, and none of the permissions Play forbids for this."""
    m = (NATIVE / "AndroidManifest.xml").read_text()
    assert "android.permission.READ_PHONE_STATE" in m
    assert re.search(r'android:name="\.CallListenService"\s+android:exported="false"\s+android:foregroundServiceType="microphone"', m)
    assert re.search(r'android:name="\.CallStateReceiver"\s+android:enabled="false"', m)
    assert 'android:name=".TellApp"' in m
    for banned in ("SYSTEM_ALERT_WINDOW", "MODIFY_PHONE_STATE", "READ_CALL_LOG", "CAPTURE_AUDIO_OUTPUT", "PROCESS_OUTGOING_CALLS",
                   "BIND_ACCESSIBILITY_SERVICE", "USE_FULL_SCREEN_INTENT", "ANSWER_PHONE_CALLS"):
        assert banned not in m, banned


def test_native_config_is_bundled_shell_not_remote():
    cfg = (APP / "native" / "capacitor.config.json").read_text()
    assert '"appId": "dev.doublespeak.app"' in cfg
    assert '"url"' not in cfg          # never a remote server.url
