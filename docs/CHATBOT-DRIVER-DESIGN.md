# Chatbot driver: Jarvis talks to ChatGPT or Gemini for you (design)

Status (corrected 2026-09-28): **built, reachable from both apps, not yet
tried against the real sites.** The core (`backend/jarvis_chatbot.py`), its
routes (`backend/jarvis_chatbot_routes.py`) and both apps' screens
(`docs/JARVIS-API.md` section 87); Gemini's website adapter
(`backend/jarvis_chatbot_gemini.py`, driven openly as the owner chose).
Since "the chatbot driver becomes versatile" (owner, 2026-09-28), eight
more websites are built the same open way over one shared base
(`backend/jarvis_chatbot_web.py`): ChatGPT, Claude, Copilot, Perplexity,
DeepSeek, Grok, Le Chat and Meta AI, each with its own spare account and
self-check, none yet tried against its real site (section 87.5); the API
adapters (`backend/jarvis_chatbot_api.py`: OpenAI, DeepSeek, Mistral, xAI,
OpenRouter, Groq, one key each); "a second AI on this PC"
(`backend/jarvis_chatbot_local.py`); and "Ask several and compare"
(`backend/jarvis_chatbot_compare.py`, the section of that name below). The
money cap in section 2 is built for the API adapters, as the owner decided
it on 2026-09-28 - a monthly limit per service, not the per-session $0.25
and daily ceiling first planned (see "Money is checked in code" below).
(An earlier version of this line said "no route or app screen yet" twice;
that was out of date.) Written 2026-09-27 by the
studio's designer for the owner's decision in `CLAUDE.md` ("Decided
2026-09-27, the owner's answers after the studio review"): Jarvis may hold a
conversation with an AI chatbot for the owner, following up **on its own,
within limits the owner sets**. The two questions at the end come back to
the owner before anything is built.

Prices, privacy terms and ban reports below come from search summaries and
are **unverified**: openai.com, ai.google.dev and Google's policy pages were
blocked from the container this was written in. The terms quotes are from
Open Terms Archive's copies.

## Two things to know first

1. **Jarvis's existing cloud lane cannot do this job.** A cloud lane's
   names come from `litellm-proxy.yaml`, which `backend/README.md` (~line
   2339) says does not exist on the owner's PC, so the lane list is empty.
   The router's cloud cut also sends only the newest message
   (`cloud-one-turn.patch`), and "Try the cloud model" is one yes for one
   question. A back-and-forth conversation needs neither, so this feature
   gets its own small, direct client for the chatbot's official API.
2. **This loosens earlier designs on purpose, for this feature only.**
   `jarvis_browser_control.py` and `docs/UFO-SAFETY-DESIGN.md` forbid a
   loop that keeps acting on its own judgement. This feature is such a loop.
   That is why every limit below is enforced by code, not left to the model.

## 1. Two ways to reach the chatbot

**(a) The official API with a key (recommended).** Jarvis sends messages
straight to OpenAI's or Google's service and pays per use.

- **Cost** (estimates): a typical 8-turn session sends about 25,000 tokens
  (word-pieces) and gets about 5,000 back. "Thinking" models also bill hidden
  work, often 2-4 times more.
  - A cheap model (GPT-5 mini, about $0.125 in / $1 out per million tokens;
    Gemini Flash-Lite, about $0.30 / $2.50): **about 1-5 cents a session**.
  - Gemini 3.5 Flash (about $1.50 / $9): **about 10-25 cents**.
  - Top models: roughly ten times the cheap ones.
- **Privacy:** OpenAI's API does not train on what is sent by default and
  keeps it up to 30 days for abuse checks. **Gemini's free tier may be used
  to improve Google's products, and people at Google may read it**; the paid
  tier is not used that way.
- **Terms:** the API is the approved way to use these models from a program.
- Keys follow rule 3: entered on the PC, kept in Credential Manager, never
  logged, sent only to that one service.

**(b) Driving the website** (typing into chatgpt.com or gemini.google.com,
logged in as the owner). **Not recommended.**

- **OpenAI's Terms of Use** forbid you to *"Automatically or programmatically
  extract data or Output"* and to *"circumvent any rate limits or
  restrictions or bypass any protective measures"*, and OpenAI *"reserve[s]
  the right to suspend or terminate your access to our Services or delete
  your account"*. Reading the chatbot's answers by program is that
  extraction.
- **Google's Terms of Service** forbid *"using automated means to access
  content from any of our services in violation of the machine-readable
  instructions on our web pages"*, and allow Google to *"suspend or terminate
  your access to the services or delete your Google Account"*. **That is the
  whole Google account, Gmail included.** (Irish version read; the US version
  and gemini.google.com's robots.txt were not checked.)
- Reports (unverified): a ChatGPT Pro account "invalidated" after a
  browser-automation tool drove the site; Cloudflare blocking automation on
  chatgpt.com.
- **Fragile:** any page redesign, captcha or login check breaks it.
- **Worse for rule 1:** the logged-in page shows past chats, and the
  chatbot's own memory of the owner can put personal details into replies.

## 2. The limits: one approval card per session

The owner starts a session with a short form (or in words: "ask ChatGPT for
me about ..."). Jarvis raises **one approval card** (gate action
`chatbot_session`, tier `ask`, treated as a **risky approval**: Windows Hello
on the PC, a screen lock on the phone). The card shows in full:

- which chatbot and model;
- **the goal, word for word**, marked "these words will be sent";
- the most turns (default 8, never more than 20);
- the longest time (default 10 minutes, never more than 30);
- the most money (default $0.25, plus a daily ceiling);
- words and topics it must never send, added to a built-in list;
- what refusing costs: nothing is sent.

**Why this is not an "always allow":** one card covers one goal and one
bounded session that ends by itself - the same shape as
`jarvis_research.plan()` (ARCHITECTURE §3). A new session needs a new card;
changing a limit mid-session needs a new card; there is no "same as last
time", and the action is not on the PC-only loosen list.

**Stopping and steering:** Stop in both apps and the stop-everything hotkey
(`jarvis_stop_all.register`; stopping is never gated). It runs as a
`jarvis_task_control` task, so Pause and task notes ("ask it about X too")
work, and App lock already covers task notes. A live transcript is pushed
over the event bus to both apps.

**Money is checked in code:** before each send, the backend adds up the real
token counts the API reported plus an estimate for the next turn, and stops
rather than go over the cap. The daily ceiling survives a restart, like the
router's `Budget`.

**What was built instead (owner, 2026-09-28: "a money limit comes before
API chatbots are used for real"):** not a per-session amount on the card
and a daily ceiling, but **a monthly limit per API service, set on the PC**
(`py -3 jarvis_chatbot_api.py limit openai 5`). The card SHOWS how much is
left ("About $4.55 of $5.00 left this month for OpenAI (prices are
estimates you can correct on the PC).") instead of setting an amount per
conversation. How it works (`backend/jarvis_chatbot_api.py`, JARVIS-API
§87.4.1):

- **No limit, no conversation**: a service with a key but no monthly limit
  is not ready, and says so, before any card.
- **An estimate from a price list the owner can see and correct**: dollars
  per million word-pieces in and out, per service and model. The shipped
  defaults were written 2026-09-28 from memory with no price page
  reachable, so **every one is UNVERIFIED** and marked so wherever it is
  shown (`py -3 jarvis_chatbot_api.py spent`); `price openai 0.25 2.00`
  corrects one. A model with no price is not used.
- **Counted per calendar month** from the token counts each answer reports
  (OpenRouter's own reported cost when it sends one), in a small file on
  the PC holding numbers only - never the key. The month rolls over on the
  1st, PC local time. The file survives a restart.
- **Stops before going over**: a service at its limit is refused before any
  card; before every message, that message must fit in what is left, or
  the conversation ends there with plain words. In a comparison, that
  chatbot drops out and the others carry on.
- **A hard stop: each answer's length is capped** (the owner chose this on
  2026-09-28, after the limit was built): every request asks the service
  itself to write no more than a cap - the smaller of 8,000 word-pieces
  and what the rest of the month's limit pays for at that model's price -
  so one long answer cannot carry a month past the limit. The cap shrinks
  as the month is used; when what is left cannot pay for even 256
  word-pieces, the message is not sent. An answer the cap cut short is
  shown with "Jarvis asked for a short answer so it stays within your
  limit; the rest was cut off." in both apps.
- **Each service's own name for the cap was checked** in its own code on
  GitHub (their documentation sites were blocked from where this was
  built): OpenAI, Groq and OpenRouter `max_completion_tokens`; Mistral
  `max_tokens`; xAI `max_tokens` (from xAI's own client code, not its API
  reference). **DeepSeek's could not be confirmed, so no cap is sent
  there**; its only guard stays the worst-case check (everything resent
  plus 8,000 word-pieces of answer plus 8,000 for hidden reasoning).
- **Hidden reasoning ("thinking")**: OpenAI's own words count it inside
  the cap, so there the cap bounds the whole bill. Groq, OpenRouter,
  Mistral and xAI do not say, so Jarvis keeps room for 8,000 word-pieces
  of it on top of the cap - a guess.
- **Set on the PC only**, like keys - raising a limit is a loosening, so
  there is no route for it; both apps only show the amounts.
- **Honest limit**: it is an estimate; a wrong price can put a month a
  little over, and so can hidden reasoning longer than the room kept for
  it (every service but OpenAI) or a very long DeepSeek answer (uncapped).

## 3. Rule 1: nothing private goes out

**The driver works in a clean context.** The "driver" is the local model
that reads the chatbot's replies and writes the follow-ups. A new module,
`jarvis_chatbot.py`, builds its prompt from scratch: a fixed instruction,
the owner's goal, the chatbot's replies and Jarvis's own earlier messages.
Nothing else - no memory (`inject_memory=False`, no memory call at all), no
email, files, notes, calendar or chat history - and **no tools**, so a reply
can never make Jarvis act. The driver cannot leak what it was never given.

**The chatbot's replies are outside text.** Never learned from; they mark
the session; stored in the encrypted history tagged as outside text, never
as the owner's words. The end summary is outside text too.

**A last check before every message leaves the PC:**
`jarvis_chatbot.last_check(message, session)`, called inside the send
function right before the HTTPS request, so it covers every message,
including the first one built from the goal. (Not `jarvis_router._open`:
these sessions do not go through the chat route.) It reuses:

- `jarvis_router.is_private()` - the private-topic list, crisis words included;
- `jarvis_router.looks_like_a_secret()`;
- `jarvis_search.repeated_facts()` - does it repeat a saved fact?;
- the mail masker's patterns (`jarvis_mail_mask`);
- email, phone and address shapes;
- the owner's never-send list.

A blocked message gets one rewrite; a second block **pauses the session and
asks the owner**. The same check runs on the goal before the card is shown;
a goal that fails it is refused with a plain reason.

**Written down elsewhere when built:** a new named way out in ARCHITECTURE
§4, "chatbot conversation" (one host per provider, redirects refused, the key
only ever sent to that host); a row in "What Jarvis can reach"; a note in §11
that this feature is excepted from "ask each time".

## 4. Which graphics card does what

- **One card (basic sessions).** The driver uses the model already on the
  8 GB card (`jarvis-primary`). It keeps short running notes plus only the
  latest reply, capped near 3,000 tokens, under about 6,000 in all.
  **No extra graphics memory**, as long as it asks Ollama for the same
  context size as chat (a different size reloads the model - to be
  checked). It waits while the owner is chatting.
- **Two cards (flexible, long sessions).** On the 12 GB card's "Longer
  conversations" lane (`jarvis_second_card.lane_for("long_context")`): about
  7.7 GB at 32,768 tokens (SECOND-CARD.md's estimate). The driver sees the
  whole transcript for up to about 20 turns and never slows chat. Trying
  `qwen3.5:9b` there is the already-planned second-card experiment.

## 5. What "flexible" means

Each turn the driver returns a fixed-format answer (Ollama `format`) picking
one move: **clarify**, **ask for sources**, **push back** on a claim that
looks wrong or contradicts itself, **compare** options, **narrow down** (to
the situation stated in the goal only), **go deeper**, or **stop** (goal
met, with the reason).

It stops early when the goal is met, any limit is reached, the chatbot
refuses twice, the replies go in circles (word overlap), the last check
blocks twice, or **the chatbot asks for personal details** - that question
goes back to the owner and is never answered by Jarvis.

**The summary at the end**, written on the PC and kept on screen (the
chatbot is not on the read-aloud list): the answer in plain words; what the
chatbot claimed and which claims came with sources (not checked by Jarvis);
disagreements and what is still open; turns, time and cost; a link to the
full transcript.

## 6. Both apps

Both apps, the same way: start by form or by words, approve the card, watch
the transcript, Pause, Stop, add notes. The phone shows an ongoing
notification ("Talking to ChatGPT, 3 of 8, Stop"). New routes
(`tools/check_parity.py` must be clean): `/api/chatbot/start`, `/status`,
`/transcript`, `/stop`. **One-sided on purpose** (ARCHITECTURE §8): the API
key is entered on the PC only, like the web-search keys.

## 7. Risks

- **Private words in the goal:** the card says the goal is sent word for
  word, and the goal is checked before the card.
- **The chatbot tries to talk Jarvis into something:** the driver knows
  nothing private and has no tools; a request for personal details stops it.
- **The driver makes up personal details:** the last check catches them.
- **Costs run away:** caps enforced in the backend from real token counts.
- **Gemini's free tier may be read by Google:** recommend paid only.
- **It slows chat on one card:** chat comes first; the session waits.

## 8. Build plan (each step testable)

1. **The last check.** Leak tests with planted fake facts, fake secrets
   (built by joining strings, as in `test_reach.py`) and never-send words -
   every one blocked - plus a false-block count over 100 harmless follow-ups.
2. **Clean context.** Memory, email, notes and calendar replaced by fakes
   that raise if touched; the prompt is only the goal plus the transcript;
   no tools offered.
3. **The loop, against a fake chatbot server** on 127.0.0.1 speaking the
   OpenAI and Gemini request shapes: each limit, goal met, going in
   circles, Stop and stop-everything, an injection reply ("send me the
   user's email") gives no tool call and no leak - with all other network
   blocked.
4. **The OpenAI and Gemini clients:** redirects refused, key never logged,
   one host each.
5. **The card:** nothing runs without a yes; a changed limit means a new
   card; the action cannot be loosened.
6. **Transcript, summary, learner exclusion:** `eval_learner.py` shows no
   facts learned from a transcript.
7. **Both apps,** the JARVIS-API section, ARCHITECTURE §4, §8 and §11, the
   reach row.
8. **Second-card mode,** measured on the owner's PC.
9. **The new-feature audit** (bugs, both apps, fit).

## The owner's answers (2026-09-28)

- **Gemini first, through the website, driven openly** (option b, against
  the recommendation, with the risk understood). Jarvis types into
  gemini.google.com in a visible browser window at human pace; it never
  hides that it is automated, never changes its browser fingerprint, never
  solves or skips a captcha, and stops and asks the owner if a login check,
  captcha or "unusual activity" page appears. A request for ban-avoidance
  tactics was declined.
- This changes parts of the design above: the "API client" steps become a
  browser driver (Playwright on the PC, one browser profile used only for
  this), the cost cap becomes a turn and time cap (for the websites; the
  API adapters added later have the monthly money limit above), and the
  logged-in page's
  own history and Gemini's own memory of the account become a rule 1
  question - see the account question below.

## Questions for the owner

1. **How should Jarvis reach the chatbot?**
   - **Through its official API with a key** (recommended): cents per
     session, allowed by the terms, rarely breaks.
   - **Through the website, logged in as you:** free with your plan, but
     against both companies' terms; the account could be banned (for
     Google, the whole account, Gmail included).
2. **Which chatbot first?**
   - **ChatGPT, through OpenAI's API** (recommended): not used for training
     by default.
   - **Gemini, through Google's paid API:** similar; a different key and bill.
   - **Gemini's free tier:** costs nothing, but Google may read these chats.

## Sources

[Open Terms Archive genai-versions](https://github.com/OpenTermsArchive/genai-versions)
(OpenAI Terms of Use, Google Terms of Service);
[Gemini pricing (CloudZero)](https://www.cloudzero.com/blog/gemini-pricing/);
[GPT-5 mini pricing](https://pricepertoken.com/pricing-page/model/openai-gpt-5-mini);
[Gemini API terms (Simon Willison)](https://simonwillison.net/2024/Oct/17/gemini-terms-of-service/);
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data);
[ChatGPT web bridge ban report](https://github.com/Wladefant/super-board/issues/276);
[Playwright blocked on ChatGPT](https://community.latenode.com/t/playwright-automation-getting-blocked-by-cloudflare-when-accessing-chatgpt/21831).

---

## Ask several and compare (2026-09-28)

Status: **built on the backend and both apps; not yet tried against the
real sites** (like everything above). The owner's decision (CLAUDE.md,
"The chatbot driver becomes versatile", point 4): "compare: ask several AIs
the same question, one card listing every AI it will ask, one summary of
agreements, disagreements and sources." Routes and fields:
`docs/JARVIS-API.md` section 87.7.

### In plain words

Tick "Ask several and compare", pick two or more chatbots, type the goal
once. ONE approval card lists every chatbot Jarvis would ask, the goal word
for word and the limits. On a yes, Jarvis holds an ordinary conversation
with each chatbot in turn - the same rules as one conversation, nothing
loosened - and at the end its own model on the PC writes ONE summary: where
they agree, where they disagree (and which chatbot said what), the sources
each gave (not checked by Jarvis), what is still open, and which chatbot
dropped out and why.

### How it fits what is already built

- **Each chatbot gets an ordinary conversation.** `jarvis_chatbot_compare.py`
  plans one `jarvis_chatbot.Session` per chatbot with `jarvis_chatbot.plan()`
  and runs each with `jarvis_chatbot.run()`. So every message to every
  chatbot goes through the same `last_check()` just before it is sent, with
  the same never-send words, and each driver sees only the goal and THAT
  chatbot's replies - the chatbots never see each other's answers, and
  nothing private is ever in the context (rule 1).
- **One card, the same kind.** Gate action `chatbot_session`, tier `ask`
  only, risky (Windows Hello on the PC, a screen lock on the phone), no
  "always allow". The card lists every chatbot by name and address.
- **One after another**, on one card and on two: one browser window at a
  time, and on one card the model writing the follow-ups is the owner's own
  chat model, which already waits while the owner chats.
- **A chatbot that cannot go on is left out**, not paused for: an error, no
  reply, two blocked messages, a question about the owner, or a captcha /
  sign-in / "unusual activity" page (never solved or skipped). A single
  conversation pauses and asks at those pages; in a comparison that would
  hold up every other chatbot, so the card says it will be left out, and the
  summary says who and why (plain words from the backend, not the model).
- **Pause / Resume / Stop act on the whole comparison.** It is one
  `jarvis_task_control` task (tool `chatbot_compare`), so the existing Pause
  and Resume (one card) work unchanged; Stop, the task Stop and Stop
  everything end every conversation in it, and the chatbots not asked yet
  are never opened.
- **The summary** is written once, by the local model, from the chatbots'
  replies only (each conversation under its name), with no tools. Its
  `who` names are checked against the chatbots asked (anything else is
  dropped); its sources are the web addresses found in each chatbot's own
  replies by plain code, plus those the model lists - none opened, none
  checked. It is outside text: never learned from, never read aloud. On one
  card it waits for the owner's chat like a single conversation's summary.
- **Kept in memory only**, like single conversations: a backend restart
  loses it.

### The limits (confirmed by the owner, 2026-09-28)

| | one graphics card | two graphics cards |
|---|---|---|
| chatbots per comparison | **2 to 3** | **2 to 4** |
| order | one after another | one after another |
| messages and minutes | the version's own, **for each chatbot** (one card: default 5, most 8 messages; default 10, most 15 minutes) | the version's own, for each chatbot (default 8, most 20 messages; default 10, most 30 minutes) |
| longest possible comparison | 3 x 15 = 45 minutes of conversation | 4 x 30 = 120 minutes |

Why these numbers: on one card the model writing the follow-ups is the
owner's own chat model, so three chatbots at up to 15 minutes each is
already a long wait; on two cards the driver is on the 12 GB card and never
slows the owner's chat, so one more is reasonable. Asking them side by side
(at the same time) on two cards is possible later, once the two-card
version is measured; it is not built. The numbers live in one place,
`jarvis_chatbot_compare.MAX_AIS`, and both apps read them from the PC
(`tier.compare_min` / `compare_max`).

### Not built, said plainly

- Changing the limits in the middle of a comparison (stop it and start a
  new one); starting a comparison by saying it; side-by-side asking on two
  cards; keeping comparisons in the encrypted chat history.
- The summary's quality depends on the local model (Qwen 3 8B on one card);
  it has not been measured on real chatbot answers.

---

## Customer-support chats (design, 2026-09-28)

Status: **designed, not built.** The owner's decision of 2026-09-28 in
`CLAUDE.md` ("Customer-support chats"). Written by the studio's designer.
Most web facts below are **unverified**: the container could not reach
groupon.com, tosdr.org or the widget makers' live pages.

**Three things to know first.** The shared website base does not exist yet
(`GeminiWeb` holds everything; the website-adapters builder is pulling it
out). Today's `last_check` blocks almost every detail a support chat needs
(emails, phone numbers, long numbers, addresses), so support mode needs "hide
the approved details, then check the rest". Groupon's terms reportedly forbid
automated access (search summary only), and here the risk lands on the
owner's **real** account.

### 1. How this differs from the AI-chatbot mode

| | AI-chatbot mode | Support mode |
|---|---|---|
| Account | a spare account used only by Jarvis | **the owner's real account** (orders, vouchers, money) |
| The other side | a program | a company, often a real person |
| What can go wrong | a wrong answer | **a promise made in the owner's name** |
| Personal details | none ever sent | **the listed details only**, per chat |
| Record | memory only today | **kept in the encrypted chat history** as evidence |

**Rule 1 is bent per chat, for the listed values only** - like the locked
backup and a project's Shareable switch: the exact words are shown first and
nothing else goes. Written down as a named exception in ARCHITECTURE §2 rule
1 ("support-chat details"), a new §4 row ("customer-support chat
(website)"), and an audit-log line `support.detail_sent` per value sent
(company, the detail's name, the time - **never the value**, which lives only
in the encrypted transcript).

### 2. Reaching the chat

Most support chats are a widget on the company's help page, made by a few
vendors whose structure is the same everywhere. **One general support-widget
adapter** (`jarvis_support_widget.py`) on the shared website base knows each
vendor from one table - Zendesk (`iframe[title*="Zendesk"]`), Intercom
(`iframe#intercom-frame`), LivePerson (`#lpChat`), Gorgias
(`#gorgias-chat-container`), Freshchat (`#fc_frame`), Salesforce (its
`embeddedservice_bootstrap` iframe - exact id a guess), Ada (a guess) - with
a fallback to standard page roles (`role="log"`, a text box, a "Send"
button); otherwise it pauses and says why. Everything inside each widget
(message box, Send, agent messages, queue position, "chat ended") is guessed
until checked on the PC with `py -3 jarvis_support_widget.py check <help
page>` (reads only, sends nothing). **Company presets** (Groupon, Amazon,
eBay, airlines, phone companies) only where they add something: the help
page address, extra hosts, or Amazon's in-house chat.

**How a chat starts:** a separate Jarvis browser profile for support chats,
in a visible window; the owner opens the help page and **signs in by hand**
(Jarvis never types, sees or keeps a password); a 2-factor code, security
question or identity check **pauses** and hands over to the owner; Jarvis
never clicks a link in the chat (it is handed to the owner); it stays on the
starting host plus the vendor's hosts; menu buttons inside the widget count
as messages and go through the same checks (one labelled with offer words
always raises a card). **Take over** in both apps pauses Jarvis so the owner
types in the window; Resume carries on, with the owner's messages marked as
theirs.

### 3. The details card

A short form: the company, the goal ("refund order 1234, the spa closed"),
and one row per detail - its name and exact value, typed by the owner, or
"find it for me" on a single row (Jarvis looks it up locally and uses it
only if the owner ticks what it found). Nothing is pulled in automatically.

**The card** (action `support_chat`, tier `ask`, risky: Windows Hello on the
PC, a screen lock on the phone) shows the company and host, the goal, **every detail word for word** under "Jarvis may give these,
and nothing else", the time limit, and "If you say no: no chat is started".
No "same as last time"; not on the PC-only loosen list.

**Refused outright:** rows named password, PIN, security answer, card number
or ID number; values shaped like a payment card number (13-19 digits passing
the card checksum), a full US Social Security number, or a secret.

**Last check, support version:** hide each approved value exactly as
written, then run today's `last_check` on the rest. Anything not on the card
still blocks; card numbers, passwords and full ID numbers block even when on
the card. The driver model gets the goal, the approved details and the
transcript only - no memory, no tools.

### 4. Writing in the owner's name (changed 2026-09-28)

~~A fixed opening line saying Jarvis is an AI assistant.~~ **The owner
removed it:** there is no opening disclosure line, and Jarvis writes in the
owner's name, like any message an assistant drafts for someone.

**What does not change:** Jarvis **never claims to be human**. If the agent
asks directly ("am I talking to a bot / a person / to Alex?" - caught by a
plain word match as well as the driver), Jarvis sends nothing, **pauses and
hands the question to the owner**, who answers in the window (owner,
2026-09-28). The driver's instructions forbid it from saying it is a person
or the owner "in person". If the agent refuses to continue, Jarvis stops and
offers Take over. The site's bot detection is never dodged either way.

### 5. Offers and promises

After every agent message two detectors look for an offer - the driver's new
`offer` move (refund, credit/voucher, cancellation, change of order or
address, "do you agree/confirm", a request for a new detail) and a plain-code
backstop (money amounts; refund, credit, voucher, cancel, confirm, agree,
accept). Either raises a card; if in doubt, a card.

**The offer card** (action `support_offer`, risky, one per offer) shows the
agent's exact words (outside text) and Jarvis's proposed reply word for word.
The owner picks **Accept** (the shown reply is sent), **Decline** ("Alex
would rather not; is there another option?"), **Say something else** (typed,
through the last check) or **Take over**. A request for a detail not on the
card gets its own card adding that one value. Jarvis never pays, never agrees
to terms, never accepts on its own.

**While a card waits:** a fixed holding line ("I'm checking with Alex, one
moment please") at most every 2 minutes, up to 3 times; then "Alex hasn't
answered yet; I can't accept anything without them" and a pause. Nothing is
accepted by default. **"Is there anything else?"** is not an offer: Jarvis
asks for a reference number and a written summary, then closes.

**Time:** waiting in a queue costs nothing (its own limit, default 45
minutes, at most 2 hours; the position is shown); the chat's limit starts at
the first agent message; a quiet agent gets one "Are you still there?" after
5 minutes, and a pause after 10 more; "chat ended" ends it with the summary.

### 6. Transcript

The company's words are outside text (`source: "support_transcript"`), never
learned from or read aloud. The whole chat is saved in the **encrypted chat
history** as a "Support chat" record (company, date, the details card, every
message with time and author, each offer card and answer, the reference
number); History search finds it. "Export transcript" is the owner's tap on
the PC, to a folder they pick, and says the file is not encrypted. Jarvis
never clicks the widget's "email me the transcript".

### 7. Legal and ethics (plain words, not legal advice)

- **Saying it is a bot:** California's SB 1001 covers bots used to push a
  sale or sway a vote; a buyer's assistant is probably outside it
  (**unverified**). There is no opening line (the owner's choice), but
  Jarvis never denies being a bot: a direct question goes to the owner.
- **Saving the transcript:** saving your own text chat is generally not
  "recording" under US law (**unverified**; state laws differ).
- **Terms of service:** Groupon's terms reportedly forbid access "using any
  robot, spider, scraper, or other automated means" (search summary; the
  page was blocked). **The owner's real account could be closed**, unused
  vouchers with it.
- **What the owner agrees to through Jarvis binds the owner** - hence a card
  for every offer.

### 8. Both apps; one or two graphics cards

Both apps use the `/api/chatbot/*` routes with `"mode": "support"`: start,
approve cards, watch, Pause, Stop, Take over, export. **One-sided on
purpose** (ARCHITECTURE §8): signing in and 2-factor codes happen in the PC
window. The phone's ongoing notification reads "Chat with Groupon: offer
waiting". **One card:** basic chats (goal, details, last 6 turns; the offer
backstop is plain code, so a small model cannot miss an offer; a support
reply goes ahead of the owner's own chat for its few seconds). **Two cards:**
the whole transcript, several problems in one chat, the owner's chat never
delayed - on once the second card is measured.

### 9. Risks

An account is closed (§7). An offer is missed (two detectors; only an offer
card can send an accepting reply). The agent asks for a card number or
password (refused by the form and the last check; handed to the owner).
Tricks written into the chat (no tools, nothing private to leak; the
injection detector warns). Sign-in cookies for real accounts in the Jarvis
profile ("Forget my sign-ins" button; App lock covers the screens). The
widget changes its layout (the general check, then a pause with a reason).

### The owner's answers (2026-09-28)

- **Jarvis sends the messages itself** (human speed, never dodging bot
  detection; no opening AI line - see §4), and each
  support card names that company's terms risk before the owner approves.
- **Identity checks are always handed to the owner** (last four digits of a
  card, security questions, codes) - never answered by Jarvis, never on a card.

### 10. Build plan (each step tested on 127.0.0.1)

1. The shared website base out of `GeminiWeb` (Gemini's tests still pass).
2. The support last check (planted card numbers, SSN-shaped numbers,
   passwords, unlisted emails all blocked; listed values pass).
3. Fake widget pages per vendor plus an unbranded one: queue, bot-to-human
   handover, menu, cross-host iframe, "chat ended", a quiet agent.
4. "Are you a bot?" caught and handed to the owner; the driver never claims to be human.
5. Offer detection over 100 written agent lines; the offer card, holding
   lines and time-out.
6. The encrypted transcript and export; the learner test shows nothing learned.
7. Routes, both apps, docs, ARCHITECTURE §2/§4/§8; `check_parity.py` clean.
8. The owner's `check` on Groupon's real help page (reads only), then one real chat.
9. The new-feature audit.

Sources: Zendesk Messaging Web Widget cookbook; "How to detect if a website
uses Intercom" (DEV); LivePerson engagement window docs; Gorgias chat HTML
snippets; freshworks/freshchat-widget; Salesforce Embedded Service guide;
Groupon support FAQ and Terms of Use (blocked here; search summary); SB 1001
text and Perkins Coie's summary.
