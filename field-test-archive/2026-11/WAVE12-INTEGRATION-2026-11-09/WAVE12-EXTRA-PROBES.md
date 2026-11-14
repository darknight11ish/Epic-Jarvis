# WAVE 12 — POST-DEPLOY READ-ONLY PROBES

**Audience:** the wave-12 deploy lead.
**Scope:** PR #1217, head `a707c2e30174c51087743f34f07436f6eb612f14`, base `origin/main` = `2644d57a2`.
**Written:** 2026-11-09. Read-only throughout: no repo edits, no live writes, no approval cards.

Every command below either (a) reads a file on disk, (b) issues a `GET`, or (c) calls a pure
function inside the **deployed** module. **Nothing POSTs, switches, installs or applies a preset.**
That distinction matters most in §D, where the obvious-looking check would change the model.

---

## 0. The two trees, and why this decides half the checks

| What | Path | On disk? |
|---|---|---|
| **Backend folder** (the installed Python) | `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` | yes — this is `apply-patches.ps1`'s own `-BackendPath` default (`scripts/apply-patches.ps1:137`) |
| **Desktop app** (Tauri exe) | `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe` (running, PID 9468 during this pass) | yes, but **only the .exe** |
| **HUD page** (served by the backend) | `<backend folder>\jarvis_hud.html`, served at `GET http://127.0.0.1:4719/` | **yes — greppable** |
| **Brain window frontend** (`brain.js`, `model-resources.js`, `model-results.js`, `index.html`) | bundled **inside the .exe** | **NO — not greppable after install** |

Measured pre-deploy state of the backend folder (this pass, 2026-11-09 ~08:50 PT):

```
jarvis_model_resources.py              ABSENT
jarvis_reversible_ui.py                ABSENT
jarvis_skills.py                       PRESENT  42,416 B  11/6/2026 09:18
jarvis_skill_hub.py                    PRESENT  70,943 B  11/6/2026 09:18
jarvis_model_recommendations.py         PRESENT  74,240 B  11/8/2026 18:35
jarvis_hud.html                        PRESENT 700,122 B  11/9/2026 03:52
(a "Pause reading"/"pauseSpeechPlayback" grep on the HUD: 0 hits; "Read out loud": 3 hits)
```

So: **the two new backend modules are the wave-12 arrival signal**, and **the HUD greps are a real
pre/post switch** because the deployed page still has the wave-11 read-aloud. The Brain plate and the
"Measured results" card live in the exe — verify them through their **route** (§B, §C) and the
owner's eyes for the pixels.

### Token discovery — reuse wave 11's, do not invent one

