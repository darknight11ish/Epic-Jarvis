# F5 field test - the read-only live probe harness

One page: how to run it, what each probe proves, which rows can only be proved after the F5 deploy,
and what it deliberately does not touch.

**The BEFORE evidence in this folder was captured against the live F3 build and MUST be re-run after
the F5 deploy.** Nothing in `post-f5-probe.txt` is a claim about F5.

## Run it

From the repository root (`C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main`):

```powershell
python .dsh-scratch\FIELD-TEST-2026-11-03\probe_f5.py
```

It prints its report and writes nothing else. To keep the report:

```powershell
python .dsh-scratch\FIELD-TEST-2026-11-03\probe_f5.py | Tee-Object .dsh-scratch\FIELD-TEST-2026-11-03\post-f5-deploy-probe.txt
```

No arguments, no flags, no setup. It needs the two things the live HUD needs anyway: the backend
running on `http://127.0.0.1:4719`, and the token at `%APPDATA%\Jarvis\token`. It reuses
[`probe.py`](probe.py), the F4 harness in this same folder, by importing it - so there is **one**
token read, **one** `scrub()`, **one** GET-only request function and **one** set of verdict rules for
both harnesses, not two copies that could drift apart.

## Which build the BEFORE evidence came from

[`post-f5-probe.txt`](post-f5-probe.txt) was captured **2026-11-03 09:41:26 -08:00** against the
**live F3 build**, and it says so itself, three ways:

- `live build : server=jarvis-hud api=1 started=2026-11-02T14:10:10 -08:00` - that is the running
  process, not a rebuild;
- `wave : F3 (the F4 habits route answers 404, so this capture is BEFORE F4)` - the harness asks
  `/api/habits` once, purely to date its own capture, because an F4 build serves that route;
- the F5 surfaces answer what an F3 build answers: `/api/receipts` says `undoable=false` for every
  settings receipt (no settings restorer is in the live process), and `GET /api/chat` is `404`.

`api=1` is not a build number - this API has none. The build is known by its answers.

## The honesty rules it runs on

The first six are `probe.py`'s, unchanged, because the harness imports it:

1. **A route that is not in this build is BLOCKED, never PASS.** `404 {"error": "not found"}` is the
   HUD saying "no such route"; the harness prints BLOCKED and says so.
2. **A 401/403 is BLOCKED, not a broken backend.** The listener is alive and refusing.
3. **BLOCKED is never counted in the PASS column.** The summary prints the three counts separately.
4. **The token is never printed, logged or written.** It is read into a local variable by
   `probe._token()` (the same `jarvis_token_store.resolve` path the F4 harness uses), and every
   printed character passes `probe.scrub()`, which replaces it with `<TOKEN-REDACTED>`. Checked, not
   assumed: the capture was read back and contains the token 0 times.
5. **A PASS is wiring and state, not the owner's experience.** That half is Sub-Row B in
   [`MATRIX-F5.md`](MATRIX-F5.md) and is BLOCKED-owner-away.
6. **One probe's PASS bar is a decision, not the wire** (`page-reader-not-switchable`,
   `page-reader-reach-line`): they PASS while the page reader stays unswitchable, which is the
   owner's decision of 2026-11-03. A FAIL there is the decision being reversed, not a harness fault.

And one rule F5 adds, because F5 adds **no route**:

7. **A surface that can only be reached with a POST is BLOCKED with the POST named.** The explain
   sentence, the "I could not read its current value" sentence, the `read_link` intent and its
   refusal of a non-link, the making of a cardless change and the applying of an undo all live
   inside a chat turn or on a POST. The harness prints those rows BLOCKED, prints the exact door, and
   never invents a route to stand in for them. Its closing block, `NOT PROBED READ-ONLY, BY DESIGN`,
   lists the four doors.

## What each probe proves

19 probes: **14 PASS, 0 FAIL, 5 BLOCKED** on live F3.

