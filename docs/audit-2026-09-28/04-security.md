# Audit 4 - Security of the new work (backend, desktop, Android)

Tree: `scratchpad/integ` (branch `audit-integration`, HEAD deaca649), new work = `git diff 9cdb0567..HEAD`.
Checked against the five rules and the dated owner decisions in the combined `CLAUDE.md`.

## Summary in plain words

**No critical findings.** I found nothing that sends email, files, passwords or saved memory
to the internet by itself. I found no public tunnel, no approval that happens without a person,
and no API key written to a log or to a plain file. The riskiest new features (the chatbot
driver, "Try the cloud model", Jarvis Live, widgets you describe, the app builder, Forget a
time frame) are built carefully, and the checks hold up when read line by line.

What I did find:

| # | Severity | What | Branch |
|---|---|---|---|
| 1 | **High** | The phone's one-time-code hider misses common code texts ("Use 482913 to log in", a code in the body when the word "code" is only in the title, "PIN", other languages), so codes can reach the AI model. That breaks the owner's condition for this feature | continuation-03kls1 |
| 2 | Medium | Lockdown says "anything that runs by itself has stopped", but a chatbot conversation that is already running keeps sending, and the Open-Meteo weather keeps fetching | competitors (Lockdown) vs research (chatbot) and 3d-animal (sky) - a clash between branches |
| 3 | Medium | Captured phone notifications are never deleted: not when the switch is turned off, not when an app is taken off the list. They sit unencrypted in the app's storage | continuation-03kls1 |
| 4 | Medium | The "private topic" check misses common health words (diabetes, pregnant, HIV, blood pressure, a medicine name). The chatbot card says "nothing private is sent", and "Try the cloud model" is described as never letting a private question out. Both rely on this check | research (chatbot, cloud-say-yes); the check itself is older |
| 5 | Low | Any other app on the phone can switch on "Hey Jarvis" listening by opening Jarvis with a special instruction (`ACTION_RESUME_LISTENING`) while App lock is off | competitors |
| 6 | Low | Importing a Claude or Gemini export reads each file inside the zip whole, with no size limit. A huge file can use up the PC's memory (the ChatGPT path has limits) | competitors |
| 7 | Low / owner's call | The plan card switches itself on when a results file appears on disk. There is no owner setting for it, and the file's location is next to the backend folder, not the repo | continuation-03kls1 |
| 8 | Low (latent) | The router's "screen words stay on this PC" rule (`has_screen`) is not passed by any chat-route patch. Nothing sends screen words yet, but it will matter once "Look at this" is connected | research |

---

## 1. HIGH - the one-time-code hider misses common code notifications

**Checked in code. Needs a real try on the device to see it with real notifications.**
Branch: `claude/jarvis-continuation-03kls1` (commit 638464b1).

**What's wrong:** the phone hides a code only when the *same field* (the title, or the text)
contains one of a short list of English trigger words, or when the whole field is just digits.
Many real code texts do not match either rule.

Evidence - `jarvis-client/app/src/main/java/com/jarvis/client/data/NotificationRedactor.kt`:
```kotlin
55  private val TRIGGER = Regex(
        "code|otp|one[- ]time|passcode|verification|verify|authenticat|2fa|" +
            "security code|access code|login code|confirmation code", IGNORE_CASE)
69  private val CODE = Regex("""\b\d{3}[- ]\d{3}\b|\b\d{4,8}\b""")
72  fun redact(text: String): String {
74      if (!TRIGGER.containsMatchIn(text) && !isBareCode(text)) return text
79  fun redactBoth(title: String, text: String) = redact(title) to redact(text)
```
I copied the same rules into Python and ran them. Each of these came through **unchanged**:
- `Use 482913 to log in to Instagram`
- `482913 - valid for 10 minutes. Do not share.` (with the title "Your code": the title and the text are checked separately, so the trigger word in the title does not protect the text)
- `Your Microsoft PIN is 4821`
- `Your sign-in number: 4821 5930`
- `Tu código es 482913`
- `482913 is your Facebook confirmation`

