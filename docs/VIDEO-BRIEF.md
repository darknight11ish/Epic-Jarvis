# Brief for a /brag launch video about Jarvis

Paste everything below the line into the conversation that runs `/brag`.
Best run from inside a clone of the Epic-Jarvis repository, so /brag can read
the real desktop windows (`jarvis-desktop/src/`) and phone screens
(`jarvis-client/`) for its "show the thing" scene.

---

Make a /brag launch video for my project **Jarvis**: a private, local-first
personal assistant that runs on my own PC, with a Windows desktop app and an
Android phone app. Use the facts below. Do not add features, numbers or
comparisons that are not here.

Suggested invocation: `/brag --tone cinematic --format landscape`
(or `--tone polished` if cinematic feels too much). Voiceover optional:
`--voice`.

## The one-line pitch
Your own Jarvis: a voice assistant that lives on your PC, answers to "Hey
Jarvis", and never sends your private life to anyone else's cloud.

## The hook (pick one)
- "Hey Jarvis." Nothing leaves the room.
- An AI assistant that asks before it acts. Every time.
- Your assistant. Your PC. Your rules.

## What makes it different (the story)
1. **Private by design.** The AI model runs on the owner's own graphics card
   (an RTX 2080 Super, via Ollama). Email, files, credentials and memory
   never go to a cloud model.
2. **It asks first.** Anything with outside effects (a smart-home lock, a
   shell command, controlling the PC or phone, installing a model) shows an
   approval card on the phone or desktop. One card, one decision. Nothing is
   ever approved automatically, and it refuses to act if its live connection
   to the PC goes stale.
3. **It learns you, with permission.** Jarvis proposes facts it has learned
   about you, and remembers only the ones you accept.

## Features to choose the 2-3 highlights from
Pick the most visual. Strong candidates are marked with a star.

- ★ **Voice:** say "Hey Jarvis" on the phone or PC, talk naturally, and
  interrupt it mid-sentence by saying "stop". It learns the owner's voice
  and checks that it is them speaking. Speech is understood on the PC, not
  in the cloud.
- ★ **Animated faces:** a living, animated face on the desktop widget and
  the phone, with several styles and colour themes, reacting when it
  listens and speaks.
- ★ **Approval cards:** swipe or tap to approve or deny on the phone; a
  countdown shows how long a card has left.
- **Notes:** type `#obs` to save straight into today's Obsidian daily note
  (also Logseq and Joplin), and search your own notes.
- **Smart home:** reads and controls Home Assistant devices (it asks first
  for locks, alarms and garage doors).
- **Runs your PC:** can operate apps, read files and run commands, each with
  an approval card.
- **Phone and desktop in sync:** the same features in both apps, connected
  privately over a mesh network (Tailscale or NordVPN Meshnet). It never
  opens anything to the public internet.
- **Memory you can see:** a "Brain" window shows what it knows, with an "as
  of" view of what it believed on any past date.
- **Wiki builder:** drop a document into a folder and Jarvis writes linked
  wiki pages into your Obsidian vault after one approval, keeping the old
  copy of every page it changes.

## Built and switched off, waiting for hardware (say "coming" or "ready for", not "does")
- A **second graphics card** mode, planned for an RTX 2060 12 GB: longer
  conversations, reading pictures (send a photo from the phone), background
  learning and browser control. It turns on only when the card is detected.
- A **"big model" mode** using a very large model streamed from SSD, for
  **"deep questions"**: ask something hard, put the phone away, and read a
  better answer later.

## Planned (only if you mention the roadmap; label it "next")
Reminders and timers, a morning briefing, calendar and email actions (always
with approval), web search and weather, voice memos into notes, "ask my
documents", a quick text helper, and tidying files.

## Hard rules for the video
- **Do not claim speeds, benchmark scores or accuracy numbers.** None have
  been measured on real hardware yet.
- **Do not compare it to Gemini, Siri or ChatGPT by name.**
- **Do not say it's on the Play Store:** it's a personal, non-commercial
  build, installed directly on the phone.
- Features in "switched off, waiting for hardware" and "Planned" must never
  be shown as working today.
- **No personal details on screen:** no device names, usernames, network
  addresses, tokens or real email content. If a screen needs sample data,
  make it obviously fake ("Dentist, Tuesday 10:00").

## Visual feel
Dark, precise, a little cinematic: the "reactor" face glowing on a dark
background, approval cards sliding in, a phone and a desktop side by side.
Calm confidence rather than hype. The line to land on at the end:
**"Your assistant. Your PC. Your rules."**
