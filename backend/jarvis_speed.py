"""How fast each answer was - numbers only, in a file on this PC.

WHAT IT IS FOR

"Jarvis got slow" has had no answer except a feeling. An Ollama update, a
game holding video memory, or a model that no longer fits on the graphics
card can each make every answer take three times as long, and nothing
records it. The only timings anywhere were one-off measurements written into
docs/MODEL-TOPOLOGY.md by hand.

This module keeps one small row per answer:

    which model   how long until the first word   how long in total
    words per second   tokens per second   how much of the model was on the
    graphics card   whether tools were used

and, when the model is switched, one row comparing the old model's speed with
the new one's (item 12 - the Tripwire speed check, `SwitchSpeed` below).

WHAT IT NEVER KEEPS

No words of the conversation. Not the question, not the answer, not a
summary, not a hash of either. That is enforced in code, not by convention:
every row passes through `_clean()`, which keeps only a fixed list of field
names and only numbers, booleans and a model name. A text field added by
mistake anywhere upstream is dropped on the floor rather than written. The
stream is read while it passes through to count words and time them; the
text itself is never held beyond the one line being parsed.

WHERE IT GOES

`speed.jsonl`, in the same settings folder everything else in Jarvis uses
(`~/.openjarvis` unless OPENJARVIS_CONFIG_DIR says otherwise). Local file,
append only. Nothing here opens a network connection except `measure()`,
which talks to Ollama and refuses outright unless Ollama's address is this
machine. There is no upload, no leaderboard and no analytics, and there will
not be - OpenJarvis has all three and they are exactly the part not taken.

Rows are never deleted or rewritten. At roughly 250 bytes a row, a hundred
answers a day is about 9 MB a year; reading only ever looks at the end of the
file, so its size does not slow anything down.

Written fresh for Epic-Jarvis. The idea came from OpenJarvis's telemetry store
and latency bench (Apache-2.0); no code was copied from either.
"""
from __future__ import annotations

import ipaddress
import json
import os
import statistics
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Optional

SCHEMA = 1
FILE_NAME = "speed.jsonl"

#: The fields a row may carry, and nothing else. `_clean()` enforces it.
#: There is deliberately no field that could hold text from a conversation.
_NUMBER_FIELDS = {
    "v", "at",
    # one answer
    "first_word_ms", "total_ms", "words", "words_per_s", "tokens",
    "tokens_per_s", "prompt_tokens", "on_gpu_percent",
    # how much of the prompt Ollama reused rather than read again (I03,
    # 2026-09-26): summed over the answer's requests to the model, and how
    # many requests that was (note_prompt)
    "cached_tokens", "prompt_rounds",
    # one speed measurement of one model (measure())
    "probes", "load_ms",
    # one model switch (SwitchSpeed)
    "old_tokens_per_s", "new_tokens_per_s", "old_first_word_ms",
    "new_first_word_ms", "change_percent",
}
_BOOL_FIELDS = {"tools", "streamed"}
_NAME_FIELDS = {"model", "old_model", "new_model"}
#: Small closed vocabularies. A value outside its list is dropped.
_ENUM_FIELDS = {
    "kind": {"answer", "bench", "switch"},
    "token_source": {"ollama", "usage", "deltas"},
    "old_source": {"measured", "stored", "answers"},
}
_MAX_NAME = 120


def _config_dir() -> Path:
    """Same rule as import_history._config_dir() and jarvis_speech: the real
    framework's CONFIG_DIR if importable, OPENJARVIS_CONFIG_DIR if set,
    otherwise ~/.openjarvis."""
    try:
        import jarvis_framework as fw  # type: ignore
        if getattr(fw, "CONFIG_DIR", None):
            return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def default_path() -> Path:
    return _config_dir() / FILE_NAME


def _clean(row: dict) -> dict:
    """Keep only the allowed fields, only in the allowed shapes."""
    out: dict = {}
    for k, v in (row or {}).items():
        if k in _NUMBER_FIELDS:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                continue
            out[k] = round(v, 2) if isinstance(v, float) else v
        elif k in _BOOL_FIELDS:
            if isinstance(v, bool):
                out[k] = v
        elif k in _NAME_FIELDS:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:_MAX_NAME]
        elif k in _ENUM_FIELDS:
            if isinstance(v, str) and v in _ENUM_FIELDS[k]:
                out[k] = v
    return out


