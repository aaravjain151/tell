#!/usr/bin/env python3
"""Project manager CLI — sessions, cross-session messages, logs, decisions, audits.

No dependencies. Run from anywhere inside the repo:
    python3 scripts/pm.py status
    python3 scripts/pm.py start backend --tool codex [--launch]
    python3 scripts/pm.py msg frontend backend "Need GET /today totals endpoint"
    python3 scripts/pm.py done backend M-0003
    python3 scripts/pm.py log backend "Added resolver; next: memory"
    python3 scripts/pm.py decide "Title" "Decision" "Why"
    python3 scripts/pm.py audit
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = "Tell"
ROOT = Path(__file__).resolve().parent.parent
PM = ROOT / "pm"
INBOX = PM / "inbox"

DOMAINS = {
    "pm": ["pm/skills.md"],
    "frontend": ["apps/skills.md", "design/skills.md"],
    "backend": ["services/api/skills.md"],
    "marketing": ["marketing/skills.md"],
    "feedback": ["feedback/skills.md"],
}
TOOLS = {"claude": "claude", "codex": "codex", "cursor": "cursor"}
STALE_MSG_DAYS = 3
STALE_SKILLS_DAYS = 14


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def check_domain(d: str) -> str:
    if d not in DOMAINS:
        sys.exit(f"unknown domain '{d}'. choose: {', '.join(DOMAINS)}")
    return d


def inbox_path(d: str) -> Path:
    INBOX.mkdir(parents=True, exist_ok=True)
    p = INBOX / f"{d}.md"
    if not p.exists():
        p.write_text(f"# inbox — {d}\n\n> Open messages for the {d} session. Resolve with `pm.py done {d} <id>`.\n\n")
    return p


MSG_RE = re.compile(r"^- \[(?P<state>[ x])\] (?P<id>M-\d{4}) · (?P<when>[\d\- :]+) · from (?P<frm>\w+): (?P<text>.*)$")


def all_messages():
    out = []
    for d in DOMAINS:
        for line in inbox_path(d).read_text().splitlines():
            m = MSG_RE.match(line)
            if m:
                out.append({**m.groupdict(), "to": d})
    return out


def next_msg_id() -> str:
    nums = [int(m["id"][2:]) for m in all_messages()]
    return f"M-{(max(nums) + 1) if nums else 1:04d}"


def append_session(domain: str, tool: str, event: str) -> None:
    p = PM / "SESSION_LOG.md"
    with p.open("a") as f:
        f.write(f"| {now()} | {domain} | {tool} | {event.replace('|', '/')} |\n")


def board_section(domain: str) -> str:
    text = (PM / "BOARD.md").read_text()
    m = re.search(rf"^## {domain}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else "(no board section)"


# ---------------- commands ----------------

def cmd_start(a):
    d = check_domain(a.domain)
    open_msgs = [m for m in all_messages() if m["to"] == d and m["state"] == " "]
    skills = "\n".join(f"   - {s}" for s in DOMAINS[d])
    msgs = "\n".join(f"   - {m['id']} from {m['frm']}: {m['text']}" for m in open_msgs) or "   - (none)"
    prompt = f"""You are the {PROJECT} **{d}** session ({a.tool}).

1. Read `skills.md` (root), then:
{skills}
2. Open messages in `pm/inbox/{d}.md`:
{msgs}
3. Your board section (pm/BOARD.md):
{board_section(d)}

