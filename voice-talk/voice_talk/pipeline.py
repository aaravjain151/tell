"""Real-time orchestration: chunker -> translate -> synthesize -> emit, strictly ordered.

Two single-consumer stages (so chunk n+1 translates while chunk n is being spoken, but
audio is produced one chunk at a time, in order, never overlapping). `stop()` bumps a
generation counter and drains the queues; in-flight thread work is discarded on return.
A failure in one chunk is reported and the session carries on.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import numpy as np

from .chunker import Chunker
from .languages import disclosure_line, lang_name
from .stt import MicSegmenter
from .voices import ConsentError, VoiceStore

Emit = Callable[[dict, "bytes | None"], Awaitable[None]]


class DisclosureError(PermissionError):
    pass


@dataclass
class SessionConfig:
    voice: str
    source: str = "en"
    target: str = "es"
    disclosure: bool = True
    disclosure_ack: bool = False  # "everyone who will hear this knows it is an AI-translated voice"
    save_audio: bool = False


@dataclass
class Job:
    seq: int
    gen: int
    text: str
    t_in: float
    fixed: bool = False
    translated: str = ""
    t_translated: float = 0.0
    translate_s: float = 0.0


def pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


class Session:
    def __init__(self, cfg: SessionConfig, translator, synth, voices: VoiceStore, emit: Emit,
                 stt=None, outputs_dir: Path | None = None, clock=time.monotonic):
        self.cfg, self.translator, self.synth, self.voices = cfg, translator, synth, voices
        self.emit, self.stt, self.clock = emit, stt, clock
        self.outputs_dir = outputs_dir
        # Cap the FIRST chunk so the opening clause is short -> first audio starts
        # sooner (qwen-tts has no streaming output, so time-to-first-audio is the
        # synthesis time of the first chunk). Later chunks use the normal size.
        self.chunker = Chunker(first_max_chars=60)
        self.gen = 0
        self.seq = 0
        self.inflight = 0
        self._q_tr: asyncio.Queue = asyncio.Queue()
        self._q_tts: asyncio.Queue = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._mic: MicSegmenter | None = None
        self._save_dir: Path | None = None
        self._state = ""

    # -- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        cfg = self.cfg
        lang_name(cfg.source), lang_name(cfg.target)
        if not cfg.disclosure and not cfg.disclosure_ack:
            raise DisclosureError(
                "the spoken AI-voice disclosure can only be turned off after confirming that everyone "
                "who will hear this knows it is an AI-translated voice")
        ref_path, ref_text = self.voices.require_usable(cfg.voice)  # consent gate (raises ConsentError)
        await asyncio.to_thread(self.synth.prepare_voice, cfg.voice, ref_path, ref_text)
        if cfg.save_audio and self.outputs_dir is not None:
            self._save_dir = Path(self.outputs_dir) / time.strftime("%Y%m%d-%H%M%S")
        self._tasks = [asyncio.create_task(self._translate_loop()), asyncio.create_task(self._synth_loop())]
        await self.emit({"type": "started", "voice": cfg.voice, "source": cfg.source, "target": cfg.target,
                         "disclosure": cfg.disclosure}, None)
        await self._set_state("ready")
        if cfg.disclosure:
            self._submit(disclosure_line(cfg.target), fixed=True)

    async def close(self) -> None:
        self.gen += 1
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def stop(self) -> None:
        """Cancel everything queued or running; speech stops, session stays usable."""
        self.gen += 1
        for q in (self._q_tr, self._q_tts):
            while not q.empty():
                q.get_nowait()
        self.inflight = 0
        self.chunker.reset()
        self._mic = None
        await self.emit({"type": "stopped"}, None)
        await self._set_state("ready")

    # -- input -------------------------------------------------------------
    def feed_text(self, text: str) -> None:
        for c in self.chunker.feed(text):
            self._submit(c)

    def flush(self) -> None:
        for c in self.chunker.flush():
            self._submit(c)

    def mic_start(self, mode: str = "open") -> None:
        self._mic = MicSegmenter(mode=mode)

    async def feed_audio(self, pcm: bytes) -> None:
        if self._mic is not None:
            for utt in self._mic.feed(pcm):
                await self._transcribe(utt)

    async def mic_end(self) -> None:
        if self._mic is not None:
            utts, self._mic = self._mic.finish(), None
            for utt in utts:
                await self._transcribe(utt)

    async def _transcribe(self, audio: np.ndarray) -> None:
        gen = self.gen
        if self.stt is None:
            await self.emit({"type": "error", "code": "stt_unavailable", "message": "speech input is not available"}, None)
            return
        try:
            text = await asyncio.to_thread(self.stt.transcribe, audio, self.cfg.source)
        except Exception as e:
            await self.emit({"type": "error", "code": "stt_failed", "message": str(e)}, None)
            return
        if gen != self.gen or not text.strip():
            return
        self.feed_text(text.strip() + " ")
        self.flush()  # an utterance boundary is a flush point

    # -- internals ---------------------------------------------------------
    def _submit(self, text: str, fixed: bool = False) -> None:
        self.seq += 1
        self.inflight += 1
        self._q_tr.put_nowait(Job(self.seq, self.gen, text, self.clock(), fixed=fixed))
        asyncio.get_running_loop().create_task(self._set_state("speaking"))

    async def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            await self.emit({"type": "state", "state": state}, None)

    async def _finish(self, job: Job) -> None:
        if job.gen == self.gen:
            self.inflight = max(0, self.inflight - 1)
            if self.inflight == 0:
                await self._set_state("ready")

    async def _translate_loop(self) -> None:
        while True:
            job: Job = await self._q_tr.get()
            if job.gen != self.gen:
                continue
            try:
                if job.fixed:
                    job.translated = job.text
                    await self.emit({"type": "disclosure", "seq": job.seq, "text": job.text}, None)
                else:
                    await self.emit({"type": "source", "seq": job.seq, "text": job.text}, None)
                    t0 = self.clock()
                    job.translated = await asyncio.to_thread(
                        self.translator.translate, job.text, self.cfg.source, self.cfg.target)
                    job.translate_s = self.clock() - t0
                    if job.gen != self.gen:
                        continue
                    await self.emit({"type": "translation", "seq": job.seq, "text": job.translated}, None)
                job.t_translated = self.clock()
                self._q_tts.put_nowait(job)
            except Exception as e:
                if job.gen == self.gen:
                    await self.emit({"type": "error", "code": "translate_failed", "seq": job.seq, "message": str(e)}, None)
                    await self._finish(job)

    async def _synth_loop(self) -> None:
        lang = lang_name(self.cfg.target)
        while True:
            job: Job = await self._q_tts.get()
            if job.gen != self.gen:
                continue
            try:
                t0 = self.clock()
                audio, sr = await asyncio.to_thread(self.synth.synthesize, job.translated, lang, self.cfg.voice)
                t1 = self.clock()
                if job.gen != self.gen:
                    continue
                dur = len(audio) / float(sr)
                metrics = {
                    "translate_ms": round(job.translate_s * 1000),
                    "synth_ms": round((t1 - t0) * 1000),
                    "audio_s": round(dur, 2),
                    "rtf": round((t1 - t0) / dur, 2) if dur > 0 else None,
                    "first_audio_ms": round((t1 - job.t_in) * 1000),
                }
                await self.emit({"type": "audio", "seq": job.seq, "sample_rate": sr, "samples": int(len(audio)),
                                 "format": "pcm_s16le", "disclosure": job.fixed}, pcm16(audio))
                await self.emit({"type": "chunk_done", "seq": job.seq, "metrics": metrics}, None)
                if self._save_dir is not None:
                    await asyncio.to_thread(self._save, job.seq, audio, sr)
            except Exception as e:
                if job.gen == self.gen:
                    await self.emit({"type": "error", "code": "synth_failed", "seq": job.seq, "message": str(e)}, None)
            finally:
                await self._finish(job)

    def _save(self, seq: int, audio: np.ndarray, sr: int) -> None:
        import soundfile as sf
        self._save_dir.mkdir(parents=True, exist_ok=True)
        sf.write(self._save_dir / f"{seq:03d}.wav", audio, sr)
