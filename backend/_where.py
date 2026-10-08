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
    "jarvis_voices.py", "jarvis_f5_worker.py",
    # which Kokoro voice pack is installed, its voices by name, the pinned
    # v1.0 download: jarvis_voices.py imports it (no patch)
    "jarvis_kokoro.py",
    "jarvis_bakeoff.py",
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
    # GET/POST /api/chatbot/money, PC only. A raise is ONE card plus Windows
    # Hello; a lowering, a removal and a price correction are not.
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
    # Per-model thinking levels (2026-10-01, Section 5.5): setting per model,
    # capabilities check, voice fast override, plain words (no card).
    "jarvis_thinking.py",
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
    # One pipeline for text that arrived from outside.
    "jarvis_content_risk.py",
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
