# Report 11 (audit), agent adc2842a, 2026-09-29T20:44Z

> **What it was asked** (first 600 characters of the task): Check PR #35 (checked out read-only at /tmp/pr35; diff via `git -C /tmp/pr35 diff origin/main...HEAD`, ignore docs/SOURCE-BUNDLE.md) against the five non-negotiable rules and every owner decision in CLAUDE.md and docs/ARCHITECTURE.md. The PR adds a headless browser (Obscura) with stealth on and REVERSES the earlier 'driven openly / nothing that dodges bot detection' rule; the PR says the owner decided this on 2026-09-29. Check: is the reversal recorded consistently everywhere (CLAUDE.md, ARCHITECTURE section 4 named ways out, design docs, tests) with no leftover text still stating the old rule

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

RULES CHECK OF PR #35 (Obscura headless browser, stealth on) - report only, no files changed. Checked at /tmp/pr35 against origin/main...HEAD, ignoring docs/SOURCE-BUNDLE.md.

BOTTOM LINE: I found no break of rules 1, 2, 3, 4 or 5. The reversal is recorded consistently, with no leftover text stating the old rule as current. There are five small things the owner or author should look at (listed at the end). Nothing here can be independently confirmed that the owner actually said it on 2026-09-29. The only evidence in the repo is the PR's own edit to CLAUDE.md, so that needs the owner's eyes at merge.

VERDICT TABLE

| Item | Verdict |
|---|---|
| Reversal recorded in CLAUDE.md | KEEPS THE RULES (recorded, old text struck through, not deleted) |
| Reversal in ARCHITECTURE section 4 and 8 | KEEPS THE RULES (row added; see the one caveat on section 4 below) |
| Reversal in design docs, code comments, tests | KEEPS THE RULES (no stale statement of the old rule) |
| Rule 1 (private data into pages) | KEEPS THE RULES, with one disclosed soft spot (item 3 below) |
| Rule 2 (no tunnel, no port, no proxy) | KEEPS THE RULES |
| Rule 4 (no auto-approve, stale stream) | KEEPS THE RULES |
| Rule 3 (keys, token, plain text on disk) | KEEPS THE RULES (no key involved) |
| Rule 5 (non-commercial, credit) | KEEPS THE RULES (Apache-2.0, credited) |
| Off by default, one card to turn on, off instant | KEEPS THE RULES |
| Never solves captchas / no proxy service / never claims to be human | KEEPS THE RULES |
| New outward path registered as a named way out | KEEPS THE RULES (registered) |
| App lock / hidden lists | KEEPS THE RULES (nothing private is shown; same pattern as sibling settings) |
| Downgrading "spare account" from rule to advice | NEEDS THE OWNER (goes beyond what the reversal text says) |
| Wording "stealth on for everything" / "Jarvis's browsers" | NEEDS THE OWNER (overstated; see item 1) |

EVIDENCE

1. Reversal recorded consistently
- CLAUDE.md:541-551 strikes through "driven openly ... nothing that hides it ... dodges Google's bot detection" and "tactics that help avoid bans", and adds "Reversed 2026-09-29 (owner)".
- CLAUDE.md:643-644 (versatile chatbots, "driven openly" struck) and CLAUDE.md:687 ("never hiding from the site's bot detection" struck) are both updated.
- A new dated decision block is at CLAUDE.md:1622-1660. It lists what changes and what does not change, including "if the other side asks directly whether it is talking to a bot, Jarvis never claims to be human" (1643-1645).
- ARCHITECTURE.md:644 adds the Obscura row, which says "the ban risk was explained". ARCHITECTURE.md:2112 adds the section 8 "one-sided on purpose" note.
- CHATBOT-DRIVER-DESIGN.md:8, 287-321, 326-328 (struck through), 556-558 and 636-637 are updated. STUDIO-REVIEW-2026-09-27.md:61-62, audit-2026-09-28/06-decisions.md:140, JARVIS-API.md:11170, 13586 and 13832, JARVIS-TODAY.md and THIRD-PARTY-NOTICES.txt are all updated.
- I grepped the whole tree (excluding the bundle, patch-history and CHANGELOG) for: openly, dodge, bot detection, never hides, no stealth, disguise, presents itself, identifies itself, automated test software. Every remaining hit is either the recorded reversal, a test asserting the old promise is absent (test_chatbot_gemini.py:238, test_chatbot_sites.py:380-383), or unrelated. The one exception is the CLAUDE.md:1622 heading mismatch in item 1.
- The old card promises "never hides that it is a program" and "never changes how the browser looks" were removed from jarvis_chatbot_web.py's card note. Both apps only display the backend's card text, so no app change was needed. The note still names the terms risk and says the account may be closed.
- Tests were rewritten, not deleted. test_chatbot_gemini.py, test_chatbot_sites.py, test_handoff.py and test_support_widget.py now check that there is still no proxy code, no captcha-solving code and no spoofing code in the visible-browser files (the FORBIDDEN list is split into PROXY_WORDS, CAPTCHA_WORDS and SPOOF_WORDS). The "never claims to be human" and identity-check handover behaviour was not touched.

