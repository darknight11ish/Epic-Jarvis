# UI refresh: the restraint and accessibility rules

Part of the 2026-09-26 cutting-edge UI audit. This part is the brake, not the
accelerator. It sets the rules any visual change to the two apps must obey,
says how much new is allowed on each screen, and lists the clutter a refresh
should **remove** rather than decorate.

**How this was checked.** I read the files named below. Every `path:line` was
opened on 2026-09-26. Nothing in the repo was changed. I ran one small script
in my own scratch folder: the desktop's own colour-blindness maths, copied from
`jarvis-desktop/tests/distinct.mjs:323-378`, run on the HUD window's graph
colours. I did not run the Playwright suites, build the phone app, or look at a
real phone.

---

## In short, for the owner

1. **The apps already have good guard rails**: contrast tests, colour-blind
   tests, a photosensitivity limit on the face, reduced-motion support, and a
   test that keeps the phone and the PC on the same three themes. A refresh
   must keep every one of them passing. It must not relax any of them.
2. **Approval cards, errors, security prompts and lock screens get no
   decoration at all.** No glow, no new animation, no jokes, no pictures. A
   refresh may only make them easier to read.
3. **At rest, one thing moves: the face.** Everything else moves only when
   something happens, briefly, and not at all under "reduce motion".
4. **The biggest win is taking things away.** The phone's Brain screen is one
   scroll of about 30 sections. The desktop's answer card shows engineering
   dots ("Ollama", "LiteLLM"). Four separate things move while an answer
   arrives. The HUD window has its own colours, which break the colour-blind
   rules the rest of the app follows.
5. **Budget: one new visual idea per screen.** A new control means an old one
   goes, and nothing new is added to the protected surfaces.
6. **Some written claims are out of date.** They are listed at the end, so
   nobody relies on them.

---

## Words used here

- **Contrast ratio**: how much lighter the text is than what is behind it.
  1:1 means invisible, 21:1 is black on white. **WCAG** is the web's
  accessibility standard. Its "AA" level asks 4.5:1 for normal text and 3:1
  for icons and borders. "AAA" asks 7:1.
- **Token**: a named colour or size such as `--text-muted`, defined once
  (in `theme.css` on the PC and in `Themes.kt` on the phone) and used
  everywhere, so a theme can change it in one place.
- **Reduced motion**: a Windows or Android setting for people who get dizzy or
  distracted from movement on screen. Windows calls it "Animation effects" and
  Android calls it "Remove animations".
- **Colour-blind (CVD)**: colour vision deficiency. Most common is
  red-green (deuteranopia and protanopia, about 1 man in 12). Blue-yellow
  (tritanopia) is rare.
- **Kicker**: the small uppercase label above a title, e.g. "NEEDS YOUR OK".
- **Loop**: an animation that repeats forever, like a spinning ring.
- **Protected surface**: a screen part where a wrong reading costs something
  real: approval cards, errors, security prompts, lock screens.

---

## The rules

Each rule says what it is, why, what enforces it today, and any gap.

### Rule 1. No decoration on protected surfaces

**Where:**
- Approval cards, wherever they appear: the Jarvis bar (`index.html`, styled at
  `style.css:1200-1700`), the widget (`widget.css:460-720`), the HUD
  (`jarvis_hud.html:453-470`), and the phone (`ApprovalCard.kt`).
- Error lines and "problem" boxes (`plain-errors.js`, `PlainErrors.kt`).
- Security prompts: Windows Hello and App lock, the phone's fingerprint check
  (`BiometricGate.kt`), pairing confirmation, and the rush-latch strip.
- Lock-screen notifications, the widget while App lock is on
  (`widget.js:604-615`), and "Stop everything".

**Allowed there:** what exists today. That is the amber edge, the countdown
bar, the entry fade of 200ms or less (`style.css:1218`), and a better layout
or bigger text.

**Not allowed there:**
- New glow, gradients, blur, frosted glass, textures or pictures.
- Any new loop. A card must not pulse or shimmer to get attention. The
  existing assertive screen-reader announcement (`a11y.mjs:45-61`) is how it
  interrupts.
- Personality: no emoji, no mascot, no humour. The round-4 character report
  says cards, errors, refusals, the lock screen and notifications get
  "**None**" (`docs/CUTTING-EDGE-2026-09-26-round4-character.md:114-116`).
- Anything that makes **Approve** more attractive than **Deny**. That means
  no animation, glow or "success" celebration on Approve, and no confetti or
  checkmark burst after approving. Today Approve is a tinted fill and Deny is
  an outline (`style.css:1623-1638`). Keep that difference, and do not widen
  it. The phone's swipe must stay turned off for anything the server does not
  mark safe to swipe (`ApprovalCard.kt:170-191`).
