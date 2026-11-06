#!/usr/bin/env python3
"""test_self_answers.py - the self-questions docs/SELF-AWARENESS.md promises.

    python3 backend/test_self_answers.py

WHAT THIS PROVES (2026-11-04, the self-awareness audit's gap 4):

  - THE DOC'S PROMISED QUESTIONS REALLY ANSWER, without the model. The page
    says "What can you do?", "Where do I change how Jarvis talks?", "What is
    connected?", "What tools do you have?", "Which of your tools ask before
    they act?" and "refresh your abilities" already work. Three of those
    answered NOTHING (the sentence went to the local model, which has no state
    to answer it from) and the refresh phrase was not wired at all. Every
    quoted question in the page's "Asking about itself" section is driven
    through the real matcher here, so the doc cannot promise more than the
    code keeps again.
  - EACH ANSWER IS THE REAL SOURCE'S OWN NUMBERS, at answer time:
    jarvis_self_portrait.tool_inventory (jarvis_agent.TOOLS + the live
    [tools].enabled), jarvis_asks_first.view's own "Asks you first" rows,
    jarvis_reach.view's own ON rows and the plug-in folder, and the portrait's
    own refresh. No typed list, and no 136 the old counts() used to emit.
  - THE ANSWER FOLLOWS A REAL SETTINGS FILE. A one-tool [tools].enabled is
    written through JARVIS_FRAMEWORK_TOML, and "what tools do you have" must
    say ONE switched on - not a constant, and not the shipped 18.
  - ALL FOUR ARE READ-ONLY. "cancel that" must not be able to undo a question,
    and a question must not clear a pending card; each name is in
    jarvis_quick.READ_ONLY_INTENTS.
  - NEAR MISSES STILL GO TO THE MODEL. "what tools do I need for this job",
    "what is connected to my phone" and "refresh my browser" are not the
    owner asking about Jarvis's own inventory, and none may be hijacked.

No network, no model, no live install: the config folder is a throwaway temp
directory, and the memory/receipts databases are pointed there too.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-answers-"))
# Before anything imports jarvis_framework or jarvis_memory: their paths are
# read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_self_portrait.py", "jarvis_asks_first.py",
                "jarvis_reach.py")
# The framework module the real backend ships beside these modules lives in
# `backend/rebuilt/` in a checkout; on the path, the live [tools].enabled read
# is the shipped `jarvis-framework.toml`, exactly as on an install.
sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as ASK  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_reach as REACH  # noqa: E402
import jarvis_self_portrait as SP  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402

PASSED, FAILED = [], []
DOC = (REPO / "docs" / "SELF-AWARENESS.md").read_text(encoding="utf-8")

#: The four intents this change added, each read-only.
SELF_INTENTS = ("tools_inventory", "tools_asking", "connected_list", "self_refresh")


class _Sched:
    def mark_command(self, text):
        pass


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def answer(words):
    return Q.answer(words, sched=_Sched())


# ---------------------------------------------------------------------------
#   1. The doc's own promises, driven
# ---------------------------------------------------------------------------


def the_docs_quoted_questions_all_answer():
    """EVERY QUOTED QUESTION IN THE PAGE'S "Asking about itself" SECTION.

    The page is the owner's map of what he can ask. It is read here, not
    restated, so a line added to it without a real answer fails this suite.
    """
    # The three self-knowledge sections the page promises (2026-11-04 phase 2
    # added the last two): every quoted question in each must answer.
    sections = (
        ("## Asking about itself", "## Its own machine, speed and memory"),
        ("## Its own machine, speed and memory", "## Two things at once"),
        ("## Two things at once", '## "Open <a place>"'),
    )
    promised = []
    for start_heading, end_heading in sections:
        start = DOC.index(start_heading)
        end = DOC.index(end_heading)
        promised += re.findall(r'"([^"\n]+\?)"', DOC[start:end])
    check("the page's section still quotes a set of questions", len(promised) >= 4,
          str(promised))
    for words in promised:
        got = Q.match(words)
        check(f"the page's promise {words!r} really answers without the model",
              got is not None, "went to the model")
    # The refresh sentence is not a question, so it is quoted separately.
    check("the page's 'refresh your abilities' line is in the document",
          '"refresh your abilities"' in DOC)
    got = Q.match("refresh your abilities")
    check("... and it is answered by the portrait refresh, not the model",
          got is not None and got.name == "self_refresh",
          got.name if got else "went to the model")
    # The three the audit drove to silence are the ones this change answers.
    for words, want in (("What is connected?", "connected_list"),
                        ("What tools do you have?", "tools_inventory"),
                        ("Which of your tools ask before they act?", "tools_asking")):
        got = Q.match(words)
        check(f"{words!r} is answered by {want}", got is not None and got.name == want,
              got.name if got else "went to the model")


def near_misses_still_go_to_the_model():
    for words in ("what tools do I need for this job",
                  "what is connected to my phone",
                  "which tools ask for a password",
                  "refresh my browser",
                  "refresh the page",
                  "what tools does a carpenter need"):
        got = Q.match(words)
        check(f"{words!r} is not hijacked", got is None or got.name not in SELF_INTENTS,
              got.name if got else None)


def all_four_are_read_only():
    for name in SELF_INTENTS:
        check(f"{name} cannot be undone by 'cancel that'",
              name in Q.READ_ONLY_INTENTS)


# ---------------------------------------------------------------------------
#   2. "What tools do you have?" - the real counts, never 136
# ---------------------------------------------------------------------------


def tools_answer_is_the_registry_and_the_live_file():
    # 63, not the 51 this read on main: the six on-demand GitHub tools (2026-11-03,
    # GitHub "Read + actions") are in jarvis_agent.TOOLS and ship switched OFF,
    # hands-free then added send_text_message (on by default), the product check
    # added product_check (off), and the four pack tools (2026-11-05) ship ON, so
    # enabled is 18. The answer is still read from the registry and the settings
    # file, never typed.
    inv = SP.tool_inventory()
    check("the inventory reads jarvis_agent.TOOLS", inv["registered"] == 63,
          str(inv["registered"]))
    check("the inventory reads the settings file's own enabled list",
          inv["enabled"] == 18, str(inv["enabled"]))
    r = answer("what tools do you have")
    check("the answer exists", r is not None and r.reply, r and r.reply)
    reply = r.reply
    check("it names the registered count", "63 tools" in reply, reply[:120])
    check("it names the switched-on count", "18 of them are switched on" in reply,
          reply[:160])
    # The list is capped at about fourteen names plus "and N more", so the
    # two named here are ones a fresh install really shows. "Web search"
    # fell past the cap when the four pack tools joined the shipped list
    # (2026-11-05), which is the cap working, not the answer losing it.
    check("it names a REAL tool in plain words",
          "Calculator" in reply and "drop-in plugins" in reply, reply[:200])
    check("it never repeats the old 136 as a tool count", "136 tools" not in reply)
    # ONE TRUTH: the chat answer, /api/self and the refresh sentence agree.
    c = SP.counts(SP.build(refresh=True))
    check("counts()['tools'] is the same number the answer names",
          f"{c['tools']} of them are switched on" in reply, str(c["tools"]))
    said = SP.refresh_sentence({}, c)
    check("the refresh sentence names the same pair",
          f"{c['tools_registered']} tools ({c['tools_enabled']} switched on" in said,
          said)


def tools_answer_follows_a_real_settings_file():
    """The answer is not a constant: a one-tool file changes it to ONE."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-self-answers-toml-"))
    only_web = tmp / "only-web.toml"
    only_web.write_text('[tools]\nenabled = ["web_search"]\n', encoding="utf-8")
    real = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(only_web)
        inv = SP.tool_inventory()
        check("the inventory follows the file it is given", inv["enabled"] == 1
              and inv["enabled_names"] == ["web_search"],
              f"{inv['enabled']} / {inv['enabled_names']}")
        reply = answer("what tools can you use").reply
        check("the chat answer follows the same file",
              bool(reply) and "1 of them are switched on" in reply
              and "Web search" in reply, reply or "")
        check("... and says the other 62 are not switched on",
              bool(reply) and "other 62 are built in but not switched on" in reply,
              reply or "")
    finally:
        if real is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = real


