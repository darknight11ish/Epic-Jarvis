# Dependencies, licences, tests and CI: audit, 2026-09-26

Read-only audit of branch `claude/admiring-ritchie-5urg5h` at commit `cd70a75`.
No code was changed and nothing was committed. Where a claim rests on a file
it gives `file:line`; where it rests on a command or on GitHub, it says so.

## Summary in plain words

1. **No licence blocks you.** Nothing is GPL or AGPL inside either app. The one non-commercial part (the "hey Jarvis" models) is fine for a free, sideloaded app.
2. **The notices are incomplete.** Both About boxes say only "MIT". The phone app lists none of the parts it is built from. The desktop notices file is out of date: it leaves out at least six parts the app now uses.
3. **One security warning, probably not shipped.** `cargo audit` flags rustls 0.23.44 (medium). My checks say the app does not build it. A one-line update clears it anyway.
4. **Most libraries are one or two versions behind, and the reason is written down.** The biggest gap: ONNX Runtime 1.22 against 1.30, held back on purpose because newer versions send data home.
5. **The most important safety code is tested only by reading its text.** That covers the approval checks in the desktop's Rust and the phone's "stream is stale" block. A reformat or a merge breaks these tests while the behaviour stays correct, and the reverse can also happen.
6. **The approval gate's end-to-end tests never run in CI.** They need `jarvis_gate.py`, which exists only on your PC.
7. **CI is slow, about 20 minutes per push.** Almost all of that is the desktop page tests running one after another. Every push starts it again, including edits to `CLAUDE.md` alone, and nothing cancels an older run.
8. **The phone's CI does not run when the backend or the desktop changes.** Some phone tests check those files, so a break there is only found on the next phone push.

## Table A: dependencies

Key: "Latest" was looked up today on crates.io, npm, PyPI, Maven Central or
GitHub (git tags). **n/c** means not checked, with the reason in the
"could not check" section. "Shipped" means the file ends up inside an app or
installer you hand out.

### Desktop app (Rust, `jarvis-desktop/src-tauri/Cargo.toml`, versions from `Cargo.lock`)

| Dependency | Where | In use | Latest | Licence | OK? |
|---|---|---|---|---|---|
| tauri | Cargo.toml:22 | 2.11.5 | 2.11.6 | Apache-2.0 OR MIT | Yes (patch behind) |
| tauri-build | :19 | 2.6.3 | 2.6.3 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-global-shortcut | :23 | 2.3.2 | 2.3.2 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-clipboard-manager | :24 | 2.3.3 | 2.3.3 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-notification | :25 | 2.4.0 | 2.4.0 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-store | :29 | 2.4.4 | 2.4.5 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-single-instance | :31 | 2.4.4 | 2.4.5 | Apache-2.0 OR MIT | Yes |
| tauri-plugin-updater | :57 | 2.11.0 | 2.12.0 | Apache-2.0 OR MIT | Yes, **missing from notices** |
| window-vibrancy | :36 | 0.6.0 | 0.8.1 | Apache-2.0 OR MIT | Yes (held on purpose, :32-35) |
| image | :37 | 0.25.10 | 0.25.10 | Apache-2.0 OR MIT | Yes |
| reqwest | :38 | 0.12.28 | 0.13.5 | Apache-2.0 OR MIT | Yes, 0.13.5 also in graph and **missing from notices** |
| serde / serde_json | :39-40 | 1.0.229 / 1.0.151 | same | Apache-2.0 OR MIT | Yes |
| tokio | :41 | 1.53.1 | 1.53.1 | MIT | Yes |
| base64 | :42 | 0.22.1 | 0.23.1 | Apache-2.0 OR MIT | Yes |
| sysinfo | :45 | 0.32.1 | 0.39.6 | MIT | Yes (7 minor behind) |
| xcap | :50 | 0.9.8 | 0.9.8 | Apache-2.0 | Yes |
| cpal | :63 | 0.15.3 | 0.18.2 | Apache-2.0 | Yes, **missing from notices** |
| hound | :66 | 3.5.1 | 3.5.1 | Apache-2.0 | Yes, **missing from notices** |
| windows-sys | :73 | 0.59.0 | 0.61.2 | Apache-2.0 OR MIT | Yes (matches Tauri) |
| windows | :99 | 0.61.3 | 0.62.2 | Apache-2.0 OR MIT | Yes (matches Tauri, comment above it) |
| windows-future | :130 | 0.2.1 | 0.100.0 (renumbered) | Apache-2.0 OR MIT | Yes |
| libc (unix only) | :133 | 0.2.189 | 0.2.189 | Apache-2.0 OR MIT | Not shipped on Windows |
| option-ext, cssparser, selectors, dtoa-short (transitive) | notices | - | - | MPL-2.0 | Yes. File-level copyleft, used unmodified (notices say so) |
| All other transitive crates (about 340 on Windows) | THIRD-PARTY-NOTICES.txt:279-300 | - | - | permissive (MIT, Apache, BSD, ISC, Zlib, Unicode, BSL) | Yes. `deny.toml` allowlist, CI `audit` job |
| @tauri-apps/cli (build tool) | package.json:35 | 2.11.5 | 2.11.5 | Apache-2.0 OR MIT | Yes, not shipped |
| Chakra Petch, IBM Plex Sans/Mono fonts | src/fonts/ | - | - | OFL-1.1 | Yes, but **not in THIRD-PARTY-NOTICES** (only `src/fonts/OFL.txt`) |
| Vendored JavaScript in `src/` | - | none found | - | - | No third-party JS: only the fonts, plus the stream2sentence word list (MIT, credited in notices) |
| WebView2 Runtime | tauri.conf.json | not redistributed | - | Microsoft | Yes (bootstrapper) |

