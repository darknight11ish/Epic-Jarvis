# Jarvis launch video v5: "A day with Jarvis"

Two cuts from one project:

- `jarvis-launch-v5.mp4`: 1920×1080, 34 s, for the README and GitHub.
- `jarvis-launch-v5-vertical.mp4`: 1080×1920, 16 s, for a phone held upright.

## The idea

One ordinary day, from 7:30 in the morning to 23:00 at night, in **one
continuous shot with no cuts**. The camera glides along a strip of the day.
A ribbon of hours runs across the top, and the reactor (Jarvis's face, from
the app's own code) rides it like a small sun. The sky behind changes with
the hour: dawn, day, dusk, night. The app's screens follow it too: its light
"paper" theme by day, its dark theme at night.

The only big line is the last one: **Your day. Your PC. Your rules.**

## Why it is fully different from v1 to v4

| | v1 to v4 | v5 |
|---|---|---|
| Structure | cuts between separate scenes | one unbroken camera move through a day |
| Look | dark, neon, HUD brackets, glitch (v2, v4), or dark and calm (v3) | light and warm: a sky gradient, paper cards, soft shadows |
| Type | machine capitals and mono readouts | a serif (Fraunces) for the hours and spoken lines, a plain sans (Inter) |
| Reactor | a hero in the middle of the frame | the playhead on the ribbon of hours, then the centre of the end card |
| Music | 120 BPM trailer electronica (v2, v4), calm plucks (v3) | a relaxed 96 BPM warm groove that changes with the time of day |
| Upright cut | the same scenes, restacked | the strip runs top to bottom, with the hours down the left |

## What it keeps from before

- Every claim is checked against the code (the table below).
- The real desktop screens, rendered from the app's own code, with made-up
  example data. Nothing shown is a result from the owner's own PC.
- Screens that belong to Windows or Android are drawn, with the exact words
  from the code.
- Every spoken line is on screen, labelled You or Jarvis.
- Only a few short lines of text at a time, big enough to read on a phone.
  The upright cut keeps words out of the top 200 px and the bottom 300 px.
- The score is remuxed after rendering, checked at −14 LUFS, and each file is
  kept well under 100 MB.

## Storyboard (landscape, 34 s)

| time | hour | on screen | words |
|---|---|---|---|
| 0–3.75 | dawn | The ribbon of hours, the reactor rising. | **A day with Jarvis.** An AI assistant that lives on your own PC. |
| 3.75–8.75 | 7:30 | The real Morning briefing card (paper theme), cropped to its rows. | You: "Brief me now." Made on your PC, without the AI model. Shows who emailed, not what they wrote. |
| 8.75–13.75 | 9:00 | The real Focus session card, on target, then "Ten minutes in", off target. | You: "Focus for 30 minutes." Jarvis: "YouTube can wait." Watches which app is in front, on your PC only. Keeps counts, never what it saw. |
| 13.75–18.75 | 15:00 | The real "Tell me when" approval card, then "When Alex writes", the phone rings. | You: "Tell me when an email from Alex arrives. Urgently." One yes sets it up. Your phone rings until you look. It never replies. |
| 18.75–23.75 | 19:30 | Dusk. The real "Saved automatically" card (dark theme), "a little later". | You: "I've started learning Spanish." It learns from your own words only. Every fact has Forget and Erase the words. |
| 23.75–28.75 | 23:00 | Night. The phone's Mind screen: one tap on Standby, and the reactor goes to sleep. | One tap: Standby frees the graphics card. The next answer takes about 5-15 seconds. |
| 28.75–34 | midnight | The reactor settles in the middle. | **Your day. Your PC. Your rules.** Made for a Windows PC with an 8 GB NVIDIA graphics card · Android phone app · No subscription |

Each bottom line stays on screen for about four seconds: an outside review of
the first render found the lines were up for only 1 to 3 seconds, so every
moment was given more time.

The upright cut (16 s) keeps dawn, 9:00 focus, 15:00 "Tell me when" and the
end card.

## Evidence for every claim

B = branch `claude/admiring-ritchie-5urg5h` at 8743728. "Today" means built
and tested in the code on that branch. **Nothing has run on the owner's PC
yet**, and the Windows-only parts (reading the front window) have never run
on Windows at all.

| claim on screen | status | evidence |
|---|---|---|
| An AI assistant that lives on your own PC | today | An 8B model in Ollama on the PC (B `docs/ARCHITECTURE.md` §7). |
| "Brief me now." — made on your PC without the AI model | today | Answered in code before the model (B `backend/jarvis_quick.py:1316-1318`); a test with every socket blocked still gets the briefing (`backend/test_briefing.py:1036-1040`). |
| The Morning briefing card | today | Brain › Work › `#briefing-card` (B `jarvis-desktop/src/brain.html:477-486`, rows from `brain.js:4058-4076`). Its text was produced by running `jarvis_briefing.build()` with made-up calendar and email, for Monday 28 September at 07:30. Calendar and email each have to be set up on the PC first (`jarvis_briefing.py:22-35, 316-321`). The screen is cropped to the briefing's rows. |
| Shows who emailed, not what they wrote | today | Only the From line is read (`jarvis_briefing.py:34-39, 464-527`). |
| "Focus for 30 minutes." | today | Answered without the model (B `backend/jarvis_quick.py:951-1000`). No focus code changed since v4 (b218ae1). |
| "YouTube can wait." and "Ten minutes in" | today | Template `"{name} can wait."` (`jarvis_focus.py:206`); youtube.com is spoken as "YouTube" (`:281`). One of four starting lines, picked at random (`:206-209`). The two cards are ten minutes apart ("24 minutes left", then "14 minutes left"), so the switch is labelled "Ten minutes in". The card switches to the real "off target" state, captured from `jarvis_focus.Engine` with YouTube in front. |
| Watches which app is in front, on your PC only | today (never run on Windows) | `jarvis_focus.py:443-569`. Nothing leaves the PC. |
| Keeps counts, never what it saw | today | The saved record holds numbers and true/false only (`jarvis_focus.py:589-633`). |
| "Tell me when an email from Alex arrives. Urgently." — one yes sets it up | today | B `backend/jarvis_tellme.py:424-478`: one approval card. "Tell me when" and "urgently" are recognised in `jarvis_quick.py`. The card is unchanged since v4 and still ends "Nothing runs until you decide." | The card was generated for Monday 28 September at 15:00. It is shown **cropped above its grey footer line**: that line comes from `asks-first.patch:97` (commit 0088dd5), written for the lighter approval rules, which the video leaves out; so the Deny and Approve buttons are not shown either.
| Your phone rings until you look — "When Alex writes" | today (drawn phone, unlocked) | Sound and vibration repeat until it is opened or swiped away, with a "Stop" button, on the "Alarms and urgent alerts" channel (B `jarvis-client/.../ScheduleNotifier.kt:93-99, 164-189`; the one Stop action at `:176`). Mail is checked every 5 minutes (`jarvis_tellme.py:132`, `EMAIL_MINUTES = 5`), so the phone rings up to 5 minutes after the email, and only while it is connected to the PC. A locked phone shows only "Jarvis: something you asked to be told about happened." |
| It never replies | today | The watch only notifies; the card says "It never replies, never acts, and never opens or reads out the email or anything else." (`jarvis_tellme.py:468-469`). |
| "I've started learning Spanish." — learned from your own words only | today | ON by default (B `backend/jarvis_auto_learn.py:198-205`). It learns only from what the owner typed, or said and passed the strictest voice check, and every word of the fact must be in the owner's own messages (`:22-65`). |
| "A little later" | today | Not instant: the learner starts 45 s after the last message, the model then writes the fact and checks it for sensitive topics, and passes are at least 5 minutes apart (`extraction-wiring.patch:57-62, 205-218`). The fact's wording is the model's; "You're learning Spanish." is an example. |
| The "Saved automatically" card, Forget and Erase the words | today | Brain › Memory › `#memory-auto-card` (B `brain.html:319-326`); Forget and "Erase the words" on every row, each asking first (`brain.js:2123, 2919, 2928`). |
| One tap: Standby (on the phone) | today | The phone's Mind › Doing plate has Active / Quiet / Standby buttons (B `jarvis-client/.../BrainScreen.kt:315-334`: title "Mind" and "State of mind" at `:242`, fields at `:317-318`, the current mode's button greyed out at `:321-329`). The Power field changes when the desktop reports the new mode. On the desktop, Standby is a tray menu item, not one tap (`tray.rs:180-201`), so the video shows the phone. |
| Standby frees the graphics card. The next answer takes about 5-15 seconds | today | The phone's own hint under those buttons: "Standby frees the graphics card; the next answer takes 5-15 seconds." (`BrainScreen.kt:332-334`). That is the app's own estimate, never timed on the owner's card, so the video says "about". The reactor's sleeping face is the app's own `standby` state, which it shows when power is standby (`jarvis-desktop/src/jarvis-link.js:457-465`). |
| The reactor | today | The app's own drawing code, `jarvis-desktop/src/faces.html`, extracted by `tools/extract-reactor.mjs`. Its states (idle, listening, speaking, approval, standby) follow the app's own state names. |
| Made for a Windows PC with an 8 GB NVIDIA graphics card | today | Sized for the owner's 8 GB RTX 2080 Super; the hardware check reads NVIDIA cards through `nvidia-smi` (B `jarvis-desktop/src-tauri/src/commands.rs:2555-2564`). Other cards are untested. |
| Android phone app · No subscription | today | B `README.md:4` ("an Android app to talk to it") and `:8` ("Free and non-commercial"). |

