<#
.SYNOPSIS
  Bring your backend folder fully up to date: patches, the modules this
  repository ships, the settings file if you have none, Python packages -
  then run the tests.

.DESCRIPTION
  backend/README.md used to say "git apply this, then this, ... and so on, in
  table order" - twenty patches, in a required order, with a backup step you
  had to remember. That is a bad thing to ask of anyone, and the failure mode
  is the worst kind: patch eleven fails and you are left half-applied, with no
  record of which half.

  This does the whole thing, and it will not leave you half-applied:

    1. DRY-RUNS the whole list of patches first, on a copy. If it would fail,
       it stops and changes nothing at all.
    2. Backs up every file that is about to be touched, into a timestamped
       folder (_jarvis-backup-<date> inside the backend folder), then applies
       the patches in order.
    3. Copies in every module this repository ships whole - the ten rebuilt
       ones (backend/rebuilt/), the tools jarvis_agent.py offers, and the new
       modules the patches call - backing up any older copy first.
    4. Puts jarvis-framework.toml (the settings file) in place ONLY if there
       is none yet. Yours is never overwritten; if it differs from this
       repository's copy, the differences are listed for you to decide on.
    5. Installs the Python packages in backend/requirements.txt into the real
       Python (not the Microsoft Store shortcut that is also called `python`).
    6. Runs the test suites and prints a summary.

  Safe to run again. Four starting points work:
    - nothing applied yet: the whole list goes on;
    - everything applied already: it says so and changes nothing;
    - SOME applied, by an earlier run with an older list: those are taken
      off, newest first, and the whole list is put back on in the current
      order - rehearsed on a copy first like everything else;
    - an OLDER VERSION of a patch applied, from before that patch was edited
      here: it is recognised (backend/patch-history keeps every earlier
      committed version), taken off, and the current version put on in its
      place - rehearsed on a copy first, and named in what the script prints.

.PARAMETER BackendPath
  The folder holding jarvis_hud.py. Defaults to the path in backend/README.md.

.PARAMETER Revert
  Undo: take every applied patch back off, newest first.

.PARAMETER SkipTests
  Apply, but do not run the test suites afterwards.

.PARAMETER FixLineEndings
  Your backend's own .py files (the ones the patches change) have Windows
  line endings (CRLF), and the patches are written with LF, so nearly every
  patch reports "not onto the files as they are". With this switch, each such
  file is first copied into _jarvis-backup-<date>-endings inside the backend
  folder, then rewritten with LF endings - nothing else about it changes, and
  Python reads both. The rewrite happens only AFTER the rehearsal (on a copy
  that is converted the same way) has succeeded and every other check has
  passed, so a run that stops early has not touched your files. Without the
  switch nothing of yours is rewritten and the script only says which files
  are affected and the command to run.

.PARAMETER Force
  By default the script refuses to change anything while a Python program that
  looks like Jarvis (its command line names the backend folder or jarvis_hud.py)
  is running, because a running Jarvis has the files open and would go on
  running the old code. Close Jarvis and run again; -Force skips that check.

.PARAMETER SkipPackages
  Do not run pip. The packages in backend/requirements.txt are then yours to
  install; the features that need them stay off until you do.

.PARAMETER SkipMissing
  Leave out any patch that needs a backend file which is not there, and apply
  the rest. A PARTIAL install: the features those patches carry will not be
  present. Only use it once you have looked for the missing files and they
  really are gone - the script prints the command to search for them.

.EXAMPLE
  From the folder this repository is cloned into. -ExecutionPolicy Bypass
  lets Windows run a script file for this one command, without changing any
  setting:

  powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath "D:\jarvis"
  powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -Revert
#>

