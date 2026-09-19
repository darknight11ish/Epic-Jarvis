# Bug audit, 19 Sep 2026

Four independent auditors, one per codebase (Rust, frontend JS, Android
Kotlin, Python), then every serious claim re-verified against the real file
by hand before it was written down here. Where a finding could be executed
rather than argued, it was — those are marked **reproduced**.

**The uncomfortable summary: the worst findings are in code written earlier
the same day.** Four of the top five are regressions introduced by the
session that was supposed to be fixing things. That is recorded here in
plain terms rather than softened, because the alternative is a document that
is pleasant to read and useless.

Legend: **[MINE]** = introduced 19 Sep. **[PRE]** = pre-existing.

---

## Status, as of the end of 19 Sep

All twenty-four were worked. Twenty-three are fixed; one was examined,
attempted, measured, and deliberately left alone.

| | Finding | Outcome |
|---|---|---|
| 1 | Phone-wide speech recognizer | fixed — `a5ad1d0` |
| 2 | Swatch governor lies | fixed — `5218b28` |
| 3 | Flash limit fails open at speed | fixed — `5218b28` |
| 4 | Pause is a one-way door | fixed — `8703dd1` |
| 5 | Windows Deny toast, three defects | fixed — `5218b28` |
| 6 | Widget says "Nothing waiting" | fixed — `a5ad1d0` |
| 7 | Widget Deny on a stale link | fixed — `a5ad1d0` |
| 8 | `LOAD_FAILED` starts false | fixed — `5218b28` |
| 9 | HA lock without the HEAVY marking | fixed — `8703dd1` |
| 10 | HA entity ids raw in the URL | fixed — `8703dd1` |
| 11 | Memory misses every `ss` word | fixed — `8703dd1` |
| 12 | `announce()` before the checkpoint | fixed — `8703dd1` |
| 13 | Stop on the final step | fixed — `8703dd1` |
| 14 | Android pause drops `screenshots` | fixed — `8703dd1` |
| 15 | `spec_drift`: null spec, `checked`, silence | fixed — `5218b28` |
| 16 | Empty assistant window flash | fixed — `a5ad1d0` |
| 17 | Bare `initialize()` in the widget | fixed — `a5ad1d0` |
| 18 | A typed note blanked by a refresh | fixed — `5218b28` |
| 19 | `voice.rs` mutex convention | fixed — `5218b28` |
| 20 | Solo view resize listener | fixed — `5218b28` |
| 21 | `prepare()` outside the try | fixed — `8703dd1` |
| 22 | One bad charset fails a mailbox | fixed — `8703dd1` |
| 23 | Repo age depends on the timezone | fixed — `8703dd1` |
| 24 | Governor counts the first transition | **not taken — see below** |

### Why 24 was not taken

The finding is accurate about the contradiction and wrong about which
half to change, and that was established by measuring rather than by
arguing. The code was changed to match the doc — the first transition
after a reset exempted from the opposing count — and both test suites
immediately reported four luminance changes reaching the screen inside
one second against a hard limit of three.

That is the right answer, and the reasoning behind the finding is the
subtle error: the limit is on what a viewer SEES, not on the governor's
internal bookkeeping. The first transition is a visible change like any
other. Calling it "not opposing" is true about direction and irrelevant
to photosensitivity.

So the change was reverted and the comment corrected in both ports. The
code was right; the sentence describing it was not. Both now say the
same thing, and both say why.

Two other items were widened once their real shape was clear, and the
extra work is in the same commits: **14** was flagged for the pause path
and three of the four early exits had it, so all four were fixed; **10**
was flagged for `plan_states` and the service domain and name reach a
URL path too, so those are checked as well.

One finding that survived was also found to be narrower than reported:
**20**'s orphaned resize listener needs `openSolo` to run twice without
a close, and `#solo` is a full-screen overlay above the grid, so there
is no way to reach that today. It is closed anyway, at the root — the
listener now captures its own surface instead of reading a global — but
the note in the code says plainly that this shuts a hole rather than
repairing an observed failure.

---

## Second pass: auditing the fixes

The twenty-three fixes were then audited themselves, by **mutation
testing** — revert each fix in a scratch copy, run its test, and require
the test to fail. A fix whose test passes either way is not protected,
and two of them were not.