### Only in the share copy

| claim | status | evidence |
|---|---|---|
| Timers, reminders and lists answered without the AI model; "Added to your shopping list." | today | `jarvis_quick.py`, wired in before the model; the reply is "Added to your {title}." (`jarvis_quick.py:1722`), the same in warm and plain (`:2050-2056`); the desktop adds "Done - answered on this PC without the AI model." (`coming-up.js:78`). |
| Your email, files and memories are handled only by the AI on your PC | today | `docs/ARCHITECTURE.md` §4: the lanes out of the PC carry no email, file or memory content to an AI. Caveats: the opt-in cloud lane gets only the newest question, and switching or installing a model does not yet refuse a cloud model's name (`ARCHITECTURE.md:510-511`). |
| Your phone reaches it over your own private network, never a public tunnel | today | The desktop listens only on this PC or Tailscale/Meshnet addresses and refuses 0.0.0.0 (`commands.rs:690-765`, `validate_bind_address`), and there is no tunnel code anywhere (CLAUDE.md rule 2). The phone's being-built "own networks only" address check is not claimed. |

## Left out on purpose

- **The "server address on your own networks only" check and the lighter
  approval rules** (including the Standby schedule, which needs no card):
  still being built or a lighter rule. The Coming up card's note and the
  Standby schedule block are cropped out of every screen.
- **"Wakes when needed":** it overclaims. The mode stays Standby; the next
  answer loads the model first.
- **The shopping list** ("Added to your shopping list.", answered without the
  model): true, cut for time. It is in the share copy.
- **The new approval notice for scheduled jobs** (commit 0088dd5, the approval
  card's grey footer line): it belongs to the lighter approval rules, so the
  card is cropped above it.
- **`OLLAMA_NO_CLOUD=1`:** not built; not mentioned.

## Honest limits of the picture

- **The desktop screens are real.** They are the app's own HTML, CSS and
  JavaScript, rendered headless with made-up data ("Alex", "Sam"). Open Sans
  stands in for Windows' Segoe UI.
- **The phones are drawn**, because they are Android's own notification and
  the Android app (which cannot be rendered here). Every word on them comes
  from the code cited above.
- **The day is a story.** The hours on the ribbon are an example day; the
  briefing, the focus numbers, the email and the fact are examples. Nothing
  here was run on the owner's PC.
