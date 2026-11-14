# Field-test matrix → the post-deploy checklist (split by Q7)

**Written:** 2026-11-09 by the wave-12 integration subagent. **Read-only** until the one file
below; no deploy, no live model load, no approval card, no token printed.
**Source matrix ref actually read:** `integration/wave13-2026-11-09:docs/FIELD-TEST-MATRIX-2026-11-09.md`
(78 lines, rows 1–31, tip `993210bdc`). `main` in this checkout is **not** that tree —
`origin/main` is `2644d57a2` (the wave-10/11 deploy tree) and `integration/wave12-2026-11-09`
is **not** an ancestor of it. A plain file read of `docs/FIELD-TEST-MATRIX-2026-11-09.md` in a
worktree may show a different branch; every row quoted below is from the ref above.

**The Q7 split this file implements.** Automated/API checks run after **each** deploy.
Owner-hands rows — drag-and-drop, listening to the read-aloud audio + Pause, the tray
"Up to date" line, importing a Notion export, approving `github_create_repo`, Creator Mode, and
the two HUD fixes — are held for **one sitting after the wave-13 deploy**, not repeated per deploy.

Classes used: **AUTOMATED-NOW** = already covered by
`.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` (script row id named) ·
**API-PROBE** = an exact read-only command that can run today · **OWNER-HANDS** = only the owner
driving it is a PASS (`sitting` = Q7-named for the post-wave-13 sitting; `own time` = not named by
Q7, still needs the owner) · **NOT-TESTABLE-YET** = cannot be driven at all today.

## 1. The table

