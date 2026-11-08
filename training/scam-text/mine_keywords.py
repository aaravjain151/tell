"""Part B.5 - mine the top scam phrases by log-odds (offline).

Computes the informative-Dirichlet-prior log-odds (Monroe et al. 2008) of every
word and 2-3 word phrase for scam vs not-scam, and writes the top 100 scam
phrases to models/keywords.json, each with a weight (0-1) and a short plain-
English reason. The JSON mirrors the (pattern, weight, reason) shape of
config.SCAM_RULES so the app can show the same style of reasons.

    python training/scam-text/mine_keywords.py [--top 100] [--prior 0.1]

Input: training/scam-text/scam_text.parquet (from pull_text_data.py).
Offline - operates on the local parquet only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from math import sqrt
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import KEYWORDS_JSON, TEXT_PARQUET  # type: ignore  # noqa: E402

_TOKEN = re.compile(r"[a-z][a-z'\-]+")
STOP = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "i", "you",
    "we", "they", "he", "she", "me", "my", "your", "our", "so", "do", "did",
    "have", "has", "had", "will", "would", "can", "could", "with", "as", "at",
    "by", "from", "not", "no", "yes", "ok", "okay", "um", "uh",
}

# Phrases we can map to a friendly reason; anything else gets a generic one.
REASON_HINTS = [
    (("gift", "card"), "Mentioned gift cards (a common scam payment)"),
    (("wire", "transfer"), "Asked for a wire transfer"),
    (("social", "security"), "Mentioned your Social Security number"),
    (("bank", "account"), "Asked about your bank account"),
    (("one", "time"), "Asked for a one-time code"),
    (("verification", "code"), "Asked for a verification code"),
    (("arrest",), "Threatened arrest"),
    (("warrant",), "Mentioned a warrant"),
    (("bail",), "Asked for bail money"),
    (("accident",), "Claimed an emergency (an accident)"),
    (("hospital",), "Claimed a medical emergency"),
    (("grandson",), "Claimed to be a relative in trouble"),
    (("grandma",), "Used a family emergency angle"),
    (("bitcoin",), "Asked for cryptocurrency"),
    (("crypto",), "Asked for cryptocurrency"),
    (("urgent",), "Pressured you to act urgently"),
    (("immediately",), "Pressured you to act immediately"),
    (("right", "now"), "Pressured you to act right now"),
    (("don't", "tell"), "Told you to keep it secret"),
    (("secret",), "Told you to keep it secret"),
    (("suspended",), "Claimed an account was suspended"),
    (("refund",), "Used a fake refund angle"),
    (("prize",), "Claimed you won a prize"),
    (("remote", "access"), "Asked for remote access to your device"),
    (("password",), "Asked for a password"),
    (("pin",), "Asked for a PIN"),
    (("irs",), "Impersonated the tax authority"),
    (("microsoft",), "Impersonated tech support"),
]


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _phrase_counts(texts: list[str]) -> Counter:
    c: Counter = Counter()
    for t in texts:
        toks = _tokens(t)
        for n in (1, 2, 3):
            c.update(_ngrams(toks, n))
    return c


def _log_odds(scam: Counter, safe: Counter, prior: float):
    """Monroe et al. informative-Dirichlet log-odds with z-scores."""
    vocab = set(scam) | set(safe)
    n_s = sum(scam.values())
    n_o = sum(safe.values())
    a0 = prior * len(vocab)
    out = {}
    for w in vocab:
        ys, yo = scam.get(w, 0), safe.get(w, 0)
        if ys + yo < 3:            # ignore very rare phrases
            continue
        # log-odds-ratio with Dirichlet prior
        l_s = (ys + prior) / (n_s + a0 - ys - prior)
        l_o = (yo + prior) / (n_o + a0 - yo - prior)
        import math
        delta = math.log(l_s) - math.log(l_o)
        var = 1.0 / (ys + prior) + 1.0 / (yo + prior)
        z = delta / sqrt(var)
        out[w] = (delta, z)
    return out


def _reason_for(phrase: str) -> str:
    words = set(phrase.split())
    for keys, reason in REASON_HINTS:
        if all(k in words or k in phrase for k in keys):
            return reason
    return f"Used scam-associated wording: \u201c{phrase}\u201d"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--prior", type=float, default=0.1)
    args = ap.parse_args()

    if not TEXT_PARQUET.exists():
        print(f"No parquet at {TEXT_PARQUET}. Run pull_text_data.py first.",
              file=sys.stderr)
        return 1

    df = pd.read_parquet(TEXT_PARQUET)
    scam_texts = df.loc[df["label"] == 1, "text"].astype(str).tolist()
    safe_texts = df.loc[df["label"] == 0, "text"].astype(str).tolist()
    if not scam_texts or not safe_texts:
        print("Need both scam and non-scam rows.", file=sys.stderr)
        return 1

    scam_c = _phrase_counts(scam_texts)
    safe_c = _phrase_counts(safe_texts)
    scored = _log_odds(scam_c, safe_c, args.prior)

    # Keep phrases that lean scam, rank by z-score, take top N.
    ranked = sorted(
        ((p, d, z) for p, (d, z) in scored.items() if d > 0),
        key=lambda t: t[2], reverse=True,
    )[: args.top]
    if not ranked:
        print("No scam-leaning phrases found.", file=sys.stderr)
        return 1

    # Normalise z-scores to weights in (0, 1].
    zmax = max(z for _, _, z in ranked) or 1.0
    keywords = [
        {
            "phrase": p,
            "weight": round(min(1.0, z / zmax), 4),
            "log_odds": round(d, 4),
            "z": round(z, 3),
            "reason": _reason_for(p),
        }
        for p, d, z in ranked
    ]

    KEYWORDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    KEYWORDS_JSON.write_text(json.dumps(
        {"description": "Top scam phrases by log-odds (scam vs not scam).",
         "n_scam_docs": len(scam_texts), "n_safe_docs": len(safe_texts),
         "keywords": keywords}, indent=2), encoding="utf-8")
    print(f"Wrote {len(keywords)} scam phrases to {KEYWORDS_JSON}")
    print("Top 10:")
    for k in keywords[:10]:
        print(f"  {k['weight']:.2f}  {k['phrase']:<22}  {k['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
