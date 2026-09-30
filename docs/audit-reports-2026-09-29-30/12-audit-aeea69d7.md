# Report 12 (audit), agent aeea69d7, 2026-09-29T20:47Z

> **What it was asked** (first 600 characters of the task): Run the owner's standing three-part audit (bugs, both apps, fit with existing features) on PR #35, checked out read-only at /tmp/pr35 (diff via `git -C /tmp/pr35 diff origin/main...HEAD`; ignore docs/SOURCE-BUNDLE.md). Feature: the Headless browser (Obscura) engine choice - Settings 'Headless browser' (Automatic / Always visible / Headless) on the desktop and phone, the backend browser tool choosing per task, one approval card to switch on, instant off. Check parity (tools/check_parity.py, docs/ARCHITECTURE.md section 8 'One-sided on purpose'), the same permission model and approval-card wordi

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Audit of PR #35 (Headless browser / Obscura engine choice). I read the diff at /tmp/pr35 and ran the tests. One real bug, one docs gap, and the rest passes.

**1. Bugs: one real finding, and it is a broken promise in the words.**

- **The "Always the visible browser" setting can be overridden (worst finding).**
  - Where: `backend/jarvis_browser_engine.py:580-599`. `_choose()` handles the model's own `mode: "headless"` argument before it looks at the owner's saved mode.
  - Failing case: with the switch on and the mode set to "visible", `choose("headless", goal="read the news", requests=[navigate example.com])` returns `{'engine': 'headless', 'why': 'headless was asked for', 'refused': ''}`. I ran this.
  - Why it matters: both apps say the opposite. The desktop mode label is "Always the visible browser", with help text "Jarvis always opens the browser window you can see and take over" (`jarvis-desktop/src/browser-engine-rules.js:27,32`). The phone shows the same words.
  - Limits on the damage: the plan card names the engine on its first line, and every step still asks. So the harm is a false promise and a possible steer by injected text, not a bypass of approval.
  - **Owner's call:** either make "Always visible" win over the model's request (my recommendation), or reword the label and help text.
- Nothing else found in the code I read. Not exhaustively checked:
  - `jarvis_obscura.py` in depth (I read `choose()`, the switch/card logic, `describe_on`, the hooks in `jarvis_browser_control.py` and `jarvis_agent.py`, and both apps' UI code).
  - The real Obscura program (nobody has run it; the docs say "not tried for real").
- **Stealth:** it is always on in the headless engine. That reverses the old "driven openly" rule, but the owner's reversal of 2026-09-29 is written in CLAUDE.md and the code comments. It is not a fit problem.

**Tests run:**
- Backend, all passing (I ran each with the venv python as a plain script, not pytest):
  - `test_browser_engine` 434/434
  - `test_obscura` 92/92
  - `test_chatbot` 232/232
  - `test_chatbot_gemini` 26/26
  - `test_chatbot_sites` 290/290
  - `test_handoff` 80/80
  - `test_support_widget` 10/10
  - `test_devices` 253/253
  - `test_screen_picture` 305/305
  - `test_shipped_modules` 485/485
  - `test_asks_first` 174/174
  - `test_card_words` 111/111
  - `test_reach` 134/134
  - `test_settings_registry` 59/59
  - `test_tool_text` 92/92
  - `test_patch_history` 24/24
- `test_agent` has 5 failures, all `tidy_inbox`. It fails the same 5 on a copy of `origin/main`, so it is not caused by this PR.
- Real-browser halves of the chatbot tests were skipped because Playwright is not installed.
- Desktop: `node tests/browser-engine.mjs` 7/7. Rust: `cargo fmt --check` and `cargo clippy --target x86_64-pc-windows-msvc --all-targets -D warnings` are clean. `cargo test` was not run (needs a Windows host).
- Only read, not run: the phone's Kotlin (`BrowserEnginePlate.kt`, `BrowserEngine.kt`, `BrowserEngineTest.kt`, and `JarvisRuntime.kt` / `JarvisApi.kt`). No local Android build, so CI is the compiler. I did not run the full `npm run test:ui` (only the new test).

**2. Both apps: PASS.**
- `python3 tools/check_parity.py` reports "No undecided drift".
- Both apps read and set the same route, `/api/browser/engine`.
  - Desktop: Settings "Headless browser", with `browser_engine.rs`, `browser-engine.js`, `browser-engine-rules.js`, the permission set and the capability entry.
  - Phone: Settings "Headless browser (Obscura)". `SETTINGS_ITEM_INDEX` is renumbered consistently, and `OpenPlace` has the "browser-engine" entry.
- ARCHITECTURE §8 has a paragraph saying the program runs on the PC only and both apps only show and set it.
- Turning it on is held on a stale link on both apps. Off is never held, and it stops the program.
- The phone shows the switch as on while a card waits, so the owner can withdraw it.
- The phone's waiting-card check matches the action name `obscura_enable`.

**3. Fit: PASS with one docs gap.**
- **Permission model:**
  - `obscura_enable` is tier ask and outbound.
  - It is in the "acts only on ask" set, `HARD_LIMITS` and `MUST_ASK`, and in `jarvis-framework.toml`.
  - Browser steps still get the same plan card, and the fence and re-check before each step also apply.
  - The card's first line names the engine.
  - There is never a silent fallback to the other browser.
  - Typed words and web-address text that repeat saved facts are refused before any card.
  - Passwords and keys are refused.
- **Reach page:** the "What asks first" page lists `obscura_enable` under "The internet". The Browser control row is reworded, and the reach, asks-first and card-words fixtures match in both apps.
- **Settings registry:** `headless_browser` is a `BoolSetting` with its own section and phrases, so voice or chat can turn it on. On raises the same card, and off is instant. Choosing the mode is not in the registry (no voice or chat door for it), which fits, since it changes nothing about who is asked.
- **Chatbot driver, support chats and Solve-it-here:** they still use the visible Playwright browser. `jarvis_chatbot_web.py`, `jarvis_support*.py` and `jarvis_handoff.py` never import the engine (only comment and word changes). The tests assert this, and ARCHITECTURE §8 gives the reason.
- **Docs and notices:**
  - JARVIS-API §97 is present.
  - THIRD-PARTY-NOTICES has an Obscura entry (Apache-2.0, not distributed).
  - ARCHITECTURE §4 has a new "way out" row.
  - `apply-patches.ps1`, `_where.py` and the patch history are updated.
- **Docs gap:** `docs/CHATBOT-DRIVER-DESIGN.md` and the comments in the chatbot files now say Jarvis "no longer promises never to hide it". That matches the owner's reversal of 2026-09-29, so I did not count it as a problem.
- Minor: choosing the mode "Headless" or "Automatic" is a looser choice that needs no card. It is defensible because the switch itself already needed a card and every plan still asks.
