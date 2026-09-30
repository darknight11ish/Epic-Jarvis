# Report 54 (outside-suggestion-check), agent a3aa1bf9, 2026-09-30T07:25Z

> **What it was asked** (first 600 characters of the task): Check this outside (Gemini) suggestion against /home/user/Epic-Jarvis (read CLAUDE.md, docs/AUDIT-2026-09-28-REPO-REFS.md, docs/JARVIS-API.md section 86 esp. 86.5 which already REJECTED 'widgets written as code by the model' and a free-form JSON renderer (a previous check this session just re-confirmed it); ARCHITECTURE section 8; grep docs/ and backend/ for each name first). Items: I.1 jesusdmedinac/json-to-compose and I.2 vvsdevs/AndroidDynamicJetpackCompose (server-driven JSON->Compose, 'AI emits JSON tree over WebSocket POST /api/widget/push; no APK rebuild'): compare to the existing fixed

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Verdict: SKIP four of the five; take one idea (fixed "graphics memory" and "speed" widget sources). I checked the repo only. GitHub not reached, so nothing about the five outside projects is checked. That covers their licences, their code, and their claims about themselves.

**Names**
- I grepped the whole repo for json-to-compose, AndroidDynamicJetpackCompose, zebar, decorum, yasb and PyQt. The only hits were two random base64 strings in `jarvis_wakebank.py` and `jarvis_voicebank.py`.
- None of the five is researched in docs/ and none is used in the code.

**I.1 json-to-compose and I.2 AndroidDynamicJetpackCompose: SKIP (borrow nothing)**
- Jarvis already has the safe version of "AI emits JSON, the app draws it": JARVIS-API §86 and `backend/jarvis_widgets.py`. It allows 5 block types (`BLOCK_TYPES`), 11 sources (`SOURCES`: 5 list, 4 number, 2 progress) and 5 button actions (`ACTIONS`). Any other key is refused (`BLOCK_KEYS`, `ALL_KEYS`).
- The suggestion says 8 data sources. The code has 11, so that number is wrong.
- A button's words are fixed, so the model cannot label one. Both apps draw a widget by one shared rule (`tools/gen_widget_cases.py`), and their tests include hostile answers.
- The phone draws these natively in `widget/JarvisBoardWidget.kt`, using Glance.
- §86.5 already rejects model-written widget code. It also rejects a free-form renderer, because no check can prove arbitrary output safe.
- A free-form JSON-to-Compose tree would drop that closed list. The model could then place any button or any data, and outside text in a turn could steer it (rule 1).
- The suggested push path, `POST /api/widget/push` over a WebSocket, does not exist. I found no such route in JARVIS-API. Jarvis has HTTP plus an events stream, and §86.5 says there is no `widgets` event on the bus. A new push path would bypass rule 4's stale-link holds and the App-lock handling.
- "No APK rebuild" is not a benefit here. Blocks and sources are already data, so the owner adds a new kind of block by editing the menu, not the app's drawing code.
- The package name `com.jarvis.client` is right.

**II.1 zebar: SKIP**
- A model-written index.html/JS mounted from `%USERPROFILE%\.glzr\` is a shell tool by another name. A file-write tool would sit outside the gate, and prompt injection could become running code. That contradicts rule 4 and §86.5.
- Zebar's hardware providers (cpu, memory, network, audio and so on) would run outside `jarvis_gate`.
- GPL-3.0: running it as a separate program is not copying or linking. Even so, it would need a THIRD-PARTY-NOTICES entry. It would also be a second widget engine, which is a duplicate.
- Jarvis already has a desktop widget window: `tauri.conf.json` label "widget", url `widget.html`, transparent, always-on-top, skip-taskbar, no shadow. The Brain → Widgets board (§86.4) draws into it with `textContent` only.

**II.2 tauri-plugin-decorum: SKIP (no problem to solve)**
- `Cargo.toml` uses `tauri = "2"` and the plugins global-shortcut, clipboard-manager, notification, store, single-instance, window-state and updater.
- Windows are built with `decorations(false)`, `transparent(true)` and `shadow(false)` in `windows.rs` and `tauri.conf.json`. The HUD is the only window with `decorations(true)`, and it uses Acrylic with a fallback.
- I grepped ARCHITECTURE.md, CLAUDE.md and `windows.rs` for snap layouts, drag regions, z-order and window borders. I found no known issue of that kind. The desktop tests were not searched.
- Revisit only if a real window fault turns up: a broken snap layout, a bad drag region or a border artefact on Windows 11.
- If it were ever adopted, it needs a THIRD-PARTY-NOTICES entry and a Cargo licence check. `cargo-deny` is not checked and I did not look for it. Its MIT licence and its Cargo dependencies are not checked.

**II.3 yasb: SKIP**
- Model-written Python widget classes executed on the desktop are again a shell tool. The suggestion also adds a second GUI toolkit next to Tauri.
- PyQt6's licence (GPL or commercial) is not checked, and I did not look at yasb's own licence. It would be another entry to list, and rule 5 only removes the "can't sell" concern.
- The tray, HUD and widget window already exist. I did not check whether they show GPU/VRAM/token speed.

**Worth keeping: two more fixed sources in `SOURCES`, no code from the model**
- `SOURCES` has no GPU, VRAM or tokens-per-second entry. I did not open `jarvis_second_card` or Brain → Model, so I don't know whether a safe read for them exists to feed a new source.
- If one does, add "graphics memory per lane" as a progress source and "tokens per second" as a number source. Both would be non-private, numbers only.
- It would change `jarvis_widgets.py`, the desktop `widget-board.js`, the phone's `net/JarvisWidgets.kt`, the shared fixture and the docs. Speed figures are unmeasured until the second card is installed.
- The owner would decide: (a) add them now, and label them "not measured" until the card is in (recommended), or (b) wait for the second card.
