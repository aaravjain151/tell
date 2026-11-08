"""Shared paths and source list for the learned-tells study (docs/LEARNED-TELLS.md).

Data never lives in the repo: everything is read from the owner's local folders (read-only) and every cache is written to
LT_DIR (default: a scratch folder outside the repo). Run every script with `python -I` (it reads downloaded audio).
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "tools" / "redteam"))

LT = Path(os.environ.get("LT_DIR", "/private/tmp/tell-learned-tells")).expanduser()
MAIN = Path(os.environ.get("TELL_MAIN", "/Users/aarav/Downloads/tell"))
CALLS = MAIN / "data" / "calls"
# the head study's local data (LibriSpeech + Qwen clones of 80 LibriSpeech voices + macOS say): docs/HEAD-FINETUNE.md
FT = Path(os.environ.get("LT_FT", str(MAIN / ".claude/worktrees/agent-ab72d70df599d316e/data/finetune")))
FRIENDS = Path(os.environ.get("LT_FRIENDS", str(MAIN / ".claude/worktrees/agent-abacd5349b51b6827/data/finetune/humans_new/wild/human")))
VO = Path("/Users/aarav/Downloads/tell_launch_film/vo")
QA = Path("/Users/aarav/Downloads/voice-talk/qa_out")
OWNER = {"owner_rough_morning": Path("/Users/aarav/Downloads/data_calls_qwen3tts_rough_morning.wav"),
         "owner_long_tech_scam": Path("/Users/aarav/Downloads/data_calls_qwen3tts_long_tech_scam.wav")}

# training/eval channel conditions (tools/redteam/degrade.py, identical for both classes)
EVAL_CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]
TRAIN_CONDS = ["clean", "opus8k", "g711_mulaw8k", "speaker_rerecord_sim", "opus_lowbitrate_with_loss"]
ALL_CONDS = ["clean", "opus8k", "g711_mulaw8k", "speaker_rerecord_sim", "opus_lowbitrate_with_loss", "chain_replay_call",
             "chain_pstn_voip"]

# estimated speakers of the 12 phone memos (docs/HEAD-FINETUNE.md: w2v-BERT/wav2vec2 clustering, best guess k = 4)
FRIEND_CLUSTER = {"hunt_2": "f1", "hunt_3": "f1", "neu_7": "f1", "hunt_4": "f2", "hunt_5": "f2", "neu_8": "f2",
                  "neu_4": "f3", "neu_5": "f3", "neu_6": "f3", "neu_1": "f4", "neu_2": "f4", "neu_3": "f4"}
SANATH_RAW_EXTRA = ["casual_call", "checking_long", "grocery_store_convenience"]   # raw m4a takes with no converted .wav twin


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fold_of(speaker: str, k: int = 5) -> int:
    return int(hashlib.sha256(speaker.encode()).hexdigest(), 16) % k


def build_sources() -> list[dict]:
    """One row per source clip. role = train (enters cross-validation) | test (never trained on)."""
    rows: list[dict] = []

    def add(cid, path, label, gen, speaker, group, script, role="train", note=""):
        rows.append({"id": cid, "path": str(path), "label": int(label), "generator": gen, "speaker": speaker,
                     "group": group, "script": script, "role": role, "note": note})

    for r in csv.DictReader(open(FT / "sources.csv")):
        if r["split"] == "repo":
            continue                                    # repo clips are taken from data/calls below (all of them)
        spk = r["speaker"]
        if r["generator"] == "human":                   # LibriSpeech: a speaker and that speaker's Qwen clone share a group
            add(r["id"], FT / r["path"], 0, "human", spk, f"ls{fold_of(spk)}", r["id"], note="librispeech")
        elif r["generator"] == "qwen":
            grp = f"ls{fold_of(spk)}" if spk.startswith("ls") else f"ls{fold_of(spk)}"
            add(r["id"], FT / r["path"], 1, "qwen", spk, grp, r["id"], note="qwen0.6b clone")
        elif r["generator"] == "say":
            add(r["id"], FT / r["path"], 1, "say", spk, f"ls{fold_of(spk)}", r["id"], note="macos say")
    owner_hash = {sha(p) for p in OWNER.values() if p.exists()}
    sd = CALLS / "human" / "sanath"
    for p in sorted(sd.glob("*.wav")):
        if ".opus8k" in p.name:
            continue
        add(f"sanath_{p.stem}", p, 0, "human", "sanath", "sanath", p.stem, note="sanath")
    for stem in SANATH_RAW_EXTRA:
        p = sd / "raw" / f"{stem}.m4a"
        if p.exists():
            add(f"sanath_raw_{stem}", p, 0, "human", "sanath", "sanath", stem, note="sanath raw m4a")
    for p in sorted((CALLS / "qwen3tts").glob("*.wav")):
        if ".opus8k" in p.name:
            continue
        role = "test" if sha(p) in owner_hash or p.stem in ("rough_morning", "long_tech_scam") else "train"
        add(f"qwen3tts_{p.stem}", p, 1, "qwen", "sanath_clone", "sanath", p.stem, role=role, note="qwen clone of sanath")
    for d, voice in (("gradium", "gradium_voice"), ("gradium_stock", "gradium_stock_voice")):
        for p in sorted((CALLS / d).glob("*.wav")):
            if ".opus8k" in p.name:
                continue
            add(f"{d}_{p.stem}", p, 1, "gradium", voice, f"ls{fold_of(voice)}", p.stem, note=d)
    for p in sorted(FRIENDS.glob("*/human__*__*.wav")):
        if p.name.count(".") > 1:
            continue                                     # pre-degraded copies; we degrade ourselves
        _, loc, n = p.stem.split("__")
        cid = f"{loc}_{n}"
        add(f"friend_{cid}", p, 0, "human", cid, FRIEND_CLUSTER[cid], cid, note="phone memo")
    # ---- pure test sets: never in any training fold
    for p in sorted(VO.glob("*.EL.wav")):
        if p.stem.startswith("08_arjun"):
            add(f"el_{p.stem}", p, 1, "elevenlabs", "el_will", "test", p.stem, role="test", note="ElevenLabs premade Will (fallback)")
        else:
            add(f"el_{p.stem}", p, 1, "elevenlabs", "el_" + p.stem.split("_")[1].split(".")[0], "test", p.stem, role="test",
                note="ElevenLabs eleven_multilingual_v2")
    for p in sorted(VO.glob("08_arjun.QWEN.take*.wav")) + [VO / "08_arjun.CLONE.wav"]:
        if p.exists():
            add(f"vo_{p.stem}", p, 1, "qwen", "aarav_clone", "test", p.stem, role="test", note="Qwen3-TTS 1.7B (never trained size)")
    for p in sorted(VO.glob("*.TEMP.wav")):
        add(f"vo_{p.stem}", p, 1, "say", "say_temp", "test", p.stem, role="test", note="macOS say take")
    for d in sorted(QA.glob("*/call.wav")):
        add(f"qa_{d.parent.name}", d, 1, "qwen", "demo_voice", "test", d.parent.name, role="test", note="voice-talk QA call (Qwen)")
    for cid, p in OWNER.items():
        if p.exists():
            add(cid, p, 1, "qwen", "sanath_clone", "test", cid, role="test", note="owner file")
    return rows


def write_sources() -> list[dict]:
    LT.mkdir(parents=True, exist_ok=True)
    rows = build_sources()
    with open(LT / "sources.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def read_sources() -> list[dict]:
    rows = list(csv.DictReader(open(LT / "sources.csv")))
    for r in rows:
        r["label"] = int(r["label"])
    return rows
