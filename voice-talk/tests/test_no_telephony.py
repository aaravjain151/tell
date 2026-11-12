"""Safeguard: no module may import telephony / virtual-audio / audio-device libraries."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED = {
    "twilio", "vonage", "plivo", "telnyx", "pjsua", "pjsua2", "sipsimple", "pyVoIP", "aiosip", "aiortc",
    "livekit", "daily", "pyaudio", "sounddevice", "soundcard", "pyvirtualmic", "pyvirtualcam", "pulsectl",
    "jack", "simpleaudio", "pygame", "playsound", "vb_cable", "pyloopback",
}


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            yield n.module.split(".")[0]


def test_no_banned_imports():
    files = [*ROOT.glob("*.py"), *(ROOT / "voice_talk").glob("*.py"), *(ROOT / "tools").glob("*.py")]
    assert len(files) >= 8
    bad = {f.name: sorted(set(imports(f)) & BANNED) for f in files if set(imports(f)) & BANNED}
    assert not bad, bad


def test_no_outbound_http_clients_except_openai_to_loopback():
    for f in (ROOT / "voice_talk").glob("*.py"):
        assert not ({"requests", "urllib3", "httpx", "aiohttp", "websockets"} & set(imports(f))), f.name


def test_page_has_no_external_resources():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    import re
    assert not re.search(r"(src|href)\s*=\s*[\"']https?://", html)
    assert "@import" not in html and "googleapis" not in html
