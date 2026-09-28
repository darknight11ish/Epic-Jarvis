# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **A red panda face** - the first animal among Jarvis's faces, on the
  desktop and the phone. It sleeps when Jarvis is on standby, perks its ears
  and tilts its head when listening, gazes into a glowing orb when thinking,
  talks with Jarvis's voice, waves when an approval is waiting, and scratches
  its head at an error. The orb is your colour for each state. Drawn in 3D
  by the graphics card with no model file; see `docs/CRITTERS.md`.
- **A pygmy owl and a sea otter** join the panda, on both apps. The owl
  perches on a branch, turns its head to follow the room and waves a wing
  when something is waiting on you; the otter floats on its back in a
  little pool, taps a glowing pebble while it thinks and covers its eyes
  with its paws to sleep.
- **Animal faces tidied after their audit:** no more see-through specks
  along the otter's outline against its pool; the owl's thinking orb now
  circles clear of its head, and its glow no longer shows through the face;
  no starburst of streaks on the owl's crown seen from above; the panda's
  tail no longer shades itself with a false shadow band.
- **The animals' mouths follow Jarvis's real voice.** Each spoken answer is
  read up front into a mouth track - how open, how wide ("ee"), how round
  ("oo"), shut in pauses and on m/b/p - and played in step with the sound
  you actually hear, on the PC (every window that shows a face) and the
  phone. When Jarvis answers without speaking (typed, Quiet mode, kept on
  screen), the animals keep their mouths shut. See `docs/LIPSYNC.md`.
- **Voice follows the face.** With the red panda, owl or otter showing,
  Jarvis's built-in voice becomes that animal's - its own voice, pace and a
  slightly higher pitch. A switch in both apps, on to start, right under
  "Jarvis's built-in voice"; it never asks first. A voice you recorded still
  wins.
- **Choose each animal's voice.** Under "Voice follows the face", the red
  panda, owl and otter each get their own row: pick any of the eleven
  built-in voices, make it deeper or higher, and choose Slower, Normal or
  Faster. **Try it** plays a short line in that voice; **Reset to its own
  voice** puts it back. The mouths still move in step with whatever you
  pick. It never asks first. Needs the patch script run again on the PC.
  **Try it** never plays over Jarvis: it waits while Jarvis is talking or
  listening, stops the moment you start a question, and says the same
  words on the PC and the phone. On the PC it plays in the Settings window,
  so the faces in the other windows stay still while it plays.
- **The animals move their bodies, calmly.** Each looks at something (often
  you) and holds the look, its head following its eyes part of the way;
  blinks, small weight shifts, the panda's tail swish, and a small idle
  happening about every 20 seconds. While speaking they lean in and gesture
  now and then - never busy. Built on published MIT work (Spring-It-On,
  TalkingHead, airi, ChatVRM), credited in THIRD-PARTY-NOTICES.txt. See
  `docs/CRITTERS.md`, "How they move".
- **Rising "Zs" while an animal sleeps.** On standby - by the schedule or by
  hand - small z's float up from beside its head, two or three at a time,
  on both apps. Not when Jarvis simply cannot be reached: then it is the
  hollow ring alone. With reduced (calm) motion, one still z instead.
- **The animals wake up and nod off**, on both apps. Leaving standby, each
  plays a short, calm wake-up (about two seconds): the panda opens its eyes
  with a slow double blink, stretches and perks its ears; the owl opens one
  eye, then the other, and ruffles its feathers; the otter rubs its eyes
  and stretches in the water. Going to standby, each nods off (about three
  seconds) before the Zs rise. The mouth never moves (no yawn); waking into
  an approval or an error, and with calm, serious or "Keep the animal
  still" on, only the eyes open or close. See `docs/CRITTERS.md`.
- **"Keep the animal still"**, off to start: the animal only breathes and
  blinks - no looking around, gestures or idle happenings. On the PC in
  Settings -> Appearance -> "Face on this computer"; on the phone in
  Appearance -> More options, under Motion. Each device keeps its own
  choice. No card.
