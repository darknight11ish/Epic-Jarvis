#!/usr/bin/env python3
"""Writes the memory words both apps use, and checks them.

    python3 tools/gen_memory_words_cases.py            # write both copies
    python3 tools/gen_memory_words_cases.py --check    # compare only

The memory review of 2026-09-27 (I8-I11) found the two apps wording memory
differently, and nothing to stop it drifting further. This file is the one
place the words are decided; it writes them, with worked cases, into

    jarvis-desktop/tests/fixtures/memory-words-cases.json
    jarvis-client/app/src/test/resources/contract/memory-words-cases.json

(byte-identical). The desktop's tests/memory-words.mjs and the phone's
MemoryWordsContractTest read it, so changing one app's words breaks the
other app's test, and the Python below says what both must answer.

What is in it:

- `status`: GET /api/memory/status -> the rows the memory counts show, in
  order (the desktop's Memory pane, the phone's "What Jarvis remembers").
  Most cases are the REAL MemoryStore.status() and reranker_status() of
  backend/rebuilt/jarvis_memory.py, put in each re-ranker state by the
  module's own functions; a few odd shapes are written by hand. I8:
  "Answer ordering (re-ranker)" and "Said again".
- `cards`: a review card's `auto_reason` -> its "Not saved automatically"
  line and, on its own line, the "older news" warning with plain dates
  ("1 January 2026"). I9. The older-news sentence is the REAL
  jarvis_intake.OLDER_NEWS, joined to the reason the way annotate() does.
- `dates` and `true_from`: "YYYY-MM-DD" -> "1 January 2026", and a
  GET /api/memory/auto row's `true_from` -> "true from 1 January 2026". I10.
- `words`: the fixed words, including the one wording for facts that are
  no longer in use (I11): "no longer used" in today's list, "true then" /
  "no longer true" when looking at a past date.

WHAT IS CHANGED AFTER THE RUN, and only this, so the file is the same on
every machine: the store's file path becomes a fixed one.
"""
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "memory-words-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "memory-words-cases.json")
COPIES = (DESKTOP, PHONE)

FIXED_DB = "~/.openjarvis/memory.db"

# ----------------------------------------------------------------------------
#   The words - decided here, once
# ----------------------------------------------------------------------------

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

WORDS = {
    "facts_in_use": "Facts in use",
    "no_longer_used_count": "No longer used",
    "embedding": "Embedding",
    "embedding_words_only": "(matches words only until the real embedding model has downloaded)",
    "search_by_meaning": "Search by meaning",
    "search_by_meaning_off": "off - facts are found by keyword",
    "waiting_to_be_indexed": "Waiting to be indexed",
    "overnight": "Overnight tidying",
    "overnight_on": "switched on, but not built yet - nothing runs",
    "overnight_off": "off (not built yet)",
    # I8
    "reranker": "Answer ordering (re-ranker)",
    "reranker_loading": "still loading - answers keep the old order until it is ready",
    "reranker_not_started": "not loaded yet - it starts loading with the first question",
    "reranker_off_by_setting": "turned off on the PC (JARVIS_MEMORY_RERANK=0)",
    "said_again": "Said again",
    "said_again_none": "nothing yet",
    "repeats": "Repeated cards dropped",
    # I9
    "reason_prefix": "Not saved automatically: ",
    "older_news_start": "It sounds older than what Jarvis knows",
    # I11: a fact no longer in use, today / on a past date.
    "no_longer_used": "no longer used",
    "true_then": "true then",
    "no_longer_true": "no longer true",
    # I10
    "true_from": "true from",
}

#: [0-9], not \d: Python's \d also matches other scripts' digits, and the
#: apps' does not. fullmatch, not $: Python's $ also matches before a final
#: newline, and JavaScript's does not.
_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_ISO_IN_TEXT = re.compile(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b")


def _days_in(y: int, m: int) -> int:
    if m == 2:
        return 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28
    return 30 if m in (4, 6, 9, 11) else 31


def plain_date(iso):
    """"2026-01-01" -> "1 January 2026". None for anything that is not a real
    day written exactly that way (year 1 or later)."""
    m = _ISO.fullmatch(iso) if isinstance(iso, str) else None
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y < 1 or not 1 <= mo <= 12 or not 1 <= d <= _days_in(y, mo):
        return None
    return f"{d} {MONTHS[mo - 1]} {y}"


def true_from_line(iso):
    day = plain_date(iso)
    return f"{WORDS['true_from']} {day}" if day else None


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num_text(v):
    """A number as both apps show it: whole numbers without ".0"."""
    if not _is_num(v):
        return None
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def _count(v):
    """A whole number of 0 or more, or None."""
    if not _is_num(v) or not float(v).is_integer() or v < 0:
        return None
    return int(v)


def _times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def reranker_value(r):
    if not isinstance(r, dict):
        return None
    state = r.get("state")
    if state == "on":
        parts = []
        used = _count(r.get("used"))
        if used is not None:
            parts.append(f"used for {used} {'answer' if used == 1 else 'answers'}")
        slow = _count(r.get("slow"))
        if slow:
            parts.append(f"too slow {_times(slow)}, so "
                         + ("that answer" if slow == 1 else "those answers")
                         + " kept the old order")
        return "on" + (" - " + "; ".join(parts) if parts else "")
    if state == "loading":
        return WORDS["reranker_loading"]
    if state == "not started":
        return WORDS["reranker_not_started"]
    if state == "off":
        why = r.get("why").strip() if isinstance(r.get("why"), str) else ""
        if why == "JARVIS_MEMORY_RERANK=0":
            why = WORDS["reranker_off_by_setting"]
        return f"off - {why}" if why else "off"
    return None


def said_again_value(v):
    n = _count(v)
    if n is None:
        return None
    return WORDS["said_again_none"] if n == 0 else _times(n)


def status_rows(s):
    """The rows under the memory counts, in order. The desktop adds the
    store's file path ("Store") after these; the phone does not show it."""
    if not isinstance(s, dict) or s.get("available") is False:
        return []
    out = []

    def add(k, v):
        if v is not None:
            out.append([k, v])
    add(WORDS["facts_in_use"], _num_text(s.get("current")))
    add(WORDS["no_longer_used_count"], _num_text(s.get("retired")))
    e = s.get("embedder")
    if isinstance(e, str) and e.strip():
        add(WORDS["embedding"], f"{e} {WORDS['embedding_words_only']}"
            if s.get("semantic") is False else e)
    if s.get("vector_search") is False:
        add(WORDS["search_by_meaning"], WORDS["search_by_meaning_off"])
    u = s.get("unembedded")
    if _is_num(u) and u > 0:
        add(WORDS["waiting_to_be_indexed"], _num_text(u))
    add(WORDS["reranker"], reranker_value(s.get("reranker")))
    add(WORDS["said_again"], said_again_value(s.get("said_again")))
    st = s.get("sleep_time")
    if isinstance(st, dict):
        add(WORDS["overnight"], WORDS["overnight_on"] if st.get("enabled") is True
            else WORDS["overnight_off"])
    return out


def card_lines(row):
    """{"reason": "Not saved automatically: ..." or None,
        "older": the older-news warning, on its own line, or None}."""
    raw = row.get("auto_reason") if isinstance(row, dict) else None
    raw = raw if isinstance(raw, str) else ""
    i = raw.find(WORDS["older_news_start"])
    before, after = (raw[:i], raw[i:]) if i >= 0 else (raw, "")
    reason = before.strip().rstrip(".").strip()
    older = None
    if after.strip():
        older = _ISO_IN_TEXT.sub(lambda m: plain_date(m.group(1)) or m.group(1), after.strip())
        if not older.endswith("."):
            older += "."
    return {"reason": WORDS["reason_prefix"] + reason if reason else None, "older": older}


# ----------------------------------------------------------------------------
#   The cases - from the real backend where it can say
# ----------------------------------------------------------------------------

def _real_statuses() -> list:
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-memory-words-"))
    os.environ.setdefault("JARVIS_NO_EMBED", "1")
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        fw = types.ModuleType("jarvis_framework")
        fw.LOG_DIR = tmp
        fw.load_framework = lambda *a, **k: {}
        sys.modules["jarvis_framework"] = fw
    fw.CONFIG_DIR = tmp
    fw.audit_log = lambda *a, **k: None
    import jarvis_memory as M

    class Stand(M.Reranker):
        name = "stand-in"

        def score(self, query, texts):
            return [0.0 for _ in texts]

    st = M.MemoryStore(tmp / "memory.db", embedder=M.HashEmbedder())
    a = st.add("Owner prefers tea to coffee", source="auto")
    st.add("Owner likes jazz", source="auto")
    old = st.add("Owner lives in York", source="user")
    st.add("Owner lives in Leeds", source="user", supersedes=old)
    t = st.get(a)["created"]
    st.said_again(a, t + 10, "typed")
    st.said_again(a, t + 20, "voice")
    st.said_again(a, t + 30, "typed")

    keep_on = M._RERANK_ON
    out = []

    def reset(**kw):
        M._rr.update(state="not started", model=None, why="", said=False, slow=0, used=0)
        M._rr.update(**kw)

    def snap(name):
        s = st.status()
        s["db"] = FIXED_DB
        out.append({"name": name, "status": json.loads(json.dumps(s))})

    def fails(exc):
        def factory():
            raise exc
        return factory
    try:
        # The states below are the re-ranker's own, so it is switched on for
        # them; it is off by default (the last case) until the PC's
        # self-test shows it helps.
        M._RERANK_ON = True
        reset()
        snap("not started: no question asked since the PC started")
        reset(state="loading")
        snap("still loading")
        reset()
        M.set_reranker(Stand())
        snap("on, not used yet")
        reset()
        M.set_reranker(Stand())
        M._rr.update(used=12, slow=1)
        snap("on, used, too slow once")
        reset()
        M.set_reranker(Stand())
        M._rr.update(used=1, slow=4)
        snap("on, used once, too slow four times")
        with contextlib.redirect_stderr(io.StringIO()):
            reset(state="loading")
            M._rr_load(fails(ImportError("no fastembed")))
            snap("off: fastembed missing")
            reset(state="loading")
            M._rr_load(fails(RuntimeError("bad file")))
            snap("off: the model could not be loaded")
        reset()
        M._RERANK_ON = False
        snap("off: not switched on (the default until the PC's self-test shows it helps)")
    finally:
        M._RERANK_ON = keep_on
        reset()
    older = dict(out[2]["status"])
    older.pop("reranker", None)
    older.pop("said_again", None)
    out.append({"name": "an older PC: no re-ranker, no said again", "status": older})
    return out


def _odd_statuses() -> list:
    base = {"available": True, "current": 3, "retired": 0, "embedder": "BAAI/bge-small-en-v1.5",
            "semantic": True, "vector_search": True, "unembedded": 0}
    return [
        {"name": "memory not available", "status": {"available": False, "reason": "no memory"}},
        {"name": "everything the route can add", "status": dict(
            base, unembedded=2, vector_search=False, sleep_time={"enabled": True},
            reranker={"state": "on", "model": "m", "why": "", "used": 0}, said_again=1)},
        {"name": "overnight tidying off", "status": dict(base, sleep_time={"enabled": False})},
        {"name": "re-ranker not an object", "status": dict(base, reranker="on", said_again=2)},
        {"name": "re-ranker state the apps do not know",
         "status": dict(base, reranker={"state": "warming"})},
        {"name": "off with no reason", "status": dict(base, reranker={"state": "off", "why": ""})},
        {"name": "counts that are not whole numbers",
         "status": dict(base, reranker={"state": "on", "used": "3", "slow": 2.5},
                        said_again="4")},
        {"name": "negative and fractional counts",
         "status": dict(base, current=2.5, reranker={"state": "on", "used": -1, "slow": -2},
                        said_again=-1)},
        {"name": "booleans are not numbers",
         "status": dict(base, current=True, retired=False, said_again=True, embedder="  ")},
    ]


def _cards() -> list:
    import jarvis_intake as I
    assert I.OLDER_NEWS.startswith(WORDS["older_news_start"]), I.OLDER_NEWS
    note = I.OLDER_NEWS.format(new="2026-01-01", old="2026-03-01")

    def joined(why):
        # jarvis_intake.annotate(): the reason without its full stop, then the note.
        why = why.strip().rstrip(".")
        return f"{why}. {note}" if why else note
    rows = [
        {"auto_reason": "from pasted text"},
        {"auto_reason": "  sensitive: money. "},
        {"auto_reason": joined("replaces a fact"), "older_news": True},
        {"auto_reason": joined(""), "older_news": True},
        {"auto_reason": joined("replaces a fact."), "older_news": True},
        {"auto_reason": I.OLDER_NEWS.format(new="2024-02-29", old="2025-02-29"),
         "older_news": True},
        {"auto_reason": ""},
        {"auto_reason": None},
        {"auto_reason": 5},
        {},
    ]
    return [{"row": r, **card_lines(r)} for r in rows]


DATES = ["2026-01-01", "2021-12-31", "2024-02-29", "2025-02-29", "2026-02-31",
         "2026-13-01", "2026-00-10", "0000-01-01", "0001-01-01", "2026-1-1", " 2026-01-01",
         "2026-01-01T00:00:00", "2026-01-01\n", "\u0662\u0660\u0662\u0666-01-01", "",
         "yesterday"]


def build() -> dict:
    status = _real_statuses() + _odd_statuses()
    return {
        "_comment": ("Generated by tools/gen_memory_words_cases.py from the real "
                     "jarvis_memory status and jarvis_intake.OLDER_NEWS. Do not edit by hand."),
        "words": dict(WORDS),
        "months": list(MONTHS),
        "dates": [{"iso": d, "says": plain_date(d)} for d in DATES],
        "true_from": [{"row": {"id": 1, "text": "Owner moved to Leeds in 2021",
                               "saved_at": 1790000000, **({"true_from": d} if d is not None else {})},
                       "line": true_from_line(d)}
                      for d in ["2021-01-01", "2026-09-05", None, "2026-02-31", 20210101]],
        "status": [dict(c, rows=status_rows(c["status"])) for c in status],
        "cards": _cards(),
    }


def document() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    doc = document()
    if "--check" in sys.argv:
        bad = [p for p in COPIES
               if not p.exists() or p.read_text(encoding="utf-8") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_memory_words_cases.py")
        if not bad:
            print("memory-words-cases.json: both copies match")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