The path to the model: `PhoneNotificationListenerService.onNotificationPosted` stores
`redactBoth(...)`. Then "Attach recent notifications" (`MainActivity.kt:2411-2414`) puts
`CapturedNotifications.sharedText()` into the chat as shared text, and the owner presses Send.
On the PC, nothing masks codes before the model sees them. `jarvis_paste_guard.py`'s own
docstring says: "THE MODEL ALREADY SAW THE UNMASKED WORDS" - it only cleans the stored history.

**Why it matters:** the owner's decision (2026-09-26) says "one-time codes hidden before
anything reaches the model". The data stays on the owner's own devices (the local model), so
this does not break rule 1. It does break the condition the owner set for switching this
feature on.

**Proposed fix (code change):**
1. Check the trigger words across the title and the text together:
   `val hit = TRIGGER.containsMatchIn("$title\n$text")`, then mask both when `hit` is true.
2. Add these trigger words: `pin|log ?in|sign[- ]?in|login|password|código|code de|kod|confirm`.
3. When an allow-listed app's text has any 4-8 digit run next to "is"/"use"/":", mask it. Hiding too much is the documented choice, so this fits.
4. As a second guard, run `jarvis_mail_mask.hide()` on the PC over any user message whose provenance is `shared`, before the model sees it. `jarvis_mail_mask` already exists, and the chatbot driver already uses it.

---

## 2. MEDIUM - Lockdown does not stop a running chatbot conversation or the Open-Meteo weather

**Checked in code.** This comes from three branches that did not know about each other.
Lockdown came from `audit-competitors-vyqpt1` (30bca340), the chatbot from
`ai-assistant-research-ff37vy`, and the sky weather from `3d-animal-mascot-8dr0tb` (22954912).

**What's wrong:** turning Lockdown on tells the owner that everything that runs by itself has
stopped. Two new ways out of the PC keep going anyway.

Evidence:
- `backend/jarvis_asks_first.py:1595-1597`: `LOCKDOWN_DONE = ("Lockdown is on. Everything that would leave this PC asks you first, and anything that runs by itself has stopped. ...")`
- `jarvis_asks_first.py:1558-1573`, `LOCKDOWN_ACTIONS`: this list has no chatbot action, and nothing for the sky or Open-Meteo.
- `request_lockdown` (`jarvis_asks_first.py:1819-1840`) only writes the file and publishes an event. It does not stop anything already running.
- `grep -i lockdown backend/jarvis_chatbot*.py backend/jarvis_sky*.py` finds nothing. `jarvis_chatbot.run()` keeps sending follow-ups for up to 20 messages or 30 minutes after the one card. `jarvis_sky.read_open_meteo` (`jarvis_sky.py:657-670`) keeps fetching `api.open-meteo.com` about every 20 minutes.
- Starting a *new* chatbot conversation still raises its card (tier `ask`), so that part is fine. Only the conversation that is *already running* goes on.

**Why it matters:** Lockdown is the owner's "stop, nothing leaves" button. The owner would
reasonably press it mid-conversation. The screen then says "stopped" while messages are still
being typed into a chatbot website.

**Proposed fix (code change):** in `request_lockdown(on=True)`, call `jarvis_chatbot.stop(...)`
(and the compare stop). Also check `jarvis_asks_first.lockdown_on()` in `jarvis_chatbot.run()`
before every `adapter.send()`, and in `jarvis_sky.refresh()`: treat Lockdown as "weather off",
with the reason. Add both to `LOCKDOWN_DETAIL`'s list, and add a test in `test_lockdown.py`.

---

## 3. MEDIUM - captured phone notifications are never deleted

**Checked in code.** Branch: `continuation-03kls1`.

**What's wrong:** when the owner turns "Reading phone notifications" off, or removes an app
from the list, what was already captured stays on the phone. It stays there forever, and it
comes back if the switch is turned on again.

