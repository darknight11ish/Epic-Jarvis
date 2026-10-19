"""The gate reads what an action TOUCHES, not the words on its card.

    python3 test_gate_touches.py

WHAT WAS WRONG. `jarvis_gate.check()` searched the PROMPT it was handed for
the names in its own `_PROTECTED` list - jarvis-framework.toml,
jarvis_gate.py, jarvis_hud.py and six more - and it did that BEFORE the tier
branches. For a card raised by a route, the prompt IS the card's own text
(`jarvis_backup._decide_restore` hands the gate `restore_card(...)`;
`jarvis_asks_first` hands it `loosen_card(...)` and `tool_enable_card(...)`).
So a card that merely DESCRIBED a protected file was refused at tier "never"
with no card ever raised, no Windows Hello, and nothing anybody could do
about it.

Measured in the owner's own log (.openjarvis/logs/*.jsonl, 2026-10-03 ..
2026-10-10): 45 `gate.refused_protected` events - `enable_reading_tool` 21,
`loosen_what_asks_first` 21, `restore_backup` 3. The redaction lengths name
the files exactly: 21 characters is jarvis-framework.toml, 13 is
jarvis_hud.py. Three features had never once worked.

WHAT WAS STILL WRONG (found 2026-10-11, pinned here). #249 read the model's
own tool call out of the prompt, but only when that call PARSES as JSON.
`jarvis_agent._gate_prompt` used to write
`tool <name> {json.dumps(args)[:1500]}` - the audit-log line had a
1500-character budget - and a JSON object cut in half does not parse. The
whole argument block was therefore dropped from the search: measured, args
3453 characters long with `pathlib.Path('jarvis_gate.py').write_text('')` at
character 62 gave blobs `['{}', 'run_shell_on_host']`, so
`run_shell_on_host` was not refused but offered as an ordinary "ask" card - a
person could approve a write to the gate itself. Making the arguments LONGER
than the log line was enough to hide the target. #260 closed THIS half, by
reading a cut tool call's raw text (section 2b).

WHAT WAS STILL WRONG AFTER THAT, AND IS CLOSED HERE (DEF-003, 2026-10-12).
#260 read only the text that SURVIVED the cut. The gate reads the model's own
arguments through the line `jarvis_agent` hands it and nowhere else on these
paths, and all THREE of that module's gate lines sliced the arguments at 1500
BEFORE the gate was called (`_gate_prompt`, the plan step, the web-search
call), so a protected name PAST character 1500 was never in the prompt at all
and no rule could read it. Measured on the unfixed module: arguments 1693
characters long with `pathlib.Path('jarvis_gate.py').write_text('')` at
character 1658 gave blobs without the name, and the action came back as an
ordinary "ask" card a person could approve. All three lines now carry the
WHOLE argument JSON, built by the one `_gate_prompt()` helper (section 2c),
so a longer cut would only have moved the hole. What is WRITTEN DOWN is still
bounded: `jarvis_gate.check()` stores at most 2000 characters of the line on
the approvals row, so the record grew by at most 500 characters. The
retirement what-if stays exempt - its arguments are the owner's own money
figures, so not even a cut version of them is written down.

WHAT THIS SUITE PINS. `_target_blobs()` decides what the rule may read: the
action's parameters (`detail`, minus the keys holding the card's own text)
and the model's own tool call, which is the JSON object inside the prompt.
Card prose is not a target and is not searched. So:

  1. a card that merely NAMES a protected file is raisable - the case that
     has bitten three times (section 1);
  2. an action whose TARGET is a protected file is still refused at "never",
     before any card exists, with the same plain reason as before - on every
     shape a real caller uses to hand it over (section 2);
  3. a tool call CUT to the audit-log line's budget is still read as a tool
     call, so a protected target cannot be hidden by making the arguments
     longer than that line (section 2b) - and the cut is NOT an excuse to
     read a card's words again (section 2b's counter-test);
  4. a protected target PAST character 1500 is refused on every one of
     `jarvis_agent`'s gate lines, tool call and plan step alike, because the
     line carries the whole argument JSON (section 2c) - and the retirement
     what-if still writes none of its numbers down;
  5. the three real cards are raisable END TO END through the real gate and
     the SHIPPED tier table, with a scratch approvals database and a scratch
     audit directory (section 3);
  6. everything else the gate refuses today, it still refuses (section 4).

`jarvis-backend/jarvis_gate.py` is this repository's published copy of the
gate (jarvis-backend/README.md says where it came from), so the module under
test here is the one the patch in `backend/` is written against. That patch,
`gate-touches.patch`, is what carries this to the owner's own backend; the
last check in this file pins it into the stack.

Runs in repo mode (JARVIS_BACKEND unset), from the repository root:

    py -3 backend/test_gate_touches.py
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
PATCH = HERE / "gate-touches.patch"
PS1 = REPO / "scripts" / "apply-patches.ps1"

# A SCRATCH home, before anything is imported: jarvis_gate resolves its
# approvals database and jarvis_framework its config at import time. The
# owner's own ~/.openjarvis is never touched, and no test here can write to
# it. `JARVIS_APPROVAL_TIMEOUT` is what keeps a raised card from blocking
# for the shipped 180 seconds.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-gate-touches-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "0.4")
# No push. Said explicitly rather than relied on: a test that quietly posted
# a card to a public broker would be the exact leak the gate exists to stop.
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

# The published copy of the gate, first on the path; backend/rebuilt/ second,
# for the library modules the shipped tier table is read by.
#
# NEITHER THE PATH NOR ANY BYTECODE OUTLIVES THESE TWO IMPORTS (2026-10-11).
# Both used to. `jarvis-backend/` stayed first on `sys.path` for the rest of
# the process, and importing the gate from there wrote
# `jarvis-backend/__pycache__/*.pyc` into the checkout. The second one is a
# real defect, not tidiness: `backend/test_base_matches_repo.py` forbids
# bytecode in the base by name ("it embeds absolute paths, and git ignores
# it"), so it reported 19 passed, 1 failed - but only when this suite had run
# first in the same workspace. CI stayed green by accident: `run_suites.py`
# walks the suites alphabetically, so `test_base_matches_repo` runs before
# `test_gate_touches`, and CI's Windows list carries the base and not this
# one. The owner, running one suite at a time, saw a red that reads exactly
# like a regression in `jarvis-backend/`. A suite whose result depends on the
# order the suites are run in is a trap, so bytecode writing is off for these
# two imports and `sys.path` is put back as it was straight afterwards. Done
# this way rather than by deleting the folder afterwards: a test that cleans
# up after itself by removing a directory in the repository is one bug away
# from removing something else.
_SAVED_PATH = list(sys.path)
_SAVED_DONT_WRITE_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(HERE / "rebuilt"))

import jarvis_framework as fw          # noqa: E402
import jarvis_gate as G                # noqa: E402

sys.path[:] = _SAVED_PATH
sys.dont_write_bytecode = _SAVED_DONT_WRITE_BYTECODE

FAILED, PASSED = [], []
SKIPPED = []

#: The three cards the owner's log shows being refused, and the module that
#: raises each one. Read from the modules themselves in section 3 - never
#: typed in here, so a rewording cannot make this suite quietly vacuous.
REAL_CARDS = (
    ("restore_backup", "jarvis_backup", "restore_card",
     ("jarvis-backup-2026-10-01-120000.jbak", {"created_at": 1759000000.0})),
    ("enable_reading_tool", "jarvis_asks_first", "tool_enable_card",
     ("calendar_read",)),
    ("loosen_what_asks_first", "jarvis_asks_first", "loosen_card",
     ("calendar_read",)),
)


#: How long a raised card waits before the gate gives up, and how long this
#: suite watches the queue while it waits. `JARVIS_APPROVAL_TIMEOUT` is read
#: by the gate at import, so the shipped 180 seconds is never in play here.
TIMEOUT = float(os.environ["JARVIS_APPROVAL_TIMEOUT"])


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run - printed as `skip`, counted on its
    own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _pending_rows():
    try:
        return G.pending()
    except Exception:
        return []


def _raise_and_watch(action, detail, prompt, timeout=None):
    """(verdict, rows) for a card, watching the queue WHILE it waits.

    The row is written before the gate starts polling and is decided or
    expired when it stops, so reading the queue afterwards sees the terminal
    state rather than the card that was offered. This samples it during the
    wait, which is what a client would see too.
    """
    seen = []
    box = {}

    def run():
        try:
            box["v"] = G.check(action, detail, prompt=prompt,
                               timeout=TIMEOUT if timeout is None else timeout)
        except Exception as exc:                   # pragma: no cover
            box["err"] = exc

    t = threading.Thread(target=run, name="gate-touches-card", daemon=True)
    t.start()
    while t.is_alive():
        rows = [r for r in _pending_rows() if r.get("action") == action]
        if rows and not seen:
            seen = rows
        time.sleep(0.03)
    t.join(5)
    if "err" in box:                               # pragma: no cover
        raise box["err"]
    return box.get("v"), seen


def _card_text(spec):
    """The real card a real module builds, or (None, why)."""
    mod_name, fn, args = spec
    try:
        mod = __import__(mod_name)
    except Exception as exc:                       # pragma: no cover
        return None, f"{mod_name} is not importable here ({type(exc).__name__}: {exc})"
    f = getattr(mod, fn, None)
    if f is None:                                  # pragma: no cover
        return None, f"{mod_name}.{fn} does not exist"
    try:
        return f(*args), ""
    except Exception as exc:                       # pragma: no cover
        return None, f"{mod_name}.{fn} raised {type(exc).__name__}: {exc}"


# ======================================================= 1. a card may name one

def t_a_card_that_merely_names_a_protected_file_is_raisable():
    """THE CASE THAT HAS BITTEN THREE TIMES. The prompt is card prose; the
    target is clean (a settings write, a restore of the owner's own data).
    Before the fix every one of these was refused at "never"."""
    card = ("Restore Jarvis from this backup?\n\n"
            "This puts that day's copy of Jarvis's own program files (the .py files "
            "beside jarvis_hud.py) back into the folder Jarvis runs from.\n\n"
            "If you say no: nothing changes.")
    v, rows = _raise_and_watch("restore_backup", {"text": card, "to": "x.jbak"}, card)
    check("a restore card naming jarvis_hud.py is raised, not refused",
          v.tier == "ask" and v.outcome != "refused",
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
    check("... and a row really reached the queue, so a person was asked",
          bool(rows), repr([r.get("action") for r in _pending_rows()]))
    check("... with the card's own text on it, for the apps to show",
          bool(rows) and "beside jarvis_hud.py" in (rows[0].get("prompt") or ""),
          repr([(r.get("prompt") or "")[:60] for r in rows]))

    loose = ('Let Jarvis read your calendar without asking you first?\n\n'
             'This changes one line of your settings file on this PC '
             '(jarvis-framework.toml): calendar_read = "auto".')
    v, rows = _raise_and_watch("loosen_what_asks_first", {"text": loose}, loose)
    check("a loosening card naming jarvis-framework.toml is raised too",
          v.tier == "ask" and v.outcome != "refused" and bool(rows),
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")

    # The CONTROL: the same name in target position is refused, so the check
    # above cannot pass by the rule having stopped working.
    v = G.check("delete_file", {"path": "C:/x/jarvis-framework.toml"},
                prompt="Delete a file the owner named.", timeout=TIMEOUT)
    check("CONTROL: the same name in the ACTION'S TARGET is still refused",
          v.tier == "never" and v.outcome == "refused",
          f"tier={v.tier!r} outcome={v.outcome!r}")


def t_braces_in_prose_are_not_read_as_arguments():
    """Only text that really PARSES as JSON is treated as arguments. Prose
    that happens to carry braces is still prose."""
    prompt = ('This changes one line: {calendar_read = "auto"} in '
              'jarvis-framework.toml.')
    v = G.check("loosen_what_asks_first", {"what": "loosen"}, prompt=prompt,
                timeout=TIMEOUT)
    check("braces in a card's prose do not make it a tool call",
          v.tier == "ask" and v.outcome != "refused",
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
    parsed = [m for m in G._JSON_OBJECT_RE.findall(prompt) if _parses(m)]
    check("... because it does not parse as JSON", parsed == [], repr(parsed))


def _parses(text):
    try:
        json.loads(text)
    except Exception:
        return False
    return True


# ======================================= 2. a target that IS one is still refused

def t_a_target_that_is_a_protected_file_is_refused_at_never():
    """The shapes REAL callers use to hand the gate a target, each with the
    file named somewhere different."""
    cases = (
        ("OpenJarvis's own confirm prompt (args in the prompt)",
         "delete_file", {"tool": "file_write", "args": "{}"},
         'Allow execution of tool \'file_write\' with args '
         '{"path": "C:/x/jarvis_gate.py"}?', "jarvis_gate.py"),
        ("jarvis_agent's tool call shape",
         "delete_file", {"text": "Delete the file the owner named."},
         'tool file_write {"path": "C:/x/jarvis_gate.py"}', "jarvis_gate.py"),
        ("jarvis_agent's plan-step shape",
         "delete_file", {"text": "Plan step - tidy up."},
         'plan step file_write {"path": "C:/x/jarvis-framework.toml"}',
         "jarvis-framework.toml"),
        ("a route card, target in `detail`",
         "delete_file", {"path": "C:/x/jarvis-framework.toml"},
         "Delete a file the owner named.", "jarvis-framework.toml"),
        ("a shell command whose args are in `detail`",
         "run_shell_on_host", {"command": "rm -f C:/x/jarvis_router.py"},
         "Clean up a temporary file.", "jarvis_router.py"),
        ("a protected name in the ACTION name",
         "unclassified_tool:file_write:jarvis_hud.py", {"text": "prose"},
         "prose", "jarvis_hud.py"),
        ("the approval queue itself, read-only tier",
         "read_files_readonly", {"path": "C:/x/approvals.db"},
         "Read a file for the owner.", "approvals.db"),
    )
    for label, action, detail, prompt, file in cases:
        v = G.check(action, detail, prompt=prompt, timeout=TIMEOUT)
        check(f"{label}: refused at 'never', naming {file}",
              v.tier == "never" and v.outcome == "refused" and file in v.reason,
              f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
        check(f"{label}: and NO row reached the queue",
              not [r for r in _pending_rows() if r.get("action") == action], "")

    # THE PLAIN REASON, WORD FOR WORD. It is the sentence the owner reads in
    # `jarvis_backup`'s record and in the gate's own audit line, so it is
    # pinned rather than described.
    v = G.check("delete_file", {"path": "C:/x/jarvis_hud.py"},
                prompt="Delete a file.", timeout=TIMEOUT)
    check("the refusal still says exactly what it said before",
          v.reason == ("this touches jarvis_hud.py, which no tool may modify; "
                       "edit it by hand"), repr(v.reason))


def t_a_refused_target_never_reaches_a_windows_hello_prompt():
    """Refused BEFORE any card, which is what makes it 'never' rather than
    'ask': no row, so nothing for `/api/pending` to offer and nothing to
    approve - on any device."""
    before = len(_pending_rows())
    v = G.check("delete_file", {"path": "C:/x/jarvis-hud.py.bak/still-no"},
                prompt="Delete a file.", timeout=TIMEOUT)
    check("CONTROL: a name that is NOT protected is unaffected by that rule",
          "no tool may modify" not in v.reason, repr(v.reason))
    v = G.check("delete_file", {"path": "C:/x/.openjarvis-patch.json"},
                prompt="Delete a file.", timeout=TIMEOUT)
    check(".openjarvis-patch.json is protected too",
          v.tier == "never" and "no tool may modify" in v.reason, repr(v.reason))
    check("and the queue is no longer than it was", len(_pending_rows()) >= before)


# ====== 2b. a tool call CUT to the log line's budget is still read

def t_a_cut_tool_call_line_still_refuses_a_protected_target():
    """THE HOLE #260 CLOSED, STILL PINNED. `jarvis_mcp.call` writes
    `tool <model_name> {plan.args_json[:1500]}` (`jarvis_mcp.py:1643`) and
    `jarvis_gate.gate_tool` slices the same way (`jarvis_gate.py:1710-1712`):
    a JSON object cut in half does not parse, so the rule read no arguments at
    all and offered an action whose target is the gate itself as an ordinary
    card, which a person could approve. What the action would TOUCH does not
    depend on the line being long enough to hold it.

    THE CUT LINE IS BUILT HERE, and that is deliberate: the real caller that
    still produces it (`jarvis_mcp.call`) needs a live plug-in server this
    suite does not have, and `jarvis_agent._gate_prompt` no longer produces it
    at all - DEF-003's fix removed the cut from all three of that module's gate
    lines (section 2c). The SHAPE is what is under test."""
    # `pathlib.Path('jarvis_gate.py').write_text('')` in the first 62
    # characters of the arguments, exactly as measured, then enough filler to
    # push the JSON past the line's 1500.
    args = {"command": "python -c \"import pathlib; "
                       "pathlib.Path('jarvis_gate.py').write_text('')\" "
                       "# " + "x" * 3300}
    full = json.dumps(args, ensure_ascii=False)
    prompt = f"tool run_shell_on_host {full[:1500]}"
    check("the arguments are longer than the audit-log line's 1500 characters",
          len(full) > 1500, len(full))
    cut = prompt[prompt.index("{"):]
    check("... so the line really holds a CUT JSON object, with the protected "
          "name still inside it",
          len(prompt) < len(full) and "jarvis_gate.py" in cut,
          f"line={len(prompt)} args={len(full)}")
    check("... which does not parse", not _parses(cut), cut[-30:])

    blobs = G._target_blobs("run_shell_on_host",
                            {"text": "Run a command the owner asked for."}, prompt)
    check("the cut arguments are still handed to the PROTECTED rule",
          any("jarvis_gate.py" in b for b in blobs), repr(blobs)[:200])

    v = G.check("run_shell_on_host", {"text": "Run a command the owner asked for."},
                prompt=prompt, timeout=TIMEOUT)
    check("... so it is REFUSED at 'never', not offered as a card",
          v.tier == "never" and v.outcome == "refused" and "jarvis_gate.py" in v.reason,
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
    check("... and NO row reached the queue, so there is nothing to approve",
          not [r for r in _pending_rows() if r.get("action") == "run_shell_on_host"], "")

    # The CONTROL, so none of the above can pass by the rule being dead: a
    # real protected target in `detail` is refused exactly as section 2 says.
    v = G.check("delete_file", {"path": "C:/x/jarvis_gate.py"},
                prompt="Delete a file.", timeout=TIMEOUT)
    check("CONTROL: a protected target in the arguments is still refused",
          v.tier == "never" and v.outcome == "refused", repr((v.tier, v.outcome)))


# ====== 2c. the arguments are read WHOLE, however long they are (DEF-003)

def t_a_protected_target_beyond_character_1500_is_still_refused():
    """THE OTHER HALF OF THE SAME HOLE, CLOSED (DEF-003, 2026-10-12).

    #260 read a tool call that had been CUT at 1500 - but only the text that
    survived the cut. The gate reads the model's own arguments through the line
    `jarvis_agent` hands it and nowhere else on these paths, and all three of
    that module's gate lines sliced them at 1500 BEFORE the gate was called:
    `_gate_prompt` (the direct tool call), the plan-step line, and the
    web-search call. A protected name past character 1500 was therefore never
    in the prompt at all, and no rule could read it - measured on the unfixed
    module, arguments 1693 characters long with a write to `jarvis_gate.py` at
    character 1658 came back as an ordinary "ask" card a person could approve.

    All three call sites now build their line with the one `_gate_prompt()`
    helper, which carries the whole argument JSON. The lines below are taken
    from the real module, never retyped here."""
    try:
        import jarvis_agent
    except Exception as exc:                       # pragma: no cover
        return skip(f"jarvis_agent is not importable here ({type(exc).__name__}: {exc})")

    # 1600 characters of filler FIRST, so the protected write is past 1500.
    args = {"command": "x" * 1600 + " ; python -c \"import pathlib; "
                                     "pathlib.Path('jarvis_gate.py').write_text('')\""}
    full = json.dumps(args, ensure_ascii=False)
    check("the protected write really is beyond character 1500 of the arguments",
          len(full) > 1500 and full.index("jarvis_gate.py") > 1500,
          f"args={len(full)} name at={full.index('jarvis_gate.py')}")

    # One shape at a time, and the tool-call line FIRST: on the unfixed module
    # that line is still cut, so the behavioural checks below fail and print
    # their reason before anything reaches the plan-step call. (That call is
    # the one that raises there - `plan_step` is a keyword the fixed helper
    # takes and the old one does not - so a loop would have hidden them behind
    # the TypeError.)
    def one_shape(label, prompt):
        check(f"{label} carries the WHOLE argument JSON, uncut",
              full in prompt, f"line={len(prompt)} args={len(full)}")
        blobs = G._target_blobs("run_shell_on_host",
                                {"text": "Run a command the owner asked for."}, prompt)
        check(f"{label}: the whole arguments reach the PROTECTED rule",
              any("jarvis_gate.py" in b for b in blobs), repr(blobs)[:200])
        v = G.check("run_shell_on_host", {"text": "Run a command the owner asked for."},
                    prompt=prompt, timeout=TIMEOUT)
        check(f"{label}: REFUSED at 'never' with the plain reason, not offered as a card",
              v.tier == "never" and v.outcome == "refused"
              and v.reason == ("this touches jarvis_gate.py, which no tool may modify; "
                               "edit it by hand"),
              f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
        check(f"{label}: and NO row reached the queue, so there is nothing to approve",
              not [r for r in _pending_rows() if r.get("action") == "run_shell_on_host"], "")

    one_shape("the tool-call line", jarvis_agent._gate_prompt("run_shell_on_host", args))
    one_shape("the plan-step line",
              jarvis_agent._gate_prompt("run_shell_on_host", args, plan_step=True))

    # EVERY gate line in the module comes from that one helper. DEF-003 names
    # three cut sites; the web-search one cannot be driven from here (it needs
    # a search provider), so the module's own source is what says the cut is
    # gone from it too - and it is what stops a fourth one appearing. Read as
    # CODE, not as text: the helper's own docstring quotes the old slice to
    # explain what was wrong with it, and a plain string search cannot tell an
    # explanation from a call. The slice check is deliberately blunt - this
    # module held exactly three 1500-cuts and nothing else that long - so a new
    # one is a question to answer, never a line to wave through.
    src = Path(str(getattr(jarvis_agent, "__file__"))).read_text(encoding="utf-8")
    calls = [l.strip() for l in src.splitlines()
             if "_gate_prompt(" in l and not l.lstrip().startswith("def ")]
    check("all three of the module's gate lines are built by that one helper",
          len(calls) == 3, calls)
    cut_at_1500 = [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)
                   and getattr(n.slice.upper, "value", None) == 1500]
    check("... and this module no longer slices anything at 1500",
          cut_at_1500 == [], [ast.unparse(n) for n in cut_at_1500])

    # The exemption is part of the fix, not a casualty of it: the retirement
    # what-if's arguments are the owner's own money figures and NOTHING of them
    # is written down - not on the card, not in the audit line.
    retirement = jarvis_agent._gate_prompt(
        jarvis_agent.RETIREMENT_TOOL, {"yearly_spending": 41000, "retire_age": 65})
    check("the retirement what-if still writes down none of its numbers",
          retirement == f"tool {jarvis_agent.RETIREMENT_TOOL}", repr(retirement))

    # The CONTROL, so none of the above can pass by the rule being dead.
    v = G.check("delete_file", {"path": "C:/x/jarvis_gate.py"},
                prompt="Delete a file.", timeout=TIMEOUT)
    check("CONTROL: a protected target in the arguments is still refused",
          v.tier == "never" and v.outcome == "refused", repr((v.tier, v.outcome)))


def t_the_cut_rule_only_reads_a_real_tool_call_line():
    """THE SCOPE, PINNED. The fix must not become an excuse to read a card's
    words again - that is what refused 45 of the owner's cards. Only a prompt
    that IS a tool-call line, from its first character to its last, is read
    as arguments. Here is a card that names three protected files, carries a
    brace that does not close, and even quotes a half-written tool call of
    its own: prose, and still raisable."""
    card = ("Restore Jarvis from this backup?\n\n"
            "This puts the .py files beside jarvis_hud.py back, and it leaves "
            "jarvis-framework.toml and jarvis_gate.py exactly as they are.\n\n"
            "The line it would run: tool file_write {\"path\": \"notes/today.md\"\n")
    blobs = G._target_blobs("restore_backup", {"text": card}, card)
    check("a card's words are not read as arguments, even with an unclosed "
          "brace and a tool-call fragment in them",
          not any("jarvis_gate.py" in b or "jarvis-framework.toml" in b
                  or "jarvis_hud.py" in b for b in blobs),
          repr(blobs)[:300])
    v, rows = _raise_and_watch("restore_backup", {"text": card}, card)
    check("... so the card it raises on is still raised",
          v.tier == "ask" and v.outcome != "refused" and bool(rows),
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")

    # The plainest form of the same thing: no braces at all, a protected name
    # in the prose, an action that touches nothing protected.
    prose = ("Let Jarvis read your calendar without asking you first?\n\n"
             "This changes one line of your settings file (jarvis-framework.toml).")
    blobs = G._target_blobs("loosen_what_asks_first", {"text": prose}, prose)
    check("... and so is a plain card naming jarvis-framework.toml",
          not any("jarvis-framework.toml" in b for b in blobs), repr(blobs)[:200])
    v = G.check("loosen_what_asks_first", {"text": prose}, prompt=prose,
                timeout=TIMEOUT)
    check("... which the gate still raises rather than refuses",
          v.tier == "ask" and v.outcome != "refused",
          f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")


# ============================== 3. the three real cards, end to end

def t_the_three_real_cards_are_raisable():
    """Through the REAL gate, with the SHIPPED tier table, on a scratch
    queue. The card text comes from the module that raises it - never typed
    in here - so a rewording cannot make this pass by accident."""
    tiers = fw.load_framework().get("autonomy", {}).get("tiers", {})
    check("the tier table is the shipped one, and answers 'ask' for all three",
          all(str(tiers.get(a, "")).strip().lower() == "ask" for a, _m, _f, _a in REAL_CARDS),
          {a: tiers.get(a) for a, _m, _f, _a in REAL_CARDS})
    for action, mod, fn, args in REAL_CARDS:
        card, why = _card_text((mod, fn, args))
        if card is None:
            skip(f"{action}: {why}")
            continue
        v, rows = _raise_and_watch(action, {"text": card}, card)
        check(f"{action}: the real card '{card.splitlines()[0][:52]}' is raised",
              v.tier == "ask" and v.outcome != "refused",
              f"tier={v.tier!r} outcome={v.outcome!r} reason={v.reason!r}")
        check(f"{action}: and it reached the queue with its card text on it",
              bool(rows) and card[:60] in (rows[0].get("prompt") or ""),
              repr([(r.get("action"), (r.get("prompt") or "")[:40]) for r in rows]))
        check(f"{action}: the reason it was refused - if it was - is not the "
              f"PROTECTED rule", "no tool may modify" not in v.reason, repr(v.reason))


def t_the_queue_and_the_audit_log_are_scratch():
    """Never the owner's own files: the whole suite runs against a temp
    directory, and this is the check that says so out loud."""
    check("the approvals database is in the scratch folder, not ~/.openjarvis",
          str(SCRATCH) in str(G.DB_PATH) and ".openjarvis" not in str(G.DB_PATH),
          str(G.DB_PATH))
    check("... and so is the audit log's directory",
          str(SCRATCH) in str(fw.LOG_DIR), str(fw.LOG_DIR))
    check("... and the shipped tier table was read, not a stub",
          bool(fw.load_framework().get("autonomy", {}).get("tiers")))


# ======================================= 4. what it refuses today, unchanged

def t_everything_else_it_refuses_today_it_still_refuses():
    v = G.check("delete_joplin_note", {"note": "x"}, prompt="Delete a Joplin note.",
                timeout=TIMEOUT)
    check("a never-tier action is still refused, in its own words",
          v.tier == "never" and "set to 'never' in jarvis-framework.toml" in v.reason,
          repr((v.tier, v.reason)))

    keep = fw.load_framework
    fw.load_framework = lambda: {}
    try:
        v = G.check("delete_file", {}, prompt="Do the thing.", timeout=TIMEOUT)
        check("an unreadable policy is still refused",
              v.outcome == "refused" and v.tier == "unknown", repr(v.reason))
    finally:
        fw.load_framework = keep

    v = G.check("something_nobody_classified", {"what": "x"}, prompt="Do the thing.",
                timeout=TIMEOUT)
    check("an unclassified action still falls to 'ask' (UNKNOWN_TIER)",
          v.tier == "ask" and v.outcome != "refused", repr((v.tier, v.outcome)))

    action, confident = G.action_for_tool("file_write", {"path": "C:/x/a.txt"})
    check("file_write is still delete_file at 'ask'",
          action == "delete_file" and confident, f"{action!r} {confident!r}")
    action, _ = G.action_for_tool("shell_exec",
                                  {"command": "ngrok http 8000"})
    check("the shell escalations are untouched: ngrok is still a tunnel",
          action == "open_public_tunnel", repr(action))

    # The verdict type's own invariants, and the outcome vocabulary.
    check("only auto/notify/approved may carry allowed=True",
          G.Verdict(True, "ask", "x", "y", outcome="refused").allowed is False
          and G.Verdict(True, "ask", "x", "y", outcome="approved").allowed is True)
    check("a timeout is still not a person saying yes",
          G.Verdict(True, "ask", "x", "y", outcome="timed_out").allowed is False)
    check("the outcome vocabulary has not grown",
          set(G.OUTCOMES) == {"auto", "notify", "approved", "denied",
                              "timed_out", "refused"}, repr(sorted(G.OUTCOMES)))


def t_the_rule_still_runs_before_every_tier_branch():
    """It is the one rule ABOVE the tier table: a protected target is refused
    even for a tier that would otherwise run with nobody asked."""
    source = (BASE / "jarvis_gate.py").read_text(encoding="utf-8")
    at_rule = source.index("hit = _touches_protected(")
    for branch in ('if tier == "never":', 'if tier == "auto":', 'if tier == "notify":',
                   "if not _approval_stamped("):
        check(f"the PROTECTED rule is above `{branch}`",
              source.index(branch) > at_rule, "")
    v = G.check("calculator", {"path": "C:/x/jarvis_gate.py"},
                prompt="Add two numbers.", timeout=TIMEOUT)
    check("... so even an auto-tier action cannot touch one",
          v.tier == "never" and v.outcome == "refused", repr((v.tier, v.outcome)))


# ======================================================= the patch itself

def t_the_patch_is_registered_and_carries_the_change():
    if not PATCH.is_file():
        check("gate-touches.patch exists", False, str(PATCH))
        return
    body = PATCH.read_text(encoding="utf-8")
    check("it patches jarvis_gate.py and nothing else",
          sorted(l[6:].strip() for l in body.splitlines() if l.startswith("+++ b/"))
          == ["jarvis_gate.py"],
          [l for l in body.splitlines() if l.startswith("+++ ")])
    check("it is the change this suite tests: the rule reads target blobs",
          "+    hit = _touches_protected(*_target_blobs(action, detail, prompt))" in body
          and "+def _target_blobs(" in body, "")
    # The refusal sentence and the protected list are not touched at all: no
    # added or removed line mentions either. (The hunk HEADER quotes
    # `_PROTECTED = (` as its context line, which is why this reads the lines
    # rather than counting the text.)
    touched = [l for l in body.splitlines()
               if l[:1] in ("+", "-") and ("this touches" in l or "_PROTECTED" in l)]
    check("it does not add a second protected list or a second refusal reason",
          touched == [], touched)

    text = PS1.read_text(encoding="utf-8")
    start = text.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in text[start:text.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("gate-touches.patch is in apply-patches.ps1's $PATCHES list",
          "gate-touches.patch" in names, names[-3:])
    check("every name in the list has a file",
          all((HERE / n).is_file() for n in names),
          [n for n in names if not (HERE / n).is_file()][:3])
    # THE ENTRY MUST BE THE BARE NAME ON ITS OWN LINE. _stack.order() reads
    # this same slice and strips only quotes, so a trailing comma or a
    # trailing comment becomes part of the file name and the whole stack walk
    # (`_stack.stand_in`, which twenty suites depend on) stops finding it.
    check("... and every entry is a bare file name (`_stack.order()` reads this "
          "list the same way)",
          all(n.endswith(".patch") and " " not in n and "#" not in n for n in names),
          [n for n in names if not (n.endswith(".patch") and " " not in n
                                    and "#" not in n)][:3])
    # "Last" means last but for the patches written after it - the same rule
    # test_gate_risk_rows.py and test_referee.py use. Every new patch is
    # appended, so the next one pushes this one up the list, and that is not a
    # defect in either of them. Each name here is a patch that was written
    # after this one and touches jarvis_gate.py not at all.
    #
    # plugin-loader.patch stays in the list rather than here: it is the one
    # patch that MUST be last (it edits the end of the file the whole stack
    # produces), so a patch appended after this one goes immediately before
    # it, and this check is what says so.
    later = {"plugin-loader.patch",
             # picture-card.patch (2026-10-11) is the first patch to take that
             # advice: it sits immediately BEFORE plugin-loader.patch, and it
             # touches jarvis_gate.py not at all (ONE hunk, in jarvis_hud.py, on
             # the owner's own lines just before the main socket is built - see
             # the note in apply-patches.ps1 and _stack.py's RATCHET), so it
             # rewrites nothing this patch wrote.
             "picture-card.patch",
             # card-prefs.patch (2026-10-10, "cards read short") is the second
             # name to take it and follows the same rule: it sits after
             # gate-touches.patch and before picture-card.patch (so, before
             # plugin-loader.patch too), and it touches jarvis_gate.py not at
             # all - ONE hunk, in jarvis_hud.py, fifteen ADDED lines: an install
             # block straight after animal.patch's own. It rewrites nothing this
             # patch wrote, which is why it is in this set rather than in the
             # list above. test_devices.py, test_gate_risk_rows.py,
             # test_referee.py and test_screen_attach.py carry the same name in
             # their own allow-lists.
             "card-prefs.patch",
             # big-coder.patch (2026-10-11) takes the same advice: it sits
             # immediately BEFORE plugin-loader.patch, and it touches
             # jarvis_gate.py not at all (two hunks, both in jarvis_hud.py, each
             # ADDING one route block on lines no other patch writes), so it
             # rewrites nothing this patch wrote.
             "big-coder.patch",
             # pictures.patch (2026-10-11, "ask for a picture") is the same
             # shape a third time: it sits immediately BEFORE
             # plugin-loader.patch, and it touches jarvis_gate.py not at all
             # (ONE hunk, in jarvis_hud.py, ADDING one install block at the end
             # of the chain), so it rewrites nothing this patch wrote.
             "pictures.patch",
             # model-lanes.patch (2026-10-13, "Start the local model") is that
             # same shape once more, and it sits immediately BEFORE
             # plugin-loader.patch (the loader's hunk was re-anchored onto ITS
             # block; initiative-payload.patch was appended between the two on
             # 2026-10-15 and is listed below): it touches jarvis_gate.py not at
             # all - the automatic lane restart raises no card and answers no
             # card, so it adds no action to the gate - and its ONE hunk in
             # jarvis_hud.py ADDS an install block at the end of the chain, so it
             # rewrites nothing this patch wrote.
             "model-lanes.patch",
             # initiative-payload.patch (2026-10-15) takes the same advice: it
             # is appended between pictures.patch and plugin-loader.patch (so,
             # before the loader too), and it touches jarvis_gate.py not at all
             # - ONE hunk, in jarvis_hud.py, on the /api/initiative route's own
             # return line, which no patch in this list writes. It rewrites
             # nothing this patch wrote: gate-touches.patch's two hunks are
             # under `_PROTECTED`/`_PROTECTED_RE` and at check()'s own
             # `hit = _touches_protected(...)` call, hundreds of lines away.
               "initiative-payload.patch",
               # hud-origin-module.patch + hud-exclusive-bind.patch (SECPRIV audit
               # 2026-10-18) are appended immediately before plugin-loader.patch and
               # touch ONLY jarvis_hud.py: the two request-edge decisions delegate to
               # the tracked jarvis_owner_check module, and the main listener takes the
               # port exclusively. No gate list entry, no tier row, no _RISK row, no
               # _TOOL_ACTIONS line, and no line this patch writes - so neither can
               # rewrite my lines. Ordering is safe: they are the last two before the
               # loader and change nothing another patch's hunks anchor on.
             "hud-origin-module.patch",
"hud-exclusive-bind.patch",
             # presets.patch (2026-10-18) is appended after those two and before
             # plugin-loader.patch: ONE helper block near the top of jarvis_hud.py and
             # FOUR chat call sites resolved through it. No gate list, no tier row, no
             # _RISK row, no _TOOL_ACTIONS line, and no line this patch writes.
             "presets.patch"}
    others = [n for n in names if n not in later]
    check("it is LAST in the stack, bar the ones written after it, and bar "
          "plugin-loader.patch (which must be last of all)",
          others and others[-1] == "gate-touches.patch",
          others[-3:] if others else names[-3:])
    check("... and plugin-loader.patch is still last of all",
          names[-1] == "plugin-loader.patch", names[-1:])


def t_the_change_is_in_the_repositorys_own_copy_of_the_gate():
    """The patch and this repository's copy of the gate must say the same
    thing: a patch written against text that is not there applies nowhere."""
    source = (BASE / "jarvis_gate.py").read_text(encoding="utf-8")
    check("the published gate holds the new rule",
          "hit = _touches_protected(*_target_blobs(action, detail, prompt))" in source)
    check("... the two new names are defined before they are used",
          source.index("def _target_blobs(") < source.index("hit = _touches_protected(")
          and source.index("_PROSE_KEYS = (") < source.index("def _target_blobs("))
    check("... and the old two-blob call is gone",
          "_touches_protected(prompt, detail)" not in source)
    # The DEF-012 whole-argument prompt and the I6 memory latch are proved by
    # BEHAVIOUR against this same published gate, in
    # t_the_whole_arguments_are_read_and_a_failed_latch_still_holds below -
    # no second source-text pin, so this suite stays inside its ratchet.
    # The patch removes the old lines the published copy no longer has, and adds
    # the two replacements (DEF-012 and I6). More than one removal is expected
    # since 2026-10-18: the gate-tool prompt and the latch's fail-open return
    # are bounded-argument/plain-error lines of this same patch's own subject.
    body = PATCH.read_text(encoding="utf-8")
    removed = [l[1:] for l in body.splitlines()
               if l.startswith("-") and not l.startswith("---")]
    check("it still removes the old two-blob call",
          "    hit = _touches_protected(prompt, detail)" in removed, removed[-6:])
    old_gate_tool = [l for l in removed
                     if l.startswith("    v = check(action, detail, prompt=f\"tool {name} ")
                     and "detail['args']" in l]
    check("... and replaces gate_tool's 1500-cut prompt with the whole arguments "
          "(DEF-012)",
          bool(old_gate_tool)
          and '+    v = check(action, detail, prompt=f"tool {name} {raw_args}")' in body
          and "+        _latch_in_memory(seconds, why)" in body, removed[-6:])


def t_the_whole_arguments_are_read_and_a_failed_latch_still_holds():
    """DEF-012 and I6, against the published gate itself.

    DEF-012: `gate_tool` used to hand the gate `detail["args"]` cut at 1,500
    characters as the prompt too, so a protected target past that point was
    never scanned and the action came back as an ordinary card. The whole
    arguments now reach the scan; the stored copy stays bounded inside check().
    I6: `latch_taint` used to `return False` when its own database write raised,
    i.e. it created NO latch for a private read. It now keeps a process-local
    latch, and taint_active() reads it.
    """
    args = {"command": "x" * 1600 + " ; python -c \"import pathlib; "
                                       "pathlib.Path('jarvis_gate.py').write_text('')\""}
    full = json.dumps(args)
    check("the protected write really is beyond character 1500 of the arguments",
          len(full) > 1500 and full.index("jarvis_gate.py") > 1500,
          f"args={len(full)} at={full.index('jarvis_gate.py')}")
    refused = G.gate_tool("run_shell_on_host", args)
    check("gate_tool REFUSES the protected target past 1500, naming it",
          isinstance(refused, str) and "no tool may modify" in refused
          and "jarvis_gate.py" in refused, refused)
    check("... and NO row reached the queue, so there is nothing to approve",
          not [r for r in _pending_rows() if r.get("action") == "run_shell_on_host"])

    # I6: a latch that cannot be written is still a latch, in memory.
    real_connect = G._connect

    def gone():
        raise RuntimeError("the latch database has gone away")

    try:
        G.clear_taint()
        G._connect = gone
        check("latch_taint returns True when its own write fails (fail closed)",
              G.latch_taint(minutes=1, why="audit-i6") is True)
        check("... and taint_active() still answers private",
              G.taint_active() is True)
    finally:
        G._connect = real_connect
        G.clear_taint()
    check("... and clearing it releases the memory latch too",
          G.taint_active() is False)


def t_no_other_patch_already_rewrites_that_call():
    """If another patch in the stack changed the CALL this one replaces, this
    one would be racing it - the failure test_gate_risk_rows.py exists to
    catch, one dict over. `no-auto-approve.patch` is the exception and is
    named here on purpose: it REMOVES an older, different call -
    `_touches_protected(prompt)` inside `confirm_auto()` - which is why the
    published gate has exactly one call left to change."""
    others = []
    for p in sorted(HERE.glob("*.patch")):
        if p.name == PATCH.name:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line[:1] in ("+", "-") and "hit = _touches_protected(" in line:
                others.append(f"{p.name}: {line[:70]}")
    check("no other patch adds or removes the call this one replaces",
          not others, others)
    # The one mention that IS allowed, pinned to the patch that owns it, so a
    # second one cannot slip in unnoticed.
    allowed = []
    for p in sorted(HERE.glob("*.patch")):
        if p.name == PATCH.name:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line[:1] in ("+", "-") and "_touches_protected" in line:
                allowed.append(p.name)
    check("the only other patch that mentions the rule is no-auto-approve.patch",
          sorted(set(allowed)) == ["no-auto-approve.patch"], sorted(set(allowed)))


def t_the_patch_applies_to_the_published_gate():
    """`git apply` on a copy of the file the patch names.

    `jarvis-backend/jarvis_gate.py` is the state the WHOLE stack leaves, so
    the patch is rehearsed the way the patcher rehearses it: take the change
    back out, which is the text the owner's own file holds, then apply it
    forwards and compare with the published copy byte for byte. A patch that
    cannot do both would apply to nothing.

    Skips honestly when git is missing."""
    import shutil
    import subprocess
    git = shutil.which("git")
    if not git:
        return skip("git is not installed, so the patch cannot be rehearsed here")
    d = Path(tempfile.mkdtemp(prefix="jarvis-gate-touches-patch-"))
    try:
        # LF, deliberately: `.gitattributes` is `* text=auto eol=lf` while
        # `*.patch -text`, so a patch's context lines are LF and the file has
        # to be written the same way. The comparison at the end normalises
        # endings rather than assuming either - the same rule `_where.
        # _same_text()` uses, and the reason that helper exists.
        armed = _normalised(BASE / "jarvis_gate.py")
        (d / "jarvis_gate.py").write_text(armed, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes(PATCH.read_bytes().replace(b"\r\n", b"\n"))
        back = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d,
                              capture_output=True, text=True)
        check("the patch reverses out of the published gate (which is how the "
              "patcher recognises and replaces an older version)", back.returncode == 0,
              back.stderr.strip())
        if back.returncode != 0:
            return
        before = _normalised(d / "jarvis_gate.py")
        check("... and what is left is the old rule, and only that",
              "hit = _touches_protected(prompt, detail)" in before
              and "_target_blobs" not in before)
        fwd = subprocess.run([git, "apply", "p.patch"], cwd=d,
                             capture_output=True, text=True)
        check("... and it applies forwards again", fwd.returncode == 0,
              fwd.stderr.strip())
        check("... giving back the published file, line endings aside",
              _normalised(d / "jarvis_gate.py") == armed)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _normalised(path):
    """The text of a file, CRLF folded to LF - `_where._same_text()`'s rule."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
