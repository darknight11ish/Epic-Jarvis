# Wave-7 field test — 2026-11-06

The read-only field harness for the **Wave-7 deploy**: PR 2 (deny-and-steer,
hidden-byte pills, card cost line, pack curator lock, "New — currently off"),
PR 2.5 (activity finally/reset/300 s lease, bench `num_gpu = block_count + 1`,
Q6 identity) and the awareness/phone-scroll work if it lands.

- **Harness:** `field_test_wave7.py` (Python 3, stdlib only)
- **One command:** `run_wave7.ps1` (dry by default)
- **Rows:** 11, plus 5 manual rows for the owner's eyes
- **Writes:** `results.json` in this folder, and nothing else anywhere

The Wave-6 folder beside this one is **untouched**: this harness *imports* its
token discovery, `scrub()`, HTTP and adb helpers from
`../FIELD-TEST-WAVE6-2026-11-06/field_test.py` instead of copying them, so the
credential code that has been used all week cannot drift from the copy here.

---

## 1. What is in this folder

| file | what it is |
| --- | --- |
| `field_test_wave7.py` | the harness: 11 scored rows, 5 manual rows, `--dry` (default) / `--run` / `--self-test` |
| `run_wave7.ps1` | the single command (PowerShell 5.1-safe), prints where `results.json` landed and exits with the harness's code |
| `_bench_resolve_probe.py` | helper: asks the **deployed** `jarvis_bench` what `num_gpu` it resolves (pure function, no run started) |
| `_catalogue_probe.py` | helper: reads the **deployed** `jarvis_feature_catalogue` as data (a row, not a grep — `from the phone` alone matches five other rows) |
| `results.json` | the latest run |
| `results-before-deploy-2026-11-06.json` | the **before** picture (the live build is still the Wave-6 one), kept so the after-run can be compared |
| `run-before-deploy-2026-11-06.log` | the full stdout of that run |
| `selftest-after-deploy-detectors.log` | `--self-test`: the after-deploy detectors proved against `jarvis-backend/` |
| `_probe_now.py`, `probe-before.json` | the scratch probe used **while building** this harness, and its raw output (the route shapes measured before any row was written) — kept as evidence, not needed to run anything |
| `README-WAVE6-BASE.md`, `FIELDTEST-PLAN-WAVE6-BASE.md` | copies of the Wave-6 documents this one is built on |

## 2. How to run it

From the repository root, Windows PowerShell 7:

```powershell
# list the rows and the evidence; makes NO request, reads NO token (default)
pwsh -NoProfile -File .dsh-scratch\FIELD-TEST-WAVE7-2026-11-06\run_wave7.ps1

# measure the live build and write results.json
pwsh -NoProfile -File .dsh-scratch\FIELD-TEST-WAVE7-2026-11-06\run_wave7.ps1 -Run

# one or two rows again, without redoing the rest
py -3 -B .dsh-scratch\FIELD-TEST-WAVE7-2026-11-06\field_test_wave7.py --run --only bench_all_layers,deny_note_route

# the after-deploy detectors, proved on the published base instead of the live build
py -3 -B .dsh-scratch\FIELD-TEST-WAVE7-2026-11-06\field_test_wave7.py --self-test

# the four cheap Wave-6 regression reads, counted apart from the 11
py -3 -B .dsh-scratch\FIELD-TEST-WAVE7-2026-11-06\field_test_wave7.py --run --carry-wave6
```

Exit codes: `0` every measured row PASS · `1` at least one FAIL · `2` dry run
(nothing sent) · `3` no FAIL but a BLOCKED row · `4` `--strict` and a
NOT-MEASURED row.

## 3. The rows

