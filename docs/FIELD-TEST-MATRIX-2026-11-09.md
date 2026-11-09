# Field-test matrix — the Wave 9–13 sweep (desktop + phone)

**Opened 2026-11-09 03:05 PT by the off-peak continuation session.** This is the
register for the owner's queue item: *field-test every new or updated feature on
BOTH the desktop Jarvis and the Android Jarvis, on real hardware*, after the
waves land.

**How to read this.** A row becomes **PASS** only when the feature was actually
driven on the real app (desktop window or the owner's phone) and the evidence
names the build, the date and what was seen. `BLOCKED`, `PARTIAL` and
`NOT-TESTABLE` are never a pass - the same rule as
`docs/FIELD-TEST-MATRIX-2026-10-11.md`, whose October/early-November rows stay
intact and untouched. Until a row is driven it reads **NOT RUN YET**, which is
also not a pass.

**State at opening:** the live install is Wave 9 (`0.2.440` / phone `0.2.4016`).
PR #1216 (Waves 10/11) merged on 2026-11-09 03:33 PT; Wave 12 is rebased onto that
`main` and awaiting its single PR; Wave 13 is being built in three local lanes
(Reminders, GitHub truth, Creator Mode). The deploy of the merged Wave-10/11 tree
to the PC, the desktop and the phone is running now. So every row below is
**NOT RUN YET**; nothing here is claimed as tested.

| # | feature | wave | desktop | phone | verdict | evidence |
|---|---|---|---|---|---|---|
| 1 | Brain → Model "Loaded now / Resources" truth + Compute panel names the real cards | 11/12 | NOT RUN YET | n/a (PC-only plate) | NOT RUN YET | — |
| 2 | Lane truth (dead pooled lane falls back; explicit num_ctx; warm guard) | 11 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 3 | "Hide advanced" label, HUD local-session line gone, foldable model filters | 11 | NOT RUN YET | n/a | NOT RUN YET | — |
| 4 | Auto Wi-Fi reconnect (switch, journal, honest "did you reconnect?") | 11 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 5 | Right/Wrong v2 ("why" tags + owner's own correction) | 10/11 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 6 | Skills self-knowledge: Jarvis answers the Skills menu truthfully | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 7 | Skill install/edit/turn-on scanned by the four extra checks (Hermes inline, exfil phrasing, gate claims, bare URL); `skills.lock` row written | 12 | NOT RUN YET (PC Settings → Skills) | n/a (phone cannot install) | NOT RUN YET | — |
| 8 | Drag-and-drop a compatible file into the HUD / chat window | 12 | NOT RUN YET | n/a (one-sided; phone has Attach a file) | NOT RUN YET | — |
| 9 | Drag-and-drop a compatible file into the Alt+Space quick bar | 12 | NOT RUN YET | n/a | NOT RUN YET | — |
| 10 | Smart note creation: "create a note called Workout Log, pin it, and add using todays date that i used the punching bag" → title/body/pin/date | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 11 | Tray + Settings → Updates four-state truth ("Up to date · checked HH:MM", never invented) | 12 | NOT RUN YET | n/a | NOT RUN YET | — |
| 12 | Brain → Tutorials "What's new in Jarvis" pane + Open Settings → Updates | 12 | NOT RUN YET | n/a (one-sided) | NOT RUN YET | — |
| 13 | Notion import: a 276 MB export imports on the PC; refusals name real numbers; progress line; free-space preflight | 12 | NOT RUN YET | NOT RUN YET (phone sends its own 4 GB zip) | NOT RUN YET | — |
| 14 | Read out loud in Jarvis's own (female) voice + Pause / Resume / Stop | 12 | NOT RUN YET | n/a (desktop audio) | NOT RUN YET | — |
| 15 | Forget a time frame: no 200-item cap, both confirmations, backups untouched | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 16 | Manual-click rule: a reversible owner UI choice (preset first) needs no card and shows an undo/switch-back | 12 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 17 | Brain IA Recs 5/6: honest Galaxy labels, HUD→Brain map button, Goals under Projects | 12 | NOT RUN YET | n/a (phone keeps its own sections) | NOT RUN YET | — |
| 18 | Memory: the reworded-facts switch ON behaves as promised (fewer cards, marked words) | 12 (setting) | NOT RUN YET | n/a (PC setting) | NOT RUN YET | — |
| 19 | Memory fault: ONE banner with "retry now" instead of a card queue | 13 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 20 | Reminders "Grandma": relative date, title parsing, phone notification flag, no false receipt | 13 | NOT RUN YET | NOT RUN YET | NOT RUN YET | — |
| 21 | GitHub truth + card-gated `github_create_repo` ("Fitness Band") | 13 | NOT RUN YET | n/a unless a screen is added | NOT RUN YET | — |
| 22 | Creator mode: stage a plug-in or skill, scan it, ONE PC-only install card, install ≠ enable | 13 | NOT RUN YET | n/a (PC-only) | NOT RUN YET | — |
| 23 | The two queue items: Jarvis-takeover design lane (no user surface yet) | next | n/a | n/a | NOT TESTABLE YET | — |
| 24 | Brain → Model "Measured results" card reads the real benchmark / five-suite scorecard stores and says so when there is nothing measured | 12 | NOT RUN YET | n/a (PC-only plate) | NOT RUN YET | — |

**Owner device:** phone `f0a5b32b` (attached 2026-11-09 02:12 PT); Windows 11 PC
with the desktop app. **Builds to write in when the sweep starts:** the
`desktop-latest` / `client-latest` versions at that time (record them by reading
`gh release view` and the installed `FileVersion` / `versionName` - never from
memory).

**What the sweep must include, per feature:** the real gesture or screen (not a
source read), the owner's words where the feature came from the owner, at least
one refusal path (the plain sentence), and the undo or switch-back where one
exists. A feature that cannot be reached on a device is written `BLOCKED` with
the concrete reason.
