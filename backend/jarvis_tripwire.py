"""
jarvis_tripwire.py - a smoke test for a model swap, and nothing more.

The original design was an evaluation suite: thirty to fifty tasks curated
from the owner's own past transcripts, scored by a judge model, producing a
number that said whether the new model was better. Two people took it apart
and it did not survive either of them.

The statistics first. Thirty to fifty tasks judged by an 8-billion-parameter
model has a noise floor of two or three tasks. A 5% regression is invisible
inside that, so any number it printed would be false precision - and a
trustworthy-looking dashboard reporting a number it cannot support is worse
than no dashboard, because people act on it.

The privacy second, and this was the one that killed the corpus. A golden
suite built from real transcripts is a second copy of the owner's life,
frozen, duplicated, and sitting outside everything the memory system does
about forgetting. Ask memory to forget something and the suite still has it.

So what is left is what a smoke test is for: catching a model that is broken,
not ranking one that is fine. The probes below are written here, in this file,
about nothing in particular. They are not the owner's data and there is no
path in this module that reads a transcript.

What it can catch: a model that answers in the wrong language, that will not
stop, that repeats itself into a loop, that emits no JSON when asked for JSON,
that ignores an instruction entirely, that returns empty. Those are the real
failures of a bad swap, and every one of them is visible without a judge.

What it cannot catch, and must never claim to: whether the new model is
better. The screen says so in those words.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

STATE_PATH = Path(os.environ.get("JARVIS_TRIPWIRE_STATE",
                                 str(_CFG_DIR / "tripwire.json")))


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("tripwire", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The probes
# --------------------------------------------------------------------------
# Each one is a prompt plus a check that is a plain function over the text. No
# judge model: a judge is a second thing that can be wrong, and it moves when
# the steward swaps it, so the numbers drift for a reason unrelated to what is
# being measured.

@dataclass
class Probe:
    id: str
    prompt: str
    check: Callable[[str], Optional[str]]     # None = passed, else the reason
    why: str                                  # what breaking this would mean


def _not_empty(text: str) -> Optional[str]:
    return None if (text or "").strip() else "answered with nothing at all"


def _is_english(text: str) -> Optional[str]:
    """A swapped model answering in another language is the loudest possible
    signal and the easiest to check: count characters outside Latin-1."""
    t = (text or "").strip()
    if not t:
        return "answered with nothing at all"
    foreign = sum(1 for ch in t if ord(ch) > 0x2100)
    if foreign > max(4, len(t) * 0.12):
        return "answered in a different script"
    return None


def _repeats(text: str) -> Optional[str]:
    """A model stuck in a loop. Character 4-grams, because the failure shows
    up inside words as often as between them ("the the the", "----------"),
    and a word-level check misses half of it."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if len(t) < 80:
        return None
    grams = Counter(t[i:i + 4] for i in range(len(t) - 3))
    if not grams:
        return None
    top, n = grams.most_common(1)[0]
    if n > len(t) * 0.10 and n > 12:
        return f"repeated {top.strip()!r} {n} times - it is looping"
    return None


def _short(limit: int) -> Callable[[str], Optional[str]]:
    def check(text: str) -> Optional[str]:
        words = len((text or "").split())
        if words > limit:
            return f"asked for at most {limit} words and wrote {words}"
        return _not_empty(text)
    return check


def _json_object(text: str) -> Optional[str]:
    raw = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except Exception:
        return "was asked for JSON and did not produce any"
    if not isinstance(data, dict):
        return f"produced JSON, but a {type(data).__name__} rather than an object"
    return None


def _contains(word: str) -> Callable[[str], Optional[str]]:
    def check(text: str) -> Optional[str]:
        if word.lower() not in (text or "").lower():
            return f"did not follow a plain instruction (no {word!r} in the answer)"
        return None
    return check


def _refuses_nothing(text: str) -> Optional[str]:
    """A model that has started refusing ordinary requests is broken for this
    use even though every individual refusal looks responsible."""
    t = (text or "").lower()
    for phrase in ("i cannot", "i can't help", "i'm unable", "i am unable",
                   "as an ai", "i'm not able to"):
        if phrase in t:
            return f"refused an ordinary request ({phrase!r})"
    return _not_empty(text)


PROBES: list = [
    Probe("answers", "What is the capital of France? Answer in one word.",
          _contains("paris"),
          "it cannot answer a question every model knows"),
    Probe("english", "Describe a bicycle in two sentences.", _is_english,
          "it is answering in a different language"),
    Probe("brevity", "In no more than 12 words, say what a hash function does.",
          _short(12), "it ignores a length instruction, so it will run on"),
    Probe("stops", "Count from 1 to 5, then stop.", _repeats,
          "it loops instead of stopping"),
    Probe("json", 'Reply with only this JSON: {"ok": true}', _json_object,
          "it cannot produce JSON, so every tool call will fail"),
    Probe("instruction", "Reply with exactly the word BANANA and nothing else.",
          _contains("banana"), "it does not follow a literal instruction"),
    Probe("helpful", "Give me two ideas for a birthday present for a keen cyclist.",
          _refuses_nothing, "it has started refusing ordinary requests"),
    Probe("nonempty", "Say hello.", _not_empty, "it returns nothing"),
]