- **Serious moments stay calm and plain.** While a crisis answer is being
  given or spoken, every animal face (the PC's widget, floating face and
  HUD, and the phone's Home) drops the gestures and tilts and simply
  listens; waiting on an approval is an attentive, still look (no wave),
  and an error a still, concerned one.
- **"Jarvis isn't connected" looks the same everywhere.** Every face shows
  standby with the same thin hollow ring on both apps (the PC's ring was
  nearly invisible and breathed; it is now the phone's fixed colour). The
  tray icon now goes to standby's colour when the link drops, and never
  shows the approval colour while approvals are blocked.
- **The PC notices a graphics card that cannot keep up** with a face and
  draws a flat version instead, trying the card again after a minute; the
  Faces window's gallery works from the keyboard (Tab, the arrow keys,
  Enter).
- **Sharper animals**: fewer see-through or stray specks along their
  outlines, measured against a slow exact render (`docs/CRITTERS.md`,
  "Drawing quality").

## 0.2.0 - 26 September 2026

The first numbered version. It gathers the work of the last few days.

**New things Jarvis can do**

- **Timers, alarms, reminders and to-do lists**, set by saying or typing
  them, answered without the AI model so they work even when it is busy or
  asleep. Plain repeating reminders and alarms need no approval card.
  "What did I miss?" sums up what went off while you were away.
- **Morning briefing**: today's calendar, new emails (how many, and from
  whom - or only how many, if you prefer), and what is coming up.
- **"Tell me when ..."**: an email from a named sender, or a device at home
  changing (the washing machine finishing). One approval card to set it up;
  a match only notifies you - urgent ones keep ringing on the phone until
  you look.
- **"Folders Jarvis may look in"**: add a folder on the PC (one approval
  card) and ask about the files in it - find them by name, search your notes,
  read PDF, Word, Excel and PowerPoint files a part at a time. "Bring in a
  Notion export" unzips your Notion export into one of those folders. What
  Jarvis reads there is never saved as a fact about you.
- **Instant "tell me when" for email**, and **"tell me if Alex hasn't
  replied by Friday"**.
- **Sending email**: one approval card per email, showing the exact
  recipients, subject and whole text. Never an "always allow".
- **Web search** with five providers to choose from (SearXNG on your own PC
  by default, DuckDuckGo, Exa, Tavily, Brave).
- **Google Calendar**, read-only, through its private link, set on the PC.
- **Focus sessions** on the PC: a timer plus Quiet, a spoken nudge when a
  distraction comes to the front, and a report at the end. Nothing leaves
  the PC, and what was on screen is never stored.
- **Stop everything**: Alt+Shift+X on the desktop, or the button on the
  phone, halts whatever Jarvis is doing at once.
- **A live check of the whole setup** (`selftest.py --preflight`): every
  real connection tested end to end, "N pass, N fail, N warn".
- **"What asks first"**, a page in both apps listing every action and
  whether it asks you, with switches to make things stricter.
- **Lights, plugs and fans without a card** - a setting, off by default.
  Locks, doors, alarms and covers always ask.
- **Memory**: Jarvis learns facts from your own words automatically, lists
  each one with Forget and "Erase the words", and still asks about
  sensitive topics. Chat history is kept on the PC, encrypted, with a switch
  to turn it off. "Who is my sister?" now works.
- **Voice**: "Hey Jarvis" on the PC and the phone, spoken-style answers that
  start at the first comma, interrupting by saying "stop", and a switch for
  the "I heard you" sound (off by default).
- **Warm or plain manner**, a setting in both apps.

**Safer**

- Both apps accept a Jarvis address on your own networks only (this PC, the
  home network, Tailscale, NordVPN Meshnet). A public tunnel is refused.
- The PC itself asks Windows Hello before a risky approval from the PC, and
  a risky approval needs a screen lock on the phone or Windows Hello on the
  PC.
- Plain `http://` to Home Assistant or the calendar only inside your own
  networks.
- Writing notes after Jarvis has read outside text (an email, a web page)
  asks first.
- App lock hides the approval widget's details on the PC, and blocks
  screenshots on the phone.
- Reading email now checks the mail server's certificate, as sending
  always did (it encrypted, but to whoever answered).

**Fixed**

- "What did I miss?" no longer lists every routine "tell me when" look as
  something that went off.
- A "tell me when" whose end date passed while the PC was asleep (or while
  it was paused) now simply ends, instead of looking one more time.
- On the two days a year the clocks change, the briefing's calendar covers
  the whole day, midnight to midnight.
- The "tell me when" approval card no longer ends by saying it sends
  nothing anywhere, which contradicted its own "How" line.
- Many smaller fixes from the bug audits of 19, 24 and 26 September
  (`docs/BUG-AUDIT-2026-09-26-*.md`).

**Packaging**

- One version number (0.2.0) for the desktop app, the phone app and the
  backend. Both About boxes show it, the maker (darknight11ish), the licence
  and a way to read the third-party notices.
- Complete third-party notices for the desktop (`THIRD-PARTY-NOTICES.txt`,
  regenerated by `tools/gen_notices.py`) and a new list inside the phone app.
- Phone and desktop downloads are published only from `main` and the
  working branch; shorter, plainer release notes with a checksum.
