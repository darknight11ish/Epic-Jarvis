# Jarvis launch video v3: "It asks first"

Two cuts from one project:

- `jarvis-launch-v3.mp4`: 1920×1080, 35 s, for the README and GitHub.
- `jarvis-launch-v3-vertical.mp4`: 1080×1920, 15 s, for a phone held upright.

## How this version was made

v2 was audited by a team:
- a film editor, a motion designer, an AI developer, a music producer, a UI engineer and an advertising specialist;
- four everyday viewers who are not developers: a privacy-wary viewer, a short-video scroller, a cautious retiree, and a busy parent.

They talked it through in three rounds, with the owner's updated brief (`docs/VIDEO-BRIEF.md`, 2026-09-24). What changed from v2, and why:

| v2 | v3 | why |
|---|---|---|
| 13 separate claims in 35 s | One idea: **it does nothing, and keeps nothing, until you say so.** Acting, remembering and stopping each show that rule once. | Viewers could not repeat a single claim back. |
| Made-up app screens | The **real desktop app**, rendered from its own code with sample data. | "Is this real or a mock-up?" |
| Glitch text, flashes, scanlines, corner labels, 22 slams | Dark and calm: sentence case, one glow (the reactor), four moves. | Every viewer read the effects as a template or "an AI ad". |
| No captions | Every spoken line is captioned "You:" / "Jarvis:". | Most people watch muted. |
| "Nothing leaves the room." | "Your email, your files, and what it knows about you stay on your PC." | The old line overstated it (see below). |
| "Keep / **Forget**" | "Keep / **Discard**", the app's real buttons. | v2 had the wrong word. |
| Hardware section: racks, bars, 8 s | One line of small print under the end line. | Viewers left during it, and it flattened the only joke. |
| Trailer score with 17 hits | Plucks and soft piano. The music stops dead on "Stop." | "Calm confidence rather than hype" (the brief). |

The owner's own calls, which are final:
- no smart home or garage door;
- the risky request is the visible browser doing an approved task on one website, labelled "ready";
- no "next: any 8 GB card";
- no "one person's own build / not in any app store" line;
- the hardware wording is "a PC with an 8 GB graphics card";
- dark and "a little cinematic";
- a landscape master.

## Evidence for every line on screen

B = the owner's working branch, `claude/admiring-ritchie-5urg5h`.

| on screen | status | evidence |
|---|---|---|
| "Hey Jarvis" only listens once you switch it on. | today | B `backend/README.md`, "Hey Jarvis", steps 1-2: off until approved. |
| You: "Hey Jarvis, renew my library book." A card for a browser plan appears on the PC and the phone. | **ready**, labelled on screen "switches on with a second graphics card" | Browser control is built (B `backend/jarvis_browser_control.py`) and ships off: it needs the second card and "Longer conversations" (B `docs/SECOND-CARD.md`). The card text on screen is the module's own `describe()`, run on the plan: the allowed site, every step with its reason, and "If you say no". The same card shows on both apps (`docs/JARVIS-API.md`). |
| The browser is visible, and does only the approved steps on the one allowed site. | ready | `_HEADLESS = False`: "Launched NOT headless on purpose: the owner should be able to see the tab Jarvis is driving." `run()` executes only the enumerated steps, re-checking each one, and stops if the page leaves the allowed sites, asks a question, opens a tab or starts a download. The library site is sample data. |
| An AI assistant that asks before it acts. Every time. | today | Nothing is ever auto-approved: `docs/ARCHITECTURE.md` and CLAUDE.md rule 4. |
| The phone asks for a fingerprint. | today, **phone only** | B `jarvis-client/.../BiometricGate.kt` `required()`: anything unclassified, outbound or irreversible. `control_browser`'s risk entry is in the owner's gate and not in this repo, so the card shows it unclassified, which asks for a fingerprint by itself. The sheet is Android's own BiometricPrompt: the card's title, then "Check the card before you confirm." The desktop fingerprint is still being built and is not shown. |
| Nobody can shout "yes" at it. You tap to approve. | today, by code; no test yet | The chat tool list has no approve or decide tool (B `backend/jarvis_agent.py`). The phone's voice path approves nothing (B `VoiceSession.kt:176`). |
| Your email, your files, and what it knows about you stay on your PC. | today | B `docs/ARCHITECTURE.md` §4. The router only *offers* a cloud model, never takes one without a yes, and private turns get no offer at all (B `backend/rebuilt/jarvis_router.py:366`, e68c04a). |
| June: "You drink coffee." September: "You're off coffee this month.", with **Keep / Discard**. | today | Real captures of Brain › Memory (`jarvis-desktop/src/brain.html`): the "What did you know on…" view and the proposal card. |
| It asks before it remembers, too. | today | Nothing enters memory until you press Keep (the Learning panel's own words). Turning learning on asks first too (B c7e17c8). |
| The old fact is set aside, not deleted. | today | Brain › Memory: "Retired facts are shown, greyed. Nothing here is deleted." |
| You: "Stop." Jarvis stops mid-word. | today, **while "Hey Jarvis" is on** | B 311739e, `voice.rs`. Tested on computer voices, not yet on a real phone. Cutting in just by talking is "coming soon" and is **not** shown. |
| Runs on a PC with an 8 GB NVIDIA graphics card. | today | `docs/MODEL-TOPOLOGY.md`. B `backend/rebuilt/jarvis_compute.py` reads the card through NVIDIA's `nvidia-smi`, so today it has to be NVIDIA. |
| Ready for a second graphics card. | ready | B `docs/SECOND-CARD.md`: built, and switched off until the card is there. |
| No subscription. | today | Ollama and the models are free. No paid service is needed. |

## Deliberately not claimed

- **"Nothing leaves the room."** An approved web search, and phone notifications if they are set up, do leave the PC (B `ARCHITECTURE.md` §4).
- **"Answers only to your voice."** It checks the voice first, but that was only tested on computer-made voices.
- **"Knows when you have finished a sentence."** It sometimes calls a pause "finished" (B `backend/README.md`).
- **The smart home.** It is built, but the owner does not want it advertised.
- **"Any 8 GB card".** It is only a design (B `docs/HARDWARE-PROFILES.md`), with no card to test it on and no date, so the owner took it out.
- **Speeds, scores or accuracy numbers, competitor names, and the Play Store.** The brief's hard rules forbid them.

## Honest limits of the picture

- **The desktop screens are real.** They are the app's own HTML, CSS and JavaScript, rendered headless with sample data. Open Sans stands in for Windows' Segoe UI.
- **The phone screen is redrawn**, from `ApprovalCard.kt` and `PendingRows.kt`, because an Android app cannot render here. The owner can swap in a real recording: `adb shell screenrecord /sdcard/jarvis.mp4`.
- **The voices are captions only.** No voice was generated for anyone.
