# Background and overnight work audit, 2026-09-27

Read-only audit. No code was changed. Scope: everything Jarvis does without
the owner actively chatting - timers/alarms/reminders, the standby schedule,
the morning briefing, "tell me when" (email/page watching), focus sessions,
the overnight memory tidy, backups, and the initiative engine. The
multi-step "plan card" / goals work is out of scope on purpose (it is
separate, ongoing work) and is not covered here beyond one aside in
"Found along the way".

Every real backend file named below was opened and read in full; every test
result below was produced by actually running the suite (`python3 backend/<test>.py`,
and the full `python3 backend/run_suites.py`), not by reading the code and
assuming. `backend/jarvis_gate.py` and the other owner's-PC-only files are
**not** in this repository (`docs/ARCHITECTURE.md` §9); nothing below claims
to have read them - claims about the gate are cited to a patch, a test, or
`docs/ARCHITECTURE.md`/`docs/JARVIS-API.md`'s own words instead.

## In short

1. **Every background mechanism in scope is a real, whole file in this
   repo, and its own test suite passes.** Running `backend/run_suites.py`
   (which stages the files the way `apply-patches.ps1` ships them, the same
   layout the owner's PC would run) gives **133 passed, 1 failed, 19
   skipped** - the 1 failure is about `jarvis_plan.py` (the plan-card
   feature), out of scope here; the 19 skips are suites that need files only
   the owner's PC has (`jarvis_hud.py`, `jarvis_gate.py`, ...), named and
   skipped by design, not silently ignored. None of the 19 skips are for a
   mechanism in this audit's scope.
2. **The one bug this brief specifically asked about - four missing "auto"
   lines for read tools - is already fixed.** `backend/rebuilt/jarvis-framework.toml:90-93`
   now has `calendar_read`, `email_read`, `notes_search`, `home_read` all
   `= "auto"`, with a comment dated 2026-09-25 explaining what broke before
   the fix (every read asked, the briefing left out calendar/email, "tell me
   when" refused to be set up).
3. **The honest gap is not a bug, it is a documented limit: nothing in this
   list has been run on the owner's real PC yet.** `docs/JARVIS-API.md` says
   "Not run on the owner's PC" for the scheduler (§21.7), the standby
   schedule (§21.8), the briefing (§22.7/§30... see below), and "tell me
   when" (§22.7); backups say "Not run on Windows" (§45.6). Every test that
   exists uses a fake Ollama, a fake calendar, a fake mail server, or a
   hand-moved clock - never the real Windows box, real daylight-saving
   transitions there, or a real IMAP/CalDAV server.
4. **The overnight memory tidy is not built, and says so.** `jarvis_sleep.py`
   only offers to turn it on; the module's own docstring says "DELIBERATELY
   DOES NOT RUN ANYTHING YET" and turning the card on "records the wish and
   runs nothing" (`docs/ARCHITECTURE.md` §10, "Still missing"). This is by
   the owner's own decision to park memory-system automation, not an
   oversight.
5. **The initiative engine is a working shell with an empty check list, on
   purpose.** It ticks on a heartbeat and files findings correctly (tests
   below), but no check has ever been registered in it - `status()["checks"]`
   is 0 - because the original check list (`HEARTBEAT.md`) could not be
   recovered, and inventing one would mean Jarvis doing unattended things
   nobody chose. Timers, the briefing, "tell me when" and focus sessions do
   **not** run through it; each is its own kind on the scheduler instead.
6. **Both apps are wired up, and `tools/check_parity.py` is clean** ("No
   undecided drift") for everything in scope. The one deliberate
   asymmetry that touches background work - the initiative feed shows as
   transient HUD toasts on the desktop but a persistent, browsable list on
   the phone - is written down in `docs/ARCHITECTURE.md` §8 ("One-sided on
   purpose"), as the standing instruction requires.
7. **Failure modes are designed for, not left open.** A job missed while
   the PC was off or asleep fires once, late, never a burst (test proves
   it); the standby schedule and the desktop's watchdog (a real,
   independently-tested restart cap in `sidecar.rs`) both have a documented
   answer for a mid-run crash or restart, with one named gap each (below).

## What was checked, and its real status

| Mechanism | Real file(s) in this repo | Test suite | Result | Shipped/tested on owner's PC? |
|---|---|---|---|---|
| Timers, alarms, reminders, to-do, the one scheduler | `backend/jarvis_schedule.py` (1904 lines) | `test_schedule.py` | **254 passed, 0 failed** | No - "Not run on the owner's PC" (`JARVIS-API.md` §21.7) |
| Back-off for unasked offers | `backend/jarvis_backoff.py` (450 lines) | `test_backoff_rule.py` | **37 passed, 0 failed** | Runs everywhere the offers it guards run; not separately shipped-and-run |
| Morning briefing | `backend/jarvis_briefing.py` (1740 lines) | `test_briefing.py` | **230 passed, 0 failed** | No - "Not run on the owner's PC" (`JARVIS-API.md` §22.7) |
| Standby schedule | `backend/jarvis_standby_schedule.py` (304 lines) + `backend/jarvis_power_switch.py` (530 lines, does the real unload/warm-up) | `test_standby_schedule.py`, `test_power_switch.py` | **73 passed** / **63 passed** | No - "Not run on the owner's PC; Ollama was a stand-in" (`JARVIS-API.md` §21.8) |
| "Tell me when ..." (email/page watching) | `backend/jarvis_tellme.py` (1827 lines) | `test_tellme.py` | **203 passed, 0 failed** | No - "Not run on the owner's PC, nor against a real calendar or mail server" (`JARVIS-API.md` §22.7) |
| Focus sessions | `backend/jarvis_focus.py` (1685 lines) | `test_focus.py` | **227 passed, 0 failed** | No - "Not run on Windows. Every test uses a stand-in for 'what is in front'" (`JARVIS-API.md` §31 known gaps) |
| Overnight memory tidy | `backend/rebuilt/jarvis_sleep.py` (rebuilt) | part of `test_rebuilt.py` | passes, but tests only the offer/back-off, not a tidy - **there is no tidy to test** | **Not built at all**, by decision (`ARCHITECTURE.md` §10) |
| Initiative engine ("Findings") | `backend/rebuilt/jarvis_initiative.py` (239 lines) | `Initiative` class in `test_rebuilt.py` | passes (4 tests: first finding rings, same-size change still rings, `mark_seen` targets the right id, concurrent filing has no duplicate ids) | Runs, but ships with **zero registered checks** by design |
| Backups | `backend/jarvis_backup.py` (1281 lines) | `test_backup.py` | **76 passed, 0 failed** | No - "Not run on Windows" (`JARVIS-API.md` §45.6) |
| Full suite, staged like the real ship layout | all of the above + everything else | `backend/run_suites.py` | **133 passed, 1 failed (out of scope, `jarvis_plan.py`), 19 skipped (named, owner's-PC-only files)** | Confirms none of the above breaks when staged together |
| Events doorbell (used by all of the above so a stale read is never acted on) | `backend/rebuilt/jarvis_events.py` | `test_events_pump.py` | **8 of 9 pass** with `PYTHONPATH=rebuilt`; the 9th needs `jarvis_hud.py`, which is not in this repo (correctly `SKIP`ped by `run_suites.py`, not run bare) | n/a |

## The specific bug this brief asked about: is it fixed?

The brief asked to check whether the missing-`auto`-lines bug
`docs/APPROVALS-AUDIT-2026-09-26.md` row 1 found is still there:

> "Missing from `backend/rebuilt/jarvis-framework.toml` (lines 77-238), so
> each read asks. The README says they should be `auto`
> (`backend/README.md:3016-3020`)"

Read today, `backend/rebuilt/jarvis-framework.toml:88-93`:

```
[autonomy.tiers]
web_research              = "auto"
read_calendar             = "auto"
# The five tools of backend/README.md "What each one needs in jarvis_gate.py
# and jarvis-framework.toml" (2026-09-26: they were missing here, and a
# missing line means "ask" - every calendar, email, notes or home READ raised
# a card, the morning briefing left calendar and email out, and "tell me
# when" refused to be set up). Reads stay on the owner's own accounts and
# change nothing; turning a device on or off still asks.
calendar_read             = "auto"
email_read                = "auto"
notes_search              = "auto"
home_read                 = "auto"
home_control              = "ask"
```

**It is fixed.** All four lines are present, all `"auto"`, and the comment
right above them names the exact incident and its date. This means the
morning briefing's calendar/email reads and "tell me when"'s setup no
longer raise an unwanted card on a PC set up from this repo's shipped
settings file.

## The `may_offer(kind=)` rule: every call site checked

The brief asked to grep every `may_offer(` call site and confirm each
passes `kind=`, per `jarvis_backoff.py`'s own enforcement. Every real call
site in the shipped code (`grep -rn "may_offer(" backend/*.py backend/rebuilt/*.py`,
excluding tests and the definition itself):

- `backend/jarvis_second_card.py:2743` - `bo.may_offer(fp, kind=SUGGEST_OFFER_KIND)`
- `backend/rebuilt/jarvis_sleep.py:247` - `bo.may_offer(fp, kind=OFFER)`
- `backend/jarvis_skill_discovery.py:754` - `bo.may_offer(fp, kind="skill_offer")`

All three pass `kind=`. `test_backoff_rule.py`'s own
`t_every_offer_site_passes_its_kind` reaches the same three sites by
reading the shipped source as text and passed (`37 passed, 0 failed`, seen
above) - so this is not just a hand grep, it is enforced by a test that
runs every time. There are exactly three offers in the whole in-scope
surface: the overnight-tidy offer (which is real even though the tidy
itself is not built - the offer is what's gated), the skill-suggestion
offer, and the "would the bigger model help?" suggestion. None of the
scheduler kinds (timer, alarm, reminder, standby, briefing, "tell me when",
focus) go through `may_offer` at all, because they are things the owner
asked for directly, not unsolicited offers - consistent with
`docs/ARCHITECTURE.md` §12's own rule ("the back-off only decides whether
to ask; the owner's own requests never consult it").

## Missed-while-off, and other failure modes

- **A job missed while the PC was off fires once, late, never a burst.**
  `backend/test_schedule.py` has a dedicated test, `t_missed_while_off_goes_off_once_late`
  (line 261), which sets the clock forward across two missed fire times and
  asserts: both are marked `late=True`, the alarm's message says "missed at
  07:00" (the actual time, not "now"), the next scheduled time is tomorrow's
  - not one of the missed ones - and a second look "goes off nothing (never
  a burst)". This test is inside the 254 that passed.
- **The standby schedule's own docstring lists six ownership edge cases in
  full** (hand-set standby vs. schedule-set standby, a task running when the
  start is due, a backend restart mid-window) and states the one known gap
  plainly: "The backend restarted inside the window: the mode is kept in
  memory (`jarvis_power`), so it comes back Active... A known gap, said in
  `docs/JARVIS-API.md` 21.8." (`backend/jarvis_standby_schedule.py:83-93`).
  This is the same gap `docs/JARVIS-API.md`'s own "Known gaps, said
  plainly" section names for the standby schedule.
- **The desktop's process watchdog is real and independently tested.**
  `jarvis-desktop/src-tauri/src/sidecar.rs` restarts a crashed or hung
  backend it owns, capped at `MAX_RESTARTS = 3` restarts inside a sliding
  `RESTART_WINDOW` (`sidecar.rs:106-109`), with its own unit tests
  (`the_cap_allows_exactly_three_then_refuses`,
  `once_given_up_the_cap_never_reopens_this_run`, `sidecar.rs:1023-1053`).
  `docs/ARCHITECTURE.md` §8 names this exact mechanism ("the restart-with-a-
  cap watchdog... a process on the PC: the Rust desktop app supervising the
  Python backend it started"). This is the answer to "what happens if the
  backend crashes mid-job" for anything the desktop supervises; a
  scheduler job itself, once the backend is back up, is caught by the
  missed-while-off rule above.
- **The overnight memory tidy has no failure mode to check, because it does
  not run anything** - by decision, not oversight (see "In short", item 4).

## Both apps

`python3 tools/check_parity.py` (run against this repo, not guessed):

```
desktop: 128 routes   phone: 108   ported: 107   not porting: 18
still to port: 1   not the backend's: 2   planned (backend first): 0
...
No undecided drift.
```

The one route "still to port" (`/api/retrieve`, a retrieval trace) is
unrelated to background work. Checked directly for the mechanisms in
scope:

- **Standby**: desktop `coming-up.js` / `brain.js`; phone `net/Schedule.kt`.
  Both surface it under Coming up / Brain, as `docs/ARCHITECTURE.md` §8's
  own table describes (line 1534, 1803).
- **Briefing**: desktop `briefing.js`, `briefing-settings.js`,
  `coming-up.js`; phone `net/Briefing.kt`, `ui/screens/BriefingPlate.kt`,
  `ui/screens/BrainScreen.kt`.
- **Focus sessions**: desktop `focus.js`, `widget.js`; phone `net/Focus.kt`
  and its screens. One deliberate PC-only piece: `GET /api/focus/callout`
  (the spoken drift line) is refused to any address but loopback and the
  desktop's Rust is the only side that ever asks for it
  (`docs/JARVIS-API.md` §31.2); this is written down in
  `docs/ARCHITECTURE.md` §8 (line 1539) as the reason, not an oversight.
- **"Tell me when"**: desktop `coming-up.js`; phone `net/WatchNotify.kt`,
  `ui/screens/WatchNotifyPlate.kt`.
- **Backups**: desktop `backup.rs`, `backup-settings.js` (full control);
  phone `net/Backup.kt`, `ui/screens/BackupPlate.kt` - **deliberately
  read-only** ("Last backup: 3 days ago."), because the folder picker is
  Windows', the recovery code is typed on the PC, and restoring needs
  Windows Hello there. `tools/check_parity.py` marks every backup route but
  `GET /api/backup` `deliberate`, and `docs/JARVIS-API.md` §45.5 states the
  same reason. This is documented one-sidedness, not a gap.
- **Initiative / "Findings"**: the one genuinely interesting asymmetry.
  `docs/ARCHITECTURE.md` §8 (line 1569): the desktop's HUD window polls
  `GET /api/initiative` but only shows transient cards while the HUD
  happens to be open, with no persistent section in the desktop's Brain
  window; the phone's Brain gives the same feed a persistent, browsable
  place. Written down as deliberate, dated 2026-09-27 off the ease-of-use
  audit. Since the engine ships with zero checks registered, this
  asymmetry has no practical effect yet - there is nothing in the feed on
  either app until a check is written.

## Found along the way (out of scope, noted honestly)

- `backend/run_suites.py`'s only real failure across the whole suite is
  `test_shipped_modules.py`: `backend/jarvis_plan.py` exists in `backend/`
  but is not registered in `apply-patches.ps1`'s `$SHIPPED` list or
  `_where.SHIPPED` (checked at `test_shipped_modules.py:236-240`, which
  reads `backend/*.py` and fails any name missing from `SHIPPED`). This is
  the plan-card/goals feature, explicitly out of scope for this audit -
  noted here only because it is the one real failure in the full run, so a
  reader of the raw test output is not left wondering about it.

## Verdict

**Background and overnight work is well-built and well-tested against
itself.** Every mechanism in scope is a real, complete file with a passing
test suite; the one specific bug this brief asked about is already fixed;
the missed-while-off rule, the offer back-off, and the desktop's crash
watchdog all do what their docs claim, checked against running code, not
just prose. Both apps carry every feature that makes sense on both, and
every one-sided piece is written down with its reason.

**It does not yet "work well" in the sense of proven on the owner's actual
PC** - every one of the seven scheduled/watching mechanisms says, in its
own docs, "Not run on the owner's PC" (or "Not run on Windows"). That is
not a code defect; it is untested-in-the-real-world, and the docs say so
rather than claiming otherwise.

**Highest-value next step:** run the scheduler, the standby schedule, the
briefing, and "tell me when" for real on the owner's Windows PC, for at
least one real missed-while-off cycle (put the PC to sleep with a timer and
a reminder pending, wake it late, confirm each fires once) and one real
overnight standby window. Nothing in this repository can do that - it
needs the owner's own machine - but until it happens, "well-tested" and
"proven to work" remain two different claims, and only the first one is
earned today.
