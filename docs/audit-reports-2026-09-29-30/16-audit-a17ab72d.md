# Report 16 (audit), agent a17ab72d, 2026-09-29T21:09Z

> **What it was asked** (first 600 characters of the task): Run the standing three-part audit (bugs, both apps, fit with existing features) on the features PR #34 brought into main: screen 'Look at this'/'Watch with me', chat-picture cleaning, Kokoro v1.0 voices with Hear-it samples, custom voices, secret rules. `main` is at /tmp/main34, read-only (`git -C /tmp/main34 diff 7df0be91 0fdd81be`, ignore docs/SOURCE-BUNDLE.md). Also cover PR #33's phone changes (encrypted CapturedNotifications.kt, EventStream buffer, HomeScreen long-press, Sky.kt wording). Check: desktop AND phone parity (tools/check_parity.py, ARCHITECTURE section 8), same approval model a

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

AUDIT OF PR #34 (screen looks, chat-picture cleaning, Kokoro voices / blends, secret rules) AND PR #33's phone changes. `main` at /tmp/main34, nothing changed in the repo.

BOTTOM LINE
- No blocking bug found. Backend tests, generator checks, parity and the Rust check are all green.
- There is one real fit gap (the "What asks first" page), a few small bugs worth fixing, and a few things I could only read, not run.
- Nothing here needs an owner decision. Two items are the owner's call (see the end).

WHAT I RAN (venv python, from /tmp/main34/backend; the tests are plain scripts, not pytest)
- All passed, 0 failed, for: test_screen 184, test_screen_clean 78, test_screen_masks 59, test_screen_picture 305, test_screen_turn 98, test_screen_win 28, test_chat_picture 125, test_kokoro 159, test_blend_voices 104, test_mouth 92, test_ocr_words 35, test_picture_text 50, test_secrets 63, test_secret_rules 35, test_reach 134, test_asks_first 174, test_card_words 110, test_gate_risk_words 15, test_settings_registry 59, test_voices 140, test_shipped_modules 479, test_patch_history 24, test_gate_stack_clean, test_photo_remind 148, test_devices 253, test_second_card 316, test_selftest_preflight 137, test_standby_schedule 73, test_tellme 216.
- Generator `--check` modes: gen_screen_cases, gen_phone_voice_cases, gen_voice_training_cases, gen_reach_cases, gen_asks_first_cases and gen_card_words_cases all match. `gen_secret_rules.py --url --check` says "up to date". The plain `--check` needs `--from` or `--url` and errors if you give neither.
- `tools/check_parity.py`: "No undecided drift". `tools/shader_size.py --check`: all animals under the limit (monkey 59,602, otter 55,018).
- Rust: `cargo check --target x86_64-pc-windows-msvc --all-targets` finished clean. I did not run clippy or fmt.
- Desktop JS: `look-rules.mjs` passes 21/21 and `sky.mjs` passes. `look.mjs`, `custom-voices.mjs`, `hotkeys.mjs`, `uikit.mjs` and `animal-options.mjs` need Playwright, which is not installed here, so they did NOT run.

ONLY READ, NOT RUN
- All Kotlin: the phone's screen looks, LookGate, ScreenWatchService, CapturedNotifications, EventStream and HomeScreen. Only CI can compile it.
- `check_screen_safety.py` and the Windows readers (they need Windows).
- Playwright tests for the desktop windows.

PART 1: BUGS (worst first; all verified against source)
1. Fail-open in `with_screen` (low severity, contrived trigger). `backend/jarvis_screen.py:1134-1135`, and the same catch-all in `jarvis_agent.with_screen`.
   - If anything inside `with_screen` throws, it returns the ORIGINAL messages. A phone `screen_text` part then goes on raw: unhidden, not labelled outside text, and with `read: False`, so no "read the screen" taint is recorded.
   - I reproduced it with a part whose `.get("text")` raises. The output still contained `{'type':'screen_text','text':'secret'}`. Ordinary inputs are all caught earlier (`_hide_or_fail`, `clean_picture`), so I could not trigger it with real data.
   - The rest of the screen-safety design fails closed. Fix: in that except branch, drop `screen_text` parts and image parts instead of returning them.
2. Secret check is slow on long unbroken text. `backend/jarvis_secrets.py`, `_gitleaks_spans`. I measured it:
   - 20,000 unbroken characters (like "aaaa…", a long hex or base64 blob, a long URL) took about 7 s. 10,000 took 3.7 s.
   - At 80,000 characters, "a.a.a." took 11.8 s and then failed with "took too long".
   - Normal prose of 80k took 0.66 s.
   - It fails closed (nothing is handed on), so this is a latency problem, not a leak.
   - Effect: "Look at this" on a screen full of a base64 or minified blob can stall for several seconds. A phone that posts a huge `screen_text` makes the PC spend 10 s or more on one request.
   - `check()` also cannot really cancel the thread on timeout. Python's `re` never lets go of the interpreter lock during one long match, and the daemon thread keeps running.
   - Suggestion: cap or chunk very long unbroken runs before scanning (treat them as "unchecked").
