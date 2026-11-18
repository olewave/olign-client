"""An alignment result, and the files you can make from it.

Times are seconds from the start of the audio. Scores are 0 to 100, or None
when the API does not send them.
"""

from __future__ import annotations

import csv
import io
import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterator, List, Optional, Union

PathLike = Union[str, "os.PathLike[str]"]


@dataclass
class Phone:
    ph: str
    begin: float
    end: float
    score: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Phone":
        return cls(ph=d["ph"], begin=float(d["begin"]), end=float(d["end"]), score=d.get("score"))

    def to_dict(self) -> dict:
        out: dict = {"ph": self.ph, "begin": self.begin, "end": self.end}
        if self.score is not None:
            out["score"] = self.score
        return out


@dataclass
class Word:
    word: str
    begin: float
    end: float
    score: Optional[float] = None
    phones: List[Phone] = field(default_factory=list)
    spoken: bool = True
    annotation: bool = False
    untranscribed: bool = False  # heard but not in your transcript (align_untranscribed=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(word=d["word"], begin=float(d["begin"]), end=float(d["end"]), score=d.get("score"),
                   phones=[Phone.from_dict(p) for p in d.get("phones") or []],
                   spoken=bool(d.get("spoken", True)), annotation=bool(d.get("annotation", False)),
                   untranscribed=bool(d.get("untranscribed", False)))

    def to_dict(self) -> dict:
        out: dict = {"word": self.word, "begin": self.begin, "end": self.end}
        if self.score is not None:
            out["score"] = self.score
        out["phones"] = [p.to_dict() for p in self.phones]
        if not self.spoken:
            out["spoken"] = False
        if self.annotation:
            out["annotation"] = True
        if self.untranscribed:
            out["untranscribed"] = True
        return out

    @property
    def timed(self) -> bool:
        """True for a spoken word with a duration: one that belongs on a timeline."""
        return self.spoken and not self.annotation and self.end > self.begin


@dataclass
class Pause:
    """A stretch of 0.05 s or more that no word covers: silence, a breath, a noise."""
    begin: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.begin

    @classmethod
    def from_dict(cls, d: dict) -> "Pause":
        return cls(begin=float(d["begin"]), end=float(d["end"]))

    def to_dict(self) -> dict:
        return {"begin": self.begin, "end": self.end}


@dataclass
class Phrase:
    """Words between pauses of 0.1 s or more. ``first`` and ``last`` are
    positions in :attr:`Result.words`, both included."""
    begin: float
    end: float
    first: int
    last: int

    @classmethod
    def from_dict(cls, d: dict) -> "Phrase":
        first, last = d["words"]
        return cls(begin=float(d["begin"]), end=float(d["end"]), first=int(first), last=int(last))

    def to_dict(self) -> dict:
        return {"begin": self.begin, "end": self.end, "words": [self.first, self.last]}


