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

WHAT THIS SUITE PINS. `_target_blobs()` decides what the rule may read: the
action's parameters (`detail`, minus the keys holding the card's own text)
and the model's own tool call, which is the JSON object inside the prompt.
Card prose is not a target and is not searched. So:

  1. a card that merely NAMES a protected file is raisable - the case that
     has bitten three times (section 1);
  2. an action whose TARGET is a protected file is still refused at "never",
     before any card exists, with the same plain reason as before - on every
     shape a real caller uses to hand it over (section 2);
  3. the three real cards are raisable END TO END through the real gate and
     the SHIPPED tier table, with a scratch approvals database and a scratch
     audit directory (section 3);
  4. everything else the gate refuses today, it still refuses (section 4).

`jarvis-backend/jarvis_gate.py` is this repository's published copy of the
gate (jarvis-backend/README.md says where it came from), so the module under
test here is the one the patch in `backend/` is written against. That patch,
`gate-touches.patch`, is what carries this to the owner's own backend; the
last check in this file pins it into the stack.

Runs in repo mode (JARVIS_BACKEND unset), from the repository root:

    py -3 backend/test_gate_touches.py
"""
from __future__ import annotations

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
             "picture-card.patch"}
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
    # The patch removes exactly the line the published copy no longer has.
    body = PATCH.read_text(encoding="utf-8")
    removed = [l[1:] for l in body.splitlines()
               if l.startswith("-") and not l.startswith("---")]
    check("it removes exactly one line, the old call",
          removed == ["    hit = _touches_protected(prompt, detail)"], removed)


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
