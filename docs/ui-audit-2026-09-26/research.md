# Cutting-edge UI research for Jarvis (September 2026)

Part of the UI audit. The owner asked for ways to "visually spice up" the phone
app and the desktop app "while still retaining a focus on what it is and not
overwhelming users". This file is the outside research: what the best AI
assistants and "ambient" apps (apps that sit quietly in the background and only
speak up when needed) are doing in 2025-2026, and which of those ideas fit
Jarvis.

Read-only research. Nothing in the repo was changed. Every claim about the
Jarvis code has a `path:line` next to it; every outside claim has a link.
Where something was not checked, it says so.

## The short version

1. **Jarvis is already ahead of most of this list on the basics.** It already
   has springy press feedback, predictive back, haptics on approvals, Mica and
   Acrylic window glass, a reduced-motion switch, contrast tests on every theme,
   and two home-screen widgets. The gains now are in *polish and presence*, not
   in a new look.
2. **The biggest win is "motion that means something":** real spring physics
   everywhere (not only on button presses), and the face reacting to the voice
   - both the owner's and Jarvis's own.
3. **The best new platform feature to use is Android 16's "Live Updates"**
   (timers, focus sessions and running tasks as a small chip in the phone's
   status bar). Jarvis's timers and focus sessions are a textbook fit.
4. **Do not chase Apple's Liquid Glass.** Apple itself walked it back in 2026
   because see-through panels made text hard to read. Jarvis's contrast tests
   exist for exactly this reason.
5. **Do not adopt Material 3 Expressive wholesale yet.** Its theme is still
   experimental (alpha only) and the app's pinned library version does not
   include it. Borrow the ideas instead.
6. **Keep approval cards out of all of this.** Every idea below either leaves
   them alone or makes them *more* plain and unmissable, never prettier.

## How to read each idea

- **What it is** - in plain words.
- **Real example** - one shipping product, with a link.
- **Can we build it?** - on the phone (Jetpack Compose, the toolkit the Android
  app is written in) and on the desktop (a Tauri window, which on Windows is a
  web page shown by WebView2, Microsoft's built-in copy of the Edge browser
  engine). Cost is rough: **small** (a day or less), **medium** (a few days),
  **large** (a week or more).
- **Fit** - does it suit a private, calm, local assistant?
- **What Jarvis has today** - checked against the files.
- **Verdict** - Do / Try / Later / Skip.

## Summary table

| # | Idea | Phone | Desktop | Verdict |
|---|------|-------|---------|---------|
| 1 | Spring motion everywhere | small | small | **Do** |
| 2 | Face reacts to the voice (both directions) | medium | medium | **Do** |
| 3 | Honest "what I'm doing" status line | small | small | **Do** |
| 4 | Android 16 Live Updates for timers and focus | medium | n/a | **Do** |
| 5 | One variable font on both apps | small | small | **Do** |
| 6 | Calm "ambient" idle mode | medium | medium | **Try** |
| 7 | Ready-made answer cards (timer, weather, calendar) | medium | medium | **Try** |
| 8 | "Next up" glanceable widget | medium | n/a | **Try** |
| 9 | Screen-edge listening glow | small | small | **Try** |
| 10 | Container transforms (a card grows into its page) | medium | medium | **Try** |
| 11 | A small haptics vocabulary | small | n/a | **Try** |
| 12 | Raycast-style quickbar polish | n/a | medium | **Try** |
| 13 | Material 3 Expressive ideas, hand-built | medium | small | **Try (borrow, not adopt)** |
| 14 | Mica / Acrylic on more windows | n/a | small | **Try, carefully** |
| 15 | A sci-fi HUD rulebook (restraint) | - | - | **Do (as a rule)** |
| 16 | Dot-matrix / monochrome accents (Nothing OS) | small | small | **Later** |
| 17 | GPU shader glow (AGSL) on the phone | medium | n/a | **Later** |
| 18 | Predictive back polish | small | n/a | **Already done; tiny polish** |
| 19 | Wallpaper colours (Material You) | small | small | **Skip** |
| 20 | Windows accent colour in the app | small | small | **Skip** |
| 21 | Liquid Glass-style see-through panels | large | medium | **Skip** |
| 22 | Model-generated UI (Gemini "dynamic view") | large | large | **Skip** |
| 23 | New gestures / card decks (Rabbit, Humane) | medium | n/a | **Skip** |

