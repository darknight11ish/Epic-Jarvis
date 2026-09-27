# Jarvis launch video v6: "Your AI"

Two cuts from one project:

- `jarvis-launch-v6.mp4`: 1920×1080, 25.6 s, for the README and GitHub.
- `jarvis-launch-v6-vertical.mp4`: 1080×1920, 13.6 s, made upright for a phone.

## How this plan was made

The owner asked for a team to reflect on v1 to v5 before anything was made.
Six reviewers worked separately, then a moderator made them argue it out:

- an AI engineer (what the model and the abilities really are, with evidence);
- a motion and effects director;
- a launch strategist;
- an everyday viewer panel (a busy student, a hobby gamer, a cautious small-business owner);
- a sound designer;
- an honesty skeptic (every past overclaim, and a checklist).

What they agreed, in short:

- v1 to v5 never showed the AI doing something clever: v4 and v5 mostly
  showed things that work *without* the model.
- Effects had been laid over the words; they belong on the cuts and the edges.
- No "cutting-edge" on screen, no decorative HUD text, no numbers that look
  measured.
- Real screens big, cropped to the one line that matters.
- v3's honest end card, with the price.

The owner then decided two things:

- name the model once, as "Qwen3 8B by default";
- of the items built since the old brief, mention only "the phone connects
  only on your own networks", and only in the post text.

## The idea

**A real AI runs on your own PC.** It looks things up and shows where it
read them, checks it is you before it writes down a word, stops when you say
stop, lets you swap its brain from your phone, and still asks first.

## The look: "Glass & Light" (new, unlike v1 to v5)

- A graphite dark. The reactor (Jarvis's face, from the app's own code) is the
  only light, and its state colour (thinking, listening, speaking, approval) is
  the only colour.
- Real screens sit on glass slabs, rim-lit by that colour. They arrive with a
  short turn in depth, then stay flat and still while being read.
- Effects on the cuts and edges only:
  - an iris that opens each new scene out of the reactor's core (8 frames, 4 times);
  - a particle ignition on frame 0 and a particle settle at the end;
  - a tracing beam that runs once round the one line that matters;
  - a touch ring where a finger taps the phone;
  - a freeze and a light dip on "Stop".
