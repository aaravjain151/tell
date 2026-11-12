"""Conversation mode: you speak or type, a local chat LLM answers, the answer is spoken in the reference voice.

user text -> History -> ChatLLM.stream -> SpokenFilter -> Session (Chunker -> [Translator] -> Qwen3-TTS -> PCM)

The existing Session does the chunking, ordering, consent gate, spoken disclosure and cancellation; this class adds
the LLM turn loop, per-turn timings and barge-in. Barge-in (voice over the bot, Esc, or an `interrupt` message)
cancels the in-flight generation and everything queued for speech. History is RAM only and wiped on close().
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .chat import History, SpokenFilter
from .demo import CachedSynth, CallRecorder, DemoCall, load_demo
from .languages import lang_name
from .personas import load_persona, system_prompt
from .pipeline import Session, SessionConfig
from .stt import MicSegmenter

BARGE_RMS = 0.04       # mic level that counts as the user speaking over the bot
BARGE_SAMPLES = 3200   # 0.2 s of that, at 16 kHz
MIN_CHUNK_CHARS = 60   # after the first chunk, merge short sentences: fewer TTS calls, fewer silent gaps between them


class PassthroughTranslator:
    """Same-language chat: the reply is spoken as written."""

    def translate(self, text: str, source: str, target: str) -> str:
        return text


@dataclass
class ConverseConfig:
    voice: str
    lang: str = "en"
    translate_to: str | None = None  # optional: speak the reply translated into this language
    persona: str = "friendly"
    disclosure: bool = True
    disclosure_ack: bool = False
    save_audio: bool = False
    demo: str | None = None      # attacker-demo persona (voice_talk/personas/demo/<name>.md); None = normal converse
    demo_auto: bool = True       # advance the stage by turn count (the Escalate control always works)
    prerecord: bool = False      # synthesize the next stage's canned line ahead of time
    save_call: bool = False      # write the whole call to qa_out/<run>/call.wav + label.json


@dataclass
class Turn:
    id: int
    t0: float
    stt_ms: int | None = None
    t_first_tok: float | None = None
    t_first_audio: float | None = None
    synth_ms: int = 0
    audio_s: float = 0.0
    text: str = ""
    gen_done: bool = False
    cancelled: bool = False
    reported: bool = False
    task: asyncio.Task | None = None
    cancel_evt: threading.Event | None = None
    stage: int | None = None
    source: str = "llm"


class ConverseSession:
    def __init__(self, cfg: ConverseConfig, chat, translator, synth, voices, emit, stt=None,
                 outputs_dir: Path | None = None, clock=time.monotonic, history_turns: int = 10,
                 personas_dir: Path | None = None, qa_dir: Path | None = None, demo_dir: Path | None = None):
        self.cfg, self.chat, self.emit, self.stt, self.clock = cfg, chat, emit, stt, clock
        self.demo: DemoCall | None = None
        self.cached: CachedSynth | None = None
        self.recorder: CallRecorder | None = None
        self.qa_dir = qa_dir
        self.saved_path: Path | None = None
        self.latencies: list[dict] = []
        self.models = {"llm": getattr(chat, "model", "?")}
        if cfg.demo:
            self.demo = DemoCall(load_demo(cfg.demo, demo_dir), auto=cfg.demo_auto)
            self.persona = {"name": cfg.demo, "title": self.demo.persona.title, "prompt": ""}
            synth = self.cached = CachedSynth(synth)
            if cfg.save_call:
                self.recorder = CallRecorder(clock)
        else:
            self.persona = load_persona(cfg.persona, personas_dir)
        self.synth_name = type(synth).__name__
        self.history = History(history_turns)
        self.target = cfg.translate_to or cfg.lang
        tr = translator if (cfg.translate_to and cfg.translate_to != cfg.lang) else PassthroughTranslator()
        self.session = Session(
            SessionConfig(voice=cfg.voice, source=cfg.lang, target=self.target, disclosure=cfg.disclosure,
                          disclosure_ack=cfg.disclosure_ack, save_audio=cfg.save_audio),
            tr, synth, voices, self._on_emit, stt=None, outputs_dir=outputs_dir, clock=clock)
        self._bg: set[asyncio.Task] = set()
        if not self.demo:  # staged demo calls chunk their own (guarded) lines
            self.session.chunker.min_chunk_chars = MIN_CHUNK_CHARS
        self._turn: Turn | None = None
        self._turn_no = 0
        self._disc: set[int] = set()
        self._mic: MicSegmenter | None = None
        self._loud = 0

    # -- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        lang_name(self.cfg.lang)
        await self.session.start()
        warm = getattr(self.chat, "warm", None)
        if warm:  # fire and forget: load the chat model while the disclosure is being spoken
            asyncio.get_running_loop().run_in_executor(None, warm)
        if self.demo:
            await self.emit({**self.demo.info("start"), "type": "stage"}, None)
            line = self.demo.stage.lines[0]
            # the opener is always cached before the call starts: it is the first thing the audience hears
            await asyncio.to_thread(self._safe_prerecord, line, lang_name(self.target))
            self._prerecord_next()
            self._spawn(self._canned_turn(self.demo.take_lead()))
        elif self.persona.get("opener"):  # free-form personas (e.g. redteam_attacker) can open the call too
            await self._open_with(self.persona["opener"])

    async def _open_with(self, text: str) -> None:
        """Bot-first personas: speak the scripted opener (queued after any spoken disclosure). Not a Turn: no model call,
        and history stays user-first; system_prompt() tells the model what it already said."""
        await self.emit({"type": "bot_delta", "turn": 0, "text": text}, None)
        self.session.feed_text(text + " ")
        self.session.flush()
        await self.emit({"type": "bot_done", "turn": 0}, None)

    async def close(self) -> None:
        await self._cancel_turn()
        for t in list(self._bg):
            t.cancel()
        await self.session.close()
        if self.recorder is not None and self.demo is not None and self.qa_dir is not None:
            try:
                self.saved_path = await asyncio.to_thread(
                    self.recorder.save, self.qa_dir, self.demo.persona, self.cfg.voice,
                    {**self.models, "tts": self.synth_name}, self.latencies, self.cfg.disclosure)
                if self.saved_path:
                    await self.emit({"type": "saved", "path": str(self.saved_path)}, None)
            except Exception:
                pass
        self.history.clear()  # End session wipes the conversation
        self._mic = None

    async def interrupt(self, reason: str = "user") -> None:
        """Barge-in: cancel generation and all queued speech. The session stays usable."""
        t = self._turn
        await self._cancel_turn()
        await self.session.stop()
        if t is not None:
            await self.emit({"type": "interrupted", "turn": t.id, "reason": reason}, None)
        await self._apply_stage()

    stop = interrupt

    # -- attacker demo -------------------------------------------------------
    def _spawn(self, coro) -> None:
        t = asyncio.get_running_loop().create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    def _prerecord(self, text: str) -> None:
        if self.cached is None:
            return
        lang = lang_name(self.target)
        asyncio.get_running_loop().run_in_executor(None, self._safe_prerecord, text, lang)

    def _safe_prerecord(self, text: str, lang: str) -> None:
        try:
            self.cached.prerecord(text, lang, self.cfg.voice)
        except Exception:
            pass  # a failed pre-record only costs latency later

    def _prerecord_next(self) -> None:
        d = self.demo
        if d and self.cfg.prerecord and not d.last:
            self._prerecord(d.persona.stages[d.idx + 1].lines[0])

    async def escalate(self) -> None:
        """The presenter's Escalate control: go to the next stage (applied between lines, then the stage's lead line is spoken)."""
        if not self.demo:
            await self.emit({"type": "error", "code": "bad_message", "message": "'escalate' needs an attacker-demo session"}, None)
            return
        if not self.demo.request_escalate():
            await self.emit(self.demo.info("final stage already"), None)
            return
        await self.emit(self.demo.info("escalate requested"), None)
        if not self._busy():
            await self._apply_stage()

    async def _apply_stage(self) -> None:
        d = self.demo
        if not d or self._busy():
            return
        p = d.apply_pending()
        if not p:
            return
        await self.emit(d.info(p["reason"]), None)
        if self.recorder:
            self.recorder.event("stage", f"stage {d.stage.n}: {d.stage.name} ({p['reason']})", d.stage.n)
        self._prerecord_next()
        if p["speak"]:
            self._spawn(self._canned_turn(d.take_lead()))

    async def _canned_turn(self, text: str) -> None:
        """Speak a fixed line as a bot turn (opener, or the lead line of a new stage). No LLM call."""
        if self._busy():
            return
        self._turn_no += 1
        turn = Turn(self._turn_no, self.clock(), stage=self.demo.stage.n if self.demo else None, source="canned")
        self._turn = turn
        turn.cancel_evt = threading.Event()
        await self._speak_piece(turn, text + " ")
        self.session.flush()
        turn.gen_done = True
        if self.demo:
            self.demo.note_bot_turn()
        if turn.text.strip():
            self.history.add("assistant", turn.text.strip())  # (dropped by History if no user turn came first)
        await self.emit({"type": "bot_done", "turn": turn.id}, None)
        await self._maybe_report()

    # -- input -------------------------------------------------------------
    async def say(self, text: str, stt_ms: int | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._busy():  # (not session.inflight: that would also cut off the spoken disclosure)
            await self._cancel_turn()
            await self.session.stop()
        self._turn_no += 1
        turn = Turn(self._turn_no, self.clock(), stt_ms=stt_ms)
        self._turn = turn
        if self.demo:
            await self._apply_stage()
            turn.stage = self.demo.stage.n
            if self.recorder:
                self.recorder.event("presenter", text, turn.stage)
        self.history.add("user", text)
        await self.emit({"type": "user", "turn": turn.id, "text": text, "stt_ms": stt_ms}, None)
        turn.task = asyncio.create_task(self._run_turn(turn))

    # compatibility with the translate-mode message names
    def feed_text(self, text: str) -> None:
        asyncio.get_running_loop().create_task(self.say(text))

    def mic_start(self, mode: str = "open") -> None:
        self._mic = MicSegmenter(mode=mode)
        self._loud = 0

    async def feed_audio(self, pcm: bytes) -> None:
        x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if x.size and self._busy():
            if float(np.sqrt((x ** 2).mean())) > BARGE_RMS:
                self._loud += x.size
                if self._loud >= BARGE_SAMPLES:
                    self._loud = 0
                    await self.interrupt("voice")
            else:
                self._loud = 0
        if self._mic is not None:
            for utt in self._mic.feed(pcm):
                await self._transcribe(utt)

    async def mic_end(self) -> None:
        if self._mic is not None:
            utts, self._mic = self._mic.finish(), None
            for utt in utts:
                await self._transcribe(utt)

    async def _transcribe(self, audio: np.ndarray) -> None:
        if self.stt is None:
            await self.emit({"type": "error", "code": "stt_unavailable", "message": "speech input is not available"}, None)
            return
        t0 = self.clock()
        try:
            text = await asyncio.to_thread(self.stt.transcribe, audio, self.cfg.lang)
        except Exception as e:
            await self.emit({"type": "error", "code": "stt_failed", "message": str(e)}, None)
            return
        await self.say(text, stt_ms=round((self.clock() - t0) * 1000))

    # -- turn loop ---------------------------------------------------------
    def _busy(self) -> bool:
        t = self._turn
        return t is not None and not t.reported and not t.cancelled

    async def _cancel_turn(self) -> None:
        t = self._turn
        if t is None:
            return
        t.cancelled = True
        if t.cancel_evt:
            t.cancel_evt.set()
        if t.task and not t.task.done():
            t.task.cancel()
            await asyncio.gather(t.task, return_exceptions=True)

    async def _run_turn(self, turn: Turn) -> None:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        turn.cancel_evt = cancel = threading.Event()
        demo = self.demo
        if demo:
            sysmsg = demo.system_prompt(lang_name(self.cfg.lang))
        else:
            sysmsg = system_prompt(self.persona, lang_name(self.cfg.lang))
        msgs = [{"role": "system", "content": sysmsg}] + self.history.messages()
        lead = demo.take_lead() if demo and demo.lead_pending else None
        if lead:
            turn.source = "canned"

        def put(item):
            try:
                loop.call_soon_threadsafe(q.put_nowait, item)
            except RuntimeError:  # loop already closed
                pass

        def produce():
            try:
                src = iter([lead]) if lead else self.chat.stream(msgs)
                if demo and not lead:
                    src = demo.guard_stream(src)
                for d in src:
                    if cancel.is_set():
                        break
                    put(("d", d))
                put(("end", None))
            except Exception as e:
                put(("err", str(e)))

        filt = SpokenFilter()
        try:
            loop.run_in_executor(None, produce)
            while True:
                kind, val = await q.get()
                if turn.cancelled:
                    return
                if kind == "err":
                    await self.emit({"type": "error", "code": "llm_failed", "message": val}, None)
                    break
                if kind == "end":
                    break
                if turn.t_first_tok is None:
                    turn.t_first_tok = self.clock()
                await self._speak_piece(turn, filt.feed(val))
            if not turn.cancelled:
                await self._speak_piece(turn, filt.finish())
                self.session.flush()
                turn.gen_done = True
                if demo:
                    demo.note_bot_turn()
                    if not lead:
                        turn.source = demo.report.source
                await self.emit({"type": "bot_done", "turn": turn.id}, None)
                await self._maybe_report()
        finally:
            cancel.set()
            if turn.text.strip():
                self.history.add("assistant", turn.text.strip())

    async def _speak_piece(self, turn: Turn, piece: str) -> None:
        if not piece:
            return
        turn.text += piece
        await self.emit({"type": "bot_delta", "turn": turn.id, "text": piece}, None)
        self.session.feed_text(piece)

    # -- events from the speech session ------------------------------------
    async def _on_emit(self, msg: dict, binary: bytes | None = None) -> None:
        t, turn = msg.get("type"), self._turn
        if t == "started":
            msg = {**msg, "mode": "converse", "lang": self.cfg.lang, "persona": self.cfg.persona, "translate_to": self.cfg.translate_to}
            if self.demo:
                msg.update(demo=self.cfg.demo, test_attacker=self.demo.persona.attacker, label=self.demo.persona.label,
                           stages=len(self.demo.persona.stages), expected_tier=self.demo.persona.tier,
                           save_call=bool(self.recorder))
        elif t == "disclosure":
            self._disc.add(msg["seq"])
        elif t == "audio" and not msg.get("disclosure") and turn and turn.t_first_audio is None and not turn.cancelled:
            turn.t_first_audio = self.clock()
        elif t == "chunk_done" and turn and not turn.cancelled and msg["seq"] not in self._disc:
            turn.synth_ms += msg["metrics"]["synth_ms"]
            turn.audio_s += msg["metrics"]["audio_s"]
        if t == "audio" and binary is not None and self.recorder is not None:
            self.recorder.add_pcm(binary, msg["sample_rate"], (turn.stage if turn and turn.stage else 0))
        await self.emit(msg, binary)
        if t == "state" and msg.get("state") == "ready":
            await self._maybe_report()

    async def _maybe_report(self) -> None:
        t = self._turn
        if t is None or t.reported or t.cancelled or not t.gen_done or self.session.inflight:
            return
        t.reported = True
        ms = lambda a: None if a is None else round((a - t.t0) * 1000)  # noqa: E731
        info = {"type": "turn", "turn": t.id, "stt_ms": t.stt_ms,
                "llm_first_token_ms": ms(t.t_first_tok), "tts_first_audio_ms": ms(t.t_first_audio),
                "synth_ms": t.synth_ms, "audio_s": round(t.audio_s, 2),
                "rtf": round(t.synth_ms / 1000 / t.audio_s, 2) if t.audio_s > 0 else None}
        if self.demo:
            info.update(stage=t.stage, source=t.source, cache_hits=self.cached.hits if self.cached else 0)
            self.latencies.append({k: info[k] for k in ("turn", "stage", "source", "llm_first_token_ms", "tts_first_audio_ms")})
            if self.recorder:
                self.recorder.event("bot", t.text.strip(), t.stage, at=t.t0)
        await self.emit(info, None)
        if self.demo:
            await self._apply_stage()
