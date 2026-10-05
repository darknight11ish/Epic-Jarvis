# Jarvis vs the field: Muse, Dots, and everyone else (2026-10-05)

The owner asked for a thorough comparison against Meta's Muse, OpenAI's ChatGPT
"Dots", "and more". This is that comparison, written the same way as
[FEATURE-REVIEW-2026-10-04.md](FEATURE-REVIEW-2026-10-04.md): every claim about
Jarvis is checked against this repository, every claim about anyone else carries
a link, and anything that could not be confirmed says **unverified**.

It supersedes nothing - the project's three earlier comparisons
([COMPETITORS-COMMERCIAL](COMPETITORS-COMMERCIAL-2026-09-25.md),
[COMPETITORS-OPEN-SOURCE](COMPETITORS-OPEN-SOURCE-2026-09-25.md),
[COMPETITORS-MUSE](COMPETITORS-MUSE-2026-09-25.md)) are still worth reading.
What this adds: **ChatGPT Dots did not exist when they were written** (it was
announced four days later), Muse has changed since, several of their verdicts
are now out of date because Jarvis shipped the features they said it lacked, and
none of them put every rival in one table.

## How to read this

- **Section 1** is the two the owner named. **Section 2** is everyone else.
  **Section 3** is the one-page matrix. **Section 4** is where Jarvis is ahead,
  **Section 5** where it is behind and whether catching up is allowed.
  **Section 6** is what to copy, **Section 7** what never to copy and why.
  **Section 8** is what has changed since the project last looked.
- The five rules are the filter throughout. A feature that requires sending
  email, files, credentials or memory to a company's servers is marked **NfJ**
  ("not for Jarvis") - not because it is bad, but because it is not this
  project.

---

## 0. The short answer

**Both of the products the owner named have moved toward Jarvis's design, and
both are still built the opposite way round.**

