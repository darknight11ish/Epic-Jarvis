# Gemini Live compared with Jarvis Live (studio scout, 2026-09-28)

Written by the studio's competitor scout for the owner's request "make sure
Jarvis Live is built well ... compare it to Gemini Live". Jarvis Live is
designed in `docs/LIVE-DESIGN.md`.

**How reliable this is.** The network proxy blocked every Google page and
every tech-news site, so every fact about Gemini comes from a search-engine
summary of the linked page, not the page itself (the one GitHub page was
read directly). Anything only one secondary site says is marked
**(unverified)**. Claims about Jarvis were checked in the repo files named.

**Two corrections to the design:**
- The "too short" limit is **2 seconds out of the box**, not 1.5: Very strict
  is the default (`backend/rebuilt/jarvis_voice.py:624` `DEFAULTS`, `:647`
  `MIN_COMMAND_SECONDS`).
- The design did no Gemini research (`LIVE-DESIGN.md:593`); this fills it.

## 1. Side by side

Key: **yes** / **partly** / **no** (could be added) / **no on purpose**.

| Gemini Live | Jarvis Live design |
|---|---|
| Start with a button, overlay, or "Hey Google, let's talk Live" | **Yes** - Live button, tray, Alt+Shift+L, "Hey Jarvis, let's talk" |
| End with a button; no app time limit found (15 min / 2 min limits are the developer API only) | **Yes, stricter** - 30 min default, 2 h max, ends after 90 s quiet |
| Interrupt by talking, with a setting to interrupt by tap only | **Partly** - barge-in always on; no tap-only switch |
| Mute button (mic closed, answer still heard), also in the notification (Dec 2025) | **No** |
| Push-to-talk inside Live (leak, July 2026, unverified) | **Partly** - talk button exists outside Live |
| Waits through pauses (fixed March 2026) | **Yes** - Smart Turn waits up to 2 s (`jarvis_speech.py:1048-1049`) |
| Captions | **Yes** |
| Floating bubble over other apps (April 2026) | **Partly** - notification on the phone, badge on the PC |
| Keeps going with the screen locked; camera needs unlock | **Yes** - camera never on the lock screen; App lock ends Live |
| "You are live" signs | **Yes** |
| Dozens of languages, switching mid-chat | **No** - English only (Parakeet v2, Kokoro); a model limit, not a rule |
| ~10-12 voices; some removed in May 2026 | **Yes** - 11 Kokoro voices, custom voices |
| "Speak faster / slower" by voice | **Partly** - a speed setting exists (`lib.rs:966`), no spoken command |
| Senses tone (March 2026) | **No** |
| Filters background noise | **Partly, stronger on voices** - other voices refused by the voice check |
| Very short replies ("yes") | **No on purpose** - the voice check needs 2 s by default |
| Live camera video on all phones (May 2025) | **Partly / no on purpose** - one picture per question, 12 GB card only |
| Screen sharing in Live | **Partly** - "Watch with me" on the PC |
| Draws boxes on the camera view (Aug 2025) | **No** - possible later on two cards |
| Type and talk in one chat; reopen a Live chat | **No** - not specified |
| Remembers past chats (June 2026) | **Yes** - Jarvis memory |
| Calendar, Tasks, Keep, Maps | **Partly** - calendar read-only by choice; to-dos and notes yes; no Maps; calendar answers stay on screen |
| Gmail by voice, Daily Brief, Spark agent (Aug 2026, paid) | **Partly** - email and briefing answers stay on screen; inbox tidy decided; **Spark no on purpose (rule 1)** |
| Home, YouTube, Spotify, travel, shopping, images (May 2026) | **Partly** - Home Assistant, PC media, web search yes |
| Timers in Live (sources conflict) | **Yes, better** - answered without the model |
| Calls and texts from the lock screen | **No on purpose** - no SMS, no phone service |
| Watch and car | **No on purpose** - need Google services |
| Desktop: Chrome (2025), Windows app (Sep 2026, reportedly without screen awareness, unverified) | **Yes** - native on the PC with "Watch with me" |
| Transcripts, audio, camera and screen kept in Google's cloud; human review up to 3 years | **Better** - only words, encrypted on the PC; no audio or pictures kept |
| One tap to confirm actions, then undo | **Yes** - cards by tapping only |
| Usage limits by plan, numbers unpublished | **Better** - no limits, no plans |
| Talking face for businesses (Sep 2026) | **Yes** - faces and animals with lip-sync (mascot branch) |

## 2. The gaps that matter most, ranked (all 0 GB, either card, unless said)

1. **"It's on your screen" mid-conversation** for calendar, briefing, email
   and notes answers (`JARVIS-API.md:2240`, `:4591-4595`). Suggestion: a
   **"Read it"** button beside that answer that reads that one answer aloud,
   like a talk-button turn; App lock unlocked first; sensitive facts still
   excluded. Small change; **owner's call** (loosens a decision).
2. **Short replies are refused.** Suggestion: **tap chips** ("Yes", "No", or
   the options Jarvis named) when a spoken answer ends in a question; a tap
   counts as typed words; never on an approval card. Small, inside the rules.