def _median(xs: Iterable) -> Optional[float]:
    vals = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if not vals:
        return None
    return round(float(statistics.median(vals)), 1)


# ==========================================================================
#   The file
# ==========================================================================

class SpeedLog:
    """Append-only JSON lines. Never raises: a speed log that can break an
    answer is worse than no speed log."""

    _lock = threading.Lock()

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    def append(self, row: dict) -> bool:
        clean = _clean(row)
        if "kind" not in clean:
            return False
        clean["v"] = SCHEMA
        clean.setdefault("at", int(time.time()))
        line = json.dumps(clean, separators=(",", ":"), sort_keys=True) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
            return True
        except OSError:
            return False

    def tail(self, n: int = 200, kind: Optional[str] = None,
             max_bytes: int = 512 * 1024) -> list:
        """The last `n` rows (of one kind, if given), oldest first. Reads at
        most `max_bytes` from the end of the file, whatever its size."""
        try:
            with open(self.path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                raw = f.read()
        except OSError:
            return []
        lines = raw.split(b"\n")
        if len(raw) == max_bytes and size > max_bytes:
            lines = lines[1:]          # the first line is probably cut in half
        rows = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            if kind and r.get("kind") != kind:
                continue
            rows.append(_clean(r))
        return rows[-n:] if n > 0 else []


# ==========================================================================
#   Item 11 - timing one answer while it streams past
# ==========================================================================

def _count_words(text: str, in_word: bool) -> tuple:
    """Words started in `text`, carrying whether the previous piece ended
    mid-word - a word split across two stream pieces is still one word."""
    n = 0
    for ch in text:
        if ch.isspace():
            in_word = False
        elif not in_word:
            in_word = True
            n += 1
    return n, in_word


class Meter:
    """Watches one answer's bytes go past and times them.

    Usage, in the chat route:

        meter = Meter(model)            # before the request to Ollama
        ...
        meter.feed(chunk)               # for every chunk relayed to the client
        ...
        meter.finish(lane)              # once, after the stream ends normally

    Understands the three shapes that reach /api/chat: OpenAI-style server
    sent events (`data: {...}` lines, what Ollama's /v1/chat/completions
    streams), Ollama's own newline-delimited JSON (`{"message":...}` lines,
    ending with a `done` line that carries Ollama's exact timings), and a
    single JSON body when streaming was off.

    `feed` and `finish` never raise. A stream that is cut off (the phone
    dropped out) is simply never finished, so it is never recorded - a
    half-answer's speed is not a speed.
    """

    _MAX_BUFFER = 1024 * 1024

    def __init__(self, model: str = "", *, tools: bool = False,
                 clock: Callable[[], float] = time.monotonic):
        self.model = model or ""
        self.tools = bool(tools)
        self._clock = clock
        self._t0 = clock()
        self._first = None          # clock() at the first word
        self._buf = b""
        self._saw_lines = False     # any SSE/NDJSON line parsed at all
        self._overflow = False
        self._in_word = False
        self.words = 0
        self.deltas = 0             # content pieces - roughly one per token
        self.usage_tokens = None    # OpenAI `usage.completion_tokens`
        self.prompt_tokens = None
        self.cached_tokens = None   # `usage.prompt_tokens_details.cached_tokens`
        self.noted = None           # note_prompt()'s totals, for a tool-loop answer
        self.ollama = None          # Ollama's own final timings, if sent
        self._done = False

    # -- reading -----------------------------------------------------------

    def feed(self, chunk: bytes) -> None:
        try:
            self._feed(chunk)
        except Exception:
            pass

    def _feed(self, chunk: bytes) -> None:
        if not chunk or self._done:
            return
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", "replace")
        self._buf += chunk
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            self._line(line.strip())
        if len(self._buf) > self._MAX_BUFFER:
            # A non-streamed body this large is not something we will parse;
            # drop it rather than hold it.
            self._buf = b""
            self._overflow = True

    def _line(self, line: bytes) -> None:
        if not line:
            return
        if line.startswith(b"data:"):
            line = line[5:].strip()
            if line == b"[DONE]":
                self._saw_lines = True
                return
        if not line.startswith(b"{"):
            return
        try:
            obj = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            return
        if isinstance(obj, dict):
            self._saw_lines = True
            self._object(obj, streamed=True)

    def _object(self, obj: dict, *, streamed: bool) -> None:
        text = ""
        choices = obj.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            part = choices[0].get("delta") if streamed else None
            if not isinstance(part, dict):
                part = choices[0].get("message")
            if isinstance(part, dict) and isinstance(part.get("content"), str):
                text = part["content"]
        msg = obj.get("message")
        if not text and isinstance(msg, dict) and isinstance(msg.get("content"), str):
            text = msg["content"]                           # Ollama native
        if not text and isinstance(obj.get("response"), str):
            text = obj["response"]                          # /api/generate
        if text:
            if self._first is None:
                self._first = self._clock()
            self.deltas += 1
            n, self._in_word = _count_words(text, self._in_word)
            self.words += n
        usage = obj.get("usage")
        if isinstance(usage, dict):
            ct, pt = usage.get("completion_tokens"), usage.get("prompt_tokens")
            if isinstance(ct, int) and not isinstance(ct, bool):
                self.usage_tokens = ct
            if isinstance(pt, int) and not isinstance(pt, bool):
                self.prompt_tokens = pt
            details = usage.get("prompt_tokens_details")
            cached = details.get("cached_tokens") if isinstance(details, dict) else None
            if isinstance(cached, int) and not isinstance(cached, bool):
                self.cached_tokens = cached
        if obj.get("done") is True:
            t = timing_from_reply(obj)
            if t:
                self.ollama = t

    def note_prompt(self, *, prompt_tokens=None, cached_tokens=None, rounds=None) -> None:
        """The chat tool loop's own count (jarvis_agent.PROMPT_USAGE): the
        prompt tokens of every request this answer made to the model, and
        how many of them Ollama reused instead of reading again. The loop
        re-writes the stream the client sees, so those counts never pass
        through feed(). Numbers only; anything else is ignored."""
        def num(v):
            return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None
        self.noted = {"prompt_tokens": num(prompt_tokens), "cached_tokens": num(cached_tokens),
                      "prompt_rounds": num(rounds)}

    # -- the row -------------------------------------------------------------

    def row(self, model: Optional[str] = None, *, tools: Optional[bool] = None) -> dict:
        end = self._clock()
        streamed = self._saw_lines
        if not streamed and self._buf and not self._overflow:
            # Streaming was off: one JSON body. It has no "first word" of its
            # own - the whole answer arrived at once - so none is recorded.
            try:
                obj = json.loads(self._buf.decode("utf-8", "replace"))
                if isinstance(obj, dict):
                    self._object(obj, streamed=False)
            except ValueError:
                pass
            self._first = None
        self._buf = b""
        total_ms = max(0, int(round((end - self._t0) * 1000)))
        first_ms = (None if self._first is None
                    else max(0, int(round((self._first - self._t0) * 1000))))
        gen_s = (end - self._first) if self._first is not None else None

        wps = None
        if gen_s and gen_s >= 0.05 and self.words >= 2:
            wps = self.words / gen_s

        tokens, tps, source = None, None, None
        if self.ollama and self.ollama.get("tokens_per_s"):
            tokens, tps, source = (self.ollama.get("tokens"),
                                   self.ollama["tokens_per_s"], "ollama")
        elif self.usage_tokens:
            tokens, source = self.usage_tokens, "usage"
            if gen_s and gen_s >= 0.05:
                tps = self.usage_tokens / gen_s
        elif self.deltas:
            tokens, source = self.deltas, "deltas"
            if gen_s and gen_s >= 0.05 and self.deltas >= 2:
                tps = self.deltas / gen_s

        return _clean({
            "kind": "answer",
            "at": int(time.time()),
            "model": model if model is not None else self.model,
            "tools": self.tools if tools is None else bool(tools),
            "streamed": streamed,
            "first_word_ms": first_ms,
            "total_ms": total_ms,
            "words": self.words,
            "words_per_s": wps,
            "tokens": tokens,
            "tokens_per_s": tps,
            "token_source": source,
            "prompt_tokens": (self.ollama or {}).get(
                "prompt_tokens", self.prompt_tokens
                if self.prompt_tokens is not None else (self.noted or {}).get("prompt_tokens")),
            "cached_tokens": (self.cached_tokens if self.cached_tokens is not None
                              else (self.noted or {}).get("cached_tokens")),
            "prompt_rounds": (self.noted or {}).get("prompt_rounds"),
        })

    def finish(self, model: Optional[str] = None, *, tools: Optional[bool] = None,
               log: Optional[SpeedLog] = None,
               gpu: Optional[Callable[[str], Optional[int]]] = None,
               background: bool = True) -> Optional[dict]:
        """Record this answer. Once only; never raises.

        The graphics-card share is looked up afterwards - it is a loopback
        call with its own timeout - and, by default, on a background thread,
        so the answer that has just finished is not held open for it.
        """
        if self._done:
            return None
        self._done = True
        if getattr(_current, "meter", None) is self:
            _current.meter = None
        try:
            row = self.row(model, tools=tools)
        except Exception:
            return None
        if not row.get("words") and not row.get("tokens"):
            return None               # nothing was said; nothing to time
        target = log or SpeedLog()
        lookup = gpu or on_gpu_percent

        def _write():
            try:
                pct = lookup(row.get("model", ""))
                if isinstance(pct, int) and not isinstance(pct, bool):
                    row["on_gpu_percent"] = max(0, min(100, pct))
            except Exception:
                pass
            target.append(row)

        if background:
            threading.Thread(target=_write, name="jarvis-speed", daemon=True).start()
        else:
            _write()
        return row


#: The Meter start() made on this thread, until it finishes: where
#: note_prompt() puts the chat tool loop's counts. jarvis_hud.py calls
#: start(), jarvis_agent.run_local_turn and finish() on the one request
#: thread, so this links them without a change to jarvis_hud.py.
_current = threading.local()


def start(model: str = "", *, tools: bool = False) -> Optional[Meter]:
    """For the hook in jarvis_hud.py: a Meter, or None if anything at all
    goes wrong. Timing is bookkeeping and must never cost an answer."""
    try:
        m = Meter(model, tools=tools)
        _current.meter = m
        return m
    except Exception:
        return None


def note_prompt(*, prompt_tokens=None, cached_tokens=None, rounds=None) -> bool:
    """jarvis_agent's prompt counts for the answer being timed on this
    thread (Meter.note_prompt). False, and nothing kept, when no answer is
    being timed here. Never raises."""
    try:
        m = getattr(_current, "meter", None)
        if m is None or m._done:
            return False
        m.note_prompt(prompt_tokens=prompt_tokens, cached_tokens=cached_tokens,
                      rounds=rounds)
        return True
    except Exception:
        return False


def _same_model(a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    strip = lambda s: s[:-7] if s.endswith(":latest") else s
    return strip(a) == strip(b)


def on_gpu_percent(model: str) -> Optional[int]:
    """How much of `model` is on the graphics card right now, from
    jarvis_models.offload_status() (gpu-offload.patch) - which asks Ollama's
    /api/ps on loopback and never loads anything. None when it cannot say."""
    try:
        import jarvis_models as MM  # type: ignore
        st = MM.offload_status(timeout=2.0)
    except Exception:
        return None
    for m in (st or {}).get("models") or []:
        if _same_model(str(m.get("name", "")), model):
            pct = m.get("on_gpu_percent")
            if isinstance(pct, int) and not isinstance(pct, bool):
                return pct
    return None


# ==========================================================================
#   What the screens read
# ==========================================================================

def summary(rows: list) -> dict:
    """Per model: how many answers, and the middle value of each speed.

    First-word time leaves out answers that used tools: those include the
    tool calls and any wait for your approval, so they would make a fast
    model look slow for reasons that have nothing to do with the model.
    """
    by: dict = {}
    for r in rows:
        if r.get("kind") != "answer" or not r.get("model"):
            continue
        by.setdefault(r["model"], []).append(r)
    out = {}
    for model, rs in by.items():
        out[model] = {
            "answers": len(rs),
            "median_first_word_ms": _median(r.get("first_word_ms") for r in rs
                                            if not r.get("tools")),
            "median_tokens_per_s": _median(r.get("tokens_per_s") for r in rs),
            "median_words_per_s": _median(r.get("words_per_s") for r in rs),
            "median_on_gpu_percent": _median(r.get("on_gpu_percent") for r in rs),
            "last_at": max((r.get("at") or 0) for r in rs) or None,
        }
    return out


def slowdown(rows: list, model: str, *, recent: int = 10, before: int = 20,
             threshold: float = 0.30) -> Optional[dict]:
    """Has `model` got noticeably slower lately? Compares the middle speed of
    its last `recent` answers with the `before` answers ahead of them. Says
    nothing at all until there are enough answers for the comparison to mean
    something - a verdict from three answers would be noise."""
    rs = [r for r in rows if r.get("kind") == "answer" and _same_model(r.get("model", ""), model)
          and isinstance(r.get("tokens_per_s"), (int, float))]
    if len(rs) < recent + before:
        return None
    now = _median(r["tokens_per_s"] for r in rs[-recent:])
    then = _median(r["tokens_per_s"] for r in rs[-(recent + before):-recent])
    if not now or not then:
        return None
    drop = (then - now) / then
    return {
        "slower": drop >= threshold,
        "change_percent": round(-drop * 100, 1),
        "recent_tokens_per_s": now,
        "earlier_tokens_per_s": then,
    }


def view(limit: int = 20, log: Optional[SpeedLog] = None,
         current: Optional[str] = None) -> dict:
    """The `speed` block of GET /api/models. Numbers only, never raises."""
    try:
        lg = log or SpeedLog()
        rows = lg.tail(500)
        answers = [r for r in rows if r.get("kind") == "answer"]
        switches = [r for r in rows if r.get("kind") == "switch"]
        out = {
            "available": True,
            "recent": answers[-max(0, min(limit, 100)):],
            "by_model": summary(answers),
            "last_switch": switches[-1] if switches else None,
            # Said here, so no screen has to build its own sentence from the
            # numbers and get it subtly different from the other screen.
            "last_switch_note": None,
            "slowdown": None,
            "note": ("How fast recent answers were. Numbers only - no words "
                     "of any conversation are kept - in a file on this PC."),
        }
        if switches:
            s = switches[-1]
            old = ({"tokens_per_s": s.get("old_tokens_per_s"),
                    "source": s.get("old_source")}
                   if s.get("old_tokens_per_s") else None)
            new = ({"tokens_per_s": s.get("new_tokens_per_s")}
                   if s.get("new_tokens_per_s") else None)
            c = compare(old, new, s.get("old_model", ""), s.get("new_model", ""))
            out["last_switch_note"] = c["note"] + " " + c["quality_note"]
        # jarvis_models.current_model() is passed straight in by the hook;
        # its exact return shape is not visible from this repository, so a
        # name is dug out of a dict too, and anything else is ignored.
        if isinstance(current, dict):
            current = current.get("ref") or current.get("name") or current.get("model")
        if isinstance(current, str) and current.strip():
            sd = slowdown(answers, current.strip())
            if sd:
                out["slowdown"] = sd
                if sd["slower"]:
                    out["note"] = (
                        f"The last 10 answers were about {abs(sd['change_percent']):.0f}% "
                        f"slower than the 20 before them, on the same model. "
                        "Something changed: an Ollama update, another program "
                        "using the graphics card, or the model no longer fitting "
                        "on it. The graphics-card line above says which, if it "
                        "is the last one.")
        return out
    except Exception as exc:
        return {"available": False, "note": f"could not be read: {type(exc).__name__}"}


# ==========================================================================
#   Item 12 - the speed check when the model is switched
# ==========================================================================
#
# Tripwire (jarvis_tripwire.py, on the owner's PC, not in this repository)
# already runs a few fixed probes on the outgoing model before a swap and on
# the incoming one after it. Ollama's own replies carry exact timings, so the
# cheapest correct design is for Tripwire to hand each probe's reply here:
#
#     speed = jarvis_speed.SwitchSpeed(old_model, new_model)
#     ... before the swap, for each probe:   speed.add("old", reply)
#     ... after the swap, for each probe:    speed.add("new", reply)
#     result["speed"] = speed.finish()       # also writes one "switch" row
#
# If a probe goes through the OpenAI-compatible endpoint (whose replies carry
# no timings), wrap the call instead: `reply = speed.timed("old", lambda: ...)`.
#
# If Tripwire cannot be changed at all, `measure(model)` runs three fixed
# prompts of its own. Read the note on it about the OLD model first.

#: About nothing in particular, and nothing from any conversation - the same
#: rule the Tripwire probes follow (jarvis-framework.toml section 21).
FIXED_PROMPTS = (
    "Count from one to twenty in words, separated by commas.",
    "List the seven days of the week, one per line.",
    "In two sentences, explain what a thermometer measures.",
)


def timing_from_reply(reply: dict) -> Optional[dict]:
    """Ollama's own timings, from a native /api/generate or /api/chat reply
    (or the final `done` line of a stream). Durations there are nanoseconds.
    None when the reply does not carry them - the OpenAI-compatible
    endpoint's replies do not."""
    if not isinstance(reply, dict):
        return None
    ec, ed = reply.get("eval_count"), reply.get("eval_duration")
    if not isinstance(ec, int) or not isinstance(ed, int) or ed <= 0 or ec <= 0:
        return None
    ld = reply.get("load_duration") if isinstance(reply.get("load_duration"), int) else 0
    pd = (reply.get("prompt_eval_duration")
          if isinstance(reply.get("prompt_eval_duration"), int) else 0)
    pc = reply.get("prompt_eval_count")
    return {
        "tokens": ec,
        "tokens_per_s": round(ec / (ed / 1e9), 2),
        # Loading plus reading the prompt is what stands between asking and
        # the first word, on Ollama's own clock.
        "first_word_ms": int(round((ld + pd) / 1e6)),
        "load_ms": int(round(ld / 1e6)),
        "prompt_tokens": pc if isinstance(pc, int) and not isinstance(pc, bool) else None,
    }


def _side(samples: list, source: Optional[str] = None) -> Optional[dict]:
    if not samples:
        return None
    return {
        "probes": len(samples),
        "tokens_per_s": _median(s.get("tokens_per_s") for s in samples),
        # The first probe pays for loading the model; the middle of the rest
        # is the steady-state first-word time. With one probe, it is all
        # there is.
        "first_word_ms": _median(s.get("first_word_ms") for s in
                                 (samples[1:] if len(samples) > 1 else samples)),
        "load_ms": samples[0].get("load_ms"),
        "source": source,
    }


def compare(old: Optional[dict], new: Optional[dict], old_model: str = "",
            new_model: str = "") -> dict:
    """A plain-words result for Tripwire's screen. Speed only."""
    out = {
        "old_model": old_model, "new_model": new_model,
        "old": old, "new": new, "change_percent": None,
        "quality_note": ("This measures speed only. It cannot tell you whether "
                         "the new model's answers are better or worse."),
    }
    o = (old or {}).get("tokens_per_s")
    n = (new or {}).get("tokens_per_s")
    if n and o:
        pct = round((n - o) / o * 100, 1)
        out["change_percent"] = pct
        if abs(pct) < 10:
            verdict = "about the same speed"
        elif pct > 0:
            verdict = f"about {pct:.0f}% faster"
        else:
            verdict = f"about {abs(pct):.0f}% slower"
        how = {"measured": "", "stored": " (the old number is from the last time it was measured)",
               "answers": " (the old number is from its recent real answers)"}.get(
                   (old or {}).get("source") or "measured", "")
        out["note"] = (f"Old: {o:.0f} tokens/s. New: {n:.0f} tokens/s. "
                       f"The new model is {verdict}{how}.")
    elif n:
        out["note"] = (f"New: {n:.0f} tokens/s. There is no earlier measurement "
                       "of the old model to compare it with.")
    else:
        out["note"] = "Speed could not be measured this time."
    return out


class SwitchSpeed:
    """Collects Tripwire's probe timings for one model switch."""

    def __init__(self, old_model: str, new_model: str, *,
                 clock: Callable[[], float] = time.monotonic):
        self.old_model, self.new_model = old_model or "", new_model or ""
        self._clock = clock
        self._samples = {"old": [], "new": []}
        self.old_source: Optional[str] = "measured"

    def add(self, side: str, reply: Optional[dict] = None, *,
            wall_ms: Optional[float] = None) -> None:
        """One probe's reply. Never raises; an unknown side is ignored."""
        try:
            if side not in self._samples:
                return
            t = timing_from_reply(reply) if reply is not None else None
            if t is None and wall_ms is not None:
                # No Ollama timings: the wall clock is all there is, and it
                # can only give a first-word figure, not a rate.
                t = {"first_word_ms": int(round(wall_ms)), "tokens_per_s": None}
            if t is not None:
                self._samples[side].append(t)
        except Exception:
            pass

    def add_measured(self, side: str, m: dict) -> None:
        """A `measure()` result, for when Tripwire's own probes cannot be
        timed and this module ran its fixed prompts instead."""
        if side in self._samples and m and m.get("ok"):
            self._samples[side].append({"tokens_per_s": m.get("tokens_per_s"),
                                        "first_word_ms": m.get("first_word_ms"),
                                        "load_ms": m.get("load_ms")})

    def timed(self, side: str, call: Callable[[], dict]) -> dict:
        """Run one probe through `call`, timing it; returns its reply
        unchanged. Exceptions from `call` propagate - that is Tripwire's
        business, not this module's."""
        t0 = self._clock()
        reply = call()
        self.add(side, reply if isinstance(reply, dict) else None,
                 wall_ms=(self._clock() - t0) * 1000)
        return reply

    def use_stored_old(self, log: Optional[SpeedLog] = None) -> bool:
        """When the old model was not measured before the swap, fall back to
        what is on file: its last measurement, else its recent answers."""
        if self._samples["old"]:
            return True
        lg = log or SpeedLog()
        rows = lg.tail(500)
        bench = [r for r in rows if r.get("kind") == "bench"
                 and _same_model(r.get("model", ""), self.old_model)]
        if bench:
            b = bench[-1]
            self._samples["old"].append({"tokens_per_s": b.get("tokens_per_s"),
                                         "first_word_ms": b.get("first_word_ms"),
                                         "load_ms": b.get("load_ms")})
            self.old_source = "stored"
            return True
        s = summary(rows).get(self.old_model)
        if s and s.get("median_tokens_per_s"):
            self._samples["old"].append({"tokens_per_s": s["median_tokens_per_s"],
                                         "first_word_ms": s.get("median_first_word_ms")})
            self.old_source = "answers"
            return True
        self.old_source = None
        return False

    def result(self) -> dict:
        return compare(_side(self._samples["old"], self.old_source),
                       _side(self._samples["new"], "measured"),
                       self.old_model, self.new_model)

    def finish(self, log: Optional[SpeedLog] = None) -> dict:
        """The result, plus one "switch" row on file - and a "bench" row for
        the new model, so the NEXT switch away from it has a number to
        compare against without having to load it again."""
        try:
            if not self._samples["old"]:
                self.use_stored_old(log)
            res = self.result()
            lg = log or SpeedLog()
            old, new = res.get("old") or {}, res.get("new") or {}
            if new.get("tokens_per_s"):
                lg.append({"kind": "bench", "model": self.new_model,
                           "probes": new.get("probes"),
                           "tokens_per_s": new.get("tokens_per_s"),
                           "first_word_ms": new.get("first_word_ms"),
                           "load_ms": new.get("load_ms")})
            lg.append({"kind": "switch", "old_model": self.old_model,
                       "new_model": self.new_model,
                       "old_tokens_per_s": old.get("tokens_per_s"),
                       "new_tokens_per_s": new.get("tokens_per_s"),
                       "old_first_word_ms": old.get("first_word_ms"),
                       "new_first_word_ms": new.get("first_word_ms"),
                       "change_percent": res.get("change_percent"),
                       "old_source": old.get("source")})
            return res
        except Exception as exc:
            return {"note": f"Speed could not be measured: {type(exc).__name__}",
                    "old": None, "new": None, "change_percent": None}


def ollama_url() -> str:
    for name in ("OLLAMA_URL", "OLLAMA_HOST"):
        v = (os.environ.get(name) or "").strip()
        if v:
            if "://" not in v:
                v = "http://" + v
            # 0.0.0.0 is how a server is told to listen everywhere; it is not
            # an address anything can connect TO. This machine is.
            return v.rstrip("/").replace("://0.0.0.0", "://127.0.0.1")
    return "http://127.0.0.1:11434"


def is_loopback(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _post_json(url: str, payload: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with _urlopen(req, timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _get_json(url: str, timeout: float = 4.0) -> dict:
    with _urlopen(url, timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _urlopen(req, timeout: float):
    """Ollama on this PC, never through a proxy (CONN-1): a set HTTPS_PROXY
    would otherwise carry the request - model names and the fixed test
    prompts - to the proxy. jarvis_local_http is shipped alongside."""
    try:
        import jarvis_local_http
    except ImportError:
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            req, timeout=timeout)
    return jarvis_local_http.urlopen(req, timeout)


def is_loaded(model: str, *, base: Optional[str] = None,
              get: Optional[Callable[[str], dict]] = None) -> Optional[bool]:
    """Is `model` in memory right now? /api/ps, which loads nothing. None if
    Ollama did not answer or the address is not this machine."""
    base = (base or ollama_url()).rstrip("/")
    if not is_loopback(base):
        return None
    try:
        body = (get or _get_json)(f"{base}/api/ps")
    except Exception:
        return None
    return any(_same_model(str(m.get("name") or m.get("model") or ""), model)
               for m in (body or {}).get("models") or [])


def measure(model: str, *, base: Optional[str] = None,
            post: Optional[Callable[[str, dict], dict]] = None,
            prompts: Iterable[str] = FIXED_PROMPTS,
            log: Optional[SpeedLog] = None) -> dict:
    """Time `model` on the fixed prompts, through Ollama's native
    /api/generate, and put one "bench" row on file.

    THIS LOADS THE MODEL if it is not already loaded - that is what running a
    prompt means. So it is for the NEW model, after the switch, which is
    being loaded anyway. For the OLD model, call it only BEFORE the swap and
    only if `is_loaded(old)` is true: on an 8 GB card, loading the old model
    back after the switch pushes the new one off the card. `SwitchSpeed.
    use_stored_old()` is the answer when the old model is not loaded.

    Refuses unless Ollama's address is this machine. Sends no num_ctx: a
    different context size would make Ollama reload the model, and the
    measurement would then be of a different configuration from the one in
    use. The options sent (a 64-token cap, temperature 0, a fixed seed) are
    per-request and change nothing about the loaded model.
    """
    base = (base or ollama_url()).rstrip("/")
    if not is_loopback(base):
        return {"model": model, "ok": False, "probes": 0,
                "note": (f"Not measured: Ollama's address ({base}) is not this "
                         "PC, and the speed check only talks to this PC.")}
    call = post or _post_json
    samples = []
    for p in prompts:
        try:
            reply = call(f"{base}/api/generate", {
                "model": model, "prompt": p, "stream": False,
                "options": {"num_predict": 64, "temperature": 0, "seed": 7},
            })
        except Exception as exc:
            return {"model": model, "ok": False, "probes": len(samples),
                    "note": f"Ollama stopped answering during the check: {type(exc).__name__}"}
        t = timing_from_reply(reply)
        if t:
            samples.append(t)
    side = _side(samples, "measured")
    if not side:
        return {"model": model, "ok": False, "probes": 0,
                "note": "Ollama answered, but without timing numbers."}
    (log or SpeedLog()).append({"kind": "bench", "model": model,
                                "probes": side["probes"],
                                "tokens_per_s": side["tokens_per_s"],
                                "first_word_ms": side["first_word_ms"],
                                "load_ms": side["load_ms"]})
    return dict(side, model=model, ok=True)
