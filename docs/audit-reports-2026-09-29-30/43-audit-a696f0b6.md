# Report 43 (audit), agent a696f0b6, 2026-09-30T07:07Z

> **What it was asked** (first 600 characters of the task): Read-only ACCESSIBILITY audit of BOTH apps in /home/user/Epic-Jarvis (read CLAUDE.md first; beginner owner; verify each claim with file:line + quote; 'not checked' honestly; do not run Android/Windows; change no files). A light probe already found: desktop has prefers-reduced-motion and :focus-visible on approval buttons; phone has FaceView live region and minimumInteractiveComponentSize on some screens; only one contentDescription=null (PairingScreen.kt:176). It did NOT check: touch targets across all clickable, sp vs dp text, swipe-to-approve TalkBack semantics, colour contrast of tokens, fo

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

ACCESSIBILITY AUDIT (code read only; nothing was run, no files changed; `python3 tools/check_parity.py` says "No undecided drift"). Not device-tested: TalkBack, Switch Access, NVDA/Narrator and WebView2 behaviour are all unchecked.

Overall: both apps are far better than the light probe suggested. Most of what you listed is already handled and commented as audit fixes. The real gaps are few.

**THREE WORST**
1. Desktop focus rings on the approval buttons are faint and vanish in Windows High Contrast. The widget's Approve and Deny buttons (`widget.css:774` `.btn:focus-visible`) and the option buttons (`style.css:1670`, `widget.css:640`) set `outline: none` and draw only `box-shadow: 0 0 0 2px rgb(var(--accent-rgb) / 0.35)`. I computed that at 2.61:1 against the dark ground, under the 3:1 needed. `style.css:1861` (`.approval-button`) is weaker still: a 0.12 shadow (1.29:1), saved only by a border colour change. There is no `forced-colors` rule anywhere in `jarvis-desktop/src`, and Windows High Contrast drops box-shadow (from my knowledge of browser behaviour, not tested). A keyboard-only owner may not see which card button is focused. Confidence: contrast measured, High Contrast effect likely.
2. Phone Talk button needs a sustained press (`ui/parts/VoiceButton.kt:107-190`). It is hold, speak, lift, with slide-up to cancel, and the code notes it has no tap alternative on purpose. Its own comment says TalkBack passing the real hold through "has not been checked on a phone". Tap-to-talk (owner decision 2026-09-28) is not built: grep for tap-to-talk finds nothing. This blocks motor-impaired and Switch Access owners from voice. Typing, "Start Jarvis Live" (`LiveScreen.kt:231`) and the wake word are alternatives, so approving is not blocked.
3. Three phone checkboxes and one switch are not tied to their labels, so TalkBack says "checkbox, not checked" with no name. `GoalsPlate.kt:359` (step done), `HistoryScreen.kt:862` (facts to forget) and `MannerPlate.kt:135` (humour switch) put a bare Material control beside a Text. The other checkboxes are done right (`AutoLearnPlate.kt:375-382`, `ForgetRangePlate.kt:367-372` use `toggleable` plus `Role.Checkbox`). The History one sits in the forget-a-time-frame list, so a blind owner cannot tell which fact they are unticking. Confidence: high (source read).

**BROKEN**
- The three items above.
- Phone reduced-motion is read once: `JarvisTheme.kt:349-354` uses `remember(context)`, so turning "remove animations" on while the app is open has no effect until it restarts. It reads only `ANIMATOR_DURATION_SCALE == 0f`. Confidence: medium.

**CONFUSING**
- The desktop approval card is deliberately `role="group"` with no focus move (`index.html:548-573`), announced via the shared live region. This is well reasoned. Not checked: whether a screen reader actually announces it in the widget window (`widget.js:1034` says it does). The widget is `skipTaskbar` with `focus: false` (`tauri.conf.json:61`), so how a keyboard-only or screen-reader owner reaches it depends on the hotkey. I did not trace that.
- Desktop text is small in places: `--text-2xs` 10px, `--text-xs` 11px (`theme.css:234-235`), and the widget's Approve and Deny buttons use 11px (`widget.css:765`). Not checked whether 200% zoom reflows the 320px widget.
- The approval countdown is deliberately not announced (correct), but nothing warns that the card is about to expire. Timeouts are set by the server.

