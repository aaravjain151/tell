#!/usr/bin/env python3
"""Markdown tables for the 2026-11-07 human retrain: old head run vs the runs with the new phone-memo humans added.

  python3 finetune/head_humans_report.py results_pella_mlp results_hum_location_pella_mlp [results_hum_cluster_pella_mlp ...]
"""
import json
import sys
from pathlib import Path

FT = Path(__file__).resolve().parent.parent / "data" / "finetune"
CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]


def cell(x):
    if "auc" not in x:
        return "-"
    return f"{x['auc']:.2f} / {x['tpr_at_fpr5']:.2f} / {x['tpr_at_0.5']:.2f} / {x['fpr_at_0.5']:.2f}"


def main(tags):
    R = {t: json.loads((FT / f"{t}.json").read_text()) for t in tags}
    base = R[tags[0]]
    print("| scenario | condition | n real / fake (new runs) | current Pellav2 | " + " | ".join(tags) + " |")
    print("|---|---|---|---|" + "---|" * len(tags))
    for scn in ("loo_qwen", "loo_gradium", "loo_say", "seen_gen", "newhum_loo_qwen", "newhum_loo_gradium", "newhum_loo_say"):
        for c in CONDS:
            last = R[tags[-1]]["table"].get(f"{scn}/current", {}).get(c)
            if not last:
                continue
            cols = [cell(R[t]["table"].get(f"{scn}/head", {}).get(c, {})) for t in tags]
            print(f"| {scn} | {c} | {last['n_real']} / {last['n_fake']} | {cell(last)} | " + " | ".join(cols) + " |")
    print("\ncells: AUC / TPR@FPR5% / TPR@0.5 / FPR@0.5 (the newhum_* rows use ONLY the new humans as reals)\n")
    for t in tags[1:]:
        fa = R[t].get("new_humans_false_alarms")
        if not fa:
            continue
        print(f"\nnew humans, false alarms ({t}); n windows {fa['current']['clean']['n_new_windows']}")
        print("| voter | " + " | ".join(CONDS + ["g711_alaw8k", "chain_pstn_voip"]) + " |")
        print("|---|" + "---|" * 6)
        for name, d in fa.items():
            print(f"| {name} | " + " | ".join(f"{d[c]['fa_0.5']:.2f} (op {d[c]['op_fpr5_old']:.2f}: {d[c]['fa_op']:.2f})" for c in CONDS + ["g711_alaw8k", "chain_pstn_voip"]) + " |")
    print("\nowner files (mean P(synthetic), 3 production windows each; head = the fold-model that never saw Sanath)")
    for name in base["owner"]:
        for c in ("clean", "opus8k", "chain_replay_call"):
            row = [f"{base['owner'][name]['current'][c]:.2f}"]
            for t in tags:
                o = R[t]["owner"][name]
                row += [f"{o['loo_qwen_sanath_heldout'][c]:.2f}", f"{o['seen_gen_sanath_heldout'][c]:.2f}"]
            print(f"| {name} | {c} | " + " | ".join(row) + " |")
    print("(columns: Pellav2 now, then per run: head no-Qwen, head Qwen-seen)")


if __name__ == "__main__":
    main(sys.argv[1:])
