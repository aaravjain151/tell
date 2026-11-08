#!/usr/bin/env python3
"""Paired Qwen3-TTS-clone vs real-speaker evaluation (2026-11-08, docs/HEAD-FINETUNE.md "Qwen-Sanath pairs").

Labels come ONLY from folders: data/calls/qwen3tts = AI (Qwen clone of Sanath), data/calls/human/** = human; the friends'
phone memos (data/finetune/humans_new) and a LibriSpeech subset (data/finetune/src/real) are human; data/calls/gradium* = AI
(other engine, used by the learned-fusion refit only). Audio is read-only and never committed; outputs are numbers only.

  python3 -I finetune/qwen_pairs.py manifest            # data/finetune/pairs/manifest.json (path, label, group, script, SHA-256)
  python3 -I finetune/qwen_pairs.py pipeline            # every clip x {clean, opus8k, g711_mulaw8k, chain_replay_call} through the
                                                        # SHIPPED local pipeline (fused p_ai, tier, every tell, shadow layers) + the two
                                                        # existing heads on the same production windows -> pairs/rows.jsonl (resumable)
  python3 -I finetune/qwen_pairs.py windows             # 4 s windows (hop 4, max 4) of the Sanath + Qwen clips x 8 conditions (head retrain)
  python3 -I finetune/qwen_pairs.py features            # frozen w2v-BERT 2.0 features of those windows (CPU)
  python3 -I finetune/qwen_pairs.py report              # pairs/report.json + pairs/report.md
  python3 -I finetune/qwen_pairs.py fusion-rows         # pairs/fusion_rows.json in tools/personal/fusion.py format (+ "group")

Everything runs on CPU (the engine on :8000 owns MPS).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "finetune"))
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "tools" / "redteam"))
FT = ROOT / "data" / "finetune"
PAIRS = FT / "pairs"
WIN_DIR = PAIRS / "win"
CALLS = Path(os.environ.get("TELL_CALLS", "/Users/aarav/Downloads/tell/data/calls"))   # the main checkout's data (read-only)
HN = FT / "humans_new"
SR = 16_000
CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]
# The 8 scripts of the 2026-11-07 cue study; everything else with both versions is a NEW script.
OLD_SCRIPTS = ["casual_clone", "long_appointment", "long_checkin", "sales_disclosed", "sales_undisclosed", "scam_bank_otp",
               "scam_grandparent", "scam_irs"]
# Qwen clips the existing heads were trained on (head_build_data: repo qwen3tts minus the owner-file duplicate).
HEAD_TRAINED_QWEN = OLD_SCRIPTS + ["long_agent_undisclosed"]
N_LIBRI = 40
SHADOW = ["qwen_cpp_db", "qwen_long_pause_per_min", "qwen_f0_rate_st_s", "qwen_onset_sharpness_db", "qwen_lowmid_balance_db",
          "modulation_4_16_ratio"]
# Direction toward AI, fixed a priori from docs/QWEN-CUES.md (the 8-pair study), NOT learned here:
# Qwen has higher CPP, fewer long pauses, slower F0 movement, sharper onsets, more 500-1000 Hz, more 4-16 Hz modulation.
SIGN = {"qwen_cpp_db": 1, "qwen_long_pause_per_min": -1, "qwen_f0_rate_st_s": -1, "qwen_onset_sharpness_db": 1,
        "qwen_lowmid_balance_db": 1, "modulation_4_16_ratio": 1}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _stems(d: Path) -> list[Path]:
    return sorted(p for p in d.glob("*.wav") if "." not in p.stem)


# --------------------------------------------------------------------------------------------- manifest
def manifest() -> None:
    clips = []
    for p in _stems(CALLS / "qwen3tts"):
        clips.append({"id": f"qwen__{p.stem}", "label": 1, "source": "qwen_sanath", "group": "sanath", "script": p.stem,
                      "wav": str(p), "txt": str(p.with_suffix(".txt")) if p.with_suffix(".txt").exists() else ""})
    for spk_dir in sorted((CALLS / "human").iterdir()):
        if not spk_dir.is_dir():
            continue
        for p in _stems(spk_dir):
            clips.append({"id": f"human_{spk_dir.name}__{p.stem}", "label": 0, "source": spk_dir.name, "group": spk_dir.name,
                          "script": p.stem, "wav": str(p), "txt": str(p.with_suffix(".txt")) if p.with_suffix(".txt").exists() else ""})
    for eng in ("gradium", "gradium_stock", "elevenlabs"):
        for p in _stems(CALLS / eng) if (CALLS / eng).exists() else []:
            clips.append({"id": f"{eng}__{p.stem}", "label": 1, "source": eng, "group": f"{eng}_voice", "script": p.stem,
                          "wav": str(p), "txt": str(p.with_suffix(".txt")) if p.with_suffix(".txt").exists() else ""})
    if (HN / "humans_meta.json").exists():
        sp = json.loads((HN / "speakers.json").read_text())["hf"]
        cl = dict(zip(sp["clips"], sp["clusters_k_best"]))
        for r in json.loads((HN / "humans_meta.json").read_text()):
            clips.append({"id": f"friends__{r['id']}", "label": 0, "source": "friends", "group": f"friend_c{cl[r['id']]}",
                          "script": f"friends_{r['id']}", "wav": str(HN / r["wav"]), "txt": ""})     # no text: local whisper, as in production
    # LibriSpeech: first utterance of N_LIBRI speakers (every other speaker of the cached 80), with its reference transcript
    rows = [r for r in csv.DictReader(open(FT / "sources.csv")) if r["label"] == "0" and r["split"] in ("dev-clean", "test-clean")]
    spk = sorted({r["speaker"] for r in rows})[::2][:N_LIBRI]
    for s in spk:
        r = next(r for r in rows if r["speaker"] == s)
        utt = Path(r["path"]).stem
        a, b, _ = utt.split("-")
        tr = list((FT / "raw").glob(f"*/LibriSpeech/*/{a}/{b}/{a}-{b}.trans.txt"))
        text = next((ln.split(" ", 1)[1].strip().lower() for ln in tr[0].read_text().splitlines() if ln.startswith(utt)), "") if tr else ""
        clips.append({"id": f"libri__{utt}", "label": 0, "source": "librispeech", "group": f"libri_{s}", "script": f"libri_{utt}",
                      "wav": str(FT / r["path"]), "txt": "", "text": text})
    for c in clips:
        c["sha256"] = _sha(Path(c["wav"]))
    PAIRS.mkdir(parents=True, exist_ok=True)
    (PAIRS / "manifest.json").write_text(json.dumps(clips, indent=1))
    from collections import Counter
    print(len(clips), Counter(c["source"] for c in clips))


def _clips() -> list[dict]:
    return json.loads((PAIRS / "manifest.json").read_text())


# --------------------------------------------------------------------------------------------- shipped pipeline + heads
def _env() -> None:
    os.environ.update(LLM_PROVIDER="stub", TELL_STT="whisper", PELLA_DEVICE="cpu", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      HF_SPOOF_MODEL=os.environ.get("HF_SPOOF_MODEL", "garystafford/wav2vec2-deepfake-voice-detector"))
    from tell.signals import pella
    os.environ.setdefault("PELLA_MODEL", str(pella.weights_path() or ""))


def _load_heads() -> dict:
    import head_train_eval as hte
    import torch
    heads = {}
    for name, stem in (("head_old", "head_pella_mlp"), ("head_hum_cluster", "head_hum_cluster_pella_mlp")):
        if (FT / f"{stem}.pt").exists():
            info = json.loads((FT / f"{stem}.json").read_text())
            h = hte.build_head(info["layers"], info["hidden"], info["kind"], info["use_std"])
            h.load_state_dict(torch.load(FT / f"{stem}.pt", map_location="cpu", weights_only=True))
            heads[name] = h.eval()
    return heads


def _pella_feats(chunks: list[np.ndarray]):
    """Masked time mean/std of every hidden layer of the frozen Pellav2 backbone (identical to head_extract.run)."""
    import head_extract as he
    import torch
    from tell.signals import pella
    m = pella._model
    wav = torch.from_numpy(np.stack([pella.prep(c) for c in chunks])).to("cpu")
    with torch.no_grad():
        feats, mask = m.features(wav)
        hs = m.backbone(input_features=feats, attention_mask=mask, output_hidden_states=True).hidden_states
        mean, std = he._pool(hs, mask)
    return mean.float().numpy(), std.float().numpy()


def pipeline() -> None:
    _env()
    import degrade
    import head_train_eval as hte
    from tell import pipeline as pl
    from tell import stt
    from tell.signals import pella
    from tell.signals import windows as win
    heads = _load_heads()
    out = PAIRS / "rows.jsonl"
    done = set()
    if out.exists():
        done = {(r["id"], r["cond"]) for r in map(json.loads, out.read_text().splitlines())}
    only = os.environ.get("PAIRS_ONLY", "")
    clips = [c for c in _clips() if not only or c["source"] in only.split(",")]
    t0 = time.time()
    with open(out, "a") as f:
        for c in clips:
            x0 = None
            for cond in CONDS:
                if (c["id"], cond) in done:
                    continue
                if x0 is None:
                    x0 = degrade.read_wav(Path(c["wav"]))
                x = x0 if cond == "clean" else degrade.CONDITIONS[cond][0](x0).astype(np.float32)
                text = Path(c["txt"]).read_text(encoding="utf-8", errors="replace") if c.get("txt") else (c.get("text") or None)
                v = pl.analyze(stt.to_wav(x), text)
                ctx = (v.egress or {}).get("context") or {}
                tells = {t.name: t for t in v.tells}
                row = {"id": c["id"], "cond": cond, "label": c["label"], "source": c["source"], "group": c["group"], "script": c["script"],
                       "tier": v.tier, "p_ai": v.p_ai, "p_scam": v.p_scam, "confidence": v.confidence,
                       "pella": tells["neural_pella"].score if "neural_pella" in tells and tells["neural_pella"].applicable else None,
                       "hf": tells["neural_hf"].score if "neural_hf" in tells and tells["neural_hf"].applicable else None,
                       "tells": [{"name": t.name, "family": t.family, "score": t.score, "weight": t.weight, "applicable": t.applicable} for t in v.tells],
                       "ctx": {k: ctx.get(k) for k in ("band_limited", "duration_s", "speech_ratio")},
                       "shadow": {k: d.get("value") for k, d in (ctx.get("shadow") or {}).items() if isinstance(d, dict)}}
                ws = win.windows(x, SR, win_s=4.0, hop_s=2.0, max_n=3)              # the production Pellav2 windows
                if ws and heads and pella._model is not None:
                    mean, std = _pella_feats([w for _, w in ws])
                    for name, h in heads.items():
                        row[name] = float(np.mean(hte.predict(h, mean, std)))
                f.write(json.dumps(row) + "\n")
                f.flush()
                print(f"{time.time() - t0:6.0f}s {c['id']:40s} {cond:18s} p_ai {v.p_ai:.2f} tier {v.tier:8s} pella {row['pella']} "
                      f"hf {row['hf']} head {row.get('head_old')}", flush=True)


# --------------------------------------------------------------------------------------------- windows / features for the retrain
def windows() -> None:
    from concurrent.futures import ProcessPoolExecutor

    import head_extract as he
    from tell.signals import windows as win
    WIN_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for c in _clips():
        if c["source"] not in ("qwen_sanath", "sanath"):
            continue
        x = he._read(c["wav"])
        for k, (t, w) in enumerate(win.windows(x, SR, win_s=4.0, hop_s=4.0, max_n=4)):
            if len(w) == he.WIN:
                items.append(({"id": c["id"], "path": c["wav"], "label": c["label"], "generator": "qwen" if c["label"] else "human",
                               "speaker": "sanath", "split": "sanath_pairs", "source_sha256": c["sha256"], "clip": c["id"], "win": k,
                               "owner": 0, "script": c["script"]}, w.astype(np.float32)))
    rows = [m for m, _ in items]
    for i, m in enumerate(rows):
        m["wid"] = i
    with open(WIN_DIR / "windows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    X = [w for _, w in items]
    print(len(X), "windows", sum(m["label"] for m in rows), "fake", flush=True)
    with ProcessPoolExecutor(max_workers=4) as ex:
        for cond in he.CONDS:
            out = list(ex.map(he._degrade_one, [(cond, w) for w in X], chunksize=4))
            np.save(WIN_DIR / f"win_{cond}.npy", (np.clip(np.stack(out), -1, 1) * 32767).astype(np.int16))
            print(cond, "ok", flush=True)


def features() -> None:
    import head_extract as he
    os.environ.setdefault("HEAD_DEVICE", "cpu")
    _env()
    he.FT = WIN_DIR
    he.extract("pella")


# --------------------------------------------------------------------------------------------- report
def _rows() -> list[dict]:
    return [json.loads(ln) for ln in (PAIRS / "rows.jsonl").read_text().splitlines()]


def _auc(pos, neg) -> float:
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    d = pos[:, None] - neg[None, :]
    return float(((d > 0) + 0.5 * (d == 0)).mean())


def _boot_auc(pos, neg, pos_units, neg_units, n=2000, seed=0, paired=False):
    """95% percentile CI. Resamples units (scripts for the paired set: a script's Qwen and real clip move together)."""
    rng = np.random.default_rng(seed)
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pu, nu = np.asarray(pos_units), np.asarray(neg_units)
    vals = []
    if paired:
        units = np.unique(np.concatenate([pu, nu]))
        for _ in range(n):
            pick = rng.choice(units, len(units))
            pi = np.concatenate([np.where(pu == u)[0] for u in pick])
            ni = np.concatenate([np.where(nu == u)[0] for u in pick])
            if len(pi) and len(ni):
                vals.append(_auc(pos[pi], neg[ni]))
    else:
        up, un = np.unique(pu), np.unique(nu)
        for _ in range(n):
            pi = np.concatenate([np.where(pu == u)[0] for u in rng.choice(up, len(up))])
            ni = np.concatenate([np.where(nu == u)[0] for u in rng.choice(un, len(un))])
            vals.append(_auc(pos[pi], neg[ni]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


def _score(r: dict, name: str):
    if name in ("p_ai", "pella", "hf", "head_old", "head_hum_cluster"):
        v = r.get(name)
    else:
        v = (r.get("shadow") or {}).get(name)
        v = None if v is None else SIGN[name] * v
    return None if v is None or not np.isfinite(v) else float(v)


SCORES = ["p_ai", "pella", "hf", "head_old", "head_hum_cluster"] + SHADOW
CUT = {"p_ai": 0.60, "pella": 0.5, "hf": 0.5, "head_old": 0.5, "head_hum_cluster": 0.5}


def report() -> None:
    rows = _rows()
    q = [r for r in rows if r["source"] == "qwen_sanath"]
    pair_scripts = sorted({r["script"] for r in q} & {r["script"] for r in rows if r["source"] == "sanath"})
    new_scripts = [s for s in pair_scripts if s not in OLD_SCRIPTS]
    human_sources = ["sanath", "friends", "librispeech"]
    res = {"n": {}, "paired": {}, "vs_humans": {}, "catch": {}, "false_alarm": {}, "tiers": {}, "per_clip": {}}
    res["pair_scripts"], res["new_scripts"] = pair_scripts, new_scripts
    for cond in CONDS:
        R = [r for r in rows if r["cond"] == cond]
        by = lambda src: [r for r in R if r["source"] == src]
        Q = by("qwen_sanath")
        res["n"][cond] = {s: len(by(s)) for s in ["qwen_sanath"] + human_sources + ["gradium", "gradium_stock"]}
        for name in SCORES:
            for subset, scripts in (("all_pairs", pair_scripts), ("new_scripts", new_scripts), ("old_scripts", [s for s in pair_scripts if s in OLD_SCRIPTS])):
                qq = [(r["script"], _score(r, name)) for r in Q if r["script"] in scripts and _score(r, name) is not None]
                hh = [(r["script"], _score(r, name)) for r in by("sanath") if r["script"] in scripts and _score(r, name) is not None]
                if len(qq) < 3 or len(hh) < 3:
                    continue
                if name.startswith("head") and subset != "new_scripts":
                    pass   # kept, but the report flags that old-script Qwen clips were in the heads' training set
                dq, dh = dict(qq), dict(hh)
                both = [s for s in scripts if s in dq and s in dh]
                res["paired"].setdefault(cond, {}).setdefault(name, {})[subset] = {
                    "n_pairs": len(both), "auc": _auc([v for _, v in qq], [v for _, v in hh]),
                    "auc_ci95": _boot_auc([v for _, v in qq], [v for _, v in hh], [s for s, _ in qq], [s for s, _ in hh], paired=True),
                    "win_rate": float(np.mean([dq[s] > dh[s] for s in both])) if both else None,
                    "mean_qwen": float(np.mean([v for _, v in qq])), "mean_real": float(np.mean([v for _, v in hh]))}
            # Qwen (all 20 clips) vs every human source; units = clips (each human clip is its own unit; for heads, new scripts only)
            Qs = [r for r in Q if not name.startswith("head") or r["script"] not in HEAD_TRAINED_QWEN]
            qv = [(r["script"], _score(r, name)) for r in Qs if _score(r, name) is not None]
            for src in human_sources + ["all_humans"]:
                H = [r for r in R if r["source"] in (human_sources if src == "all_humans" else [src])]
                hv = [(r["id"], _score(r, name)) for r in H if _score(r, name) is not None]
                if len(qv) >= 3 and len(hv) >= 3:
                    res["vs_humans"].setdefault(cond, {}).setdefault(name, {})[src] = {
                        "n_qwen": len(qv), "n_human": len(hv), "auc": _auc([v for _, v in qv], [v for _, v in hv]),
                        "auc_ci95": _boot_auc([v for _, v in qv], [v for _, v in hv], [s for s, _ in qv], [s for s, _ in hv])}
            if name in CUT:
                for subset, QQ in (("all", Q), ("new_scripts", [r for r in Q if r["script"] not in HEAD_TRAINED_QWEN]),
                                   ("gradium", by("gradium") + by("gradium_stock"))):
                    v = [_score(r, name) for r in QQ if _score(r, name) is not None]
                    res["catch"].setdefault(cond, {}).setdefault(name, {})[subset] = {"k": int(sum(s >= CUT[name] for s in v)), "n": len(v)}
                for src in human_sources:
                    v = [_score(r, name) for r in by(src) if _score(r, name) is not None]
                    res["false_alarm"].setdefault(cond, {}).setdefault(name, {})[src] = {
                        "k": int(sum(s >= CUT[name] for s in v)), "n": len(v), "max": float(max(v)) if v else None}
        from collections import Counter
        res["tiers"][cond] = {s: dict(Counter(r["tier"] for r in by(s))) for s in ["qwen_sanath"] + human_sources}
        res["per_clip"][cond] = {r["id"]: {k: (round(r[k], 3) if isinstance(r.get(k), float) else r.get(k)) for k in ("p_ai", "tier", "pella", "hf", "head_old", "head_hum_cluster")}
                                 for r in R if r["source"] in ("qwen_sanath", "sanath")}
    (PAIRS / "report.json").write_text(json.dumps(res, indent=1))
    (PAIRS / "report.md").write_text(_markdown(res))
    print(_markdown(res))


def _fmt_auc(d):
    if not d:
        return "n/a"
    ci = d.get("auc_ci95")
    return f"{d['auc']:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else f"{d['auc']:.2f}"


def _markdown(res) -> str:
    L = [f"Pair scripts: {len(res['pair_scripts'])} (new since the 8-pair study: {len(res['new_scripts'])}: {', '.join(res['new_scripts'])})", ""]
    for cond in CONDS:
        L.append(f"n clips {cond}: " + ", ".join(f"{k} {v}" for k, v in res["n"][cond].items()))
    L += ["", "### Paired AUC, Qwen clone vs the same speaker reading the same script (CI: bootstrap over scripts)", "",
          "| score | condition | all pairs: n / AUC [95% CI] / paired win | new scripts only: n / AUC [95% CI] / win |", "|---|---|---|---|"]
    for name in SCORES:
        for cond in CONDS:
            p = res["paired"].get(cond, {}).get(name, {})
            a, b = p.get("all_pairs"), p.get("new_scripts")
            f = lambda d: "n/a" if not d else f"{d['n_pairs']} / {_fmt_auc(d)} / {d['win_rate']:.2f}"
            L.append(f"| {name} | {cond} | {f(a)} | {f(b)} |")
    L += ["", "### Qwen clone vs each human source (AUC [95% CI], n_qwen / n_human; heads: Qwen clips of new scripts only)", "",
          "| score | condition | vs Sanath | vs friends | vs LibriSpeech | vs all humans |", "|---|---|---|---|---|---|"]
    for name in SCORES:
        for cond in CONDS:
            v = res["vs_humans"].get(cond, {}).get(name, {})
            cell = lambda s: "n/a" if s not in v else f"{_fmt_auc(v[s])} ({v[s]['n_qwen']}/{v[s]['n_human']})"
            L.append(f"| {name} | {cond} | {cell('sanath')} | {cell('friends')} | {cell('librispeech')} | {cell('all_humans')} |")
    L += ["", "### Catch rate (Qwen called AI) and false alarms (human called AI) at the shipping cut (fused p_ai >= 0.60; voters/heads >= 0.5)", "",
          "| score | condition | catch: all Qwen | catch: Qwen new scripts | catch: Gradium | FA Sanath | FA friends | FA LibriSpeech |", "|---|---|---|---|---|---|---|---|"]
    for name in CUT:
        for cond in CONDS:
            c = res["catch"].get(cond, {}).get(name, {})
            fa = res["false_alarm"].get(cond, {}).get(name, {})
            k = lambda d: "n/a" if not d or not d["n"] else f"{d['k']}/{d['n']}"
            L.append(f"| {name} | {cond} | {k(c.get('all'))} | {k(c.get('new_scripts'))} | {k(c.get('gradium'))} | {k(fa.get('sanath'))} | {k(fa.get('friends'))} | {k(fa.get('librispeech'))} |")
    L += ["", "### Tiers", ""]
    for cond in CONDS:
        L.append(f"- {cond}: " + "; ".join(f"{s} {d}" for s, d in res["tiers"][cond].items()))
    return "\n".join(L) + "\n"


def fusion_rows() -> None:
    out = []
    for r in _rows():
        if r["source"] not in ("qwen_sanath", "sanath", "friends", "librispeech", "gradium", "gradium_stock"):
            continue
        out.append({"engine": "human" if r["label"] == 0 else ("qwen3tts" if r["source"] == "qwen_sanath" else r["source"]),
                    "speaker": r["group"], "group": r["group"], "name": r["script"], "cond": r["cond"], "is_ai": bool(r["label"]),
                    "p_ai": r["p_ai"], "tells": r["tells"], "shadow": r["shadow"]})
    (PAIRS / "fusion_rows.json").write_text(json.dumps(out))
    print(len(out), "rows")


if __name__ == "__main__":
    {"manifest": manifest, "pipeline": pipeline, "windows": windows, "features": features, "report": report,
     "fusion-rows": fusion_rows}[sys.argv[1]]()
