# contract/ - the shared tables the apps and the PC both read

This folder holds small, data-only contracts: one table of facts that more than
one surface must agree on. They are read by tests/checkers and by the code that
owns the next copy, so two surfaces cannot quietly disagree.

## `schedule-cases.json` - the ONE schedule action table (F5 / Q2, 2026-10-22)

The one answer to: **for one scheduled job, which buttons may a surface draw, in
which order, with which words?** It is derived from the PC's real authority -
`backend/jarvis_schedule.py`'s `Kind` registry and `Scheduler.act()` decision
table (never from prose) - plus Wave D-1's `ready_for_review` marker.

**How to read it**

- `labels` - the exact user-facing word for every action, and the two amounts the
  PC really uses: `add_time` is `length_words(300)` (5 minutes) and `snooze` is
  `length_words(SNOOZE_DEFAULT)` (10 minutes). The plus sign on `+5 minutes` is a
  button's word, not a backend number.
- `kinds` - one entry per schedule kind. `listed: true` means a row appears in
  Coming up / the HUD Reminders list; `false` means the kind is internal. A
  kind's `states` map lists its actions **in button order** for `active`,
  `paused`, `waiting` and (for a kind that can be snoozed) `fired`.
- `states.ready_for_review` - Wave D-1 (merged to main as #722 / `478c934f0`, 2026-10-22): a to-do Jarvis has finished its part of.
  It adds a **marker and the sentence**, never a new button: `done` and `delete`
  are still the only actions, and only the owner's `done` completes it.
- `surfaces` - the three places that draw buttons, with the file that holds each
  one's table, an `owner`, and a `status`. `pending` means **the surface has not
  consumed this table yet**; its differences are reported and excused (xfail with
  a reason). `enforced` means a difference is a failure.

**What consumes it, and in what order**

| surface | file | owner of the consuming change |
|---|---|---|
| HUD Reminders | `jarvis-desktop/src/jarvis_hud.html` (3 byte-identical copies) | Coherence Fix Slice, Session A |
| Brain "Coming up" | `jarvis-desktop/src/coming-up.js` | Coherence Fix Slice, Session A |
| Phone Coming up | `jarvis-client/app/src/main/java/com/jarvis/client/net/Schedule.kt` | Session B / Android (Q2) |

None of those files is edited by the contract PR that added this file: the table
and its proof land first, then each owner flips its status when the consuming
change lands. The same table is what a surface should draw; a surface may read
the JSON at build time or copy its values, but it must not keep a fourth
hand-written set.

**How it is proved, and how to turn it strict**

```
py -3 tools/check_schedule_actions.py            # report; exit 0 while gaps are the named ones
py -3 tools/check_schedule_actions.py --strict   # a pending gap is a failure
py -3 tools/check_schedule_actions.py --json     # machine-readable
py -3 backend/run_suites.py test_schedule_contract.py   # the suite (authority + checker)
```

`backend/test_schedule_contract.py` also proves the table against the real
registry and `Scheduler.act()` on this PC: `add_time` only on a timer, `done`
only on a to-do, `pause` never on a to-do or a `Kind.ends` kind, `resume` only
from paused, `snooze` only on a fired timer/alarm/reminder, `delete` on every
listed and fired row. The checker reads each surface's own table from the source
shape it has today (an unrecognised shape is reported, never guessed at), so a
surface PR that renames its table updates the checker in the same change.

When the last surface lands, flip its `status` to `"enforced"` and the same
checker becomes the cross-surface test; `--strict` can be wired in the same PR.