[CmdletBinding()]
param(
    [string] $BackendPath = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program",
    [switch] $Revert,
    [switch] $SkipTests,
    [switch] $SkipMissing,
    [switch] $SkipPackages,
    [switch] $FixLineEndings,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

# The order is the one in backend/README.md, and it is not arbitrary.
# memory-safety must land before anything makes the extractor run, or the
# first accepted proposal retires a roughly-matching unrelated fact,
# permanently. bitemporal edits code memory-safety wrote and a route
# memory-pane added, so it is also a TEXTUAL dependency and must go last.
$PATCHES = @(
    'memory-safety.patch'
    'events-pump.patch'
    'appearance.patch'
    'gate-push.patch'
    'skill-notes.patch'
    'documents-honesty.patch'
    'memory-prefix.patch'
    'extraction-wiring.patch'
    'voice-503.patch'
    'degrade-filter.patch'
    'vram-estimate.patch'
    'memory-pane.patch'
    'token-file.patch'
    'bitemporal.patch'
    'embedding-guard.patch'
    'gpu-offload.patch'
    'gate-outcome.patch'
    'no-auto-approve.patch'
    'memory-noise.patch'
    # After memory-noise: its context is that patch's dedupe rewrite (the
    # 'pending','rejected' query) and memory-safety's queue_full() field.
    'decide-once.patch'
    'event-allowlist.patch'
    # Last: it rewrites `pending()` and `_push` in jarvis_gate.py, which
    # gate-outcome and no-auto-approve have already edited, and the
    # doorbell copy in jarvis_events.py that event-allowlist wrote. Its
    # context lines are their output, so it cannot go earlier.
    'approval-notice.patch'
    # Textually independent of everything above - it only ADDS new entries
    # to two dictionaries in jarvis_gate.py, touching no line any other
    # patch here touches. Listed last for readability, not because order
    # matters for this one.
    'ui-control-wiring.patch'
    # The tool->action gaps (2026-10-03). Eleven names jarvis_agent.py's
    # TOOLS have always put to jarvis_gate had no _TOOL_ACTIONS entry, so
    # action_for_tool() fell through to "unclassified_tool" and every call
    # asked. It only ADDS entries, at the very END of the _TOOL_ACTIONS dict
    # (after "persona_write"), so it touches no line any other patch edits -
    # not the entries ui-control-wiring, plan-gate, email-send, draft-email
    # or inbox-tidy add near the top of that dict, and not the closing brace
    # the _RANK and _NO_RULE_FROM_DENIAL blocks further down are built on.
    # It still goes right after ui-control-wiring because that is the last
    # patch in this list that puts lines into _TOOL_ACTIONS above this one's
    # own region - the table this patch completes.
    'gate-entries.patch'
    # Also independent - touches jarvis_hud.py's /api/chat, but a different
    # few lines than degrade-filter or any other patch that lands there.
    'ollama-direct.patch'
    # Textually independent of ollama-direct too, but listed right after it:
    # a tool-enabled local turn only makes sense once the local lane is
    # actually reaching Ollama.
    'tool-calling-wiring.patch'
    # Its context lines are token-file's output (the token banner and the
    # line above HUD_TOKEN), which nothing after token-file touches. Last so
    # a backend that already has everything above takes only this.
    'loopback-too.patch'
    # After all of these. Its context lines are other patches' output:
    # memory-safety's _accept() and the end of propose() in jarvis_extract.py
    # (with memory-noise and decide-once already above it), memory-pane's
    # GET and POST memory routes, and tool-calling-wiring's `if use_tools:`
    # split in /api/chat. So it cannot go earlier than tool-calling-wiring.
    'feedback.patch'
    # After feedback.patch, and it MUST stay after it: feedback's POST hunk
    # ends on the memory-route tuple line ("/api/memory/learning",
    # "/api/memory/sleep_time"):) that this patch rewrites to add keep_both,
    # so the other way round feedback fails to apply (checked with git apply
    # on a rebuilt jarvis_hud.py). Its jarvis_extract.py context is the output of
    # memory-safety, memory-noise and decide-once (the dedupe lines, the
    # full-queue counter, setup_status's dropped_full block and the file's
    # last function), and its jarvis_hud.py context is the learner and call
    # site extraction-wiring wrote and the memory block memory-pane wrote.
    # It needs backend\jarvis_intake.py copied into the backend folder too;
    # without it every hook falls back to the old behaviour.
    'memory-intake.patch'
    # Needs appearance.patch: both of its hunks sit inside lines appearance
    # wrote (the /api/visual-spec entry in the GET list, and the end of the
    # /api/visual-spec branch). Nothing else here touches those lines. It
    # also needs jarvis_skill_discovery.py copied beside jarvis_hud.py, or
    # the route answers "available": false - it never fails the request.
    'skill-suggest.patch'
    # Its context lines are documents-honesty's output (the three
    # _has_table(DOCS_DB, "documents") checks and the _has_table function),
    # so it must come after that one. Needs jarvis_owned_tables.py copied
    # into the backend folder; without it the documents are simply never
    # read, which is the safe side.
    'documents-owned.patch'
    # Its context lines are gpu-offload's output (the "offload" line in
    # _models_view) and tool-calling-wiring's (both answer branches of
    # /api/chat), so it must come after both. Needs jarvis_speed.py copied
    # into the backend folder; without it nothing is timed and every
    # answer works exactly as before.
    'speed-record.patch'
    # "Train my voice". Its context lines are voice-503's output (the end of
    # the /api/voice/say branch) and appearance's (the "/api/appearance" line
    # in the models tuple right after it), which nothing later touches - so
    # it only has to come after those two; last is simplest. Needs
    # jarvis_voice_enroll.py copied in; without it the new route answers 503
    # "voice training is not installed on this PC".
    'voice-enroll.patch'
    # Its context is ollama-direct's `_completions_url(lane),` line inside
    # `_open`, so it must come after that one; nothing else touches `_open`.
    # A cloud lane then gets the newest question alone, never the
    # conversation the clients now send with it.
    'cloud-one-turn.patch'
    # --- task controls, notes, power (2026-09-23) ---------------------------
    # Pause/Resume/Stop, a note for what runs next, and a note on one approval
    # card. Its context lines are feedback's and memory-intake's output (the
    # end of the /api/feedback/mark block, the memory-route tuple) and
    # extraction-wiring's (_activity), so it goes after all of them. Needs
    # jarvis_task_control.py copied in; without it the routes answer 503.
    'task-control.patch'
    # Logseq/Joplin notes that are really filed. Its jarvis_hud.py context is
    # task-control's output (it sits right after those routes), and its
    # jarvis_gate.py context is ui-control-wiring's. Needs
    # jarvis_note_capture.py copied in; without it the route answers 503.
    'note-capture.patch'
    # Active / Quiet / Standby from either app. Its context is note-capture's
    # output (it sits right after that route). Needs jarvis_power_switch.py
    # copied in; without it the route answers 503.
    'power-mode.patch'
    # --- end task controls ---------------------------------------------------
    # How long each approval card has left (`expires_in` on /api/pending).
    # Its context is approval-notice's output in jarvis_gate.pending() (the
    # `d["notice"]` line); ui-control-wiring and note-capture only add lines
    # above it, so anywhere after approval-notice works - last is simplest.
    'approval-expiry.patch'
    # Refuses every spelling of "every network interface" ("0", "0x0", ...)
    # as the bind address. Its context is loopback-too's output (the
    # _loopback_companion function and its call in main()), so it goes
    # after that one; nothing else touches those lines.
    'bind-wildcard.patch'
    # Every local chat turn through jarvis_agent: streamed once, the right
    # Content-Type, keepalives while an approval card waits, thinking off,
    # plain error messages. Its context is tool-calling-wiring's and
    # speed-record's lines (the tool branch) and ollama-direct's (the 503
    # message), so it goes after all three; last is simplest. Needs the
    # jarvis_agent.py from the same commit - an older one has no
    # content_type(), and the patched code then falls back to the plain
    # relay exactly as before.
    'chat-stream.patch'
    # Smart Turn ("finished, or only paused?"): adds POST /api/voice/turn
    # right after voice-enroll's route, and its context is voice-enroll's
    # last lines, so it comes after that one; nothing else touches them.
    # Needs jarvis_turn.py copied in; without it the route answers 503.
    'voice-turn.patch'
    # One voice print per microphone: hands `?mic=phone|desktop` from
    # /api/voice/utterance to jarvis_speech.hear(). Its context is
    # voice-503's lines in that route, which nothing later touches. Passes
    # it only to a jarvis_speech.py that says TAKES_MIC.
    'voice-mic.patch'
    # The pairing token moves out of the plain file token-file.patch wrote,
    # into Windows Credential Manager (CLAUDE.md rule 3). Its context is
    # token-file's _resolve_token and banner, with loopback-too's and
    # bind-wildcard's lines around them, so it goes after all three; nothing
    # else touches those lines. Needs jarvis_token_store.py copied in; without
    # it the backend runs with no token (this PC only) and says so.
    'token-store.patch'
    # The second graphics card: GET and POST /api/second-card, the chat
    # turn's route header saying when the second card answered, the
    # learner's quiet wait, and the approval notice's words for
    # second_card_enable in jarvis_gate.py. Its context is power-mode's and
    # note-capture's route blocks, chat-stream's route-header lines,
    # extraction-wiring's learner loop, and note-capture's jarvis_gate.py
    # lines, so it goes after all of them; last is simplest. Needs
    # jarvis_second_card.py copied in; without it every hook does exactly
    # what it did before and the route answers 503.
    'second-card.patch'
    # The wiki builder: GET /api/wiki, GET and POST /api/wiki/ingest, and
    # the approval notice's words for wiki_update in jarvis_gate.py. Its
    # context is second-card's own GET and POST route blocks and its
    # jarvis_gate.py line, so it goes after second-card. Needs jarvis_wiki.py
    # copied in; without it the routes answer 503.
    'wiki.patch'
    # The big model (slow), run by colibri on this PC for background jobs:
    # GET and POST /api/big-model, GET /api/deep, POST /api/deep/ask, and
    # the approval notice's words for big_model_enable in jarvis_gate.py.
    # Its context is wiki's own GET and POST route blocks and its
    # jarvis_gate.py line, so it goes after wiki. Needs jarvis_big_model.py
    # copied in; without it the routes answer 503 and the wiki keeps using
    # the second card only.
    'big-model.patch'
    # Custom voices: GET /api/voice/voices and POST /api/voice/voices/create,
    # /active, /delete and /better, and the approval notice's words for
    # custom_voice and better_voice_enable in jarvis_gate.py. Its context is
    # big-model's own GET and POST route blocks and its jarvis_gate.py line,
    # so it goes after big-model. Needs jarvis_voices.py (and, for the better
    # voice, jarvis_f5_worker.py) copied in; without it the routes answer 503
    # and Jarvis speaks in its built-in voice as before.
    'voices.patch'
    # Turning background learning ON raises an approval card (the owner's
    # decision, 2026-09-24); OFF stays immediate. One line of memory-pane's
    # /api/memory/learning route; its context is that route, so it goes after
    # memory-pane - last, like every new patch. Needs jarvis_learning_switch.py
    # copied in; without it the route answers 503 rather than switching on
    # with no card.
    'learning-asks.patch'
    # Interrupting Jarvis by talking (?source=barge_in on /api/voice/utterance:
    # "stop or not", never transcribed), the app's own wait (?waited_ms=) for
    # the delay's numbers, and GET /api/voice/moment (the "One moment." clip).
    # Its context is voice-mic's lines in the utterance route and voices'
    # GET route, so it goes after both - last, like every new patch. Needs
    # jarvis_voice_flow.py copied in; without it barge_in answers "do not
    # stop" and the clip route answers 503.
    'voice-flow.patch'
    # Chat history kept on this PC, encrypted (the owner's decision,
    # 2026-09-24): /api/chat records each turn, the apps' bookkeeping fields
    # are taken off before any model sees them, and GET /api/history,
    # /api/history/conversation, POST /api/history/delete and
    # /api/history/settings are added, with the approval notice's words for
    # history_enable in jarvis_gate.py. Its context is voices' route blocks
    # and jarvis_gate.py line, chat-stream's and speed-record's /api/chat
    # lines and memory-intake's learner call - last, like every new patch.
    # Needs jarvis_chat_log.py copied in; without it the history routes
    # answer 503 and chat works as before, keeping nothing.
    'chat-history.patch'
    # Automatic learning (the owner's decision, 2026-09-24): a fact from the
    # owner's own words - typed, or said to this PC and checked very
    # strictly - is saved without a card when every check in
    # jarvis_auto_learn.py passes; everything else stays a card, with the
    # reason on it. Adds GET /api/memory/learning and /api/memory/auto and
    # POST /api/memory/learning/auto and /sensitive, jarvis_extract's
    # accept_auto() (the facts keep their proposal's source), the learner's
    # refusal of an Ollama cloud model, quote marks round the recalled facts,
    # and the approval notice's words for learning_auto_enable and
    # learning_sensitive_enable in jarvis_gate.py. Its context is
    # chat-history's lines (the learner call it moves after the history
    # record, both route blocks, _NO_CHAT_LOG and the gate line),
    # memory-intake's learner and propose(), memory-safety's _accept() and
    # memory-noise's recalled-facts block - last, like every new patch.
    # Needs jarvis_auto_learn.py copied in; without it every fact waits for
    # the owner's yes, as before, and the new routes answer 503.
    'auto-learn.patch'
    # "Erase the words" (the owner's decision, 2026-09-24): POST
    # /api/memory/erase wipes ONE fact's words for good and keeps its dates.
    # One route block, added right above memory-pane's forget/edit route; its
    # context is auto-learn's /api/memory/learning/auto block and that route
    # tuple, so it goes after auto-learn - last, like every new patch. The
    # work is in the shipped rebuilt\jarvis_memory.py (erase(),
    # handle_erase()); with an older copy the route answers 501.
    'memory-erase.patch'
    # A question about the past ("where did I live before?", "what did I
    # believe in June?") also gets the RETIRED facts that match, each
    # labelled "(no longer true since <date>)"; every other question gets
    # exactly the search it got before. One line of the chat turn's recall:
    # its context is memory-prefix's search call and memory-noise's
    # `created` lines, which nothing later touches - last, like every new
    # patch. Needs jarvis_past.py copied in; without it the old search runs.
    'past-recall.patch'
    # "Always keep in mind" (the owner's decision, 2026-09-24): a short list
    # of facts the owner pins, read with every local chat question, word for
    # word, first in the recalled-facts block; a pinned fact the search also
    # found is not repeated. Adds GET and POST /api/memory/profile. Its
    # context is auto-learn's /api/memory/auto and /learning/auto route
    # blocks, memory-erase's route line, past-recall's search lines and
    # auto-learn's recalled-facts lines, so it goes after past-recall - last,
    # like every new patch. The work is in the shipped
    # rebuilt\jarvis_memory.py (pin(), profile(), with_profile()); with an
    # older copy the routes answer 501 and chat recalls exactly as before.
    'memory-profile.patch'
    # Temporary chat and "Used in this answer" (the owner's decisions,
    # 2026-09-25): a request with "temporary": true recalls no facts (no
    # pinned list either), learns nothing (no "Remember:" either) and is not
    # kept in the chat history; X-Jarvis-Route says "temporary": true. Adds
    # GET /api/memory/used?ids=, the words of the facts an answer used. Its
    # context is memory-profile's GET route and search lines, past-recall's,
    # memory-prefix's placement, feedback's header lines and chat-history's
    # and auto-learn's record and learner lines - last, like every new
    # patch. The work is in the shipped rebuilt\jarvis_memory.py
    # (used_view) and jarvis_chat_log.py (TEMPORARY_CHAT); with older copies
    # the route answers 501 and a temporary chat is not recorded at all.
    'temporary-chat.patch'
    # Presets for any graphics cards (docs/HARDWARE-PROFILES.md): GET
    # /api/hardware (the cards, what runs now, three setups) and POST
    # /api/hardware/apply, /create (one approval card, models_create) and
    # /measure. Two route blocks, each right after second-card's - their
    # context is second-card's and wiki's blocks - and models_create's lines
    # in jarvis_gate.py after auto-learn's. Last, like every new patch.
    # Needs jarvis_hardware.py and jarvis_profiles.py copied in; without
    # them the routes answer 503.
    'hardware.patch'
    # The log scrubber (docs/EXTRACTION-RESEARCH-2026-09-23.md, Module 1):
    # right after HUD_TOKEN is resolved, jarvis_scrub.install(HUD_TOKEN)
    # takes passwords, keys and the pairing token out of everything the
    # backend prints or logs - backend.log - and the banner says so. Its
    # context is loopback-too's and bind-wildcard's lines; last, like every
    # new patch. Needs jarvis_scrub.py copied in; without it the log is
    # written as before and the banner line is not printed.
    'log-scrub.patch'
    # Timers, alarms, reminders and the to-do list, with ONE scheduler (the
    # owner's decisions, 2026-09-25): GET /api/schedule and POST
    # /api/schedule/add and /act, the scheduler started at boot, the fast
    # path in /api/chat that answers "set a timer for 10 minutes" WITHOUT
    # the model, and the approval notice's words for schedule_repeat in
    # jarvis_gate.py. Its context is hardware's route blocks and gate line,
    # chat-history's lines at the top of the answering part of /api/chat and
    # extraction-wiring's start-up banner - last, like every new patch. Needs
    # jarvis_schedule.py and jarvis_quick.py copied in; without them the
    # routes answer 503 and chat works exactly as before.
    'schedule.patch'
    # "Who is my sister?" - the entity layer (memory wave 3, 2026-09-25):
    # GET /api/memory/entities (the people and things facts are linked to,
    # for the desktop's "About <name>"), the "are these the same?" card
    # left out of /api/memory/pending unless asked for with ?merge_cards=1,
    # and jarvis_extract's propose_merge() / _accept_merge() - accepting that
    # card joins two entries and adds no fact. Its context is
    # temporary-chat's /api/memory/used route, memory-profile's GET line,
    # and feedback's pending filter and _accept() lines, so it goes after
    # temporary-chat - last, like every new patch. The work is in the
    # shipped rebuilt\jarvis_memory.py (the entity layer; recall uses it
    # through jarvis_past.py); with an older copy the route answers 501.
    'memory-entities.patch'
    # The morning briefing and the back-off for offers (2026-09-25): GET
    # /api/briefing and POST /api/briefing/now, "not now" on the
    # overnight-tidy card as a real answer (quiet for 1 day, then 7, then
    # 30), the conversation clock and a briefing's calendar read in
    # /api/chat, and the approval notice's words for schedule_repeat. Its
    # context is schedule's route blocks, its /api/chat block and its gate
    # line, and learning-asks' sleep_time lines - last, like every new
    # patch. Needs jarvis_briefing.py and jarvis_backoff.py copied in;
    # without them the routes answer 503 and chat works exactly as before.
    'briefing.patch'
    # Web search with a choice of five providers (the owner's decisions of
    # 2026-09-25): GET /api/search and POST /api/search/settings and /test,
    # and the approval notice's words for web_search (one search's card)
    # and stop_asking_before_every_web_search in jarvis_gate.py. Its context is hardware's
    # and schedule's route blocks and gate lines, so it goes after both.
    # Needs jarvis_search.py copied in; without it the routes answer 503 and
    # the model is never offered web_search's settings.
    'web-search.patch'
    # "What Jarvis can reach" (the Muse audit, 2026-09-25): GET /api/reach,
    # the list both apps show, written by jarvis_reach.py from the PC's own
    # settings. Its context is the end of web-search's GET /api/search block
    # and schedule's GET /api/schedule line, so it goes after web-search.
    # Needs jarvis_reach.py copied in; without it the route answers 503.
    'reach.patch'
    # The approval gap, step 1 (docs/APPROVAL-GAP-DESIGN.md, the owner's
    # decision of 2026-09-25): POST /api/approve asks Windows Hello itself
    # for a risky card approved from this PC, and the gate believes no
    # "approved" that this running backend did not stamp. Its context is
    # gate-outcome's approved branches in jarvis_gate.py and log-scrub's
    # banner line in jarvis_hud.py, so it goes after both. Needs
    # jarvis_owner_check.py copied in; without it EVERY approval is refused
    # (the gate fails closed), and the start-up banner says so.
    'owner-check.patch'
    # Sending email, one approval card per email (the owner's decision of
    # 2026-09-25, after the Muse audit): GET /api/email/sending (whether it
    # is set up - the Settings line in both apps), and in jarvis_gate.py the
    # notice's words for send_email, send_email in _TOOL_ACTIONS, and "no
    # memory rule from a no" (each email is its own card). Its context is
    # web-search's GET route block and _NO_RULE_FROM_DENIAL / _RISK lines, and
    # note-capture's _TOOL_ACTIONS lines, so it goes after web-search - last,
    # like every new patch. Needs jarvis_email_send.py copied in; without it
    # the route answers 503 and the send_email tool says it is unavailable.
    'email-send.patch'
    # How Jarvis words things - warm and brief (the default) or plain (the
    # owner's decision of 2026-09-25): GET and POST /api/manner, no card
    # either way. Its context is web-search's GET and POST route blocks, so
    # it goes after web-search - last, like every new patch. Needs
    # jarvis_manner.py copied in; without it the routes answer 503 and
    # answers are worded as before.
    'manner.patch'
    # "Stop everything" (the owner's decision of 2026-09-25): POST
    # /api/stop_all halts a running task, the tools of the answer being
    # written, and anything registered with jarvis_stop_all; it never
    # approves or starts anything. Its context is owner-check's banner
    # lines, so it goes after it. Needs jarvis_stop_all.py copied in;
    # without it the route is not there and the banner says so.
    'stop-all.patch'
    # Focus sessions (the owner's decision of 2026-09-25): GET /api/focus,
    # /api/focus/diag and /api/focus/callout (this PC only), POST
    # /api/focus/start and /api/focus/act. Its context is manner's GET block
    # and power-mode's POST block, so it goes after both. Needs
    # jarvis_focus.py copied in; without it the routes answer 503.
    'focus.patch'
    # Per-model thinking levels (2026-10-01, Section 5.5): GET and POST
    # /api/thinking, no approval card either way. It goes AFTER focus.patch:
    # its first hunk's trailing context is focus's own
    # `if path in ("/api/focus", ...)` block, which does not exist in the file
    # until focus.patch has inserted it. Applying it first makes `git apply`
    # fail on that hunk (no fuzz, no --3way), which stops the WHOLE run with
    # "N patch(es) will not apply" and leaves the backend unchanged. Needs
    # jarvis_thinking.py copied in.
    'thinking.patch'
    # "What asks first" (the owner's decisions of 2026-09-26, after the
    # approvals audit): GET /api/asks_first (every action and whether it
    # asks, from this PC's own settings), POST /api/asks_first/tier (stricter
    # at once from either app; looser only from this PC, one card plus
    # Windows Hello, and only for a short safe list) and POST
    # /api/asks_first/lights ("Lights, plugs and fans without a card"), and in
    # jarvis_gate.py the words for loosen_what_asks_first and schedule_repeat
    # (plain repeats no longer have a card). Its context is focus's GET and
    # POST blocks and briefing's and email-send's jarvis_gate.py lines, so it
    # goes after focus - last, like every new patch. Needs
    # jarvis_asks_first.py copied in; without it the routes answer 503 and
    # every change in the home still asks.
    'asks-first.patch'
    # "Folders Jarvis may look in" (the owner's decisions of 2026-09-26:
    # asking about PDFs and Word files, and bringing in a Notion export):
    # GET /api/folders, POST /api/folders/add (this PC only, one approval
    # card), /remove (at once) and /import (a Notion export, this PC only),
    # wrapped round the server's handler at start-up like stop-all. Its
    # context is stop-all's banner lines, so it goes after it - last, like
    # every new patch. Needs jarvis_documents.py copied in; without it the
    # banner says so and the routes are not there.
    'documents.patch'
    # The crisis help line's ONE cosmetic flag (the owner's decision of
    # 2026-09-27): route_header["wellbeing"] = "crisis", so both apps can
    # draw a calm panel instead of an ordinary chat bubble. The safety
    # behaviour itself - no tools on a crisis turn, the note to the model,
    # the help message appended or sent alone on failure, never learned -
    # is complete without this patch, in jarvis_agent.py and
    # jarvis_intake.py below, which this script always copies in. UNLIKE
    # every other patch here, this one was written with no real
    # jarvis_hud.py to check it against (see backend/README.md's own
    # section, "The crisis help line", for exactly what that means and
    # why); if the rehearsal above says it will not apply, that almost
    # certainly means this file has moved since it was written - send the
    # reason back rather than editing it by hand.
    'wellbeing.patch'
    # Games and role-play run in a temporary chat automatically (the
    # owner's decision, 2026-09-27, CLAUDE.md / Q19): a game or made-up
    # scenario, once started by the owner's own words, is put through
    # _temporary_chat() too, so it recalls no facts, is never kept and is
    # never learned from - the same as a manually-started temporary chat.
    # Its context is temporary-chat's _temporary_chat() function and the
    # two lines in the chat turn's `finally` block that check
    # body.get("temporary") directly, so it goes after temporary-chat -
    # last, like every new patch. The detection itself is in the shipped
    # jarvis_intake.py (game_or_roleplay()); without that module, or on any
    # error, nothing is detected and chat works exactly as before.
    'games-temporary.patch'
    # Smartwatch notifications (the owner's decision, 2026-09-25;
    # reconfirmed 2026-09-27, Q17): GET and POST /api/notifications/watch -
    # off by default (every notification stays on the phone), ON is one
    # approval card (watch_notifications_enable), OFF is instant. Wrapped
    # round the server's handler at start-up like folders. Its context is
    # documents's banner lines, so it goes after it - last, like every new
    # patch. Needs jarvis_watch_notify.py copied in; without it the banner
    # says so and the route is not there.
    'watch-notifications.patch'
    # Email drafts (the owner's decision, 2026-09-27, "a card every time,
    # showing the full draft"): GET /api/email/drafting (the Settings line,
    # same shape as email-send's), and in jarvis_gate.py the words for
    # draft_email, draft_email in _TOOL_ACTIONS, and "a no proposes no
    # memory rule" for it - all right beside send_email's own lines. Its
    # jarvis_hud.py context is web-search's route block (the same one
    # email-send.patch built on); its jarvis_gate.py context is
    # email-send.patch's three blocks, so it goes after email-send - last,
    # like every new patch. Needs jarvis_email_draft.py copied in; without
    # it, or on any error, the route says so.
    'draft-email.patch'
    # "Things you can say" (already approved as feasibility I116; the
    # ease-of-use audit's do-first table, row 4, 2026-09-27): GET
    # /api/sayable - the fixed list of real sentences Jarvis answers
    # without the model, read by the empty Jarvis bar/Home screen, the
    # walkthrough and Help in both apps. Fixed text, not a setting, so no
    # approval card either way, the same shape as reach.patch and
    # manner.patch. Its context is draft-email's own new route block, so it
    # goes after it - last, like every new patch. Needs jarvis_sayable.py
    # copied in; without it, or on any error, the route says so.
    'sayable.patch'
    # Offering a reading tool to the AI model at all, from the PC (the
    # owner's answer, 2026-09-27): POST /api/asks_first/tools - a DIFFERENT
    # thing from asks-first.patch's /api/asks_first/tier (whether a tool is
    # offered at all, [tools].enabled, never whether it asks first). Its
    # jarvis_hud.py context is asks-first.patch's own tier/lights route
    # block, so it goes after asks-first.patch; its jarvis_gate.py context
    # is asks-first.patch's two blocks too. Needs jarvis_asks_first.py -
    # already needed by asks-first.patch, so nothing new to copy in.
    'tools-enable.patch'
    # Backups (the owner's decision, 2026-09-27): GET /api/backup and
    # /api/backup/list, POST /api/backup/folder ("Back up into this folder?",
    # one approval card, change_own_config - jarvis_documents.check_folder's
    # own refusal list), /api/backup/now (this PC only, no card),
    # /api/backup/restore/preview and /api/backup/restore (this PC only, ONE
    # approval card that always needs Windows Hello - a new jarvis_gate.py
    # _RISK entry and jarvis_owner_check.PC_ONLY_ACTIONS). Its jarvis_hud.py
    # context is watch-notifications.patch's own install block, and its
    # jarvis_gate.py context is tools-enable.patch's two blocks, so it goes
    # after both - last, like every new patch. Needs jarvis_backup.py copied
    # in; without it, or on any error, the routes say so.
    'backup.patch'
    # Music and video control on this PC (the owner's decision, 2026-09-27,
    # feasibility I91: "no card, only from the owner's own words"): GET
    # /api/media ("what's playing") and POST /api/media/control - never a
    # card, never jarvis_gate, for either route; the fast path itself is in
    # the shipped jarvis_quick.py, not this patch. Its jarvis_hud.py context
    # is backup.patch's own install block (merged in after it, 2026-09-27),
    # so it goes after it - last, like every new patch. Needs
    # jarvis_media.py copied in; without it, or on any error, the banner
    # says so and the routes answer 503.
    'media.patch'
    # News headlines in the morning briefing (the owner's decision,
    # 2026-09-27, feasibility I49: "one card per address the owner adds,
    # read-only, never follows links elsewhere, never acts on what it
    # reads"): GET /api/news, POST /api/news/add (ONE approval card, from
    # either app) and /api/news/remove (at once). Its context is media's
    # own banner block, so it goes after it - last, like every new patch.
    # Needs jarvis_news.py copied in; without it, or on any error, the
    # banner says so and the routes answer 503.
    'news.patch'
    # "Between us" (the owner's decision, 2026-09-27): GET and POST
    # /api/memory/shared - tag or untag ONE fact as a shared joke or
    # nickname (meta.kind = "shared"), the owner's own tap only, no approval
    # card, the same shape as memory-profile.patch. Its jarvis_hud.py
    # context is the route-dispatch chain right after /api/memory/status
    # (original line ~1964) - a different part of the file from the
    # startup install() block every backup/media/news-shaped patch touches,
    # so its place in this list is only about order, not about finding its
    # own anchor text. The work is in the shipped
    # rebuilt\jarvis_memory.py (shared(), is_shared(), shared_facts(),
    # without_shared_in_plain(), with_profile()'s new `manner` argument);
    # with an older copy the routes answer 501 and nothing is filtered.
    'memory-shared.patch'
    # "Data health in the preflight" (feasibility I97, docs/FEASIBILITY-AUDIT-
    # 2026-09-26.md: "Small, read-only" / "WARN, never fix"): GET
    # /api/data-health, read by --preflight's own "Is Jarvis's own data
    # healthy?" check. Its jarvis_hud.py context is the route-dispatch chain
    # near /api/reach (original line ~1626), a completely different part of
    # the file from every patch above it in this list (they all touch the
    # startup install() block) - so its place in this list is only about
    # order, not about finding its own anchor text. Needs
    # jarvis_data_health.py copied in; without it the route answers 503.
    'data-health.patch'
    # "Check for tool updates" (the owner's request, made directly): GET
    # /api/tool_updates (the report, read-only) and POST
    # /api/tool_updates/check (ONE approval card, ever - then never again;
    # it never installs or changes a file itself). Its jarvis_hud.py
    # context is news.patch's own install block, so it goes after it -
    # last, like every new patch. memory-shared.patch and
    # data-health.patch, above it in this list, both touch a different,
    # unrelated part of the file (the route-dispatch chain, not this
    # startup install() block), so neither changes what this patch's own
    # hunk actually finds. Needs jarvis_tool_updates.py copied in, and the two files step 3b
    # below copies (requirements.lock, rust-crates.lock); without any of
    # the three, or on any error, the banner says so and the routes answer
    # 503 or say plainly what could not be read.
    'tool-updates.patch'
    # "Where this came from" and the quote check (feasibility I42/I132,
    # docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md detail 1): GET
    # /api/chat/sources?turn_id=<id> - each reading tool's own result this
    # turn, by reference (a note's ref, a wiki page's path, a web result's
    # url, a file's path), plus which quoted phrases in the answer were not
    # found in any of them. Two hunks: its startup install() block, whose
    # context is tool-updates.patch's own (so it goes after it, like every
    # new patch); and its jarvis_hud.py hunk right after chat-history.patch's
    # `_history["turn"] = _turn` line (nothing later in this list touches
    # `_turn`), where `route_header["turn_id"]` - set before this loop ever
    # ran, since the header goes out before jarvis_agent even starts - is
    # already in scope. Needs jarvis_sources.py copied in; without it, or on
    # any error, the banner says so and the route answers 503, and nothing
    # about an ordinary chat turn changes.
    'answer-sources.patch'
    # Noticing a conversation could use the bigger model (CLAUDE.md
    # 2026-09-27's "Both, with a setting" answer): one small hunk, right
    # after feedback.patch's own POST /api/feedback/mark block (so it goes
    # after it, like every new patch), passing an optional
    # `conversation_id` on to jarvis_second_card.py's per-conversation
    # correction count. jarvis_agent.py and jarvis_second_card.py carry the
    # rest of this feature as ordinary code, needing no patch (they are
    # whole shipped modules, copied in like every other one in this list).
    'second-card-suggest.patch'
    # The Jarvis rules stay first on a turn with no tools enabled, too: one
    # hunk in the relay's _open(), right after chat-history.patch's
    # _chat_client_fields_off lines (so it goes after it, like every new
    # patch), calling jarvis_agent.keep_rules_first() - the same call the
    # tool loop already makes - for the local model only. Needs nothing new
    # copied in: jarvis_agent.py is already in this list.
    'rules-first-relay.patch'
    # The owner's yes for one question, to the cloud lane
    # jarvis_router.choose() already offers but never uses on its own
    # (docs/ARCHITECTURE.md "Cloud / API keys", "the owner chose 'ask each
    # time'"). One line added to the ALREADY-EXISTING choose() call this
    # repository had never patched before 2026-09-27 - real, verified
    # against the owner's own file by hand, not a stand-in, because no
    # earlier patch's hunk touches this call at all (see the patch's own
    # comment for why that matters). Every privacy gate above it in
    # choose() still runs first and in the same order; this can only ever
    # turn an "offer" into an "escalate" for a question that had already
    # cleared every other gate on its own.
    'cloud-say-yes.patch'
    # "Goals with one card per step" (the owner's "build it now",
    # 2026-09-27, after the Jarvis evaluation; design:
    # docs/creativity-2026-09-25/future.md idea 3). One try/except block,
    # append-only, right after answer-sources.patch's own new route block -
    # jarvis_goals.py is a brand-new whole module, so this adds a route the
    # same way news.patch and tool-updates.patch each did. Never batches an
    # approval: every acting step still gets its own separate card through
    # ordinary chat tool use, exactly as today - this is NOT the "plan
    # card" (docs/FEASIBILITY-AUDIT-2026-09-26.md I61) still gated behind
    # the multi-step safety tests; see jarvis_goals.py's own docstring for
    # why the two are different and why this one was never waiting on that.
    'goals.patch'
    # "One card, several steps" (feasibility I61, "the plan card"; the
    # owner's own words, 2026-09-28). Two small hunks against jarvis_gate.py
    # only: a risk entry for run_plan and a tier line for propose_plan/
    # run_plan, both append-only next to their own kind's existing entries
    # (control_computer's own risk line; draft_email's own tier line).
    # jarvis_plan.py itself is SWITCHED OFF until tools/tool_eval's real
    # results clear the bar - see that module's own docstring - so this
    # patch alone changes nothing the model can reach yet; it only teaches
    # the gate the two new action names for when it is turned on.
    'plan-gate.patch'
    # Reading phone notifications (the owner's decision, 2026-09-26; built
    # 2026-09-28, CLAUDE.md): GET and POST /api/notifications/phone - OFF by
    # default (Jarvis never reads a phone notification), ON is one approval
    # card (phone_notifications_read), OFF is instant. Three hunks: its
    # jarvis_gate.py "acts only on tier ask" line (context is backup.patch's
    # own restore_backup line, so it goes after it) and its jarvis_gate.py
    # _RISK entry (context is plan-gate.patch's own run_plan entry, so it
    # goes after it); and its jarvis_hud.py install() block (context is
    # goals.patch's own block, so it goes after it - last, like every new
    # patch touching that block). Needs jarvis_phone_notifications.py copied
    # in; without it, or on any error, the banner says so and the route is
    # not there. Everything else (which apps, the one-time-code redaction,
    # never SMS, the allow list) lives entirely on the phone
    # (jarvis-client/), proved by that app's own tests - this patch and its
    # module never see a notification's text.
    'phone-notifications.patch'
    # The Brain upgrades (the owner's choice, 2026-09-28; docs/JARVIS-API.md
    # section 71): GET /api/history/search ("search what was said in old
    # chats" - each kept turn opened in memory for that one search, no
    # index, nothing written) and GET /api/memory/fact-history ("history of
    # this fact" - an erased version never with its words). Reads for the
    # apps only; nothing here reaches the AI model. Its jarvis_hud.py
    # context was answer-sources.patch's own install block; since GitHub's
    # main was merged with the research branch (2026-09-28) it is
    # forget-range.patch's install block, the last of that branch's chain
    # (projects -> chatbot-routes -> live -> forget-range), so it goes after
    # it. second-card-suggest.patch touches a different part of the file
    # (the POST route chain). Needs jarvis_brain_reads.py copied in; without it the banner
    # says so and the two routes are simply not there (404).
    'brain-reads.patch'
    # Warm-up with words, after a learning pass (speed fix, 2026-09-28): one
    # hunk in the learner thread's _loop, whose lines are extraction-
    # wiring.patch's own (nothing after it in this list touches them), so
    # it goes last, like every new patch. After each pass that asked a
    # model it calls jarvis_agent.warm_after_learning(), which re-reads the
    # start every question shares only on a one-card PC and never while a
    # question is being answered. Needs nothing new copied in: jarvis_agent.py
    # is already in this list; without it, nothing changes.
    'warm-prefix.patch'
    # "Photo to reminder" (the owner's choice, 2026-09-28; docs/JARVIS-API.md
    # section 83): POST /api/photo/scan reads the words in a picture with
    # Windows' own text recognition (jarvis_ocr.py), finds a date and time
    # with jarvis_quick.py's own parser, and PROPOSES a reminder - it sets
    # nothing up; the owner's tap adds it through /api/schedule/add. Its
    # jarvis_hud.py context is brain-reads.patch's own install block, so it
    # goes after it - last, like every new patch; warm-prefix.patch, above,
    # touches the learner thread, not these lines. Needs
    # jarvis_photo_remind.py copied in; without it the banner says so and the
    # route is simply not there (404).
    'photo-reminder.patch'
    # "Bring in chats from ChatGPT, Claude or Gemini" (the owner's choice,
    # 2026-09-28; docs/JARVIS-API.md section 85): GET /api/memory/import_chats
    # and POST /api/memory/import_chats/start (this PC only, no card - it
    # only PROPOSES; every fact waits for the owner's yes) and /cancel. Its
    # jarvis_hud.py context is photo-reminder.patch's own install block, so
    # it goes after it - last, like every new patch. Needs
    # jarvis_history_import.py and import_history.py copied in; without them
    # the banner says so and the routes are simply not there (404).
    'history-import.patch'
    # Projects, build steps 1 and 2 (the owner's decision of 2026-09-28,
    # docs/PROJECTS-DESIGN.md): GET and POST /api/projects and its
    # benchmarks. One hunk, the startup install() block; its context is
    # answer-sources.patch's own install block (second-card-suggest.patch,
    # just above, touches a different part of the file), so it goes after
    # both - last, like every new patch. Needs jarvis_projects.py copied
    # in; without it, or on any error, the banner says so and the routes
    # are not there. goals.patch (continuation branch) anchors on the SAME
    # lines: whichever of the two lands second is re-anchored on the
    # other's block when that branch merges.
    'projects.patch'
    # Talking to an AI chatbot for the owner (jarvis_chatbot.py and its
    # Gemini adapter, jarvis_chatbot_gemini.py, both shipped whole): the
    # gate's _RISK line for `chatbot_session` (it leaves this PC and cannot
    # be taken back, so its approval is a risky one), and its line in the
    # "a no is not a standing rule" list. Two hunks in jarvis_gate.py, whose
    # context is backup.patch's own lines (so it goes after it, like every
    # new patch). No route yet: the feature is still not reachable from
    # either app.
    'chatbot.patch'
    # "Talk to a chatbot for me" (the owner's decisions of 2026-09-27 and
    # 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md, JARVIS-API section 87): GET
    # /api/chatbot/status, POST /api/chatbot/start (ONE approval card per
    # conversation; nothing is sent before a person's yes), /api/chatbot/stop
    # (never a card) and /api/chatbot/limits (a NEW card). Its jarvis_hud.py
    # context is projects.patch's own install block (which itself follows
    # answer-sources.patch's), so it goes after it - last, like every new
    # patch. Needs jarvis_chatbot.py and jarvis_chatbot_routes.py copied in;
    # without them, or on any error, the banner says so and the routes are
    # simply not there.
    'chatbot-routes.patch'
    # Jarvis Live (the owner's decision and answers of 2026-09-28;
    # docs/LIVE-DESIGN.md, JARVIS-API section 63): GET and POST
    # /api/voice/live - start, stop, extend and resume a Live conversation
    # (no card: the owner's own act). Its jarvis_hud.py context is
    # chatbot-routes.patch's own install block, so it goes after it - last,
    # like every new patch. Needs jarvis_live.py copied in; without it, or
    # on any error, the banner says so and the route is simply not there.
    'live.patch'
    # "Forget a time frame" (the owner's decision of 2026-09-28; JARVIS-API
    # section 64): GET /api/memory/forget_range and /preview, POST
    # /api/memory/forget_range (ONE approval card listing every fact and
    # chat; nothing changes before a person approves) and /undo (10
    # minutes, no card). Three hunks: two in jarvis_gate.py, whose context
    # is chatbot.patch's own lines (the "a no is not a standing rule" list
    # and the risk table), and the startup install() block in jarvis_hud.py,
    # whose context is live.patch's own block - so it goes after both, last,
    # like every new patch. Needs jarvis_forget_range.py copied in; without
    # it, or on any error, the banner says so and the routes are simply not
    # there.
    'forget-range.patch'
    # The sun, the moon and the weather behind the animal faces (the owner's
    # decisions of 2026-09-28): GET /api/sky and POST /api/sky. Its
    # jarvis_hud.py context is answer-sources.patch's own startup install()
    # block (second-card-suggest.patch, just above, touches a different part
    # of the file), so it goes last, like every new patch. Needs jarvis_sky.py
    # and jarvis_sky_places.py copied in; without them, or on any error, the
    # banner says so and the route answers 503 - the faces are drawn as before.
    'sky.patch'
    # Animal options (the owner's decisions of 2026-09-28): GET /api/animal
    # and POST /api/animal - "Keep the animal still" and the animal's
    # behaviour switches, shared by both apps, at once and with no card - and
    # the same values in GET /api/appearance as "animal". Two hunks: one in
    # appearance.patch's _appearance_view, one right after sky.patch's own
    # startup install() block (so it goes after it, like every new patch).
    # Needs jarvis_animal.py copied in; without it, or on any error, the
    # banner says so, the route answers 503 and the faces are drawn as before.
    'animal.patch'
    # "Chat with customer support for me" (the owner's decisions of
    # 2026-09-28; JARVIS-API section 65): the gate's _RISK lines for
    # `support_chat` (ONE card per support chat, listing every detail
    # Jarvis may give) and `support_offer` (ONE card per offer; nothing is
    # accepted without it) - both leave this PC and cannot be taken back,
    # so their approvals are risky ones - and their lines in the "a no is
    # not a standing rule" list. Two hunks in jarvis_gate.py whose context
    # is forget-range.patch's own lines, so it goes after it - last, like
    # every new patch, but before devices.patch, which must stay the very last
    # (its hunk in jarvis_hud.py has to come before every install() block, and
    # backend/test_devices.py checks it is last); devices.patch's gate hunks
    # are at other lines. No route of its own: chatbot-routes.patch already
    # installs jarvis_chatbot_routes.py, which reaches jarvis_support.py.
    'support-chat.patch'
    # Pairing a phone by QR code, with a key per device (the owner's
    # decisions of 2026-09-24 and 2026-09-28; docs/PAIRING-DESIGN.md phase 1,
    # docs/JARVIS-API.md section 90). Three hunks: two in jarvis_gate.py - the
    # two new cards (pair_device, unretire_shared_key) join the "a no is not
    # a standing rule" list right after its opening line (gate-outcome.patch's
    # own lines), and their _RISK lines go after phone-notifications.patch's
    # own entry - and ONE block in jarvis_hud.py, right after
    # `_refuse_every_interface(bind)` and BEFORE owner-check.patch's block,
    # because every module's install() keeps the _token_ok it is handed: the
    # device-key check must replace it before the first of them. It goes last
    # in this list because its context is other patches' lines; its block
    # still lands before theirs in the file. Needs jarvis_devices.py copied
    # in; without it, or on any error, nothing is replaced - only the shared
    # key works, exactly as before - and the banner says so.
    'devices.patch'
    # An app inside a Jarvis project (the owner's decisions of 2026-09-28 and
    # 2026-09-29; docs/APPS-IN-PROJECTS-DESIGN.md, docs/JARVIS-API.md section
    # 92): an app's tasks, a task's whole change, and ONE risky approval card
    # (app_merge_change) before a change is added to the app; a change is
    # pasted in on the PC only. Three hunks: the startup install() block in
    # jarvis_hud.py, right after projects.patch's own block (and before
    # chatbot-routes.patch's, whose first lines are its context); and two in
    # jarvis_gate.py - the "a no is not a standing rule" list, after
    # forget-range.patch's own last line, and the _RISK entry, after
    # devices.patch's register_approval_key line. So it goes after
    # projects.patch, chatbot-routes.patch, forget-range.patch and
    # devices.patch - last, like every new patch. Needs jarvis_apps.py (and
    # jarvis_app_workspace.py, jarvis_projects.py) copied in; without it, or
    # on any error, the banner says so and the app routes are simply not
    # there.
    'apps-in-projects.patch'
    # "Inbox tidy by voice" (the owner's decision of 2026-09-28; JARVIS-API
    # section 95): archive, star, mark as read or move to Trash a checked list
    # of emails, ONE approval card listing every one, 10 minutes to Undo.
    # Four hunks: in jarvis_gate.py the new action joins the "a no is not a
    # standing rule" list (right after support-chat.patch's own last line),
    # gets its _RISK line (after support-chat.patch's last entry - an
    # outbound one: it changes the owner's mailbox on the provider's server,
    # so its approval is a risky one) and its _TOOL_ACTIONS line (after
    # draft-email.patch's); in jarvis_hud.py ONE install block after
    # sky.patch's (GET /api/email/tidy and POST /api/email/tidy/undo). Its
    # context is other patches' lines, so it goes after them - last, like
    # every new patch (after devices.patch and apps-in-projects.patch, whose
    # own hunks use the same gate lists as context and must see them before
    # this one adds its lines). Needs jarvis_inbox_tidy.py copied in; without it, or on any error,
    # the banner says so and the routes are simply not there.
    'inbox-tidy.patch'
    # "Look at this" and "Watch with me" (the owner's decision of 2026-09-28;
    # docs/SCREEN-DESIGN.md, JARVIS-API sections 62 and 96): GET/POST
    # /api/screen and /api/screen/never-look. Three hunks in jarvis_hud.py:
    # the startup install() block (context: inbox-tidy.patch's own block, the
    # last one before `_loopback_companion`, so it goes after it - last, like
    # every new patch), a small `_screen_turn` helper (context:
    # games-temporary.patch's own lines), and `has_screen=` in the router
    # call, so a turn carrying the owner's screen never leaves this PC
    # (context: cloud-say-yes.patch's own lines). The message field `screen`
    # comes off before the model in temporary-chat.patch's own list. Needs
    # jarvis_screen.py and jarvis_screen_win.py copied in; without them, or
    # on any error, the banner says so and the routes are simply not there.
    'screen.patch'
    # Picture mode for "Look at this" and "Watch with me" on a PC with one
    # graphics card (the owner's decision of 2026-09-29; JARVIS-API section
    # 96.1): ONE card to turn it on (screen_picture_enable, tier ask). Two
    # hunks in jarvis_gate.py, both right after inbox-tidy.patch's own last
    # lines (the "acts only on tier ask" list and the _RISK table), so it goes
    # after everything else - last, like every new patch. Needs
    # jarvis_screen_picture.py copied in; the routes are answered by
    # jarvis_screen.py, which screen.patch already installs.
    'screen-picture.patch'
    # The headless browser, Obscura (the owner's decision of 2026-09-29;
    # JARVIS-API section 97): ONE card to turn it on (obscura_enable, tier
    # ask) and GET/POST /api/browser/engine. Three hunks: in jarvis_gate.py the
    # new action joins the "a no is not a standing rule" list and gets its
    # _RISK line - both right after screen-picture.patch's own last lines, so
    # it goes after it - and in jarvis_hud.py ONE install block right after
    # screen.patch's own, the last one before `_loopback_companion` (last,
    # like every new patch). Needs jarvis_browser_engine.py and
    # jarvis_obscura.py copied in; without them, or on any error, the banner
    # says so and the route is simply not there - the visible browser is
    # unchanged.
    'browser-engine.patch'
    # "Fill in the form, show me, then send it" (the owner's decision of
    # 2026-09-30; docs/FORM-REVIEW-DESIGN.md): a browser plan's last click may
    # be marked final; Jarvis stops before it and raises a SECOND card
    # (browser_form_submit, tier ask, a risky approval) with the site, every
    # word typed and a picture of the page, and GET /api/form-review/picture
    # serves that picture while the card waits. Three hunks: in jarvis_gate.py
    # the new action joins the "acts only on tier ask" list and gets its _RISK
    # line - both right after browser-engine.patch's own last lines - and in
    # jarvis_hud.py ONE install block right after browser-engine's, the last
    # before `_loopback_companion`. So it goes last. Needs
    # jarvis_form_review.py copied in; without it the banner says so and the
    # plan card still says its last step waits for a second card that cannot
    # be raised - so nothing is sent.
    'form-review.patch'
    # The web search on/off switch (the settings audit of 2026-09-30): turning
    # web search back ON after the owner switched it off is ONE card
    # (web_search_enable, tier ask); turning it off is instant. Two gate hunks
    # only - the new action joins the "a no is not a standing rule" list and
    # gets its _RISK line - both right after browser-engine.patch's own last
    # lines, so it goes after it (last, like every new patch). It touches no
    # route: POST /api/search/settings already exists (web-search.patch) and
    # jarvis_search.py answers the new {"enabled": ...} body.
    'web-search-switch.patch'
    # "Quiz me on a text" (the owner's decision of 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md,
    # JARVIS-API section 98): POST /api/quiz and GET /api/quiz/<id>, .../answer, .../finish,
    # .../stop. ONE hunk in jarvis_hud.py, an install block right after form-review.patch's
    # own (the last one before `_loopback_companion`), so it goes last, like every new patch.
    # No card: the owner's own pasted words, the local model only, kept in memory only. Needs
    # jarvis_quiz.py copied in; without it, or on any error, the banner says so and the routes
    # are simply not there.
    'quiz.patch'
    # "Review decks" (the owner's decision of 2026-09-30; docs/QUIZ-DECKS-DESIGN.md, JARVIS-API section
    # 102): GET/POST /api/decks, /api/decks/<id>/act|cards, /api/decks/settings, GET /api/review and
    # POST /api/review/reveal|rate|more, and the function the quiz calls to keep chosen questions in a
    # deck. ONE hunk in jarvis_hud.py, an install block right after quiz.patch's own, so it goes after
    # it. No card: the owner's own tap saves the owner's own words, sealed in study.db under a key of
    # their own. Needs jarvis_decks.py copied in (and the py-fsrs package from requirements.txt);
    # without it, or on any error, the banner says so and the routes are simply not there.
    'decks.patch'
    # "Spending summaries" (the owner's decision of 2026-09-30; docs/FINANCE-DESIGN.md part A, JARVIS-API
    # section 100): GET /api/spending, GET/POST /api/spending/profile, POST /api/spending/profile/delete,
    # /categories and /suggest (this PC only) and GET /api/chat/table?id=<id>. ONE hunk in jarvis_hud.py,
    # an install block right after decks.patch's own (the last one before `_loopback_companion`), so it goes
    # last, like every new patch. No card and no gate line: the my_spending tool is decided under file_read's
    # action, and it reads a file in a folder the owner already listed. Needs jarvis_spending.py and
    # jarvis_money_parse.py copied in; without them, or on any error, the banner says so and the routes are
    # simply not there.
    'spending.patch'
    # "Retirement what-if" (the owner's decision of 2026-09-30; docs/FINANCE-DESIGN.md part B, JARVIS-API
    # section 103): GET /api/retirement/defaults and POST /api/retirement/run. ONE hunk in jarvis_hud.py, an
    # install block right after spending.patch's own, so it goes after it. A pure calculation on numbers the
    # owner typed: no file, no network, nothing stored, no card and no gate line. Needs jarvis_retirement.py
    # (and jarvis_money_parse.py) copied in; without them, or on any error, the banner says so and the routes
    # are simply not there.
    'retirement.patch'
    # "Activity heatmap and balance chart" (the owner's decision of 2026-09-30; docs/GOALS-PROGRESS-DESIGN.md
    # part C, JARVIS-API section 105): GET /api/progress/activity and GET/POST /api/progress/balance. ONE hunk
    # in jarvis_hud.py, an install block right after retirement.patch's own, so it goes after it. It only reads
    # the owner's ticked steps and logged numbers; the owner's choice of chart areas is a display setting (no
    # card, no gate line). Not a model tool. Needs jarvis_progress.py (and jarvis_projects.py, jarvis_goals.py)
    # copied in; without them, or on any error, the banner says so and the routes are simply not there.
    'progress.patch'
    # "Topic controls" (the owner's decision of 2026-09-30; docs/TOPIC-CONTROLS-DESIGN.md, JARVIS-API section
    # 107): GET/POST /api/topics, /api/topics/mode|file|settings, GET /api/topics/preview|review|hidden, the
    # owner's memory lists with the topic filter applied, and the count `topics_left_out` in the chat route's
    # header. THREE hunks: in jarvis_gate.py the new action `topic_loosen` joins the "acts only on tier ask"
    # set and gets its _RISK line (both right after browser-engine.patch's own last lines, so it goes after it);
    # in jarvis_hud.py ONE install block right after progress.patch's own (the last one before
    # `_loopback_companion`) and ONE line after auto-learn.patch's `injected_sensitive` line. Needs
    # jarvis_topics.py copied in, and the rebuilt jarvis_memory.py (its tables and the search filter); without
    # them, or on any error, the banner says so and the routes are simply not there - and with every topic on
    # "Learn and use" nothing about learning or answers changes at all.
    'topics.patch'
    # "Referee suggestions" and "Study helper" (the owner's decisions of 2026-09-30; JARVIS-API section 108;
    # two more switches on the second graphics card, both built OFF until the card is installed and
    # measured). THREE hunks: in jarvis_gate.py the new action `referee_tick` joins the "acts only on tier ask"
    # set and gets its _RISK line (both right after topics.patch's own last lines, so it goes after it); in
    # jarvis_hud.py ONE block right after topics.patch's own (the last one before `_loopback_companion`) that
    # installs the quiet hourly "This looks done - tick it?" look and hands the quiz its model call, so the
    # quiz uses the second card while "Study helper" is on. It adds no route and no tool. Needs jarvis_referee.py
    # copied in (and the rebuilt jarvis-framework.toml's `referee_tick = "ask"` line); without it, or on any
    # error, the banner says so and both switches simply do nothing.
    'referee.patch'
    # "Suggest tags overnight" (the owner's decision of 2026-09-30; docs/OVERNIGHT-TAGS-DESIGN.md, JARVIS-API
    # section 104): once a night the LOCAL model may suggest a tag for a few untagged chats, each one a card,
    # filed only on a tap. THREE hunks: in jarvis_gate.py the two actions `chat_tags_suggest_on` and
    # `chat_tag_suggest` join the "acts only on tier ask" set and get their _RISK lines (both right after
    # referee.patch's own, so it goes after it); in jarvis_hud.py ONE block right after referee.patch's
    # own (the last one before `_loopback_companion`) that keeps the quiet hourly look in step with the
    # switch. It adds no tool; the two routes are in chat-history.patch. Needs jarvis_tag_suggest.py copied
    # in (and the rebuilt jarvis-framework.toml's two `ask` lines); without it, or on any error, the banner
    # says so and the switch simply does nothing.
    'tag-suggest.patch'
    # "Quiz me on a YouTube video" (the owner's decision of 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md
    # section 5 and 14, JARVIS-API section 112): ONE card per YouTube link, then the video's CAPTION TEXT
    # only is fetched and quizzed on as outside text. It breaks YouTube's terms and may be blocked; the card
    # says so. TWO files: in jarvis_gate.py the new action `youtube_captions_read` joins the "acts only on
    # tier ask" set and gets its _RISK line (both right after tag-suggest.patch's own, so it goes after it);
    # in jarvis_hud.py ONE install block after tag-suggest.patch's own (the last one before
    # `_loopback_companion`). Needs jarvis_youtube.py copied in, the youtube-transcript-api package from
    # requirements.txt, and the rebuilt jarvis-framework.toml's `youtube_captions_read = "ask"` line; without
    # them, or on any error, the banner says so and the routes are simply not there.
    'youtube.patch'
    # "Grade this better" on a quiz (the owner's decision of 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md
    # section 7 and 15, JARVIS-API section 113): ONE card per request that lists exactly what would leave the
    # PC (the quiz's questions, the owner's answers and the passages), then that one message goes to the
    # cheapest cloud service the chatbot driver has set up (a saved key AND a monthly limit). Never for a
    # quiz that looks private or had a crisis answer. TWO files: in jarvis_gate.py the new action
    # `quiz_cloud_grade` joins the "acts only on tier ask" set and gets its _RISK line (both right after
    # youtube.patch's own, so it goes after it); in jarvis_hud.py ONE install block after youtube.patch's
    # own (the last one before `_loopback_companion`). Needs jarvis_quiz_cloud.py copied in, chatbot.patch's
    # jarvis_chatbot_api.py, and the rebuilt jarvis-framework.toml's `quiz_cloud_grade = "ask"` line; without
    # them, or on any error, the banner says so and the routes are simply not there.
    'quiz-cloud.patch'
    # "Chatbot money limits" - the INSTALL BLOCK half (the owner's approval of
    # 2026-10-06; docs/ACCOUNT-KEYS-DESIGN.md decisions 1 and 3, JARVIS-API
    # section 87.4.1). ONE block in jarvis_hud.py, wrapped round Handler right
    # after quiz-cloud.patch's own, before anything listens.
    #
    # This is a SEPARATE PATCH from chatbot-limits.patch below, and that is
    # load-bearing rather than tidiness: the two halves need different positions
    # in this list. This hunk's context is quiz-cloud.patch's own printed lines,
    # so it must run straight after quiz-cloud; put later, the tutorials.patch
    # and readpage.patch blocks land between its anchor and that context, so it
    # is materialised at the END of the file instead - which duplicates the
    # `_loopback_companion(bind, HUD_PORT, Handler)` line it uses as trailing
    # context (test_installed_stand_in.py, test_bind_wildcard.py,
    # test_loopback_too.py). The gate half must run after readpage.patch, for
    # its own reason. One patch cannot sit in two places, so there are two.
    #
    # Needs jarvis_chatbot_limits.py copied in (it is in SHIPPED below) and
    # chatbot.patch's jarvis_chatbot_api.py; without them, or on any error, the
    # banner says so and the route is simply not there.
    'chatbot-limits-hud.patch'
    # The gate renamed an action on its way out (2026-10-03). For the 58
    # _TOOL_ACTIONS entries whose value is a TIER literal ("calculator": "auto"),
    # action_for_tool() returned f"tool:{name}" as the action name. That string
    # is what goes to the checker, into the audit log, and onto the "What can
    # Jarvis reach" page (jarvis_reach.action_of) - and no config file, page or
    # suite has ever used it. Three suites expected "calculator" and got
    # "tool:calculator". It now returns the bare name.
    #
    # The entry is still REGISTERED in _SYNTH_TIERS under that bare name: a
    # tier literal is not a key of [autonomy.tiers], so _tiers()'s
    # tiers.get(action, UNKNOWN_TIER) would otherwise resolve "calculator" to
    # "ask" instead of "auto". That registration is load-bearing and stays.
    #
    # One hunk, in action_for_tool, which no other patch touches - so it can go
    # last, like every new patch, with no ordering constraint.
    'gate-action-name.patch'
    # "Tutorials and the FAQ" (the owner's request of 2026-10-05; docs/TUTORIALS-DESIGN.md,
    # JARVIS-API section 114): GET /api/tutorials, POST /api/tutorials/progress and GET
    # /api/faq. ONE hunk in jarvis_hud.py, an install block right after retirement.patch's
    # own, so it goes after it. One catalogue and the owner's reading progress, kept on the
    # PC and shared by both apps: it writes its own one JSON file in the config folder,
    # raises no card and calls nothing out. Needs jarvis_tutorials.py copied in (it is in
    # SHIPPED below); without it, or on any error, the banner says so and the routes are
    # simply not there.
    'tutorials.patch'
    # "Read this page out loud" (the owner's request of 2026-10-05; JARVIS-API section 115):
    # ONE approval card per address the owner hands over, raised BEFORE any fetch, then ONE
    # plain GET of that one page and its words read out as outside text. THREE hunks in
    # jarvis_gate.py: the action name in _NO_RULE_FROM_DENIAL, its own risk row, and its
    # _TOOL_ACTIONS line (2026-10-06 - without the third, action_for_tool() fell through to
    # "unclassified_tool" and the card the owner was shown was never the one this tool
    # raises). The first two hunks' context is quiz-cloud.patch's own added lines, so it goes
    # after quiz-cloud; the third sits right after inbox-tidy.patch's own _TOOL_ACTIONS line.
    # It needs jarvis_readpage.py and jarvis_agent.py copied in (both are in SHIPPED below);
    # without them the tool is simply not offered to the model and the gate row is never used.
    'readpage.patch'
    # "Chatbot money limits" - the GATE half (the owner's approval of
    # 2026-10-06; docs/ACCOUNT-KEYS-DESIGN.md decisions 1 and 3, JARVIS-API
    # section 87.4.1). Raising a limit is a loosening, so it raises ONE
    # approval card (`raise_api_limit`) plus Windows Hello on the PC, and is
    # refused from any other device. Lowering one, removing one, correcting a
    # price and resetting one tighten or correct, so they need no card - the
    # reason there are TWO action names, since the owner-check attaches Windows
    # Hello to the action and not to the direction. TWO hunks in jarvis_gate.py:
    # the names join the "acts only on tier ask" set and get their _RISK lines.
    # Each of the two goes at the END of its list, right after readpage.patch's
    # own last entry there (`read_web_page`), which is where readpage.patch and
    # quiz-cloud.patch each put theirs. Both hunks first named the entry that was
    # last when this patch was written - `quiz_cloud_grade` in the set,
    # `youtube_captions_read` in _RISK - and neither was last any more, so
    # `_stack.py` could not match them and materialised a pre-image at the end of
    # the file instead: that re-emitted the context lines and gave
    # `youtube_captions_read` a second _RISK row, of which only the last is ever
    # read (test_gate_risk_words.py's duplicate check is what caught it). Both
    # hunks now apply to real context - `_stack.py`'s RATCHET for jarvis_gate.py
    # came down from 25 to 23 with the fix.
    #
    # It sits HERE, after readpage.patch, and that position is load-bearing:
    # written straight after quiz-cloud.patch it stopped readpage.patch applying
    # at all, because readpage's own jarvis_gate.py hunks anchor on the same two
    # lists these two names join. test_readpage.py and
    # test_installed_stand_in.py are what prove the order is right. The install
    # block half is chatbot-limits-hud.patch above, which must stay where it is.
    #
    # Needs jarvis_chatbot_limits.py copied in (it is in SHIPPED below) and
    # chatbot.patch's jarvis_chatbot_api.py; without them, or on any error, the
    # banner says so and the route is simply not there.
    'chatbot-limits.patch'
    # The ADDRESSES of the owner's accounts (the owner's decision of 2026-10-06,
    # CLAUDE.md: "anything needing a key or a sign-in should be settable in the
    # Jarvis app itself, desktop only, stored under rule 3"): GET and POST
    # /api/accounts/addresses - the mail server, its port and mailbox, the
    # sending server, its port and how the email is encrypted, the Home
    # Assistant address and the calendar's CalDAV address. TWO hunks in
    # jarvis_hud.py, each sitting on a line web-search.patch wrote (its own GET
    # block's 503 return, and its POST block's own return), so it goes after
    # web-search.patch and touches nothing any later patch rewrites. It carries
    # ADDRESSES ONLY: POST refuses every name but the eight, so no route here
    # can put a key, a password, a token or the private calendar link in a
    # plain-text file (rule 3). Needs jarvis_accounts.py copied in (it is in
    # SHIPPED below); without it the routes answer 503 and carry on.
    'accounts.patch'
    # The gate's risk table held draft_email TWICE: the owner's own original
    # line ("a draft is not a sent message", rated local) and draft-email.patch's
    # row ("saves the draft ... to your own Drafts folder", rated outbound -
    # which is right, because saving a draft goes to the mail server). Python
    # keeps the LAST of two equal keys, so outbound won today; but only by luck
    # of ordering, and the natural cleanup - deleting the later line - would
    # have made an email draft swipe-approvable with nobody noticing, because
    # the two had already collapsed into one key in the file. This removes the
    # stale original line, so there is one row, the right one, on any reading.
    # Tested by test_gate_risk_rows.py; the apply itself is proven by this
    # script's dry run, as for every patch here.
    'gate-risk-rows.patch'
    # "Look at this" can hand the owner the CLEANED picture of the look, for the
    # question box (the owner's decision of 2026-10-07;
    # .dsh-scratch/SCREEN-ATTACH-DESIGN.md): ONE install block in jarvis_hud.py,
    # whose context is tutorials.patch's own block (the last one before
    # `_loopback_companion`), so it goes last, like every new patch. Its wrapper
    # takes over POST /api/screen so the request body is read once, and hands
    # every other verb to jarvis_screen.handle_post - so it MUST come after
    # screen.patch, whose route it wraps. Needs jarvis_screen_attach.py copied
    # in; without it, or on any error, the banner says so and a look is exactly
    # what it was before (the words only, no picture).
    'screen-attach.patch'
)

# --- every module this repository ships WHOLE ------------------------------
#
# Copied beside jarvis_hud.py by step 3 below, every run, by content: a copy
# that already matches is left alone, an older one is backed up and replaced.
# backend\_where.py has the same list (SHIPPED) and
# backend\test_shipped_modules.py fails if the two differ, or if any module a
# shipped file or a patch imports is neither here nor explicitly accounted
# for. That test exists because this list fell behind twice: jarvis_agent.py
# was shipped while the seven tool modules it imports were not, so every tool
# quietly said "unavailable"; and the rebuilt modules were shipped by nothing
# at all, so fixes made to them here never reached the PC.
#
# No patch touches any file in this list (the test checks that too), so the
# order of copying and patching does not matter.
$SHIPPED = @(
    # --- the ten rebuilt modules (backend\rebuilt\) ---
    # The originals were lost; these were rebuilt from the patches, the API
    # document and the config. Forward slashes: a path on Windows and Linux
    # alike. Each lands beside jarvis_hud.py, never in a "rebuilt" folder.
    'rebuilt/jarvis_compute.py'
    'rebuilt/jarvis_events.py'
    'rebuilt/jarvis_framework.py'
    'rebuilt/jarvis_initiative.py'
    'rebuilt/jarvis_memory.py'
    'rebuilt/jarvis_power.py'
    'rebuilt/jarvis_recall.py'
    'rebuilt/jarvis_router.py'
    'rebuilt/jarvis_sleep.py'
    'rebuilt/jarvis_voice.py'    # also needed by "Train my voice" (voice-enroll.patch)
    # --- modules the patches call ---
    'jarvis_intake.py'           # memory-intake.patch
    'jarvis_feedback.py'         # feedback.patch
    'jarvis_skill_discovery.py'  # skill-suggest.patch
    'jarvis_speed.py'            # speed-record.patch
    'jarvis_owned_tables.py'     # documents-owned.patch
    'jarvis_agent.py'            # tool-calling-wiring.patch; updated for skill-suggest
    'jarvis_voice_enroll.py'     # voice-enroll.patch ("Train my voice")
    'jarvis_speech.py'           # voice-503.patch; sends the status shape the phone reads
    # --- task controls, notes, power (2026-09-23) ---
    'jarvis_task_control.py'     # task-control.patch
    'jarvis_note_capture.py'     # note-capture.patch
    'jarvis_power_switch.py'     # power-mode.patch
    # --- end task controls ---
    'jarvis_wakeword.py'         # "hey Jarvis": jarvis_speech.py calls it for wake-word clips
    'jarvis_token_store.py'      # token-store.patch; the pairing token in Credential Manager
    'jarvis_second_card.py'      # second-card.patch; the second graphics card's switches
    'jarvis_wiki.py'             # wiki.patch; the wiki builder (the second card, or the big model)
    'jarvis_big_model.py'        # big-model.patch; the big model (slow) with colibri, background jobs only
    'jarvis_turn.py'             # voice-turn.patch: Smart Turn, "finished, or only paused?"
    'jarvis_wakebank.py'         # other voices' "hey Jarvis" (numbers): the owner's wake-word verifier trains against it
    'jarvis_stopword.py'         # the "stop" word's numbers: jarvis_wakeword.spot_stop, to interrupt Jarvis while it talks
    'jarvis_local_http.py'       # HTTP to this PC's own services (Ollama, Joplin, the second card) never through a proxy
    'jarvis_child_env.py'        # what the second Ollama and colibri inherit: an allowlist, so no token or key goes with them
    'jarvis_voices.py'           # voices.patch: custom voices (ZipVoice on the processor); jarvis_speech.say() asks it first
    'jarvis_f5_worker.py'        # the better voice (F5-TTS) as its own program on the second card; jarvis_voices.py starts it
    'jarvis_kokoro.py'           # which Kokoro voice pack is installed (v0.19 or v1.0), its voices BY NAME, the pinned v1.0 download; jarvis_voices.py imports it, no patch. Upgrade: backend\README.md "Upgrade the voice pack to Kokoro v1.0"
    'jarvis_bakeoff.py'          # the voice upgrades' bake-off: the owner runs it by hand (py -3 jarvis_bakeoff.py); nothing imports it
    'jarvis_learning_switch.py'  # learning-asks.patch: turning learning on raises an approval card
    'jarvis_voicebank.py'        # other people's voices (numbers only): the voice check's comparison step, jarvis_voice.cohort_for
    'jarvis_voice_flow.py'       # voice-flow.patch: interrupting by talking, the delay in numbers, the "One moment." clip; jarvis_speech.py calls it
    'jarvis_mouth.py'            # the animals' mouths timed by Kokoro itself (a "jmth" chunk in say()'s WAV); jarvis_speech.py calls it, no patch. One-time step: backend\README.md "Mouths that match the words"
    'jarvis_chat_log.py'         # chat-history.patch: chat history kept on this PC, encrypted
    'jarvis_paste_guard.py'      # feasibility I115, "Paste guard": masks a pasted password, PIN or one-time code before it is written to the encrypted database
    'jarvis_auto_learn.py'       # auto-learn.patch: facts from the owner's own words saved without a card
    'jarvis_sensitive.py'        # the sensitive-topic check jarvis_auto_learn.py asks: word lists, shapes, the local model
    'jarvis_past.py'             # past-recall.patch: questions about the past also get retired facts, labelled
    'jarvis_entities.py'         # the entity layer's optional local-model pass (off by default); jarvis_auto_learn.py calls it
    'jarvis_profiles.py'         # hardware.patch: the three setups' arithmetic, words and one-line command (no I/O)
    'jarvis_hardware.py'         # hardware.patch: finding the cards, the steps, making a tuned model, measuring
    'jarvis_scrub.py'            # log-scrub.patch: passwords, keys and the token kept out of backend.log
    'jarvis_schedule.py'         # schedule.patch: the one scheduler - timers, alarms, reminders, the to-do list
    'jarvis_quick.py'            # schedule.patch: timers and reminders answered without the AI model
    'jarvis_settings_registry.py' # "open"/"adjust" any setting by voice or chat, 2026-09-27; jarvis_quick.py (above) calls it, no patch of its own
    'jarvis_standby_schedule.py' # the standby schedule ("standby from 01:00 to 07:00"): a kind of job on the one scheduler, no patch
    'jarvis_backoff.py'          # briefing.patch: offers nobody asked for - a few at most, not mid-chat, a "no" heard
    'jarvis_briefing.py'         # briefing.patch: the morning briefing, a kind of job on the one scheduler
    'jarvis_reach.py'            # reach.patch: "What Jarvis can reach", written from the settings, never by the model
    'jarvis_owner_check.py'      # owner-check.patch: Windows Hello for risky approvals from this PC, and the approval stamp
    'jarvis_manner.py'           # manner.patch: warm and brief, or plain - the wording of answers only
    'jarvis_card_words.py'       # approval-notice.patch: every approval card's plain title, and what Jarvis says aloud about a card
    # --- the tools jarvis_agent.py offers the model ---
    # Each is imported inside a try, so a missing one never stops anything:
    # the tool just answers "unavailable". Copying one in does not switch it
    # on: the model is offered a tool only when [tools].enabled in
    # jarvis-framework.toml names it, and every action it takes still goes
    # through the approval gate.
    'jarvis_research.py'         # tool "github_search": is there already a library for this?
    'jarvis_ui_control.py'       # tool "control_computer": reading and clicking other windows
    'jarvis_android_control.py'  # tool "control_phone": the phone over adb
    'jarvis_browser_control.py'  # tool "browser_control": a real browser, via Playwright
    'jarvis_calendar.py'         # tool "calendar_read"
    'jarvis_email.py'            # tool "email_check"
    'jarvis_mail_mask.py'        # hides one-time codes and sign-in links in everything jarvis_email.py reads
    'jarvis_email_send.py'       # tool "send_email": ONE email per approval card; email-send.patch
    'jarvis_email_draft.py'      # tool "draft_email": ONE draft per approval card, saved to Drafts only, never sent; draft-email.patch
    'jarvis_inbox_tidy.py'       # tool "tidy_inbox": archive, star, mark as read or move to Trash, ONE card listing every email, 10 minutes to Undo, no permanent delete; inbox-tidy.patch
    'jarvis_energy.py'           # what one answer cost the card (jarvis_agent.py records a row at the end of a turn; off by default)
    'jarvis_injection.py'        # the "sneaky instruction" table (jarvis_agent._TurnWatch.took_in turns a hit into a card flag; advisory only)
    'jarvis_notes.py'            # tool "notes_search"; carries the token-in-an-error fix
    'jarvis_home.py'             # tools "home_read" and "home_control": Home Assistant
    'jarvis_search.py'           # tool "web_search" (SearXNG, DuckDuckGo, Exa, Tavily or Brave) and its settings; web-search.patch
    'jarvis_accounts.py'         # the ADDRESSES of the owner's accounts (mail server, sending server, Home Assistant, CalDAV) in accounts.json beside web-search.json; accounts.patch. ADDRESSES ONLY - never a key, password or token (rule 3)
    # --- Stop everything (2026-09-25) ---
    'jarvis_stop_all.py'         # stop-all.patch: POST /api/stop_all, and the hook other features register with
    'jarvis_tellme.py'           # "tell me when ..." (an email from someone, a device changing): a kind of job on the one scheduler, no patch; NOT a model tool
    # --- focus sessions (focus.patch) ---
    'jarvis_front.py'            # what is in front on this PC: the one front-window reader focus sessions and "Watch with me" share (split out of jarvis_focus.py, 2026-09-28); no patch
    'jarvis_focus.py'            # focus sessions: a timer plus Quiet, drifts named out loud on this PC, counts only
    # --- what asks first (asks-first.patch) ---
    'jarvis_asks_first.py'       # "What asks first": every action and whether it asks; stricter from either app, looser on the PC only; lights without a card
    # --- folders Jarvis may look in (documents.patch) ---
    'jarvis_documents.py'        # "Folders Jarvis may look in": the list, the my_files tool (find, search, read PDFs and Word files in parts), the Notion import
    # --- the words in a picture (2026-09-26) ---
    'jarvis_ocr.py'              # reads the words in a picture (and where each one sits) with Windows' own text recognition, on this PC, inside Jarvis through the pywinrt packages or else through PowerShell; jarvis_agent.py marks them as outside text; no patch
    # --- screen safety (2026-09-29): secrets in a picture of the screen are painted black before anything reads it ---
    'jarvis_secret_rules.py'     # GENERATED (tools/gen_secret_rules.py): gitleaks's rule data (MIT), what a key, token or password looks like; no patch
    'jarvis_secrets.py'          # finds secrets in the words read from a picture (gitleaks + Presidio patterns, a card must pass the check digit) and works out the black boxes; no patch
    'jarvis_picture.py'          # paints SOLID BLACK boxes on a picture and hands on only a checked one; jarvis_screen.clean_picture is the door; no patch
    'jarvis_chat_picture.py'     # the pictures the owner ATTACHES to a chat get the same black-out (jarvis_screen.clean_picture) before any model sees them; one that cannot be checked is withheld and the answer says so; jarvis_agent.py calls it, no patch
    # --- plug-in programs (MCP), reached only through more_tools("plugins") ---
    'jarvis_mcp.py'              # read-only tools from programs on this PC you list under [mcp]; stdio only; every call asks
    # --- the crisis help line (2026-09-27) ---
    'jarvis_wellbeing.py'        # the word check, the fixed US help message, the note to the model; jarvis_agent.py and jarvis_intake.py call it, no patch needed for the safety behaviour itself
    # --- the smartwatch notifications setting (2026-09-27) ---
    'jarvis_watch_notify.py'     # off by default; ON is one approval card, watch_notifications_enable; OFF is instant
    # --- "Things you can say" (2026-09-27, sayable.patch) ---
    'jarvis_sayable.py'          # sayable.patch: the fixed list of real sentences Jarvis answers without the model
    # --- Backups (2026-09-27, backup.patch) ---
    'jarvis_backup.py'           # one locked backup file with a recovery code shown once; restore is one card plus Windows Hello
    # --- music and video control (2026-09-27, media.patch) ---
    'jarvis_media.py'            # media.patch: play/pause/next/previous and "what's playing", no card, no model tool
    # --- "tell me when this page changes" (a source of jarvis_tellme.py, no patch of its own) is IN jarvis_tellme.py above
    # --- news headlines in the morning briefing (2026-09-27, news.patch) ---
    'jarvis_news.py'             # news.patch: RSS/Atom feed addresses the owner adds, headlines only, one card per feed
    # --- data health in the preflight (feasibility I97, data-health.patch) ---
    'jarvis_data_health.py'      # do the chat history and memory databases open, is there disk space, do the settings files parse - read-only, WARN never fix
    # --- "Check for tool updates" (tool-updates.patch) ---
    'jarvis_tool_updates.py'     # tool-updates.patch: reports outdated Python packages, Rust crates and pinned GitHub tools; one card ever, never installs anything
    # --- "Who are you?" fixed answers (feasibility I131, 2026-09-27) ---
    'jarvis_identity.py'         # fixed text, no model, no romance; jarvis_quick.py (already SHIPPED, above) calls it - no patch of its own
    # --- "Where this came from" and the quote check (answer-sources.patch) ---
    'jarvis_sources.py'          # answer-sources.patch: each reading tool's own result this turn, by reference; the quote check; GET /api/chat/sources
    # --- the app builder's workspace (2026-09-28, docs/APP-BUILDER-DESIGN.md milestone A) ---
    'jarvis_app_workspace.py'    # app projects, a separate copy per task, one card with the full diff before a merge; runs nothing; no tool yet
    'jarvis_apps.py'             # apps-in-projects.patch: an app inside Projects - its tasks, a task's whole change, Merge (ONE risky card) and Discard; a change is pasted in on the PC only; runs nothing
    # --- "Goals with one card per step" (goals.patch) ---
    'jarvis_goals.py'            # goals.patch: a goal's own plan and weekly check-in; accepting sets up the check-in with no card (a plain repeat); every acting step still asks through ordinary chat
    # --- "One card, several steps" (plan-gate.patch) ---
    'jarvis_plan.py'             # plan-gate.patch: the plan card's own module - SWITCHED OFF until tools/tool_eval's real results clear the bar; see its own docstring
    # --- reading phone notifications (2026-09-28, phone-notifications.patch) ---
    'jarvis_phone_notifications.py'  # off by default; ON is one approval card, phone_notifications_read; OFF is instant; never sees a notification's own text
    # --- the Brain upgrades (2026-09-28, brain-reads.patch) ---
    'jarvis_brain_reads.py'      # brain-reads.patch: GET /api/history/search, /api/memory/fact-history, /api/memory/conversation-facts and /api/pc/help, reads for the apps only
    # --- "remind me next time I talk about X" and "ring my phone" (2026-09-28) ---
    'jarvis_next_time.py'        # a reminder with no time of its own, brought up beside the question; a kind on jarvis_schedule.py, no patch
    'jarvis_find_phone.py'       # "ring my phone": ONE ring_phone event the phone rings for, no card, no patch
    # --- smarter memory dates, "Where did I put ...?" (2026-09-28) ---
    'jarvis_places.py'           # "where is my passport?" answered from the places the owner said, no model; jarvis_quick.py and jarvis_auto_learn.py call it, no patch
    'jarvis_tidy.py'             # the overnight tidy: "Still true?" / "Which is true now?" review cards only, on the one scheduler, only while its switch is on; no patch
    # --- "Better voice" (2026-09-28, no patch of its own) ---
    'jarvis_microwake.py'        # the second "hey Jarvis" detector (microWakeWord), off unless the owner chooses both; jarvis_speech.py calls it
    # --- Today cards (2026-09-28) ---
    'jarvis_today.py'            # the owner's own words on the Today part of both apps, at a time on chosen days; a kind on jarvis_schedule.py, no card, no patch
    'jarvis_photo_remind.py'     # "Photo to reminder": the dates in a picture, read on this PC and PROPOSED, never set by itself (photo-reminder.patch)
    # --- "PC help" (2026-09-28, no patch of its own) ---
    'jarvis_pc_help.py'          # "why is my PC slow?", "how full is my disk?" and three more, read-only, no model; GET /api/pc/help through jarvis_brain_reads.py
    # --- Tutorials and the FAQ (2026-10-05) ---
    'jarvis_tutorials.py'        # the owner's own request: one catalogue for both apps and the reading progress kept on the PC (tutorials.patch); no gate line, no card, no tool
    # --- "Smarter answers" (2026-09-28, no patch of its own) ---
    'jarvis_claims.py'           # "I've done it" when nothing was done: one plain line at the end of the answer; jarvis_agent.py calls it
    # --- "Bring in chats from ChatGPT, Claude or Gemini" (2026-09-28) ---
    'import_history.py'          # the old-chats importer itself; still runs from this repository on the command line too
    'jarvis_history_import.py'   # history-import.patch: the Brain's button runs import_history.run() in the background; every fact waits for a yes
    # --- "Widgets you describe" (2026-09-28, no patch of its own) ---
    'jarvis_widgets.py'          # a widget as a small checked description (never code): the model's JSON from a fixed menu; /api/widgets routes, switched on by jarvis_brain_reads.py
    # --- talking to an AI chatbot for the owner (2026-09-28): the core and the Gemini adapter; routes in chatbot-routes.patch, the gate's _RISK line in chatbot.patch ---
    'jarvis_chatbot.py'          # the driver, the last check before every message, one card per conversation
    # --- Projects, build steps 1 and 2 (projects.patch, 2026-09-28) ---
    'jarvis_projects.py'         # projects.patch: projects, life benchmarks and their numbers, projects.db; jarvis_quick.py (already SHIPPED) calls it for "log 5 km run"
    'jarvis_forecast.py'         # the pure finish-time range ("about 6 to 9 weeks") jarvis_projects.py and jarvis_goals.py read; no patch (JARVIS-API section 101)
    'jarvis_chatbot_gemini.py'   # the Gemini website adapter: a visible browser window, typed at a person's pace, stops at any captcha or sign-in page; needs Playwright (not installed by this script)
    'jarvis_chatbot_routes.py'   # chatbot-routes.patch: GET /api/chatbot/status, POST /api/chatbot/start (ONE card), /stop and /limits (a new card)
    # --- more chatbot websites, in a visible window the same way (2026-09-28, "the chatbot driver becomes versatile"); reached through chatbot-routes.patch ---
    'jarvis_chatbot_web.py'      # what every website adapter shares: the visible window, the typing, the host lock, every "needs you" page, sign-in and self-check; jarvis_chatbot.py loads it, and it loads the site files below
    'jarvis_chatbot_chatgpt.py'  # ChatGPT (chatgpt.com): a thin site file - its selectors, host and words; its own profile and spare account
    'jarvis_chatbot_claude.py'   # Claude (claude.ai): a thin site file
    'jarvis_chatbot_copilot.py'  # Microsoft Copilot (copilot.microsoft.com): a thin site file
    'jarvis_chatbot_perplexity.py' # Perplexity (www.perplexity.ai): a thin site file; its listed sources are read as text, never opened
    'jarvis_chatbot_deepseek.py' # DeepSeek (chat.deepseek.com): a thin site file
    'jarvis_chatbot_grok.py'     # Grok (grok.com): a thin site file
    'jarvis_chatbot_lechat.py'   # Le Chat by Mistral AI (chat.mistral.ai): a thin site file
    'jarvis_chatbot_metaai.py'   # Meta AI (www.meta.ai): a thin site file
    'jarvis_chatbot_api.py'      # the API adapters (OpenAI, DeepSeek, Mistral, xAI, OpenRouter, Groq): a key from Credential Manager, sent to that one host only; no key, no conversation
    'jarvis_chatbot_limits.py'   # chatbot-limits.patch: the monthly money limits and the price list, set from the PC's app - a raise is ONE card plus Windows Hello, a lowering and a price correction are not; GET/POST /api/chatbot/money, PC only
    'jarvis_chatbot_local.py'    # "a second AI on this PC": another Ollama model, loopback only, never a cloud model; one card allows only the everyday model, two cards any model on the second card
    # --- looking at the screen (2026-09-28/29): the session rules, the Windows readers and the routes (screen.patch) ---
    'jarvis_screen_win.py'       # the Windows half of "Look at this" and "Watch with me": what is in front (password box, capture protection, lock), the picture (in memory, never on disk) and the window's own text; copied before jarvis_screen.py
    'jarvis_screen.py'           # "Look at this" and "Watch with me": session states, pause rules, caps, the Never look at list, GET/POST /api/screen and /api/screen/never-look (screen.patch)
    'jarvis_screen_picture.py'   # slow picture mode for one graphics card: a small picture model on the PROCESSOR in its own copy of Ollama; off by default, ON is one card, OFF is instant; secrets blacked out first or no picture; GET/POST /api/screen/picture (routes in jarvis_screen.py, gate lines in screen-picture.patch)
    # "look at this" can hand back the CLEANED picture of the look, for the question box
    # (the owner's decision of 2026-10-07, .dsh-scratch/SCREEN-ATTACH-DESIGN.md;
    # screen-attach.patch installs its wrapper round jarvis_screen.py's route). It takes
    # no picture of its own: the look is jarvis_screen.Screen._grab's, in its one order,
    # and the bytes handed on are jarvis_picture.clean's own output - never the capture.
    'jarvis_screen_attach.py'
    # --- the headless browser, Obscura (2026-09-29, browser-engine.patch) ---
    'jarvis_obscura.py'          # the driver for Obscura, a browser with no window: started over standard input/output (no port), --stealth always, no proxy, allow-listed tools only, one program at a time, hard limits; the owner's install line and check
    'jarvis_browser_engine.py'   # which browser Jarvis uses (visible or headless), the switch (off by default, ON is one card), the mode rule, GET/POST /api/browser/engine (browser-engine.patch)
    'jarvis_form_review.py'      # "fill in the form, show me, then send it": the second card (browser_form_submit), the picture of the page held in memory only while that card waits, GET /api/form-review/picture (form-review.patch)
    'jarvis_chatbot_compare.py'  # "Ask several and compare": 2 or more chatbots, ONE card listing every one, one after another, ONE summary; routes in jarvis_chatbot_routes.py
    # --- Jarvis Live (2026-09-28): talking back and forth; the camera off until the second card passes the photo test ---
    'jarvis_live.py'             # the Live session (start, stop, time limit, quiet, pauses), the source=live rules jarvis_speech follows, GET/POST /api/voice/live (live.patch)
    'jarvis_live_photo_test.py'  # the camera's photo test: run once, when the 12 GB card is in; a pass is what lets the camera switch appear on the phone
    # --- "Forget a time frame" (2026-09-28): a checked list, ONE card, 10 minutes to undo ---
    'jarvis_forget_range.py'     # forget-range.patch: GET/POST /api/memory/forget_range, /preview and /undo; jarvis_quick.py (already SHIPPED) calls it for "forget what you learned last week"
    # --- "Chat with customer support for me" (2026-09-28): Groupon first; the details card, an offer card per offer, identity checks and "are you a bot?" handed to the owner ---
    'jarvis_support.py'          # the support chat's rules: the details card, the last check before every message, offers, the transcript; routes in jarvis_chatbot_routes.py, risk lines in support-chat.patch
    'jarvis_support_widget.py'   # the support window on the chatbot websites' shared base: the company's help page, its chat widget (Zendesk, Intercom, LivePerson, Gorgias, Freshchat, Salesforce, unbranded); needs Playwright (not installed by this script)
    # --- "Solve it here" (2026-09-28): a captcha or sign-in page handed to the owner's phone ---
    'jarvis_handoff.py'          # one picture at a time of the ONE paused browser window, and the owner's own taps and typing to it, only while paused there; routes in jarvis_chatbot_routes.py
    # --- the sun, the moon and the weather behind the animals (2026-09-28, sky.patch) ---
    'jarvis_sky.py'              # sky.patch: GET/POST /api/sky - show the sun and moon, the town (PC only), the weather source (Open-Meteo ON is one card)
    'jarvis_sky_places.py'       # the towns jarvis_sky.py finds a place in, carried on this PC (GeoNames, CC BY 4.0) - never looked up online
    # --- Animal options (2026-09-28, animal.patch) ---
    'jarvis_animal.py'           # animal.patch: GET/POST /api/animal - "Keep the animal still" and the behaviour switches, shared by both apps, no card
    # --- pairing a phone by QR code, a key per device (2026-09-28, devices.patch) ---
    'jarvis_devices.py'          # devices.patch: every request's key checked (a device key never falls back to the shared one), the registry of key hashes, ONE pairing at a time, the pair_device card (PC only, Windows Hello), Remove and Retire
    # --- "Quiz me on a text" (2026-09-30, quiz.patch) ---
    'jarvis_quiz.py'             # quiz.patch: questions written from a pasted text and answers marked against the passage, by the local model only; in memory only, no card, never learned from
    'eval_quiz_grader.py'        # run by hand on the PC: checks the quiz's marking against the real local model and writes quiz_grader_results.json beside jarvis_quiz.py (quiz_grader_cases.json is copied in step 3b)
    # --- "Review decks" (2026-09-30, decks.patch) ---
    'jarvis_decks.py'            # decks.patch: kept quiz questions studied again on a spaced schedule (py-fsrs), sealed in study.db under their own key; the owner rates each card, no model is called; the one quiet `review` scheduler kind
    # --- "Spending summaries" (2026-09-30, spending.patch) ---
    'jarvis_spending.py'         # spending.patch: totals from a bank CSV/Excel export the owner dropped in a listed folder (the my_spending tool), a table shown on screen only, the layout box (PC only) and the categories; every number from code, the model's one sentence checked against the table
    'jarvis_money_parse.py'      # money, dates and bank-file headers read exactly (Decimal, whole cents); shared by jarvis_spending.py and the retirement what-if to come
    # --- "Retirement what-if" (2026-09-30, retirement.patch) ---
    'jarvis_retirement.py'       # retirement.patch: a simplified what-if from numbers the owner typed - 10,000 made-up futures with a fixed seed, answered only as ranges, the disclaimer added by code; plain Python, no numpy; screen-only money
    # --- "Activity heatmap and balance chart" (2026-09-30, progress.patch) ---
    'jarvis_progress.py'         # progress.patch: 12 weeks of days shaded by steps ticked and numbers logged, and a 3-to-8 area balance chart the owner picks; every number from code, no streak, no total score; NOT a model tool (a test fails if anything imports it)
    # --- "Topic controls" (2026-09-30, topics.patch) ---
    'jarvis_topics.py'           # topics.patch: per-topic mode (Learn and use / Use but don't learn / Learn but don't use / Off) - tables in memory.db, sorting by fixed rules with the local model only as an opt-in suggestion, one card (topic_loosen) for turning a private topic back on; the filter itself lives in the rebuilt jarvis_memory.py
    'jarvis_referee.py'          # referee.patch: "This looks done - tick it?" - one card per goal step whose number reached its target, at most three a day, no model, only the owner's tap ticks; a second-card switch (id referee)
    'jarvis_tag_suggest.py'      # tag-suggest.patch: "Suggest tags overnight" - the local model may suggest a tag for a few untagged chats a night, each a card (chat_tag_suggest), filed only on a tap; off by default, turning it on is one card (chat_tags_suggest_on)
    # --- "Quiz me on a YouTube video" (2026-09-30, youtube.patch) ---
    'jarvis_youtube.py'          # youtube.patch: ONE card per YouTube link (youtube_captions_read), then the caption text only is fetched (youtube-transcript-api) and quizzed on as outside text; breaks YouTube's terms, may be blocked; never video or audio
    # --- "Grade this better" (2026-09-30, quiz-cloud.patch) ---
    'jarvis_quiz_cloud.py'       # quiz-cloud.patch: ONE card per request (quiz_cloud_grade) listing exactly what leaves the PC, then one message to the cheapest set-up cloud service (jarvis_chatbot_api.py); never for a private quiz or after a crisis answer
    # --- "Read this page out loud" (2026-10-05, readpage.patch) ---
    'jarvis_readpage.py'         # readpage.patch: the model's read_web_page tool - ONE card per address (read_web_page, tier ask, risky: the PC contacts that one site), then ONE plain GET and the words a reader would see, handed back as outside text; never a link on the page, never a second page, no new dependency
    # --- "Show or hide menus" (2026-09-30, no patch) ---
    'jarvis_menus.py'            # the menus both apps may hide or fold, the feature groups, the never-hideable list and the words; jarvis_quick.py (already SHIPPED) calls it for "hide the finance menu" - no patch, no route, no card
    # --- Per-model thinking levels (2026-10-01, Section 5.5) ---
    'jarvis_thinking.py'         # thinking.patch: setting per model (everyday, second, third), capabilities check, voice fast override, plain words (no card)
    # --- The page `GET /` serves (2026-10-07) ---
    # Not a module: jarvis_hud.py reads it from its own folder at request time,
    # so it has to sit beside the server. It was in the base and in neither
    # SHIPPED list, so the patcher never copied it and the backend answered
    # `GET /` with 500 "jarvis_hud.html is missing from this folder" - which is
    # why the desktop app had never connected on the owner's PC and fell back to
    # its demo data. test_shipped_modules.py keeps this list and _where.py's
    # SHIPPED in step.
    'jarvis_hud.html'            # the HUD page itself: the server hands it to a browser at GET / - no patch, no route of its own
    # --- The five the base carried but this list did not (2026-10-07) ---
    # All five were already in jarvis-backend/ and a SHIPPED module imports each,
    # but none was listed here and no patch delivered any of them - so a backend
    # built from the published base imported a shipped module that imported a
    # file the repository never handed over. test_shipped_modules.py keeps this
    # list and _where.py's SHIPPED in step. See .dsh-scratch/UNSHIPPED-MODULES-REPORT.md.
    'jarvis_arbiter.py'          # the one place that decides whether to interrupt the owner: an attention budget, overflow drained into one daily digest; jarvis_hud.py and jarvis_watch.py import it - no patch
    'jarvis_ledger.py'           # a tamper-evident append-only record of what the assistant did, hashing metadata only so integrity and forgetting do not cancel out; jarvis_hud.py imports it - no patch
    'jarvis_watch.py'            # "tell me what's new on GitHub for the things I care about": pull not push, a repo page treated as text from a stranger; jarvis_hud.py and jarvis_settings_registry.py import it - no patch
    'jarvis_tripwire.py'         # a smoke test for a model swap, deliberately not an eval suite; jarvis_models.py imports it - no patch
    'jarvis_structured.py'       # makes a malformed tool call structurally impossible via Ollama's `format` JSON Schema; jarvis_extract.py imports it - no patch
    # Pulled in by the five above: jarvis_arbiter and jarvis_watch import
    # jarvis_jobs, and jarvis_watch imports jarvis_content_risk.
    'jarvis_jobs.py'             # Long Fuse: work that outlives the conversation; imported by jarvis_arbiter.py and jarvis_watch.py - no patch
    'jarvis_content_risk.py'     # one pipeline for text that arrived from outside; imported by jarvis_watch.py - no patch
)

# The settings file. Installed only where none exists; never overwritten.
$CONFIG_SRC  = 'rebuilt/jarvis-framework.toml'
$CONFIG_NAME = 'jarvis-framework.toml'

# --- the six patches whose fixes are already IN the rebuilt modules --------
#
# Ten of the backend's twenty-six modules were rebuilt after the originals were
# found to exist nowhere, and two of them - jarvis_memory and jarvis_events -
# were rebuilt WITH the fixes these patches make. So on a backend carrying the
# rebuilt modules, six patches cannot apply: their context lines are the
# unfixed code, which no longer exists.
#
# That is correct and expected, and the script still refused the whole run over
# it, applying none of the other fifteen. The owner was blocked by a state this
# repository created.
#
# Four of the six ALSO patch a surviving file, and that half is still needed.
# backend/rebuilt-patches/ holds those halves, split by target file. The other
# two touch only a rebuilt module and are skipped entirely.
$REBUILT_SUPERSEDES = @{
    'memory-safety.patch'     = 'jarvis_memory.py, already in the rebuild'
    'extraction-wiring.patch' = 'jarvis_events.py, already in the rebuild'
    'bitemporal.patch'        = 'jarvis_memory.py, already in the rebuild'
    'embedding-guard.patch'   = 'jarvis_memory.py only - nothing else to apply'
    'event-allowlist.patch'   = 'jarvis_events.py only - nothing else to apply'
    'approval-notice.patch'   = 'jarvis_events.py, already in the rebuild'
}

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PatchDir   = Join-Path $RepoRoot 'backend'
$Stamp      = Get-Date -Format 'yyyy-MM-dd-HHmmss'

# The list above is hand-ordered because the order matters, which means it can
# fall behind the directory - and it did: event-allowlist.patch was written,
# documented in backend/README.md, and never added here, so it silently did
# not get applied. A missing patch produces no error anywhere; it just is not
# there. Checked on every run.
#
# Which list applies: the full patches, or the split halves for a backend
# carrying the rebuilt jarvis_memory.py and jarvis_events.py?
#
# Applying: ALWAYS the split halves, because step 3 below copies the rebuilt
# modules in on every run. This used to be decided by looking at the
# backend's jarvis_memory.py, which went wrong two ways: nothing ever copied
# the rebuilt modules in, so a backend without them got the full list and
# patches aimed at a jarvis_memory.py it did not have; and only jarvis_memory
# was looked at, while two of the six skipped patches are about
# jarvis_events.py.
#
# Reverting: whatever is actually there, told by a marker the rebuild puts in
# its own docstring - in either of the two files, not just one.
$SplitDir = Join-Path $PatchDir 'rebuilt-patches'
$UsingRebuilt = -not $Revert
if ($Revert) {
    foreach ($probeName in @('jarvis_memory.py', 'jarvis_events.py')) {
        $probePath = Join-Path $BackendPath $probeName
        if (-not (Test-Path -LiteralPath $probePath)) { continue }
        $head = Get-Content -LiteralPath $probePath -TotalCount 12 -ErrorAction SilentlyContinue
        if ($head -join "`n" -match 'PART RECOVERED, PART REBUILT') { $UsingRebuilt = $true }
    }
}

$onDisk = @(Get-ChildItem -LiteralPath $PatchDir -Filter '*.patch' -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name)
$unlisted = @($onDisk | Where-Object { $PATCHES -notcontains $_ })
if ($unlisted.Count -gt 0) {
    Write-Host "  FAIL  $($unlisted.Count) patch file(s) exist but are not in this script's list:" -ForegroundColor Red
    foreach ($u in $unlisted) { Write-Host "          $u" -ForegroundColor Red }
    Write-Host "        Add them to `$PATCHES, in the right place - the order is a" -ForegroundColor Cyan
    Write-Host "        dependency order, not alphabetical. See backend/README.md." -ForegroundColor Cyan
    exit 1
}

function Say($msg, $colour = 'Gray') { Write-Host $msg -ForegroundColor $colour }
function Ok($msg)   { Write-Host "  ok    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  skip  $msg" -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# --- what this run did, and how it ends --------------------------------------
#
# Audit 2026-09-30 found runs that ended looking like success after something
# failed (a missing module printed FAIL and carried on, -SkipTests said "Done"
# whatever had happened, no exit code was set at the end), and a message that
# said "NOTHING HAS BEEN CHANGED" after the line endings had been rewritten.
# So: every real problem goes in $script:Problems, everything that touched the
# owner's files is recorded in $script:State, and the run ends in ONE place
# (Finish-Run) that says plainly whether it worked and what to do next.
$script:Problems = New-Object System.Collections.ArrayList
$script:Notes    = New-Object System.Collections.ArrayList
$script:State    = @{
    Changed          = $false   # any real file of the owner's touched yet
    Patching         = $false   # in the middle of changing the patched files (not yet safe to stop)
    Damaged          = $false   # the patched files may be HALF changed right now
    Backup           = $null    # _jarvis-backup-<stamp>
    EndingsBackup    = $null    # _jarvis-backup-<stamp>-endings
    EndingsConverted = $false
    Proven           = $false   # the test suites ran, none failed, none skipped
    StartLine        = $null
}
function Add-Problem($msg, [switch] $Damaged) {
    [void]$script:Problems.Add([string]$msg)
    if ($Damaged) { $script:State.Damaged = $true }
}
function Add-Note($msg)    { [void]$script:Notes.Add([string]$msg) }

# One PowerShell line that puts every file this run backed up back where it
# was. The patch backup goes first and the line-endings backup second, so the
# oldest copy (the owner's own, CRLF) wins where a file is in both.
function Get-RestoreCommand {
    $dirs = @()
    foreach ($d in @($script:State.Backup, $script:State.EndingsBackup)) {
        if ($d -and (Test-Path -LiteralPath $d)) { $dirs += ("'" + ($d -replace "'", "''") + "'") }
    }
    if ($dirs.Count -eq 0) { return $null }
    $dest = "'" + ($BackendPath -replace "'", "''") + "'"
    return ('foreach ($d in ' + ($dirs -join ',') + ') { Get-ChildItem -LiteralPath $d | Copy-Item -Destination ' + $dest + ' -Recurse -Force }')
}

# The end of every run. Never returns.
function Finish-Run {
    param([string] $Kind = 'apply')
    $bar = ('=' * 68)
    Write-Host ""
    if ($script:Problems.Count -gt 0) {
        Write-Host $bar -ForegroundColor Red
        Write-Host " DONE WITH PROBLEMS - do not trust this update yet" -ForegroundColor Red
        Write-Host $bar -ForegroundColor Red
        $n = 0
        foreach ($p in $script:Problems) {
            $n++
            Write-Host "  $n. $p" -ForegroundColor Red
        }
        Write-Host ""
        $restore = Get-RestoreCommand
        if ($script:State.Damaged) {
            Write-Host "Some of your backend files WERE changed before this went wrong, and the" -ForegroundColor Yellow
            Write-Host "patched files may be HALF updated." -ForegroundColor Yellow
            if ($script:State.EndingsConverted) {
                Write-Host "That includes their line endings (CRLF to LF)." -ForegroundColor Yellow
            }
            Write-Host "Jarvis may not start correctly until that is fixed. Do NOT start it yet." -ForegroundColor Yellow
            if ($restore) {
                Write-Host "To put every file back exactly as it was, paste this one line:" -ForegroundColor Cyan
                Write-Host "    $restore" -ForegroundColor Cyan
                Write-Host "Then, if Jarvis is running, close it and start it again." -ForegroundColor Cyan
            }
        } elseif ($script:State.Changed) {
            Write-Host "Your backend files WERE changed by this run, and the patches themselves are on;" -ForegroundColor Yellow
            Write-Host "the problems above are about the rest. Close Jarvis and start it again only" -ForegroundColor Yellow
            Write-Host "once you have read them." -ForegroundColor Yellow
            if ($restore) {
                Write-Host "To undo the whole update instead, paste this one line:" -ForegroundColor Cyan
                Write-Host "    $restore" -ForegroundColor Cyan
            }
        } else {
            Write-Host "None of your backend files were changed by this run." -ForegroundColor Green
        }
        if ($script:Notes.Count -gt 0) {
            foreach ($t in $script:Notes) { Write-Host "  note: $t" -ForegroundColor Yellow }
        }
        Write-Host ""
        Write-Host "What to do: read the problem list above, fix the first one, run the" -ForegroundColor Cyan
        Write-Host "same command again. If it is not clear, send back the log file." -ForegroundColor Cyan
        if ($script:RunLog) { Write-Host "Log: $($script:RunLog)" -ForegroundColor Cyan }
        exit 1
    }
    Write-Host $bar -ForegroundColor Green
    if ($Kind -eq 'revert')            { Write-Host " FINISHED - the patches were taken off" -ForegroundColor Green }
    elseif ($script:State.Proven)      { Write-Host " ALL DONE - the backend is patched and proven" -ForegroundColor Green }
    else                               { Write-Host " DONE - no problems, but NOT fully proven (see below)" -ForegroundColor Yellow }
    Write-Host $bar -ForegroundColor Green
    foreach ($t in $script:Notes) { Write-Host "  note: $t" -ForegroundColor Yellow }
    Write-Host ""
    if ($script:State.Changed) {
        Write-Host "Restart Jarvis (close it and start it again) so it uses the new files." -ForegroundColor Cyan
    }
    if ($script:State.StartLine) {
        Write-Host "Start it (one line), and watch its 'token' line - it should say Windows Credential Manager:" -ForegroundColor Cyan
        Write-Host "    $($script:State.StartLine)" -ForegroundColor Cyan
    }
    if ($script:State.Backup -and (Test-Path -LiteralPath $script:State.Backup)) {
        Write-Host "Your files from before this run are in:  $($script:State.Backup)" -ForegroundColor Gray
    }
    if ($script:State.EndingsBackup -and (Test-Path -LiteralPath $script:State.EndingsBackup)) {
        Write-Host "Your files from before the line-endings change:  $($script:State.EndingsBackup)" -ForegroundColor Gray
    }
    Write-Host "Nothing deletes old backups for you. After a good run you can delete the old" -ForegroundColor Gray
    Write-Host "_jarvis-backup-* folders inside the backend folder; keep the newest one for now." -ForegroundColor Gray
    if ($script:RunLog) { Write-Host "Log: $($script:RunLog)" -ForegroundColor Gray }
    exit 0
}

# Any error nobody planned for (a locked file, a full disk) lands here instead
# of scrolling past as a red block with no hint what state the files are in.
trap {
    Write-Host ""
    Write-Host "  FAIL  The script stopped unexpectedly: $($_.Exception.Message)" -ForegroundColor Red
    if ($script:State.Patching) {
        Add-Problem "The script stopped unexpectedly: $($_.Exception.Message)" -Damaged
    } else {
        Add-Problem "The script stopped unexpectedly: $($_.Exception.Message)"
    }
    Finish-Run
}

# --- which Python ------------------------------------------------------------
#
# NOT simply `python`. On a fresh Windows 11 that name is a Microsoft Store
# shortcut (an "App Execution Alias" in ...\WindowsApps\) that does not run
# Python at all: it prints "Python was not found" and exits 9009. This script
# used to run the tests with whatever `python` was, so on such a PC every
# suite would have "failed", and the summary said a failure is a real
# finding - when all it meant was "Python is not installed".
#
# So each candidate is actually RUN, and must print its own real path. `py -3`
# first: the launcher the python.org installer puts in C:\Windows is never the
# Store shortcut. Returns $null when there is no working Python.
function Find-Python {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        foreach ($cand in @('py -3', 'python', 'python3')) {
            $parts = $cand -split ' '
            $cmd = Get-Command $parts[0] -CommandType Application -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if (-not $cmd) { continue }
            $pre = @()
            if ($parts.Count -gt 1) { $pre = @($parts[1..($parts.Count - 1)]) }
            $out = @(& $cmd.Source @pre -c "import sys; print(sys.executable); print('%d.%d' % sys.version_info[:2])" 2>$null)
            if ($LASTEXITCODE -ne 0 -or $out.Count -lt 2) {
                if ($cmd.Source -match '\\WindowsApps\\') {
                    $script:PythonStubSeen = $cmd.Source
                }
                continue
            }
            $exe = "$($out[0])".Trim()
            if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { continue }
            return @{ Exe = $exe; Version = "$($out[1])".Trim(); Via = $cand }
        }
    } finally {
        $ErrorActionPreference = $prev
    }
    return $null
}

# Why there is no Python, in words a person can act on.
function Explain-NoPython {
    if ($script:PythonStubSeen) {
        Say "  The only 'python' on this PC is the Microsoft Store shortcut:" Yellow
        Say "    $($script:PythonStubSeen)" Yellow
        Say "  It is not Python. Install the real one (one line, then open a NEW" Cyan
        Say "  PowerShell window so it is found):" Cyan
    } else {
        Say "  No Python was found on this PC. Install it (one line, then open a" Cyan
        Say "  NEW PowerShell window so it is found):" Cyan
    }
    Say "    winget install Python.Python.3.12" Cyan
    Say "  Then run this script again." Cyan
}
$script:PythonStubSeen = $null

# --- where is everything -----------------------------------------------------

if (-not (Test-Path -LiteralPath $BackendPath)) {
    Bad "No folder at: $BackendPath"
    Say ""
    Say "Point it at the folder holding jarvis_hud.py:" Cyan
    Say "    powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath `"D:\your\path`"" Cyan
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $BackendPath 'jarvis_hud.py'))) {
    Bad "That folder exists but has no jarvis_hud.py in it: $BackendPath"
    Say "  Point it at your own Jarvis backend folder - the one with jarvis_hud.py in it -" Yellow
    Say "  not at this repository, and not at OpenJarvis (an unrelated project with a similar name)." Yellow
    Say "  docs\INSTALL.md, step 1.3, says where the backend files come from." Yellow
    exit 1
}

# `patch` is not on a stock Windows box; `git apply` is, if Git is installed.
$UseGit = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
if (-not $UseGit -and -not (Get-Command patch -ErrorAction SilentlyContinue)) {
    Bad 'Neither git nor patch is on PATH, and one of them is needed.'
    Say "  Install Git for Windows: https://git-scm.com/download/win" Cyan
    exit 1
}

# --- a log of this run -------------------------------------------------------
#
# Everything this script prints also goes to a file (ease-of-use audit
# 2026-09-27, #8i: the only record of a run used to be a window that was
# closed afterwards). One file per run, in _jarvis-logs inside the backend
# folder, beside the _jarvis-backup-<date> folders. It holds what is printed
# here and nothing else - no token or key is ever printed by this script.
# The transcript ends when this PowerShell process does (the INSTALL line
# runs the script in a process of its own, with -File).
$RunLog = $null
try {
    $logDir = Join-Path $BackendPath '_jarvis-logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $RunLog = Join-Path $logDir "apply-patches-$Stamp.txt"
    Start-Transcript -LiteralPath $RunLog -Append | Out-Null
} catch {
    $RunLog = $null
}

Say ""
Say "Backend : $BackendPath"
Say "Patches : $PatchDir"
Say "Tool    : $(if ($UseGit) { 'git apply' } else { 'patch' })"
if ($RunLog) { Say "Log     : $RunLog (a copy of everything printed here)" }
else { Say "Log     : none - the log file could not be started, so copy this window if you need a record" Yellow }

# --- a backend folder inside ANOTHER git repository --------------------------
#
# `git apply` behaves differently inside a repository than outside one: it
# applies the repository's own line-ending rules (.gitattributes, autocrlf) to
# the files it reads. The rehearsal runs on a copy in %TEMP% - outside any
# repository - so a real run inside one could behave differently from the
# rehearsal that was meant to predict it (reproduced 2026-09-30 with a
# `*.py text eol=crlf` attribute: the same patch applied inside the repository
# and was refused outside it). So every git call here is told to stop looking
# for a repository at the folder ABOVE the backend (GIT_CEILING_DIRECTORIES):
# rehearsal and real run then behave the same. And after the real run the
# result is checked again (Test-StackReverses).
$script:GitCeiling = $null
if ($UseGit) {
    $resolvedBackend = (Resolve-Path -LiteralPath $BackendPath).Path
    $ceil = Split-Path -Parent $resolvedBackend
    if ($ceil) { $script:GitCeiling = $ceil }
    $prevEapG = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $topOk = $false
    $topOut = @()
    try {
        $topOut = @(& git -C $resolvedBackend rev-parse --show-toplevel 2>$null)
        $topOk = ($LASTEXITCODE -eq 0)
    } catch { $topOk = $false } finally { $ErrorActionPreference = $prevEapG }
    if ($topOk -and $topOut.Count -gt 0) {
        $top = "$($topOut[0])".Trim().Replace('/', [IO.Path]::DirectorySeparatorChar)
        $sameTop = $false
        try { $sameTop = ((Resolve-Path -LiteralPath $top).Path.TrimEnd('\', '/') -eq $resolvedBackend.TrimEnd('\', '/')) } catch { $sameTop = $false }
        if (-not $sameTop) {
            Say "Git     : this backend folder sits inside another git repository ($top)." Yellow
            Say "          git is told to ignore that repository for this run, so the rehearsal and" Yellow
            Say "          the real run behave the same." Yellow
            Add-Note "the backend folder sits inside the git repository at $top; git was told to ignore it for this run"
        }
    }
}

# --- substitute the split patches, if the rebuilt modules are installed ------
if ($UsingRebuilt) {
    $swapped = @()
    foreach ($name in $PATCHES) {
        if (-not $REBUILT_SUPERSEDES.ContainsKey($name)) { $swapped += $name; continue }
        $half = Join-Path $SplitDir $name
        if (Test-Path -LiteralPath $half) {
            $swapped += "rebuilt-patches\$name"
        }
        # else: the whole patch is superseded, so it is simply left out.
    }
    $PATCHES = $swapped
}

# --- line endings ------------------------------------------------------------
#
# A unified diff's context lines must match the target byte for byte, so CRLF
# on either side breaks every hunk of every patch at once. `git apply` reports
# it as "patch does not apply", which sends you looking for a wrong patch.
# There are two sides and they are handled differently.
#
# THE PATCH FILES - fixed here, silently, every run.
#
# This cost a whole run of twenty. The patches are LF in the repository, but a
# Windows clone with the default `core.autocrlf=true` writes them to disk as
# CRLF, and `.gitattributes` (which says `*.patch -text`) does NOT retroactively
# rewrite files that were already checked out before it existed. So a clone
# made last week still has CRLF patches today, `git checkout -- .` does not
# touch them, and all twenty fail with an error that names none of this.
#
# Rather than ask anyone to fix their working tree, every patch is copied to a
# temp folder with its endings forced to LF and the copy is what gets applied.
# Nothing in the repository or the backend is rewritten. It is correct on a
# machine where the files were already LF, so there is no case to detect.
#
# THE FILES THE PATCHES WRITE - the other side, and not fixed here. `git apply`
# writes its result through git's own conversion too, so `core.autocrlf=true`
# turns an LF patch on an LF target into a CRLF file however clean the patch
# is. That half is pinned at the one call that writes anything (Invoke-Patch,
# with `-c core.autocrlf=false -c core.eol=lf`); the comment there has the
# measured bytes.
$LfDir = Join-Path ([IO.Path]::GetTempPath()) "jarvis-patches-lf-$Stamp"
New-Item -ItemType Directory -Path $LfDir -Force | Out-Null

# Copies $Src to $Dest with every CRLF made LF. Returns how many it changed.
function Copy-AsLf {
    param([string] $Src, [string] $Dest)
    # Byte-level. Get-Content/Set-Content would re-encode, and a patch can
    # carry any bytes its target carries.
    $raw = [IO.File]::ReadAllBytes($Src)
    $buf = New-Object 'System.Collections.Generic.List[byte]'
    $dropped = 0
    for ($i = 0; $i -lt $raw.Length; $i++) {
        # Drop a CR only when it is part of CRLF. A bare CR inside a line is
        # content and stays.
        if ($raw[$i] -eq 13 -and $i + 1 -lt $raw.Length -and $raw[$i + 1] -eq 10) {
            $dropped++
            continue
        }
        $buf.Add($raw[$i])
    }
    [IO.File]::WriteAllBytes($Dest, $buf.ToArray())
    return $dropped
}

$crlfPatches = 0
foreach ($name in $PATCHES) {
    $src = Join-Path $PatchDir $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $flat = Split-Path -Leaf $name
    $crlfPatches += (Copy-AsLf -Src $src -Dest (Join-Path $LfDir $flat))
}
# Everything that applies a patch reads from here, never from $PatchDir.
$PatchSrc = $LfDir
if ($crlfPatches -gt 0) {
    Say "Endings : normalised $crlfPatches CRLF line(s) to LF in a temp copy of" Yellow
    Say "          the patches (your files are untouched - that is git's" Yellow
    Say "          autocrlf having written them that way, not anything you did)" Yellow
}

# --- earlier versions of each patch ------------------------------------------
#
# Whether a patch is on is found out by taking it off (git apply --reverse),
# and that only works with the EXACT text that went on. Several patches were
# edited after they were first published. A backend that got the older text
# could not take it off with the newer one, so the run stopped with "will
# not apply" and there was nothing the owner could do about it.
#
# backend/patch-history holds every earlier committed text of every patch
# (tools/build_patch_history.py writes it; backend/test_patch_history.py
# fails if it falls behind). index.tsv lists them newest first per patch,
# tab-separated: patch, file, commit, date, subject. When the current text
# of a patch will not come off, step (c) below tries these, newest first.
$HistDir = Join-Path $PatchDir 'patch-history'
$History = @{}
$histIndex = Join-Path $HistDir 'index.tsv'
if (Test-Path -LiteralPath $histIndex) {
    foreach ($line in [IO.File]::ReadAllLines($histIndex)) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $cols = $line.Split([char]9)
        if ($cols.Count -lt 4) { continue }
        $subject = ''
        if ($cols.Count -gt 4) { $subject = $cols[4] }
        if (-not $History.ContainsKey($cols[0])) { $History[$cols[0]] = @() }
        $History[$cols[0]] += @{ File = $cols[1]; Commit = $cols[2]; Date = $cols[3]; Subject = $subject }
    }
}

# The older texts to try for one entry of $PATCHES, newest first, each an
# LF copy in $LfDir: @{ File = <LF copy>; Label = <plain words> }. Written to
# the pipeline one by one - call it inside @( ) to get a list.
#
# For a split half (rebuilt-patches\x.patch) the FULL x.patch is tried too,
# as it is now and then its older texts: runs before the split existed put
# the whole patch on, and the half alone may not match what they left.
function Get-OlderVersions {
    param([string] $Name)
    $key = $Name -replace '\\', '/'
    $keys = @($key)
    $leaf = ($key -split '/')[-1]
    if ($key -ne $leaf) { $keys += $leaf }
    foreach ($k in $keys) {
        if ($k -ne $key) {
            $whole = Join-Path $PatchDir $k
            if (Test-Path -LiteralPath $whole) {
                $dest = Join-Path $LfDir ('older__whole__' + $leaf)
                [void](Copy-AsLf -Src $whole -Dest $dest)
                @{ File = $dest; Label = "the whole $k, as it is now (from before the split into rebuilt-patches)" }
            }
        }
        if (-not $History.ContainsKey($k)) { continue }
        foreach ($h in $History[$k]) {
            # index.tsv writes '/', which Windows reads as '\'.
            $src = Join-Path $HistDir $h.File
            if (-not (Test-Path -LiteralPath $src)) { continue }
            $dest = Join-Path $LfDir ('older__' + ($h.File -replace '[\\/]', '__'))
            [void](Copy-AsLf -Src $src -Dest $dest)
            $short = $h.Commit
            if ($short.Length -gt 7) { $short = $short.Substring(0, 7) }
            $day = $h.Date
            if ($day.Length -gt 10) { $day = $day.Substring(0, 10) }
            @{ File = $dest; Label = "the older $k from $day (commit $short)" }
        }
    }
}

# THE BACKEND FILES - reported, never fixed. Rewriting someone's source to
# make a patch fit is a much bigger thing to do silently than it looks.
$probe = Join-Path $BackendPath 'jarvis_hud.py'
if (Test-Path -LiteralPath $probe) {
    $bytes = [IO.File]::ReadAllBytes($probe)
    $crlf = 0
    for ($i = 1; $i -lt $bytes.Length; $i++) {
        if ($bytes[$i] -eq 10 -and $bytes[$i - 1] -eq 13) { $crlf++ }
    }
    $lf = 0
    foreach ($b in $bytes) { if ($b -eq 10) { $lf++ } }
    if ($crlf -gt 0) {
        Say "Endings : jarvis_hud.py has $crlf CRLF line(s) of $lf" Yellow
        Say "          The patches are LF. If they will not apply, THIS is why," Yellow
        Say "          not a wrong patch. Say so and it gets handled properly." Yellow
    } else {
        Say "Endings : LF, which is what the patches expect"
    }
}

# --- backend files with Windows line endings (CRLF) ------------------------------
#
# The patches are LF. A backend .py file that has CRLF lines can take none of
# their hunks: the patch tool compares context byte for byte, so the run said
# "will not apply" for nearly every patch (seen 2026-09-30: jarvis_hud.py had
# 3375 CRLF lines of 3375, and the script's own warning above was the whole
# answer). Rewriting someone's source is not done silently: it needs
# -FixLineEndings, and every file it changes is copied to
# _jarvis-backup-<date>-endings first.
#
# WHEN the rewrite happens matters (audit 2026-09-30). It used to run right
# here, before the missing-file check and before the rehearsal, so a run that
# then stopped with "NOTHING HAS BEEN CHANGED" had in fact rewritten the
# owner's files. Now this section only FINDS the CRLF files. The rehearsal
# runs on a copy converted the same way (Reset-Rehearsal), and the real files
# are converted (Convert-BackendEndings) only after the rehearsal succeeded
# and every other check has passed.
function Get-CrlfFiles {
    $endTargets = @{}
    foreach ($pname in $PATCHES) {
        $pf = Join-Path $PatchSrc (Split-Path -Leaf $pname)
        if (-not (Test-Path -LiteralPath $pf)) { continue }
        foreach ($pl in [IO.File]::ReadAllLines($pf)) {
            if ($pl.StartsWith('+++ b/')) {
                # Up to a tab: diff -u writes the file's date after one.
                $endTargets[($pl.Substring(6) -split "`t")[0].Trim()] = $true
            }
        }
    }
    $found = @()
    foreach ($tname in ($endTargets.Keys | Sort-Object)) {
        $tp = Join-Path $BackendPath $tname
        if (-not (Test-Path -LiteralPath $tp)) { continue }
        $tb = [IO.File]::ReadAllBytes($tp)
        $tc = 0
        for ($ti = 1; $ti -lt $tb.Length; $ti++) {
            if ($tb[$ti] -eq 10 -and $tb[$ti - 1] -eq 13) { $tc++ }
        }
        if ($tc -gt 0) { $found += [pscustomobject]@{ Name = $tname; Path = $tp; Count = $tc } }
    }
    return $found
}

