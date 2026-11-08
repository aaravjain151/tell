#!/usr/bin/env python3
"""Consultant council — ask Claude, GPT, Grok and Gemini the same question.

Each provider answers once as a panel of the chosen consultant roles; then Claude
(if configured) writes a synthesis: agreements, disagreements, recommendation.
No dependencies (stdlib only). Keys/models come from .env or the environment.

    python3 council/ask.py "Should v1 ship feature X?"
    python3 council/ask.py "..." --roles strategist skeptic --providers anthropic xai
    python3 council/ask.py "..." --paste      # prompts to paste into the apps, no keys needed
    python3 council/ask.py "..." --dry-run
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "Tell"
ONELINER = "a privacy-first detector that tells you whether a caller is human, a disclosed AI, an undisclosed AI, or a scam, without caller audio ever leaving the device"
ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "council"
SESSIONS = HERE / "sessions"
TIMEOUT = 180


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #")[0].strip().strip('"').strip("'")
        if v and k.strip() not in os.environ:
            os.environ[k.strip()] = v


def post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:400]}") from None


def call_anthropic(system, user, model):
    r = post("https://api.anthropic.com/v1/messages",
             {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
             {"model": model, "max_tokens": 4000, "system": system, "messages": [{"role": "user", "content": user}]})
    return "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")


def _openai_compatible(base, key_env):
    def call(system, user, model):
        r = post(f"{base}/chat/completions", {"authorization": f"Bearer {os.environ[key_env]}"},
                 {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        return r["choices"][0]["message"]["content"]
    return call


def call_gemini(system, user, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = post(url, {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
             {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}]})
    return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])


PROVIDERS = {
    "anthropic": ("Claude", "ANTHROPIC_API_KEY", "COUNCIL_ANTHROPIC_MODEL", call_anthropic),
    "openai":    ("GPT",    "OPENAI_API_KEY",    "COUNCIL_OPENAI_MODEL",    _openai_compatible("https://api.openai.com/v1", "OPENAI_API_KEY")),
    "xai":       ("Grok",   "XAI_API_KEY",       "COUNCIL_XAI_MODEL",       _openai_compatible("https://api.x.ai/v1", "XAI_API_KEY")),
    "gemini":    ("Gemini", "GEMINI_API_KEY",    "COUNCIL_GEMINI_MODEL",    call_gemini),
}

# Only defaults we're sure of; others must be set in .env (model names change often).
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}


def context_block() -> str:
    parts = []
    for rel in ("pm/PRODUCT.md", "pm/DECISIONS.md"):
        p = ROOT / rel
        if p.exists():
            parts.append(f"<{rel}>\n{p.read_text()[:12000]}\n</{rel}>")
    return "\n\n".join(parts)


def build_prompts(question: str, roles: dict) -> tuple[str, str]:
    system = (f"You are part of a board of senior consultants advising a founder building '{PROJECT}', "
              f"{ONELINER}. Be concrete, opinionated and brief. "
              "Flag any number you are not sure of as an estimate. Don't pad.")
    panel = "\n".join(f"- **{name}**: {desc}" for name, desc in roles.items())
    user = (f"Project context:\n\n{context_block()}\n\n---\n\n"
            f"Answer as this panel, one section per role (use the role name as a heading):\n{panel}\n\n"
            f"End with **Bottom line:** one paragraph with your single recommendation.\n\n"
            f"QUESTION: {question}")
    return system, user


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "question"


def main():
    load_env()
    all_roles = json.loads((HERE / "roles.json").read_text())
    ap = argparse.ArgumentParser(description=f"{PROJECT} consultant council")
    ap.add_argument("question")
    ap.add_argument("--roles", nargs="+", choices=list(all_roles), default=list(all_roles))
    ap.add_argument("--providers", nargs="+", choices=list(PROVIDERS), default=list(PROVIDERS))
    ap.add_argument("--paste", action="store_true", help="write prompts to paste into chat apps; no API calls")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-synthesis", action="store_true")
    a = ap.parse_args()

    roles = {r: all_roles[r] for r in a.roles}
    system, user = build_prompts(a.question, roles)
    SESSIONS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    out = SESSIONS / f"{stamp}-{slugify(a.question)}.md"

    if a.paste:
        out = out.with_name(out.stem + "-PASTE.md")
        out.write_text(f"# Council prompt — paste into ChatGPT, Grok, Gemini, Claude\n\n"
                       f"Paste everything between the lines into each app, then paste the answers back into "
                       f"this file under the headings below.\n\n---\n\n{system}\n\n{user}\n\n---\n\n"
                       + "".join(f"## {PROVIDERS[p][0]}\n\n_(paste answer)_\n\n" for p in a.providers))
        print(f"wrote {out.relative_to(ROOT)}")
        return

    ready, skipped = [], []
    for p in a.providers:
        label, key_env, model_env, _ = PROVIDERS[p]
        model = os.environ.get(model_env, "") or DEFAULT_MODELS.get(p, "")
        if not os.environ.get(key_env):
            skipped.append(f"{label}: no {key_env}")
        elif not model:
            skipped.append(f"{label}: set {model_env}")
        else:
            ready.append((p, model))

    print(f"roles: {', '.join(roles)}")
    print("calling: " + (", ".join(f"{PROVIDERS[p][0]} ({m})" for p, m in ready) or "nobody"))
    for s in skipped:
        print(f"skipped — {s}")
    if a.dry_run:
        return
    if not ready:
        print("\nNo providers configured. Add keys + models to .env, or use --paste.")
        return

    answers = {}
    with cf.ThreadPoolExecutor(max_workers=len(ready)) as ex:
        futs = {ex.submit(PROVIDERS[p][3], system, user, m): (p, m) for p, m in ready}
        for f in cf.as_completed(futs):
            p, m = futs[f]
            try:
                answers[p] = (m, f.result())
                print(f"✓ {PROVIDERS[p][0]}")
            except Exception as e:
                answers[p] = (m, f"**ERROR:** {e}")
                print(f"✗ {PROVIDERS[p][0]}: {e}")

    md = [f"# Council · {stamp}\n\n**Question:** {a.question}\n\n**Roles:** {', '.join(roles)}\n"]
    for p, (m, text) in answers.items():
        md.append(f"\n---\n\n## {PROVIDERS[p][0]} · `{m}`\n\n{text.strip()}\n")

    ok = {p: v for p, v in answers.items() if not v[1].startswith("**ERROR")}
    if not a.no_synthesis and "anthropic" in dict(ready) and len(ok) > 1:
        joined = "\n\n".join(f"### {PROVIDERS[p][0]}\n{t}" for p, (_, t) in ok.items())
        synth = call_anthropic(
            "You synthesize advice from several AI consultants for a founder. Be brief and decisive.",
            f"Question: {a.question}\n\nAnswers:\n\n{joined}\n\n"
            "Write: **Where they agree** (bullets), **Where they disagree and why** (bullets, name who), "
            "**Recommendation** (one paragraph), **Cheapest test this week** (one line).",
            dict(ready)["anthropic"])
        md.insert(1, f"\n## Synthesis\n\n{synth.strip()}\n")

    out.write_text("".join(md))
    print(f"\nwrote {out.relative_to(ROOT)}")
    print("Next: if this changes direction → python3 scripts/pm.py decide \"...\" \"...\" \"...\"")


if __name__ == "__main__":
    main()
