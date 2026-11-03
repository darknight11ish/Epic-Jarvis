# mood

The owner's own mood log: **one 1-5 tap a day**, optional words, and a history
to look at. Kept on this PC, never learned, never sent anywhere.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name mood`) and restart Jarvis.

- Module the loader calls: `jarvis_mood.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Routes: `GET /api/mood` (history for the chart), `POST /api/mood`

## The shape, exactly

One row per day: a whole number from 1 to 5, and up to 200 characters of your
own words (or none). A second entry the same day **replaces** the first - that
is what one row per day means. The chart is a display concern: the module
returns rows and computes no average, no trend and no verdict.

## Why it exists after the project said no

A mood log was declined on 2026-09-26 ("a health-like record nobody asked
for"). The owner asked for one on 2026-11-02 and chose this shape himself, so
the decline is reversed for **his own log and nothing else**
(`decisions.d/2026-11-02-mood-log-recorded.md`).

## What it deliberately does not do

- **It is not learned, at all.** Mood values and words never become facts -
  not card-gated, impossible: no learner module names this one and it names
  none, and writing a mood creates no fact store. `backend/test_learning_exclusion.py`
  proves both directions.
- **It never asks.** There is no "how are you feeling today?" nudge and no job
  of its own; entries happen because you tapped.
- **It judges nothing.** No score, no streak, no interpretation, no advice.
- **It is not the crisis path.** A sentence that is bigger than a mood note
  still goes to `jarvis_wellbeing.py` and a real person; this module holds no
  help-line logic of its own, and a test pins that.