# Rewrites each CRLF file with LF, one file at a time (temp file, then
# replace), after copying it to the endings backup. If any file cannot be
# replaced - the usual reason is Jarvis still running and holding it open -
# every file already converted is put back from the backup, the temp files
# are removed, and the run stops saying which file it was. Only called once
# nothing else can stop the run first.
function Convert-BackendEndings {
    param($Files)
    $endBackup = Join-Path $BackendPath "_jarvis-backup-$Stamp-endings"
    New-Item -ItemType Directory -Force -Path $endBackup | Out-Null
    $script:State.EndingsBackup = $endBackup
    $script:State.Changed = $true
    $script:State.Patching = $true
    Say "Endings : -FixLineEndings: $($Files.Count) backend file(s) have CRLF. Each is copied to" Yellow
    Say "          $endBackup" Yellow
    Say "          first, then rewritten with LF (nothing else about it changes)." Yellow
    $done = @()
    foreach ($cf in $Files) {
        $tmpLf = $cf.Path + ".lf-tmp"
        try {
            Copy-Item -LiteralPath $cf.Path -Destination (Join-Path $endBackup $cf.Name) -Force
            $changed = Copy-AsLf -Src $cf.Path -Dest $tmpLf
            Move-Item -LiteralPath $tmpLf -Destination $cf.Path -Force
            $done += $cf
            $script:State.EndingsConverted = $true
            Say "          $($cf.Name): $changed line(s) now LF"
        } catch {
            $why = $_.Exception.Message
            Bad "$($cf.Name) could not be rewritten: $why"
            $undone = @()
            $stuck = @()
            foreach ($d in $done) {
                try {
                    Copy-Item -LiteralPath (Join-Path $endBackup $d.Name) -Destination $d.Path -Force
                    $undone += $d.Name
                } catch { $stuck += $d.Name }
            }
            Get-ChildItem -LiteralPath $BackendPath -Filter '*.lf-tmp' -File -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
            if ($stuck.Count -eq 0) {
                # Everything is as it was. Say so - and only then.
                $script:State.EndingsConverted = $false
                $script:State.Changed = $false
                $script:State.Patching = $false
                Add-Problem "$($cf.Name) is locked or could not be replaced ($why). Close Jarvis (and anything else that has that file open), then run this again. Files already converted ($($undone.Count)) were put back from $endBackup; nothing of yours is changed."
            } else {
                Add-Problem "$($cf.Name) is locked or could not be replaced ($why), and $($stuck -join ', ') could not be put back either. Close Jarvis, then paste the restore line below." -Damaged
            }
            Finish-Run
        }
    }
    $script:State.Patching = $false
}

