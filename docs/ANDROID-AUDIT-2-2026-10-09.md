# Android client audit 2 — 2026-10-09

**This machine now has the Android SDK, JDK 17 and `jarvis-client/local.properties`,
so this audit is the first one that could compile and run the app's tests.**

- **The unit tests were run locally, on this branch: `.\gradlew.bat testDebugUnitTest`
  — 1,959 tests, 0 failures, 0 errors, 0 skipped. BUILD SUCCESSFUL in 1m 45s.**
  (Counted from the 178 JUnit XML files the run wrote to
  `jarvis-client/app/build/test-results/testDebugUnitTest/`, not from the console
  summary.)
- **Nothing was installed on a device.** There is no emulator (virtualization is off
  in this machine's firmware) and no phone attached, so **no instrumented test ran
  and nothing was side-loaded.** Every statement about Android's own behaviour
  (notifications, biometrics, bubbles, screenshots, TalkBack) is read, not observed.

**What was audited.** `jarvis-client/` — the app that talks to the backend. Read at
commit `44646f2d` on branch `audit/android-2` (worktree
`.dsh-scratch/android-audit2`). Read-only: **no app change is proposed as a commit
here**, and this branch changes only this file.

**What this audit adds to the first one.** The first audit
(`docs/ANDROID-AUDIT-2026-10-08.md`, PR #125) stated that the large work plates were
"searched for the private-material gates, the stale-link gate and their write calls,
**not read line by line**". This pass read them line by line, plus the three largest
files the first audit did not name in that gap: `HomeScreen.kt` (159 KB — the
largest file in the app), `BrainScreen.kt` (106 KB) and `HistoryScreen.kt` (80 KB).

**Method.** Reading, plus one throwaway probe test. Where a claim could be turned
into a run, it was: the probe exercised the JSON-reading and control flow behind the
one new finding below and passed; it was deleted afterwards and is **not** committed.
Nothing about this app's behaviour on a phone was exercised.

---

## Part 1 — The first audit's 12 findings, today

Checked against the current source, not against its text. "Fixed by" is the merge
commit that landed the fix, checked in the code.

| # | Sev | Finding (short) | Status today |
|---|-----|-----------------|--------------|
| 1 | HIGH | "Send test" claimed success with no notification posted | **FIXED** — PR #128 |
| 2 | MED | A Deny that never reached the PC froze the card | **FIXED** — PR #136 (and #128 for the Deny half) |
| 3 | MED | The Mute tile could send "mute" twice | **FIXED** — PR #128 |
| 4 | MED | Security footer says turning something on is always instant | **STILL PRESENT** |
| 5 | MED | The daily standby card is lost for the day after a restart | **STILL PRESENT** |
| 6 | MED | "Open my spending" answered "only on your PC" | **FIXED** — PR #128 |
| 7 | MED | "Never look at" app picker walks every installed app on the main thread | **STILL PRESENT** |
| 8 | LOW | "Show everything saved automatically" scrolls by index | **STILL PRESENT** |
| 9 | LOW | "Clear the numbers" refills the PC's made-up figures | **STILL PRESENT** |
| 10 | LOW | "Reading…" on the job list can never appear | **STILL PRESENT** |
| 11 | LOW | "Hear it" prints the same result line twice | **STILL PRESENT** |
| 12 | LOW | "Quality" and "Sharpness" are one control under two names | **STILL PRESENT** |

**8 of the 12 still stand** (4 medium, 4 low). The 1 high and 2 mediums the owner
had fixed are genuinely fixed; the third medium (#6) was fixed too, in the same PR
as #1 and #3.

### Fixed, verified in the code

**1 (HIGH) — fixed by PR #128** (`dc6a3b86`). `ScheduleNotifier.post` now returns
`Boolean` and answers it honestly on both refusal paths:
`jarvis-client/app/src/main/java/com/jarvis/client/service/ScheduleNotifier.kt:139-142`
returns `false` when `POST_NOTIFICATIONS` is not granted, and `:174-176` returns
`runCatching { … notify(…) }.isSuccess`, so a throw from `notify` is a `false` too.
The plate reads that answer into a nullable
(`ui/screens/PhoneNotificationsPlate.kt:387`, `:420-427`) and colours the line by it
(`:431-442`), with no "Test notification sent." anywhere in the file.

**2 (MEDIUM) — fixed by PR #136** (`b57476f0`), with the Deny half in #128.
Both decisions now go through one function,
`MainActivity.kt:3525-3542` `decideAndReset`, which awaits the decision and calls the
card's own `onReset` when it did not go out (`:3540`), and it catches a throw as "not
sent" so the flag cannot latch (`:3532-3539`). `denyItem` (`:3561-3562`) returns
`JarvisRuntime.decide(item, approve = false) is ApiResult.Ok`. Both Home call sites
use it (`:3141`, `:3144`).

**3 (MEDIUM) — fixed by PR #128.** `data/QuickTiles.kt:190-193` `muteCommand` drops a
tap aimed at the state already asked for, and `service/LinkTileService.kt:119-133`
holds the asked-for mute locally and renders "Muting…" until the PC's re-read agrees
(`:147-152`, `:175-183`).

**6 (MEDIUM) — fixed by PR #128.** `"spending"` moved into `PLACES` as
`Where.Go(Screen.BRAIN, "spending")` (`ui/OpenPlace.kt:106-111`) and is no longer in
`PC_ONLY` (`:130-145`). The plate it now opens exists on the phone
(`ui/screens/BrainScreen.kt:530`-region, `item(key = "spending")`).

### Still present, verified in the code

**4 (MEDIUM) — the Security footer still contradicts itself.**
`ui/screens/SecurityScreen.kt:257-266` still reads "Turning something on is instant."
`data/Security.kt:337-346` still counts "Swipe to approve or deny" and "Let Jarvis
read this phone's screen" as **loosenings** when switched **on**, and
`MainActivity.kt:3479-3505` still sends every loosening through `ownerCheck`. So two
switches on that screen ask for the fingerprint or PIN on the way **on**, and the
first sentence promises they will not. The behaviour is the careful one; only the
words are wrong. *Smallest honest fix:* delete "Turning something on is instant." and
keep "Turning something off, or making it looser, asks for your fingerprint or PIN
first."

**5 (MEDIUM) — the daily standby card still cannot survive a restart.**
`MainActivity.kt:1479-1486` still caches the offer payload in a plain `remember`
(`:925`) and still adopts it only when `cachedSleepOffer == null`
(`:1482`). The file's own comment at `:919-924` justifies this by saying the block
"re-populates it from the still-cached server data on the next recomposition" — that
is true within one process and gives the day's offer away when the process dies. Once
the PC has served an offer it marks the day as made, so the restart's read returns
nothing and the card is gone until tomorrow. *Smallest honest fix:* give the payload
the same lifetime as its suppression flag (persist the offer's fields, or re-read it
with the day as its key), not plain `remember`.

**7 (MEDIUM) — the "Never look at" picker is still on the main thread.**
`ui/screens/LookPlate.kt:116-118` still calls `store.installedApps(skipNotificationList
= false)` inside a `remember`, i.e. during composition. `data/NotificationAllowListStore.kt`
walks `pm.getInstalledApplications(GET_META_DATA)` and asks each app for its label. The
identical call was moved off the main thread in
`ui/screens/PhoneNotificationsPlate.kt:258-264`, with a comment naming the freeze it
used to cause. *Smallest honest fix:* copy that `produceState` loader here and show a
"Looking for apps…" line until it arrives.

**8 (LOW) — still scrolling by index.** `ui/screens/BrainScreen.kt:712-716` still
computes `here + 1` from the visible item's index, while the row it means
(`item(key = "memory-auto")`, `:729`) is hideable (`net/MenuCatalog.kt:95`,
`net/MenuState.kt:102-104`). With that menu hidden, the button labelled "Show
everything saved automatically" (`net/MemoryUsed.kt`) lands on "Always keep in mind".
*Smallest honest fix:* scroll by key via `ui/parts/ScrollToKey.kt`, as other screens
already do.

**9 (LOW) — "Clear the numbers" is still a misnomer.**
`ui/screens/RetirementPlate.kt:229-238` still resets to
`Retirement.startingValues(d)`, and `net/Retirement.kt:151-153` still returns exactly
the placeholder defaults. *Smallest honest fix:* rename it "Start over".

**10 (LOW) — "Reading…" still cannot appear.**
`ui/screens/TasksPlate.kt:117` still branches on `Tasks.Read.Reading` for a colour,
and `net/Tasks.kt:137` still declares `data object Reading : Read` that nothing
constructs. `read` is only ever assigned `JarvisRuntime.tasks()` (`:66`, `:92`,
`:103`, `:141`). *Smallest honest fix:* delete the state and both branches, or set it
before the first call.

**11 (LOW) — "Hear it" still prints the line twice.**
`ui/screens/VoicesScreen.kt:635` and `:648` still carry the same predicate in the same
column (`saidFor == c.id && said.isNotBlank()` and its mirror); only the first has
`liveStatus()`. *Smallest honest fix:* delete the second block.

**12 (LOW) — one setting, two names.** `ui/screens/FaceEditor.kt:165`, `:174`, `:187`
("Quality") and `ui/screens/AnimalOptionsPlate.kt:184`, `:192`, `:197` ("Sharpness")
still draw `QualityTier.entries.chunked(2)` and still write the same
`copy(quality = it, autoAdjust = false)`; `data/FaceTuning.kt` still has exactly one
stored field. *Smallest honest fix:* use one name for both, or point one section at
the other.

### The two withdrawn claims stay withdrawn

Both were checked again and are **not** findings. Nothing here should be "fixed".

- **"The Mute tile sends the opposite of what it shows."** False, still false.
  `LinkTileService.kt:119` reads the same `attention.muted` field the tile draws
  (`:175-183`), and the only writer is the `GET /api/attention` re-read.
- **"The overnight card is held only in `remember` and its suppression is consumed
  server-side."** Muddled, still muddled. The suppression flag is `rememberSaveable`
  (`MainActivity.kt:932`); what the PC consumes on read is the **offer**. The real
  defect is finding 5, reported above.

---

## Part 2 — New findings, ranked by what hurts the owner

### N1. MEDIUM — "Nothing new" on Watches can be a false all-clear after a failed read

`jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/WatchPlate.kt:77-80`
(the read) and `:188-199` (what is drawn).

```kotlin
when (val r = JarvisRuntime.watchReport()) {
    is ApiResult.Ok -> findings = Watch.findings(r.value)
    is ApiResult.Failed -> Unit // the topics line above already says why
}
```

**What the code does.** `findings` is written only on `Ok`. On a failure the list
keeps whatever it held — and if it held nothing (a fresh visit, or a report the phone
cannot parse), the screen draws `Text("Nothing new since you last marked the list
read.")` at `:191-195`. No error line is produced anywhere: `readError` is set only by
the *topics* read above (`:74-75`), and the comment's claim that "the topics line above
already says why" does not hold when `GET /api/watch` succeeds and `GET /api/watch/report`
alone fails.

**What the UI promises.** "What is new" is the whole point of the plate, and line
`:183` promises "Looking here marks nothing read. Only \"Mark these read\" does." A
read that did not happen is presented as a read that came back empty — and the empty
sentence is the reassuring one. `Watch.findings` (`net/Watch.kt:108-110`) also returns
`emptyList()` for any body without a `findings` or `items` array, so a shape drift reads
the same way.

**Proven, not asserted.** A throwaway probe test (written, run, then deleted — it is
not in this commit) exercised the two halves: `Watch.findings` on `{"ok":true}` and
`{}` both return an empty list, `Watch.failure` returns null for everything except
`NotFound`/`NotAvailable`, and the screen's own state machine keeps the previous list
across a failed read. All four probes passed; `.\gradlew.bat testDebugUnitTest --tests
"com.jarvis.client.ZZAudit2ProbeTest"` was BUILD SUCCESSFUL. This is a run, not a
reading, for the JSON layer and the control flow; whether the owner's PC ever fails
that one route is a runtime fact.

**Smallest honest fix.** Give the report its own line, as every other plate does:
`is ApiResult.Failed -> { findings = null; reportError = JarvisRuntime.noticeFor(r.error) }`,
draw `reportError` where `findings == null`, and make `list == null` draw a failure
sentence rather than nothing (the `when` at `:189-195` already has that branch; it is
unreachable today).

### N2. LOW — Watches' "What is new" heading shows stale rows over a failed refresh

`WatchPlate.kt:77-80` and `:172-199`. Same root cause as N1, different symptom: with
rows already loaded, a failed report leaves them on screen indefinitely, under a
heading that says what is new, with no age line and no error. `InboxScreen` solved the
identical problem properly (`ui/screens/InboxScreen.kt:187-201`, `:444-488`): it says
which list could not be read, says "What is shown below is from the last read that
worked", and offers Retry. *Fix:* one line saying the list could not be refreshed.

### N3. LOW — the "open the approval" scroll counts the list's own items by hand

`HomeScreen.kt:1045-1059`. `leading` is a literal sum of ten conditional expressions
(`if (busy) 1 else 0` …) that must equal the number of list items above the approval
cards, and the file's own comment says so: "Adding an item to this list above the cards
means adding it here too." I checked it against `ConversationList`
(`:1252-1305`) and **it is correct today** — all ten are real: stop-everything,
lockdown, pc-watching, phone-watching (which is one item whether the sign or the offer
is drawn, `:1268-1272`), task-controls, quick-note, pc-media, inbox-tidy, notice,
approvals-off, then the "Waiting on you" label. This is reported as a hazard, not a
current defect: it is the same bug class as the first audit's finding 8 — arithmetic
that silently opens the wrong row — in the one place the owner is sent by a
notification to decide something. *Smallest honest fix:* scroll by the card's own key
instead of by index, as `ui/parts/ScrollToKey.kt` does.

### N4. Cosmetic — a condition the compiler proves is always true

`ui/screens/ChatbotPlate.kt:241`: `if (showCompare && c != null)`, where `showCompare`
already requires `c != null` (`:230-231`). The build prints
`ChatbotPlate.kt:241:40 Condition is always 'true'.` Harmless, and worth deleting so
a real warning is not lost in it. Two other warnings the same build prints are in
dead branches, not live defects: `VoiceTrainingScreen.kt:484`, `:508`, `:538` are
inside `current != null` arms of a `when` whose `current == null` arm
(`:469-473`) makes them unreachable, and `HistoryScreen.kt:276` is an empty `else`
that deliberately does nothing.

---

## Part 3 — Looked at and found clean

Each of these was read line by line in this pass. One line each; no padding.

- **`ui/screens/QuizPlate.kt` (1,225 lines)** — clean. The Keep sheet's ticks, the
  crisis path, the Spanish accents and the YouTube block all gate writes on `canAct`
  and clear their words when the lists hide (`:154-156`); `open!!` at `:502` is guarded
  by the `when` at `:283`.
- **`ui/screens/DecksPlate.kt` (887)** — clean. Hidden mode closes the review, the card
  list and the confirm dialogs together (`:132-138`); every write goes through a
  `canAct`/`busy` guard.
- **`ui/screens/ChatbotPlate.kt` (778)** — clean apart from N4. Limits, compare picks
  and the never-send words are all re-read from the PC and hidden with the lists.
- **`ui/screens/ProjectsPlate.kt` (711)** — clean. The private-mark offer, the Shareable
  switch and the delete confirmations all match `docs/PROJECTS-DESIGN.md`'s rules, and
  a coding project's folder and a benchmark's command are honestly labelled
  "Set on your PC".
- **`ui/screens/GoalsPlate.kt` (592)** — clean. "No card" is accurate for creating a
  goal and ticking a step; `acceptGoal` raises the scheduler's one card and the plate
  says "Waiting for your approval" (`:374-377`).
- **`ui/screens/ProgressPlate.kt` (566)** — clean. The private gate is one rule shared
  with the desktop (`:105-148`, `:172-174`, `:223-224`); the picker is not offered while
  hidden (`:154`).
- **`ui/screens/SupportPlate.kt` (534)** — clean. Never an Accept — accepting is only
  ever the offer's own card (`:323-334`); the transcript and summary wear "outside text"
  plates and hide with the lists.
- **`ui/screens/BriefingPlate.kt` (357)** — clean. Its `hide()` in `net/Briefing.kt:286-290`
  keeps only the summary and drops every line, which is exactly what
  `backend/jarvis_briefing.py:46-48` documents as the contract ("lines (`items`), never
  the summary").
- **`ui/screens/WatchPlate.kt`** — clean except N1/N2.
- **`ui/screens/SharedPlate.kt` (183)**, **`UsedMemoriesPlate.kt` (273)** — clean. Forget
  asks first and a fact no longer in use offers nothing.
- **`ui/screens/TopicsPlate.kt` (1,057)** — clean. The four-choice picker, "Show them",
  "Check these" and the delete-with-a-home all refuse while hidden and read the list
  again after a `202`; keyword editing is honestly absent and says so.
- **`ui/screens/ComingUpPlate.kt` (512)**, **`InboxScreen.kt` (518)**,
  **`SpendingPlate.kt` (364)**, **`ForgetRangePlate.kt` (383)**,
  **`AutoLearnPlate.kt` (577)** — clean. Inbox is the model the rest should copy: it
  names each list that failed, says whether stale rows are on screen, and offers Retry.
- **`HomeScreen.kt` (3,563; the largest file in the app)** — clean apart from N3. The
  composer, the approval queue, the used-memories list, "Where this came from", the
  spending table and the inbox-tidy strip all gate on `state.link == CONNECTED &&
  !state.stale` and route through `JarvisRuntime`'s own refusals.
- **A whole-repo check of the five non-negotiables, again:** no speech-to-text on the
  phone (the recogniser is still a stub that errors, `assistant/JarvisRecognitionServiceStub.kt`,
  and `audio/Recorder.kt:23` says so); no browsable model catalogue; no memory graph;
  no bulk approve and no control that clears a rush latch (`data/QuickTiles.kt:21-25`
  states the ban and `QuickTilesTest` holds the safe list to five); `X-Jarvis-Client: hud`
  is added in the one place requests are built (`net/JarvisApi.kt:319-321`) and nowhere
  bypasses it; and no token or key is logged or written in plain text.
- **Writes that are correctly held on a stale link** — spot-checked in
  `JarvisRuntime.kt`: `addWatch`:4045, `clearList`:5052-5053,
  `addStandbySchedule`:5106, `setBriefing`:7305, `setBriefingSenders`:7326 (ON only).
- **The build itself** — no compile error and no warning that points at a live defect
  (the two that look like one are in Part 2, N4).

---

## Part 4 — Needs a real phone or emulator

None of this can be settled here: **no emulator (virtualization is off in this
machine's firmware) and no attached phone, so no instrumented test ran.**

1. **`POST_NOTIFICATIONS` on the owner's phone today**, and whether "Send test" now
   tells the truth on the device that matters. The code path is fixed (finding 1); the
   message still has to be read on a phone with notifications switched off.
2. **Whether `/api/watch/report` ever fails or changes shape on the owner's PC**, which
   decides whether N1 fires in practice. The phone-side behaviour is proven; the
   trigger is not.
3. **App lock really blocks screenshots and the recents thumbnail**, and the Keystore
   and biometric prompt still behave after a reboot.
4. **Whether a Floating Jarvis bubble appears at all on Android 11+** — the project's
   own note says try it on a real phone (`service/WakeWordService.kt:636-639` records
   the missing `MessagingStyle` as the second, unfixed blocker).
5. **SSE reconnection and the stale-link gate across a real half-open socket**,
   including the 70-second keepalive watchdog (`JarvisRuntime.kt:1111-1212`). The gate
   is read, not exercised.
6. **Live audio**: the 2-second voice check, the headset button, the hand-off frames
   and the captcha hand-off.
7. **TalkBack ordering and announcements** — including N1's fix, which should be heard
   as well as seen.
8. **Whether the "Never look at" picker (finding 7) is visibly slow on the owner's
   phone.** The main-thread call is confirmed by reading; the jank is not observable
   here.
9. **Whether a given menu is hidden for the owner** — menu visibility is server-driven,
   so findings 8 and 12 may or may not be reachable in his configuration.

---

## Summary

- **8 of the first audit's 12 findings still stand** — findings 4, 5, 7 (medium) and
  8, 9, 10, 11, 12 (low). The one high and the three mediums that were fixed are
  genuinely fixed in the code, each named above with the PR that landed it.
- **Both withdrawn claims stay withdrawn** and are not to be "fixed".
- **Four new findings**, ranked: **N1** (medium, proven by a throwaway test) and
  **N2, N3, N4** (low / hazard / cosmetic).
- **The large plates the first audit did not read are, with those exceptions, clean.**
  The two most careful screens in the app are `InboxScreen.kt` — which says per list
  what failed, whether the rows on screen are stale, and offers Retry — and
  `ForgetRangePlate.kt`.
- **Nothing here breaks a CLAUDE.md non-negotiable.**

*Read line by line, and the unit tests were run, on 2026-10-09. Nothing was installed
on a device.*
