# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **Three drawing fixes for the animal faces (2026-09-29, from the skeptical
  review).** (1) **The robot's eyes now show the colour of what Jarvis is
  doing.** They were coming out nearly white in every state (so listening
  and waiting on you looked the same pale pink); now listening is amber,
  waiting on you yellow, thinking violet, an error rose, idle cyan - the
  same colours the animals' orbs use. Both apps. The picture in
  `docs/critters/robot-states.png` was redrawn. (2) **Sharper animals on the
  PC:** the desktop draws each animal with 1.5 to 2 times more steps of its
  ray-marching than the phone can afford, which removes the dotted seam where
  the panda's tail crosses its cheek and the blue fringe round the monkey's
  head (wrongly drawn pixels against a very slow reference: panda 9,042 to
  289, monkey 3,481 to 46, owl 1,448 to 34, otter 2,822 to 4, robot 98 to 1).
  The phone's drawing is unchanged; the two now differ by a few edge pixels.
  Not measured here: how long a Windows graphics driver takes to build the
  longer shaders the first time a face opens - if a face is slow to appear,
  lower its number in `tools/gen_critters.py` (`DESKTOP_STEPS`). (3) **The
  owl's cream chest fades into the brown at the neck** instead of ending in a
  straight line. Needs the new desktop and phone builds; no backend change.

- **The animals move less when Jarvis is not being used, and never the
  same way twice (2026-09-29, both apps).** Three fixes from the skeptical
  review. (1) **Fewer small idle moves:** while you have not talked to
  Jarvis, typed, been given an answer or been asked something for five
  minutes, and your pointer (PC) or finger (phone) is not on the face, an
  animal does about one small thing (a tail flick, an ear turn, a stretch)
  in four - about 40 an hour instead of 155 to 190. Breathing and looking
  around are unchanged; the moves that remain are the same clips, only
  rarer, and they fade in and out over a couple of seconds when you come
  back. A face that has only just opened counts as used for its first five
  minutes; the Faces window always counts as used. (2) **Motion that does
  not repeat:** the five heads no longer sway together while talking (they
  were 86 to 91 percent alike; now about 5), breathing is uneven (each
  breath up to about 15 percent longer or shorter, never deeper than
  before), each small idle move differs a little in size (up to a quarter
  smaller) and length (0.8 to 1.25 times), and the owl's thinking head
  rolls half as far and turns to its orb now and then instead of all the
  time (it moved 87 percent of the time, now 19). Nothing moves faster or
  further than it did. (3) **Gestures land on the end of a sentence:** a
  nod used to peak about half a second after the sentence it marked, inside
  the next one. Both apps read each spoken clip before it plays, so they
  know where its sentences end and start the gesture early: it now peaks
  within a tenth of a second of the end, at every voice speed. A typed
  answer and the phone's own voice keep their old timing. Needs the new
  desktop and phone builds; no backend change.
- **A focus session shows the focus buddy, not a sleeping animal.** A focus
  session puts Jarvis on Quiet, and every screen drew Quiet as asleep, so the
  animal slept, woke to say "YouTube can wait" and dozed off again - the
  focus buddy never appeared. Now a Quiet that a focus session set shows the
  awake focus buddy on the PC's faces, the HUD, the tray icon and the phone;
  a Quiet you set by hand, and standby, stay asleep. The screen reader says
  Jarvis is working beside you and will not speak, except to name a
  distraction.

- **A still ring for errors, and a not-connected ring you can see.** On the
  four animals and the robot an error now also draws a thin, still ring with
  a gap at the bottom in the error colour, on both apps; it never moves, so
  it is fine under Still, calm motion and a serious moment. The
  "not connected" ring was so faint (1.65 : 1 against the background) that it
  looked like plain sleep from across a room; it is now a heavier, complete
  circle at about 4 : 1, and both rings stay readable on light and dark
  backgrounds. They differ by shape as well as colour (a gap or none, heavy
  or thin), so a colour-blind eye can tell them apart, and neither is the
  waiting-on-you clock.

- **The desktop tells a screen reader what the face shows, in the phone's
  words.** It used to say only "Jarvis isn't connected" (or a raw word like
  "banked"); the floating face, the widget and the face page now say the
  phone's eight sentences, plus not connected and a focus session.

