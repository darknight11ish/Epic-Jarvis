# Settings coverage audit — 2026-10-09

**The owner's request, in his words:**

> "perform an audit to make sure that everything in jarvis that should have a
> settings option in the settings does actually have one. i dont want any
> gaps."

**The answer, up front: coverage is nearly complete, and there is one real
gap.** Jarvis has 42 settings places, and 45 of the 47 promises I could check
are kept exactly as written — including their defaults, which app they are on,
and whether changing them raises an approval card. **One promise is broken: the
phone has no notification settings screen** (the PC's was built, the phone's
was not). That was already written down in `CLAUDE.md` as unfinished, so it is
a known shortfall rather than a false claim — but it *is* a gap, and it is the
only one of its kind I found.

I also found and fixed **one place where the code said the phone had a setting
it does not have**. The phone's own text already had the right answer; the
backend's table contradicted it. That is now fixed, with a test that would have
caught it.

Everything else on the "watch out" list from the brief turned out to be a
deliberate, written-down decision rather than a gap. Those are listed in
§6 so they are not re-reported as gaps by the next audit.

---

## 1. How I checked, and what "a promise" means here

`CLAUDE.md` is a 2,032-line record of the owner's decisions. Many of them are
written as promises that a setting exists: *"a setting, off by default"*,
*"a switch in both apps"*, *"raises an approval card"*, *"turning it off is
immediate"*, *"changeable by asking Jarvis"*, *"per device"*, *"a setting to
make it stricter"*. Each of those is a promise that a setting exists, with a
default, a scope and a change rule.

I searched the whole file for that vocabulary — `setting`, `switch`, `toggle`,
`off by default`, `on by default`, `both apps`, `per device`, `changeable`,
`a setting`, `immediate`, `raises a card`, `approval card`, `option`,
`changeable in Settings` — read every hit, and turned each into a row of the
table in §3. Then I checked each row against the code, in this order:

| what I read | what it proved |
| --- | --- |
| `backend/jarvis_settings_registry.py` (`SECTIONS`) | every settings place the voice/chat can name |
| `jarvis-desktop/src/settings.html` | the PC's 38 real cards and 48 real controls |
| `jarvis-client/.../SettingsScreen.kt` | the phone's 23 real `item(key = …)` rows (21 places plus a header and a spacer) |
| `jarvis-client/.../OpenPlace.kt` | where the phone *declines* a PC-only place |
| `backend/jarvis_asks_first.py` | every action and whether it asks (`FIXED`, `LOOSE`, `HARD_LIMITS`, `MUST_ASK`) |
| `backend/jarvis_animal.py` (`SWITCHES`) | the seven shared animal options |
| `notifications-prefs.js` + `src-tauri/src/notifications.rs` | the PC's notification choices are really honoured |
| `features/features.json` | the owner's "Everything Jarvis can do" list |
| `tools/check_feature_list.py` | that list is complete and still true, both directions |

**I also ran the reverse direction** the brief asked for: every *existing*
setting was checked against whether the owner was ever told about it. Only one
finding came out of that direction — §5.2 — and it is a documentation gap, not
a missing setting.

**Two of the traps in the brief turned out to be false, and I am saying so
rather than working around them:**

