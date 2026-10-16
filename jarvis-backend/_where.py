"""Where the backend actually is, so the tests run on the owner's machine too.

THE PROBLEM THIS SOLVES

Every test in this directory was written assuming the backend modules sit
beside it:

    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE))
    import jarvis_memory          # only works if jarvis_memory.py is HERE

That is true in the development container, where the modules are symlinked
into this folder. It is false on the machine that actually runs Jarvis, where
the backend lives somewhere like

    C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\Desktop program

and this repository is cloned somewhere else entirely. So the suites could be
run by one person in one place, which is the opposite of what a test is for —
and `apply-patches.ps1` offered to run them straight after patching, which
would have produced eighteen import errors that look exactly like the patches
having broken something.

TWO ROOTS, NOT ONE

The tests need two different places and were using `HERE` for both:

    BACKEND   the Python modules being tested. Elsewhere, on a real install.
    REPO      this repository: the patches, and the desktop client source
              that several tests read to check a route has a caller.

`REPO` is always the parent of this file's directory — the tests live in the
repo, so that cannot be wrong. `BACKEND` is `JARVIS_BACKEND` if it is set,
and otherwise this directory, which keeps the container working exactly as
before with no flag.

USAGE

    from _where import BACKEND, REPO

    HUD = BACKEND / "jarvis_hud.py"          # a backend source file
    BRAIN_JS = REPO / "jarvis-desktop" / "src" / "brain.js"

Importing this module also puts `BACKEND` on `sys.path`, so `import
jarvis_memory` works without each test repeating it.
"""
from __future__ import annotations

import inspect as _inspect
import os
import sys
from pathlib import Path

# Python < 3.10 compatibility: Path.write_text did not accept newline.
#
# The probe used to be `Path("").write_text("", newline="\n")`, which asks the
# filesystem rather than the signature: `Path("")` is the current directory,
# so opening it for writing raises IsADirectoryError or PermissionError, never
# the TypeError being tested for. On a Python 3.9 machine the shim therefore
# never installed, and all 84 `write_text(..., newline=...)` call sites raised
# TypeError. Asking the signature directly cannot be defeated by a permission
# or a path, and it never touches a file.
if "newline" in _inspect.signature(Path.write_text).parameters:
    pass
else:
    _orig_write_text = Path.write_text

    def _compat_write_text(self, data, encoding=None, errors=None, newline=None):
        if newline is not None:
            with self.open(mode="w", encoding=encoding, errors=errors, newline=newline) as f:
                return f.write(data)
        return _orig_write_text(self, data, encoding=encoding, errors=errors)

    Path.write_text = _compat_write_text

# A SUITE'S OWN OUTPUT, CARRIED BY A WINDOWS CONSOLE TOO.
#
# A Windows console - and a pipe - defaults Python's stdout to the machine's
# ANSI code page (cp1252 here), and 56 suites print a character it cannot
# encode: a curly quote from a fixture, an em dash, the Cyrillic host
# test_youtube.py refuses. The print raises UnicodeEncodeError INSIDE the
# suite, so a check that passed is reported as a failing suite. run_suites.py
# sets PYTHONIOENCODING for its children for exactly this reason (its own
# docstring documents the class) and scripts/apply-patches.ps1 asks for it
# too - but a bare `python backend\test_wakeword.py`, which is how one suite
# gets run by hand, has neither.
#
# Measured 2026-10-10, test_wakeword.py direct in this checkout: 101 passed,
# 1 failed, exit 1 without this, and 121 passed, 0 failed, 1 skipped with
# PYTHONIOENCODING=utf-8 - the exception abandoned one check twenty checks
# early. Every suite imports this module, so the fix belongs here once rather
# than in each of the 56 files, which is how such a line gets rediscovered one
# suite at a time. tools/check_tutorial_places.py sets its two streams the
# same way for the same reason; there the check IS the process, so nobody can
# set the variable for it. A character the console cannot draw is replaced
# rather than fatal.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        # Not a text stream (a suite's own capture, a closed pipe): nothing to
        # reconfigure, and never a reason for an import to fail.
        pass
del _stream

_HERE = Path(__file__).resolve().parent

#: This repository. The tests are in it, so its location is never in doubt.
REPO = _HERE.parent

#: The folder holding jarvis_hud.py, jarvis_memory.py and the rest.
#:
#: Set JARVIS_BACKEND to run the suites against a real install:
#:
#:     $env:JARVIS_BACKEND = "C:\\...\\Desktop program"; python backend\\test_memory_safety.py
#:
#: Unset, it is this directory - which is where the dev container symlinks
#: them, so nothing there needs the variable.
BACKEND = Path(os.environ.get("JARVIS_BACKEND") or _HERE).resolve()


# --------------------------------------------------------------------------
#   ONE STAGING ROOT FOR A DIRECT RUN (2026-10-11)
# --------------------------------------------------------------------------
#
# THE HALF OF THE LEAK #261 LEFT. That work closed the SWEEP path: a run of
# `backend/run_suites.py` stages one `jarvis-sweep-<rand>` root, points
# TMPDIR/TEMP/TMP into it, and removes it in a `finally`. But suites are run
# DIRECTLY too - `python backend/<suite>.py`, which is how every teammate works
# and what the briefs instruct - and then nothing owns their scratch. Nearly
# every suite in this folder makes its own `jarvis-<suite>-<rand>` at import
# time with `tempfile.mkdtemp` and never removes it: one folder per suite per
# run. Measured 2026-10-11: 1,663 `jarvis-*` folders under %TEMP% and growing
# (581 at 02:20 the same night), against 20,633 reaching 123.6 GB the night
# this started.
#
# WHAT THIS DOES, and it is deliberately the SAME machinery, not a second one:
# a direct run claims ONE `jarvis-direct-<rand>` root with run_suites.claim()
# (so it carries `_owner.json` and an exclusive lock, and a killed run's root
# is recognisable and reapable by run_suites.reap_orphans), points
# TMPDIR/TEMP/TMP - and `tempfile.tempdir`, which is cached on first use - into
# `<root>/tmp`, and removes the whole root from an `atexit` handler that closes
# the lock FIRST (on Windows a file this process still holds open cannot be
# deleted, which is how a folder gets left behind whole).
#
# WHY IT DOES NOT REAP. Reaping here would delete the folders that are already
# on the machine - most of the 1,663 carry no marker and are over a day old -
# and cleaning %TEMP% while agents run is how tonight's damage happened. The
# reaper stays where #261 put it, on the sweep path, and a killed direct run's
# marked root is collected there.
#
# INSIDE A SWEEP IT DOES NOTHING: the sweep owns the root already, and TMPDIR
# is `<sweep>/tmp`.
def _stage_a_direct_run() -> None:
    """Never raises: a suite must still run if this cannot. A failure here
    leaves the old behaviour (folders under %TEMP%), not a broken suite."""
    try:
        if str(os.environ.get("JARVIS_NO_DIRECT_STAGE") or "") == "1":
            return
        import atexit
        import tempfile

        here = Path(tempfile.gettempdir())
        try:
            import run_suites as _R
        except Exception:
            return
        # Already inside a sweep: `<sweep>/tmp`. Its root owns this already.
        if here.name == _R.SUITE_TEMP_NAME and _R.REAPABLE.match(here.parent.name or ""):
            return
        root = Path(tempfile.mkdtemp(prefix=_R.DIRECT_PREFIX, dir=str(here)))
        lock = _R.claim(root, "direct")
        if lock is None:
            return
        inner = root / _R.SUITE_TEMP_NAME
        inner.mkdir(parents=True, exist_ok=True)
        for _k in ("TMPDIR", "TEMP", "TMP"):
            os.environ[_k] = str(inner)
        # tempfile caches the answer on its first use, and a suite's own
        # mkdtemp may already have run by now in an odd import order.
        tempfile.tempdir = str(inner)

        def _done() -> None:
            try:
                os.close(lock)
            except Exception:
                pass
            try:
                _R.remove_tree(root, "direct suite run")
            except Exception:
                pass

        atexit.register(_done)
    except Exception:
        return


