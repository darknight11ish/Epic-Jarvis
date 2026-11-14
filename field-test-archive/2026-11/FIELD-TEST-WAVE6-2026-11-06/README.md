# Wave-6 field test — how to run it (2026-11-06)

Four files to run, all in this folder, plus the pre-deploy control receipt. They
are the read-only field test for tonight's Wave-6 deploy (`#1194`, the Wave-3
bundle: packs, notes, quotes, upload, the approval-policy tool, the repository
map, the 3-GPU planned presets).

| file | what it is |
|---|---|
| `field_test.py` | measures 11 checks over the live API + the three binaries; writes `results.json` |
| `screens.py` | launches the phone app, captures the new-feature screens, captures the desktop window with PowerShell |
| `FIELDTEST-PLAN.md` | feature → check id → manual step → accepted evidence; the honest label rules |
| `README.md` | this file |
| `results-pre-deploy-control.json` | the 2026-11-06 **pre-deploy** control run (0.2.421), kept so the checks' discrimination is on the record — not a result about the deployed build |

Everything they write stays in this folder (`results.json`, `screens/*.png`,
`screens/_desktop_capture.ps1`). Nothing in the repository is modified.

---

## Before you start

- The deploy has finished and the live backend is up on `127.0.0.1:4719`.
- The phone is **awake and unlocked** (`screens.py doctor` tells you; the scripts
  refuse to fake a screenshot of a lock screen).
- You know the versions you expect, if you want the identity check to assert
  them. Without `--expect-*` it reports the three versions separately.

Run from the repository root in Windows PowerShell 7 (one line per command):

```powershell
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\field_test.py --dry
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\field_test.py
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\field_test.py --allow-live-turns
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\field_test.py --expect-backend 0.2.430 --expect-desktop 0.2.430 --expect-phone 0.2.3900
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py doctor
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py run
```

`--dry` makes **no network call and reads no token**; it prints the 11 checks,
what each accepts, and the doc lines the harness is built on. Use it to see the
shape before sending anything.

## `field_test.py` — what it measures

| check | route | card? |
|---|---|---|
| `live_status` | `GET /api/status` with the token | no |
| `chat_quote` | `POST /api/chat` "send me a quote" (model-free fast path) | no |
| `chat_packs_list` | `POST /api/chat` "list my packs" — **only with `--allow-live-turns`** | no (read-only tool) |
| `chat_notes_list` | `POST /api/chat` "what notes do I have" (fast path) | no |
| `chat_approval_policy_read` | `POST /api/chat` "what asks first"; `--allow-live-turns` adds the policy-tool read | no |
| `routes_present` | GET `/api/self/version`, `/api/notes/list`, `/api/self`; GET `/api/upload/begin` (recorded, not scored) | no |
| `version_identity` | GET `/api/self/version` + the exe's FileVersion + `adb ... dumpsys package` | no |
| `phone_app_foreground` | `adb shell dumpsys window` / `dumpsys power` | no |
| `repo_map` | GET `/api/projects` then `/api/projects/<id>/map` | no |
| `presets_3gpu` | GET `/api/presets` | no |
| `skills_read` | GET `/api/skills` | no |

The only optional POST that could raise a card is `POST /api/upload/begin`, and
it is **never sent** unless you pass `--allow-upload-probe`. With that flag the
harness sends `{}` — the docs say `begin` refuses a body with no name/extension
before any card — and it fails the check if a card appears.

### Exit codes

| code | meaning |
|---|---|
| `0` | every measured check PASS (`NOT-MEASURED` and opt-in skips allowed) |
| `1` | at least one `FAIL` |
| `2` | `--dry`, or refused/bad input (nothing was sent) |
| `3` | no `FAIL`, at least one `BLOCKED` (backend down, no token, phone asleep, no vault) |
| `4` | `--strict` and something was `NOT-MEASURED` |

`BLOCKED` and `NOT-MEASURED` are **never** counted as passes. The count line
always shows both, and `results.json` keeps every detail.

