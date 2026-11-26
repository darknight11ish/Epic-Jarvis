#!/usr/bin/env python3
"""test_chat_flexibility.py - the same request in different words.

    python3 backend/test_chat_flexibility.py

WHAT THIS PROVES (2026-11-24, the owner's flexibility audit). The owner asked
whether Atlas understands a sentence that is *close* to the right one. A probe
of 54 plausible sentences against the real matcher measured 26 reaching code
(48%); the misses were almost all the same miss - "tell me what tools you
have" and "what tools are currently on" mean "what tools do you have", and a
set of whole-sentence patterns could not see it. `jarvis_quick.flex_normalise`
is that gap closed, and this suite is the audit made permanent.

THREE LISTS, and the middle one is the point:

  * REGRESSIONS - every sentence the audit measured reaching an intent BEFORE
    the normaliser. Each must still reach the same intent. The normaliser is
    retried only on a miss, so this list is the guarantee that it added routes
    and took none away.
  * LIFTS - the sentences the audit measured going to the model, which the
    normaliser must now carry to a named intent. Each one is a real sentence a
    person would type, not a pattern written to fit itself.
  * STAYS WITH THE MODEL - sentences that must NOT be claimed by this layer:
    an ambiguous "delete everything except this week" (files? chats?), and
    actions the model's own tools own (merging a pull request, reading the
    calendar). A normaliser that quietly captured those would be worse than
    the miss it replaced.

The numbers are re-measured here, so a change that lowers them fails this
suite instead of being discovered by the owner.
"""

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-flex-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")
sys.path.append(str(HERE / "rebuilt"))

import jarvis_quick as Q  # noqa: E402

NOW = time.time()
PASSED, FAILED = [], []

#: Measured by the audit BEFORE the normaliser existed. Same sentence, same
#: intent - the no-regression promise.
REGRESSIONS = (
    ("what tools do you have", "tools_inventory"),
    ("what tools do you have switched on", "tools_inventory"),
    ("what tools do you have around notes", "tools_inventory"),
    ("which of your tools ask first", "tools_asking"),
    ("which tools ask before they act", "tools_asking"),
    ("do any of your tools ask", "tools_asking"),
    ("what is connected", "connected_list"),
    ("what is connected right now", "connected_list"),
    ("what have you got connected", "connected_list"),
    ("which accounts are connected", "accounts_answer"),
    ("do i have github connected", "connect_account"),
    ("clear old chats", "forget_range"),
    ("delete my chat history", "forget_range"),
    ("clear chats older than 30 days", "history_purge"),
    ("can you delete chat history", "forget_range"),
    ("read my note grocery list", "note_read"),
    ("delete my note called draft", "note_delete"),
    ("open my notes", "open_app"),
    ("can you remind me every day at 11 to take my meds", "reminder_set"),
    ("set an alarm for 7am", "alarm_set"),
    ("change a setting", "settings_unknown"),
    ("turn off the wake word", "settings_wake_word"),
    ("switch on autostart", "settings_not_by_asking"),
    ("what github tools do you have", "github_self"),
    ("what can you do with github", "feature_capabilities"),
    ("check my mail", "honest_chat"),
)

#: Measured by the audit going to the MODEL, and the normaliser must now carry
#: each of them to the named intent.
LIFTS = (
    ("what tools are currently on", "tools_inventory"),
    ("which tools are on right now", "tools_inventory"),
    ("what are your active tools", "tools_inventory"),
    ("tell me what tools you have", "tools_inventory"),
    # 2026-11-25: the ANSWER to this one deliberately changed shape, not the
    # route. "list every tool you have" now reaches `tools_list_all` - the
    # complete inventory, one line per tool - because the owner's complaint was
    # that this question got the count answer's "and 17 more". "list all of
    # them" below keeps the summary: with no tool noun it does not say WHAT to
    # list, so it stays the safe count answer.
    ("list every tool you have", "tools_list_all"),
    ("list all of them", "tools_inventory"),
    ("how many tools are switched on", "tools_inventory"),
    ("what tools need my approval", "tools_asking"),
    ("whats hooked up", "connected_list"),
    ("can you clear all chat history except for any chat in the last week", "history_purge"),
    ("delete my chat history except the last 30 days", "history_purge"),
    ("what's on my calendar today", "local_calendar_read"),
)

#: Must keep going to the model. A normaliser is allowed to add routes, never
#: to claim a sentence whose meaning it does not know.
STAYS_WITH_MODEL = (
    "delete everything except this week",
    "merge my pull request",
    "what is failing on my pr",
    "do i have any email",
    "find a note about the boiler",
    # "all" alone must not turn an unrelated request into an inventory: this
    # names something to list, so it is not the tools question (2026-11-25).
    "list all the tools for painting",
)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def intent_of(text):
    got = Q.match(text, NOW)
    return getattr(got, "name", None)


def main() -> int:
    # ---- the normaliser itself, before any question is asked ----------------
    check("flex: a polite prefix is stripped and the sentence made canonical",
          Q.flex_normalise("Tell me what tools you have") == "what tools do you have",
          Q.flex_normalise("Tell me what tools you have"))
    check("flex: a contraction is expanded and the phrase is canonicalised",
          Q.flex_normalise("Whats hooked up") == "what is connected",
          Q.flex_normalise("Whats hooked up"))
    check("flex: a question mark and spaces do not matter",
          Q.flex_normalise("  what   tools do you have?  ") == "what tools do you have",
          Q.flex_normalise("  what   tools do you have?  "))
    check("flex: a sentence with no rule is returned unchanged",
          Q.flex_normalise("merge my pull request") == "merge my pull request",
          Q.flex_normalise("merge my pull request"))
    check("flex: 'except the last week' becomes a day range",
          Q.flex_normalise("clear all chat history except for any chat in the last week")
          == "clear chats older than 7 days",
          Q.flex_normalise("clear all chat history except for any chat in the last week"))

    # ---- no regression: everything that worked still works ------------------
    for text, want in REGRESSIONS:
        got = intent_of(text)
        check(f"still: {text!r} -> {want}", got == want, f"got {got!r}")

    # ---- the lifts: the sentences the owner actually typed ------------------
    for text, want in LIFTS:
        got = intent_of(text)
        check(f"now: {text!r} -> {want}", got == want, f"got {got!r}")

    # ---- and the line the normaliser must not cross -------------------------
    for text in STAYS_WITH_MODEL:
        got = intent_of(text)
        check(f"left alone: {text!r}", got is None, f"got {got!r}")

    # ---- the two numbers the audit published -------------------------------
    reached = sum(1 for text, _ in LIFTS if intent_of(text) is not None)
    total = len(REGRESSIONS) + len(LIFTS)
    hit = len(REGRESSIONS) + reached
    pct = round(100.0 * hit / total)
    check(f"the measured reach is {hit}/{total} ({pct}%), up from 26/54 (48%)",
          pct >= 60, f"{hit}/{total} = {pct}%")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                   # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