_stage_a_direct_run()

#: Every suite imports this file. A suite run on the owner's PC (with
#: JARVIS_BACKEND set, or by apply-patches.ps1) must never write the made-up
#: conversations it runs into the owner's real chat history: the modules that
#: keep a finished conversation there on their own (jarvis_chatbot's
#: keep_in_history) keep nothing while this is set. A suite that tests the
#: keeping hands in its own ChatLog.
os.environ["JARVIS_SUITE_RUNNING"] = "1"

# Prepended, not appended: if a stale copy of a module is ever left in this
# folder, the one in BACKEND is the one under test and must win.
_b = str(BACKEND)
if _b in sys.path:
    sys.path.remove(_b)
sys.path.insert(0, _b)

#: The ten modules this repository ships WHOLE, as this checkout holds them:
#: `backend/rebuilt/`. APPENDED, never prepended - a copy in BACKEND is the one
#: under test and must win (see `_b` above).
_REBUILT = _HERE / "rebuilt"

# WHY THIS LINE IS HERE, AND WHY IT IS NOT IN EVERY SUITE.
# On the owner's PC, apply-patches.ps1 flattens these ten BESIDE jarvis_hud.py;
# run_suites.py flattens them into the staged backend it hands every suite. In
# both of those `import jarvis_memory` just works. A suite run straight out of a
# clone (JARVIS_BACKEND unset - `python backend/test_x.py`, which is how the
# owner runs them) has neither: this folder holds the patches and the tests, and
# `rebuilt/` holds the ONLY copy of those ten modules that exists anywhere. So
# 110 suites already carry the same line themselves, in FOUR spellings
# (`append(str(HERE / "rebuilt"))` x51, `insert(0, ...)` x32, `insert(1, ...)`
# x14, `append(str(REPO / "backend" / "rebuilt"))` x14). The six that forgot it
# died at `ModuleNotFoundError: No module named 'jarvis_memory'` before a single
# check could run - which is how this drift is found: one suite at a time, by
# whoever runs the next one. This module already owns sys.path (its docstring
# above says putting `BACKEND` on it is so "`import jarvis_memory` works without
# each test repeating it"), so the missing half lives here too, once. A suite
# that needs these modules FIRST still says so itself - `test_rebuilt.py` tests
# the rebuilt copies and puts them at the front - and for everyone else BACKEND's
# copy still wins.
if _REBUILT.is_dir() and str(_REBUILT) not in sys.path:
    sys.path.append(str(_REBUILT))


def missing(*names: str) -> list[str]:
    """Which of these backend files are not where BACKEND says they are.

    Tests call this to skip honestly rather than fail. A suite reporting
    "jarvis_hud.py is not in <path>" is a configuration problem; the same
    suite reporting nine assertion failures looks like the patches broke the
    product, which is the wrong thing to be told after applying them.
    """
    return [n for n in names if not (BACKEND / n).is_file()]


def explain() -> str:
    """One line a person can act on, for when a file is not there."""
    where = "JARVIS_BACKEND" if os.environ.get("JARVIS_BACKEND") else "this folder"
    return (f"Backend modules were looked for in {BACKEND} ({where}). "
            f"Set JARVIS_BACKEND to the folder holding jarvis_hud.py.")


def hud_block(start: str, end: str) -> tuple:
    """(the text between `start` and `end` in the patched jarvis_hud.py, where
    it came from) - or (None, why this run cannot have it).

    WHY THIS IS HERE AND NOT IN ONE SUITE. jarvis_hud.py is the entry point
    scripts/apply-patches.ps1 edits IN PLACE (it is never copied), so a clone's
    backend/ does not hold it and `SRC = BACKEND / "jarvis_hud.py"` died as a
    FileNotFoundError before a single check. Seven suites read it; one of them,
    test_appearance.py, only ever looks at ONE self-contained block of it, and
    that block is the text the patch stack itself writes. So the block is what
    this returns, from whichever of the two this run can honestly use:

      * BACKEND's own jarvis_hud.py when it is there - the file the backend
        runs, and the only thing a check that reads the SURROUNDING file may
        use. Anything asking "is this route still wired up in main()" needs
        the owner's own lines, which no stand-in holds; those suites say so
        and skip instead (a stand-in that made such a check pass would be the
        patch grading itself).
      * otherwise, in repo mode only (no JARVIS_BACKEND), the patch stack's
        own text for it (`_stack.stand_in`, which walks every patch
        apply-patches.ps1 applies, in order). Ten suites already lift real
        code out of that stand-in - test_chat_log.py, test_temporary_chat.py,
        test_tidy.py, eval_learner.py and the rest - so this is the project's
        own way of driving patch-written code in a clone, not a new one.

    IT REFUSES A BLOCK THE STACK COULD NOT REBUILD WHOLE. `_stack` leaves a
    "# gap" where the owner's own lines between two hunks are missing, so a
    block with a gap in it is part real, part absent, and a suite that drove
    it would be testing a fragment. The block must also compile. Both are
    returned as the reason, so the caller skips saying which and why - never a
    pass, and never a traceback.
    """
    path = BACKEND / "jarvis_hud.py"
    if path.is_file():
        src, where = path.read_text(encoding="utf-8"), str(path)
    elif os.environ.get("JARVIS_BACKEND"):
        # A run that NAMES a backend: a file missing from it is that install's
        # problem and is said so, not papered over with the stack's text.
        return None, (f"jarvis_hud.py is not in {BACKEND}, which JARVIS_BACKEND "
                      f"names, and the patcher edits it in place. {explain()}")
    else:
        import _stack                                   # beside this file
        src, log = _stack.stand_in("jarvis_hud.py")
        if src is None:
            return None, ("the patch stack could not build jarvis_hud.py: "
                          + "; ".join(log[-2:]))
        where = "the patch stack's own text for it, from backend/_stack.py"
    try:
        block = src[src.index(start):src.index(end)]
    except ValueError:
        return None, (f"jarvis_hud.py ({where}) does not hold both `{start}` and "
                      f"`{end}`")
    if any(line.startswith("# gap") for line in block.splitlines()):
        return None, (f"the stand-in has a gap between `{start}` and `{end}`: the "
                      f"owner's own lines are missing there, so this block is not "
                      f"all real and a check that drove it would prove nothing")
    try:
        compile(block, f"<jarvis_hud.py {start!r}>", "exec")
    except SyntaxError as exc:
        return None, (f"the block from `{start}` to `{end}` in jarvis_hud.py "
                      f"({where}) does not compile: {exc.msg} (line {exc.lineno})")
    return block, where


