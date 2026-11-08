"""Step 2: fine-tune pellav2's layer weights + output layer on cached features.

Usage:

    python train_head.py --weights pellav2_detector.pt --features features --out pellav2_qwen.pt

The saved file has the same format as the original, so the official script works:

    python pellav2_infer.py pellav2_qwen.pt some_clip.wav
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


def split_by_speaker(speakers, labels, val_frac, seed):
    """Hold out whole speakers for validation, stratified by class.

    Splitting is still BY SPEAKER (no voice appears in both folds), but we draw
    the validation speakers separately within each class, so the validation set
    always contains unseen REAL *and* unseen FAKE voices. Without this, a random
    speaker draw can accidentally put every held-out voice in one class, making
    the other class's "unseen" metric meaningless.
    """
    speakers = np.asarray(speakers)
    labels = np.asarray(labels)
    rng = np.random.default_rng(seed)

    # Map each speaker to its (single) class label.
    spk_label: dict[str, int] = {}
    for s, y in zip(speakers, labels):
        spk_label.setdefault(s, int(y))

    val_spk: set[str] = set()
    for cls in (0, 1):
        spks = sorted(s for s, y in spk_label.items() if y == cls)
        rng.shuffle(spks)
        if len(spks) >= 2:
            n_val = max(1, round(len(spks) * val_frac))
            val_spk.update(spks[:n_val])
        # If a class has <2 speakers it cannot both train and validate on an
        # unseen voice of that class; leave it all in train and warn below.

    uniq = sorted(spk_label)
    if len(uniq) < 4:
        print(f"WARNING: only {len(uniq)} speakers, so validation voices overlap less "
              "meaningfully. Add more speakers (e.g. LibriSpeech) for an honest test.")
    is_val = np.array([s in val_spk for s in speakers])
    return ~is_val, is_val, sorted(val_spk)


def metrics(p, y, thr=0.5):
    pred = p >= thr
    fake, real = y == 1, y == 0
    return {
        "accuracy": float(np.mean(pred == (y == 1))),
        "fakes_caught": float(np.mean(pred[fake])) if fake.any() else None,
        "real_flagged": float(np.mean(pred[real])) if real.any() else None,
        "balanced_acc": float((np.mean(pred[fake]) + np.mean(~pred[real])) / 2)
        if fake.any() and real.any() else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="pellav2_detector.pt")
    ap.add_argument("--features", default="features")
    ap.add_argument("--out", default="pellav2_qwen.pt")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--anchor", type=float, default=1e-2,
                    help="pull toward the original weights so it keeps what it knew")
    ap.add_argument("--val-frac", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    fdir = Path(args.features)
    X = torch.from_numpy(np.load(fdir / "feats.npy").astype(np.float32))
    with open(fdir / "meta.csv") as f:
        meta = list(csv.DictReader(f))
    y = np.array([int(r["label"]) for r in meta])

    tr, va, val_spk = split_by_speaker(
        [r["speaker"] for r in meta], y, args.val_frac, args.seed
    )
    print(f"{len(y)} examples | train {tr.sum()} | validation {va.sum()} "
          f"(held-out speakers: {', '.join(val_spk)})")
    if len(set(y[va])) < 2:
        print("WARNING: validation set lacks real or fake clips; "
              "make sure each speaker has both.")

    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    lw0 = state["layer_weights"].float().clone()
    W0, b0 = state["head.weight"].float().clone(), state["head.bias"].float().clone()

    lw = nn.Parameter(lw0.clone())
    head = nn.Linear(W0.shape[1], 1)
    with torch.no_grad():
        head.weight.copy_(W0)
        head.bias.copy_(b0)
    params = [lw, *head.parameters()]

    def predict(xb):
        w = torch.softmax(lw, dim=0)
        return head((xb * w[None, :, None]).sum(1)).squeeze(-1)

    ytr = torch.from_numpy(y[tr]).float()
    n_pos, n_neg = ytr.sum(), len(ytr) - ytr.sum()
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=(n_neg / n_pos.clamp(min=1)))
    opt = torch.optim.Adam(params, lr=args.lr)

    def probs(mask):
        with torch.no_grad():
            return torch.sigmoid(predict(X[mask])).numpy()

    before = metrics(probs(va), y[va])

    best, best_state, patience = -1.0, None, 0
    for epoch in range(args.epochs):
        perm = torch.randperm(int(tr.sum()))
        Xtr = X[tr][perm]
        ysh = ytr[perm]
        for i in range(0, len(Xtr), 64):
            opt.zero_grad()
            loss = loss_fn(predict(Xtr[i:i + 64]), ysh[i:i + 64])
            loss = loss + args.anchor * (((lw - lw0) ** 2).sum()
                                         + ((head.weight - W0) ** 2).sum()
                                         + ((head.bias - b0) ** 2).sum())
            loss.backward()
            opt.step()
        score = metrics(probs(va), y[va])["balanced_acc"] or 0.0
        if score > best:
            best, patience = score, 0
            best_state = (lw.detach().clone(), head.weight.detach().clone(),
                          head.bias.detach().clone())
        else:
            patience += 1
        if (epoch + 1) % 20 == 0:
            print(f"epoch {epoch + 1}: loss {loss.item():.4f}, val balanced acc {score:.1%}")
        if patience >= 30:
            print(f"Stopped early at epoch {epoch + 1}")
            break

    with torch.no_grad():
        lw.copy_(best_state[0])
        head.weight.copy_(best_state[1])
        head.bias.copy_(best_state[2])

    after = metrics(probs(va), y[va])
    aug = np.array([r["aug"] for r in meta])
    per_cond = {c: metrics(probs(va & (aug == c)), y[va & (aug == c)])
                for c in sorted(set(aug)) if (va & (aug == c)).any()}

    print("\nValidation on unseen speakers (threshold 0.5):")
    print(f"  {'':12}{'fakes caught':>14}{'real flagged':>14}{'accuracy':>10}")
    for name, m in (("before", before), ("after", after)):
        fc = f"{m['fakes_caught']:.1%}" if m["fakes_caught"] is not None else "-"
        rf = f"{m['real_flagged']:.1%}" if m["real_flagged"] is not None else "-"
        print(f"  {name:12}{fc:>14}{rf:>14}{m['accuracy']:>10.1%}")
    for c, m in per_cond.items():
        print(f"  after/{c:6}{(m['fakes_caught'] or 0):>14.1%}"
              f"{(m['real_flagged'] or 0):>14.1%}{m['accuracy']:>10.1%}")

    new_state = dict(state)
    new_state["layer_weights"] = lw.detach().to(state["layer_weights"].dtype)
    new_state["head.weight"] = head.weight.detach().to(state["head.weight"].dtype)
    new_state["head.bias"] = head.bias.detach().to(state["head.bias"].dtype)
    torch.save(new_state, args.out)
    Path(args.out).with_suffix(".json").write_text(json.dumps(
        {"before": before, "after": after, "per_condition": per_cond,
         "val_speakers": val_spk}, indent=2))
    print(f"\nSaved {args.out} (+ metrics in {Path(args.out).with_suffix('.json')})")


if __name__ == "__main__":
    main()
