# contract/ - the shared tables the apps and the PC both read

This folder holds small, data-only contracts: one table of facts that more than
one surface must agree on. They are read by tests/checkers and by the code that
owns the next copy, so two surfaces cannot quietly disagree.

## `schedule-cases.json` - the ONE schedule action table (F5 / Q2, 2026-10-22)

The one answer to: **for one scheduled job, which buttons may a surface draw, in
which order, with which words?** It is derived from the PC's real authority -
`backend/jarvis_schedule.py`'s `Kind` registry and `Scheduler.act()` decision
table (never from prose) - plus Wave D-1's `ready_for_review` marker.

**The shared desktop table lives in code now.** Coherence slice #729 added
`jarvis-desktop/src/hud-actions.js` (no dependency, no DOM): `ACTION_LABELS`,
`WENT_OFF_ACTIONS`, `NO_PAUSE_KINDS`, `actionsFor()` and `actionNames()`. The
HUD's Reminders panel imports it (and keeps a browser-served fallback for a page
with no module graph); the Brain's `coming-up.js` imports the same functions.
The contract's `shared` entry names that module; the checker reads it plus the
HUD's fallback table and compares both to the contract.

**How to read the contract**

- `labels` - the exact user-facing word for every action, and the two amounts the
  PC really uses: `add_time` is `length_words(300)` (5 minutes) and `snooze` is
  `length_words(SNOOZE_DEFAULT)` (10 minutes). The plus sign on `+5 minutes` is a
  button's word, not a backend number.
- `kinds` - one entry per schedule kind. `listed: true` means a row appears in
  Coming up / the HUD Reminders list; `false` means the kind is internal. A
  kind's `states` map lists its actions **in button order** for `active`,
  `paused`, `waiting` and (for a kind that can be snoozed) `fired`.
- `states.ready_for_review` - Wave D-1 (merged to main as #722 / `478c934f0`):
  a to-do Jarvis has finished its part of. It adds a **marker and the
  sentence**, never a new button: `done` and `delete` are still the only actions,
  and only the owner's `done` completes it. No surface draws the marker yet, so
  `surface_status` is `pending-d1-surfacing` and the checker reports that as a
  note, not as a surface difference.
- `surfaces` - the places that draw buttons, with the file that holds each one's
  table, an `owner`, and a `status`. `enforced` means a difference is a failure;
  `pending` (none today) means a surface has not consumed the table yet and must say
  `"xfail": true` with a reason (its differences are printed as `EXPECTED-GAP`).
- `management` - **HUD Reminders Phase 2** (2026-10-22): `edit`, `move` and
  `reorder` are kept out of the per-kind `states` action lists because they open
  an editor / list picker / keyboard reorder instead of drawing one button per
  action. `authority.verbs` is the closed nine-verb set, `management.cases` is
  the real accept/refuse matrix driven through the PC's `Scheduler.act`, and
  `management.surfaces` names the open Phase-2 UI branch that must consume it.
  The Phase-2 words (`Edit`, `Save changes`, `Cancel`, `To-do list`, `Move up`,
  `Move down`) are the open branch's own words.

**Consumers and current status**

| surface | table it reads | status |
|---|---|---|
| HUD Reminders | `jarvis-desktop/src/hud-actions.js` (import) + browser-served `fallbackActionsFor` in `jarvis_hud.html` (3 byte-identical copies) | **enforced** (consumed in #729; both copies match every case) |
| Brain "Coming up" | `jarvis-desktop/src/coming-up.js` imports `ACTION_LABELS` / `WENT_OFF_ACTIONS` / `actionNames` from `hud-actions.js` | **enforced** (a pure consumer since #729) |
| Phone Coming up | `jarvis-client/.../net/Schedule.kt` hand-written `actionsOf`/`labelOf`/`ACTIONS` | **enforced** - consumed 2026-10-23; `add_time` is in `ACTIONS`, `actionsOf` and `labelOf` |
| HUD/Brain Phase-2 `edit`/`move`/`reorder` | the Phase-2 block of `jarvis-desktop/src/hud-actions.js` (`EDIT_LABEL`, `EDITABLE_KINDS`, `canEdit`) on `feat/hud-reminders-phase2-edit-move-reorder-ui` | **pending** on the open UI branch; phone is `not-planned` (its Coming up has no editor yet). This is a contract entry, not a second table. |

Two contract entries are deliberately **outside the cross-surface comparison
yet**, each with its reason and owner beside it in the JSON: the D-1
`ready_for_review` marker (backend-only; no surface draws it) and the Goals-only
`goal_checkin` kind (Goals' own module registers it, the phone already draws it
with no buttons, the desktop surfaces do not special-case it yet). Removing
either note means adding the case, not hiding it.

**How it is proved, and how to turn it strict**

```
py -3 tools/check_schedule_actions.py            # report; enforced surfaces must match
py -3 tools/check_schedule_actions.py --strict   # a pending gap WITHOUT xfail is a failure
py -3 tools/check_schedule_actions.py --json     # machine-readable
py -3 backend/run_suites.py test_schedule_contract.py   # the suite (authority + checker)
```

`backend/test_schedule_contract.py` also proves the table against the real
registry and `Scheduler.act()` on this PC: `add_time` only on a timer, `done`
only on a to-do, `pause` never on a to-do or a `Kind.ends` kind, `resume` only
from paused, `snooze` only on a fired timer/alarm/reminder, `delete` on every
listed and fired row. It also reads the **verb set** out of `Scheduler.act`'s
own source (AST, no backend import) and fails if `authority.verbs` differs, and
it drives every `management.cases` entry through the real `act()` with its
expected 200/202/400/409. `tools/check_schedule_actions.py` asserts the same
verb set independently, so a future verb cannot drift out of the contract. The
checker reads each surface's own table from the source shape it has today (an
unrecognised shape is reported, never guessed at), so a surface PR that renames
its table updates the checker in the same change.

When a surface consumes the table, remove its `"xfail": true` (none today) and flip its `status` to
`"enforced"`; the same checker then becomes the complete cross-surface test, and
`--strict` can be wired in that PR. The suite proves that one-switch flip on a
copy of the contract today.
