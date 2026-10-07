# What changed

Newest first. One version number covers the desktop app, the phone app and
the backend files (the `VERSION` file). Builds made by GitHub add a build
number as the last part - `0.2.57` is a build of 0.2.

## Not in a numbered version yet

- **The cloud lane asks the service for the service's own model now, not for
  its own lane name (2026-10-06).** The lane built the day before reached
  DeepSeek correctly - right address, right key, right limit - and then asked
  it for a model called `jarvis-escalate`, which no service has. The one line
  that resolves a lane had written the model it had just looked up onto the
  HUD's *parsed request* (`do_POST`'s own `body`) instead of onto the copy of
  the request that is actually sent, because inside that helper a bare `body`
  is the parsed request and the copy is a sibling function's local - so the
  escalation could never answer. The resolved model now goes on the very dict
  the request is built from: `_completions_url(lane, body)`, with `body` a
  parameter rather than a name read from around the function. That call is also
  the last line of `cloud-one-turn.patch`'s context, so that patch's copy of the
  line was re-anchored in the same change rather than left broken. No test here
  had caught it: lifting `_completions_url` out of the file to run it turns the
  enclosing name into a global, which is the wrong object by construction, so a
  new check runs the HUD's `_completions_url` and `_open` **where they really
  live** - pasted back inside a stand-in `do_POST` - and reads the JSON that
  would go out; a second, smaller check reads the same shape from the patch's
  own text, so it runs without the owner's file too.

- **The cloud escalation lane has a real transport now, and DeepSeek is behind it (2026-10-06).** "Try the cloud model" sent its one question to `JARVIS_URL`, the port of a program this setup never installed; a lane name such as `jarvis-escalate` now resolves to a real service and model through the same code the chatbot API keys use - DeepSeek's own pinned host over HTTPS, the key from Windows Credential Manager, the monthly money limit, and the answer-length cap - and a lane the limit cannot pay for is answered on this PC instead, so the offer can disappear rather than overspend. DeepSeek's address, current model names and worst-case (peak, cache-miss) prices were read from its own pricing page on 2026-10-06, so the limit stops early rather than late; the desktop's "LiteLLM" health light now reads the lane's real state, and "What Jarvis can reach" no longer reads lane names out of `litellm-proxy.yaml`. `docs/ACCOUNT-KEYS-DESIGN.md` section 5 says what to remove from the PC by hand.

- **Anything needing a key is settable in the app now (2026-10-06).** Settings
  has a new "Chatbot API keys" card for the six chatbot API services (OpenAI,
  DeepSeek, Mistral, xAI, OpenRouter, Groq): each key is typed on the PC and
  written straight into Windows Credential Manager from Rust, never over HTTP
  and never to the phone, exactly like the Accounts page's four secrets. The
  same card carries each service's monthly money limit and its price list,
  because a key with no limit leaves the service unusable: raising a limit is a
  loosening, so it gets one approval card and Windows Hello, while lowering one,
  removing one and correcting a price change at once with no card. Every default
  price says it is unverified and when it was written; every price says whether
  it is yours and the date you set it. `docs/ACCOUNT-KEYS-DESIGN.md` is the
  design.

- **The desktop tutorial no longer says the PC has one chat box
  (2026-10-06).** `backend/jarvis_tutorials.py` now teaches the big HUD
  window's own chat box and the **Open the Jarvis bar** button still beside it,
  and `jarvis-backend/` carries the same text.

- **Three comments that still described the HUD's box as opening the Jarvis bar now describe the reversal (2026-10-06).** `voice.rs`'s doc comment on `hud_open_bar`, the `hud-voice` set's comment in `permissions/surfaces.toml` and the matching line in `build.rs` all still said, in the present tense, that the PC has one chat box, so the HUD's own box opens it instead of chatting on its own - the rule the owner reversed when the box came back. They now say what the code does: the HUD's box is its own conversation, the button beside it opens the bar, and that window has no Temporary chat, no New conversation, no "Used in this answer" and no crisis panel. Comments only - no permission, command or behaviour changed.

