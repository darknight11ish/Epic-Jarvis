# Report 47 (audit), agent a9ff4f15, 2026-09-30T07:12Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first, esp. the Screen decisions: 'Look at this', 'Watch with me', screen safety 2026-09-29, picture mode, never-look list, 'nothing saved', outside text; docs/SCREEN-DESIGN.md, JARVIS-API sections 62/96, ARCHITECTURE section 8; verify each claim with file:line + quote; 'not checked' honestly; change no files). AREA: SCREEN SAFETY end to end, built 2026-09-29 and never run on Windows, never re-audited: backend/jarvis_screen.py, jarvis_screen_win.py, jarvis_screen_picture.py (just changed: it now sends the cleaned picture to the Pictures

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

SCREEN SAFETY AUDIT (read-only; nothing edited). Ran test_secrets, test_secret_rules, test_screen_clean, test_screen_masks, test_screen_picture, test_screen_win, test_chat_picture and test_photo_remind: all pass. Nothing here has run on Windows. I also ran two probe scripts of my own (in the scratchpad), and they found the gaps below.

Good news first. I found no path where raw pixels reach a model, log, file or the phone. The cleaner is fail-closed on every exception, OCR failure, size mismatch, PNG bomb (`jarvis_picture.py:96-98`), missing cleaner (`jarvis_screen_picture.py:559-563`), and unreadable window list or Never-look list (`jarvis_screen_win.py:705,714`).

The new Pictures-lane path is sound:
- It sends only `clean()`'s output (`jarvis_screen_picture.py:1261-1274`).
- It posts only to 127.0.0.1 and rejects non-loopback or cloud-named lanes (`:1066`, `:1088`, `:1100`).
- Its text is tidied and marked OUTSIDE TEXT (`:1436`).
- The chat turn is recorded as a `read_screen` tool call (`jarvis_agent.py:6396`).

Findings, most serious first.

1. HIGH: a slow secret scan freezes the whole backend.
- Evidence: 70k characters of dense alphanumeric text took 11-13 s. I ran a 50 ms ticker thread beside it and its longest gap was 5.4 s.
- Cause: Python's `re` holds the GIL, and `_gitleaks_spans` (`jarvis_secrets.py:189-203`) checks the deadline only between rules. `check()`'s `t.join(15)` (`:573-577`) cannot interrupt one long regex.
- Result: it fails closed, but during the stall approval cards and the event stream freeze. The apps can then show a stale link, which under rule 4 blocks acting. A web page with lots of dense text can trigger it.
- The `_LONG_RUN` guard (`:467`) does not help: 1,000-character runs also took 12 s. Total size is the trigger.
- Smallest fix: lower `MAX_SCAN_CHARS` (`:90`) from 80,000 to about 25,000. Ordinary screens are 4,500 characters (0.09 s) and 24k of code took 0.5 s. Best fix: run the scan in a child process with a hard kill.

2. HIGH: secret patterns that miss common real forms (my probes).
- `DB_PASSWORD=HY2rDwOAsAKAc6` is not hidden. `_LABELLED` (`jarvis_secrets.py:360`) starts with `\b` before `pass`, and `_` is a word character. `MY_SECRET:` was caught.
- `Authorization: Bearer <40 random characters>` is not hidden.
- US SSNs (`Social Security Number 123-45-6789`) are not hidden. There is no SSN pattern.
- A one-time code written before its label ("482913 is your verification code") is missed. "Your code is 482913" is missed too, because `_CODE` (`:364`) needs `verification|security|...` before "code".
- `Passwort:`, a form label on the line above its value, and `password hunter2` with no colon are missed.
- Card numbers (spaced or not), JWT, GitHub, Stripe, AWS, Google, Slack, IBAN, connection strings, private-key blocks and `Password: x` were all hidden. Real-shaped OpenAI and Anthropic keys were hidden too.
- Smallest fix: change `\b` to `(?<![A-Za-z0-9])` in `_LABELLED`, and add an SSN pattern, a `Bearer\s+\S{20,}` pattern, and "code is NNNNNN" / "NNNNNN is your ... code".
- Note the limits already documented: passwords behind a show-password eye, non-English labels, and text in images.

