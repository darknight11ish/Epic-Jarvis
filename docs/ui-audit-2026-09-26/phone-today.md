# The phone app as it looks today (jarvis-client), 2026-09-26

Part of the cutting-edge UI audit. This part only takes stock: what the phone
app looks like now, what is already good, and what looks dated, uneven or
plain. Other parts of the audit make the proposals.

**Paths.** Unless a path says otherwise, it is under
`jarvis-client/app/src/main/java/com/jarvis/client/`. Line numbers are from
the repo at commit `1ce1dac`.

**How this was checked, and its limits.**
- I read the Compose code (Compose is the Android toolkit the phone app's
  screens are written in). There is no Android build in this container, and
  **the repo has no screenshots of the phone's screens.** The only phone
  pictures CI takes are face shots (`androidTest/.../FaceShotTest.kt`), and
  they are CI downloads, not files in the repo. So everything below about
  how things *look* comes from the code. Nobody has looked at it on a phone.
- The desktop screenshots in `jarvis-desktop/tests/shots/` are **out of
  date.** They were last changed in commit `7fda1b7` (2026-09-23). The widget
  shot shows Approve on the left of Deny, but the code now puts Deny on the
  left (`jarvis-desktop/src/widget.html:293-294`,
  `jarvis-desktop/src/card-words.js:32`). Use them for the general feel only.
- An earlier phone audit, `docs/UI-AUDIT-2026-09-23.md` ("Instrument Deck"),
  planned most of today's look, and most of it has been built. The points
  below are about what is left, or what that plan did not cover.

---

## 1. In short

1. **The phone's building blocks are careful and consistent.** There is one
   shared set of parts (plates, pills, toggles, buttons), one easing curve,
   measured colours, a crossfade between themes and reduced motion honoured
   everywhere. That is a solid base to add polish to. It does not need a
   redesign.
2. **The text barely steps up in size.** The two big text styles are never
   used anywhere (`displaySmall` 0 times, `headlineSmall` 0 times). Most text
   is the two smallest sizes (`bodySmall` 238 uses, `labelSmall` 181). There
   is no display font: the phone uses the phone's own font
   (`ui/theme/JarvisTheme.kt:231`), while the desktop uses Chakra Petch for
   titles and section headings (`jarvis-desktop/src/theme.css:217`,
   `brain.css:222`, `brain.css:600`). This is the biggest reason the phone
   will look plainer than the PC.
3. **Answers are shown as raw text.** The phone has no Markdown renderer
   (Markdown is the `**bold**` / `- list` formatting models write). A typed
   answer with a list or bold shows the asterisks and dashes as they are
   (`ui/screens/HomeScreen.kt:1985-1992`). The desktop formats them
   (`jarvis-desktop/src/markdown.js`).
4. **Mind is one very long scroll.** Mind is the phone's version of the
   desktop's Brain window. It is one list of about 33 sections
   (`ui/screens/BrainScreen.kt:255-720`, 37 `item(key = ...)` calls counting
   the hidden versions). Live status, settings (web search, manner, "what
   asks first") and memory are mixed together, with no way to jump between
   them. The desktop splits the same things into 8 tabs in a side rail
   (`jarvis-desktop/src/brain.html:51-115`) plus a separate Settings window.
5. **The phone still says "Mind", but the owner decided on "Brain".** On
   2026-09-26 the owner decided the screen is called "Brain" in both apps
   (CLAUDE.md). The phone still says "Mind" on the nav button
   (`HomeScreen.kt:1269`), the title (`BrainScreen.kt:242`), the face's
   screen-reader action (`HomeScreen.kt:1513`), the Appearance setting
   (`AppearanceScreen.kt:706`) and Help text (`FaqScreen.kt:144,159`). Another
   agent may already be changing this. I have not checked other branches.
6. **Idle Home is bare, and loading and errors look like placeholders.**
   With no conversation, the area under the face holds only a small
   "Quick note…" link (`HomeScreen.kt:966`, `1802-1804`; the reply plate is
   hidden when empty, `1944-1948`). Every "loading" state is the word
   "Reading…" in grey. Errors are written two different ways: "Could not read
   this: …" with a Retry button (`BrainScreen.kt:1361-1395`), and "Couldn't
   read the briefing: …" with no button, in about 15 plates (for example
   `BriefingPlate.kt:163`).