- **Settings → Accounts now collects the server ADDRESSES, so email and Home Assistant work from the app itself (2026-10-06).** The card already held the four secrets (the IMAP username and password, the private calendar link, the Home Assistant token) in Windows Credential Manager - but no server address, so email answered "JARVIS_IMAP_HOST is not set - there is no mail server to read" and Home Assistant answered "not set up on this PC" unless the addresses were plain-text Windows environment variables. Eight addresses and one choice now have their own boxes (the mail server, its port and mailbox; the sending server, its port and how email is encrypted; the Home Assistant address; the calendar's CalDAV address); they are read from and written to the PC's own route and kept in `accounts.json` beside `web-search.json`, because an address is not a secret - it is a plain settings file, and the box shows what is saved. A key, password or token can never reach it: the route refuses every name but the eight. An environment variable you already set still wins, and the row says so.

- **The big HUD window has its own chat box again (2026-10-06).** This
  reverses the decision of 2026-09-28 that the desktop HUD's own box should
  open the Jarvis bar instead, "so the PC has one chat box". The box and its
  Send are shown and work exactly as the page always made them: type or press
  Enter, the answer streams in, and the window's own conversation is kept in
  History with its own id and the tag **HUD**. The **Open the Jarvis bar**
  button stays, now beside the box rather than instead of it, and the mic
  button is unchanged. What the box does not have - and the Jarvis bar does -
  is a **Temporary chat**, **New conversation**, the "Used in this answer"
  list and the crisis panel; those are now known limits of that window, not a
  reason to hide it. Only the packaged app was hiding it: the HUD page served
  on its own in a plain browser always showed its box, and still does. The
  suite's own check was inverted honestly rather than dropped - it now
  asserts the box and Send are *visible and working* (a message typed into
  them really reaches `/api/chat`), and still asserts the button exists and
  still asks the shell for `hud_open_bar`. Not yet typed in by hand on a real
  desktop run.

- **The phone's face photographs job was red because the runner had no sound
  library, not because anything here was broken (2026-10-06).** The job that
  renders the animal faces downloads Android's emulator and starts it. The
  download finished; the program would not start. The runner's own error said
  why: `libpulse.so.0: cannot open shared object file` - a sound library the
  emulator needs simply was not installed on the machine. So the job now
  installs `libpulse0` (the Ubuntu package that provides that one file) before
  it touches the emulator, and nothing else: the check that caught this - "the
  emulator exists but does not run" - is kept exactly as it was, and it still
  fails the step rather than reporting success. No test was weakened, no step
  removed, and the job still only renders; it cannot block a merge. Only a real
  run on GitHub can prove the emulator now starts.

- **Past approvals get their own screen on the phone.** The read-only list you
  asked for on 2026-09-27 was built and drawn inside the Inbox, and the
  approvals audit of 2026-09-30 found the one thing wrong with it: "It is only
  reachable via Inbox". The Inbox keeps its ACTIVITY row, which now opens a
  screen of its own (`jarvis-client/.../ui/screens/ApprovalsScreen.kt`) with
  the same fields the PC's Activity pane shows - what each card was, Approved /
  Denied / Timed out, when, and which device - and the same four filters.
  Nothing on it decides anything: no approve, deny, cancel, clear or re-open,
  no new permission, and no new way out of the PC. While "Hide memory lists and
  chat history" is on, the list hides behind the same Show as the phone's other
  history surfaces. With nothing decided yet it says "Nothing decided yet.",
  the PC's own words.

- **A full audit pass, recorded 2026-10-04 23:44 PDT (2026-10-05 06:44 UTC).**
  Twelve of fourteen read-only passes are complete and written up as five
  documents, indexed by `docs/AUDIT-PASS-2026-10-05.md`: a whole-project feature
  review, a comparison against Muse and ChatGPT "Dots" and the rest, a bug hunt
  across the backend, both clients and the Rust shell, a UI audit of both apps,
  and two deep audits (prompt injection end to end; dependencies and supply
  chain). Nothing in the product was changed - the pass only added documents.
  Two passes, disaster recovery and performance, were still running and are
  appended in a second commit. Headlines: the 12 GB card is installed and
  nothing is measured; fourteen of the worst defects are features or tests that
  silently do nothing (including **all spoken audio**, the "What Jarvis can see"
  privacy section, and 46 of 56 local UI suites); the live backend is exactly
  base + stack, with all 119 applied patches reverse-applying cleanly; and the
  rush latch that would catch "approve this now, before it expires" has no
  caller on Jarvis's own read path. The pass ends with eleven choice groups for
  the owner.
- **The "driven openly" rule is gone (2026-09-29, your decision).** You asked
  several times, after being told the risk each time, for stealth to be on for everything the
  new headless browser runs, so the old rule "nothing that hides that a
  program is driving, nothing that dodges a site's bot checks" no longer
  exists. The approval cards for chatbot websites no longer say "never hides
  that it is a program". What did not change: Jarvis never solves a captcha
  (it hands it to you, on the PC or with "Solve it here" on the phone), there
  is no proxy service, nothing private (email, files, passwords, memory) goes
  into a chat or a web page, every approval card still asks, and if someone
  asks Jarvis whether it is a bot it never says it is a person. The risk is
  real: a Gemini, ChatGPT or similar account could still be closed, and each
  card still says so; a spare account used only by Jarvis stays as advice. The
  browser window you see stays a plain, real browser (Jarvis adds no disguise
  to it) so you can take over at a captcha or sign-in. The new invisible
  browser (Obscura) with stealth is in the next entry. Where it is
  written: `CLAUDE.md` ("Stealth on for everything"), `docs/CHATBOT-DRIVER-DESIGN.md`.
- **A second browser with no window: the headless browser, Obscura (2026-09-29,
  both apps).** Jarvis's browser tool used to open only a browser window you
  can watch. It can now also choose **Obscura**, a small open-source browser with
  no window, for plain reading and quick lookups - per task: the visible window
  whenever you might need to sign in, pay or take over, the headless browser
  for simple reading (Settings, "Headless browser", picks which Jarvis prefers:
  Automatic, Always visible, or Headless). **Stealth is on for everything it
  runs** (your decision): it looks like an ordinary Chrome. That does **not**
  solve captchas, a site can still block or ban it, and signing in to a real
  account with any automated browser can get the account closed - so Jarvis
  never types a password with it and never solves a captcha, and at a captcha
  or a sign-in page it recognises it stops and tells you to ask again with the
  visible browser (a sign-in that starts with only a username or email box may
  not be recognised). **Off to
  start; turning it on is one approval card**; off is instant. Every page it
  opens and every click and box it fills is still listed on the same approval
  card as the visible browser's, and what it reads counts as outside text. It
  cannot reach your own network, uses no proxy, keeps no cookies, saves no files
  and opens no network port. You install it with **one PowerShell line** shown in
  Settings (Jarvis never downloads it itself): it downloads one named release,
  prints its checksums for you to compare and does not run it; a second command
  it prints checks it, and its checksum is then remembered and a different file
  is refused. It stops itself after 3 idle minutes, and the words it types and
  the addresses it opens are checked first. **A real Obscura has not been run yet** (nothing here
  could run a Windows program): `py -3 tools\check_obscura.py` is the real check.
  The chatbot driver and the support chats still use the visible browser, because
  they must hand a captcha to you in a window. Needs the new backend files
  (apply-patches.ps1 copies them) and the new desktop and phone builds.

- **Secrets in pictures you attach to a chat are covered with black too
  (2026-09-29, both apps).** Until now only "Look at this" and "Watch with me"
  had anything that looks like a key, password, card number, IBAN, crypto
  wallet, email or IP address painted solid black (never blurred) before a model
  looked. A picture you attach to a chat now gets the same, on the PC, before
  any model sees it - the second graphics card's picture model, the everyday
  model, or the words read for a model that cannot see. Nothing to hide: the
  picture goes on exactly as it was. A picture the PC cannot check (no text
  reader, a JPEG it cannot open) is NOT sent to any model, and the answer says
  so in words. The note beside the answer says how many places were covered
  (a number, never what they were). Both apps say, under the attachment:
  "Secrets in pictures you attach are covered with black boxes before Jarvis
  looks." Same limits as the screen: a password behind a show-password eye,
  tiny or stylised text and a QR code are not caught. "Photo to reminder" gets
  the same check on its words, so a proposed reminder never carries a key or a
  card number. Needs the new backend files (apply-patches.ps1 copies them) and
  the new desktop and phone builds. Not run on a real Windows PC yet.

- **Painted eyelids for the four animals (2026-09-29, both apps).** The red
  panda, pygmy owl, sea otter and monkey now have a lid of their own fur over
  the top of each eye, so the looks read at a glance: **waiting on you** a
  level, attentive lid; **something went wrong** a sloped, worried one;
  **dozing** a heavy, sleepy one. Idle, listening, thinking and talking have
  none, exactly as before. The lid eases in over about a second, never pops,
  adds no idle movement, is the same under calm motion and Still, and is left
  off entirely during a crisis-help answer (the animal stays neutral). It comes
  down as an animal nods off and lifts a little after the eyes open as it wakes.
  A blink still shuts the eye all the way, and a shut eye (asleep, mid-blink)
  keeps its dark line - the lid gives way to it. The robot has none. Painted in
  the shader's surface colouring, so it costs nothing per march step; the
  phone's shaders are still under 60,000 (panda 59,693, owl 52,064, otter
  55,018, monkey 59,602). Pictures in `docs/critters/eyelids/`; details in
  `docs/CRITTERS.md` "Painted eyelids". Needs the new desktop and phone
  builds; no backend change.

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
  See `docs/JARVIS-API.md` section 93 and `docs/CRITTERS.md`, "Animal
  options".