$crlfFiles = @(Get-CrlfFiles)
if ($crlfFiles.Count -gt 0) {
    if ($FixLineEndings) {
        Say "Endings : -FixLineEndings: $($crlfFiles.Count) backend file(s) have CRLF. They are rehearsed on a" Yellow
        Say "          converted copy first. Only if the whole rehearsal works are the real files" Yellow
        Say "          converted - each copied to a _jarvis-backup-$Stamp-endings folder first." Yellow
        Say "          Until then nothing of yours is touched." Yellow
    } else {
        Say "Endings : $($crlfFiles.Count) backend file(s) the patches change have Windows line endings:" Yellow
        foreach ($cf in $crlfFiles) { Say "          $($cf.Name) ($($cf.Count) CRLF lines)" Yellow }
        Say "          That is why patches say 'not onto the files as they are'. To fix it, run" Yellow
        Say "          this same command again with  -FixLineEndings  on the end: each file is" Yellow
        Say "          copied to a backup folder first, then only its line endings change." Yellow
    }
}
Say ""

# A running Jarvis has its files open (Windows will not let a locked file be
# replaced) and keeps running the OLD code from memory after they change. Best
# effort: a Python program whose command line names the backend folder or
# jarvis_hud.py. -Force skips it. Returns a list of short descriptions.
function Get-RunningBackend {
    $found = @()
    try {
        $bp = (Resolve-Path -LiteralPath $BackendPath).Path
        $rows = @()
        if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
            foreach ($p in @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)) {
                $rows += @{ Id = [int]$p.ProcessId; Name = "$($p.Name)"; Cmd = "$($p.CommandLine)" }
            }
        } else {
            # Not Windows (this is how the tests reach the check).
            foreach ($l in @(& ps -eo 'pid=,comm=,args=' 2>$null)) {
                $m = [regex]::Match("$l", '^\s*(\d+)\s+(\S+)\s+(.*)$')
                if ($m.Success) { $rows += @{ Id = [int]$m.Groups[1].Value; Name = $m.Groups[2].Value; Cmd = $m.Groups[3].Value } }
            }
        }
        foreach ($r in $rows) {
            if ($r.Id -eq $PID) { continue }
            if ($r.Name -notmatch '^(py|pyw|python[0-9.]*|pythonw[0-9.]*)(\.exe)?$') { continue }
            if (-not $r.Cmd) { continue }
            if ($r.Cmd.IndexOf($bp, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $r.Cmd -match 'jarvis_hud\.py') {
                $found += "process $($r.Id): $($r.Name)"
            }
        }
    } catch { }
    return $found
}

