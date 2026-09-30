# Report 48 (audit), agent a8d6cbc9, 2026-09-30T07:17Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis's APPROVAL CARDS as the owner experiences them (read CLAUDE.md fully first: rules 1-5; 'never auto-approve'; risky approvals need Windows Hello / phone fingerprint; decisions about which things ask, 'What asks first', approvals-audit 2026-09-26 'small low-risk things stop asking'; plan card; one card per email; one smart-home card may cover several named devices; Goals; card wording rule; docs/APPROVALS-AUDIT-2026-09-26.md, docs/ARCHITECTURE.md sections 3/4/12, JARVIS-API.md; verify each claim with file:line + quote; 'not checked' honestly; change no f

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

APPROVAL CARDS AUDIT (read-only, nothing changed). Ran: nothing (no tests run; code read only). Not checked: the owner's real jarvis_gate.py (not in repo), real `history()` rows, real per-action risk rows (reach/reversible), phone Kotlin rendering, real card counts. Prior audit (docs/APPROVALS-AUDIT-2026-09-26.md) already inventoried tiers; its changes 1-3 are built (framework toml now has email_read/calendar_read/notes_search/home_read = auto, rebuilt/jarvis-framework.toml:90-93).

VERDICT: cards are strong on safety and honest wording; weak spots are jargon on a few setup cards, history that keeps no detail, and Undo that lives in different places per feature.

CARD KINDS (title source: backend/jarvis_card_words.py TITLES; taint lines: jarvis_agent.py)
| Kind | Tier | Effective? | Efficient? | Issues |
|---|---|---|---|---|
| send_email | ask, NEEDS_A_PERSON | Yes: From/To/Cc/subject/whole text, taint line on top (jarvis_agent.py:1877), "cannot be taken back" (jarvis_email_send.py:456) | Yes, 1 per email | Too long = refused, not cut (1891). Widget shows 1 line, redirects to bar (widget.js:1046-1060) |
| draft_email | ask | Yes, same shape | Yes | none |
| tidy_inbox | ask | Yes: lists every email, taint line (2005) | Yes: 1 card <=30 emails | Not refused after outside text, card warns only |
| home_control | ask (NEEDS_A_PERSON); lights setting can skip | Yes, devices listed | Batched OK | risk row for it not in repo (README says add by hand) - not checked |
| shell / control_computer / browser | ask | Yes, full plan | 1 per plan | Plan >4000 chars is refused before the card (_card_would_be_cut, 2282-2300) |
| note write after outside text | ask | Yes, says why (2079) | fine | none |
| web search | ask only when private | Yes: exact words + why (2117) | Good | none |
| chatbot / support / offer | ask | Names terms risk (jarvis_chatbot.py:445) | 1 per chat, 1 per offer | not read in full |
| second-card / model / settings loosenings | ask | Mixed | fine | JARGON: card says "a second copy of Ollama", "id <uuid>", "listens on 127.0.0.1:port" (jarvis_second_card.py:3032-3035) |
| schedule_repeat (briefing, tell-me) | ask | ok | 1 card | plain repeats need none |
| Forget-a-time-frame | ask, risky | Lists every item | 1 card | after 10 min gone for good |
| plan card | off | n/a | n/a | not measured yet |
| fallback title | - | Weak: `Jarvis wants your OK for "big model enable"` for an unknown action | - | plus "check PyPI, crates.io and GitHub" title is jargon |

WALKTHROUGHS (cards / taps)
- Reply to Sam's email: read = 0 cards; send = 1 card (Approve, plus Windows Hello/fingerprint since it leaves the PC) = 2 taps. Good.
- Kitchen lights off + lock door: 2 cards (lights set, lock always alone). Correct per decision. With lights setting on: 1.
- Read a page, summarise, save a note: search 0 (own question, clean chat); note write after reading = 1 card. Obsidian daily when clean = 0.
- Tidy inbox: 1 card, then Undo strip (10 min). Best flow.
- Install a model: 1 card, no chained switch card (separate ask if switching).
- Ask Gemini: 1 card per conversation.
- Web search after reading an email: 1 card only if words repeat a saved fact/sensitive; else 0 (bug-free per ARCHITECTURE decisions).
- Repeating reminder: 0 cards (decided 2026-09-26).
Cap 5 cards per answer (CARDS_PER_TURN, jarvis_agent.py:2338), by design so a flood cannot tire the owner. Timeout 180 s, then refused (toml:79).

