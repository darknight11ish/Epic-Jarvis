# The studio review: testing Jarvis and making it better (27-28 September 2026)

**In one paragraph:** a team of helper agents (the "studio",
`.claude/agents/`) play-tested the desktop and phone apps, a first-time
setup and every voice path; scouted closed-source and open-source
assistants; looked on GitHub for code Jarvis can actually use; and checked
every idea against the five rules. Twelve confirmed bugs are fixed and
pushed. The owner answered sixteen decisions (all recorded in `CLAUDE.md`).
**Next up, by the owner's choice: the chatbot driver** - Jarvis holding a
conversation with Gemini (and later others) on its own, within limits,
with a limited one-card version and a full two-card version.

The agents' own notes (condensed, with file and line references) are in
`docs/studio-2026-09-27/`. Read those before re-researching anything.

---

## 1. What "testing" could and could not mean

| Part | How it was tested | What that proves | What it does not |
|---|---|---|---|
| Windows desktop app | Its real screens in a test browser, with a fake backend giving realistic answers (`jarvis-desktop/tests/uikit.mjs`) | What you see, click and read | That the app starts on Windows, the Rust side, or the real backend |
| Rust (desktop) | `cargo fmt`, `check`, `clippy` against the Windows target | It compiles, lints clean | `cargo test` needs Windows (CI runs it) |
| Android app | Code walk-through, tap by tap; GitHub's emulator (45 tests, the signed app starts and stays up) | The logic; that it builds and launches | Anything on a real phone screen - no emulator here |
| Backend | Its tests run here (voice, tell-me-when, wake word...) | The patched modules behave | The owner's own backend files, which are not in this repo |
| Whole chain | **Nowhere.** | - | No test pairs the phone with a real backend and model. The owner's PC is the only place that happens. |

---

## 2. Fixed and pushed (all verified in the code first, each with a test)

