# Creativity audit: the rules, and where they could bend safely

Read-only audit, 2026-09-25. Nothing in the repo was changed. Every claim about Jarvis below was checked against the file named next to it. Where I am guessing (mostly how often something annoys you), I say so. **The rules are yours. This report only proposes.**

Words used below:
- **Card**: an approval card, the "Jarvis wants to... Approve / Deny" box.
- **Tier**: the setting each action has in `jarvis-framework.toml`: `auto` (just do it), `notify` (do it, tell you after), `ask` (card every time), `never`.
- **Tainted / outside text**: the conversation has read something you did not write (an email, a web page, a file, a tool's answer). From then on, some actions ask first.

---

## 1. The answer in short

- **Almost every rule earns its keep.** The five rules, "facts only from your own words", "no approve-all", and "Approve never on a lock screen" each block a failure that has really happened to a competitor (Muse, OpenClaw, ChatGPT's "Never ask"). Keep them exactly.
- **The friction comes from a few *mechanisms*, not from the principles.** Three are worth fixing:
  1. **Any saved memory in the answer makes every web search ask first.** That includes a single pinned fact ("Always keep in mind"), which goes into *every* turn. So once you pin anything, every search asks. It is probably the biggest unintended source of cards. (Section 4.)
  2. **One light is one card.** "Turn off the kitchen, hall and bedroom lights" is three cards, which already uses 3 of the 5 cards one answer may raise. One card listing all three lights is allowed by the no-approve-all rule as written.
  3. **Tiers can only be changed by editing a TOML file.** That is hard for a beginner, even when you only want to make something *stricter*.
- **Most creative idea that stays safe:** scheduled or time-limited actions for **one named light**, never a lock, with every run listed on one card. The architecture's own definition of "no approve-all" allows this if the list is finite and shown in full. It has one real prerequisite, explained in idea I-5.
- **Ideas I recommend against** even though competitors have them: "always allow", "for this conversation" grants, learning trust from your past yeses, and approving by voice.

---

## 2. Inventory: every rule, what it protects, what it costs

Class key: **A** keep exactly · **B** keep the principle, change the mechanism · **C** can relax safely with a guard · **D** could be a setting of yours (default unchanged).
"How often" is my estimate from how the code works. I have no usage logs.

### The five rules (`CLAUDE.md`)

| Rule | Bad outcome it prevents | Daily cost | How often | Class |
|---|---|---|---|---|
| 1. Email, files, credentials, memory stay on the local model | Your inbox or memories reach a company's server. Enforced by the router's role filter and the "newest turn only" cut (`ARCHITECTURE.md` §4) | Hard questions get the 8B model's answer; the cloud is only *offered* (`offer` in `X-Jarvis-Route`) | Often, for hard questions | **A** |
| 2. No public tunnel | Anyone on the internet can reach Jarvis. Enforced by `validate_bind_address` and a refusal to start with no token (`ARCHITECTURE.md` §2.2) | No web app, no WhatsApp, and Jarvis is unreachable when Tailscale/Meshnet is down | Rarely | **A** |
| 3. API keys allowed, handled like the pairing token | A key leaks through a log, a card or the phone link | Keys can only be typed on the desktop (`ARCHITECTURE.md` §8, the "Entering an Exa, Tavily or Brave key" row) | Once per key | **A** (not worth relaxing) |
| 4a. Never auto-approve | A planted instruction gets carried out without you. This is Muse's and ChatGPT's "always allow" / "Never ask" | Every acting step is a card | Many times a day if tools are on | **A** |
| 4b. Block acting on a stale event stream | You approve a card that is already decided or gone | Approve **and Deny** are both refused while stale: desktop `commands.rs:1920` sits before any approve/deny split, and the phone's `decisionBlocker` (`JarvisRuntime.kt:2363`) is used for both | Rarely. Cards also expire after 180 s (`approval_timeout_seconds`) | **A** for Approve, **C** for Deny |
| 5. Non-commercial, sideloaded | Store rules and payment pressure | Installing with adb | Per update | **A** |

### "Also standing" and your amendments

| Rule | Protects | Cost | Class |
|---|---|---|---|
| No speech-to-text on a client | The speaker check runs on the whole clip on the PC. And automatic learning trusts `voice` only when "this PC's own speech route made those exact words" (`ARCHITECTURE.md` §5, chat history). Speech-to-text on the phone would break that trust | Phone voice needs the PC | **A**. Removing it would quietly weaken automatic learning |
| No memory graph on the phone (this now includes People and things) | The reason written down is only "out of scope on the phone" (`ARCHITECTURE.md` §8, first two rows). *My guess:* a phone can be lost, and the graph is the most complete picture of your life | You cannot see "Priya = sister" on the phone | **C** for a read-only view of names under facts the phone already shows (idea I-9) |
| No deep config editing on the phone | A lost or borrowed phone rewrites Jarvis's rules | Settings like tiers need the PC | **B**: changes that only make things *stricter* could be allowed (idea I-4) |
| No browsing the model catalogue on the phone; install only by typing a name (amended 2026-09-20) | Scope and screen size. *My reading:* it is not really a safety rule; installing still needs a card | Typing model names by hand | **D**, low value. Leave it |
| No control that clears a rush latch, and no bulk approve | Being hurried into a yes. `test_gate_outcome.t_there_is_still_no_approve_all` bans the names `approve_all`, `yolo`, etc. (`backend/test_gate_outcome.py:356-391`) | None | **A** |
| `X-Jarvis-Client: hud`, never log the token | The token leaking. Note: the header proves nothing about *which* device is asking (`JARVIS-API.md` §1) | None | **A** |
| Switching and installing models from the phone go through a card | A model swap changes "which model reads your email" (toml comment, line 131) | One card | Keep as is |

### The decisions of 2026-09-24 and 2026-09-25

| Rule | Protects | Cost | Class |
|---|---|---|---|
| Facts learned only from your own typed or spoken words | Poisoned memory. The research's one working defence (`RESEARCH-2026-09-24.md` §3) | Jarvis will not learn "flight at 9" from an email. You can still type "Remember: ..." | **A** |
| Sensitive facts wait for your yes, unless you turn on the setting | Health or money details saved by mistake | Some extra memory cards | Already **D** |
| Passwords, PINs, account and ID numbers always wait (`jarvis_sensitive.always_asks`) | Secrets in `memory.db` | Rare cards | **A** |
| Turning something on asks; turning it off is immediate | A loosening sneaks in; tightening is never blocked | One card per loosening | **A**. This is the ratchet the rest depends on |
| Note writes wait for a yes after outside text (`NOTE_WRITES`, `jarvis_agent.py:1013`) | An email plants text in your notes, or copies a private file into a note that syncs to the cloud (`RESEARCH` §2) | "Summarise this email into my daily note" is always a card | **A**. That card *is* the protection |
| Taint lasts for the whole conversation (`taint_persists_for_conversation = true`, toml line 40) | Planted text acting several turns later | Every later search or note write in that chat asks | **B**: offer a fresh chat (idea I-7) |
| Web search asks when outside text, memories, pasted text, or the "every search" setting is involved (`web_search_card_lines`, `jarvis_agent.py:1067`) | Private words ending up in a search query | See the conflict in section 4: memory recall is much broader than "private words in the query" | **B** (idea I-1) |
| One-off timers need no card; repeats get one card listing the next 3 times | Something repeating forever without your knowledge | One card per repeating job | **A**. Could be *extended* (idea I-5) |
| Scheduled runs may only read; anything that acts gets its own card (`RESEARCH` §7, briefing in `ARCHITECTURE.md` §10) | A night-time job acting while you sleep | No "porch light at 7 pm every day" | **B** (idea I-5) |
| Plain `http://` only inside your own networks | Your Home Assistant token sent unencrypted over the internet | None | **A** |
| No silent switch to another search provider | Your words going to a service you did not choose | "Search is down" instead of an answer | **A** |
| Cloud: ask every time, no standing grant (`ARCHITECTURE.md` §11) | Private text slowly drifting to the cloud | A yes for each cloud question | **D** at most, and I would not (section 3, "rejected") |

### Invariants in the code

| Invariant | Protects | Cost | Class |
|---|---|---|---|
| One decision per id (`decide(request_id)`) | Bulk approval | — | **A** |
| At most 5 cards per answer (`CARDS_PER_TURN`, `jarvis_agent.py:1162`) | Wearing you down with a flood of cards | Long jobs stop halfway: "ask again in a new message" | **A** for the number. It bites less once lights can share a card (I-2) |
| Deny can be a notification button; Approve never (`ARCHITECTURE.md` §3, `notice`) | Approving from the lock screen without reading | You open the app to approve | **A** |
| A card marked "someone tried to hurry you" is never in a quick-action group (invariant 4) | Being rushed | — | **A** |
| Tools that always need a person (`NEEDS_A_PERSON`, `jarvis_agent.py:986`: GitHub search, browser, control the computer, control the phone, shell, **home control**) | A config line becoming your yes | A card for every light switch | **A** for everything except lights. **B** for lights (I-2, I-5) |
| Tiers change only by editing the file (toml line 50: "changing this requires editing this file, not asking in conversation") | A chat or a planted instruction talking Jarvis into looser tiers | A beginner edits TOML to make anything stricter | **B** (I-4) |
| Jarvis never drives its own approval screens (`ARCHITECTURE.md` §2) | Approve-all by the back door | — | **A** |
| Offers go through the back-off: at most 3, never mid-chat, a "no" goes quiet for 1, then 7, then 30 days (`jarvis_backoff.py`) | Nagging | — | **A** |
| No delete-all for history or schedules | One mistaken tap wiping everything | One tap per item | **A**, low cost |
| Windows Hello or fingerprint for "Risky only" approvals (`lock/rules.rs:182`, `is_risky`) | Someone else at your desk approving | A check on risky cards only | Already flexible. **Note:** the backend itself does not check this yet (`ARCHITECTURE.md` §3, "A known limit") |

---

## 3. Ideas: more flexibility, the same protection

Each idea says which rule it touches, the new way it could go wrong, the guard, what you would see, its size (S/M/L), and what else it affects. The last part always includes: the gate, both apps, `JARVIS-API.md`, tests, `tools/check_parity.py`, and the audit every new feature gets.

### I-1. Web search: ask when memory could actually leak, not whenever memory was used (S, B)
- **Rule touched:** your 2026-09-25 decision "When a search asks first".
- **Today:** a card if *any* recalled fact is in the turn (`watch.memory`, `jarvis_agent.py:1073`). Pinned facts go into every local turn (`ARCHITECTURE.md` §5), so one pin means every search asks.
- **Change:** memory alone triggers a card only when (a) a recalled fact is sensitive (`injected_sensitive` already exists), or (b) the search words share an uncommon word with a recalled fact. The check is done in code, reusing the memory search's word-weighting idea. Outside text, taint, pasted text and the "every search" setting still always ask.
- **New way it could go wrong:** a *reworded* fact slips out. For example, pinned "I'm vegetarian and live in Leeds" becomes the search "vegan restaurants Leeds" with no card. The word check cannot catch every rewording. That is the honest limit.
- **Guard:** sensitive facts still always ask, so health, money and other people's details are covered. Password-looking words are refused outright, as today. SearXNG, the default, runs on your PC.
- **What you see:** fewer "Jarvis recalled saved memories" cards. The card line changes to "The search words repeat something you told Jarvis".
- **Ripple:** `web_search_card_lines`, `JARVIS-API.md` §23.3, `ARCHITECTURE.md` §4, the test for "search after memory", both apps' wording (no new screen). It is your call (question 1).

### I-2. One card for several lights (S-M, B)
- **Rule touched:** none. `ARCHITECTURE.md` §2 already says "one decision about one bounded set of things, every one of them shown in full" is allowed.
- **Change:** `home_control` accepts up to, say, 6 entities with the *same* on/off service, as one plan. It refuses to mix in a "heavy" domain: lock, alarm or cover (`jarvis_home._HEAVY_DOMAINS`, line 99). Heavy actions stay one card each.
- **New way it could go wrong:** a planted instruction slips a seventh item into a long list. **Guard:** every entity is printed in full on the card, "What shaped this request" still appears, and the card-length check (`_card_would_be_cut`) still refuses anything too long to show.
- **What you see:** "Turn off: light.kitchen, light.hall, light.bedroom" as one card instead of three.
- **Ripple:** `jarvis_home.plan_service`, the tool schema in `jarvis_agent.py`, the comment on `CARDS_PER_TURN` (its reason for five changes), `JARVIS-API.md` (home), tests. No app change: the card is text.

### I-3. Several waiting cards on one screen (S, C)
- **Rule touched:** none, as long as each card keeps its own Approve and Deny. There is no "all" button and no swipe-to-approve for cards marked "hurried".
- **Guard:** the existing invariant 4, and still at most 5 cards per answer.
- **Note:** I did not check whether the apps already show several waiting cards in one list. The phone's Home screen uses a scrolling list (`HomeScreen.kt:868`), so it may already do this. Check before building.

### I-4. "Make stricter" controls in both apps (S-M, B)
- **Rules touched:** "tiers only by editing the file" and "no deep config on the phone".
- **Change:** a short list, for example "Ask before reading my calendar / email / notes / home", or "Always ask before writing notes". Switching one ON makes it stricter and happens at once. Switching one OFF follows your existing pattern: loosening asks, with one `change_own_config` card. It never goes below what the TOML says.
- **New way it could go wrong:** a setting that *seems* to protect but is not wired up. Invariant 6 already bit here: the old `sandbox_*` lines did nothing (toml lines 280-289). **Guard:** a test that reads the tool loop's real tier for each switch.
- **What you see:** safety settings you can use without a text editor.
- **Ripple:** a new route and settings file, both apps' Settings/Mind, the `tools/check_parity.py` entry, `JARVIS-API.md`, and `ARCHITECTURE.md` §8. Tightening on the phone is arguably not "deep config"; that is your call.

### I-5. Scheduled or time-limited actions for one light (M-L, B, your call)
- **Rules touched:** invariant 3 (no approve-all), `NEEDS_A_PERSON["home_control"]`, and "scheduled runs may only read".
- **Change, in two forms, both approved with ONE card:**
  - **(a) A repeating action with a fixed plan.** "Porch light on at 19:00 and off at 23:00, every day for 14 days." The card lists **all 28 runs**. That makes the set finite and fully shown, which is the §2 test. It uses the one scheduler (`register_kind`) with no model at run time: the exact Home Assistant call is fixed when you approve. Reusing the `schedule_repeat` card shape.
  - **(b) A short pass.** "Jarvis may switch light.hall on/off without asking until 23:00 tonight, at most 10 times." One entity, one on/off service pair, a hard end time of midnight at the latest, a use count, and an immediate "Stop" in both apps.
- **New ways it could go wrong, and the guards:**
  - A planted instruction uses the pass. **Guard:** the pass does not apply in a tainted turn, which goes back to a card. It never covers heavy domains (lock, alarm, cover). The model cannot create a pass; only your tap on a card can.
  - **The real prerequisite:** today any program already on the PC can approve a card with the token alone, without Windows Hello (`ARCHITECTURE.md` §3, "A known limit"). A pass turns one stolen approval into many actions. **Build (b) only after the backend itself requires the Windows Hello check.** Form (a) has the same weakness, but only for a light on a fixed timetable, which limits the harm.
  - A pass is used while you are away. **Guard:** each use raises the `notify` doorbell ("Jarvis switched the hall light on (pass, 3 of 10)"). The pass works only while a paired app is connected, in the spirit of rule 4b.
- **What you see:** "Coming up" shows the runs. A "Passes" line in both apps shows what is allowed, until when, the uses left, and Stop.
- **Ripple:** a large one. It needs a new scheduler kind, pass records in the gate (named by id, never "all"), an update to `t_there_is_still_no_approve_all` so it states what a pass is and is not, new wording in `notice_for`, both apps, parity, `JARVIS-API.md`, `ARCHITECTURE.md` §2 (to say how this fits "no approve-all"), and the new-feature audit. Honest note: rule 4 says "never auto-approves anything". Form (b) stretches that wording and form (a) does not. That is why it is question 2.

### I-6. Deny while the link is stale (S, C)
- **Rule touched:** 4b, which says to block *acting*. Denying does not act.
- **Change:** allow Deny, and never Approve, while the link is stale. A second answer to the same card already gets a harmless 409.
- **Honest value:** small. The card refuses itself after 180 s anyway. The benefit is that Jarvis stops waiting sooner.
- **Ripple:** `commands.rs` `answer_approval`, `decisionBlocker`, the tests on both sides, `JARVIS-API.md` §9.

### I-7. When a card is caused by taint, offer "start a fresh chat" (S, B)
- **Rule touched:** taint lasting for the whole conversation. The rule does not change.
- **Change:** a card raised *only* because of earlier taint adds one line: "This chat read outside text earlier. A new chat would not need this card." It offers a button for a new chat. This makes nothing looser.
- **Ripple:** a line in the agent's card text, a button in both apps, docs.

### I-8. "You have never written to this address" warning, for when email sending is built (S, tightening)
- Sending is not built (`jarvis_email.py`'s header, quoted in `COMPETITORS-MUSE` §3). A "trusted recipients" list that *removes* a card would weaken the notice rule: leaving the machine makes a card heavy (`ARCHITECTURE.md` §3). The safe version works the other way round: every email is still a heavy card, and a **new** recipient adds a warning line. That makes the list useful without loosening anything.

### I-9. A read-only view of names on the phone (S, C, your call)
- **Rule touched:** "no memory graph on the phone".
- **Change:** show the names under each fact the phone *already* lists ("Saved automatically", "Used in this answer"). The names are copied word for word from those facts (`ARCHITECTURE.md` §5, "Grounded or dropped"), so the phone learns nothing new. No "About <name>" browsing and no merge card.
- **New way it could go wrong:** almost none, since it is data already on screen. It is covered by "Hide memory lists" and by screenshot blocking.

### Considered and rejected, with the reason

- **"Allow for this conversation" or "always allow".** These grant future actions that nobody has named. That is exactly the case `ARCHITECTURE.md` §2 forbids, and the Muse and OpenClaw failures are why.
- **Suggesting passes from your past yeses** ("you approved the hall light 10 times, want a pass?"). It conflicts with the Muse audit's own recommendation that "an offer never asks for more access" (`COMPETITORS-MUSE` §6, idea 4). The gate already learns in the *tightening* direction: a "no" becomes a proposed rule (`backend/README.md:3176`). Keep it one-way.
- **Approving by voice, even for small cards.** The voice check cannot tell you from a recording (`RESEARCH` §5), and a TV saying "yes" is a real risk. It could only be safe with a "say these three words shown on screen" challenge, and that is more work than a tap.
- **A cloud grant for "general knowledge" questions.** It drifts into a standing grant (`COMPETITORS-OPEN-SOURCE`, line 103, says the same). You chose "ask each time" on 2026-09-24.
- **Typing keys on the phone.** Rule 3's wording forbids it, and a key is entered once.

---

## 4. How the rules connect to the features, and where they clash

**Map of which rule shapes which feature:**
- **Taint / outside text** affects note writes (card), web search (card), the "What shaped this request" line on every card, automatic learning (a tainted conversation is never learned from), push notifications (none while tainted, §4 ntfy row), and the briefing (email senders count as outside text).
- **"Your own words only"** affects automatic learning, the entity layer (links come only from saved facts), and the cut-off note (Jarvis's words are never yours).
- **Rule 1 (local only)** affects the cloud router, the chat model's "is this really local?" check, web search (private words only reach a query after being read, which is why reading makes a card), and deep questions (kept in memory only).
- **"On asks, off is immediate"** applies to learning, history, sensitive topics, the second card, the big model, voices, briefing senders, and "Ask before every web search".
- **One card per action + 5 per answer** applies to home control, shell, UI, phone control, the browser and search.

**Where rules clash today:**
1. **Pinned facts vs web search.** A pinned fact makes `recalled_memory()` true on every local turn (`jarvis_agent.py:1091-1106`, `ARCHITECTURE.md` §5). So every search is a card and uses up one of the 5 allowed per answer. Automatic learning is on by default, so more facts get recalled and this gets worse over time. **Probably the most frequent unneeded card** (estimate).
2. **Home control vs the 5-card cap.** The code itself says three lights already use three cards (`jarvis_agent.py:1159-1161`). I-2 fixes this.
3. **The stale-link rule blocks Deny as well** (`commands.rs:1920`; `decisionBlocker`). That is stricter than the rule's own words. Harmless, but a small mismatch.
4. **"Scheduled runs only read" vs a home assistant's most common routine** (lights at set times). Neither app can do it today.
5. **One header for every device** (`X-Jarvis-Client: hud`, `JARVIS-API.md` §1). The PC cannot tell the phone from the desktop, so no permission can be limited to "only from the desktop" until per-device keys arrive with QR pairing.
6. **The tier file vs a beginner owner.** Making something stricter needs a TOML edit, even though "turning off is immediate" everywhere else.

---

## 5. Top recommendations, ranked

Ranked by value gained × safety kept ÷ size.

1. **I-1: web search asks only when memory could leak** (S). Removes the biggest unneeded source of cards. Sensitive facts still always ask. Your call: question 1.
2. **I-2: one card for several lights, never locks, alarms or covers** (S-M). Fits the no-approve-all rule as written. No new rule needed.
3. **I-7: "start a fresh chat" on cards caused by taint** (S). Makes nothing looser.
4. **I-4: "Make stricter" switches in both apps** (S-M). Safety you can use without editing a file. Loosening still asks.
5. **I-5a: a repeating light schedule with every run listed on one card** (M). Closes the "porch light" gap. There is no model at run time, so planted text cannot reach it. Your call: question 2.
6. **I-3: several cards on one screen, each with its own buttons** (S). Check first whether the apps already do this.
7. **I-8: warn about a new email recipient, once sending is built** (S). Design it now, so the "trusted list" idea never turns into skipping cards.
8. **I-5b: a short pass for one light, only after the backend checks Windows Hello itself** (M-L). The most useful loosening, and the riskiest. Put it in the queue *behind* that fix.

Not ranked, but cheap: I-6 (Deny while the link is stale) and I-9 (read-only names on the phone).

---

## 6. Questions for you

**1. Web search and your saved memories.** Right now, if Jarvis used any saved fact in an answer, even one you pinned, every web search in that answer asks you first.
- **Ask only when the search words repeat something you told Jarvis, or a sensitive fact was used** (recommended)
- **Keep asking whenever memories were used**

**2. Lights on a timetable.** Should a repeating schedule be allowed to switch one light (never a lock, alarm or blind) at fixed times, approved once on a card that lists every run?
- **Yes, up to two weeks per card** (recommended)
- **No, schedules only remind and read**

**3. A short "pass" for one light** ("switch the hall light without asking until 11 pm, at most 10 times").
- **Not yet: first make the PC itself check Windows Hello on approvals** (recommended)
- **Never: every light switch gets a card**

---

*What I did not verify:* how often any of these costs actually hits you (there are no usage logs here); whether the apps already show several cards on one screen; what the owner-only files (`jarvis_gate.py`, `jarvis_content_risk.py`) do beyond what this repo quotes.
