"""Part B.6 - train the scam-text classifier (offline).

TF-IDF (1-3 grams) + logistic regression. The test set HOLDS OUT WHOLE SCAM
TYPES, so the model is judged on scam styles it never saw in training (a much
more honest test than a random split, which leaks near-duplicate turns). Reports
precision, recall and the false-positive rate, and saves the pipeline with
joblib to models/scam_text_model.joblib.

    python training/scam-text/train_text.py [--holdout-frac 0.3] [--seed 0]

Input: training/scam-text/scam_text.parquet (from pull_text_data.py). Offline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import TEXT_MODEL, TEXT_PARQUET  # type: ignore  # noqa: E402


def _type_holdout(df: pd.DataFrame, holdout_frac: float, seed: int):
    """Put whole scam *types* in the test fold (unseen styles)."""
    rng = np.random.default_rng(seed)
    scam_types = sorted(df.loc[df["label"] == 1, "type"].unique())
    safe_types = sorted(df.loc[df["label"] == 0, "type"].unique())
    test_types: set[str] = set()
    for pool in (scam_types, safe_types):
        pool = list(pool)
        rng.shuffle(pool)
        if len(pool) >= 2:
            k = max(1, round(len(pool) * holdout_frac))
            test_types.update(pool[:k])
    test_mask = df["type"].isin(test_types)
    # Guard: ensure both classes appear in train and test; else fall back to a
    # stratified random split so the metrics are still computable.
    if (df.loc[~test_mask, "label"].nunique() < 2
            or df.loc[test_mask, "label"].nunique() < 2
            or test_mask.sum() == 0):
        print("WARNING: type-holdout could not keep both classes in both folds; "
              "falling back to a stratified random split.", file=sys.stderr)
        from sklearn.model_selection import train_test_split

        idx = np.arange(len(df))
        tr, te = train_test_split(idx, test_size=holdout_frac, random_state=seed,
                                  stratify=df["label"].values)
        m = np.zeros(len(df), dtype=bool)
        m[te] = True
        return ~m, m, sorted(test_types)
    return ~test_mask.values, test_mask.values, sorted(test_types)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--holdout-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not TEXT_PARQUET.exists():
        print(f"No parquet at {TEXT_PARQUET}. Run pull_text_data.py first.",
              file=sys.stderr)
        return 1

    from joblib import dump
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import precision_recall_fscore_support
    from sklearn.pipeline import Pipeline

    df = pd.read_parquet(TEXT_PARQUET)
    df = df.dropna(subset=["text", "label"]).reset_index(drop=True)
    tr_mask, te_mask, test_types = _type_holdout(df, args.holdout_frac, args.seed)
    Xtr, ytr = df.loc[tr_mask, "text"].tolist(), df.loc[tr_mask, "label"].astype(int).values
    Xte, yte = df.loc[te_mask, "text"].tolist(), df.loc[te_mask, "label"].astype(int).values
    print(f"{len(df)} rows | train {len(ytr)} | test {len(yte)}")
    print(f"Held-out types: {', '.join(test_types) or '(random split)'}")

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 3), min_df=2, sublinear_tf=True,
                                  strip_accents="unicode", lowercase=True)),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0)),
    ])
    pipe.fit(Xtr, ytr)

    pred = pipe.predict(Xte)
    prec, rec, _, _ = precision_recall_fscore_support(
        yte, pred, labels=[1], average="binary", zero_division=0
    )
    # False-positive rate = not-scam wrongly flagged as scam.
    safe = yte == 0
    fpr = float(pred[safe].mean()) if safe.any() else float("nan")
    acc = float((pred == yte).mean())

    print("\n================ scam-text model (held-out types) ================")
    print(f"  precision (scam): {prec:.1%}")
    print(f"  recall    (scam): {rec:.1%}")
    print(f"  false-positive rate (not-scam flagged): "
          f"{'n/a' if fpr != fpr else f'{fpr:.1%}'}")
    print(f"  accuracy        : {acc:.1%}")
    print("==================================================================")

    # Refit on ALL data for the shipped model (more signal), keeping the metrics
    # above as the honest held-out estimate.
    pipe.fit(df["text"].tolist(), df["label"].astype(int).values)
    TEXT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    dump({"pipeline": pipe,
          "metrics": {"precision": float(prec), "recall": float(rec),
                      "fpr": None if fpr != fpr else float(fpr), "accuracy": acc},
          "held_out_types": test_types}, TEXT_MODEL)
    print(f"\nSaved scam-text model to {TEXT_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
