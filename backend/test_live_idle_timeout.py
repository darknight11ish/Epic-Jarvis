"""test_live_idle_timeout.py - how long Jarvis Live waits before it turns off.

    python -B backend/test_live_idle_timeout.py

THE OWNER'S ASK (2026-11-01): "also id likee to he able to tell jarvis to change
the setting that turns off jarvos live by extending how long ot takestoo turn
off when it doesntt hear anything". He asked for it BOTH by talking to Jarvis
(chat and Live) AND in Settings on the PC and the phone.

ONE SOURCE OF TRUTH, and this file is built around it: `[live].quiet_s` in the
owner's settings file. `jarvis_live.quiet_seconds()` is the engine's reader, the
`live_idle_seconds` row in `jarvis_limits.py` owns the default (90 s), the range
(30 s..600 s), the step (30 s for the two apps' -/+ controls) and the words, and
`jarvis_settings_registry.set_live_idle` writes it by calling the very function
`POST /api/limits/settings` calls. Nothing here pins a number in a second place.

WHAT IS PROVED, in order:

1. **The default IS today's behaviour.** The shipped file says 90 s, the engine
   reads 90 s, and a session ends after 90 seconds of quiet - not after 89, and
   not after 91.
2. **Asking changes it, and the engine acts on the new number.** "make Jarvis
   Live wait three minutes" goes through the real phrase matcher and the real
   runner, and a NEW session then lasts 180 seconds of quiet, not 90 - read back
   through `jarvis_live.quiet_seconds()`, the same function the engine's tick
   calls, and shown by a session that is still on at 179 s and ends at 181.
3. **Out of range is refused, in words that name the range, and nothing is
   written.** Both the spoken lane and the route itself refuse 5 s and 2 hours.
4. **The spoken reply names the new value AND the accepted range** - the
   owner's own example, "Okay - Jarvis Live will now wait three minutes before
   turning off" - and the ASK answer names the current value and the range.
5. **The desktop AND phone catalogues carry it**, with the same title, range,
   unit and step, because both screens read the one row through `view(app=...)`.
6. **The change goes through the same path as every other settings change.**
   The spoken sentence calls `jarvis_limits.change` - the exact function the
   route calls - and the row's own direction decides whether a card is raised:
   this row raises none in either direction, while an "up" row of the same table
   still raises ONE and writes nothing without a yes. The lane invents no tier.
7. **A hand-edited nonsense value cannot defeat the bounds**: 99999 clamps to
   600, 1 clamps to 30, and text falls back to the 90 s default.
8. **The grammar is narrow**: the owner's sentences reach it, and a timer, "turn
   off jarvis live" and "the idle timeout" (the chat's own client-side row) do
   not.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

os.environ.setdefault("JARVIS_TEST_UNSEALED_FIXTURES", "1")
require_shipped("jarvis_live.py", "jarvis_limits.py", "jarvis_settings_registry.py",
                "jarvis_quick.py", "jarvis_framework.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-live-idle-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
# The undo receipt's own store: never the owner's real receipts.db (2026-11-03).
os.environ["JARVIS_RECEIPTS_DB"] = str(TMP / "receipts.db")

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"

import jarvis_limits as JL  # noqa: E402
import jarvis_live as LIVE  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fresh(text: str = None) -> Path:
    """The owner's settings file again: the shipped one, or `text` verbatim."""
    p = TMP / "jarvis-framework.toml"
    if text is None:
        shutil.copyfile(SHIPPED, p)
    else:
        p.write_bytes(text.encode("utf-8"))
    JL._reload()
    return p


def file_bytes() -> bytes:
    return (TMP / "jarvis-framework.toml").read_bytes()


def quiet_line() -> str:
    """The one line in the file that carries the number, as written.

    The key is compared, not a prefix: the notifications table above it has
    `quiet_start`/`quiet_end`, and `"quiet_start".startswith("quiet_s")` is
    true - which is exactly the kind of slip this helper would hide."""
    for line in (TMP / "jarvis-framework.toml").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key == "quiet_s":
            return line.strip()
    return ""


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = float(t)

    def __call__(self):
        return self.t


class World:
    """A Live session driven by a clock, the way backend/test_live.py does it:
    no loop thread, no model, no microphone."""

    def __init__(self):
        self.clock = Clock()
        self.engine = LIVE.Live(clock=self.clock, run_loop=False,
                                publish=lambda kind, detail: None,
                                cards_waiting=lambda: [],
                                windows_locked=lambda: None,
                                voice_ready=lambda device: None,
                                power_mode=lambda: "active",
                                warm=lambda: None)


