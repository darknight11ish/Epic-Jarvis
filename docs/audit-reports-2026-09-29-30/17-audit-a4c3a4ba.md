# Report 17 (audit), agent a4c3a4ba, 2026-09-29T21:09Z

> **What it was asked** (first 600 characters of the task): Bug-hunt the "Look at this" / "Watch with me" SCREEN feature merged in PR #34. `main` is checked out read-only at /tmp/main34 (compare `git -C /tmp/main34 diff 7df0be91 0fdd81be`, ignore docs/SOURCE-BUNDLE.md). Files: backend/jarvis_screen.py, jarvis_screen_win.py, jarvis_screen_picture.py, jarvis_secrets.py, jarvis_secret_rules.py, screen.patch, screen-picture.patch, jarvis_agent.py screen hooks, desktop src-tauri/src/look.rs, src/look-rules.js, look-settings.js, watch-badge.*, phone screen code, tools/check_screen_safety.py. Rules to test against (CLAUDE.md 'Jarvis may look at the owner's sc

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

SCREEN FEATURE (PR #34) BUG HUNT. No files changed. Windows-only code (`jarvis_screen_win.py`, `look.rs`, the Android service) was read, not run.

Backend tests all pass on main: test_screen 184, test_screen_clean 78, test_screen_masks 59, test_screen_turn 98, test_screen_win 28, test_screen_picture 305, test_secrets 63, test_secret_rules 35. `node tests/look-rules.mjs` passes 21. `check_parity` is clean. So the bugs below are gaps the tests do not cover.

Every path below is under /tmp/main34.

## Worst first

**1. A phone screenshot that OCR reads no words from, with picture mode ON, is not treated as outside text (medium-high; ran it with a stubbed picture job).**
- `backend/jarvis_screen.py:1116-1133`. The picture-reader description is appended to the model's message at 1129-1133, but `info["read"]` is only set True when words exist (1114).
- `backend/jarvis_agent.py:6293` only calls `watch.took_in(SCREEN_TOOL)` and sets `screen_read` when `read` is true.
- Result: the model gets text derived from the screen, but the turn is not marked "read outside text". Notes and searches do not ask first, cards do not say "after Jarvis read your screen", the chat is not tainted, and read-aloud rules see a normal turn. This breaks "screen content is outside text, never causes action".
- The trigger is exactly where OCR fails but the small picture model can read stylised text. My stub run printed `read flag: False`, and the model saw `PICTURE_READER_SAYS...`.
- The PC's own look path is fine, because `model_part` always returns a part.
- Fix: set `info["read"]=True` whenever anything is added, including `extra` and `SCREEN_TEXT_NONE`.

**2. Mastercard 2-series card numbers are not hidden (medium; ran it).**
- `backend/jarvis_secrets.py:211-213`. `_CARD` only starts with 4, 51-55, 6, 1x or 3. It has no 2221-2720 range, and no Maestro 56-58.
- `2221 0000 0000 0009` passes Luhn and comes back as `'Card number 2221 0000 0000 0009'`, hidden=0. Visa, Discover and UnionPay were hidden.
- These numbers reach the model, and stay unpainted in the picture sent to picture mode.
- Fix: add `2(?:2[2-9]\d|[3-6]\d\d|7[01]\d|720)` and `5[6-8]\d{2}`.

**3. Passwords and codes that are plain but not hidden (medium-low; ran it).**
- `backend/jarvis_secrets.py:355-377`, the "labelled password" pattern:
  - Label and value on separate OCR lines: `['Password:', 'hunter2']` is not hidden. The second, line-joined pass only keeps matches that cross lines, and this pattern's span is only the value.
  - Passphrases: `Password: correct horse battery staple` becomes `Password: [hidden] horse battery staple`, because the value is `[^\s]{3,64}`.
  - Not matched at all: `PIN 4821`, `Your password is hunter22`, `CVV: 123`.
  - One-time codes: `Your verification code is 482913` is not hidden. Phone notifications redact these, but the screen path does not reuse that redactor.
- Fix: allow the value on the next line, and add "code"/"cvv"/"otp" labels.

**4. Stop and status freeze while the once-a-second check is reading Windows (medium; ran with a slow stub).**
- `backend/jarvis_screen.py:1289-1301`. `tick()` calls `self._snapshot()` (UI Automation and browser address-box reads) while holding `self._lock`.
- `stop()` (1254), `status()` (1520), `stop_everything()` (1544), `extend()` and `ask()` all take that same lock.
- With a 3 s snapshot, `stop()` waited 3.0 s and `status()` waited 3.0 s.
- A hung or frozen app can stall UI Automation for much longer. The badge's Stop button and Stop everything would then hang, against "Stop still works".
- Fix: take the snapshot outside the lock and apply the result under it.

**5. Any paired device can read the PC's held look (low-medium; ran it).**
- `jarvis_screen.py:1118-1121` and `jarvis_agent.py:4534`. Looks are limited to this PC (`LOCAL_DOS`, `is_local`), but at read time `with_screen(mark="look")` never checks who is asking.
- A chat request from the phone with `screen:"look"` gets the PC's held words. My run printed `True True` for read and "banana" present.
- It also consumes a Watch-mode look meant for the desktop question.
- The phone app does not send this mark today; a compromised or odd client could.
- Fix: honour the "look" mark only for local requests.

**6. The black-out mask cannot see Store (UWP) apps' real program names (low-medium; read).**
- `jarvis_screen_win.py:561-583` (`_exe_of_hwnd`, used by `_list_windows` at 641) does not unwrap `ApplicationFrameHost.exe`.
- `jarvis_front.py:149-165` does unwrap it, for the front-window pause check.
- A Store app on the owner's Never look at list, sitting beside or over the picture, is not painted black.
- Related: `must_hide` returns False when the exe is unknown (`jarvis_screen_win.py:196-197`). The pause check fails closed in the same case, so the two disagree.
- Fix: reuse the unwrap in `_exe_of_hwnd`; treat an unknown exe as hide.

**7. A held look is not dropped after two minutes (low; read).**
- `jarvis_screen.py:1448-1475` and `1477`. Expiry is checked only when someone asks or when `follow_up` is called. No timer runs.
- The Glance with the screen's words stays in RAM until the next access, the bar closing, or Stop.
- `status()["look_held"]` stays true, so the desktop strip keeps saying "Jarvis is holding what it read".
- An expired look is never sent to the model (the age check works), so this is memory and display only. It still contradicts "held for two minutes, then dropped".

**8. Session timing uses the wall clock (low; read).**
- `jarvis_screen.py:1164` and `1293-1296` use `time.time`. A clock set back by an hour lengthens a session past the 2-hour maximum, and the "PC slept" check ignores a backward jump.
- The phone side correctly uses `nanoTime`. Fix: use `time.monotonic`.

**9. Phone password-field name check misses underscore IDs (low; read).**
- `jarvis-client/.../net/ScreenText.kt`, `WORDY = (?i)(...\bcvv2?\b|\bpin\b|one[- ]time)`. Java's `\b` counts `_` as a word character, so `pin_code`, `card_cvv` and `one_time_code` do not match.
- The input-type and autofill checks still catch properly marked fields.

**10. A bare "Hey Jarvis" takes a look with no voice check (low; read).**
- `jarvis-desktop/src-tauri/src/voice.rs:2280`. `ask_blocking` runs on `wake_heard`, which is before the "is it the owner" check.
- With Watch on, anyone or anything saying the wake word makes the PC read the screen's words into memory. Nothing leaves the PC, and a later marked question could pick it up.

**11. Phone: the owner's own attached photo is mislabelled as a screenshot (low; Kotlin read, not run).**
- `net/ChatSession.kt:505` (`sentPicture = picture ?: look?.picture`). With Watch running and a held Watch picture, `screen.pictureIsScreen` is still true.
- The owner's photo is then sent with `screen:"phone"`. The PC reads only its words and keeps it off the vision model. The real screenshot is discarded.
- The owner sees a wrong or "words only" answer.

**12. The Never look at list stays "broken" until restart (low; read).**
- `jarvis_screen.py:367-388`. `load()` runs only at start and after a failed save.
- One transient read error (an antivirus lock, for example) means every look is refused and the list cannot be edited until Jarvis restarts.
- This fails in the safe direction but is a usability trap.

**13. `screen_mark` is defined twice (latent; read).**
- `jarvis_screen.py:1012` takes messages; `:1620` takes a status and silently replaces it.
- No caller uses either today (the agent has its own `_screen_mark_of`), but anyone calling `jarvis_screen.screen_mark(messages)` gets "".

## Risks I could not prove here (need the owner's PC or phone)
- **Browser password boxes:** whether Chrome or Firefox reports `IsPassword` on the first UI Automation query, before accessibility switches on, is not confirmed. Elsewhere `_password_focused` treats a plain False as "not a password", so an early miss would let a look through. The code header lists this as unverified.
- **Private-window detection:** it relies on the title saying InPrivate, Incognito or Private Browsing. I could not confirm that Chrome's window title carries "(Incognito)".
- **Android 14 sign:** the watch notification is `setOngoing`, but Android 14 lets users swipe away foreground-service notifications. Sharing could continue with no sign. Only checked at start (`signVisible`), not re-checked while it runs.
- **Stale frame:** the phone sends the newest frame Android delivered. It never checks the frame's timestamp against the app-switch time, so a just-left blocked app could in theory appear.

## Checked and fine
- **Storage and network:** no picture or word is written to disk (only in-memory PNG and bytes). Picture mode talks only to 127.0.0.1 on its own port, CPU only, `OLLAMA_NO_CLOUD=1`. Cloud routing is blocked by `has_screen` in the patched router call.
- **Learning and history:** the learner (`owner_turns`) and the chat log ignore `screen_text` and list content. `with_screen` copies messages, so screen words never reach history or learning.
- **Events and audit:** events carry only fixed status words.
- **Looks:** `look`, `start`, `ask` and `extend` are refused unless the request is from this PC. The desktop app refuses a non-loopback base and holds looks on a stale link or under App lock.

Files: /tmp/main34/backend/jarvis_screen.py, jarvis_secrets.py, jarvis_screen_win.py, jarvis_agent.py, jarvis_front.py; /tmp/main34/jarvis-desktop/src-tauri/src/look.rs, voice.rs; /tmp/main34/jarvis-client/app/src/main/java/com/jarvis/client/net/ScreenText.kt, ChatSession.kt.