| | Found in the fixes | Outcome |
|---|---|---|
| A | A cold-start Deny still opened the window | fixed — `f2cf91d` |
| B | Android checkpoint below the device check | fixed — `f2cf91d` |
| C | Flash call site had no test at all | fixed — `f2cf91d` |
| D | Announce ordering untested on two of three loops | fixed — `f2cf91d` |

**A.** `decide_denied_at_startup` answered the approval and its doc said
"The window is not raised" — but `build_hud_window` builds the HUD
`.visible(true).focused(true)` for every launch that is not a login
start. So the window went up regardless, and the fix written to honour
rule 2 was paying Approve's price while claiming not to. The claim was
three files away from the code that falsified it, which is exactly how
the last one of these got through.

**B.** The Android loop read the checkpoint *below* the device
re-verification, and that path returns on its own. Because `checkpoint()`
now consumes, a phone unplugged while a pause was pending stranded the
pause forever — the one-way door, still reachable by another route.

**C, and the most uncomfortable.** `tests/flashgov.mjs` never touched the
`faces.html` call site. Reverting the two-clock fix there left all ten
checks passing. The photosensitivity limit — the thing the spec calls a
hard limit, not advice — was guarded by a test that could not see the
code it guarded. The bug was never in `governedResolve`; it was in what
the renderer handed it, and the test only ever drove the function.

### Two of the new tests were themselves wrong

Recorded because it is the same lesson twice:

- The first mutation "proving" the swatch test worked failed with a
  `ReferenceError` from how the mutation was written, not the real
  symptom. It proved nothing until redone; done properly it reports
  `approval bound #ffffff but showed #000000`.
- The new call-site check matched `function governedResolve(gov, …)` —
  the declaration — instead of the call, so it was red against correct
  code. A check that fails on a healthy tree is worse than no check.

Both were caught by running them, not by reading them.

### Checked and found sound

- The edited `memory-safety.patch` hunks apply cleanly under `git apply`
  against a base rebuilt from the patch's own context; the edit touches
  only the `jarvis_memory.py` section.
- `governedResolve` has exactly two callers and no surface resolves
  ungoverned; `_is_heavy_service` has exactly one caller.
- `closeApproval` does clear `state.approval`, so the note-blanking
  `fresh` check is correct when the same card is reopened.
- The prepare-time `continue` still emits exactly one tool message per
  `tool_call` id, which the API requires.

---

## Critical

### 1. [MINE] The app publishes a phone-wide speech recognizer that always fails

`jarvis-client/app/src/main/res/xml/recognition_service.xml`
`jarvis-client/app/src/main/AndroidManifest.xml` (the `JarvisRecognitionServiceStub` block)

`JarvisRecognitionServiceStub` exists only to satisfy the
`<voice-interaction-service>` schema, which requires a `recognitionService`
attribute. It errors immediately on every call, by design. But it is also
declared with `<action android:name="android.speech.RecognitionService"/>`,
and its `<recognition-service>` element does **not** set
`android:selectableAsDefault` — which AOSP defaults to `true`.

So it is enumerated by the system's recognizer discovery and appears in
Settings → Voice input as a pickable default speech recogniser. If it is
ever selected — by the owner browsing that screen, or by the system falling
back to the first available recognizer when the configured one is missing or
its package changes — then **every** `SpeechRecognizer` call on the entire
phone fails instantly. Gboard voice typing, every other app. Nothing points
at Jarvis as the cause.

This is a bug whose blast radius is the whole device, shipped by an app whose
own rule is that it does no speech recognition at all.

**Fix:** `android:selectableAsDefault="false"` on the `<recognition-service>`
element (API 33+, and minSdk is 33, so always honoured). Better still, also
drop the `<intent-filter>` — `VoiceInteractionServiceInfo` reads the
`recognitionService` *attribute string* and never queries by action, so the
filter buys nothing and is what makes the service discoverable.

### 2. [MINE] The flash-governor "fix" broke the colour picker — reproduced

`jarvis-desktop/src/faces.html:4082` (`const SWATCH_GOV`) and `:4103`

One governor instance shared across all eight state chips. `syncUI()` loops
every chip through it in a single pass at one timestamp, so the governor sees
eight unrelated colours as one surface flashing, spends its three-transition
budget on the first few, and hands the rest a previous chip's colour.

