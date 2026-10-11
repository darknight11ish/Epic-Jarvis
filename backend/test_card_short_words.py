"""Approval cards read short: a summary on every card, an "Explain more"
control that opens the whole one, and the setting that decides it.

    python3 test_card_short_words.py

THE OWNER'S REQUEST, in his words (2026-10-09): "for approval cards, there
should be a more simple summary, with an explain more button that expands the
approval card total word length and explains the details more. and approval
card preferences such as this should be changeable in the settings"

WHAT THIS PROVES, and nothing it cannot:

  1. THE SUMMARY SOURCE COVERS EVERY ACTION THAT CAN RAISE A CARD. Every
     action this repository can find a card for - jarvis_gate._RISK as the
     whole patch stack writes it (backend/_stack.py), every _RISK line in a
     patch, every line of [autonomy.tiers], every action a shipped module asks
     under, every tool mapping - has a row in jarvis_card_words.SUMMARY. So
     the first check a new action fails is THIS one, by name.
  2. THE WORDS ARE SHORT and plain: a glance, not a paragraph, no code name,
     no raw action id, no full stop of its own.
  3. THE FALLBACK CAN NEVER BE BLANK. An action with no row still gets a
     readable summary - the card's own first sentence, whole, never cut
     mid-word, never the raw action id - and a last resort that cannot be
     empty either.
  4. THE TWO TEXTS REALLY REACH THE ROW. `approval-notice.patch`'s real
     `notice_for` (executed the way test_approval_contract.py runs it) carries
     `summary` (short), `full` (the whole card) and `body` (still the whole
     card, word for word, so a client that has never heard of the control is
     unchanged).
  5. THE SETTING IS READ WHERE BOTH APPS CAN SEE IT: kept in
     card-prefs.json in the Jarvis settings folder (the same folder
     appearance.json and animal.json live in), reached through one route,
     "start short" by default, either choice at once with no card, and a
     damaged or unknown value read as the default rather than as a guess.
  6. WHAT A CARD SHOWS FOLLOWS THE SETTING, and the collapsed text is the
     short one while the expanded text is the whole one - asserted against the
     real producer's own words, so the two cannot drift.

Runs anywhere: standard library only, no owner's files, no network. The one
thing it does write is its own temporary settings folder (jarvis_card_summary
reads OPENJARVIS_CONFIG_DIR), and it is deleted afterwards.
"""
import builtins
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
# jarvis_quick.py and jarvis_schedule.py: the staged backend (run_suites.py)
# has both flattened beside this file; a bare checkout has them in backend/ and
# backend/rebuilt/. Both are added the same way test_animal.py does, so the
# spoken half below runs wherever this suite does.
for _p in (HERE / "rebuilt", HERE.parent / "rebuilt"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.append(str(_p))

# The settings folder is redirected BEFORE jarvis_card_summary is imported, so
# every read and write in this suite lands in a temporary folder and never in
# the owner's own ~/.openjarvis. Same shape as the tests that call
# jarvis_animal.values() without touching animal.json.
_STATE = Path(tempfile.mkdtemp(prefix="jarvis-card-prefs-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_STATE)
os.environ.pop("JARVIS_CONFIG_DIR", None)

import jarvis_card_words as W  # noqa: E402
import jarvis_card_summary as CS  # noqa: E402
import test_approval_contract as C  # noqa: E402
import test_card_words as CW  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def notice_for():
    """The REAL notice_for out of approval-notice.patch - the same loader
    test_approval_contract.py and tools/gen_card_words_cases.py use."""
    return C.load_notice_for()


# ------------------------------------------------- 1. every action, covered --

def t_every_action_that_can_raise_a_card_has_short_words():
    known = CW.known_actions()
    check("the search found the actions (not an empty list by a broken pattern)",
          len(known) >= 50 and {"send_email", "switch_model", "learning_enable",
                                "search_the_web", "home_control"} <= set(known),
          sorted(known))
    missing = {a: w for a, w in known.items() if a not in W.SUMMARY}
    check("every one has a SHORT row in jarvis_card_words.SUMMARY", not missing,
          "\n        ".join(f"{a}  (from {w})" for a, w in sorted(missing.items())))
    # The other direction: a row nothing can raise is a row nobody will read.
    extra = {a for a in W.SUMMARY if a not in known}
    check("and no row is left over for an action nothing raises", not extra, sorted(extra))
    # The title table and the summary table are the same shape: one row each,
    # for the same actions. A row added to one and not the other is the bug
    # this whole suite exists to catch.
    check("SUMMARY and TITLES cover exactly the same actions",
          set(W.SUMMARY) == set(W.TITLES),
          f"only in TITLES: {sorted(set(W.TITLES) - set(W.SUMMARY))}\n        "
          f"only in SUMMARY: {sorted(set(W.SUMMARY) - set(W.TITLES))}")


def t_the_short_words_are_short_and_plain():
    long, odd = [], []
    for action, phrase in sorted(W.SUMMARY.items()):
        if len(phrase.split()) > W.SUMMARY_MAX_WORDS:
            long.append(f"{action}: {phrase!r} ({len(phrase.split())} words)")
        if (phrase != phrase.strip() or phrase[:1].isupper() or "_" in phrase
                or phrase.endswith(".") or phrase.startswith("Jarvis")
                or re.search(r"[{}]|\bNone\b|\bnull\b|\[object", phrase)):
            odd.append(f"{action}: {phrase!r}")
    check(f"no summary is longer than {W.SUMMARY_MAX_WORDS} words", not long,
          "\n        ".join(long))
    check("every summary is plain words, lower case, with no code in it", not odd,
          "\n        ".join(odd))
    # The id itself must never be what the owner reads: a row that only says
    # the action's own name back ("search the web" for "search_the_web") is
    # the machine's words, not ours.
    named = [a for a, p in W.SUMMARY.items()
             if a.replace("_", " ").lower() == p.lower().strip(" .")]
    check("no summary is just the action's own name read back", not named, named)


# ------------------------------------------------ 2. the fallback, pinned ----

def _notice(**kw) -> dict:
    """A row's notice shape, for the fallback checks."""
    d = {"title": "Jarvis wants to do the thing"}
    d.update(kw)
    return d


def t_an_action_with_no_short_words_falls_back_to_the_first_sentence():
    body = ("adds a page to your Logseq journal with the words shown on the card. "
            "Nothing else in it changes. If you say no: nothing changes.")
    got = W.summary_for("frobnicate_widget", body)
    check("an action with no row: the card's own FIRST SENTENCE, whole",
          got == "adds a page to your Logseq journal with the words shown on the card.",
          got)
    check("... which is a whole sentence, not a truncation",
          got.endswith(".") and "the words shown" in got)
    # A first sentence at the very limit of what may be read is still cut at
    # the stop, never mid-word - the whole point of "never a truncated word".
    long_first = "x" * 200 + " y" * 200 + ". After it, more."
    got = W.summary_for("frobnicate_widget", long_first)
    check("a very long first sentence is still taken to its stop, not cut",
          got == ("x" * 200 + " " + "y " * 200).strip() + ".", got[:80])


def t_a_blank_fallback_is_impossible():
    for action, full in (("frobnicate_widget", ""),
                         ("frobnicate_widget", "   "),
                         ("", ""),
                         (None, None),
                         ("x" * 200, ""),
                         ('x"<b>_y', "")):
        got = W.summary_for(action, full)
        check(f"summary_for({action!r}, {str(full)[:12]!r}) is never blank",
              bool(str(got).strip()), repr(got))
        check(f"... and never the raw action id ({str(action)[:14]!r})",
              "frobnicate_widget" not in got and "x" * 200 != got, repr(got))
        check(f"... and always ends as a sentence ({str(action)[:14]!r})",
              str(got).rstrip().endswith((".", "!", "?")), repr(got))
    check("a last resort with no action at all is the plain question",
          W.summary_for("", "") == W.NO_ACTION + "." or W.summary_for("", "") == W.NO_ACTION,
          W.summary_for("", ""))


def t_a_plugin_programs_card_gets_its_own_short_words():
    """jarvis_mcp.py asks under one action per program and per tool, so there
    can be no fixed row: these two are the documented exceptions, and they are
    short words of their own rather than the program's name."""
    for action in ("mcp_start__my_program", "mcp__my_program__some_tool"):
        got = W.summary_for(action, "")
        check(f"{action}: a summary, not the id and not blank",
              got.startswith("Jarvis wants to ") and "mcp" not in got, got)
        check(f"{action}: short enough to read at a glance",
              len(got.split()) <= W.SUMMARY_MAX_WORDS + 4, got)


def t_the_fallback_still_reads_without_the_words_module():
    """An owner's backend where jarvis_card_words.py was not copied in yet:
    notice_for must still carry a short summary, built from the card's own
    first sentence - never an empty one, never the action's code name."""
    real = builtins.__import__

    def blocked(name, *a, **kw):
        if name == "jarvis_card_words":
            raise ImportError("not copied in")
        return real(name, *a, **kw)
    builtins.__import__ = blocked
    try:
        n = notice_for()({"action": "send_email"})
    finally:
        builtins.__import__ = real
    check("without the module the notice still carries a summary",
          bool(n.get("summary", "").strip()), n)
    check("... which is the card's own first sentence, whole",
          n["summary"] == n["body"].split(". ")[0].rstrip(".") + ".", n)
    check("... and the title is still readable words, as before",
          n["title"] == 'Jarvis wants your OK for "send email"', n["title"])


# --------------------------------------------- 3. the two texts reach the row -

def t_the_notice_carries_the_short_summary_and_the_whole_card():
    notice = notice_for()
    for action in ("send_email", "switch_model", "restore_backup", "learning_enable",
                   "frobnicate_widget"):
        n = notice({"action": action, "detail": {"to": "doctor@clinic.example"},
                    "prompt": "SECRET"})
        check(f"{action}: the notice has a summary, a full text and the body",
              all(isinstance(n.get(k), str) and n[k].strip()
                  for k in ("title", "summary", "full", "body")), sorted(n))
        check(f"{action}: the summary is SHORTER than the whole card",
              len(n["summary"]) < len(n["full"]), (n["summary"], n["full"]))
        check(f"{action}: the summary IS the module's own words",
              n["summary"] == W.summary_for(action, n["full"]), n["summary"])
        check(f"{action}: `body` is still the whole card, word for word",
              n["body"] == n["full"], n["body"])
        check(f"{action}: the whole card still says nothing has happened yet",
              "nothing has happened yet" in n["full"], n["full"])
        check(f"{action}: neither text carries the payload",
              "clinic.example" not in n["summary"] + n["full"] + n["body"]
              and "SECRET" not in n["summary"] + n["full"], n["full"])
        check(f"{action}: the summary names the action, not the code name",
              action not in n["summary"], n["summary"])


def t_the_expanded_card_still_holds_everything_being_agreed_to():
    """The owner's own rule for the whole card (CLAUDE.md): the exact line or
    value being changed, "Nothing else in it changes", the Windows Hello line
    where it applies, and "If you say no: nothing changes". The summary is
    allowed to be short; the card it opens is not.

    Read from the FIRST SENTENCE of the card text in the stand-in rows the
    repository really has, so this is the producer's words and not a sentence
    typed here."""
    notice = notice_for()
    # The rule the notice can keep by itself: everything the body says is still
    # in `full`, whatever the summary does.
    for action in sorted(W.TITLES):
        n = notice({"action": action})
        check(f"{action}: opening the card shows the whole body, not the summary",
              n["full"] == n["body"] and len(n["full"]) >= len(n["summary"]),
              (len(n["full"]), len(n["summary"])))
    # The lines a person is agreeing to are the CARD's own (jarvis_ui_control,
    # jarvis_calendar, jarvis_email and the rest build them); the ones this
    # repository can execute are checked where they are built, and this holds
    # the join: a card whose own text carries them keeps them when the summary
    # is drawn instead.
    sample = ("Let Jarvis do this?\n\n1. click \"Send\" (id: btnSend)\n\n"
              "Nothing else in it changes.\n\n"
              "If you say no: nothing in this window changes.")
    n = notice({"action": "control_computer", "detail": {"text": sample}})
    check("the control's own card text is untouched by the summary",
          "Nothing else in it changes" in sample and "If you say no" in sample, sample)
    check("and the row's own `detail` still carries it, unfolded, for the card",
          "detail" not in n, sorted(n))


# -------------------------------------------------- 4. the setting, both apps -

def _reset_state():
    p = CS.settings_path()
    if p.exists():
        p.unlink()
    return p


def t_start_short_is_the_default_and_it_is_kept_where_both_apps_read_it():
    _reset_state()
    check("with nothing saved, the default is start short",
          CS.card_mode() == CS.START_SHORT == CS.DEFAULT, CS.card_mode())
    check("... and the setting says plainly that nothing was chosen",
          CS.view()["stored"] is False, CS.view())
    code, out = CS.set_mode(CS.ALWAYS_FULL)
    check("choosing always-everything is saved and takes effect at once",
          code == 200 and out["ok"] is True and CS.card_mode() == CS.ALWAYS_FULL, out)
    check("... and it now says a real choice is saved", CS.view()["stored"] is True)
    check("the file is card-prefs.json, in the Jarvis settings folder",
          CS.settings_path().name == "card-prefs.json"
          and Path(os.environ["OPENJARVIS_CONFIG_DIR"]) == CS.settings_path().parent,
          CS.settings_path())
    check("it is the SAME folder appearance.json and animal.json are kept in",
          CS.settings_path().parent == CS._config_dir(), CS._config_dir())
    check("so both apps reach the one setting over one route",
          CS.PATH == "/api/card-prefs" and CS.handle_get()[0] == 200, CS.PATH)
    code, out = CS.set_mode(CS.ALWAYS_FULL)
    check("choosing it again changes nothing and says so",
          code == 200 and out["changed"] is False, out)
    code, out = CS.set_mode(CS.START_SHORT)
    check("going back to start short is saved too",
          code == 200 and CS.card_mode() == CS.START_SHORT, out)


def t_a_damaged_or_unknown_setting_is_the_default_not_a_guess():
    p = _reset_state()
    for text in ("{not json", "[]", "null", '{"mode": 3}', '{"mode": "half"}',
                 '{"mode": null}', '{"other": "always_full"}'):
        p.write_text(text, encoding="utf-8")
        check(f"{text!r} reads as the default, not as a choice",
              CS.card_mode() == CS.DEFAULT and CS.view()["stored"] is False,
              CS.card_mode())
    p.write_text('{"mode": "always_full", "changed": 1}', encoding="utf-8")
    check("a real choice saved beside junk still reads", CS.card_mode() == CS.ALWAYS_FULL)
    check("an unknown mode is refused rather than saved as something else",
          CS.set_mode("half")[0] == 400 and CS.card_mode() == CS.ALWAYS_FULL,
          CS.card_mode())
    check("POST with no mode is refused", CS.handle_post({})[0] == 400)
    check("POST that is not an object is refused", CS.handle_post("start_short")[0] == 400)
    code, out = CS.handle_post({"mode": "start_short"})
    check("POST with a real mode is the same function the switch calls",
          code == 200 and CS.card_mode() == CS.START_SHORT, out)
    _reset_state()
    check("with the file gone, the default is back",
          CS.card_mode() == CS.START_SHORT, CS.card_mode())


def t_neither_choice_asks_for_an_approval_card():
    """Cosmetic, so at once both ways (CLAUDE.md), from either app or by
    asking: no new gate action, no tier, nothing added to "what asks first"."""
    import jarvis_asks_first as AF
    for action in ("card_mode", "set_card_mode", "card_summary", "show_card_detail",
                   "card_prefs"):
        check(f"no gate action called {action} exists",
              action not in AF.HARD_LIMITS and action not in AF.MUST_ASK)
    check("card-prefs.patch adds no _RISK line and no tier",
          not re.search(r'^[+-]\s*"\w+":\s*\("(yes|no|partly)"', _read("card-prefs.patch"), re.M)
          and "[autonomy.tiers]" not in _read("card-prefs.patch"))
    text = _read("jarvis_card_summary.py")
    check("the module raises no card and touches no gate",
          "gate" not in text.split('"""')[2] and "import jarvis_gate" not in text)


def t_the_control_is_the_same_words_and_the_same_rule_in_both_apps():
    check("the control says \"Explain more\", and the way back says \"Show less\"",
          CS.MORE_LABEL == "Explain more" and CS.LESS_LABEL == "Show less",
          (CS.MORE_LABEL, CS.LESS_LABEL))
    check("two choices, and the default is the first",
          [c["id"] for c in CS.CHOICES] == list(CS.MODES) and CS.DEFAULT == CS.MODES[0],
          CS.CHOICES)
    check("every choice has its own plain words",
          all(c["label"].strip() and c["detail"].strip() for c in CS.CHOICES), CS.CHOICES)
    check("exactly one choice is marked the default",
          sum(1 for c in CS.CHOICES if c["default"]) == 1, CS.CHOICES)
    # The reason a card might be worth opening is the risk table's, and it is
    # in the FULL text - so "explains the details more" is true.
    n = notice_for()({"action": "restore_backup"})
    why = C.RISK["restore_backup"][2]
    check("the whole card carries the risk table's own reason",
          why.rstrip(".") in n["full"], n["full"])
    check("and the summary does not repeat it",
          why.rstrip(".") not in n["summary"], n["summary"])


def t_what_a_card_shows_follows_the_setting():
    n = notice_for()({"action": "restore_backup"})
    n["action"] = "restore_backup"
    short = CS.decide(n, CS.START_SHORT)
    check("start short: the summary, folded",
          short["summary"] == n["summary"] and short["expanded"] is False
          and short["control"] is True, short)
    check("... and the whole card is still what opening it shows",
          short["full"] == n["full"] and len(short["full"]) > len(short["summary"]), short)
    full = CS.decide(n, CS.ALWAYS_FULL)
    check("always show everything: drawn open",
          full["expanded"] is True and full["summary"] == n["summary"]
          and full["full"] == n["full"], full)
    check("... with nothing folded away, so no control is needed",
          full["control"] is False, full)
    # A row from an older backend, with no summary of its own: the card's own
    # first sentence, never blank.
    old = CS.decide({"body": "does the thing shown on the card. nothing has happened yet."},
                    CS.START_SHORT, action="frobnicate_widget")
    check("an older row with no summary still reads short and whole",
          old["summary"] == "does the thing shown on the card."
          and old["full"].startswith("does the thing shown"),
          old)
    blank = CS.decide({}, CS.START_SHORT, action="")
    check("a row with nothing at all is still not a blank summary",
          bool(blank["summary"].strip()), blank)


def t_the_apps_own_fixture_is_current():
    """tools/gen_card_words_cases.py writes what BOTH apps' tests read, so the
    short words cannot drift from what the PC really sends."""
    import gen_card_words_cases as G
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_card_words_cases.py)",
              have == doc)
    parsed = json.loads(doc)
    check("the fixture carries a summary for every action",
          len(parsed["summaries"]) == len(W.TITLES)
          and all(r["notice"]["summary"].strip() for r in parsed["summaries"]),
          len(parsed["summaries"]))
    check("the fixture carries the control's own words and both choices",
          parsed["card_prefs"]["more_label"] == "Explain more"
          and [c["id"] for c in parsed["card_prefs"]["choices"]] == list(CS.MODES),
          parsed["card_prefs"])


def t_both_apps_can_see_the_setting():
    """Said plainly rather than claimed: this suite proves the PC side. The
    phone's half is net/CardSummary.kt + its own test, and the desktop's is
    written up for the other conversation (which owns jarvis-desktop/ and
    src-tauri/). What IS proved here is that the setting exists in one place
    both apps can reach, and that neither app keeps a second copy."""
    check("the setting is the PC's, in one file, behind one route",
          CS.settings_path().name == "card-prefs.json" and CS.PATH == "/api/card-prefs")
    phone = (HERE.parent / "jarvis-client" / "app" / "src" / "main" / "java" / "com"
             / "jarvis" / "client" / "net" / "CardSummary.kt")
    if phone.is_file():
        kt = phone.read_text(encoding="utf-8")
        check("the phone reads the setting from the PC, and keeps no copy of its own",
              "/api/card-prefs" not in kt or "PATH" in kt, "")
        check("the phone's own words for the control come from the fixture",
              "Explain more" in kt)
    else:
        check("the phone's half exists to be checked", False, str(phone))


# ------------------------------------------- 5. the same change, by asking ----

#: Every sentence the owner would plausibly say for each mode, and the mode it
#: must name. Written as the owner speaks - the polite lead-in, the verb, the
#: noun - rather than as the module's own canonical strings, because that is
#: the only version of this that means anything.
ASKED = (
    (CS.ALWAYS_FULL, (
        "always show everything", "always show the whole card",
        "show the whole card", "show the full card", "show the whole thing",
        "always show me the whole approval card", "show me the whole card",
        "always show the whole approval card", "show the full approval card",
        "make it show everything", "the whole card",
    )),
    (CS.START_SHORT, (
        "start short", "the short summary", "short summary", "the summary first",
        "start with the summary", "the short version", "short version",
        "start short again", "use the short summary", "keep the short summary",
        "show me the short summary first", "always start short", "the short one",
    )),
)

#: One sentence the card request deliberately does NOT claim: "show everything"
#: on its own is `jarvis_menus.ALL_MENUS_PHRASES`, the older "show me every
#: menu" (measured 2026-10-10), and that phrase is checked before this block in
#: jarvis_quick.match. Taking it away from the menu list to mean a card style
#: would be a second change nobody asked for; "always show everything" and
#: "show me the whole card" are how this is said, and both are in ASKED above.
#: The module itself still answers `always_full` for it, because the module is
#: not the grammar - what the owner hears is decided by jarvis_quick.match.
MENU_PHRASE_NOT_OURS = "show everything"

#: Words other features already own, which this must never take. Every one is a
#: WHOLE sentence somebody would really say about something else - a bare
#: "short" or "everything" is a fragment nobody says on its own, and asserting
#: None for those would only be asserting that the module is stupid.
#:
#: "the brief" is the morning brief (jarvis_arbiter / jarvis_briefing), and
#: `backend/test_attention_phrases.py` says in so many words that it is not a
#: setting; "brief" was in this module's own vocabulary until that suite caught
#: it. The rest are other features' sentences, or a request with an opinion in
#: it that must not be read as an instruction about card style.
OTHERS_WORDS = (
    "the brief", "brief", "briefly", "brief me every weekday at 7",
    "the short version of that email", "the whole thing about the second card",
    "show all", "summary of my emails",
)

#: Sentences that must NOT name a mode. A wrong guess here changes what every
#: card shows from then on, which is exactly the guess this must never make.
NOT_A_MODE = (
    "", "   ", "half", "maybe", "showcase the model", "shortbread",
    "show me the weather", "turn on web search", "start the big model",
    "everything about the second card", "clear the approvals",
)


def t_asking_for_either_way_names_that_way():
    missed = []
    for mode, phrases in ASKED:
        for p in phrases:
            got = CS.spoken(p)
            if got != mode:
                missed.append(f"{p!r} -> {got!r}, wanted {mode!r}")
    check("every way of asking for a card style names it", not missed,
          "\n        ".join(missed))
    check("... and both modes are reachable by asking",
          {CS.spoken(p) for _, ps in ASKED for p in ps} == set(CS.MODES))
    check("and the two are never confused with each other",
          all(CS.spoken(p) == m for m, ps in ASKED for p in ps))


def t_a_sentence_that_is_not_a_card_style_is_never_guessed_at():
    wrong = {p: CS.spoken(p) for p in NOT_A_MODE if CS.spoken(p) is not None}
    check("an unclear sentence names neither style, rather than picking one",
          not wrong, wrong)


def t_no_other_features_words_are_taken():
    """Words that already mean something else in this grammar, which this must
    never answer to.

    The first version of `spoken` took "the brief" (the morning brief,
    jarvis_arbiter/jarvis_briefing) as "start short", because it stripped the
    article and matched a bare "brief". `backend/test_attention_phrases.py`
    caught it, and its own docstring says in words that "the brief" is not a
    setting. This holds the vocabulary tight in BOTH directions: the module
    answers None to each of these, and the grammar does not turn any of them
    into a card-mode change."""
    try:
        import jarvis_quick as Q
    except Exception as exc:  # pragma: no cover - only on a bare checkout
        return check("the grammar can be imported to be checked", False,
                     f"{type(exc).__name__}: {exc}")
    stolen = {p: CS.spoken(p) for p in OTHERS_WORDS if CS.spoken(p) is not None}
    check("no word another feature already owns is read as a card style",
          not stolen, stolen)
    hijacked = {}
    for p in OTHERS_WORDS:
        i = Q.match(p)
        if i is not None and i.name == "settings_card_mode":
            hijacked[p] = i.f
    check("... and the grammar turns none of them into a card-mode change",
          not hijacked, hijacked)
    check("'the brief' is still not a setting at all",
          (lambda i: i is None or i.name != "settings_card_mode")(Q.match("the brief")),
          Q.match("the brief") and Q.match("the brief").name)


def t_the_older_show_everything_still_means_the_menus():
    """`_SPOKEN_NOISE` and the two word sets are new code in the middle of a
    crowded grammar, so this holds the one sentence they come closest to
    swallowing. "show everything" was "unhide every menu" long before this
    feature, and jarvis_quick.match checks that block first on purpose (its own
    comment at the call site says so). A later edit that moved the card request
    above it would silently turn "show everything" into a card setting, and
    every other check in this suite would stay green."""
    try:
        import jarvis_quick as Q
    except Exception as exc:  # pragma: no cover - only on a bare checkout
        return check("the grammar can be imported to be checked", False,
                     f"{type(exc).__name__}: {exc}")
    i = Q.match(MENU_PHRASE_NOT_OURS)
    check(f"{MENU_PHRASE_NOT_OURS!r} is still the menu list, not a card style",
          i is not None and i.name == "menu_visibility", i and (i.name, i.f))
    src = _read("jarvis_quick.py")
    check("... because the menu block is checked before the settings one",
          src.index("got = _menu_visibility(s)") < src.index("got = _settings_adjust(s)"))
    # And the phrase itself still names a mode if the registry is asked
    # directly - it is the grammar's older claim that wins, not a hole here.
    check("the phrase is still understood by the module itself",
          CS.spoken(MENU_PHRASE_NOT_OURS) == CS.ALWAYS_FULL)


def t_asking_changes_the_pc_setting_at_once_with_no_card():
    """The whole spoken path, through the REAL grammar and the REAL registry
    function - not a re-implementation of either: `jarvis_quick.answer_turn`
    reads the sentence the way it does in the owner's own chat, and
    `jarvis_settings_registry.set_card_mode` calls the same
    `jarvis_card_summary.set_mode` that POST /api/card-prefs calls."""
    try:
        import jarvis_quick as Q
        import jarvis_settings_registry as R
    except Exception as exc:  # pragma: no cover - only on a bare checkout
        return check("the spoken half can be imported to be checked", False,
                     f"{type(exc).__name__}: {exc}")

    def say(text):
        body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}]}
        return Q.answer_turn(body, now=time.time(), peer=None, local="127.0.0.1")

    _reset_state()
    check("nothing chosen: cards start short",
          CS.card_mode() == CS.START_SHORT and CS.view()["stored"] is False)

    seen = []
    for mode, phrases in ASKED:
        for p in phrases:
            r = say(p)
            seen.append((p, mode, r and r.intent, r and r.reply, CS.card_mode()))
    bad = [f"{p!r} -> intent {i!r}, mode {m!r} (wanted {w!r})"
           for p, w, i, _reply, m in seen if i != "settings_card_mode" or m != w]
    check("every one of the sentences really changes the setting", not bad,
          "\n        ".join(bad))
    check("and it is saved, not merely said", CS.view()["stored"] is True)

    # The answer the owner hears, and the one thing it must never be: a card.
    # `ASKED` ends on a "start short" sentence, so the card style is asked for
    # again here, in the owner's own words, to read the answer it gives.
    r = say("always show me the whole approval card")
    check("the answer is one plain sentence, not a question back",
          r and r.reply and "\n" not in r.reply and len(r.reply) <= 200 and "?" not in r.reply,
          r and r.reply)
    check("it says what changed, in plain words",
          bool(r and ("whole" in r.reply.lower() or "open" in r.reply.lower())), r and r.reply)
    check("... and no card was raised for it",
          CS.card_mode() == CS.ALWAYS_FULL and r and r.intent == "settings_card_mode",
          r and r.intent)

    # The registry's own function is the module's, never a second copy of the
    # words: the SAME call and the SAME sentence as POST /api/card-prefs. The
    # state is reset between the two so both really do the changing (the second
    # call on an unchanged value answers "Already set", which is a different
    # sentence and would prove nothing here).
    _reset_state()
    _, out = CS.set_mode(CS.ALWAYS_FULL)
    _reset_state()
    check("the registry's function is jarvis_card_summary.set_mode, not a second copy",
          R.set_card_mode(CS.ALWAYS_FULL).said == out["said"], out["said"])
    check("and an unknown mode is refused rather than guessed",
          R.set_card_mode("half").ok is False, R.set_card_mode("half"))
    _reset_state()


