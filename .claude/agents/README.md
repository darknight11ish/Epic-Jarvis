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
| `rules-guardian` | Checks any idea or change against the five non-negotiable rules and the owner's decisions in `CLAUDE.md` | No |
| `feature-auditor` | The owner's standing three-part audit for every new feature: bugs, both apps, fit | No |
| `bug-hunter` | Finds real bugs, each one checked against the source before it is reported | No |
| `plain-words-editor` | Checks on-screen wording and write-ups for jargon, vagueness and blame | No |
| `ci-reader` | Reads GitHub Actions results (the only Android compiler) and says in plain words what failed and why | No |

None of them changes code. They report; the main session (or you) decides what
to fix. That keeps one place responsible for every change.

## House rules every agent follows

- Read `CLAUDE.md` first. It overrides anything in these files.
- Verify against the actual file before stating anything about it. Quote the
  evidence. "I have not checked" beats a confident guess.
- Plain words: the owner is a beginner developer.
- Never propose something that breaks one of the five rules. If a good idea
  needs a rule bent, say so plainly and leave the call to the owner.
- Earlier research lives in `docs/`. Build on it; do not redo it.
