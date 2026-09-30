# Report 20 (audit), agent a5141bc9, 2026-09-29T21:25Z

> **What it was asked** (first 600 characters of the task): Play-test ONLY the desktop screens added since 2026-09-27, in the checkout at /tmp/pr35 (main + PR #35), acting as the owner (a beginner developer): Settings -> 'Headless browser' (browser-engine.js/.html, Automatic/Always visible/Headless, the install line, on/off with its approval card), the Look at this / Watch with me settings and 'Jarvis is watching' badge (look-settings.js, watch-badge.html), picture mode switch, the Voice settings 'Hear it' buttons and Ashby/Clara voices (custom-voices.js, voice-panel.js), and the 'What asks first' page rows. Use the headless browser with the stubbed Ta

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

PLAY-TEST REPORT: desktop screens added since 2026-09-27 (/tmp/pr35, main + PR #35). Nothing was broken, but there are several confusing spots and one layout bug. The harness fakes the Tauri bridge and the backend, so none of this proves anything about the real Windows app, the Rust side or the backend. Where the harness had no stub (browser_engine, screen_picture) I wrote my own, and it simplifies real answers. I changed no repo files. I symlinked node_modules into jarvis-desktop temporarily, removed it afterwards, and ran `git checkout -- jarvis-desktop/tests/shots`; `git status` is clean.

EXISTING CHECKS (run, no failures)
- browser-engine (7 passed), look-rules (21 passed), look (13 passed), custom-voices, asks-first, reach and a11y all passed.
- `npm run test:ui` and `test:themes` as a whole were not run.
- Playwright cannot be imported from tests/ unless `node_modules/playwright` exists. NODE_PATH does not help for ES modules, so the README's command fails on a clean checkout without the symlink.

THREE WORST PROBLEMS
1. Watch badge text is cut off (fairly sure). The badge window is a fixed 400x64 (look.rs BADGE_W/BADGE_H). When the link is catching up, the second line reads "24 min left · The link to Jarvis is catching up - Stop still works" and wraps to a third line, so "works." is clipped. The "Ending soon" and "paused" states have the same risk. At 200% text, the badge shows only "20 more m…" and the Stop button is gone. A clipped Stop button on a sign that says Jarvis is watching your screen is a real problem. This is the harness at 400x64, not the real window, so please check on Windows. Screenshots: badge-stale.png and badge-200.png.
2. In Headless browser settings, the install steps come last and the wording is confusing (sure).
   - The order is: switch, status, a long "Stealth is always on…" paragraph, browser picker, then the install line at the bottom. A beginner can switch it on before installing it.
   - When it is not installed, the same sentence appears twice: "Obscura is not installed on this PC yet." Once inside "On, but not working yet: Obscura (the headless browser) is not installed on this PC yet. Settings shows the one line that installs it…" and again as its own line.
   - "Obscura" and "Stealth" are used without a plain explanation. "Stealth… makes the browser look like an ordinary Chrome" reads oddly next to "Jarvis normally… no hiding".
   - The picker stays active while the switch is off, and nothing says that choosing "The headless browser when it can run" does nothing until it is on.
   - The install line is a single-line box showing `$d = "$env:USERPROFILE\.openjarvis\obscura"; New-Item -ItemTy…` (cut off). You must press Copy to see it.
   - Screenshots: be-on_but_not_installed.png and be-small200.png.
3. "Hear it" gives feedback far from the button (sure, though it is not a bug).
   - The status line "Playing Clara (made for Jarvis)." appears below the whole 13-row voice list, next to "Voice follows the face". Clicking Hear it on Ashby at the top gives no visible feedback in a normal-height window.
   - The button does not change state while playing.
   - Pressing a second Hear it while the first plays just switches the status text.
   - Screenshot: voice-hear.png.

HEADLESS BROWSER (Settings, settings.html:1728, browser-engine.js)
BROKEN
- None. On/off, the mode picker, the stale link and a read failure all behaved. Off is instant ("Headless browser is off."). On shows "A card is waiting for your yes in the Jarvis bar. The headless browser stays off until you say yes." A stale link disables the switch, with the title "Offline — Jarvis is not answering… Approving is blocked until it reconnects."
CONFUSING
- A read failure (my stub threw "HTTP 404") shows a greyed "half-checked" switch, the raw text "HTTP 404", and an empty picker. The real Rust says which feature is missing (browser_engine.rs:79); I could not test that path. Screenshot: be-readfail.png.
- When the switch is disabled by a stale link, the reason is only in a tooltip and is not shown on screen.
- A failed "on" shows the backend's raw message. My stub gave `HTTP 500 {"detail":"boom"}`, and it displayed verbatim.
- Two full paragraphs of legal-style text (`detail` plus `stealth`) come before the switch's effect is clear.
COULD BE NICER
- Put the install steps directly under the switch, and show them only while it is not installed.
- The "Headless browser (Obscura)" heading is missing a plain-words subtitle such as "a browser Jarvis uses without opening a window".

LOOK AT THIS / WATCH WITH ME / PICTURE MODE (settings.html:1668, look-settings.js)
CONFUSING
- The description says "Jarvis reads the words only: a picture is never saved…", and the Picture mode block just below says Jarvis can look at the picture itself. The two contradict each other on one card.
- Picture mode says "With one graphics card Jarvis reads only the WORDS…", but it is shown regardless of the card count.
- The Picture mode block stays active on an older PC that has no "Look at this". The old-PC message is "This PC's Jarvis does not have "Look at this" and "Watch with me" yet."; the picture switch below it still looks usable.
- "Take off..." buttons are greyed on a stale link with no title and no explanation (the picture switch does have a tooltip). Screenshot: look-stale.png.
- Add with an empty box does not say what is missing; the status just repeats the dropdown label "A program (like MyBank.exe)" in warning tone.
- "how big it is has not been checked" (the picture model download) is honest but alarming for a beginner.
- The empty-list line says "Nothing added of your own yet. Add your bank here." while built-in rows are listed.
- Built-in rows (keepass.exe) also offer "Take off...", which raises a card. That is fine, but the row does not say "asks first".
COULD BE NICER
- "Take off..." beats a bare "Remove", but the row's own two-line height wastes space.
- Badge states seen in the harness:
  - "Jarvis is watching | 24 min left"
  - "Jarvis is watching - paused | Paused: a password box · 20 min left"
  - "Watching ended | Ended: the time was up"
  - The paper theme looks fine.
- Screenshots: look-takeoff.png, badge-*.png.

VOICE SETTINGS: "Hear it" and Ashby/Clara (custom-voices.js, voice-panel.js)
CONFUSING
- "Which of Kokoro's voices…" uses "Kokoro" unexplained. The card's intro never says what it is.
- The stated behaviour is that Hear it "plays a short sample without changing your choice", and that is what happened: no set_voice_speaker call was made.
- With Kokoro v1.0 not made yet, the note reads "Ashby and Clara, two voices made for Jarvis, are not made yet. To make them, run the one line under "M…". The line is elsewhere on the page.
- The old pack lists "American (female)" with no name, while v1.0 lists "American (female) - Heart".
- The picker is one long list of 11-13 rows plus a Hear it button each, so the card is very tall. Ashby and Clara sit first with a good one-line description ("A warm British butler, calm and a little slower… not modelled on anyone.").
- I did not test a sample refused while Jarvis is speaking (HEAR_BUSY).

WHAT ASKS FIRST (Settings, asks-first.js)
CONFUSING
- Two rows look like they contradict each other:
  - "Set up a repeating reminder or alarm, or the standby schedule - Does it without asking"
  - "Set up something that repeats - Asks you first, every time" (this one is the morning briefing and "tell me when").
  - The second name is far too broad.
- Similar: "Switch lights, plugs and fans you name - Asks you first, every time" sits next to its own switch "Lights, plugs and fans without a card", and the row's note is just "Off by default. The switch is below."
- "Offer this to the AI model" is unexplained jargon.
- Many rows carry the same note: "Only your settings file (jarvis-framework.toml) changes this one." A beginner cannot act on that. "Never - your settings file switches it off" is also opaque.
- After a status line like "Lockdown is off: everything asks first as your settings say." the button text "Turn on Lockdown" runs straight on, with no space in the extracted text (the screenshot was not inspected).
- The page is very long: 30+ rows.
- Screenshots: asks-first-pc_shipped.png, asks-first-pc_lockdown_on.png (in the scratchpad).

WHAT I DID NOT COVER
- The picture mode "card waiting" poll.
- Screen-reader output.
- The Look/Watch strip in the Jarvis bar.
- The real Rust and Windows behaviour (badge size at 100%/200% text, Windows Hello).
- The other themes (only default and paper for the badge).

Screenshots and driver scripts (be.mjs, look.mjs, v.mjs, a.mjs) are in /tmp/claude-0/-home-user-Epic-Jarvis/9107f2ad-de34-5a00-97f9-3a345fb31dd0/scratchpad/.

Files involved (all under /tmp/pr35/jarvis-desktop/src/): browser-engine.js, browser-engine-rules.js, settings.html (lines 1668-1760), look-settings.js, look-rules.js, watch-badge.html, custom-voices.js, voice-panel.js, asks-first.js.
