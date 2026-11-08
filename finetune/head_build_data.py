#!/usr/bin/env python3
"""Step 1 of the neural-head recipe: assemble a many-speaker real/fake source list with provenance.

Everything lands under data/finetune/ (gitignored). Nothing here touches the network; download the two LibriSpeech
archives once (see docs/HEAD-FINETUNE.md) and untar them under data/finetune/raw/{dev,test}/.

  python3 finetune/head_build_data.py plan      -> data/finetune/src/real/*.wav, data/finetune/qwen_jobs.json, manifest.json
  (run finetune/head_gen_qwen.py with the voice-talk venv to synthesise the fakes in qwen_jobs.json)
  python3 finetune/head_build_data.py finalize  -> data/finetune/sources.csv (one row per source clip: label/generator/speaker/hash)

Real speech:  LibriSpeech dev-clean + test-clean (80 speakers, CC BY 4.0, https://www.openslr.org/12), plus the repo's own
              Sanath recordings (data/calls/human/sanath, consented) .
Fakes:        Qwen3-TTS (local, zero-shot clone) of every LibriSpeech speaker from ONE reference utterance each, plus the two
              consented voice-talk reference voices (demo-say, demo-say-imp: synthetic macOS 'say' voices) and the repo's
              existing Qwen3-TTS clones of Sanath; the repo's Gradium clips (data/calls/gradium*, generator 'gradium');
              macOS `say` (generator 'say', a non-neural, free, local baseline). No ElevenLabs clip exists in the repo and the
              paid API is off limits, so that generator is NOT in the evaluation.
Owner files (never used): data/calls/qwen3tts/long_tech_scam.wav == ~/Downloads/data_calls_qwen3tts_long_tech_scam.wav.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FT = ROOT / "data" / "finetune"
REPO_DATA = Path("/Users/aarav/Downloads/tell/data/calls")   # the repo's own (gitignored) clips live in the main checkout
SR = 16_000
SEED = 20261107
N_REAL, N_FAKE = 5, 5     # utterances per LibriSpeech speaker, real and cloned
OWNER_HASHES = {
    "9b23e4d457f16669f4ad33a4b88570f0cde1c2e43062a645cdd16cd5b1040dfc",   # long_tech_scam (qwen3tts)
    "fdcee4d6ed16430e52749eb308cbc5675cf4d8242cd2925bd1cbb6849f3ed250",   # rough_morning (qwen3tts)
}
ARCHIVES = {
    "dev-clean": ("https://www.openslr.org/resources/12/dev-clean.tar.gz", "76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3"),
    "test-clean": ("https://www.openslr.org/resources/12/test-clean.tar.gz", "39fde525e59672dc6d1551919b1478f724438a95aa55f874b576be21967e6c23"),
}

CONVERSATIONAL = [
    "Hi, this is a quick call about your account. I just need to confirm a couple of details with you before we go any further today.",
    "Hey, it's me. I'm running about twenty minutes late, so could you tell the others to start dinner without me and save me a plate?",
    "Good afternoon, I'm calling from the front desk to remind you about your appointment on Thursday at ten thirty in the morning.",
    "I know this is sudden, but I got into a little trouble and I really need you to send some money right away, please don't tell anyone.",
    "We noticed some unusual activity on your card, and to protect you we need you to read back the six digit code we just texted.",
    "Thanks for holding. I looked into the delivery, and it looks like the package was left with a neighbour around three o'clock yesterday.",
    "Honestly, I think we should take the early train, because the weather is supposed to get worse after lunch and the roads will be slow.",
    "This is the tax office. There is a warrant issued in your name, and the only way to resolve it today is to pay by gift card.",
    "Can you grab milk and some bread on your way home? Also, if they have those good tomatoes, get a few, we're making pasta tonight.",
    "Hello, am I speaking with the homeowner? We're offering a free inspection this week, and it only takes about fifteen minutes of your time.",
    "I saw your message late last night, sorry. Yes, Saturday works for me, and I can bring the folding chairs and the big cooler as well.",
    "Your computer has been sending us error reports for several days, so I'm going to walk you through a quick fix, if you can sit at it now.",
    "Grandma, it's me, I'm in a bit of a bind and my phone is broken, so please don't worry, I just need a little help from you today.",
    "Alright, so the meeting got moved to Wednesday, the budget numbers are still not final, and Priya wants everyone to review the slides first.",
    "I'm sorry to bother you so early, but the landlord called about the leak in the kitchen and he says someone has to be home before noon.",
    "To keep your service active, please confirm your date of birth and the last four digits of your social security number right now.",
    "We've had a really lovely week, the kids finally learned to swim, and my brother says he might drive up for the long weekend after all.",
    "You have won a holiday for two, but to claim it we need a small processing fee, which you can pay over the phone with your debit card.",
    "Let me double check the schedule for you. The next opening is Tuesday afternoon, unless you would rather wait for a cancellation call.",
    "Please stay on the line, an officer will be with you shortly, and do not hang up or speak to anyone else about this case, understood?",
]

SAY_VOICES = ["Samantha", "Alex", "Daniel", "Karen", "Moira", "Tessa", "Fred", "Victoria", "Rishi", "Fiona"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def to_wav16(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(SR),
                    "-c:a", "pcm_s16le", str(dst)], check=True)


def dur(p: Path) -> float:
    import soundfile as sf
    i = sf.info(str(p))
    return i.frames / i.samplerate


def libri_utts(split: str) -> dict[str, list[tuple[Path, str]]]:
    """speaker -> [(flac path, transcript)] for one extracted LibriSpeech split."""
    base = FT / "raw" / ("dev" if split == "dev-clean" else "test") / "LibriSpeech" / split
    out: dict[str, list[tuple[Path, str]]] = {}
    for spk in sorted(base.iterdir(), key=lambda p: int(p.name)):
        for ch in sorted(spk.iterdir()):
            tr = {l.split(" ", 1)[0]: l.split(" ", 1)[1].strip() for l in (ch / f"{spk.name}-{ch.name}.trans.txt").read_text().splitlines()}
            for flac in sorted(ch.glob("*.flac")):
                out.setdefault(spk.name, []).append((flac, tr[flac.stem].lower().capitalize() + "."))
    return out


def plan() -> None:
    rng = random.Random(SEED)
    (FT / "src" / "real").mkdir(parents=True, exist_ok=True)
    manifest = {"archives": {k: {"url": v[0], "sha256": v[1], "licence": "CC BY 4.0", "attribution":
                "LibriSpeech corpus, Panayotov, Chen, Povey, Khudanpur, ICASSP 2015, https://www.openslr.org/12"} for k, v in ARCHIVES.items()},
                "files": []}
    for split, (_, want) in ARCHIVES.items():
        have = sha256(FT / "raw" / f"{split}.tar.gz")
        assert have == want, f"{split} archive hash mismatch {have}"
    jobs, rows = [], []
    book_pool: list[str] = []
    for split in ARCHIVES:
        utts = libri_utts(split)
        for spk, items in utts.items():
            ok = [(f, t) for f, t in items if 4.5 <= dur(f) <= 14.0]
            rng.shuffle(ok)
            ref, real_pick, rest = None, ok[:N_REAL], ok[N_REAL:]
            # reference for cloning: 5-9 s, distinct from the real picks
            cands = [(f, t) for f, t in rest if 5.0 <= dur(f) <= 9.0]
            ref = cands[0]
            for flac, _ in real_pick:
                dst = FT / "src" / "real" / f"ls{spk}" / f"{flac.stem}.wav"
                to_wav16(flac, dst)
                rows.append({"id": f"real_ls{spk}_{flac.stem}", "path": str(dst.relative_to(FT)), "label": 0, "generator": "human",
                             "speaker": f"ls{spk}", "split": split, "source_sha256": sha256(flac)})
                manifest["files"].append({"file": f"{split}/{spk}/{flac.name}", "sha256": sha256(flac), "role": "real"})
            ref_wav = FT / "src" / "ref" / f"ls{spk}.wav"
            to_wav16(ref[0], ref_wav)
            manifest["files"].append({"file": f"{split}/{spk}/{ref[0].name}", "sha256": sha256(ref[0]), "role": "clone_reference"})
            book_pool += [t for f, t in rest[:30] if 12 <= len(t.split()) <= 28 and f != ref[0]]
            jobs.append({"speaker": f"ls{spk}", "ref_wav": str(ref_wav), "ref_text": ref[1]})
    # texts: half conversational/scam sentences, half book sentences (from OTHER speakers' unused transcripts)
    rng.shuffle(book_pool)
    out_jobs = []
    for j in jobs:
        for k in range(N_FAKE):
            text = CONVERSATIONAL[rng.randrange(len(CONVERSATIONAL))] if k % 2 == 0 else book_pool.pop()
            out_jobs.append({"id": f"qwen_{j['speaker']}_{k}", "speaker": j["speaker"], "ref_wav": j["ref_wav"], "ref_text": j["ref_text"],
                             "text": text, "out": str(FT / "src" / "qwen" / j["speaker"] / f"{k}.wav")})
    # consented voice-talk reference voices (synthetic demo voices); 'sanath' is deliberately NOT cloned here
    vt = Path("/Users/aarav/Downloads/voice-talk/voices")
    for v in ("demo-say", "demo-say-imp"):
        consent = json.loads((vt / v / "consent.json").read_text())
        assert consent.get("attestation") and consent["voice"] == v, f"no consent for {v}"
        for k in range(N_FAKE * 2):
            out_jobs.append({"id": f"qwen_{v}_{k}", "speaker": v, "ref_wav": str(vt / v / "ref.wav"), "ref_text": (vt / v / "ref_text.txt").read_text().strip(),
                             "text": CONVERSATIONAL[(k * 3 + (v == "demo-say-imp")) % len(CONVERSATIONAL)] if k % 2 == 0 else book_pool.pop(),
                             "out": str(FT / "src" / "qwen" / v / f"{k}.wav")})
    (FT / "qwen_jobs.json").write_text(json.dumps(out_jobs, indent=1))
    (FT / "real_rows.json").write_text(json.dumps(rows, indent=1))
    (FT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(rows)} LibriSpeech real clips, {len(out_jobs)} qwen jobs, {len(jobs)} speakers")


def make_say(rows: list[dict]) -> None:
    """macOS `say`: free local non-neural TTS. One reading per voice x text; generator 'say'."""
    rng = random.Random(SEED + 1)
    d = FT / "src" / "say"
    d.mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(SAY_VOICES):
        for k in range(4):
            out = d / f"{v}_{k}.wav"
            if not out.exists():
                tmp = d / "tmp.aiff"
                subprocess.run(["say", "-v", v, "-o", str(tmp), CONVERSATIONAL[rng.randrange(len(CONVERSATIONAL))]], check=True)
                to_wav16(tmp, out)
                tmp.unlink()
            rows.append({"id": f"say_{v}_{k}", "path": str(out.relative_to(FT)), "label": 1, "generator": "say", "speaker": f"say_{v}",
                         "split": "local", "source_sha256": sha256(out)})


def finalize() -> None:
    rows = json.loads((FT / "real_rows.json").read_text())
    for j in json.loads((FT / "qwen_jobs.json").read_text()):
        p = Path(j["out"])
        if p.exists() and dur(p) >= 4.2:
            rows.append({"id": j["id"], "path": str(p.relative_to(FT)), "label": 1, "generator": "qwen", "speaker": j["speaker"],
                         "split": "local", "source_sha256": sha256(p)})
    # repo clips: Sanath real recordings, existing Qwen3-TTS clones of Sanath, Gradium clips
    skipped_owner = 0
    for sub, label, gen, spk in (("human/sanath", 0, "human", "sanath"), ("qwen3tts", 1, "qwen", "sanath"),
                                 ("gradium", 1, "gradium", "gradium_voice"), ("gradium_stock", 1, "gradium", "gradium_stock_voice")):
        for p in sorted((REPO_DATA / sub).glob("*.wav")):
            if ".opus8k" in p.name or ".g711" in p.name:
                continue
            h = sha256(p)
            if h in OWNER_HASHES:
                skipped_owner += 1
                continue
            dst = FT / "src" / "repo" / sub.replace("/", "_") / p.name
            to_wav16(p, dst)
            rows.append({"id": f"{gen}_{sub.replace('/', '_')}_{p.stem}", "path": str(dst.relative_to(FT)), "label": label, "generator": gen,
                         "speaker": spk, "split": "repo", "source_sha256": h})
    make_say(rows)
    with open(FT / "sources.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by.setdefault((r["label"], r["generator"]), []).append(r["speaker"])
    for k, v in sorted(by.items()):
        print(k, "clips", len(v), "speakers", len(set(v)))
    print("owner files skipped from repo dirs:", skipped_owner)


if __name__ == "__main__":
    {"plan": plan, "finalize": finalize}[sys.argv[1]]()