- A "preview" of hidden content: no blurred thumbnail and no shape of the
  text behind App lock or "Hide memory lists". A blur of text still shows
  how long it is and what shape it has.

**Amber means "waiting on you".** Amber is reserved for approvals. The PC
already moved one misuse off it (`theme.css:142-149`: listening had been
painted amber, "the colour the spec binds to APPROVAL"). The attention list is
"Quieter than the approval gate on purpose… Making it as loud as the gate would
teach the eye to discount both" (`style.css:1796-1800`). A refresh must not
use amber or `--warn` as an accent anywhere else.

### Rule 2. Motion limits

- **At rest, one moving thing per window: the face.** This is the phone's
  written rule already: "One moving thing at a time. The face is the only
  thing that animates all the time" (`docs/UI-AUDIT-2026-09-23.md:59`). This
  audit adopts it for the PC too.
- **Event motion uses the existing durations only.** On the PC they are 90,
  160 and 260ms (`theme.css:226-228`). On the phone they are 120, 200 and
  280ms (`JarvisTheme.kt:185-189`). Both use one curve
  (`theme.css:224`, `JarvisTheme.kt:210`). The only longer one is the phone's
  500ms theme crossfade (`JarvisTheme.kt:481`). A new animation picks one of
  these tokens. It does not invent a number.
- **No new loops.** The only allowed loops are: the face, a "listening" mic,
  an honest "still working" indicator with no known end, and a countdown.
- **Under reduced motion: nothing slides, grows or spins.** Colour and
  fade may still change, briefly, so a change is still visible. That is the
  PC's own stated approach, "Amplitude to zero, not duration to zero"
  (`style.css:1753-1790`). Every new animation must be covered by it. The
  face slows down but never freezes. Tests assert 12 redraws a second or
  fewer (`tests/hud.mjs:498-504`, `tests/faces.mjs:587-592`).
- **Flash limit (photosensitive seizures).** No more than 3 opposing
  light/dark swings a second, where a swing is a change of 0.10 in brightness
  or more (`jarvis-visual-spec.json` `limits.flash`, enforced by
  `tests/flashgov.mjs`). This covers any new colour animation, not only the
  face. No strobe, no flicker, and no theme switch without the crossfade.
- **Face settings only slow down.** Speed is 0.25x to 1x, never faster
  (`tests/continuity.mjs:122-133`).
- **PC performance:** animate only `transform` and `opacity`. The streaming
  hairline once used `background-position` and cost 16 times the CPU
  (`style.css:170-180`).

### Rule 3. Contrast

- **Every new colour is a token.** It goes in `theme.css` (all three theme
  blocks) and in `Themes.kt`/`Chrome.kt` on the phone. A literal colour in
  a PC component fails `scripts/check-tokens.py`.
- **Body text 4.5:1 at worst, icons and edges 3:1. High Contrast is held to
  7:1** (`tests/themecheck.mjs:148-182`). Any new text/background pair is
  added to that `PAIRS` list.
- **Measure over a black AND a white backdrop on the PC.** The PC windows are
  see-through, and a pair once measured 9.8:1 over black and 2.21:1 over
  white (`tests/README.md`, "Why both backdrops"; `contrast.mjs:9-13`). So no
  new translucent panel may carry text unless it passes over both.
- **On the phone, text passes at the worst of all three surfaces**
  (`ThemeContrastTest.kt:26`). **The face's well stays near-black**
  (`ThemeContrastTest.kt:38-42`), and **glow can only be turned down**
  (`:128-133`).
- **Disabled is readable, not faded** (`style.css:1647-1668`,
  `tests/disabled.mjs`).

### Rule 4. Text scaling and touch size

- **PC:** Ctrl+= and the Settings text sizes zoom from 0.8x to 2.5x
  (`jarvis-link.js:952`, `a11y.mjs:246-282`). **Phone:** the app's text size
  multiplies the phone's own setting by 0.85x to 1.5x (`JarvisTheme.kt:415-423`,
  `:484-485`). A new layout must still work at 200%: nothing clipped, no
  one-word-per-line titles. That exact failure happened on approval titles and
  was fixed by giving the title its own line (`ApprovalCard.kt:276-284`).
- **No new text smaller than today's smallest step.** Protected surfaces
  (Rule 1) use at least the body-small size: 12px on the PC, 13sp on the phone.
