# Report 35 (audit), agent ad4dc765, 2026-09-30T06:58Z

> **What it was asked** (first 600 characters of the task): Read-only audit of the ANDROID app notifications in /home/user/Epic-Jarvis/jarvis-client (read CLAUDE.md first: rules, the plain-words rule for a beginner owner, decisions on notifications: urgent alerts 'keep ringing until seen', late alarms 'ring only if at most 10 minutes late else silent notification saying when it was missed', smartwatch 'every notification stays on the phone by default', phone-notification READING (a different feature: reading OTHER apps' notifications), App lock / 'Hide memory lists and chat history' hiding content, screenshots blocked, approval notifications never appr

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Phone notification audit (code read only; no device, no Android run; nothing changed). Paths are under /home/user/Epic-Jarvis/jarvis-client/app/src/main/java/com/jarvis/client/.

**Table.** Lock-screen column: "own text" means Android's default private view, with no public version set.

| Notification | Trigger | Channel / importance | Lock screen | Actions | Switch to disable | Issues |
|---|---|---|---|---|---|---|
| Link status (EventService.kt:415) | Service running | jarvis_link, LOW, silent | own text ("2 approvals waiting") | none | Stop the link | none |
| Approval (ApprovalNotifier.kt:257) | Pending card | jarvis_approval HIGH, or jarvis_approval_quiet LOW | PRIVATE + public "A decision is waiting. Unlock to see it." | Deny only, and only if `notice.denyOk` (:315) | none | 3, 9 |
| Approval summary (:338) | 2 or more pending | HIGH or LOW | PUBLIC "N approvals waiting" | open | none | 3 |
| Timer, reminder, briefing (ScheduleNotifier.kt:133) | PC `schedule` event | jarvis_approval (HIGH, sound) | PRIVATE + public kind words | Snooze 10 min (not on briefing or missed) | none | 2, 4, 5 |
| Alarm, urgent tell-me, find-phone (:189) | same | jarvis_alarm HIGH, alarm sound, vibration pattern, FLAG_INSISTENT | PRIVATE + public | Stop, Snooze | none | 2, 6 |
| Missed notice | Heard over 10 min late | approval channel, `setSilent` | as above | none | none | 4 |
| Chatbot or support line (ChatbotNotifier.kt:91) | Session running | jarvis_link LOW, silent, ongoing | PRIVATE + public fixed words | Stop | none | 1 |
| Site needs you (HandoffNotifier.kt:77) | Captcha or sign-in page | jarvis_needs_you HIGH | PRIVATE + public | "Solve it here" (opens the app) | none | 8 |
| Live ongoing (LiveService.kt:576) | Live on | jarvis_live LOW | PUBLIC, fixed words | End Live, Mic off, Stop talking | End Live | none |
| Live move offer (:688) | "Hey Jarvis" while Live runs on the PC | HIGH, times out after 30 s | own text (fixed words) | opens the app | none | 8 |
| Live Resume (:734) | Live ended by itself | DEFAULT, silent, times out | PUBLIC | Resume Live (opens the app) | none | 8 |
| Wake-word, floating avatar, screen-watch (WakeWordService.kt:790, AvatarOverlayService.kt:337, ScreenWatchService.kt:339) | Feature on | LOW, silent | own text, or PUBLIC for screen-watch | Stop | the feature itself | 1 |
| Wake restart notice (WakeResumeNotifier.kt:55) | Boot | wake channel LOW, silent | own text | tap | none | 1 |

**Findings, worst first**

1. **Broken: two notifications share id 0x3200.** ChatbotNotifier.kt:42 and WakeResumeNotifier.kt:37 both use `NOTIFICATION_ID = 0x3200`. Chatbot `cancel()` (:114) would remove the "Jarvis stopped listening after restart" notice, and the reverse. The comment at WakeResumeNotifier.kt:36 claims the id is "apart from ScheduleNotifier's", but nobody checked it against ChatbotNotifier. Sure: high, from the ids. Untested on a device.
2. **Broken: late-ring rule applied to only one of the ring paths.** `heardLate` is called only at JarvisRuntime.kt:4864. The urgent tell-me path (`onTellMeMatched`, :4828) and the briefing (:5561) never check it. An urgent alert heard 3 hours late rings as if it were now. The decision (CLAUDE.md, 2026-09-26) says "a late alarm rings only if at most 10 minutes late". That covers alarms and reminders, and tell-me is a judgement call, but the code is silent on it. Sure about the code path. Whether the owner meant to include tell-me is a decision.
3. **Confusing: there is no per-kind control.** In the Kotlin sources I searched, I found no in-app switch for a kind of notification, no quiet hours, and no test notification. Nothing links to a per-channel system screen. The only `ACTION_APP_NOTIFICATION_SETTINGS` (MainActivity.kt:3352) is a fallback for the bubble screen. The Checks button (:1846) only re-asks for the permission. After two refusals Android shows no dialog, so the button does nothing (the comment at MainActivity.kt:1356 admits this). Sure.
4. **Confusing: reminders and briefings use the "Approvals" channel.** ScheduleNotifier.kt:133 posts at HIGH with sound on `jarvis_approval` (named "Approvals"). A timer and a decision cannot be tuned separately. Turning the "Approvals" channel off in Android also silences reminders. Nothing separates the "quiet" tier either. Sure.
5. **Confusing: the approval channel has no notification-preference setting of its own.** Its importance, and the fact that `jarvis_approval_quiet` was added as a second channel to work around this, are explained at JarvisApp.kt:69-85. The owner can adjust channels only in Android settings, and the app never points there (finding 3).
6. **Broken or risky: urgent alerts do not bypass Do Not Disturb.** This is the designed limit (ScheduleNotifier.kt:173: alarm usage, "nothing here overrides it"). But a "keeps ringing until seen" urgent alert can be silenced by the phone's DND if "Alarms" is off there. The app never warns the owner (`ACCESS_NOTIFICATION_POLICY` is not requested). It is truthful in code comments and nowhere in the UI that I read (not checked in the strings).
7. **Broken (probable): foreground id 0x4A57 is used twice.** WakeWordService.kt:856 and ScreenWatchService.kt:369 both use it. If both run, the second replaces the first's notification, and stopping one removes the shared notification while the other keeps running. I did not verify whether the two can run at once (not checked).
8. **Could be nicer: Live offer and Resume skip the permission check.** LiveService.kt:684 and :721 call `manager.notify` with no `POST_NOTIFICATIONS` check, and HandoffNotifier's captcha alert has no Deny path. No secrets leak. Live offer and Resume text is fixed words.
9. **Confusing: an approval notification is not made generic under App lock.** `textFor` (ApprovalNotifier.kt:242) always shows the desktop's `notice`, whatever App lock or "Hide memory lists and chat history" says. Schedule notifications check both (JarvisRuntime.kt:4816, `locked = security.appLock || security.privateLists`). The notice is built from the action name only, so the leak risk is low. It is inconsistent, and the shade on an unlocked phone shows it. The lock-screen public version is correct.

**What checked out (quotes)**
- No notification can approve. ApprovalNotifier.kt:294: "Deny only, never Approve". Deny waits for a live link, and `decide` refuses on a stale link (EventService.kt:120-129). Snooze is held the same way (:145).
- Late alarm rule for alarms and reminders is real: `LATE_RING_LIMIT_S = 10 * 60` (Schedule.kt:803), with a silent "Missed at HH:MM." notice.
- Watch bridging: every builder calls `.setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())`. Live, screen-watch and the handoff alert are always local-only.
- Every PendingIntent uses `FLAG_IMMUTABLE`. No `USE_FULL_SCREEN_INTENT`, and no full-screen intent anywhere. Foreground service types are declared in the manifest (specialUse, microphone, mediaProjection).
- POST_NOTIFICATIONS is asked when the phone is paired (MainActivity.kt:1370). Approval, Schedule, Chatbot, Handoff and WakeResume notifiers each check it and log. ApprovalNotifier counts the silenced ones, but I found no screen except Checks that shows the count.
- Restart survival: ApprovalNotifier `restore()` rebuilds its ids from notification extras (:91). Schedule ids are tag-based, so they survive.
- Resolved on the PC: approvals are cancelled by `sync` (:158). Timers, alarms and reminders are cancelled on a `changed` event (JarvisRuntime.kt:4777). A tell-me match is deliberately kept.
- Rule 2 and rule 4: no tunnel code touched. Notifications fire only from the paired PC's events.
- Not checked: the exact wording in strings.xml for channel descriptions; whether the two colliding services can run together; behaviour on Android 14+ for setOngoing on the alarm.

**Owner decisions**
1. Should the phone get a "Notifications" screen (per-kind on/off, link to each Android channel, a test button)?
   - Recommended: yes, small. One row per kind with an "Open Android settings" link for that channel.
   - Or: only add the links, no switches.
2. Should an urgent "tell me when" that is more than 10 minutes late follow the same silent "Missed" rule as alarms?
   - Recommended: yes, for consistency.
   - Or: keep ringing, because an urgent alert is still worth it late.
3. Should reminders and the briefing get their own channel so approvals are not silenced with them?
   - Recommended: yes, a new channel id (an existing channel's importance cannot be changed by the app).
   - Or: leave as is.
