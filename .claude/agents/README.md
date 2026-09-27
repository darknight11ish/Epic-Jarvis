# The Jarvis studio

A team of helper agents for this repository. Each file here is one agent:
a short job description that Claude Code loads, so any session can say
"use the desktop-playtester" and get the same careful behaviour every time.

You do not need to do anything to use them. In a Claude Code session in this
folder, just ask for one by name, for example:

> Use the desktop-playtester to try the new timers screen.

Or ask for several at once ("run the play testers and the scouts").

## Who is on the team

| Agent | What it does | Changes files? |
|---|---|---|
| `desktop-playtester` | Uses the Windows app's real screens in a test browser, as the owner would, and reports what is confusing, broken or slow | No (screenshots go to the scratchpad) |
| `phone-playtester` | Walks the Android app screen by screen through its code and CI's screenshots, as the owner would on the phone | No |
| `newcomer-playtester` | Plays a first-time user: install, pair the phone, first chat, first voice command. Finds where a new person gets stuck | No |
| `voice-playtester` | Walks every voice path (talk button, "Hey Jarvis", interruptions, read-aloud) for timing and trust problems | No |
| `competitor-scout` | Searches the web for closed-source assistants (ChatGPT, Gemini, Alexa+, Siri, Copilot, Muse...) and what they shipped lately | No |
| `open-source-scout` | Reads GitHub projects (OpenClaw, Hermes, Home Assistant, Open WebUI...) for ideas Jarvis can safely borrow | No |
| `integration-scout` | Looks on GitHub for code Jarvis can actually use (a library, a model, a module to adapt) in one area, checking the licence, whether it runs on Windows/Android, and privacy | No |
| `clean-room-spec-writer` | For a good idea whose licence Jarvis cannot copy from (GPL, AGPL, closed apps): first checks if it can simply run as a separate program; if not, writes a plain-words spec with no code in it, for a different agent to build from | No (hands the spec back; the main session saves it) |
| `rules-guardian` | Checks any idea or change against the five non-negotiable rules and the owner's decisions in `CLAUDE.md` | No |
| `feature-auditor` | The owner's standing three-part audit for every new feature: bugs, both apps, fit | No |
| `bug-hunter` | Finds real bugs, each one checked against the source before it is reported | No |
| `plain-words-editor` | Checks on-screen wording and write-ups for jargon, vagueness and blame | No |
| `ci-reader` | Reads GitHub Actions results (the only Android compiler) and says in plain words what failed and why | No |

None of them changes files: helper agents hand their report back as text. They report; the main session (or you) decides what
to fix. That keeps one place responsible for every change.

## House rules every agent follows

- Read `CLAUDE.md` first. It overrides anything in these files.
- Verify against the actual file before stating anything about it. Quote the
  evidence. "I have not checked" beats a confident guess.
- Plain words: the owner is a beginner developer.
- Never propose something that breaks one of the five rules. If a good idea
  needs a rule bent, say so plainly and leave the call to the owner.
- Earlier research lives in `docs/`. Build on it; do not redo it.

## Ideas from projects Jarvis cannot copy from

Copyright protects someone's exact code, not the idea of what it does. So a
good idea from a GPL/AGPL project, or from a closed app like ChatGPT, can
still come to Jarvis, in one of two ways:

1. **Run it beside Jarvis, unchanged**, as its own program (how Jarvis
   already uses SearXNG). Its licence then stays with it.
2. **Clean room.** The `clean-room-spec-writer` reads the original and
   writes down only what it does, with no code, in `docs/clean-room/`. A
   *different* agent, told never to open the original, builds Jarvis's own
   version from that spec.

Never: copying its code, prompts or long text; decompiling a closed app;
using model weights under a licence that forbids it. This is a careful
habit, not legal advice.
