# Report 38 (audit), agent ab06c4e8, 2026-09-30T07:02Z

> **What it was asked** (first 600 characters of the task): Read-only spot-check for the owner of /home/user/Epic-Jarvis (read CLAUDE.md first). Another agent is building a coverage map of what was never audited; YOUR job is to actually probe five cross-cutting areas that likely never got a dedicated audit, and report REAL, verified findings (file:line + quote; say 'not checked' honestly; do not run Android or Windows). Areas: (A) ACCESSIBILITY: phone Compose screens (contentDescription on icon buttons, clickable without semantics/role, touch target size < 48dp, text sizes in dp vs sp, colour-only state, TalkBack labels on custom controls like the face

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Spot-check of five areas. I read code and ran nothing. Android and Windows were not run. Fewer real bugs than expected: most of these areas are already handled with visible care.

**Findings, worst first**

1. **App lock can silently switch off if its saved record has one bad value (area C, medium).**
   - `jarvis-desktop/src-tauri/src/lock/rules.rs:186-190`: `parse_stored` does `serde_json::from_value::<Security>(value)...unwrap_or_default()`. The struct has `#[serde(default)]` per field, which handles a missing field. It does not handle a field with an unknown value.
   - Example: a stored `{"appLock": true, "approvals": "biometric"}` fails to parse as a whole. The result is `Security::default()`, which means `app_lock: false` and `private_answers: false`. The likely causes are a downgrade after a newer build stored a new enum value, or a hand edit.
   - `lock.rs:73-80` (`current`) also uses `.ok()...unwrap_or_default()`. If the settings store cannot open (a corrupt file), the lock quietly reads as off.
   - The test at `rules.rs:642` deliberately expects `"never"` to parse to the defaults, which are stricter for `approvals`. The same fallback loosens `app_lock`.
   - Owner sees: App lock and "Hide memory lists" quietly stop asking. No warning.
   - Smallest fix: parse field by field, so a bad field falls back alone. If the raw value has `appLock` or `privateAnswers` true, keep them true (fail closed). Safe to fix without an owner decision.

2. **`backend.log` grows without limit while Jarvis runs (area D, low-medium).**
   - `jarvis-desktop/src-tauri/src/logfile.rs:98-100`: `backend_sinks()` calls `rotate_if_large` only when the backend starts.
   - The child process then holds the file open in append mode for its whole life. The 4 MB cap in the header comment ("rotated by size") only bites at restart.
   - A PC left on for weeks, with a chatty backend or a restart loop, has no cap. Scrubbing exists (`log-scrub.patch`), but size does not.
   - Smallest fix: re-check the size on the watchdog tick and restart the sink, or start with a tail-truncate. Safe to fix.

3. **Backup retention sorts by file name, which is a timestamp (area E/D, low).**
   - `jarvis_backup.py:594-602`: `_retain` sorts by name and deletes `rows[KEEP:]`.
   - If the PC clock was wrong once (jumped forward), a bogus future-named backup sits at the top. It survives, and one real backup is deleted for each bogus one. With 5 or more bogus files, every real backup would be deleted.
   - This is rare. Fix: keep by newest modified time, or never delete the newest real one. Safe to fix.

4. **Wall clock used for short security timers (area E, low).**
   - `time.time()` is used for pending expiries: `jarvis_speech.py:854, 876, 903` (wake-word prompt), `jarvis_voice_enroll.py:658, 725`, `jarvis_voices.py:3029`, and the Undo window `jarvis_forget_range.py:190-194, 843` (`until: now + UNDO_SECONDS`).
   - A clock set backwards, or a DST-style correction, stretches these windows. Sleep and resume shortens them, which is the safe direction.
   - Impact is limited. The 10-minute Undo is not a loosening of an approval, and the prompts still need a person's tap.
   - Fix: use `time.monotonic()` for in-memory windows. The 147 existing uses of `monotonic` in the backend show the pattern is already in use. Safe, but not urgent.

5. **Widget and floating-face preferences are written non-atomically (area C, cosmetic).**
   - `windows.rs:813` and `windows.rs:1097` use `std::fs::write`, and `jarvis_speech.py:710` uses `write_text`.
   - A crash mid-write loses the preference and it resets to the default. I checked the wake file: a broken file falls back to `_cfg("wake_word_enabled", False)`, so it fails to the safe side.
   - Owner call, minor: leave as is.

**Checked and fine, so nobody re-audits these**

- **`jarvis_second_card.py:1044-1058` (area C).**
  - A missing or broken state file means everything off and "suggest" on.
  - Its docstring explains why those two defaults are opposite.
  - `_write_state` writes to a temp file first.
- **Logging (area B).**
  - `logfile.rs:32` says plainly that the desktop log has no redaction pass and never receives tokens, approval text, chat or memory.
  - `crash_notes.rs` scrubs every note and keeps at most 10.
  - The backend log goes through `jarvis_scrub.py`.
  - The phone's `Log.*` calls (`TokenStore.kt:62-79`) log a message and a throwable, not the token.
  - No `?token=` URL is built anywhere in `src`, `src-tauri`, `jarvis-client` or the backend, apart from the Joplin URL that `jarvis_local_http.py` already guards.
- **Pictures on disk (area D).**
  - I found no temp-file writes in `jarvis_screen*.py`, `jarvis_picture.py`, `jarvis_chat_picture.py` or `jarvis_photo_remind.py`. PNGs are built in memory (`jarvis_picture.py:187`).
  - The phone has no `cacheDir` or `createTempFile` use, so nothing is left behind on error paths.
  - Caveat: I did not check every `open(...)` in those files exhaustively.
- **Retention (area D).**
  - `jarvis_backup.py` has `KEEP = 5`.
  - Phone captured notifications are capped by count and by age (`CapturedNotifications.kt:55, 85`).
  - The second-card lane logs are opened with `"wb"`, so each start truncates them.
- **Phone approval expiry and clock skew (area E).** `approval-expiry.patch:10-22` sends seconds left instead of a clock time, so a phone with a wrong clock still counts down correctly. The desktop App lock idle timer uses `Instant` (monotonic). I did not check whether `Instant` counts time spent asleep on Windows.
- **Accessibility (area A), light probe only.**
  - Desktop: `prefers-reduced-motion` handling exists in `style.css:317, 594`, `jarvis_hud.html:474, 825` and `faces.html:5750`.
  - Desktop: the approval buttons use `:focus-visible` with a box-shadow replacing the outline (`widget.css:640`, `style.css:1670`).
  - Phone: `FaceView.kt:533` has a polite live region. `AppearanceScreen.kt` and `InboxScreen.kt` use `minimumInteractiveComponentSize`, and the "a11y-12" note there shows an earlier a11y pass.
  - Phone: only one `contentDescription = null` turned up (`PairingScreen.kt:176`), and I did not check whether it is decorative.
  - Not checked: touch targets across all 12 `.clickable` uses, sp vs dp, swipe-to-approve TalkBack semantics, and colour contrast of the `--tokens`.

**Owner's call (only #3-adjacent, if raised): what should a bad security value do?**
- (recommended) Fail closed: keep App lock on if the raw value says on, and reset only the bad field.
- Or keep today's behaviour and show a plain "your security settings were reset" note.

Nothing was changed.
