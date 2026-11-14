# Post-F4 field probes (live backend F4 `7cc47e55a`, live apps) — 2026-11-03

Harness: `.dsh-scratch\FIELD-TEST-2026-11-03\probe.py` (GET only; token read into memory,
never printed; no card approved, no setting changed, no process touched).
Runs:
- `post-f4-probe.txt` — 2026-11-03T12:26:05-08:00, first run, **15 PASS / 2 FAIL / 0 BLOCKED**
- `post-f4-probe-v2.txt` — same live state, after fixing one harness verdict bug (see below),
  **16 PASS / 1 FAIL / 0 BLOCKED**

Live build seen: `server=jarvis-hud api=1 voice_mode=owner`, `/api/version` capabilities=18.

## The 16 PASS

build-version; build-status; data-health; voice-status; approvals-read; devices-read;
habits-read; week-in-review; goals-read; goals-progress (see below); self-explain-apps;
self-explain-model (`current=qwen3.5:9b previous=qwen3:8b installed=15`);
self-explain-price; def028-live-words (the false Live promise is gone — the one FAIL on F3
is now PASS); wake-word; live-voice-check.

Compared with the F3 capture (`17 probes: 11 PASS, 1 FAIL, 5 BLOCKED`): the five rows that
were BLOCKED on F3 (habits, mood, week-in-review, goals-read, goals-progress) now exist, and
`def028-live-words` flipped FAIL -> PASS. That is F4 reaching the live system.

## The one FAIL — a real, minor contract nit (not a deploy failure)

`mood-read  200  FAIL  ok=True rows=None latest=null`

`GET /api/mood?days=7` answers 200 with `ok: true` and `rows: null` when the owner has no
mood logged. `docs/JARVIS-API.md:31105` says the route answers "the last N days **as rows**
(newest first)"; every other list route (habits -> `habit=0`, goals -> list) answers an
empty list, and the probe (correctly) expects a list. So: the route is wired, but the empty
case returns `null` where the documented shape says rows. Classification: **PARTIAL at
most — never PASS**. Small fix later: return `[]` (one line in the mood route) plus a test.
Do not "fix" the probe to accept null; the probe's expectation follows the doc.

## The harness bug that produced the second FAIL (fixed, both runs kept)

`goals-progress 404 {"ok": false, "error": "no such goal"}` was printed FAIL although the
probe's own docstring says a 404 whose body starts "no such goal" is exactly the proof that
the route is wired. Cause: the runner's verdict line was
`verdict = "PASS" if st == 200 else "FAIL"`, so no honest non-200 refusal could ever pass.
Fixed in the harness only (backup `probe.py.before-verdict-fix-20261103`); its rule is now
"the probe's own assertion is the proof; the status is shown beside it" — still BLOCKED for
401/403 and for a route that is absent. The v2 run is the number to quote.

## What this means for the F5 deploy (step 18 reference)

F5's runbook expects "the same counts F4's own post-deploy capture recorded". That
reference is now measured: **16 PASS / 1 FAIL / 0 BLOCKED** with `mood-read` as the only
FAIL, and `probe_f5.py`'s own 19-probe set is separate (its `settings-receipt-undoable`
row stays BLOCKED until one cardless setting change runs in the new process — do not
"fix" it).
