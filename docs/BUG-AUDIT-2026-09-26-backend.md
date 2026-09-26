# Bug audit of the Python backend - 2026-09-26

Scope: `backend/*.py` (the shipped modules), `backend/rebuilt/*.py`, `backend/*.patch`
and `scripts/apply-patches.ps1`. The code added or changed since 2026-09-24 came first.
Left out on purpose, because other sessions are changing it right now: server-address
checks, and the approval-tier / "what asks first" work (the repeat-card logic in
`jarvis_schedule`, people facts in `jarvis_sensitive`, the lights setting in
`home_control`, the new tiers route).

## In plain words (for the owner)

1. **I found no break of the five rules.** No password, key or private link leaks
   into a log, an error or an event. Nothing is approved without a person. Nothing
   private leaves the PC by a new route.
2. **One real timing bug in focus sessions.** If you stop a session and start a new
   one within a second or two, the new session can lose its end time. It then never
   ends by itself: Jarvis keeps watching the screen and stays on Quiet until you say
   "stop focus".
3. **"Tell me when" has two small problems.** "What did I miss?" says a watch "went
   off" every time Jarvis merely *looked* at your inbox, even when nothing matched.
   And a watch whose end date passed while the PC was asleep looks once more when
   the PC wakes, and can notify you about an email that came after the end date.
4. **Smaller problems:** an email subject containing a rare "line separator"
   character passes the checks, then fails with a Python error after you approve
   it. On the two days a year the clocks change, the morning briefing's calendar is
   wrong by one hour's worth of events. Reading email has no time limit if the mail
   server stops answering (this one is older code, from 2026-09-19).
5. **Everything was checked against the code, and each problem was reproduced**
   with a small script. All 95 test suites pass (19 skipped because they need files
   that only exist on your PC), and `apply-patches.ps1` has no PowerShell-7-only
   syntax.

## Findings

| # | Severity | Where | One-line bug | Fix size |
|---|---|---|---|---|
| 1 | Medium | `jarvis_focus.py` `finish()` / `_drop_timer()` | Stopping (or ending) a session while a new one starts deletes the NEW session's end job; that session never ends by itself | Small (about 10 lines) |
| 2 | Low-medium | `jarvis_schedule.py` `fired_since()` | "What did I miss?" reports every routine "tell me when" look as something that "went off" | One line |
| 3 | Low-medium | `jarvis_schedule.py` `tick()` + `jarvis_tellme.py` `look()` | A "tell me when" found overdue after its end date looks once more and can notify about mail that arrived after the end | A few lines |
| 4 | Low | `jarvis_email_send.py` `_INVISIBLE` | A subject containing U+2028/U+2029 passes `plan()`, can show a fake line on the card, then fails with `ValueError` after approval | One line |
| 5 | Low | `jarvis_briefing.py` `_read_calendar()` | On clock-change days the briefing reads a 24-hour window: misses the last hour on the 25-hour day, and shows tomorrow's 00:00-01:00 events as "today" on the 23-hour day | Small |
| 6 | Low (older code) | `jarvis_email.py:205` | The email-reading tool opens IMAP with no timeout, so a mail server that stops answering hangs the chat answer for good | One line |

---

### 1. Focus: a quick stop-then-start leaves the new session with no end (Medium, certain)

**Evidence.** `finish()` marks the session over inside the lock, then does slow work
outside it and touches `self.job_id` afterwards:

```
jarvis_focus.py:1398            jid = self.job_id
jarvis_focus.py:1399        # Outside the lock: switching power waits for its answer.
jarvis_focus.py:1400        restore = self._restore_power()
jarvis_focus.py:1401        if not completed and jid:
jarvis_focus.py:1402            self._drop_timer()
jarvis_focus.py:1403        self.job_id = ""
```

`_drop_timer()` does not delete `jid`; it deletes whatever `self.job_id` is *now*:

```
jarvis_focus.py:939     jid, self.job_id = self.job_id, ""
...
jarvis_focus.py:943         self._sched().act(jid, "delete")
```

`_restore_power()` calls `set_mode("active", ..., wait_s=1.5)` (line 985), so the
window can be over a second. And there is no fallback end while a scheduler job is
supposed to exist:

```
jarvis_focus.py:1026            if not self.on_scheduler and now >= self.ends_at:
```

**What goes wrong, step by step.**
1. A session is running; focus had set Quiet.
2. The owner says "stop focus". `finish()` sets `on = False`, releases the lock, and
   starts switching power back to Active.
3. Before that returns, the owner starts a new session (a button in either app, or
   "focus for 25 minutes"). `start()` sees `on == False`, resets, and puts a NEW end
   job on the scheduler; `self.job_id` is now the new job.
