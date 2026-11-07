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
        r"\bgift ?card (number|code|pin)s?\b", r"\bscratch (off|the back)\b", r"\b(steam|itunes) cards?\b",
        r"\b(send|transfer|move) (the |your )?(money|funds|cash)\b",
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
        r"\brouting number\b", r"\byour (social security|ssn)\b", r"\b(bank|checking|savings) account (number|details|login)\b",
        r"\b(security code|cvv|cvc) (on the back|of your card)\b", r"\bpin number\b",
    ],
    "secrecy": [
        r"\bdon'?t tell (anyone|anybody|your|mom|dad)\b", r"\bkeep this between us\b", r"\bdo not (contact|call) (the|your)\b",
        r"\bdon'?t call (the bank|the police|anyone)\b", r"\bthis is confidential\b", r"\bnot (to )?tell\b",
    ],
    # Someone you love is hurt or in trouble. Each pattern needs a concrete claim: "in trouble with my homework",
    # "the hospital called about your prescription" and "the accident report is ready" must NOT fire.
    "emergency": [
        r"\b(kidnap(ped|ping)?|ransom)\b",
        r"\b(had|been in|was in|were in|got into|got in) an? (car |bad |serious )?(accident|crash)\b",
        r"\b(in|at|rushed to|taken to) the (emergency room|er|hospital)\b(?! (called|phoned|about|bill|billing|records?|pharmacy))",
        r"\bin (serious|big|real|deep) trouble\b", r"\b(i'?m|he'?s|she'?s|they'?re) in trouble\b(?! (with|at|for|again)\b)",
        r"\bin jail\b", r"\b(post|posting|pay|paying|need|needs|for) (the |his |her |my |your )?bail\b",
        r"\b(hurt|injured) (badly|bad)\b",
    ],
    # Threats of arrest or legal action. Plain mentions of police or lawyers ("I called the police about the noise") do not fire.
    "authority_threat": [
        r"\b(you('re| are|'ll be| will be| could be| may be)|going to be) (arrested|prosecuted|charged)\b",
        r"\barrest warrant\b", r"\bwarrant (for|out for) your\b", r"\bgoing to jail\b", r"\b(face|facing) (criminal )?(charges|prosecution|jail time)\b",
        r"\blegal action (against|will be taken)\b", r"\b(sue|suing|lawsuit against) you\b", r"\bfiled a lawsuit against you\b",
        r"\b(send|sending|dispatch(ed|ing)?) (the |a )?(police|sheriff|officers?)\b", r"\bpolice (are |is )?(on (their|the) way|coming)\b",
        r"\bfederal (crime|charges|offen[cs]e)\b",
    ],
}

# A genuine bank or agency saying "we will never ask for your PIN" must not read as an ask.
_NEGATION = re.compile(
    r"\b(never|won'?t|will not|would not|do not|don'?t|doesn'?t|does not|should not|shouldn'?t)\s+(ever\s+)?"
    r"(ask|asks|request|requests|call|share|give|tell|read|send|accept|take)\b[^.!?]{0,40}$", re.I)
_NEGATABLE = {"credential_ask", "payment_rails", "emergency", "authority_threat"}


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION.search(text[max(0, start - 70):start]))


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
            for m in re.finditer(p, text, re.I):
                if name in _NEGATABLE and _negated(text, m.start()):
                    continue
                hits.append(m.group(0))
                break
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