- Inter for the words, IBM Plex Mono (the app's own font) for "You ▸".
- Music: a bright, clean 150 BPM half-time score in F♯ Lydian with UI
  sounds (tick, ping, chime) and a real silence after "Stop".

## Storyboard (landscape, 25.6 s)

| time | on screen | words |
|---|---|---|
| 0–1.6 | The reactor ignites, already bright on frame 0. | **AI. On your PC.** |
| 1.6–4.8 | Iris. The real Jarvis bar: the step line ticks "asking the model" → "using web_search" → "web_search done" → "writing the answer", then the answer. | **It looks it up.** You ▸ How do sourdough starters work? · Example answer |
| 4.8–8.0 | The same answer with "Where this came from" open; a beam round "not found in what Jarvis read". | **It shows its sources.** And flags quotes it can't find. |
| 8.0–11.2 | Iris. The reactor listening; the owner's voice drawn as sound, which settles into words. | **First: is it you?** → **Then the words.** You ▸ Hey Jarvis… · After voice setup |
| 11.2–14.4 | The real Jarvis bar speaking; "Stop." freezes it; a dip, then silence. | You ▸ **Stop.** It stops talking. · After voice setup |
| 14.4–17.6 | Iris. The phone's Brain screen, Model list: a tap on "Use", then "Waiting for your approval". | **Swap its brain.** Qwen3 8B by default |
| 17.6–20.8 | The approval card rises; a beam round "Nothing runs until you decide."; a tap on Approve. | **You say yes.** |
| 20.8–25.6 | Iris. Particles settle into the reactor; it shrinks beside the name. | **Your PC. Your AI. Your rules.** Jarvis · Windows PC · 8 GB NVIDIA graphics card · Android · Free |

The upright cut (13.6 s): the hook, "Swap its brain.", "You say yes.",
"Stop.", and the end card.

## Evidence for every claim

Main = `main` at da432b3, where all the feature work is now merged. "Today"
means built, on by default or after the setup named, and tested in the
repository. **Nothing has run on the owner's PC yet.**

| claim on screen | status | evidence |
|---|---|---|
| AI. On your PC. | today | The AI model runs in Ollama on the PC's own graphics card (`README.md:3-5`; `docs/MODEL-TOPOLOGY.md:3`). |
| Qwen3 8B by default | today | `backend/jarvis-primary.Modelfile:86` (`FROM qwen3:8b`). "By default" because the model can be switched (below). |
| It looks it up | today (on by default) | Web search is the one tool on by default (`backend/rebuilt/jarvis-framework.toml:1391-1392`). The step line's words are the app's own (`jarvis-desktop/src/step-words.js:24-41`). It sends the search words out (post text says so). |
| It shows its sources | today | "Where this came from" (`jarvis-desktop/src/memory-used.js:206`); sources are read from what a tool really returned, never from what the model claims (`backend/jarvis_sources.py:16-26`). |
| And flags quotes it can't find | today | "not found in what Jarvis read" (`memory-used.js:221`); a word-for-word check against what was actually read, which only warns and never corrects (`jarvis_sources.py:27-38`). |
| The answer text | example | Made-up example data fed to the real window; not a real model answer. Labelled "Example answer" on screen. |
| First: is it you? Then the words. | today, after voice setup | The owner check runs before speech-to-text: "not the owner → refused, not transcribed" (`backend/jarvis_speech.py:58-61`); "your voice is checked before any words are written down" (`:527-530`). Voice commands need the voice set up and trained (`backend/rebuilt/jarvis_voice.py:12-16`), hence the label. It cannot tell a recording of the owner from the owner (not claimed). |
| Stop. It stops talking. | today, after voice setup | Talking over a reply: it stops for the owner's voice, and for the word "stop" said by anyone; not for the TV or its own voice; never transcribed (`backend/jarvis_voice_flow.py:12-37`). On by default on the PC (`jarvis-desktop/src/barge-in.js:14-17`); listening must be on. |
| Swap its brain (from the phone) | today | The phone's Brain › Model and PC › Model list with "Active" and "Use" (`jarvis-client/.../ui/screens/BrainScreen.kt:583-587, 937-940`); `JarvisRuntime.switchModel` (`jarvis-client/.../JarvisRuntime.kt:1224`). Allowed by the owner on 2026-09-18 (`CLAUDE.md`). |
| "Waiting for your approval … Nothing changes until you do." | today | `BrainScreen.kt:1020-1033`, with `Approvals.WHERE` (`net/Approvals.kt:17`). |
| You say yes (the approval card) | today | "Needs your OK", "Deny", "Approve" (`net/CardWords.kt:29, 32`); the title (`backend/jarvis_card_words.py:99`); "Nothing runs until you decide." (`ui/approval/ApprovalCard.kt:545`). A model switch is a plain tap: the phone asks for a fingerprint only on risky cards by default (`data/Security.kt`). The switch is never shown finishing. |
| Windows PC · 8 GB NVIDIA graphics card · Android · Free | today | `README.md:3-8` ("Free and non-commercial"); sized for an 8 GB NVIDIA card (`docs/MODEL-TOPOLOGY.md:3`). |
| The reactor | today | The app's own drawing code (`jarvis-desktop/src/faces.html`), extracted by `tools/extract-reactor.mjs`; its states are the app's own state names. |

### Only in the share copy

| claim | status | evidence |
|---|---|---|
| Learns from your own words, with Forget and "Erase the words" | today (on by default) | `backend/jarvis_auto_learn.py:198-205`; `jarvis-desktop/src/brain.js` Forget / Erase the words. |
| Web search sends only the search words out | today | `jarvis-desktop/src/web-search.js:61`. |
| The phone connects only on your own networks | today | `jarvis-client/.../data/OwnNetwork.kt:5-30` (the owner allowed this item in the post text only). |
| Ready for a second graphics card: longer conversations, pictures, one bigger model | ready | `backend/jarvis_second_card.py`; off until a second card is found and the owner approves. |

## Left out on purpose

- **Any number that looks measured** (speed, tokens per second, graphics-card
  memory, temperature, context size). None has been measured on the owner's
  PC. v4 showed the test stand-in's sample gauges (`6.1/8.0 GB · GPU 71% ·
  62°`) with no label; that was a mistake, not repeated here.
- **The lighter approval rules** (repeating reminders without a card, the
  lights setting, the Standby schedule): they work against "asks first", and
  the lights count as smart home, which the owner does not advertise.
- **"Never leaves your PC", "instant", "reasons", "sees pictures", "answers
  only your voice", "autonomous", "sir", "J.A.R.V.I.S."**: false or banned.
  Thinking mode is off; pictures need the second card.
- **Memory and the second card as scenes:** true, but cut for time; they are
  in the share copy.

## Honest limits of the picture

- **The desktop screens are real.** They are the app's own HTML, CSS and
  JavaScript, rendered headless with made-up data, cropped. No gauges and
  nothing reading "J.A.R.V.I.S." are in any crop.
- **The phone is drawn**, because the Android app cannot be rendered here.
  Every word on it is the app's own (cited above). No sizes, speeds or badges
  are drawn, because they come from data the example does not have.
- **The answer and the question are examples.** Nothing here was run on the
  owner's PC.