`.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` already discovers it read-only
(`HUD_TOKEN` env → Windows Credential Manager `Jarvis Backend/pairing token` /
`Jarvis Desktop/pairing token` → `jarvis-framework.toml`'s `[hud]`), verifies it with one
`GET /api/status`, and **never prints or writes it** (`discover_token()`, `:368`, returns
`(value, source, notes)`; `scrub()` at `:163`). Load that module rather than retyping the lookup:

```powershell
py -3 -B -c "import importlib.util,argparse; s=importlib.util.spec_from_file_location('w11',r'.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); a=argparse.Namespace(base_url='http://127.0.0.1:4719', backend_path=r'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program', timeout=25.0); tok,src,notes=m.discover_token(a); print('token source:', src if tok else 'NONE'); c,b,e=m.http_get(a.base_url+'/api/models/resources',token=tok); print('HTTP',c); print(b[:3000])"
```

Run it **from the repository root**. It prints the *source label*, never the token.

---

## A. Hermes skill-scan checks + `skills.lock` (DEF-049)

**What shipped:** `64e87d290` wires the hub's four extra checks into the one install scan;
`591b840fa` writes `skills.lock` on install/edit and forgets the row on removal.

**Route / files (deployed tree):** no route. `jarvis_skill_hub.py` + `jarvis_skills.py`.

- `jarvis_skill_hub.py` — `LOCK_NAME = "skills.lock"` (`:1099`), lock merge `:1168`, row delete `:1203`.
- `jarvis_skills.py:831` — "Write or refresh this skill's row in `skills.lock` (wired 2026-11-09)";
  `:862` deletes it on uninstall.

**Command (automatable, no token):**

```powershell
$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($f in @("jarvis_skill_hub.py","jarvis_skills.py")){ "--- $f"; Select-String -Path (Join-Path $d $f) -Pattern "extra_findings|LOCK_NAME =|skills.lock" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" } }
```

**Expected:** `jarvis_skills.py` carries an `extra_findings(` **call** (the fix is the call, not a copy)
and the `skills.lock` write/delete pair; `jarvis_skill_hub.py` carries `LOCK_NAME = "skills.lock"`
and `extra_findings` as a definition. Both files' timestamps must move off `11/6/2026 09:18`.

**Automatable / eyes:** the wiring is **automatable** (grep). The *behaviour* — a Hermes skill using
the inline `!`cmd`` form is refused at install with the hub's finding named — needs **the owner's
eyes** (or a real install, which raises a card and is out of scope here).

> **Not-installed honesty:** `vet()`'s report carries `extra_checks 1`, or `0` when the hub is absent
> from an older base (`64e87d290`'s message). A `0` here is visible, never a silent pass — if the two
> files still show `11/6/2026 09:18`, the wave-12 skills work did **not** install.

---

## B. Brain → Model "Loaded now / Resources" plate + "Plan:" labels

**Route:** `GET /api/models/resources` (PC-only, token + origin).
**File:** `jarvis_model_resources.py` (new, shipped whole; `scripts/apply-patches.ps1:2862`), served by
`jarvis_model_recommendations.install()` — `PATH_RESOURCES = "/api/models/resources"` at
`backend/jarvis_model_recommendations.py:204`.

**Command:** **you already have this probe.** Reuse it rather than re-deriving the answer:

```powershell
py -3 -B .dsh-scratch\WAVE12-INTEGRATION-2026-11-09\probe_model_resources.py
```

It reuses the wave-11 token discovery, GETs the one route, and compares every field against an
independent `/api/ps` + `nvidia-smi` read (`probe_model_resources.py:1-22`). Raw one-off GET if you
want to eyeball the JSON: the §0 one-liner.

**Expected — the answer's own keys** (`jarvis_model_resources.py:600-618`):

```
available: true
read_at / read_at_words            "HH:MM:SS"
active_lane: {url, source, file, fallback, preset, preset_title, words}
lanes:     [ ... ]                 one per running Ollama lane
gpus:      [ ... ]                 total/used/free, plus jarvis_mb when the driver reports it
gpu_share: {known, why, loaded_vram_gib, cards}
jarvis:    { ... }                 Jarvis's own RSS / CPU
warnings:  [ ... ]
notes:     ["Read-only: this answer only looked. Nothing was loaded, switched or started.", ...]
words:     [ ... ]                 the headline the plate draws
```

Honest-limit expectations, so a truthful answer is not misread as a failure:

- **`gpu_share.known` may be `false`** on this PC — the Windows driver answers `[N/A]` for per-process
  video memory (`:541-546`, `:563-572`). Then `gpu_share.why` says so in words and `notes` carries a
  second sentence. That is the **correct** state, not a bug.
- `jarvis.gpu`-level `jarvis_mb` / `other_mb` are only set when `share_known` (`:548-560`).

**"Plan:" labels** are the second half of `6fe454fd4` and live in the **exe's** `brain.js`
(`jarvis-desktop/src/brain.js` +459/-… in the diffstat; `model-resources.js` is new, +226). They are
**not** on disk after install → **the owner's eyes**.

**Automatable / eyes:** route = **automatable** (probe exists). The plate's pixels and the exact
`Plan:` wording = **eyes**.

---

## C. "Measured results" scorecard card

**Route:** `GET /api/models/measured` (PC-only). **File:** same module, `PATH_MEASURED` at
`backend/jarvis_model_recommendations.py:210`; `measured()` at `jarvis_model_resources.py:928`.

**Command:** same one-liner as §0 with the path swapped:

```powershell
py -3 -B -c "import importlib.util,argparse; s=importlib.util.spec_from_file_location('w11',r'.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); a=argparse.Namespace(base_url='http://127.0.0.1:4719', backend_path=r'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program', timeout=25.0); tok,src,notes=m.discover_token(a); print('token source:', src if tok else 'NONE'); c,b,e=m.http_get(a.base_url+'/api/models/measured',token=tok); print('HTTP',c); print(b[:3000])"
```

**Expected keys** (`jarvis_model_resources.py:946-957`):

```
available: true            (false + why when jarvis_bench.py is absent — never an invented row)
read_at / read_at_words
runs:      []              newest first, up to MEASURED_RUNS_SHOWN = 3
scorecards:[]             up to MEASURED_SCORES_SHOWN = 5
counts:    {runs, scorecards}
stores:    {speed: {...}, scores: {...}}   each {name, exists}
empty:     {runs, scorecards}              a SENTENCE, with the reason
notes:     [ ... ]
words:     [ ... ]
```

**Empty is a pass, and the reason is the evidence.** An empty store is described *in words with why*
(`_empty_reason`, `:911`; `available: false` when the module is missing, `:962-967`) — so `runs: []`
with a sentence in `empty.runs` is **honest PASS**, not a failure. A number with no store row behind it
would be the failure.

**Automatable / eyes:** route = **automatable**. The card's rendering = **eyes**.

---

## D. Manual-click reversible UI allow-list `{apply_preset, switch_model}`

> ### STOP — do not probe this route with a POST
> `SWITCH_ROUTE = "/api/models/switch"` (`backend/jarvis_reversible_ui.py:151`) **really switches the
> model** (`_switch_for_the_owner`, `:389`). A "does it work" POST is a live write and is out of scope
> for this pass. The read-only check is the allow-list itself.

**File:** `jarvis_reversible_ui.py` (new, shipped whole; `scripts/apply-patches.ps1:3161`).
**Allow-list:** `REVERSIBLE_UI_CHOICES` at `:157`, whose two keys are exactly `apply_preset` and
`switch_model`.

**Command (automatable, no token, no request):**

```powershell
$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Select-String -Path (Join-Path $d "jarvis_reversible_ui.py") -Pattern "REVERSIBLE_UI_CHOICES|SWITCH_ROUTE =|\"apply_preset\"|\"switch_model\"" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

**Expected:** `SWITCH_ROUTE = "/api/models/switch"`, `REVERSIBLE_UI_CHOICES` defined at ~`:157` with
exactly two keys — `apply_preset` and `switch_model` — and `install()` returning a status line
`reversible  ready (2 choice(s))` (`:395`). That status line is also worth grepping the **deploy log**
for; it is the module's own report that it wrapped the handler.

**The 404 is a feature** (`1c536b03b`): any other path gets
`{"error": "There is nothing at that address, so nothing was changed."}` (`:369`). If you see that text
in the deploy log or a trace, it is the guard working, not a missing route.

**The property the owner actually cares about — "a preset clicked in either app applies with no card"**
(`f6c06c880`) — needs **the owner's eyes**: click a preset, confirm the model changes and **no approval
card appears**. That is a real state change, so it belongs in the owner's acceptance, not here.

**Automatable / eyes:** allow-list + status line = **automatable**. "No card on a preset click" = **eyes**.

---

## E. Drag-and-drop (a dropped file rides the bar's next question)

**Commits:** `77d6428eb` (a compatible file dragged in really arrives; a multi-file drop says what was
left out), `a3682ef43` (a slower earlier read cannot overwrite a later drop), `c7f9f985a`.

**Files:** `jarvis_quick.py` (+511) on the backend; the quickbar's own `attach*` family in the **served**
HUD page — so this one **is** greppable, unlike §B.

**Command (automatable, no token — reads the page the backend actually serves):**

```powershell
$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Select-String -Path (Join-Path $d "jarvis_hud.html") -Pattern "function attachTake|function attachOthers|function attachNone|function attachShow|function attachClear" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

Confirmed present in the repo tree at head (`backend/jarvis_hud.html:7664`, `:7677`, `:7640`, `:7647`,
`:7652`). **Expected after deploy:** the deployed `jarvis_hud.html` carries `attachTake(file, extra)`
and `attachOthers(n)` — the "what was left out" sentence — and its size/timestamp move past
`700,122 B / 11/9/2026 03:52`.

**The behaviour** — drag a real file onto the bar, the next question carries it; drop three files and
the bar names the ones it left out — is **the owner's eyes** (a drag gesture is not scriptable from
here, and the desktop suite `tests/quickbar-attach.mjs` is the automated proof already in CI).

**Automatable / eyes:** markers = **automatable**. The gesture = **eyes**.

---

## F. Read-aloud in Jarvis's own (female) voice + Pause / Stop

**Commit:** `64a2caeef` (TASK-51). The page now asks **this PC** for the sound
(`speak_reply` → `POST /api/voice/say` → `jarvis_speech.say()` → `jarvis_voices.speaker()`), plays the
returned `data:audio/wav`, and **never** uses `speechSynthesis`/`getVoices`, so it can no longer fall
back to index-0 Microsoft David.

**File:** the **served** HUD page — `jarvis_hud.html` (grep-able). Deploy also needs the new Tauri
capability `hud-speech = allow-speak-reply` (`jarvis-desktop/src-tauri/capabilities/hud.json`,
`permissions/surfaces.toml`) — see risk **R4**.

**Command (automatable, no token):**

```powershell
$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($m in @("pauseSpeechPlayback","resumeSpeechPlayback","stopSpeechPlayback","speechSynthesis","getVoices","data:audio/wav")){ $c=(Select-String -Path (Join-Path $d "jarvis_hud.html") -Pattern ([regex]::Escape($m)) -AllMatches -ErrorAction SilentlyContinue | Measure-Object).Count; "{0,-24} {1}" -f $m,$c }
```

**Expected after deploy:**

| marker | expected | means |
|---|---|---|
| `pauseSpeechPlayback` | ≥1 | the Pause/Resume control exists |
| `resumeSpeechPlayback` | ≥1 | Resume exists |
| `stopSpeechPlayback` | ≥1 | Stop reading exists |
| `data:audio/wav` | ≥1 | it plays the PC's own clip |
| `speechSynthesis` | **0** | the WebView2 fallback is gone |
| `getVoices` | **0** | no voice enumeration, so no David fallback |

Pre-deploy measured: `pauseSpeechPlayback` **0**, and `Read out loud` **3** — so the page is genuinely
still the wave-11 one. **`speechSynthesis`/`getVoices` going to 0 is the load-bearing assertion**; a
non-zero count means the old fallback shipped.

**Automatable / eyes:** markers = **automatable**. **"It is the female Jarvis voice" and "the audio
actually plays" = the owner's ears.** No grep can prove a voice is female; state that plainly in the
acceptance record rather than letting the marker count stand in for it.

---

## G. Notion 4 GB cap

**Commits:** `9d3207698` (4 GB unpacked ceiling, real numbers in every refusal, free-space preflight),
`1229ddb03` (the phone may send a 4 GB export too).

**Files:** `jarvis_notion_obsidian.py` (**PC side**), `jarvis_upload.py` (**phone side**) — and the note
that these are **two different numbers** deliberately made equal.

**Command (automatable, no token):**

```powershell
$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($f in @("jarvis_notion_obsidian.py","jarvis_upload.py")){ "--- $f"; Select-String -Path (Join-Path $d $f) -Pattern "4 GB|4 GiB|MAX_NOTION_BYTES|EXPORT_UNCOMPRESSED_MAX|STAGING_MAX" | Select-Object -First 8 | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" } }
```

**Expected:** `jarvis_upload.py` shows `MAX_NOTION_BYTES  4 GiB` and `STAGING_MAX  4 GiB`
(`jarvis_upload.py:119`, `:127`, `:193-202`), and `jarvis_notion_obsidian.py` shows the 4 GB ceiling
plus the **declared total also raised to 4 GB** (`:151`, `:164`, `:373`). The comments at those lines
state the two numbers are distinct and were equalised on purpose — read them before calling a mismatch
a bug.

**Honest limit:** the cap's *refusal text* ("real numbers in every refusal") and the free-space
preflight are proven by the suites, not by a GET. Driving a real 4 GB upload is a live write and is
**out of scope**. Read the constants = automatable; sending a 4 GB export = not in this pass.

**Automatable / eyes:** constants = **automatable**. No eyes needed for the cap itself; a real upload
is a separate, deliberate test.

---

## H. F1 quick-intent dispatch fix (`chat_best_coding`)

**Commit:** `bbc419410` — the one real product failure of the wave-11 acceptance (2026-11-09 04:00 PT):
*"which model is better for the Coding preset?"* answered *"There is no preset called \"better for the
Coding\""* instead of naming `qwen3-coder-30b-a3b-ud-q3-k-xl`.

**Route:** none new — `POST /api/chat`, the existing fast path. The fix is inside `_model_chat` in the
deployed `jarvis_quick.py`.

**This row ALREADY EXISTS in the wave-11 probe.** Row id **`chat_best_coding`**
(`verify_wave11_live.py:135`, in `CHAT_SENTENCES`). You do not need a new probe — you need to re-run it
and see it flip from FAIL to PASS:

```powershell
py -3 -B .dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py
```

**Expected:** row `chat_best_coding` = **PASS**, the reply naming the Coding preset's real model and
**not** containing `There is no preset called`. Its guard rejects an invented model ref (`_MODEL_TAG`,
`:140`). The chat rows only run when the chat lane already has a model loaded (the probe checks
`GET /api/ps` first and reports BLOCKED otherwise, `:72-75`) — **BLOCKED is not a pass**, per the
project's 2026-10-11 rule.

**Automatable / eyes:** **automatable**, and already built.

---

## I. F3 `:latest` tag fix in `is_pooled_model`

**Commit:** `a61e9cacf`. Proved on the live 0.2.441 install: `/api/ps` on lane 11436 held
`qwen3-coder-30b-a3b-ud-q3-k-xl:latest` at 14,442,446,190 B with 10,679,610,244 B in VRAM; the Q6b
guard compared exact names, so Ollama's own `:latest` tag walked it past and the owner got the
74%-on-card / 26%-on-CPU duplicate.

**File:** `jarvis_presets.py:1202` `def is_pooled_model(model) -> bool:` (deployed tree).
**Pure function — safe to call.**

**Command (automatable, no token, no request, no state change):**

```powershell
py -3 -B -c "import importlib.util,sys; p=r'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_presets.py'; s=importlib.util.spec_from_file_location('jp',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('tagged  :', m.is_pooled_model('qwen3-coder-30b-a3b-ud-q3-k-xl:latest')); print('bare    :', m.is_pooled_model('qwen3-coder-30b-a3b-ud-q3-k-xl'))"
```

**Expected:** `tagged : True` and `bare : True`. A `tagged : False` means the fix did not install.
The suite's own Q6d row is `backend/test_lane_integrity.py:232-233`, and it drives the real
`warm_everyday()` seam proving the tagged name answers `False` with **zero** requests.

**Automatable / eyes:** **fully automatable** — this is the cheapest, sharpest check in the wave.

---

## Additive or already covered? — the wave-11 row inventory

`.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` **already carries these row ids**:

```
hud_model_chip   brain_hardware   compute_wording   lane_spill
chat_measured    chat_presets     chat_best_coding   chat_current_model
chat_safety      chat_conversation  chat_lane        chat_lane_resolution
smoke_no_token   smoke_status     smoke_pending      smoke_no_benchmark
mc_measured      mc_benchmark_start  mc_best_models  mc_preset_models
mc_current_previous  mc_installed  mc_conversation
```

| Feature | Already in the wave-11 file? |
|---|---|
| **H — F1 `chat_best_coding`** | **YES — row `chat_best_coding`. Nothing new needed.** |
| **B — resources plate** | **PARTLY.** `hud_model_chip`, `brain_hardware`, `compute_wording` cover the *wording* of the old panels; the `/api/models/resources` **route** is new and is already covered by the separate `probe_model_resources.py` the deploy lead built. **No new row in the wave-11 file.** |
| **C — measured card** | **NO new row.** `chat_measured` / `mc_measured` prove the *chat answers* about measurements, not the card's route. **New check (§C).** |
| **A — skills / DEF-049** | **NO.** Nothing in the wave-11 file touches skills. **New.** |
| **D — reversible UI** | **NO.** New route guard, new allow-list. **New.** |
| **E — drag-and-drop** | **NO.** New. **New.** |
| **F — read-aloud voice/Pause/Stop** | **NO.** New (`hud-read-aloud-voice.mjs` is the *repo* suite, not the live probe). **New.** |
| **G — Notion 4 GB** | **NO.** New. **New.** |
| **I — `:latest` guard** | **NO.** New. **New.** |

**Bottom line for the lead: the wave-11 file is additive.** 8 of the 9 items are new checks; only F1 is
an existing row that simply needs to flip to PASS, and B is already covered by your own
`probe_model_resources.py`. **Do not edit `verify_wave11_live.py`** — put the new rows in a wave-12
section/file so a wave-11 re-run stays comparable.

---

## Deploy risks visible in the diff

**R1 — the two new modules must land, or the routes are simply 404.**
`jarvis_model_resources.py` and `jarvis_reversible_ui.py` are **new files**, not patch hunks to existing
modules. Both are registered in the shipped list (`scripts/apply-patches.ps1:2862` and `:3161`), but the
copy step is what makes them exist. Because both routes are *added by an existing wrapper*
(`jarvis_model_recommendations.install()`, `jarvis_reversible_ui.install()`), a missing file yields
**"the route does not exist"** — which reads exactly like a patch failure. **Check the two file
timestamps before probing anything else.**

**R2 — a renamed settings/state file (with a fallback).**
`jarvis_model_resources.py:57-60`:
```
CHOICE_FILE = "presets-choice.json"
#: The name this file had before 2026-11-09; read only as a fallback.
LEGACY_CHOICE_FILE = "preset-choice.json"
```
`preset-choice.json` → `presets-choice.json`. The old name is read **only as a fallback**, so an
existing install keeps working — but the choice file is now the thing `active_lane.preset` /
`preset_title` come from (`:584-598`). **If the plate says no preset is chosen while the HUD shows one,
suspect two files, not a broken plate.** Note also `_jarvis-state.json` and its
`before-reseal-*` backups in the backend folder: that file is resealed, not reset.

**R3 — no new required environment variable was found.** Stated as a checked negative, not an
assumption: the diff adds no `os.environ[...]` requirement for the wave-12 features; the new module's
only ambient reads are the lane file and `OLLAMA_URL` as the **documented fallback**
(`jarvis_model_resources.py:53-61`). The one new grant is a **Tauri capability**, next risk.

**R4 — a new capability, which a stale exe build silently denies.**
`hud-speech = allow-speak-reply` is added to `jarvis-desktop/src-tauri/capabilities/hud.json` and
`permissions/surfaces.toml` (+40/-… in the diffstat). If the desktop exe is **not** rebuilt — only the
backend files copied — the HUD's one `speak_reply` call is **denied at the Tauri layer**, and Read out
loud fails with nothing useful in the page. `tools/check_invoke_grants.py` holds that grant. **Verify
the exe's build time moved, not just the backend folder's.** This is the highest-risk item in the wave
for a "backend-only" deploy.

**R5 — patch-base mismatch.**
The head is `a707c2e30` on `origin/main` `2644d57a2`. The routes arrive through
`backend/model-recommendations.patch` (which anchors on the owner's own lines just before the socket,
`backend/README.md:283`), so `apply-patches.ps1` will re-apply that patch over the **wave-11**
`jarvis_model_recommendations.py` now in the folder (74,240 B, 11/8 18:35). If the live base is older
than `2644d57a2`, an anchor can drift and the patch fails — the run's own `leftOut` / `notInstalled`
record is where that shows up. Twins are consistent at head (`backend/_where.py` and
`jarvis-backend/_where.py` both +26/−2), so the repo side is clean; the **live base** is the variable.

**R6 — a static-file path that differs between the repo tree and the installed tree.** The one that
will cost someone an hour:

| repo path | installed path | greppable? |
|---|---|---|
| `jarvis-desktop/src/jarvis_hud.html` / `jarvis-backend/jarvis_hud.html` | `<backend folder>\jarvis_hud.html` | **yes** |
| `jarvis-desktop/src/brain.js`, `model-resources.js`, `model-results.js`, `index.html` | inside `C:\Users\pcadmin\AppData\Local\Jarvis Desktop\jarvis-desktop.exe` | **NO** |

So a `grep brain.js` against the backend folder finds **nothing** and looks like a failed install. It
isn't — the file was never meant to be there. Measure the Brain by its **route** (§B, §C) and the
owner's eyes for the pixels. Confirmed this pass: `brain.js`, `model-resources.js`, `model-results.js`
and `index.html` are all absent from the backend folder, while `jarvis_hud.html` and `hud-presets.js`
are present.

---

## The run order, shortest first

1. **§0 timestamps** — did `jarvis_model_resources.py` and `jarvis_reversible_ui.py` arrive? (10 s, no token)
2. **§I `:latest`** — one pure function call; the sharpest single fix. (10 s, no token)
3. **§F HUD markers** — `speechSynthesis`/`getVoices` must be **0**. (10 s, no token)
4. **§A skills wiring** + **§G Notion constants** + **§D allow-list**. (30 s, no token)
5. **§B `probe_model_resources.py`** — you already built it. (token)
6. **§C measured** one-off GET. (token)
7. **§H re-run the wave-11 probe**; `chat_best_coding` flips to PASS. (token, needs a loaded model)
8. **Owner's eyes:** the plate's `Plan:` labels, the preset click raises **no card**, the drag gesture,
   and — the one no grep can settle — **that the voice is the female Jarvis voice**.

**Honest limits of this document.** I read the **head commit's** files via `git show` and the
**deployed** tree on disk; I did not run the deploy and did not call any route. Every route named here
is quoted from the head tree with a `file:line`, not inferred. The one place I am unsure of the exact
on-screen string is the read-aloud and drag-drop **button labels** (the HUD builds them in JS, and a
`"Pause reading"` grep at head returns only *comments*), which is why §F and §E assert on
**function names** rather than label text — deliberately, so a wording change cannot make a working
feature read as missing.