# ---------------------------------------------------------------------------
#   3. "Which of your tools ask before they act?" - the page's own rows
# ---------------------------------------------------------------------------


def asking_answer_is_the_pages_own_rows():
    view = ASK.view(here=False)
    want = [str(row.get("title") or row.get("id") or "")
            for group in view.get("groups") or ()
            for row in group.get("rows") or ()
            if str((row or {}).get("says") or "") == ASK.SAYS["ask"]]
    check("the page really has rows that ask first", len(want) > 0, str(len(want)))
    reply = answer("which of your tools ask before they act").reply
    check("the answer counts the page's own ask rows",
          f"{len(want)} actions ask you first" in reply, reply[:160])
    check("... and names a real row from the page", want[0] in reply, reply[:300])
    check("it says where the full list is",
          '"What asks first"' in reply and "Settings" in reply)
    # It must not be a made-up "all tools ask": the page says some do not.
    check("it does not claim every action asks", len(want) < 136, str(len(want)))


# ---------------------------------------------------------------------------
#   4. "What is connected?" - the reach page's ON rows + the plug-in folder
# ---------------------------------------------------------------------------


def connected_answer_is_the_reach_pages_on_rows():
    view = REACH.view()
    on = [str(r.get("name") or "") for r in view.get("rows") or () if r.get("on")]
    reply = answer("what is connected").reply
    check("the answer exists and is the reach list's own", reply.startswith(
        "Right now these are connected or reachable from this PC:") if on else
        reply.startswith("Nothing is connected"), reply[:160])
    for name in on:
        check(f"the connected answer names the reach row {name!r}", name in reply,
              reply[:300])
    try:
        import jarvis_plugins as P
        plugins = len(P.available() or ())
        want = (f"Plug-ins installed on this PC: {plugins}." if plugins
                else "No plug-ins are installed on this PC.")
        check("the plug-in count is the loader's own", want in reply, reply)
    except Exception:
        check("without jarvis_plugins the answer says it cannot read the folder",
              "cannot read the plug-in folder" in reply, reply)
    check("it says the PC wrote the list, not the model",
          "not by the AI model" in reply)


