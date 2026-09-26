# Creativity audit, 2026-09-25: one plan from four reports

Four agents looked at Jarvis from four sides. Their full reports are in
`docs/creativity-2026-09-25/`:

- `rules.md` - every rule, what it protects, what it costs, where it could bend;
- `usefulness.md` - a day in the owner's life, and 30+ ideas cut to 12;
- `experience.md` - how it feels to use: steps, cards, voice, wording;
- `future.md` - the big ideas for the next 6-12 months.

Every claim about Jarvis in them was checked against the file it names.
Guesses are marked as guesses. Nothing here is built yet, and nothing about
the rules changes without the owner's answer.

## The answer in one paragraph

The rules hold up: each one blocks a mistake that has really happened to
Muse, OpenClaw or ChatGPT. The friction comes from a few **mechanisms**, not
the rules - above all, any saved memory in a question makes every web search
ask first, and one light is one card. Jarvis already has almost every part a
useful day needs, so the biggest gains come from **joining the parts up**
(scheduler, briefing, calendar, email, notes, memory, Home Assistant, voice),
not from new outside services. The two apps also need **one way of showing a
card** - today the words and the Approve/Deny order differ between screens.

## Where all four agree

1. **Too many approval cards, for the wrong reasons.** Estimated 4-9 cards
   on a normal day, 10-18 if lights are voice-controlled (estimates - there
   are no usage logs). The two biggest causes: web search carding whenever a
   pinned or recalled fact was in the question (`jarvis_agent.py`
   `web_search_card_lines`), and one card per light (`jarvis_home.py`).
2. **The card itself.** The bar shows a code name (`switch_model`), the
   widget says "APPROVAL REQUIRED", the phone says "Jarvis wants to learning
   enable". Approve and Deny swap places between screens.
3. **Never "always allow", never approve by voice.** All four reject both:
   the first breaks "no approve-all"; the voice check cannot tell a
   recording from the real voice.

## The plan, ranked (value / size)

**Small and soon**

| # | What | From | Size | Touches a rule? |
|---|---|---|---|---|
| 1 | Web search asks only when the search words repeat a saved fact, or a sensitive fact was used | rules, experience | S | **Yes - question 1** |
| 2 | One plain approval card on every screen: a human title, one button order | experience | S | No (wording) |
| 3 | Fix: Quiet mode does not hold back offers (`jarvis_backoff.may_offer`) | usefulness | S | No (bug) |
| 4 | "Open the card" link wherever a button raises one; the PC notifies every card | experience | S | No |
| 5 | Error messages in plain words, with the fix on the spot | experience | S | No |
| 6 | Snooze, "cancel that", named lists ("add milk to the shopping list") | usefulness | S | No |
| 7 | "What did I miss?" - the briefing's builder, since you last looked | usefulness | S | No |
| 8 | Voice says a card is waiting, and what happened after | experience | S | No |

**Medium**

| # | What | From | Size | Touches a rule? |
|---|---|---|---|---|
| 9 | One card for several named home devices (never locks, alarms, covers); home names and scenes | rules, experience, usefulness | S-M | **Yes - question 2** |
| 10 | A "Today" page: what Jarvis did, in plain words, in both apps | experience | M | No |
| 11 | Focus sessions: a timer plus Quiet, back to Active only if focus set Quiet | usefulness | S-M | No |
| 12 | Evening wrap-up into the Obsidian daily note, from the owner's own words | usefulness | S-M | No (calendar titles left out, so no card) |
| 13 | A nudge before calendar events, with a "prep me" sheet of related notes | usefulness | S-M | No |
| 14 | "Tell me when..." (an email from someone, a device changes) - one card to set up, a match only notifies; merged with the GitHub watchlist | usefulness | M | No |
| 15 | Alarms that keep ringing; timers said aloud | experience | S-M | No |
| 16 | A settings map on the phone; one name for Brain / Mind | experience | S-M | No |
| 17 | "Make stricter" switches in both apps (looser still raises a card) | rules | S-M | No (tightening only) |

**Bigger, later**

| # | What | From | Size | Notes |
|---|---|---|---|---|
| 18 | "Ask my own stuff": one question across notes, the wiki and dated facts, with sources | future | M-L | Whether past chats are searched is the owner's call |
| 19 | Goals: a plan the owner edits, one card per step that acts | future, Muse audit | L | |
| 20 | Second card, first use: seeing (screen, phone photos) or reading the whole vault | future | M | The owner's call, once the card is fitted and measured |
| 21 | A home that learns routines, offering one automation at a time as a card | future | L | Needs a new Home Assistant history read |
| 22 | A weekly journal draft, saved to Obsidian after a card | future | M | |
| 23 | A light schedule approved once, the card listing every run | rules | M | The owner's call |
| 24 | A short time-limited pass for one light | rules | M-L | Only after approval-gap step 1 |

## Rejected by the audit, with the reason

- "Always allow" / "for this conversation" grants - permission for actions
  nobody has named; breaks "no approve-all".
- Approving by voice - the voice check cannot tell a recording from the owner.
- A standing cloud grant - the owner chose "ask each time" (2026-09-24).
- Typing API keys on the phone - rule 3 (a key goes only to its service).
- Household mode - breaks "one owner"; "room awareness" is offered instead.
- Suggesting passes from past approvals - an offer may never ask for more access.

## Questions for the owner

Asked two at a time. The first two (below) touch the rules; the rest follow.

1. Web search asks first whenever a saved memory was in the question. Ask
   only when the search words would repeat a saved fact, or a sensitive fact
   was used? (recommended) / Keep asking whenever memories were used.
2. One smart-home card for several named devices, listed in full (never
   locks, alarms or doors)? (recommended) / Keep one card per device.

Later: a warm, brief manner with a "Plain" option; whether "ask my own
stuff" may search past chats when asked; the second card's first job; the
evening note without calendar titles; a read-only shopping list on the phone
for when the PC is off; the light schedule.
