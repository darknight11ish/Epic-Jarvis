# FIELD TEST — 2026-11-02, results only (what is on the machine NOW)

Machine: the owner's Windows 11 PC. Deploy #8 (pin F3 = `fc852e1a7c990e19c869c22e16ce847697ccdb52`).
Backend live at `C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program` (HUD `http://127.0.0.1:4719`,
token resolved read-only through `jarvis_token_store.resolve(...)`; **the token was never printed or logged**).
Phone: OnePlus CPH2419, adb `f0a5b32b`. Desktop: `C:\Users\pcadmin\AppData\Local\Jarvis Desktop`.
Run window: 2026-11-02 14:16 – 15:10 PT. Phone UI read from `adb shell uiautomator dump` XML (screenshots are black
under FLAG_SECURE); no screenshot was relied on for any row.

Verdicts: PASS / FAIL / PARTIAL / BLOCKED / NOT-TESTABLE. BLOCKED and NOT-TESTABLE are never passes. A PASS means the
feature was actually driven on this hardware after the deploy.

## Tier 1 — Health and gate proof

| # | Feature / check | Verdict | Evidence |
|---|---|---|---|
| T1.1 | `/api/version` | PASS | 200; `"api": 1`; `"server": "jarvis-hud"`; `"started": 1793657410.82` = **2026-11-02 14:10:10 PT** (after the deploy restart) |
| T1.2 | `/api/status` | PASS | 200; `"tools": 28`; `"ollama": true`; `"default_model": "qwen3.5:9b"`; lanes `jarvis-escalate/jarvis-critic/jarvis-bulk` |
| T1.3 | Live `jarvis_gate.py` sha256 (both new gate patches) | PASS | `af7d35a3f0dcfb8dcc55ec50a3936a18878dd1f2bda7837f9dc783e04ea57aa6` — exact match to the expected combined sha; 196,351 bytes, mtime 13:35:52 |
| T1.4 | Phone install | PASS | `versionName=0.2.3531`, `versionCode=1000003531`; `firstInstallTime=2026-10-09 22:14:29` (unchanged); `lastUpdateTime=2026-11-02 13:45:02` |
| T1.5 | Phone logcat, no FATAL | PASS | whole buffer, 11,622 lines, `-d -v brief`: zero `FATAL EXCEPTION` / `AndroidRuntime…FATAL` matches |
| T1.6 | Desktop 0.2.397 installed and running | PASS | `FileVersion`/`ProductVersion` = 0.2.397; process `jarvis-desktop` pid 50488, started 14:10:04 PT |
| T1.7 | `/api/pending` waiting=0 at the end | PASS | final read `waiting = 0`; only two cards were created all session, both `search_the_web`, both `denied` by `field-test-2026-11-02` |
| T1.8 | Independent verifier (`verify-deploy5.ps1`) | PASS (with 1 UNVERIFIED cell) | `.dsh-scratch/DEPLOY-2026-11-02-RUN/verify-run-2/stdout.txt` (14:24:59): `PASS 28 / FAIL 0 / UNVERIFIED 1 / WARN 0`, verdict `PASS-with-UNVERIFIED`. The ONE UNVERIFIED is the phone APK-vs-release cell (**never a PASS**): installed `a94823f1…`, `client-latest` has no asset for `fc852e1` (newest is `jarvis-client-daf2684.apk`) |

## Tier 2 — The owner's direct asks and the merged features