| # | short row text | class | command to run | expected evidence | when / who |
|---|---|---|---|---|---|
| 1 | Brain "Loaded now / Resources" truth + Compute panel names the real cards | AUTOMATED-NOW | `py -3 -B .dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` — rows `brain_hardware`, `compute_wording` | 3 NVIDIA cards / 28 GiB, tier sentence once; never "the second card". Plate pixels + "Plan:" labels are NOT RUN YET (exe) | after every deploy / deploy lead |
| 2 | Lane truth (dead pooled lane falls back; explicit `num_ctx`; warm guard) | AUTOMATED-NOW | same script — rows `lane_spill`, `mc_current_previous` | `/api/ps` context_length 49,152 and size == size_vram == 0 spill on the active lane; BLOCKED if nothing loaded (never a pass) | after every deploy / deploy lead. **F2 stays OPEN** — see finding F1 |
| 3 | "Hide advanced" label, HUD local-session line gone, foldable model filters | AUTOMATED-NOW | same script — rows `ui_hide_advanced`, `ui_foldable_filters`, `ui_no_local_session_line` | three PASS lines naming the served page's bytes; the matrix calls the 0.2.441 run PARTIAL because it was not visually driven | after every deploy / deploy lead |
| 4 | Auto Wi-Fi reconnect (switch, journal, honest "did you reconnect?") | OWNER-HANDS (own time) | — owner toggles the switch | switch moves, a journal line appears, and the "did you reconnect?" question is honest | owner, own time (not Q7-named) |
| 5 | Right/Wrong v2 ("why" tags + owner's own correction) | OWNER-HANDS (own time) | — owner marks an answer Wrong and types a correction | the "why" tags draw; the owner's correction is what is stored | owner, own time |
| 6 | Skills self-knowledge: Jarvis answers the Skills menu truthfully | OWNER-HANDS (own time) | — ask in chat: "what skills do I have on?" | the answer matches the Skills menu, not a generic list | owner, own time |
| 7 | Skill install/edit/turn-on scanned by the four extra checks; `skills.lock` row written | API-PROBE | `$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($f in @("jarvis_skill_hub.py","jarvis_skills.py")){ "--- $f"; Select-String -Path (Join-Path $d $f) -Pattern "extra_findings|LOCK_NAME =|skills.lock" \| ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" } }` | `jarvis_skills.py` has an `extra_findings(` **call** and the `skills.lock` write/delete pair; both file timestamps moved off `11/6/2026 09:18`. A `vet()` report with `extra_checks 0` means it did not install | after every deploy / no token. The *behaviour* (a Hermes `!`cmd`` skill refused) is owner-hands, own time |
| 8 | Drag-and-drop a compatible file into the HUD / chat window | OWNER-HANDS (**sitting**) | pre-check only, no token: `$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Select-String -Path (Join-Path $d "jarvis_hud.html") -Pattern "function attachTake|function attachOthers|function attachNone|function attachShow|function attachClear"` | `attachTake(file, extra)` and `attachOthers(n)` present; page size/timestamp past `700,122 B / 11/9/2026 03:52`. Gesture: the file arrives on the next question; a 3-file drop names the ones left out | post-wave-13 sitting / owner (Tauri handler is in the exe — finding F2) |
| 9 | Drag-and-drop into the Alt+Space quick bar | OWNER-HANDS (**sitting**) | same marker grep as row 8 | same markers; the drop rides the bar's next question | post-wave-13 sitting / owner |
| 10 | Smart note creation: one sentence yields title/body/pin/date | OWNER-HANDS (own time) | — owner says one sentence into Notes | title, body, pin and date all filled from the one sentence; the note opens | owner, own time |
| 11 | Tray + Settings → Updates four-state truth | OWNER-HANDS (**sitting**) | — owner opens the tray menu and Settings → Updates | tray says "Up to date" only when it is, and the four states agree with the installed `FileVersion` | post-wave-13 sitting / owner. **Exe-only — finding F2** |
| 12 | Brain → Tutorials "What's new in Jarvis" pane + Open Settings → Updates | API-PROBE | `GET /api/recent-changes` with the token (see §2) | the answer carries the generated recent-changes entries the pane draws; the pane's pixels are eyes | after every deploy / deploy lead + owner's eyes |
| 13 | Notion import: a 276 MB export imports; refusals name real numbers; progress; free-space check | OWNER-HANDS (**sitting**) | pre-check, no token: `$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($f in @("jarvis_notion_obsidian.py","jarvis_upload.py")){ "--- $f"; Select-String -Path (Join-Path $d $f) -Pattern "4 GB|4 GiB|MAX_NOTION_BYTES|EXPORT_UNCOMPRESSED_MAX|STAGING_MAX" \| Select-Object -First 8 \| ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" } }` | `MAX_NOTION_BYTES 4 GiB`, `STAGING_MAX 4 GiB`, PC ceiling 4 GB and the declared total also raised. Owner's real 276 MB export then imports with progress and no false receipt | post-wave-13 sitting / owner. The two 4 GB numbers are deliberately distinct and equalised — read the comments before calling a mismatch a bug |
| 14 | Read out loud in Jarvis's own (female) voice + Pause / Resume / Stop | OWNER-HANDS (**sitting**) | pre-check, no token: `$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; foreach($m in @("pauseSpeechPlayback","resumeSpeechPlayback","stopSpeechPlayback","speechSynthesis","getVoices","data:audio/wav")){ $c=(Select-String -Path (Join-Path $d "jarvis_hud.html") -Pattern ([regex]::Escape($m)) -AllMatches -ErrorAction SilentlyContinue \| Measure-Object).Count; "{0,-24} {1}" -f $m,$c }` | `pauseSpeechPlayback` / `resumeSpeechPlayback` / `stopSpeechPlayback` / `data:audio/wav` ≥1 each; **`speechSynthesis` = 0 and `getVoices` = 0** (the David fallback is gone). Owner's ears: it is the female Jarvis voice and Pause really pauses | post-wave-13 sitting / owner. **Needs the rebuilt exe** (`hud-speech` capability) — finding F2 |
| 15 | Forget a time frame: no 200-item cap, both confirmations, backups untouched | OWNER-HANDS (own time) | — owner forgets a date range | two confirmations, no 200-cap truncation, and no backup file is touched | owner, own time |
| 16 | Manual-click rule: a reversible owner UI choice needs no card and has a switch-back | API-PROBE | `$d="C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; Select-String -Path (Join-Path $d "jarvis_reversible_ui.py") -Pattern "REVERSIBLE_UI_CHOICES|SWITCH_ROUTE =|\"apply_preset\"|\"switch_model\"" \| ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }` | `SWITCH_ROUTE = "/api/models/switch"`; exactly two allow-list keys; deploy log line `reversible  ready (2 choice(s))`; any other path gets `{"error": "There is nothing at that address, so nothing was changed."}` | after every deploy / no token. **Never POST the switch route** — it really switches the model. "No card on a preset click" is owner-hands, own time |
| 17 | Brain IA Recs 5/6: honest Galaxy labels, HUD→Brain map button, Goals under Projects | OWNER-HANDS (own time) | — owner opens Brain → Recommendations | labels match the Galaxy, the map button lands on Brain, Goals sits under Projects | owner, own time |
| 18 | Memory: the reworded-facts switch ON behaves as promised | OWNER-HANDS (own time) | — owner answers the card already waiting on the live PC | fewer cards, marked words, and the switch-back | owner, own time — **a card is pending right now** (finding F3) |
| 19 | Memory fault: ONE banner with "retry now" instead of a card queue | NOT-TESTABLE-YET | — | wave-13 work; nothing deployed to drive | after wave-13 deploy |
| 20 | Reminders "Grandma": relative date, title parsing, phone notification, no false receipt | NOT-TESTABLE-YET | — | wave-13 lane, not deployed | after wave-13 deploy |
| 21 | GitHub truth + carded `github_create_repo` ("Fitness Band") | OWNER-HANDS (**sitting**) | — owner approves the card | one card names the exact repo; nothing POSTs before the yes; the answer matches what GitHub created | post-wave-13 sitting / owner (needs the owner's token and ask) |
| 22 | Creator mode: stage a plug-in or skill, scan it, ONE PC-only install card, install ≠ enable | OWNER-HANDS (**sitting**) | — owner stages and installs | exactly one PC-only card; install does not enable; the plug-in half is refused in the pack manager's words | post-wave-13 sitting / owner |
| 23 | Jarvis-takeover design lane | NOT-TESTABLE-YET | — | no user surface exists to drive | not scheduled |
| 24 | Brain → Model "Measured results" card reads the real benchmark / five-suite stores | API-PROBE | `py -3 -B -c "import importlib.util,argparse; s=importlib.util.spec_from_file_location('w11',r'.dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); a=argparse.Namespace(base_url='http://127.0.0.1:4719', backend_path=r'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program', timeout=25.0); tok,src,notes=m.discover_token(a); print('token source:', src if tok else 'NONE'); c,b,e=m.http_get(a.base_url+'/api/models/measured',token=tok); print('HTTP',c); print(b[:3000])"` | `available: true`, `runs`/`scorecards`/`counts`/`stores`/`empty`/`notes`/`words`. **Empty is a pass when `empty.runs` says why**; a number with no store row is the failure | after every deploy / token. Card rendering = eyes |
| 25 | Ask "which model is better for the <preset>?" and get that preset's real model | AUTOMATED-NOW | `py -3 -B .dsh-scratch\WAVE11-VERIFY-2026-11-08\verify_wave11_live.py` — row `chat_best_coding` | **PASS**, naming `qwen3-coder-30b-a3b-ud-q3-k-xl`, and the text `There is no preset called` absent. BLOCKED (no model loaded) is not a pass | after every deploy / deploy lead — must flip from the 0.2.441 FAIL |
| 26 | The pooled lane keeps its 49,152-token window after a cold chat-triggered reload | NOT-TESTABLE-YET | — (no fix exists; see finding F1) | **OPEN** — a live 8,192 reload was measured. Nothing claims it fixed | not scheduled |
| 27 | The everyday lane never warms the pooled 30B, whatever tag Ollama reports | API-PROBE | `py -3 -B -c "import importlib.util,sys; p=r'C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program\jarvis_presets.py'; s=importlib.util.spec_from_file_location('jp',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('tagged  :', m.is_pooled_model('qwen3-coder-30b-a3b-ud-q3-k-xl:latest')); print('bare    :', m.is_pooled_model('qwen3-coder-30b-a3b-ud-q3-k-xl'))"` | `tagged : True` and `bare : True`. A `tagged : False` means the fix did not install. Pure function — no request, no state change | after every deploy / no token — the cheapest sharp check in the wave |
| 28 | Q6 two-tier benchmark: current vs candidate, KEEP CURRENT | API-PROBE | no re-run required; evidence receipt `.dsh-scratch/WAVE9-DEPLOY-2026-11-08/run-20261109-033413/WAVE11-RESULT-2026-11-09.md` | already **PASS** (76.8 vs 65.3 tok/s, KEEP CURRENT). Re-run only if the lane topology or preset changes | already measured; not per deploy |
| 29 | Q8 pooled warm before acceptance | API-PROBE | no re-run required; evidence `.dsh-scratch/WAVE11-INTEGRATION-2026-11-08/q8-run-20261109-035353/warm-result.json` | already **PASS** (49,152 / 0 spill, preset restored byte-for-byte) | already measured; not per deploy |
| 30 | The chosen personality is drawn as the chosen row, not a "(current)" word | NOT-TESTABLE-YET → sitting | — | wave-13 branch only (`993210bdc`, not in wave-12 or `origin/main`). Desk evidence exists: `jarvis-desktop/tests/hud-presets.mjs` 30/30, `hud-presets-chosen.mjs` 5/5 | after wave-13 deploy; then the owner's click in the sitting |
| 31 | The top model chip refreshes within 30 s of a preset changed outside the window | NOT-TESTABLE-YET → sitting | — | wave-13 branch only; `hud-current-models.mjs` pins the repaint. Drive by changing the preset on the PC and watching the chip without a reload | after wave-13 deploy; then the owner's eyes in the sitting |

## 2. The token, and never printing it

Every API-PROBE above that needs a token discovers it **the same read-only way
`verify_wave11_live.py` does** — `HUD_TOKEN`/`JARVIS_HUD_TOKEN` env → Windows Credential Manager
`Jarvis Backend/pairing token` then `Jarvis Desktop/pairing token` → `jarvis-framework.toml`'s
`[hud]` line — and verifies it with one `GET /api/status`. The one-liners load the script's own
`discover_token()` (line 368) and print only the **source label** and the HTTP status, never the
value. `scrub()` (line 163) redacts it from every printed and written string.

Read-only by construction, the only routes used here: `GET /api/status`, `/api/models`,
`/api/presets`, `/api/models/recommendations`, `/api/models/resources`, `/api/models/measured`,
`/api/compute`, `/api/pending`, `/api/bench`, `/api/bench/history`, `/api/recent-changes`,
`/api/version`, `GET /` (the HUD page), a lane's `/api/ps`, and `POST /api/chat`. **No approval
route, no switch, no install, no preset apply, no benchmark start.**

## 3. What the wave-12 deploy can honestly mark PASS

Only these, and only as the named script rows — never as the matrix row's whole feature:

- **Rows 1 and 3** — `brain_hardware`, `compute_wording`, `ui_hide_advanced`,
  `ui_foldable_filters`, `ui_no_local_session_line`. The matrix already calls row 1 PARTIAL and
  row 3 PARTIAL: these prove the shipped bytes/wording, not the drawn plate.
- **Row 2** — `lane_spill` and `mc_current_previous` prove the *measured* lane state only. F2 is
  open, so row 2 stays **PARTIAL** and row 26 stays **FAIL/OPEN**.
- **Row 25** — `chat_best_coding` may flip to **PASS**, and that is the one real product failure
  of the 0.2.441 acceptance. It needs a loaded model; BLOCKED is not a pass.
- **Rows 27, 24, 16, 7, 12** — an API-PROBE PASS means "the route/constant/allow-list arrived",
  which is a **precondition**, not the feature's own PASS. Write them as `ARRIVED`, not as the
  matrix row.
- **Rows 28 and 29** stay **PASS** on their existing receipts; they are not re-measured per deploy.

**Nothing owner-hands may be marked PASS from these checks.** A marker grep proves the code
shipped; it does not prove a drag, a voice, a tray line or an import.

## 4. What must stay NOT RUN YET, and why

| rows | state | why |
|---|---|---|
| 8, 9, 11, 13, 14, 21, 22 | **NOT RUN YET** | Q7 holds them for the one post-wave-13 sitting. A wave-12 deploy can only prove their arrival markers |
| 30, 31 | **NOT RUN YET** | wave-13 branch only; the fix is not in the wave-12 tree and not on `origin/main` |
| 19, 20 | **NOT RUN YET** | wave-13 lanes; nothing is deployed to drive |
| 26 | **FAIL / OPEN** | measured wrong on 0.2.441 and no fix exists (finding F1) |
| 23 | **NOT TESTABLE YET** | no user surface exists |
| 4, 5, 6, 10, 15, 17, 18 | **NOT RUN YET** | owner-driven, and **not named by Q7's sitting** — they need their own time |
| 1 (plate half), 2, 3 (visual half), 12, 17, 24 (card) | **PARTIAL / eyes** | pixels live in the exe; a route or grep cannot prove them |

## 5. Findings — rows naming something wave 12 may not deliver

**F1 — rows 2 and 26 are called "wave-13 design items" but no wave-13 lane carries them.**
The matrix says of F2: *"**F2 IS OPEN**: a chat-triggered reload lands at 8,192 because Ollama's
OpenAI-compatible endpoint ignores the request's top-level `options` … (DEF-034 second finding;
wave-13 design item)"*, and row 26: *"Carried to wave 13 as its first design item (DEF-034 second
finding); nothing claims it fixed."* But wave 13 is built in three lanes — creator, GitHub,
reminders — and the wave-13 diff (`origin/main..integration/wave13-2026-11-09`) changes no
lane-truth/`num_ctx` seam. **Consequence:** the post-wave-13 deploy will not close row 2 or row
26. Do not write them into the sitting's expected-PASS list.

**F2 — the owner-hands rows need the desktop exe, not a backend-only copy.**
Rows 8/9 (the Tauri drop handler *"must be off per window"*), 11 (the tray lives in the exe), 14
(the `hud-speech = allow-speak-reply` capability) and 30/31 (Brain/HUD frontends bundled inside
the exe) cannot be exercised by a backend-file deploy. The wave-12 probe doc's own highest-risk
item says it plainly: *"If the desktop exe is not rebuilt — only the backend files copied — the
HUD's one `speak_reply` call is denied at the Tauri layer, and Read out loud fails with nothing
useful in the page."* **Consequence:** "the wave-12 deploy" must mean **desktop release + backend
+ phone**, and the lead must check the exe's build time moved, not just the backend folder's.

**F3 — a memory card is already pending on the live PC.** Row 18: *"The card was raised last on
the live PC and is waiting for the owner; nobody answered it."* The deploy's `smoke_pending` row
counts *new* cards, so a pre-existing one will not fail it — but the owner should answer or deny
it before the sitting, or row 18 cannot be driven cleanly.

**F4 — the two commits the fixes claim are real in wave 12.** Verified by ancestry, not assumed:
`bbc419410` (row 25's F1 fix) and `a61e9cacf` (row 27's `:latest` fix) are both ancestors of
`integration/wave12-2026-11-09`; `993210bdc` (rows 30/31) is **not** — it is wave-13 only. No
finding here, recorded so the lead does not re-verify it.

**F5 — the Notion file has a non-obvious name.** Row 13 says "In #1217" and the module is
`jarvis_notion_obsidian.py` (present on wave 12), **not** `jarvis_notion.py`. A grep for the
obvious new name finds nothing and looks like a failed install. Constants live in
`jarvis_notion_obsidian.py` (PC) and `jarvis_upload.py` (phone) — two numbers deliberately made
equal.

---

**Honest limits.** I read the matrix from `integration/wave13-2026-11-09` and the probe commands
from the already-written `.dsh-scratch\WAVE12-INTEGRATION-2026-11-09\WAVE12-EXTRA-PROBES.md`;
I did **not** run the deploy and did **not** call any route. Every command above is one this
repository already documents, quoted rather than invented. Where no command exists, the cell says
`—` and the row is owner-hands or not-testable; nothing was made up to fill a row.