- **The widget's sleeping Zs no longer get cut off.** In the widget's round
  120 px window the panda's and monkey's Zs poked out past the edge; they now
  stay inside it.

- **The docs pictures of the animals' eight states are redrawn.** The red
  panda's and pygmy owl's still showed a wave at "waiting on you" and a raised
  paw or wing at "error", removed on 2026-09-28. All five are redrawn from the
  current code and now show the error ring and the Zs.

- **A thumbs-down on a crisis-help answer no longer counts toward "suggest
  the bigger model".** Crisis messages were already never counted for the
  owner's own "that's wrong" words or for Jarvis struggling with a tool, but
  pressing the thumbs-down on the answer to a crisis message still added one
  to the "you corrected me" count. It no longer does. The backend keeps a
  short list of crisis-answer ids in memory only (ids, no words, nothing
  written to disk or to a log, gone when it restarts, oldest dropped after
  200), and the count skips any answer on it. Nothing else about the crisis
  help line changes. Needs `apply-patches.ps1` on the PC (`jarvis_agent.py`
  and `second-card-suggest.patch`).

- **The animals' new behaviours, on both apps.** Every animal and the robot
  now does what the six "Animal options" switches promised, each switch
  turning its own off: **listening nods** (a small nod in your pauses while
  you talk) and **gestures on Jarvis's sentence ends** (while it speaks
  aloud, its nods and paw lifts land where a sentence ends - a typed or
  quiet answer keeps the old timing); a **focus buddy** (in a focus session
  it works quietly beside you, and stretches when the session ends); a small
  **nod when a fact is saved** (never while App lock or "Hide memory lists
  and chat history" is on) and a **glow when a long answer is ready**;
  **petting** (on the PC stroke the Widget's face, or press, hold and stroke
  in the Faces window; on the phone a long press on the face, which does not
  open the Brain); **two cute idle moments** per face, taking turns after it
  has rested a while; a **goodbye and a hello** when you switch faces; and
  **seasonal touches** behind the face (off to start). "Keep the animal
  still" and serious moments switch every one off; calm motion makes them
  smaller - the focus buddy's pose included (it was drawn full size under
  calm; fixed). While Jarvis is waiting on you or something went wrong, a
  face switch is a quick gentle cross-fade, as in a serious moment (the
  animal used to bow and drop out of view). Also fixed in this batch:
  **the voice-speed fix** - the sentence-end finder missed almost every
  sentence end at the normal pace and faster (only 1 of 36 at the fastest),
  because sentences spoken back to back leave only about a tenth of a
  second of quiet; it now finds 25 to 34 of 36, and never one inside a
  sentence. **The options snap** - a face opened before the stored options
  were read eased in from the defaults, so a face set to Still moved for a
  moment; both apps now take them at once. On the PC the same now holds for
  a face switched back to after another, and for the seasonal touches. And
  on the PC, the sentence-end gestures
  now switch on when Jarvis's voice is first heard (they almost never did:
  the face turns to "speaking" as the text starts, before any sound), a
  face that has just opened waits its "rested a while" before a cute moment,
  and a stroke, a nod, a glow or a stretch is drawn at the full frame rate.
  Needs `apply-patches.ps1` on the PC for the new Petting wording
  (`jarvis_animal.py`). See `docs/CRITTERS.md`, "New behaviours".

- **A fifth face: the robot, on both apps.** From the owner's own picture:
  a small floating robot with a big white helmet, a glossy dark-blue visor
  with a glowing rim, ear pods with teal fins, an egg of a body with a teal
  shield, two mitten arms and no legs - it floats, with a soft shadow on
  the ground. No mouth and no orb: its glowing eyes carry the state's colour
  and its expression, and pulse with Jarvis's real voice. Now and then at
  rest it zips round inside its own picture (never out of it, never under
  "Keep the animal still", calm motion, a serious moment, a focus session or
  a petting hand), waves, or polishes its visor. It counts as an animal for
  every animal option and does everything the animals do - all eight
  states, powering down and booting up, the Zs, hello and goodbye, and the
  new behaviours. Its own voice under "Voice follows the face": Emma, two
  steps higher and a little faster (changeable in "Each animal's voice").
  The sky's switches now read "Show the sun and moon behind the face" and
  "Weather behind the face", so they fit the robot too. Pick it in the
  Faces window (PC) or Appearance (phone). Needs `apply-patches.ps1` on the
  PC for its voice and the new sky wording (`jarvis_voices.py`, `jarvis_sky.py`,
  `jarvis_reach.py`, `jarvis_quick.py`). See `docs/CRITTERS.md`, "Robot".