# --------------------------------------------------------------------------
#   Running it
# --------------------------------------------------------------------------

@dataclass
class Result:
    probe: str
    passed: bool
    reason: str = ""
    why: str = ""
    answer: str = ""
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def run(ask: Callable[[str], str], probes: Optional[list] = None,
        keep_answer_chars: int = 400) -> list:
    """Run every probe through `ask`. `ask` takes a prompt, returns text.

    Injected rather than calling Ollama directly, because the caller knows
    which model it is testing and this module should not be able to pick one.
    """
    out = []
    for p in (probes or PROBES):
        t0 = time.time()
        try:
            answer = ask(p.prompt) or ""
        except Exception as exc:
            out.append(Result(p.id, False, f"the call failed ({exc})", p.why,
                              "", time.time() - t0))
            continue
        reason = p.check(answer)
        out.append(Result(p.id, reason is None, reason or "", p.why,
                          answer[:keep_answer_chars], time.time() - t0))
    return out


def baseline(ask: Callable[[str], str], model: str) -> dict:
    """Record how the CURRENT model answers, before a swap.

    Kept so the screen after a swap can put the two answers side by side. This
    is the only thing this module stores, it is about the probes above and not
    about the owner, and it is overwritten by the next baseline rather than
    accumulating.
    """
    results = [r.as_dict() for r in run(ask)]
    state = {"model": model, "at": time.time(), "results": results}
    _save(state)
    _audit("tripwire.baseline", {"model": model,
                                 "passed": sum(1 for r in results if r["passed"])})
    return state


def _save(state: dict) -> bool:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), "utf-8")
        os.replace(tmp, STATE_PATH)
        return True
    except Exception:
        return False


def _load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        return {}


def after_swap(ask: Callable[[str], str], model: str) -> dict:
    """Run the probes against the model that was just switched in and produce
    the one screen the owner sees.

    Read the shape of what comes back, because it is the whole design:

      * `broke` - probes the old model passed and this one does not. This is
        the only thing worth a person's attention.
      * `answers` - the old answer and the new one, side by side, for exactly
        those probes. Not a score.
      * `verdict` - a sentence, and the sentence never says "better".
      * `default_action` - always "keep". A screen whose default button
        accepts the change is not asking a question.
    """
    before = _load()
    prev = {r["probe"]: r for r in before.get("results", [])}
    results = [r.as_dict() for r in run(ask)]
    now = {r["probe"]: r for r in results}

    broke, already, fixed = [], [], []
    for pid, r in now.items():
        was = prev.get(pid)
        if r["passed"]:
            if was and not was["passed"]:
                fixed.append(pid)
            continue
        if was and not was["passed"]:
            already.append(pid)
        else:
            broke.append(pid)

    answers = [{"probe": pid,
                "prompt": next((p.prompt for p in PROBES if p.id == pid), ""),
                "why": now[pid].get("why", ""),
                "reason": now[pid].get("reason", ""),
                "before": (prev.get(pid) or {}).get("answer", ""),
                "after": now[pid].get("answer", "")}
               for pid in broke]

    total = len(results)
    if not before:
        verdict = (f"Nothing to compare against - there is no baseline from the "
                   f"previous model. {total - len(broke)} of {total} probes pass. "
                   f"This is not a claim that it is better.")
    elif broke:
        verdict = (f"This model breaks {len(broke)} of {total} probes that "
                   f"{before.get('model', 'the previous model')} passed.")
    else:
        verdict = ("Nothing broke. This is not a claim that it is better - "
                   "these probes catch a model that is broken, not one that is "
                   "worse.")

    out = {"model": model, "previous": before.get("model"),
           "total": total, "broke": broke, "already_failing": already,
           "fixed": fixed, "answers": answers, "verdict": verdict,
           "default_action": "keep",
           "actions": [{"id": "keep", "label": f"Keep {before.get('model') or 'the previous model'}",
                        "note": "rolls back; rollback needs no approval"},
                       {"id": "switch", "label": f"Use {model}",
                        "note": "keeps the model that was just switched in"}],
           "note": ("No score is shown on purpose. A suite this size judged "
                    "locally has a noise floor of two or three probes, so a "
                    "percentage would imply a precision it does not have.")}
    _audit("tripwire.after_swap", {"model": model, "broke": len(broke),
                                   "total": total})
    return out


def status() -> dict:
    st = _load()
    return {"available": True, "probes": len(PROBES),
            "baseline_model": st.get("model"), "baseline_at": st.get("at"),
            "note": ("A smoke test, not an evaluation. It catches a model that "
                     "is broken; it cannot tell you one is better.")}