2. Named way out
- ARCHITECTURE.md:644 is a full row in the section 4 table. It gives what goes out (navigation, click and typed words only to sites named on the plan card), which rule-1 checks apply, and the gate hooks.
- The gate action is `obscura_enable`. It is registered in backend/browser-engine.patch as tier `ask` and outbound risk, and added to "acts only on tier ask". The PR adds it to the lists in jarvis_asks_first.py, so it cannot be loosened by an app. jarvis_card_words.py and jarvis_reach.py have entries for it.
- Every page, click and typed box still goes through the ordinary `control_browser` plan card. The card's first line names the engine (jarvis_browser_control.py describe() diff). jarvis_browser_engine.py:22-31 says choosing headless "changes which browser runs the steps, never who is asked".

3. Rule 1
- Refused before any card: a `<secret>` step; typed text or a web address that looks like a password, key or token; and typed text or an address query that repeats a saved fact (jarvis_agent._browser_private_refusal, jarvis_browser_engine.py:33-41).
- Refused at run time: a password, card-number, file or hidden box.
- Page text comes back as outside text (`took_in`, so the conversation is tainted and nothing is learned as a fact).
- Obscura's private-address guard stays on, and the backend refuses addresses on this PC, the home network, Tailscale and Meshnet before Obscura is asked (jarvis_browser_engine.py:52-56).
- Disclosed soft spot: an ordinary word the model chose to type that came from an email or file it read is NOT blocked. The card shows it and, after outside text, adds a warning line at the top (BROWSER_OUTSIDE_LINE, jarvis_agent.py diff). This is stated at jarvis_browser_engine.py:40-42 and in ARCHITECTURE.md:644. The visible browser has the same gap today, so it is not new. It is an "ask, shown in full" case rather than a hard block.

4. Rule 2
- ARCHITECTURE.md:644 says: no `--http`, `--host`, `--port`, `--proxy` or `--allow-private-network` (also jarvis_obscura.py:33-38).
- The program runs over standard input/output only, so there is no listening port. Only the fixed flags `--stealth mcp` are passed (jarvis_obscura.py:379-382).
- It starts only while the switch is on, with 3-minute-idle and 10-minute watchdogs.
- The environment is an allow-list (jarvis_obscura.py:60).
- The binary is downloaded only by the owner's own pasted line. The backend never downloads it (jarvis_obscura.py:76-84).

5. Rule 4 and the switch
- `obscura_enable` is off by default and turning it on raises one card. jarvis_browser_engine.request() returns HTTP 202 "waiting", never "on", until approved (1531-1571). Turning it off is immediate and also stops the program (1541-1552), and it withdraws a pending card.
- Held on a stale link: browser_engine.rs:71 (`action == "on" || "mode"` refused if `look::stale`) and JarvisRuntime.kt (`if (on) actionBlocker()`; `setBrowserEngineMode` also blocked). "Off" is never held.
- Choosing the default browser mode (Automatic, Visible or Headless) has no card. That is defensible, because both browsers ask on every plan and the mode does nothing unless the switch is on. It is also held on a stale link.
- The desktop passes only a switch position or one of the three fixed mode names (browser_engine.rs body(), with Rust tests). The phone caches nothing.
- The voice and chat door (jarvis_settings_registry.py set_browser_engine) calls the same request(), so ON there is also one card.

