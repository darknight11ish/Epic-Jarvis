# F4 field test - the read-only live probe harness

One page: how to run it, what each probe proves, and what it deliberately does not touch.

## Run it

From the repository root (`C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`):

```powershell
python .dsh-scratch\FIELD-TEST-2026-11-03\probe.py
```

It prints its report and writes nothing else. To keep the report:

```powershell
python .dsh-scratch\FIELD-TEST-2026-11-03\probe.py | Tee-Object .dsh-scratch\FIELD-TEST-2026-11-03\post-deploy-probe.txt
```

No arguments, no flags, no setup. It needs the two things the live HUD needs anyway: the backend
running on `http://127.0.0.1:4719`, and the token at `%APPDATA%\Jarvis\token`.

## Which build the pre-deploy evidence came from

[`pre-deploy-probe.txt`](pre-deploy-probe.txt) was captured **2026-11-03 09:09:43 -08:00** against
the **live F3 build** - the deploy that was running *before* today's F4 deploy. Two things identify
it, both in the capture:

- the HUD's own `/api/version` says `server=jarvis-hud api=1`, and its `started` stamp
  (`1793657410.82`) is **2026-11-02 14:10:10 -08:00** - that is the running process, not a rebuild;
- the F4 routes are **absent** (`/api/habits`, `/api/mood`, `/api/habits/week`, `/api/phone/apps`
  and the goals progress route all answer `404 {"error": "not found"}`), and `/api/asks_first`
  still carries the pre-fix DEF-028 sentence. On an F4 build those flip.

That is how F3 is known here: by its answers, not by a version string - this API has no build
number to read.

## The six honesty rules it runs on

1. **A route that is not in this build is BLOCKED, never PASS.** `404 {"error": "not found"}` is the
   HUD saying "no such route"; the harness prints BLOCKED and says so.
2. **A 401/403 is BLOCKED, not a broken backend.** A bare request answering 401/403 means the
   listener is alive and refusing - so the run is BLOCKED with `auth refused`.
3. **BLOCKED is never counted in the PASS column**, and the summary prints the three counts
   separately.
4. **The token is never printed, logged or written.** It is read into a local variable the same way
   `.dsh-scratch/FIELD-TEST-2026-11-02/hud.py` reads it (`jarvis_token_store.resolve`), and every
   printed character passes through `scrub()`, which replaces it with `<TOKEN-REDACTED>`.
5. **One probe's PASS bar is the fix, not the wire** (`def028-live-words`). It is marked on the row
   and in the matrix, so its FAIL on F3 is not mistaken for a harness fault.
6. **A PASS here is wiring and state, not the owner's experience.** The half that needs his voice,
   his thumb or his eyes is Sub-Row B in [`MATRIX.md`](MATRIX.md) and is BLOCKED-owner-away.

## What each probe proves

| probe | route | what a PASS actually proves |
|---|---|---|
| `build-version` | `GET /api/version` | the live HUD answers and identifies itself, with its capabilities block |
| `build-status` | `GET /api/status` | routing and the interrupt budget read, and the budget has a shape |
| `data-health` | `GET /api/data-health` | 6 data stores open and check out, `warn=0` |
| `voice-status` | `GET /api/voice/status` | the voice gate's live state: enrolled, sample count, threshold |
| `approvals-read` | `GET /api/pending` | the approval queue reads, and the 20-entry history names **who decided** each past card |
| `devices-read` | `GET /api/devices` | the device registry reads - which devices may decide a card |
| `habits-read` | `GET /api/habits` | F4: the habit list answers `ok:true` with a `habits` array |
| `mood-read` | `GET /api/mood?days=7` | F4: the mood rows, `latest` and the 1-5 scale read |
| `week-in-review` | `GET /api/habits/week` | F4: the week's counts answer `ok:true` with their own keys |
| `goals-read` | `GET /api/goals` | the goals list plus its limits read |
| `goals-progress` | `GET /api/goals/no-such-goal-probe/progress` | F4: the progress-log route is wired - it answers `no such goal` instead of "no such route". A read of a goal that cannot exist is the only read-only proof; creating a goal would be a write |
| `self-explain-apps` | `GET /api/phone/apps` | the app allow-list read that the new explanation rests on |
| `self-explain-model` | `GET /api/models` | `current` / `previous` / `installed` - the live truth behind "which model is answering" |
| `self-explain-price` | `GET /api/decks` | the `radar` list the price-radar explanation rests on (empty is an honest answer) |
| `def028-live-words` | `GET /api/asks_first` | **DEF-028**: the `fixed:live` row no longer promises "Every sentence is still checked", and says the check is **once per Live session** |
| `wake-word` | `GET /api/version` | the wake phrase and whether the wake word is on |
| `live-voice-check` | `GET /api/voice/live` | the Live session state (`state`, `on`, `session`, `ended`) the check belongs to |

17 probes: **four** baseline health reads, and **thirteen** aimed at the F4 wave's Sub-Row A rows -
one feature, plugins, has no probe at all, and two rows take two probes each (goals, approvals).

## What it deliberately does not probe, and why

- **`/api/plugins` - it does not exist, and the design says it never will.** The plugins feature is
  two chat tools (`plugin_list`, `plugin_switch`), and its own changelog says *"there is no
  `GET`/`POST` for any of this"*. There is nothing read-only to call, so F4-07's Sub-Row A is
  BLOCKED with that citation instead of a made-up route.
- **`/api/selftest`, `/api/health`, `/api/features`, `/api/settings` - checked, absent, dropped.**
  All four answered `404 {"error": "not found"}` on F3. They were candidate probe targets; calling
  them would have produced four meaningless BLOCKEDs dressed up as features.
- **`/api/voice/wake` - absent on F3** (`404`). The wake word is read from `/api/version` instead,
  which is where the live build actually keeps it.
- **`/api/live/stream` - not probed.** It answers `501` with "the persistent stream is switched off
  on this PC"; that is a policy state, not a Live voice check, and probing it would read as a
  failure when nothing is wrong. `live-voice-check` reads `/api/voice/live` instead.
- **Anything that writes.** No `POST`/`PUT`/`DELETE` on any path, ever: no card approved or denied,
  no setting changed, no plugin toggled, no Live session started, no goal, habit or mood row
  created, no pairing, no process restarted. The three functions that make a request all use
  `method="GET"`; there is no code path that can send anything else.
- **The phone.** It is a separate device with its own surfaces; nothing here reaches for it. The
  owner's thumb on it is Sub-Row B.

## Files in this folder

| file | what it is |
|---|---|
| `probe.py` | the harness - GET-only, token never printed, writes nothing but its own console output |
| `pre-deploy-probe.txt` | the real captured output of running it against live **F3** on 2026-11-03 09:09 |
| `MATRIX.md` | the wave's field-test matrix: 12 features × Sub-Row A (automated) and Sub-Row B (owner) |
| `README.md` | this page |
