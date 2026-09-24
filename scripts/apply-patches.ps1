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
    [switch] $SkipPackages
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
    'jarvis_learning_switch.py'  # learning-asks.patch: turning learning on raises an approval card
    'jarvis_voicebank.py'        # other people's voices (numbers only): the voice check's comparison step, jarvis_voice.cohort_for
    'jarvis_voice_flow.py'       # voice-flow.patch: interrupting by talking, the delay in numbers, the "One moment." clip; jarvis_speech.py calls it
    'jarvis_chat_log.py'         # chat-history.patch: chat history kept on this PC, encrypted
    'jarvis_auto_learn.py'       # auto-learn.patch: facts from the owner's own words saved without a card
    'jarvis_sensitive.py'        # the sensitive-topic check jarvis_auto_learn.py asks: word lists, shapes, the local model
    'jarvis_past.py'             # past-recall.patch: questions about the past also get retired facts, labelled
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
    'jarvis_notes.py'            # tool "notes_search"; carries the token-in-an-error fix
    'jarvis_home.py'             # tools "home_read" and "home_control": Home Assistant
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
    Say "  This needs the OpenJarvis backend folder, not this repository." Yellow
    exit 1
}

# `patch` is not on a stock Windows box; `git apply` is, if Git is installed.
$UseGit = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
if (-not $UseGit -and -not (Get-Command patch -ErrorAction SilentlyContinue)) {
    Bad 'Neither git nor patch is on PATH, and one of them is needed.'
    Say "  Install Git for Windows: https://git-scm.com/download/win" Cyan
    exit 1
}

Say ""
Say "Backend : $BackendPath"
Say "Patches : $PatchDir"
Say "Tool    : $(if ($UseGit) { 'git apply' } else { 'patch' })"

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
Say ""

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
    try {

    # NOT $args - that is an automatic variable in PowerShell, and writing to
    # it inside a function is a way to lose an afternoon.
    if ($UseGit) {
        # --3way is deliberately absent. It can leave conflict markers in a
        # working Python file, which turns "the patch did not apply" into
        # "the backend will not start and the error is a syntax error on
        # line 900".
        $gitArgs = @('apply', '--verbose')
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
        exit 1
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
        exit 1
    }
}