### Phone app (`jarvis-client/app/build.gradle.kts`; there is no version catalog)

| Dependency | Where | In use | Latest | Licence | OK? |
|---|---|---|---|---|---|
| Android Gradle plugin | build.gradle.kts (root):8 | 9.4.0 | n/c (Google Maven blocked) | Apache-2.0 | Build tool |
| Kotlin compose/serialization plugins | root :9-10 | 2.4.20 | 2.4.20 (stable) | Apache-2.0 | Yes |
| Gradle | gradle-wrapper.properties:3 | 9.6.0 | 9.8.0 | Apache-2.0 | Build tool, checksum pinned |
| Compose BOM (ui, material3, foundation) | app :258 | 2026.06.00 | n/c | Apache-2.0 | Yes (held on purpose, :247-257) |
| androidx core-ktx / activity-compose / lifecycle ×2 | :260-271 | 1.15.0 / 1.12.4 / 2.8.7 | n/c | Apache-2.0 | Yes |
| androidx glance, glance-appwidget | :287-288 | 1.1.1 | n/c | Apache-2.0 | Yes |
| androidx biometric / fragment | :302, :318 | 1.1.0 / 1.3.0 | n/c | Apache-2.0 | Yes |
| kotlinx-serialization-json | :293 | 1.7.3 | 1.11.0 | Apache-2.0 | Yes (4 minor behind) |
| kotlinx-coroutines-android | :294 | 1.9.0 | 1.11.0 | Apache-2.0 | Yes |
| OkHttp | :320 | 4.12.0 | 5.5.0 | Apache-2.0 | Yes (4.x on purpose, MockWebServer API, :345-347) |
| Okio | :321 | 3.6.0 | 3.18.2 | Apache-2.0 | Yes (above the 3.4.0 fix for CVE-2023-3635, from memory) |
| ONNX Runtime Android | :332 | 1.22.0 | 1.30.0 | MIT | Yes. **Pinned on purpose:** 1.30.0 adds telemetry (:323-331) |
| openWakeWord models ×3 (in APK) | assets/wakeword/ | v0.5.1 | - | **CC BY-NC-SA 4.0** | Yes for this app (non-commercial, attributed). **Missing from the About box** |
| stop_head.bin (own model on openWakeWord embeddings) | assets/wakeword/ | - | - | treated as CC BY-NC-SA 4.0 | Same as above |
| Smart Turn v3.2 (in APK) | assets/turn/ | 3.2 | - | BSD-2-Clause | Yes, licence text sits next to it |
| junit / androidx.test / mockwebserver (tests only) | :334-355 | 4.13.2 / 1.2.1-1.6.2 / 4.12.0 | 4.13.2 / n/c / 5.5.0 | EPL-1.0 / Apache-2.0 | Not shipped |

### Backend (`backend/requirements.txt`: **no versions are pinned**, so each install gets the newest)

(Since 2026-09-26 `backend/requirements.lock` pins them all with hashes, and CI checks it for
advisories; the install does not use it yet - "Python packages pinned with hashes" below.)

