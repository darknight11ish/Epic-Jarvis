# Audit #6 - Does the combined code follow every owner decision?

Combined tree `integ` (HEAD deaca649). Tests were run on a copy
(`scratchpad/a02/tree`, with `scratchpad/venv`), never in `integ` itself.

## Short version (plain words)

- **Two decisions are broken in the code:**
  1. **Animal voices** (owner, 2026-09-28): "Voice follows the face" should start OFF, be offered once
     per face, and the sea otter must not use the "Sky" voice. The code has it ON by default, has no
     one-time offer, and gives the otter voice "4", which is Sky. A test locks the wrong default in.
  2. **"Jarvis can change any animal option when asked"** (owner, 2026-09-28): not built. Nothing in
     the chat or voice commands handles "turn weather off" or "make the animal sharper".
- **One decision is honoured only halfway:** reading phone notifications - turning it off on the PC
  does not reach the phone until its settings page is opened (details in report 02, F1).
- **The entity layer** (the part of memory search that links people's names): it is ON by default
  and has been since 2026-09-25, before the "a change that makes a number worse is not kept" rule.
  On the new LoCoMo test (words only, on the build machine) it made every number worse, "Found all
  @5" 9.5% -> 3.6%. It was not a new change, so the rule was not broken by the letter, but by the
  rule's own spirit it has not earned its place on this test. **Owner's call**, after the PC's
  real-model run.
- Everything else I checked is followed: the plan card is off and cannot turn on (its safety-test
  results file does not exist), the chatbot limits are as confirmed, humour and the "I heard you" sound
  are off, the focus report has no streak line, crisis rules hold (988/911, never learned, never
  counted, thumbs-down fixed and tested), no model catalogue on the phone, the 12 GB features stay
  off, the maker is "darknight11ish".

## Violations

### V1 - high - Animal voices: default ON, no one-time offer, otter uses "Sky"
**Checked in code.** Decision (CLAUDE.md lines 551-561, research branch commit a633325a): "the first
time the owner picks an animal face, one line asks ... (Use it / Keep my voice) ... that switch
stays, but starts off ... The sea otter must not use Kokoro's "Sky" voice".

Evidence:
- `backend/jarvis_voices.py:531` - `FACE_VOICE_DEFAULT = True`
- `backend/jarvis_voices.py:556-558` - `face_voice_on()` returns `FACE_VOICE_DEFAULT` when the owner
  never chose.
- `backend/jarvis_voices.py:516` - `"seaotter": {"name": "Sea Otter", "speaker": "4", ...}`
- `backend/jarvis_voices.py:392` - `("4", "American (female) - Sky"),`
- `backend/test_voice_upgrades.py:365` - `check("on by default", V.face_voice_on() is True and V.FACE_VOICE_DEFAULT is True)` - the test enforces the wrong default.
- No "Use it" / "Keep my voice" offer in the backend or either app (grep for "Keep my voice",
  "its own voice. Use" finds nothing). The phone comment `net/CustomVoices.kt:36` also says "on by
  default".
- The feature ("Voice follows the face", 529a6558) is already on `origin/main`; the decision was
  written on the research branch and never applied to the code.

Why it matters: the owner explicitly said a face must never change the voice by itself; today picking
an animal does exactly that. The Sky voice was named for a likeness reason.
Fix (code): `FACE_VOICE_DEFAULT = False`; give the otter another Kokoro voice with a playful pitch
(e.g. "2" Nicole or "3" Sarah - pick by ear; not "4"); update `test_voice_upgrades.py:365` and the
phone comment; build the one-time "The <animal> has its own voice. Use it?" line in both apps, stored
per face on the PC (for example a `face_voice_offered` list in `state.json`), with "Use it" turning
the switch on. The apps only mirror the PC's value, so the default change needs no app change.

### V2 - medium - "Jarvis can change any animal option when asked" is not built
**Checked in code.** Decision (CLAUDE.md lines 819-824, mascot commit ee75ffcb): "Jarvis can change
any of them when asked ("turn weather off", "make the animal sharper") ... cosmetic options change at
once; anything that opens a way out of the PC (online weather) still raises its approval card."
Evidence: no match for "sky", "sun and moon", "keep the animal still", "weather off" or "sharper" in
`backend/jarvis_quick.py` or `backend/jarvis_settings_registry.py` (the "adjust any setting" door);
the registry only has "open appearance" (`jarvis_settings_registry.py:138`). `backend/sky.patch` adds
only the GET/POST route. The decision was written 1 hour before the sky feature was built
(ee75ffcb 09:51 vs 22954912 10:54 UTC) and the build did not include it.
The first half ("every animal option in one place") IS followed: desktop Settings "Face on this
computer" + "Sun, moon and weather" (`settings.html:488-605`); phone Appearance holds FaceEditor,
Still and the sky section (`AppearanceScreen.kt:519, 617, 770`).
Fix (code): add `sky_show` and `sky_weather` to the settings registry (weather "Open-Meteo" going
through `jarvis_sky`'s own card path); the per-device options (Still, quality, frame rate) live on
each device, so "make the animal sharper" needs a small event the apps act on - or the owner accepts
"PC-wide options by voice only". Owner's call on that last part.

### V3 - medium - Phone notifications: "turning it off is immediate" does not hold from the PC
**Checked in code.** See report 02, F1 (`JarvisRuntime.kt:3545-3546`, only caller of the refresh
is `PhoneNotificationsPlate.kt:75`). Every other part of the safe version is followed (below).

## Open question, not a violation by the letter

### Q1 - Entity layer ON by default while LoCoMo shows it hurts (owner's call)
**Checked in code and docs.**
- It is on unless turned off: `backend/rebuilt/jarvis_memory.py:4388-4390`
  `_ENTITY_RECALL = os.environ.get("JARVIS_MEMORY_ENTITIES", "1")...` ("Chat recall uses the entity
  layer unless JARVIS_MEMORY_ENTITIES=0").
- Every chat turn asks for it: `backend/jarvis_past.py:430-441` (`store.search(query, entities=True, ...)`),
  used inside `search()` at `jarvis_memory.py:2382` (adds linked names to the query) and `:2506`.
- It dates from 4c60a352, 2026-09-25 ("Memory wave 3: the entity layer"), a day BEFORE the
  2026-09-26 "a change that makes a number worse is not kept" rule.
- The drop: `docs/MEMORY-SCOREBOARD.md:138-139`, commit e8657e6b (github-repos branch, 2026-09-28):
  plain 45.0% / 9.5% / 0.238 / 18.9% vs entity layer 32.0% / 3.6% / 0.124 / 11.8%, "build machine,
  words only". Line 142: "the entity layer made every number worse, in every one of the five chats.
  Nobody has looked into why yet." CLAUDE.md lines 853-855 repeat this.
- Caveats written there: words only (no meaning model), and one stored item is a chat line, not a fact.
- What to do: have the owner run the LoCoMo test on the PC with real models. If it still loses, the
  rule's spirit says turn it off: one line,
  `[Environment]::SetEnvironmentVariable('JARVIS_MEMORY_ENTITIES', '0', 'User'); Write-Host 'Done. Quit Jarvis from the tray and start it again.'`
  (the 71-fact table and "who is my sister?" questions should be re-checked with it off first, since
  those are what the layer was built for).

## Everything else, decision by decision

Legend: **OK** = checked in code in this audit; **OK (tests)** = the named test passes here;
**Not built** = the decision queues work that does not exist yet (not a violation);
**Not re-checked** = older decision whose code the new work did not touch; I did not re-verify it.

### The 5 rules and "also standing"
| Decision | Status | Evidence |
|---|---|---|
| Rule 5 note: never commercialized, NC licences fine | OK | Doc-only rule |
| No model catalogue on the phone | OK | No new phone file lists installable models; `net/ModelsCache.kt` replays only what was already shown (grep for catalog/qwen/llama/gemma in new phone code: comments only) |
| `X-Jarvis-Client: hud` on every request | OK for new Rust modules | `brain/chatbot.rs:304,409`, `goals.rs:159,257`, `widgets.rs:314,331`, `projects.rs:267,289` all use `commands::jarvis_headers` |
| No bulk approve | OK | Forget-a-time-frame is the owner's named exception (one card listing every item); compare lists every AI on one card; plan card off |
| Maker "darknight11ish", not "Jarvis Labs" | OK | `tauri.conf.json:81-82`; `test_version.py:87` checks; "Jarvis Labs" appears only in docs/CLAUDE.md |

### 2026-09-18 / 09-20 (model switch/install from phone), 09-24 (learning, voice, notes), 09-25, 09-26 (most)
Not re-checked, except where below. The new work did not change `jarvis_search.py`,
`jarvis_manner.py`, `voice-flow.js` or the web-search patch (`git diff --stat 9cdb0567..HEAD`).

| Decision | Status | Evidence |
|---|---|---|
| Web search ships switched on, SearXNG default | OK (unchanged) | `jarvis_search.py:121` `DEFAULT_PROVIDER = "searxng"`, `:282` defaults when no file |
| "I heard you" sound off by default (09-25) | OK | Phone `data/ClientSettings.kt:92` `prefs.getBoolean(KEY_HEARD_SOUND, false)`; desktop `voice-flow.js:274` on only when stored "on". Stale comment: phone `voice/VoiceFlow.kt:361` still says "on by default" (low) |
| "Listening" sound after bare "Hey Jarvis" joins that switch (09-28) | Not built | No such sound in either app. Note: Jarvis Live's end tone (`main.js:5147-5170`, `playLiveEndTone`) plays regardless of the switch - a separate Live sound, not the "I heard you" one; mention to the owner |
| Humour off by default (09-27) | OK (tests) | `jarvis_manner.py:87` `HUMOR_DEFAULT = False`; `test_manner.py` |
| Focus report: no streak line (09-27) | OK | `jarvis_focus.py:480-515` still returns `streak` in the data; both apps parse it (`focus.js:89`, `net/Focus.kt:73,92,105,124`) but nothing reads the parsed value (no `.streak` use in either app), so it is never shown |
| Crisis 988/911, never learned, never counted (09-27) | OK (tests) | `test_wellbeing.py` 213/213 in the full tree; `jarvis_intake.py:234,279-285` skip crisis turns; `import_history.py:22,793` skips crisis messages; Live: `jarvis_live.Engine.note_crisis`, ARCHITECTURE §5 |
| Crisis thumbs-down stops counting (09-28, 248227a2) | OK (tests) | `test_wellbeing.py` includes `t_a_crisis_answer_marked_wrong_is_not_counted` (passes) |
| Memory changes measured before kept (09-26) | Partly | Said-again tiebreak OFF (`jarvis_memory.py:691-692`), re-ranker OFF (`:671`). 7d169fc9 (forgotten facts not re-learned) ran `eval_memory.py` ("every accuracy number identical") but did not add a scoreboard row; Live's side-talk learning exclusion (cfff8d5b, b221174d) names no eval run. Low - both only make learning stricter |
| Phone connects through Tailscale/Meshnet only (09-28, replaces home addresses) | OK | `data/PhoneAddress.kt:11-16,59` refuses 192.168.x/`.local`; fixture only renamed the owner's machine to `my-pc.nord` |
| Reading phone notifications - safe version (09-26, built 09-28) | Mostly OK | Off by default + one card (`test_phone_notifications.py` 70/70); allow list empty, banking blocked, SMS dropped twice (`PhoneNotificationListenerService.kt:56-60`); codes redacted before storing (`:67`); nothing sent to the PC by the service (`:44-45`). Gap: V3 |
| Smartwatch: notifications stay on the phone | OK | Every phone notifier, including the new `LiveService`, `ChatbotNotifier`, `WakeResumeNotifier`, references the watch/local-only setting |
| 12 GB card features not on before measured | OK | Live camera `jarvis_live.py:24-26, 1180-1186` (off until a photo test passes); chatbot full version `jarvis_chatbot.py:764-790` needs `[chatbot] full_version` AND a running lane; Projects code-writing not built; app builder not wired |
| Plan card only after multi-step safety tests pass | OK (tests) | `jarvis_plan.py:302-338` needs `tools/tool_eval/tool_eval_results.json` with >=90% multi-step and 0 carried injections; that file does not exist (`ls tools/tool_eval/`). `test_plan.py` 72/72, `test_agent_plan_wiring.py` 49/49. The field names it reads (`models -> summary -> full -> multi/injection.carried`) match what `ollama_tool_eval.py:592-610,700-705` writes. Note: `_results_path()` (`jarvis_plan.py:297-299`) looks in `<backend folder>/../tools/tool_eval/` - on the owner's PC the backend is outside this repo, so a real run in the repo would not unlock it. Safe (fails closed) but worth knowing when the owner does run it |
| Games/role-play temp chat, inside jokes, "From now on" with Undo, music no card, news safe version, reading tools from PC, History search box (09-27) | Not re-checked | Unchanged by new work |

### 2026-09-27/28 studio review answers
| Decision | Status | Evidence |
|---|---|---|
| Talk-to-type: one card to switch on, PC only | OK | `talk_type.rs:10-17` (ON = `change_own_config` card via `/api/voice/enroll`); §8 row 29. CLAUDE.md:511 still says "Not built yet" (stale, low) |
| Web search / weather / home answers read aloud | Not re-checked | - |
| Chatbot driver: Gemini website, driven openly (reversed 2026-09-29), spare account | OK in design/code comments | Not tried for real (ARCHITECTURE §4 rows say so) |
| Inbox tidy by voice | Not built | No module |
| Animal voices offered once, otter not Sky | **Violated** | V1 |
| Kokoro v1.0 | Not built | Voices still numeric (`jarvis_voices.py:388-399`) |
| Prompt-injection detector trial | Not built | No module |
| Build the chatbot driver first; one-card/two-card versions | OK | `jarvis_chatbot.py:764-790` |
| Phone tap to talk, stopping at a pause | Not built | No match in phone code; listed in docs/STUDIO-REVIEW-2026-09-27.md:75 |
| Projects (both kinds, card per change, Shareable off, build order, private mark card) | OK, except goals join | `jarvis_projects.py`; Shareable off by default; Goals not joined (report 02, F2) |
| Swipe setting on phone | OK | `data/Security.kt:32`, §8 row 86 |
| Versatile driver; studio's extra chatbots confirmed | OK | Presets in `jarvis_chatbot_api.py:240-275`; website adapters |
| Money limit before API use; "about"; hard stop with answer caps | OK | `jarvis_chatbot_api.py:607` ("About {left} of {limit} left..."), `:868-873`, `:1469-1471`; caps table `:133-159` |
| DeepSeek usable with estimate check only; OpenAI keeps gpt-5-mini | OK | `jarvis_chatbot_api.py:153` "UNVERIFIED - NO CAP IS SENT", `:165`; `:240` `"gpt-5-mini"` |
| Compare: 3 on one card, 4 on two, captcha/sign-in left out | OK | `jarvis_chatbot_compare.py:98` `MAX_AIS = {CB.ONE_CARD: 3, CB.TWO_CARDS: 4}`; `:111-120` left-out words; `:46-52`. Comment `:92` still says "PROPOSED" (stale, low) |
| Customer-support chats | Not built (design only) | Commits 87545503, c58a07a4 touch only CLAUDE.md and the design doc |
| Look at the screen (both devices) | Backend rules only | JARVIS-API §62 header says "not in the apps yet" |
| Screen answers after "Hey Jarvis" stay on screen, setting to allow | OK | Default `screen_on_screen` (`test_voice_strict.py:690`); both apps show it |
| Jarvis Live (trust default full, stricter setting, App lock end, one interrupt setting, side talk not kept, crisis more time, camera off, 2-second check) | OK (spot-checked) | `test_voice_strict.py:818` default FULLY; desktop Brain rail "Now" (`brain.html:106`); one "Interrupting Jarvis" (`live-rules.js:32`); camera off (above) |
| Forget a time frame: one card, risky, 10-minute Undo | OK (docs + fixtures) | ARCHITECTURE §3 lines 323-335; shared `forget-range-cases.json` identical on both apps |
| One or two graphics cards | OK | - |

### 2026-09-27/28 animal-face decisions
| Decision | Status | Evidence |
|---|---|---|
| Mouths follow the real voice | OK | Lip-sync commits in both apps |
| Calm body motion; serious moments calm, plain voice | OK | `wellbeing` event read by both apps (`jarvis-link.js:586`, `JarvisRuntime.kt:1396`); `test_wellbeing.py` covers the plain voice. ARCHITECTURE.md:1409 still says the apps' side "is not built yet" (stale) |
| Not connected = asleep with hollow ring | OK | ARCHITECTURE §8 lines on `drawOfflineRing` in both apps |
| Zs on standby only; Still option off by default | OK | "Keep the animal still" in both apps |
| Wake/sleep animations; monkey; sharp on capable hardware; otter fur and water | OK | Commits aea8a0e9, 22954912, 4c5ce8d1, e9563510 |
| Sun/moon off by default; weather off by default; Open-Meteo = card | OK | `jarvis_sky.py:284` `DEFAULTS = {"show": False, ..., "weather": "off"}`; `:61-63` ON is one `change_own_config` card |
| Every animal option in one place | OK | See V2 |
| Jarvis can change any animal option when asked | **Violated** | V2 |

### 2026-09-28 repo-refs milestones and app builder
| Decision | Status | Evidence |
|---|---|---|
| Milestone 7 (prompt-cache share, both apps) | OK | 564c90a6: `brain.js` + `ApiModels.kt` |
| Milestone 12 (said-again tiebreak, OFF) | OK | `jarvis_memory.py:691-692` |
| Milestone 13 (LoCoMo in self-test) | OK | `eval_memory.py --locomo`; drop recorded (Q1) |
| Milestone 8 (crisis wrong gap) | OK | Fixed, above |
| Copying the owner's voice stays refused | Not re-checked | - |
| App builder: local first, card per merge/command, aider locked down | Workspace only | `jarvis_app_workspace.py` not wired to any tool, route or screen; see report 02, F3 about Projects overlap and the 12 GB wait |

### Built/Fixed entries (Try the cloud model, Goals, plan card, third card, models cache, phone notifications, CI fixes)
All OK as described, with the notes above: plan card off and gated; third card never a default
(`second_card_third_assign` card per CLAUDE.md, `test_second_card.py` not re-run by me); models
cache is no catalogue; phone notifications gap V3. Goals' weekly check-in asks one card
(`jarvis_goals.py:421`, `plain_repeat=False`) - CLAUDE.md says "the same ONE schedule_repeat card a
repeating reminder already raises", but since 2026-09-26 a plain repeating reminder asks no card.
**Owner's call:** keep the card for goals, or treat the check-in as a plain repeat like Today cards.

## Tests I ran (on a copy)
`test_plan` 72/0, `test_agent_plan_wiring` 49/0, `test_wellbeing` 213/0, `test_voice_upgrades`
268/0 (it asserts the wrong default, V1), `test_phone_notifications` 70/0. (On a partial copy of only
`backend/` and `tools/` some of these failed because they read app fixtures; on the full-tree copy
all pass.)