### The token: where it comes from, and what is never done

Tried in this order, each candidate **verified** with one `GET /api/status`
before it is used:

1. `HUD_TOKEN` in the environment (the desktop passes it to the backend this way).
2. Windows Credential Manager, a **read-only** `CredReadW` of
   `Jarvis Backend/pairing token`, then `Jarvis Desktop/pairing token`.
3. A `[hud]` table (or a bare `hud_token`) in the live folder's or the data
   folder's `jarvis-framework.toml`. Nothing else in the file is read, so a
   Joplin/GitHub/IMAP token can never be mistaken for the pairing token.

The harness deliberately does **not** call `jarvis_token_store.resolve()`:
`resolve()` can *mint and store* a new token when it finds none, which would
unpair the phone on the next backend start. No token found → the unauthenticated
probe still runs (to prove the backend is up) and every token'd check is
`BLOCKED`, never a pass.

Measured on this PC, 2026-11-06: neither `jarvis-framework.toml` (live folder or
data folder) has a `[hud]` table or a `hud_token`, and `HUD_TOKEN` is not set in
an ordinary shell — the live backend's token is in Credential Manager under
`Jarvis Backend/pairing token`, which is where the harness found and verified it.
When the desktop app starts the backend it passes its own token as `HUD_TOKEN`
(desktop Credential Manager target), so both targets are tried and each is
verified before use.

The token is never printed, never logged, never put in an exception message and
never written: every console line and every byte of `results.json` passes through
`scrub()`, and the file is written only after that. If you ever see a 43-character
`token_urlsafe`-shaped string in the output, that is a bug — report it, do not
paste it anywhere.

### Two measured facts the harness encodes (so you do not chase phantoms)

- **`/api/status` without a token answers `401`, not `403`, when
  `X-Jarvis-Client: hud` is sent.** `403` is the *cross-origin* refusal (no
  client header). Measured 2026-11-06 on the live backend:
  no headers → `403 {"error": "cross-origin request refused"}`;
  client header, no token → `401 {"error": "bad or missing X-Jarvis-Token"}`.
- **`GET /api/upload/begin` cannot answer `405`.** This server answers
  `404 {"error": "not found"}` for *any* POST-only route asked with GET —
  measured on `/api/schedule/add` and `/api/schedule/act`, which are certainly
  present. The harness records the code and does not score it; the upload
  route's presence is proved by the upload plugin in `/api/self` (and, only with
  `--allow-upload-probe`, by the refused `{}` body).
- **`/api/status` carries no version on 0.2.421.** The running-backend identity
  comes from `GET /api/self/version` instead (`app_version`, `api_version`,
  `server`, `pid`, `deploy.resealed.ref`); `/api/status` is still the token check
  and the budget/lane read.

## `screens.py` — the screenshot pass

```powershell
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py doctor
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py labels
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py run
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py shot 06-upload-card
py -3 .dsh-scratch\FIELD-TEST-WAVE6-2026-11-06\screens.py desktop 05-desktop-jarvis
```

It resolves the main activity itself
(`adb shell cmd package resolve-activity --brief com.jarvis.client`), launches
with `am start -W -n <that>`, waits, and captures:

| file | screen |
|---|---|
| `screens/01-home.png` | the app after launch |
| `screens/02-settings.png` | Settings root |
| `screens/03-settings-folders.png` | **Send a document** / **Bring in a Notion export** |
| `screens/04-settings-voice.png` | the **OFF** "Read out answers that use what Jarvis remembers" switch |
| `screens/05-desktop-jarvis.png` | the desktop window |

Navigation taps only on the exact labels named in the script (`Settings`,
`Folders`, `Voice`, with small alias lists). If a label is not found the script
prints `MISSING` with the texts that *are* on screen and exits `4` — that is a
partial capture, never a pass. Use `labels` to discover the exact text, then
`tap "<text>"` and `shot <name>`.