3. Captured notifications can be overwritten after a failed decrypt. `CapturedNotifications.kt`, `load()` and `add()`.
   - If the encrypted blob cannot be opened, `load()` returns an empty list. The comment says "keep the blob where it is".
   - The next `add()` then calls `save(added(load()))`, which overwrites the old blob with just the new row.
   - Outcome: old captured notifications are lost. That is not a privacy leak (it errs toward losing data), but the comment is wrong.
   - The store's `init` may also run Keystore work on the main thread, because `remember { CapturedNotifications(context) }` is in `PhoneNotificationsPlate.kt:315`. This is minor.
   - The encryption itself looks right: AES-GCM, an IV generated by the Keystore, a check for a too-short blob, and the plain-text copy is removed on save, on failed encryption and on `clear()`.
4. EventStream buffer (`.buffer(Channel.UNLIMITED)`) is correct and fixes the dropped-approval bug. The trade-off is that memory is unbounded if the collector stalls for a long time. Acceptable; not a bug.
5. HomeScreen long-press: `CritterPose.awake` is `internal` in the same module and `state.faceOffline` exists, so it should compile. It matches the "no petting during approval, error, standby or offline" rule.
6. Sky.kt and `sky.js` wording ("rises …, then sets …") is identical in both apps and sorted by time. Both golden files were updated.

PART 2: BOTH APPS: PASS, with items to know
- `check_parity.py` is clean. §8 has the "One-sided on purpose" row for "Look at this": the Never look at list is per device, and the keys and badge are PC-only. The routes are classified: `/api/screen` ported, `/api/screen/picture` ported, `/api/screen/never-look` deliberate.
- Picture mode: the desktop has it in Settings (`look-settings.js`) and the phone in `ScreenPicturePlate.kt`.
- The chat-picture line "Secrets in pictures you attach are covered…" is word for word in the backend, the desktop chip and the phone's `ChatPicture.SECRETS_COVERED`. `test_chat_picture` checks all three.
- The phone can stop the PC's watch from anywhere, and cannot start or look. The PC enforces this with `is_local()`, refusing from any non-PC address. That matches the owner's rule.
- Rule 4: the desktop holds Look and Watch on a stale link and under App lock (`look.rs` `held()`). Stop is never held.
- Small note: the old "Attach a screen capture" key (`capture_screen`, Alt+Shift+S) now means "Look at this". It keeps the same id and key, so anyone who bound it will silently get the new behaviour. It is written in the code comment and CHANGELOG.

PART 3: FIT
1. FIT GAP (the most real finding). The "What asks first" page does not list "Look at this" or "Watch with me". `backend/jarvis_asks_first.py` GROUPS/FIXED has no row for them.
   - The owner said the page lists every action. Live and "Solve it here" got fixed rows saying "no card, your own tap" (`fixed:live`, `fixed:handoff`).
   - Screen looks are also "no card, only the owner's own act, with a sign on screen". They need the same kind of `fixed:screen` row.
   - Removing an entry from the Never look at list raises a `change_own_config` card. It falls under the generic "own settings" row, but is not named.
   - The tests still pass because no gate action is missing. Fix: add the row, then re-run `tools/gen_asks_first_cases.py`.
2. Picture mode (`screen_picture_enable`) is wired everywhere: HARD_LIMITS, MUST_ASK, the GROUPS "AI models and graphics cards", card title, the What-Jarvis-can-reach row, the gate `_RISK` line (`screen-picture.patch`), and JARVIS-API §96.1. The registry second door is `set_screen_picture`, in section "screen-look", and it calls the same card. It is off by default, ON is one card, OFF is instant, and the model comes from a pasted line. The copy of Ollama it starts is locked down: 127.0.0.1, `CUDA_VISIBLE_DEVICES=-1`, `OLLAMA_NO_CLOUD=1`, and a cloud model name is refused.
3. The Never look at list has no voice or chat second door (add or remove). Adding is stricter, so it could be instant. It is a small, optional gap; the list is on the PC only by design.
4. THIRD-PARTY-NOTICES:
   - gitleaks and Presidio are credited, each with its full MIT text. winrt/pywinrt is credited too, and `requirements.lock` is updated.
   - MiniCPM-V 4.6 is written as "reported as Apache-2.0 (the licence was not re-checked)". CLAUDE.md and JARVIS-API §96.1 state Apache-2.0 flatly.
   - Its model tag, size and the checksum pin are also unverified: the pin is the first measurement unless `PINNED_DIGEST` is set. Verify the licence and digest before switching it on for real.
   - "Ashby" and "Clara" are in the Sherpa credit block as averages of Kokoro's own voice tables, and no new voice data ships. Fine.
5. Docs: JARVIS-API adds §62.6-62.13 (including chat-picture cleaning and screen safety), §94.7 and §96/96.1. ARCHITECTURE section 3, the §8 row and the "Still missing" block are updated. The CLAUDE.md decisions are recorded. The screen safety wording is honest about what it cannot catch (a show-password eye, QR codes, tiny text) and that nothing has run on Windows yet.
6. Rules 1-4: screen text and the phone's screenshots are labelled outside text and never learned. Chat history only reads `type == "text"` parts, so `screen_text` words are not kept. A screen turn is pinned to this PC (`has_screen` in the router). The `screen` field is stripped before any model. Secret redaction fails closed everywhere I checked. Live's camera stays off, and any picture that reaches `/api/chat` goes through the cleaner anyway.

OWNER'S CALL
- Whether to add a "What asks first" row for Look at this and Watch with me (recommended: yes, same shape as the Live row).
- Whether to verify MiniCPM-V 4.6's licence and digest before its download line is used. The other fixes above (fail-open branch, long-text slowness, comment on the encrypted store) are mine to make when you say so.