7. **A few small things look dated or don't match.** Seven "→" arrows are
   still typed as text, although the app's own rule replaced typed arrows
   with drawn chevrons (`Nav.kt:308-318`). The typing box on Home has no
   border or focus ring, but every other text field has one
   (`HomeScreen.kt:2255-2260` against `ui/parts/Parts.kt:660-664`). Swiping an
   approval card moves the card but shows nothing behind it
   (`ApprovalCard.kt:191-231`, `260`). The first screen a new owner sees
   (Pairing) is the word "JARVIS" and a form, with no face and no welcome
   (`PairingScreen.kt:124`). The desktop has a three-step welcome
   (`jarvis-desktop/src/onboarding.html:130,146,165`).
8. **Settings are hard to find.** Security (App lock and fingerprint), voice
   training, the voice check and custom voices open only from "Platform
   checks". To get there you tap the status line on Home
   (`ReadinessScreen.kt:240`, `MainActivity.kt:1339-1359`). The Home nav row
   offers only Mind, Inbox, Appearance and Help (`HomeScreen.kt:1258-1294`),
   and it is hidden until swiped by default.

---

## 2. Inventory: every screen and how you get there

`Screen` enum, `ui/Nav.kt:74`: HOME, BRAIN, INBOX, CHECKS, APPEARANCE, FAQ,
VOICE, SECURITY, VOICE_CHECK, VOICES, HISTORY. Before pairing there is also
PairingScreen, and a crash screen that can appear at any time.

| Screen | File | How you reach it | What it is |
|---|---|---|---|
| Pairing | `ui/screens/PairingScreen.kt` | first launch; "Change desktop or token" | "JARVIS" wordmark in the accent colour (`:124`), address and token fields, long help text (`:144-150`) |
| Home | `ui/screens/HomeScreen.kt` | start | status line, optional nav row, face in a dark well, drag handle, conversation list, typing box |
| Mind (Brain) | `ui/screens/BrainScreen.kt` | nav row "Mind", tap the face, "State of mind →" | one long list, ~33 sections (§1 point 4) |
| Inbox | `ui/screens/InboxScreen.kt` | nav row "Inbox · N" | mute toggle, today's brief, running jobs, the undo shelf |
| Platform checks | `ui/screens/ReadinessScreen.kt` | tap the status line | phone permissions and connection; also the only way to Security and the voice screens |
| Appearance | `ui/screens/AppearanceScreen.kt` | nav row | theme, Home layout, face preview and editor, face picker, state colours, "More options" |
| Help | `ui/screens/FaqScreen.kt` | nav row | questions you can open and close |
| History | `ui/screens/HistoryScreen.kt` | Mind, Chat history | past chats kept on the PC |
| Security | `ui/screens/SecurityScreen.kt` | Checks | App lock, fingerprint, hiding private lists |
| Train my voice / Voice check / Jarvis's voice | `VoiceTrainingScreen.kt`, `VoiceCheckScreen.kt`, `VoicesScreen.kt` | Checks | voice setup |
| Crash | `ui/screens/CrashScreen.kt` | when something breaks | colours typed in directly **on purpose**, so it still works if the theme code is what broke (`:20-28`) |

**Navigation.** The app keeps its own list of screens for Back
(`Nav.kt:91-160`). Android 14's back gesture previews: the screen shrinks,
rounds its corners and follows your finger (`Nav.kt:276-300`). Moving between
screens fades and rises 8dp (`Nav.kt:264-272`). This switches off under
reduced motion or the "Screen transitions" setting. Every sub-screen shares
one top bar with a drawn chevron and the word "Back" (`BrainScreen.kt:1683-1724`,
`Nav.kt:352-366`). There is no bottom tab bar. The nav row slides down under
the status line when you swipe or tap the chevron (`HomeScreen.kt:731-740`,
`1221-1254`).

