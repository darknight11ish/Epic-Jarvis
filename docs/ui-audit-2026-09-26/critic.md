# UI audit: the critic's pass (devil's advocate and both-apps check)

Part of the 2026-09-26 cutting-edge UI audit. I read the other five reports
(`desktop-today.md`, `phone-today.md`, `research.md`, `alive.md`,
`restraint.md`). I attacked every idea in them, then checked each claim my verdicts
depend on against the actual files. Nothing in the repo was changed.

**The tests each idea had to pass:**
- **Distract?** Does it pull attention away from what Jarvis is: a calm, private,
  fast assistant?
- **Overwhelm?** Does it add a second moving thing, another control, or more to read?
- **Trendy?** Will it look dated in a year? (A "trend" here means a look that
  big products all adopted in 2025-26, such as edge glows, glass and wavy bars.)
- **Both apps?** Can the phone and the PC both do it? If only one can, is there a
  good reason?
- **Cost:** battery, frame time (how long the phone takes to draw one picture of
  the screen), upkeep, and CI rounds (the phone only compiles on GitHub, about
  15 minutes per try).
- **Rules:** does it break a restraint rule (`restraint.md`) or a CLAUDE.md rule?

---

## In short, for the owner

1. **Most of what survives is taking things away or fixing things, not adding
   decoration.** That is fine. The apps already have a clear look. The real
   "spice" that survives my attacks is:
   - the desktop face finally moving with your voice and Jarvis's voice (the phone
     already does this);
   - bigger, clearer text sizes, including big numbers on the Brain screen;
   - the small ask-bar logo speaking the same "language" as the big face;
   - the phone's lists gliding instead of jumping.
2. **Four ideas contradict something already decided or tested.** Each was
   checked in the file:
   - "Bundle one new font in both apps" (research idea 5, marked **Do**) goes
     against your own choice to keep the phone's built-in font
     (`JarvisTheme.kt:300-301`: "the owner chose to keep the built-in ones").
   - "Run the calm desktop face at 30 frames a second" (alive P3) would fail two
     tests that exist on purpose (`tests/hud.mjs:492-504` and
     `tests/faces.mjs:582-594` both require 12 or fewer redraws a second under
     reduced motion).
   - "Mica glass on Brain and Settings is one Rust call" (research idea 14). Both
     windows are opaque (`windows.rs:418-431`, `:470-482` never make them
     see-through), so it is a bigger change than that. The gain is a faint
     wallpaper tint on a near-black window.
   - "Face reacts to voice, phone: medium" (research idea 2). The phone already
     does it (`HomeScreen.kt:1525-1538` feeds the real mic and speaker levels
     into the face). Only the desktop needs it.
3. **Two ideas would muddy the one signal that must never be misread: an
   approval waiting.**
   - A glowing screen edge while listening (research idea 9) would show the
     listening colour. The shared spec measured listening's colour against
     approval's at a difference of **4.5 for people with red-green
     colour-blindness** (`jarvis-visual-spec.json:1020`, `:2134`). That is close
     to "looks the same" (2 or less means identical). The spec's answer is that
     "approval's identity is its motion", and a big glowing edge is a new motion.
   - "A ring moving inwards for each tool step" (alive P6). Rings already mean
     two things: a tap, and the approval "knock" (a ring that leaves the face
     every 1.6 seconds). A third kind of ring weakens the knock.
4. **Two of the reports disagree about what to keep moving while an answer
   streams in.** `alive.md` P2 says keep the scan line *or* the logo spin, and
   stop the cursor blink. `restraint.md` Clutter 3 says keep the cursor and the
   logo. My call is below: **keep the logo, drop the scan line and the dot
   pulse, and keep the cursor but make it stop blinking.**
5. **Put the phone work into one or two CI rounds.** Every phone idea that
   survives is listed at the end in a single batch.

---

## Verdicts, one row per idea

**Key:** **Survives** means build it as proposed. **Change it** means build a
narrower or different version. **Drop it** means do not build it now. The
"Source" column names the report and its idea number.

### A. Research ideas (`research.md`)