def quiet_end_at(seconds: int):
    """Start a session, wait `seconds` of quiet, one tick: (still_on, ended)."""
    w = World()
    w.engine.start("phone")
    w.clock.t += seconds
    w.engine.tick()
    st = w.engine.status()
    return st["on"], st["ended"]


def say(text: str):
    """"The fast path's own answer to `text`, or None when it would use the
    model. Runs the REAL matcher and the REAL runner - nothing is stubbed."""
    intent = Q.match(text)
    if intent is None:
        return None, None
    if intent.name not in ("live_idle_ask", "live_idle_set"):
        return intent, None
    return intent, Q.run(intent, None, 1_800_000_000.0)


# --------------------------------------------------------------------------
# 1. the default IS today's behaviour
# --------------------------------------------------------------------------

def t_the_default_is_the_behaviour_live_always_had():
    fresh()
    row = JL.find("live_idle_seconds")
    check("the limits table owns the window, defaulting to 90 s",
          row is not None and row.kind == "int" and row.default == 90,
          None if row is None else (row.kind, row.default))
    check("...and it is bounded 30 s..10 minutes, with a 30 s step for the apps",
          row is not None and (row.low, row.high, row.step) == (30, 600, 30),
          None if row is None else (row.low, row.high, row.step))
    check("the shipped settings file really carries quiet_s = 90",
          quiet_line() == "quiet_s = 90", quiet_line())
    check("the engine reads that key: quiet_seconds() == 90",
          LIVE.quiet_seconds() == 90, LIVE.quiet_seconds())
    check("the engine's own fallback bounds agree with the row",
          (LIVE.QUIET_MIN_S, LIVE.QUIET_MAX_S) == (row.low, row.high),
          (LIVE.QUIET_MIN_S, LIVE.QUIET_MAX_S, row.low, row.high))
    # The behaviour, not just the number: 89 s of quiet keeps the session, and
    # 91 s (one tick past the window) ends it with the reason the apps word as
    # "It was quiet."
    check("a session is still on after 89 seconds of quiet",
          quiet_end_at(89) == (True, None), quiet_end_at(89))
    on, ended = quiet_end_at(91)
    check("...and ends on the quiet timeout just after 90 seconds",
          on is False and ended == "quiet", (on, ended))
    # The status the two apps draw says the same number.
    w = World()
    w.engine.start("phone")
    st = w.engine.status()
    check("the status both apps read reports 90 s, and a countdown that starts there",
          st["limits"]["quiet_s"] == 90 and st["quiet_left_s"] == 90,
          (st["limits"]["quiet_s"], st["quiet_left_s"]))


# --------------------------------------------------------------------------
# 2. asking changes it, and the new number drives the engine
# --------------------------------------------------------------------------

def t_asking_changes_it_and_the_engine_uses_the_new_number():
    fresh()
    intent, out = say("make jarvis live wait three minutes")
    check("the owner's change sentence reaches the Live idle setting",
          intent is not None and intent.name == "live_idle_set"
          and intent.f.get("seconds") == 180,
          None if intent is None else (intent.name, intent.f))
    check("...and the file really moved to 180 s", quiet_line() == "quiet_s = 180",
          quiet_line())
    check("...and the engine reads the NEW value: quiet_seconds() == 180",
          LIVE.quiet_seconds() == 180, LIVE.quiet_seconds())
    check("...and a session is still on after 179 seconds of quiet",
          quiet_end_at(179) == (True, None), quiet_end_at(179))
    on, ended = quiet_end_at(181)
    check("...and ends just after 180, not at the old 90",
          on is False and ended == "quiet", (on, ended))
    w = World()
    w.engine.start("phone")
    st = w.engine.status()
    check("the apps' own status reports the new window",
          st["limits"]["quiet_s"] == 180 and st["quiet_left_s"] == 180,
          (st["limits"]["quiet_s"], st["quiet_left_s"]))
    # Every way of saying it reaches the same key: the owner's own sentence, the
    # timeout by name, and the timeout with a length on the end.
    for phrase, want in (
            ("set the jarvis live timeout to 45 seconds", 45),
            ("change the live idle timeout to 5 minutes", 300),
            ("jarvis live should wait two minutes before it turns off", 120),
            ("change how long before jarvis live turns off when it hears "
             "nothing to ten minutes", 600),
            ("make live wait ninety seconds", 90)):
        fresh()
        got, _ = say(phrase)
        check(f"{phrase!r} sets {want} s",
              got is not None and got.name == "live_idle_set"
              and got.f.get("seconds") == want and LIVE.quiet_seconds() == want,
              None if got is None else (got.name, got.f, LIVE.quiet_seconds()))


