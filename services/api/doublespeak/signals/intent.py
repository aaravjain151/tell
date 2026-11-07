"""Intent tells — is the caller trying to do something harmful? Transcript in, Tells toward scam out.

Also detects AI self-disclosure ("I'm an automated assistant"), which is *good* behavior:
legitimate AI callers are required to identify themselves, so disclosure moves a verdict to the
neutral "AI — identified itself" tier rather than the red "undisclosed" one.
"""
from __future__ import annotations

import re

from .. import thresholds as T
from ..types import Tell

PATTERNS: dict[str, list[str]] = {
    "urgency": [
        r"\bright now\b", r"\bimmediately\b", r"\bwithin (the|an) hour\b", r"\burgent(ly)?\b", r"\blast chance\b",
        r"\btoday only\b", r"\bact now\b", r"\bdon'?t hang up\b", r"\bstay on the line\b", r"\btime[- ]sensitive\b",
        r"\bbefore (it'?s|its) too late\b", r"\bexpires? (today|tonight|in)\b", r"\bwarrant\b", r"\bsuspend(ed)?\b",
    ],
    "payment_rails": [
        r"\bgift cards?\b", r"\bapple (gift )?cards?\b", r"\bgoogle play\b", r"\bbitcoin\b", r"\bcrypto(currency)?\b",
        r"\bwire (transfer|the money)\b", r"\bwestern union\b", r"\bmoneygram\b", r"\bzelle\b", r"\bvenmo\b", r"\bcash ?app\b",
        r"\bprepaid (debit )?card\b", r"\bbail (money|bond)\b", r"\bread (me|us) the (numbers?|code) on the back\b",
        r"\bcourier\b", r"\bcash (deposit|in an envelope)\b",
    ],
    "impersonation": [
        r"\bthis is your (grandson|granddaughter|son|daughter|nephew|niece)\b", r"\bit'?s me,? (grandma|grandpa|mom|dad)\b",
        r"\b(calling|I'?m) (from|with) (the )?(irs|social security|medicare|fbi|sheriff|police|your bank|chase|wells fargo|bank of america|amazon|microsoft|apple support|paypal)\b",
        r"\bofficer\b", r"\bfederal agent\b", r"\bcase (number|id)\b", r"\bfraud department\b", r"\btech(nical)? support\b",
    ],
    "credential_ask": [
        r"\bverification code\b", r"\bone[- ]time (code|password|pin)\b", r"\botp\b", r"\bsocial security number\b",
        r"\byour (password|pin|passcode)\b", r"\bcard number\b", r"\baccount number\b", r"\bread (me|back) the code\b",
        r"\bconfirm your (date of birth|mother'?s maiden name)\b", r"\bremote access\b", r"\binstall (anydesk|teamviewer)\b",
    ],
    "secrecy": [
        r"\bdon'?t tell (anyone|anybody|your|mom|dad)\b", r"\bkeep this between us\b", r"\bdo not (contact|call) (the|your)\b",
        r"\bdon'?t call (the bank|the police|anyone)\b", r"\bthis is confidential\b", r"\bnot (to )?tell\b",
    ],
}

DISCLOSURE = [
    r"\bi('m| am) an? (ai|artificial intelligence|automated|virtual|digital) (assistant|agent|caller|voice|system)\b",
    r"\bi('m| am) an ai\b", r"\bthis is an (ai|automated|artificial) (assistant|call|voice|message|system)\b",
    r"\byou('re| are) (speaking|talking) (to|with) an? (ai|automated|virtual)\b", r"\bthis call is (ai|computer)[- ]generated\b",
    r"\bai[- ]generated voice\b", r"\bautomated assistant\b", r"\bvirtual assistant\b",
]


def detect(text: str) -> tuple[list[Tell], bool]:
    """Return (intent tells, disclosed_ai)."""
    if not text or len(text.split()) < 3:
        return [Tell("intent", "intent", 0.0, 1.0, "no transcript — intent unknown", applicable=False)], False
    tells = []
    for name, pats in PATTERNS.items():
        hits = []
        for p in pats:
            m = re.search(p, text, re.I)
            if m:
                hits.append(m.group(0))
        w = T.INTENT_WEIGHTS[name]
        n = len(hits)
        score = 0.0 if n == 0 else min(1.0, 0.55 + 0.2 * (n - 1))
        label = name.replace("_", " ")
        ev = f"no {label} cues" if n == 0 else f"{label}: " + ", ".join(f"“{h}”" for h in hits[:3])
        tells.append(Tell(name, "intent", score, w, ev))
    disclosed = any(re.search(p, text, re.I) for p in DISCLOSURE)
    if disclosed:
        tells.append(Tell("ai_disclosure", "intent", 0.0, 0.0, "caller identified itself as AI/automated", applicable=False))
    return tells, disclosed