function Assert-JarvisClosed {
    if ($Force) { return }
    $running = @(Get-RunningBackend)
    if ($running.Count -eq 0) { return }
    Say ""
    Bad "Jarvis (or something else using this backend folder) looks like it is still running:"
    foreach ($r in $running) { Say "          $r" Red }
    Say "  Close Jarvis first (quit the desktop app from the tray, or close the PowerShell" Cyan
    Say "  window it runs in), then run this again. To go ahead anyway, add  -Force." Cyan
    Say "  NOTHING HAS BEEN CHANGED." Yellow
    Add-Problem "Jarvis looks like it is still running ($($running -join '; ')). Close it, then run this again (or add -Force)."
    Finish-Run
}

# --- how to run one patch ----------------------------------------------------

function Invoke-Patch {
    param([string] $File, [switch] $Check, [switch] $Reverse)

    # `$ErrorActionPreference = 'Stop'` at the top of this file turns ANY
    # stderr output from a native program into a terminating error - even when
    # the program succeeded. `git apply --verbose` writes "Checking patch
    # jarvis_memory.py..." to stderr on every single call, so the first check
    # killed the script with a NativeCommandError and nineteen patches never
    # got looked at.
    #
    # Relaxed here and restored in the finally, rather than globally: the Stop
    # preference is doing real work elsewhere in this file, where a failed
    # Copy-Item must not be shrugged off before the backup is complete.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $prevCeiling = $env:GIT_CEILING_DIRECTORIES
    if ($UseGit -and $script:GitCeiling) { $env:GIT_CEILING_DIRECTORIES = $script:GitCeiling }
    try {

    # NOT $args - that is an automatic variable in PowerShell, and writing to
    # it inside a function is a way to lose an afternoon.
    if ($UseGit) {
        # THE ENDINGS OF THE FILE THIS WRITES (2026-10-05). `git apply` does
        # not write the patch's bytes: it writes them through git's own
        # line-ending conversion, so on a machine whose `core.autocrlf` is
        # true - this PC's system config sets exactly that - an LF target and
        # an LF patch still land as a CRLF file. Normalising the PATCHES (see
        # the section above) cannot help with this half: the conversion
        # happens on the way OUT. Measured here with three lines of Python
        # and a three-line patch, in a scratch repo with
        # `core.autocrlf=true`: plain `git apply` left
        # `6f 6e 65 0d 0a 54 57 4f 0d 0a 74 68 72 65 65 0d 0a` (3 CRLF,
        # bytes=17), and the same call with the pins below left
        # `6f 6e 65 0a 54 57 4f 0a 74 68 72 65 65 0a` (no CR at all,
        # bytes=14). That drift is what the .gitattributes comment calls an
        # afternoon, and on the owner's PC it would be every run.
        #
        # Pinned per call with -c, the way the GIT_CEILING_DIRECTORIES above
        # is pinned per call: nothing global and nothing in a repository is
        # changed, and nothing about which patch is chosen or in what order
        # changes. core.autocrlf=false is the measured half. core.eol=lf is
        # the other half of the same conversion, and it is not decoration:
        # if the backend folder is itself a git repository then the ceiling
        # above cannot hide its .gitattributes, and a `* text=auto` attribute
        # with autocrlf=false still writes CRLF unless core.eol says lf
        # (measured: CR=3 without it, CR=0 with it). An explicit `eol=crlf`
        # attribute beats both - only the ceiling stops that one, which is
        # why the ceiling is not optional either.
        #
        # --3way is deliberately absent. It can leave conflict markers in a
        # working Python file, which turns "the patch did not apply" into
        # "the backend will not start and the error is a syntax error on
        # line 900".
        $gitArgs = @('-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply', '--verbose')
        if ($Check)   { $gitArgs += '--check' }
        if ($Reverse) { $gitArgs += '--reverse' }
        $gitArgs += $File
        $out = & git @gitArgs 2>&1
    } else {
        $patchArgs = @('-p1')
        if ($Reverse) { $patchArgs += '-R' } else { $patchArgs += '--forward' }
        if ($Check)   { $patchArgs += '--dry-run' }
        $patchArgs += @('-i', $File)
        $out = & patch @patchArgs 2>&1
    }

    } finally {
        $ErrorActionPreference = $prev
        if ($null -eq $prevCeiling) { Remove-Item Env:GIT_CEILING_DIRECTORIES -ErrorAction SilentlyContinue }
        else { $env:GIT_CEILING_DIRECTORIES = $prevCeiling }
    }
    return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($out | Out-String).Trim() }
}

