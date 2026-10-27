"""test_settings_help.py - "what can I change?", and where the answer comes from.

    python backend/test_settings_help.py

THE OWNER'S DECISION (2026-10-10)
    He asked to change every setting by talking to Jarvis. Most of that already
    worked - "turn off web search" and ten more phrases act through
    jarvis_settings_registry.BOOL_SETTINGS, and each setting's own setter
    decides whether it needs an approval card. What was missing is that Jarvis
    could not TELL him what he may change: "what can I change?" reached the AI
    model, which invented an answer - naming switches that do not exist, and
    never saying that a change which loosens a rule still raises a card.

WHAT THIS PROVES
    The answer is DERIVED from the real switches, so it cannot promise a
    setting that is not there and cannot miss one that is. Every check fails on
    the code before this change: there was no `settings_help` intent at all, so
    "what can I change?" was the model's to answer.

No model, no network, no port.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
# 1. The question is answered here, not by the model
# --------------------------------------------------------------------------

print("--- the question is ours to answer ---")
for phrase in ("what can I change",
               "what can I change?",
               "what settings can I change",
               "what can I change by talking to you",
               "which settings can I change",
               "what settings do you have",
               "what settings are there",
               "list my settings",
               "list the settings",
               "what can I change in settings"):
    m = Q.match(phrase)
    check(f"'{phrase}' is answered here",
          m is not None and m.name == "settings_help",
          f"got {m.name if m else 'the model'}")
print()

# --------------------------------------------------------------------------
# 2. It is not a way round the gate: a loosening still raises its card
# --------------------------------------------------------------------------

print("--- a loosening is still a card, and is not a 'change' ---")
# These must keep their own intents. If "what can I change" had been written as
# a loose pattern, one of these could be swallowed by it - and a phrase that
# LOOSENS a rule must never be routed to a help answer.
for phrase, want in (("turn on lights without asking", "settings_bool"),
                     ("turn off web search", "settings_bool"),
                     ("stop asking before jarvis reads my calendar", "settings_asks_first"),
                     ("turn off weather", "animal_weather")):
    m = Q.match(phrase)
    check(f"'{phrase}' still goes to {want}",
          m is not None and m.name == want,
          f"got {m.name if m else 'the model'}")
print()

# --------------------------------------------------------------------------
# 3. The words come off the real switches, not a second list
# --------------------------------------------------------------------------

print("--- the answer is built from the real switches ---")
data = R.changeable_settings()
check("every real on/off switch is offered",
      data["count"] >= len(R.BOOL_SETTINGS),
      f"offered {data['count']}, switches exist {len(R.BOOL_SETTINGS)}")
check("there is at least one switch, so the answer is not empty",
      data["count"] >= 5, str(data["count"]))
real_names = [b.names[0] for b in R.BOOL_SETTINGS if b.names]
for name in real_names:
    check(f"the answer names '{name}'", name in data["words"])

# The strongest check: a switch added to the table appears by itself. This is
# what stops the offered list drifting away from what phrases can reach.
extra = R.BoolSetting("test_only_switch", ("a setting added by the test",),
                      None, R.set_prompt_coach)
R.BOOL_SETTINGS = R.BOOL_SETTINGS + (extra,)
try:
    after = R.changeable_settings()
    check("a switch added to the table is offered by itself",
          "a setting added by the test" in after["words"],
          after["words"][:200])
    check("and it raises the count by exactly one",
          after["count"] == data["count"] + 1,
          f"{data['count']} -> {after['count']}")
finally:
    R.BOOL_SETTINGS = R.BOOL_SETTINGS[:len(R.BOOL_SETTINGS) - 1]
    R._BOOL_BY_NAME = {R._bare(n): b for b in R.BOOL_SETTINGS for n in b.names}
unchanged = R.changeable_settings()
check("and removing it again leaves the answer as it was",
      unchanged["count"] == data["count"], f"{unchanged['count']} vs {data['count']}")
print()

# --------------------------------------------------------------------------
# 3b. THE ANSWER IS NOT ALLOWED TO UNDERSTATE WHAT IS REACHABLE
# --------------------------------------------------------------------------

print("--- every reachable family is in the answer (the 13 -> 42 fix) ---")
# WHAT THIS IS FOR. The answer used to offer only BOOL_SETTINGS - 13 settings -
# while far more were reachable by asking, so the owner was told he could not
# do things he could. A completeness test that cannot fail is decoration, so
# the check below is made to bite: removing a family from the table fails it.
try:
    import jarvis_animal as _AN
    _animal_switches = len(_AN.SWITCHES)
except Exception:
    _animal_switches = 0

# Each family, and the source that owns it. `expect` is the number of settings
# that source declares, so a family that shrinks or grows unnoticed fails here.
_FAMILIES = [
    ("the asks-first switches", len(R.asks_first_targets())),
    ("the reading tools offered to the model", len(R.tool_targets())),
    ("the shared animal switches", _animal_switches),
]
for label, n in _FAMILIES:
    check(f"{label} are counted somewhere in the answer ({n})",
          n > 0 and n <= data["count"],
          f"{label}={n}, answer count={data['count']}")

# The families whose tables live in other modules, named so the answer must
# mention each one. This is the list that would have been MISSING before the
# change: every one of these was absent from the old 13-item answer.
_MUST_APPEAR = [
    ("what asks first", "the asks-first switches"),
    ("animal faces", "the animal options"),
    ("sun and moon", "the sky option"),
    ("weather", "the weather source"),
    ("approval card is shown", "how much of a card is shown"),
    ("speak up", "the interruption budget"),
    ("how Jarvis talks", "the manner"),
    ("menu", "menu visibility"),
    ("thinks before answering", "the thinking level"),
    ("Lockdown", "Lockdown"),
    # 2026-10-26: the two switches that are not BOOL_SETTINGS/CHOICE_SETTINGS
    # rows. If either stops being counted, the answer understates what can be
    # changed - the exact failure the 13 -> 42 fix above was about.
    ("wake word", "the wake word (\"hey Jarvis\")"),
    ("which browser Jarvis uses", "which browser Jarvis uses"),
]
for needle, label in _MUST_APPEAR:
    check(f"the answer mentions {label}",
          needle.lower() in data["words"].lower(),
          f"{label!r} (looking for {needle!r}) missing from:\n{data['words'][:400]}")

check("the answer says how many settings it covers",
      str(data["count"]) in data["words"],
      data["words"][:160])
check("that number is well above the 13 switches alone, since the rest are reachable",
      data["count"] > len(R.BOOL_SETTINGS) + 10,
      f"count={data['count']}, switches={len(R.BOOL_SETTINGS)}")

# AND THE HARDER HALF: every family the answer advertises must really be
# reachable. A row that promises something no phrase can do is worse than an
# omission, because the owner will try it and be refused. Each phrase below is
# run through the real intent matcher, so a family whose grammar disappeared
# fails here rather than in his hands.
_REACHABLE_BY = [
    ("keep the animal still", "the shared animal switches"),
    ("show the sun and moon", "the sky option"),
    ("turn the weather on", "the weather source"),
    ("make the animal sharper", "per-device sharpness"),
    ("start short", "how much of a card is shown"),
    ("speak up 3 times a day", "the interruption budget"),
    ("from now on, be plainer", "the manner"),    ("hide the finance menu", "menu visibility"),
    ("turn on lockdown", "Lockdown"),
    ("switch to exa for search", "the web search provider"),
    # 2026-10-26 - the two that are not table rows.
    ("turn on the wake word", "the wake word"),
    ("set the browser to headless", "which browser Jarvis uses"),
]
for phrase, label in _REACHABLE_BY:
    m = Q.match(phrase)
    check(f"a phrase really reaches {label} ({phrase!r})",
          m is not None,
          f"{phrase!r} reached the model instead of an intent - the answer must "
          f"not advertise {label} if nothing can do it")
print()

# --------------------------------------------------------------------------
# 4. The answer says what matters, and reads like words
# --------------------------------------------------------------------------

print("--- what the answer must say ---")
words = data["words"]
check("it says these can be changed by asking", "by asking" in words, words[:120])
check("it says a loosening still shows a card first",
      "card" in words and "loosen" in words, words[-160:])
check("it says the word to take a change back",
      "undo" in words, words[-120:])
check("it is not an empty sentence", len(words) > 60, words)
check("it has no markdown bullets, because it may be read aloud",
      "\n" not in words and " - " not in words and "*" not in words, repr(words[:120]))
check("it names more than one setting", words.count(";") >= 2, words)
print()

# --------------------------------------------------------------------------
# 5. Nothing to offer is said plainly, never an empty answer
# --------------------------------------------------------------------------

print("--- when there is nothing to offer ---")
empty = R.changeable_words(rows=[])
check("an empty table gives words, not a blank answer", bool(empty.strip()), repr(empty))
check("and it says where settings do live", "Settings" in empty, empty)
print()

# --------------------------------------------------------------------------
# 6. Running it changes nothing and uses no model
# --------------------------------------------------------------------------

print("--- running the answer ---")
res = Q.run(Q.Intent("settings_help"), None, 0.0)
check("the intent runs and returns an answer", res is not None)
check("the answer is a sentence the owner can read",
      res is not None and len(res.reply) > 60, res.reply[:120] if res else "None")
check("it reports itself as settings_help, so the route header says so",
      res is not None and res.intent == "settings_help")
check("it asks for no approval card",
      res is not None and getattr(res, "open_settings", None) is None)
check("the answer names a real switch",
      res is not None and R.BOOL_SETTINGS[0].names[0] in res.reply,
      res.reply[:200] if res else "None")
print()

print(f"PASS {len(PASSED)}   FAIL {len(FAILED)}")
if FAILED:
    print()
    for name in FAILED:
        print(f"FAILED: {name}")
sys.exit(1 if FAILED else 0)