Evidence - `jarvis-client/.../data/CapturedNotifications.kt`:
- `:63` The 7-day age filter runs only inside `add()`: `.filter { it.postedAtMs >= now - MAX_AGE_MS }`.
- `:70` `recent()` does **not** filter by age.
- `:72` `fun clear() = prefs.edit { remove(KEY_ITEMS) }`. A search of the whole app found no caller of `clear()`.
- The store is a plain `SharedPreferences` file (`jarvis_captured_notifications`), not encrypted. `allowBackup="false"`, so it does not leave the phone.
- `MainActivity.kt:2300-2303`: the attach button checks only the on/off switch and `sharedText() != null`. It does not check whether each item's app is still on the allow list.

**Why it matters:** "turning it off is immediate" is the owner's rule for every loosening
switch. Here, off stops *new* capture but keeps up to 200 old notifications (other people's
messages, for example). If the switch is turned back on, even weeks later, those old items can
be attached as "recent". That includes items from an app the owner has since removed from the
list.

**Proposed fix (code change):** call `CapturedNotifications(ctx).clear()` when the setting
turns off (where `ClientSettings.phoneNotifications` flips to false). On
`NotificationAllowListStore.remove(pkg)`, drop that package's items. Make `recent()` apply
`MAX_AGE_MS` as well. Optionally, store the items in the app's existing encrypted preferences.

---

## 4. MEDIUM - the private-topic check misses common health words, and two new features lean on it

**Checked in code, and by running the check** (the backend venv in the scratchpad).
`jarvis_router.is_private()` is older code. The new reliance on it is from the research branch.

**What's wrong:** I ran `rebuilt/jarvis_router.is_private()` on some phrases. It returned
**False** for: "my cholesterol is 240", "I have diabetes", "my blood pressure is high", "I am
pregnant", "my HIV test", "I take sertraline 50mg", "my divorce lawyer". It returned True for
cancer, therapist, salary and bank.

`jarvis_chatbot.last_check(goal_check=True)` therefore passed these goals:
- "My cholesterol is 240, what diet should I follow?"
- "My sister Anna is pregnant, what gifts?"
- "I live in Springfield near the Kwik-E-Mart, best pizza?"

The promises that rest on this check:
- `backend/chatbot.patch`, the gate's risk line: "...nothing private is sent, and what is sent cannot be taken back".
- `backend/cloud-say-yes.patch` comment: "a yes can never pull a private, tainted or picture turn out". The private part of that is only `is_private()` (`rebuilt/jarvis_router.py`, the gate order in `choose()`: `lockdown`, `taint`, `image`, `screen`, `private`, `secret`, `complexity`, `budget`, then `offer`/`escalate`).

**Why it matters:** in both features the owner sees the exact words before anything leaves:
the goal is shown word for word on the card, and the cloud question is the owner's own
question. So this is not a silent leak. But the card's wording ("nothing private is sent")
over-promises. And a health question with "Try the cloud model" pressed does go to the cloud
lane, although the docs imply it cannot.

