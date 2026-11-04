# watch-decisions

What the GitHub watcher **would** have told you: one structured decision row per
event, written instead of interrupting, readable before you let the watcher
speak.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this, and there is nothing in the core to take out: the feature
was born as a folder. Copy this folder into the backend's `jarvis_plugins\`
folder (or run `scripts\add-plugin.ps1 -Name watch-decisions`) and restart
Jarvis.

- Module the loader calls: `jarvis_watch_ci.install()` (takes the core's Handler)
- The patch this replaces: none - this is not a feature that used to be a patch
- Position in the loader's order: 150, after every folder the old patch stack had
  (`receipts` at 149), so its path is checked in the order it was added rather
  than in the middle of somebody else's

The module itself is shipped by `scripts/apply-patches.ps1` like every other
shipped module. This folder does not change it.

Its one route, and it is a **read**:

    GET /api/watch/decisions?limit=50

The answer carries `mode` (`off` / `observe` / `active`), the recent decision
rows newest first, and the closed `reasons` list so a client can explain a code
in plain words. A row is:

    {"at": 1762..., "source": "github_pr_ci",
     "thread_key": "pr:1135:a1b2c3d4e", "outcome": "would_notify",
     "reason_code": "ci_all_required_green",
     "shadow_reason_code": "observe_shadow_logged",
     "verdict": "all_green", "mode": "observe", "delivery": "shadow",
     "preview_text": "PR #1135 is green: all 7 required checks passed and ..."}

**Why observe exists.** A new proactive watcher starts in `observe`: it runs the
whole pipeline - polls, batches the seven required CI checks into one thread per
pull request, evaluates - and writes a row instead of speaking. You read the
rows, and when the log shows no noise you promote it to `active` in your
settings file (`[watch] pr_checks_mode = "active"`). The alternative - build the
rule, switch it on, get interrupted - is how a watcher ends up muted.

**What it never does.** It raises no approval card, approves nothing, pushes
nothing and merges nothing. Nothing here is always-on: the watcher polls only
when a job names a pull request, and there is no thread or timer of its own.
`observe` is the default even then, and an unreadable mode falls back to
`observe`, never to `active`.
