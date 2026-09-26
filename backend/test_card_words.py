"""The approval card's words: a plain title for every action the gate knows,
and one set of words both apps show.

    python3 test_card_words.py

What it holds (the creativity audit, 2026-09-25, "one plain card on every
screen"):

  1. Every action the gate can ask about has a phrase in
     jarvis_card_words.TITLES - every action in jarvis_gate._RISK as the
     whole patch stack writes it (a stand-in, backend/_stack.py), every
     line of [autonomy.tiers] in the shipped jarvis-framework.toml, every
     action a shipped module asks under, and every action a tool is mapped
     to. So no card says "Jarvis wants to learning enable" again.
  2. The phrases read as plain words: no code names, no underscores.
  3. notice_for (approval-notice.patch, the real code) gives exactly
     title_for's words - and, without the module, still a readable title.
  4. What a spoken question hears and how a repeating reminder's answer
     ends: fixed lines, none of which invites a spoken "yes".
  5. The file both apps' tests read (tools/gen_card_words_cases.py) is what
     the producer makes today.

Runs anywhere: standard library only, no owner's files.
"""
import builtins
import re
import sys
import tomllib
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import jarvis_card_words as W  # noqa: E402
import test_approval_contract as C  # noqa: E402
import test_gate_risk_words as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def known_actions() -> dict:
    """{action: where it was found}, from everything in this repository that
    names a gate action."""
    found = {}

    def add(action, where):
        found.setdefault(action, where)

    for a in R._risk():
        add(a, "jarvis_gate._RISK (the patch stack)")
    for a in C.RISK:
        add(a, "a _RISK line in a patch")
    cfg = tomllib.loads(_read("rebuilt/jarvis-framework.toml"))
    for a in cfg["autonomy"]["tiers"]:
        add(a, "[autonomy.tiers] in rebuilt/jarvis-framework.toml")
    # The actions each shipped module asks the gate under.
    for path in sorted(HERE.glob("jarvis_*.py")):
        for m in re.finditer(r'^(?:[A-Z_]*ACTION[A-Z_]*)\s*=\s*"([a-z_]+)"\s*$',
                             path.read_text(encoding="utf-8"), re.M):
            add(m.group(1), path.name)
    # A tool's lookup name -> the action it is asked under (_TOOL_ACTIONS),
    # and the tools whose entry is a tier of their own ("agent_spawn": "ask").
    for patch in sorted(HERE.glob("*.patch")):
        text = patch.read_text(encoding="utf-8")
        for m in re.finditer(r'"jarvis_\w+?_run(?:_authenticated)?":\s*"(\w+)"', text):
            add(m.group(1), f"_TOOL_ACTIONS in {patch.name}")
        for m in re.finditer(r'"(\w+)":\s*"(?:ask|notify|never)"', text):
            add(m.group(1), f"a tool asked under its own name in {patch.name}")
    # The tool actions backend/README.md tells the owner to add to the gate
    # (browser control, calendar, email, notes, Home Assistant).
    readme = _read("README.md")
    for m in re.finditer(r"_TOOL_ACTIONS\[\"jarvis_\w+_run\"\] = \"(\w+)\"", readme):
        add(m.group(1), "backend/README.md")
    for m in re.finditer(r"`jarvis_\w+_run -> (\w+)`", readme):
        add(m.group(1), "backend/README.md")
    # What the gate calls a tool it has no entry for.
    add("unclassified_tool", "jarvis_gate.action_for_tool")
    return found


def t_every_action_the_gate_knows_has_a_plain_title():
    known = known_actions()
    check("the search found the actions (not an empty list by a broken pattern)",
          len(known) >= 50 and {"send_email", "switch_model", "learning_enable",
                                "search_the_web", "home_control"} <= set(known), sorted(known))
    missing = {a: w for a, w in known.items() if a not in W.TITLES}
    check("every one has a phrase in jarvis_card_words.TITLES", not missing,
          "\n        ".join(f"{a}  (from {w})" for a, w in sorted(missing.items())))