# --- does the backend actually have the files the patches name? --------------
#
# `git apply` answers a missing target with "error: <name>: No such file or
# directory", one line, inside the output of the patch that wanted it. With
# twenty patches failing for a different reason at the same time, that line is
# unfindable - and it is the only one that is not about line endings. Asked
# once, up front, in words.
$wanted = @{}
foreach ($name in $PATCHES) {
    $src = Join-Path $PatchSrc $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    foreach ($line in (Get-Content -LiteralPath $src)) {
        # Up to a tab, not to the end of the line: `diff -u` writes the
        # file's date after a tab ("+++ b/jarvis_hud.py<TAB>2026-09-18 ..."),
        # and three patches here have one. Read to the end of the line, the
        # name carried the date, no such file existed, and this check stopped
        # every run with "jarvis_hud.py 2026-09-18 ... is not in your backend
        # folder" - even with every file present. Found 2026-09-23.
        if ($line -match '^\+\+\+ b/([^\t]+)') {
            $t = $Matches[1].Trim()
            if (-not $wanted.ContainsKey($t)) { $wanted[$t] = @() }
            $wanted[$t] += $name
        }
    }
}
$absent = @($wanted.Keys | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $BackendPath $_))
} | Sort-Object)

if ($absent.Count -gt 0) {
    # Which patches are actually stopped by this, and which are not. A patch
    # is blocked if ANY file it touches is missing - there is no applying half
    # of one. Worth separating, because "two files are missing" reads like the
    # whole run is lost when in fact most of it is fine.
    $blocked = @{}
    foreach ($a in $absent) { foreach ($n in $wanted[$a]) { $blocked[$n] = $true } }
    $clear = @($PATCHES | Where-Object { -not $blocked.ContainsKey($_) })

    Say ""
    Bad "$($absent.Count) file(s) the patches expect are not in your backend folder:"
    foreach ($a in $absent) {
        Say "          $a   (wanted by $($wanted[$a] -join ', '))" Red
    }
    Say ""
    Say "That folder is: $BackendPath" Cyan
    Say ""
    Say "$($blocked.Count) patch(es) are stopped by this. $($clear.Count) are not." Cyan
    Say ""
    Say "Find the missing files first - this searches your whole user folder:" Cyan
    foreach ($a in $absent) {
        Say "    Get-ChildItem `$env:USERPROFILE -Filter $a -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName" Cyan
    }
    Say ""
    Say "If they turn up somewhere else, that folder is your backend - pass it" Cyan
    Say "with -BackendPath. If they are genuinely gone, you can apply the" Cyan
    Say "$($clear.Count) that do not need them:" Cyan
    Say "    powershell -ExecutionPolicy Bypass -File .\scripts\apply-patches.ps1 -BackendPath `"$BackendPath`" -SkipMissing" Cyan

    if (-not $SkipMissing) {
        Say ""
        Say "NOTHING HAS BEEN CHANGED." Yellow
        Add-Problem "$($absent.Count) file(s) the patches expect are not in your backend folder ($($absent -join ', ')). Find them (commands above) or add -SkipMissing."
        Finish-Run
    }

    # -SkipMissing is safe to offer because it changes nothing about how the
    # decision is made: the shortened stack still has to apply cleanly to a
    # throwaway copy before a real file is opened. If dropping these six
    # breaks the ones below them - and it may, because several share a file
    # and so share context - the rehearsal says so and the run stops there.
    Say ""
    Say "-SkipMissing: leaving out $($blocked.Count), rehearsing the other $($clear.Count)." Yellow
    Say "  Left out:" Yellow
    foreach ($n in $PATCHES) { if ($blocked.ContainsKey($n)) { Say "    $n" Yellow } }
    Say ""
    Say "  This is a PARTIAL install. The features those patches carry will not" Yellow
    Say "  be there, and backend/README.md says what each one was for." Yellow
    $PATCHES = $clear
    if ($PATCHES.Count -eq 0) {
        Bad "Nothing is left to apply."
        Add-Problem "Every patch needs a file that is missing; nothing is left to apply."
        Finish-Run
    }
    Add-Note "PARTIAL install (-SkipMissing): $($blocked.Count) patch(es) were left out; the features they carry are not there."
    $script:State.Partial = $true
    # Only the files the remaining patches touch are converted.
    $crlfFiles = @(Get-CrlfFiles)
}

Push-Location -LiteralPath $BackendPath
try {

    # --- revert ---------------------------------------------------------------
    if ($Revert) {
        Assert-JarvisClosed
        if ($FixLineEndings -and $crlfFiles.Count -gt 0) { Convert-BackendEndings -Files $crlfFiles }
        Say "Removing patches, newest first." Cyan
        $script:State.Patching = $true
        $removed = 0
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
            if (-not (Test-Path -LiteralPath $full)) { continue }
            if ((Invoke-Patch -File $full -Check -Reverse).Ok) {
                $r = Invoke-Patch -File $full -Reverse
                if ($r.Ok) { Ok $name; $removed++; $script:State.Changed = $true } else { Bad "$name`n$($r.Output)"; Add-Problem "$name could not be taken off." -Damaged }
                continue
            }
            # Not the current text. An older one, from before it was edited?
            $older = $null
            foreach ($o in @(Get-OlderVersions -Name $name)) {
                if ((Invoke-Patch -File $o.File -Check -Reverse).Ok) { $older = $o; break }
            }
            if ($older) {
                $r = Invoke-Patch -File $older.File -Reverse
                if ($r.Ok) { Ok "$name - $($older.Label)"; $removed++; $script:State.Changed = $true } else { Bad "$name`n$($r.Output)"; Add-Problem "$name (older version) could not be taken off." -Damaged }
            } else {
                Warn "$name (was not applied)"
            }
        }
        Say ""
        Say "Removed $removed." Cyan
        Say "(Modules this script copied in - jarvis_intake.py, the rebuilt modules" Cyan
        Say " and the rest - and your jarvis-framework.toml are left where they are." Cyan
        Say " Any older copy a run replaced is in a _jarvis-backup-<date> folder in" Cyan
        Say " the backend folder.)" Cyan
        $script:State.Patching = $false
        Finish-Run -Kind revert
    }

    # --- 1. rehearse the WHOLE STACK on a copy -------------------------------
    #
    # Two earlier versions of this got it wrong in the same way, from opposite
    # directions, and both times the cause was treating a STACK as a SET.
    #
    # v1 ran `git apply --check` on each patch against the unpatched tree and
    # refused to start if any failed. bitemporal edits code memory-safety
    # wrote, so it cannot apply to a pristine backend and never could: the
    # check could only ever report failures that were not real.
    #
    # v2 applied them in order to a copy - right - but decided "already
    # applied?" per patch, by reverse-checking it alone. That fails too:
    # memory-safety cannot be reversed out of a tree that has bitemporal on
    # top of it, because bitemporal rewrote its context. Running the script
    # twice reported six phantom failures.
    #
    # So the question is asked about the whole stack, never about one patch:
    #
    #   Does the ENTIRE stack reverse cleanly?  -> already applied, nothing to do
    #   Does the ENTIRE stack apply cleanly?    -> go ahead for real
    #   Take off what IS applied, newest first
    #   (current text, or an older one),
    #   then does the ENTIRE stack apply?       -> go ahead: undo those, then all
    #   None of these                           -> say so and touch nothing
    #
    # Both rehearsals run on a throwaway copy, so the real files are not
    # opened until an answer is known.
    $rehearsal = Join-Path ([IO.Path]::GetTempPath()) "jarvis-rehearsal-$Stamp"
    $broken    = @()
    $already   = $false
    # Set only by (c): the patches an earlier run left on, newest first,
    # which come off the real files before the whole list goes on.
    $undoFirst = @()

    function Reset-Rehearsal {
        if (Test-Path -LiteralPath $rehearsal) {
            Remove-Item -LiteralPath $rehearsal -Recurse -Force
        }
        New-Item -ItemType Directory -Path $rehearsal -Force | Out-Null
        Copy-Item -Path (Join-Path $BackendPath '*.py') -Destination $rehearsal -Force
        # With -FixLineEndings the real files will be converted only AFTER
        # this rehearsal succeeds, so the rehearsal must see them already
        # converted - the same files, the same conversion (Copy-AsLf).
        if ($FixLineEndings) {
            foreach ($cf in $crlfFiles) {
                $rdest = Join-Path $rehearsal $cf.Name
                $rdir = Split-Path -Parent $rdest
                if ($rdir -and (Test-Path -LiteralPath $rdir)) {
                    [void](Copy-AsLf -Src $cf.Path -Dest $rdest)
                }
            }
        }
    }

    # Does the WHOLE stack reverse cleanly on a fresh copy of the backend as
    # it is right now? True means every patch in the list is on. Used for
    # the "already applied?" question, and again after the real run: a real
    # run that reported success is checked against the files themselves.
    function Test-StackReverses {
        Reset-Rehearsal
        Push-Location -LiteralPath $rehearsal
        $all = $true
        try {
            $bw = @($PATCHES); [array]::Reverse($bw)
            foreach ($nm in $bw) {
                $fp = Join-Path $PatchSrc (Split-Path -Leaf $nm)
                if (-not (Test-Path -LiteralPath $fp)) { $all = $false; break }
                if (-not (Invoke-Patch -File $fp -Reverse).Ok) { $all = $false; break }
            }
        } finally { Pop-Location }
        return $all
    }

    try {
        # (a) is it already patched? Reverse the stack, newest first.
        $reversedAll = Test-StackReverses

        if ($reversedAll) {
            $already = $true
            Say ""
            Ok "All $($PATCHES.Count) patches are already applied. Nothing to do."
        }
        else {
            # (b) will the stack apply? Forward, in order.
            Say "Rehearsing all $($PATCHES.Count) on a copy first." Cyan
            Reset-Rehearsal
            Push-Location -LiteralPath $rehearsal
            foreach ($name in $PATCHES) {
                $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
                if (-not (Test-Path -LiteralPath $full)) {
                    $broken += @{ Name = $name; Why = "missing from $PatchDir" }
                    Bad "$name - not found"
                    continue
                }
                $r = Invoke-Patch -File $full
                if ($r.Ok) { Say "  ok           $name" }
                else {
                    $broken += @{ Name = $name; Why = $r.Output }
                    # Not "FAIL" yet: on a backend an earlier run patched,
                    # this is expected, and (c) below may still succeed.
                    Say "  not onto the files as they are   $name" Yellow
                }
            }
            Pop-Location

            # (c) PART of the stack is already on. The usual case on a real
            # machine: an earlier run applied the list as it was then, and
            # since then patches were added - at the end, and at least one
            # (decide-once) in the MIDDLE. (a) fails because the newest
            # patches are not on; (b) fails because the old ones cannot go
            # on twice. Neither is a broken patch.
            #
            # So: on a fresh copy, take off every patch that IS on, newest
            # first, each one tested on its own the way -Revert does it; then
            # put the whole list back on in order. Not a search for "the
            # first N are applied": decide-once sits in the middle and is not
            # on the owner's machine, so the applied ones are not an unbroken
            # run from the top.
            #
            # And a patch that is on may be an OLDER TEXT of it: several were
            # edited after they were published, and the current text cannot
            # take off the old one. So when the current text will not come
            # off, every earlier committed text of that patch is tried,
            # newest first (backend/patch-history, read above). The one that
            # comes off cleanly is the one that is there; it is taken off
            # here on the copy, and later from the real files, and the
            # current text goes on in its place with everything else.
            if ($broken.Count -gt 0) {
                Reset-Rehearsal
                Push-Location -LiteralPath $rehearsal
                # Each: @{ Name = <list entry>; File = <the text that came
                # off>; Older = <plain words, or $null for the current text> }
                $found = @()
                $backwards = @($PATCHES); [array]::Reverse($backwards)
                foreach ($name in $backwards) {
                    $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
                    if (-not (Test-Path -LiteralPath $full)) { continue }
                    if ((Invoke-Patch -File $full -Check -Reverse).Ok) {
                        if ((Invoke-Patch -File $full -Reverse).Ok) {
                            $found += @{ Name = $name; File = $full; Older = $null }
                        }
                        continue
                    }
                    foreach ($o in @(Get-OlderVersions -Name $name)) {
                        if ((Invoke-Patch -File $o.File -Check -Reverse).Ok) {
                            if ((Invoke-Patch -File $o.File -Reverse).Ok) {
                                $found += @{ Name = $name; File = $o.File; Older = $o.Label }
                            }
                            break
                        }
                    }
                }
                if ($found.Count -gt 0) {
                    $olderFound = @($found | Where-Object { $_.Older })
                    Say ""
                    Say "$($found.Count) of these are already on your backend from an earlier run." Cyan
                    if ($olderFound.Count -gt 0) {
                        Say "$($olderFound.Count) of those are an OLDER version of the patch, from before it" Cyan
                        Say "was changed here. Each is taken off and the current version put on:" Cyan
                        foreach ($f in $olderFound) { Say "  older        $($f.Name)  -  $($f.Older)" Yellow }
                    }
                    Say "Rehearsing again: take those off, newest first, then put all" Cyan
                    Say "$($PATCHES.Count) back on in order. Still on the copy." Cyan
                    $again = @()
                    foreach ($name in $PATCHES) {
                        $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
                        if (-not (Test-Path -LiteralPath $full)) {
                            $again += @{ Name = $name; Why = "missing from $PatchDir" }
                            continue
                        }
                        $r = Invoke-Patch -File $full
                        if ($r.Ok) { Say "  ok           $name" }
                        else {
                            $again += @{ Name = $name; Why = $r.Output }
                            Bad "$name - will not apply"
                        }
                    }
                    # The second answer is the one that means something: the
                    # first was measured against files half-way through.
                    $broken = $again
                    if ($broken.Count -eq 0) { $undoFirst = $found }
                }
                Pop-Location
            }
        }
    } finally {
        Remove-Item -LiteralPath $rehearsal -Recurse -Force -ErrorAction SilentlyContinue
    }

    if ($broken.Count -gt 0) {
        Say ""
        Bad "$($broken.Count) patch(es) will not apply. NOTHING HAS BEEN CHANGED."
        Say "(The rehearsal ran on a copy. Your backend files were not changed - not even their line endings.)" Cyan
        Say ""
        foreach ($b in $broken) {
            Say "--- $($b.Name) ---" Yellow
            Say $b.Why
        }
        Say ""
        Say "Usually this means the backend file has moved on since the patch was" Cyan
        Say "written, or was edited by hand. (Older versions of these patches that" Cyan
        Say "this repository ever published were already tried and would have" Cyan
        Say "been recognised.) Send the block above back and the patch gets" Cyan
        Say "regenerated." Cyan
        Add-Problem "$($broken.Count) patch(es) will not apply to your files as they are: $(($broken | ForEach-Object { $_.Name }) -join ', '). Nothing was changed."
        Finish-Run
    }

    # The rehearsal worked. From here on the owner's real files are touched,
    # so a running Jarvis has to be closed first (Windows locks open files,
    # and a running Jarvis would keep the old code in memory anyway).
    Assert-JarvisClosed

    # -FixLineEndings: only now, with everything else known to be fine.
    if ($FixLineEndings -and $crlfFiles.Count -gt 0) { Convert-BackendEndings -Files $crlfFiles }

    # No early exit here even with -SkipTests: step 3 (the modules) still
    # has to run on a backend whose patches are all on already.
    if ($already) { Say "" }

    # --- 2. back up, then apply ----------------------------------------------
    # One backup folder for the whole run: the patched files below, and any
    # older copy of a module that step 3 replaces.
    $backup = Join-Path $BackendPath "_jarvis-backup-$Stamp"
    $script:State.Backup = $backup
    if (-not $already) {
        $todo = @($PATCHES | ForEach-Object { Join-Path $PatchSrc (Split-Path -Leaf $_) })
        New-Item -ItemType Directory -Path $backup -Force | Out-Null

        # Every file named in any patch header, so a revert is always possible
        # even if this script is never run again.
        # That includes the files an OLDER text being taken off names: it may
        # touch a file the current list does not.
        $touched = @{}
        $headerSources = @($todo) + @($undoFirst | ForEach-Object { $_.File })
        foreach ($full in $headerSources) {
            foreach ($line in (Get-Content -LiteralPath $full)) {
                # Up to a tab, for the same reason as the missing-file check.
                if ($line -match '^\+\+\+ b/([^\t]+)') { $touched[$Matches[1].Trim()] = $true }
            }
        }
        foreach ($f in $touched.Keys) {
            if (Test-Path -LiteralPath $f) {
                $dest = Join-Path $backup $f
                # Every current patch touches a top-level .py, but a future one
                # might not, and a backup that silently skipped a file would be
                # discovered at the worst possible moment.
                $destDir = Split-Path -Parent $dest
                if ($destDir -and -not (Test-Path -LiteralPath $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                Copy-Item -LiteralPath $f -Destination $dest
            }
        }
        Say ""
        Ok "Backed up $($touched.Count) file(s) to $backup"

        # From (c): what an earlier run left on, taken off newest first -
        # exactly what the rehearsal did before the whole list applied, with
        # the same text (the current one, or the older one it found).
        if ($undoFirst.Count -gt 0) {
            Say ""
            Say "Taking off $($undoFirst.Count) patch(es) an earlier run applied, newest first." Cyan
            $script:State.Changed = $true
            $script:State.Patching = $true
            foreach ($u in $undoFirst) {
                $r = Invoke-Patch -File $u.File -Reverse
                if ($r.Ok) {
                    if ($u.Older) { Ok "off  $($u.Name)  ($($u.Older) - the current version goes on below)" }
                    else          { Ok "off  $($u.Name)" }
                }
                else {
                    Bad "$($u.Name)`n$($r.Output)"
                    Say ""
                    Bad "Stopped part-way: your backend is only PARTLY updated."
                    Add-Problem "Taking off $($u.Name) failed part-way, so your backend is only partly updated. Jarvis may not start until it is restored." -Damaged
                    Finish-Run
                }
            }
        }
        Say ""
        Say "Applying $($todo.Count)." Cyan
        $script:State.Changed = $true
        $script:State.Patching = $true

        foreach ($full in $todo) {
            $name = Split-Path -Leaf $full
            $r = Invoke-Patch -File $full
            if ($r.Ok) { Ok $name }
            else {
                Bad "$name`n$($r.Output)"
                Say ""
                Bad "Stopped part-way: your backend is only PARTLY updated."
                Add-Problem "$name failed part-way through applying, so your backend is only partly updated. Jarvis may not start until it is restored." -Damaged
                Finish-Run
            }
        }

        # Every patch said "ok" - now look at the files themselves. The whole
        # stack must take off cleanly from a fresh copy of what is on disk
        # now; if it cannot, the tool reported success on files that do not
        # carry the patches (which is what a git that skipped or reshaped
        # the work would look like).
        $verified = $false
        try { $verified = Test-StackReverses }
        finally { Remove-Item -LiteralPath $rehearsal -Recurse -Force -ErrorAction SilentlyContinue }
        if ($verified) {
            Ok "Checked again on the real files: all $($PATCHES.Count) patches are on."
            $script:State.Patching = $false
        } else {
            Bad "Every patch said ok, but the real files do not show them all."
            Add-Problem "The patches reported success, but a second check of the real files does not find them all on. Treat the backend as NOT updated." -Damaged
            Finish-Run
        }
    }

    # --- 3. every module this repository ships whole -------------------------
    #
    # $SHIPPED, at the top of this file. Several patches only add a call into
    # a module that ships whole in backend\ (there is nothing on the PC to
    # patch for it), jarvis_agent.py's tools are whole modules, and the ten
    # rebuilt modules are fixed HERE and have to reach the PC somehow. Every
    # one of those imports quietly falls back when the module is missing. So
    # a run that stopped at step 2 could say "patched and proven" with every
    # new feature switched off. Checked here, by content, every run -
    # including the "already applied" one.
    $copied = 0
    $absentSrc = @()
    foreach ($m in $SHIPPED) {
        $src = Join-Path $PatchDir $m
        if (-not (Test-Path -LiteralPath $src)) { $absentSrc += $m; continue }
        # By file name: 'rebuilt/jarvis_voice.py' lands beside jarvis_hud.py,
        # not in a rebuilt folder the backend never looks in.
        $leaf = Split-Path -Leaf $m
        # The rebuilt event bus only replaces a rebuilt one: an original
        # jarvis_events.py carries patches (event-allowlist and friends) that
        # the next run would then fail to find.
        if ($leaf -eq 'jarvis_events.py' -and -not $UsingRebuilt) {
            Say "  skipped      $m (this backend does not use the rebuilt modules)" Yellow
            continue
        }
        $dst = Join-Path $BackendPath $leaf
        $had = Test-Path -LiteralPath $dst
        if ($had -and (Get-FileHash -LiteralPath $dst).Hash -eq (Get-FileHash -LiteralPath $src).Hash) {
            continue
        }
        if ($had) {
            if (-not (Test-Path -LiteralPath $backup)) {
                New-Item -ItemType Directory -Path $backup -Force | Out-Null
            }
            Copy-Item -LiteralPath $dst -Destination (Join-Path $backup $leaf) -Force
        }
        $script:State.Changed = $true
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied++
        if ($had) { Ok "$leaf - replaced an older copy (the old one is in $backup)" }
        else      { Ok "$leaf - copied in (it was not there, so what it does was off)" }
    }
    if ($absentSrc.Count -gt 0) {
        # Not silently skipped: this is a broken checkout of this repository,
        # not a problem with the backend.
        Bad "$($absentSrc.Count) module(s) this script ships are missing from this repository's backend folder:"
        foreach ($a in $absentSrc) { Say "          $a" Red }
        Say "        Get a fresh copy of the repository (git pull) and run this again." Cyan
        Add-Problem "$($absentSrc.Count) module(s) this script ships are missing from this repository ($($absentSrc -join ', ')), so the features they carry are OFF. Get a fresh copy (git pull) and run again."
    }
    if ($copied -eq 0 -and $absentSrc.Count -eq 0) {
        Ok "All $($SHIPPED.Count) modules this repository ships are there and up to date."
    }

} finally {
    Pop-Location
    # The LF copies were only ever an intermediate. Leaving twenty patch files
    # in %TEMP% after every run is the kind of litter nobody notices until a
    # disk is full.
    Remove-Item -LiteralPath $LfDir -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 3b. the two files "Check for tool updates" reads -----------------------
#
# jarvis_tool_updates.py has no other way to reach backend\requirements.lock
# or jarvis-desktop\src-tauri\Cargo.lock on the owner's PC - the real backend
# folder is not this checkout. Copied by content, every run, the same
# "already matches: leave it; an older one: back it up first" rule step 3
# uses for the modules themselves - NOT part of $SHIPPED, because neither
# file is Python (quiz_grader_cases.json, for eval_quiz_grader.py, rides here too; test_shipped_modules.py parses every $SHIPPED entry as a
# module's source). Cargo.lock lands under a different name (rust-crates.lock)
# so it is never mistaken for an active Rust project sitting in a Python
# backend folder.
Say ""
$toolManifests = @(
    @{ Src = (Join-Path $PatchDir 'requirements.lock'); Dst = 'requirements.lock' }
    @{ Src = (Join-Path $RepoRoot 'jarvis-desktop\src-tauri\Cargo.lock'); Dst = 'rust-crates.lock' }
    @{ Src = (Join-Path $PatchDir 'quiz_grader_cases.json'); Dst = 'quiz_grader_cases.json' }
)
$manifestsCopied = 0
$manifestsAbsent = @()
foreach ($m in $toolManifests) {
    if (-not (Test-Path -LiteralPath $m.Src)) { $manifestsAbsent += $m.Src; continue }
    $dst = Join-Path $BackendPath $m.Dst
    $had = Test-Path -LiteralPath $dst
    if ($had -and (Get-FileHash -LiteralPath $dst).Hash -eq (Get-FileHash -LiteralPath $m.Src).Hash) {
        continue
    }
    if ($had) {
        if (-not (Test-Path -LiteralPath $backup)) {
            New-Item -ItemType Directory -Path $backup -Force | Out-Null
        }
        Copy-Item -LiteralPath $dst -Destination (Join-Path $backup $m.Dst) -Force
    }
    $script:State.Changed = $true
    Copy-Item -LiteralPath $m.Src -Destination $dst -Force
    $manifestsCopied++
    if ($had) { Ok "$($m.Dst) - replaced an older copy (the old one is in $backup)" }
    else      { Ok "$($m.Dst) - copied in (Check for tool updates was off until now)" }
}
if ($manifestsAbsent.Count -gt 0) {
    Bad "$($manifestsAbsent.Count) file(s) 'Check for tool updates' reads are missing from this repository:"
    foreach ($a in $manifestsAbsent) { Say "          $a" Red }
    Say "        Get a fresh copy of the repository (git pull) and run this again." Cyan
    Add-Problem "$($manifestsAbsent.Count) file(s) 'Check for tool updates' reads are missing from this repository ($($manifestsAbsent -join ', ')). Get a fresh copy (git pull) and run again."
} elseif ($manifestsCopied -eq 0) {
    Ok "requirements.lock and rust-crates.lock (for 'Check for tool updates') are there and up to date."
}

# The real Python, or $null. Needed by steps 4 to 6.
$py = Find-Python
if ($py) {
    Say ""
    Say "Python  : $($py.Exe)  ($($py.Version), found as '$($py.Via)')"
    $pyVer = [version]$py.Version
    if ($pyVer -lt [version]'3.11') {
        Warn "Python $($py.Version) is older than 3.11. The backend is written for 3.11 or"
        Say "        newer; install 3.12 with: winget install Python.Python.3.12" Cyan
    }
}

# --- 4. the settings file: put in place if absent, NEVER overwritten -----------
#
# jarvis-framework.toml holds decisions only the owner makes - which actions
# ask first, which tools are on, where the notes live. Overwriting it would
# undo them without a word. So: if the backend would find no settings file
# at all, this repository's copy is put beside jarvis_hud.py. If there is
# one, EVERY LINE OF IT IS KEPT, and the differences are printed below.
#
# THE ONE EXCEPTION, AND WHY IT HAS TO BE ONE (found 2026-10-06)
#
# A patch adds an ACTION, and that action's tier is a line in [autonomy.tiers].
# A line is something a fresh install gets and an existing file never did -
# and this step used to print the difference and stop there. So a new action
# arrived WITHOUT its tier line, the gate resolved it through
# unknown_action_tier ("ask" - fail-safe, but not the tier it was written
# for), and two suites on the owner's PC failed with
# "every action in the repository's shipped [autonomy.tiers] has a line in
# the live one" - four red checks on a repository that was entirely correct.
# The tests were right. The config had simply never caught up.
#
# So the missing TIER lines are added now, by backend\_apply_toml_tiers.py,
# which is deliberately the least it can do:
#
#   * only keys that are MISSING, only inside [autonomy.tiers];
#   * the SHIPPED value, spelled out - never "auto" unless the shipped file
#     says "auto", so nothing can be loosened: a missing tier is already
#     "ask", and the only other shipped value ("never", "notify") is
#     stricter, not looser;
#   * a key that is already in the file is never touched, whatever it says -
#     an owner may always choose to be asked more, and a live value that is
#     LOOSER than the shipped one stays tools/sync-framework-tiers.py's
#     decision to report, not this script's to make;
#   * it refuses to write at all unless the result parses, every added line
#     reads back, every existing tier is unchanged and no other section moved;
#   * it keeps a dated copy of the file first, and prints its path.
#
# Anything else the two files disagree about ([tools].enabled, a notes
# folder, which voice) is still only printed: those are the owner's own
# choices, and nothing here can know which of the two values he meant.
#
# Looked for where rebuilt\jarvis_framework.py's config_path() looks, in the
# same order, so "the one in use" here is the one the backend reads.
Say ""
$cfgSrc = Join-Path $PatchDir $CONFIG_SRC
$cfgDir = $env:OPENJARVIS_CONFIG_DIR
if (-not $cfgDir) { $cfgDir = $env:JARVIS_CONFIG_DIR }
if (-not $cfgDir) { $cfgDir = Join-Path $HOME '.openjarvis' }
$cfgCandidates = @()
if ($env:JARVIS_FRAMEWORK_TOML) { $cfgCandidates += $env:JARVIS_FRAMEWORK_TOML }
$cfgCandidates += (Join-Path $cfgDir $CONFIG_NAME)
$cfgCandidates += (Join-Path $BackendPath $CONFIG_NAME)
$cfgParent = Split-Path -Parent $BackendPath
if ($cfgParent) { $cfgCandidates += (Join-Path (Split-Path -Parent $BackendPath) $CONFIG_NAME) }
$cfgInUse = $null
foreach ($c in $cfgCandidates) {
    if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { $cfgInUse = $c; break }
}
if (-not (Test-Path -LiteralPath $cfgSrc)) {
    Bad "This repository has no $CONFIG_SRC - get a fresh copy (git pull)."
    Add-Problem "This repository has no $CONFIG_SRC (the settings file), so none was put in place. Get a fresh copy (git pull) and run again."
} elseif (-not $cfgInUse) {
    $cfgDst = Join-Path $BackendPath $CONFIG_NAME
    Copy-Item -LiteralPath $cfgSrc -Destination $cfgDst
    $script:State.Changed = $true
    Ok "$CONFIG_NAME - you had none, so this repository's copy is now at $cfgDst"
    Say "        It is yours from now on: this script will never overwrite it." Cyan
} else {
    $mine = [IO.File]::ReadAllText($cfgInUse) -replace "`r`n", "`n"
    $ours = [IO.File]::ReadAllText($cfgSrc) -replace "`r`n", "`n"
    if ($mine -eq $ours) {
        Ok "$CONFIG_NAME - yours ($cfgInUse) is the same as this repository's."
    } else {
        Say "  note  $CONFIG_NAME - yours is kept: $cfgInUse" Cyan
        Say "        It differs from this repository's copy ($cfgSrc)." Cyan
        $missingCount = 0
        if ($py) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $diffOut = @(& $py.Exe (Join-Path $PatchDir '_config_diff.py') $cfgInUse $cfgSrc 2>&1)
            } finally {
                $ErrorActionPreference = $prevEap
            }
            $shown = 0
            $missingCount = 0
            foreach ($line in $diffOut) {
                if ($shown -ge 60) { Say "        ... and more. Run it yourself for the whole list:" Cyan; break }
                Say "        $line"
                $shown++
            }
            # `_config_diff.py`'s own summary line: "In this repository's copy
            # but NOT in yours (23)." Used for one honest sentence at the end -
            # a difference nobody is told about is how this whole step failed
            # the owner on 2026-10-06.
            foreach ($line in @($diffOut)) {
                if ($line -match 'NOT in yours \((\d+)\)') { $missingCount = [int]$Matches[1] }
            }
        }
        Say "        Every line of yours is kept. Anything below that is only in this" Cyan
        Say "        repository's copy stays yours to add - except the [autonomy.tiers]" Cyan
        Say "        lines, which are added for you now (shown in full):" Cyan
        # See the top of this step. Only ever ADDS missing tier lines, with the
        # shipped value, and refuses to write anything unless the result parses
        # and every other line is unchanged.
        $tierMerger = Join-Path $PatchDir '_apply_toml_tiers.py'
        if ($py -and (Test-Path -LiteralPath $tierMerger)) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $tierOut = @(& $py.Exe $tierMerger --apply $cfgInUse 2>&1)
                $tierMerged = ($LASTEXITCODE -eq 0)
            } finally {
                $ErrorActionPreference = $prevEap
            }
            foreach ($line in $tierOut) { Say "        $line" }
            # What is still missing, read back from the REAL file every run:
            # the script says what it did, and this does not take its word.
            $stillMissing = @()
            $checker = "import sys, tomllib`n" +
                       "cfg = tomllib.loads(open(sys.argv[1], encoding='utf-8-sig').read())`n" +
                       "tiers = (cfg.get('autonomy') or {}).get('tiers') or {}`n" +
                       "sys.exit(0 if sys.argv[2] in tiers else 1)"
            foreach ($line in @($diffOut)) {
                if ($line -match '^\s*\[autonomy\.tiers\]\s+([a-z][a-z0-9_]*)\s*=') {
                    $key = $Matches[1]
                    $prevEap = $ErrorActionPreference
                    $ErrorActionPreference = 'Continue'
                    try {
                        $null = @(& $py.Exe -c $checker $cfgInUse $key 2>&1)
                        if ($LASTEXITCODE -ne 0) { $stillMissing += $key }
                    } finally {
                        $ErrorActionPreference = $prevEap
                    }
                }
            }
            if ($tierMerged -and $stillMissing.Count -eq 0) {
                if ("$tierOut" -match 'Nothing to add') {
                    Ok "$CONFIG_NAME - no [autonomy.tiers] line was missing."
                } else {
                    Ok "$CONFIG_NAME - the missing [autonomy.tiers] lines are now in your file (a copy from before is kept beside it)."
                    $script:State.Changed = $true
                }
            } elseif ($stillMissing.Count -gt 0) {
                Bad "$CONFIG_NAME - these tier lines are STILL missing from $cfgInUse`: $($stillMissing -join ', ')"
                Say "        The actions they name resolve to unknown_action_tier instead, and the" Cyan
                Say "        gate-name suites fail on this. Add them by hand, or run:" Cyan
                Say "          py -3 `"$tierMerger`" --apply `"$cfgInUse`"" Cyan
                Add-Problem "$CONFIG_NAME is missing the [autonomy.tiers] line(s) $($stillMissing -join ', '), so those actions take unknown_action_tier instead of their own tier. Add them to $cfgInUse by hand, or run: py -3 `"$tierMerger`" --apply `"$cfgInUse`""
            } else {
                Warn "the missing [autonomy.tiers] lines could not be added to $CONFIG_NAME."
                Say "        Your backend is patched and running; until those lines are there" Cyan
                Say "        those actions take 'ask' (unknown_action_tier) instead of their own" Cyan
                Say "        tier, and the gate-name suites will say so. Run this, then restart" Cyan
                Say "        the backend:" Cyan
                Say "          py -3 `"$tierMerger`" --apply `"$cfgInUse`"" Cyan
                Add-Note "$CONFIG_NAME is missing [autonomy.tiers] line(s) that this repository's copy has; the update did NOT add them, so those actions take unknown_action_tier ('ask') instead of their own tier. To add them: py -3 `"$tierMerger`" --apply `"$cfgInUse`""
            }
        } elseif (-not (Test-Path -LiteralPath $tierMerger)) {
            Warn "'$tierMerger' is missing from this repository, so the missing [autonomy.tiers] lines were not added."
            Say "        Get a fresh copy (git pull) and run again, or add them by hand:" Cyan
            Say "          py -3 `"$tierMerger`" --apply `"$cfgInUse`"" Cyan
            Add-Note "backend\_apply_toml_tiers.py is missing from this repository, so the [autonomy.tiers] lines a new patch needs were NOT added to $cfgInUse; the actions they name take unknown_action_tier ('ask') instead. Get a fresh copy (git pull) and run again."
        }
        Say "        To see the whole difference any time:" Cyan
        Say "          py -3 `"$(Join-Path $PatchDir '_config_diff.py')`" `"$cfgInUse`" `"$cfgSrc`"" Cyan
        if ($missingCount -gt 0) {
            Say "        $missingCount setting(s) this repository has and yours does not - the tier" Cyan
            Say "        lines above were added for you; everything else is yours to add." Cyan
        }
    }
}