#: Modules this repository ships WHOLE, for the owner's backend folder:
#: apply-patches.ps1 copies each one beside jarvis_hud.py (a "rebuilt/" entry
#: lands there too, by file name). Every import of one of these is wrapped,
#: so a backend without the file runs - with that feature quietly off.
#:
#: The SAME list, in the same order, as `$SHIPPED` in scripts/apply-patches.ps1.
#: test_shipped_modules.py fails if they differ, and if any module a shipped
#: file or a patch imports is in neither this list nor its exemptions. This
#: tuple once lagged the script by seven modules and the script once lagged
#: jarvis_agent.py by seven more.
SHIPPED = (
    # the ten rebuilt modules
    "rebuilt/jarvis_compute.py", "rebuilt/jarvis_events.py",
    "rebuilt/jarvis_framework.py", "rebuilt/jarvis_initiative.py",
    "rebuilt/jarvis_memory.py", "rebuilt/jarvis_power.py",
    "rebuilt/jarvis_recall.py", "rebuilt/jarvis_router.py",
    "rebuilt/jarvis_sleep.py", "rebuilt/jarvis_voice.py",
    # modules the patches call
    "jarvis_intake.py", "jarvis_feedback.py", "jarvis_skill_discovery.py",
    "jarvis_speed.py", "jarvis_owned_tables.py", "jarvis_agent.py",
    "jarvis_voice_enroll.py", "jarvis_speech.py",
    "jarvis_task_control.py", "jarvis_note_capture.py", "jarvis_power_switch.py",
    "jarvis_wakeword.py",
    "jarvis_token_store.py",
    "jarvis_second_card.py",
    "jarvis_wiki.py",
    "jarvis_big_model.py",
    "jarvis_turn.py", "jarvis_wakebank.py", "jarvis_stopword.py",
    "jarvis_local_http.py", "jarvis_child_env.py",
    "jarvis_voices.py", "jarvis_f5_worker.py",
    # which Kokoro voice pack is installed, its voices by name, the pinned
    # v1.0 download: jarvis_voices.py imports it (no patch)
    "jarvis_kokoro.py",
    "jarvis_bakeoff.py",
    "jarvis_learning_switch.py",
    "jarvis_voicebank.py",
    "jarvis_voice_flow.py",
    # "Write Like Me": how the owner writes, measured from his own words, with
    # names and numbers stripped before anything reaches a model. Its own
    # voiceprint.db, every write guarded by jarvis_scrub, and its routes come
    # from plugins/ready/voiceprint - no patch
    "jarvis_voiceprint.py",
    # the animals' mouths timed by Kokoro itself: jarvis_speech.py calls it
    "jarvis_mouth.py",
    "jarvis_chat_log.py",
    # "Paste guard" (feasibility I115): masks a pasted password, PIN or
    # one-time code before jarvis_chat_log.py writes a message to the
    # encrypted database - reuses jarvis_sensitive.py's and
    # jarvis_mail_mask.py's own pattern shapes, its own small variant
    "jarvis_paste_guard.py",
    "jarvis_auto_learn.py",
    "jarvis_sensitive.py",
    "jarvis_past.py",
    "jarvis_entities.py",
    "jarvis_profiles.py", "jarvis_hardware.py",
    # the five work setups - combinations of local models for a kind of work,
    # each explained in plain words before the owner starts, and the pure
    # offer that reads the owner's own words (work.patch). It switches
    # nothing: every model change is still the existing card.
    "jarvis_work.py",
    "jarvis_scrub.py",
    # The one connection class that CLOSES when its `with` block ends, shared
    # by jarvis_schedule.py, jarvis_goals.py and jarvis_projects.py
    # (2026-10-08: the WinError 32 "schedule.json is being used by another
    # process" failure, fixed by hand three times before it was shared).
    "jarvis_sqlite.py",
    "jarvis_schedule.py", "jarvis_quick.py",
    # "open"/"adjust" any setting by voice or chat (2026-09-27): jarvis_quick.py
    # (already SHIPPED, above) is the only importer - no patch of its own.
    "jarvis_settings_registry.py",
    "jarvis_standby_schedule.py",
    "jarvis_backoff.py", "jarvis_briefing.py",
    "jarvis_reach.py",
    "jarvis_owner_check.py",
    "jarvis_manner.py",
    "jarvis_card_words.py",
    # The approval card's short summary and the "Start short" / "Always show
    # everything" choice (the owner's request of 2026-10-09, card-prefs.patch):
    # GET/POST /api/card-prefs, kept in card-prefs.json so BOTH apps read the
    # one setting, and the "what one card shows" rule they both follow.
    # Cosmetic, so no card either way.
    "jarvis_card_summary.py",
    # the tools jarvis_agent.py offers
    "jarvis_research.py", "jarvis_ui_control.py", "jarvis_android_control.py",
    "jarvis_browser_control.py", "jarvis_calendar.py", "jarvis_email.py",
    "jarvis_mail_mask.py",
    "jarvis_email_send.py",
    "jarvis_email_draft.py",
    "jarvis_inbox_tidy.py",
    "jarvis_energy.py", "jarvis_injection.py",
    "jarvis_notes.py", "jarvis_home.py",
    "jarvis_search.py",
    # the ADDRESSES of the owner's accounts - the mail server, its port and
    # mailbox, the sending server, its port and how the email is encrypted, the
    # Home Assistant address and the calendar's CalDAV address - in
    # accounts.json beside web-search.json (accounts.patch, the owner's
    # decision of 2026-10-06). ADDRESSES ONLY: the four secrets stay in
    # Windows Credential Manager and this file refuses to carry one.
    "jarvis_accounts.py",
    # Stop everything (stop-all.patch)
    "jarvis_stop_all.py",
    # "tell me when ..." - a kind of job on the one scheduler (not a tool)
    "jarvis_tellme.py",
    # focus sessions (focus.patch): a kind of job on the one scheduler
    # what is in front on this PC: the one reader focus sessions and
    # "Watch with me" share (split out of jarvis_focus.py, no patch)
    "jarvis_front.py",
    "jarvis_focus.py",
    # "What asks first" and "Lights, plugs and fans without a card" (asks-first.patch)
    "jarvis_asks_first.py",
    # "Folders Jarvis may look in" and the my_files tool (documents.patch)
    "jarvis_documents.py",
    # the words in a picture, read on this PC and marked as outside text (no patch)
    "jarvis_ocr.py",
    # screen safety (2026-09-29): secrets in a picture of the screen are painted
    # black before anything reads it (no patch)
    "jarvis_secret_rules.py", "jarvis_secrets.py", "jarvis_picture.py",
    # the pictures the owner attaches to a chat get the same treatment, before any model (no patch)
    "jarvis_chat_picture.py",
    # plug-in programs (MCP): read-only tools from programs on this PC, through more_tools
    "jarvis_mcp.py",
    # the crisis help line: the word check, the fixed US help message, the note to the model
    "jarvis_wellbeing.py",
    # the smartwatch notifications setting (watch-notifications.patch)
    "jarvis_watch_notify.py",
    # "Things you can say": the fixed list of real sentences answered without
    # the model (sayable.patch)
    "jarvis_sayable.py",
    # Backups: one locked backup file, a recovery code shown once, restore
    # with a card plus Windows Hello (backup.patch)
    "jarvis_backup.py",
    # music and video control on this PC: play/pause/next/previous and
    # "what's playing", never a card, never a model tool (media.patch)
    "jarvis_media.py",
    # news headlines in the morning briefing: RSS/Atom feed addresses the
    # owner adds, headlines only, one card per feed (news.patch)
    "jarvis_news.py",
    # data health in the preflight: do the databases open, is there disk
    # space, do the settings files parse - read-only, WARN never fix
    # (feasibility I97, data-health.patch)
    "jarvis_data_health.py",
    # "Check for tool updates": outdated Python packages, Rust crates and
    # pinned GitHub tools, report only, one card ever (tool-updates.patch)
    "jarvis_tool_updates.py",
    "jarvis_identity.py",
    # "Where this came from" and the quote check: each reading tool's own
    # result this turn, by reference; GET /api/chat/sources
    # (feasibility I42/I132, answer-sources.patch)
    "jarvis_sources.py",
    # the app builder's workspace: app projects, a separate copy per task, one
    # card showing the full diff before anything reaches the app; runs nothing
    # (docs/APP-BUILDER-DESIGN.md, milestone A - no patch, no tool yet)
    "jarvis_app_workspace.py",
    # an app inside Projects: its tasks, a task's whole change, and the ONE
    # merge card; routes installed by apps-in-projects.patch (2026-09-29,
    # docs/APPS-IN-PROJECTS-DESIGN.md - screens, merge card and a change
    # pasted in on the PC; no model tool, nothing runs)
    "jarvis_apps.py",
    # "Goals with one card per step" (the owner's "build it now",
    # 2026-09-27; goals.patch): a goal's own plan and weekly check-in.
    "jarvis_goals.py",
    # "One card, several steps" (the owner's own words, 2026-09-28;
    # plan-gate.patch): SWITCHED OFF until tools/tool_eval clears the bar.
    "jarvis_plan.py",
    # Reading phone notifications (2026-09-26 decision, built 2026-09-28;
    # phone-notifications.patch): off by default, ON is one approval card,
    # OFF is instant; never sees a notification's own text - that lives on
    # the phone.
    "jarvis_phone_notifications.py",
    # The Brain upgrades (2026-09-28, brain-reads.patch): GET
    # /api/history/search and /api/memory/fact-history, for the apps only
    # (and, since the memory dates group, /api/memory/conversation-facts)
    "jarvis_brain_reads.py",
    # "remind me next time I talk about X": a kind on the one scheduler,
    # brought up beside the question by jarvis_agent.py - no patch
    "jarvis_next_time.py",
    # "ring my phone": ONE ring_phone event the phone rings for - no patch
    "jarvis_find_phone.py",
    # "Where did I put ...?" (2026-09-28): the places the owner said,
    # answered without the model; jarvis_quick.py and jarvis_auto_learn.py
    # call it, no patch
    "jarvis_places.py",
    # The overnight tidy (2026-09-28): "Still true?" and "Which is true
    # now?" review cards only, a kind of job on the one scheduler, no patch
    "jarvis_tidy.py",
    # "Better voice" (2026-09-28): the second "hey Jarvis" detector
    # (microWakeWord); jarvis_speech.py and jarvis_voice.py call it
    "jarvis_microwake.py",
    # Today cards (2026-09-28): the owner's own words shown on the Today
    # part of both apps at a time, on chosen days - a kind of job on the one
    # scheduler, no card, no patch
    "jarvis_today.py",
    # "Photo to reminder" (2026-09-28, photo-reminder.patch): POST
    # /api/photo/scan reads a picture's dates with plain code and PROPOSES a
    # reminder; it sets nothing up itself
    "jarvis_photo_remind.py",
    # "PC help" (2026-09-28): why is my PC slow, how full is my disk, what is
    # using the graphics card - read-only, answered without the model;
    # jarvis_quick.py and jarvis_brain_reads.py (GET /api/pc/help) call it
    "jarvis_pc_help.py",
    # Tutorials and the FAQ (owner, 2026-10-05; docs/TUTORIALS-DESIGN.md): one
    # catalogue and the owner's reading progress, read by both apps -
    # GET /api/tutorials, POST /api/tutorials/progress, GET /api/faq
    "jarvis_tutorials.py",
    # "Smarter answers" (2026-09-28): the "I've done it" check at the end of
    # an answer; jarvis_agent.py calls it, and the tool test shares its
    # pattern - no patch
    "jarvis_claims.py",
    # "Bring in chats from ChatGPT, Claude, Gemini or DeepSeek" (2026-09-28,
    # history-import.patch): the importer itself, and the Brain button's
    # background run of it - every fact it finds waits for a yes
    "import_history.py",
    "jarvis_history_import.py",
    # "Widgets you describe" (2026-09-28): a small checked description (never
    # code) of what a home-screen / desktop widget shows; switched on by
    # jarvis_brain_reads.install(), no patch of its own
    "jarvis_widgets.py",
    # A conversation with an AI chatbot for the owner: the driver, the last
    # check, one card per conversation
    "jarvis_chatbot.py",
    # Projects, build steps 1 and 2: projects, life benchmarks and their
    # numbers in projects.db; GET/POST /api/projects (projects.patch)
    "jarvis_projects.py",
    # "about N to M weeks": the pure finish-time range jarvis_projects.py
    # and jarvis_goals.py read (2026-09-30, JARVIS-API section 101)
    "jarvis_forecast.py",
    # ... and its Gemini website adapter: a visible browser window,
    # stopping at any captcha or sign-in page (chatbot.patch gives
    # the gate its _RISK line)
    "jarvis_chatbot_gemini.py",
    # ...and its routes, /api/chatbot/* (chatbot-routes.patch)
    "jarvis_chatbot_routes.py",
    # ... what every chatbot website adapter shares (the visible window, the
    # typing, the host lock, every "needs the owner" page, sign-in and
    # self-check), and the other chatbot websites, each a thin site file
    # in a visible window the same way (2026-09-28, "the chatbot driver becomes
    # versatile")
    "jarvis_chatbot_web.py",
    "jarvis_chatbot_chatgpt.py",
    "jarvis_chatbot_claude.py",
    "jarvis_chatbot_copilot.py",
    "jarvis_chatbot_perplexity.py",
    "jarvis_chatbot_deepseek.py",
    "jarvis_chatbot_grok.py",
    "jarvis_chatbot_lechat.py",
    "jarvis_chatbot_metaai.py",
    # ... its API adapters (OpenAI-style Chat Completions: OpenAI, DeepSeek,
    # Mistral, xAI, OpenRouter, Groq; keys in Credential Manager) and "a
    # second AI on this PC" (another Ollama model, loopback only). No patch
    # of their own: jarvis_chatbot.py loads both.
    "jarvis_chatbot_api.py",
    # The monthly money limits and the price list, set from the PC's own app
    # (chatbot-limits.patch; docs/ACCOUNT-KEYS-DESIGN.md decisions 1 and 3):
    # GET /api/chatbot/money, on both apps since 2026-10-12 (the phone reads
    # it in Brain -> Money and time; the WRITE half is still the PC's).
    # A raise is ONE card, answered with Windows Hello on the PC or with the
    # asking phone's own fingerprint or PIN; a lowering, a removal and a price
    # correction are not.
    "jarvis_chatbot_limits.py",
    "jarvis_chatbot_local.py",
    # "Look at this" and "Watch with me": the session rules, pause rules,
    # caps, the Never look at list and the routes (screen.patch installs
    # them); jarvis_screen_win.py is the Windows half - what is in front,
    # the picture, the window's own text (2026-09-29)
    "jarvis_screen_win.py",
    "jarvis_screen.py",
    # ... and its slow picture mode for a PC with one graphics card (2026-09-29):
    # a small picture model on the processor, off by default, ON is one card
    # (screen-picture.patch adds the gate lines); the routes are jarvis_screen.py's
    "jarvis_screen_picture.py",
    # ... and a look handing its CLEANED picture to the question box: "look at
    # this" with a chart or an error message, the one key, nothing saved (the
    # owner's decision of 2026-10-07, .dsh-scratch/SCREEN-ATTACH-DESIGN.md;
    # screen-attach.patch installs its wrapper round jarvis_screen.py's own
    # route). No second cleaner: the picture handed on is
    # jarvis_picture.clean(..., want_png=True)'s own output, never the capture.
    "jarvis_screen_attach.py",
    # The headless browser, Obscura (2026-09-29): the driver (started over
    # standard input/output, --stealth always, no port, no proxy) and the
    # engine choice, the switch (off by default, ON is one card) and its
    # routes (browser-engine.patch adds the gate lines and the install block)
    "jarvis_obscura.py",
    "jarvis_browser_engine.py",
    # "Fill in the form, show me, then send it" (2026-09-30): the second card
    # of a browser plan's final click, and the picture that rides on it,
    # held in memory only (form-review.patch adds the gate lines and the
    # install block)
    "jarvis_form_review.py",
    # "Ask several and compare": several of the conversations above, ONE
    # card, ONE summary. No patch of its own: jarvis_chatbot.py loads it and
    # chatbot-routes.patch already installs the routes that reach it.
    "jarvis_chatbot_compare.py",
    # Jarvis Live (2026-09-28): the session and the rules jarvis_speech
    # follows for `source=live`; GET/POST /api/voice/live (live.patch)
    "jarvis_live.py",
    # ... and the camera's photo test, run once when the second card is in
    # (no patch: the owner runs it by hand)
    "jarvis_live_photo_test.py",
    # "Forget a time frame" (2026-09-28): a checked list, ONE card, 10
    # minutes to undo; GET/POST /api/memory/forget_range (forget-range.patch)
    "jarvis_forget_range.py",
    # "Chat with customer support for me" (2026-09-28): the support chat's
    # rules and its window on the chatbot websites' shared base. No route
    # patch: chatbot-routes.patch already installs jarvis_chatbot_routes.py,
    # which reaches it; the gate's risk lines are support-chat.patch.
    "jarvis_support.py",
    "jarvis_support_widget.py",
    # "Solve it here" (2026-09-28): a captcha or sign-in page handed to the
    # owner's phone. No patch: jarvis_chatbot_routes.py answers its routes.
    "jarvis_handoff.py",
    # how long that hand-off stays on offer (the owner's setting of
    # 2026-10-08: "Stop early" by default, or keep offering it for the full
    # 15 minutes). No patch: jarvis_chatbot_routes.py answers its one route,
    # and jarvis_handoff.py reads it.
    "jarvis_handoff_mode.py",
    # what a captcha does about its browser window (the owner's setting of
    # 2026-10-09: "1 by default with the option for 2 in the settings of
    # Jarvis": leave it exactly where it is, or bring it to the front). No
    # patch: jarvis_chatbot_routes.py answers its one route, and
    # jarvis_handoff.py reads it.
    "jarvis_handoff_front.py",
    # The first Docker integration (the owner's request of 2026-10-09,
    # docs/DOCKER-INTEGRATION-DESIGN.md): the containers on Jarvis's OWN list
    # (today SearXNG, the default search provider) and start/stop for one. It
    # deliberately cannot create or pull - a start is refused unless the pinned
    # image is already on this PC - and it never touches a container that is
    # not ours (wrong image, a port beyond loopback, or privileged). Start is
    # one card, stop is instant; docker.patch installs its routes.
    "jarvis_docker.py",
    # the sun, the moon and the weather behind the animal faces, and the
    # town list it finds a place in without going online (sky.patch)
    "jarvis_sky.py", "jarvis_sky_places.py",
    # every animal option in one place: "Keep the animal still" and the
    # behaviour switches, shared by both apps (animal.patch)
    "jarvis_animal.py",
    # pairing a phone by QR code, with a key per device (devices.patch,
    # docs/PAIRING-DESIGN.md phase 1): the check on every request's key,
    # the registry of key hashes, the pairing session and its card
    "jarvis_devices.py",
    # "Quiz me on a text" (2026-09-30; quiz.patch): questions from a pasted
    # text, marked by the local model, in memory only.
    "jarvis_quiz.py",
    # ... and the script that checks the quiz's marking against the real local
    # model (quiz_grader_cases.json is copied beside it, apply-patches.ps1 step 3b)
    "eval_quiz_grader.py",
    # "Review decks" (2026-09-30; decks.patch): kept quiz questions, spaced
    # review with py-fsrs, sealed in study.db.
    "jarvis_decks.py",
    # "Spending summaries" (2026-09-30; spending.patch): totals from a bank
    # export, and the money/date reader it and the retirement what-if share.
    "jarvis_spending.py",
    "jarvis_money_parse.py",
    # "Retirement what-if" (2026-09-30; retirement.patch): a simplified
    # what-if from numbers the owner typed, answered only as ranges.
    "jarvis_retirement.py",
    # "Activity heatmap and balance chart" (2026-09-30; progress.patch): the
    # heatmap and the owner's balance chart. Not reachable from any model.
    "jarvis_progress.py",
    # "Which card draws the pictures" (2026-10-10; picture-card.patch): the
    # three ways of running a picture-maker beside the everyday chat, each its
    # own switch, all off until the owner turns one on. It draws nothing
    # itself - asking for a picture is jarvis_pictures.py's route - and it is
    # not reachable from any model. Not a tool, no card: it only moves which
    # card a local program runs on and unloads/reloads the owner's own chat.
    "jarvis_picture_card.py",
    # "Topic controls" (2026-09-30; topics.patch): a mode per topic (learn /
    # use), the sorting, the one card. The search filter is in the rebuilt
    # jarvis_memory.py; test_topics_leaks.py lists every reader of facts.
    "jarvis_topics.py",
    # "Referee suggestions" (2026-09-30; referee.patch): the propose-only
    # "This looks done - tick it?" card. No route, no tool, no model.
    "jarvis_referee.py",
    # "Suggest tags overnight" (2026-09-30; tag-suggest.patch): cards only.
    "jarvis_tag_suggest.py",
    # "Quiz me on a YouTube video" (2026-09-30; youtube.patch): one card per
    # link, caption text only, quizzed on as outside text.
    "jarvis_youtube.py",
    # "Grade this better" (2026-09-30; quiz-cloud.patch): one card per request,
    # the whole message shown, the cheapest set-up cloud service; never private.
    "jarvis_quiz_cloud.py",
    # "Read one web page out loud" (2026-10-05; readpage.patch, JARVIS-API
    # section 115): the model's read_web_page tool - ONE card per address, then
    # one plain GET and the words a reader would see, handed back as outside
    # text; no new dependency.
    "jarvis_readpage.py",
    # "Show or hide menus" (2026-09-30): the list of menus, the groups, the
    # never-hideable list and the words; jarvis_quick.py calls it (no patch, no route).
    "jarvis_menus.py",
    # "open Notion", "open settings", "open Jarvis settings" (2026-10-10, the
    # owner's request): which app, Windows panel or Jarvis Settings section the
    # owner's own words name. jarvis_quick.py calls it. No patch, no route, NO
    # card and no model tool - the same shape as jarvis_media.py.
    "jarvis_open.py",
    # Per-model thinking levels (2026-10-01, Section 5.5): setting per model,
    # capabilities check, voice fast override, plain words (no card).
    "jarvis_thinking.py",
    # The page this server hands to a browser at `GET /` (2026-10-07).
    #
    # Found while debugging a desktop app that had NEVER connected: the backend
    # answered `GET /` with 500 "jarvis_hud.html is missing from this folder",
    # because the file was in the published base but in neither SHIPPED list and
    # in no patch - so the patcher never copied it. The app lost the connection
    # menu and fell back to its demo data, which reads as "Jarvis is not
    # connected" however healthy the backend is.
    #
    # This is not a module: it is a resource the shipped `jarvis_hud.py` reads
    # from `HERE` at request time, so it has to sit beside the server. Adding it
    # here is all that is needed - `test_shipped_modules.py` requires a shipped
    # entry to be a file in `backend/` as well as in the base, which is why it is
    # copied there too.
    "jarvis_hud.html",
    # --- the five the base already carried but SHIPPED did not list (2026-10-07) ---
    # Found by comparing a working backend against this list: all five were
    # already IN jarvis-backend/, and a SHIPPED module imports each of them, but
    # none was in SHIPPED and no patch delivered any of them. So a backend
    # assembled from the published base imported a shipped module which imported
    # a file this repository never handed over - an import error for anyone
    # building from scratch, and their tests could not run in CI either.
    # `docs/audit-2026-10-07/` and .dsh-scratch/UNSHIPPED-MODULES-REPORT.md carry
    # the evidence. Listing them changes nothing about what each does; it makes
    # the delivery match what the code already assumes.
    #
    # The one place that decides whether to interrupt the owner: nothing
    # unsolicited reaches a client directly, it holds an attention budget and
    # drains the overflow into one daily digest. jarvis_hud.py and jarvis_watch.py
    # import it.
    "jarvis_arbiter.py",
    # A tamper-evident record of what the assistant did, and a "why did you do
    # that" view over it: append-only, hashing metadata only so the integrity
    # feature and forgetting do not cancel each other out. jarvis_hud.py imports it.
    "jarvis_ledger.py",
    # "Tell me what's new on GitHub for the things I care about": pull, never
    # push, results handed over when asked, and a repo page treated as text from
    # a stranger. jarvis_hud.py and jarvis_settings_registry.py import it.
    "jarvis_watch.py",
    # A smoke test for a model swap, and deliberately not an eval suite: the
    # header explains why a judge-scored corpus from real transcripts was
    # rejected (noise floor, and a second copy of the owner's life that
    # forgetting cannot reach). jarvis_models.py imports it.
    "jarvis_tripwire.py",
    # Makes a malformed tool call structurally impossible: builds the JSON
    # Schema Ollama's `format` field constrains decoding to, instead of retrying
    # until bad JSON parses. jarvis_extract.py imports it.
    "jarvis_structured.py",
    # These two are pulled in by the five above (jarvis_arbiter and jarvis_watch
    # import jarvis_jobs; jarvis_watch imports jarvis_content_risk). Adding them
    # is not optional: test_shipped_modules.py fails a shipped file that imports
    # an unshipped module, which is what caught the first five in the first place.
    #
    # Long Fuse: work that outlives the conversation.
    "jarvis_jobs.py",
    # The limits and frequencies the owner can change: one table, one route.
    "jarvis_limits.py",
    # One pipeline for text that arrived from outside.
    "jarvis_content_risk.py",
    # The job list (2026-10-08, tasks.patch, JARVIS-API section 118): work that
    # outlives one chat turn - a task is a named job with steps, each step still
    # goes through the one gate, and the list remembers where it got to through a
    # restart. Copied in shape from OpenMuse's task worker
    # (docs/COMPETITORS-OPENMUSE-2026-10-08.md, including a correction: the report
    # first called the address check a gap, and Jarvis already had it).
    # A lease so a crashed job is picked up again and never run twice at once, a
    # checkpoint after every step, `outcome_unknown` for an interrupted send, an
    # idempotency key so one request makes one action, and a card whose decision
    # must carry the hash of the words that were shown. Local SQLite only,
    # standard library only, no network, no child process, approves nothing.
    "jarvis_tasks.py",
    # The prompt coach (2026-10-08, prompt-coach.patch, JARVIS-API section
    # 119): checks ONE prompt the owner is about to send and returns what is
    # missing - a score, up to four gaps and a rewritten version. Advice only:
    # it sends nothing, runs no tool, raises no card, keeps nothing, and the
    # address it sends to is checked with jarvis_auto_learn.check_local_model
    # before the request is built. Off until the owner turns it on.
    "jarvis_prompt_coach.py",
    # This PC's own notification choices - which of its toasts fire and the
    # quiet hours around them - in the OWNER'S SETTINGS FILE instead of one
    # webview's localStorage, so the phone can change them too (the owner's
    # decision of 2026-10-08). jarvis_limits.py rides the same seven values as
    # rows and calls this module's check_time for the two clock times, which is
    # why it is shipped whole. No patch, no route of its own.
    "jarvis_notify_prefs.py",
    # Drop-in modules (feat/plug-and-play-modules): the loader that replaces a
    # feature's one startup patch by calling each module's own install() from
    # a folder. plugins/loader/plugin-loader.patch adds the single call;
    # plugins/registry.json says which features fit and why the rest do not.
    # Standard library only, no network, no child process, writes nothing.
    "jarvis_plugins.py",
    # The owner's uncensored opt-ins, both halves (2026-10-10, Decision 5):
    # ONE clearly-labelled opt-in for fiction and role-play that is never the
    # everyday assistant and never a default, AND the abliterated models
    # already on disk offered as opt-in choices with no new download, each
    # carrying the measured cost on its label. Two switches, off on a machine
    # that has never run it, in their own JSON beside hardware-choice.json.
    # Uses Ollama's own import of a local .gguf path and the existing switch;
    # no route, no tool, and it never writes jarvis-framework.toml.
    "jarvis_optin_models.py",
    # What this machine can hold, and what may be offered on it (2026-10-10,
    # the owner's Decision 6): free space on the drive models live on, card
    # count and video memory, then the Lean / Comfortable / Generous tiers with
    # their size on disk, what each is for, which card it uses and what it
    # leaves free. may_download() is the one gate every download passes: never
    # a silent download, and never one leaving under MIN_FREE_AFTER_DOWNLOAD -
    # the night C: hit 5.7 GB free and every build broke. Reads no network,
    # starts nothing, downloads nothing; the work setups use it rather than
    # building a second chooser.
    "jarvis_storage.py",
    # "Ask for a picture, and keep it" (2026-10-11, the owner's decision of
    # 2026-09-27; pictures.patch, docs/JARVIS-API.md section 129). A prompt the
    # owner typed, drawn by a program ON THIS PC (ComfyUI or
    # stable-diffusion.cpp - a setting with named values, never guessed at),
    # saved in a folder on this PC with a sidecar holding the prompt, the seed,
    # the model and the settings. Nothing leaves the PC and no route sends a
    # picture anywhere, so making one needs NO approval card - the same shape as
    # a timer or a note. The switch ("Making pictures") is OFF by default, and
    # with nothing configured the owner gets ONE plain sentence naming both
    # programs. Not a tool in jarvis_agent.py.
    "jarvis_pictures.py",
    # The 30B coder: both cards, with Jarvis paused (2026-10-11, the owner asked
    # for it by name). One model that needs BOTH cards - so it is an OPT-IN mode,
    # off by default, that pauses the two live lanes (proved from /api/ps), loads
    # at the largest zero-spill context measured (28,672), announces the pause
    # BEFORE it starts, and puts both lanes back exactly as they were, proved
    # again. big-coder.patch wires its two routes; nothing downloads, every
    # call is loopback, and turning it on is one approval card.
    "jarvis_big_coder.py",
    # "Start the local model" (2026-10-13, the owner's decision; model-lanes.patch):
    # the button on the standing "the local model isn't running" line both apps
    # draw. It runs HIS OWN Windows logon task - found on this PC with
    # `schtasks`, matched by the stable half of its name - and then watches that
    # lane's /api/tags until it answers, so "starting" is never reported as
    # "up". One lane, the one Jarvis talks to (OLLAMA_URL's port), never both.
    # No approval card: his own logon task already runs this command unattended.
    "jarvis_model_lanes.py",
    # Action receipts and one-click undo (2026-10-14; the owner's brief,
    # borrowed from BasedHardware/omi). Every action that CHANGES something
    # leaves a receipt saying what changed, with one button to put it back:
    # `action_receipts` in its own receipts.db (WAL, a connection per call -
    # never a table in approvals.db, which the gate must stay the only writer
    # of). record() is called BEFORE the change and never raises into it, and
    # never writes an unscrubbed word (no scrubber, nothing written). undo()
    # reverses exactly once - the claim is one conditional UPDATE, so a second
    # call refuses with "this was already undone" - and falls back to the
    # before snapshot when the in-memory callable is gone, saying which path
    # it took. Its two routes come from install(), which the drop-in folder
    # plugins\ready\receipts calls: no patch of its own. Undo is a mutating
    # action, so it raises ONE card (undo_action, tier ask) and a denied card
    # changes nothing. jarvis_goals.py records a receipt for every step tick.
    "jarvis_receipts.py",
    "jarvis_auto_router.py",
    # The skill library's other doors (2026-10-15): a reference manual read
    # only when it is asked for, leading /skill and /bundle chains that stop at
    # the first name they do not know, a trusted project's own skills at
    # <folder>/.jarvis/skills with anything that fails the scan quarantined,
    # and /learn - a four-section distillation scrubbed through jarvis_scrub,
    # writing NOTHING when the scrubber is absent. It re-implements none of
    # jarvis_skills.py: the index, the body, the list, the removal and
    # write_skill() are all CALLED, and every save goes through write_skill()
    # so its scanner and its modify_own_code card run where they always have.
    # Its four routes come from its own install(), called by the
    # plugins\ready\skill-hub drop-in folder: no patch of its own.
    "jarvis_skill_hub.py",
    # The blind credential vault (2026-10-14; the owner's brief,
    # feat/blind-credential-vault): a secret is stored in Windows Credential
    # Manager - the SAME store and the same ctypes calls jarvis_token_store
    # already uses, never a second mechanism - and every other part of the
    # system carries an opaque handle, `{{vault:github}}`, never the value.
    # `resolve()` puts the real value in exactly once, at the point of use, and
    # only for the host the value is bound to; `redact()` puts anything that
    # comes back through jarvis_scrub. No patch and no core change:
    # `plugins/ready/vault/plugin.json` names this module and the loader calls
    # its install(). `install()` wraps the Handler for GET /api/vault/handles
    # (names and last use - never a value, never a prefix of one) and
    # POST /api/vault/put (ONE approval card at tier ask; a denied, timed-out
    # or refused card stores nothing). The names, their host binding and their
    # times live in vault.json; NO VALUE IS EVER IN THAT FILE.
    "jarvis_vault.py",
    # The schema a skill's `format` may carry, and the guard around it
    # (2026-10-15, Upgrade 3A). A skill's own format is validated against a
    # declared schema BEFORE anything uses it, so a malformed one is refused
    # in plain words rather than acted on. It validates only: no route, no
    # card, no file written, nothing downloaded. Standard library only, and
    # no patch. It has NO CALLER YET, and docs/JARVIS-API.md says the same;
    # its own docstring records why - putting a tool's schema in `format` on
    # a call that also offers `tools` corrupted the arguments on the live
    # Ollama, so the schema belongs on a call with no `tools` at all.
    "jarvis_tool_schema.py",
    # One bounded, revocable lease over a run of steps (the task-lease work
    # order, Slice 1): what a lease is, who may open one - `jarvis_gate.check()`
    # at tier "ask", failing CLOSED when the gate cannot be reached - and the
    # deterministic check that answers "is this step inside it?". A lease names
    # one surface, the sites or the (pid, hwnd) windows it may touch, the
    # actions it may take, a TTL (300 seconds by default, 900 hard, longer
    # requests CLAMPED) and a step budget; and it refuses with `step_up_ask`
    # on Jarvis's own window or HUD page, a password field, a card or file
    # control, a high-consequence verb on the target, the TTL, the budget or
    # revocation. Leases live in memory and die with the process: no route, no
    # patch, no file, no database. It IS wired on the consumer side -
    # `jarvis_browser_control.py` imports it in its one integration point, and
    # `run_steps()` checks each step against it when a caller names a lease -
    # but no production caller opens one yet: `create()` is called only from
    # `test_task_lease.py`. Standard library only, and `jarvis_gate` is
    # imported lazily inside one function.
    "jarvis_task_lease.py",
    # The Ollama compatibility probe (2026-10-15, self-improvement phase 1).
    # One read-only POST /api/show, at start-up and on every model change,
    # sorted into exactly three outcomes: understood; a capability name Jarvis
    # has never heard of (logged ONCE, never an error, because an extra name
    # cannot take tools or vision away); or a capability Jarvis uses that the
    # model's own answer plainly shows it has while the capabilities list does
    # not name it, reported flatly as Jarvis about to under-use the model.
    # Ollama not answering is none of the three - it is no verdict at all,
    # logged once, so it can never read as understood. No version is read or
    # compared anywhere (jarvis_hardware.py:912). Writes nothing, loads
    # nothing, opens no route, and has no call site yet.
    "jarvis_ollama_contract.py",
    # Verify a GGUF by its LISTING, before any download (2026-10-15, 3B
    # piece 2). It answers four questions from the repo's file list alone:
    # what is in it by name and size, with the vision projector reported
    # SEPARATELY from the model GGUF; the exact quant labels the repo uses,
    # verbatim; the KV cache a hybrid model really grows, counted only over
    # the layers that grow one; and what is missing. ONE HTTPS GET to
    # huggingface.co/api/models/<owner>/<name>/tree/main?recursive=true - the
    # repo id is the whole request, with no token, cookie, key, local file
    # name or chat word in it, and no weight is ever fetched. It writes
    # nothing at all: no file, no cache, no state, no audit row, no timer and
    # no background job. Standard library only, no patch, no call site yet.
    "jarvis_hf_inspect.py",
    # Read-only self-diagnosis, and drafting with no way to apply it
    # (2026-10-16, self-improvement phases 3 and 4). Retrieval over the
    # program's own text files selects the lines that answer a question; the
    # local model explains them, and every answer either cites a real
    # file:line - re-read from disk - or says plainly that it could not
    # establish it, so a paraphrase can never be reported as a fact. `draft()`
    # produces a code diff and a separate new-file test diff for the OWNER to
    # apply by hand, and refuses any diff touching jarvis_gate.py, a tier or
    # risk table, a test file or the three SHIPPED lists. It applies nothing,
    # writes nothing, opens no route, reaches no network but the loopback
    # model, and fails closed when jarvis_scrub is absent. Standard library
    # only.
    "jarvis_self_improve.py",
    # A Notion export, tidied into an Obsidian vault (2026-10-16): ids off the
    # file and folder names with collisions decided deterministically, page
    # properties lifted into YAML frontmatter (notion_id kept, so a second
    # import is idempotent), each exported CSV database merged into its rows'
    # notes with an index note of [[wikilinks]] and a .base beside it, HTML
    # turned into Markdown (callouts, toggles, checklists, fenced code with
    # its language, pipe tables), Notion's relative links rewritten through
    # the cleaned-name map, and pictures and documents moved into the vault's
    # attachments folder. Plan -> describe -> gate -> run, one atomic move,
    # and one reversible entry in jarvis_receipts so Undo takes it back off.
    # It writes only inside the vault it is pointed at. It does NOT unpack a
    # zip with a guard of its own: it imports jarvis_documents.safe_parts,
    # .protected and .ImportRefused, because that module already refuses
    # zip-slip, caps the size, unpacks Part-N.zip and moves the result into
    # place in one step - and a second extractor is the duplicate feature
    # this project's audits look for. Standard library only, and no patch:
    # plugins/ready/notion-obsidian calls its install().
    "jarvis_notion_obsidian.py",
)