| probe | route | what a PASS actually proves |
|---|---|---|
| `build-identity` | `GET /api/version` | the live HUD answers and identifies itself: `server`, `api`, its `started` stamp and 18 capabilities |
| `data-health` | `GET /api/data-health` | 6 data stores open and check out (`warn=0`) - so a BLOCKED row below is not a broken backend |
| `explain-door` | `GET /api/chat` | **never PASS**: it records that the answer door is `POST /api/chat` only (a GET is 404), so the explain sentence cannot be provoked read-only |
| `feature-guide-tool` | `GET /api/reach` | the read-only tool that answers "what is X" is offered to the model (`feature_guide`, 11 tools offered) |
| `settings-write-tool` | `GET /api/reach` | the ONE allowed write path - the registry behind `change_setting` - is offered |
| `value-antislop` | `GET /api/antislop` | `antislop_mode`'s value reads (`mode=during`, `enabled=False`): the fourth fact has a live source |
| `value-personality` | `GET /api/manner` | the personality in force reads **and** is one of the 10 presets that answer publishes (`warm_peer`) |
| `value-focus-preset` | `GET /api/presets` | the applied focus preset reads and is one of the 9 it publishes (`general`) |
| `value-sky-show` | `GET /api/sky` | "Show the sun and moon" reads as a real bool (`show=True`) - a switch with no `BoolSetting` row |
| `value-weather-source` | `GET /api/sky` | the weather source reads and is one of the sources the sky module offers (`off`, of `off/home_assistant/open_meteo`) |
| `value-animal-switches` | `GET /api/animal` | all 7 shared animal switches read as bools, and the values table is complete against the switch table |
| `value-never-a-default` | `GET /api/chat` | **never PASS**: the "I could not read its current value" sentence is only spoken in an answer, and forcing a reader to fail is a write |
| `receipts-read` | `GET /api/receipts` | the receipts list and its undo contract read: `undo_action`, `undo_tier=ask`, `undone` + `undone_at` on every row, the "already undone" words |
| `settings-receipt-undoable` | `GET /api/receipts` | **BLOCKED until F5 ships and one cardless change runs**: a `change_setting` receipt this build can put back (`undoable=true`). On F3 it is `20 receipts, 0 undoable` - the live process holds no settings restorer |
| `undo-applies-once` | `GET /api/receipts` | **never PASS**: the guard's state is readable, but applying an undo is `POST /api/receipts/<id>/undo` and "once" needs it applied twice |
| `read-link-reader-carded` | `GET /api/reach` | the YouTube caption reader the intent hands a link to is ON and carded every time (`asks=Yes, every time`) - proven **without fetching a link** |
| `read-link-intent` | `GET /api/chat` | **never PASS**: `read_link` lives in the chat matcher; a non-link refusal and one card per link need `POST /api/chat` |
| `page-reader-not-switchable` | `GET /api/asks_first` | **the decision**: `read_web_page` is in `not_offered.tier_c`, not in `switchable`, and not in the app's `tools.items` |
| `page-reader-reach-line` | `GET /api/reach` | **the decision, second surface**: its own reach row is `state=off`, is not offered to the model, and still names the settings file as the one step |

## Which rows will only be provable AFTER the F5 deploy

- **Provable after the deploy, but not by the deploy alone:** `settings-receipt-undoable`. The
  restorer is registered *inside the change path* (`backend/jarvis_quick.py:14716`, just before the
  receipt is written), not at import - so the live process can only report `undoable=true` after one
  cardless setting change has run in it. Until then the row stays BLOCKED, and that is honest.
- **Provable after the deploy, by a read-only probe:** nothing else flips on its own. That is the
  point of F5: it adds no route.
- **Never provable by a GET, before or after any deploy:**
  - the explain sentence itself - what it is / where / its value / the exact phrase (`POST /api/chat`);
  - the "I could not read its current value on this PC, so I will not guess." sentence - it needs a
    reader to fail, which is a write, or the local suite `backend/test_setting_explain.py`;
  - the `read_link` intent and its refusal of a non-link, and one card per link (`POST /api/chat`);
  - a carded change's card, Live pausing, and the one calm spoken line (`POST /api/chat`, then
    `/api/approve` or `/api/deny`);
  - an undo being applied, and refused the second time (`POST /api/receipts/<id>/undo`, twice).
- **A code-suite fact, not a live one:** "no module writes `jarvis-framework.toml`" - pinned by
  `backend/test_settings_registry.py`, cited on F5-10A and not claimed as a probe.

## What it deliberately does not probe, and why

- **`GET /api/youtube`** - not called. It is the Quiz page's async route and its `start` path fetches
  captions; a probe must fetch nothing. The caption reader's registration is proven from
  `/api/reach` instead, which reads a list.
- **Any POST.** No card approved or denied, no setting changed, no undo applied, no link fetched, no
  Live session started, no pairing, no process restarted. Every request in both harnesses goes
  through `probe.call()`, which is `method="GET"` and has no code path that can send anything else.
- **`/api/settings`, `/api/explain`, `/api/feature_guide`** - checked (all `404 {"error": "not found"}`
  on F3), so they are recorded as absent rather than probed four times for nothing.
- **The phone.** It is a separate device with its own surfaces; nothing here reaches for it. The
  owner's thumb on it is Sub-Row B.
- **A paired/authorised change of any kind.** This is a read-only instrument; the moment it changed
  something, its BEFORE/AFTER value would be gone.

## Files in this folder

| file | what it is |
|---|---|
| `probe.py` | the F4 harness - GET-only, token never printed, shared by this one |
| `pre-deploy-probe.txt` | the F4 wave's BEFORE capture, against live F3, 2026-11-03 09:09 |
| `MATRIX.md` | the F4 matrix: 12 features x Sub-Row A / Sub-Row B |
| `README.md` | how to run the F4 harness and what it proves |
| `probe_f5.py` | **this wave's harness** - 19 read-only probes for F5, same shape and same verdict rules |
| `post-f5-probe.txt` | the real captured output of running it NOW against live **F3**, 2026-11-03 09:41:26 -08:00 (the BEFORE record) |
| `MATRIX-F5.md` | the F5 matrix: 10 features x Sub-Row A / Sub-Row B, including the page-reader decision |
| `README-F5.md` | this page |