# --- 5. Python packages ---------------------------------------------------------
#
# The backend starts without any of these - every import is guarded - but
# memory search by meaning, the voice features and the window-reading tool
# are off until they are installed. backend\requirements.txt says which
# package carries what. pip leaves a package that is already installed alone.
$reqs = Join-Path $PatchDir 'requirements.txt'
if ($SkipPackages) {
    Say ""
    Warn "Python packages (-SkipPackages). To install them yourself:"
    Say "          py -3 -m pip install -r `"$reqs`"" Cyan
    Add-Note "Python packages were not installed (-SkipPackages); the features that need them stay off until you install them."
} elseif (-not $py) {
    Say ""
    Bad "Python packages were not installed, because there is no working Python."
    Explain-NoPython
    Add-Problem "Python packages were not installed, because there is no working Python (winget install Python.Python.3.12, then open a NEW PowerShell window and run again)."
} else {
    Say ""
    Say "Installing the Python packages in backend\requirements.txt (a minute or two the first time)." Cyan
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $pipOut = @(& $py.Exe -m pip install --disable-pip-version-check -r $reqs 2>&1)
        $pipOk = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($pipOk) {
        Ok "Python packages are installed."
    } else {
        Bad "pip could not install everything. The last lines it printed:"
        Say (($pipOut | Select-Object -Last 15 | ForEach-Object { "        $_" }) -join "`n")
        Say "        The backend still starts; the features those packages carry stay off." Cyan
        Say "        Send the lines above back if the reason is not clear." Cyan
        Add-Problem "pip could not install everything in backend\requirements.txt; the features those packages carry stay off. The last lines pip printed are above."
    }
}

