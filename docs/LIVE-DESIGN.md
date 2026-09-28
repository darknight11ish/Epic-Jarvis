# Jarvis Live: talking back and forth, and showing the camera (design)

Status: **design only; nothing built.** For the owner's decision of
2026-09-28 in `CLAUDE.md` ("Jarvis Live": design voice and camera together
now). Written by the studio's designer against
`claude/jarvis-ai-assistant-research-ff37vy` (commit `2860995d`). Every
claim about today's code was checked in the file named next to it. Anything
marked **estimate** or **unverified** has not been measured on the owner's
PC or phone.

**In one paragraph:** Jarvis Live is a conversation you start and stop. You
press **Live** (or say "Hey Jarvis, let's talk"), and from then on you just
talk: no "Hey Jarvis" before each sentence, and you can cut in while Jarvis
is speaking. Under the hood it is the same voice path Jarvis already has,
held open for the whole session: every sentence you say is still a complete
recording, still checked to be your voice before any words are made from
it, and still turned into words on the PC only. On the phone you can also
turn on the **camera** and ask about what it sees; a picture is taken only
when you finish a question, goes only to your PC, and is never saved. A
"Live" sign is on screen the whole time on both devices. Approval cards
still need a tap. Nothing leaves your own devices.

## Four things to know first (some are bad news, said plainly)

- **A turn will take about 2-4 seconds, not "a second or two".** The
  decision's wording is more hopeful than the numbers. Jarvis's own estimate
  for "you finish speaking, Jarvis starts talking" is already 2.5-4 s
  (`docs/JARVIS-API.md:2755-2757`; `backend/jarvis_voice_flow.py:627`). Live
  does not make any step slower, but it cannot make them faster by itself
  either (§4 has the breakdown and what could help). With the camera on it
  is slower still, about 3.5-7 s (**estimate**).
- **Very short replies ("yes", "no", "okay") will be refused.** The voice
  check needs at least 1.5 seconds of speech at the Balanced setting and 2
  at Very strict (`backend/rebuilt/jarvis_voice.py:647`), measured with a
  little quiet either side, so about one second of actual words. A shorter
  clip is refused before it is checked or turned into words
  (`backend/jarvis_speech.py:1729`). This already happens after "keep
  listening after a question"; in a conversation it will happen more. The
  design keeps the rule (§3.4) because the evidence says a shorter clip
  cannot be checked: in the one test so far, the stand-in owner was
  recognised only from 2-second clips, never from 1.2 or 1.5-second ones
  (`backend/README.md:7600-7606`, synthetic voices, not the owner's).
- **On the phone, Live sends every sentence said near it to the PC.** Today
  the phone's hands-free listener sends nothing until its own "Hey Jarvis"
  spotter fires (`service/WakeWordService.kt:61-72`). In Live there is no
  phrase to wait for, so each sentence the phone hears goes to the PC to be
  checked. It stays on your own devices (Tailscale/Meshnet), and a voice
  that is not yours is never turned into words - but it is more of the
  room's sound travelling than before, and it costs battery (**unmeasured**).
- **The camera wording in the decision reads two ways.** It says both "with
  one card it reads text only" and "the camera part stays off until the
  card is in and a photo test passes". This design follows the second
  (camera off until the second card passes) and asks you to confirm
  (question 3).

## 1. What it is, and what it reuses

Live is not a new voice system. It is one new thing - **a session that holds
the listening window open** - wrapped around parts that already exist:

| Already built | What it does today | In Live |
|---|---|---|
| "Hey Jarvis" (`jarvis_wakeword.py`) | Starts a spoken question | Not needed between turns; can start Live ("Hey Jarvis, let's talk") |
| The listening window after a bare "Hey Jarvis." (`jarvis_speech.py:725-779`, 8 s, used once, per microphone) | The next sentence needs no phrase | **Held open for the whole session**, for that one device only |
| Keep listening after a question (`jarvis_speech.py:836-912`; phone `VoiceSession.kt:219`, `WakeWordService.kt:270`) | After an answer ending in "?", the reply needs no phrase | Every answer is followed by listening, question or not |
| The owner voice check before any words (`jarvis_speech.py:32`, `:1755`, `:1788`, then speech-to-text at `:1800`) | Refuses other voices before transcribing | **Unchanged, on every clip** |
| Smart Turn, "finished or only paused?" (`jarvis_speech.py:1048-1049`: ask after 200 ms of quiet, wait up to 2 s) | Ends a hands-free sentence | Ends each Live turn |
| Interrupting by talking (`jarvis_voice_flow.py:1-35`, `barge_in`, never transcribed; apps pause first, decide second, `VoiceFlow.kt` 0.5 s onset, 3 s grace, ~2 s clip) | Stops Jarvis for your voice or "stop" | The same, always on in Live where the device can do it |
| Telling the model it was interrupted (`JARVIS-API.md` §17.7) | The next question says where you stopped it | The same |
| Spoken-style answers (`jarvis_agent.py:2872`, `SPOKEN_NOTE` :4239) and speaking from the first comma (`speech-pieces.js`, `SpeechText.kt`) | Short answers, speech starts early | The same |
| "One moment." and "I heard you" | Fillers while you wait | The same switches, unchanged |
| The spoken card lines (`net/CardWords.kt:48-52`) | "I need your OK for that. There's a card on your screen." | The same (§6) |
| A photo sent with a question (`net/ChatPicture.kt:10-48`: in memory, metadata dropped, 1920 px cap, only to the PC) | Phone chat pictures | Camera frames use exactly this path |
| Reading a picture's words on the PC (`jarvis_ocr.py`, Windows' own text reader, at most 4,500 characters, `:56`) and the second card's Pictures lane (`jarvis_second_card.py:20`, `:271`) | One card: words only. Two cards: a picture model | The camera's two modes (§5) |

