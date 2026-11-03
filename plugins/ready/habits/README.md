# habits

Habit check-ins: "I want to walk three times a week", a nudge at the time you
picked, and **one tap** that records it happened that day.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name habits`) and restart Jarvis.

- Module the loader calls: `jarvis_habits.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Routes: `GET`/`POST /api/habits`, `POST /api/habits/<id>/tick|untick|stop`,
  `GET /api/habits/week`, `POST /api/habits/week/start|stop`

## What it keeps, and where

`habits.db` beside `goals.db` in the Jarvis settings folder: one row per habit,
and **one row per habit per DAY**. A second tap on the same day changes
nothing - the table's primary key is `(habit, day)`. Stopping a habit deletes
its reminder and **keeps every tick**.

## What it deliberately does not do

- **No score, no streak, no percentage, no "longest run".** This project has
  removed a streak twice on purpose. The nudge under the job is one sentence
  in your own words; nothing here computes a rate.
- **No card for logging.** Creating a check-in and ticking it are both the
  cardless `plain_repeat` class - your own tap, reading nothing new, acting on
  nothing. Stopping is immediate.
- **Learns nothing.** A habit's name and its ticks never reach the learner,
  because no such call exists in the module; `backend/test_learning_exclusion.py`
  proves it in both directions.
- **Sends nothing.** No model call, no network call, no child process.

## The weekly review

The same module owns the **week in review**: four counts of stored rows
(habit ticks, goal steps ticked, reminders that went off, mood entries) filed
as one line in your own journal through the existing cardless notes route. It
runs only because you turned it on, and `POST /api/habits/week/stop` turns it
off in one tap. It interprets nothing and says so in the line it writes.