| # | Idea | Verdict | Reason |
|---|---|---|---|
| R1 | Spring motion everywhere | **Change it** | A "spring" is an animation driven by a pretend spring rather than a fixed timing curve. The existing curve, `cubic-bezier(0.22, 1, 0.36, 1)`, already behaves like a spring that settles without bouncing, so on most things nobody could tell the two apart. What a spring really adds is smooth hand-off from a finger. So use springs only where a finger lets go: the drag handle and the approval card's snap-back (already `animateTo`, `ApprovalCard.kt:219-226`). Skip the desktop, which has nothing you drag. One real fix: the button-press spring is `DampingRatioMediumBouncy` (`Parts.kt:94-96`), the one bouncy thing in a calm app. Make it low-bounce. The research itself flags this. |
| R2 | Face moves with both voices | **Survives, desktop only** | The phone already does it (`HomeScreen.kt:1525-1538`). The desktop does not: I searched `src/` and found no caller of `attachSpeechSource` / `attachMicSource` (defined at `voice.js:288,293`). This is the same work as alive P1. It is the best "alive" gain in the whole audit. |
| R3 | Honest "what I'm doing" line | **Change it** | Keep the words and drop the shimmer. A "shimmer" is a moving highlight across the text, which is a new loop, and it makes the words harder to read. The phone already shows the step in words (`net/Steps.kt:14`, `ApiModels.kt:88`). The desktop card shows only general words (Thinking / Working / Waiting / Loading, `main.js:2188-2195`), and step events are used only for speech (`main.js:4093-4096`). So this is a desktop gap: put the step's own words in the card's status line, the way the phone does. |
| R4 | Android 16 "Live Updates" chip | **Change it: later, as a feature** | This is a new ability, not a new look. It triggers CLAUDE.md's rule that every new feature gets its own audit and parity check. It also needs build changes the report glossed over: `compileSdk = 36` (`build.gradle.kts:73`), and `core-ktx:1.15.0` (`:286`). The report says the setter needs API 36.1; I have **not checked** which core-ktx version has it. Timers are not shown as a running countdown on the phone today (the ongoing notification in `ScheduleNotifier.kt:164-185` is for when an alarm rings). A countdown chip also needs a rule for a stale link (CLAUDE.md rule 4). Worth doing, but separately. |
| R5 | One variable font on both apps | **Drop it** | It contradicts your recorded choice to keep the phone's built-in font (`JarvisTheme.kt:300-301`; the question was `docs/UI-AUDIT-2026-09-23.md:180-182`). The desktop body font, Segoe UI Variable, is already a variable font (one font file that can smoothly change weight). The narrower question worth asking you is about headings only. See "Questions for the owner". |
| R6 | Calm "ambient" idle mode | **Change it** | The face already rests: idle draws 30 frames a second, standby 15 and banked 2 (`face/Spec.kt:77-82`). Standby is already the "dim" state. A new dim level would touch all 20 faces for little gain. Keep only the useful half: idle Home shows **one quiet line** ("Next: timer, 4 min" or a hint of what to ask), with no animation. That is Home's one new idea in the restraint budget. It must hide words when App lock or "Hide memory lists" is on, the same way Coming up does (`ComingUpPlate.kt:58`). |
| R7 | Ready-made answer cards (timer etc.) | **Change it** | A timer card would copy Coming up, which already shows timers counting down (`ComingUpPlate.kt:40-60`, and the Brain on the PC). CLAUDE.md says no duplicates. The answer arrives as chat text. I have **not checked** whether the chat stream says which job was just set, so this may need a backend patch (the backend lives outside this repo). Narrower version: under the answer, show the same Coming up row, reused rather than redesigned, and only if the backend can name the job. |
| R8 | "Next up" home-screen widget | **Change it: later** | It is a new feature, so it needs its own audit. The desktop widget is 320px wide and gets **0** new ideas in the budget (`restraint.md`). The "generated previews" add-on needs a Glance version the report did not name (the app pins 1.1.1, `build.gradle.kts:313-314`). **Not checked.** |
| R9 | Screen-edge glow while listening | **Drop it** | It breaks "one moving thing at a time" (`ui/Nav.kt:223-226`). It also has a colour problem with no good answer. Listening's colour is too close to approval's for red-green colour-blind eyes (a difference of 4.5, `jarvis-visual-spec.json:1020`). A cyan glow would instead disagree with the face, which shows listening in ember (`theme.css:156`). And it is the Siri/Gemini 2025 look, which is the most likely thing here to look dated. The face, the mic ring (`VoiceButton.kt:61-65`) and the talk button already show "listening". |
| R10 | Container transforms (a card grows into its page) | **Drop it** | The phone deliberately avoids keeping two screens alive during the back swipe, "one of them possibly Home with the face" (`Nav.kt:236-239`). A shared-element transition needs exactly that. It is also medium work on the phone's own screen switcher, for a flourish on screens you rarely open. |
| R11 | More vibrations | **Change it** | Keep only one: a light tick when you let go of the talk button (that is alive P5). Press and cancel already vibrate (`VoiceButton.kt:113,147`). The phone has no "sheets" to snap. Never vibrate when an approval arrives. `alive.md` points out that it could double up with the notification's own vibration, and that is **not checked**. |
| R12 | Raycast-style ask bar (shortcut hints) | **Change it** | The report left this "not checked". I checked: the shortcut list already exists (`#primer`, `index.html:296` onward) and has about 10 rows, which `desktop-today.md` already calls too heavy for a light bar. So do the opposite of adding: cut the primer to the 3-4 keys a beginner needs, with "More shortcuts" in Settings. |
| R13 | Material 3 Expressive, hand-built pieces | **Drop it** | "Material 3 Expressive" is Google's bolder 2025 design style. Its "wavy progress bar" is a new loop and very 2025. "One emphasised action per screen" is already true where it matters (Approve filled and Deny outlined, `restraint.md` Rule 1). The rest is covered by R1. Look again when it is stable, as the report says. |
| R14 | Mica on Brain and Settings | **Drop it (keep the comment fixes)** | Mica is Windows 11's lightly tinted window backdrop. Both windows are built opaque (`windows.rs:418-431`, `:470-482`, with no `.transparent(true)`). Mica would mean making them see-through, making the page background see-through, and re-measuring every text colour over black and white on three themes. Daylight is opaque by design (`theme.css:259-262`, per research). The two out-of-date comments are real and cheap to fix: `theme.css:231-234` against `windows.rs:153-157`, and "0.5.3" at `windows.rs:155` against `Cargo.toml:36` `"0.6"`. Checking the HUD blur (`jarvis_hud.html:285,297,330,358`) on the real PC **survives**. |
| R15 | A sci-fi HUD rulebook | **Survives, merged** | Do not write a second rulebook. `restraint.md` already is one, with its test: "each new moving or glowing thing must mean a state". Drop the film-studio / Marvel framing: `restraint.md` Rule 8 notes a trademark risk that grows with Iron Man visuals. |
| R16 | Dot-matrix accents | **Drop it** | A strong, borrowed style (Nothing phones). It would be dated fast, and it would need a new shared face pattern on both sides. |
| R17 | Extra GPU glow effect on the phone | **Drop it** | It competes with the face's own GL renderers for battery. There is nothing it must show that the face cannot. |
| R18 | Predictive back polish | **Survives (nothing to do)** | Already built (`Nav.kt:188-211`, per research). |
| R19-R23 | Wallpaper colours, Windows accent colour, see-through glass, model-written UI, new gestures | **Drop it (agree with research)** | Each clashes with the measured themes, readability, security or learnability, for the reasons the research gives. Model-written UI would run code a local model wrote inside a window that holds the pairing key. |