---

## 3. Inventory: the design system (theme tokens)

A **design token** is a named value (a colour, a size, a speed) that every
screen reads, instead of typing the number in each place.

**Colours** (`ui/theme/Chrome.kt:221-316`, values in `ui/theme/Themes.kt`):
- Three themes: **Reactor** (default, cool near-black, `Themes.kt:73-95`),
  **Daylight** (light panels, but the face keeps a dark "well" behind it,
  `:112-142`) and **High Contrast** (`:151-173`). Every contrast figure is
  measured and written next to the value.
- Three layers of panel colour (`surface0/1/2`), three text strengths
  (`textHi/Mid/Lo`), three edge lines (`hairline`, `hairlineStrong`,
  `hairlineFocus`), and ok / warn / bad in a text version and an icon
  version. `cloudInk` (violet) marks "this is leaving your machine".
- **There is no accent-colour setting, on purpose.** The accent is worked out
  from the colour chosen for Jarvis's "idle" state (`Chrome.kt:362-381`), so
  the caret, focus ring and selected items always match the face. The
  desktop does the same (`jarvis-desktop/src/jarvis-link.js:748,807`).
- A 500ms crossfade between themes, skipped under reduced motion
  (`JarvisTheme.kt:373-394`).

**Shape** (`JarvisTheme.kt:143-171`): corners of 18 / 14 / 10 / 8dp, a fully
round pill that means "this is a label, not a button", and a "Sharp" option.

**Spacing** (`JarvisTheme.kt:99-117`): Comfortable or Compact. Touch targets
stay 48dp in both.

**Motion** (`JarvisTheme.kt:181-210`): one easing curve, the desktop's exact
`cubic-bezier(0.22, 1, 0.36, 1)`. Three speeds: 120, 200 and 280ms. All
become zero when the phone asks for less animation.

**Panel edges** (`JarvisTheme.kt:126-135`): Hairline (default), Bevel (a
lighter line along the top edge) or None. **No shadows anywhere**, because a
shadow costs time on every frame while scrolling (`ui/parts/Parts.kt:112-119`).

**Type scale** (`JarvisTheme.kt:229-310`). A type scale is the fixed list of
text sizes and weights. The phone's: display 34sp light, headline 22, title
22 / 18 / 16 semibold, body 17 / 15 / 13, label 15 / 13 / 11 (the 11sp
"kicker" is uppercase and spaced out), plus `machine` (monospace, for model
names and ids) and `telemetry` (small monospace readouts). Font: the phone's
own (`:231`, `:234`). How often each style is used in `ui/`, outside the
theme file:

| Style | Uses |
|---|---|
| displaySmall (34sp) | **0** |
| headlineSmall (22sp) | **0** |
| titleLarge | 2 |
| titleMedium | 4 |
| titleSmall | 45 |
| bodyLarge | 12 |
| bodyMedium | 75 |
| bodySmall (13sp) | **238** |
| labelMedium | 36 |
| labelSmall (11sp) | **181** |
| telemetry | 1 (the ON/OFF inside a toggle, `Parts.kt:858`) |
| machine | 3 |

