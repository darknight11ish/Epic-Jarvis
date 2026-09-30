# Report 44 (audit), agent ac609ae5, 2026-09-30T07:09Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis, area: TIME (read CLAUDE.md first; verify each claim with file:line + quote; 'not checked' honestly; change no files). Already found by a probe (do NOT repeat, but extend): wall-clock time.time() used for short security windows (jarvis_speech.py wake-word prompt, jarvis_voice_enroll.py, jarvis_voices.py, Undo window jarvis_forget_range.py UNDO_SECONDS) and backup retention sorted by file name. Audit: (1) SCHEDULER and reminders (backend/jarvis_schedule.py, jarvis_tellme.py, jarvis_briefing*.py, jarvis_standby*.py, jarvis_focus*.py, jarvis_initiative*, 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

TIME audit. No repo files changed; throwaway scripts are in the scratchpad dir. "Ran" means I ran it on Linux with TZ set. Nothing here was run on Windows.

Cleared:
- jarvis_schedule.py is DST-safe when run with Linux TZ (America/New_York, Europe/London).
- A 02:30 daily alarm on the spring-forward day fires at 03:00, once. A 01:30 alarm on the fall-back day fires once, at the first 01:30. After that it is 25 hours to the next run.
- "Every weekday at 7" is correct across 31 Dec to 3 Jan (weekend skipped), and across 29 Feb 2028.
- The tidy hour is not a production bug. jarvis_tidy.py:618-631 (`run_night`) takes one `now` per run, so no call can cross 02:00. The 01:59 failure was a test-only double read of the real clock (test_tidy.py:312-329, already fixed).
- Approval-card countdown is safe. The backend sends seconds left (approval-expiry.patch, "Sent as seconds LEFT"), so the phone's clock does not matter.
- Pairing sessions use `time.monotonic()` (jarvis_devices.py:492-494).
- Phone App lock uses `elapsedRealtime` (MainActivity.kt:3222).
- Date parsers handled Dec to Jan ranges, "last week" on a Sunday, and a Friday said on a Friday. The bug in that area is item 6.

Ranked findings, worst first:

1. **A missed alarm can ring loudly as if it were happening now.**
   - Desktop, brain/schedule.rs:590-594: `.and_then(|j| j.get("fired_at"))...unwrap_or(0.0) as i64`. Then line 499 is `fired_at > 0 && now - fired_at > LATE_RING_LIMIT_S`. If the job read fails, `fired_at` is 0 and `heard_late` is false, so it rings.
   - Phone, JarvisRuntime.kt:4827 with Schedule.kt:806-807: `firedAt != null && firedAt > 0 && ...`. A null `firedAt` also means "not late".
   - Trigger: the app restarts and replays an old event while the backend read fails (backend restarting, or the job already purged after FIRED_KEEP).
   - The event itself carries `"late"` (jarvis_schedule.py:1598), and neither client uses it as a fallback. Read, not run.
   - Fix: if the read fails and the event says `late`, or the age is unknown, show it quietly. Failing quiet is the safe side.

2. **The phone judges "late" using its own clock against the PC's clock.**
   - Schedule.kt:806 compares the phone's `arrived/1000` (JarvisRuntime.kt:4802, `System.currentTimeMillis`) with the PC's `fired_at`.
   - Phone more than 10 minutes ahead of the PC: every alarm becomes a silent "Missed" notice, so a wake-up alarm does not ring. Phone behind: old alarms ring.
   - Fix: have the PC send `age_s` (its own now minus `fired_at`) in the job view, and have both clients use it. One field on the PC. Read, not run.

3. **Alarm wording bugs in quick parse (ran, jarvis_quick.py:459/442-445/649-657).**
   - "12 at night" and "12 in the evening" set at 15:00 Friday give **Sat 12:00**, which is noon. The "pm" rule does `hh % 12 + 12`, and midnight wanted 0. Wrong alarm hour, silently.
   - "every day at 12" gives `{'at': '00:00'}` (midnight), because the first candidate hour is taken. A bare "at 6" repeat silently means 06:00.
   - Fix: treat 12 with "night" as 0. Ask, or say the time back, for a bare 12.