| # | row | what it reads | a PASS means |
| --- | --- | --- | --- |
| 1 | `version_identity_wave7` | live `VERSION`, the installed exe's `FileVersion`, `_jarvis-state.json`'s `resealed.ref`, then the checker's identity half and its Q6 half | identity `MATCH` **and** `PASS (runtime tree identical to deployed ref …)` |
| 2 | `bench_all_layers` | `GET /api/bench?model=qwen3.5:9b` **and** the deployed `jarvis_bench.normalise_controls()` (no run started) | resolved `num_gpu == block_count + 1` (33, not 32) |
| 3 | `asks_first_new_off` | `GET /api/asks_first` → `tools.new_off` | object present, label exactly `New — currently off`, `items` are template tools that are not on live |
| 4 | `curator_lock_surface` | `jarvis_packs.py locked` / `lock` / `unlock` from a temp cwd, then `GET`+`POST /api/packs/lock` | `{"ok": true, "locked": [...]}`; `lock`/`unlock` refuse without a name (exit 2); **no HTTP route** (404/405) |
| 5 | `hidden_bytes_contract` | live `jarvis_hud.py`/`jarvis_gate.py` for `hidden_bytes` + `hidden_bytes_more`, then `GET /api/pending` | payload code present with file:line; pending is a clean list. **End-to-end NOT-MEASURED: needs a real card** |
| 6 | `cost_line_contract` | same, for `estimate_usd`/`monthly_usd`/`cap_usd` | payload code present with file:line. **End-to-end NOT-MEASURED: needs a real card** |
| 7 | `deny_note_route` | `POST /api/deny` with a **fake** id and a note; `GET /api/pending` before/after | 404/409, `ok:false`, `note_kept`/`note_why` present, no card created or settled |
| 8 | `awareness_phone_documents` | the live `jarvis_feature_catalogue.py` as data + `GET /api/folders` | a row for sending a document **from the phone**, `notion-import` surface `both`, `notion.can_import == true` |
| 9 | `phone_apk_has_send_document` | `adb devices`, `pm path`, `adb pull` to `%TEMP%`, then the APK's bytes | `NotionImport`, `api/notion/phone-import`, `api/upload/finish`, `From my phone` all present; **no device is BLOCKED** |
| 10 | `repo_map_now` | `GET /api/projects/<65c6e3a9…>/map` | HTTP 200, `ok`, `available`, a non-empty map |
| 11 | `main_ci_and_release_identity` | `git rev-parse origin/main`, `gh` check-runs on it, `gh release view desktop-latest/client-latest` | all seven required checks success; both releases name that sha |

**BLOCKED and NOT-MEASURED are never a pass.** Rows 5 and 6 say out loud that
they prove a *source contract only*: the end-to-end card path is NOT-MEASURED
with the reason "needs a real card", because this harness must never raise one.

## 4. The before picture (measured 2026-11-06 17:11 PT, ~20 s)

Live build: `VERSION 0.2.433`, deployed ref `e4d01b9`, installed desktop
`0.2.433`, phone `0.2.3942` (versionCode `1000003942`), `origin/main a24201d`.

```
11 rows: 8 FAIL, 1 NOT-MEASURED, 2 PASS
```

| row | before | why |
| --- | --- | --- |
| `version_identity_wave7` | **FAIL** | identity is `MATCH` (0.2.433 both sides) but Q6 says `CHANGED: 21 runtime file(s) differ between e4d01b9 and origin/main` — **a deploy is required** |
| `bench_all_layers` | **FAIL** | the deployed resolver asks `num_gpu 32` = `block_count`, not 33 → the 83.6 %-on-card state the addendum measured |
| `asks_first_new_off` | **FAIL** | `tools.new_off` is absent (tools rows: can_enable, detail, extra, groups, items, label, not_switchable, vault) |
| `curator_lock_surface` | **FAIL** | `jarvis_packs.py` is `version: 2` and prints its **self-check for any argument** — no `locked`/`lock`/`unlock` CLI at all. The HTTP half is already right: `GET` and `POST /api/packs/lock` → 404 |
| `hidden_bytes_contract` | **FAIL** | no `hidden_bytes`/`hidden_bytes_more` anywhere in the live `jarvis_hud.py` / `jarvis_gate.py` |
| `cost_line_contract` | **FAIL** | no `estimate_usd`/`monthly_usd`/`cap_usd` in the live files |
| `deny_note_route` | **FAIL** | `POST /api/deny` with a fake id answers 409 with the **Wave-6 shape** (`error, id, ok, state`; no `note_kept`/`note_why`) and changes nothing |
| `awareness_phone_documents` | **FAIL** | 178 catalogue rows, **no** phone-sends-a-document row, and `notion-import` still says `surface: "desktop"` |
| `phone_apk_has_send_document` | **PASS** | the installed APK (0.2.3942) has all four strings, all in `classes.dex` |
| `repo_map_now` | **PASS** | HTTP 200 in 11.6 s: 55 files / 1798 symbols walked, 10 ranked rows, 380/400 tokens |
| `main_ci_and_release_identity` | **NOT-MEASURED** | 5 of 7 required checks green on `a24201d`; `backend` and `backend-windows` were **still running** when the run was taken |