3. MEDIUM: a Watch session outlives its visible sign.
- The badge is a window in the desktop app (`watch-badge.js`, `look.rs`). The backend session lives in `jarvis_screen.py` and ends only on Stop, timer (up to 120 minutes, `MAX_MINUTES`), lock or sleep (`tick`, `:1332-1338`).
- If the desktop app quits or crashes, the state stays WATCHING with no sign. Any local program holding the token can still POST `{"do":"ask"}` or `{"do":"look"}`. `is_local` (`:1773`) counts the PC's own Tailscale address as local.
- I found no heartbeat.
- Related, and lower: `look` and `ask` need no owner gesture at the backend, so a local program with the token can capture a (cleaned) screen and read the model's answer. That is the token's normal power. Whether the owner accepts it for the screen is an owner decision.
- Smallest fix: the desktop pings every 10-15 s, and the backend ends WATCHING after about 45 s of silence.

4. MEDIUM: a race between Stop and `ask()`.
- `ask()` (`jarvis_screen.py:1478-1498`) checks the state, takes the look, then stores `self._look = g` without re-checking. Stop pressed in between leaves a look taken after Stop, held for 120 s and used by the next question.
- Smallest fix: re-check `state in (WATCHING, PAUSED)` under the lock before storing, otherwise cancel `g`.

5. MEDIUM: an unreadable program name means "not hidden".
- `must_hide` (`jarvis_screen_win.py:196-197`) returns False when `exe` is empty. `_exe_of_hwnd` returns "" whenever `OpenProcess` is denied. Everything else in that path fails closed.
- Smallest fix: if the exe is unknown, the Never-look list is non-empty and the window is visible in the capture, paint it.

6. LOW: a phone screenshot that could not be checked reads as "no words".
- In `with_screen`, an unchecked phone picture gives `_ocr_words` an empty result. The model then gets `SCREEN_TEXT_NONE` ("could not read any words", `:1136-1137`), not the UNCHECKED line.
- The model may say the screen was empty. Nothing leaks.
- Smallest fix: when `got["unchecked"]` is true, add `SCREEN_TEXT_UNCHECKED`.

7. LOW, "nothing saved".
- I found no disk, log or history path. The audit log carries counts only (`jarvis_screen.py:1427`). The chat log stores only `text` parts.
- The lane's Ollama keeps its last prompt in its cache. I found no way for an unrelated request to read it. Its Windows log content is not checked.
- The only file write is the owner's own `check_screen_safety.py`, which is documented.

8. What `tools/check_screen_safety.py` covers, and what is left for the owner on Windows.
- It checks: which OCR engine is in use, timing, and how many secrets were hidden from one fake picture. It writes a cleaned PNG for the owner to look at. `--screen` lists which windows would be painted black, and writes a whole-monitor picture.
- It does NOT test: the pause conditions (password box focused, protected window, private window); DPI or multi-monitor beyond eyeballing `--screen`; a Never-look window behind the front one, except by eye; UAC or the secure desktop; DRM windows; the Pictures lane; the Watch sign or Stop; or the phone.
- Owner list for Windows: run `--screen` with a listed program behind the front window; focus a password box and press the Look key; open a private browser window and press the Look key; put the picture model on the Pictures card and do a look with it; start Watch, quit the app, and see whether the sign vanishes (finding 3).

Not checked: `LookPlate.kt`, `ScreenText.kt` and `ScreenWatch.kt` beyond `ScreenWatchService.kt`; whether a screen read taints later turns through `jarvis_chat_log`; Windows OCR behaviour (scaling, PowerShell fallback); the accuracy of Chrome's `IsPassword` when accessibility is off (a focused password box could read as False).

Owner decisions:
A. Fix the secret scan freeze (finding 1)?
   - Lower the size limit to 25k now (recommended).
   - Run the scan in a separate process (bigger change).
B. Should `look` and `ask` need a real key press?
   - Keep as is (the token already grants this).
   - End Watch when the desktop app stops pinging (recommended).

Files: /home/user/Epic-Jarvis/backend/jarvis_secrets.py, jarvis_screen.py, jarvis_screen_win.py, jarvis_screen_picture.py, jarvis_picture.py; /home/user/Epic-Jarvis/tools/check_screen_safety.py; /home/user/Epic-Jarvis/jarvis-desktop/src/watch-badge.js.
