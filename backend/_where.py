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
import os
import sys
from pathlib import Path

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

# Prepended, not appended: if a stale copy of a module is ever left in this
# folder, the one in BACKEND is the one under test and must win.
_b = str(BACKEND)
if _b in sys.path:
    sys.path.remove(_b)
sys.path.insert(0, _b)


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
    "jarvis_voices.py", "jarvis_f5_worker.py", "jarvis_bakeoff.py",
    "jarvis_learning_switch.py",
    "jarvis_voicebank.py",
    "jarvis_voice_flow.py",
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
    "jarvis_scrub.py",
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
    # the tools jarvis_agent.py offers
    "jarvis_research.py", "jarvis_ui_control.py", "jarvis_android_control.py",
    "jarvis_browser_control.py", "jarvis_calendar.py", "jarvis_email.py",
    "jarvis_mail_mask.py",
    "jarvis_email_send.py",
    "jarvis_email_draft.py",
    "jarvis_notes.py", "jarvis_home.py",
    "jarvis_search.py",
    # Stop everything (stop-all.patch)
    "jarvis_stop_all.py",
    # "tell me when ..." - a kind of job on the one scheduler (not a tool)
    "jarvis_tellme.py",
    # focus sessions (focus.patch): a kind of job on the one scheduler
    "jarvis_focus.py",
    # "What asks first" and "Lights, plugs and fans without a card" (asks-first.patch)
    "jarvis_asks_first.py",
    # "Folders Jarvis may look in" and the my_files tool (documents.patch)
    "jarvis_documents.py",
    # the words in a picture, read on this PC and marked as outside text (no patch)
    "jarvis_ocr.py",
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
    # "Smarter answers" (2026-09-28): the "I've done it" check at the end of
    # an answer; jarvis_agent.py calls it, and the tool test shares its
    # pattern - no patch
    "jarvis_claims.py",
    # "Bring in chats from ChatGPT, Claude or Gemini" (2026-09-28,
    # history-import.patch): the importer itself, and the Brain button's
    # background run of it - every fact it finds waits for a yes
    "import_history.py",
    "jarvis_history_import.py",
    # "Widgets you describe" (2026-09-28): a small checked description (never
    # code) of what a home-screen / desktop widget shows; switched on by
    # jarvis_brain_reads.install(), no patch of its own
    "jarvis_widgets.py",
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