# --------------------------------------------------------------------------
# 3. out of range: refused, in words, with nothing written
# --------------------------------------------------------------------------

def t_out_of_range_is_refused_and_changes_nothing():
    for phrase in ("make jarvis live wait 5 seconds", "make jarvis live wait 2 hours",
                   "set the jarvis live timeout to 11 minutes"):
        fresh()
        before = file_bytes()
        intent, out = say(phrase)
        check(f"{phrase!r} reaches the setting", intent is not None, None)
        reply = "" if out is None else out.reply
        check("...is refused in words that name the accepted range",
              "outside what I can set" in reply
              and "from 30 seconds to 10 minutes" in reply, reply)
        check("...says plainly that nothing changed",
              "Nothing was changed" in reply, reply)
        check("...and the settings file is byte-for-byte as it was",
              file_bytes() == before and quiet_line() == "quiet_s = 90",
              (quiet_line(), len(file_bytes()), len(before)))
        check("...and the engine still reads 90", LIVE.quiet_seconds() == 90,
              LIVE.quiet_seconds())
    # The route itself refuses too - the spoken lane asks first so the owner
    # hears a length, but the PC's own check is not relaxed for chat.
    fresh()
    before = file_bytes()
    code, out = JL.change({"key": "live_idle_seconds", "value": 1})
    check("the route refuses 1 s with a 400 and its own range sentence",
          code == 400 and "between 30 and 600" in str(out.get("error") or ""), out)
    code, out = JL.change({"key": "live_idle_seconds", "value": 601})
    check("...and 601 s too", code == 400, out)
    check("...and neither refusal wrote anything", file_bytes() == before)


# --------------------------------------------------------------------------
# 4. the spoken reply: the new value AND the range, in plain words
# --------------------------------------------------------------------------

def t_the_spoken_reply_names_the_value_and_the_range():
    fresh()
    _, out = say("make jarvis live wait three minutes before turning off")
    reply = "" if out is None else out.reply
    check("the change is answered in the owner's own shape",
          reply.startswith("Okay") and "Jarvis Live will now wait 3 minutes "
          "before turning off when it hears nothing" in reply, reply)
    check("...and the reply names the accepted range",
          "from 30 seconds to 10 minutes" in reply, reply)
    check("...and says where else it can be changed",
          "Settings on your PC or phone" in reply, reply)
    # The ASK answer: the current value and the range, and nothing written.
    fresh()
    before = file_bytes()
    intent, out = say("how long before jarvis live turns off when it hears nothing")
    reply = "" if out is None else out.reply
    check("the question is the read, not a change",
          intent is not None and intent.name == "live_idle_ask", None if intent is None else intent)
    check("it names the current value in words", "1 minute and 30 seconds" in reply, reply)
    check("...and the whole accepted range", "from 30 seconds to 10 minutes" in reply, reply)
    check("...and writes nothing at all", file_bytes() == before)
    # Asking twice must not write twice, and must say it is already that value.
    _, out = say("make jarvis live wait three minutes")
    _, again = say("make jarvis live wait three minutes")
    check("asking for the value already in force says 'already' and changes nothing",
          again is not None and "already waits 3 minutes" in again.reply
          and "Nothing was changed" in again.reply, None if again is None else again.reply)


# --------------------------------------------------------------------------
# 5. both Settings catalogues carry it - the same row, so the same words
# --------------------------------------------------------------------------

def t_the_desktop_and_phone_catalogues_carry_it():
    fresh()
    desktop = {r["key"]: r for r in JL.view(app="desktop")["limits"]}
    phone = {r["key"]: r for r in JL.view(app="phone")["limits"]}
    check("the desktop's Settings catalogue has the row", "live_idle_seconds" in desktop,
          sorted(desktop))
    check("the phone's Settings catalogue has the row", "live_idle_seconds" in phone,
          sorted(phone))
    if "live_idle_seconds" not in desktop or "live_idle_seconds" not in phone:
        return
    d, p = desktop["live_idle_seconds"], phone["live_idle_seconds"]
    check("both apps are offered the same title, value, range, unit and step",
          (d["title"], d["value"], d["low"], d["high"], d["unit"], d["step"])
          == (p["title"], p["value"], p["low"], p["high"], p["unit"], p["step"]),
          (d, p))
    check("the row is offered to both, and is not PC-only",
          d["app"] == "both" and p["app"] == "both"
          and d["pc_only"] is False and p["pc_only"] is False, (d["app"], d["pc_only"]))
    check("its words are a length of time, never a bare number of seconds",
          d["words"] == "1 minute and 30 seconds", d["words"])
    check("it is in each app's own list (limits_for), not only the full view",
          any(r.key == "live_idle_seconds" for r in JL.limits_for("desktop"))
          and any(r.key == "live_idle_seconds" for r in JL.limits_for("phone")))
    check("the row's note says it never starts Live and never opens the microphone",
          "never starts Live" in d["note"] and "never opens the microphone" in d["note"],
          d["note"])