**Proposed fix:** either (a, a code change) widen the private-topic list with common health and
medicine words, measured with `test_router_private_terms.py`; or (b, the owner's call) change
the chatbot card's line to "Jarvis checks for passwords, codes, addresses, phone numbers,
private topics and things it saved about you - read the goal before you say yes". Both are
reasonable. (b) is more honest either way.

---

## 5. LOW - another phone app can switch on "Hey Jarvis" listening

**Checked in code. Needs a real try on the device.** Branch: `audit-competitors-vyqpt1` (5027bd68).

`MainActivity` is exported (it is the app's launcher screen), and it acts on
`com.jarvis.client.action.RESUME_LISTENING` coming from *any* intent (`MainActivity.kt:432-438`).
When it gets one, `MainActivity.kt:1233-1256` calls `startPhoneListening()`
(`MainActivity.kt:2582-2601`), which starts `WakeWordService`. The only checks are paired,
App lock (`if (locked) return`) and `WakeRules.mayListen`. Nothing checks that the owner had
listening on before the restart (the notice's own `WakeResume.offer(..., wanted)` flag), and
nothing checks that the intent came from Jarvis's own notification. A foreground app on the
phone can therefore turn Jarvis's microphone listening on while App lock is off.

The audio only goes to the owner's own PC, and Android shows the microphone indicator. That is
why this is low.

**Fix (code change):** send the notice's tap through a `PendingIntent` that carries a random
one-time token saved when the notice is posted, and compare that token in
`readResumeListeningIntent`. Or at least require the saved "wanted" flag.

---

## 6. LOW - importing a Claude or Gemini export has no memory limit

**Checked in code.** Branch: `audit-competitors-vyqpt1` (96f0418d).

`backend/import_history.py:722-741`, `_walk_json_documents`, which the Claude and Gemini
parsers use (`:299`, `:349`), calls `json.load(io.TextIOWrapper(z.open(name)))` on every
`.json` inside a zip with no size cap. The ChatGPT path (`_json_items`, `:447`) is capped
(`WHOLE_FILE_MAX`, `ONE_ITEM_MAX`). Nothing is extracted to disk, so a file inside the zip cannot
be written to the wrong folder. The only risk is running out of memory. The route is PC-only
(`jarvis_history_import.py`, `jarvis_owner_check.from_this_pc`) and the file is the owner's
own, so this is low.

**Fix:** reuse `_json_items(fh, info.file_size)` in `_walk_json_documents`, or refuse
`info.file_size > WHOLE_FILE_MAX`.

---

## 7. LOW / owner's call - the plan card switches itself on from a file

**Checked in code.** Branch: `continuation-03kls1`.

`backend/jarvis_plan.py:297-299`:
`_results_path() = Path(__file__).parent.parent / "tools" / "tool_eval" / "tool_eval_results.json"`.
`enabled()` (`:302-338`) turns `propose_plan` on for everyone as soon as that file shows a
passing result. There is no owner setting and no card.

Two consequences:
- (a) On the owner's PC the backend lives outside the repo (ARCHITECTURE section 9), so running the eval in the repo probably never turns it on. This is a function problem.
- (b) Anything that writes that JSON file turns it on silently.

The plan runner itself is sound. `_plan_step_dispatch` (`jarvis_agent.py:835-954`) re-checks
every step's real tier, refuses plug-in tools and `send_email`/`draft_email`/schedule tools, and
gives risky and `from_step` steps their own card. The plan's result is counted as read outside
text (`took_in`, `_NOT_READING` at `jarvis_agent.py:3118`).

One small difference: a `web_search` step goes through the generic gate at tier `ask`. That is
stricter than a direct search, not looser, but the card loses `web_search_card_lines`' reasons.

**Suggestion:** the owner may want "Turn on the plan card" to be an explicit PC-only card, once
the file passes.

---

## 8. LOW (latent) - `has_screen` is never passed to the router

**Checked in code.** `rebuilt/jarvis_router.py:621-631` keeps screen words on the PC only when
the caller passes `has_screen=True`. No patch passes it: `grep has_screen backend/*.patch` finds
nothing, and `cloud-say-yes.patch` passes `has_image` but not `has_screen`.
`jarvis_screen.turn_has_screen()` (`jarvis_screen.py:683`) exists "for the chat route to hand
jarvis_router.choose(has_screen=...)". `read_screen` is not a registered tool yet, so nothing
leaks today. Whoever connects "Look at this" or "Watch with me" to chat must add
`has_screen=jarvis_screen.turn_has_screen(messages)` next to `owner_said_yes` in the same
`choose()` call.

---

## Checked and clean (so nobody re-checks them)

- **Chatbot driver (website).** One card per conversation, tier `ask` only, and a risky approval (`chatbot.patch`). `last_check` runs before every send, the goal included, and blocks whenever a check cannot run (`jarvis_chatbot.py:891-957`). The driver model is on this PC only (loopback), never an Ollama cloud model, and it gets no tools and no memory (`jarvis_chatbot.py:707-727`). Captcha and sign-in pages pause the conversation (`jarvis_chatbot_web.py:750`). The browser is `headless=False`, so its window is visible. The routes sit behind origin and token checks (`jarvis_chatbot_routes.py:461-470`). The audit log gets ids and counts only. ARCHITECTURE section 4 has a row for each site, for the API services and for compare.
- **Chatbot API keys.** Stored in Windows Credential Manager. The address must be https on the preset's own host and port, with no user name, checked before every request (`jarvis_chatbot_api.py:469-487`). Redirects are refused, never followed (`_RefuseRedirect`). Errors never quote the service's text. The key is registered with `jarvis_scrub`. `point_at()` is for tests only, and `_TEST_LOOPBACK_OK = False`. **The money limit is enforced on the PC**, before the card and before every send (`money_check`/`reply_cap`, `:885-944`). Limits and prices can only be set from the PC's command line, and no route can raise them. The DeepSeek gap (no reply cap) is written down honestly.
- **"Try the cloud model".** `owner_said_yes` only changes `offer` into `escalate` after the lockdown, taint, picture, private and secret gates (`jarvis_router.py:596-661`). The cloud lane gets the newest user turn only (the `cloud-one-turn` context in `rules-first-relay.patch`), with `inject_memory=False`. Both apps resend the same question with its provenance (`ChatSession.kt:808-811`, `commands.rs:1713-1754`).
- **Jarvis Live.** A live clip is refused before any check when no session is on for that device (`jarvis_live.py:981-1006`). A session started by "let's talk" is recorded as `by="voice"` by the PC itself (`jarvis_speech.py:2099`). The apps can only claim button, tray or hotkey (`APP_STARTS`). The trust rules match the owner's 2026-09-28 answers exactly (`rebuilt/jarvis_voice.py:2209-2236`). Live pauses while a card raised since Live started is waiting, and cards are decided by tap only.
- **Widgets you describe.** The model writes JSON only, checked against a fixed menu. Buttons are the five tile actions (never Approve or Deny). The desktop checks widget ids before building a URL (`brain/widgets.rs:431`), and holds on a stale link (`:464-466`). No `innerHTML` in any new desktop JS file. The phone widget hides private blocks under App lock or "Hide lists" (`JarvisBoardWidget.kt:95`).
- **Desktop.** No change to the CSP. The new capabilities are narrow (`live-badge.json`, widget-board, sky-read). No new network listener: every new `ThreadingHTTPServer` is in tests, on 127.0.0.1. Talk-to-type keeps the clip out of Clipboard History and Cloud Clipboard (`talk_type/paste_windows.rs:1-15`). `hud_proxy` now hides private reads under "Hide lists".
- **Android.** All 20 `PendingIntent.get*` calls are `FLAG_IMMUTABLE`. `PhoneNotificationListenerService` is `exported="false"` and needs the notification-listener permission. SMS is checked again at capture time. The tile services require the tile permission. `QuickTiles.decide` never approves, holds on a stale link (except Stop everything), and asks for an unlock under App lock. The phone address check is now mesh-only (`PhoneAddress.kt`), matching the 2026-09-28 decision.
- **Forget a time frame.** One risky card listing every item, tier `ask` only, and on the hard-limits list so no app can loosen it.
- **App builder workspace.** Runs nothing. `safe_path` refuses `..`, `.git`, device names and symlink escapes. The merge card shows the whole diff and refuses if anything changed after the card. It is not connected to any route yet (only `_where.py`).
- **Watches.** Each watch gets one card. A search watch refuses when "Ask before every web search" is on, and Lockdown stops it. The GitHub token goes only to api.github.com, with no redirect.
- **MCP and tool updates under Lockdown.** Both ask again (`jarvis_mcp.card_every_start`, `jarvis_tool_updates._lockdown_on`).
- **Backups.** `projects.db` was added to the backup (a good catch by the Projects audit).
- **Logging.** A search of the new backend and Rust lines for printing or logging a key, token, secret or password found nothing real.