Push-Location -LiteralPath $BackendPath
try {

    # --- revert ---------------------------------------------------------------
    if ($Revert) {
        Say "Removing patches, newest first." Cyan
        $removed = 0
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
            if (-not (Test-Path -LiteralPath $full)) { continue }
            if ((Invoke-Patch -File $full -Check -Reverse).Ok) {
                $r = Invoke-Patch -File $full -Reverse
                if ($r.Ok) { Ok $name; $removed++ } else { Bad "$name`n$($r.Output)" }
                continue
            }
            # Not the current text. An older one, from before it was edited?
            $older = $null
            foreach ($o in @(Get-OlderVersions -Name $name)) {
                if ((Invoke-Patch -File $o.File -Check -Reverse).Ok) { $older = $o; break }
            }
            if ($older) {
                $r = Invoke-Patch -File $older.File -Reverse
                if ($r.Ok) { Ok "$name - $($older.Label)"; $removed++ } else { Bad "$name`n$($r.Output)" }
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
        exit 0
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
    }

    try {
        # (a) is it already patched? Reverse the stack, newest first.
        Reset-Rehearsal
        Push-Location -LiteralPath $rehearsal
        $reversedAll = $true
        $backwards = @($PATCHES); [array]::Reverse($backwards)
        foreach ($name in $backwards) {
            $full = Join-Path $PatchSrc (Split-Path -Leaf $name)
            if (-not (Test-Path -LiteralPath $full)) { $reversedAll = $false; break }
            if (-not (Invoke-Patch -File $full -Reverse).Ok) { $reversedAll = $false; break }
        }
        Pop-Location

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
        Say "(The rehearsal ran on a copy. Your backend was never opened.)" Cyan
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
        exit 1
    }

    # No early exit here even with -SkipTests: step 3 (the modules) still
    # has to run on a backend whose patches are all on already.
    if ($already) { Say "" }

    # --- 2. back up, then apply ----------------------------------------------
    # One backup folder for the whole run: the patched files below, and any
    # older copy of a module that step 3 replaces.
    $backup = Join-Path $BackendPath "_jarvis-backup-$Stamp"
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
            foreach ($u in $undoFirst) {
                $r = Invoke-Patch -File $u.File -Reverse
                if ($r.Ok) {
                    if ($u.Older) { Ok "off  $($u.Name)  ($($u.Older) - the current version goes on below)" }
                    else          { Ok "off  $($u.Name)" }
                }
                else {
                    Bad "$($u.Name)`n$($r.Output)"
                    Say ""
                    Bad "Stopped part-way. Your originals are in:"
                    Say "  $backup" Yellow
                    Say "  Copy them back, or run with -Revert." Yellow
                    exit 1
                }
            }
        }
        Say ""
        Say "Applying $($todo.Count)." Cyan

        foreach ($full in $todo) {
            $name = Split-Path -Leaf $full
            $r = Invoke-Patch -File $full
            if ($r.Ok) { Ok $name }
            else {
                Bad "$name`n$($r.Output)"
                Say ""
                Bad "Stopped part-way. Your originals are in:"
                Say "  $backup" Yellow
                Say "  Copy them back, or run with -Revert." Yellow
                exit 1
            }
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
# one, it is left exactly as it is and the differences are printed.
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
} elseif (-not $cfgInUse) {
    $cfgDst = Join-Path $BackendPath $CONFIG_NAME
    Copy-Item -LiteralPath $cfgSrc -Destination $cfgDst
    Ok "$CONFIG_NAME - you had none, so this repository's copy is now at $cfgDst"
    Say "        It is yours from now on: this script will never overwrite it." Cyan
} else {
    $mine = [IO.File]::ReadAllText($cfgInUse) -replace "`r`n", "`n"
    $ours = [IO.File]::ReadAllText($cfgSrc) -replace "`r`n", "`n"
    if ($mine -eq $ours) {
        Ok "$CONFIG_NAME - yours ($cfgInUse) is the same as this repository's."
    } else {
        Say "  note  $CONFIG_NAME - yours is kept, untouched: $cfgInUse" Cyan
        Say "        It differs from this repository's copy ($cfgSrc)." Cyan
        if ($py) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $diffOut = @(& $py.Exe (Join-Path $PatchDir '_config_diff.py') $cfgInUse $cfgSrc 2>&1)
            } finally {
                $ErrorActionPreference = $prevEap
            }
            $shown = 0
            foreach ($line in $diffOut) {
                if ($shown -ge 60) { Say "        ... and more. Run it yourself for the whole list:" Cyan; break }
                Say "        $line"
                $shown++
            }
        }
        Say "        Nothing is changed for you. To see the whole difference any time:" Cyan
        Say "          py -3 `"$(Join-Path $PatchDir '_config_diff.py')`" `"$cfgInUse`" `"$cfgSrc`"" Cyan
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
} elseif (-not $py) {
    Say ""
    Bad "Python packages were not installed, because there is no working Python."
    Explain-NoPython
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
    }
}

# --- 6. prove it -----------------------------------------------------------------

if ($SkipTests) {
    Say ""
    Ok "Done. Tests skipped."
    exit 0
}

if (-not $py) {
    Say ""
    Bad "The patches and modules are in place, but the tests were NOT run: there is no working Python."
    if ($SkipPackages) { Explain-NoPython } else { Say "  (What to do about it is just above.)" Cyan }
    exit 1
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

$tests = Get-ChildItem -LiteralPath $PatchDir -Filter 'test_*.py' | Sort-Object Name
$pass = 0; $fail = @()

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
        if ($LASTEXITCODE -eq 0) { Ok $t.Name; $pass++ }
        else {
            Bad $t.Name
            $fail += @{ Name = $t.Name; Output = ($out | Out-String).Trim() }
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
if ($fail.Count -eq 0) {
    Ok "$pass suites passed. The backend is patched and proven."
    Say ""
    Say "Start it (one line), and watch its 'token' line - it should say Windows Credential Manager:" Cyan
    Say "    & `"$($py.Exe)`" `"$hudPath`"" Cyan
} else {
    Bad "$pass passed, $($fail.Count) failed."
    Say ""
    foreach ($f in $fail) {
        Say "===== $($f.Name) =====" Yellow
        Say ($f.Output -split "`n" | Select-Object -Last 25 | Out-String)
    }
    Say "Send the block above back. A failing suite here is a real finding." Cyan
    Say ""
    Say "CI runs these suites too, but only against this repository: about" Cyan
    Say "twenty of them need your jarvis_hud.py, jarvis_gate.py and the other" Cyan
    Say "files that live only on your PC, so CI skips those. Your machine is" Cyan
    Say "the first place they meet the real modules. A failure means the" Cyan
    Say "backend here differs from the one the patches were written against," Cyan
    Say "or that a rebuilt module is wrong - and the second one has happened." Cyan
    exit 1
}
