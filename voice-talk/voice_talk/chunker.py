"""Incremental sentence/clause chunker.

feed(text) returns the chunks that are complete so far; flush() releases whatever is
left (used on pause, stop, or end of input). A chunk is emitted as soon as a sentence
end, or a clause end once the clause is long enough, has been seen.
"""
from __future__ import annotations

ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "mt", "gen", "col", "sgt",
    "capt", "lt", "rev", "hon", "fig", "no", "inc", "ltd", "co", "corp", "dept", "approx",
    "e.g", "i.e", "a.m", "p.m", "u.s", "u.k", "ph.d", "jan", "feb", "mar", "apr", "jun",
    "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
SENT_END = ".!?…。！？"
CJK_SENT_END = "。！？…"
TRAILING = "\"'”’)]」』»"
CLAUSE = ",;:—–，、；："
CJK_CLAUSE = "，、；："


def _is_abbreviation(buf: str, i: int) -> bool:
    j = i
    while j > 0 and not buf[j - 1].isspace():
        j -= 1
    word = buf[j:i].lstrip("([\"'“‘").lower()
    if not word:
        return False
    if word in ABBREVIATIONS:
        return True
    if len(word) == 1 and word.isalpha():  # initials: "J. Smith"
        return True
    if "." in word and all(len(p) <= 2 for p in word.split(".")):  # "u.s", "e.g"
        return True
    return False


class Chunker:
    def __init__(self, min_clause_chars: int = 18, max_chars: int = 180, first_max_chars: int | None = None,
                 min_chunk_chars: int = 0):
        self.min_clause_chars = min_clause_chars
        # after the first chunk, merge sentences shorter than this into the next one: fewer, longer TTS calls (each call
        # has fixed overhead, so tiny chunks synthesize slower than they play and leave silent gaps). 0 = off.
        self.min_chunk_chars = min_chunk_chars
        self.max_chars = max_chars
        self.first_max_chars = first_max_chars  # optional: cap the FIRST chunk after a flush/reset (faster first audio)
        self._first = True
        self._buf = ""

    @property
    def pending(self) -> str:
        return self._buf

    def reset(self) -> None:
        self._buf = ""
        self._first = True

    def feed(self, text: str) -> list[str]:
        self._buf += text
        return self._drain(final=False)

    def flush(self) -> list[str]:
        out = self._drain(final=True)
        rest = self._buf.strip()
        self._buf = ""
        self._first = True
        if rest:
            out.append(rest)
        return out

    # -- internals ---------------------------------------------------------
    def _drain(self, final: bool) -> list[str]:
        out: list[str] = []
        while True:
            cut = self._find_cut(self._buf, final)
            if cut is None:
                break
            piece, self._buf = self._buf[:cut], self._buf[cut:]
            piece = piece.strip()
            if piece:
                out.append(piece)
                self._first = False
        return out

    def _find_cut(self, buf: str, final: bool) -> int | None:
        cut = self._find_cut_raw(buf, final)
        fm = self.first_max_chars if self._first else None
        if fm and len(buf) > fm and (cut is None or cut > fm + 1):
            k = buf.rfind(" ", 0, fm)  # a long first chunk: cut at a word boundary so speech starts sooner
            return k + 1 if k > 0 else fm
        if cut is not None and self.min_chunk_chars and not self._first:
            while len(buf[:cut].strip()) < self.min_chunk_chars:
                nxt = self._find_cut_raw(buf[cut:], final)
                if nxt is None:
                    return len(buf) if final else None  # wait for more text (on flush: one last chunk with everything left)
                cut += nxt
        return cut

    def _find_cut_raw(self, buf: str, final: bool) -> int | None:
        n = len(buf)
        i = 0
        while i < n:
            ch = buf[i]
            if ch in SENT_END:
                j = i + 1
                while j < n and (buf[j] in SENT_END or buf[j] in TRAILING):
                    j += 1
                if ch in CJK_SENT_END:
                    return self._with_space(buf, j)
                if j >= n:
                    if final:
                        return None  # flush() takes the remainder
                    break  # wait: "3." may become "3.5"
                if not buf[j].isspace():
                    i = j
                    continue  # decimal, domain, "e.g.x"
                if ch == "." and j == i + 1 and _is_abbreviation(buf, i):
                    i = j
                    continue
                return self._with_space(buf, j)
            if ch in CLAUSE and len(buf[: i + 1].strip()) >= self.min_clause_chars:
                if ch in CJK_CLAUSE:
                    return self._with_space(buf, i + 1)
                if i + 1 < n and buf[i + 1].isspace():
                    return self._with_space(buf, i + 1)
            i += 1
        limit = self.first_max_chars if (self._first and self.first_max_chars) else self.max_chars
        if n > limit:
            k = buf.rfind(" ", 0, limit)
            return k + 1 if k > 0 else limit
        return None

    @staticmethod
    def _with_space(buf: str, j: int) -> int:
        while j < len(buf) and buf[j].isspace():
            j += 1
        return j
