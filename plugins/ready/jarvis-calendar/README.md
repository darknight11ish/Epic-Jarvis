# Jarvis Calendar - the calendar Jarvis owns

**What it is.** Your own events, kept by Jarvis on this PC. They are shown
beside Google Calendar and iCal - never merged into either, never sent to
either, and never synced out. The feature is **on by default**; one switch
turns every surface off and **keeps every event**.

This folder is the whole of the wiring: `plugin.json` names
`jarvis_local_calendar`, and `jarvis_plugins.py` calls that module's own
`install()` with the server's origin/token checks. No patch to `jarvis_hud.py`,
no approval-gate entry, no network door.

**Where the data lives.** `calendar.db` in the Jarvis settings folder, beside
`schedule.db` and `memory.db` - plain SQLite, the same boundary this project
already accepts for reminders (the Windows account plus BitLocker). The switch
is `calendar-settings.json` beside it: **no file means on**; a damaged file
means off, with a sentence saying why. `JARVIS_CALENDAR_DB` and
`JARVIS_CALENDAR_SETTINGS` point both at a throwaway file for a test.
`calendar.db` is on `jarvis_backup.SOURCE_DBS`, so a backup carries it.

**The routes** (all behind the server's own origin check and
`X-Jarvis-Token`; the three writes are host-only writes for now, and the HUD
commands that will call them are a later slice):

| route | what it does | card |
|---|---|---|
| `GET /api/calendar?days=7` | the next 1-90 days (default 7), every event expanded into the window, plus a `sources` block that says honestly what Google and iCal are doing | no |
| `GET /api/calendar?id=<id>` | ONE stored event | no |
| `POST /api/calendar/add` | one event; `title` is required, `date` defaults to today | **no** - the owner's 2026-10-29 ruling |
| `POST /api/calendar/act` | `{"id", "do": "delete" \| "update", ...}` - ONE event. There is no delete-all and no bulk form | no |
| `POST /api/calendar/settings` | `{"on": true \| false}` - a preference you can change back in one press | no |

**Why the writes are cardless.** `docs/ARCHITECTURE.md`'s "Cardless by design"
table now carries this feature on the reasoning of its "One job on the
schedule" row: ONE item, no list form, no delete-all, and the audit line
carries ids and outcomes only - never the event's words. Rule 4 still applies
to any surface that acts: it holds its own writes while the event stream is
stale. The owner's words and the full reasoning are in the `decisions.d/`
fragment of the same PR.

**The wall clock, and why there is no epoch.** An event stores its date and
time as they read on the clock, plus an informational `tz`. Storing a bare
epoch would move a 09:00 event to 08:00 or 10:00 across a daylight-saving
change; this keeps 09:00 as 09:00. An epoch is computed on read for ordering,
and it follows this PC's own clock (a time that never happened goes at the
moment of the jump; a time that happened twice takes the first).

**Recurrence, v1.** `none`, `daily`, `weekly`, `monthly`, optionally with a
`count` or an `until` date. A monthly event on the 31st is clamped to the
short months (28 February in a common year), so it repeats every month instead
of disappearing. Editing or deleting a repeating event changes the WHOLE
series; there are no per-occurrence exceptions in v1.

**Reminders are stored, not rung.** `remind_minutes` is kept for the PC or the
phone to use later; nothing in this slice rings.

**Switched off.** The read answers 200 with `"on": false` and an empty list
(and still counts what it keeps). An add or an act is refused in words. The
file is never deleted, and turning it back on shows everything again.

**Self-check.** `py -3 jarvis_local_calendar.py check` seeds a throwaway
folder, proves add / list / act / settings / backup-list / recurrence / DST,
prints PASS and the counts, and removes its own folder. It touches no owner
data and opens no network.

**Tests.** `backend/test_local_calendar.py`: the routes through a stand-in
Handler (origin and token on all four), add/update/delete, no bulk, the
off-keeps-data rule, a damaged settings file and a damaged database, the DST
wall clock, recurrence including the 31st, the one-day window, the backup
line, and the self-check.