@dataclass
class Result:
    """One olign job. ``words`` is empty until ``state`` is ``done``."""

    job_id: Optional[str] = None
    state: str = "done"
    audio_seconds: Optional[float] = None
    transcript_source: Optional[str] = None
    words: List[Word] = field(default_factory=list)
    pauses: List[Pause] = field(default_factory=list)
    phrases: List[Phrase] = field(default_factory=list)
    progress: Optional[float] = None
    error: Optional[str] = None
    api_version: Optional[str] = None
    olign_version: Optional[str] = None

    # -- reading -------------------------------------------------------------

    @classmethod
    def from_dict(cls, d: dict, headers: Optional[dict] = None) -> "Result":
        """Build a Result from a job status response, or from what
        :meth:`to_json` or the API saved. Fields the client does not use are
        ignored."""
        h = {k.lower(): v for k, v in (headers or {}).items()}
        saved = {k.lower(): v for k, v in (d.get("_versions") or {}).items()}
        result = d.get("result") or {}
        progress = d.get("progress")
        return cls(
            job_id=d.get("job_id"),
            state=d.get("state", "done"),
            audio_seconds=None if d.get("audio_seconds") is None else float(d["audio_seconds"]),
            transcript_source=d.get("transcript_source"),
            words=[Word.from_dict(w) for w in result.get("words") or []],
            pauses=[Pause.from_dict(p) for p in result.get("pauses") or []],
            phrases=[Phrase.from_dict(p) for p in result.get("phrases") or []],
            progress=None if progress is None else float(progress),
            error=d.get("error"),
            api_version=h.get("x-olign-api-version") or saved.get("x-olign-api-version"),
            olign_version=h.get("x-olign-version") or saved.get("x-olign-version"),
        )

    @classmethod
    def load(cls, path: PathLike) -> "Result":
        """Read a result saved as JSON."""
        return cls.from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    @property
    def done(self) -> bool:
        return self.state == "done"

    @property
    def text(self) -> str:
        """The spoken words, joined by spaces."""
        return " ".join(w.word for w in self.words if w.spoken and not w.annotation)

    @property
    def duration(self) -> float:
        """The audio length, or the end of the last word when it is unknown."""
        if self.audio_seconds is not None:
            return self.audio_seconds
        return max((w.end for w in self.words), default=0.0)

    def timed_words(self) -> Iterator[Word]:
        return (w for w in self.words if w.timed)

    def phrase_words(self, phrase: Phrase) -> List[Word]:
        """The words of one of :attr:`phrases`."""
        return self.words[phrase.first:phrase.last + 1]

    # -- writing -------------------------------------------------------------

    def to_json(self, path: Optional[PathLike] = None, indent: int = 1) -> str:
        """The job's public fields and its words, in the API's own shape, so
        :meth:`load` reads it back."""
        d: dict = {"job_id": self.job_id, "state": self.state, "audio_seconds": self.audio_seconds,
                   "transcript_source": self.transcript_source,
                   "result": {"words": [w.to_dict() for w in self.words],
                              "pauses": [p.to_dict() for p in self.pauses],
                              "phrases": [p.to_dict() for p in self.phrases]}}
        if self.error:
            d["error"] = self.error
        versions = {k: v for k, v in (("X-Olign-Api-Version", self.api_version),
                                      ("X-Olign-Version", self.olign_version)) if v}
        if versions:
            d["_versions"] = versions
        return _out(json.dumps(d, indent=indent, ensure_ascii=False) + "\n", path)

    def to_csv(self, path: Optional[PathLike] = None, phones: bool = False) -> str:
        """One row per word. With ``phones=True``, one row per phone."""
        buf = io.StringIO()
        out = csv.writer(buf, lineterminator="\n")
        if phones:
            out.writerow(["word_index", "word", "phone", "begin", "end", "score"])
            for i, w in enumerate(self.words):
                for p in w.phones:
                    out.writerow([i, w.word, p.ph, _num(p.begin), _num(p.end), _opt(p.score)])
        else:
            out.writerow(["index", "word", "begin", "end", "score", "spoken"])
            for i, w in enumerate(self.words):
                out.writerow([i, w.word, _num(w.begin), _num(w.end), _opt(w.score), str(w.spoken).lower()])
        return _out(buf.getvalue(), path)

    def to_textgrid(self, path: Optional[PathLike] = None) -> str:
        """A Praat TextGrid with a words, a phones and a pauses tier. The
        gaps between intervals become empty ones, as Praat requires."""
        xmax = self.duration
        words = list(self.timed_words())
        tiers = {
            "words": [(w.begin, w.end, w.word) for w in words],
            "phones": [(p.begin, p.end, p.ph) for w in words for p in w.phones if p.end > p.begin],
            "pauses": [(p.begin, p.end, "pause") for p in self.pauses if p.end > p.begin],
        }
        lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "",
                 "xmin = 0", f"xmax = {_num(xmax)}", "tiers? <exists>", f"size = {len(tiers)}", "item []:"]
        for n, (name, spans) in enumerate(tiers.items(), 1):
            iv = _fill(spans, xmax)
            lines += [f"    item [{n}]:", '        class = "IntervalTier"', f'        name = "{name}"',
                      "        xmin = 0", f"        xmax = {_num(xmax)}", f"        intervals: size = {len(iv)}"]
            for k, (b, e, label) in enumerate(iv, 1):
                text = label.replace('"', '""')
                lines += [f"        intervals [{k}]:", f"            xmin = {_num(b)}",
                          f"            xmax = {_num(e)}", f'            text = "{text}"']
        return _out("\n".join(lines) + "\n", path)

    def cues(self, max_chars: int = 42, max_duration: float = 6.0, max_gap: float = 0.6,
             max_words: Optional[int] = None) -> List[List[Word]]:
        """Group the spoken words into subtitle cues. A new cue starts after a
        pause longer than ``max_gap`` seconds, after a word that ends a
        sentence, or when the cue would grow past ``max_chars`` characters,
        ``max_duration`` seconds or ``max_words`` words. ``max_words=1``
        gives one cue per word."""
        cues: List[List[Word]] = []
        cur: List[Word] = []
        for w in self.timed_words():
            if cur:
                chars = sum(len(x.word) + 1 for x in cur) + len(w.word)
                if (w.begin - cur[-1].end > max_gap or cur[-1].word.rstrip("\"')").endswith((".", "?", "!"))
                        or chars > max_chars or w.end - cur[0].begin > max_duration
                        or (max_words and len(cur) >= max_words)):
                    cues.append(cur)
                    cur = []
            cur.append(w)
        if cur:
            cues.append(cur)
        return cues

    def to_srt(self, path: Optional[PathLike] = None, **cue_options: Any) -> str:
        """SubRip subtitles. Each cue starts when its first word starts and
        ends when its last word ends. Takes the options of :meth:`cues`."""
        blocks = []
        for n, cue in enumerate(self.cues(**cue_options), 1):
            text = " ".join(w.word for w in cue)
            blocks.append(f"{n}\n{_clock(cue[0].begin, ',')} --> {_clock(cue[-1].end, ',')}\n{text}\n")
        return _out("\n".join(blocks), path)

    def to_vtt(self, path: Optional[PathLike] = None, word_timing: bool = True, **cue_options: Any) -> str:
        """WebVTT subtitles. With ``word_timing`` (the default), every word
        after the first in a cue carries its start time as a WebVTT timestamp
        tag, so players that support it highlight each word as it is said.
        Takes the options of :meth:`cues`."""
        blocks = ["WEBVTT\n"]
        for cue in self.cues(**cue_options):
            parts = [_vtt_escape(cue[0].word)]
            last = cue[0].begin
            for w in cue[1:]:
                tag = ""
                if word_timing and w.begin > last:  # WebVTT wants each tag later than the one before
                    tag, last = f"<{_clock(w.begin, '.')}>", w.begin
                parts.append(tag + _vtt_escape(w.word))
            blocks.append(f"{_clock(cue[0].begin, '.')} --> {_clock(cue[-1].end, '.')}\n{' '.join(parts)}\n")
        return _out("\n".join(blocks), path)


def _fill(spans, xmax: float):
    """Sort the spans, clip overlaps and fill every gap with an empty interval."""
    out, t = [], 0.0
    for b, e, label in sorted(spans):
        b, e = max(b, t), min(e, xmax)
        if e <= b:
            continue
        if b > t:
            out.append((t, b, ""))
        out.append((b, e, label))
        t = e
    if t < xmax:
        out.append((t, xmax, ""))
    return out


def _num(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _opt(x: Optional[float]) -> str:
    return "" if x is None else _num(float(x))


def _clock(seconds: float, sep: str) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _vtt_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _out(text: str, path: Optional[PathLike]) -> str:
    if path is not None:
        p = pathlib.Path(path)
        if p.parent != pathlib.Path("."):
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text