Before changing anything: summarize the constraints that apply, propose a plan for the top NOW item
(or the open messages, if more urgent), then implement in small steps and run the validation commands
from your domain skills.md. Stay inside your domain's folders. For anything another domain must do:
`python3 scripts/pm.py msg {d} <domain> "..."`. When done: `python3 scripts/pm.py log {d} "..."`, resolve
handled messages with `pm.py done {d} <id>`, and add any specific lesson to the relevant skills.md."""
    append_session(d, a.tool, "session start")
    print(prompt)
    if a.launch:
        exe = TOOLS[a.tool]
        if a.tool == "cursor":
            print("\n(cursor has no prompt CLI — opening the repo; paste the prompt above into the agent.)")
            if shutil.which("cursor"):
                subprocess.run(["cursor", str(ROOT)])
            return
        if not shutil.which(exe):
            print(f"\n('{exe}' CLI not found on PATH — paste the prompt above into the tool instead.)")
            return
        os.chdir(ROOT)
        os.execvp(exe, [exe, prompt])


def cmd_msg(a):
    frm, to = check_domain(a.frm), check_domain(a.to)
    mid = next_msg_id()
    with inbox_path(to).open("a") as f:
        f.write(f"- [ ] {mid} · {now()} · from {frm}: {a.text.strip()}\n")
    append_session(frm, "-", f"msg {mid} → {to}")
    print(f"{mid} → {to}")


def cmd_done(a):
    d = check_domain(a.domain)
    p = inbox_path(d)
    text = p.read_text()
    new, n = re.subn(rf"^- \[ \] ({re.escape(a.id)} ·)", r"- [x] \1", text, flags=re.M)
    if not n:
        sys.exit(f"{a.id} not open in {d} inbox")
    p.write_text(new)
    append_session(d, "-", f"resolved {a.id}")
    print(f"resolved {a.id}")


def cmd_log(a):
    d = check_domain(a.domain)
    append_session(d, a.tool, a.text.strip())
    print("logged")


def cmd_decide(a):
    p = PM / "DECISIONS.md"
    text = p.read_text()
    nums = [int(n) for n in re.findall(r"^## D-(\d{3})", text, re.M)]
    did = f"D-{(max(nums) + 1) if nums else 1:03d}"
    with p.open("a") as f:
        f.write(f"\n## {did} · {dt.date.today()} · {a.title}\n**Decision:** {a.decision}\n**Why:** {a.why}\n")
    append_session("pm", "-", f"decision {did}: {a.title}")
    print(did)


def file_age_days(path: Path) -> float:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
        ts = float(out) if out else path.stat().st_mtime
    except Exception:
        ts = path.stat().st_mtime
    return (dt.datetime.now().timestamp() - ts) / 86400


def cmd_audit(a):
    lines = [f"\n## Audit · {now()}"]
    issues = 0
    cutoff = dt.datetime.now() - dt.timedelta(days=STALE_MSG_DAYS)
    stale = [m for m in all_messages() if m["state"] == " "
             and dt.datetime.strptime(m["when"].strip(), "%Y-%m-%d %H:%M") < cutoff]
    open_count = sum(1 for m in all_messages() if m["state"] == " ")
    lines.append(f"- Open messages: {open_count} ({len(stale)} older than {STALE_MSG_DAYS}d)")
    for m in stale:
        lines.append(f"  - ⚠ {m['id']} {m['frm']}→{m['to']}: {m['text']}")
        issues += 1
    for d, files in DOMAINS.items():
        for f in files:
            p = ROOT / f
            if not p.exists():
                lines.append(f"- ⚠ missing {f}")
                issues += 1
                continue
            age = file_age_days(p)
            body = p.read_text()
            lessons = body.split("## Recent lessons")[-1]
            n_lessons = len(re.findall(r"^- \d{4}-\d{2}-\d{2}", lessons, re.M))
            flag = "⚠ " if age > STALE_SKILLS_DAYS else ""
            if flag:
                issues += 1
            lines.append(f"- {flag}{f}: updated {age:.0f}d ago, {n_lessons} lessons")
    for d in DOMAINS:
        sec = board_section(d)
        now_part = sec.split("### NEXT")[0]
        n_now = len(re.findall(r"^- ", now_part, re.M))
        if n_now > 3:
            lines.append(f"- ⚠ {d}: {n_now} items in NOW (max 3)")
            issues += 1
    root = (ROOT / "skills.md").read_text().split("## 10. Recent lessons")[-1]
    n_root = len(re.findall(r"^- \d{4}", root, re.M))
    if n_root > 10:
        lines.append(f"- ⚠ root skills.md has {n_root} lessons (keep 10; move older to domain files)")
        issues += 1
    lines.append(f"- Result: {'clean' if not issues else f'{issues} issue(s)'}")
    report = "\n".join(lines) + "\n"
    with (PM / "AUDITS.md").open("a") as f:
        f.write(report)
    append_session("pm", "-", f"audit: {issues} issue(s)")
    print(report)


def cmd_status(a):
    msgs = all_messages()
    for d in DOMAINS:
        open_msgs = [m for m in msgs if m["to"] == d and m["state"] == " "]
        now_part = board_section(d).split("### NEXT")[0]
        items = [l[2:] for l in now_part.splitlines() if l.startswith("- ")]
        print(f"\n■ {d}  ({len(open_msgs)} open msg)")
        for i in items:
            print(f"   now: {i}")
        for m in open_msgs:
            print(f"   msg: {m['id']} from {m['frm']}: {m['text']}")


def main():
    p = argparse.ArgumentParser(description=f"{PROJECT} PM")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("domain"); s.add_argument("--tool", default="claude", choices=TOOLS); s.add_argument("--launch", action="store_true"); s.set_defaults(fn=cmd_start)
    s = sub.add_parser("msg"); s.add_argument("frm"); s.add_argument("to"); s.add_argument("text"); s.set_defaults(fn=cmd_msg)
    s = sub.add_parser("done"); s.add_argument("domain"); s.add_argument("id"); s.set_defaults(fn=cmd_done)
    s = sub.add_parser("log"); s.add_argument("domain"); s.add_argument("text"); s.add_argument("--tool", default="-"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("decide"); s.add_argument("title"); s.add_argument("decision"); s.add_argument("why"); s.set_defaults(fn=cmd_decide)
    s = sub.add_parser("audit"); s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