def _same_text(a: Path, b: Path) -> bool:
    # Line endings do not count: a Windows clone may hold CRLF copies of
    # files that are LF here, and Python reads both the same.
    return (a.read_bytes().replace(b"\r\n", b"\n")
            == b.read_bytes().replace(b"\r\n", b"\n"))


def require_shipped(*names: str) -> None:
    """Stop the suite, plainly, if the backend's copy of a shipped module is
    missing or is not the one in this repository.

    Only when JARVIS_BACKEND is set - that is, when the suite is being run
    against a real install. Without this, the suite imported THIS folder's
    copy whenever the backend had none (every suite also puts this folder on
    sys.path), passed, and said nothing about the copy the backend actually
    runs. In the dev container BACKEND is this folder, so there is nothing
    to compare and nothing happens.
    """
    if not os.environ.get("JARVIS_BACKEND") or BACKEND == _HERE:
        return
    problems = []
    for n in names:
        # "rebuilt/jarvis_memory.py" is this repository's path; on the PC the
        # file sits beside jarvis_hud.py under its own name.
        leaf = n.rsplit("/", 1)[-1]
        theirs, ours = BACKEND / leaf, _HERE / n
        shown = "backend\\" + n.replace("/", "\\")
        if not theirs.is_file():
            problems.append(f"{leaf} is not in {BACKEND}, so the feature it carries "
                            f"is switched off there. Copy {shown} into the "
                            f"backend folder (apply-patches.ps1 does this for you).")
        elif ours.is_file() and not _same_text(theirs, ours):
            problems.append(f"{leaf} in {BACKEND} is not the copy in this repository "
                            f"(an older one, most likely). Copy {shown} into "
                            f"the backend folder (apply-patches.ps1 does this for you).")
    if problems:
        for p in problems:
            print("FAIL  " + p)
        print("\nNot run: this suite would have tested this repository's copy "
              "instead of the one your backend uses.")
        sys.exit(1)