### B. Motion proposals (`alive.md`)

| # | Idea | Verdict | Reason |
|---|---|---|---|
| P1 | Desktop face hears and speaks for real | **Survives, top pick** | Checked: the clip plays at `main.js:3212-3221`; Rust computes loudness at `voice.rs:1475` and throws it away; the face reads a flat 0.28 floor. It sends levels only, never audio, and stays inside the app, so rule 1 is fine. It adds no drawing work. It makes the two apps match. Also fix the stale "Nothing in this build plays TTS yet" comment (`voice.js:280`). |
| P2 | Ask-bar logo: same "language" as the face, one clock | **Survives, with my call on the streaming conflict** | I counted the loops in `style.css`: halo 3.4s (`:330`), rings 9s and 6s (`:343,349`), core 2.6s (`:363`), dot pulse 1.1s (`:727`), cursor blink 1s (`:904`), scan 1.6s (`:202`). My resolution: **keep the logo spin-up** (it is the bar's face, and so the "one moving thing"); **drop the scan line and the dot pulse**; **keep a still cursor** so you can see where text ends, but stop the blink. The approval "knock" ring and the error's reversed turn make those states readable without colour, which is exactly what the spec asks for. The cost goes down. |
| P3 | One reduced-motion rule everywhere | **Change it** | Unifying is right, but "drop the 10 frames a second, draw at 30" would fail `tests/hud.mjs:492-504` and `tests/faces.mjs:582-594` (both assert 12 or fewer). The real problem is the shake and flinch at 10 frames a second. `faces.html` checks `CALM` only for pacing (`:3990-4020`). So **keep the 10 frames a second cap** and add the phone's rule on top: no shake, no flinch, no speech push. Also give `settings.css:524-527`'s endless sweep a reduced-motion block. It uses a literal `1.2s`, so the token collapse at `theme.css:402` does not reach it. |
| P4 | Phone list items glide in and out; paragraphs fade | **Survives, one guard** | No phone code uses `animateItem` (checked by search). Entry is 200ms once, which is inside Rule 1's limit for cards. Guard, **not checked in Compose**: an item fading out may still be tappable for 200ms, so an approval card on its way out should have its buttons turned off. |
| P5 | "Caught it" when you let go of the talk button | **Survives** | One light tick plus a short face "inhale", inside the existing 600ms full-speed window (`Spec.kt:85`). The desktop uses the existing `VOICE_HEARD` event (`voice.rs:1690`). No new loop. Both apps. |
| P6 | Inward ring for each tool step | **Drop it** | Rings already mean "you tapped me" and "approval knocking". The spec says approval must be "legible with no colour at all" (`jarvis-visual-spec.json:2027`). A third ring blurs that. The step words (R3) already carry the information, and they work under reduced motion too. |
| P7 | Measure lip-sync and a possible idle blink | **Survives** | It is logs only (timings, never words). Measure before fixing. |
| P8 | Slow the approval knock after 60 seconds | **Owner's call; I recommend leaving it alone** | Nobody has complained that the knock nags. A quieter approval is the one direction this project has always refused. If you want it, keep it as a question (below). |
| P9 | Cover the GL faces' fade when leaving Home | **Survives** | Small, a known issue (`Nav.kt:240-243`), one fill for 200ms. **Not tested on a phone**, so put it in the same CI batch as P4. |

### C. Restraint rules and clutter removals (`restraint.md`)

| # | Idea | Verdict | Reason |
|---|---|---|---|
| Rules 1-10 and the budget table | **Survive** | This is the test every idea above was judged by. One addition: Rule 2's "no new loops" should say that a *signal already on screen* (the face, the logo) wins over a new one. |
| Clutter 1 | Split the phone's Brain screen and move settings out | **Survives, in two steps** | It is the biggest clarity win in the audit (37 `item(key` in `BrainScreen.kt`, 1,764 lines). It is also the riskiest phone change for CI. Step 1: rename "Mind" to "Brain" (still "Mind" at `BrainScreen.kt:242`, `HomeScreen.kt:1269,1568`) and group sections under a few headings. Step 2: a real Settings screen. Keep every phone setting reachable at every step. |
| Clutter 2 | Remove the Core / Ollama / LiteLLM dots from every answer | **Change it** | Do not move them only to Settings: while Core is up, the Ollama dot is the only on-bar sign that the model is down (`main.js:941-952` switches the badge only for Core). Show **nothing** when all is well, and a plain line ("The model isn't answering") when Ollama is down. Move the a11y tests (`a11y.mjs:216-244`) with it, as `restraint.md` says. |
| Clutter 3 | Fewer streaming signals | **Survives** | Merged with P2 above. |
| Clutter 4 | Put the HUD on the shared colour tokens | **Survives** | Checked: "Brains" and "Projects" are both `#ffb648` (`jarvis_hud.html:802,809`), which is also the approval amber (`theme.css:159`). Labels measure 2.3-2.6:1 (`desktop-today.md`). This is a fix before any spice. |
| Clutter 5 | Size tokens on the desktop, protected text 12px or more | **Survives** | Checked: the widget's "someone tried to hurry you" line and its quote are 10px (`widget.css:900-915`). |
| Clutter 6 | One reduced-motion approach | **Survives** | Merged with P3 (with the 10fps correction). |
| Clutter 7 | Wording pass before the visual pass | **Survives** | A polished look over mixed wording still looks unfinished. |

### D. Gaps named in the two "today" reports

| # | Idea | Verdict | Reason |
|---|---|---|---|
| D1 | Phone shows Markdown (bold, lists, code) in answers | **Survives, with a safety rule** | Checked: paragraphs are plain `Text` (`HomeScreen.kt:1985-1992`). Use a small hand-written subset, not a new library, which would add CI risk. **Show every link's real address**: the desktop draws `[words](url)` as a link labelled with the words (`markdown.js:93`), and after Jarvis reads an email or web page those words may have been written by someone else. Reuse the desktop's test cases (`scripts/markdown-test.mjs`). |
| D2 | Big numbers on the Brain screen (the unused display size) | **Survives** | It uses the phone's existing display style (0 uses today, `phone-today.md` §3), needs no new font and no motion, and it is cheap. |
| D3 | Phone section titles in the accent colour, like the desktop | **Change it** | If every title is in the accent, the accent stops pointing at the caret, focus and selected item (`Chrome.kt:362-381` ties it to those). Make titles stronger by size and weight instead (`titleSmall` exists). |
| D4 | Chakra Petch (the desktop's heading font) on the phone | **Owner's call** | It is a new question, not a fix (`phone-today.md` §3). Note: the repo's files are `.woff2` (`jarvis-desktop/src/fonts/`), a web format. Android's font folder takes `.ttf`/`.otf`, so they would need converting. **Not checked** whether that works offline here. |
| D5 | Drawn icons for the Brain rail instead of text symbols (✦◷◆…) | **Survives** | This replaces something rather than adding it. Reuse the phone's drawn shapes where they match (`NavIcons.kt`), so both apps share one icon language. |
| D6 | More icons on every phone section and row | **Drop it** | This is decoration. Text-only rows are calm and readable. |
| D7 | Settings: a jump list, one on/off style, one heading style | **Survives** | This groups and tidies with no new knobs, which the budget allows. |
| D8 | Onboarding teaches the wrong colours | **Survives (bug)** | Checked: "thinking" is shown as `#ffb648` (`onboarding.html:85`), which is the approval colour (`theme.css:159`). Use the state tokens. |
| D9 | Three tokens undefined in Settings, the widget and Brain | **Survives (bug)** | Checked: `--surface-raised` is defined only in `style.css:37`, and is used in `settings.css` (2 times), `widget.css` (4) and `brain.css` (1). |
| D10 | Phone pairing screen becomes a welcome | **Survives, small** | This is onboarding's one idea. Use a still picture of the face (the picker already uses stills, `AppearanceScreen.kt:1137-1204`) and one sentence. Write down in ARCHITECTURE §8 why the phone has no three-step tour. |
| D11 | Phone approval swipe shows something underneath | **Change it** | It is on a protected surface, so it is allowed only as readability: the plain word "Deny" on one side and "Approve" on the other, the same weight and no colour flood, only on swipeable cards (`ApprovalCard.kt:191`). A green wash behind Approve would make Approve more attractive than Deny, which Rule 1 forbids. |
| D12 | Draw the phone's planned "streaming hairline" (`Chrome.kt:166-170`) | **Drop it** | The desktop is removing its scan line (P2). The phone's face already shows thinking. It would be a second moving thing on Home. |
| D13 | Small phone fixes: typed "→" arrows (7 places), the typing box's focus ring, one error wording with Retry | **Survive** | Checked: the arrows are at `HomeScreen.kt:1568`, `InboxScreen.kt:256`, `BrainScreen.kt:1016`, `SecondCardPlate.kt:117`, `HardwarePlate.kt:233`, `BigModelPlate.kt:167`, `CardWaitingLine.kt:66`. Cheap, and they go in the same batch. |
| D14 | Pictures in empty states | **Change it** | Rule 9 allows personality on idle Home only. Elsewhere, an empty state gets one helpful next step in words, not a picture. |
| D15 | Faces window "developer" readouts (`45.7 ms/frame`) | **Survives, small** | Tuck them behind a "Details" switch. The Faces window keeps its own palette on purpose (`themes-all.mjs:22-26`). |
| D16 | Do not shrink the rush-latch banner that repeats on every Brain tab | **Keep as is** | A "rush latch" is the red warning shown when something tried to hurry you into approving. It is a protected surface. Showing it on every tab is correct, even though it takes the first row. |

---

## Both apps: parity check on the survivors

| Survivor | PC | Phone | One-sided on purpose? |
|---|---|---|---|
| Face moves with real voices | needs it (P1) | done | Ends up the same on both |
| "Caught it" on release | face inhale | tick plus inhale | PCs have no vibration. Worth one line in ARCHITECTURE §8 |
| Step words while working | needs it (R3) | done | Ends up the same on both |
| Ask-bar logo language | yes | no ask bar | The phone's face already speaks it |
| One reduced-motion rule | yes | already the model | Write the rule once in the spec's new `calm` block |
| List glide / paragraph fade | already fades blocks (`style.css:915`) | needs it (P4) | Ends up the same on both |
| Markdown | done | needs it (D1) | Ends up the same on both |
| Big numbers / type scale | size tokens (Clutter 5) | display style (D2) | Same idea, each in its own toolkit |
| Brain grouping and the name "Brain" | tabs already | needs it (Clutter 1) | Ends up the same on both |
| Drawn icons | Brain rail (D5) | 4 nav icons already | Share the shapes |
| Welcome | three-step tour | still face plus one sentence (D10) | Yes. Record the reason in §8 |
| Quiet idle "next up" line | not on the bar (widget budget is 0) | Home (R6) | Decide first. The PC's widget already has a place a line could go, but the budget says no |

`tools/check_parity.py` checks features, not looks (`phone-today.md` §6), so
the table above is the only parity check for visual work. Keep it in the final
report.

---

## Cost and CI plan for the phone

Every phone survivor fits into **two CI rounds** if they are grouped:
- **Round 1, small and safe:** P4 (list glide, with the button guard), P5
  (release tick), P9 (GL fade cover), D2 (big numbers), D13 (arrows, focus ring,
  error wording), R1 (the calmer press spring), and the Mind-to-Brain rename.
- **Round 2, bigger:** D1 (Markdown subset plus its unit tests), R6 (idle line),
  D10 (welcome), D11 (swipe words), and Brain grouping step 1.
- Later, separately: the Brain Settings split (step 2), R4 (Live Updates) and
  R8 (the widget). Each is a feature with its own audit.

Battery and frame time: no survivor adds a loop. P4, P5, P9 and D11 run only
when something happens. The face stays the only thing always moving.

---

## Questions for the owner (short, as CLAUDE.md asks)

**1. The phone's headings.** The PC uses a squared-off "techy" font (Chakra
Petch) for titles. The phone uses the phone's own font everywhere, which you
chose on 2026-09-23.
- **Keep the phone's font everywhere** (recommended: it is your earlier choice,
  and bigger sizes give most of the gain)
- **Use Chakra Petch for phone titles only**

**2. An approval nobody has answered for a minute.** The face knocks every 1.6
seconds for as long as a card waits.
- **Leave it as it is** (recommended: approvals never get quieter)
- **Slow the knock after a minute**; the card and its colour stay the same

---

## Not checked

- Anything on a real phone or a real Windows PC.
- Whether an item fading out in a Compose list can still be tapped (P4 guard).
- Which `core-ktx` version has the Live Update setter, and which Glance version
  has generated previews.
- Whether the chat stream names the job a timer answer just set (R7).
- Whether an approval vibration inside the app would double up with the
  notification's own vibration.
- Whether the `.woff2` fonts can be converted to `.ttf` offline in this
  container (D4).
- The claim in `desktop-today.md` that the "Local" badge stays lit while
  offline. `main.js:941-952` switches it to "Offline" when the health report
  says Core is down. The screenshot may only reflect the test stub. I did not
  settle which one is right on a real machine.
