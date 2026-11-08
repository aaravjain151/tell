"""Part B.4 - pull scam-text datasets and normalise to one parquet (online).

Downloads three Hugging Face datasets, normalises every row to a common schema
and appends our own scripts, then writes one local parquet file:

    {text: str, label: int (1 scam, 0 not), source: str, type: str}

Datasets (see DATA_SOURCES.md for licences, which this script also prints):
  * BothBosu/single-agent-scam-conversations
  * BothBosu/multi-agent-scam-conversation
  * sugiv/call-gate-robocalls
  * data/own_scripts/*.txt + data/scam_scripts.txt  (authored in-house, scam=1)

Needs the network and ``pip install datasets``. Training is offline after.

    python training/scam-text/pull_text_data.py [--max-per-dataset N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (  # type: ignore  # noqa: E402
    OWN_SCRIPTS,
    SCAM_SCRIPTS,
    TEXT_PARQUET,
    ensure_dirs,
)

HF_DATASETS = [
    "BothBosu/single-agent-scam-conversations",
    "BothBosu/multi-agent-scam-conversation",
    "sugiv/call-gate-robocalls",
]

# Candidate column names across datasets (they differ) - we probe these.
TEXT_KEYS = ("text", "conversation", "dialogue", "transcript", "content",
             "message", "utterance", "body")
LABEL_KEYS = ("label", "is_scam", "scam", "target", "class", "category")
TYPE_KEYS = ("type", "scam_type", "category", "subtype", "intent")

SCAM_WORDS = {"scam", "fraud", "spam", "robocall", "phishing", "1", "true", "yes"}
SAFE_WORDS = {"not_scam", "notscam", "legit", "legitimate", "ham", "benign",
              "normal", "0", "false", "no", "non-scam", "nonscam"}


def _first_key(row: dict, keys) -> str | None:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return k
    # case-insensitive fallback
    low = {k.lower(): k for k in row}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None


def _coerce_label(val) -> int | None:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return 1 if int(val) == 1 else 0
    if isinstance(val, bool):
        return int(val)
    s = str(val).strip().lower()
    if s in SCAM_WORDS:
        return 1
    if s in SAFE_WORDS:
        return 0
    if "scam" in s or "fraud" in s or "phish" in s or "robocall" in s:
        return 1
    if "legit" in s or "benign" in s or "normal" in s or "ham" in s:
        return 0
    return None


def _normalise(ds, source: str, max_rows: int) -> list[dict]:
    rows: list[dict] = []
    for i, ex in enumerate(ds):
        if max_rows and i >= max_rows:
            break
        tk = _first_key(ex, TEXT_KEYS)
        lk = _first_key(ex, LABEL_KEYS)
        if tk is None or lk is None:
            continue
        text = str(ex[tk]).strip()
        label = _coerce_label(ex[lk])
        if not text or label is None:
            continue
        typ_key = _first_key(ex, TYPE_KEYS)
        typ = str(ex[typ_key]).strip() if typ_key else (
            "scam" if label == 1 else "not_scam")
        rows.append({"text": text, "label": label, "source": source,
                     "type": typ or ("scam" if label == 1 else "not_scam")})
    return rows


def _own_scripts() -> list[dict]:
    rows: list[dict] = []
    files = list(OWN_SCRIPTS.glob("*.txt")) if OWN_SCRIPTS.exists() else []
    if SCAM_SCRIPTS.exists():
        files.append(SCAM_SCRIPTS)
    for f in files:
        for ln in f.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                rows.append({"text": ln, "label": 1, "source": "own",
                             "type": f"own:{f.stem}"})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-per-dataset", type=int, default=0,
                    help="cap rows per HF dataset (0 = all)")
    args = ap.parse_args()

    ensure_dirs()
    try:
        from datasets import load_dataset
    except ImportError:
        print("The 'datasets' package is required.\n"
              "Install once (online):  pip install datasets", file=sys.stderr)
        return 2

    all_rows: list[dict] = []
    for name in HF_DATASETS:
        print(f"\nDownloading {name} ...")
        try:
            ds = load_dataset(name, split="train")
        except Exception as exc:
            print(f"  ! could not load {name}: {exc}", file=sys.stderr)
            continue
        lic = getattr(getattr(ds, "info", None), "license", None) or "see dataset page"
        print(f"  licence (as reported): {lic}")
        rows = _normalise(ds, name, args.max_per_dataset)
        print(f"  normalised {len(rows)} rows")
        all_rows.extend(rows)

    own = _own_scripts()
    print(f"\nAdded {len(own)} in-house scam lines.")
    all_rows.extend(own)

    if not all_rows:
        print("No rows collected.", file=sys.stderr)
        return 1

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["text"]).reset_index(drop=True)
    df.to_parquet(TEXT_PARQUET, index=False)
    n_scam = int((df["label"] == 1).sum())
    print(f"\nWrote {len(df)} rows ({n_scam} scam, {len(df)-n_scam} not scam) "
          f"to {TEXT_PARQUET}")
    print("Sources:", ", ".join(sorted(df["source"].unique())))
    print("Next: python training/scam-text/mine_keywords.py "
          "and python training/scam-text/train_text.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