- **An app Jarvis builds is now a project (the backend half).** In
  Projects, a coding project can be an app: its latest saved version and its
  open tasks show on its page. A task is one change kept as a separate copy
  of the app; open it, read the whole change, then **Merge** - ONE approval
  card lists every file and the whole change (Windows Hello on the PC, your
  fingerprint or PIN on the phone; never from a widget) - or **Discard**. On
  the PC you can paste a change in. A change too big for one card is refused
  with "ask Jarvis to split it". Nothing runs and Jarvis does not write the
  code yet (that waits for the 12 GB card). Deleting the project keeps the
  app's files; they can be added back. Also fixed: throwing away a task whose
  copy had been deleted by hand left its branch behind. Needs git. Not yet
  tried on your PC's real approval queue (`backend/README.md`, "Apps in
  Projects").
- **Chats: carry one on, see the whole thing, find it again.** Open any chat
  or Jarvis Live session in History and press **Continue this chat**: the
  Jarvis bar (PC) or Home (phone) picks it up where it stopped - the same
  chat, its newest kept messages, and its "read outside text" mark. The chat
  you are in now shows every earlier question and answer in a scrolling
  "Earlier in this chat" list, not just the last one. **Earlier chats** on
  Home and in the Jarvis bar (and "Chat history…" in the PC's tray) opens
  History. After 30 quiet minutes the next question starts a new chat, and a
  line says so. History marks each chat's kind - a Live session shows its
  length ("Live · 12 min · Today 14:05"), and "Show" can list Live sessions
  only, support chats, chats with other AIs or comparisons. **Chats Jarvis
  had with other AIs, and comparisons, are now kept in History** (encrypted,
  marked as outside text, never learned from or read aloud). A chat with a
  crisis moment is kept under the title "A difficult moment". Support chat
  records are never removed by "Delete conversations older than", start
  unticked in "Forget a time frame", and Delete asks once more. History: the
  list first (phone), dates with times and Today / Yesterday in both apps,
  answers without stray `**` and `#`, Copy on old answers, and "Forget a
  time frame…" at the top. The HUD window's own chat box now opens the
  Jarvis bar, so the PC has one chat box. Not yet tried on a real phone.

- **Fixed: chats that were not what they seemed** (the chat audit). Game and
  role-play chats were being kept in History although they are temporary -
  they are not any more, and both apps now say "This looks like a game or
  role-play, so it's a temporary chat". Deleting the chat you were in (from
  History, "Erase the words" with its chat, or "Forget a time frame") left
  its words going to Jarvis and brought it back under a new title - now a
  new chat starts and says why. "Move it here" in Jarvis Live on the phone
  carried on the wrong chat. "Erase the words" now names the chat it would
  also delete, and says plainly when there was none. Projects no longer
  promise that Jarvis reads a project's instructions in chats (it does not
  yet). The Brain's History and Projects status line no longer sits on
  "reading…". The phone's "Forget a time frame" and chatbot forms keep what
  you typed when you scroll or turn the phone; the phone now says when a
  temporary chat starts or ends, and "New conversation".

- **Solve it here: a captcha handed to your phone.** When a chatbot website
  or a customer-support chat that Jarvis is using stops at a captcha, a
  sign-in page or an "unusual activity" page, your phone now says so ("Gemini
  needs you") and offers **Solve it here**: a live picture of that one
  browser window on your PC, and your taps and typing passed back to it -
  only while Jarvis is paused there, never saved on either side. Jarvis never
  solves it for you. Some captchas refuse taps passed on this way; "Solve it
  on the PC instead" is always there, and the PC's Brain shows the same
  alert. Press Resume when it is done (Resume asks with a card, as always).
  Not yet tried against a real captcha.

- **Jarvis Live extras.** On the PC: a key to start or end Live, off until
  you pick one in Settings -> Shortcuts (Alt+Shift+L is free for it). On the
  phone: a Quick Settings tile (with the minutes left), the headset button
  (press to stop Jarvis talking, hold to turn the microphone off or on - it
  never approves anything), a "Live ended - Resume" notification for ten
  minutes, a Bluetooth headset's microphone used while one is connected (the
  Live screen says which microphone), "Talk about this in Live" in the Share
  sheet (the shared text is outside text and goes when you tap Send), and
  "End Live when" on the Security screen, like the PC's: when App lock would
  ask again (the default), or only when the phone's screen locks (asks for
  your fingerprint or PIN). Not yet tried on a real phone.