## 5. What must flip after the deploy (and what will not)

The after-deploy detectors were proved against the **published base**
(`jarvis-backend/`, the code that will be deployed) with `--self-test` — 4 of 4
scored probes OK, so these are not guesses:

- rows 5 and 6 → the exact payload lines they look for:
  `jarvis_gate.py:2781` `d["hidden_bytes"]`, `:2783` `d["hidden_bytes_more"]`,
  `:1095-1097` `estimate_usd`/`monthly_usd`/`cap_usd`;
- row 2 → `block_count 32 -> resolved num_gpu 33` (taken from the base, not live);
- row 4 → `{"ok": true, "locked": []}` exit 0 and `{"ok": false, "error": "say
  which pack: lock <name> or unlock <name>"}` exit 2 from the base CLI;
- row 3 → the base's `tools.new_off` is `{label: "New — currently off", why,
  items}` (jarvis_asks_first.py:1944, 2492).

Rows 1, 7 and 11 depend on the deploy itself, not on the code in the repo:

- **1** needs `resealed.ref` to become the deployed sha (after step 5 of the
  runbook) so Q6 prints `PASS (runtime tree identical …)`;
- **7** needs the resealed `jarvis_hud.py` (the `note_kept`/`note_why` block at
  jarvis-backend/jarvis_hud.py:4738);
- **11** needs the seven checks to have **finished** on the final main sha, and
  both releases to name it.

**Row 8 will not flip.** There is no awareness work in this repository: the
`notion-import` row on `main` still says `surface: "desktop"`, `features/features.json`
has no phone-sends-a-document row, and the two branches the brief named
(`fix/self-awareness-phone-upload-notion-2026-11-06`,
`feat/phone-home-answer-scroll-2026-11-06`) are **not on origin** and have no
open PR. The phone *code* is on main (`NotionImport.kt`, `Upload.kt`), which is
why row 9 passes; the catalogue half is not. Row 8 will keep saying "the deploy
is old, or the awareness PR never landed" until that PR lands and is deployed.

## 6. Things the brief expected that the build does not do

1. **`controls.num_gpu` is never resolved on the route.** `GET /api/bench?model=…`
   returns `controls = dict(CONTROLS)` on **both** builds, so `controls.model` is
   `""` and `controls.num_gpu` is `null` (jarvis_bench.py:2184). `null` means
   "all of them" — the route does not expose the number the run will use. The
   row therefore measures the deployed module's own `normalise_controls()` — the
   same pure function a run uses — which is 32 today and 33 after the deploy.
2. **The identity checker's plain command cannot print `MATCH` on a deployed
   machine.** `tools/check_live_version_identity.py:244-248` takes the Q6 branch
   whenever the live record has a deployed ref, and the reseal writes one — so
   the plain command printed the Q6 `CHANGED:` line, not `MATCH:`. The harness
   calls the tool's own `check()` (same sentence, same exit code) for the
   identity half and records the plain command's line too.
3. **`py -3 -B tools/check_live_version_identity.py --help` crashes**:
   `ValueError: unsupported format character 'O'` — the `--desktop-exe` help
   string contains a literal `%LOCALAPPDATA%` and argparse formats help with
   `%` (tools/check_live_version_identity.py:230). A one-line defect; not fixed
   here because this lane writes only in its own scratch folder.
4. **`client-latest`'s `targetCommitish` is stale.** The release **name** is
   `Jarvis for Android 0.2.3956 (main @ a24201d)` but `targetCommitish` is
   `bcee9a2d…`, from 2026-10-24 — GitHub keeps the creation value on a moving
   tag. So the phone release's identity must be read from its **name** (or the
   APK), never from `targetCommitish`. `desktop-latest` does name the sha
   (`a24201deeeff…`) and `0.2.434`.
5. **`files` in the repo-map answer is not the walk count.** It read `1` while
   the map's own first line said "24 files with names to show, 165 symbols
   declared". The row reports the map's own numbers, and the walk is
   time-limited (6 s), so the counts vary run to run (55/1798 and 133/4933 were
   both measured).
6. **The live folder's `.pyc` files are the backend's, not the harness's.** A run
   leaves the live folder's item count unchanged (4914 → 4914, measured). The
   `.pyc` files that appear during a run (`jarvis_storage`, `jarvis_pc_help`,
   `jarvis_pc_facts` at 17:04) belong to the **running** backend lazily importing
   modules while it serves the GETs; every subprocess this harness starts uses
   `py -3 -B`, which writes no bytecode.

## 7. The manual rows (not scored)

They are in `results.json` under `manual_rows` with numbered steps, printed at
the end of every `--run`, and summarised here. They need a real card, a real
cloud spend, a real pack, or a finger on the phone — none of which a read-only
harness may produce.

1. `manual_phone_home_answer_scroll` — ask a long question on the phone, drag
   **inside** the answer box, confirm the last line is reachable without "Show
   chat".
2. `manual_deny_and_steer_note` — Deny a real card with a note, and check the
   waiting turn reads the note back and creates no standing permission.
3. `manual_hidden_bytes_pill` — a crafted card (zero-width space + RTL override),
   and the pill that counts and reveals the hidden characters.
4. `manual_cost_line_cloud_card` — a cloud-bound answer shows this answer's
   estimate, the month's spend and the monthly limit.
5. `manual_curator_lock_refusal` — `py -3 -B jarvis_packs.py lock <pack>`, then a
   removal from the phone must be refused, naming the lock and the PC-only way
   out.

## 8. What the harness never does

- Never approves, denies or clicks a card. The one writing request is
  `POST /api/deny` with the id `field-test-no-such-card-wave7`, which cannot
  settle anything real (409, measured) and is checked against `/api/pending`
  before and after.
- Never raises a card, never starts a benchmark, never sends a chat turn (no
  model-turn row exists in this harness), never changes a setting.
- Never prints, logs or writes the token: every printed and written string goes
  through the Wave-6 `scrub()`, and the token is read only through the Wave-6
  `CredReadW` helper (never `jarvis_token_store.resolve()`, which can mint one).
- Never writes to the live folder: `-B` on every subprocess, the packs CLI from
  a temp cwd, the pulled APK in `%TEMP%` and deleted afterwards.

## 9. Evidence this is built on

- `jarvis-backend/jarvis_hud.py:4685-4738` — `POST /api/approve|/api/deny`, the
  `note` and the `note_kept`/`note_why` reply.
- `jarvis-backend/jarvis_gate.py:880-903,2778-2783` — `hidden_bytes()`, the
  payload fields and `MAX_HIDDEN_ROWS = 12`.
- `jarvis-backend/jarvis_gate.py:1013-1097` — `estimate_usd`/`monthly_usd`/`cap_usd`.
- `jarvis-backend/jarvis_packs.py:2727-2751` — the CLI that is the only door to
  the curator lock.
- `jarvis-backend/jarvis_asks_first.py:1944-1950,2492` — `NEW_OFF_LABEL` and
  `tools.new_off`.
- `jarvis-backend/jarvis_bench.py:1297` — `every = block_count + 1`, and the
  measured 83.6 % at 32 vs 100 % at 33/34/40/99.
- `tools/check_live_version_identity.py:215,338` — the two sentences rows 1 wants.
- `.dsh-scratch/FIELD-TEST-WAVE6-2026-11-06/ADDENDUM-2026-11-06-repomap.md` —
  the project `65c6e3a9…` and the 6 s walk.
- `CLAUDE.md` — the seven required checks.