- **Animal options: every animal option in one place, on both apps, and
  Jarvis changes them when asked.** The desktop's Settings has a new
  "Animal options" card; the phone's Appearance has the same section. It
  holds "Keep the animal still", the sun, moon and weather (moved there),
  sharpness and frame rate (marked "on this computer" / "on this phone"),
  a button to the face's voice, and six switches for the new behaviours -
  listening nods, focus buddy, small acknowledgements, petting and cute
  idle moments (on to start) and seasonal touches (off). It covers every
  character face, the robot included. Those six are saved and shared, and
  the animals now do all six (see "The animals' new behaviours" above).
  **"Keep the animal still" and the
  switches are now shared**: kept on the PC, so a change on either device
  changes both (before, each device had its own Still - if either had it on,
  it stays on). Sharpness and frame rate stay per device. Say "keep the
  animal still", "stop the animal's nodding", "turn off the weather", "turn
  on the sun and moon" or "make the animal sharper" - answered at once,
  without the AI model; "make the animal sharper" changes only the device
  you asked from; switching the weather to Open-Meteo still shows its
  approval card first. Anything unclear gets a plain question back. Needs
  `apply-patches.ps1` on the PC (new: `jarvis_animal.py`, `animal.patch`).
  See `docs/JARVIS-API.md` section 60 and `docs/CRITTERS.md`, "Animal
  options".

- **Sharper animals, and more frame-rate choices, on both apps.** Quality
  now reads **Lower, Balanced, High, Maximum**, each with a one-line note on
  what it costs (your saved choice still works). At Maximum the PC draws an
  animal at 2x2 samples per pixel and the phone at its full resolution -
  the edges go from visibly stepped to smooth (measured on the panda: edge
  error 9.4 -> 3.2 out of 255 on the PC; on the phone High is now 0.75 of
  full resolution instead of half, 23 -> 13). With Auto adjust on, an
  animal starts at High and goes up to Maximum by itself only when its
  frames are very cheap; it steps down Maximum, then 60 fps, then Balanced,
  then 30 fps, then Lower. Battery saver on the phone still overrides it
  all. **Frame rate** adds 30 and 90. When the screen cannot match a pick
  exactly it rounds up, never down: on a 144 Hz screen 90 draws 144, and
  120 on a 165 Hz screen draws 165.
  An animal at rest is drawn 60 times a second when there is room (else
  30), and smoothly at full rate while it stretches or scratches; picking a
  rate lifts its rest to that. The PC's widget, HUD and floating face now
  rest too (they drew every frame). Both apps show "fps · ms per frame ·
  animal resolution" (the Faces window's full-size view; the phone's Face
  editor). A small face skips its soft shadow. See `docs/CRITTERS.md`,
  "Resolution and frame rate".

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
- **A monkey joins the animals**, on both apps - from the owner's own
  picture: warm brown fur, a big peach heart of a face, round ears, a tuft
  on top and a long curly tail. It hangs by one arm from a vine and swings
  gently, a little livelier than the other three; its banana is its orb and
  glows in your colour for each state. To sleep it climbs up and sits on the
  vine, tail curled round it. Its voice (with "Voice follows the face") is
  Michael, one step higher. See `docs/CRITTERS.md`.
- **The sun, the moon and the weather behind the animals**, on both apps,
  both off until you switch them on (Settings, Appearance, "Sun, moon and
  weather" on the PC; Appearance on the phone). Type your town once on the
  PC and the real sun rises, arcs over the animal and sets at the right
  times, and at night the moon shows in its real shape - worked out on your
  own devices, nothing sent anywhere. The weather adds soft rain, slow snow
  or wind, from your own Home Assistant or from Open-Meteo online (that one
  asks with an approval card first, because it sends your rough position).
  It stays dark and calm, dims when Jarvis sleeps, and holds still under
  reduced motion. See `docs/CRITTERS.md`, "The sky behind the animals".
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