# --------------------------------------------------------------------------
# 6. the same path as every other settings change - no new tier
# --------------------------------------------------------------------------

class Gate:
    """Stands in for jarvis_gate the way backend/test_limits.py does: records
    every card it is asked for and answers with `allowed`."""

    class Verdict:
        def __init__(self, allowed):
            self.allowed = allowed
            self.outcome = "approved" if allowed else "denied"
            self.tier = "ask"

    def __init__(self, allowed=True):
        self.allowed, self.calls = allowed, []

    def __call__(self, action, detail, prompt=None):
        self.calls.append((action, dict(detail or {})))
        return self.Verdict(self.allowed)


def t_the_change_goes_through_the_same_path_and_the_row_owns_the_card():
    fresh()
    real_change = JL.change
    calls = []

    def recording_change(body, **kwargs):
        calls.append(dict(body))
        return real_change(body, **kwargs)

    JL.change = recording_change
    try:
        _, out = say("make jarvis live wait four minutes")
    finally:
        JL.change = real_change
    check("the spoken sentence calls jarvis_limits.change itself, with the key "
          "and the number",
          calls == [{"key": "live_idle_seconds", "value": 240}] and out is not None
          and "will now wait 4 minutes" in out.reply,
          (calls, None if out is None else out.reply))
    check("...which is the function the settings route calls: both write the same key",
          quiet_line() == "quiet_s = 240", quiet_line())
    # The route, by hand, on the same row: this is what both Settings screens do.
    code, out = JL.handle_post(JL.ROUTE, {"key": "live_idle_seconds", "value": 300})
    check("POST /api/limits/settings sets the same value",
          code == 200 and quiet_line() == "quiet_s = 300" and LIVE.quiet_seconds() == 300,
          (code, quiet_line()))
    # NO CARD IN EITHER DIRECTION for this row (Live is already running; the
    # microphone is already open), and the same function still asks on a row
    # whose own direction loosens - so the lane did not weaken the table.
    gate = Gate(allowed=True)
    JL.configure(gate=gate, tier_of=lambda action: "ask")
    try:
        fresh()
        JL.change({"key": "live_idle_seconds", "value": 600})
        JL.change({"key": "live_idle_seconds", "value": 30})
        live_cards = list(gate.calls)
        code, out = JL.change({"key": "undo_window", "value": 168})
        other_cards = list(gate.calls)
    finally:
        JL.configure(gate=None, tier_of=None)
    check("this row raises NO card in either direction", live_cards == [], live_cards)
    check("...while a raising row of the same table still asks, through the same function",
          len(other_cards) == 1 and other_cards[0][0] == JL.RAISE_ACTION, other_cards)
    check("...and the raising row's card carries its own words, not this row's",
          bool(other_cards) and other_cards[0][1].get("limit") == "undo_window",
          other_cards)
    # A DENIED card on that raising row writes nothing and says so.
    fresh()
    before = file_bytes()
    JL.configure(gate=Gate(allowed=False), tier_of=lambda action: "ask")
    try:
        code, out = JL.change({"key": "undo_window", "value": 168})
    finally:
        JL.configure(gate=None, tier_of=None)
    check("...a denied raise is a 409 in words and the file is untouched",
          code == 409 and file_bytes() == before, (code, out))


# --------------------------------------------------------------------------
# 7. a hand-edited value cannot defeat the bounds
# --------------------------------------------------------------------------

def t_a_hand_edited_value_is_clamped_or_ignored():
    fresh("[live]\nquiet_s = 99999\n")
    check("99999 s is clamped to the row's 600 s high", LIVE.quiet_seconds() == 600,
          LIVE.quiet_seconds())
    fresh("[live]\nquiet_s = 1\n")
    check("1 s is clamped to the row's 30 s low", LIVE.quiet_seconds() == 30,
          LIVE.quiet_seconds())
    fresh("[live]\nquiet_s = nonsense\n")
    check("nonsense falls back to the 90 s default", LIVE.quiet_seconds() == 90,
          LIVE.quiet_seconds())
    fresh("# no [live] table at all\n[undo]\nttl_hours = 24\n")
    check("a file with no [live] table behaves exactly as it did: 90 s",
          LIVE.quiet_seconds() == 90, LIVE.quiet_seconds())


