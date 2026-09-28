# Jarvis Live on the desktop: play-test (studio, 2026-09-28)

Real frontend at deff2f5a in headless Chromium with the stubbed Tauri bridge;
Rust, tray, the always-on-top window, the mic and the backend were code-read
only. `tests/jarvis-live.mjs` 24 ok; a11y and themes pass; `test:ui` passed
on a rerun (one flaky `blockers.mjs` wait, not Live).

## Worst three

1. **Esc during Live forgets the conversation.** `dismiss()` (`main.js:3996`)
   -> `closeCard()` empties the conversation (`main.js:810`); the next
   question goes out alone with a new id. Fix: while `liveOnHere()`, Esc
   only hides the window; keep the conversation until Live ends.
2. **Side talk wipes the answer off the screen, including the crisis help
   panel.** `liveSideTalk` (`main.js:4614`) sets "(not for Jarvis)";
   `send()` clears the panel first (`main.js:2768`). Against LIVE-DESIGN
   rule E. Fix: no new answer card for a Live turn until the first
   non-marker text; show "(not for Jarvis)" in the Live strip's detail line.
3. **The always-on-top badge cuts off why Live is paused** in 12 of 14
   states (420x52, `live.rs:55`; `white-space: nowrap`,
   `live-badge.html:45`); no tooltip; no "Show the card". Fix: two rows
   (~76 px), `title=` with the full text, "Show the card" on card pauses, a
   click on the words opens the bar.

## Broken

4. The "Jarvis Live ended" strip never goes away (`jarvis_live.py:582`
   keeps `ended`; `live-rules.js:105`, `main.js:4813`). Hide after 15 s or
   once not resumable and seen.
5. "Resume Live" missing when the bar opens after a quiet end: `endedAt`
   set only on a `live-status` event (`main.js:4773`), not the first read
   (`:4813`), so `:4514` is always past 10 min. Trust the PC's `resumable`.
6. A refused start says "Jarvis could not answer." (`main.js:4563` ->
   `showError`), also for App lock and a stale link; "Voice check" is not a
   Settings section ("Voice"). Fix: "Jarvis Live didn't start. Train your
   voice first: Settings -> Voice." with a button there.
7. A spoken "Hey Jarvis, let's talk" that the PC refuses gets silence
   (`main.js:4675`, screen reader only). Say the PC's fixed reason.
8. Quick-answer buttons garbled (shared rule, `live-rules.js:183-209` and
   `LiveRules.kt`): "Which one - the red, the blue or the green one?" ->
   ["- the red", ...]; "Is that the one you mean, or the other one?" ->
   ["One you mean", ...]. Strip leading punctuation/dashes, drop a
   mid-phrase first option, add to `live-cases.json`.
9. "One moment" in Live (`main.js:4599-4603`) plays every slow turn, skips
   `momentFlow`'s once-per-question guard, and does not `live_hold` the mic.
   Route it through `sayAside`-style holding and `momentFlow`.
10. Answers may stream into a hidden bar (code-read: `windows.rs:224-231`;
    no Live path shows the window). While Live is on, show the bar without
    focus when an answer stays on screen, or pin it at start. Check on
    Windows.
11. Brain's advanced "Live" tab prints raw JSON for Live events
    (`stream.rs:766`, `brain.js` ~5589). Add a `kind === "live"` line. (The
    tab is being renamed "Now" - owner, 2026-09-28.)
12. Crisis and the time limit: after a crisis turn the 30-minute limit still
    runs and "Two minutes left..." was spoken straight after the 988 answer
    (`jarvis_live.py:816`). Extend quietly / don't end at the limit and skip
    the warning after a crisis turn - **owner's call**.
13. At 200% text the typing box is 7 px wide; the badge ignores zoom and
    theme changes (reads `jarvis.theme` once, no `followTheme`/`followZoom`).

## Confusing

Two "Stop" buttons ("Stop talking | Mute | Stop"; "Stop" ends Live) - call
it "End Live" everywhere; "Mute" reads as Jarvis's voice - "Mic off"/"Mic
on", and "Listen anyway" for a call pause (both apps); the Live button is an
unlabelled icon that turns red, no explainer, no FAQ entry - a visible
"Live" label and a first-time line; a card already on screen pauses Live
silently (`liveSign` has no local `cardShown`) - "Waiting for your tap on the
card"; pause words with no next step, "tap" on a PC -> "click"; clumsy
ended wording ("It ended: you ended it."); Settings -> Voice: heading "Jarvis
Live" -> "How far Jarvis Live is trusted", the interrupt setting sits above
a footnote that doesn't apply (`settings.html:605-615`), and in Live the
older "Interrupt Jarvis while it talks" switch is ignored (`main.js:3827,
:4743` never read `loadBargeIn()`), shows on older PCs and hides when status
can't be read though it is a local setting; quick-answer buttons sit in the
strip styled like Mute/Stop - put them under the answer; Live running on the
phone is invisible on the PC; the "move it here?" offer is easy to miss.

## Polish and a11y

Toggle changes both name and `aria-pressed` - keep one name; the
quick-answers container needs `role="group"`; `.jarvis-live-sign
span[role="status"]` (`style.css:2322`) matches nothing; badge separator
double spacing; `live-badge.html` not in `themes-all.mjs`; no Live mark on
the tray icon, tray row right under "Stop everything", no end tone.

## Desktop vs phone

More time: phone button, desktop voice only; the end hint shown on the phone
only; "Show the card" phone only; explainer phone only; labelled vs
unlabelled Live button; typed-answer hint phone only; Resume after reopening
(#5); "End" vs "Stop".

## Ideas (0 GB, either card setup)

A Live hotkey (Alt+Shift+L, unbound by default); "+20 min" on the badge and
strip; click the badge's words to open the bar; keep the bar open without
focus during Live; Esc = hide during Live.