4. **Every timer, alarm and reminder is an absolute wall-clock epoch.**
   - Examples: `now + d` in jarvis_quick.py:677, `due <= now` in tick at jarvis_schedule.py:1527, and `late = now - due > 120` at :1530.
   - PC sleep: on resume a timer fires once, late, and the job says "missed". Fine.
   - Clock stepped backwards (NTP fix, manual): timers and alarms wait until the clock catches up, so they can be hours late.
   - Clock stepped forward: they fire early.
   - Nothing in the tick loop uses a monotonic guard. Fix: on a backwards jump (`now` lower than the last tick), re-anchor the timers' `due` (timers only).

5. **Phone alarms depend on the PC event stream.**
   - There is no AlarmManager anywhere in jarvis-client (grep found none). If the phone is out of Tailscale reach or Doze cut the stream at ring time, nothing rings. When it reconnects after more than 10 minutes, it shows a silent notice (by design, but worth stating).
   - "Missed at 07:00" is `clock(fired_at)` from the PC (jarvis_schedule.py:1728): PC zone, HH:MM only, and no date for a job from yesterday.
   - The phone also never shows times in its own zone or 12/24h. Travel is only "wrong" in the sense that everything is the PC's clock. Consistent, but say so.

6. **Small parser bugs (ran):**
   - jarvis_forget_range.py:1116: "forget what you learned 29 february to 15 january" (today 2028-03-10) gives an unhandled `ValueError: day is out of range for month`, from `start.replace(year=end.year-1)`. Result: a crash for that phrase, not data loss. Fix: try/except, then ask.
   - jarvis_past.py:216: `monday = today - wday*86400` is off by an hour when a zone's clock change falls mid-week. Ran with Asia/Jerusalem, Sun 2026-03-29: the "last week" window ends "Sun 2026-03-22 23:00" instead of Monday 00:00. It is harmless in zones that change on Sunday (New York and London showed correct output). Fix: use `_local(y, mo, d - wday)`.
   - "friday at 5pm" said on Friday 15:00 gives next Friday, not today 17:00 (ran). This is an intentional-looking rule at jarvis_quick.py:476, but debatable.

7. **Calendar events in another time zone show at the wrong hour** (jarvis_briefing.py:680-702). `event_when` ignores TZID and treats it as the PC's zone. This is documented, but it affects travel and Google recurring events.

8. **Expiries by clock type:**
   - Wall clock, and they follow a clock step:
     - Undo windows (jarvis_inbox_tidy.py:1154 `until`; jarvis_forget_range.py:843). Both also run a `threading.Timer` purge, so a clock stepped backwards cannot extend Undo past 600 s. A forward step or sleep ends it early, which is stricter and safe.
     - The phone's "new chat after 30 quiet minutes" (ChatHistory.kt:376, `currentTimeMillis`): a backwards clock step delays the new chat only. No security effect.
   - Not checked:
     - whether Rust `Instant` and Python `time.monotonic` count PC sleep on Windows. The desktop App lock (lock.rs:190, `Instant`) depends on this.
     - the gate's approval wait loop in jarvis_gate.py. It is not in the repo, only the patch.

9. **Tests.**
   - The DST tests SKIP on Windows (test_schedule.py:140 and :170: "no time.tzset here"). The owner's PC runs Windows, so `wall_to_epoch`'s dst=0/1 mktime trick is untested on the real platform. Not checked there.
   - 46 backend test files use `time.time()`, `datetime.now` or `localtime()`. Most-affected: test_briefing.py (12 uses), test_tidy.py (5, two fixed), test_schedule.py (4), test_tellme.py (3), test_quick_wins.py, test_standby_schedule.py.
   - test_briefing.py:1284 asserts `tm_hour == 7` using the machine's zone. test_forget_range.py and test_past have no TZ pinning.

Owner decisions (recommendation first):
- **Late-alarm rule.** (A) The PC sends the age in seconds and the clients use it, so clock differences stop mattering. Recommended. (B) Leave it, and only fix the failed-read case.
- **"12 at night".** (A) Read it as midnight and always say the time back. Recommended. (B) Ask "midnight or noon?".