def t_the_phrases_are_plain_words():
    for action, phrase in sorted(W.TITLES.items()):
        title = W.title_for(action)
        ok = (phrase == phrase.strip() and phrase[:1].islower() and "_" not in phrase
              and not phrase.endswith(".") and not phrase.startswith("Jarvis")
              and len(title) <= 80)
        check(f"{action}: {title!r}", ok, phrase)


def t_titles_for_names_with_no_phrase_still_read():
    check("an unknown action is quoted as a name, not dropped into a sentence",
          W.title_for("frobnicate_widget") == 'Jarvis wants your OK for "frobnicate widget"',
          W.title_for("frobnicate_widget"))
    check("no action at all", W.title_for("") == W.title_for(None) == W.NO_ACTION)
    check("only letters, digits and spaces reach the title",
          W.title_for('x"<b>_y') == 'Jarvis wants your OK for "x b y"', W.title_for('x"<b>_y'))
    check("and a long name is cut", len(W.title_for("a" * 500)) < 100)
    check("a known action reads as a sentence",
          W.title_for("learning_enable") == "Jarvis wants to turn on learning")


def t_the_notice_uses_the_table():
    notice_for = C.load_notice_for()
    for action in sorted(W.TITLES):
        got = notice_for({"action": action, "detail": "SECRET", "prompt": "SECRET"})["title"]
        if got != W.title_for(action):
            check(f"notice_for({action!r}) is title_for's words", False, got)
            return
    check("notice_for's title is title_for's words, for every action in the table", True)
    check("... and for one with no phrase",
          notice_for({"action": "frobnicate_widget"})["title"] == W.title_for("frobnicate_widget"))
    check("... and for a row with no action",
          notice_for({})["title"] == W.NO_ACTION, notice_for({})["title"])


def t_without_the_module_the_notice_still_reads():
    """An owner's backend where jarvis_card_words.py was not copied in yet."""
    real = builtins.__import__

    def blocked(name, *a, **kw):
        if name == "jarvis_card_words":
            raise ImportError("not copied in")
        return real(name, *a, **kw)
    import gen_card_words_cases as G
    notice_for = C.load_notice_for()
    builtins.__import__ = blocked
    try:
        a = notice_for({"action": "learning_enable"})["title"]
        b = notice_for({})["title"]
        odd = {n: notice_for({"action": n})["title"] for n in G.UNKNOWN}
    finally:
        builtins.__import__ = real
    check("the name is quoted, the same shape as the fallback",
          a == 'Jarvis wants your OK for "learning enable"', a)
    check("and no action reads as the plain question", b == W.NO_ACTION, b)
    for name, got in odd.items():
        check(f"... letter for letter the module's fallback: {name[:20]!r}",
              got == W.title_for(name), got)


def t_the_spoken_lines_never_invite_a_spoken_yes():
    import jarvis_agent
    import jarvis_quick
    check("a line for waiting, and one for each outcome the PC sends",
          set(W.VOICE) == {"waiting"} | set(jarvis_agent.CARD_OUTCOME_WORDS), sorted(W.VOICE))
    for word, line in W.VOICE.items():
        check(f"{word}: {line!r} is short, and asks for nothing by voice",
              len(line) <= 80 and not re.search(r"\bsay\b|\byes\b|\bapprove\b", line, re.I), line)
    check("jarvis_quick ends a card's answer with the same words",
          jarvis_quick.UNTIL_APPROVED == W.UNTIL_APPROVED)
    check("and no longer says 'until you say yes'",
          "until you say yes" not in _read("jarvis_quick.py"))
    check("the label and the button order",
          W.KICKER == "Needs your OK" and W.BUTTONS == ("Deny", "Approve"))


def t_the_file_both_apps_read_is_current():
    import gen_card_words_cases as G
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_card_words_cases.py)",
              have == doc)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