FINDINGS (worst first)
1. Approval history keeps only the title, not what was approved. `test_gate_egress.py` proves history() never reads detail/prompt and decide() nulls them (JARVIS-API §42.1). Good for privacy; cost: the owner cannot see later which recipient/command they approved. Fix (small): title-only stays; add a one-line "what" summary (recipient count, device name) that is non-sensitive. Owner call.
2. History is unorganised and partly guessed: no paging, no filter, no search, no export; unparseable rows dropped silently; field names (decided_by, state/outcome, decided_at) ASSUMED (§42.1, §42.3). Newest first only. Desktop (brain.js renderActivity) and phone (InboxScreen.kt) match by design. Fix: confirm real row shape on the PC first, then add filter by decision and device.
3. Undo is scattered. Inbox tidy has a strip under the bar (inbox-tidy.js, 10 min, in memory only - lost if the backend restarts); Forget-a-time-frame has its own panel; reminders/timers by saying "undo/cancel that"; other kinds rely on the undo shelf, whose backend jarvis_undo.py is not in the repo (JARVIS-API:1399 "unconfirmed"). No general "Undo" on the after-approval confirmation. Fix: one shared line after approving saying which Undo exists and where.
4. Jargon on setup cards (see table): second-card card (jarvis_second_card.py:3032), fallback title. Fix: plain rewrite, drop uuid and port from body (keep in details).
5. Widget shows 1 line (first 200 chars, widget.js:940-951) but Approve on "heavy" cards is redirected to the bar (1046-1060); ok, but a risky one-line card can look small next to its consequence. Mitigated by riskLine "No undo - leaves this machine" (jarvis-link.js:1440). Good.
6. amend note (POST /api/pending/<id>/amend, JARVIS-API:1607): kept with the card, not part of the signed/changed card, handed to the model with the answer. A note cannot change the approved action but could steer the model's next step; the next step raises its own card. Acceptable; recommend the card show "you added a note" on the result. Low.
7. Good and verified: Deny left, Approve right (jarvis_card_words.py BUTTONS); focus stays off Approve (widget.js:1935; main.js:2379); heavy cards wait before Approve unlocks (main.js:2512); risky = unclassified, outbound, irreversible or rushed (jarvis_owner_check.py:150-170); no bulk/always-allow.

HISTORY AND UNDO
Where stored: gate `approvals` table on the PC (jarvis_gate.py, not in repo); audit log ~/.openjarvis/logs/, 90 days, "redact_private_content_in_logs" (toml:505-510). History fields: title, Approved/Denied/Timed out, when, device (assumed). No exact text kept. Whether Forget/auto-delete/backup touch it: not checked.
Undo by kind: send email - never (says so); shell/purchases - never (should say "cannot be undone" on the card; email does, shell not confirmed); inbox tidy - yes 10 min, in-memory; Forget range - yes 10 min; single Forget - Undo 10 min (ARCHITECTURE:986); reminders/timers - "cancel that" instantly; model switch - Roll back (own card-free action); home lights - no undo, but "turn it back" is trivial (no button); note writes - no undo; settings loosening - off is instant (acts as undo); memory saves - Forget.
Missing undo that would be cheap: note writes and home lights (no shelf entry known).

OWNER QUESTIONS
Q1. Should past approvals show one non-sensitive detail (e.g. recipient count, device)? (a) Yes, small summary line, recommended; (b) Keep title-only.
Q2. After any approve, show one line saying which Undo exists? (a) Yes, recommended; (b) Leave as is.
Q3. Rewrite the second-card and other setup cards in plain words (drop "Ollama copy", id, port)? (a) Yes, recommended; (b) Keep technical, put behind "Details".
