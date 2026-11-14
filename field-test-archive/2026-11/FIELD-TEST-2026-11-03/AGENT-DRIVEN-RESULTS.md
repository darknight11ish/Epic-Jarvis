# Agent-driven field test — results (2026-11-03, F5 build)

**What this is.** The owner delegated the field-test driving to the agent ("you do the driving"). Every row below was driven through the **same path the HUD uses** — `POST /api/chat` with `X-Jarvis-Client: hud`, `stream: true`, and the newest user turn carrying `"provenance": "typed"` (the fast path refuses a turn with no provenance; without the tag every question silently falls through to the model — measured). Results are graded **AGENT-DRIVEN**, never as an owner field PASS: `docs/FIELD-TEST-MATRIX-2026-10-11.md` says a probe PASS is not a field PASS, and an agent is not the owner. Owner-only rows stay BLOCKED.

**Harness:** `.dsh-scratch/FIELD-TEST-2026-11-03/agent_drive.py` (batch) and `agent_drive_undo2.py` (the receipted change + double undo). Raw captures: `agent-drive-batch1-accepted.log`, `agent-drive-undo2.log`, `agent-drive-last.json`, `agent-drive-undo2.json`.

**State touched and restored:** the batch made no change (every row a read or a refusal). The undo pair toggled the sun-and-moon switch off and back on; the final read is `/api/sky` → `{"show": true}`, which is where it started. Anti-Slop was turned on by an early attempt and turned back off; `/api/antislop` → `{"enabled": false}`. No approval card was raised by any row in this run (`pending: []` before and after each row), and no card was ever approved or denied.

## What the driving found first, and it matters more than any row

The click-through page's own suggested sentences are **not all accepted by the fast path**, and when a sentence misses, the local model answers from its own knowledge — sometimes wrongly. Both failures were reproduced twice, in separate runs:

| page's sentence | what happened |
|---|---|
| "which model is answering me, and why that one?" | fast path declined (`jarvis_quick.match` → None); model answered "I'm Qwen3.5:9b … If you'd ever want to try a cloud model like DeepSeek-flash … just say yes and I can take that card" — the model **invented a card offer**. |
| "where do I change the weather source, and what is it set to?" | fast path declined; model answered "The weather source setting lives in your Home Assistant configuration files … `configuration.yaml`" and offered to search notes — **wrong on both facts** (Jarvis's weather source is `off/home_assistant/open_meteo` in its own settings file, and it is set to **Off**). |
| "list my plugins" | declined; model answered "I don't have access to a direct list plugins function … I'd need to know the specific path" — while the plugin list is a real chat tool. |
| "which apps on my phone may you open?" | declined; model answered "I can't open your phone's apps directly. However, I can help with tasks through them … email, calendar, reminders, contacts, photo access" — **invented capabilities**; the real answer is that the allow-list is empty. |

The accepted phrasings, found by probing the live grammar directly (`jarvis_quick.match`) and then confirmed end to end:

| row | accepted sentence | answer (abridged) | verdict |
|---|---|---|---|
| **F4-05B** | `which model are you using` | "You are running qwen3.5:9b on this PC, under the \"General\" preset. Brain, Models lists every installed model and its measured speed." | **AGENT-PASS** — matches `GET /api/models` (`current=qwen3.5:9b`) and `GET /api/presets` (`current=general`) |
| **F4-04B** | `what can you open on my phone` | the whole allow-list explanation: list ships empty, where it lives (`[phone_apps]`), adding/removing raises one card naming friendly name + package id, `control_phone` off by default, adb cable, `com.jarvis` refused, honest limit | **AGENT-PASS** — matches `GET /api/phone/apps` → `count=0, empty=true` |
| **F4-06B** | `what is the price radar showing` | "No — the price and flight radar is OFF by default. It is read-only (never books or buys) … `[price_radar] enabled = true` … no chat approval card for that switch exists yet" | **AGENT-PASS** — honest and empty, as `decks=0 radar=0` |
| **F4-07B** | `what plugins do you have` | "22 plug-in(s) are installed on this PC … The catalogue has 48 … add one with `scripts/add-plugin.ps1`" | **AGENT-PARTIAL** — the list half passes; the switch-one-off half needs a card and was not driven |
| **F5-01B** | `how do i change the weather source` | four facts: "Weather behind the face" is a choice in Settings, animal options · current **Off** · exact sentences `set the weather source to off|home assistant|open meteo` · Open-Meteo asks on a card | **AGENT-PASS** |
| **F5-02B** | `what is the anti-slop filter set to` | "The Anti-Slop filter is off … Say \"turn on anti-slop\" and it starts at once — no approval card." | **AGENT-PASS** — matches `GET /api/antislop` `enabled=false` |
| **F5-02B** | `how do i change the personality` | "The personality is a choice in Settings … Right now: Warm Collaborator … Say \"set the personality to advocate\" … a change that needs approval still asks on a card first." | **AGENT-PASS** — matches `GET /api/manner` `manner=warm` |
| **F5-02B** | `how do i change the sun and moon` | "… Right now: on … cosmetic, so no card is needed." | **AGENT-PASS** — matches `GET /api/sky` `show=true` |
| **F5-03B** | `how do i change the jarvis live timeout` | "… a number in Settings, limits. Right now: 1 minute and 30 seconds … It can be anything from 30 seconds to 10 minutes." | **AGENT-PASS** — value and range stated (no GET route re-read it; recorded as written) |
| **F5-05B** | `turn off the sun and moon` → `undo` | change: "The sun and moon are no longer shown." (cardless, no card) · undo: "The sun and moon now show behind the face." | **AGENT-PASS** — the reversal reached the setter; `/api/sky` went true → false → true |
| **F5-06B** | a second `undo` | "I already put the sun and moon back in this chat, so there is nothing left to undo." | **AGENT-PASS** — refuses, changes nothing (`/api/sky` stays true) |
| **F5-10B** | `change the warp drive calibration to nine` | "I don't recognize \"warp drive calibration\" as a setting I have on this PC …" | **AGENT-PASS** — honest refusal, **no card** raised |

### Two findings from the driving that are not passes

- **D1 — the page's sentences are wrong for several rows.** The four failures in the table at the top are a documentation defect (the page tells the owner sentences the product does not accept) and a usability gap (a natural compound question falls through to the model, which then invents facts). Fixing the page is mine; widening the grammar is a product decision. **Not fixed in this pass.**
- **D2 — the Anti-Slop toggle is a cardless change with no undo receipt.** `turn on the anti-slop filter` really changes the setting (answer: "Anti-Slop filter on (During mode…)", `/api/antislop` `enabled=true`) but writes **no** settings receipt, so a following `undo` answers *"There is nothing here for me to take back."* The F5 claim "a cardless change leaves one receipt" is therefore false for this one setting; the receipted path is the registry/animal path (sun-and-moon, weather source, bools, choices), which the row above exercises. Recorded as a defect candidate, not fixed.

## Rows driven this pass, and what is left

Driven and graded above: F4-05B, F4-04B, F4-06B, F4-07B (list half), F5-01B, F5-02B (×3), F5-03B, F5-05B, F5-06B, F5-10B.

Still BLOCKED or assigned elsewhere:
- **F4-01B, F4-02B, F4-03B** — phone rows (habit tick, mood tap, week in review); being driven through the phone UI by the phone lane, screenshots to `phone/`. F4-03B may end BLOCKED — not enough time yet.
- **F4-08B** — the DEF-028 Live line on the phone; phone lane.
- **F4-09B** — goals progress; **BLOCKED**: no goal exists on this PC and creating one writes owner data, so it was not driven.
- **F4-10B, F4-11B, F4-12B** — wake word, Live voice check, fingerprint approval: **BLOCKED — needs the owner's voice or finger.**
- **F5-04B** — the "I could not read its current value" sentence: **BLOCKED** — it needs one module stopped for a minute; not done without the owner watching.
- **F5-07B** — a carded setting change in Live: **BLOCKED** — needs Live and a card.
- **F5-08B** — read a link: raises one card; **BLOCKED pending the owner** (the row wants one card per link and a declined card; declining is the owner's action).
- **F5-09B** — page reader unswitchable: **API-verified** (two independent probes: `read_web_page` in `not_offered.tier_c`, absent from `switchable` and from the app's tool items); the **screen absence** is not driven — it needs one look at Settings, or the phone lane's screenshot.