def require_rebuilt(*modules: str) -> None:
    """Stop the suite, plainly, if a module this repository ships WHOLE
    (`backend/rebuilt/`) cannot be imported in this run.

    THE GUARD FOR THE LINE AT THE TOP OF THIS FILE. `_REBUILT` is put on
    sys.path above, so a suite that needs one of the ten shipped-whole modules
    imports it in every run mode. If that line is ever lost, the suite used to
    die at the next `import jarvis_memory` with a bare traceback and no checks
    at all; five suites failed exactly that way in a clone of this repository
    (`ModuleNotFoundError: No module named 'jarvis_memory'`, measured
    2026-10-10). This says so in one named line instead, and exits.

    Sibling of `require_shipped` above, with the same shape for the same
    reason: a suite that cannot import the module under test must say that,
    not look like nine assertion failures. Call it BEFORE the import:

        from _where import require_rebuilt
        require_rebuilt("jarvis_memory")
        import jarvis_memory as M

    When JARVIS_BACKEND is set, `require_shipped` is still the check that the
    backend's own copy is the one being used; this only asks whether the
    module can be imported at all.
    """
    problems = []
    for name in modules:
        try:
            __import__(name)
        except Exception as exc:                 # noqa: BLE001 - report, never raise
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
    if problems:
        print("FAIL  this run cannot import the modules this repository ships "
              "whole (backend/rebuilt/):")
        for p in problems:
            print("      " + p)
        print(f"      _where.py looks in {_REBUILT} and puts it on sys.path; "
              f"BACKEND is {BACKEND}. {explain()}")
        print("\nNot run: this suite would have tested something other than the "
              "modules it is about.")
        sys.exit(1)


# ===== the published base ==================================================
#
# THIS IS jarvis-backend/'s COPY, AND IT IS NOT THIS REPOSITORY'S. Everything
# above this line is backend/_where.py, word for word. These last lines are the
# whole of the difference, and backend/test_base_regeneration.py fails if the
# two files differ by anything else.
#
# It is in the base at all because import_history.py - which the base carries,
# and which must run from a cloned folder with no repository around it - imports
# BACKEND and explain from this file. Nothing else in jarvis-backend/ imports
# it: the SHIPPED tuple above and require_shipped() below belong to the
# repository's own test runner, and the base carries none of those tests.
#
# It was kept by hand until 2026-10-10, and by then it had gone stale: 77 lines
# of SHIPPED entries this repository's copy had gained and this one had not,
# with nothing to notice. tools/gen_base_from_backend.py now DERIVES this file
# from backend/_where.py, so re-taking the base refreshes it too, and
# backend/test_base_regeneration.py is what says the two have not drifted apart
# again.