# ---------------------------------------------------------------------------
#   5. "Refresh your abilities" - the portrait's own refresh, said
# ---------------------------------------------------------------------------


def refresh_answer_is_the_portraits_own_refresh():
    r = answer("refresh your abilities")
    check("the refresh answer exists", r is not None and r.reply, r and r.reply)
    check("it says it re-read rather than restarted",
          "re-read" in r.reply and "Nothing was restarted" in r.reply, r.reply)
    c = SP.counts(SP.build(refresh=True))
    check("it names the real numbers the portrait holds",
          f"{c['settings']} settings" in r.reply
          and f"{c['tools_registered']} tools" in r.reply, r.reply)
    check("it changes nothing: the counts before and after are equal",
          c == SP.counts(SP.build(refresh=True)), str(c))


# ---------------------------------------------------------------------------
#   6. Two answers that used to deny something real (audit gaps 5 and 6)
# ---------------------------------------------------------------------------


def read_a_link_is_the_feature_it_names():
    """"compare web search and read a link" denied the row read-web-page.

    The row's own names were "read a web page" and "read a page"; "read a link"
    was answered "The feature list has no 'reading a link' row" - a limit that
    sounded honest and was false.
    """
    good = FG.find("read a link", loose=True)
    check('"read a link" names the real read-web-page row',
          good.get("kind") == "feature" and good["row"]["id"] == "read-web-page",
          str(good)[:200])
    check('"reading a link" names it too',
          FG.find("reading a link", loose=True).get("kind") == "feature")
    got = Q.match("compare web search and read a link")
    check("the comparison resolves to the real row, not a bare phrase",
          got is not None and got.name == "feature_difference"
          and got.f.get("second") == "read-web-page",
          str(got.f if got else None))
    r = answer("compare web search and read a link")
    check("the comparison answers with both real features",
          r is not None and "Read one web page out loud" in r.reply
          and "Web search" in r.reply, r and r.reply[:200])
    check("... and never repeats the false 'no reading a link row' limit",
          r is not None and "nothing to compare it with" not in r.reply)