- **Phone touch targets stay 48dp, even in Compact** (`JarvisTheme.kt:95-97`).
- **Fixed sizes break zoom:** the phone uses its type scale (`JarvisType`,
  `JarvisTheme.kt:229-310`). The PC has **no type-size tokens** (the "Type"
  block in `theme.css:214-219` names only font families). New PC text should
  use a small shared set of sizes, not another literal (see Clutter 5).

### Rule 5. Colour-blind safety

- **Colour is never the only signal.** A state also has a word, a shape or a
  position. This is tested: online and offline dots have different shapes and
  words (`a11y.mjs:216-244`), and graph groups use hue plus filled/hollow
  (`theme.css:168-179`).
- **Any new colour set that carries meaning goes into `tests/distinct.mjs`.**
  The pass mark is a colour difference of 15 or more (CIEDE2000, a standard
  measure; under 2 looks the same). If a word or shape always goes with the
  colour, the pass mark is 10, or 5 under colour-blindness, and the test must
  name that word or shape (`distinct.mjs:300-320`).
- **Gap 1: blue-yellow colour blindness is not simulated.** The test runs
  normal vision plus two red-green types (`distinct.mjs:326-330`), while
  `tests/README.md:29` says "three kinds of colour-blindness".
- **Gap 2: the phone has no colour-blind test.** `ThemeContrastTest.kt`
  checks contrast only. The phone's ok/warn/bad colours are not measured
  against each other.

### Rule 6. One look shared by both apps

- **The same three themes with the same names and descriptions:** Reactor,
  Daylight and High Contrast. Tested by `continuity.mjs:33-73`, which reads
  the phone's `Themes.kt`. Renaming or adding a theme on one side fails the
  build. The theme names are protected.
- **The shared direction already exists. It is "Instrument Deck"**
  (`docs/UI-AUDIT-2026-09-23.md:51-59`). Its four rules: status always
  visible in words; edges, not shadows; two fonts with clear jobs (reading and
  readouts); one moving thing at a time. A refresh builds on it and does not
  start a second style.
- **A visual change lands in both apps in the same piece of work**, or the
  reason one side is left out goes in `docs/ARCHITECTURE.md` §8, as
  CLAUDE.md requires for features.
- **Same curve, same scale of corner radii** (`JarvisTheme.kt:137-171`,
  `theme.css:203-206`). The numbers may differ, the proportions may not.
- **No new appearance settings.** The phone already has about fifteen look
  controls (`AppearanceScreen.kt:661-785`). A refresh changes the defaults.
  It does not add knobs.

### Rule 7. Phone battery and frame budget

- **No shadows, no live blur, no full-screen animated backgrounds, no film
  grain.** The measured costs are 8-20ms a frame for blur and 2-8ms for 20
  shadowed cards (`docs/UI-AUDIT-2026-09-14.md:185-199`,
  `Parts.kt:115-118`). The summary line: "the phone can afford one animated
  surface, at one bounded size" (`UI-AUDIT-2026-09-14.md:198`).
- **The high refresh rate is only for the face on Home, never in battery
  saver or when the phone is hot** (`DisplayRatePolicyTest.kt:21-60`).
- Still decoration drawn once (the tick ring round the face, a 1dp bevel
  line) and a small vibration are allowed (`Parts.kt:151`).

### Rule 8. Keep clear of Iron Man

The round-4 report found Marvel holds the JARVIS trademark for voice-assistant
software. It says the risk grows with "Iron Man visuals (arc-reactor rings)",
the "J.A.R.V.I.S." spelling, or film lines (`round4-character.md:305-311`).
The Reactor theme and the faces stay as they are, since they are protected.
A refresh adds **no more** arc-reactor imagery, no film-style lettering and
no "J.A.R.V.I.S." wordmark.

### Rule 9. Where visual personality may show

