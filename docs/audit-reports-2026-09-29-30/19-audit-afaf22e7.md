# Report 19 (audit), agent afaf22e7, 2026-09-29T21:22Z

> **What it was asked** (first 600 characters of the task): Check the on-screen wording added since 2026-09-27 against the plain-words rules in /tmp/pr35/CLAUDE.md ('Explain things simply', beginner developer, never blame the wrong thing, say what to do next, same words in both apps). Scope: the headless browser (backend/jarvis_browser_engine.py card_line/words, jarvis_obscura.py messages, desktop browser-engine-rules.js/settings.html, phone BrowserEngine.kt/BrowserEnginePlate.kt), screen looks (jarvis_screen.py PAUSE_WORDS/END_WORDS/said, look-rules.js, ScreenLook/ScreenNever strings), picture mode, Kokoro/Hear-it/Ashby/Clara voice notes (jarvis_voice

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Wording review. I changed no files. I read the code in /tmp/pr35 (branch ...research-ff37vy, HEAD 1d024df5), because the headless-browser files are not in /home/user/Epic-Jarvis. "Both apps" means desktop and phone.

I checked the wording against the plain-words rules in /tmp/pr35/CLAUDE.md. Its Stealth section (owner, 2026-09-29) accepts "stealth on" for the headless browser, so I raised the word "stealth" only as jargon, not as a policy problem.

The phone and desktop text for the headless browser and picture mode is word-for-word identical to the PC's fixed text. That part is fine. The wording problems are listed below, worst first.

## A. Headless browser
Files are in /tmp/pr35/backend/, /tmp/pr35/jarvis-desktop/src/ and /tmp/pr35/jarvis-client/.../net/.

1. **Two different fixes for "not checked yet", and one of them is wrong.**
   - jarvis_browser_engine.py:1616-1617 (`status_line`) says: "Installed, but not checked yet - run the install line once to check it."
   - jarvis_obscura.py:201-203 (`WHY["not_checked"]`) says: compare the checksum, then run the check command the line printed.
   - The install line only downloads. It does not check anything. The status line sends the owner back to the wrong step, so they run it again and see the same message.
   - Rewrite for :1617: "Installed, but not checked yet. Run the second command the install line printed (it starts with Set-Location ... --check)."
   - Rewrite for :1613-1615 (the "changed" case): "Installed, but the file is not the one Jarvis checked, so Jarvis will not start it. If you did not update it yourself, delete it. If you did, run the install line again, then the check command with --accept-new."

2. **"Headless" and "Stealth" are used before they are explained.**
   - The title and the switch name (WORDS at jarvis_browser_engine.py:147,157; browser-engine-rules.js:20,32; BrowserEngine.kt:47,58) lead with "headless". Only the detail text below explains it ("a small browser with no window").
   - :173-178 (`stealth`) opens with "Stealth is always on for the headless browser." The next sentence explains it: "It makes the browser look like an ordinary Chrome."
   - Suggested title: "Browser without a window (Obscura)". Suggested switch: "Let Jarvis use the windowless browser (Obscura)". This would need a change in the shared words table and both apps' copies.
   - Rewrite for the stealth paragraph: "This browser pretends to be an ordinary Chrome so fewer sites turn it away. That does not stop a site from blocking it, or from closing an account you sign in to. So Jarvis never types a password with it and never solves a captcha. When it reaches a captcha or sign-in page it stops and hands the job to the browser window you can see. A sign-in that starts with only a username or email box may not be spotted."

3. **The "missing" message tells a beginner to run a file with no folder and no how.**
   - Repeated in :182-183, browser-engine-rules.js:47 and BrowserEngine.kt:70-72. The same wording appears for picture mode at jarvis_screen_picture.py:174, look-rules.js:221, and jarvis_screen.py:1703-1704 (`PICTURE_MISSING`, which also names a bare file, "apply-patches.ps1").
   - The current words are: "Run scripts\apply-patches.ps1 on the PC to add it."
   - "Patches" is meaningless to the owner, and "the PC" is ambiguous when the reader is on the phone.
   - Rewrite: "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis folder, run: .\scripts\apply-patches.ps1 . Then restart Jarvis."

4. **Failure messages state the problem but give no next step.** All are in jarvis_obscura.py:207-215.
   - "start_failed" says "Obscura could not be started."
   - "died" says "Obscura stopped unexpectedly."
   - "error" says "Obscura ran into an error."
   - "slow" says "Obscura took too long, so it was stopped."
   - "limit_time" says "Obscura had been running for its time limit, so it was stopped."
   - "limit_pages" says "Obscura reached its limit of pages for one run, so it was stopped."
   - Rewrite pattern: "The windowless browser (Obscura) could not start. Jarvis used the visible browser instead. Run 'py -3 jarvis_obscura.py --check' on the PC to see why."
   - For "slow": "... took too long, so Jarvis stopped it. Try again, or ask for the visible browser."
   - "refused_tool" ("Jarvis does not allow that Obscura tool.") is jargon. Rewrite: "Jarvis refused a step that this browser is not allowed to do."

5. **Checksum words with no explanation.**
   - jarvis_obscura.py:201-203 and :810-814 say "Compare the checksum ..." and "SHA-256".
   - :851-852 says "no official one is built in yet (nobody could read one), so this one will be REMEMBERED".
   - Rewrite for :201-203: "Obscura is installed but not checked yet, so Jarvis will not start it. The install line printed a long code (a checksum, a fingerprint of the file). Check it matches the one on the release page. Then run the check command the line printed."
   - Rewrite for :851-852: "Jarvis has no official fingerprint for this file to compare with, so it will remember this one. If the file ever changes, Jarvis will refuse it."

6. **Two places where the card or a message points at the wrong thing.**
   - jarvis_browser_engine.py:296-297 (`_DAMAGED`) says "Turn it on again to rewrite it". That is fine, but it begins in lower case and is shown as a "why". Make it a sentence: "The browser settings file is damaged, so the windowless browser stayed off. Turn the switch on again to rewrite the file."
   - jarvis_browser_engine.py:1574-1576 is a config-error text with a raw "tier 'ask' in jarvis-framework.toml". It is shown to the owner as an error. Rewrite: "Your PC's settings file lets this switch turn itself on. It must ask you first. Set it to ask in jarvis-framework.toml."

7. **The card line is dense.** card_line at jarvis_browser_engine.py:632-641 packs five ideas into one sentence.
   - The current line begins "Browser: HEADLESS (Obscura, no window) - ... Stealth is on: it looks like an ordinary Chrome, which does not stop a site blocking it."
   - Suggested split, in the same order: "Browser: no window (Obscura) - {why}. It looks like an ordinary Chrome, but a site can still block it. It cannot reach your own network. It stops at any captcha or sign-in page it recognises. It checks where a link leads before clicking, but a redirect is only noticed after the page loads. What the page says is outside text (Jarvis never follows instructions in it)."
   - "outside text" is defined nowhere on this card.

8. **Three names for the same choice.**
   - "Which browser Jarvis uses" has the option "The headless browser when it can run". Its help text says "The headless browser" and "the visible browser".
   - `state_line` at :1632 says "On, but not working yet: ..." and reuses `not_ready` text.
   - Pick one term (for example "windowless browser" and "visible browser") everywhere. The card line uses HEADLESS in capitals, the switch says "headless", and the settings help says "Obscura". A beginner will not connect "Obscura" and "headless" until the third read.

## B. Screen looks
9. **`said_for` builds broken sentences from PAUSE_WORDS** (jarvis_screen.py:1626-1629, fed by :215-230).
   - The pattern is "I'm not looking: " plus a phrase. It works for the four hand-written PAUSE_SAID lines, but the others read badly:
     - "I'm not looking: your Never look at list could not be read."
     - "I'm not looking: looking at the screen is not built on this PC yet."
     - "I'm not looking: the picture could not be taken."
     - "I'm not looking: a window I can't check for password boxes or capture protection."
   - The mix of noun phrases ("a password box") and full clauses ("the picture could not be taken") is the cause.
   - Rewrite (add to PAUSE_SAID, or change the fall-back format):
     - "list_unreadable": "I can't read your Never look at list, so I'm not looking. Open Settings, Look at this and Watch with me, to see why."
     - "not_built": "Looking at the screen is not set up on this PC yet."
     - "capture_failed": "I couldn't take the picture. Try again."
     - "cannot_check": "I can't tell whether this window has a password box, so I'm not looking."
     - "admin_prompt": "That's a Windows permission window, so I'm not looking."
     - "protected": "That window asks not to be captured, so I'm not looking."
   - "admin prompt" and "capture protection" are jargon. The desktop sign shows the same PAUSE_WORDS text (look-rules.js:77, "Paused: ..."). "Paused: a window I can't check for password boxes or capture protection" is unreadable.

10. **Ended reasons read as odd labels** (jarvis_screen.py:238-244; shown at :1604 and look-rules.js:98 as "Ended: <words>").
    - "Ended: Stop everything" looks like an instruction. Rewrite to "Ended: you pressed Stop everything".
    - "Ended: Windows locked" -> "Ended: Windows was locked".
    - "Ended: the PC slept" is fine.

11. **Screen strings that say what failed but not what to do.**
    - `NOT_BUILT` (jarvis_screen.py:185-186) says "the rules are in, but the Windows readers it needs are the next step." That is developer talk. Rewrite: "Looking at the screen does not work on this PC yet. Jarvis is missing the part that reads windows." The `not_built_words` fall-backs at :1668 and :1672-1673 name .py files and say "not in the backend folder", with no step. Add: "Run .\scripts\apply-patches.ps1 in the Jarvis folder, then restart Jarvis."
    - `look_line` fall-back (:1617, look-rules.js:118) says "Jarvis could not look at your screen just now." Add a next step: "Try again. If it keeps happening, check Settings, Look at this and Watch with me."
    - `LOCAL_ONLY_SAYS` (:1710-1711) is fine, but tell the phone owner what to do: "Press the Look at this key on the PC."

12. **Different names for the same list in the two apps.**
    - The desktop says "Never look at" (look-rules.js:174), and the pause words say "your Never look at list".
    - The phone's section title is "Never look at these apps" (ScreenNever.kt:93) but its pause line says "an app on your Never look at list" (:62).
    - The desktop's remove button is "Take off..." (look-rules.js:185). The phone's is "Remove" (LookPlate.kt:89).
    - The desktop section is "Look at this and Watch with me". The phone section is "Looking at your screen" (LookPlate.kt:49) and its switch is "Let Jarvis read this phone's screen".
    - The phone's "Watch this phone with me" vs the desktop's "Watch with me" is understandable (different device), but say so once.
    - Suggested fix: use "Never look at list" as the noun everywhere, and the same section title in both apps.

13. **The Never look at list has no "What asks first" row.**
    - I found no row in jarvis_asks_first.py for "Look at this", "Watch with me", or adding an app to the Never look at list. The page promises to list every action.
    - Removing an entry raises a card whose action is `change_own_config`. Its title reads "change one of its settings" (jarvis_card_words.py, `change_own_config`). The card body at jarvis_screen.py:552-564 is good, but the generic title tells the owner nothing. Give the card its own title, for example "take a program or website off your Never look at list".
    - Suggested rows: "Look at your screen once, or Watch with me. No card; only your own key, button or words. Nothing is saved." "Add to Never look at list. No card, instant. Taking one off asks first."

14. **Desktop `SEEN` lines that need words defined.**
    - "held" says "thrown away when it is two minutes old or the bar closes". The owner may not know "the bar". Say "the Jarvis bar".
    - "link" says "The link to Jarvis is catching up - Stop still works". This is confusing; the owner may think Jarvis itself is behind. Rewrite: "Reconnecting to Jarvis. Stop still works."
    - Unhelpful defaults: the desktop `empty` line says "Nothing added of your own yet. Add your bank here." It does not say how. Rewrite: "You have not added any yet. Type your bank's website or program name below and press Add to the list."
    - On the phone (ScreenNever.kt:59-63), "a screen Jarvis cannot tell the app of" is awkward. Rewrite: "a screen Jarvis cannot tell which app it belongs to".
    - ScreenNever.kt:86-92 (`SETTING_DETAIL`) says "when Jarvis is set as your phone's assistant app" but never says how. Add: "Set this in Android Settings, Default apps, Digital assistant app."

## C. Picture mode
(Note: jarvis_screen_picture.py, look-rules.js `PICTURE` and ScreenPicture.kt all carry the same wording.)

15. **Three names for one feature.**
    - The settings title is "Read pictures of my screen (slow, on the processor)" (jarvis_screen_picture.py:161). The switch says "Let Jarvis look at pictures of my screen (slow)" (:170). The off-line and messages say "Picture mode".
    - The phone section is titled "Looking at your screen: pictures" (ScreenPicturePlate.kt:81). "Picture mode" also appears in "What asks first" and "What Jarvis can reach" (jarvis_reach.py:813, "Picture mode for the screen (slow)").
    - Suggested one name: "Picture mode". Title: "Picture mode (Jarvis looks at your screen's picture, slowly)". Use it in both apps.

16. **"the processor" is used with no explanation, and "the picture model / picture reader" are two names for the same thing.**
    - :161-169 says "runs on this PC's processor, not on your graphics card". Rewrite: "It runs on your PC's main chip (the CPU), not on your graphics card, so your chat model is not slowed down."
    - The detail says "With one graphics card Jarvis reads only the WORDS on your screen." This implies two cards changes things. But this feature is off by default and runs on the CPU either way. Rewrite: "By default Jarvis reads only the words on your screen."
    - Pick "picture reader" (the noun the errors use) or "picture model" (the download) and use it consistently.

17. **`steps_note` worries the owner without saying why.**
    - :177-178 says: "It downloads the picture model from Ollama (ollama.com; how big it is has not been checked)."
    - Rewrite: "It downloads the picture model from Ollama (ollama.com). We have not checked how big the download is, so expect a wait. Then it times one look on your PC and saves the number."

18. **Failure reasons (WHY_WORDS, jarvis_screen_picture.py:183-203) mostly lack a next step.**
    - "not_installed" -> add "Run the set-up line in Settings, Picture mode."
    - "changed" says "The picture model's file has changed since it was measured, so Jarvis will not use it until it is measured again." "Measured" is unexplained. Rewrite: "The picture model changed since you last timed it, so Jarvis will not use it. Run the set-up line in Settings again to time it."
    - "no_cleaner": "The part of Jarvis that blacks out secrets in a picture is not installed, so no picture was used." Add "Run .\scripts\apply-patches.ps1, then restart Jarvis."
    - "cloud": explains the risk but not what to do. Add "Pick a model that runs on this PC."
    - "superseded" is a code word. Rewrite: "You asked something newer, so this picture was skipped."
    - LAST_WORDS "refused" says "Your PC's settings do not let this be approved, so it stayed off." Rewrite: "Your PC's settings file does not allow this switch to be turned on from a card, so it stayed off. Open jarvis-framework.toml to allow it."

19. **The card (describe_on, :1344-1383) is good, with two small fixes.**
    - "a separate copy of Ollama that uses only this PC's processor" is jargon; use the "main chip (CPU)" wording above.
    - "Expect seconds to minutes for one look" is fine.

## D. Voices (jarvis_voices.py, jarvis_kokoro.py)
20. **"Kokoro" is never introduced.**
    - jarvis_voices.py:424 says "Which of Kokoro's voices ..." and jarvis_kokoro.py:256-264 says "the newer voice pack (Kokoro v1.0)".
    - Rewrite for SPEAKER_DETAIL: "Which of the voices in Kokoro (the voice program Jarvis speaks with) Jarvis's built-in voice uses. It is never a voice you recorded; those are under 'Voices' below. 'Hear it' plays a short sample and does not change your choice."

21. **Error messages show Python class names.**
    - jarvis_voices.py:746 says "the built-in voice failed (RuntimeError)". :757 and :877 do the same: "it could not be checked (ValueError)".
    - The owner cannot act on that. Rewrite: "Jarvis's voice could not make the sample. Restart Jarvis and try again. If it keeps happening, run 'py -3 jarvis_speech.py --check' on the PC." (Use whatever real diagnostic command exists; I did not check one.) Keep the class name in the log, not on screen.

22. **`CHECK_BUSY` and `SAMPLE_BUSY` use "Hear it" as a noun** (jarvis_voices.py:430, :693).
    - "the PC is still making the sound for the last Hear it. Try again in a moment" is confusing, and worse when the owner has just picked a voice, not pressed Hear it. Rewrite: "The PC is still making another voice sample. Try again in a moment."

23. **Ashby and Clara notes:**
    - jarvis_voices.py:764-767 says "Ashby sounds too much like your own voice, so Jarvis will not use it." and "... could not be checked against your voice print, so Jarvis will not use it yet."
    - "voice print" is unexplained on this screen, and the second message gives no next step.
    - Rewrite: "Ashby sounds too close to your own voice. Jarvis will not use it, so the normal voice speaks. (Jarvis avoids voices that sound like yours because a voice that sounds like you could pass its own voice check.)" And: "Jarvis could not compare Ashby with your saved voice, so it will not use it yet. Try again, or retrain your voice under Voice, Your voice."
    - :740 says "this PC has no built-in voice to check it with". Add "The voice files are missing; see the Kokoro line in Settings."
    - The two notes at jarvis_kokoro.py:258-264 tell the owner to run "the one line under 'Make Ashby and Clara' in backend\README.md". The owner does not know where that folder is. Rewrite: "...in the README.md file inside the backend folder of your Jarvis folder."
    - Also, jarvis_voices.py:568-571 says "which Jarvis has not loaded yet (see below). Until it does, ... speaks." Add "Restart Jarvis" (it appears only in BLENDS_RESTART, which shows after).
    - jarvis_voices.py:573-574 says "which needs the newer voice pack (Kokoro v1.0). Until it is installed ..." with no how. Point to the upgrade line: "See the 'Upgrade the voice pack' line below."

24. **`UPGRADE_NOTE`** (jarvis_kokoro.py:551-554) is fine. Small nit: "run the one line under 'Upgrade the voice pack to Kokoro v1.0' in backend\README.md on your PC" has the same folder problem as above.

## E. Inbox tidy and "What asks first"
25. **Inbox tidy words are good.** jarvis_card_words.py:56 ("tidy your inbox (archive, star, mark read or trash)") and jarvis_reach.py:104,571-578 are plain, name Undo and 10 minutes, and say nothing is deleted for good. I found no issues.

26. **Two "What asks first" rows are unclear.**
    - jarvis_asks_first.py:417-421 (`fixed:handoff`) ends "Resume still asks with a card." Resume is undefined here. Rewrite: "After you solve it, the paused job only carries on after you approve a card."
    - jarvis_card_words.py:116 says "use a headless browser (Obscura) for plain web reading". The card title uses the same "headless" jargon as item 2. Rewrite: "let Jarvis read web pages with a browser that has no window (Obscura)".
    - jarvis_card_words.py:115 says "let it look at pictures of your screen, slowly, on the processor". Rewrite: "let Jarvis look at pictures of your screen (slow, uses your main chip)".

27. **Reach page wording** (jarvis_reach.py:732-744): "(Obscura, no window, stealth on)" repeats the jargon. Rewrite to "(a browser with no window, Obscura)". "stealth on" adds nothing for the reader here.

## Top four to do first
1. Item 1: the status line says the wrong next step for "not checked yet".
2. Item 3: the "run scripts\apply-patches.ps1" fix is repeated verbatim in eight places and is not usable by a beginner.
3. Item 9: `said_for`, which builds broken sentences from PAUSE_WORDS (shown in the desktop sign too).
4. Items 15 and 12: one name per feature and per list, in both apps.

Key files:
- /tmp/pr35/backend/jarvis_browser_engine.py
- /tmp/pr35/backend/jarvis_obscura.py
- /tmp/pr35/backend/jarvis_screen.py
- /tmp/pr35/backend/jarvis_screen_picture.py
- /tmp/pr35/backend/jarvis_voices.py
- /tmp/pr35/backend/jarvis_kokoro.py
- /tmp/pr35/backend/jarvis_asks_first.py
- /tmp/pr35/backend/jarvis_card_words.py
- /tmp/pr35/backend/jarvis_reach.py
- /tmp/pr35/jarvis-desktop/src/browser-engine-rules.js
- /tmp/pr35/jarvis-desktop/src/look-rules.js
- /tmp/pr35/jarvis-client/app/src/main/java/com/jarvis/client/net/BrowserEngine.kt
- /tmp/pr35/jarvis-client/app/src/main/java/com/jarvis/client/data/ScreenNever.kt
- /tmp/pr35/jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/LookPlate.kt
- /tmp/pr35/jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ScreenPicturePlate.kt

I did not review the shipped Kotlin phone text beyond the strings above. I did not check the real `--check` diagnostic commands named in the suggested rewrites (items 4, 21), so confirm them before using them.
