"""AST scan: every .py under tell/ (recursive, no fixed file list) is checked for anything that can
open a network connection or spawn a process. Files that legitimately do so are in ALLOWLIST with a reason.
The scan fails on a new file or a new banned use. It is static: native libs and subprocess children are
covered only by the runtime guard (test_network_guard.py) and the OS-level monitor.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BANNED_MODULES = {
    "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "websockets",
    "ftplib", "smtplib", "telnetlib", "xmlrpc", "poplib", "imaplib", "nntplib", "socketserver",
    "anthropic", "ctypes", "subprocess",
}
BANNED_ASYNCIO = {"open_connection", "open_unix_connection", "create_connection", "start_server", "getaddrinfo", "create_subprocess_exec", "create_subprocess_shell"}
BANNED_OS_PREFIXES = ("system", "popen", "exec", "spawn", "posix_spawn", "fork")
DYNAMIC_IMPORTERS = {"__import__", "import_module"}


def _root(name: str) -> str:
    return name.split(".")[0]


def _os_banned(attr: str) -> bool:
    return attr.startswith(BANNED_OS_PREFIXES)


def scan_source(src: str) -> set[str]:
    """Return findings: a banned module name (e.g. 'socket', 'urllib'), 'os.system'/'os.popen'/'os.exec*'/'os.spawn*',
    'asyncio.open_connection', 'subprocess' (import or call), or 'dynamic_import' for a non-literal import."""
    tree = ast.parse(src)
    found: set[str] = set()
    mod_alias: dict[str, str] = {}      # local name -> module it names ("o" -> "os")
    from_alias: dict[str, str] = {}     # local name -> "module.attr" ("s" -> "os.system")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mod_alias[a.asname or _root(a.name)] = a.name if a.asname else _root(a.name)
                if _root(a.name) in BANNED_MODULES:
                    found.add(_root(a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                if _root(node.module) in BANNED_MODULES:
                    found.add(_root(node.module))
                for a in node.names:
                    from_alias[a.asname or a.name] = f"{node.module}.{a.name}"
                    if node.module == "os" and _os_banned(a.name):
                        found.add("os." + a.name)
                    if node.module == "asyncio" and a.name in BANNED_ASYNCIO:
                        found.add("asyncio." + a.name)
                    if node.module == "asyncio" and a.name == "subprocess":
                        found.add("subprocess")

    def resolve(fn: ast.expr) -> str | None:
        """Dotted name of a call target with import aliases resolved, or None."""
        parts: list[str] = []
        while isinstance(fn, ast.Attribute):
            parts.append(fn.attr)
            fn = fn.value
        if not isinstance(fn, ast.Name):
            return None
        head = fn.id
        base = from_alias.get(head) or mod_alias.get(head) or head
        return ".".join([base, *reversed(parts)])

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = resolve(node.func)
        if not name:
            continue
        top = _root(name)
        if top == "subprocess":
            found.add("subprocess")
        if top == "os" and "." in name and _os_banned(name.split(".")[1]):
            found.add("os." + name.split(".")[1])
        if top == "asyncio" and name.split(".")[-1] in BANNED_ASYNCIO:
            found.add("asyncio." + name.split(".")[-1])
        last = name.split(".")[-1]
        if last in DYNAMIC_IMPORTERS and (name in DYNAMIC_IMPORTERS or top in ("importlib", "builtins")):
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if _root(arg.value) in BANNED_MODULES:
                    found.add(_root(arg.value))
            else:
                found.add("dynamic_import")
        if name == "getattr" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            tgt = node.args[0]
            if isinstance(tgt, ast.Name) and (mod_alias.get(tgt.id) or tgt.id) == "os" and _os_banned(node.args[1].value):
                found.add("os." + node.args[1].value)
        if name in ("exec", "eval", "compile"):
            found.add("dynamic_import")   # string-built code can import anything
    return found


# file (relative to tell/) -> banned things it may use. Anything else, or any other file, fails.
ALLOWLIST: dict[str, set[str]] = {
    # The one loopback opener (D-009): urllib for HTTP, socket only to resolve and verify the host is loopback.
    "localhost.py": {"urllib", "socket"},
    # Ollama goes through localhost.py; the optional dev-only `anthropic` SDK (text only, metered by record_egress) is imported lazily.
    "llm.py": {"anthropic"},
    # Spoken verdict: runs the Gradium CLI via `uvx` (our verdict text only, metered as verdict_tts).
    "speak.py": {"subprocess"},
    # Decoding webm/ogg/mp3 pipes the bytes to a local `ffmpeg` child over stdin/stdout, no network.
    "audio.py": {"subprocess"},
    # redteam.py, main.py (fastapi), pipeline.py, stt.py, privacy.py, scorer.py, signals/*: nothing banned, no entry.
}

PKG = Path(__file__).resolve().parents[1] / "tell"


def scan_package() -> dict[str, set[str]]:
    out = {}
    for p in sorted(PKG.rglob("*.py")):
        f = scan_source(p.read_text())
        if f:
            out[p.relative_to(PKG).as_posix()] = f
    return out


def test_scan_covers_every_file_recursively():
    files = {p.relative_to(PKG).as_posix() for p in PKG.rglob("*.py")}
    assert {"stt.py", "signals/neural.py", "signals/acoustic.py", "pipeline.py", "localhost.py"} <= files


def test_package_matches_allowlist_exactly():
    found = scan_package()
    for rel, things in found.items():
        assert rel in ALLOWLIST, f"{rel} uses {sorted(things)} but is not in ALLOWLIST (new network/process use must be reviewed)"
        assert things <= ALLOWLIST[rel], f"{rel} newly uses {sorted(things - ALLOWLIST[rel])}"
    # the allowlist must not go stale or grant more than is used
    for rel, allowed in ALLOWLIST.items():
        assert (PKG / rel).is_file(), f"ALLOWLIST names missing file {rel}"
        assert allowed == found.get(rel, set()), f"{rel}: allowlist {sorted(allowed)} != actual {sorted(found.get(rel, set()))}"


def test_localhost_is_the_only_file_with_urllib_or_socket():
    found = scan_package()
    assert {r for r, f in found.items() if f & {"urllib", "socket", "http", "ssl"}} == {"localhost.py"}


SHIM = Path(__file__).resolve().parents[1] / "doublespeak"


def test_compat_shim_only_aliases_tell():
    """D-013: the deprecated `doublespeak` package is one file that maps doublespeak.X onto tell.X. Its only flagged use
    is importlib.import_module on a name built from the constant "tell" prefix; no network, process or ctypes use."""
    files = sorted(p.relative_to(SHIM).as_posix() for p in SHIM.rglob("*.py"))
    assert files == ["__init__.py"]
    src = (SHIM / "__init__.py").read_text()
    assert scan_source(src) == {"dynamic_import"}
    assert '_NEW = "tell"' in src
    calls = {ast.unparse(n.args[0]) for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "import_module"}
    # tell.<sub> for doublespeak.<sub>, and doublespeak.<name> (which the finder above maps to tell.<name>)
    assert calls == {"_NEW + spec.name[len(__name__):]", "f'{__name__}.{name}'"}


def test_net_monitor_and_offline_guard_need_no_network_library():
    # Present once those PRs merge; psutil / env-only files must never import a network library.
    for name in ("net_monitor.py", "offline_guard.py", "secure_store.py", "limits.py", "signals/pella.py"):
        p = PKG / name
        if p.exists():
            assert scan_source(p.read_text()) == set(), name


# ---------------- scanner self-tests ----------------
@pytest.mark.parametrize("src,expect", [
    ("import socket", {"socket"}),
    ("import os, socket", {"socket"}),
    ("import os,\\\n    socket as s", {"socket"}),
    ("from socket import create_connection", {"socket"}),
    ("import urllib.request", {"urllib"}),
    ("from urllib import request", {"urllib"}),
    ("from urllib.parse import quote", {"urllib"}),
    ("import http.client", {"http"}),
    ("from http import client", {"http"}),
    ("import ssl", {"ssl"}),
    ("import urllib3, requests, httpx, aiohttp, websockets", {"urllib3", "requests", "httpx", "aiohttp", "websockets"}),
    ("import ftplib, smtplib, telnetlib, xmlrpc.client", {"ftplib", "smtplib", "telnetlib", "xmlrpc"}),
    ("import importlib\nimportlib.import_module('socket')", {"socket"}),
    ("import importlib\nimportlib.import_module('urllib.request')", {"urllib"}),
    ("from importlib import import_module\nimport_module('requests')", {"requests"}),
    ("__import__('socket')", {"socket"}),
    ("import importlib as il\nil.import_module('http.client')", {"http"}),
    ("__import__('so' + 'cket')", {"dynamic_import"}),
    ("import importlib\nimportlib.import_module(name)", {"dynamic_import"}),
    ("exec('import socket')", {"dynamic_import"}),
    ("import subprocess\nsubprocess.run(['curl', 'x'])", {"subprocess"}),
    ("import subprocess as sp\nsp.Popen(['ffmpeg'])", {"subprocess"}),
    ("from subprocess import run\nrun(['x'])", {"subprocess"}),
    ("import os\nos.system('curl x')", {"os.system"}),
    ("import os as o\no.popen('curl x')", {"os.popen"}),
    ("from os import system as s\ns('curl x')", {"os.system"}),
    ("import os\nos.execvp('curl', ['curl'])", {"os.execvp"}),
    ("import os\nos.spawnl(0, 'x')", {"os.spawnl"}),
    ("import os\ngetattr(os, 'system')('curl x')", {"os.system"}),
    ("import asyncio\nasync def f():\n    await asyncio.open_connection('x', 1)", {"asyncio.open_connection"}),
    ("from asyncio import open_connection", {"asyncio.open_connection"}),
    ("import asyncio\nasyncio.create_subprocess_exec('curl')", {"asyncio.create_subprocess_exec"}),
    ("def f():\n    import socket\n    return socket", {"socket"}),
    ("import anthropic", {"anthropic"}),
    ("import ctypes", {"ctypes"}),
])
def test_scanner_flags_bypass_forms(src, expect):
    assert expect <= scan_source(src), scan_source(src)


@pytest.mark.parametrize("src", [
    "import os, re, json\nos.path.join('a', 'b')\nos.environ.get('X')",
    "import numpy as np\nfrom pathlib import Path",
    "from fastapi import FastAPI\nfrom . import localhost\nfrom .localhost import post_json",
    "import psutil",
    "import importlib\nimportlib.import_module('numpy')",
    "__import__('json')",
    "x = 'import socket'\ny = 'urllib.request'",
    "# import socket\nsocket_name = 1\nhttp_ok = True",
    "import os\nos.getcwd()\nos.makedirs('d', exist_ok=True)",
    "import logging, wave, io, hashlib, hmac, threading",
    "class socket:\n    pass",
    "from . import socket",
])
def test_scanner_passes_clean_source(src):
    assert scan_source(src) == set()
