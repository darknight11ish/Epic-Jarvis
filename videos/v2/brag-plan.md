# Brag Plan: Jarvis — v2 "It learns. It adapts. It scales."

## What changed from v1
The owner asked for more focus on three cutting-edge traits, and a 35-second cut:

1. **It learns you, over time** — the learner, the review queue, memory that
   keeps history ("as of" any past date), and voice training.
2. **It adapts** — Smart Turn (waits while you pause mid-thought), asks
   before it acts, can be interrupted mid-sentence.
3. **It scales** — one 8 GB card today; built and ready for a second card and
   a big model; next, a design for any 8 GB card and up to two cards.

## Evidence for every claim (checked 2026-09-24)
Features come from the owner's feature branch `claude/admiring-ritchie-5urg5h`.

| On screen | Status | Source |
|---|---|---|
| Re-reads what you said once the conversation goes quiet, proposes facts; nothing kept until you accept | **on** | `docs/INSTALL.md` "Jarvis learns from your conversations, and it is on" |
| Nothing deleted; old facts retired; "as of" any past date | **on** | `docs/ARCHITECTURE.md` §5 (bi-temporal facts); VIDEO-BRIEF "Memory you can see" |
| Train my voice: a print per microphone, a someone-else check, own "Hey Jarvis" verifier | **on** | commits `6130c8a`, `e9304d3` |
| Smart Turn: "finished, or only paused?" | **on** | commit `d328470` |
| Interrupt with "stop" | **on** | commit `311739e` |
| Approval card before a lock/garage action | **on** | VIDEO-BRIEF "Smart home"; `ApprovalCard.kt` |
| Second card: longer conversations, pictures, background learning, browser control | **built, off until a capable card is detected** → shown as **READY** | `docs/SECOND-CARD.md` |
| Deep questions on a big model | **built, off** → **READY** | `docs/BIG-MODEL.md` |
| Any 8 GB card, up to two cards; Fastest / Smartest / Most features | **design only** → shown as **NEXT · IN DESIGN** | `docs/HARDWARE-PROFILES.md` ("Status: a design. Nothing here is built") |

Hard rules kept from the owner's brief: no speed, benchmark or accuracy
numbers; no competitor names; no Play Store; ready/planned features never
shown as working today; no personal details (sample facts are generic).

## Tone
Cinematic type, trailer pacing — every cut on a 120 BPM beat. Honest status
tags (TODAY / READY / NEXT) are part of the look, like a spec sheet.

## Format: landscape 1920x1080 · Duration: 35 s

## Storyboard (seconds; one beat = 0.5 s)
1. **Ignite** 0-2 — Arc spins up from a point.
2. **"Hey Jarvis."** 2-3.5 — listening; HUD: VOICEPRINT ▸ OWNER MATCH.
3. **Nothing leaves the room** 3.5-5.5 — data tags bounce off the room wall.
4. **It learns you** 5.5-7.5 — Geodesic thinking; "You ▸ I've started running on Tuesdays." types in.
5. **Only what you accept** 7.5-10 — a proposal card "You run on Tuesdays." Keep / Forget; Keep is tapped; the fact flies into memory.
6. **It remembers what changed** 10-13 — a memory timeline: "You run on Mondays" is retired, not deleted; the new fact starts; an AS OF scrubber slides back to July. Tag: BI-TEMPORAL MEMORY.
7. **It learns your voice** 13-15.5 — training ring fills; OWNER ▸ MATCH ✓, SOMEONE ELSE ▸ NOT YOU ✗. Tag: VOICEPRINT · A PRINT PER MICROPHONE.
8. **It waits while you think** 15.5-17 — "Lock the…" · PAUSED, NOT FINISHED · "…garage door." · FINISHED. The music itself pauses. Tag: SMART TURN.
9. **It asks before it acts** 17-19 — phone approval card, swipe, Approved.
10. **Interrupt it** 19-22 — the reply mentions your run (it remembered); "STOP."; silence.
11. **Today** 22-24 — one graphics card, the reactor above it. Tag TODAY.
12. **Ready** 24-27 — a second card slides in; five capabilities light up. Tag READY · BUILT, SWITCHED OFF UNTIL THE HARDWARE IS THERE.
13. **Next** 27-30 — any 8 GB card, up to two; three choices: Fastest answers / Smartest answers / Most features. Tag NEXT · IN DESIGN.
14. **Your rules** 30-35 — three braams, three lines, JARVIS, fade.

## Audio
Original score regenerated for 35 s on the same timing table (`assets/timing.json`):
groove through the learning act, the music drops out while Jarvis waits on a
pause (16.0-16.5) and dies on "STOP." (20.0-20.5), a build through the
scaling act, braams on 30 / 31 / 32. The low-band envelope drives the
reactor's glow.
