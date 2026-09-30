# Report 51 (build), agent a9f5efff, 2026-09-30T07:20Z

> **What it was asked** (first 600 characters of the task): You are in a git worktree of Epic-Jarvis. Read CLAUDE.md fully first (rules; plain words for a beginner owner; both-apps rule; 'How the Android apps get built': there is NO local Android compiler, GitHub CI is the only compiler, so read every Kotlin file you touch back carefully: imports, parameter names, call sites, nullability; write pure-Kotlin unit tests where logic can be isolated, following existing tests in jarvis-client/app/src/test). Do NOT push or open a PR; commit on your worktree branch, report branch+sha. Other agents edit backend/*.py, jarvis-desktop/ and scripts/: do NOT touch t

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Branch `worktree-agent-a9f5efff8512c3aa5`, commit `ceaf1db6`. Not pushed. Only `jarvis-client/` was touched. `tools/check_parity.py` is clean. No `gen_*.py` fixtures are affected. **Nothing here was compiled or run: no Android compiler, so CI is the first compile.** I read each changed Kotlin file back for imports, names and nullability, and checked the existing source-reading tests (LiveExtras, CardWords, Goals, AppProjects) still match the edited files.

**1. Live launches (`InternalLaunch.kt` new, `MainActivity`, `LiveTileService`, `LiveService.showResume`, `HandoffNotifier`)**
- Design: the app makes a random 256-bit secret once and keeps it in private storage (not per process, so an old notification still works after a restart). The Live tile, the "Resume" notification and the handoff alert put it in their intents.
- `InternalLaunch.decide()` is the pure decision. START/RESUME_LIVE without the secret only open the Live screen, where the owner presses Start. OPEN_HANDOFF without it is ignored. A re-created activity never starts Live.
- Static shortcuts already use OPEN_LIVE, never START_LIVE; a new test pins that.
- Verified from source: START_VOICE only opens Home, QUICK_NOTE only opens the note box, and ASK_BRIEF_ME / ASK_WHAT_DID_I_MISS ask one fixed sentence and read no extras. No microphone, and no incoming text is used.
- Not changed, for you to decide: the "Talk about this in Live" share (`ShareToLive`) can still start Live once unlocked, if another app fires it. Its text is already treated as outside text.

**2. Watch (`ScreenWatchService`, `net/ScreenWatch.kt`)**
- The service now ends the session ("link to your PC was lost") after 10 s of a down or stale link; a link that recovers in time cancels the countdown.
- `HOW` and the notification text now say Watch cannot see password boxes, with "Close pages with password boxes first. Jarvis cannot pause on them." No existing test pinned `HOW`. New tests are in `ScreenWatchTest`.

**3. Widget and tile (`ApprovalWidgetRules.kt` new, `ApprovalWidget`, `QuickTiles`, `LinkTileService`)**
- Under App lock or hidden lists, or when settings are unreadable, the widget shows only "A decision is waiting" and Deny opens the locked app.
- The Mute tile asks for the phone unlock when App lock is on and the phone is locked (`QuickTiles.muteNeedsUnlock`).
- Tests: `ApprovalWidgetRulesTest`.

**4. Concurrency**
- `startStream` and `stopStream` are now `@Synchronized`, and the four job fields are `@Volatile`.
- `ScreenWatchService.ended` is an `AtomicBoolean` with `compareAndSet`.
- `EventService.start` failure now sets `lastStartFailure`.
- `AvatarOverlayService` sets `avatarView` only after a successful add.
- `LiveService` wraps `rec?.release()` in `runCatching`.

**5. Accessibility**
- `GoalsPlate`, `HistoryScreen` and `MannerPlate` rows are now `toggleable` with the inner control's `onCheckedChange = null`.
- `JarvisTheme` re-reads reduced motion on `ON_RESUME`.
- (c) No other bare `Checkbox`, `Switch` or `RadioButton` exists in `jarvis-client`; the other uses already have `toggleable`.

**6. Notification ids**
- `service/NotificationIds.kt` now holds every id, and all users point to it.
- Screen Watch's foreground id is now 0x4A59 and WakeResume's is 0x3203.
- `NotificationIdsTest` checks that no two match, that the list is complete, and that all sit below the approval range. The stale comment is fixed.

**Owner decisions found:** 2026-09-28 "under App lock the widgets' buttons open the locked app first"; 2026-09-28 Live extras (tile, resume notification); 2026-09-28 "Watch pauses on password fields", which the phone cannot do, so it now says so.

**Paste-ready note for CLAUDE.md:**
Built 2026-09-30, the phone audit fixes (`jarvis-client/`, commit ceaf1db6, uncompiled until CI runs). Start-Live, Resume-Live and the handoff screen are honoured only with an app-private secret (`InternalLaunch`), so other apps cannot start the microphone; static shortcuts only open screens. Phone Watch ends after 10 s of a lost link and says it cannot see password boxes. The approval widget shows only "A decision is waiting" and its Deny opens the app under App lock; the Mute tile asks for the phone unlock. Stream start/stop is now single-file, and small leaks were tidied. Three unlabeled switches and checkboxes now read to TalkBack, and reduced motion is re-read on resume. Every notification id lives in `NotificationIds` (two clashes fixed), with a test.
