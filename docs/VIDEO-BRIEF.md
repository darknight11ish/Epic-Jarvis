# Brief for a /brag launch video about Jarvis

Paste everything below the line into the conversation that runs `/brag`.
Best run from inside a clone of the Epic-Jarvis repository, so /brag can read
the real desktop windows (`jarvis-desktop/src/`) and phone screens
(`jarvis-client/`) for its "show the thing" scene.

Updated 2026-09-24. This version replaces the first brief: it adds what was
built since, and it separates what works **today** from what is **being
built right now**, what is **built and waiting for hardware**, and what is
**planned**.

---

Make a /brag launch video for my project **Jarvis**: a private, local-first
personal assistant that runs on my own PC, with a Windows desktop app and an
Android phone app. Use only the facts below. Do not add features, numbers or
comparisons that are not here, and keep each feature in the group it is
listed in.

Suggested invocation: `/brag --tone cinematic --format landscape`
(or `--tone polished` if cinematic feels too much). Voiceover optional:
`--voice`.

## The one-line pitch
Your own Jarvis: a voice assistant that lives on your PC, answers only to
your voice, and never sends your private life to anyone else's cloud.

## The hook (pick one)
- "Hey Jarvis." Nothing leaves the room.
- An AI assistant that asks before it acts. Every time.
- Your assistant. Your PC. Your rules.

## What makes it different (the story)
1. **Private by design.** The AI model runs on the owner's own graphics card.
   Email, files, passwords and memory never go to a cloud AI. Jarvis never
   sends a question to a cloud AI by itself: at most it offers, and nothing
   private is ever offered.
2. **It asks first.** Anything with real-world effects - a smart-home lock,
   a command on the PC, controlling the PC or phone, installing a model,
   turning on background learning - shows an approval card on the phone or
   desktop. One card, one decision. Nothing is ever approved automatically,
   voice can never approve anything, and it refuses to act if its live
   connection to the PC goes stale.
3. **It learns you, with permission.** Jarvis proposes facts it has learned
   about you, and remembers only the ones you accept.

## Works today - choose the 2-3 highlights from here
Strong candidates for the video are marked with a star.

- ★ **Voice:** say "Hey Jarvis" on the phone or PC and talk naturally. It
  knows when you have finished a sentence rather than just paused. Say
  "stop" (or "Hey Jarvis") to cut it off mid-sentence. It checks that the
  voice is the owner's before it listens to the words, and speech is
  understood on the PC, not in a cloud.
- ★ **Animated faces:** a living face on the desktop widget and the phone,
  with many styles and colour themes, reacting as it listens and speaks.
- ★ **Approval cards:** swipe or tap to approve or deny on the phone, with a
  countdown; risky ones need the owner's fingerprint. Saying no is always
  one tap.
- **The phone and the PC match:** the same features in both apps, connected
  privately over a mesh network (Tailscale or NordVPN Meshnet). It never
  opens anything to the public internet.
- **Notes from anywhere:** type `#obs` (or `#log`, `#joplin`) in chat on the
  phone or PC and it files straight into today's note in Obsidian, Logseq or
  Joplin. It can also search your own notes.
- **Watches:** ask Jarvis to keep an eye on something and it reports what it
  noticed, on both apps.
- **See what it is doing:** a live list of each step Jarvis takes, on the PC
  and the phone.
- **Memory you can see:** a "Brain" window (and the phone's "Mind" screen)
  shows what it knows and how much, with an "as of" view of what it believed
  on any past date.
- **Smart home:** reads and controls Home Assistant devices, asking first
  for locks, alarms and garage doors.
- **Runs your PC, with permission:** can operate apps, read files and run
  commands, each behind an approval card.
- **Standby:** one tap frees the graphics card(s); Jarvis wakes when needed.

## Being built right now - say "coming soon", never "does"
- **Custom voices:** give Jarvis a voice of your choice from a short
  recording (about 5 seconds of someone reading a sentence). It will refuse
  to copy the owner's own voice, so it can never be mistaken for them.
- **Even stricter "only my voice":** a "very strict" setting with longer
  voice training, and private answers (email, calendar, notes) shown on
  screen rather than read aloud unless you choose otherwise.
- **Interrupt by just talking:** cut Jarvis off simply by speaking - your
  voice only, not the TV.
- **A fingerprint / Windows Hello lock** on both apps, with a choice of how
  much needs a fingerprint.
- **Update notices that ask:** both apps say when a new version exists; the
  desktop installs one only when you press the button.

## Built and switched off, waiting for hardware - say "ready for", never "does"
- A **second graphics card** mode (planned: an RTX 2060 12 GB): longer
  conversations, reading pictures (send or share a photo from the phone),
  background learning, browser control, a higher-quality voice, and a
  **wiki builder** that turns documents you drop into a folder into linked
  pages in your Obsidian vault. It turns on only when the card is detected,
  and each part asks first.
- A **"big model" mode**: a very large model streamed from the SSD, for
  **"deep questions"** - ask something hard, put the phone away, and read a
  better answer later.

## Planned - only if you show a roadmap, labelled "next"
Works on any 8 GB graphics card and up to two cards, detecting the PC's
hardware and recommending settings; advice on when a task needs a bigger
model; more devices (a second phone, a laptop) driven by the main PC; a
short guided setup the first time you open either app; clicking through
apps with the real mouse (every step shown and approved first); reminders
and timers, a morning briefing, calendar and email actions (always with
approval), web search and weather, voice memos into notes, "ask my
documents", a quick text helper, tidying files, and a sleep schedule.

## Hard rules for the video
- **Do not claim speeds, benchmark scores or accuracy numbers.** None have
  been measured on the owner's hardware yet.
- **Do not compare it to Gemini, Siri, Alexa or ChatGPT by name.**
- **Do not say it is on the Play Store:** it is a personal, non-commercial
  build, installed directly on the phone.
- **Keep each feature in its group.** "Being built", "waiting for hardware"
  and "planned" features must never be shown as working today.
- **No personal details on screen:** no device names, usernames, network
  addresses, tokens, keys or real email content. If a screen needs sample
  data, make it obviously fake ("Dentist, Tuesday 10:00").
- **Voice cloning is shown as consent-based:** a person reading a sentence
  for their own voice, never "copy anyone's voice".

## Visual feel
Dark, precise, a little cinematic: the "reactor" face glowing on a dark
background, approval cards sliding in, a fingerprint confirming a risky
yes, a phone and a desktop side by side showing the same thing. Calm
confidence rather than hype. The line to land on at the end:
**"Your assistant. Your PC. Your rules."**