Reproduced by lifting the real `resolve`/`governedResolve` out of the file
and driving them the way `syncUI()` does:

```
approval    rgb(255,182,72)  ->  rgb(142,234,255)   <<< shows speaking's blue
standby     rgb(62,76,94)    ->  rgb(142,234,255)   <<< shows speaking's blue
banked      #8fa3b8          ->  rgb(255,216,220)   <<< shows error's pink
```

It does not flicker; it lies stably. The picker's only job is to show which
colour is bound to which state, so the owner binds amber to `approval`, sees
ice blue, and concludes the binding failed.

This is *verbatim* the failure `limits.flash.scope_why` in the visual spec
describes ("spent its budget on those cross-surface transitions and then held
one face's colour on another"). That sentence was read, quoted in the commit
message, and then contradicted by the change it justified.
`tests/flashgov.mjs` passes because it exercises a single governor instance —
the multi-binding case is precisely what it does not cover.

**Fix:** one governor per chip — `const SWATCH_GOV = {}` keyed by state id,
`governedResolve(SWATCH_GOV[sid] ||= newFlashGovernor(), …)`. Reverting
`:4103` to plain `resolve(...)` is also strictly better than the status quo.

### 3. [PRE] Photosensitivity limit fails open at high speed

`jarvis-desktop/src/faces.html:3523`, `:3643`, `:3073`

`governedResolve` is handed `s.clock`, which `:3643` advances by
`dt * speed`. The governor's one-second window (`t - at < 1.0`) is therefore
measured in *speed-scaled face-clock seconds*. The spec's `speed.max` values
reach 6, so at the top of the slider one governor "second" is 1/6 of a real
second and up to 18 opposing transitions per real second get through —
against a hard limit of 3 that the spec itself calls "a hard limit, not
advice". The same scaling defeats the 1.3 Hz flicker clamp (→ 7.8 Hz).

**Fix:** keep `s.clock` for `resolve()`, but give the governor an unscaled
wall-clock value for its `recent` window.

---

## Serious

### 4. [MINE] Pause is a one-way door

`backend/jarvis_task_control.py` — `clear()`

`clear()` has no caller anywhere outside its own tests, and none of the three
`run()` loops clears on exit. Its docstring promises "a stale pause from a
task that already ended can never leak onto a different task"; nothing
implements that. Pause a task, press continue, and the fresh run pauses again
at step 1 — permanently, and so does any later task reusing that id.

**Fix:** have `checkpoint()` consume the signal, or add a `resume()` that
clears, and document which caller owns it.

### 5. [MINE] The Windows Deny toast, three defects

`jarvis-desktop/src-tauri/src/winrt_toast.rs`, `lib.rs:506`, `stream.rs:779`

- **`winrt_toast.rs:141` claims a startup path that does not exist.**
  `deny_id_from_argv` has exactly one non-test caller — inside the
  single-instance callback, which by design only fires in an *already
  running* process. Deny clicked on a toast while Jarvis is closed silently
  does nothing and opens the app, which is the cost rule 2 reserves for
  Approve.
- **No dev-build AUMID guard.** `tauri-plugin-notification`'s own source
  deliberately skips setting the AUMID when the exe sits in `target/debug`
  or `target/release`, because it does not resolve for uninstalled builds.
  This module sets it unconditionally, and only falls back when `Show()`
  returns `Err` — so in exactly the builds used for testing, the likely
  outcome is *no notification at all* rather than a plain one.
- **Empty id swallows a real second launch.** `stream.rs:702` filters on id
  *presence*, not non-emptiness; `unwrap_or_default()` yields `""`;
  `strip_prefix("jarvis-deny:")` on `"jarvis-deny:"` returns `Some("")`;
  `lib.rs:511` then early-returns and skips the window raise.
  (A *normal* second launch cannot be swallowed — `argv[0]` cannot contain
  `jarvis-deny:`, since `:` is illegal in a Windows path.)

### 6. [MINE] The approvals widget says "Nothing waiting" when it has no data

`jarvis-client/.../widget/ApprovalWidget.kt:70-96`

`initialize()` constructs objects and launches collectors; it never fetches.
When the launcher redraws the widget in a process where `EventService` is not
already running, `pending` is the empty initial value and the widget renders
"Nothing waiting" — an approvals widget claiming there are no approvals,
which is the one failure it exists to prevent.

**Fix:** a distinct "no data yet — tap to open" state, or `refreshPending()`
inside `provideGlance` when paired.

### 7. [MINE] Widget Deny is offered, and silently swallowed, on a stale link

`jarvis-client/.../widget/ApprovalWidget.kt:74`

`connected` checks only `link == CONNECTED`, but `decisionBlocker` refuses on
`_stale` as well. So on a connected-but-stale link the widget shows Deny, the
tap does nothing, and the explanation lands in an in-app notice the owner is
not looking at. The retired widget this was ported from guarded on exactly
this.

**Fix:** `&& !JarvisRuntime.stale.value`.

### 8. [PRE] One character of data loss in the Faces window

`jarvis-desktop/src/faces.html:5053`

```js
/** True until a load has succeeded. Saving before then would publish defaults. */
let LOAD_FAILED = false;
```

The comment says `true`; the code says `false`. `loadAppearance()` is fired
unawaited *after* the save handler is wired, so between window open and the
load resolving, pressing save publishes spec defaults over the owner's real
saved face. No undo.

**Fix:** `let LOAD_FAILED = true;`.

### 9. [PRE] Home Assistant: a lock can be operated without the HEAVY marking

`backend/jarvis_home.py:107`

`_is_heavy_service` classifies on the *service* domain only. Home Assistant's
`homeassistant.turn_on/turn_off/toggle` forwards to the entity's own domain,
so `homeassistant.turn_off` on `lock.front_door` is not flagged heavy and the
approval card omits the "this is marked HEAVY" line for an unlock.

**Fix:** classify on `entity_id.split(".", 1)[0]` as well as `domain`.

### 10. [PRE] Home Assistant: entity ids are interpolated raw into the URL path

`backend/jarvis_home.py:157`, `:186`

`f"{base.rstrip('/')}/api/states/{eid}"` with `eid` arriving from the model,
only `.strip()`ed. `../../api/services/lock/unlock` reaches the wire
unescaped, and a `?` or `#` re-splits the URL. `plan_states` ships at tier
`auto` — no card — so this is the "standing grant" escape the module's own
docstring warns against.

**Fix:** `urllib.parse.quote(eid, safe="")` plus a shape check on ids.

### 11. [PRE] Memory search misses every word ending in `ss` — reproduced

`backend/rebuilt/jarvis_memory.py:209`, `:810`

`_words()` strips a trailing `s` before terms reach a `porter`-tokenized FTS
index. Porter keeps `ss` (`class`→`class`); `_words` makes it `clas`; Porter
then stems that to `cla`. No match.

```
'email address'  -> ['My email address is bob@exam']
'address'        -> []
```

Hits `class, pass, address, business, access, press, boss, glass`. The
`sqlite3.OperationalError` handler would hide it even if it raised.

**Fix:** build FTS terms from raw query tokens; let Porter stem. Keep
`_words` for the overlap tests, where both sides are folded consistently.

---

## Worth fixing, lower blast radius

12. **[MINE]** `announce()` fires *before* the checkpoint in all three control
    modules (`jarvis_ui_control.py:326`, `jarvis_android_control.py:266`,
    `jarvis_browser_control.py:508`), so a pause leaves the Brain window
    claiming a step that never ran — and `set_activity` is sticky.
13. **[MINE]** A stop arriving during the *final* step returns `ok: True`
    with no acknowledgement it was seen (`jarvis_ui_control.py:328`), and
    combined with #4 the signal then poisons the next run.
14. **[MINE]** The Android pause/stop return drops `screenshots`
    (`jarvis_android_control.py:267-277`), discarding images from steps it
    still reports as done.
15. **[MINE]** `spec_drift.rs:146` treats a 200 with no `spec` field as drift
    (`Null != object`), firing the exact false alarm the module doc says it
    exists to avoid. Also `:85-94` sets `checked: true` on paths that compare
    nothing, and every outcome except drift is completely silent — the
    `note` field is never surfaced and the `VISUAL_SPEC_DRIFT` event has no
    consumer.
16. **[MINE]** An empty assistant window flashes on every assist invocation
    (`JarvisVoiceInteractionSession.kt`) because `finish()` is an async IPC
    that lands after the session window is shown. Fix: `setUiEnabled(false)`
    in `onCreate()`.
17. **[MINE]** `JarvisRuntime.initialize()` is called bare from the widget
    (`ApprovalWidget.kt:71`, `:271`) where `MainActivity.kt:148` wraps the
    identical call in `runCatching` — a Keystore failure becomes "Problem
    loading widget" instead of a readable error.
18. **[PRE]** A note being typed is blanked by any unrelated queue refresh
    (`main.js:1204`, `widget.js:454`), including a resync that changes
    nothing — under a comment asserting this is safe unconditionally. This is
    the documented amend path, so it is the text most worth not losing.
19. **[PRE]** `voice.rs:145/155/168` use `if let Ok(...)` on the sample
    mutex where the whole codebase otherwise recovers with
    `unwrap_or_else(|p| p.into_inner())`. One poisoning turns recording into
    permanent silence with no error anywhere, and `stop_voice_capture` would
    POST an empty WAV.
20. **[PRE]** Re-opening the Faces solo view orphans a `resize` listener
    (`faces.html:4369-4389`); after close, every window resize throws
    `TypeError` once per orphan for the rest of the session.
21. **[PRE]** `jarvis_agent.py:751` — `tool.prepare()` runs outside any
    `try`, so a prepare-time `ValueError` (e.g. `{"days_ahead":"seven"}`)
    escapes `run_local_turn` entirely, against its own docstring. Reproduced.
22. **[PRE]** `jarvis_email.py:224` — one malformed header charset raises
    `LookupError` (which `errors="replace"` does not cover) and fails the
    whole mailbox read. One sender can break every `email_check`. Reproduced.
23. **[PRE]** `jarvis_research.py:296` — `time.mktime()` on a UTC timestamp
    makes repo age depend on the machine's timezone (±offset, and negative
    ages). Fix: `calendar.timegm`. Reproduced.