4. The first `finish()` continues: `_drop_timer()` deletes the NEW job, and line 1403
   blanks `job_id`. The OLD job is left on the scheduler.
5. The new session has `on_scheduler == True` and no job. When the old job fires,
   `on_fire()` ignores it (`job_id == self.job_id` fails, line 950). The session
   never ends: the screen is read every second and Quiet stays on until "stop focus".

The natural end has the same shape: `on_fire` → `finish(completed=True)` → line 1403
blanks the id of a session started during the power switch.

The same end-state is also reached if the hidden `focus` job is deleted by id through
`POST /api/schedule/act` (its id goes out on the `schedule` event), because of line 1026.

**Reproduction (run).** `repro_focus.py`: a power switch stand-in that blocks until a
second `start()` has run, then:

```
second start: 200 job_id: s2343921256 on_scheduler: True
after first stop finished: on: True job_id: '' on_scheduler: True
focus jobs left on scheduler: [('sa4b734eff6', 'active')]     <- the OLD session's job
26 minutes later: session still on? True left_s: 0.0
```

**Smallest fix.** In `finish()`, delete the captured id, not the current one, and
only clear `job_id` if it still belongs to this session - e.g. replace lines 1401-1403
with `if not completed and jid: self._sched().act(jid, "delete")` (in a try) and
`with self._lock: if self.job_id == jid: self.job_id = ""`. For belt and braces, let
the look thread also end a session whose `left_s()` has been 0 for a minute.

---

### 2. "What did I miss?" counts "tell me when" looks as things that went off (Low-medium, certain)

**Evidence.** A tellme job is registered `silent=True`, but `notify` and
`owner_listed` keep their defaults (True):

```
jarvis_tellme.py:942  S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True,
jarvis_tellme.py:943                  repeatable=True, silent=True, first_now=True, leaves=True,
```

`tick()` stamps `fired_at` on every look (line 1385). `fired_since()` filters only on
`notify` and `owner_listed`, not on `silent`:

```
jarvis_schedule.py:1244            k = KINDS.get(r["kind"])
jarvis_schedule.py:1245            if k is not None and (not k.notify or not k.owner_listed):
jarvis_schedule.py:1246                continue
```

`_view()` already knows a silent kind's late look is "just a look" (line 1536); this
filter was missed.

**What goes wrong.** With one email watch set up and nothing matching, the owner asks
"What did I miss?" and is told something went off. That is a claim that is not true
(ARCHITECTURE invariant 6), and it reads like the watch matched.

**Reproduction (run).** `repro_missed.py`: one email watch, twelve 5-minute looks, no
matching mail:

```
fired_since: [('tellme', '03:12')]
{'key': 'went_off', ... 'summary': '1 "tell me when" went off.', 'items': ['03:12 "tell me when"']}
```

**Smallest fix.** In `fired_since()`, also skip `k.silent` (a match already has its own
`matched` event and `alert`). If a matched watch should appear there, list it from
`jarvis_tellme`'s `matched_at`, not from `fired_at`.

---

### 3. "Tell me when" looks once more after its end date (Low-medium, certain)

**Evidence.** When an overdue repeating job fires past its end, `tick()` marks it
`fired`, but still spawns `on_fire` for it:

```
jarvis_schedule.py:1376   if rule.get("ends") is not None and nxt > float(rule["ends"]):
jarvis_schedule.py:1377       nxt = None
...
jarvis_schedule.py:1424   if k is not None and k.on_fire is not None:
jarvis_schedule.py:1426       self._spawn(lambda fn=fn, jid=jid: _safe(fn, jid))
```

and `look()` accepts a `fired` job and never compares the clock with `ends`:

```
jarvis_tellme.py:739      if row is None or row["state"] not in ("active", "fired"):
```

**What goes wrong.** The card said "Until: <date>". The PC sleeps (or is off, or the
watch is paused and later resumed - `act("resume")` sets the next due time from the
rule, which can be after `ends`). When it wakes days after the end, the overdue job
fires once: Jarvis signs in to the mail server (or reads Home Assistant) and, if an
email from that sender arrived in the meantime, rings the phone - including urgent,
keep-ringing alerts - for mail that came after the watch ended.

**Reproduction (run).** `repro_end.py`: a watch ending in one hour; the clock moved
three days; an email from Alex arrives after the end:

```
looks so far: 1
looks after waking, 3 days later: 2 (ends was 71 hours ago)
matched events: [{'id': 's3da860eda0', 'kind': 'tellme', 'state': 'matched', 'urgent': False}]
```