# --- 6. prove it -----------------------------------------------------------------

if ($SkipTests) {
    Say ""
    Warn "Tests skipped (-SkipTests). Nothing here has been proven to work."
    Add-Note "The test suites were not run (-SkipTests), so this update is applied but NOT proven."
    Finish-Run
}

if (-not $py) {
    Say ""
    Bad "The patches and modules are in place, but the tests were NOT run: there is no working Python."
    if ($SkipPackages) { Explain-NoPython } else { Say "  (What to do about it is just above.)" Cyan }
    Add-Problem "The tests were NOT run: there is no working Python."
    Finish-Run
}

Say ""
Say "Running the test suites against the patched backend." Cyan
Say ""

# THE ONE THING THAT MAKES THESE RUNNABLE HERE AT ALL.
#
# The suites live in this repository; the modules they test live in the
# owner's backend folder. Until _where.py existed they used one path for both,
# so they only ran in the dev container where the modules are symlinked in -
# and this script would have run them anyway and produced eighteen import
# errors that look exactly like the patches having broken something.
#
# _where.py reads JARVIS_BACKEND for the modules and derives the repo from its
# own location, so both roots are right at once.
$env:JARVIS_BACKEND = (Resolve-Path -LiteralPath $BackendPath).Path

# WHAT A FAILING SUITE'S REASON LOOKS LIKE. This used to keep the LAST 25 LINES
# and nothing else, and that is what cost the owner a diagnosis on 2026-10-05.
#
# test_gate_push.py printed six sections. The failing check is in the second
# one, so its `FAIL` line and the detail beside it were lines 7 and 8 of the
# 54 the suite printed. Only the last 25 lines were shown, and the two sections
# that ran LAST - both of them entirely passing - filled every one of them. The
# log showed a section header, eighteen `ok` lines and nothing else: the
# assertion, the detail and any traceback were gone, and the failure survived
# only as the bare name in "failed: a redacted body reaches the broker
# unchanged".
#
# A check that DIES is worse than one that fails. The suite catches it and
# prints the traceback WHERE THE CHECK RAN - in the middle of the output, never
# the end - so a tail-only view hides exactly the thing a person needs to read.
#
# So `ok` lines are the only kind dropped: they are the one kind that carries
# no reason, and a suite prints them by the hundred. Every other line stays,
# tracebacks included, which is the whole promise. If that is still enormous
# the middle is cut - and the cut says so, so a clipped traceback is never
# mistaken for a whole one.
function Show-SuiteFailure($out) {
    $lines = @("$out" -split "`r?`n")
    $kept = @($lines | Where-Object { $_ -notmatch '^[ \t]*ok[ \t]' })
    $hidden = $lines.Count - $kept.Count
    $note = "      ($hidden passing line(s) hidden - every other line of this suite is below)"
    if (@($kept | Where-Object { $_.Trim() }).Count -eq 0) {
        # Non-zero exit, and nothing but passing checks (or nothing at all):
        # it stopped before it could say why. Say that, rather than printing a
        # blank block that reads like the harness losing the output.
        return "$note`n      (and there is no other line: it stopped before it could say what went wrong)"
    }
    if ($kept.Count -gt 200) {
        $cut = $kept.Count - 200
        $kept = @($kept[0..79]) + @("... $cut line(s) cut here ...") + @($kept[($kept.Count - 120)..($kept.Count - 1)])
    }
    $note + "`n" + (($kept | ForEach-Object { "      $_" }) -join "`n")
}

$tests = @(Get-ChildItem -LiteralPath $PatchDir -Filter 'test_*.py' | Sort-Object Name)
$pass = 0; $fail = @()
# A suite that exits 0 is not necessarily a suite that tested anything: many
# print "SKIP - <reason>" (as a pass) when a file, a package or a machine
# feature they need is absent, and _where.missing() skips a whole suite when a
# backend file is not there. The output is read, and a suite that skipped
# anything is counted and named, never folded into "passed".
$skipped = @()

# Same trap as Invoke-Patch: a test that prints anything to stderr - which a
# failing one does, and several passing ones do too - would terminate the run
# rather than be reported as a failure.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

# The suites run real code that writes - the audit log, approval queues,
# switch files. Without this, one run put 131 fake events into your real
# audit log in .openjarvis\logs. So for this run the config folder and the
# audit log are a temporary folder, deleted afterwards. run_suites.py works
# out the variables (the same ones CI's runner uses), one KEY=VALUE a line.
$stateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("jarvis-suite-state-" + $Stamp)
$savedEnv = @{}
$stateLines = & $py.Exe (Join-Path $PatchDir 'run_suites.py') --state-env $stateDir 2>$null
foreach ($line in @($stateLines)) {
    $parts = "$line" -split '=', 2
    if ($parts.Count -eq 2 -and $parts[0] -and $parts[1]) {
        $savedEnv[$parts[0]] = [Environment]::GetEnvironmentVariable($parts[0], 'Process')
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
    }
}
if ($savedEnv.Count -eq 0) {
    Say "  (Could not move the tests' state to a temporary folder; they may write to your real audit log.)" Yellow
}

try {
    foreach ($t in $tests) {
        $out = & $py.Exe $t.FullName 2>&1
        $exitCode = $LASTEXITCODE
        $txt = ($out | Out-String)
        if ($exitCode -eq 0) {
            # A check a suite could not run now prints "skip  <why>" (each
            # suite's own skip() helper, beside its check()), and a handful of
            # older harnesses still print "SKIP  <name>" themselves. Both are
            # read here, case-insensitively. The word has to be a whole word
            # followed by a space, a colon or the end of the line: test_topics.py
            # has a real check named "skipped-this-week is a number per topic",
            # and counting that as a skip would be the same mistake in reverse.
            $skipN = ([regex]::Matches($txt, '(?mi)^[ \t]*(ok[ \t]+)?skip(ped)?(?=[ \t:]|$)')).Count
            $sm = [regex]::Match($txt, '(?i)\b(\d+) skipped\b')
            if ($sm.Success -and [int]$sm.Groups[1].Value -gt $skipN) { $skipN = [int]$sm.Groups[1].Value }
            $pass++
            if ($skipN -gt 0) {
                Warn "$($t.Name) - passed, but $skipN part(s) were SKIPPED (not proven)"
                $skipped += "$($t.Name) ($skipN)"
            } else { Ok $t.Name }
        }
        else {
            Bad $t.Name
            $fail += @{ Name = $t.Name; Output = $txt.Trim() }
        }
    }
} finally {
    foreach ($k in @($savedEnv.Keys)) {
        [Environment]::SetEnvironmentVariable($k, $savedEnv[$k], 'Process')
    }
    Remove-Item -LiteralPath $stateDir -Recurse -Force -ErrorAction SilentlyContinue
}

$ErrorActionPreference = $prev

$hudPath = Join-Path $env:JARVIS_BACKEND 'jarvis_hud.py'
Say ""
$ran = $pass + $fail.Count
if ($ran -eq 0) {
    Bad "No test suites were found to run in $PatchDir - nothing has been proven."
    Add-Problem "No test suites ran (none found in $PatchDir), so nothing is proven. Get a fresh copy of the repository (git pull) and run again."
}
if ($fail.Count -gt 0) {
    Bad "$pass passed, $($fail.Count) failed."
    Say ""
    foreach ($f in $fail) {
        Say "===== $($f.Name) =====" Yellow
        # Not the last 25 lines: see Show-SuiteFailure above for what that
        # cost, and why the reason is usually in the MIDDLE of a suite's
        # output rather than the end of it.
        Say (Show-SuiteFailure $f.Output)
    }
    Say "Send the block above back. A failing suite here is a real finding." Cyan
    Say ""
    Say "CI runs these suites too, but only against this repository: about" Cyan
    Say "twenty of them need your jarvis_hud.py, jarvis_gate.py and the other" Cyan
    Say "files that live only on your PC, so CI skips those. Your machine is" Cyan
    Say "the first place they meet the real modules. A failure means the" Cyan
    Say "backend here differs from the one the patches were written against," Cyan
    Say "or that a rebuilt module is wrong - and the second one has happened." Cyan
    Add-Problem "$($fail.Count) test suite(s) FAILED: $(($fail | ForEach-Object { $_.Name }) -join ', '). The output is above."
} elseif ($ran -gt 0) {
    if ($skipped.Count -eq 0) {
        Ok "$pass suites passed, none skipped."
        if (-not $script:State.Partial) { $script:State.Proven = $true }
    } else {
        Warn "$pass suites passed, but $($skipped.Count) of them skipped part or all of their checks."
        Add-Note "Patched, but $($skipped.Count) of the $pass suites could not fully run, so this is NOT fully proven: $($skipped -join ', '). (A skip usually means a backend file, a Python package or a machine feature the suite needs is not there.)"
    }
}
if ($py) { $script:State.StartLine = "& `"$($py.Exe)`" `"$hudPath`"" }
Finish-Run