---

## A. Motion and feel

### 1. Spring motion everywhere - **Do**

**What it is.** "Spring motion" means an animation driven by a pretend spring
(how stiff it is, how much it wobbles) instead of a fixed timing curve. It
feels physical: things settle, and if you interrupt them mid-way they carry on
smoothly from where they are instead of jumping. Google's 2025 design update
made springs the default for all of Android.

**Real example.** Material 3 Expressive's "motion physics system":
<https://m3.material.io/blog/m3-expressive-motion-theming>. On Pixel phones,
notifications stick together and snap away when swiped
(<https://9to5google.com/2025/09/03/android-16-qpr1-pixel/>).

**Can we build it?**
- Phone: yes, built into Compose (`spring()`). **Small.**
- Desktop: yes. Modern CSS has `linear()`, a timing function that can hold a
  sampled spring curve, so no JavaScript is needed
  (<https://developer.chrome.com/docs/css-ui/css-linear-easing-function>,
  generator: <https://www.kvin.me/css-springs>). WebView2 is Chromium-based,
  and `linear()` has been in Chromium since version 113. **Small.**

**Fit.** Good, if the springs are *critically damped or nearly so* (they
settle without visible bouncing). Bouncy springs read as playful, which is the
wrong tone for approvals and memory.

**What Jarvis has today.**
- Phone: presses already use a spring
  (`jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/Parts.kt:94`,
  `Spring.DampingRatioMediumBouncy`). Every other animation uses fixed-time
  `tween` curves (`ui/theme/JarvisTheme.kt:204-206`), and reduced motion sets
  their time to zero (`JarvisTheme.kt:202`).
- Desktop: one easing curve and three durations as tokens
  (`jarvis-desktop/src/theme.css:224-228`), collapsed to 1 ms under reduced
  motion (`theme.css:402-407`).

**Verdict.** Add a `spring` token next to `--ease` on the desktop (a `linear()`
value) and a `spring()` spec next to `micro()/enter()/state()` on the phone,
used for things that *move* (sheets, cards, the face's size). Keep fades on the
current curves. The reduced-motion switch must still collapse both. Note the
existing press spring is the "medium bouncy" preset - worth checking by eye
whether that is too playful next to the rest.

### 2. The face reacts to the voice, both ways - **Do**

**What it is.** While you talk, the assistant's visual moves with your voice;
while it answers, it moves with its own speech. It is the main way modern
voice assistants show "I'm with you" without words.

**Real examples.**
- Gemini Live's 2026 refresh: a blue waveform pill that grows with how loud and
  how long you speak, plus a soft animated background glow
  (<https://www.sammyfans.com/2026/05/14/google-quietly-refreshing-gemini-live-with-new-interactive-ui/>,
  <https://www.androidauthority.com/gemini-overlay-live-neural-design-apk-teardown-3690991/>).
- ChatGPT moved voice *into* the chat in November 2025 (live transcript on
  screen while you talk), keeping the old full-screen orb as an option
  (<https://www.macrumors.com/2025/11/26/chatgpt-voice-mode-update-seamless-chat/>).

**Can we build it?**
- Phone: the microphone level is already read ~50 times a second and drawn as a
  halo on the talk button without recomposing
  (`ui/parts/VoiceButton.kt:61-65, 97-104`). Feeding the same number, and the
  level of Jarvis's own speech playback, into the face is **medium** - the face
  has a frame budget and quality tiers (`face/FaceBudget.kt`) that must stay in
  charge.
- Desktop: the Web Audio API's analyser can read a level from the playing
  answer; not currently used (no `AnalyserNode` in `jarvis-desktop/src/*.js` -
  checked by search). **Medium.**

**Fit.** Very good. It carries meaning (who is talking), needs no extra text,
and nothing leaves the device. Under reduced motion, keep a non-moving signal
(e.g. brightness), the same way the desktop keeps the hairline when it stops
the scan (`jarvis-desktop/src/style.css:214-219`).

**Verdict.** Do. Also keep the ChatGPT lesson: the transcript stays visible
while speaking, so voice never hides what was heard.

### 3. An honest "what I'm doing" line - **Do**

**What it is.** Instead of a spinner, a single short line that says what the
assistant is actually doing ("Searching the web", "Reading your notes",
"Waiting for your yes"), often with a gentle shimmer across the text.

**Real example.** Current guidance for AI chat UIs: label the phase honestly,
no fake progress bars
(<https://thefrontkit.com/blogs/ai-chat-ui-best-practices>); a ready-made
shimmer component: <https://ui.elevenlabs.io/docs/components/shimmering-text>.

**Can we build it?** Both sides: **small** for the look, provided the backend's
event stream already names the step (not checked here - the backend lives
outside this repo).

**Fit.** Excellent, and it is more than decoration: it can say out loud when a
turn has read outside text (email, web, files), which is what the approval and
note-writing rules in CLAUDE.md hinge on. It builds trust by being specific.

**What Jarvis has today.** The desktop shows a moving hairline while an answer
streams, deliberately built to be cheap (only `transform`, measured)
(`jarvis-desktop/src/style.css:170-212`). There is no step label beside it
(not found by search for "thinking"/"shimmer" in `style.css` and `widget.css`).

**Verdict.** Do. Shimmer must switch off under reduced motion, like the scan.

## B. Glanceable and ambient

### 4. Android 16 "Live Updates" for timers, focus and running tasks - **Do**

**What it is.** Android 16 lets an ongoing notification be "promoted": it
appears as a small chip in the status bar and stays visible on the lock screen
while something is happening. It is Android's answer to the iPhone's Live
Activities. There is a new progress template with steps and milestones.

**Real example.** Android developer guide:
<https://developer.android.com/develop/ui/compose/notifications/live-update>.
Samsung's own version is the "Now Bar"
(<https://akexorcist.dev/live-notifications-and-now-bar-in-samsung-one-ui-7-as-developer-en/>).

**Can we build it?** Phone only. The app targets Android 16 (API 36)
(`jarvis-client/app/build.gradle.kts:80`) but supports down to Android 13
(`build.gradle.kts:79`), so it needs a fallback to a normal ongoing
notification. Rules: must be ongoing, have a title, no custom layout, not
"colorized"; the promotion setter needs API 36.1 and a manifest permission
(`POST_PROMOTED_NOTIFICATIONS`). Jarvis already posts ongoing notifications
(`service/ScheduleNotifier.kt:173`, `service/EventService.kt:352`,
`service/WakeWordService.kt:647`). **Medium.**

**Fit.** Very good for timers, a focus session's countdown, and "Jarvis is
doing X" for a running task. **Privacy caution:** the lock screen is visible to
anyone holding the phone. Timer and focus chips are harmless; a task title
might not be. Follow the existing App lock / "Hide memory lists and chat
history" rules, and never put approval details there (an approval chip must
say only "Jarvis is waiting for you" and open the locked app).

**Verdict.** Do, starting with timers and focus sessions.

### 6. A calm "ambient" idle mode - **Try**

**What it is.** When nothing is happening, the app quietens: the face slows and
dims, and the screen shows only the time and the next thing coming up. It
brightens the moment something needs you. This is "calm technology": a device
should need the smallest possible amount of attention and move to the edge of
your awareness when idle.

**Real example.** Amber Case's principles of calm technology:
<https://caseorganic.com/post/principles-of-calm-technology/>. Dia (the Arc
team's AI browser) aims to be "present when you need it, invisible when you
don't" (<https://www.viget.com/articles/the-dia-ai-browser>).

**Can we build it?**
- Phone: the face already has quality tiers and an automatic governor
  (`face/FaceBudget.kt:14-40`); an "idle" tier is a natural extension.
  **Medium.**
- Desktop: the widget already hides the face when it cannot be seen
  (`jarvis-desktop/src/widget.html:97-103`). An idle state for the HUD is
  **medium**.

**Fit.** Excellent - saves battery and GPU, and makes the moments when Jarvis
*does* light up mean more. Must never dim an approval card or an alarm.

**Verdict.** Try.

### 7. Ready-made answer cards - **Try**

**What it is.** For a few common answers (a timer, the weather, today's
calendar, a reminder), show a small designed card instead of a paragraph -
e.g. a timer that counts down in place with a Cancel button.

**Real example.** Google's generative UI research, where Gemini builds a
custom visual layout per answer
(<https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/>).
Jarvis should take the *idea* (visual answers) but not the *method* - see
idea 22.

**Can we build it?** Both sides, **medium** each: a fixed set of card designs,
filled with data the backend already sends. Timers are answered without the
AI model (CLAUDE.md, 2026-09-25), so a timer card works even when the model is
asleep.

**Fit.** Good if the set stays small (four or five kinds) and every card is a
fixed, tested template. The cards must look clearly different from approval
cards so the two are never confused.

**Verdict.** Try, starting with the timer.

### 8. A "Next up" glanceable widget - **Try**

**What it is.** A home-screen widget that answers one question at a glance:
what is next (the next alarm, timer or reminder, and whether anything is
waiting for you).

**Real example.** Google's widget "canonical layouts" (standard sizes and
shapes that look right on every launcher):
<https://android-developers.googleblog.com/2025/03/design-with-widget-canonical-layouts.html>;
generated widget-picker previews:
<https://developer.android.com/develop/ui/compose/glance/generated-previews>.

**Can we build it?** Phone: the app already uses Glance (Google's library for
widgets written like Compose) 1.1.1 (`build.gradle.kts:313-314`) for an
approval widget and a quick-link widget (`widget/ApprovalWidget.kt:68`,
`widget/QuickLinkWidget.kt:64`). **Medium.** Desktop: the always-on desktop
widget already exists; a "next up" line there is small (not measured).

**Fit.** Good. It must obey App lock the same way the desktop approval widget
does (short title only, per CLAUDE.md 2026-09-25).

**Verdict.** Try. Also add generated previews to the two existing widgets so
the widget picker shows what they really look like (small).

### 9. A screen-edge listening glow - **Try**

**What it is.** A soft band of light around the edge of the screen while the
assistant is listening.

**Real example.** Siri's Apple Intelligence edge glow
(<https://www.pocket-lint.com/how-to-get-new-siri-look-glowing-border/>);
Gemini's overlay moved to a similar full-screen glow in late 2025
(<https://9to5google.com/2025/11/24/gemini-overlay-fullscreen/>).

**Can we build it?** Phone: a `drawBehind` gradient stroke, **small**.
Desktop: a CSS gradient border on the HUD, **small** - animate only `transform`
and `opacity`, the lesson already written into `style.css:170-181`.

**Fit.** Medium. It is an unmistakable "I am listening" signal, which matters
for trust with a microphone. But: one glow colour must mean "listening" and
nothing else, and it must not look like an approval or alarm. Static under
reduced motion.

**Verdict.** Try, in the accent colour, only while the mic is open.

## C. Moving between screens

### 10. Container transforms (a card grows into its page) - **Try**

**What it is.** When you tap a memory fact or a task, the card itself grows
into the detail page instead of the page sliding in from the side. It shows
where you came from and where "back" goes.

**Real example.** Compose shared-element transitions, with debug tools added
in the April 2026 release
(<https://android-developers.googleblog.com/2026/04/jetpack-compose-april-2026-updates.html>);
on the web, the View Transitions API
(<https://developer.chrome.com/docs/web-platform/view-transitions>).

**Can we build it?** Phone: `SharedTransitionLayout`, **medium** (the app's own
screen switcher in `ui/Nav.kt` would need to host it). Desktop: same-page View
Transitions work in Chromium, so in WebView2; **medium**. Not checked on the
owner's exact WebView2 version.

**Fit.** Good for Brain (memory lists) and History. Not for approval cards -
they should appear plainly, not fly in.

**Verdict.** Try, on Brain first.

### 18. Predictive back - **Already done; tiny polish**

**What it is.** On Android 14+, a back swipe shows a preview of where you are
going before you let go.

**Real example.** <https://developer.android.com/guide/navigation/navigation-3/animate-destinations>.

**What Jarvis has today.** Done properly: the manifest opts in
(`AndroidManifest.xml:61`), and a `PredictiveBackHandler` makes the screen
follow the finger (`ui/Nav.kt:188-211`).

**Verdict.** Nothing to add except matching the preview's scale and corner
rounding to Google's spec, if it does not already (not checked visually).

## D. Colour, glass and type

### 5. One variable font on both apps - **Do**

**What it is.** A "variable font" is one font file that can smoothly change its
weight, width and other traits ("axes"), instead of shipping one file per
weight. It lets text thicken slightly when something becomes active, and lets
light-on-dark text be tuned so it does not look bolder than dark-on-light
(the "grade" axis).

**Real example.** Google Sans Flex, released as open source (SIL Open Font
Licence) in November 2025, six axes including weight, width, optical size,
grade and roundness (<https://www.omgubuntu.co.uk/2025/11/google-sans-flex-font-ubuntu>,
<https://design.google/library/google-sans-flex-font>).

**Can we build it?** Both sides, **small**. Compose supports variable font
settings on Android 8+; CSS `font-variation-settings` works in WebView2.

**What Jarvis has today - and a real inconsistency.**
- Desktop body text is `Segoe UI Variable Display` (Windows 11's own variable
  font) with a display font of Chakra Petch (`theme.css:215-217`). Bundled IBM
  Plex Sans is 400 weight only, so any bolder weight is faked by the browser
  (`jarvis-desktop/src/fonts/fonts.css`, header comment).
- Phone uses the platform default font, with a written TODO saying the
  product's own face (IBM Plex Sans) was never bundled because no font download
  was reachable from the build container (`ui/theme/JarvisTheme.kt:223-231`).
- So the two apps do not share a body font today.

**Fit.** Good: quiet, no extra colour or motion, makes both apps feel like one
product. Must re-run the contrast checks after any font change (thinner
strokes read as lower contrast even when the colours pass).

**Verdict.** Do: pick one open-licence variable body font (Google Sans Flex or
a variable IBM Plex Sans - the latter's availability **not checked**), bundle
it in both apps, keep Chakra Petch for display text only.

### 13. Material 3 Expressive, borrowed not adopted - **Try**

**What it is.** Google's 2025 update to its design system: bolder sizes and
colour contrast for the one key action on a screen, shapes that morph
(a pill turning into a rounded square when selected), wavy progress bars, and
spring motion. Google says its eye-tracking studies (46 studies, 18,000+
people) found users spotted key buttons up to 4x faster
(<https://design.google/library/expressive-material-design-google-research>).

**Can we build it - the catch.** The app pins Compose BOM `2026.06.00`
(`build.gradle.kts:284`), which maps to `material3` **1.4.0**
(<https://developer.android.com/develop/ui/compose/bom/bom-mapping>).
`MaterialExpressiveTheme` and the expressive components exist only in the
1.5.0 **alpha** line, behind an "experimental" opt-in
(<https://developer.android.com/jetpack/androidx/releases/compose-material3>).
Moving to an alpha library for looks means breaking changes on every update,
and each Android change costs a ~15-minute CI round trip to even compile
(CLAUDE.md). **Large and risky** to adopt; **medium** to hand-build the two or
three pieces that fit.

**Fit.** Partly. "Make the one important action easy to spot" fits approval
cards perfectly - but that is plainness, not decoration. Morphing shapes and
wavy bars are playful; a wavy bar could suit long jobs (a model install, the
memory self-test).

**Verdict.** Borrow: spring motion (idea 1), one emphasised action per screen,
maybe a wavy progress bar for long installs. Revisit the full theme when
1.5.0 is stable and in a BOM.

### 14. Mica and Acrylic on more windows - **Try, carefully**

**What it is.** Windows 11's own window materials. **Mica** is an almost
opaque backdrop lightly tinted by your wallpaper, for main app windows.
**Acrylic** is frosted glass, for short-lived pop-ups. "Mica Alt" is a stronger
tint for tabbed windows.
(<https://learn.microsoft.com/en-us/windows/apps/design/style/mica>,
<https://learn.microsoft.com/en-us/windows/apps/develop/ui/system-backdrops>).

**What Jarvis has today.** Acrylic on the quickbar, Mica (Acrylic fallback) on
the HUD, Acrylic on the desktop widget
(`jarvis-desktop/src-tauri/src/windows.rs:145-192`, called at `:71`, `:85`,
`:760`) - with Microsoft's own "Mica for app windows, Acrylic for pop-ups" rule
correctly quoted in the comments (`windows.rs:128-137`).

**Two things the owner should know (checked, not guessed):**
- `theme.css:231-234` says an acrylic backdrop "is not available on a current
  machine", while `windows.rs:145-166` applies Acrylic and explains that only
  the *tint colour* is ignored on new Windows 11 builds. The two comments
  disagree; one of them is out of date. Also `windows.rs:150` names
  `window-vibrancy 0.5.3`, but `Cargo.toml:36` asks for `0.6`.
- The HUD uses CSS `backdrop-filter: blur()` on its panels
  (`jarvis-desktop/src/jarvis_hud.html:285, 297, 330, 358`). Tauri has several
  open bug reports that this blur does not see through a transparent window
  (<https://github.com/tauri-apps/tauri/issues/12437>,
  <https://github.com/tauri-apps/tauri/issues/10064>). It may be doing little
  on the owner's PC. **Not checked on a real Windows machine.**

**Can we build it?** Brain and Settings could get Mica (they are long-lived
windows): one Rust call each, **small**. Their contrast must still pass the
over-black and over-white checks (`theme.css:22-27`).

**Verdict.** Try Mica on Brain and Settings; fix the two stale comments;
check the HUD blur on the real PC before relying on it.

### 19. Wallpaper colours (Material You) - **Skip**

**What it is.** Android can recolour an app from the user's wallpaper
("dynamic colour").

**Real example.** <https://developer.android.com/design/ui/mobile/guides/styles/color>.

**Why skip.** Jarvis's three themes are measured colour by colour, with exact
contrast numbers in the code (`ui/theme/Themes.kt:14-24, 36-57`), and a
colour-blind check on the ok/bad pair (`Themes.kt:20-24`). Wallpaper colours
cannot be measured in advance, and the face's palette is shared with the
desktop through `jarvis-visual-spec.json`. Google's own guidance allows
keeping brand colours for key actions. Not used today (no `dynamicColor` in
the phone code, checked by search). Skip.

### 20. Windows accent colour - **Skip**

The CSS keyword `AccentColor` exposes the Windows accent colour, but Chromium
only allows it for installed web apps, because it can be used to fingerprint
people (<https://groups.google.com/a/chromium.org/g/blink-dev/c/knAC85FErrE>).
Whether WebView2 exposes it is **not checked**. Same reasons as idea 19. Skip.

### 21. Liquid Glass-style see-through panels - **Skip**

**What it is.** Apple's 2025 design (iOS 26): controls made of refracting,
see-through "glass".

**Why skip.** Readability. Apple added a "Reduce Transparency" workaround in
2025 and, at WWDC 2026, lowered the default transparency and added a slider up
to fully opaque for iOS 27
(<https://www.macrumors.com/2026/06/10/how-liquid-glass-is-changing-in-ios-27/>).
Jarvis already learned this lesson: its transparent windows are contrast-tested
over both black and white wallpapers (`theme.css:22-27`), and the light theme
is deliberately opaque (`theme.css:259-262`). Skip. (If anything, one small
"lens" effect on the face alone would be the place to play - not text.)

## E. Presence and personality

### 15. A sci-fi HUD rulebook - **Do (as a written rule)**

**What it is.** Film interface studios (Territory Studio: *Blade Runner 2049*,
Marvel films) design HUDs that "guide without pulling focus, reassure without
demanding attention and remain readable when required"
(<https://www.aerosociety.com/news/from-hollywood-to-aerospace/>). Their
real-world lesson is restraint: one accent colour, thin lines, numbers in a
fixed-width font, and motion only when a state changes. Gallery of examples:
<https://www.hudsandguis.com/home/2018/blade-runner-2049>.

**What Jarvis has today.** Already this style: Reactor is "near-black ...
one cyan accent, everything else grey" (`theme.css:252-253`); a mono font is
reserved for machine strings (`JarvisTheme.kt:233-234`, `FontFamily.Monospace`).

**Verdict.** Write it down as the test for every idea in this audit: *each
new moving or glowing thing must mean a state, and each state gets one visual
signal.* It stops "spice" from turning into clutter.

### 16. Dot-matrix and monochrome accents (Nothing OS) - **Later**

**What it is.** Nothing's phones use a retro dot-matrix font and, on the Phone
(3), a tiny grid of 489 LEDs for glanceable status
(<https://design-milk.com/the-nothing-phone-3s-glyph-matrix-turns-notifications-into-pixel-art/>).

**Fit.** A dot-matrix style could suit an idle "ambient" face or the desktop
widget's clock. But it is a strong style, and Jarvis already has a clear look
(Chakra Petch, the reactor). **Later**, possibly as a face pattern - the face
patterns are shared data (`jarvis-desktop/src/jarvis-visual-spec.json`, "9
pattern kinds"), so it would have to be added on both sides.

### 17. GPU shader glow on the phone (AGSL) - **Later**

**What it is.** AGSL is Android's small shader language: tiny programs that
run on the graphics chip to draw glows, grain or ripples cheaply
(<https://developer.android.com/develop/ui/views/graphics/agsl/using-agsl>).

**Can we build it?** Every phone Jarvis supports can, because AGSL needs
Android 13 and the app's minimum is Android 13 (`build.gradle.kts:79`).
**Medium.** But the face already has its own GL renderers
(`face/gl/MembraneRenderer.kt`, `face/gl/TokamakRenderer.kt`) and a frame
budget; a second GPU effect competes with it for battery.

**Verdict.** Later, and only inside the face's budget.

### 11. A small haptics vocabulary - **Try**

**What it is.** Haptics are the phone's small vibrations. Android's guidance:
prefer "clear" crisp taps tied to real events, use the named system effects
(Confirm, Reject, tick) so every phone does the right thing, avoid "buzzy"
long vibrations, and match them with what is on screen
(<https://developer.android.com/develop/ui/views/haptics/haptics-principles>).

**What Jarvis has today.** Confirm on approve and Reject on deny
(`ui/approval/ApprovalCard.kt:160-167`); LongPress and Reject on the talk
button (`ui/parts/VoiceButton.kt:113, 147`).

**Verdict.** Try a few more, each tied to one event: a light tick when Jarvis
starts listening, and when a sheet snaps into place. Never a haptic on an
incoming approval that could be mistaken for "done". Skip on desktop (PCs have
no general haptics).

### 12. Raycast-style quickbar polish - **Try**

**What it is.** Raycast (a keyboard launcher for Mac and now Windows) is the
reference for command palettes: a very dark, quiet surface ladder, hairline
borders, small corner radii, colour used rarely, and every action showing its
keyboard shortcut (<https://manual.raycast.com/ai/chat>; design notes:
<https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/raycast/DESIGN.md>).

**What Jarvis has today.** The quickbar is already a spotlight-style bar with
Acrylic (`windows.rs:126-145`), and the token file already uses a quiet surface
ladder (`theme.css:41-50`). Whether the quickbar shows shortcut hints for its
actions was **not checked**.

**Verdict.** Try: shortcut hints and an action list under the input. Desktop
only (the phone has no keyboard shortcuts).

## F. Things to avoid

### 22. Model-generated UI (Gemini "dynamic view") - **Skip**

Gemini 3 writes custom interactive code for each answer
(<https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/>).
For Jarvis this means running code a local 8B model just wrote, inside a
window that holds the pairing key and can approve actions. That is a security
problem, not a style choice. Use fixed templates instead (idea 7).

### 23. New gestures and card decks (Rabbit, Humane) - **Skip**

rabbitOS 2 (September 2025) rebuilt the Rabbit R1 around a swipeable deck of
colourful cards (<https://www.rabbit.tech/newsroom/rabbitos-2-launch>). The
Humane AI Pin projected a UI onto your palm, controlled by tilting your hand; a
common post-mortem point is that the gestures were hard to learn and the
display hard to read outdoors
(<https://infinum.com/blog/ai-pin-ux-design-review/>). Lesson for Jarvis: use
the gestures people already know (tap, swipe back, the existing
swipe-to-decide on approval cards) and do not invent new ones.

---

## Ground rules any change must keep

From the task brief and CLAUDE.md, restated so the design team has them in
one place:
- The three themes and their names (Reactor, Daylight, High Contrast on the phone,
  `Themes.kt:39, 78, 117`; `deep-space`, `paper`, `high-contrast` in
  `theme.css:252-335`) stay.
- The contrast, colour-blind and accessibility tests
  (`jarvis-desktop/tests/contrast.mjs`, `a11y.mjs`, `themes-all.mjs`) must pass
  after every visual change.
- Reduced motion collapses every new animation (desktop tokens
  `theme.css:402-407`; phone `JarvisTheme.kt:202`).
- The face's frame budget (`face/FaceBudget.kt`) stays in charge on the phone.
- Approval cards stay plain and unmissable, never decorated, never animated in
  a way that could hide or delay them. Nothing auto-approves.
- App lock and the screenshot block (`MainActivity.kt:621-628`) apply to any
  new surface: widgets, Live Update chips, the HUD.
- Fonts must be bundled, not fetched at runtime - the desktop already removed
  a Google Fonts call because it leaked the owner's IP address
  (`jarvis-desktop/src/fonts/fonts.css`, header comment).