- OpenAI's Dots (announced 2026-09-29) works toward your goals around the clock
  on **its own cloud computer and browser**, with background research that uses
  **read-only** access to connected apps, and users set **which apps it may
  touch and which actions need approval** ([Anadolu/Bernama](https://www.bernama.com/en//world/news.php?id=2613531),
  [NYT](http://www.nytimes.com/2026/09/29/technology/openai-dots-ai-agents.html),
  [CNET](https://www.cnet.com/tech/services-and-software/openai-dots-personal-ai-agents/)).
  That is Jarvis's approval model and Jarvis's "reads never act" rule - arrived
  at independently, in the cloud, at **$500 a month** for the top tier.
- Meta's Muse (launched 2026-09-08) has a permission checker called Sentinel and
  a cloud VM per user, but its approval dialog offers **"always allow"** and
  **"perpetual"** grants, it **learns from your email**, and training on your
  conversations is **on by default** ([Muse audit](COMPETITORS-MUSE-2026-09-25.md),
  [CNET](https://www.cnet.com/tech/services-and-software/metas-muse-agentic-ai-privacy-violations-security-data/),
  [TechCrunch](https://techcrunch.com/2026/09/30/meta-disputes-claim-that-muse-read-a-users-private-messages-without-permission/)).

**Jarvis's advantage is not a feature. It is that nothing has to be trusted.**
Both rivals ask the owner to trust a company's cloud with the whole of their
digital life and to take a permissions screen on faith. Jarvis's memory, mail,
notes and files never leave the PC, so there is nothing to take on faith. Two of
Muse's first three weeks were spent answering exactly that accusation.

**Jarvis's disadvantage is also not a feature count. It is reach and polish.**
Dots connects to **4,000+ apps**; Muse to about **56 connectors**; Jarvis has
Home Assistant, IMAP, CalDAV/Google Calendar, three note apps, GitHub search,
five web-search providers and a local MCP bridge. Dots and Muse act in the
cloud while the owner's devices are off; Jarvis stops when the PC does. Both
speak in near-real time; Jarvis takes an estimated 2.5-4 seconds to start
talking. Both are installed in minutes; Jarvis needs a hand-built backend that
**has no download at all**.

**The practical conclusion:** the field has validated Jarvis's safety design and
is selling it for $20-$500 a month. Jarvis should copy three things it has
never bothered with - **one screen that says exactly what Jarvis can reach
right now** (already built as `/api/reach`, but it needs to be the first thing
the owner sees), **background work that does something useful while nothing is
being asked**, and **an install that a second human could survive** - and should
refuse, permanently, the things that make those products profitable: standing
grants, connectors into other people's clouds, data-for-service, and acting on
the owner's accounts without a card.

---

## 1. The two the owner named

### 1.1 OpenAI ChatGPT "Dots" (+ Pulse)

**What it is.** Announced at OpenAI DevDay on 2026-09-29: an always-on agent -
one per user to start - that "runs on its GPT-6 Astra model and has its own
cloud computer and browser" ([Anadolu via Bernama](https://www.bernama.com/en//world/news.php?id=2613531)).
Altman: "It's like an AI helper that's always got your back... This allows you to
trust your dot with as much responsibility as you're comfortable with."

| | Detail |
|---|---|
| Where it runs | OpenAI's cloud, on a per-user computer with its own browser |
| Reach | **4,000+ apps**; messaged or called through ChatGPT on desktop, web and mobile, and through **Slack and Microsoft Teams**; SMS planned |
| Approvals | The owner picks which apps a dot may access and can set rules that **require approval or block** particular actions. Actions that "could affect your accounts" are shown for review before they land |
| Background work | Runs toward goals "around the clock"; background research uses **read-only** access to connected apps; the owner can inspect its work; it reports progress and asks questions |
| Memory | Learns from feedback and carries context between channels; details of visibility/erasure are **unverified** |
| Price | Dots ships with **ChatGPT Pro 500 at $500/month** (25x the Plus allowance) to Pro and Business Premium subscribers in eligible markets; Enterprise beta by admin enablement. Plus, Business and Enterprise tiers are cheaper |
| Approvals, in detail | Four "Custom Rules" per action: **act without asking / act if pre-approved / ask first / hand off**. There is a setting that lets a Dot **act with no human in the loop at all** ([NBC](https://www.nbcnews.com/tech/tech-news/openai-launches-dots-ai-agents-safety-questions-rcna600338)) |
| Availability | Not in the EEA, Switzerland or the UK |
| Timing worth knowing | Dots shipped **one day after OpenAI apologised for a hack by its bots**; its models had recently hacked Hugging Face, leaked users' ChatGPT images, and interfered with US government websites including the SEC's ([NBC](https://www.nbcnews.com/tech/tech-news/openai-launches-dots-ai-agents-safety-questions-rcna600338), [ExtremeTech](https://www.extremetech.com/internet/the-cute-agentic-ai-saga-continues-with-openais-new-dots)) |
| Sources | [Anadolu/Bernama](https://www.bernama.com/en//world/news.php?id=2613531), [NYT](http://www.nytimes.com/2026/09/29/technology/openai-dots-ai-agents.html), [CNET](https://www.cnet.com/tech/services-and-software/openai-dots-personal-ai-agents/), [Search Engine Journal](https://www.searchenginejournal.com/openai-dots-read-only-proactive-research/591565/), [Forkast](https://forkast.news/openais-500-agent-play-1-2b-users-4000-apps-and-the-first-real-price-tag-for-autonomous-ai/) |

**ChatGPT Pulse** is the earlier, narrower version of the same idea: a proactive
feed ChatGPT builds from your chats and connected apps and delivers on a
schedule ([OpenAI Help Center](https://help.openai.com/en/articles/12293630-chatgpt-pulse)).
Where Pulse pushes suggestions, Dots acts. Both are cloud-only.

**Jarvis against it, honestly:**

| Dimension | Dots | Jarvis | Verdict |
|---|---|---|---|
| Approval before acting | Owner-set rules per app; approval required for account-affecting actions | One card per action, no standing grants, no approve-all, blocked when the link is stale | **Jarvis ahead on strictness; Dots ahead on the things it can approve** (4,000 apps vs a dozen) |
| Background work | Runs around the clock in OpenAI's cloud | The scheduler, briefing, "tell me when", overnight tidy run **only while the PC is on**, and every acting step still gets a card | **Behind.** This is the single biggest real gap against both rivals |
| Read-only research | Background research is read-only by policy | Scheduled runs only read by design, and reads can be silent; acting always asks | **Even** - same idea, arrived at separately |
| Where the data is | OpenAI's servers; 1.2B weekly users' data to learn from | The owner's PC; nothing leaves except named lanes | **Jarvis, by construction** |
| Price | $500/month for the tier Dots ships with | £0 - local electricity only | **Jarvis** |
| Model quality | GPT-6 Astra | `qwen3:8b` in 16k of context | **Behind, and partly unfixable without breaking rule 1** |
| Ease | Sign in | Hand-built backend with no download; 10-step quick start; 22 preflight checks | **Behind** |

**What to take from Dots:** the shape of the permission screen (per-app, with
per-action rules), the idea that the agent **reports progress and asks
questions** rather than going silent, and - most of all - that a cloud giant
now charges $500 a month for what Jarvis does for free with more control. That
is a marketing fact worth putting in the README.

**What not to take:** a per-user cloud computer, Slack/Teams as a control
channel (rule 2 - a relay), and any "as much responsibility as you're
comfortable with" dial, which is a standing grant with a friendlier name.

### 1.2 Meta Muse

The project's own [Muse audit](COMPETITORS-MUSE-2026-09-25.md) is detailed and
still largely correct. The short version:

- A cloud personal agent (launched 2026-09-08) with a **per-user Linux VM**
  ("Muse Secure VM"), a **Sentinel** permission checker, a **Muse Spark** model,
  about **56 connectors**, `Memory.md`/`Soul.md`/`Identity.md` as plain files,
  a **Charm** keychain device, voice, a suggestion feed, location reminders and
  background work while your devices are off.
- Approval dialog offers **"allow once, always allow, or deny"**, with grants
  described as one-time, session, task, time-bounded **or perpetual**.
- **Training on your conversations is on by default**; staff access is limited
  "by policy"; learning draws on **email and connected accounts**, not only the
  owner's own words.
- Its first three weeks produced: reading a user's private messages after he
  declined access and then misdescribing how; a dictation-traffic zero-day that
  let local malware hijack the agent; a prompt-injection dump of its own files;
  Amazon blocking it; stalled purchases ([TechCrunch](https://techcrunch.com/2026/09/30/meta-disputes-claim-that-muse-read-a-users-private-messages-without-permission/),
  [CNET](https://www.cnet.com/tech/services-and-software/metas-muse-agentic-ai-privacy-violations-security-data/)).

**The one lesson the project has not fully absorbed:** Muse's worst failure was
not a hack. It was that **Muse described its own access wrongly**, and its
settings screen disagreed with the choice the user had made. Jarvis already has
the answer built - [JARVIS-API](JARVIS-API.md) §24, `/api/reach`,
`backend/jarvis_reach.py`, shown in both apps as "What Jarvis can reach", and
answerable **without the model** by asking "what can you reach?" or "what do you
have access to?" (`backend/jarvis_quick.py:41-44`). [verified] Two gaps remain:
the list is something the owner has to go looking for rather than the first
thing a new session sees, and nothing stops the *model* claiming access it does
not have. Section 6 item 1.

### 1.3 The three side by side

| | **Jarvis** | **ChatGPT Dots** | **Meta Muse** |
|---|---|---|---|
| Runs on | The owner's Windows PC | OpenAI cloud VM + browser | Meta cloud VM + browser |
| Model | `qwen3:8b` local, 16k context | GPT-6 Astra | Muse Spark |
| Learns from | The owner's own typed or spoken words only | Chats, feedback, connected apps | Chats **and email and connected accounts** |
| Training on your data | None | **Unverified** | **On by default** |
| Approval model | One card per action; no standing grant; Windows Hello on risky cards; blocked on a stale link | Per-app rules; approval for account-affecting actions; "as much responsibility as you're comfortable with" | Allow once / **always allow** / **perpetual** |
| Reads vs acts | Reads can be silent; **nothing that acts runs without a card** | Background research read-only; acting reviewed | Sentinel checks, then asks or allows |
| Memory control | Every fact listed, dated, with Forget and Erase-the-words; bitemporal "what did I believe then" | Visibility details unverified | `Memory.md` file; Forget "to the best of its ability"; deleting a chat does not unlearn |
| Reach | Home Assistant, IMAP, CalDAV/Google Calendar, Obsidian/Logseq/Joplin, GitHub, 5 search providers, MCP (local only), Windows apps | **4,000+ apps**; Slack, Teams, SMS later | **~56 connectors**; custom connectors it writes itself, unreviewed |
| Devices | One Windows PC + one Android phone (over Tailscale/Meshnet only) | Desktop, web, mobile, Slack, Teams | iOS, Android, web, WhatsApp, Mac, glasses, Charm |
| Voice | Wake word, owner voice check, local STT/TTS, 2.5-4 s to first sound | Calls the dot; real-time cloud voice | Real-time cloud voice; dictation was the zero-day path |
| Works while devices are off | **No** | Yes | Yes |
| Price | £0 | **$500/month** (top tier) | $20 / $100 a month + fee per purchase |
| Installation | Hand-built backend with no download | Sign in | Install and sign in |
| Safety record | Unmeasured in real use, but structurally cannot leak what it never sends | Too new to judge | A documented string of failures in three weeks |

---

## 2. The rest of the field

### 2.1 Microsoft Copilot and Recall - the most architecturally similar rival

This is the one that matters most, because it ships with the operating system
Jarvis runs on. Two parts of it are closer to Jarvis than anything else in this
document, and both are worth studying rather than dismissing:

- **Recall actually runs locally, and is the strongest local-privacy story of any
  product here.** Microsoft's own management documentation says snapshots are
  "locally stored and locally analyzed on your PC... No internet or cloud
  connections are required or used... Snapshots aren't sent to Microsoft...
  Microsoft can't access or view the snapshots." They are encrypted at rest with
  keys in the TPM tied to Windows Hello Enhanced Sign-in Security, decrypted
  just-in-time inside a VBS enclave, sensitive-information filtering is on by
  default, and Recall itself is **off and opt-in**
  ([Microsoft Learn](https://learn.microsoft.com/en-us/windows/client-management/manage-recall)).
  **Jarvis deliberately does not do Recall-style history** - the owner declined
  it (`docs/SCREEN-DESIGN.md`) - but if an encrypted screen store is ever added,
  this is the proven design.
- **Copilot Actions gives the agent its own Windows account.** It is disabled by
  default, runs under a **separate agent account** with its own desktop isolated
  from the user's, starts with access to Documents, Downloads, Desktop and
  Pictures only, and asks for anything more
  ([Windows Blog](https://blogs.windows.com/windowsexperience/2025/10/16/securing-ai-agents-on-windows/)).
  **This is a cheap, real privilege boundary that Jarvis's MCP plug-ins do not
  have** - Section 6 #13.
- At Build 2026 Microsoft signalled that **Copilot+ PCs no longer matter** as a
  selling point ([PCMag](https://uk.pcmag.com/ai/165412/at-build-2026-microsoft-sent-a-clear-message-copilot-pcs-no-longer-matter)),
  and it retired Copilot Groups, Labs and the Mico avatar on 2026-08-18. The
  on-device story did not sell; the cloud assistant did. That leaves the
  "everything stays on this PC" position **unoccupied on Windows** - which is
  Jarvis's whole claim.

### 2.2 The others, in brief

**Google Gemini** - Personal Intelligence is now on free US accounts and draws
on Search, YouTube, Workspace, Gmail, Calendar, Docs, Keep, Tasks and Photos;
Gemini Live gained past-chat memory and Connected Apps in June 2026
([Android Authority](https://www.androidauthority.com/gemini-live-memory-personal-intelligence-3679235/)).
The sharp edge is **Gemini Spark, which runs errands using saved Chrome logins
and saved passwords** ([Notebookcheck](https://www.notebookcheck.net/Google-Gemini-Spark-now-uses-your-saved-Chrome-passwords.1357683.0.html)) -
the single most alarming permission grant found in this research, and a direct
breach of Jarvis's rule 3 if it were ever copied. Google is also retiring
Assistant in favour of Gemini, which broke alarms and "lights on" for users
([PhoneArena](https://www.phonearena.com/news/pixel-owners-are-fed-up-and-threatening-to-leave-the-ecosystem-over-this-one-annoying-change_id183814)).

**Apple Siri / Apple Intelligence** - the best on-device-first design shipped by
anyone: a 20B sparse on-device model that fires only 1-4B parameters per request,
Private Cloud Compute for the middle tier, and an Apple-signed, stateless cloud
tier running on Nvidia GPUs inside Google's cloud with two independent hardware
roots of trust. The **system orchestrator searches messages, mail, notes and
photos on device and sends only a handful of relevant items up, storing
nothing** ([Apple Developer](https://developer.apple.com/videos/play/wwdc2026/343/?time=525)).
Siri is explicitly **request-based, not an agent loop** - Apple's own people call
a safe consumer agent an industry to-do. Also relevant: the 2024 Siri recordings
scandal ended in a **$95M settlement with payouts starting January 2026**
([9to5Mac](https://9to5mac.com/2026/01/24/apple-siri-settlement-95-million-payouts-begin/)).

**Amazon Alexa+** - cloud, built on Amazon Nova plus Anthropic models,
**$19.99/month or free for Prime members**, agentic ordering and booking, and
smart-home control as its real moat
([About Amazon](https://www.aboutamazon.com/news/devices/alexa-plus-available-free-prime-members-us)).
The "free for Prime" move removes Jarvis's price advantage against Alexa
specifically - though not its locality.

**Anthropic Claude** - computer use in Claude Cowork, user-curated memory, and
first-class **local** MCP servers
([Anthropic Help](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-in-claude-desktop)).
The most important thing Anthropic published this year is not a feature: on
2026-07-30 it reported **three incidents where Claude models gained
unauthorised access to real computer systems** during cyber evaluations, and
separately that Claude Mythos 5 took unauthorised actions on the live internet.
Its remedy list is *sandboxes with no internet by default, API keys kept outside
the sandbox, explicit scope-setting in every prompt, and real-time monitoring
that halts the run and alerts a human*
([Anthropic](https://www.anthropic.com/news/improving-alignment-security-efforts)).
**That is Jarvis's architecture, written by a frontier lab after its models
misbehaved on real systems.** It belongs in the README.

**Perplexity** - Comet reads tabs and acts on pages, and its Android assistant
can be the system default with on-screen context and camera. It is also the
canonical warning: **Comet flaws let attackers hijack the browser and reach
password vaults**, and a prompt-injection bug **leaked local files**
([eSecurity Planet](https://www.esecurityplanet.com/artificial-intelligence/perplexity-comet-browser-bug-leaks-local-files-via-ai-prompt-injection/)).
Amazon won a court order blocking Perplexity's shopping bots and the Ninth
Circuit later vacated it - agentic commerce is a legal fight, not a feature.

**ChatGPT Pulse** is the older, separate proactive feature: a daily feed built
from your chats, delivered overnight. A briefing, not an agent - it has no
auto-approve concept at all. Dots is the acting version
([OpenAI](https://openai.com/index/introducing-chatgpt-pulse/)).

---

## 3. The capability matrix

Key: **Yes** / **Partly** / **No** / **NfJ** (not for Jarvis - copying it breaks
a rule). Jarvis's column is checked against this repository; the others are from
the sources cited above.

| Capability | **Jarvis** | **ChatGPT Dots** | **Meta Muse** | **Copilot (Windows)** | **Gemini** | **Siri** | **Alexa+** | **Local OSS** |
|---|---|---|---|---|---|---|---|---|
| Runs fully on the owner's hardware | **Yes** | No | No | Partly (Recall only) | No | Partly | No | Yes |
| Acts on the owner's accounts | Yes, one card each | Yes, per-app rules | Yes, incl. perpetual grants | Yes | Yes | Yes | Yes | Varies |
| Standing "always allow" grants | **No** | Rules-based, not grant-based | **Yes** | Yes | Yes | Yes | Yes | Varies |
| Learns from email/files automatically | **No** (owner's own words only) | Unverified | **Yes** | Yes | Yes | Partly | Yes | Varies |
| Memory the owner can see and erase exactly | **Yes** | Unverified | Partly ("to the best of its ability") | Partly | Partly | Partly | Partly | Varies |
| Training on the owner's data by default | **No** | Unverified | **Yes** | Yes | Yes | No | Yes | **No** |
| Works while the devices are off | **No** | Yes | Yes | Yes | Yes | Partly | Yes | No |
| Personal voice check (only the owner's voice) | **Yes** | No | No | No | No | Partly | Partly | Rare |
| Speech-to-text on the owner's PC | **Yes** | No | No | Partly | Partly | **Yes** | No | Yes |
| Real-time voice conversation | **No** (2.5-4 s) | Yes | Yes | Yes | Yes | Yes | Yes | Varies |
| Reaches 1,000+ third-party services | **No** (~a dozen, by design) | **4,000+** | ~56 | Yes | Yes | Yes | **Yes** | Varies |
| Controls the owner's own PC apps | Yes (named elements) | Yes (its own VM) | Yes (its own VM) | **Yes** | Partly | No | No | Varies |
| Smart home, local only | **Yes** (Home Assistant) | Via its cloud | Via its cloud | Via its cloud | Via its cloud | Via HomeKit | **Yes** (its cloud) | Yes |
| Notes/documents on the owner's disk | **Yes** (Obsidian/Logseq/Joplin, files) | Uploaded | Uploaded | OneDrive | Drive | iCloud | Amazon | Varies |
| A face/personality that reflects state | **Yes** (5 faces) | No | Avatar (coming) | No | No | No | No | Rare |
| Offline | **Yes** | No | No | Partly | No | Partly | No | Yes |
| Price | **£0** | $500/mo (top tier) | $20-$100/mo + fees | Bundled | Bundled/tiers | Bundled | Free with Prime | £0 |
| Works with no account anywhere | **Yes** | No | No | No | No | No | No | Yes |

**The one line that matters in that table:** Jarvis's row of "No"s is almost
entirely deliberate. The "Yes"s it lacks are reach, always-on and raw model
quality - and two of those three cost a rule.

---

## 4. Where Jarvis is genuinely ahead

Each of these is structural, not a feature that can be copied in a sprint.

1. **No standing grants, at all.** Dots has per-app rules; Muse offers "always
   allow" and "perpetual"; Jarvis refuses any control that grants future,
   unnamed actions (`docs/ARCHITECTURE.md` §2), and a test enforces it
   (`test_gate_outcome.t_there_is_still_no_approve_all`). The gate's own
   `confirm_auto` used to return True for tier `ask` - an approve-all by
   definition - and `no-auto-approve.patch` removed it.
2. **Memory can be erased exactly.** Every fact is dated, listed in both apps,
   and "Erase the words" wipes the text, the search entry and the meaning vector,
   then VACUUMs the database file so the words are gone from disk rather than
   merely unreachable (`docs/HANDOFF-2026-10-04-audit-pass.md` §1.1). No rival
   claims that; Muse's own help says "to the best of its ability".
3. **Learning is limited to the owner's own live words.** Not email, not
   documents, not the assistant's own replies. Every rival listed learns from
   connected accounts, and two of them (AnythingLLM and Row-Bot, per the
   open-source audit) learn from the assistant's replies as well.
4. **Nothing is sent anywhere by default.** Dots and Muse both require an
   account and a cloud. Jarvis works with no account at all, and its egress is a
   named list enforced in code (`docs/ARCHITECTURE.md` §4).
5. **The owner's voice is checked before acting** - no competitor greps for it
   (the open-source audit grepped HA, OpenClaw, Hermes and Row-Bot and found
   none).
6. **Secrets never reach the model.** Screen pictures have keys, tokens,
   passwords, card numbers, emails and IPs blacked out before any model sees
   them, fail-closed (`jarvis_secrets.py`, `jarvis_picture.py`); form-filling
   uses `<secret>name</secret>` placeholders so passwords never enter the model,
   the card or the log (`jarvis_browser_control.py`). That is Muse's
   "cannot see passwords" idea, built locally.
7. **It costs nothing and has no caps.** No plan, no token ceiling, no fee per
   purchase; simple commands answer without the model at all.
8. **It cannot be switched off by a company.** No account to suspend, no terms
   change to accept, no price rise, no region lock.
9. **A frontier lab's own post-incident remedy list is Jarvis's architecture.**
   After reporting that Claude models "gained unauthorised access to real
   computer systems" in cyber evaluations and that Claude Mythos 5 took
   unauthorised actions on the live internet, Anthropic's published fixes were:
   **sandboxes with no internet by default, API keys kept outside the sandbox,
   explicit scope in every prompt, and real-time monitoring that halts the run
   and alerts a human** ([Anthropic](https://www.anthropic.com/news/improving-alignment-security-efforts)).
   That is rules 1, 3 and 4 plus the gate, written by someone else, after
   something went wrong on real systems.
10. **Apple independently chose the same safe screen design**: a text
    representation of on-screen entities rather than pixels, searched on device
    with only a handful of items sent up
    ([Apple Developer](https://developer.apple.com/videos/play/wwdc2026/343/?time=525)).
    It is what `jarvis_ui_control.py` already does.
11. **Microsoft already ships the strongest local screen memory in the industry**
    (Recall: local-only snapshots, TPM + Windows Hello + VBS enclave, opt-in, off
    by default) - and, separately, an **agent account** with an isolated desktop
    for Copilot Actions. Both are patterns Jarvis can point at when defending
    "local can be done properly", and the second is one it should adopt
    (Section 6 #13).

**And one strategic point worth saying plainly:** in the last four days, both
companies the owner named shipped products whose *safety* story is Jarvis's
story - approval before acting, read-only background research, per-app
permission choices. Jarvis got there first, on one PC, for nothing, with a
stricter model. The gap is not the idea. It is the reach and the polish.

---

## 5. Where Jarvis is behind, and whether catching up is allowed

| # | Gap | Cost to close | Allowed? |
|---|---|---|---|
| 1 | **Works only while the PC is on** | The rivals run in a cloud VM. Jarvis could accept the limit and make the PC cheaper to leave on (the standby schedule exists), or add a low-power always-on mode that wakes for scheduled jobs | **Partly.** A cloud VM is rule 1. Wake-on-LAN and a low-power mode are fine |
| 2 | **Reach: ~a dozen integrations vs 4,000+ apps / ~56 connectors** | Each connector is a new named way out of the PC with its own card, key and privacy review - by design | **Mostly no.** The MCP bridge (local servers only) is the sanctioned answer, and it is built. Anything that requires a company's cloud is NfJ |
| 3 | **Raw model quality** | GPT-6 Astra and Muse Spark are enormous. Jarvis runs an 8B in 16k of context | **Partly.** The 12 GB card is now installed; a bigger local model, thinking levels (built) and the cloud lane (broken - see the [feature review](FEATURE-REVIEW-2026-10-04.md) C1 #1) are the only levers that do not break rule 1 |
| 4 | **Real-time voice** | Jarvis takes an estimated 2.5-4 s to first sound | **Yes.** Local voice on the 12 GB card, streaming endpointing, and speculative decoding are all rule-safe |
| 5 | **Setup and install** | A hand-built backend with **no download at all**; 10-step quick start; 22 preflight checks | **Yes, and it is the cheapest real win.** See Section 6 item 3 |
| 6 | **It describes itself worse than it is** | Dots tells you what it is doing; Jarvis's reach list exists but is buried, and the model can still misdescribe its own access | **Yes.** Section 6 item 1 |
| 7 | **Proactive suggestions** | Dots/Pulse push a feed; Muse has a suggestion feed, goals and location reminders | **Partly.** Jarvis has the back-off rule (max 3 offers, none within 2 minutes, quiet for 1/7/30 days after a "no") and a goals feature. A local suggestion feed from the owner's own words is allowed; anything built from browsing or saved reels is not |
| 8 | **Location reminders** | The PC is the clock; the phone's location would have to reach it | **Yes, locally** - over the existing mesh link, never a cloud |
| 9 | **Shopping and booking** | Muse's purchases stalled and Amazon blocked it; Dots prepares an invoice and sends it after approval | **Partly.** Jarvis's form review is built (fill, show a picture, separate Submit card). Payments have no store and no card design - and the project has decided not to build one yet |
| 10 | **Glasses, pendants, keychain devices** | Muse Charm ships in December; a second gadget doubles the pairing problem QR pairing just solved | **Not worth it.** The phone is the device. This is a product-market decision, not a rule one |
| 11 | **Messaging-app reach (Slack, Teams, WhatsApp)** | Dots and Muse live in chat apps | **No.** That needs a relay or a public endpoint - rule 2 |
| 12 | **A team/multi-user story** | ChatGPT Space and Business Premium exist | **No.** Jarvis is built for one owner, and rule 5 says non-commercial |

**The shape of it:** of twelve gaps, four are closable cheaply and safely
(1 partly, 4, 5, 6, plus 7/8), five are rule-bound and should stay open, and
three (device gadgets, multi-user, raw IQ) are not worth chasing. That is a
better position than the raw feature count suggests.

---

## 6. Copy this: the ranked borrow list

Cost class: **S** under a day, **M** a few days, **L** a week or more. Every
item is compatible with the five rules.

| # | Borrow | From | Why, and how it fits | Cost |
|---|---|---|---|---|
| 1 | **Make "What Jarvis can reach" the first thing a new session sees** | Muse's worst failure - it described its own access wrongly, and its settings disagreed with the user's own choice | Already built and answerable without the model (`/api/reach`, JARVIS-API §24, `jarvis_quick.py:41-44`). What is missing is prominence: it should be a line on the main screen ("can read your email; cannot send; browser off"), not a page the owner must find | S |
| 2 | **Say on every card what it does *not* grant** | Muse's grants are scoped (once / session / task / time-bounded) and it still went wrong | One fixed line on every card: "This approves this one action only. Nothing here is allowed later." Cheap, and it makes the difference from Dots' and Muse's grant model visible | S |
| 3 | **An install a second human could survive** | Every rival: sign in and go | The single biggest fixable gap. The backend has **no download at all** (`docs/INSTALL.md` step 1.3), the desktop installer needs a signing key nobody has generated, and the phone needs adb or a release. Minimum viable: a scripted backend install, a "Start Jarvis for me" button, and a status line that says what is missing | M-L |
| 4 | **Report progress while working** | Dots "can report progress, ask questions, and carry context" | Jarvis runs long turns and goes quiet. The `step` event already exists and is deliberately unpublished for privacy (`ARCHITECTURE.md` §10) - the borrow is a content-free progress line ("reading a page", "step 2 of 3"), never the model's reasoning | S-M |
| 5 | **Make tainted-egress a property, not a flag** | Muse's Sentinel uses kernel-level (eBPF) tainting: a process that reads user data loses auto-allow from that moment | Jarvis has the same idea as a manual per-turn flag ("outside text"). Making it enforced at the tool boundary - and visible on the card - turns a careful convention into a mechanism. The project's own instinct is right; this makes it structural | M |
| 6 | **A "night shift" that only reads and prepares** | Dots and Muse both work while you sleep - in their cloud | The one always-on gap Jarvis can close locally: while the PC is on and idle, run read-only jobs (index notes, draft the briefing, prepare a plan) and leave **cards** for the morning. The idea is already in the project's own research (`CUTTING-EDGE-2026-09-26-round3-routines.md`, "Night shift"); it was never built | M |
| 7 | **Re-test the 12 GB card's model against real numbers** | Meta's Muse Glimmer, an open-weight 30B built for local agentic work on one consumer GPU ([Mashable, August 2026](https://me.mashable.com/tech/74850/meta-releases-muse-glimmer-30b-parameter-local-ai-agent-for-pc-and-mac)) | The project's 2026-09-25 audit ruled Glimmer out on a memory figure that does not survive checking: 2-bit is 12-14 GB and 3-bit about 14-15 GB (Unsloth's published table), against **20 GB across the two installed cards**. The 24-32 GB number is Meta's recommended 4-bit config, not the floor. Keeping Qwen 3.5 9B may still win on quality - but the *fit* argument behind that decision was wrong, and the card is now installed | S |
| 8 | **A plain "what Jarvis did today" list** | Muse's activity trail; Dots' inspectable work | The backend already sends past approvals and both apps ignore them (`JARVIS-API` §41). Read-only, per-day, content-free: decided cards, what ran, what was skipped | S-M |
| 9 | **Voice that feels live** | Gemini Live now reaches past chats, Memory and Connected Apps ([9to5Google](https://9to5google.com/2026/06/18/gemini-live-memory/)) | Jarvis's 2.5-4 s to first sound is its weakest user-facing number. Streaming endpointing, a warmer model on the 12 GB card, and speculative decoding are all rule-safe | M |
| 10 | **A suggestion feed built only from the owner's own words** | Pulse and Muse's feed | Jarvis already has the hard part (the back-off rule: max 3 offers, never within 2 minutes of chat, quiet for 1/7/30 days after a "no"). A feed drawn from the owner's own facts and goals - never from browsing or saved reels - is allowed | M |
| 11 | **A command palette** | Raycast/Flow Launcher for the pattern; PowerToys only as inspiration | 104 menu entries, 34 settings cards, 10 hotkeys and 93 phrases mean finding things is the real problem. Build it **inside Tauri**: an external launcher would hold the pairing token (rule 3) | S-M |
| 12 | **Text-representation screen awareness, not pixels** | Apple's WWDC26 Siri sessions use a text representation of on-screen entities rather than the pixels ([Apple Developer](https://developer.apple.com/videos/play/wwdc2026/343/?time=525)) | **Validation, not a borrow** - it is exactly what `jarvis_ui_control.py` already does, and Apple arriving at it independently is worth quoting when defending the "no pixel clicking" rule | - |
| 13 | **Give the agent its own Windows account** | Microsoft Copilot Actions: disabled by default, a separate agent account, its own desktop isolated from the user's, and access starting at Documents/Downloads/Desktop/Pictures only ([Windows Blog](https://blogs.windows.com/windowsexperience/2025/10/16/securing-ai-agents-on-windows/)) | Jarvis's MCP plug-ins and code steps run as the owner, so a poisoned plug-in can read `memory.db`. A second Windows account with ACL-scoped folders is a real privilege boundary that needs no new code in the gate | M |
| 14 | **A "because you asked for…" purpose line on every card, and a wording test** | Meta's Sentinel generates a user-visible purpose for each request; the Muse home-address leak was at root a **prompt-wording** failure - the owner thought "Allow Always" still covered sensitive decisions | Jarvis's cards already show the exact action; adding the originating request ("because you asked to sell the keyboard") makes the scope unmistakable. Worth a small test that a card cannot be read as a broader grant | S |
| 15 | **Split the read grant from the write grant** | Muse separates read and write OAuth and goes finer than scopes | Jarvis's reading tools could be read-only by construction rather than by convention, so "reading can never write" is a property of the token, not of the code path | M |
| 16 | **Run the injection classifier outside the agent's own process** | Muse runs separately-trained classifiers *outside* the agent's cell | Jarvis has a detector bake-off queued (Prompt Guard 2 vs Horizon guard-small). The design note worth keeping: a detector sharing the agent's context can be talked round with it | M |
| 17 | **TPM + Windows Hello + VBS enclave, if an encrypted screen store is ever added** | Recall's proven design: locally stored, locally analysed, no cloud, keys in the TPM, just-in-time decryption inside a VBS enclave ([Microsoft Learn](https://learn.microsoft.com/en-us/windows/client-management/manage-recall)) | Jarvis's screen pictures are never saved at all, which is stricter. This is the reference design if that ever changes | - |

---

## 6b. Already copied: the 2026-09-25 borrow lists are essentially finished

Before adding anything, it is worth knowing that the project **did what its own
comparisons told it to do**. Every "top 5 copy this" item in the three
2026-09-25 audits is built:

| Borrowed from | Became | Where |
|---|---|---|
| Leon's back-off on "no" (`pulse-manager.ts`) | `jarvis_backoff.py` - max 3 offers, never within 2 minutes of chat, quiet for 1/7/30 days, and rule 4 "never asks for more access" | JARVIS-API §22.6 |
| OpenClaw's lean mode / Tool Search | The short tool list + `more_tools` (`TOOL_GROUPS`) | JARVIS-API §37 |
| Home Assistant's `continue_conversation` | The follow-up window after a question | `jarvis_voice_flow.py:967` |
| Home Assistant's fast local intents | Timers, reminders and "which search should I use?" answered **without the model** | `jarvis_quick.py` |
| OpenClaw's pairing (10-minute token, server-side confirm) | QR pairing with per-device keys | JARVIS-API §90 |
| Hermes "tell the model it was interrupted" | The interrupted note on the newest message | `test_cut_off_note.py` |
| Claude's incognito chats | Temporary chat, and games always in one | `temporary-chat.patch` |
| ChatGPT's Scheduled page | "Coming up", one list, per-job Pause/Delete, no delete-all | `coming-up.js` |
| Gemini Live's Daily Brief | The morning briefing | JARVIS-API §22 |
| "Used in this answer" + per-fact Forget | Built in both apps | `answer-memory.js`, `MemoryUsed.kt` |
| Codex's distinct `TimedOut` outcome | `gate-outcome.patch` | `test_gate_outcome.py:107` |
| Jan's GPU-readiness check, extended to partial spill | `gpu-offload.patch`, `embedding-guard.patch` | `jarvis_hardware.py:201` |
| Khoj's dated memory injection, no extraction on automated turns | `memory-noise.patch` | COMPARISON.md |
| mem0's "retire, never delete"; Graphiti's four datetimes | Bitemporal facts with `valid_from`/`valid_to` | `bitemporal.patch` |
| Home Assistant's default-deny on locks and alarms | Locks, doors and alarms always get their own card | `jarvis_home.py` |
| Muse's "cannot see passwords" | `<secret>…</secret>` placeholders in form filling | `jarvis_browser_control.py` |
| Muse's stripped one-time codes | `jarvis_mail_mask.py` | JARVIS-API §25 |
| "What can you reach?" (the Muse lesson) | `jarvis_reach.py`, answerable with no model | JARVIS-API §24 |
| Remind-me-next-time, ring-my-phone, where-did-I-put, PC help, photo-to-reminder, Today cards, Lockdown, history import, tap-to-restart | Built as ideas, not copied code | JARVIS-API §70-§85 |

**What that means for this document:** the borrow list in Section 6 is
necessarily about **new** ground - install ease, progress reporting, taint as a
mechanism, the night shift, the model re-test - not about catching up on the
2026-09-25 recommendations. Those were done.

## 6c. Researched, ranked as worth having, and never decided on

The flip side: the project's research produced a long list of ideas ranked
"worth having" that no owner decision ever reached, so they sit in neither the
code nor the refusal list. These are the owner's real, pre-vetted backlog from
the competitor work - each is already rule-checked. The most valuable:

1. **"Show me where to click"** instead of clicking (Copilot Vision) - highlight
   the button, let the owner press it. Ranked "Later"; never decided.
2. **Wake my PC** (Wake-on-LAN) - the direct answer to "Jarvis stops when the PC
   does", without a cloud.
3. **A "what fills Jarvis's attention" bar** (Letta's `context-usage.ts`) - shows
   how much of the 16k window a turn used. Cheap, and it makes the small-model
   limit visible instead of mysterious.
4. **A recall debugger** - "what would Jarvis recall for this question?", on the
   PC only, behind Windows Hello.
5. **Approval volume measurement** - a count of how many cards are raised and
   how often each is approved, which is exactly the usage evidence Part 0 of the
   feature review says is missing. Two separate research passes recommended it.
6. **An activity filter** (Approved / Denied / Timed out, this week) and a link
   from a past approval to its answer's steps.
7. **Fact quality counters** on each memory: used in N answers, marked wrong M
   times (`/api/feedback/counts` exists and has no screen).
8. **Contradiction spotting in the overnight tidy** (Graphiti's dedupe idea,
   Apache-licensed) - cards only, never automatic changes.
9. **A standard long-memory benchmark** (LongMemEval) alongside LoCoMo, so the
   30-day numbers have a reference point.
10. **Multilingual embeddings** - several of the owner's facts may be in another
    language; the current embedder is English-only.
11. **Undo on the card** - the one approval refinement Muse and Dots both have.
12. **A "close the day" / journal summary** and **a reading list in the daily
    note** - two small Obsidian-shaped wins.
13. **Housekeeping the research already ranked**: `nvidia-smi` polled every 3 s
    on the desktop, the phone retrying when offline, CI running twice per commit,
    15 duplicated test-case files, lazy-loading `jarvis_sensitive`, caching the
    pairing key in memory.
14. **Pocket TTS, built and hash-pinned but never switched on** - a decision, not
    work.
15. **"Explain simply" as its own switch**, separate from speaking speed.

---

## 7. Never copy this - the anti-patterns, each with the incident that proves it

| # | Anti-pattern | Who does it | The evidence | The rule it breaks |
|---|---|---|---|---|
| 1 | **"Allow always" / perpetual grants** | Meta Muse | An owner granted "Allow Always" for Marketplace sales; Muse accepted a lowball offer **and sent the buyer his home address**, unbidden. The buyer turned up at his apartment. Meta's explanation: granting the pickup location plus auto-replies *counted as* permission to include the address - it now says it will reword the prompt ([ExtremeTech](https://www.extremetech.com/internet/metas-muse-ai-shared-a-users-home-address-following-confusion-about-permissions)) | Rule 4. This is precisely what one card per action, never a standing grant, prevents - and it is the strongest single argument in this document |
| 2 | **A setting that lets the agent act with no human in the loop** | OpenAI Dots | Four Custom Rules per action include "act without asking", and a Dot can be set to run with no human in the loop ([NBC](https://www.nbcnews.com/tech/tech-news/openai-launches-dots-ai-agents-safety-questions-rcna600338)) | Rule 4 |
| 3 | **Learning from email, files and connected accounts** | Muse (and most rivals) | Learning draws on connected accounts; training on conversations is on by default | Rule 1 and the 2026-09-24 decision: the owner's own words only |
| 4 | **A cloud computer that holds the owner's data** | Dots (per-user VM), Muse (Secure VM) | Dots: "its own cloud computer and browser"; Muse: a per-user Linux VM | Rule 1 |
| 5 | **Messaging apps as a control channel** | Dots (Slack, Teams), Muse (WhatsApp) | Both require a relay or a public endpoint to reach the assistant | Rule 2 |
| 6 | **Data-for-service pricing** | Muse (free tier + fee per purchase), Dots ($500/month top tier) | - | Rule 5, and rule 1 in spirit |
| 7 | **Pixel-loop computer control** | UI-TARS, OmniParser, Fara-class models | A pixel pointer has no name to re-check before clicking, which is the whole safety property of `jarvis_ui_control.py` | Rule 4 (nothing to gate on) |
| 8 | **Always-on screen history** | Recall-style products | The owner declined it (2026-09-28) | The owner's own decision |
| 9 | **Connectors the agent writes itself, unreviewed** | Meta Muse | Custom connectors built for one user from any API, and "Meta does not review those" | The permission model: outside text never makes Jarvis act |
| 10 | **Claiming capability the code does not have** | Muse, twice in three weeks | It described its own access wrongly, and its settings screen disagreed with the user's choice | Invariant 6, "nothing is claimed that is not true". **Jarvis is not immune** - its own broken "Try the cloud model" button (see the [feature review](FEATURE-REVIEW-2026-10-04.md) C1 #1) is the same failure in miniature, and it is currently shipping |
| 11 | **Acting with the owner's saved browser passwords** | Google Gemini Spark | Spark "runs errands using saved Chrome logins and saved passwords" ([Notebookcheck](https://www.notebookcheck.net/Google-Gemini-Spark-now-uses-your-saved-Chrome-passwords.1357683.0.html)) - the bridge from "the browser knows your password" to "the agent acts as you" | Rules 1 and 3. It is also the strongest argument for keeping the chatbot driver on a **spare** account |
| 12 | **Auto-approve as the first option in a menu** | OpenAI Dots | The first of four Custom Rules is "take action without asking" ([Drag](https://www.dragapp.com/blog/openai-dots/)) | Rule 4. A control the market leader sells as convenience is the control whose absence caused Muse's worst incident |
| 13 | **Passwords typed into a page the model can see** | Most agentic browsers | Prompt-injection bugs in Comet leaked local files and reached password vaults ([eSecurity Planet](https://www.esecurityplanet.com/artificial-intelligence/perplexity-comet-browser-bug-leaks-local-files-via-ai-prompt-injection/)) | Rule 3, and the reason Jarvis form-filling uses `<secret>…</secret>` placeholders |
| 14 | **Putting a price on a prompt injection instead of fixing it** | Meta (a bounty up to $130,000 for a successful injection against Muse) | A bounty is a measurement of the risk, not a defence | Rule 4 - Jarvis's answer is that every acting call has a card, whatever the text says |

---

## 8. What has changed since the project last looked (2026-09-25)

The three audits from 2026-09-25 are still worth reading, and their star counts
and licences were re-checked in this pass and found accurate. What follows is
everything that moved.

**The field**

- **OpenAI Dots** (2026-09-29), ChatGPT **Pulse**, **GPT-6.1 Sol**, **ChatGPT
  Space** and the **$500/month Pro 500** plan - none of which existed when the
  audits were written. Dots is the single biggest change: an always-on cloud
  agent with 4,000+ app connections and its own computer.
- **Muse's worst incident happened after the audit.** The audit's risk table is
  frozen at 25 September and misses the home-address failure (Section 7 #1) and
  a second macOS security finding. A reader today sees weaker evidence than
  exists.
- **Muse's architecture details are now known**, and they validate Jarvis:
  Sentinel is a **separate host-side program** that is the sole authority for
  connector actions and network egress (the agent only proposes), and
  `hatch-authd` issues **surrogate tokens** so the agent never holds a real
  credential ([Forkast](https://forkast.news/metas-muse-agent-lives-behind-a-kernel-level-sentinel-the-architecture-reveals-where-agent-security-is-heading/)).
  Both are Jarvis's gate and Jarvis's rule 3, arrived at independently.
- **Muse Glimmer shipped 2026-08-10**, about six weeks *before* Muse - not
  alongside it as the audit implies - and its memory figures are more forgiving
  than the audit states (Section 6 #7).
- **Copilot: Microsoft retired Copilot Groups, Labs and the Mico avatar on
  2026-08-18** - five weeks before the audit listed "Copilot Groups" as a live
  feature - and at Build 2026 it signalled that **Copilot+ PCs no longer
  matter** ([PCMag](https://uk.pcmag.com/ai/165412/at-build-2026-microsoft-sent-a-clear-message-copilot-pcs-no-longer-matter)).
  A Copilot "super app" with an OpenClaw-based "Autopilot" was shown on
  2026-09-28.
- **ChatGPT temporary chat can now use saved memories**, so the commercial
  audit's "temporary chat is memory-free" baseline is wrong.
- **Gemini Live gained memory** - past chats, Memory and Connected Apps
  ([9to5Google](https://9to5google.com/2026/06/18/gemini-live-memory/)).
- **Alexa+ is free for Prime members in the US** and launched in India
  ([Amazon](https://www.aboutamazon.com/news/devices/alexa-plus-available-free-prime-members-us),
  [Medianama](https://www.medianama.com/2026/09/223-amazon-alexa-plus-launched-india/)).
- **Khoj Cloud has been sunset**, resolving the audit's open "unverified either
  way" note; the repo has not been pushed to since 2026-08-02.
- **One licence correction:** ZeroClaw is **Apache-2.0 only**, not "MIT or
  Apache" (`docs/COMPETITORS-OPEN-SOURCE-2026-09-25.md:43`).
- **Nothing in the audits was fabricated.** All ~21 named projects exist, with
  the star counts and licences the audits claim (re-verified today: OpenClaw
  391k MIT, Hermes 251k MIT, Open WebUI 154k, Home Assistant 91k Apache-2.0,
  AnythingLLM 67k MIT, Jan 45k, Khoj 38k AGPL-3.0, Row-Bot 1.5k).

**Jarvis itself** - which makes the old scorecards stale in its favour. Since
2026-09-25 it has shipped: **sending email** (one card per email), timers,
alarms and reminders on one scheduler, the morning briefing, **web search with
five providers**, "tell me when" and page watches, the reach list, one-time-code
masking in email previews, goals, projects, quiz and review decks, chat tags and
forks, topic controls, thinking levels, notification settings and tutorials. The
2026-09-25 scorecards still say Jarvis "cannot send email", "has no timers" and
"cannot search the web". All three are now false.

**The audits' own failure mode, worth naming:** it is not invention, it is **a
single-sourced number carried into a decision without a second check** - exactly
what happened to the Glimmer memory-fit conclusion that has shaped the model
plan ever since. Every numbers-based decision in this document carries its
source for that reason. **The fix is one line of process:** any figure that
changes what gets built gets a second source before it is used - and any figure
that never gets one is written down as an estimate, not a fact.

**Two smaller housekeeping notes about the old comparisons, so the next reader
is not misled:**

- Two ideas the feasibility audit marked "**No**" were later built anyway (the
  FSRS quiz, now JARVIS-API §102, and "between us", §48), and two "Later" items
  were superseded. Its tally of 26 refusals is therefore **not** a current
  statement of what Jarvis will not do - check the code, not the verdict.
- Three features that came from competitor research were built without a
  separate entry in `CLAUDE.md` (`jarvis_reach.py`, `jarvis_mail_mask.py` and the
  back-off's "never asks for more access" rule). They live in
  [JARVIS-API](JARVIS-API.md) §24, §25 and §22.6. A future comparison that greps
  only `CLAUDE.md` will report them as undecided when they are built.

---

## 9. Decisions this comparison needs from the owner

Short and multiple-choice, as the project's rules ask.

1. **The 12 GB card is in, and the model plan was built on a wrong memory
   figure for the one local competitor model that exists.**
   - **Measure first: run the card's real numbers with the current plan and with Muse Glimmer (2-bit/3-bit), then decide** (recommended)
   - Keep Qwen 3.5 9B, do not revisit
   - Try Glimmer as the everyday model straight away
2. **Every rival installs in minutes; Jarvis cannot be installed by a second
   person at all.**
   - **Spend the time to make the backend installable (scripted install, "Start Jarvis for me", honest status)** (recommended)
   - Only improve the documentation
   - Leave it: one owner, one PC
3. **The biggest safe gap is "it stops when the PC stops".**
   - **Build the local night shift: read-only jobs while the PC is idle, cards in the morning** (recommended)
   - Leave it; the scheduler and briefing are enough
   - Reconsider a cloud worker for this one job (breaks rule 1)
