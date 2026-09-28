# Clean-room specs

Each file here describes one good idea from a project whose licence Jarvis
cannot copy code from (GPL, AGPL, closed-source apps and the like), in
plain words and with no code in it.

How it works:

1. The `clean-room-spec-writer` agent reads the original project and writes
   the spec here: what it does, how it should behave, how it fits Jarvis,
   and tests the new version must pass. Its first section says exactly what
   was read, and when.
2. A different agent builds Jarvis's own version **from the spec alone**,
   and is told never to open the original project.

Why: copyright protects someone's exact code, not the idea of what it does.
Keeping the reader and the builder apart means none of the original code
can slip into Jarvis, even by accident. This is a careful habit, not legal
advice.

Before a spec is written, the agent checks a simpler route: can the program
just run beside Jarvis, unchanged, as its own program? That is how Jarvis
already uses SearXNG (AGPL-3.0; see `THIRD-PARTY-NOTICES.txt`).