If the remembered-answers row is **below the fold** on `04-settings-voice.png`,
scroll the phone by hand (or `adb shell input swipe 540 1800 540 700 300`) and run
`screens.py shot 04b-voice-scrolled` — a picture that does not show the switch is
not evidence of it. The row's exact words are *"Read out answers that use what
Jarvis remembers"*, and its OFF line begins *"Off by default"*.

The desktop capture is PowerShell only (`System.Drawing` + `user32`), no new
dependency. It restores the `jarvis-desktop` window, tries to bring it to the
front, and copies its rectangle to PNG. If Windows refuses the foreground change
or another window covers it, the picture shows that — a locked desktop can also
capture black; look at the image before claiming anything.

The phone writes **one** temporary file during navigation
(`/sdcard/jarvis-fieldtest.xml`, the UI dump) and deletes it again. It never
touches another app's data.

### Exit codes

| code | meaning |
|---|---|
| `0` | every planned shot captured |
| `1` | a hard error (adb missing, screencap not a PNG, desktop capture failed) |
| `2` | bad input / unknown command |
| `3` | phone not ready (not attached, asleep, lock screen, app not installed) — nothing was launched |
| `4` | partial: some shots captured, at least one navigation label not found |

## Reading `results.json`

`schema`, `wave`, `started`/`finished`, `base_url`, `token_source`, `opt_ins`,
`expect`, `checks[]` (each with `id`, `verdict`, `detail`, `data`), `counts`,
`evidence[]`. The `data` block is where the machine-readable proof lives:
`quick` and timing for a chat check, route status codes, `/api/self` tool names,
versions, the phone's window state, the repo-map counts, the 3-GPU counts.

The file contains **no** token and **no** note text. `chat_notes_list` reports
the shape (`one_note_read`, `note_list`, `honest_no`), a count and lengths — the
note's title and words stay off the report on purpose; read them in the app.

## What these scripts will never do

- Approve, deny or answer an approval card; click a button in the desktop app.
- Change a setting, switch a preset or model, install or remove a pack/skill.
- Restart, stop or start any process (including the backend and the desktop).
- Send speech to the phone or touch the microphone.
- Print, log or write the pairing token.
- Write anything outside this folder.

If you want a card in a screenshot, open it yourself and run `screens.py shot
<name>`; that is a capture, not an approval.

## If something goes wrong

| symptom | meaning / next step |
|---|---|
| `token : COULD NOT BE DISCOVERED` | every token'd check is BLOCKED. Run `py -3 jarvis_token_store.py where` in the live folder; if the token is typed into the desktop's Settings, it is not in Credential Manager — set `HUD_TOKEN` for this shell instead (never paste it into a file). |
| `no answer from http://127.0.0.1:4719` | the backend is down. This harness does not start it. |
| `live_status FAIL ... REJECTED` | the token was read but refused: the running backend is using a different token (usually `HUD_TOKEN` set when it started). Nothing else can be measured until that is resolved. |
| `chat_quote FAIL ... QUOTE_MISSING` | `jarvis_quotes.py` or `quotes_corpus.json` did not land; the latter is a **beside-file** the deploy tool does not carry (`RUNBOOK-REV3.md` §4B). |
| `chat_notes_list FAIL ... the OLD refusal` | `jarvis_quick.py` was not updated. This is the sharpest broken-deploy signal; see `FIELDTEST-PLAN.md` §8. |
| `routes_present FAIL ... tools missing` | a shipped module (`jarvis_packs.py`, `jarvis_approval_policy.py`) did not land, or `jarvis_agent.py` was not updated. |
| `phone_app_foreground BLOCKED ... ASLEEP` | wake and unlock the phone, re-run. Asleep is a state, never a pass. |
| `repo_map FAIL ... 404` | §195's route did not land (`jarvis_projects.py` / `jarvis_hud.py` not updated). |
| `skills_read BLOCKED ... list is empty` | the route works, but no skill is installed to observe; the remove-when-off step is manual. |

The full feature-by-feature contract, with the exact doc lines and what counts as
evidence, is `FIELDTEST-PLAN.md`.
