# Prompt to continue this work in a fresh conversation

Copy everything between the lines into the new conversation.

---

Read these three files first, in this order, before doing anything else:

1. `docs/HANDOFF-UI-RESEARCH-2026-10-09.md` — start here; it is the continuation document.
2. `docs/SUMMARY-UI-RESEARCH-2026-10-09.md` — the five-minute plain-language version.
3. `docs/UI-CUTTING-EDGE-2026-10-09.md` — the full research, 18 parts. Read Part 14 (the open PRs and the six self-corrections), Part 15 (flexibility) and Part 17 (Brain) as needed.

Then run `git status` and `git log --oneline -5` and tell me in two lines whether the
repo has moved since 2026-10-09. If it has, re-check the handoff's §3 before trusting any
"still open" claim in the research — nine PRs were open and some findings may since be fixed.

## How I want to be asked things

This matters as much as the work itself.

- **Whenever a decision is mine, give me multiple choice.** Not an open question, and not
  a wall of text with radio buttons buried in it.
- **One or two questions at a time.** Two or three options each. One or two sentences per
  option. Not four options, and not paragraphs.
- **Lead with your recommendation and say it is your recommendation.**
- **Put the long reasoning around the question, or in a file — never inside the options.**
- **Plain words.** I am a beginner developer. Say what a thing is before using its name.
- **When I answer, do the work.** Do not ask me to approve each step.

## Rules that are not up for discussion

Do not propose anything that breaks these, and do not ask me whether to break them:

- **Never auto-approve anything**, and acting stays blocked while the event stream is stale.
- **Nothing private leaves my PC** — email, files, credentials, stored memory.
- **No public tunnel.** No ngrok, no Cloudflare Tunnel, no Tailscale Funnel.
- **A client never does speech-to-text.** The words are worked out on the PC.
- **Non-commercial, sideloaded, never on Play.**
- **No bulk approval, and nothing that clears a rush latch.**
- **Jarvis never sends a text message.** Not in car mode, not for a named contact, not
  ever — auto-send is forbidden and is not built. Read `docs/RULE-FLEXIBILITY.md` entry 002.
- **The eight "must stay fixed" items** in the report's Part 15.5 must not become settings.
  They already have tests that fail the build if they change.

**If a rule ever needs relaxing**, the process is in `docs/RULE-FLEXIBILITY.md`: a written
entry naming the rule and exactly what is kept, an approval card that says in plain words
*which rule* is being relaxed, and a line on the "What asks first" page. An agent may not
decide this — only I can. Read that file before proposing anything that touches a rule.

## What is already decided — do not re-open these

- **Auto-send is forbidden.** My earlier draft recommended auto-reply to named senders;
  I chose otherwise. Jarvis may draft a reply, speak it, and accept a spoken reply, and
  **I** send it.
- **Car mode may read texts aloud**, and that is the only exception to the SMS rule.
  See `docs/CAR-MODE-DESIGN.md`, including its §6 "Questions only the owner can answer".
- **Do not adopt Material 3 Expressive** (it is beta, and it overshoots).
- **Do not swap Acrylic for Mica** — the desktop app already reasons that out.
- **Do not rewrite the desktop frontend in a framework** — it is 11 separate webviews.
- **Four findings from the 2026-10-05 audit are already fixed.** The handoff lists them
  with commit hashes. Do not redo them.

## Ask me these, in this order, one or two at a time

Ask the first one now. Ask the next after I answer, and do the work each answer implies.

**1. What should you build first?**
- **Fix the two widget approval bugs, then make the theme colours one source of truth** *(your recommendation)* — about a day, and nothing else matters if a click can approve the wrong card.
- **Start on Brain: pin Galaxy as DOM/SVG buttons** — a few days, no library, and it turns my "nothing drawn only on the canvas" rule into a fact.
- **Merge the open PRs first** — two of them are the flexibility recipe you would otherwise be copying by hand.

**2. Which Brain view should come first?**
- **The DOM/SVG constellation** *(your recommendation)* — real buttons pinned by kind; keyboard, theming and high contrast all come free.
- **The plain table view** — the only fully accessible surface, and what a screen reader will actually use.
- **The River (timeline)** — the quickest visible win; uses the "true from" dates I already decided to build.

**3. Should Jarvis be able to browse and search my whole message history?**
- **No, leave it** *(your recommendation)* — car mode and drafting already cover reading and replying.
- **Yes, and write the RULE-FLEXIBILITY entry first** — it reverses the SMS rule for reading and needs my decision.

**4. Someone is mid-work in my working tree** — four uncommitted files, including a
settings search box in `SettingsScreen.kt` and `settings.html`. What should you do?
- **Leave those files alone and work around them** *(your recommendation if I have not told you otherwise)* — avoids clobbering work in progress.
- **Take them over and land the search box** — only if I say that work has stopped.

**5. Do you want me to test KDE Connect?** It is the only genuinely private open-source
phone-to-PC text bridge, and its Windows half is built but unproven.
- **Yes, one afternoon over Tailscale** *(your recommendation)* — it would settle whether the desktop can see texts without any new code.
- **Skip it** — leave SMS entirely to car mode and drafting.

## Anything else

If something in the research looks wrong to you, say so and show me the file and line.
The research already corrected itself six times; a seventh is welcome.