| Dependency | Where | Pinned | Latest (PyPI) | Licence (PyPI metadata) | Advisories on latest | OK? |
|---|---|---|---|---|---|---|
| numpy | requirements.txt:17 | no | 2.5.3 | BSD-3 AND 0BSD AND MIT AND Zlib AND CC0 | 0 | Yes |
| sherpa-onnx | :18 | no | 1.13.8 | Apache | 0 | Yes |
| onnxruntime | :19 | no | 1.30.0 | MIT | 0 | Yes (the PC gets 1.30, the phone 1.22; see B-15) |
| fastembed | :20 | no | 0.8.1 | Apache-2.0 | 0 | Yes |
| sqlite-vec | :21 | no | 0.1.9 | MIT / Apache-2.0 | 0 | Yes |
| uiautomation (Windows) | :22 | no | 2.0.29 | Apache 2.0 | 0 | Yes |
| tomli (<3.11) | :23 | no | 2.4.1 | MIT | 0 | Yes |
| ddgs | :24 | >=9.16.0 | 9.16.0 | MIT (brings primp MIT, lxml/click BSD-3) | 0 | Yes |
| cryptography | :25 | no | 50.0.1 | Apache-2.0 OR BSD-3 | 0 | Yes |
| tzdata (Windows) | :26 | no | 2026.4 | Apache-2.0 | 0 | Yes |
| Optional: playwright, speechbrain, torch, f5-tts, soundfile | :28-51 | no | 1.63.0, 1.1.1, 2.14.0, 1.1.22, 0.14.0 | Apache / Apache / Apache+BSD+MIT mix / MIT / BSD-3 | 0 | Yes, and none is shipped |
| SearXNG (Docker, separate program) | THIRD-PARTY-NOTICES.txt:225 | - | - | AGPL-3.0 | - | Yes: run unmodified, not distributed |

### Models the backend downloads (the owner downloads them; they are not in the repo unless stated)

| Model | Where named | Licence | OK? |
|---|---|---|---|
| qwen3:8b (Ollama) | backend/jarvis-primary.Modelfile:86 | Apache-2.0 (from memory, not re-checked) | Yes, not redistributed |
| BAAI/bge-small-en-v1.5 (fastembed downloads it on first use) | rebuilt/jarvis_memory.py:421 | MIT (from memory, not re-checked) | Yes, but **not in notices** |
| openWakeWord v0.5.1 ×3 | backend/README.md:4806 | CC BY-NC-SA 4.0 | Yes (non-commercial) |
| Parakeet TDT 0.6B v2 (speech to text) | README.md:4784 | CC-BY-4.0 | Yes |
| Kokoro-82M v0.19 (voice) | README.md:4799 | Apache-2.0 | Yes |
| Silero VAD | README.md:4806 | MIT | Yes |
| 3D-Speaker CAM++ | README.md:4305 | Apache-2.0 | Yes |
| NeMo TitaNet-Large | README.md:6754 | "as its NGC card states", **never checked** (notices say so) | Unknown |
| ZipVoice distill + Vocos 24 kHz | README.md:6479 | Apache-2.0 (**not checked**, notices say so) + MIT; trained on Emilia (NC) | Yes for non-commercial |
| F5-TTS v1 Base + vocos-mel-24khz | README.md:6530 | **CC-BY-NC** + MIT | Yes for non-commercial |
| Smart Turn v3.2 (from the pipecat-ai 1.11.0 wheel, SHA-256 checked) | README.md:4991 | BSD-2-Clause | Yes |

### CI actions (`.github/workflows/`). Not shipped, so their licence does not matter here.

| Action | Pinned how | In use | Latest tag | Note |
|---|---|---|---|---|
| actions/checkout | SHA `11d5960a` in 4 files; **tag `@v4` in ci.yml** | v4.4.0 | v7.0.1 | Node 20, warns |
| actions/setup-node | SHA `49933ea5` (desktop-release); `@v4` (ci.yml:43) | v4.4.0 | v7.0.0 | Node 20 |
| actions/setup-python | **`@v5` only** (ci.yml:106,126) | v5 | v7.0.0 | Node 20, warns in logs |
| actions/setup-java | SHA `cf277c60` | v4.9.1 | v6.0.1 | Node 20, warns |
| actions/upload-artifact | SHA `ea165f8d` | v4.6.2 | v7.0.1 | Node 20, warns |
| actions/download-artifact | SHA `d3f86a10` | v4.3.0 | v8.0.1 | Node 20, warns |
| android-actions/setup-android | SHA `9fc6c4e9` | v3.2.2 | v4.0.4 | Node 20, warns |
| Swatinem/rust-cache | SHA `6323deb1` (release); **`@v2` (ci.yml:29)** | v2.9.2 | v2.9.2 | OK |
| dtolnay/rust-toolchain | SHA `6bed0761` (release); **`@stable` (ci.yml:26,404)** | stable | - | Branch-pinned |
| taiki-e/install-action | **`@cargo-deny` (ci.yml:405)** | moving tag | v2.87.20 | Unpinned |