- **Chat with customer support for me.** Jarvis can chat with a company's
  customer support for you - Groupon first - in your name, in a browser
  window you can see on the PC. Fill in the company, what you want done and
  the details Jarvis may give (each one exactly as written) on either app's
  Brain; ONE approval card shows all of it and the company's terms risk
  (your real account could be closed). You open the chat on the help page
  yourself; Jarvis writes from there. **Every offer - a refund, a credit, a
  cancellation - gets its own card**, and nothing is accepted before you
  approve it; the app offers Decline, Say something else and Take over,
  never Accept. "Are you a bot?", identity checks (card digits, security
  questions, codes) and a detail not on the card are handed to you - Jarvis
  never claims to be a person and never sends a password, card number or ID
  number. The chat is kept in your encrypted chat history; Export on the PC
  saves a plain text copy. Not yet tried on Groupon's real site: run the
  read-only check first (backend/README.md, "Chat with customer support for
  me").

- **Forget a time frame.** Say or type "forget what you learned last
  week" or "delete my chats from 1 to 15 September", or open it yourself:
  the desktop's Brain -> History, or the phone's Brain. Jarvis lists every
  fact it saved in those days and every chat from them, each ticked; untick
  anything to keep and tap **Forget these**. One approval card lists
  everything, and you approve it by tapping - saying "yes" does nothing.
  The facts are forgotten, exactly like Forget, and the chats deleted; for
  **10 minutes one tap on Undo puts it all back** (the Undo is kept in
  memory only, so it also ends if Jarvis restarts). A chat that also has
  messages from other days is marked, because the whole chat goes. At most
  200 at once. If a date could mean two things ("on Monday" said on a
  Monday, "3/9"), Jarvis asks. Erasing a fact's words for good is still
  "Erase the words", one fact at a time. This is the one place Jarvis
  deletes many things at once. Not yet tried on your PC's real memory.

- **The money limit for chatbots with a key is now a hard stop.** Every
  message asks the service to keep its answer short enough to fit in what
  is left of your monthly limit (at most 8,000 word-pieces, fewer as the
  month is used), so one long answer cannot carry a month past it. An
  answer cut short says so under it in both apps: "Jarvis asked for a
  short answer so it stays within your limit; the rest was cut off." Each
  company calls this setting something different; each name was checked in
  that company's own code (OpenAI, Groq, OpenRouter, Mistral, and xAI from
  its own client program). **DeepSeek's could not be confirmed, so no cap
  is sent to DeepSeek** - it keeps the old check before each message. For
  every service except OpenAI, whether hidden "thinking" counts inside the
  cap is not stated, so Jarvis leaves room for it - a guess, so a month
  can still end slightly over there. See it per service with
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py spent`. Not yet
  tried against the real services.

- **A monthly money limit for chatbots with a key.** Each service Jarvis
  reaches with an API key (OpenAI, DeepSeek, Mistral, xAI, OpenRouter,
  Groq) now needs a monthly limit before it is used - set on the PC with
  one line, for example
  `cd "<your backend folder>"; py -3 jarvis_chatbot_api.py limit openai 5`
  for $5 a month. Jarvis estimates each message's cost from the
  word-pieces the company reports and a price list, stops a service when
  its month reaches the limit, and checks before every message that it
  cannot go over. The approval card and both apps show "About $4.55 of
  $5.00 left this month for OpenAI", and "Used so far" adds "about $0.03".
  **The prices Jarvis starts with are not checked** (written from memory,
  no price page could be opened): see them with
  `py -3 jarvis_chatbot_api.py spent` and correct one with
  `py -3 jarvis_chatbot_api.py price openai <in> <out>`. It is an estimate,
  so a month can end slightly over. Limits and prices can only be set on
  the PC; the apps only show them. Not yet tried against the real services.

- **Jarvis Live, fixed after four reviews - and your three answers built.**
  - **After a crisis answer, Live gets more time.** It does not end at its
    time limit until at least 30 minutes after the last such answer, and
    it does not say "minutes left". It is quiet about it. You can still end
    it any time. Both apps.
  - **One "Interrupting Jarvis" setting** instead of two, for Live and
    everyday voice alike: "Interrupt by voice" (recommended), "By button
    only", or "Don't interrupt". On the PC: Settings -> Voice, where the old
    switch was. On the phone: the Readiness screen. Your old choice carries
    over (the old switch off becomes "Don't interrupt"; Live's "tap only"
    becomes "By button only").
  - **Remarks to someone else are not kept in chat history at all** (they
    were kept, marked "(not for Jarvis)"). An old one still in your history
    shows as "(not for Jarvis)".
  - **"End Live when"** (PC, Settings -> Voice): with App lock on, Live ends
    when App lock would ask again (the default), or only when Windows locks
    - the looser choice asks with an approval card. The phone keeps App
    lock's own rule.
  - **Clearer words:** "End Live" (not "Stop"), "Mic off" / "Mic on" (not
    "Mute"), "Listen anyway" during a call; every pause says what to do
    next; "your PC", never "your desktop"; when Live ends it says why, in
    a sentence, and says it aloud when it ended by itself.
  - **Fewer surprises:** "that's it" or "I'm done" in answer to a question
    no longer ends Live; only a card raised during Live pauses it (an old
    waiting card does not); tap buttons no longer come out garbled; typing
    counts as talking for the quiet timer; Esc on the PC hides the bar but
    keeps the conversation; a remark to someone else no longer wipes the
    answer (or the crisis help) off the screen.
  - **Easier to find:** the phone has a strip on Home while Live is on and
    a "Live" shortcut when you long-press the app icon; the PC's tray icon
    gets a red mark; "What asks first" lists "Start Jarvis Live - does it
    without asking" in both apps; Brain's old "Live" tab on the PC is now
    called "Now".
  - Said plainly: none of this has run on your PC or phone yet, and the
    phone's part is only compiled by GitHub.

- **Jarvis Live: talk back and forth, on the PC and the phone.** Press
  Live (the Jarvis bar, the tray, or Home -> Live on the phone) or say "Hey
  Jarvis, let's talk", then just talk - no "Hey Jarvis" before each
  sentence. Every sentence is still checked to be your voice on your PC
  before any words are made of it, and cards still need a tap (Jarvis stops
  listening while one waits). A sign shows the whole time ("Jarvis Live ·
  24 min left"), with Mute and Stop; on the phone a notification with End
  and Mute. It ends when you say "Okay Jarvis, that's all for now", press
  Stop, after 90 quiet seconds, or at 30 minutes ("give me twenty more
  minutes" adds time). After a spoken question, tap buttons ("Yes", "No")
  answer it; you can type too. It pauses itself during a phone or video
  call. Two new voice settings in both apps: "Jarvis Live" (how far it is
  trusted under "Only trust the talk button"; trusted fully by default) and
  "Interrupting Jarvis in Live" (by voice, or by tap only). Said plainly:
  it needs your voice trained first; very short replies ("yes") are still
  too short to check, so use the buttons; nothing has been timed on your
  PC; and **the camera part is built but switched off** until the second
  graphics card is in and passes the photo test.

- **Chatbot driver fixes, and a correction: every chatbot is reachable from
  both apps.** The entries below that say "still not usable from either
  app" are out of date: both apps' chatbot screens can start a
  conversation with any of the chatbots once it is set up (a website signed
  in, a key saved, or the model chosen). None has been tried against the
  real site or service yet. Fixed at the same time: a website window no
  longer reads an answer from a different chat you clicked while the first
  answer was coming; each site's self-check now asks two questions in the
  same chat, so a wrong guess about a site's chat address is caught by the
  check rather than mid-conversation; a site no longer shows "ready" after
  a sign-in window that was closed before you finished signing in (if you
  signed in to Gemini before this change, run
  `py -3 jarvis_chatbot_gemini.py sign-in` once more - it finishes at once
  if it is still signed in); the second AI on your PC no longer ends with a
  wrong "did not answer within 180 seconds" when it was only waiting for
  your own chat, and Stop now cancels its answer so the graphics card is
  freed; and a few words are now right (no "leaves this PC" or "(this PC)
  (this PC)" for the second AI on your PC, and the real reason when a
  key-based chatbot is not set up).

- **A new voice setting in both apps: "Answers about your screen after
  "Hey Jarvis"".** If you choose "Only trust the talk button" for
  hands-free, an answer about your screen to a question that starts with
  "Hey Jarvis" now stays on screen - written, not read aloud. This setting
  lets you allow reading those answers aloud anyway: "Read aloud" shows an
  approval card first; "Keep on screen" (the default) applies at once. With
  "Same as the talk button" it changes nothing, and the settings page says
  so. It is under Settings -> Voice on the PC, and Checks -> Voice check on
  the phone. Said plainly: Jarvis cannot look at your screen from either
  app yet, so for now the setting is stored and waiting.


- **Ask several chatbots and compare** (both apps, Brain -> "Talk to a
  chatbot for me"). Tick "Ask several and compare", pick two or more
  chatbots, type the goal once. One approval card lists every chatbot
  Jarvis would ask. Jarvis then talks to each one in turn, under the same
  limits and checks as a single conversation, and at the end writes one
  summary on your PC: where they agree, where they disagree (and who said
  what), the sources each gave (not checked by Jarvis), and which one
  dropped out and why. If one shows a captcha or a sign-in page, Jarvis
  leaves it out and carries on with the others. Pause, Resume and Stop act
  on the whole comparison. Up to 3 chatbots with one graphics card, 4 with
  two (you confirmed these numbers). Not yet tried against the real
  chatbot websites.
- **The chatbot chooser is a list you can read on a phone.** It used to be
  one row of buttons, and with sixteen chatbots most fell off the screen.
  Both apps now list them one per line under three headings - "Websites (a
  browser window on the PC)", "With a key (each message costs a little)",
  "On this PC" - with the reason under any that is not set up yet.
- **A conversation through a key shows what it used**: "Used so far: 3
  requests, 4,215 word-pieces (tokens), model gpt-5-mini" (per chatbot in a
  comparison). The card already said Jarvis would show this; neither app
  did.
- **"What Jarvis can reach" showed the chatbot ways out as Off** although
  both apps can start conversations: a switch the routes should have set
  was never set. Fixed.
- **The chatbot driver can now work eight more chatbot websites - still not
  usable from either app.** ChatGPT, Claude, Microsoft Copilot and
  Perplexity, plus DeepSeek, Grok, Le Chat (Mistral) and Meta AI (these
  last four picked as "other commonly used" websites - say if you want any
  left out). Each works exactly like Gemini: a browser window you can see,
  a steady typing pace, nothing hidden, and a stop to ask you at any
  captcha, sign-in or "unusual activity" page. Each has its own spare
  account, signed in once by hand, and each company's terms restrict
  automated use, so that account may be blocked or closed. Perplexity's
  listed sources are copied as text under its answer, never opened. How
  Jarvis finds each site's buttons could not be tried against the real
  sites: run each site's one-line self-check on the PC first
  (`backend/README.md`).

- **The rules for letting Jarvis look at your screen - not in the apps
  yet.** "Look at this" (one look when you ask) and "Watch with me" (a
  session you start and stop, 30 minutes unless you say otherwise, 2 hours
  at most) now have their rules written and tested on the PC side: Jarvis
  pauses on password boxes, on anything on your "Never look at" list
  (password managers and Windows sign-in to start with; adding is instant,
  taking something off asks with a card), on protected windows and on pages
  whose site it can't read; it checks just before and just after each
  picture and throws the picture away if either check fails; it keeps
  nothing it saw; and "Stop everything" ends a session. Answers about the
  screen will be read aloud unless a sensitive fact was used, like web
  search answers. There is no key, button or setting for it in either app
  yet, and the parts that read Windows itself are the next step.

- **A switch to turn off swiping on approval cards** (phone, Security).
  Swiping right to approve and left to deny stays on unless you turn it
  off; off, every card is decided with its buttons only. Turning it back on
  asks for your fingerprint or PIN.
- **The chatbot driver can also use a key, or a second AI on your PC -
  still not usable from either app.** With a key saved on the PC, Jarvis
  can hold its one-card conversation with ChatGPT (OpenAI), DeepSeek,
  Mistral, Grok, OpenRouter or Groq through each company's official API.
  The key stays in Windows Credential Manager and goes only to that
  company. Each message costs a little on that account; Jarvis shows the
  word-pieces (tokens) used, but there is no money limit yet. Or it can talk
  to another AI model on your own PC, where nothing leaves the PC: with one
  graphics card that is the same model Jarvis uses, with both cards any
  model you already have. How to save a key: `backend/README.md`.
- **The chatbot driver's Gemini part is written - still not usable from
  either app.** Jarvis can now open its own Gemini window (gemini.google.com,
  in a browser window you can see), type a question at a steady pace, and
  read back only the answer to it. (It used to promise it never hides that
  it is a program; you reversed that on 2026-09-29, see above.) At a captcha, a sign-in page or an "unusual activity" page it stops and
  asks you instead of trying to get past it. It uses its own browser profile,
  which you sign in to once, by hand, with the spare Google account. Before
  real use, run the one-line self-check on the PC (`backend/README.md`) - it
  sends "What is 2 plus 2?" and says PASS or FAIL for each step, because the
  way it finds Gemini's buttons could not be tested against the real site.
- **"Talk to a chatbot for me" now has its screens in both apps - but no
  chatbot can be reached yet.** On the PC it is a card in Brain -> Work; on
  the phone, a card in Brain. You choose the chatbot, type what Jarvis
  should find out (the card says these words are sent exactly as typed),
  set the most messages and minutes and any words it must never send, and
  Start asks for one approval card - nothing is sent before your yes. While
  it talks you see the conversation, with the chatbot's words marked
  "outside text", plus Pause, Resume and Stop; changing a limit asks a new
  card; the summary stays on screen at the end and is never read aloud. The
  phone also shows "Talking to Gemini, 3 of 5" with a Stop button. Gemini's
  part is still being built, so today Start says so and does nothing.
- **New: Projects in both apps.** Brain now has Projects on the PC and on
  the phone. Make a project, write how Jarvis should help with it and a
  few notes, and track numbers ("benchmarks") - log a number with a tap,
  see a small chart of your numbers over time with your target as a
  dashed line, and whether each one is better or worse than last time.
  Health and money numbers show "private - not read aloud". Deleting asks
  "are you sure?" first. A coding project's folder is chosen on the PC
  (from "Folders Jarvis may look in"); the phone says "Set on your PC" for
  that. The "Shareable" switch asks you with a card to turn on, and turns
  off at once.
- **New: take a wrong private mark off.** Jarvis sometimes marks a number
  private by mistake - it reads "5k time" as money. You can now remove
  that mark; because the numbers may then be read aloud, it asks you with
  one approval card first. A mark you added yourself comes off at once.
  Renaming the benchmark checks its name again.
- **Backups and the data-health check now include your projects**
  (`projects.db`). Before this, a backup would not have kept them.
- **The core of the chatbot driver - not usable yet.** The part of Jarvis
  that will hold a conversation with an AI chatbot for you (Gemini first)
  is written and tested on the PC side: one approval card per
  conversation, a check before every message so nothing private leaves,
  and stops at any captcha or sign-in page. There is no button for it in
  either app yet, and the Gemini part is not built.
- **Fixed: marking a crisis answer "wrong" counted toward "suggest the
  bigger model".** Crisis messages are never learned from and never
  counted; the thumbs-down on a crisis answer was the one place that still
  counted. It no longer does. A thumbs-down on any other answer counts as
  before.
- **Fixed (phone): "Use" on a model that cannot chat.** Brain › Model on the
  phone offered "Use" on memory-search models such as nomic-embed-text,
  which would leave Jarvis unable to answer. Like the desktop, their row now
  has no "Use" and says "for memory search only - it cannot chat". Both
  apps follow one shared table of cases, so they cannot drift apart.
- **New (phone): reconnects as soon as the network changes.** Walking out
  of Wi-Fi, or switching Tailscale on, used to leave the phone on a dead
  connection for up to about a minute and a half. Now it reconnects within
  a couple of seconds. Approving still waits until the link is trusted.
- **New (phone): "Tailscale (or Meshnet) is off on this phone".** When the
  link is down and the phone has no VPN running at all, Home and Checks
  say so under the link.
- **New (phone): Show token on the pairing screen.** The 43-character token no
  longer has to be typed blind. It starts hidden, is never saved anywhere
  new, and screenshots and screen recording are blocked while it is shown.
- **New (phone): "Background restart" is offered once after pairing.** A
  line on Home, in the same words as the Checks card, with "Keep link
  alive" and "Not now". It never comes back after either.
- **New (PC): the live check asks "Can your phone reach Jarvis?"**
  (`selftest.py --preflight`): is a phone address set, is it a Tailscale or
  Meshnet one, is Tailscale or Meshnet on this PC, is Jarvis listening
  there, and is there a Windows Firewall rule - each with the one line or
  the one setting that fixes it.
- **Docs: a Quick start at the top of `docs/INSTALL.md`** - the shortest
  way to a first typed chat, with the desktop app starting Jarvis, then
  pairing the phone.
- **Projects, first part (on the PC's side only - not in the apps yet).**
  Jarvis can now keep projects: a coding project (an app) or a life
  project ("run a half marathon"), each with its own instructions, a few
  notes, a to-do list and the goals it belongs to. A coding project's
  folder must already be one of "Folders Jarvis may look in", and is
  chosen on the PC. Each project can track numbers ("benchmarks"): say
  "I ran 5 km" or "log my weight as 72.5 kg" and Jarvis writes it down
  without the AI model and says whether it is better or worse than last
  time - but only when one of your projects tracks that number.
  Weight, heart rate, money and other health or money numbers stay on
  screen and are never read aloud. A "Shareable" switch per project
  starts off, and turning it on asks you with a card; nothing is ever
  sent by it yet. Running tests and Jarvis changing code come later. The
  screens in both apps are next.
- **Fixed (phone): "open help", "connection", "the morning briefing",
  "about" and "Jarvis's voices" opened Settings at the top.** Each now opens
  the phone's own place for it - Help, Checks, Brain or "Jarvis's voice" -
  and scrolls to it. A setting that only the PC app has (keyboard shortcuts,
  accounts and a few more) now says so in one line instead.
- **Fixed (phone): "Catching up…" explained properly.** An approval card
  said "Not connected to the desktop" even while the phone was connected and
  only catching up. It now says Jarvis is catching up with your PC and the
  decision waits until then. Checks calls this state "Catching up…" like
  Home (it said "Stale"), Home shows Retry next to it, and coming back to the
  app reconnects on its own. Approving still waits until the link is
  trusted again.
- **Fixed (phone): the "Brief me now" and "What did I miss?" app-icon
  shortcuts** opened Brain at the top. Each now asks its question on Home,
  as if you had typed it.
- **Fixed (phone): an answer made without the AI model** said "answered on
  this PC" on the phone. It now says "on your PC".
- **Answers from web search and home status are read aloud again when you
  ask by voice.** Before, any answer where Jarvis used a tool was kept on
  screen ("It's on your screen."), so a spoken question answered from the
  web was never spoken. Now only web search and home status (which is
  where the weather comes from) are read aloud. Email, calendar, notes,
  files, memory and any other tool still keep the answer on screen, and so
  does Jarvis not being sure which tool ran. Both apps follow one shared
  table of cases, so they cannot drift apart.
- **Fixed: one "Hey Jarvis" heard by both the phone and the PC.** Both
  used to answer, so you got two answers - and a timer or "next song" could
  happen twice. Or, after a plain "Hey Jarvis.", the second device used up
  the listening moment and your real question was thrown away. Now only the
  first copy is answered, the other device stays quiet, and each device
  listens for its own follow-up question. Your voice is still checked
  before any words are written down.
- **Fixed (desktop): Forget's "when did this stop being true?" box.** "Sept
  20" was saved as the year 2001; now a date with no year means the most
  recent one that has passed, a date in the future is refused, and a date it
  cannot read asks again instead of quietly dropping the Forget you said yes
  to.
- **Fixed (desktop): "Use" on a model that cannot chat.** Memory-search
  models such as nomic-embed-text say "for memory search only" instead.
- **Fixed (desktop): raw underscores in answers** - `_words_` now show in
  italics.
- **Fixed (desktop): putting one of two approval cards aside hid both.** The
  next card now shows, and the count of waiting cards is right.
- **Clearer (desktop): Erase's second question** says what OK and Cancel
  each do. Two small wording slips fixed in Hardware and Voices.
- **Fixed: typing the phone's pairing key exactly as the PC shows it.** The
  PC shows the key in groups of four with spaces, to make it easier to read.
  The phone kept those spaces, so the key was refused. The phone now drops
  them as you type, and the PC says to leave them out.
- **Fixed: "Tell me when this page changes" alerting when nothing visible
  changed.** It compared the whole page, including hidden codes that change
  on every visit. It now compares only the words you can see. Watches set up
  before this record the new kind once, quietly, instead of alerting.
- **Fixed: "Start with Windows" said on when Task Manager had it off.**
  Settings now reads Task Manager's Startup switch too, and turning it on in
  Jarvis turns that switch back on.
- **Clearer message** when the patch script is pointed at the wrong folder:
  it no longer sends you looking for "OpenJarvis", an unrelated project.

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

**New: watches**

- **"Tell me when a search shows something new."** Jarvis runs your search
  once a day (every 6 hours at most) through the search service you chose -
  never another one - and tells you when new results appear.
- **"Tell me when the price on <address> drops below X."** The price is read
  by plain code, not the AI, and shown under the watch so you can check it
  picked the right number. Jarvis never buys anything.
- **GitHub watches:** "tell me when CI fails (or finishes) on owner/repo" and
  "tell me when PR #12 on owner/repo merges". Read-only, using the GitHub key
  you already have. One line to add on the PC: `github_read = "auto"` under
  `[autonomy.tiers]` in `jarvis-framework.toml` (the refusal message names it).
- **A watch that stops working tells you once** (at most every 12 hours)
  instead of failing silently, and clears by itself when it works again.
- **Page watches ignore hidden page bytes**, so a page nobody changed no
  longer counts as changed (a fix ported from another branch).

**New: Brain upgrades**

- **Search what was said in your old chats**, in both apps' History - not
  just titles. Each match shows the words in place, and "Find in this chat"
  steps through them. The search runs on your PC; nothing is saved and
  nothing goes to the AI.
- **"History of this fact"** on the PC's Memory tab: every earlier wording,
  with the changed words marked. Erased words never come back.
- **Galaxy now shows the people and things Jarvis knows about.** Click a name
  to open "About <name>".
- **Fixed: Galaxy could show memory while "Windows Hello for memory lists"
  said it was hidden.** The HUD's copy is covered too. Galaxy's search now
  counts every match and says when nothing matches.

**New: reminders, your phone, and Lockdown**

- **"Remind me next time I talk about X."** When your own words later mention
  it, Jarvis brings it up in the chat. At most 3 times, never out loud if the
  topic is sensitive, gone after 90 days. No card.
- **"Ring my phone."** Said to Jarvis on the PC, your phone rings on its alarm
  sound - even on silent - with a Stop button, for at most 2 minutes. It never
  rings for an old message.
- **"Playing on your PC" on the phone's Home:** previous, play, pause, next.
- **Lockdown.** One tap (or "lockdown") makes everything that would leave the
  PC ask first, and anything that runs by itself stop. Turning it off is on
  the PC only, with a card and Windows Hello. Not yet covered: the ntfy push
  notice, which lives in your own `jarvis_gate.py`.

**New: smarter memory**

- **"Where did I put ...?"** Tell Jarvis "the passport is in the top
  drawer", then ask "where's my passport?" - it answers at once, without the
  AI model, and says when you told it. A newer place replaces the older one.
  ("Where's my phone?" still rings your phone.)
- **Facts keep "until" dates from your words** ("on holiday until 12
  October") and are never hidden by themselves when the date passes: Jarvis
  asks "Still true?" instead.
- **Overnight memory tidying now actually runs, cards only:** at most five
  "Still true?" or "Which is true now?" cards a night, using the AI on this
  PC only, and only while its switch is on. It never changes a fact by itself.
- **Deleting a chat offers to forget the facts it taught you**, with nothing
  ticked to start, and "are you sure?" before anything is forgotten.

**New: phone conveniences**

- **After a restart, a quiet "Hey Jarvis is off - tap to turn it back on"
  notice**, if listening was on before. Nothing opens the microphone by
  itself.
- **Three Quick Settings tiles you choose:** a focus session, a 10-minute
  timer, Brief me, Stop everything, or play/pause on the PC. Never Approve or
  Deny. Held while the connection catches up. Stop everything works even
  while the app is locked, like the PC's hotkey.
- **Notes for Android 17:** Jarvis's voice has its own volume slider, and
  Floating Jarvis may work as an app bubble (touch and hold the icon).
- **Install notes for 2027:** Google will require extra steps to install
  unverified apps by tapping the file; installing from the PC with adb stays
  allowed (docs/INSTALL.md).

**New: better voice (each off until measured on your PC)**

- **An optional second "hey Jarvis" check:** two detectors must agree before
  Jarvis wakes, for fewer false wake-ups. Off until you choose it, in both
  apps.
- **A newer speech detector (Silero VAD v6)** you can switch to after
  measuring it on your PC; today's stays the default.
- **A third voice-ID model (WeSpeaker ResNet221)** is ready but cannot be
  chosen until it is measured on your PC - in a first test it let other
  voices through more often than the one used today.

**New: Today cards**

- **Your own words on a Today section** in both apps (above Coming up), at a
  time and on the days you choose: "show gym bag on my Today page on Mondays
  at 7". Set by saying it or with a small form; no approval card; Delete is
  immediate.
- **The Today section also shows today's briefing** - weather, calendar,
  email and what is still to come - without reading anything new.

**New: photo to reminder**

- **Give Jarvis a screenshot, a picture file or a shared photo** of a flyer or
  ticket, and it suggests a reminder from the date and time it finds. Nothing
  is set up until you tap Add (or "Also on my phone"). The words are read on
  your PC, never by the AI model, and are not kept.
- **You can now say calendar dates:** "remind me on 12 October at 2pm to pay
  the deposit". A slashed date like 5/10 is read month first (May 10).

**New: PC help**

- **Ask "why is my PC slow?", "how full is my disk?", "what's using my graphics
  card?", "how hot is my graphics card?" or "when did my PC last restart?"**
  and get a plain answer at once, without the AI model. Also under Settings ->
  Hardware and models on the PC and Brain -> PC help on the phone. It only
  reads; program names never leave the PC and are not saved. Changing Windows
  settings (Night light, dark mode) is not built yet.

**New: widgets you describe**

- **Say or type what a small widget should show** - "my next 3 reminders and
  a 10-minute timer button" - and Jarvis makes a preview; tap Add to keep it.
  It is built from a fixed menu of five block kinds and eleven sources, never
  code, and plain code on the PC checks it. It shows on the phone's home
  screen (Jarvis widget 1-3) and in the desktop widget window, in place of
  the face. Its buttons are only the Quick Settings tile actions. Delete is
  instant. Email text, saved facts and web pages are never on the menu.

**New: smarter answers**

- **Big tool results (long files, emails, web pages) are shortened to their
  start and end** instead of being dropped, so Jarvis can still answer from
  them. In long answers that use many tools, older tool results are cleared
  to make room; your own words are never cut.
- **If Jarvis says it did something but nothing actually ran,** the answer
  now ends with "(Nothing was actually done - no action ran in this
  answer.)" - and says so aloud on voice.

**New: model tryouts (tools only - nothing switches by itself)**

- **Try other chat models overnight** against Jarvis's own: tools, learning,
  speed and how much fits on the graphics card, with a plain verdict for each
  (`tools/model_tryout/README.md`).
- **Try other memory-search models and re-rankers** with the memory
  self-test. New `JARVIS_MEMORY_EMBED_MODEL` / `JARVIS_MEMORY_RERANK_MODEL`
  switches; the defaults are unchanged.
- **The preflight check warns about a hidden llama.cpp `config.ini`,** and
  docs/MODEL-TOPOLOGY.md has two engine settings to try, with how to measure
  and undo each.

**New: bring in old chats from ChatGPT, Claude or Gemini**

- **Brain -> Memory on the PC: "Bring in chats from ChatGPT, Claude or
  Gemini".** Choose the export file; Jarvis reads it in the background and
  every possible fact waits for your yes, one card at a time. Nothing is
  saved by itself, and nothing leaves the PC.
- **Changed: importing reads only your own messages,** never the other
  assistant's replies - for all three services (Claude and Gemini imports
  used to read both sides).
- **Fixed:** a Google Takeout with Search activity in it no longer treats
  searches as Gemini chats.
- **DeepSeek chats can be brought in too**, and Jarvis reads imported chats
  better: a long chat is read in pieces the model can take in whole (the
  start of a long chat could be cut off before), with the date the chat
  happened and the facts Jarvis already keeps, the same way live learning
  does. Gemini's prompts are put back into conversations instead of being
  read one line at a time, without the "Prompted" in front, and "Gave
  feedback" lines are no longer taken as things you said. Claude's hidden
  reasoning and tool output are never read. If the AI model stops answering
  partway, the import pauses and nothing is lost.

**New: desktop polish**

- **Brain, Settings, Faces and the HUD reopen where you left them,** at the
  same size, and maximised if they were. App lock still asks Windows Hello
  before the HUD shows. A window whose screen was unplugged opens centred.
- **While Jarvis is clicking or typing on your screen,** the widget shows
  "Jarvis is working on your screen", a timer and a Stop button - the same
  as the Stop everything key.

**New: talk-to-type on the PC**

- **Hold Alt+Shift+T, speak, let go** - Jarvis types what you said into the
  program in front. Off by default; turning it on shows one approval card,
  turning it off is immediate. The voice check still comes first.
- **It never types into a password box, while Jarvis is locked, or into a
  window you switched to.** Your clipboard is put back afterwards, and the
  words stay out of Windows' clipboard history. The words are not kept.

**Fixed**

- **Desktop security update.** The desktop app's framework (Tauri) goes from
  2.11.5 to 2.11.6, which closes a published hole (GHSA-w28w-mhc8-qvjv) where
  one window of an app could read data queued for another window. Jarvis has
  several windows and streams chat answers that way, so it was affected.
- **Speech and memory-search models no longer report to Microsoft.** The
  library that runs them (ONNX Runtime) has its own usage reports switched on
  by default. Jarvis now switches them off before any model loads. One copy
  inside the speech engine can't be reached this way; Windows' own "Send
  optional diagnostic data" switch covers that one (docs/ARCHITECTURE.md §4).
- **A fact you forget no longer comes back by itself.** Jarvis re-reads the
  whole chat when it learns, so about a minute after you pressed Forget (or
  Erase), the same sentence could be saved again without asking. Now nothing
  is learned again from the lines it had already read in that chat, and if
  you say a forgotten fact again later, it waits for your yes.

**Faster**

- **A faster first answer after waking, and after a pause.** Jarvis now
  reads its rules and tool list into the model ahead of time - a one-word
  warm-up whose answer is thrown away and never recorded. It never loads the
  model by itself, never runs while you are asking something, and gives way
  the moment you do. To switch it off: `warm_prefix = false` under `[power]`
  in `jarvis-framework.toml`.
- **Jarvis speaks sooner.** Speech-to-text and the voice now use 4 processor
  threads instead of 2 on a PC with cores to spare (2 on a small one), which
  measured about 0.3 s sooner to the first sound. Your own `stt_threads` /
  `tts_threads` setting still wins.
- **The model's settings file explains the real memory check.** The notes in
  `backend/jarvis-primary.Modelfile` were out of date about flash attention.
  They now give the one PowerShell line that shows whether the whole model is
  on the graphics card ("offloaded 37/37").

**Smaller fixes**

- **The model tool test is fair to other models.** A model that loads with
  too short a conversation is skipped with a plain message saying how to fix
  it, `--repeat` saves the worst of several runs, and a model maker's own
  settings can be tried (`tools/tool_eval/README.md`).
- **The smartwatch setting says a ringing alarm may stay on the phone.**
  Watches often skip notifications that keep going until you stop them.

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