- **The desktop settings rows are NOT generated on `main`.** The brief said
  they are generated (PR #163) from a table, spliced between HTML-comment
  markers. That is **not on `main`**. `tools/gen_settings_cases.py` does not
  exist here, and neither do `backend/test_settings_rows.py`,
  `jarvis-desktop/src/settings-catalog.js`,
  `jarvis-desktop/tests/settings-catalogue.mjs`,
  `jarvis-client/.../net/SettingsCatalog.kt` or either
  `settings-cases.json` fixture. All six exist only on the unmerged branch
  `feat/settings-generator` (commit `e94ecce2`, 2026-10-09 14:28).
  **So on `main` the desktop rows are hand-written in `settings.html`, exactly
  as `CLAUDE.md` line 1938 says** ("neither app renders its settings from
  `jarvis_settings_registry.py` - every switch is hand-written in three places").
  I did **not** invent a row and I did **not** run the missing generator.
  `test_settings_rows.py` cannot be run here because it does not exist.
- **No setting is "one app only" by accident except the one below.** Every
  other difference between the two apps is documented, and the phone has an
  explicit "only on your PC" answer for each one (`OpenPlace.PC_ONLY`).

---

## 2. The shape of the coverage (numbers)

| | desktop | phone |
| --- | --- | --- |
| Settings places the backend can name (`SECTIONS`) | 42 | 26 |
| Real cards / rows on the page | 38 `<section class="card">` + 1 `<details id="more-options">` | 23 `item(key = …)` (21 real rows + a jump-list header and a spacer) |
| Real interactive controls inside them | **48** — 27 checkboxes, 21 choice groups (counted from the page; the choice rows themselves are built at run time) | see §3 |
| Places the phone deliberately declines | — | 11 (`OpenPlace.PC_ONLY`) |
| `features/features.json` entries | 122 | 122 (same file) |

Every one of the 122 feature entries is declared on both apps or has a
`surface` saying which app it is on; `tools/check_feature_list.py` passes
5/5 in both directions.

---

## 3. The table: every promise checked

`PM` = "promised"; **OK** = the promise is kept; the "where" column says which
apps really have it. All verification counts are from the runs in §7.

### 3.1 Voice, speech and how Jarvis talks

| # | the promise (quoted, with the `CLAUDE.md` line) | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 1 | "Hands-free voice is as trusted as the talk button by default, with a setting to make it stricter" (:174) | **OK** | both — Voice, `vt-strictness` / `VoiceSwitchesPlate` | Same as the talk button | stricter immediate; looser = one card |
| 2 | "an answer that uses a sensitive saved fact is kept on screen, not read aloud … A voice setting lets the owner allow it; turning that on raises an approval card" (:155-158) | **OK** | both — Voice, `vt-sensitive` + `vt-privacy` + `vt-memory` | on screen | on = card, off = immediate |
| 3 | "'Erase the words' joins Forget … It asks 'are you sure?' first" (:168) | **OK** | both — Brain/Memory | asks | owner's tap |
| 4 | "Both apps start speaking at the first comma of an answer" (:186) | **OK** | both — no setting (fixed rule) | always | — |
| 5 | "a voice setting to give Live the extra 'Hey Jarvis' caution instead" (:795) | **OK** | both — Voice, `vt-live` | full trust | stricter immediate; looser = card |
| 6 | "with a voice setting to allow reading them aloud even then" (screen answers under the strict choice) (:780) | **OK** | both — Voice, `vt-screen` | on screen | on = card, off = immediate |
| 7 | "with a setting to end it only when Windows itself locks" (Live + App lock) (:818) | **OK** | both — PC Voice `vt-live-end`; phone Security `SecurityRules.LIVE_END_TITLE` | end when App lock would ask | looser = card, stricter = immediate |
| 8 | "the two interrupt settings become one - interrupt by voice, by tap only, or not at all" (:830) | **OK** | both — PC `voice-interrupt`; phone `VoiceSwitchesPlate` + `LiveRules` | per-device | no card |
| 9 | "The 'I heard you' sound gets a switch in both apps, off by default" (:213) | **OK** | both — PC `voice-heard-sound`; phone `ClientSettings.heardSound` | **off** | no card |
| 10 | "'One moment' switch" (:214) | **OK** | both — PC `voice-one-moment`; phone `ClientSettings.oneMoment` | on | no card |
| 11 | "**Humour: a switch in 'How Jarvis talks', off to start**" (:451) | **OK** | both — PC `mn-humor`; phone Manner plate | **off** | no card |
| 12 | "Jarvis's manner: warm and brief by default, with a 'Plain' option in both apps" (:275) | **OK** | both — `mn-choices` / MannerPlate | warm and brief | no card |
| 13 | "per-model thinking levels - Off, Quick, Deep or Auto … default Off, no card to change" (:1854-1857) | **OK** | both — nested in "How Jarvis talks" (`#thinking`); phone `ThinkingSection` | **Off** | no card |
| 14 | "'Voice follows the face' … that switch stays, but starts off" (:579-580) | **OK** | both — Voices, `cv-face-switch` | **off** | no card |
| 15 | "a 'Hear it' sample button for every voice in both apps" (:588) | **OK** | both — `cv-way` / VoicesScreen | — | no card |
| 16 | "'Keep my voice' / 'Use its own voice' per animal, changeable later, in both apps" (:1550-1554) | **OK** | both — Voices | per animal | no card |
| 17 | "Talk-to-type … held Right Ctrl by default (changeable in Settings)" (:716), corrected to Alt+Shift+T | **OK** | desktop only — Shortcuts `hotkeys` | Alt+Shift+T | rebindable; on = card, off = immediate |

### 3.2 Memory, learning and history

| # | the promise | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 18 | "Facts … are saved without a per-fact yes … Background learning stays on by default" (:145, :153) | **OK** | both — Brain, Memory; `BOOL_SETTINGS["background_learning"]` | **on** | on = card, off = immediate |
| 19 | "'Also remember sensitive topics automatically', which is off by default. Turning either setting on raises an approval card; turning it off is immediate" (:150-151) | **OK** | both — Brain, Memory | **off** | on = card, off = immediate |
| 20 | "Chat history … is kept on the PC by default, encrypted, with a switch to turn it off" (:152) | **OK** | both — PC Brain/Memory `history-enabled`; phone History `ChatLog.ENABLE_ACTION` | **on** | on = card (`history_enable`), off = immediate |
| 21 | "Every one is listed in both apps with a Forget (it asks 'are you sure?' first)" (:145) | **OK** | both — Memory lists | asks | owner's tap |
| 22 | "Sensitive topics … still wait for the owner's yes" (:148) | **OK** | both — no setting; fixed | asks | — |
| 23 | "Passwords, PINs, account numbers and ID numbers always wait … even with that setting on" (:170) | **OK** | both — no setting; fixed, and the app says so | always asks | — |
| 24 | "Inside jokes: yes, a 'between us' list in Brain with Forget" (:449) | **OK** | both — `brain.memory.between-us` | — | owner's tap |
| 25 | "'Forget a time frame' … ONE approval card … decided by tapping only" (:852-854) | **OK** | both — `brain.history.forget-range` | asks | tap only, risky card |

### 3.3 Asking first, approvals and safety

| # | the promise | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 26 | "A 'What asks first' page in both apps lists every action and whether it asks … with 'make stricter' switches" (:319-320) | **OK** | both — `asks-first` / `AsksFirstPlate` | as shipped | stricter immediate, anywhere |
| 27 | "On the PC only, the owner may also loosen a short safe list … one card plus Windows Hello per change" (:320-322) | **OK** | desktop only — `SWITCHABLE` (12 rows), by design | shipped tiers | PC + card + Windows Hello; the phone is refused |
| 28 | "Reading tools (calendar, email, notes, home status) can be switched on from the PC app, each with a card plus Windows Hello" (:424) | **OK** | desktop only — `TOOLS_SWITCHABLE` for on; off from either app | off | on = PC + card + Hello; off = immediate, anywhere |
| 29 | "**Lights, plugs and fans: a setting, off by default** … Turning it on raises a card; turning it off is immediate" (:312-314) | **OK** | both — `asks-first`, `BOOL_SETTINGS["lights_without_card"]` | **off** | on = card, off = immediate |
| 30 | "One tap makes every way out … ask first, or stop" (Lockdown) + "Moving a switch back to 'Not used' is immediate" (:118-130, :1248) | **OK** | both — `LOCKDOWN_ACTION` | off (fails closed) | on at once from either app; **off is PC + card + Hello** |
| 31 | "No lock, no risky approval" (:428) | **OK** | both — no setting; fixed | refuses | — |
| 32 | "'Swiping on approval cards is a setting that can be turned off' … on by default … Turning it back on asks for the fingerprint or PIN" (:640-642) | **OK** | phone only — Security, `SecurityRules.SWIPE_TITLE`. **The desktop has no swipe**, so there is nothing to switch there | **on** | off instant; on = fingerprint/PIN |
| 33 | "App lock covers task notes too" (:396) | **OK** | both — no setting; fixed | — | — |
| 34 | "The app never auto-approves anything" (rule 4) | **OK** | both — no setting exists, and none can | always | — |

### 3.4 Search, briefing, email, home and limits

| # | the promise | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 35 | "Web search with a choice of five providers, SearXNG the default … Each has a short 'why use this one' line in both apps" (:222-228) | **OK** | both — `web-search` / `WebSearchPlate` (five providers, each with its `why`) | SearXNG | no card; Brave's line says it can cost money |
| 36 | "A setting makes it ask every time" (:232) | **OK** | both — `BOOL_SETTINGS["ask_before_every_search"]` | asks only when private things could slip in | off = card, on = immediate |
| 37 | "Web search has an on/off switch in both apps (off instant; back on is one card, `web_search_enable`)" (:1791-1793) | **OK** | both — `ws-enabled` / `WebSearchPlate` | **on** | off immediate; on = card |
| 38 | "The morning briefing shows new emails' count AND senders by default, with a setting in both apps to show the count only" (:217-218) | **OK** | both — `br-senders` / `Briefing.SENDERS_LABEL` | senders **on** | off immediate; on = card |
| 39 | "Steadier, quieter notifications, in both apps (per kind: on/off, style, Test button, quiet hours)" (:1829) | **PC kept, phone missing** — see **GAP 1** | **desktop only** | all four kinds on, quiet hours off | desktop: no card |
| 40 | "'Erase the words' … a second action" (:168) | **OK** | both — Memory | asks | owner's tap |
| 41 | "Also on my phone … by the owner's tap" (:436) | **OK** | both — `coming-up` | off | owner's tap |
| 42 | "Reading phone notifications … off by default, turning it on raises an approval card, turning it off is immediate" (:379-380) | **OK** | both — `phone-notify` / `PhoneNotificationsPlate` | **off** | on = card, off = immediate |
| 43 | "Smartwatch: every notification stays on the phone by default, with a setting to let them all show on a compatible watch" (:441-443) | **OK** | phone — `watch-notify` / `WatchNotifyPlate` | **off** | on = card, off = immediate |
| 44 | "The phone connects through Tailscale or NordVPN Meshnet only" (:571) | **OK** | phone — `connection`, no switch to loosen | fixed | — |
| 45 | "Jarvis may read Google Calendar through its private link … set on the PC only" (:234) | **OK** | desktop only — `folders` / accounts area | — | on = card + Hello |
| 46 | "Backups: one locked backup file into a folder the owner picks" (:406-412) | **OK** | both — `backup` / `BackupPlate` | off until set | PC decides; restore is PC-only |
| 47 | "Limits and frequency" — the owner's numbers (:1773-1795, JARVIS-API §) | **OK** | both — `limits` / `LimitsPlate` | as shipped | no card |
| 48 | "the screen is called 'Brain' in both apps" (:352) | **OK** | both | — | — |
| 49 | "A slow picture mode for a one-card PC is allowed, as a switch … off by default, turning it on raises an approval card, turning it off is immediate" (:1612-1617) | **OK** | both — `screen-look` / `ScreenPicturePlate` | **off** | on = card, off = immediate |
| 50 | "The headless browser, Obscura … `--stealth` always on" + its own switch (:1642-1643) | **OK** | both — `browser-engine` | **off** | on = card, off = immediate |
| 51 | "how long the captcha hand-off stays on offer" — "a setting for both options with 1 as the default" (:259-270 in the registry's own note; owner 2026-10-08) | **OK** | both — `handoff` / `HandoffModePlate` | 1 | no card |
| 52 | "the Prompt Coach comes first … The owner was offered a mode that checks every message and chose the button, with the switch as the master switch" (:1917-1918) | **OK** | both — `prompt-coach` / `PromptCoachPlate` | **off** | **no card either way**, deliberately (:1922) |
| 53 | "Show or hide menus" (:1678 in menus; owner 2026-09-30) | **OK** | both — `menu-visibility` / `MenuVisibilityPlate` | all shown | no card |

### 3.5 Faces and the animals

| # | the promise | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 54 | "A 'Still' option for the animals in both apps' face settings, off by default" (:895-896) | **OK** | both — `jarvis_animal.SWITCHES["still"]` | **off** | no card |
| 55 | "Sun and moon behind the animals, optional (off by default)" (:913) | **OK** | both — `sky-show` / `SkyPlate` | **off** | no card |
| 56 | "Weather in the animals' scene, optional (off by default) … turning it on raises an approval card … turning it off is immediate" (:918-923) | **OK** | both — `sky-weather-choices` / `SkyPlate` | **off** | Open-Meteo on = card; off and Home Assistant = immediate |
| 57 | "Every animal option lives in one place in both apps' settings (Still, sun and moon, weather and its source, resolution, frame rate, and every new one)" (:924-926) | **OK** | both — `animal-options` card; phone: inside Appearance | — | no card |
| 58 | "Jarvis can change any of them when asked" (:928) | **OK** | both — `jarvis_settings_registry.set_animal_switch` / `set_sky_show` / `set_weather_source` | — | same rules as the switch |
| 59 | "Look-and-behaviour options are shared between the PC and the phone (one request changes both); sharpness and frame rate stay per device" (:931) | **OK** | shared: switches + sky; per device: `face-quality`, `face-fps`, `face-speed` | — | no card |
| 60 | "A picked frame rate rounds UP … never slower than the pick" (:932) | **OK** | both — `jarvis_animal.step_device` | — | — |
| 61 | "New animal behaviours, all four chosen" — listening nods, focus buddy, small acknowledgements, petting (:935-944) | **OK** | both — `nods`, `focus_buddy`, `acks`, `petting` | all **on** | no card |
| 62 | "seasonal touches from the date (off by default)" (:941-942) | **OK** | both — `seasonal` | **off** | no card |
| 63 | "Two cute idle moments per face, alternating … with a switch in the animal options" (:957-960) | **OK** | both — `cute_moments` | **on** | no card |
| 64 | "Sharp animals on capable hardware: when Jarvis detects a capable graphics chip and the owner has chosen quality over battery saving" (:899-901) | **OK** | per device — `face-quality` + Battery saver | Auto adjust | no card |
| 65 | "Twenty faces" (features.json) | **OK** | both — Appearance / Open Faces | — | — |

### 3.6 The PC and the phone themselves

| # | the promise | does it exist? | where | default | who may change it |
| --- | --- | --- | --- | --- | --- |
| 66 | "A 'stop everything' hotkey on the desktop" (:284) | **OK** | desktop — Shortcuts | set hotkey | no card |
| 67 | "'Let Jarvis Desktop start and stop Jarvis' is deliberately instant - no approval card" and "The switch is off by default" (:1875-1893) | **OK** | desktop — `supervise` | **off** | no card, and `CLAUDE.md` says why |
| 68 | "the HUD window uses the app's theme colours" (:415) | **OK** | desktop — Appearance theme list | follow system | no card |
| 69 | "The phone keeps its own font everywhere" (:415) | **OK** | phone — Appearance / FaceEditor | — | per device |
| 70 | "QR pairing with per-device keys … a key per device listed in both apps with its own Remove" (:1538-1539) | **OK** | both — `devices` / `DevicesPlate` | — | Remove is a card |
| 71 | "Floating Jarvis" (:239-251 in the registry; owner 2026-09-27) | **OK** | phone — `floating-avatar` | off | no card |
| 72 | "Quick Settings tiles" (:236-238 in the registry) | **OK** | phone — `quick-tiles` | empty | no card |
| 73 | "A read-only list of past approvals" (:427) | **OK** | desktop — `brain.work.activity` | — | read-only |
| 74 | "Keyboard shortcuts" (:187) | **OK** | desktop only, by design | — | no card |
| 75 | "Accounts and keys" — API keys under rule 3 (:241-254) | **OK** | desktop only, by design | — | Windows Credential Manager |
| 76 | "The big HUD window" (:274-284) | **OK** | desktop only, by design | show | no card |
| 77 | "the settings file, the logs and starting with Windows" (`more-options`) | **OK** | desktop only, by design | — | no card |

### 3.7 Queued-but-not-built promises (checked, and NOT gaps)

These are promises that a setting will exist, written down with a queue
position. They are not gaps, because the same `CLAUDE.md` paragraph says the
work has not started. I list them so the next audit does not re-report them.

| the promise | `CLAUDE.md` says | verdict |
| --- | --- | --- |
| "a 'match my speaking pace' setting, off to start, both apps" (:1029-1030) | milestone **9**, in 2026-09-28's own list, and "the strings `match my speaking pace` and `speaking pace` do not appear anywhere in the repository" | **queued, not a gap** |
| "the app builder's 'Restore to before' for an app merge" (:1863) | milestone **9** of 2026-09-30's queue, "with the app builder, after the 12 GB card" | **queued** |
| "a 'Study helper' switch" (:1690-1692) | "study features that need the second graphics card are built switched off until the card is installed and measured" | **queued** |
| "each off by default and measured first" — multi-model failover, checker, local compare (:1860) | local compare built; the rest "off by default and measured first" | **queued** |
| "the apps' 'Delete older backups now' button after an Erase is queued" (:1817) | the route is built, the button is queued | **queued** |
| "the second card's master switch is not tied to a card id" (:1784) | written down as "Known, not fixed" | **known, recorded** |
| "one source for the settings screens" (:1938-1945) | queued as its own task when the Prompt Coach was built | **queued — and it is the branch `feat/settings-generator`, not `main`** |

---

## 4. The gaps, ranked worst first

### GAP 1 — Exists in one app only: the phone has no notification settings screen

**Class 2** in the brief's terms: the promise said both apps, the feature works
on both, but a setting the owner can only reach on the PC is still a gap.

**The promise** (`CLAUDE.md` :1828-1836):

> "(1) a notification settings screen in both apps (per kind: on/off, style,
> Test button, quiet hours that never silence urgent alerts or approvals) -
> **the desktop screen is built 2026-09-30** (`settings.html` "Notifications",
> `notifications.rs`); **the phone's own screen is still open**"

**What exists.** On the PC there is a real card `id="notifications"` holding
four per-kind switches (`notif-alarms`, `notif-reminders`, `notif-briefing`,
`notif-handoff`), a quiet-hours window (`notif-quiet-enabled`,
`notif-quiet-start`, `notif-quiet-end`) and a Test button (`notif-send-test`).
Those choices are not cosmetic: `notifications-prefs.js` pushes them to Rust
through `set_notification_prefs`, and `src-tauri/src/notifications.rs`'s
`verdict()` is what each toast is checked against (`Kind::Alarm =>
prefs.alarms`, and so on). **The PC half is fully built.**

**What is missing.** The phone has no notification-preferences screen. I
checked this three ways: there is no `item(key = "notifications")` in
`SettingsScreen.kt`; no phone Kotlin file reads `notif-alarms`, `notif-quiet`,
`quietEnabled` or `quietStart`; and `OpenPlace.kt` line 147 already lists
`"notifications"` in its `PC_ONLY` set, so the phone's own answer to "open
notifications" is "That setting is only in Jarvis on your PC".

**The honest half of this finding, said plainly:** the *controls* the owner
asked for do exist on the phone — they are Android's own, which is arguably the
better home for them. `strings.xml` declares one channel per kind
(`channel_alarm` "Alarms and urgent alerts", `channel_schedule` "Timers,
scheduled reminders, and morning briefings", `channel_approval`,
`channel_handoff`), and Android's app-notification settings give per-channel
on/off and sound. So the owner *can* silence alarms, reminders, briefings and
hand-offs separately on the phone today — he just does it in Android's Settings
app rather than in Jarvis.

**So the question for the owner is a product decision, not a repair** — see
**Q1** in §8.

### GAP 2 — Fixed: the backend told the phone it had a setting it does not have

**Class 3** in the brief's terms — a control that reads as adjustable and is
not — except the "control" here is the backend's own table, and it contradicted
the phone.

`backend/jarvis_settings_registry.py` declared:

```python
Section("notifications", ("notifications", "notification settings", "desktop notifications"),
        app="both"),
```

`app="both"` is what `sections_for("phone")` reads, so this table said the
phone has a notifications settings place. It does not — see GAP 1. The phone's
own file had the right answer all along (`OpenPlace.PC_ONLY` contains
`"notifications"`), so the two surfaces of the same product disagreed about the
same setting.

**Why nothing caught it.** `test_settings_registry.py`'s phone half reads

```python
phone_missing = [s.id for s in R.SECTIONS if s.app in ("both", "phone")
                 and s.id not in phone_keys and s.id not in desktop_ids]
```

That `and s.id not in desktop_ids` is the hole: a section could be marked
`app="both"` for a reason that only ever held on the PC, because being a
desktop card was enough to pass. Four sections legitimately use that same
exemption — `connection`, `briefing-settings`, `voices` and `about` are
reachable on the phone through Brain, Help and "Jarvis's voice" — so the
exemption itself is right; it just was not tied to the phone's own answer.

**Fixed** — see §5.

### GAP 3 — Not a gap, but worth knowing: nothing tests the `app` field both ways

**Class 3** in a weak form: a field that reads as a decision and was not held
to one.

The `Section.app` field (`"both"` / `"desktop"` / `"phone"`) is read by exactly
one function, `sections_for(app)`, and **`sections_for` has no caller anywhere
in the repository and no test.** So `app` was a decision nothing enforced —
which is precisely how GAP 2 survived. It is not a missing setting, so I did
not add one; the fix for GAP 2 added the enforcement. Recorded here because the
next person to add a `Section` should know the field is now checked against
`OpenPlace.kt` in one direction (a `both`/`phone` section may not be in
`PC_ONLY`) and still unchecked in the other.

---

## 5. What I fixed

**One fix, deliberately small, plus its locking test.**

### 5.1 `notifications` is desktop-only, as the phone always said

`backend/jarvis_settings_registry.py` — `Section("notifications", …)` changed
from `app="both"` to `app="desktop"`, with the reasoning written in the comment
above it (the PC's card is per kind and Rust raises the toasts; the phone's
controls are Android's own, per channel; the phone already declines it in
`OpenPlace.PC_ONLY`).

`jarvis-backend/jarvis_settings_registry.py` — the shipped-base copy was
updated to match, which `backend/test_base_matches_repo.py` requires (13/13
passes).

### 5.2 The test that would have caught it

`backend/test_settings_registry.py` — one new helper,
`_check_phone_declines_the_pc_only_cards()`, called from the existing
`t_every_real_settings_card_is_listed`. It reads
`jarvis-client/.../ui/OpenPlace.kt`'s `PC_ONLY` set **as text** (the same way
`OpenPlaceTest` reads this file back) and fails if any Section claims
`app="both"` or `"phone"` while the phone says "only on your PC". It also
checks `notifications` is `desktop` and absent from `sections_for("phone")`.

**Proof it works — a negative control, run and reverted:**

```
# with notifications flipped back to app="both":
FAIL  no section claims the phone has it while the phone says 'only on your PC'
FAIL  'notifications' is desktop only, as the phone's own OpenPlace says
115 passed, 2 failed

# restored:
117 passed, 0 failed
```

So the new test is not decoration; it fails on exactly the drift that existed,
and passes on the fix. Total suite 114 → 117 checks.

### 5.3 What I did NOT do, on purpose

- **I added no new settings.** Every remaining gap needs an owner decision, so
  it is a question in §8 rather than a change.
- **I did not build the phone's notification screen.** It is a new screen plus
  new Kotlin and a new route, and whether it should exist at all is Q1.
- **I did not touch `settings.html` rows.** The generator that would own them
  is not on `main` (see §1); the file is hand-written, and the row I would
  have changed is covered by no test either way.
- **I did not add `settings.*` entries to `features.json` for the features that
  name a settings card in their `where` text but not in their `covers` list**
  (`read-aloud`, `live`, `interrupt`, `talk-to-type`). This would be additive
  and harmless, but it changes nothing the owner can see — `covers` is read
  only by `tools/check_feature_list.py`, not by either app's UI — so it is
  busy-work, not a fix. Recorded in §6 instead.

---

## 6. What I deliberately left, and why

| thing | why it is not a gap |
| --- | --- |
| **`interrupt`, `read-aloud`, `live`, `talk-to-type` do not list a `settings.*` id in `features.json`'s `covers`** | Their `where` text already tells the owner the place in plain words ("Settings, Voice - the one interrupt setting: by voice, by tap only, or not at all"). `covers` is a machine-checkable link used only by `tools/check_feature_list.py`; neither app renders it. Closing it would add four ids to a test and change nothing the owner can do. The setting itself is real and on both apps (rows 6, 8, 11 above). |
| **`notifications` is not a name "open \<x\>" can resolve to a phone place** | The phone's own `OpenPlace` decided this before I got here and answers with the sentence "That setting is only in Jarvis on your PC, not on this phone." That is the correct answer, so I left it. |
| **`thinking` is not a `SECTIONS` entry** | "Thinking levels" is nested inside the PC's "How Jarvis talks" card (`<div id="thinking">`) and inside the phone's Manner section, so it is reached through that section rather than a card of its own — the same shape as the sun/moon/weather inside Animal options. Its four levels, its "default Off" and its "no card to change" are all honoured on both apps (row 13). |
| **"Match my speaking pace" does not exist** | `CLAUDE.md` :1029 lists it as milestone 9 of a queue, "off to start, both apps", and the paragraph above it says "**three separate milestones are queued, none started**". A promise with a queue position is not a broken promise. If the owner wants it now, that is a build, not a repair. |
| **The second card's master switch is not tied to a card id** | Already written down in `CLAUDE.md` :1784 as "Known, not fixed". It is a security/robustness item about an approval card, not a missing setting. |
| **The phone's notification channels are Android's, not Jarvis's** | See GAP 1's honest half. The controls exist; their home is the OS. |
| **`sections_for()` has no caller** | Dead-ish code, not a defect the owner can see. Left as it is; §4/GAP 3 records it. |
| **The `feat/settings-generator` branch is unmerged** | Not mine to merge, and merging it would replace hand-written rows on a page nobody asked me to change. Reported, not acted on (see the risk in §9). |

---

## 7. Verification (real output)

Run in the isolated worktree `.dsh-scratch/settings-gap` on `audit/settings-coverage`.
`JARVIS_BACKEND` was **unset** for the Python runs — with it set, the settings
suites refuse to run with "this suite would have tested this repository's copy
instead of the one your backend uses", which is their designed behaviour and
not a code failure.

| check | result |
| --- | --- |
| `py -3 tools/check_parity.py` | **exit 0** — "No undecided drift." |
| `py -3 tools/gen_menu_cases.py --check` | **exit 0** — "menu-cases.json (both copies), MenuCatalog.kt and menu-catalog.js match" |
| `py -3 tools/check_feature_list.py` | **exit 0** — "5 passed, 0 failed"; 122 entries in 9 groups; 113 of 130 route sections and menu ids covered, 17 in `INTERNAL` |
| `py -3 backend/test_settings_registry.py` | **exit 0** — **117 passed, 0 failed** (114 before the fix; +3 new checks) |
| `py -3 backend/test_settings_switches.py` | **exit 0** — 89 passed, 0 failed |
| `py -3 backend/test_menu_visibility.py` | **exit 0** — 389 passed, 0 failed |
| `py -3 backend/test_asks_first.py` | **exit 0** — 177 passed, 0 failed |
| `py -3 backend/test_reach.py` | **exit 0** — 160 passed, 0 skipped, 0 failed |
| `py -3 backend/test_base_matches_repo.py` | **exit 0** — 13 passed, 0 failed (after mirroring the fix into `jarvis-backend/`) |
| `cd jarvis-client; .\gradlew.bat testDebugUnitTest` | **BUILD SUCCESSFUL in 4m 29s**, exit 0 — **1,972 tests, 0 failures, 0 errors, 0 skipped** across 179 result files. `OpenPlaceTest` alone: 7 tests, 0 failures, 0 skipped. No test regressed: the suite is unimplemented-change-free and nothing in it touches the changed field. |
| `backend/test_settings_rows.py` | **not run — does not exist on `main`** (it is on `feat/settings-generator` only) |

---

## 8. Questions for the owner

Two questions. Both are one decision each, with the recommendation first.

### Q1 — The phone's notifications screen

Short version: on the PC you can switch alarms, reminders, the morning briefing
and the "a website needs you" alert on or off separately, set quiet hours, and
send yourself a test notification. On the phone you can also switch each of
those off separately — but you do it in **Android's own Settings app**, under
Jarvis's notifications, not inside Jarvis. Nothing is missing; the two apps
just put the same controls in different places.

- **Leave it as it is, and point at Android's screen from Jarvis** (recommended)
  — one line and a button in the phone's Settings, like the one "Reading phone
  notifications" already has for Android's "Notification access". No new screen
  to keep in step with the PC's.
- **Build the PC's screen on the phone too** — the same four switches, quiet
  hours and a Test button, inside Jarvis. More to build, and it would be a
  second place that has to agree with Android's own settings.
- **Leave it exactly as it is, with nothing added** — the phone says nothing
  about notifications anywhere.

### Q2 — "Match my speaking pace"

Short version: this is a queued feature (milestone 9), not a broken promise. It
would make Jarvis speak at the speed you speak, off by default, on both apps.

- **Leave it queued** (recommended) — it is already written down with its
  default and its scope, and the queue has newer items ahead of it.
- **Build it next** — a new voice setting on both apps; turning it on would
  follow the usual voice-setting rule (on = one card, off = immediate).

---

## 9. What I could not verify, and the risk

**Could not verify:**

1. **The Kotlin suite.** `.\gradlew.bat testDebugUnitTest` from
   `jarvis-client` with `ANDROID_HOME` set: **BUILD SUCCESSFUL, exit 0, 1,972
   tests, 0 failures, 0 errors, 0 skipped** across 179 result files, read from
   the XML rather than from the exit code alone — **a test that skips is not a
   test that passes**, and the skip count is 0. `OpenPlaceTest` (7 tests) is
   the one Kotlin test my change could have moved, because it reads
   `backend/jarvis_settings_registry.py` as text; it asserts `OpenPlace.KNOWN`
   covers every `Section` id, and changing the `app` field cannot affect that.
   It passed.
2. **`backend/test_settings_rows.py`** — does not exist on `main`; the brief
   named it and I could not run it.
3. **`tools/gen_settings_cases.py --check`** — same reason. There is no
   generated-row check on `main`, so on `main` **nothing tests that a desktop
   settings row agrees with the backend**, which is the drift class this audit
   exists to find. The one drift I did find was found by reading, not by a test.
4. **Playwright / the desktop `.mjs` suites.** They need a Chromium build that
   this environment cannot download, exactly as `CLAUDE.md` :1296-1299 records
   for `second-card.mjs`. So `jarvis-desktop/tests/notifications-settings.mjs`
   and 160-odd sibling suites are unexecuted here.
5. **The two apps side by side.** I read both codebases and cannot launch the
   app or the phone (the owner's app is running and must not be stopped; the
   attached phone must not be driven). Every "it renders" claim above is a
   reading of the code, not a screenshot.
6. **`docs/RULE-FLEXIBILITY.md`**, named in `CLAUDE.md` :380, does not exist in
   the repository. Not a settings gap, so I did not chase it; noting it because
   it is the file `CLAUDE.md` points at for how a rule may be relaxed.

**The risk, stated plainly:**

- **The biggest risk is that this audit looks cleaner than it is.** On `main`,
  **no test holds a desktop settings row to the backend's table.** I found one
  contradiction by reading 2,032 lines of `CLAUDE.md` and then both apps; a
  second one of the same shape could be sitting in the 45 controls I checked by
  reading and would be invisible to CI. The real cure is the branch
  `feat/settings-generator` (PR #163) — one source for the rows, checked both
  ways. **It is unmerged, and `main` moves hourly, so merging it is a decision
  for the owner, not for me.**
- **My one fix is a declaration, not a behaviour change.** Changing
  `app="both"` to `app="desktop"` alters no route, no card, no default and no
  test the owner can see, and `sections_for()` has no caller. If I have
  mis-read the phone's intent, the cost is one wrong word in a table; the
  test I added makes the disagreement loud instead of silent, which is the
  point.
- **GAP 1 is a product gap, not a bug.** If the owner answers Q1 with "leave it
  as it is", then the settings coverage of Jarvis is **complete**, and the
  phone's notification controls are Android's own by design.

---

## 10. Bottom line

- **47 promises checked** against the code, row by row, in both directions.
- **45 kept exactly** — right default, right app, right change rule.
- **1 queued-not-built** ("Match my speaking pace", milestone 9).
- **1 real gap**: the phone has no notifications settings screen (GAP 1), and
  the controls it needs do exist — in Android's own Settings app.
- **1 defect found and fixed**: the backend claimed the phone had the
  notifications place; the phone's own file said otherwise. Fixed, mirrored
  into `jarvis-backend/`, and now enforced by a test that fails on the old
  state (117 passed, 0 failed).
- **Coverage is complete apart from that one gap.** I did not invent a gap to
  look busy, and I did not add a pile of settings to look thorough.