## Table B: tests and CI issues

Sizes: S = under an hour, M = half a day, L = a day or more.

| # | Issue | Where | Fix | Size |
|---|---|---|---|---|
| B-1 | Desktop approval rules (stale stream, widget under App lock, email only in the Jarvis bar, notification can only deny) are tested only by regex over the Rust text. The page tests exercise a JavaScript stand-in, not the Rust. | decide.mjs:161-163, security.mjs:304-341, email-send.mjs:201; stand-in uikit.mjs:1249,1278,1335; real code commands.rs:2103-2190 | Move the checks into one plain Rust function (inputs: stale, window, App lock, is-email, approve) and test it with `cargo test`. Keep one text check that `answer_approval` calls it. | M |
| B-2 | Phone `decisionBlocker` (rule 4 on the phone) is called by no test. `actionBlocker` is checked only by its position in the source text. | JarvisRuntime.kt:2413,2436; AutoLearnTest.kt:590-592, MemoryEraseTest.kt:108, MemoryProfileTest.kt:129, MemoryUsedTest.kt:143 | Make the blocker a pure function of (stale, link, deciding, pending, now) and add a JVM test per case. | S-M |
| B-3 | The approval gate's end-to-end tests (stamp refused, egress, push) are skipped in CI because they need the owner's `jarvis_gate.py` | run_suites.py NEEDS_OWNER (gate_egress, gate_outcome, gate_push, approval_notice); test_owner_check.py:28-30 | Build a stand-in `jarvis_gate.py` from the patches, as test_installed_stand_in.py already does for `jarvis_hud.py`, and run those suites against it | M-L |
| B-4 | Phone's risky-approval fingerprint path (BiometricPrompt) has no test. The rule for WHICH cards are risky is tested well. | RiskyApprovalContractTest.kt (rule only); no test mentions biometric | JVM test that a risky decide() asks for the fingerprint before posting (inject the prompt) | M |
| B-5 | Many tests read other code's text and match exact lines. They broke in the last merges: 84ca552 (MemoryUsedTest), 5df29b8 (coming-up.mjs after rustfmt), cd70a75 (emulator test). | Desktop: 42 of 71 suites read `src-tauri` text (security, coming-up, pairing, auto-learn, briefing, second-card, hud, history, voice-training most). Phone: 8 JVM tests read `.kt` (AutoLearn, CardWordsContract, MemoryErase, MemoryProfile, MemoryUsed, SpeechText, VoiceFlow, VoiceStrict). Backend: test_chat_stream, test_tool_calling_wiring, test_big_model heaviest. | Keep text reads that pull out DATA (route lists, shared wording). Replace ones that match CODE with behaviour tests (B-1, B-2 first). Follow the shared-fixture pattern of test_approval_contract.py and RiskyApprovalContractTest. | L (do it gradually) |
| B-6 | test_standby_schedule's clock-change checks do not skip on Windows, where `use_tz` cannot set the zone. On your PC (apply-patches runs the suites) they pass only in a UK-style zone. test_schedule.py skips the same case properly. | test_standby_schedule.py:82-87, 182-194; compare test_schedule.py:139-140 | `if not use_tz(...): return check("SKIP ...", True)` around the two DST checks | S |
| B-7 | test_standby_schedule's `_settled()` waits up to 6 s for background work, then carries on without saying so. A slow machine gives a confusing failure later instead of "timed out". | test_standby_schedule.py:325-330 | Fail with a clear message when it runs out of time | S |
| B-8 | Wall-clock deadlines remain in test_sensitive after 8501f46 fixed one of them | test_sensitive.py:442-447 (<1.5 s), 566-569 (<1.8 s) | Allow more time (e.g. under 3 s: the point is "not 8 s"), or measure with the injected clock | S |
| B-9 | Clock-dependent briefing tests failed CI three times (runs 169-171) until 71b08a2. More real-clock reads remain. | test_briefing.py:287,367,623-627,873,937,959,1167 | Give every World/backoff the test clock. Leave real time only for the deadline check. | S-M |
| B-10 | `npm run test:all` runs 36 of 71 desktop suites. Missing: security, pairing, email-send, own-network, focus, reach, web-search and 28 more. | package.json:31 vs tests/ | Make `test:all` loop over tests/*.mjs the way ci.yml:67-82 does | S |
| B-11 | CI takes about 20 min, and 19.6 min of it is the desktop page-test step, run one suite at a time | GitHub run 36210892916, "Every desktop test suite" 02:12:10 to 02:31:47 | Run the suites 4 at a time (`xargs -P4`) or split them over 2-3 jobs; print each suite's time | M |
| B-12 | No `concurrency` in ci.yml: an older push keeps running. Runs 185 and 186 ran side by side on the same branch. | ci.yml (none); the other 3 workflows have it | Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` | S |
| B-13 | CI runs on every push to every branch AND on pull_request (a PR branch runs twice). A `CLAUDE.md`-only commit runs the full 20 min (run 178). | ci.yml:8-11 | `paths-ignore: [CLAUDE.md]` (not `docs/`: over 20 suites read docs). Limit `pull_request` to `main`. | S |
| B-14 | The phone workflow runs only when `jarvis-client/**` changes, but its JVM tests read `backend/` and `jarvis-desktop/` files | jarvis-client.yml:5-10; e.g. MemoryUsedTest.kt:42,51 | Add `backend/**` and `jarvis-desktop/src/**` to its paths, or run just the JVM tests from ci.yml | S |
| B-15 | Node 20 deprecation warning on every job. Every action is a v3/v4-era release. | logs of runs 36197820141, 36210788623 | Move to checkout v5+, setup-python v6+, setup-java v5+, artifact v5+ (current majors listed in Table A). Check each release note. | S-M |
| B-16 | ci.yml uses moving tags (`@v4`, `@stable`, `@cargo-deny`). The other workflows pin commits, and verify-toolchain.yml:24 says every `uses:` should be pinned. | ci.yml:25-29,42-43,99,106,125-126,145,403-405 | Pin to commit SHAs like the other workflows | S |
| B-17 | Unpinned tools in CI: Playwright (`npm install playwright`, no version), pip packages, stable Rust with `clippy -D warnings`. A new upstream release can turn CI red with no code change. | ci.yml:65, 109, 26; no rust-toolchain.toml | Pin Playwright and the pip versions; add rust-toolchain.toml (e.g. the version CI uses today) | S |
| B-18 | No job-level `timeout-minutes` in ci.yml (GitHub's default is 6 hours) | ci.yml | 30 min each | S |
| B-19 | Write permission for every job: `contents: write` is set for the whole workflow in jarvis-client, android-apk and desktop-release, including test jobs. ci.yml sets nothing. | jarvis-client.yml:12, android-apk.yml:33, desktop-release.yml:46 | `contents: read` at the top; `write` only on the publish job | S |
| B-20 | Rolling releases are overwritten by whichever branch pushed last. client-latest has no branch filter. desktop-latest takes `claude/**` (your 2026-09-24 decision). | jarvis-client.yml:5, desktop-release.yml:41 | Your call. At least limit client-latest the same way. | S |
| B-21 | Jobs or steps that cannot fail: `face-shots` (job), APK publish step (continue-on-error). A failed publish shows green. | jarvis-client.yml:1071, 956 | Deliberate. Consider making the publish failure visible as a red check. | S |
| B-22 | THIRD-PARTY-NOTICES is out of date, and nothing checks it | see A. `npm run notices` exists, package.json:23 | CI step: regenerate and diff | S |
| B-23 | `cargo audit` fails on the lockfile (RUSTSEC-2026-0285, rustls). `cargo deny` in CI passes. | see "Security advisories" below | `cargo update -p rustls` | S |
| B-24 | No Dependabot or Renovate, so nobody is told when a dependency ages | .github/ | Add dependabot.yml for github-actions, cargo, npm, gradle (monthly) | S |

## Details

### Licences: what is and is not a problem

- **Copyleft:** none in either shipped app. The Rust graph is guarded by
  `deny.toml` (allowlist, CI job `audit`, ci.yml:397-406). The MPL-2.0 crates
  are used unmodified and named in the notices. SearXNG (AGPL) and
  Ollama run as separate programs, and nothing of them is distributed.
- **Non-commercial:** openWakeWord models (in the APK), F5-TTS weights and
  the ZipVoice training data (downloaded by the owner). All are fine while
  Jarvis stays free and non-commercial (rule 5). The NC licence also allows
  publishing on GitHub and a public GitHub release, as long as nobody sells it.
- **ShareAlike:** `stop_head.bin` and `jarvis_wakebank.py` are made from
  openWakeWord output. They are already treated as CC BY-NC-SA
  (THIRD-PARTY-NOTICES.txt:86-108). **But `LICENSE` says the whole repository
  is MIT, with no exception.** Add one line to LICENSE: "Except the files
  named in THIRD-PARTY-NOTICES.txt, which keep their own licences".
- **The About boxes (confirmed):** desktop `settings.html:1266`
  "MIT — see LICENSE in the source". Phone `FaqScreen.kt:391`, same words.
  Neither links to the notices. The desktop installer does carry the
  notices file (`tauri.conf.json:108-109`). The phone APK carries only
  `assets/wakeword/LICENSE.txt` and `assets/turn/LICENSE.txt`.
- **The phone APK also strips licence copies:** `packaging.resources.excludes
  += "/META-INF/{AL2.0,LGPL2.1}"` (app/build.gradle.kts:197). That is a
  common template line, but it means nothing in the APK carries the Apache text.

### What a complete notices file must contain

**Desktop (THIRD-PARTY-NOTICES.txt, shipped in the installer)**

1. What is there now: the crate list and the hand-written sections (browser-use, openWakeWord, Smart Turn, AgentDojo, Graphiti and the rest).
2. **Add** the crates now in the Windows graph but not listed. I compared `cargo metadata --filter-platform x86_64-pc-windows-msvc` with the list: cpal 0.15.3, dasp_sample 0.11.0, hound 3.5.1, tauri-plugin-updater 2.11.0, minisign-verify 0.2.5, reqwest 0.13.5, windows/windows-core 0.54.0. Also tempfile and jobserver, which may be build-only. **Remove** window-vibrancy 0.5.3, which is gone. The quickest way is `npm run notices` (package.json:23).
3. **Add** the fonts: Chakra Petch (The Chakra Petch Project Authors) and IBM Plex Sans/Mono (IBM Corp.), SIL OFL 1.1, with the OFL text or a pointer to the shipped `src/fonts/OFL.txt`.
4. **Add** the full licence TEXTS, not only their names. MIT, BSD and ISC say the copyright notice and the permission text must go with every copy. Apache-2.0 §4(a) asks for a copy of the licence, and a URL is the weak reading of that. `cargo about` can generate names, copyright lines and texts in one file.
5. **Add** bge-small-en-v1.5 (fastembed's model) under the backend models, next to the voice models.

**Phone (new: an asset file such as `assets/licenses/NOTICES.txt` plus a "Third-party notices" row in About)**

1. Jarvis itself: MIT.
2. AndroidX (core, activity, lifecycle, compose ui, graphics, material3, foundation, glance, glance-appwidget, biometric, fragment): Apache-2.0, "Copyright The Android Open Source Project", licence text.
3. Kotlin standard library, kotlinx-coroutines, kotlinx-serialization: Apache-2.0, JetBrains.
4. OkHttp 4.12.0 and Okio 3.6.0: Apache-2.0, Square, Inc.
5. ONNX Runtime 1.22.0: MIT, Microsoft. Its own ThirdPartyNotices cover the parts it bundles. I did not open the AAR to list them.
6. openWakeWord v0.5.1 models (melspectrogram, embedding_model, hey_jarvis_v0.1): David Scripka, **CC BY-NC-SA 4.0**, link to the licence, "unmodified", NON-COMMERCIAL. The embedding model derives from Google's speech_embedding (Apache-2.0).
7. stop_head.bin: Jarvis's own model on openWakeWord embeddings, CC BY-NC-SA 4.0. Its training voices: LibriTTS-R (CC BY 4.0, Koizumi et al., 2023) and Kokoro v0.19 (Apache-2.0).
8. Smart Turn v3.2: Daily, BSD-2-Clause, full text (already in `assets/turn/LICENSE.txt`, so point to it).
9. Code ideas re-implemented in the phone: stream2sentence word list (MIT, Kolja Beigel), Pipecat's Whisper features (BSD-2, Daily), itself from Hugging Face transformers (Apache-2.0).

**Both About boxes:** "Jarvis: MIT. Built with third-party parts under their own licences, including non-commercial wake-word models." Then a link or button to the notices.

### Security advisories

- **Rust, `cargo audit`** (installed into the scratchpad, advisory DB fetched
  today): `1 vulnerability found`: **RUSTSEC-2026-0285, rustls 0.23.44**,
  "TLS 1.3 handshake messages incorrectly accepted across encryption level
  boundaries", 5.3 medium, fixed in 0.23.45. Plus the 7 unmaintained or
  unsound warnings already listed in `deny.toml:28-36`.
  Is it in the app? `cargo tree -i rustls --target all` prints "nothing to
  print", meaning no feature path builds it, and CI's `cargo deny` job passes
  (run 36210892916, job `audit`). `cargo audit` reads every line of
  Cargo.lock and so counts it anyway. So it is most likely NOT in the shipped
  program. `cargo update -p rustls` removes the warning either way. Note that
  `cargo metadata` does include rustls and ring, and that is why the notices
  list them. The Cargo.toml comment (:51-56) says rustls was avoided on purpose.
- **npm, `npm audit --package-lock-only`**, on a copy of the lockfile: "found 0 vulnerabilities".
- **Python:** pip-audit is not installed. I read PyPI's own `vulnerabilities`
  field for the newest release of each package instead: 0 for all of them.
  Because requirements.txt pins nothing, that is also what a new install gets.
  An older install on your PC was not checked.
- **Android / Maven:** not run (OSV and Google Maven are blocked from here).

### Test map

| Suite | Count | What runs it | Time |
|---|---|---|---|
| Backend `backend/test_*.py` | 115 files. CI: 95 passed, 19 skipped (need your PC's files). Locally today: 96 passed, 0 failed, 19 skipped. | `run_suites.py` in ci.yml `backend` job. Also apply-patches.ps1 on your PC, unless `-SkipTests` (apply-patches.ps1:1473) | ~3 min CI. Slowest locally: auto_learn 47 s, web_search 36 s, browser_control_live 33 s, suite_state 16 s |
| Parity check | 1 | ci.yml `backend` | <1 s |
| Desktop `jarvis-desktop/tests/*.mjs` | 71 suites (+ uikit harness, shots) | ci.yml `frontend`: all 71. `npm run test:all`: 36. | 19.6 min in CI |
| Desktop markdown + tokens + `node --check` | 3 steps | ci.yml `frontend` | seconds |
| Rust `#[test]` | 318 (80 in commands.rs; lock/rules.rs 15) | ci.yml `rust` on Windows (`cargo test`) | ~3 min with cache |
| Credential Manager live test | 1 | ci.yml `credential-manager` (Windows) | 3 s |
| PowerShell 5.1 parse + apply-patches run | 3 steps | ci.yml `powershell-5` | ~30 s |
| Phone JVM (`app/src/test`) | 77 files | jarvis-client.yml `build` (`testDebugUnitTest`), only on jarvis-client changes | part of ~14.5 min |
| Phone emulator (`app/src/androidTest`) | 6 classes: Launch, EventStreamContract, TokenStore, ApiContract, FaceRender in `smoke`; FaceShot in `face-shots` (may fail) | jarvis-client.yml:533, 1174 | 35 min limit |
| Release APK start on emulator | 1 gate | jarvis-client.yml smoke, before publishing | - |

**What runs where:** CI (ci.yml) runs on every branch push and every PR.
The phone workflow runs only when `jarvis-client/**`, `keystore/**` or its
own file changes, on any branch. The desktop release runs for `main` and
`claude/**` when `jarvis-desktop/**` changes. The old phone app's workflow
runs for `jarvis-android/**`. verify-toolchain runs only when its own file
changes, or by hand.

### Important behaviour with no behaviour test (the five rules and approvals)

- **Rule 4, desktop:** the stale-stream block and the other approval
  refusals in `answer_approval`. Text match only (B-1).
- **Rule 4, phone:** `decisionBlocker`. No test calls it (B-2).
- **Approval gap step 1:** "approved written straight into approvals.db is
  refused". Tested end to end only on your PC (B-3). The stamp logic itself
  is unit-tested in test_owner_check.py:172 onward.
- **Phone fingerprint before a risky approval:** no test (B-4).
- Covered well, for contrast: `X-Jarvis-Client: hud` on phone requests
  (ApiContractTest.kt:119, 267, 516), which approvals are risky (shared
  fixture used by backend, Rust and phone), the approval row shape
  (test_approval_contract.py fixture), and the Credential Manager token
  store (live on Windows).

### Python packages pinned with hashes (I111, first half - done 2026-09-26, install switch NOT made)

**Done.**
- `backend/requirements.lock`: every package in `requirements.txt` and
  everything they pull in, at one exact version, each with the sha256 of
  every file PyPI has for it. Windows and Linux, Python 3.10 and newer
  (numpy and onnxruntime get a different version per Python version - the
  lock says which). Made with `uv pip compile --universal --generate-hashes
  --exclude-newer 2026-09-19` - the 7-day wait: no release younger than a
  week. The hashes came from uv, never typed. The command is at the top of
  the file.
- `sherpa-onnx-core` is now named in `requirements.txt`. sherpa-onnx's
  Windows and Linux files need it, but not every sherpa-onnx file says so,
  and the first lock left it out - found when the lock was tried for
  Windows, not guessed.
- Checked here: uv installed the lock, hash-checked, for Windows (Python
  3.12 and 3.13) and Linux (3.12); real pip installed it in hash-checking
  mode on Linux (Python 3.11), every package imported, and `pip check`
  found no conflict. NOT checked: a real install on Windows (there is no
  Windows here).
- `tools/check_python_advisories.py` and CI job `python-advisories` (next to
  `cargo deny`): the lock pins everything with a hash, and no pinned
  release, on any platform the lock covers, has an advisory in PyPI's own
  database (the one pip-audit reads). Today: 52 pinned lines, 0 advisories.
  `pip-audit` itself was not used: it only checks the lines that match the
  machine it runs on, so the Windows-only packages would be skipped.
- `backend/test_shipped_modules.py` checks the lock offline on every run.

**Not done, on purpose: `apply-patches.ps1` still installs from
`requirements.txt`, unpinned.** Installing the lock changes packages that
are already on your PC to the locked versions, and some of them are shared
with things this repository does not install. One clash is certain if you
have the better voice (f5-tts): it uses `transformers`, whose 4.x versions
need `huggingface-hub` below 1.0 and `tokenizers` at most 0.23.0
(PyPI metadata for transformers 4.57.1), while the lock pins
huggingface-hub 1.32.0 and tokenizers 0.23.2 (for fastembed). Your PC's
installed versions were not checked from here, so switching blind could
break the better voice.

**The plan, in order:**
1. You run one line on the PC that installs NOTHING (the second half
   downloads to pip's cache to work out what would change) and send
   back the two files it writes:
   `py -3 -m pip freeze > "$env:USERPROFILE\Desktop\jarvis-pip-freeze.txt"; py -3 -m pip install --dry-run --require-hashes -r backend\requirements.lock > "$env:USERPROFILE\Desktop\jarvis-lock-dry-run.txt" 2>&1; Write-Host "Two files are on your Desktop: jarvis-pip-freeze.txt and jarvis-lock-dry-run.txt"`
   (run it from the folder this repository is cloned into).
2. From that: either the lock can be installed as it is, or the backend
   gets its own Python environment (a "venv", a private copy of Python's
   package folder just for Jarvis) so its pins cannot touch f5-tts's.
3. Then `apply-patches.ps1` installs with
   `pip install --require-hashes -r backend\requirements.lock`, and says in
   plain words what changed.
4. Once a month (or when a package is added): make the lock again with the
   command at its top, and let CI's advisory check pass. Pins that are never
   updated rot the other way - stuck on old, vulnerable versions.

CI's own backend job still installs its four packages (numpy, sherpa-onnx,
onnxruntime, cryptography) unpinned: installing the whole lock there would
also bring fastembed and change which memory tests run, which needs its own
CI round trip to check.

## Could not check

- **AndroidX, Compose BOM and AGP latest versions:** Google Maven redirects to `dl.google.com`, which is blocked here (CLAUDE.md says the same).
- **Advisories for Maven/Android libraries and for the actions:** OSV (`api.osv.dev`) and rustsec.org do not answer from here. The Rust check used the advisory DB through git instead.
- **Per-suite times for the desktop tests in CI:** the log download host is blocked, and Chromium is not installed here to run them locally. The 19.6 min is the step total.
- **Rust `cargo test`:** needs Windows. Not run here. CI ran it green (run 36210892916).
- **Model licences marked "from memory"** (qwen3, bge-small) and the three the notices themselves mark unchecked (TitaNet-Large, ZipVoice, the Emilia terms). Hugging Face is not reachable from here.
- **Which crates in the notices diff are build-only** (tempfile, jobserver): `cargo-license` is not installed, so I compared with `cargo metadata` instead.
- **Your PC's time zone:** it decides whether B-6 fails there today.
- **Licences of the GitHub actions:** not checked, and not needed, because they are not shipped.
- `jarvis-android/` (the old app) was out of scope and was not audited.