3. **Every turn feels slow (2-4 s).** Suggestion: a visible "Heard you -
   thinking" state the moment a clip passes the voice check; offer the "I
   heard you" sound for Live once (it stays off by default); keep the model
   loaded; with two cards, a voice on the 2060. Small / medium.
4. **No mute, no tap-only interrupting.** Suggestion: a **Mute** button (mic
   closed, session continues, sign says "Muted") and a Live setting
   "Interrupt by voice / by tap only"; optionally hold-to-talk in Live.
   Small; also a privacy win.
5. **Cannot type in Live or reopen a Live chat.** Suggestion: a text box on
   the Live screen and Jarvis bar; "Continue in Live" in History. Small.
6. **"Speak faster / slower" by voice.** Suggestion: a `jarvis_quick.py`
   command, a "From now on..." change with Undo. Small.
7. **The 90-second quiet timeout may end Live mid-task.** Suggestion: a
   choice of 90 s / 5 min / 15 min, 2 h ceiling kept. Small; **owner's call**
   (a longer open microphone).
8. **"Start Live about this"** from the share sheet or a document, marked
   outside text. Small.
9. **Pointing at things on the camera picture** (boxes on the frozen
   picture, never on a face). Two cards, medium; accuracy unmeasured.

Not ranked: other languages (Parakeet v3 is researched), only if the owner
wants it.

## 3. What Gemini Live users complain about

- **Cuts you off when you pause** (Google community thread; fixed March
  2026). Keep Smart Turn's 2 s wait; measure it in Live step 5.
- **Noise and echo set it off**, which led to the mute button. See gap 4.
- **Fast but wrong** (Engadget). Never skip a web search to save time.
- **Not dependable** (Android Authority, Nov 2025).
- **Stops mid-sentence** on the developer API (GitHub python-genai #2117,
  27 Feb 2026, read directly), worse after tool calls. Add a Live test that
  a long answer after a tool call is spoken to the end.
- **Voices removed** (May 2026). Never remove a voice the owner chose.
- **Voice quality worse after an update** (March 2026). Keep the voice
  bake-off rule.
- **Blurry camera** for a month. Test for blur in the photo test.
- **Paid tiers with unpublished limits.**
- **Privacy**: camera and screen may be reviewed by people for up to 3 years.
- **Warmth matters as much as speed** (Android Police).

**Do not copy:** a camera that streams video all the time; talk-and-listen-
at-once voice models (they skip the voice check and cards); Spark-style
24/7 cloud agents (rule 1); calls, texts or device control from a locked
phone; confirming by voice; a photo-real avatar or "a real person's accent";
removing voices; paywalls; cloud transcripts; human review.

## 4. Better and worse, honestly

**Better:** only the owner's voice counts; nothing leaves the owner's
devices and no audio or picture is kept; the PC works offline; no limits or
tiers; timers and "stop" work without the model; trust settings the owner
can see and change; cards show the exact action; a clear start, end and
time limit; a lip-synced face for everyone.

**Worse:** slower (2-4 s against about 1-3 s); English only; short replies
refused; no camera on one card, and one picture per question rather than
video on two; a much smaller model (8B) for hard questions; no Maps,
travel or shopping; private answers stay on screen by default.

## 5. Speed

- Gemini 3.8 Live, developer version: about **1.18 s** to first sound
  (Artificial Analysis, Sep 2026, one source, unverified); 3.1 Flash Live
  about 2.99 s. The phone app may differ.
- Jarvis Live's design: about **2-3.5 s on the PC, 2.3-4 s on the phone,
  3.5-7 s with the camera** - estimates, nothing measured on the owner's PC.
- What it will feel like: Gemini now feels like "a person thinking briefly";
  Jarvis will feel like someone pausing before each reply - fine for
  "what's the weather", noticeable in quick back-and-forth.
- What helps most without full-duplex: an instant "heard you" cue; a faster
  first sound (on two cards, a voice on the 2060); keeping the model
  loaded; starting checks early; and measuring on the PC first
  (`jarvis_voice_flow.py --measure`, design step 5) before promising any
  number.

## Sources (via search summaries unless noted)

9to5Google (26 Mar 2026 Gemini 3.1 Flash Live; 15 Sep 2026 Gemini 3.8 Live;
26 Aug 2026 productivity; 18 Jun 2026 memory; 23 May 2026 connected apps;
7 and 19 Apr 2026 redesign; 27 May 2026 voices; 12 Dec 2025 mute; 12 Nov
2025 speed and accents; 30 May 2025 camera; 9 Aug 2025 apps; 20 May 2025
Chrome; 4 Jul 2026 plans; 6 Aug 2026 Wear OS) - Android Authority (visual
guidance; push-to-talk; vs ChatGPT, 4 Nov 2025) - AndroidHeadlines (July
2026 leak) - Android Police - PiunikaWeb (20 Mar 2026) - PhoneArena -
Engadget - Artificial Analysis and @GeminiApp on X - GitHub
googleapis/python-genai #2117 (read directly) - Google developer forum
(audio regression; latency) - Google AI docs (Live API sessions) - Gemini
help pages (Live, lock screen, utilities, Privacy Hub) - Google community
thread - Unite.AI - Quasa - Google Cloud blog (Live Avatar) - Pondero -
Android Central - androidayuda - Yahoo Tech. Full URLs are in the scout's
report in this session's history.
