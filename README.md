# Jarvis

A personal assistant that runs on **your own Windows PC**, with a desktop app
and an Android app to talk to it. The AI model runs on the PC's own graphics
card, so your emails, files and memories never go to a company's servers.

Version 0.2.0 ([what changed](CHANGELOG.md)). Made by darknight11ish.
Free and non-commercial: installed by hand, never sold, never on Google Play.

## Launch video

[![Jarvis launch video v5: a day with Jarvis](videos/v5/jarvis-launch-v5.jpg)](videos/v5/jarvis-launch-v5.mp4)

**Tap the picture to watch v5** (34 seconds, sound on; every spoken line is on
screen). It opens the video file, and GitHub plays it in the browser. On a
phone held upright, watch [the 16-second cut](videos/v5/jarvis-launch-v5-vertical.mp4).

One day with Jarvis, from the morning briefing to Standby at night, in one
continuous shot: a focus session, a "Tell me when" alert that rings your phone,
and a memory that learns from your own words. Every screen is the real desktop
app, with made-up examples.

Every version is kept in [`videos/`](videos/), with the plan and the project
needed to make it again: [v1](videos/v1/jarvis-launch-v1.mp4),
[v2](videos/v2/jarvis-launch-v2.mp4), [v3](videos/v3/jarvis-launch-v3.mp4),
[v4](videos/v4/jarvis-launch-v4.mp4).

## The five rules

1. **Private things stay on the PC.** Email, files, passwords and memories
   are only ever handled by the model on your own PC.
2. **No public tunnel.** Jarvis is reachable only over your own networks,
   never opened up to the internet.
3. **Keys are kept like passwords.** An API key is never logged, and is sent
   only to the one service it belongs to.
4. **Nothing is approved for you.** Jarvis asks, you decide - and it will
   not act while the phone's or desktop's link to the PC is out of date.
5. **Non-commercial.** Built for one owner, installed by hand.

## What it can do

**Talk and listen**
- Chat, with answers that appear as they are written.
- Voice: push-to-talk, or say "Hey Jarvis" (on the PC and the phone).
  Spoken questions get short, spoken-style answers; say "stop" to interrupt.
- A choice of manner: warm and brief, or plain.

**Remember**
- Learns facts about you from **your own words only** - never from emails,
  web pages or files - and lists every one, with Forget and "Erase the
  words". Health, money, passwords and other sensitive topics wait for your
  yes.
- Keeps your chat history on the PC, encrypted (you can turn it off).

**Keep time**
- Timers, alarms, reminders and to-do lists, by voice or typing.
- A morning briefing: today's calendar, new emails, what is coming up.
- "What did I miss?" - what went off while you were away.
- **"Tell me when ..."** an email from someone arrives, or the washing
  machine finishes. Urgent ones keep ringing on the phone until you look.
- **Focus sessions** on the PC: a timer, Quiet, and a nudge when a
  distraction comes to the front. Nothing about what you were doing is kept.

**Do things, with your OK**
- Read your email, calendar and notes, and write notes to Obsidian, Logseq
  or Joplin.
- **Send email** - one approval card per email, showing exactly who it goes
  to and every word of it.
- Search the web, with five providers to choose from.
- Control lights and devices through Home Assistant. A setting (off by
  default) lets it switch lights, plugs and fans you name without asking;
  locks, doors and alarms always ask.
- **Stop everything**: Alt+Shift+X on the PC, or the button on the phone.

**Stay in your control**
- Anything that matters waits for your approval, on the PC or the phone.
  There is no "approve all". Risky approvals need Windows Hello on the PC or
  the screen lock on the phone.
- **"What asks first"**: a page in both apps listing every action and
  whether it asks you, with switches to make it stricter.
- **Your own networks only**: the apps connect to Jarvis only on this PC,
  your home network, Tailscale or NordVPN Meshnet. Anything else is refused.
- A live check of the whole setup: `python backend\selftest.py --preflight`.

**Look how you like**
- An animated face shows what Jarvis is doing (20 designs), with themes and
  colours that match on the PC and the phone.

## Install it

Follow [`docs/INSTALL.md`](docs/INSTALL.md), in order. It has three parts:

1. **The backend on the PC** - the Python program that does the work, plus
   the model in Ollama. One script, `scripts/apply-patches.ps1`, puts this
   repository's changes into it (INSTALL.md part 1 has the exact command).
2. **The desktop app** - for now you build it yourself on the PC
   (INSTALL.md part 2). A ready-made installer will appear under
   [Releases](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/desktop-latest)
   once the updater's signing key is set up
   ([`jarvis-desktop/README.md`](jarvis-desktop/README.md), "Turning on
   updates").
3. **The phone app** - download the `.apk` from the
   [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest)
   and open it on the phone, or run `adb install -r <file>.apk` from the PC.
   Then pair it with the PC (INSTALL.md part 3).

Install only `jarvis-client`, from that release. The `jarvis-android` folder
is an older app kept for reference: it speaks a connection method the
backend never had, so it cannot talk to Jarvis at all. It no longer
publishes a download, so the two cannot be mixed up - installing the wrong
one would look like "my phone is broken" rather than "wrong app".

## Where things are

| Folder | What is in it |
|---|---|
| `jarvis-desktop/` | The Windows app (Tauri). Rust in `src-tauri/`, the windows in `src/`. |
| `jarvis-client/` | The Android app. |
| `backend/` | Changes (patches) for the backend on the PC, the modules it needs, and a test for each. The backend itself lives on the PC, not here. |
| `docs/` | How it all works. [`docs/README.md`](docs/README.md) says which documents are current. |
| `scripts/`, `tools/` | The patch script, and tools that generate test data and notices. |
| `keystore/` | How the phone app's signing key is restored on GitHub's build machines. The key itself is never committed. |
| `jarvis-android/` | The older phone app, kept as source only. |
| `server/` | An old server, not used by Jarvis (its README says so). |

The documents to read first: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
(how the pieces fit, and the rules), [`docs/INSTALL.md`](docs/INSTALL.md),
[`docs/JARVIS-API.md`](docs/JARVIS-API.md) (what the apps ask the PC), and
[`backend/README.md`](backend/README.md) (what each backend change fixes).

## How it is built

- **Phone app:** GitHub builds it. A build is published to `client-latest`
  only after an Android emulator has installed and started that exact file,
  and only from `main` or the working branch - the release notes say which.
- **Desktop app:** built on Windows with `npm install` and `npm run tauri build`
  in `jarvis-desktop/`; GitHub also builds the installer.
- **Every change** runs the tests on GitHub: the backend suites, every
  desktop page test, the Rust checks, and PowerShell 5.1 running the patch
  script.

## Licence

Jarvis is MIT-licensed ([`LICENSE`](LICENSE)). It is built with parts made by
other people that keep their own licences, including wake-word models that
are for non-commercial use only: see
[`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt), and in the phone app,
FAQ -> About -> Third-party notices.