24. **[PRE]** Both flash-governor ports count the *first* transition as
    "opposing" (`spec.rs:666`, `faces.html:3072`) despite `spec.rs:618`
    documenting that it never is — consuming one of three budget slots after
    every reset. Errs safe; the comment is simply wrong. Consistent across
    both ports, so no drift.

---

## Checked and found sound

Recorded so it is not re-audited:

- **Every risky Android API call is real**, verified against AOSP source
  rather than memory: `VoiceInteractionSession.onShow(Bundle?, Int)`,
  `startAssistantActivity(Intent)` (the call flagged in the commit message as
  least certain — it exists), `finish()`, the `VoiceInteractionSession(Context)`
  constructor, `VoiceInteractionSessionService.onNewSession`, and
  `RecognitionService`'s exactly-three abstract methods. The manifest
  metadata satisfies `VoiceInteractionServiceInfo`'s parser, which requires
  both `sessionService` and `recognitionService` or it refuses the service.
- **Every Compose/Glance scope use is valid** — all `Modifier.weight` and
  Glance `defaultWeight()` calls sit inside a real Row/ColumnScope, and
  `PillButton` correctly takes the weight as a parameter rather than calling
  it from its own unscoped body.
- **No panic path in `winrt_toast.rs`** — `escape_xml` covers `& < > "`,
  single quotes need no escaping inside double-quoted attributes, and a
  `LoadXml` failure falls through to the plain toast.
- **Markdown → HTML in `main.js:351-430` is not injectable** — `escapeHtml`
  runs before any placeholder is introduced, and a character reference inside
  a quoted attribute cannot terminate it.
- **`jarvis_task_control`'s locking is correct** — every access is inside the
  lock, no nested acquisition, no callback under the lock. Its defects are
  lifecycle (#4), not concurrency.
- **`jarvis_android_control`'s adb shell-safety holds** — `_SAFE_TEXT` /
  `_SAFE_KEYCODE` close the injection hole, and nothing reaches a host shell.
- `rebuilt/jarvis_voice.verify()` fails closed on every malformed input.
  `jarvis_agent`'s `_safe_eval` guards, fail-closed `_gate_check`, and
  `max_rounds` cutoff are all correct.

---

## A note on method

Two auditors reported findings that did not survive verification against the
real file, and are deliberately absent above. The count matters less than the
habit: every item here was re-read in the source before being written down,
and the ones marked *reproduced* were executed. A finding that cannot survive
that is not a finding.
