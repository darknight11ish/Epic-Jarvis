# Pixel 9 field test — the deployed build, driven on the phone (2026-11-04)

Phone: Google **Pixel 9** (`tokay`), Android **17** (SDK 37), build 15:39 PT, serial `48270DLAQ00A19`.
This is the owner's PRIMARY phone. The OnePlus seen in earlier probes is the backup and was not touched.

## What the deploy did to this phone (measured)

| item | before | after |
|---|---|---|
| Jarvis app | 0.2.3724 / `1000003724` (lastUpdated 07:04) | **0.2.3742 / `1000003742`** (installed 14:42) |
| APK | — | `jarvis-client-8a4a8e7.apk`, 34,868,078 B, sha256 `03BDE866…` = the `client-latest` release digest |
| pairing survived | firstInstallTime `2026-10-15 19:44:14` | **unchanged** `2026-10-15 19:44:14` |

## Results (each driven, with its evidence in this folder)

| check | result | evidence |
|---|---|---|
| App launches on Android 17 and talks to the deployed backend | **PASS** — header shows a green dot and **Connected** | `pixel-home.png`, `ui-home.xml` |
| Typed chat round-trip phone → PC → local model → phone | **PASS** — sent "what is 2 plus 2", answer **"It's 4."** | `pixel-reply2.png`, `pixel-now.png`, `ui-fullscreen.xml` |
| Conversation is kept on the PC, listed as from the phone | **PASS** — History: `what is 2 plus 2`, `Today 14:45 · phone · 2 messages`; "kept on your PC, encrypted: On" | `ui-history.xml`, `pixel-history.png` |
| Answer actions (feedback / pin) | **PASS** — "This answer … Right / Wrong … Pin message … Kept on this phone. In History, under Pinned." | `ui-tap1.xml` |
| Face bar layout (#1134: full-screen face bar must not take the whole screen) | **PASS (visual)** — header, strip, face area and bottom bar are all visible; "Back to full screen" control present | `pixel-home.png`, `pixel-fullscreen.png` |
| Face-bar typing box (#1139: fills its cell, says "Ask Jarvis") | **PASS** — `EditText` bounds `[650,2188][1022,2314]` in the bottom bar, placeholder "Ask Jarvis", sends with Enter | `ui-home.xml`, `ui-typed.xml`, `ui-reply.xml` |
| Settings screen opens (all sections) | **PASS** | `ui-settings.xml`, `pixel-settings.png` |
| Live screen opens (voice-check rule is written where the owner sees it) | **PASS (screen only;** the spoken part needs the owner) | `ui-live2.xml`, `pixel-live2.png` |
| Reminders screen opens; fired timers + Snooze/Delete shown | **PASS** — two 5-minute timers shown as "Just went off" (14:49, 14:56) with Snooze/Delete; "0 reminders" | `ui-reminders2.xml`, `pixel-reminders2.png` |
| App crashes / ANRs while doing all of this | **NONE** — app logcat has no errors, only normal IME/Insets/JIT lines | app pid 15215 logcat captured live |
| Update prompt | **CORRECT BUT IMPORTANT** — app says "A newer build of this app is on GitHub (main, 715aa57)"; `client-latest` now really publishes `jarvis-client-715aa57.apk` (34,868,074 B, sha256 `38250e9c…`, 22:36Z), which is newer than the deploy build. The phone was deliberately left on the deploy-validated 0.2.3742 build (8a4a8e7) | release API + on-screen row |
| Launcher quick-link widget | **NOT PRESENT on the Pixel launcher** — the "Reconnecting" widget seen at 14:01 was on the OnePlus; nothing to reproduce here | `launcher.xml`, `pixel-launcher.png` |
| Locked-phone voice check, "hey Jarvis", Live voice, spoken answers | **BLOCKED on the owner** (needs speech) | — |
| Call recording from the phone, hands-free approval mode, SMS writing | **NOT BUILT / NOT IN THIS BUILD** — the call-recording PRs are open, hands-free is the new request | PR #1151 |

## Findings worth acting on

1. **The deploy skipped this phone.** The deploy's phone step installed 0.2.3742 on the *connected* device, which was the OnePlus backup; the primary Pixel 9 was still on 0.2.3724 (07:04). It is now on the deploy build, pairing intact. A deploy should name the device it installs to, not "the connected one".
2. **A newer client build than the deploy exists on `client-latest`** (`jarvis-client-715aa57.apk`, from post-deploy main `715aa5762`). The phone's update prompt correctly offers it. Decision needed later: stay on the deploy-validated client until a new deploy, or update the phone to the post-deploy build (not validated as a pair with the live backend).
3. **Android 17 compatibility on the deploy build is good** — no crash, full chat, screens, and actions all worked on the primary phone.
4. Nothing on this phone showed the "Reconnecting" state; the earlier OnePlus observation stays a backup-phone/widget observation, not a backend problem.

## What only the owner can test (already in OWNER-TEST-STEPS.md)

- Lock the phone, say "hey Jarvis": it should ask for the owner voice check only in the documented cases.
- Open Live, ask a spoken question (and "what's on my screen?" while at the PC).
- The by-ear reminder/routine ticks and a real spam-free conversation.