This follows the round-4 table (`round4-character.md:106-116`).
**Allowed:** the face, chat answers, and (my suggestion, not in round 4)
empty or idle states on Home. **Not allowed:** approval cards, errors,
refusals, security, lock screen, notifications and Settings rows.
Personality also never changes what a screen *says* about state (Rule 1, and
Instrument Deck's "status always visible").

### Rule 10. Private and locked screens

- On the phone, screenshots are blocked while App lock or hidden lists are on
  (`MainActivity.kt:621-630`). On the PC widget, App lock shows only
  "Jarvis is waiting for your approval" (`widget.js:613-615`). A refresh must
  not add a preview, a count or a picture that shows more than those words.
- Hidden memory lists show a plain "Show" row
  (`BrainScreen.kt:583`, `HiddenSection`). Keep it plain: no blurred list
  behind it.

---

## The budget: how much new per screen

**"One new visual idea"** means one thing the owner would notice as new, such
as a status strip, a new card style, or a still illustration. A layout tidy-up
that removes things does not count against the budget.

| Screen | New visual ideas allowed | Controls | Motion |
|---|---|---|---|
| Approval cards (all four places) | **0.** Readability and layout only | Never more. Deny and Approve stay the only decision buttons | None new |
| Errors, security, lock, notifications, Stop everything | **0** | Never more | None new |
| Phone Home / PC Jarvis bar | 1 | One in, one out | The face only at rest. At most one signal while an answer arrives (see Clutter 3) |
| Brain (both apps) | 1, and only after the phone's Brain is split (Clutter 1) | One in, one out | None at rest |
| Settings / Appearance | 0 new knobs. Grouping and headings are fine | Fewer, not more | None at rest |
| Widget (320px) | 0. It has no room | Never more | None at rest |
| HUD | 0 until it joins the theme system (Clutter 4) | - | - |
| Onboarding / pairing | 1 | - | One entry fade, 260ms or less |

**Before merging any visual change, all of these pass:**
`npm run test:tokens`, `test:themes`, `test:a11y`, `test:ui` (including
`continuity.mjs`), `tests/flashgov.mjs`, and on the phone
`ThemeContrastTest`, `FaceBudgetTest` and `DisplayRatePolicyTest`. If a
change adds a colour, it adds rows to `themecheck.mjs`'s `PAIRS` and, if the
colour carries meaning, to `distinct.mjs`. Note that `npm run test:all` runs
only some of the suites (`package.json` `test:ui` list). CI runs every
`tests/*.mjs` (`.github/workflows/ci.yml:98-114`), so CI is the real check.

---

## Clutter a refresh should REMOVE, not decorate

Worst first. Each one was checked in the file.

### 1. The phone's Brain screen is one long scroll of about 30 sections

`BrainScreen.kt:300-680` renders, one after another: Doing, Steps, Coming
up, Focus, Briefing, Web search, What asks first, Reach, Email sending,
Manner, Model, Hardware, Second graphics card, Big model, Deep questions,
Attention budget, Background work, Compute, Memory counts, Saved
automatically, Always keep in mind, History, Memory awaiting review, Wiki,
Watch, "What did I believe on this date?", Initiative, Ledger, Skills,
Capabilities and This backend. Status, settings and memory are mixed in one
list. The PC groups the same things into tabs with an "Advanced" fold
(`brain.html:53-125`). The professionalism audit already said the phone has
no Settings screen and spreads its settings over this one (table #15,
`PROFESSIONALISM-AUDIT-2026-09-26.md:57`). It is also still titled "Mind"
(`BrainScreen.kt:242`), though the owner renamed it "Brain" on 2026-09-26.
**Remove:** move settings to a Settings screen and group the rest the way
the PC does. No new styling is needed to make this better.

### 2. Engineering status dots on every desktop answer

The answer card's footer shows "Core", "Ollama" and "LiteLLM" dots
(`index.html:654-657`). They are names a beginner does not need on every
answer. The professionalism audit notes LiteLLM is not mentioned in the
README, INSTALL or ARCHITECTURE (`PROFESSIONALISM-AUDIT:76-81`). The
connection line already says "Offline" or "Stale" in words when something is
wrong (`continuity.mjs:224-232`). The dots only display (`main.js:920-939`).
When Core is down, the route badge already switches to "Offline" in words
(`main.js:941-950`). **Remove** the dots from the answer card and show service
health in Settings, keeping the "Ollama is not answering" fact reachable
there, because while Core is up the Ollama dot is the only place on the
bar that shows it. Two a11y tests read these dots
(`a11y.mjs:216-244`) and must move with them. They must not be deleted.

### 3. Four moving things while one answer arrives

While streaming, the Jarvis bar runs: a sliding highlight on the top edge
(`style.css:186-202`), a faster reactor spin (`style.css:397-410`), a pulsing
dot (`style.css:724-728`), and a blinking cursor (`style.css:895-905`). New
paragraphs also fade in (`style.css:914-916`). That is four signals for one
fact, "the answer is arriving". At rest the small reactor already runs four
loops of its own (`style.css:327-363`). **Remove** two of the streaming
signals. My suggestion is to keep the cursor and the reactor.

### 4. The HUD window's own colour world

`jarvis_hud.html:19-23` commits on purpose to "one dark visual world". It
does not load `theme.css` (only `fonts/fonts.css`, `:16`). It has about 114
literal colours (66 hex, 48 rgb/rgba, counted). It is not in the token check
(`scripts/check-tokens.py:12` lists five CSS files) or the theme-reach test
(`tests/themes-all.mjs:237-247` lists four pages and excludes only
`faces.html`, by name). Its graph uses 11 colours with no shape difference
(`jarvis_hud.html:800-812`, all nodes drawn as filled discs `:1208-1210`), and
"Brains" and "Projects" are **the same colour**, `#ffb648`. Measured with the
desktop's own colour-blind maths: **12 of the 55 colour pairs fall under the
floor of 15** under red-green colour blindness, and 3 are under 6. The Brain
window replaced exactly this kind of 10-colour palette because it failed
(`theme.css:168-179`, `distinct.mjs:279-284`). Its buttons are also
lower-case (`jarvis_hud.html:608-632`, per `PROFESSIONALISM-AUDIT:264-267`).
**Remove** the HUD's own palette and put it on the tokens, or state in
ARCHITECTURE why it stays apart and add it to the tests anyway. Do not add
any styling to it first.

### 5. Tiny text on the desktop

Across `style.css`, `widget.css`, `brain.css` and `settings.css`, 115
`font-size` declarations are between 9px and 11.5px (counted). There are no
size tokens, so each is a separate number. One of them is on a protected
surface: the widget shows the "someone tried to hurry you" warning at 10px,
and the quote itself at 10px italic, 85% opacity (`widget.css:900-915`). That
is the one line on the card where the attacker's own words are the point.
**Remove** the extra sizes by replacing them with 4-5 size tokens, and lift
protected text to at least 12px. Ctrl+= helps, but it should not be needed to
read a security warning.

### 6. Four different approaches to reduced motion

- PC Jarvis bar: nothing moves, and fades still run at 120ms
  (`style.css:1763-1790`).
- Widget: everything cut to 0.01ms (`widget.css:877-883`).
- HUD: everything cut to 0.001ms (`jarvis_hud.html:449-451`).
- Theme tokens: 1ms (`theme.css:402-408`).
- Phone: every duration to 0 (`JarvisTheme.kt:202`). It reads the setting
  once per screen (`:347-355`). I have not checked whether it notices a change
  while the app is open.
- **Settings has none.** `settings.css` has no reduced-motion block, and its
  "download in progress" sweep loops forever (`settings.css:524-527`).

**Remove** the variants and use one approach everywhere: the Jarvis bar's.
This is a small fix, not decoration.

### 7. Wording noise that looks like design noise

The professionalism audit found mixed lower-case buttons, "..." mixed with
"…", and mixed dashes (`PROFESSIONALISM-AUDIT:263-280`). A visual refresh
over mixed wording still looks unfinished. Do the wording pass first.

---

## Written claims that are wrong or out of date

- `docs/PROFESSIONALISM-AUDIT-2026-09-26.md:303-304` says "The phone has no
  automated contrast test like the desktop's." It has one now:
  `jarvis-client/app/src/test/java/com/jarvis/client/ui/theme/ThemeContrastTest.kt`.
- `jarvis-desktop/tests/README.md:29` says "three kinds of colour-blindness".
  `distinct.mjs` simulates two, both red-green.
- `theme.css:14` names `scripts/check-tokens.mjs` and `:23` names
  `scripts/check-contrast.mjs`. Neither exists. The real files are
  `scripts/check-tokens.py` and `tests/themecheck.mjs`.
- `theme.css:302`: Daylight's `--warn-faint` is still the old amber
  `rgba(138, 88, 0, …)`. The comment just above it (`:295-297`) says that
  amber was replaced because colour-blind readers could not tell it from red.
  It is only a faint wash, so the risk is low, but it is a leftover.
- `style.css:1660` says `disabled.mjs` "measures all four themes". There are
  three.
- `BrainScreen.kt:242` still says "Mind" and "State of mind", although the
  owner's 2026-09-26 decision renames it "Brain". Another piece of work may be
  doing this now. I did not check other branches.

## Not checked

- Anything on a real phone or a real Windows PC. No screenshots were taken.
- Whether the phone notices a change to "Remove animations" while the app is
  open.
- The Faces window (`faces.html`) beyond its flash governor. It keeps its own
  colours on purpose (`themes-all.mjs:242-246`).
- The contrast of the widget's 85%-opacity quote. It is not in any test's
  pair list, and I did not measure it.
- Whether anything other than the answer-card dots shows Ollama's health
  on the PC today (Clutter 2). I read only `main.js:920-950` and `:4125`.
