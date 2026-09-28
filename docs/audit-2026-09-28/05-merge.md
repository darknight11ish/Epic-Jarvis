# 05 - Integration merge report (audit-integration, scratch, not pushed)

Final HEAD: `deaca649153344a7c776f15a1017a765276f29a6`. Nothing was pushed.

## 1. origin/claude/jarvis-audit-competitors-vyqpt1 -> commit 39912547
15 files. All were "both sides added in the same place", so I kept both:
- JARVIS-API.md: main's §59-61 kept, then competitors' §70-86. No section number clashes. For the `/api/graph` row I used competitors' text (taken off the Brain allowlist) and for `/api/models` main's text (offline cache).
- docs/README.md, AndroidManifest (the notification listener and the 3 Quick Settings tile services), JarvisRuntime (scheduleJob/Goals plus addTodayCard), MainActivity, Schedule.kt `tag()` (goal_checkin, next time, today card), HomeScreen, build.rs, lib.rs, brain.json, surfaces.toml, brain.css, brain.js, uikit.mjs (both mock blocks, and bridge params goals+historyImport+widgets): unions, with the shared closing lines repeated where each side needed its own.
- SettingsScreen `SETTINGS_ITEM_INDEX`: both used 12, so **quick-tiles was renumbered to 13**.

## 2. origin/claude/jarvis-ai-assistant-research-ff37vy -> 5b9e4246 (+ fix commit 841206e4)
48 files. The resolutions that needed more than a plain union:
- jarvis_agent.py: main had moved the notes into `dress_messages()`, and research added the Live note inline. I added `live=` to `dress_messages` (after the spoken note) and pass `watch.live`. The side-talk counting is kept after next_time's brought_up.
- jarvis_voice.py, voice_enroll, VoiceStrict/StrictVoice.kt, voice-training.js, voice_training.rs, settings.html, voice-panel.js: main's talk_to_type, wake_confirm and voice_id_model now sit next to research's hands_free_screen, hands_free_live and live_end in every list (DEFAULTS, _CHOICES, LOOSER, _STRICT_WHEN_DAMAGED, loosens, isLoosening, currentSetting).
- main.js `send()`: main's third argument was positional `cloudYes` and research's was `{live}`. They are now one options object `{live, cloudYes}`, and the cloud "yes" caller now passes `{cloudYes: true}`.
- BrainScreen.kt: main had moved the models list into Live/StaleModelsBody. I applied research's "embedding model gets no Use" (canChat) to both.
- JarvisRuntime.setSleepTime: main's "off is never held" plus research's `LinkWords.decisionBlocked`.
- ChatSession: `openSettingsFromRoute ?: ForgetRange.openFromRoute`, and both `cloudYes` and `live` are passed. second-card.mjs now expects the keys `..., "offer", "open_brain"`.
- brain.js: the Live view was renamed to "now" (research), and Galaxy uses `memory_entities` (main).
- asks-first-cases.json (both copies): regenerated with tools/gen_asks_first_cases.py.
- **Renumbered:** research's JARVIS-API §60 (chatbot) became **§87** and §61 (projects) became **§88**, because main already uses 60 (plan card) and 61 (phone notifications). 107 references that came with that branch were renumbered too, including the test anchors `"## 60."` / `"## 61."`. Comments inside .patch files were not changed. §62-64 kept their numbers.

## 3. origin/claude/jarvis-3d-animal-mascot-8dr0tb -> da92e16a (+ 76346df4, deaca649)
10 files: CHANGELOG, jarvis_reach.py, test_wellbeing.py (both test lists), ARCHITECTURE (the weather row moved into the section-4 table; the Voice row taken from the mascot side and the Cloud row from main), package.json and tests/README (merged word by word), widget.json, and floating.js (the `...signal` message, then `state="listening"` while talk-to-type holds the mic).
- critters-gen.js and CritterShaders.kt: regenerated with tools/gen_critters.py (`--check` passes).
- **Renumbered:** mascot §59 (the sky) became **§89**, because §59 is Goals. 12 references were renumbered with it.

## Patch-list ordering (the union-merged files)
No duplicates. $PATCHES has 97 entries, $SHIPPED 126, and `_where.SHIPPED` matches $SHIPPED exactly. The backend/README duplicate rows were already there on origin/main.

**Real ordering break, fixed:** the jarvis_hud.py install block had five patches all anchored "right after sources' block". They were goals and phone-notifications (continuation), brain-reads (competitors), projects (research) and sky (mascot). With all of them in the list, projects.patch did not apply, and test_installed_stand_in failed after the first merge. I re-anchored them into one chain: brain-reads.patch after phone-notifications, projects.patch after history-import, and sky.patch after forget-range. backend/patch-history was rebuilt.

## Check results (final tree)
| Command | Result |
|---|---|
| backend/run_suites.py (venv with numpy, sherpa-onnx, onnxruntime, cryptography) | 172 pass, 4 FAIL: test_brain_reads, test_photo_remind, test_history_import, test_forget_range (details below); 19 skipped |
| tools/check_parity.py | pass ("No undecided drift") |
| tools/check_command_acl.py | pass (249 commands) |
| Every generator with --check (asks-first, private-aloud, phone-voice, voice-training, lipsync, critters, projects, gen_notices) | pass after regenerating (gen_sky_places needs geonamescache, not installed) |
| Desktop tests/*.mjs (104 suites) | 103 pass, FAIL faces.mjs |
| cargo fmt --check; cargo check --target x86_64-pc-windows-msvc --all-targets | pass (I had to add the target with rustup) |
| apply-patches.ps1 (pwsh 7, stand-in backend, -SkipTests -SkipMissing -SkipPackages) | every jarvis_hud patch ok; memory-safety.patch "will not apply" to the synthetic jarvis_extract stand-in, and origin/main does the same |
| Android | no leftover conflict markers; no duplicated fun/class. Not compiled. |

Details of the 4 backend failures: each has a test that asserts its patch is **"last in apply-patches.ps1"** or that its install block "sits right before the main socket". These cannot all be true at once in the combined tree. The stack itself applies. They need the `_stack.later_rewriting` style check that test_rules_first_relay already uses.

faces.mjs: the only failure is "nothing is fetched from the network". An `https://iquilezles.org` credit in a faces.html comment is outside `<!-- -->`. It came from the continuation branch (d513af91), not from these merges.

## Merge findings for the owner and other sessions
1. JARVIS-API numbering: three branches chose their numbers independently (research 60/61, mascot 59). The renumbering to 87, 88 and 89 must be done again for real when these branches land on main.
2. The "last patch, right after sources" pattern breaks whenever two branches add a jarvis_hud install. Five patches did it this time. The four "is last" tests should be relaxed.
3. main.js `send()`: two branches changed the signature in incompatible ways (positional `cloudYes` versus the `{live}` object). A plain union would have made every Live turn a cloud "yes".
4. SettingsScreen index 12 was used by both phone-notify and quick-tiles.
5. Semantic overlaps to review (not changed): talk-to-type and Jarvis Live both claim the PC microphone, and voice.rs checks each against the talk button but not against each other. On a Live side-talk turn, next_time "brought up" is still counted.
6. Generated fixtures went stale in the combined tree (private-aloud, phone-voice, voice-training, critters). They were regenerated here and must be regenerated again when these branches merge for real.