| # | Feature (PR) | Verdict | Evidence |
|---|---|---|---|
| 1 | Three phone text removals (#1090) | PASS | (a) Home XML: the sentence `Stops Jarvis talking and anything it is doing…Asks nothing first; approves nothing.` is **absent**; (b) running Live screen XML shows only `To end, say "Okay Jarvis, that's all for now".` — **no** `or use End Live`, and no `Microphone: this phone's` / `Voice: … from your PC` lines |
| 2 | Face typing box + one Attach row + Quick note sheet (#1085) | PARTIAL | Quick note sheet opened (`Quick note` / `To Obsidian` / `#obs File what you type in today's Obsidian daily note` / `Close`); More sheet has **exactly one** attach row (`Attach a file`) that opens the system picker. The face typing box was **not** seen — the face is not "Full screen" on this phone, so the box does not render (untested, never a pass); Quick note survival across rotation not driven |
| 3 | Reminders on the home row, Appearance Settings-only (#1077) | PASS | Home XML icon row = Brain, Inbox, Live, **Reminders**, Settings, Help (6 cells, bounds 0–1080 at y 278–446); **no Appearance icon**; `Appearance` is a Settings row at bounds [515,897][735,943] |
| 4 | Editable phone HUD (#1079) | PARTIAL | Home draws the layout: `YOUR HOME SCREEN · 30 CARDS`, sections `TOP STRIP` / `BODY` / `COMPOSER`, pointer `Rearrange it in Settings, Home screen`; Settings → HOME SCREEN: `Choose which of Jarvis's cards sit on your Home screen…`, `The five built-in arrangements are read-only. Duplicate one to make it yours.`, button `Edit Home screen`. **No card was reordered**, so "layout changes persist" was not driven (not a pass) |
| 5 | Feature directory = 168 contract rows (#1078) | PASS | Settings search `abilities` → card `ALL FEATURES AND ABILITIES` with `168 features` and rows drawn in the PC's own labels (`Command-Only (Runs When You Ask — No Switch Needed)`, first row `Type a message and read the answer`) — on the installed APK |
| 6 | Skeptic preset `No-Nonsense Critic` (#1095) | PASS | Chat `Change your personality to the No-Nonsense Critic` → `No-Nonsense Critic active. Bring me your plan and I'll show you where it breaks.`; `GET /api/manner` `personality` went `warm_peer` → `devils_advocate`; **no card** (`/api/pending` 0, newest history row unchanged). Flawed claim answered: `Verdict: False. The claim is incorrect.` … `Weak point: Assuming more memory automatically implies superior performance ignores the fundamental role of compute throughput and bandwidth bottlenecks.` `Fix: Compare actual benchmark scores…` |
| 7 | Settings by chat (#1068, "stop saying one moment") | PASS | `start saying one moment again` → `On. Jarvis will say "One moment." again…` and `jarvis_voice_flow.one_moment_enabled()` went False → **True**; `stop saying one moment` → `Off. Jarvis will not say "One moment." …` and the same function went True → **False**. Both directions changed the real PC setting; no card either way. **The owner's setting was OFF before and is OFF again** |
| 8 | "One moment." clip uses the voice in use (#1088) — F0 probe | PARTIAL | With the setting ON, `GET /api/voice/moment` returned **200**, a 0.91 s / 24 kHz mono WAV (43,710 bytes), median F0 **240.0 Hz**; the reply voice's own sample (`POST /api/voice/say`) is 1.88 s, median F0 **216.2 Hz** — same female voice range, but this is two different sentences, not a speaker ID, and the owner's ear test was not possible. Note: the owner keeps "One moment." **OFF**, so on this machine as configured **no clip exists at all** |
| 9 | Conversation web-search grant (#1074) | **FAIL** | Two attempts, two wordings (`Give me full approval to search the web for this conversation.`, `Approve web search for this conversation, so you can search without asking me each time in this chat.`). **No `grant_web_search_conversation` card was ever raised** (`/api/pending` stayed empty; history unchanged). The model still answered `Understood. Search is approved for this conversation. Ready to check the web whenever needed.` — a grant that did not exist: the **next search in that same conversation raised an ordinary `search_the_web` card** (`4dcb115905b2`), so nothing was granted. Fail-safe (no bypass), but the row's "one card, then searches run without cards" never happened |
| 10 | Small read-only approval card alone (#1070) | PARTIAL | The card that did appear is one card, read-only in shape and deny-clean: `risk {reversible: yes, reach: outbound, swipe_ok: false}`, `notice {deny_ok: true, approve_ok: false, weight: heavy}`, and `POST /api/deny` answered `200 {ok: true, state: denied}`. "Approved by the card alone / fingerprint optional" **cannot be proven without approving**, which this lane must never do |
| 11 | Staged attachment says not sent (#1084) | PARTIAL | Picked a photo with the system picker; the composer strip read `Attached to your next question — not sent yet. Type it and press Sen…` with a `Remove` button and `Find a date in it`. The strip was then removed (no attachment left staged). The **offline send-failure half was not driven** (that needs the phone offline plus a live send) |
| 12 | Presets search (#1083) | PASS | Settings search `presets` → `1 setting matches.` + `Not in Settings: Focus presets` / `It is in Brain, under Hardware.` + `Open`; tapping `Open` landed on `Brain` → `HARDWARE` → `FOCUS PRESETS` (row `General - Current`, `qwen3.5:9b on RTX 2060 (the long-context card), 196,608 tokens`) |
| 13 | Live says what it really checks (#1082) | PASS | Live screen while running: `Jarvis Live · 30 min left`, `To end, say "Okay Jarvis, that's all for now".`; idle screen: `Jarvis listens after every answer until you end it, say "Okay Jarvis, that's all for now", or it has been quiet for 90 seconds. Every full sentence is checked for your voice on your PC; once this session is verified, a short reply is trusted without a check.` Live was started and **ended** (`Jarvis Live ended` / `You ended it.`) |
| 14 | PiP "hey Jarvis" is one input (#1086) | NOT-TESTABLE | PiP is Off on this phone, and a wake-word test needs a human saying "hey Jarvis" into the phone. Neither the setting flip (owner's setting) nor the voice input is available to this lane |
| 15 | Live capability read-aloud (#1080) | NOT-TESTABLE | The spoken half needs a Live turn with a real voice asking "what can you do"; this lane has no voice input. Its text half ("say what Live really checks") is covered and passing under row 13 |

## Tier 3 — Safety

| # | Check | Verdict | Evidence |
|---|---|---|---|
| S1 | Nothing left waiting on `/api/pending` | PASS | final `waiting = 0`; both cards this session were denied and appear as `denied` in history |
| S2 | No approval was ever auto-answered | PASS | the only two decisions this session are `POST /api/deny` on `d5b6abce5cf2` and `4dcb115905b2`, `decided_by = field-test-2026-11-02`, state `denied`. No `approve` call was made |
| S3 | No secret printed | PASS | the token was read only inside the helper (`jarvis_token_store.resolve(...)`), never echoed, never written to any log or to this file |
| S4 | The owner's settings are as they were | PASS | flipped for the test and **put back**: `personality` `warm_peer` → `devils_advocate` → `warm_peer`; `one_moment_enabled()` `False` → `True` → `False` (the owner's own OFF state, re-read from `jarvis_voice_flow`). No other setting touched |

## What I could not test and why

- **PiP "hey Jarvis" (#1086)** — PiP is off and the row needs a spoken wake word; there is no way for this lane to say it.
- **Live capability answer spoken (#1080)** — same reason: no voice input, and the row's point is the audio.
- **The face typing box (#1085)** — the face is not "Full screen" on this phone, so the box never renders; turning the face size up would be a permanent change to the owner's appearance settings.
- **HUD reorder persistence (#1079)** — I opened the editor and read the Home layout but deliberately did not drag a card, because a reorder is the owner's setting and a mis-dropped drag is not easily undone from adb. Driving it needs the owner present.
- **The web-search grant's own card (#1074)** — never raised in two attempts, so there was nothing to approve or deny; this is the FAIL above, not an untested row.
- **The "no fingerprint" half of #1070 and the approve path of any card** — approving is outside this lane by instruction; only denials were made.
- **The offline send-failure half of #1084** — needs the phone offline and a real send; the staged-strip half was driven and then cleaned up.
- **"One moment." ear test (#1088)** — needs the owner's ear; and with the setting the owner actually uses (OFF) no clip is produced at all.
- **Phone screenshots** — black under FLAG_SECURE; every phone row above is from `uiautomator dump` XML text, and any purely visual claim is recorded as untested rather than passed.
- The deploy verifier's phone APK-vs-release cell is **UNVERIFIED** by its own report (`client-latest` has no asset for `fc852e1`); it is not repeated as a pass here.

**PASS 16 / FAIL 1 / PARTIAL 5 / BLOCKED 0 / NOT-TESTABLE 2**
