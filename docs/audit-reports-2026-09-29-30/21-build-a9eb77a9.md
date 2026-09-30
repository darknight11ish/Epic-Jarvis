# Report 21 (build), agent a9eb77a9, 2026-09-29T21:29Z

> **What it was asked** (first 600 characters of the task): You are fixing phone (Android, Jetpack Compose) UI problems in the Jarvis repo; this worktree is based on branch ccr-a9b557ac-cpnbwx (commit 6494da8a). Read CLAUDE.md 'Explain things simply' and 'How the Android apps get built' first: there is NO Android compiler here (GitHub CI compiles), so read every edit carefully by eye, keep to APIs already used in the same file, add matching imports, and keep pure logic in files with JVM tests. The owner is a beginner developer: plain words, say what to do next. Do not change any safety rule or approval logic. Another worker is rewording strings in Scre

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Committed as 0db33d8a in the worktree (not pushed). No Android compiler here, so none of the Kotlin has been compiled; CI has to confirm it.

Checks run and passing: test_blend_voices (106), test_kokoro (159), test_voices (140), test_voice_contract (737), check_parity (no undecided drift). I did not run the other tools/gen_*_cases.py --check scripts (the shell refused the loop). I did regenerate the two fixtures affected by the new backend field: phone-voice-cases.json and voice-training-cases.json. JVM tests for the new pure logic are in the new src/test/.../ScreenPlateTextTest.kt, not run here.

**By item**
1. Stop watching now shows a red polite-live-region line under the sign when the call fails ("Could not reach your PC to stop it. Try again, or press Stop everything on the PC."). `JarvisRuntime.stopScreenWatch()` now returns `String?`, and it still re-reads status either way. The sign is never marked off by the phone. The line clears on the next tap. `HomeActions.onStopWatching` is now `suspend () -> String?`; the phone-watch Stop is wrapped so it returns null.
2. Hear it: the status line now sits under the tapped voice's row and stays there (errors stay next to the voice that caused them). While a sample plays or the PC is making it, that row's button becomes "Stop" (calls `JarvisRuntime.voice.stopSamples()`). The other rows stay disabled while a sample runs. The "Hear ${label}" TalkBack label is kept, and Stop reads "Stop the sample of ${label}".
3. Copy the line: the backend did not send the line, so I added `make_line` to `speaker_view()` in `backend/jarvis_voices.py`. It carries `K.MAKE_LINE` only while Ashby and Clara are not "ready" on a v1.0 pack, and is "" otherwise. Updated `docs/JARVIS-API.md`, added a check to `test_blend_voices.py`, and regenerated the two fixtures. The phone reads it in `CustomVoices.Speaker.makeLine` and shows a "Copy the line" button plus "Paste it into PowerShell on your PC, then restart Jarvis." **The desktop does not show it yet:** its voice code does not render the speaker note at all, so it needs a small follow-up.
4. Done as you specified: no extend button. The PC sign on Home appends "Extend it on the PC." to an "Ending soon" line, in the plate's own text. `ScreenRules` is untouched.
5. The hint is shown only when Jarvis does not hold the assistant role. It reuses `PlatformReadiness.assistantRoleHeld(context)`, which already existed.
6. "Waiting for the connection to your PC." now shows under picture mode's switch (when it is greyed for the link and not waiting on a card) and under Home's "Watch this phone with me" button when the link is not connected. I did not touch the Obscura switch.
7. The PC sign has its own title in `titleSmall` in the warning colour, plus a second line "Your PC's screen". The phone-watch sign does not get that line. `ScreenRules.TITLE` is unchanged.
8. The notifications allow list now shows the app's real name, falling back to the package name. To do this I made `LookPlate.labelOf` `internal` so both plates share it.
9. TalkBack labels "Remove ${app}" and "Add ${app}" are set through `semantics` on the buttons in both LookPlate and PhoneNotificationsPlate.
10. Both pickers have a "Search apps" `TextInput` above the 240 dp list. It filters by app name, then package name, through `ScreenPlateText.filterApps`. If nothing matches, it says "No app matches that."
12. Picture mode says "This also needs the Looking at your screen switch on the Security screen." and LookPlate says "Picture mode is under Settings." Neither title was touched.
13. No change needed. `MainActivity.onResume` already bumps `permissionTick`, and `usageAccess` is computed with `remember(tick)`, so the plate is re-read when the owner comes back from Android's Usage access screen.

**Skipped:** 11, as you instructed (the Obscura files were not touched).

**Where I am unsure the Kotlin compiles**
- HomeScreen: `PcWatchingPlate` now has a default parameter and a lambda `{ actions.onStopPhoneWatch(); null }` passed where a `suspend () -> String?` is expected. This should be fine. It also uses `PlatformReadiness` (already imported) and `LocalContext.current` inside `PhoneWatchStartPlate`.
- MainActivity: the `onStopWatching = { JarvisRuntime.stopScreenWatch() }` lambda now returns `String?`. Only a trailing comment changed.
- VoicesScreen: new imports `LocalClipboardManager`, `AnnotatedString` and `liveStatus`, copied from the `ScreenPicturePlate` pattern. `hearing`, `saidFor` and `said` are plain `var ... by remember`, used inside the `for` loop.
- PhoneNotificationsPlate: `val appName = remember(pkg) { labelOf(context, pkg) }` sits inside `allowed.forEach { ... }` (an inline lambda in a composable). It should be fine, but it is the most unusual construct I added.
- LookPlate and PhoneNotificationsPlate: `TextInput(value=, onValueChange=, placeholder=)` matches its definition in Parts.kt. `ScreenPlateText.filterApps` is generic, called with `{ it.label }, { it.packageName }`.
- The new text and filter helpers live in `net/ScreenPlateText.kt`.