# --------------------------------------------------------------------------
# 8. the grammar is narrow
# --------------------------------------------------------------------------

def t_the_grammar_is_narrow():
    fresh()
    for phrase in ("how long before jarvis live turns off when it hears nothing",
                   "how long does jarvis live wait before it turns off",
                   "what is the jarvis live timeout",
                   "how long does jarvis live wait when it hears nothing"):
        got = Q.match(phrase)
        check(f"{phrase!r} is the READ", got is not None and got.name == "live_idle_ask",
              None if got is None else got.name)
    for phrase in ("remind me in 3 minutes", "turn off jarvis live",
                   "what is the idle timeout", "change the idle timeout to 3 minutes",
                   "stop jarvis live", "make the timer 3 minutes",
                   "make jarvis live sing for three minutes",
                   "make jarvis live wait a bit"):
        got = Q.match(phrase)
        check(f"{phrase!r} is NOT the Live idle setting",
              got is None or got.name not in ("live_idle_ask", "live_idle_set"),
              None if got is None else got.name)
    check("...and none of those wrote anything", quiet_line() == "quiet_s = 90",
          quiet_line())
    check("the owner's own sentence is in the changeable list",
          "live idle" in " ".join(n for n, _ in R.changeable_settings()["switches"]).lower()
          or "jarvis live waits" in R.changeable_settings()["words"].lower(),
          R.changeable_settings()["words"][:200])
    check("the backend's capability report names it, so a newer app can tell "
          "an older backend cannot",
          "limit:live_idle_seconds" in R.capability_keys(),
          [k for k in R.capability_keys() if k.startswith("limit:")])


def t_a_cardless_change_leaves_one_receipt_and_undo_puts_it_back():
    """BUG 6, the number half (2026-11-03 audit).

    *"A cardless change leaves ONE undo receipt"* was false for exactly the
    settings this slice's headline names: this runner set the number and wrote
    no receipt, so "say undo in the same chat" had nothing to take back.

    Now the change leaves one row under `change_setting` holding the NUMBER in
    seconds - the value `set_live_idle` takes, not the words "3 minutes" - and
    "undo" puts the old window back through the same writer.
    """
    import jarvis_receipts as RC

    class Sched:
        def last_set(self, cid, now):
            return None

    fresh()
    rows = len(RC.recent(200))
    intent = Q.match("make jarvis live wait three minutes")
    check("the sentence reaches the setting",
          intent is not None and intent.name == "live_idle_set",
          None if intent is None else intent.name)
    out = Q.run(intent, None, 1_800_000_000.0, conversation="live-idle-undo")
    check("...the window really moved to 180 s", LIVE.quiet_seconds() == 180,
          (LIVE.quiet_seconds(), None if out is None else out.reply))
    now_rows = RC.recent(200)
    check("...and it left exactly ONE receipt", len(now_rows) == rows + 1,
          (rows, len(now_rows)))
    newest = now_rows[0] if now_rows else {}
    check("...under the settings tool's own name",
          newest.get("tool_name") == Q.SETTINGS_RECEIPT_TOOL, newest.get("tool_name"))
    check("...holding the NUMBER it changed from, never the words",
          (newest.get("before") or {}).get("value") == 90, newest.get("before"))
    undo = Q._run_undo({"noun": None, "soft": False}, Sched(),
                       1_800_000_000.0, "live-idle-undo")
    check("'undo' puts the old window back through the same writer",
          LIVE.quiet_seconds() == 90,
          (LIVE.quiet_seconds(), None if undo is None else undo.reply))
    check("...and the settings file says so", quiet_line() == "quiet_s = 90",
          quiet_line())
    check("...and the receipt is marked undone",
          RC.get(str(newest.get("receipt_id") or "")).get("undone") is True,
          RC.get(str(newest.get("receipt_id") or "")))


def main():
    for fn in (t_the_default_is_the_behaviour_live_always_had,
               t_asking_changes_it_and_the_engine_uses_the_new_number,
               t_out_of_range_is_refused_and_changes_nothing,
               t_the_spoken_reply_names_the_value_and_the_range,
               t_the_desktop_and_phone_catalogues_carry_it,
               t_the_change_goes_through_the_same_path_and_the_row_owns_the_card,
               t_a_hand_edited_value_is_clamped_or_ignored,
               t_a_cardless_change_leaves_one_receipt_and_undo_puts_it_back,
               t_the_grammar_is_narrow):
        print(f"\n--- {fn.__name__} ---")
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  - {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
