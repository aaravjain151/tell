import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_web_samples_reproduce_expected_tiers():
    """apps/web/build_samples.py --check exits non-zero if any inline sample's tier would change."""
    r = subprocess.run([sys.executable, str(ROOT / "apps/web/build_samples.py"), "--check"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "caller_audio" not in r.stderr
