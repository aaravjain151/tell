"""D-013: the package is `tell`; the deprecated `doublespeak` name still imports the very same modules."""
import importlib
import subprocess
import sys
from pathlib import Path

import tell.main
import tell.privacy
import tell.signals.pella

API = Path(__file__).resolve().parents[1]


def test_old_names_are_the_same_module_objects():
    import doublespeak.main
    from doublespeak import privacy
    from doublespeak.signals import pella
    assert doublespeak.main is tell.main and privacy is tell.privacy and pella is tell.signals.pella
    assert doublespeak.main.app is tell.main.app


def test_alias_does_not_corrupt_the_real_spec():
    importlib.import_module("doublespeak.privacy")
    assert tell.privacy.__spec__.name == "tell.privacy"
    importlib.reload(tell.privacy)


def test_unknown_submodule_still_fails():
    import pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("doublespeak.no_such_module")


def test_old_uvicorn_target_resolves_in_a_fresh_interpreter():
    """`uvicorn doublespeak.main:app` (old Makefiles, an installed menu-bar app) imports this way."""
    code = ("import warnings; warnings.simplefilter('error', DeprecationWarning)\n"
            "try:\n    import doublespeak\nexcept DeprecationWarning:\n    print('warned')\n"
            "warnings.simplefilter('ignore')\nimport doublespeak.main as m, tell.main as t\n"
            "print(m.app is t.app, m.app.title)")
    out = subprocess.run([sys.executable, "-c", code], cwd=API, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["warned", "True", "Tell"]
