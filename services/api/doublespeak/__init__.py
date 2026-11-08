"""DEPRECATED compatibility shim: the package is now ``tell`` (D-013, the product is called Tell again).

``import doublespeak.X`` returns the very same module object as ``import tell.X`` (no copy, so monkeypatching
either name patches both), and ``uvicorn doublespeak.main:app`` still starts the real app. New code, commands and
docs use ``tell``. Delete this package once nothing launches ``doublespeak.main:app`` any more.

No network, process or I/O code lives here (``tests/test_import_scan.py`` scans this file too).
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

import tell as _tell

_NEW = "tell"
warnings.warn("the 'doublespeak' package is deprecated; import 'tell' instead (D-013)", DeprecationWarning, stacklevel=2)


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves doublespeak.<sub> to the already-importable tell.<sub> and registers it under both names."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(__name__ + "."):
            new = _NEW + fullname[len(__name__):]
            if importlib.util.find_spec(new) is None:
                return None
            return importlib.util.spec_from_loader(fullname, self, is_package=False)
        return None

    _real_specs: dict[str, object] = {}

    def create_module(self, spec):
        mod = importlib.import_module(_NEW + spec.name[len(__name__):])
        self._real_specs[mod.__name__] = mod.__spec__
        return mod

    def exec_module(self, module):
        # importlib stamped the alias spec onto the shared module object; put the real one back
        real = self._real_specs.get(module.__name__)
        if real is not None:
            module.__spec__ = real


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())

# `from doublespeak import privacy` looks the name up on this package first
def __getattr__(name: str):
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError:
        if hasattr(_tell, name):
            return getattr(_tell, name)
        raise AttributeError(name) from None
