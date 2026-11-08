#!/usr/bin/env python3
"""Print the held-out comparison tables (markdown) from data/finetune/results_*.json.  python3 finetune/head_report.py results_pella_mlp [...]"""
import json
import sys
from pathlib import Path

FT = Path(__file__).resolve().parent.parent / "data" / "finetune"
CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call", "g711_alaw8k", "chain_pstn_voip"]


def f(r, k):
    v = r.get(k)
    return "-" if v is None else f"{v:.2f}"


def main(tags):
    cur = {}
    for tag in tags:
        r = json.loads((FT / f"{tag}.json").read_text())
        print(f"\n### {r['tag']}  (head params {r['head_params']}, train {r['train_seconds_total_all_folds']} s for all folds)\n")
        print("| scenario | voter | condition | n real | n fake | AUC [95% CI] | EER | FPR@TPR90 | TPR@FPR5% | TPR@0.5 | FPR@0.5 |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for key, conds in r["table"].items():
            scn, voter = key.split("/")
            for c in CONDS:
                x = conds[c]
                if "auc" not in x:
                    continue
                ci = x.get("auc_ci95")
                ci = f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else ""
                print(f"| {scn} | {voter if voter != 'head' else r['tag']} | {c} | {x['n_real']} | {x['n_fake']} | {x['auc']:.2f}{ci} | {f(x,'eer')} | {f(x,'fpr_at_tpr90')} | {f(x,'tpr_at_fpr5')} | {f(x,'tpr_at_0.5')} | {f(x,'fpr_at_0.5')} |")
        print("\nowner files (mean P(synthetic) over production windows):")
        for name, o in r["owner"].items():
            print(f"- {name} (n windows {o['n_windows']}): current {o['current']}")
            for scn in ("loo_qwen", "seen_gen"):
                print(f"    head {scn}: {o[scn]}")


if __name__ == "__main__":
    main(sys.argv[1:])
