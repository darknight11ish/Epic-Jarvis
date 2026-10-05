"""What the approval notice says a second-card, wiki or big-model card does.

    python3 test_gate_risk_words.py

jarvis_gate.py's _RISK table gives each action the sentence the notice shows
under "Stays on this PC". Three patches add one (second-card, wiki,
big-model), and two of those sentences said something untrue (audit AP-10):

  - second_card_enable: "turning the switch off stops it". The second Ollama
    runs while ANY switch that uses it is on (jarvis_second_card._wanted), so
    turning one off while another is on stops nothing. big_model_enable said
    the same of colibri, which runs while any big-model job switch is on
    (jarvis_big_model._reconcile).
  - wiki_update promised the earlier copy of a page is kept in .versions, and
    said nothing of index.md and log.md, which are appended to with no copy.

And one thing no check here could see (added 2026-10-05): an action written
into the table TWICE. Every check above reads the table through a dict, and a
dict keeps only the last value for a repeated key - so the earlier sentence
would be dead code that a reader could edit for ever without a test noticing.
`t_each_action_is_given_one_risk_line` reads the table as a list instead.

Runs anywhere: jarvis_gate.py is the owner's file, so its _RISK lines come
from a stand-in built from the whole patch stack (backend/_stack.py).
"""
import ast
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402

FAILED, PASSED = [], []

#: One line of jarvis_gate.py's _RISK table. Shared by _risk() below and by
#: the duplicate-key check, so the two cannot drift apart.
_RISK_LINE = re.compile(r'^    "(\w+)":\s*(\(.*\)),\s*$', re.M)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _risk_rows() -> list:
    """[(action, value, line number)] for the table, IN SOURCE ORDER, repeats
    kept. _risk() below cannot see a repeat: it builds a dict, and Python keeps
    only the last value for a key given twice."""
    text, log = _stack.stand_in("jarvis_gate.py")
    if text is None:
        raise AssertionError("\n".join(log))
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = _RISK_LINE.match(line)
        if not m:
            continue
        try:
            v = ast.literal_eval(m.group(2))
        except (ValueError, SyntaxError):
            continue
        if isinstance(v, tuple) and len(v) == 3:
            out.append((m.group(1), v, i))
    return out


def _risk() -> dict:
    out = {}
    for action, v, _line in _risk_rows():
        out[action] = v
    return out


def t_each_action_is_given_one_risk_line():
    """A repeated action in _RISK is invisible to every check above.

    _risk() returns a dict, and a dict keeps only the LAST value for a key
    given twice. So an action written into _RISK twice is silently the second
    sentence: editing the first one would change nothing, the stand-in would
    still parse, and every check here would still pass. The table is read as a
    LIST for this one, and a repeat is a failure naming both lines.

    This cannot be seen in this repository either way - jarvis_gate.py is the
    owner's file and is not here (backend/run_suites.py's OWNER_FILES) - so the
    stand-in built from the patch stack is the only copy a reader can check.
    """
    rows = _risk_rows()
    check("jarvis_gate.py's _RISK table was found in the stand-in", bool(rows),
          "no line matched; the table's shape has changed and this check is blind")
    seen = {}
    for action, v, line in rows:
        seen.setdefault(action, []).append(line)
    dupes = {a: lines for a, lines in seen.items() if len(lines) > 1}
    check("no action is given a second sentence further down the table",
          not dupes,
          "; ".join(f"{a} at lines {lines}" for a, lines in sorted(dupes.items()))
          + " - the LAST one wins, so the earlier one is dead code")


def t_the_second_card_and_big_model_do_not_promise_one_switch_stops_them():
    r = _risk()
    for action, rule in (("second_card_enable", "any second-card switch"),
                         ("big_model_enable", "any big-model job switch")):
        said = r.get(action, ("", "", ""))[2]
        check(f"{action} has a sentence", bool(said), repr(r.get(action)))
        check(f"{action} no longer says turning the switch off stops it",
              "turning the switch off stops it" not in said, said)
        check(f"{action} says it runs while {rule} is on", rule in said and "last one" in said,
              said)
        check(f"{action} still says it is reachable from this PC only",
              "127.0.0.1" in said and r[action][1] == "local", said)


def t_the_wiki_says_what_it_appends_without_a_copy():
    said = _risk().get("wiki_update", ("", "", ""))[2]
    check("wiki_update still says a changed page's earlier copy is kept in .versions",
          ".versions" in said, said)
    check("and that index.md and log.md are added to, with no copy",
          "index.md" in said and "log.md" in said and "no copy" in said, said)
    # The module agrees: run() appends to both and copies only pages.
    src = (HERE / "jarvis_wiki.py").read_text(encoding="utf-8")
    run = src[src.index("def run("):src.index("def status(")]
    check("jarvis_wiki.run() appends to index.md and log.md (the sentence is true)",
          "_append(idx" in run and "_append(log" in run)
    check("and keeps .versions copies of pages only",
          run.count("VERSIONS_DIR}/{c.name}") == 1 and "VERSIONS_DIR}/{INDEX" not in run)


def t_a_note_after_outside_text_says_it_stays_on_this_pc():
    """jarvis_agent.py asks for a note write after outside text under its own
    action (the owner's decision of 2026-09-24). Without a _RISK line the
    notice would read it as unknown: "might leave the machine"."""
    import jarvis_agent
    r = _risk().get(jarvis_agent.NOTE_AFTER_OUTSIDE_ACTION)
    check("write_notes_after_outside_text has a risk line", r is not None, repr(r))
    r = r or ("", "", "")
    check("... that says it stays on this PC and can be undone",
          r[0] == "yes" and r[1] == "local", repr(r))
    check("... and why it asks", "outside text" in r[2] and "notes" in r[2], r[2])


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