| Fix | Where |
|---|---|
| The pairing key could not be typed as the PC shows it (the spaces) | phone `PairingKey.kt`, PC Settings hint |
| "Tell me when this page changes" alerted when nothing visible changed | `backend/jarvis_tellme.py` |
| "Start with Windows" said on when Task Manager had it off | `autostart.rs` |
| The patch script sent people looking for "OpenJarvis" | `apply-patches.ps1` |
| Forget's date box saved "Sept 20" as 2001, accepted the future, dropped a confirmed Forget | desktop `brain.js`, `valid-to.js` |
| "Use" offered on a memory-search model that cannot chat | desktop Brain (**phone still has it**, see §5) |
| Raw `_underscores_` in answers | desktop `markdown.js` |
| Putting one of two approval cards aside hid both | desktop `main.js` |
| Erase's second question, and two wording slips | desktop, backend |
| "Open help" / "connection" / "briefing" opened the phone's Settings at the top | phone |
| "Not connected" shown while only catching up; no Retry; no reconnect on return | phone |
| The "Brief me now" / "What did I miss?" shortcuts did nothing useful | phone |
| "answered on this PC" on the phone | phone |
| The owner's own Meshnet machine name used as an example (docs, Settings help, tests) - now `my-pc.nord` (owner's OK, 2026-09-28) | docs, desktop, phone tests |
| Answers from web search and home status never read aloud (owner's decision) | both apps, one shared table of 58 cases |
| One "Hey Jarvis" heard by phone and PC answered twice (a timer could be set twice) | backend, PC only |

Kotlin in these fixes is compiled only by GitHub's build; the CI reader
checks each push.

---

## 3. The owner's decisions (27-28 September) - full wording in `CLAUDE.md`

1. Talk-to-type on the PC: one card to switch it on.
2. Web search, weather and home status answers are read aloud.
3. **The chatbot driver:** Gemini first, **through its website**
   (~~driven openly, no hiding from bot detection, ban-avoidance tactics
   declined~~ - **reversed by the owner on 2026-09-29**, see `CLAUDE.md`
   "Stealth on for everything"), with **a spare Google account** used only by
   Jarvis; **versatile** (an adapter per chatbot, more later, each with the
   owner's OK); **one-card limited and two-card full versions**;
   **built first**.
4. Jarvis is built for one or two graphics cards; every agent plans for both.
5. Inbox tidy by voice: yes, one card listing every email, then Undo; Trash only.
6. The phone stays on Tailscale/Meshnet (replaces "allow home addresses").
7. A "listening" sound after a bare "Hey Jarvis": only with "I heard you" on.
8. Animal faces offer their voice once (the built switch starts off); the
   otter drops the "Sky" voice.
9. Upgrade to Kokoro v1.0 with "Hear it" samples.
10. Injection detector: test Meta's and an Apache one; keep the winner.
11. A crisis answer's thumbs-down stops counting toward "suggest the bigger model".
12. Phone: tap to talk, stopping at a pause.

---

## 4. The build queue (in this order)

**1. The chatbot driver** (owner's pick; `docs/CHATBOT-DRIVER-DESIGN.md`).
Step 1, the core (limits, the privacy check before every message, the
clean context, one-card/two-card tiers, tested against a fake chatbot) is
being built now. Then: the Gemini website adapter (Playwright on the PC, a
browser profile used only for this, stops at any captcha or login check),
the routes and both apps' screens, and the new-feature audit.

**2. Easier setup** - the biggest reason nobody but the owner could install
Jarvis, and it costs the owner hours (`studio-2026-09-27/newcomer-playtest.md`):
QR pairing (code found: `qrcode` crate on the PC, ZXing + CameraX on the
phone, both licence-clean); the desktop installer (the owner makes the
update signing key once - about 10 minutes); a phone-reach line in the
preflight; the phone's reconnect when the network changes; a "Show" button
on the key field; a Quick start at the top of INSTALL.

**3. Voice upgrades** (`voice-playtest.md`, `voice-lineup.md`, `voice-fx.md`):
Kokoro v1.0 and the "Hear it" picker; interrupting Jarvis turns your words
into the next question (today they are dropped); "One moment." while the
model wakes up; the PC talk button working while "Hey Jarvis" is on; more
processor threads for the voice (measured here: about 0.4 s faster per
first sentence); the phone's mouth-sync timing and the desktop's (the desktop
face's mouth does not follow the real voice yet); tap-to-talk on the phone.

**4. The other new abilities:** inbox tidy, talk-to-type, the Today page,
"remind me about this" from the screen (with a card), promises turned into
reminder offers ("I'll call the dentist Friday" → "Remind you Friday at 9?").

**5. Engine and quality:** make the tool test honest before choosing models
(check argument values, run 3 times, dated results); warm up the model with
a real request; try `qwen3.5:4b` and `granite4.2:8b`; the Ettin re-ranker
in the memory self-test; the injection detector bake-off; crash-safe
approvals (never re-run an approved action after a crash).

---

## 5. Found but not fixed yet (small, within the rules)

- **Phone:** "Use" on memory-search models (the desktop fix's twin); only
  the last question and answer are ever shown; voice switches live in
  Checks, not Settings; Settings missing from Home's row; "Background
  restart" never offered after pairing; TalkBack not told when the link
  drops; the assistant gesture reopens the last screen.
- **Desktop:** Settings is 17,400 pixels tall with no search; jargon on
  screen ("rush latch", "tier auto → ask", "extraction is a scaffold");
  example sentences with no heading; onboarding cut off at large text;
  browser-style pop-ups for Forget/Erase.
- **Windows notifications' Deny/Snooze may not work** - needs one click on
  the owner's PC to find out (not confirmed).
- **Docs out of date:** `MODEL-TOPOLOGY.md` on tool-call grammars;
  `gemma4:e4b` is not an 8 GB model; the Modelfile's `repeat_penalty`;
  sherpa-onnx's GPL espeak-ng needs a line in the notices.

## 6. Still the owner's call, later

- A much bigger model on the 12 GB card using ordinary memory
  (`qwen3.6:35b-a3b`) - after the card is installed and measured.
- The phone security check that contacts a Google server - with per-device keys.

## 7. The studio itself

`.claude/agents/README.md` lists the 13 agents and how to use them. Every
agent reads `.claude/agents/JARVIS-TODAY.md` first (what Jarvis has, what is
researched, one or two cards). Ideas from projects Jarvis may not copy go
through `docs/clean-room/`. Mistakes caught during this review, written down
so they are not repeated: a "Cancel still erases" finding that was
overstated; a "phone never speaks on its own" rule that does not exist; a
claim that cloud lanes were ready when none is configured on the owner's PC.