6. App lock and hidden lists
- The new screens (desktop Settings, "Headless browser"; phone Settings -> Headless browser) show only fixed words, a switch position and the install command. They show no memory, chat or page content, so the hidden-lists rule has nothing to hide. The new code adds no App-lock-specific handling. I did not find a place where it needed to.
- The install line and status are in Settings like the sibling picture-mode switch, and I saw no new bypass of the lock.

7. Rule 5 and credit
- THIRD-PARTY-NOTICES.txt credits Obscura (Apache-2.0) and says it is not distributed or linked, so credit and licence terms are satisfied.

8. Within what the owner said
- Never solves a captcha: a captcha, an "are you human" page or a sign-in page it recognises stops the run and hands off to the visible browser (jarvis_browser_engine.py:44-46; the reach status text says the same).
- No proxy anywhere. No cookies or files are saved. Running the page's own script, tabs, key presses and downloads are not reachable (ALLOWED_TOOLS).
- The typing pause stays as a fixed value, "not a disguise" removed (CLAUDE.md:1650-1652).
- The headless browser is switched off until the owner turns it on with one card. Off works with nothing else enabled, and it is not registered with Pause/Resume; "Stop everything" stops it (`stop_all`).

ISSUES TO LOOK AT

1. Wording overstates the reversal. The CLAUDE.md heading at 1622 and the design doc at CHATBOT-DRIVER-DESIGN.md:287-293 say "Stealth on for everything" and "Jarvis's browsers ... run with stealth ON for everything". In fact only Obscura has stealth. The visible browser used for Gemini, ChatGPT and support chats has none, and a test still forbids spoofing code there (CLAUDE.md:1627-1631, ARCHITECTURE.md:2112). The owner's quoted words are "stealth on for everything it runs", meaning Obscura. Suggest the heading and design intro say "for everything Obscura runs" and state plainly that the chatbot and support windows stay unspoofed. NEEDS THE OWNER only if they intended stealth for those windows too.

2. Beyond the stated reversal: the spare Google account was a written rule (CLAUDE.md:552-554, "A spare Google account used only by Jarvis") and is now downgraded to "advice, not a rule" (CLAUDE.md:1648-1650, CHATBOT-DRIVER-DESIGN.md:319-320). The reversal quote covers stealth and bot-detection dodging only. The docs also say a card still names the terms risk, so nothing is hidden. Confirm the owner meant to relax this too. Whether Jarvis's code ever enforced it is not something I checked.

3. Soft rule-1 spot (see section 3): words from an email or file can still be typed into a web page after a card that shows them in full. The card now warns at the top after outside text, but nothing blocks it. It is the same as the visible browser and is disclosed, so it is a NEEDS A CARD item, not a break.

4. Supply-chain note: `PINNED_DIGEST` is empty (jarvis_obscura.py:82-83), so the first file the owner checks is trusted and later ones must be accepted by hand. That is disclosed in ARCHITECTURE.md:644, and the owner compares checksums before the first run. A real Obscura binary has never been run here (jarvis_obscura.py:89-92). It is also plain-text on disk: `obscura.log` holds Obscura's own error output (jarvis_obscura.py:86-88). The claim that it never holds a typed value is a claim, not something I verified against a real binary.

5. Behaviour change worth noting: `browser_control` is now offered without the second graphics card whenever the headless browser is on (jarvis_agent.py offered_tools diff). It works on one card, which fits "one or two cards", and it costs no graphics memory (a separate program on the processor). The visible browser and Solve it here still need the second card. Reach text was updated to say so (jarvis_reach.py diff). I found no rule problem here.

DUPLICATION: none found. It adds a second engine under the existing `browser_control` tool and the existing plan card rather than a new approval path.

KEY FILES (absolute, at the PR checkout)
/tmp/pr35/CLAUDE.md (541-554, 643-644, 684-688, 1622-1660)
/tmp/pr35/docs/ARCHITECTURE.md (640-644, 2112)
/tmp/pr35/docs/CHATBOT-DRIVER-DESIGN.md (8, 287-321, 326-328, 556-558, 636-637)
/tmp/pr35/backend/jarvis_browser_engine.py, jarvis_obscura.py, browser-engine.patch
/tmp/pr35/jarvis-desktop/src-tauri/src/browser_engine.rs
/tmp/pr35/jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt
