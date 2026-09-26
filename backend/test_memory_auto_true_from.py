"""test_memory_auto_true_from.py - "true from" dates in the Saved automatically
list (the memory review's I10, 2026-09-27).

    python3 backend/test_memory_auto_true_from.py

Memory idea 4 stores the date a fact's own words give ("I moved to Leeds in
2021") as when it became true, marked meta["true_from"] = "said". Until now
neither app could see it: GET /api/memory/auto sent only `saved_at`. Each row
now carries `true_from`, a plain "YYYY-MM-DD" in this PC's time zone - only
for a fact whose date came from the owner's words. Both apps show it as
"true from 1 January 2021" (contract/memory-words-cases.json).

What it proves:

1. A fact whose words give a date: `true_from` is that day, the same day
   the store's valid_from falls on.
2. A fact with no date in its words: no `true_from` at all (its saved_at
   already says when it became true), and nothing else in the row changes.
3. The helper never raises and says nothing for a damaged row: meta
   without the mark, a missing, non-number or infinite valid_from.
4. No words are added: `true_from` is a date and nothing else.
"""
import os
import re
import sys
import tempfile
import time
import traceback
import types
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_auto_learn.py", "jarvis_sensitive.py")
sys.path.insert(0, str(HERE / "rebuilt"))
os.environ.setdefault("JARVIS_NO_EMBED", "1")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-auto-true-from-"))
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "memory.db")
_fw = sys.modules.get("jarvis_framework")
if _fw is None:
    _fw = types.ModuleType("jarvis_framework")
    _fw.LOG_DIR = _TMP
    _fw.audit_log = lambda *a, **k: None
    _fw.load_framework = lambda *a, **k: {}
    _fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = _fw
_fw.CONFIG_DIR = _TMP

import jarvis_memory as M  # noqa: E402
import jarvis_auto_learn as A  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_the_list_carries_the_day_the_words_give():
    st = M.MemoryStore(_TMP / "list.db", embedder=M.HashEmbedder())
    dated = st.add("Owner moved to Leeds in 2021", source="auto",
                   meta={"provenance": "typed", "device": "phone"})
    plain = st.add("Owner likes jazz", source="auto", meta={"provenance": "typed"})
    row = st.get(dated)
    check("the store read a date from the words (memory idea 4)",
          M.said_from(row.get("meta")), row)
    facts = {f["id"]: f for f in A.list_auto(store=st)["facts"]}
    want = date.fromtimestamp(float(row["valid_from"])).isoformat()
    check("a dated fact: true_from is the day its words give",
          facts[dated].get("true_from") == want == "2021-01-01", facts[dated])
    check("... a plain YYYY-MM-DD, never words",
          re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(facts[dated].get("true_from"))) is not None)
    check("a fact with no date in its words: no true_from", "true_from" not in facts[plain],
          facts[plain])
    check("the rest of the row is unchanged",
          set(facts[plain]) == {"id", "text", "saved_at", "provenance", "device"}, facts[plain])


def t_the_helper_says_nothing_for_a_damaged_row():
    good = {"true_from": "said"}
    check("unmarked meta: nothing", A._true_from_day({}, time.time()) is None)
    check("another mark: nothing", A._true_from_day({"true_from": "told"}, time.time()) is None)
    check("no valid_from: nothing", A._true_from_day(good, None) is None)
    check("text valid_from: nothing", A._true_from_day(good, "soon") is None)
    check("infinite valid_from: nothing", A._true_from_day(good, float("inf")) is None)
    check("zero valid_from: nothing", A._true_from_day(good, 0) is None)
    check("a huge valid_from: nothing, no exception", A._true_from_day(good, 1e20) is None)
    when = time.mktime((2024, 5, 3, 12, 0, 0, 0, 0, -1))
    check("a real one: that local day", A._true_from_day(good, when) == "2024-05-03",
          A._true_from_day(good, when))


if __name__ == "__main__":
    import shutil
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