**CHECKED AND FINE (with proof)**
- Contrast (WCAG ratios computed from the hex values):
  - Phone Reactor theme, worst surface: body text 14.3, muted 6.9, faint 4.57, ok 10.8, warn 10.3, bad 7.2.
  - Phone Daylight theme, worst surface: body text 15.9, muted 6.4, faint 4.95, ok ink 10.4, marks 4.39 to 8.9 (the tightest, warn mark 4.39, is an icon at 3:1 or more).
  - Phone input/switch borders (`hairlineFocus`): 3.68 in Reactor and 3.03 in Daylight, both pass 3:1.
  - Desktop dark theme on the `surface-1` colour: text 17.3, muted 8.9, faint 6.6, ok 10.7, warn 12.4, bad 6.9, accent 13.6, standby state colour exactly 4.5. All pass.
  - Card hairlines are 1.2:1, decorative by design.
- Colour-only status: the phone's ON/OFF switch shows the word, the thumb side and the colour (`Parts.kt` toggle, `Role.Switch`). Approve is filled and Deny is outlined (`Parts.kt:415-420`). The face is a live region that speaks its state (`FaceView.kt:531-533`), with a still error ring and an offline ring.
- The phone approval card has live regions for "why you cannot act" (`ApprovalCard.kt:462, 480`). Swipe is optional, so Approve and Deny buttons always exist (`:548`), and a Security setting turns swipe off.
- The face-size drag has TalkBack actions (`HomeScreen.kt:1753-1769`).
- Touch targets: `heightIn(min = 48.dp)` on the shared controls, `Affirm` and `Quiet`.
- Text uses sp and follows font scale (`JarvisTheme.kt:416-421`). The one `contentDescription = null` (`PairingScreen.kt:176`) is a decorative logo, so it is correct.
- Haptics: Confirm, Reject and LongPress only, no flashing loops found.
- Desktop: landmarks and headings, `role="status"` regions, `prefers-reduced-motion` in 6 stylesheets, and `lang="en"`. `faces.html:179` is a real `aria-modal` dialog with a focus trap. No `<div onclick>` in any HTML file, and no input without an id or label in the settings and index pages I grepped.
- Not checked: the 35 JS-built `div`/`span` elements (only 5 `tabindex=0` or `role="button"` hits), keyboard use of the brain graph (`galaxy-view.js`), HUD/tray screen-reader reach, the plain-words rule beyond the strings I saw, and `tabindex` order.

**SMALLEST FIXES**
1. Focus ring: change the widget and approval `:focus-visible` rules to a solid `outline: 2px solid var(--focus-ring)` (`--focus-ring` is already defined as #7df3ff at `theme.css:60`), plus `@media (forced-colors: active)` using `outline: 2px solid Highlight`. About 6 lines of CSS.
2. Wrap the three phone label pairs in `Modifier.toggleable(role = ...)` with `onCheckedChange = null`, as in `ForgetRangePlate.kt:367`.
3. Build tap-to-talk (already decided).
4. Change `JarvisTheme.kt:349` to re-read the animator scale when the app resumes.

**OWNER DECISIONS**
1. Phone Talk button for motor and TalkBack users: (a) build tap-to-talk with a pause stop, as decided (recommended); (b) also add a "tap once to start, tap to stop" switch first, as a quick interim. It needs no extra graphics memory (works with one card or two).
2. Approval focus ring on the desktop: (a) solid bright outline, no fade (recommended); (b) keep the soft glow and add a border only in High Contrast.

**PHONE IDEAS (five rules checked)**
- Tap-to-talk in the Quick Settings tile, so one large target starts a Live session. Fine: it reuses Live, no new way out of the PC, no speech-to-text on the phone.
- A TalkBack custom action "Approve" and "Deny" on the card. The buttons already exist, so this only adds a shortcut. It must keep the risky-card fingerprint gate, never approve by voice, and never appear on the widget.
- Android Auto and watch: read-only status only. Never approvals (rule 4).