The comments about the font disagree with each other. `JarvisTheme.kt:223-227`
still says "TODO: bundle IBM Plex Sans". `:301-302` says "the owner chose to
keep the built-in ones". That choice was question 2 in
`docs/UI-AUDIT-2026-09-23.md` §6. **Treat the font as the owner's decision.**
Using a display font for headings only (the desktop's Chakra Petch) would be
a new question for the owner, not a fix.

---

## 4. Inventory: the shared parts (`ui/parts/Parts.kt`)

| Part | Lines | Look |
|---|---|---|
| `pressable` | 83-110 | a small spring "press" (scale 0.972) instead of Android's ripple effect; no scaling under reduced motion |
| `Plate` | 120-194 | a flat panel with a 1dp edge line; optional bevel |
| `Kicker` | 203-211 | an 11sp uppercase heading, spaced out, in `textLo` (the faintest text colour) |
| `Pill` | 221-240 | round label, tinted 13% |
| `Dot` | 243-246 | status dot, always next to a word |
| `Freshness` | 270-305 | "Link live · board read 2 min ago" / "stale…" line |
| `Field` | 337-368 | label on the left, value on the right |
| `Meter` | 378-411 | thin bar that glides to its value |
| `Affirm` / `Refuse` | 422-472 | Approve filled, Deny outlined, so they differ in shape and not only in colour |
| `Quiet` | 475-499 | text button in the accent, 48dp target |
| `Primary` / `Secondary` | 520-613 | boxed buttons: tinted fill and strong edge, or plain edge |
| `TextInput` | 623-700 | flat field with an edge; a 2dp accent ring while typing |
| `Notice` | 712-762 | amber-tinted dismissible warning, with Details and one fix button |
| `Toggle` | 794-881 | on/off switch with the word ON/OFF inside, a square-ish thumb |
| `Section` | 907-933 | kicker heading plus content |
| Icons (`ui/parts/NavIcons.kt`) | 67, 87, 111, 127 | only four drawn line icons (Mind, Inbox, Appearance, Help). No other icons in the app. |
| `VoiceButton` (`ui/parts/VoiceButton.kt`) | ~60-160 | 48dp hold-to-talk button, a drawn microphone, a ring that grows with your voice |

---

## 5. Inventory: Home, the face and the cards

**Home, top to bottom** (`HomeScreen.kt:718-920`):
1. **Status line**, always there (`:1074-1214`): a dot plus words ("Linked ·
   Local · 2 waiting · model", "Stale — reconnecting", "Offline"), the step
   Jarvis is on, Retry when offline, and a chevron for the nav row.
2. **Nav row** (hidden by default): four icon-and-word buttons
   (`:1258-1294`).
3. **Face pane**: a dark rounded well (`:1476-1482`) holding the face, a still
   ring of 60 tick marks like a gauge's edge (`:1599-1633`), a Local / Cloud
   pill (`:1636-1648`) and "State of mind →" (`:1568`). By default the face
   takes 75% of the height (`:146`). You can drag it from 20% to 85%
   (`:149-150`). Face sizes are Full screen, Extra large, Large, Medium or
   Hidden (`data/AppearanceStore.kt:550-554`).
4. **Drag handle**, 48dp tall with a pill in the middle (`:1329-1408`).
5. **Conversation list** (`:930-1053`): Stop everything, task controls, Quick
   note, a notice, "Approvals are off", "Waiting on you" with the approval
   cards, and last the reply.
6. **Reply** (`:1926-2066`): a "You" kicker with your question, a "Jarvis"
   kicker (in the accent while streaming), the answer as plain paragraphs,
   then Copy / Share, "Used 2 memories", Right / Wrong and New conversation.
7. **Typing box** (`:2194-2330`): Photo, the field ("Ask Jarvis"), a Send
   button that turns into Stop, and the microphone.

Full screen swaps the list and typing box for the answer's first lines and a
centred microphone (`:2371-2422`).

**The face.** All 20 of the desktop's faces draw on the phone. Most are drawn
with Compose, one uses a GPU shader and two use OpenGL (`AppearanceScreen.kt:554-585`,
`face/`). A quality governor lowers the detail when frames run late
(`face/FaceBudget.kt:34-75`). Rules to keep:
- The face is the only thing that is always moving (`Nav.kt:225-226`,
  `HomeScreen.kt:1589`).
- Appearance shows **one** live preview, not a grid of live ones, because of
  flash and battery limits (`AppearanceScreen.kt:459-485`). The face picker
  uses still pictures (`AppearanceScreen.kt:1137-1204`, handed in at
  `MainActivity.kt:1793`).
- The well must stay dark on every theme (`Chrome.kt:317-323`).

**Approval card** (`ui/approval/ApprovalCard.kt:257-490`): a panel with an
amber edge at 35% (`:264-268`), a deadline bar running down along the top
(`:277-280`), the "Needs your OK" kicker and an amber title (`:292-302`), a
reach badge, the summary, plan options, a red "tried to rush you" chip, a
line saying why it can or cannot be swiped, with a drawn glyph (`:344-370`),
Show detail, "Add a note before deciding", then **Deny (outlined, left) and
Approve (filled, right)** (`:478-481`), with a vibration on each (`:160-168`).
When you swipe, the card follows your finger and springs back. Nothing shows
underneath it (`:191-231`, `:260`).

**Empty and error states.**
- Idle Home: nothing but "Quick note…" under the face (§1 point 6).
- Loading: the word "Reading…" everywhere (`Parts.kt:296`,
  `BrainScreen.kt:1387`, and about 15 plates).
- Failed: two different sentences, and only one of them has a button (§1
  point 6). Mind's own `SectionUnread` shows three clear states: reading,
  "Not on this backend", or failed with Retry (`BrainScreen.kt:1355-1395`).
- Empty lists get honest one-liners ("Nothing waiting.", `InboxScreen.kt:363`;
  "No topics watched.", `WatchPlate.kt:119`) with no picture or next step.

---

## 6. Side by side with the desktop

These cover the places where the same thing appears in both apps.
`tools/check_parity.py` checks features, not looks. The continuity audit
(`docs/CONTINUITY-AUDIT-2026-09-26.md`) found the card words identical in
both apps.

| Thing | Phone | Desktop | Same? |
|---|---|---|---|
| Theme names | Reactor, Daylight, High Contrast | the same names, older ids (`theme.css:240-262`) | yes |
| Accent colour | worked out from the idle colour | the same function (`jarvis-link.js:748`) | yes |
| Easing | `0.22, 1, 0.36, 1` | `--ease`, the same (`theme.css:224`) | yes; phone durations are shorter on purpose |
| Card buttons and words | Deny left, Approve right; "Needs your OK" | the same (`card-words.js:15,32`) | yes |
| Heading font | the phone's own font, 11sp kicker in faint grey (`Parts.kt:208`) | Chakra Petch, uppercase, **in the accent colour** (`brain.css:600-605`) | **no**: the desktop's headings have more character |
| Depth | edge lines only, no shadows | shadows and an accent glow (`theme.css:230-235`) | different on purpose (phone frame time) |
| Answer formatting | raw text | Markdown (`markdown.js`) | **no** |
| Brain layout | one long scroll called "Mind" | 8-tab rail called "Brain" with small glyphs (`brain.html:36-115`) | **no**: name and layout both differ |
| Brief rows | title and summary only (`InboxScreen.kt:236-247`) | a small kind chip per row, e.g. APPROVAL / JOB / FINDING (`style.css:1897-1909`) | **no** |
| Welcome | pairing form only | three-step onboarding page | **no** (it may be fine for the phone to differ, but it should be written down) |

---

## 7. What already feels polished (keep it)

- **One set of parts, applied everywhere.** Android's stock buttons, switches,
  text fields and ripples are gone. Everything is drawn from the app's own
  parts (`Parts.kt`). I found no stray colours outside the theme except the
  crash screen, which is on purpose.
- **The dark well with the tick-mark ring** gives the face a "gauge set into
  a dashboard" look, costs almost nothing per frame (`HomeScreen.kt:1586-1633`),
  and keeps Daylight working.
- **Status is honest and always on screen**, in words, never by colour alone
  (`HomeScreen.kt:1086-1111`).
- **Movement is careful.** The spring press, the swipe-back preview, the
  theme crossfade, the nav row sliding in, the face shrinking to make room
  for an approval (`HomeScreen.kt:623-640`) and the deadline bar all run on
  one curve and all respect reduced motion.
- **Approval cards stay plain and unmissable.** They use an amber edge,
  differ in shape as well as colour, include a vibration, and say plainly
  why a gesture will not work. Keep them this way.
- **The Appearance screen is rich but starts calm.** The face editor and
  "More options" start closed (`AppearanceScreen.kt:259`, `660-661`).
- **Screen-reader work is thorough.** It has headings, live announcements,
  switch roles, and actions for the drag handle (`HomeScreen.kt:1361-1383`).

## 8. What looks dated, uneven or plain

Ordered by how much each would change the first impression.

1. **Flat text sizes and no display font** (§3). The whole app reads as
   small grey text in the phone's default font. Big numbers on Mind were
   planned on 2026-09-23 (`docs/UI-AUDIT-2026-09-23.md` Phase 3, "big numbers
   on Mind") and never built: `displaySmall` is unused. The monospace
   readout style is used once.
2. **Raw Markdown in answers** (§1 point 3). It is the most-read thing in the
   app, and it looks broken whenever the model uses a list or bold.
3. **Mind is a ~33-section scroll with the old name** (§1 points 4-5). It
   mixes live status with settings, and every section has the same weight:
   a faint grey kicker over a plate.
4. **Home looks empty when idle and plain when loading** (§1 point 6).
   There is no greeting, no hint of what to ask, and no calm "Jarvis is
   ready" moment under the face.
5. **Pairing is a form, not a welcome** (§1 point 7). It is the first
   impression, and the face does not appear on it.
6. **Small mismatches:**
   - typed "→" in seven places: `HomeScreen.kt:1568`, `InboxScreen.kt:256`,
     `BrainScreen.kt:1016`, `SecondCardPlate.kt:117`, `HardwarePlate.kt:233`,
     `BigModelPlate.kt:167`, `approval/CardWaitingLine.kt:66`;
   - the Home typing box has no border or focus ring
     (`HomeScreen.kt:2255-2260`), unlike `TextInput`;
   - Inbox types "TODAY'S BRIEF" by hand instead of using `Kicker`
     (`InboxScreen.kt:216-221`), and gives it the warning colour;
   - "Could not read" and "Couldn't read" are both used, and only one comes
     with Retry;
   - the "streaming hairline" (a thin accent line while an answer arrives)
     is described in `Chrome.kt:166-170` but is still not drawn;
   - the swipe on an approval card shows nothing underneath it, although a
     reveal was planned (`docs/UI-AUDIT-2026-09-23.md` §3, Approval card);
   - there are only four icons in the whole app, so every Mind section,
     Inbox list and settings row is text only;
   - there is a stale font TODO (`JarvisTheme.kt:223-227`).
7. **Settings live under "Platform checks"** (§1 point 8), which is
   something you would not expect.

## 9. Limits for anyone proposing changes

- The face is the only thing that moves all the time. Anything else moves
  only when something happens, and follows the Motion setting and reduced
  motion (`Nav.kt:225-226`, `JarvisTheme.kt:181-207`).
- No blur, no shadows, no full-screen overlays, no film grain on the phone
  (`Parts.kt:112-119`; perf-14 in `docs/UI-AUDIT-2026-09-23.md`). Still
  decoration drawn once and cached, like the tick ring, is fine.
- There is one live face preview at a time. The well stays dark. Glow and
  Motion settings can only reduce, never increase.
- Every colour pair is measured. A new colour needs its contrast measured
  against all three panel colours on all three themes (`Chrome.kt:216-219`).
- Approval cards stay plain: Deny on the left and outlined, Approve on the
  right and filled, no decoration that could hide a word, and nothing that
  approves by itself.
- The font is the owner's choice (§3).
- Anything new has to compile on CI only (about 15 minutes per try), so
  group changes.

## 10. Not checked

- How any of this actually looks on a phone (no build, no screenshots).
- Whether another branch or agent is already renaming Mind to Brain.
- The full content of Checks, Help, History and the voice screens beyond
  their structure. I read the headings and the entry points, not every line.
- The face renderers themselves (`face/Faces.kt`, `face/gl/`), beyond the
  budget rules.