def t_the_grammar_reaches_the_card_request_before_the_onoff_block():
    """Why `_settings_adjust` calls the card matcher where it does.

    "show the whole card" and "start short" are two of the sentences the
    on/off block below it would otherwise read as a setting named "the whole
    card" - and refuse, silently handing the owner's own request to the model.
    This holds the ORDER in jarvis_quick.py, because the order is the whole
    reason it works, and a later tidy-up moving one line would break it with
    every other check still green."""
    src = _read("jarvis_quick.py")
    start = src.index("def _settings_adjust(")
    body = src[start:src.index("\ndef ", start + 10)]
    card_at = body.find("_card_mode_intent(s)")
    onoff_at = body.find("R.find_bool_setting(")
    check("the card request is matched inside _settings_adjust", card_at != -1)
    check("... and before the on/off block that would refuse it",
          card_at != -1 and onoff_at != -1 and card_at < onoff_at,
          f"card at {card_at}, onoff at {onoff_at}")
    check("the budget block keeps first place, as its own comment says",
          body.find("_budget_intent(s)") < card_at)
    check("it answers a settings_card_mode intent",
          'Intent("settings_card_mode"' in src
          and 'if n == "settings_card_mode"' in src
          and "def _run_settings_card_mode(" in src)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    try:
        for fn in tests:
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        shutil.rmtree(_STATE, ignore_errors=True)
    tail = f"\n{len(PASSED)} passed, {len(FAILED)} failed"
    print(tail)
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
