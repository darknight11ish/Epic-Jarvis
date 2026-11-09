# Field-test matrix — the Wave 9–13 sweep (desktop + phone)

**Opened 2026-11-09 03:05 PT by the off-peak continuation session.** This is the
register for the owner's queue item: *field-test every new or updated feature on
BOTH the desktop Jarvis and the Android Jarvis, on real hardware*, after the
waves land.

**How to read this.** A row becomes **PASS** only when the feature was actually
driven on the real app (desktop window or the owner's phone) and the evidence
names the build, the date and what was seen. `BLOCKED`, `PARTIAL` and
`NOT-TESTABLE` are never a pass - the same rule as
`docs/FIELD-TEST-MATRIX-2026-10-11.md`, whose October/early-November rows stay
intact and untouched. Until a row is driven it reads **NOT RUN YET**, which is
also not a pass.

**State at opening:** the register was opened on 2026-11-09 03:05 PT against the then-live
Wave-9 install. It now records the next measured state too: **Wave 10/11 is deployed and
installed** - desktop 0.2.441, backend 0.2.441, phone 0.2.4028 on `f0a5b32b`, runtime tree
identical to `2644d57a2` - and its live acceptance was **24 rows: 23 PASS / 1 FAIL / 0
BLOCKED** on 2026-11-09 (`chat_best_coding`, which #1217 fixes). Wave 12 is PR #1217
(F1 and F3 folded in, F2 recorded open) and is not deployed yet; Wave 13 is being built in
three local lanes. Rows whose feature is not deployed still read **NOT RUN YET**, and the
rows written from the 0.2.441 acceptance name their evidence paths; nothing below is
claimed beyond what that run measured.

| # | feature | wave | desktop | phone | verdict | evidence |
|---|---|---|---|---|---|---|
| 1 | Brain -> Model "Loaded now / Resources" truth + Compute panel names the real cards | 11/12 | PARTIAL | n/a (PC-only plate) | PARTIAL | Acceptance on the live 0.2.441 install (2026-11-09): `brain_hardware` PASS - the Brain names 3 NVIDIA cards / 28 GiB and its tier sentence once with no competing fit claims; `compute_wording` PASS - names the everyday card and "any card beyond the first", never "the second card" (`wave11-live-result.json`, receipt `.dsh-scratch/WAVE9-DEPLOY-2026-11-08/run-20261109-033413/WAVE11-RESULT-2026-11-09.md`). The wave-12 "Loaded now / Resources" plate and Measured results card are in #1217 and not deployed yet, so that half is NOT RUN YET. |
| 2 | Lane truth (dead pooled lane falls back; explicit num_ctx; warm guard) | 11 | PARTIAL | PARTIAL | PARTIAL | The warmed state is measured and honest: acceptance `lane_spill` PASS with the Q8-warmed 30B - /api/ps 11450 reports context_length 49,152 and size == size_vram == 17,366,494,735 B (0 spill, all three cards) (`.dsh-scratch/WAVE11-INTEGRATION-2026-11-08/q8-run-20261109-035353/warm-result.json`), and `mc_current_previous`/`lane_spill` rows pass. **F2 IS OPEN**: a chat-triggered reload lands at 8,192 because Ollama's OpenAI-compatible endpoint ignores the request's top-level `options`; the live 49,152 window is never claimed for a cold turn (DEF-034 second finding; wave-13 design item). |
| 3 | "Hide advanced" label, HUD local-session line gone, foldable model filters | 11 | PARTIAL | n/a | PARTIAL | Acceptance rows `ui_hide_advanced`, `ui_foldable_filters`, `ui_no_local_session_line` PASS as shipped-bytes checks: the installed 0.2.441 desktop release is built from ref 2644d57a2, whose brain.js/brain.html/hud-safety.js carry the whole fix (`wave11-live-result.json`). Not visually driven in this pass, so PARTIAL rather than PASS. |
| 4 | Auto Wi-Fi reconnect (switch, journal, honest "did you reconnect?") | 11 | NOT RUN YET | NOT RUN YET | NOT RUN YET | Shipped in 0.2.441 (the deploy reconcile added jarvis_wifi.py and the wifi-reconnect plugin passed - receipt gate 0H/4), but the switch and its journal were not driven in this pass. |
| 5 | Right/Wrong v2 ("why" tags + owner's own correction) | 10/11 | NOT RUN YET | NOT RUN YET | NOT RUN YET | Shipped in 0.2.441 (C115/C117/C118 claims) but not driven in this pass. |
| 6 | Skills self-knowledge: Jarvis answers the Skills menu truthfully | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | In #1217, not deployed yet. |
| 7 | Skill install/edit/turn-on scanned by the four extra checks; `skills.lock` row written | 12 | NOT RUN YET | n/a (phone cannot install) | NOT RUN YET | In #1217, not deployed yet. |
| 8 | Drag-and-drop a compatible file into the HUD / chat window | 12 | NOT RUN YET | n/a (one-sided; phone has Attach a file) | NOT RUN YET | In #1217 (the Tauri handler must be off per window); owner gesture test after deploy. |
| 9 | Drag-and-drop a compatible file into the Alt+Space quick bar | 12 | NOT RUN YET | n/a | NOT RUN YET | In #1217; owner gesture test after deploy. |
| 10 | Smart note creation: one sentence yields title/body/pin/date | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | In #1217, not deployed yet. |
| 11 | Tray + Settings -> Updates four-state truth | 12 | NOT RUN YET | n/a | NOT RUN YET | In #1217, not deployed yet. |
| 12 | Brain -> Tutorials "What's new in Jarvis" pane + Open Settings -> Updates | 12 | NOT RUN YET | n/a (one-sided) | NOT RUN YET | In #1217, not deployed yet. |
| 13 | Notion import: a 276 MB export imports on the PC; refusals name real numbers; progress; free-space check | 12 | NOT RUN YET | NOT RUN YET (phone sends its own 4 GB zip) | NOT RUN YET | In #1217, not deployed yet; owner has a real 276 MB export to try. |
| 14 | Read out loud in Jarvis's own (female) voice + Pause / Resume / Stop | 12 | NOT RUN YET | n/a (desktop audio) | NOT RUN YET | In #1217, not deployed yet; needs the owner's speakers. |
| 15 | Forget a time frame: no 200-item cap, both confirmations, backups untouched | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | In #1217, not deployed yet. |
| 16 | Manual-click rule: a reversible owner UI choice (preset first) needs no card and has a switch-back | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | In #1217 (preset receipt + Gemini-Q2 allow-list), not deployed yet; the owner's own click is the test. |
| 17 | Brain IA Recs 5/6: honest Galaxy labels, HUD->Brain map button, Goals under Projects | 12 | NOT RUN YET | n/a (phone keeps its own sections) | NOT RUN YET | In #1217, not deployed yet. |
| 18 | Memory: the reworded-facts switch ON behaves as promised (fewer cards, marked words) | 12 (setting) | NOT RUN YET | n/a (PC setting) | NOT RUN YET | The card was raised last on the live PC and is waiting for the owner; nobody answered it. |
| 19 | Memory fault: ONE banner with "retry now" instead of a card queue | 13 | NOT RUN YET | NOT RUN YET | NOT RUN YET | Wave-13 work, not built yet. |
| 20 | Reminders "Grandma": relative date, title parsing, phone notification flag, no false receipt | 13 | NOT RUN YET | NOT RUN YET | NOT RUN YET | Wave-13 lane building in its own worktree. |
| 21 | GitHub truth + carded `github_create_repo` ("Fitness Band") | 13 | NOT RUN YET | n/a unless a screen is added | NOT RUN YET | Built locally in the wave-13 GitHub lane; the first real POST needs the owner's token and ask. |
| 22 | Creator mode: stage a plug-in or skill, scan it, ONE PC-only install card, install != enable | 13 | NOT RUN YET | n/a (PC-only) | NOT RUN YET | Built locally in the wave-13 Creator lane; the skill half is complete, the plug-in half is refused in the pack manager's words. |
| 23 | The two queue items: Jarvis-takeover design lane (no user surface yet) | next | n/a | n/a | NOT TESTABLE YET | No user surface exists to drive. |
| 24 | Brain -> Model "Measured results" card reads the real benchmark / five-suite scorecard stores | 12 | NOT RUN YET | n/a (PC-only plate) | NOT RUN YET | In #1217, not deployed yet. |
| 25 | Ask "which model is better for the <preset>?" and get that preset's real model | 11 | FAIL (0.2.441), fixed in #1217 - re-test after the wave-12 deploy | NOT RUN YET | FAIL | Acceptance row `chat_best_coding` FAIL on the live 0.2.441 install: "which model is better for the Coding preset?" answered "There is no preset called 'better for the Coding'" (24 rows: 23 PASS / 1 FAIL / 0 BLOCKED; `wave11-live-result.json`). Fixed in #1217 (bbc419410) with `backend/test_quick_wins.py` checks; the wave-12 deploy's acceptance re-runs this row. |
| 26 | The pooled lane keeps its measured 49,152-token window after a cold chat-triggered reload | 11 | FAIL (0.2.441) / OPEN | n/a | FAIL | Measured live 2026-11-09: with the 30B unloaded, POST /v1/chat/completions carrying options.num_ctx=49152 reloaded the model at context_length 8192 - Ollama's OpenAI-compatible endpoint ignores the top-level options field. The Q8 native load does produce 49,152 / 0 spill, so the window is real but the chat path does not name it. Carried to wave 13 as its first design item (DEF-034 second finding); nothing claims it fixed. |
| 27 | The everyday lane never warms the pooled 30B, whatever tag Ollama reports | 12 (fix) | FAIL (0.2.441), fixed in #1217 - re-test after the wave-12 deploy | n/a | FAIL | Reproduced live: /api/ps on 11436 held qwen3-coder-30b-a3b-ud-q3-k-xl:latest at 14,442,446,190 B, 10,679,610,244 B in VRAM (74% on card) - the owner's photographed duplicate. Root cause: the third-card guard compared exact names and Ollama reports a ":latest" tag. Fixed in #1217 (a61e9cacf, `backend/test_lane_integrity.py` Q6d drives the real warm seam). |
| 28 | Q6 two-tier benchmark on this PC: current vs candidate, KEEP CURRENT verdict | 11 | PASS (measured by the Q6 harness) | n/a | PASS | Coding pair at 49,152: incumbent 76.8 tok/s / 0 spill / promotion-grade / 6 of 6 coding; candidate q4_K_M 65.3 tok/s / 231.5 MiB spill / 6 of 6 -> KEEP CURRENT. Q9 general pair at the literal 196,608: both promotion-grade (qwen3.5:9b 41.5 tok/s, gemma4:12b 33.3 tok/s), five-suite scores recorded, general verdict KEEP CURRENT (receipt `.dsh-scratch/WAVE9-DEPLOY-2026-11-08/run-20261109-033413/WAVE11-RESULT-2026-11-09.md`). |
| 29 | Q8 pooled warm before acceptance | 11 | PASS | n/a | PASS | After apply_preset("coding"): /api/ps on 11450 shows context_length 49,152, size == size_vram == 17,366,494,735 B (0 spill), model spread over all three cards; the owner's preset was restored byte-for-byte afterwards, and no card was raised or answered (`.dsh-scratch/WAVE11-INTEGRATION-2026-11-08/q8-run-20261109-035353/warm-result.json`). |

**Reading a PARTIAL / FAIL row:** PARTIAL means one honest half was measured and the other was not;
FAIL means a real app was driven and the result was wrong. Neither is a pass.
**Measured on:** desktop 0.2.441 / backend 0.2.441 / phone 0.2.4028 (attached `f0a5b32b`), runtime tree
identical to `2644d57a2`; acceptance 24 rows: 23 PASS / 1 FAIL / 0 BLOCKED.
**The merged tree's own main CI confirms the deploy's same-tree waiver:** run `42609957379` on
`2644d57a2` completed **SUCCESS at 2026-11-09 04:55:55 PT**, every job green including `audit` - so the
wave-10/11 deploy tested a tree a full green run of its own had passed, not only the pull-request run.

**Owner device:** phone `f0a5b32b` (attached 2026-11-09 02:12 PT); Windows 11 PC
with the desktop app. **Builds to write in when the sweep starts:** the
`desktop-latest` / `client-latest` versions at that time (record them by reading
`gh release view` and the installed `FileVersion` / `versionName` - never from
memory).

**What the sweep must include, per feature:** the real gesture or screen (not a
source read), the owner's words where the feature came from the owner, at least
one refusal path (the plain sentence), and the undo or switch-back where one
exists. A feature that cannot be reached on a device is written `BLOCKED` with
the concrete reason.