What Live adds is small: a **session** (start, stop, time limit, the sign),
a new clip source `live` on the existing `/api/voice/utterance` route, and
the phone camera screen.

## 2. Starting, stopping and the sign

**Starting (no card).** Starting Live is the owner's own act, like pressing
the talk button or starting "Watch with me" (`docs/SCREEN-DESIGN.md` §5, "No
card to start"). It needs no approval card, and it does **not** need the
"Hey Jarvis" switch to be on. Ways to start:

- **PC:** a **Live** button next to the microphone in the Jarvis bar; a tray
  row; an optional key (Alt+Shift+L, unbound by default - Alt+Shift+S, N, W,
  X and F are taken, `hotkeys.rs:71-108`).
- **Phone:** a **Live** button on Home; an app-icon shortcut.
- **By voice:** "Hey Jarvis, let's talk" (or "go live"), answered by
  `jarvis_quick.py` without the model, on the device that heard it. Only
  words that passed the owner check can start it. **The model gets no tool
  that starts Live**, so nothing it reads, and no schedule, can start one.
- Not while the event stream is stale (rule 4), and on the phone not while
  App lock is locked.

**The sign, the whole time:**

- **PC:** a small always-on-top badge, "Jarvis Live · 24 min left · Stop",
  and a Live mark on the tray icon. The same badge window "Watch with me"
  will use (`SCREEN-DESIGN.md` §2) - built once for both.
- **Phone:** the Live screen (Jarvis's face, your words and its answer as
  captions, time left, Camera and End buttons); and, when you leave the
  app, an ongoing notification "Jarvis Live · 24 min left · End" - the
  shape of the chatbot notification (`ARCHITECTURE.md:1572`). Android's own
  microphone indicator shows too, as it does for hands-free listening today
  (`WakeWordService.kt:83-87`).
- The sign also says when Live is **paused** and why: "Waiting for your tap
  on the card", "Paused: other voices", "Paused: link lost".

**Stopping - any of these ends it:**

| How | Notes |
|---|---|
| The **Stop / End** button (badge, tray, Live screen, notification) | Always works, even with App lock on |
| **Stop everything** (the desktop key Alt+Shift+X, the phone's button) | Live registers a stopper, like "Watch with me" does (`jarvis_screen.py:143`, `:1032-1033`) |
| Saying "bye", "that's all", "stop Live" | Must pass the owner check, like any command. Plain "stop" still only stops Jarvis talking, for anyone, as today |
| **Quiet for 90 seconds** after Jarvis last spoke (proposed) | Long enough to think or fetch something; short enough that an open microphone is not forgotten. A soft end tone, and "Live ended - it was quiet" |
| **The time limit**: 30 minutes by default, "20 more minutes" extends, 2 hours at most | The same numbers as "Watch with me" (`jarvis_screen.py:115-117`). Jarvis says once, 2 minutes before: "Two minutes left. Say 'more time' to keep going." |
| **PC:** Windows locks or sleeps | As for "Watch with me" |
| **Phone:** App lock locks, or the phone restarts | Live never restarts by itself |

**Phone screen off, or leaving the app (proposed):** the **camera stops at
once**; the **voice carries on**, like a phone call, with the ongoing
notification. Answers that must stay on screen say "It's on your screen"
and wait in the app. With **App lock** on, the phone locking **ends** Live
instead, because App lock means "nothing of Jarvis while locked". Android
allows this: the hands-free listener already keeps a microphone service
running with the screen off (`WakeWordService.kt:824`, foreground service
type microphone).

**Only one Live session at a time.** Starting Live on the phone ends one on
the PC, and the other way round. While Live runs on one device, "Hey Jarvis"
clips from the **other** device are dropped with the reason "Live is on your
phone" - the same shape as today's "answered on your other device"
(`jarvis_speech.py:811-833`).

## 3. The conversation loop

### 3.1 One turn

1. **Listen.** After Jarvis's answer finishes (or when Live starts), the
   device listens. It cuts your sentence with Smart Turn, exactly as the
   hands-free listener does today.
2. **Send the clip** to `/api/voice/utterance?source=live&mic=phone|desktop`.
   The PC runs every step it runs today, in the same order (`jarvis_speech.py`
   docstring, `:32-67`): is there speech (Silero), is it long enough (§3.4),
   **is it the owner**, and only then speech-to-text. The one difference: a
   `live` clip needs no "hey Jarvis" while that device's session is on,
   exactly like a clip in today's listening window (`:1697`). A `live` clip
   with no session on is refused, never transcribed.
3. **Answer.** The words go to the chat as a spoken question
   (`provenance: "voice"`), with a camera picture if the camera is on (§5).
   Spoken-style answer, speech from the first comma.
4. **Back to 1.** No "hey Jarvis", no button.

### 3.2 Interrupting

The existing barge-in, unchanged: while Jarvis speaks, half a second of
speech pauses the reply at once, about 2 seconds of it go to the PC as
`source=barge_in` ("was that the owner, or the word stop?" - never turned
into words, `jarvis_voice_flow.py:13-35`), and the reply stops for good or
carries on. When you were the one who spoke, what you said after that is the
next Live clip. It needs the device's echo canceller: on the phone Live uses
the voice-call microphone path the barge-in listener already uses
(`WakeWordService.kt:464-478`); on a phone without an echo canceller,
interrupting works only with "stop" or the End button, and the Live screen
says so.

### 3.3 The TV, other people, and Jarvis's own voice

- **Other voices** are refused by the voice check before any words exist, as
  today. Nothing of them is kept.
- **Jarvis's own voice** coming back through the speaker: during speech it
  only ever reaches the barge-in check, which compares it with Jarvis's
  voices and keeps talking (`jarvis_voice_flow.py:432-441`); after speech, the
  voice check refuses it.
- **Repeated refusals (proposed):** after 3 refused clips in a row, the sign
  shows "Hearing other voices - only yours counts" (nothing is said). After
  10 in a row, or 2 minutes with only refused clips, Live **pauses** ("Paused:
  other voices", one tone; tap to carry on). Pausing stops the phone sending
  the room's sound to the PC when you are not the one talking.

### 3.4 Too-short replies

Kept as they are (the evidence is in "Four things to know first"). What
changes is only how it is said: instead of the long reason sentence
(`jarvis_speech.py:1609-1611`), Live says a short line once - "Say a bit
more, so I can tell it's you." - and shows the full reason as a caption. Not
more than once a minute, so a room of short noises does not make Jarvis
chatter.

### 3.5 "Only trust the talk button" - the owner's call (question 1)

The strict hands-free setting decides whether a turn that did not come from
the talk button may read memories, private or sensitive answers aloud, and
may save facts without a card (`jarvis_voice.py:592-601`, `hands_free_trusted`
at `:1905-1915`). **A new `live` source is not the talk button, so today's
code already treats it like "Hey Jarvis" under the strict setting** - it
fails closed for any source it does not know (`:1913-1915`).

- **Proposed: keep it that way.** You pressed Start once, but then the
  microphone is open for up to 30 minutes, and a recording of your voice
  played near it would pass the voice check (which cannot tell a recording
  from you - `JARVIS-API.md` §16). That is exactly what the strict setting
  guards against.
- Under the default setting, "Same as the talk button", nothing changes
  either way: Live turns are trusted like the talk button.

### 3.6 Read aloud or kept on screen

**Every existing rule applies unchanged**, in the same order
(`JARVIS-API.md` §16, "What the apps must do about private answers"): answers
from email, calendar, notes, documents or any tool not on the read-aloud list
stay on screen ("It's on your screen."); a sensitive saved fact keeps an
answer on screen unless you allowed it; answers about the screen follow the
2026-09-28 rule; web search, weather and home status are read aloud. The
utterance reply for a `live` clip carries the same `private_aloud`,
`memory_aloud`, `sensitive_aloud` and `screen_aloud` fields as any clip
(`jarvis_speech.py:1757-1786`).

**Camera answers need a rule (question 2).** Today there is none: the PC
records its reading of a picture's words as a reading tool
(`jarvis_agent.py:4937`, `read_picture_text`) but, as far as I can see,
sends no `step` event naming it (`STEP_READS` holds only `read_screen`,
`:3165`), so the apps cannot tell; and the second card's picture model runs
no tool at all. **Proposed:** treat a camera answer exactly like an answer
about the screen - read aloud unless a sensitive fact was used or the strict
setting says otherwise - by adding the camera read to `STEP_READS` and to the
shared read-aloud table (`private-aloud-cases.json`).

### 3.7 Chat history and learning

- **One Live session is one chat**, kept in history like any chat by default
  (voice transcripts included, as decided 2026-09-24), encrypted on the PC. A
  temporary chat stays temporary.
- **Learning** from Live's spoken turns works as for any voice turn (and
  under the strict setting, like "Hey Jarvis"). A question sent **with a
  camera picture** is already marked by the PC as "came with a picture", not
  the owner's own words (`jarvis_agent.py:2884-2889`), so no fact is saved
  from it without a card (`jarvis_auto_learn.py:568`). The spoken-style
  answer still applies to it: that reads the app's own `voice` tag
  (`jarvis_agent.py:2872`), not the picture mark.
- **Never kept:** the audio (as today), camera pictures, and the words read
  from them - only your question's words and Jarvis's answer
  (`jarvis_chat_log.py:48`: "A picture: its words only ... The picture
  never.").

## 4. How long a turn takes

All numbers per turn, from "you stop talking" to "Jarvis's first sound".
**Everything is an estimate** unless it says measured, and the measured
numbers come from this repository's container (4 processor cores), **not
the owner's PC** (`backend/README.md:7583-7596`).

| Step | Estimate | Where the number comes from |
|---|---|---|
| Being sure you finished | 0.2-0.5 s; up to 2 s after a mid-sentence pause | Smart Turn's rule, `jarvis_speech.py:1048-1049` |
| Phone only: sending the clip over Tailscale/Meshnet | 0.1-0.3 s | estimate (~150 KB for 5 s of speech) |
| Finding the speech, the voice check, speech-to-text | ~0.45-0.55 s | measured in the container, "a later question" (`backend/README.md:7594`) |
| The app passing the words to the chat | 0.05-0.2 s | estimate |
| The model's first word | 0.2-0.8 s | estimate; not measured anywhere (thinking is switched off per request, `jarvis-primary.Modelfile` ~line 120) |
| Up to the first comma | 0.1-0.3 s | estimate |
| Making the first piece's sound (Kokoro, on the processor) | ~0.8-1.6 s | measured in the container: first sound 1.23 s after the first-comma change (`backend/README.md:7692`); a whole first sentence 1.3-1.6 s (`:7593`) |
| Phone only: fetching the sound | 0.1-0.2 s | estimate |
| **Total, voice only** | **PC about 2-3.5 s; phone about 2.3-4 s** | agrees with the 2.5-4 s already written in `JARVIS-API.md:2755` |

**One card vs two, voice only:** the same. Live's turns are answered by the
everyday model on the main card either way. When a long Live chat outgrows
the main card's room and "Longer conversations" is on, that answer moves to
the second card, which is slower per word (about two thirds of the memory
speed, `MODEL-TOPOLOGY.md:335-339`, published figures).

**With the camera on (§5):**

- **One card (words only):** plus Windows' text reader, started as PowerShell
  for each picture (about 1-2 s, **unmeasured** - `SCREEN-DESIGN.md` §8), plus
  up to ~1,500 tokens more for the model to read (about 0.9 s at the ~1,700
  tokens (word pieces) a second the 2080 Super reads in, `backend/README.md:773`). About
  **4-7 s**.
- **Two cards (pictures):** the question goes to the picture model on the
  slower 2060 (`jarvis_second_card.py:20`), and every picture costs at least
  1,024 tokens there (`HARDWARE-PROFILES.md:362-364`). About **3.5-6 s**,
  **unmeasured**; the first camera question after a while may wait several
  seconds more while the picture model loads.

**What could make it faster without breaking a rule:**

1. **Measure first.** `jarvis_voice_flow.py --measure` already prints each
   step's time on the owner's PC (`backend/README.md:7538`). Live's build
   step 5 runs it before anything is tuned.
2. **Keep the everyday model loaded** for the whole Live session, so no turn
   pays for loading it (how long Ollama keeps it today on the owner's PC:
   **unverified**).
3. **A faster first sound** - the single biggest step. Candidates already on
   the queue: Pocket TTS (measured here at 1.2 s first sound while copying a
   voice, `backend/README.md:7120-7122`) and Kokoro v1.0 (decided 2026-09-28); with two
   cards, a voice on the graphics card (research §11,
   `CUTTING-EDGE-2026-09-26-voice-vision.md:248-263`). Each measured by the
   existing bake-off before it replaces anything.
4. **Start checking early (later, measured):** send the clip when Smart Turn
   first says "finished", and throw the result away if you carry on
   talking. The owner check still comes first; only your own words are ever
   transcribed.
5. **Camera off when not needed.** The camera costs 1-3 s per turn; the Live
   screen says so next to the switch.

**Not allowed, even though each would be faster:** turning speech into words
before or alongside the voice check (`jarvis_voice_flow.py:69-71`); any
speech-to-text on the phone; talk-and-listen-at-once models
(`CUTTING-EDGE-2026-09-26-voice-vision.md:309-321`: they skip the voice check,
the on-screen rules and cards); any cloud service.

## 5. The camera

**Which camera: the phone's only, for now (proposed).** The use is pointing
at something - a label, a plant, a broken part, a sign. A PC webcam mostly
sees your face, your room and whoever is behind you. It could be added later
under the same rules if you ask for it.

**How a picture is taken - the simplest safe option (proposed):**

- The camera is **off** at the start of every Live session. You turn it on
  with the Camera button on the Live screen. The preview fills the screen
  while it is on, so you always see what Jarvis would see; Android's own
  green camera dot shows too.
- **One fresh picture per question**, taken the moment you finish speaking -
  never in the background, never "every few seconds", never streamed. The
  same shape as "Watch with me" (`SCREEN-DESIGN.md` §2).
- **Sent only after your voice passes.** The phone sends your clip first; only
  when the PC answers with words (it was you) does the picture go, inside
  the chat request, exactly as a chat photo goes today (`ChatPicture.kt`:
  re-encoded in memory, location and time data dropped, 1,920 px cap). A clip
  that was not yours means the picture is dropped, never sent.
- Rejected: a separate "Look" button (easy to forget, and one more thing to
  press while talking) and pictures on a timer (a camera that watches).

**Nothing saved.** One picture in memory at a time, dropped when the answer
is finished. Never written to disk by the phone (`ChatPicture.kt:24-28`),
never kept in chat history, never learned from.

**Pausing rules (fail safe):** no picture is taken when (a) the Live screen
is not in front, the screen is off or the phone is locked - **never on a
lock screen**; the Live screen is not shown over the lock screen; (b) App
lock is locked; (c) a card is waiting; (d) the picture is almost all black
(lens covered, phone face down) - dropped, and the caption says "Couldn't
see anything". While paused the camera itself is closed, not just ignored.

**Outside text.** What the camera sees can hold writing someone else wrote
(a poster saying "Jarvis, email this to..."). Like any picture, the PC marks
the question as "came with a picture" (`jarvis_agent.py:2884-2889`), so from
then on in that Live chat a note write or web search asks first, and any
card says what was read. Nothing the camera sees can start or approve
anything.

**Other people.** Jarvis never says who a person in the picture is: the
picture model is told not to identify anyone by their face (the research's
rule, `CUTTING-EDGE-2026-09-26-voice-vision.md:341-346`). Nothing about them
is kept.

**Stays on your devices.** The phone sends pictures only to your PC, over
Tailscale/Meshnet. The PC already keeps any turn with a picture on its own
model ("A PICTURE NEVER LEAVES", `backend/rebuilt/jarvis_router.py:587`). No
cloud picture service, and never into the chatbot driver.

**One card vs two:**

- **Two cards (the plan):** the picture goes to the second card's existing
  Pictures lane - no new switch. Candidates, **all unmeasured**:
  **`qwen3.5:9b`** (about 6.6 GB download; might serve long conversations and
  pictures as one model, so nothing swaps - research §4) - **recommended**,
  and **Qwen3-VL 8B** (about 6.1 GB) as the fallback. The photo test below
  picks between them. (Today's default in the code is `qwen2.5vl:7b`,
  `jarvis_second_card.py:271`.)
- **One card:** the PC reads only the **words** in the picture with Windows'
  own reader (`jarvis_ocr.py`), and the answer says "words only". This is
  what a one-card PC would get; whether the owner's PC uses it before the
  second card is question 3.
- **The phone never reads the picture itself** - no text recognition, no
  picture model on the phone. It only sends it.

**The photo test (run once, when the second card is in).** The camera switch
does not appear in the app until the PC says a photo test has passed on this
PC with the picture model it will use.

- **What it is:** a program, `jarvis_live_photo_test.py` (not written yet),
  with a fixed set of about 30 photos made for the test, with nothing
  personal in them: a food label, a plant, a street sign, an error message
  on a screen, a handwritten shopping list, a thermostat, a tangle of cables,
  a crowd of strangers. Each has a question and the facts a right answer
  must contain. It runs both candidates and keeps the winner.
- **What it measures:** how many answers are right; time from the question
  reaching the PC to the model's first word (middle and worst); the most
  graphics memory used on each card; whether the everyday model on the 2080
  Super stayed loaded; whether the long-conversation model had to be
  swapped out; and that the crowd photo never gets a name.
- **The one line to run** (PowerShell, on the PC):

  ```
  cd "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 jarvis_live_photo_test.py; Write-Host "The results are in $env:USERPROFILE\.openjarvis\live\photo-test (the newest folder: results.txt)"
  ```

- **Proposed pass bar:** at least 24 of 30 right; first word within 3 s in
  the middle case and 6 s at worst; nothing runs out of graphics memory or
  spills into the PC's normal memory; the everyday model never unloaded;
  no name ever given for the crowd photo. A model that misses any line does
  not switch the camera on, and the results say which line it missed.

**Camera and "Watch with me" together (proposed):**

- **One picture per question, from the device you asked on.** On the phone,
  the camera and the phone's own "Watch with me" (screen sharing) do not
  run together: turning one on pauses the other. Two pictures in one
  question would double the wait and confuse the answer.
- **On the PC, Live and "Watch with me" can run together:** a Live question
  asked at the PC takes the screen picture "Watch with me" would take for a
  talk-button question. Both signs show.

## 6. Approval cards during Live

- A question that needs a card works as it does today: the card appears on
  the screens as usual, and Jarvis says the existing fixed line, **"I need
  your OK for that. There's a card on your screen."** - then, once decided,
  "Approved. Carrying on.", "OK, I won't do that." or "That card timed out,
  so nothing was done." (`net/CardWords.kt:48-52`, the same on the desktop,
  `card-words.js`). Fixed words, never the card's contents, so it is safe in
  any room.
- **While a card waits, Live pauses listening** (the sign: "Waiting for your
  tap on the card"). It carries on once the card is decided or times out.
  The End button and Stop everything still work.
- **Never approved by voice.** A spoken "yes" answers nothing - the voice
  check cannot tell a recording from you (`voice/CardVoice.kt:16-18`). With
  listening paused, a "yes, do it" is not even heard. Swiping (on the phone,
  if switched on) and the buttons are the only ways.
- The five-cards-per-answer limit applies as always (`jarvis_agent.py:1805`).

## 7. Both apps, and the rules

**Both apps get Live's voice half.** What is **one-sided on purpose**, for
`ARCHITECTURE.md` §8:

| What | Where | Why |
|---|---|---|
| The camera in Live | Phone only | Proposed: you point a phone at things; a PC webcam mostly sees faces and the room. Can be added later if the owner asks. |
| The always-on-top "Jarvis Live" badge and the optional Alt+Shift+L key | PC only | Keyboard keys and floating windows are PC things, like the other hotkeys; the phone's sign is its Live screen and ongoing notification. |
| The ongoing "Jarvis Live · End" notification | Phone only | The chatbot notification's reason (`ARCHITECTURE.md:1572`): how a phone in a pocket shows something is still going. |
| Carrying on with the screen off | Phone only | A PC has no "screen off" of that kind; Windows locking ends Live, as it ends "Watch with me". |

New route `/api/voice/live` (read, start, stop, extend) is used by both
apps, so it is `ported` in `tools/check_parity.py`.

**Rule check:**

1. **Private things stay on the local model.** Audio, pictures and words go
   only between the owner's own devices. Live questions are answered on the
   PC's own model; a picture turn already never leaves the PC; Live offers
   no "try the cloud model". **Kept.**
2. **No public tunnel.** The phone reaches the PC through Tailscale or
   Meshnet only (2026-09-28); the PC listener sends audio only to a server
   on the same PC (`voice.rs:1015`, `is_loopback_base`). **Kept.**
3. **API keys.** None involved. **Kept.**
4. **Never auto-approves; blocks acting on a stale stream.** Cards need a
   tap; Live pauses while the event stream is stale ("Paused: link lost"),
   like barge-in and every other request. **Kept.**
5. **Non-commercial, sideloaded.** Nothing changes. **Kept.**

**"A client must not do speech-to-text."** Kept. The phone sends whole
recordings (`jarvis_speech.py:1017-1025`: `client_stt_allowed: False`); its
end-of-sentence check (Smart Turn) works on sound only, already accepted
(`ARCHITECTURE.md:1530`); and it does no reading of camera pictures either.

**Other standing decisions checked:** Stop everything ends Live; nothing
clears a rush latch or approves in bulk; `X-Jarvis-Client: hud` on every
request; the token is never logged; screenshots stay blocked on the phone
under App lock (`MainActivity.kt:656-673`, App lock or "Hide memory lists and chat
history"), which covers the Live screen.

## 8. Risks, and what is deliberately not included

**Risks:**

- **Waiting.** 2-4 s a turn (more with the camera) may feel slow next to
  cloud products that answer in under a second. Said plainly in §4.
- **Short replies refused** (§3.4). Most likely the most noticed annoyance.
- **A recording of the owner** can pass the voice check. Cards are still a
  tap; the strict setting (question 1) covers reading aloud and learning.
- **Battery and data on the phone:** an open microphone, the voice-call
  audio path, and the camera. **Unmeasured.**
- **A noisy room:** every loud sound becomes a clip the PC must check. The
  pause after repeated refusals (§3.3) limits it; a neural speech detector
  in the apps (research §9) would help more.
- **Echo on phones without an echo canceller:** interrupting only by "stop"
  or the button.
- **Camera text giving orders** is marked outside text and cannot act, but
  is still read.
- **The 12 GB card is not measured.** The picture model may not fit beside
  the long-conversation lane; the photo test finds out.

**Not included, on purpose:**

- **Always-on listening.** Live has a start, an end, a time limit and a
  sign. It never starts by itself.
- **Recording.** No audio or picture is saved, ever.
- **Talk-and-listen-at-once models** (Moshi, PersonaPlex, omni models): they
  skip the voice check, the on-screen rules and cards.
- **Streaming audio or video** to the PC. Whole clips and single pictures
  only; the old app's duplex streaming stays unported, for the reason
  `CLAUDE.md` gives (the voice check needs a complete clip).
- **Any cloud service** for speech, pictures or answers.
- **Recognising people** in camera pictures, and a camera that watches.
- **Approving by voice.**

## 9. Build plan (small testable steps)

1-2 are testable in this repository; the phone compiles only in CI; the
desktop with `cargo clippy --target x86_64-pc-windows-msvc`.

1. **Backend session** (`jarvis_live.py`): one session per device, start /
   stop / extend, the time limit, the quiet timeout, the refusal counter,
   pause reasons, a Stop-everything stopper, status as numbers and states
   only. `jarvis_speech.hear(source="live")`: no phrase needed while that
   device's session is on, refused otherwise; the other device's wake clips
   dropped during Live. Tests with made-up clips prove the owner check still
   runs before speech-to-text for every `live` clip.
2. **Routes and words:** `GET`/`POST /api/voice/live`, `source=live`, a `live`
   event; "let's talk" / "that's all" in `jarvis_quick.py`; the short
   too-short line; JARVIS-API section; `check_parity.py` `ported`.
3. **Desktop Live:** the Jarvis bar button, the badge (shared with "Watch
   with me"), the tray row, the listener's Live mode in `voice.rs`, card
   pause, a `tests/live.mjs` harness held to a shared `live-cases.json`.
4. **Phone Live (voice):** the Live screen, a Live mode of the listening
   service, the notification, screen-off and App lock rules, card pause; a
   `LiveRulesTest` held to the same `live-cases.json`.
5. **On the owner's PC and phone:** `jarvis_voice_flow.py --measure` during
   Live; a TV test (how many refusals, and that none became words); the
   phone's battery over 30 minutes. Numbers written into this document.
6. **The feature audit** (bugs, both apps, fit), ARCHITECTURE §8 rows,
   `docs/JARVIS-API.md`.

The camera - built switched off, **needs the 12 GB card to switch on**:

7. **Phone camera:** the CAMERA permission (not in the manifest today -
   `AndroidManifest.xml` has RECORD_AUDIO at line 27 and no CAMERA), CameraX
   (Apache-2.0, a new AndroidX library), the preview, one frame at the end
   of a turn, sent only after the voice passed, the black-frame drop, the
   pause rules; hidden until the PC says the camera is ready. JVM tests.
8. **Backend:** a `camera_ready` field that is true only when the Pictures
   lane is available and a passing photo test result is on file for that
   model; the camera read added to `STEP_READS` and the read-aloud table
   (after question 2).
9. **The photo test program and its photos** (licences checked) - written
   before the card arrives, run after. **Needs the 12 GB card.**
10. **The owner installs the card, runs the photo test** (§5). Pass: the
    camera switch appears in the phone. **Needs the 12 GB card.**
11. **The feature audit** again, for the camera.

## 10. Questions for the owner

1. **In Live you press Start once, then talk freely. If you have chosen
   "Only trust the talk button", should Live count as the talk button?**
   (Under the default setting nothing changes either way.)
   - **No, treat Live like "Hey Jarvis"** (recommended): memory, private and
     screen answers stay on screen and facts wait for a card, because a
     recording played near the open microphone could pass the voice check.
   - **Yes, treat Live like the talk button**: you pressed Start, so Live
     turns are fully trusted.
2. **Should Jarvis read its answers about what the camera sees out loud?**
   Today no rule covers it.
   - **Read them aloud, like answers about your screen** (recommended):
     unless a sensitive fact was used or the strict setting says otherwise.
   - **Keep them on screen**: Jarvis says "It's on your screen."
3. **Before the second graphics card is in, should the camera work at
   all?** Your decision says both "one card reads text only" and "off until
   the card passes a photo test".
   - **Off until the second card passes the photo test** (recommended): the
     simplest, and what the decision says last.
   - **Words only now, full pictures later**: with one card Jarvis reads the
     writing the camera sees (labels, signs), about 4-7 seconds a turn.

Sources: the files named in each section; Android's camera privacy
indicator and while-in-use microphone rules (platform behaviour, not
re-checked for this document); Gemini Live's shape as described in the
owner's decision.
