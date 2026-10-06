# Handoff: the gate-entries patch (start here)

Written 2026-10-03, at the end of a long session. **Read this file first.** It has
everything needed to continue, so nothing has to be explained again.

## What the owner asked for

The update has been applied to the owner's PC but the test suites flagged problems.
The owner chose to fix **the gate entries** first (the other two options were the
`0x00000000` bind check and the stale generated fixtures).

The owner is a **beginner developer**: plain words, one command at a time, and
multiple-choice questions (short, recommendation first). They are on **Windows 11**,
and their shell is **PowerShell 5.1** (`pwsh` 7 is NOT installed). Git **is** now
installed (2.55.0) and on the PATH.

## The problem, in one paragraph

The owner's backend `jarvis_agent.py` defines ten tools that the owner's
`jarvis_gate.py` has **no `_TOOL_ACTIONS` entry** for. The test
`backend/test_agent.py` iterates `AG.TOOLS` and checks each tool's
`gate_lookup_name()` is a key in `jarvis_gate._TOOL_ACTIONS`. It is not, for these
ten, so several suites fail. The gate's own fallback is fail-safe —
`action_for_tool` returns `("unclassified_tool", False)` and `unclassified_tool`
becomes **"ask"** (see `jarvis_gate.py:1327`'s own comment) — so nothing runs
silently; the tools just prompt the owner every time. **This is not a safety hole.**

## The ten exact missing lookup names

Taken from the real log (`_jarvis-logs\apply-patches-2026-10-03-154859.txt`):

```
jarvis_browser_control_run
jarvis_calendar_read_run
jarvis_email_read_run
jarvis_notes_search_run
jarvis_home_read_run
jarvis_home_control_run
set_timer
set_reminder
todo_add
todo_done
coming_up
```

(That is eleven names for ten tools — `home_control` and `home_read` are separate
tools. Confirm the full set by re-running the test, do not trust this list alone.)

## Where everything lives

- **The owner's real backend** (readable from the agent's workspace — NO pasting needed):
  `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program`
  - `jarvis_gate.py` — 1870 lines. The tool→action table starts at about **line 735**
    (a plain `"tool_name": "action_name",` map; its own entries include
    `"browser_navigate": "web_research"`, `"memory_store": "notify"`,
    `"shell_exec": "run_shell_on_host"`, `"git_commit": "ask"`).
  - `_TOOL_ACTIONS.get(name)` is at **line 867**; the fallback is line 869.
  - Existing `jarvis_<tool>_run` entries to copy the style from: lines **760-772**
    (`jarvis_ui_control_run`, `jarvis_android_control_run`, `jarvis_research_run`).
  - `jarvis_agent.py`, `jarvis_hud.py`, `jarvis_memory.py`, `jarvis_backup.py`,
    `jarvis_apps.py` are all present.
  - Backups from the update: `_jarvis-backup-2026-10-03-154859`. The full log is
    `_jarvis-logs\apply-patches-2026-10-03-154859.txt` (84 `FAIL` lines total).
- **The repo** (the agent's workspace):
  `C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main` — note the folder is
  FLAT (no repeated name), and it is a **downloaded ZIP, not a git clone**.
  - The previous copy (kept as a safety net by the owner):
    `...\Documents\Jarvis github\Epic-Jarvis-main-OLD`
  - Patches live in `backend/*.patch`. `backend/jarvis_agent.py` is the **reference**
    copy, not the owner's live file.

## What to build

A patch that adds the missing entries to the gate's tool→action table, then wire it
into the stack **in the correct position** (the stack is ordered; `git apply` has no
fuzz and no `--3way`, so one out-of-order patch stops the whole run — this exact
class of bug cost the owner every one of 118 patches until `thinking.patch` was
moved after `focus.patch`).

### The tiers to use, and why

Match the project's own recorded decisions in `CLAUDE.md`:

- **Reading tools** — `calendar_read`, `email_check`, `notes_search`, `home_read`:
  they only look at things, so `"auto"` (or `"notify"` if the project's convention
  for a store write fits better — check the neighbouring entries first).
- **Control tools** — `home_control`, `browser_control`: these change things, so they
  must **ask**. `home_control` is a smart-home control: per `CLAUDE.md`, lights/plugs
  may be card-free only behind an off-by-default setting, and locks/doors/alarms
  always keep their own card — so a plain `"ask"` is the safe, honest choice.
- **Timers/reminders/to-dos** — `set_timer`, `set_reminder`, `todo_add`, `todo_done`,
  `coming_up`: `CLAUDE.md` (owner, 2026-09-26) says *"Plain repeating reminders, alarms
  and the standby schedule need no card"*, so `"auto"`.

**Do not guess a tier.** Read the neighbouring table entries and the project's own
notes, and if a tier is genuinely ambiguous, ask the owner with a short
multiple-choice question — a wrong tier either nags them forever or lets something
run without asking, and rule 4 is not negotiable.

## How to verify

1. `backend/test_agent.py` — must go from `97 passed, 1 failed` to all passing.
2. `backend/test_agent_plan_wiring.py` and `backend/test_agent_retirement_wiring.py`
   also failed on this; check them.
3. Run the repo's guards: `python tools\check_parity.py` (expect "No undecided
   drift") and `python tools\check_command_acl.py` (expect "338 commands,
   generate_handler! and build.rs agree").
4. Parse the changed `.ps1` and `.py` files before finishing.

## Standings and honesty notes

- **The update DID apply** — unlike the owner's previous attempt, which failed with
  "NOTHING HAS BEEN CHANGED". That was caused by `thinking.patch` coming before
  `focus.patch`; it is fixed in the repo copy at
  `...\Epic-Jarvis-main\scripts\apply-patches.ps1` (now `focus.patch` line ~469,
  `thinking.patch` line ~478). **That fix is NOT on GitHub** — a fresh download still
  has the broken order. Do not re-download without re-applying it.
- **The log shows 84 `FAIL` lines, but the individual suites are "hundreds passed,
  1-3 failed"** (e.g. `test_agent` 97/1, one suite 501/1, another 583/2, another
  734/3). The picture is far better than "62 suites failed" sounds.
- **The gate entries are ONE cluster, not the whole problem.** Also seen in the log,
  each needing its own investigation (do not assume one cause):
  - stale generated fixtures: `focus-cases.json`, `inbox-tidy-cases.json`,
    `voice-status-cases.json`, `voice-training-cases.json`, `phone-voice-cases.json`
    ("does not equal a fresh run of the producer");
  - `bind '0x00000000' gets no second listener` (and `'0.0'`, `'0.0.0'`,
    `'000.000.000.000'`) — **security-shaped, NOT yet investigated**;
  - a backup/restore cluster (~17 checks); a note-write outside-text check; a memory
    erase check; hardware golden files; `test_apps.py`'s 6 failures.
- **No test suite can be run inside the agent's own sandbox** (it refuses the temp
  directory the suites create). The owner runs them on their PC; ask for output.
- Repo hygiene: no scratch files, delete `__pycache__`, keep the tracker tidy.
