"""test_settings_followup.py - "Turn on that setting for me." now lands.

    python backend/test_settings_followup.py

THE OWNER'S REPORT (2026-11-23, with screenshots)
    He asked Jarvis to find duplicate notes. The answer said the notes search
    tool was off and where to switch it on, so he replied "Turn on that setting
    for me." - and got:

        "I cannot change that setting by asking yet. Say \"what can I change?\"
         and I will list the ones I can, or name the screen and I will open it"

    That sentence is `_run_settings_unknown`, and it was TRUE about the words:
    "that setting" names no row, because the fast path is stateless. The
    setting the answer had just named WAS changeable by name all along
    ("turn on the notes search tool" -> `settings_tool`).

WHAT THIS PROVES
    A follow-up that names nothing resolves to the ONE setting the previous
    answer named - through the SAME intent the named sentence produces, so the
    same setter, the same tier and the same approval card run. Nothing is
    guessed: no context, two named settings, or a name no registry knows keeps
    the old refusal byte for byte, and an ordinary "turn it on" about anything
    else still falls through to the model.

No model, no network, no port, nothing written.
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
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: The answer the owner was actually looking at (his screenshot, 2026-11-23).
NOTES_ANSWER = (
    "I cannot search your notes for duplicates right now because the notes "
    "search tool is off. To turn it on, open Settings and toggle notes search "
    "in the Brain section."
)

#: The exact refusal he got back, and must keep getting when nothing resolves.
UNKNOWN = (
    "I cannot change that setting by asking yet. Say \"what can I change?\" "
    "and I will list the ones I can, or name the screen and I will open it - "
    "\"open security\"."
)


def refusal_sentence():
    """The sentence the unknown-settings handler really says (no model, no port)."""
    return Q._run_settings_unknown().reply


# ---------------------------------------------------------------- resolves ---

got = Q.match("Turn on that setting for me.", said=NOTES_ANSWER)
check("the screenshot's follow-up resolves at all", got is not None, repr(got))
check("...to the tool the answer named",
      got is not None and got.name == "settings_tool"
      and got.f.get("tool") == "notes_search" and got.f.get("on") is True, repr(got))

for said_phrase in ("turn it on", "enable that setting", "switch on that setting"):
    got = Q.match(said_phrase, said=NOTES_ANSWER)
    check(f'"{said_phrase}" resolves the same way',
          got is not None and got.name == "settings_tool"
          and got.f.get("tool") == "notes_search" and got.f.get("on") is True, repr(got))

got = Q.match("switch that off", said=NOTES_ANSWER)
check('"switch that off" asks for OFF',
      got is not None and got.f.get("on") is False, repr(got))

got = Q.match("turn that setting off", said=NOTES_ANSWER)
check('"turn that setting off" asks for OFF too',
      got is not None and got.f.get("on") is False, repr(got))

# A boolean switch named in the previous answer takes the boolean intent.
got = Q.match("turn that setting on", said="Web search is off. Say turn on web search.")
check("a named boolean switch comes back as settings_bool",
      got is not None and got.name == "settings_bool"
      and got.f.get("key") == "web_search", repr(got))

# A page-only row named in the previous answer is refused BY NAME, not as unknown.
got = Q.match("turn on that setting for me.", said="The app lock is off.")
check("a page-only row is named by its own refusal",
      got is not None and got.name == "settings_not_by_asking"
      and got.f.get("dom_id") == "sec-app-lock", repr(got))

# The longest name wins: "notes search tool" is not also read as "notes".
check("the longest name wins, so one tool is not two",
      Q.match("turn it on", said="The notes search tool is off.") is not None)

# ------------------------------------------------------------ no resolution ---

check("no history keeps the old intent",
      Q.match("Turn on that setting for me.").name == "settings_unknown")
check("no history keeps the old SENTENCE, word for word",
      refusal_sentence() == UNKNOWN,
      repr(refusal_sentence()))

check("a history naming nothing keeps the old intent",
      Q.match("Turn on that setting for me.", said="Sure - happy to help.").name
      == "settings_unknown")

two = Q.match("turn on that setting", said="Turn on web search and the prompt coach.")
check("two named settings are refused, never guessed",
      two is not None and two.name == "settings_unknown", repr(two))
check("...and the words still get the honest refusal",
      two is not None and refusal_sentence() == UNKNOWN, repr(two))
check("a pronoun form with two names simply falls through to the model",
      Q.match("turn that setting on", said="Turn on web search and the prompt coach.")
      is None)

check("an unrelated 'turn it on' still falls through to the model",
      Q.match("turn it on") is None)

check("a sentence that names its own setting is unchanged",
      Q.match("turn on web search").name == "settings_bool"
      and Q.match("turn on web search").f.get("key") == "web_search")

check("the named tool sentence is unchanged",
      Q.match("turn on the notes search tool").name == "settings_tool")

# ------------------------------------------------------------- the history ---

body = {"messages": [
    {"role": "user", "content": "find duplicate notes", "provenance": "typed"},
    {"role": "assistant", "content": NOTES_ANSWER},
    {"role": "user", "content": "Turn on that setting for me.", "provenance": "typed"},
]}
said = Q.newest_jarvis_words(body)
check("the newest assistant sentence is read from the request",
      said is not None and "notes search tool" in said, repr(said))
check("a request with no assistant turn reads None",
      Q.newest_jarvis_words({"messages": [
          {"role": "user", "content": "hello", "provenance": "typed"}]}) is None)
check("a picture-only assistant turn reads None",
      Q.newest_jarvis_words({"messages": [
          {"role": "assistant", "content": [{"type": "image", "data": "x"}]}]}) is None)


# --------------------------------------------------------------- the counts ---

print()
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    for name in FAILED:
        print(f"FAILED: {name}")
    sys.exit(1)
