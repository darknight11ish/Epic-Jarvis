# Feasibility audit - the plan (owner's request, 2026-09-26)

Runs once ALL the research is in: the cutting-edge rounds 1-4
(`docs/CUTTING-EDGE-2026-09-26-*.md`), the memory research
(`docs/MEMORY-RESEARCH-2026-09-26.md`) and anything they point back to
(`docs/CREATIVITY-AUDIT-2026-09-25.md`, `docs/COMPETITORS-*.md`).

The owner asked for "a feasibility audit with a team of agents that discuss
how this would impact Jarvis, if it's possible to get these new features
working well, if they mesh well with the current Jarvis (and don't overwhelm
severely, or ways so these don't) and more" - and **"be sure the feasibility
audit also looks at security around these new potential features."**

## The team

Each reviewer reads every idea from its own side, then the reviewers answer
each other's objections before anything is ranked.

| Reviewer | The question they answer |
|---|---|
| **Fit** | Does it plug into how Jarvis is built, or fight it? What does it depend on, and what must come first? |
| **Hardware and speed** | Does it fit the graphics cards' memory next to everything else (8 GB now, the 12 GB card later)? What does it cost in answer time and phone battery? |
| **Rules** | Can it keep all five rules, the one-card-per-action model, the owner's dated decisions in `CLAUDE.md`, and the owner-only-words rule for memory? |
| **Security** | A threat model for EACH feature: what new way out of the PC it opens; what new outside text it lets in (and whether that text could steer Jarvis - prompt injection); what secrets or keys it touches and where they are kept; what new attack surface it adds (ports, background listeners, file watchers, notification access, plug-in servers like MCP); the supply chain of every new model, library or download (licence, who publishes it, pinned versions, checksums, telemetry); what an attacker already on the PC or on the home network could do with it; what happens if it fails - does it fail closed? Plus the smallest set of guardrails that makes it safe, or "not safe enough - do not build". |
| **Overwhelm** | Too many settings, cards, notifications or screens? How to keep Jarvis simple (off by default, advanced options tucked away, one place for each thing, the same words everywhere). |
| **Upkeep** | Tests it needs, burden on CI (the phone compiles only in CI), docs, how it is kept working over time. |
| **Devil's advocate** | Argues against every idea, to catch hype and "nice but not worth it". |

## What comes out

- One line per idea: **build / build later / don't build**, with the reason,
  and for every "build", its security guardrails.
- A build order that respects dependencies and the second-card timing.
- A short "keep Jarvis simple" guardrail list for the whole set.
- Decisions go to the owner two questions at a time.

Every claim about Jarvis's code is checked against the file before it is
reported, as everywhere in this project.