def the_focus_preset_is_a_real_setting():
    """"what is the focus preset" denied a real 22-option setting.

    The preset-detail grammar read the words as a preset called "focus" and
    answered "There is no preset called focus" - while `focus_preset` is a real
    choice in the settings registry. Phase 3 gave it the richer answer the
    ruling asked for: every real preset row with its model, and which one is
    chosen - read from `jarvis_presets`, not typed here. A REAL preset must
    still answer as one.
    """
    got = Q.match("what is the focus preset")
    check("it is the focus preset's own answer, not a preset detail",
          got is not None and got.name == "focus_presets",
          f"{got.name if got else None} {getattr(got, 'f', None)}")
    r = answer("what is the focus preset")
    check("the answer never denies it exists",
          r is not None and "There is no preset called" not in r.reply,
          r and r.reply)
    check("... it names the setting and how many real rows it picks between",
          r is not None and "focus preset is a choice in Settings" in r.reply
          and f"{len(_presets())} model presets" in r.reply,
          r and r.reply[:300])
    check("... every row it lists is a real row's own title and model",
          r is not None and all(p.title in r.reply and p.model in r.reply
                                for p in _presets()), r and r.reply[:600])
    check("... and it says which one is chosen, or that none is",
          r is not None and ("chosen on this PC right now" in r.reply
                             or "none is chosen" in r.reply
                             or "could not read which preset" in r.reply),
          r and r.reply[-300:])
    got = Q.match("what is the coding preset")
    check("a REAL preset still answers as a preset",
          got is not None and got.name == "preset_detail"
          and got.f.get("name") == "coding", str(getattr(got, "f", None)))


def _presets():
    import jarvis_presets as P
    return list(P.PRESETS)


def the_two_settings_numbers_reconcile():
    """80 vs 48: "what can I change?" and /api/self used to disagree.

    Both numbers are honest - the spoken answer counts permission rules, tool
    offers and family rows; the portrait counts the Settings cards' own rows -
    but two doors gave two numbers with nothing relating them (audit gap 9).
    The spoken sentence now states the difference, and both counts are derived
    from the tables rather than typed.
    """
    data = REG.changeable_settings()
    registry_rows = (len(REG.BOOL_SETTINGS) + len(REG.CHOICE_SETTINGS)
                     + len(REG.NUMBER_SETTINGS))
    check("the registry's own row count is 49", registry_rows == 49,
          str(registry_rows))
    check("the spoken answer names how many of its count are those rows",
          f"{registry_rows} of them are the switches, named choices and numbers" in
          data["words"], data["words"][-500:])
    check("the spoken answer names the other half as what it is",
          data["count"] > registry_rows
          and f"the other {data['count'] - registry_rows} are permission rules" in
          data["words"], data["words"][-500:])
    p = SP.counts(SP.build(refresh=True))
    check("the portrait's settings count IS the registry's own row count",
          p["settings"] == registry_rows, str(p["settings"]))
    check("the visible settings list has the same size",
          len([r for r in SP.settings() if r["kind"] in
               ("switch", "choice", "number")]) == registry_rows)


# ---------------------------------------------------------------------------


def main() -> int:
    try:
        the_docs_quoted_questions_all_answer()
        near_misses_still_go_to_the_model()
        all_four_are_read_only()
        tools_answer_is_the_registry_and_the_live_file()
        tools_answer_follows_a_real_settings_file()
        asking_answer_is_the_pages_own_rows()
        connected_answer_is_the_reach_pages_on_rows()
        refresh_answer_is_the_portraits_own_refresh()
        the_two_settings_numbers_reconcile()
        read_a_link_is_the_feature_it_names()
        the_focus_preset_is_a_real_setting()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
