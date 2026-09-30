# Report 49 (audit), agent a1ef1de0, 2026-09-30T07:18Z

> **What it was asked** (first 600 characters of the task): Read-only audit of how APPROVAL CARDS look and behave in the apps in /home/user/Epic-Jarvis (read CLAUDE.md fully first; verify each claim with file:line + quote; 'not checked' honestly; do not run Android/Windows; change no files). Another agent audits the card CONTENT and counts per task on the backend; YOU audit the UX in the apps: phone (jarvis-client: ApprovalCard.kt, approval screens, swipe-to-approve and its setting, ApprovalNotifier, approval widget, Deny-only notification, risky-card fingerprint/PIN flow, 'Turn on signed approvals', decisionBlocker on stale link, app-merge whole-chang

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

**Approval-card UX audit: code walk-through only.** I read the code and did not run the phone app, the desktop app or Windows Hello. `python3 tools/check_parity.py` says "No undecided drift", and the Deny/Approve/"Needs your OK" wording matches on both sides (CardWords.kt:29-32, card-words.js:28-32). All paths are under /home/user/Epic-Jarvis; "P/" = jarvis-client/app/src/main/java/com/jarvis/client/, "D/" = jarvis-desktop/src/.

**Verdict.** The safety design is strong. Decisions are bound to the card id (not list position), the stale-link gate is enforced in the runtime as well as in the UI, and Approve is never offered on a notification. The efficiency problems are small and fixable, and there is one real bug.

**Top findings, by severity**

1. **BROKEN (fairly sure, from code): a cancelled fingerprint kills the card's buttons on the phone.**
   - P/ui/approval/ApprovalCard.kt:145 `var decided by remember(item.id)` is set true at tap (lines 205-214) and never reset.
   - Both buttons and swipe are gated on `!decided` (lines 239, 547-548).
   - Approve on a risky card runs the fingerprint check in MainActivity.approveItem (:3133). Cancelling returns silently (`Verdict.Stop(null)`, Security.kt:222). Any refused decision behaves the same: an offer-signed-approvals notice, or a failed send.
   - Result: the card sits there with greyed Approve and Deny and no message.
   - It only recovers when the card leaves composition (rotate, or navigate away and back). The manifest has no `configChanges`.
   - Smallest fix: reset `decided` when the decision fails or is cancelled, or drive it from `JarvisRuntime.deciding`.
2. **Notification tap does not land on the card (fairly sure).**
   - HomeScreen.kt:992-998 counts the items above the cards as `leading` and scrolls to `leading + index`. Its own comment says "Adding an item to this list above the cards means adding it here too".
   - The list now always has `quick-note` and `pc-media` above the label (:1225, :1229). It also has optional stop-everything, lockdown, watch signs and inbox-tidy items. None are counted.
   - So the scroll lands about 2 or more items too early. The card is outlined, but not at the top.
   - Fix: build the index from the real list, or use a `LazyListState` key lookup.
3. **Routine cards are silent and time out in 3 minutes.** (Owner call.)
   - Normal-weight cards use the low-importance channel (JarvisApp.kt:88-90). "Normal" here means undoable and staying on the PC. The desktop toast is silent too (winrt_toast.rs:158).
   - The PC's approval time limit is about 180 s (PendingRows.kt comment).
   - So a routine card can expire unseen, and the owner then sees "Expired — ask the desktop to raise this again."

**Time to decision**

| Device | Path | Taps |
|---|---|---|
| Phone, normal card | tap notification, Approve | 2 |
| Phone, risky card | tap notification, Approve, fingerprint (or signed-approval fingerprint) | 3 |
| Phone, Deny | notification's Deny button | 1 (waits up to 20 s for the link; toast says the result) |
| Phone, Deny from widget | Deny button | 1 |
| Desktop widget, plain card | Approve | 1 |
| Desktop, email/heavy/App-lock card | widget Approve opens the bar, then Approve, then Windows Hello | 2 to 3 |
| Desktop, keyboard | none: no approve/deny shortcut by design; Esc only parks the card | Tab + Enter |

**Table**

| Screen | What works | Problems |
|---|---|---|
| Phone card (ApprovalCard.kt) | Title, reach badge, risk line, rush chip, expiry bar and countdown. Buttons are 48 dp+, Deny left, Approve right, and shape differs (filled vs outlined). Swipe threshold is 96 dp; swipe is never on for rush-latched cards; the card springs back and is removed only when the PC confirms. `_deciding` latch stops double-tap. Heavy cards: Approve locked 2 s and until detail is opened. | Bug 1 above. `ReachBadge` (:790-795) is an if/else chain, so an outbound and irreversible card shows only "LEAVES THIS MACHINE" and the "NO UNDO" cue is lost. Approve is solid green even on risky cards (Parts.kt:437). Buttons are only 8 dp apart (:546). Buttons are not pinned: a long summary is a plain Text with no limit (:356), so Approve can be far down (the desktop pins its buttons, style.css:1488). Approve does not say a fingerprint follows. |
| Phone list (HomeScreen.kt:1263-1312) | Count kicker ("N waiting on you"), footer said once, `key = it.id`, stable server order. | Finding 2. Cards do not say which task or device raised them. A card decided elsewhere slides the next card up (200 ms animation), so a tap could land on a different card. The id binding keeps it correct, but the owner may not have read that card. There is no post-swap tap guard except the 2 s heavy delay. |
| Phone notification and widget | Private lock-screen version; title comes from the PC's `notice`, never row text; Deny hidden if `deny_ok` is false; summary at 2+ cards; widget says "Not checked yet" instead of "Nothing waiting"; the widget's Approve is "Review" and opens the app. | Notifications are re-posted for every card on every sync (ApprovalNotifier.kt:161-165). ApprovalWidget.kt does not check App lock at all, and its Deny acts in one tap. That conflicts with the owner's 2026-09-28 rule that widget buttons only open the app under App lock. |
| Phone Windows-style checks | Prompt shows title plus `risk.why`. Cancel is silent. "No lock" gives a plain sentence with a settings button. Signed approvals: "Turn on signed approvals" appears as a button on the Home notice (HomeScreen.kt:562). | Silent cancel plus finding 1. The prompt shows only the title and risk line, not recipients or key facts. |
| Phone Inbox | Read-only past approvals ("Approved / Denied / Timed out · age · device"), InboxScreen.kt:383. It is built. | It is only reachable via Inbox. |
| Desktop bar (main.js) | Verbatim email text (`pre-wrap`), 300 px scroll box, sticky buttons, "N of M", risk line plus expiry clock, heavy gate (2 s plus scroll), 409 gives "Already handled somewhere else", failed sends release the latch, Esc parks and does not deny. | Cards stay hidden behind Esc with only a bar hint. The card raises no sound of its own. The main.js comment mentions Ctrl+Enter, which submits the prompt and is not related to cards. |
| Desktop widget (widget.js) | Two-line detail clamp (widget.css:552-565). Email, heavy and App-lock Approve is redirected to the bar. Under App lock only a title shows, with Deny still available. "1 of N". | The widget shows `queue.items[0]`. If it is decided elsewhere, the next card appears in the same spot, and a plain card there takes one click to approve. The widget cannot show a long command or file list at all, so its Approve is only safe for cards where two lines suffice. |
| Desktop past approvals | "Activity" in Brain (brain.js:7272), read-only. | `history` rows and the decision device are partly assumed (comment says "not confirmed"). |

**Rule 4 note.** Deny is blocked on a stale link everywhere (phone `decisionBlocker`, desktop `syncApprovalButtons`, Rust `answer_approval`). That is stricter than necessary; the notification Deny waits up to 20 s. It is safe, but a stuck link also blocks the safe direction.

**Missing UX**
- There is no line saying which Jarvis task raised the card ("why am I being asked").
- Reversible actions do not show an Undo cue on the card. The Undo shelf and the inbox-tidy Undo strip exist elsewhere.
- Card fatigue: routine cards look identical apart from the title.

**Owner decisions, recommendation first**
1. Silent routine cards: (a) give normal cards a short quiet reminder when a card has under 60 s left (recommended); (b) leave as is.
2. Widget Deny under App lock: (a) open the app first, as decided for other widget buttons (recommended); (b) keep one-tap Deny as the safe direction.
3. Buttons on long phone cards: (a) pin Deny/Approve at the bottom of the card area (recommended); (b) keep scrolling.

**Not checked:** exact widget layout at 320 px, TalkBack announcements, Windows Hello wording in lock/rules.rs, what the backend puts in card content (another agent's job), and whether the phone card ever shows recipient lists apart from `detail`.