**Smallest fix.** In `look()`: if `rule.get("ends")` is set and `sched.now() > ends`,
end the job and return without looking. (The last legitimate look is due at or before
`ends`, so it still runs.)

---

### 4. Email subject with U+2028: odd card, then a crash after approval (Low, certain)

**Evidence.** The subject check blocks control and format characters only:

```
jarvis_email_send.py:337  _INVISIBLE = ("Cc", "Cf", "Cs", "Co", "Cn")
jarvis_email_send.py:388      if _hidden_chars(subject):
```

U+2028 (LINE SEPARATOR) is category `Zl`, U+2029 is `Zp`, so they pass. Python's
email library treats them as line breaks when the header is set:

```
jarvis_email_send.py:463      msg["Subject"] = p.subject
jarvis_email_send.py:696      data = message(p).as_bytes(policy=SMTP_POLICY)   # outside the try
```

**What goes wrong.** A model (or text it copied from an email) writes a subject like
`Hi<U+2028>Bcc: someone@x.com`. `plan()` accepts it; the card is raised. On a screen
that renders U+2028 as a new line (Android's text views do), the card shows a line
reading "Bcc: someone@x.com" - on a card that promises "no hidden (Bcc) recipients".
The owner approves; `message()` raises `ValueError: Header values may not contain
linefeed or carriage return characters`; `_one_call` turns that into the tool result
(`jarvis_agent.py`, the `except Exception` around `tool.execute`). Nothing is sent -
so no harm beyond a confusing card and a raw Python error after a yes.

**Reproduction (run).**

```
p = plan(['a@b.com'], subject='Hi Bcc: evil@x.com', body='hello')
repr(p.problem)  ->  ''
message(p)       ->  ValueError: Header values may not contain linefeed or carriage return characters
```

**Smallest fix.** Add `"Zl", "Zp"` to `_INVISIBLE` (the body allows `\n` already, so
refuse or normalise them there too).

---

### 5. Morning briefing calendar on the two clock-change days (Low, certain)

**Evidence.** "Today" is worked out correctly (`_today()`, 23 or 25 hours), but the
calendar is read for exactly 24 hours from local midnight:

```
jarvis_briefing.py:421     p = CAL.plan(1, now=datetime.fromtimestamp(start, tz=timezone.utc))
jarvis_calendar.py:283     end = moment + timedelta(days=days_ahead)
```

and an event on another date is labelled as if it began earlier:

```
jarvis_briefing.py:408     tail = " (repeats)" if repeats else " (continues from an earlier day)"
```

**What goes wrong.** Clocks go back (25-hour day): events from 23:00 to midnight are
not read, so a late event is missing from "today". Clocks go forward (23-hour day):
events from 00:00 to 01:00 *tomorrow* are read and shown as today's, marked
"(continues from an earlier day)".

**Reproduction (run, TZ=Europe/London).**

```
25 Oct 2026, events 09:00Z and 23:30Z:  '1 event today.' ['09:00 Morning thing']          (23:30 missing)
28 Mar 2027, event 2027-03-28T23:30Z:   '1 event today.' ['00:30 Tomorrow 00:30 flight (continues from an earlier day)']
```

**Smallest fix.** Plan the read with the real end of today (`_today(now)[1]`) - e.g.
give `jarvis_calendar.plan` an optional `end=` - and in `calendar_items` drop events
that start after today.

---

### 6. Email reading has no network timeout (Low, likely - older code)

**Evidence.**

```
jarvis_email.py:205    conn = imaplib.IMAP4_SSL(p.host, p.port)
```

No `timeout=`, and nothing in `backend/` or `backend/rebuilt/` calls
`socket.setdefaulttimeout` (checked with grep). The two newer IMAP calls in the same
file (lines 329, 406) and `jarvis_tellme` do pass a timeout. This one is used by
`run()` (line 527), i.e. the model's `email_check` tool.

**What goes wrong.** A mail server (or a network path) that accepts the connection and
then goes silent leaves the chat answer waiting forever, with keepalives flowing, and
the model loaded.

**Reproduction (run).** A local socket that accepts and never speaks; the fetch in a
thread: `still waiting after 8 s: True`. Whether the owner's `jarvis_hud.py` sets a
global socket timeout was not checked (it is not in this repository) - hence "likely".

**Smallest fix.** `imaplib.IMAP4_SSL(p.host, p.port, timeout=_COUNT_TIMEOUT)` (or its
own constant).

---

## Possible, not verified

- **A stamp can outlive a refused approval.** `jarvis_owner_check.approve_check()`
  stamps the approval (line 632) *before* the owner's own `/api/approve` handler runs.
  If that handler then refuses (a 400 or 409 of its own) while the gate is still
  waiting for the row, the stamp stays for up to 15 minutes, and an "approved" written
  straight into `approvals.db` for that id during that time would be believed. For a
  risky card from this PC the stamp needs Windows Hello first, so the owner would
  have confirmed it anyway; the gap matters only if the handler has refusal reasons
  the check does not share. Not verified: the handler is in the owner's `jarvis_hud.py`,
  which is not in this repository. Safer order: stamp only after the handler returned
  200 (or drop the stamp on any other status).
- **Repeating reminders set by the model do not count towards the five-cards limit.**
  `set_reminder` with `repeat` goes through `_schedule_call` → `jarvis_schedule`, which
  raises its own `schedule_repeat` card on a thread; `watch.cards` is never
  incremented, so one answer could raise more than `CARDS_PER_TURN` of them. Only in a
  turn of the owner's own words (outside text refuses schedule tools). Not pursued:
  it sits in the repeat-card logic another session is changing.

## Areas read and found fine

- **`jarvis_owner_check.py`**: the stamp (per-process secret, HMAC over id and action,
  one use, TTL, capped), `from_this_pc` (loopback, IPv4-mapped, `peer == local`,
  unplaceable counts as this PC), the re-read of the queue after Windows Hello, deny
  never held up, the gate failing closed without the module (`owner-check.patch`).
  The Windows Hello child itself was not run (no Windows here).
- **`jarvis_email_send.py`**: address and Message-ID regexes leave no way to start a
  new header; CR/LF refused in the subject; Bcc impossible; caps; settings and
  fingerprint re-checked in `run()`; the password never in a plan, card, result,
  error or event (exception names only); scrubber registration of the base64 forms;
  dot-stuffing left to `smtplib`; no retry.
- **`jarvis_agent.py`**: send_email refused before any card unless the turn's model is
  on this PC and the tier is `ask`; `NEEDS_A_PERSON`; Stop everything checked before
  the gate and again after an approval (`_one_call`, `_web_search_call`);
  `end_turn()` in a `finally`; the card-length refusal; `CARD_OUTCOME_WORDS` sent only
  after an "approval" line; `_model_waking` asks only this PC's Ollama.
- **`jarvis_search.py`**: no socket in `plan()`, secret check that fails closed,
  redirects refused, answers capped at 1 MB, the key sent only in its own header,
  settings re-checked in `run()`, no silent fallback.
- **`jarvis_calendar.py` (private link)**: `_FeedRedirect` (same host or Google hosts,
  https only), `_hide_link` on every failure, capped and time-limited reads.
- **`jarvis_tellme.py` IMAP**: only LOGIN, EXAMINE, UID SEARCH, UID FETCH
  `BODY.PEEK[HEADER.FIELDS (FROM)]`, CLOSE, LOGOUT; the name never sent; errors by
  exception name. Lock order between its `_LOCK` and the scheduler's lock checked: no
  inversion.
- **`jarvis_schedule.py`**: DST helpers (`wall_to_epoch` gap and fold, `next_at`,
  `last_at`), snooze copies, "cancel that" (per conversation, time window, once),
  named lists and `clear_list`'s count check, the card thread's withdrawal check,
  the schema migration (`ALTER TABLE` for new columns).
- **`jarvis_quick.py`**: snooze, undo, lists, what did I miss, tell me when, focus,
  search and reach parsers; the answer only for the owner's own typed or said words.
- **`jarvis_stop_all.py`, `jarvis_manner.py`, `jarvis_card_words.py`, `jarvis_reach.py`
  (hosts only, never a path or key), `jarvis_mail_mask.py` (bounded to 1,600
  characters, withholds on error), `jarvis_backoff.py`, `jarvis_standby_schedule.py`,
  `selftest.py --preflight`** (the web-search probe runs without a flag, but that is
  documented in its header).
- **`scripts/apply-patches.ps1`**: parses cleanly in PowerShell 7 (0 errors); no `??`,
  `?.`, ternary, `&&`/`||`, or 6+-only parameters found; every native call
  (`git`, `patch`, `py`, `pip`, the suites) runs with `$ErrorActionPreference =
  'Continue'` and restores it in a `finally`.
- **Patch context**: `python3 backend/run_suites.py` - 95 passed, 0 failed, 19 skipped
  (they need the owner's own files); `test_patch_history.py` passed.

Reproduction scripts were run from the session's scratch folder; they are not part of
the repository. Each is short and is described in its finding above.
