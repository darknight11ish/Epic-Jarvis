# Audit #11 - Documentation accuracy (2026-09-28)

Scope: the docs checked against the code in **origin/main** (f81d230d, read with
`git show origin/main:<path>`) and in the **combined tree** (`integ`, deaca649).
Every finding below was checked in the file named; "main" / "combined" says
where it is true. All findings are **checked in code** unless marked otherwise.
Nothing in the repository was edited.

How it was checked (scripts in `scratchpad/p11/`):
- `routes.py` - every `/api/...` route the desktop (Rust + JS) and phone (Kotlin)
  call (reusing `tools/check_parity.py`'s own scanner), every route string in
  `backend/*.py` and the `+`/context lines of `backend/*.patch`, against every
  route mentioned in `docs/JARVIS-API.md`.
- A section-number scan of JARVIS-API.md and every "JARVIS-API ... §N / section N"
  reference in the tree.
- `paths.py` - every file path the main docs name, looked up in the tree.
- `psblocks.py` + `pscheck.ps1` - every PowerShell code block in the main docs,
  tokenised by the real PowerShell parser for `??`, `?.`, ternary, `&&`, `||`,
  `-Parallel`, parse errors, and more than one line.
- A code-fence balance check on `backend/README.md`.

## Summary

| # | Severity | Where | One line |
|---|---|---|---|
| D1 | **high** | main + combined | `backend/README.md` has a broken code fence at ~line 4715: from there on, GitHub shows prose as code and code as prose - to the END of the file on main (13,895 lines), for ~10,500 lines on combined. The task-control section's test command is lost and cloud-one-turn's test block sits in its place. |
| D2 | medium | combined | `backend/README.md`'s patch table is missing 10 of the 97 patches, two of them (`plan-gate.patch`, `phone-notifications.patch`) are not mentioned anywhere in the file, and the table order is not the script's order - yet the file says "The table order is the only order that works, and the script applies exactly it" and tells a by-hand user to go "in table order". |
| D3 | medium | main + combined | `backend/README.md` counts are stale: "Fifty-one patches" (97 combined / 83 main), heading "Thirty-four of the thirty-six actually apply" and "34 patches ... two skipped" (95 of 97 / 81 of 83). |
| D4 | medium | combined | `jarvis-client/README.md` (new, github-repos branch) says the phone pairs by **QR code confirmed by a card on the PC** - not built anywhere - and that the phone reaches the PC over **the home network** - the phone refuses home-network addresses (`PhoneAddress.kt`, CLAUDE.md line 421 "replaced 2026-09-28"). |
| D5 | medium | main + combined | `docs/JARVIS-API.md`'s opening says "That file has never existed", "Nobody writing this page could read [the backend]", "Roughly 55 distinct endpoint paths". All untrue now (~200 routes; ~126 backend modules are in `backend/`). |
| D6 | medium | combined | `docs/ARCHITECTURE.md` never mentions the plan card ("One card, several steps", switched off), Goals, or the third graphics card's own lane and card - three changes to the approval model / lanes. |
| D7 | low | main + combined | `README.md`: "20 designs" - the spec has 24 faces on combined (23 on main), including the animals. |
| D8 | low | main + combined | `jarvis-desktop/tests/README.md`: "Ten checks" (104 suites combined, 83 main) and "`npm run test:all` - everything below": it runs 44 of 104 (39 of 83 on main). CI runs all of them by glob. |
| D9 | low | main + combined | `docs/INSTALL.md` 2.4: "Six are registered at startup" - 8 on combined (Alt+Shift+F floating face, Alt+Shift+T talk-to-type added), 7 on main. |
| D10 | low | combined | `docs/README.md` (the doc index): Jarvis Live "design only, not built" (it is built); `designs/` "MCP bridge ... not built yet" (built, `jarvis_mcp.py`, also main); 8 new docs and 4 folders not indexed; "about ninety documents" (102). |
| D11 | low | main + combined | `tools/tool_eval/README.md` and `ollama_tool_eval.py`'s docstring: "62 requests" - the code has 65 (`CASES` 43 + `HELD_OUT` 22). |
| D12 | low | combined | `backend/chatbot-routes.patch` line 9 still says "JARVIS-API section 60" - the chatbot section is now §87 (§60 is the plan card). The only stale reference left by the renumbering; every other one (~70) checked right. |
| D13 | low | combined | JARVIS-API.md section numbers jump 64 -> 70 and 75 -> 77 (65-69 and 76 do not exist). Nothing references them; harmless but confusing. |
| D14 | low | main + combined | `jarvis-desktop/README.md`: hotkey table misses Alt+Shift+X/F/T (and its Alt+Shift+W row sits outside the table); "IPC surface" lists ~25 commands, `check_command_acl.py` counts 249. |
| D15 | low | main + combined | `docs/MODEL-TOPOLOGY.md` line 128: a two-line PowerShell block (`setx` twice) - breaks the ONE-line rule. |
| D16 | low | combined | `README.md` "What it can do" lists none of the big built features that landed this week (Jarvis Live, Projects, Goals, chatbot conversations, Watches, Lockdown, Today cards, widgets you describe, history import, talk-to-type, photo to reminder, backups). Owner's call how much to list (see Q2). |

Things checked and found RIGHT (so nobody re-checks them):
- Every route either app calls is mentioned in JARVIS-API.md (the only two not
  mentioned are `/api/tags`, which is Ollama's own route, and `/api/memory`,
  which the parity scanner reads from the Brain's allow-list, not a real call).
  Every route string in the shipped backend code is in the doc, except Home
  Assistant's own `/api/states`/`/api/services` and crates.io's `/api/v1/crates`
  (other services' routes, correctly not Jarvis's).
- Every "one-sided on purpose" route in `tools/check_parity.py` has its row in
  ARCHITECTURE.md §8. `check_parity.py` is clean.
- ARCHITECTURE §4 (ways out of the PC) has rows for every new outbound path:
  chatbot website, chatbot API, chatbot comparison, Watches, Open-Meteo.
- Every gate action a patch adds (31) is named in JARVIS-API.md except
  `control_phone` and `research_authenticated` (both old, from `ui-control-wiring.patch`).
- The 31 gate actions, `_where.SHIPPED` (126 modules) and the script's `$SHIPPED`
  agree with the files on disk; `$PATCHES` (97) matches the 97 `.patch` files.
- The phone notifications section (§61) matches the code (action
  `phone_notifications_read`, the settings-registry second door).
- `videos/README.md`: v1-v6 all present, every link resolves, largest file 35 MB.
- No PowerShell block in the main docs uses `??`, `?.`, ternary, `&&`, `||` or
  `-Parallel`. The only multi-line ones are D15 and two "by hand" examples in
  backend/README (lines 348, 518) that are meant as a list of commands.
- CLAUDE.md: every file it names exists (except the owner-only `jarvis_hud.py`
  and `jarvis_gate.py`, which is correct); `JarvisRuntime.installModel`,
  `BrainScreen.kt`'s `ModelsPlate`, `net/OpenChatPhrase.kt`, `_OPEN_CHAT` all exist.
- CLAUDE.md, the phone FAQ (`FaqScreen.kt`) and ARCHITECTURE §2 agree that the
  phone uses only Tailscale/Meshnet names. Only `jarvis-client/README.md` (D4) disagrees.

---

## Details

### D1 - backend/README.md: a lost opening fence inverts ~10,000 lines (high)

**Checked in code, main and combined.** Combined `backend/README.md` lines 4700-4716:

```
## Test it
```powershell
$env:JARVIS_BACKEND = "..."; py -3 backend\test_cloud_one_turn.py
```
Runs the patch's own lines on a request carrying a private earlier question
...
and - with `JARVIS_BACKEND` set - checks `_open` in your real file.
python backend\test_task_control.py
```                                    <- line 4715: a CLOSING fence with no opener
```

This sits inside `# task-control.patch` (starts line 4627). The cloud-one-turn
section (line 4589) has no test block of its own, so its "Test it" block was
spliced here, and task-control's own opening fence (and its one-line command)
was lost. From line 4715 on, every ``` pairs with the wrong partner: my fence
pairing found 120 "closers" that carry a language tag (`` ```powershell `` used
as a closer), first at 4809, last at 15287 (combined). On **main** the file has
an **odd** number of fences (445), so the inversion runs to the last line. On
GitHub this shows most of the patch documentation as grey code and the
commands as prose.

Why it matters: this is the file the owner is told to follow for every patch.

Fix (plain, safe): replace the combined lines 4704-4715 region so each section
has its own block:

old (combined 4713-4715):
```
and - with `JARVIS_BACKEND` set - checks `_open` in your real file.
python backend\test_task_control.py
```
```
new:
```
and - with `JARVIS_BACKEND` set - checks `_open` in your real file.

## Test it (task-control)

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; py -3 backend\test_task_control.py
```
```
(and, better, move the `test_cloud_one_turn.py` "Test it" block up into the
cloud-one-turn section, before line 4627). Re-run a fence check afterwards:
the file should then have no `` ```lang `` closers.

### D2 - backend/README.md's patch table: missing rows and a different order (medium)

**Checked in code, combined.** The table (rows `| \`x.patch\` |`) lists 87
distinct patches; `$PATCHES` has 97. Missing from the table:
`chat-stream`, `chatbot-routes`, `learning-asks`, `phone-notifications`,
`plan-gate`, `reach`, `token-store`, `voice-mic`, `voice-turn`, `warm-prefix`.
Eight of these have their own section further down; **`plan-gate.patch` and
`phone-notifications.patch` are mentioned nowhere in backend/README.md** (both
from the continuation branch, 03kls1, which never touched this file). On main
six are missing from the table (`chat-stream`, `learning-asks`, `reach`,
`token-store`, `voice-mic`, `voice-turn`), all with sections elsewhere.

The order also differs from the script's (e.g. the table has `bind-wildcard`
before `approval-expiry`, `stop-all` before `email-send`/`manner`, and
`projects`/`chatbot`/`live` before the patches the script puts first).

The file says (combined line ~42): "**Order.** This is a *stack*, not a set.
The table order is the only order that works, and the script applies exactly
it." and, in the by-hand blocks (lines 351 and 521): "... and so on, in table order".

Fixes (plain, safe):
- old: `The table order is the only order that works, and the script applies exactly it.`
  new: `The order of the $PATCHES list in scripts/apply-patches.ps1 is the only order that works, and the script applies exactly it. The table below is grouped for reading and does not list every patch; by hand, follow the script's list.`
- old (twice): `... and so on, in table order`
  new: `... and so on, in the order of $PATCHES in scripts\apply-patches.ps1`
- Add table rows for `plan-gate.patch` (jarvis_gate.py: teaches the gate the
  plan card's action; JARVIS-API §60; switched off) and
  `phone-notifications.patch` (jarvis_gate.py: the `phone_notifications_read`
  action, "yes/local"; JARVIS-API §61) - wording to be taken from the patches'
  own comments.

### D3 - backend/README.md counts (medium)

- line 8, old: `Fifty-one patches against the Jarvis backend (counted 2026-09-24, after`
  new (combined): `Ninety-seven patches against the Jarvis backend (counted 2026-09-28; the list grows, so trust the script's $PATCHES over this number), each with an executable test`
  (main: `Eighty-three`.)
- heading, old: `## Thirty-four of the thirty-six actually apply, and that is correct`
  new: `## All but two of the patches apply, and that is correct`
- old: `split versions: 34 patches, four of them as halves, and two skipped.`
  new: `split versions: every patch in the list except two, four of them as halves, and two (embedding-guard, event-allowlist) skipped.`
  Count-free wording on purpose: these numbers went stale three times.

### D4 - jarvis-client/README.md claims two things the phone does not do (medium)

**Checked in code, combined** (file added by github-repos branch, commit
1c1179f5; not on main).

1. "reached over Tailscale, NordVPN Meshnet, or the home network" and "The
   address it's given must be on the owner's own networks - this PC, the home
   network, Tailscale, or NordVPN Meshnet".
   `jarvis-client/.../data/PhoneAddress.kt` lines 44-49 allow cleartext only to
   `ts.net`, `nord`, `localhost`, `127.0.0.1`, and its MESSAGE refuses "a number
   or a home-network name". CLAUDE.md line 421: "~~Phone: allow home-network
   addresses~~ - **replaced 2026-09-28**". The phone FAQ says the same as the code.
2. "The app pairs with one Jarvis backend at a time (QR code, with a short typed
   code as a backup), confirmed by an approval card on the PC first."
   A search for QR/barcode/`/api/pair` finds no pairing code in the phone,
   desktop or backend. CLAUDE.md lists QR pairing as decided, "built together
   with per-device keys (task 'more devices')", which ARCHITECTURE line 424
   still describes as future.

Fixes (plain, safe):
- old: `over Tailscale, NordVPN Meshnet, or the home network - never a public tunnel`
  new: `over Tailscale or NordVPN Meshnet, by the PC's .ts.net or .nord name - never a public tunnel, and not by a home-network number or .local name (data/PhoneAddress.kt says why)`
- old: `The app pairs with one Jarvis backend at a time (QR code, with a short typed code as a backup), confirmed by an approval card on the PC first. The address it's given must be on the owner's own networks - this PC, the home network, Tailscale, or NordVPN Meshnet;`
  new: `The app pairs with one Jarvis backend at a time: you type the PC's Tailscale or Meshnet name and the pairing key. (Pairing by QR code, confirmed by a card on the PC, is decided but not built yet - it comes with "more devices".) Any other address -`
- also: `builds, unit-tests, signs, and runs an emulator smoke test on every push` -> `... on every push that touches the phone app, the backend or the desktop's shared files` (jarvis-client.yml has a `paths:` filter).

### D5 - JARVIS-API.md's opening is out of date (medium)

**Checked in code, main and combined.** Lines 5-12: "Eight files in this
repository cite `docs/JARVIS-API.md` ... That file has never existed. Checked
on 2026-09-20 ... returns **zero** commits". Line 22-23: "Nobody writing this
page could read it." Line 1558: "Reconstructed 2026-09-20 ... Roughly 55
distinct endpoint paths." The file exists (13,165 lines), `backend/` ships 126
modules and 97 patches, and sections 11-89 are written from that backend code;
my scan finds ~200 distinct routes mentioned.

Fix (plain, safe) - replace the paragraph under "Read this paragraph before you
trust anything else on this page." with:
> This page was first reconstructed on 2026-09-20 from the two apps' call sites,
> when no API document existed. Since then most of the backend has been added to
> this repository (`backend/`: the shipped modules and the patches), and the
> sections from §11 on are written from that code. The owner's own
> `jarvis_hud.py`, `jarvis_gate.py` and `jarvis_extract.py` still live only on
> the PC. Where this page and the backend disagree, the backend wins.

and line 22-23 old: `Nobody writing this page could read it.` new: `The routes the patches and shipped modules add are read from that code; the owner's own routes (sections 1-10) were read from the apps.`
and line 1558 old: `Roughly 55 distinct endpoint paths.` new: `About 55 distinct endpoint paths then; about 200 by 2026-09-28.`

### D6 - ARCHITECTURE.md misses three approval/lane changes (medium)

**Checked in code, combined.** `grep -i` over docs/ARCHITECTURE.md finds no
"plan card", "several steps", "jarvis_plan", "goal", "third card" or "third
graphics card". Yet:
- `backend/jarvis_plan.py` + `plan-gate.patch` + JARVIS-API §60: "One card,
  several steps" - a card that covers more than one step (built, SWITCHED OFF).
  CLAUDE.md: "The plan card is allowed later, only after the multi-step safety
  tests pass; risky steps still get their own card." This is exactly what §3
  ("one mechanism, no exceptions") exists to record.
- Goals (JARVIS-API §59, `jarvis_goals.py`): one card per acting step, weekly
  check-in through the same scheduler card.
- The third graphics card's own lane and its approval card (JARVIS-API §12,
  line 1778; CLAUDE.md lines 1042-1073).
- Phone notifications appear only in §8, not in §3's list of switches whose ON
  raises a card.
CLAUDE.md's standing rule ("`docs/JARVIS-API.md` and the other docs updated")
covers ARCHITECTURE. Not a plain text swap - it needs a paragraph each in §3
(and §7 for the third card). Code change: none; a doc to write.

### D7 - README.md face count (low)

`jarvis-client/app/src/test/resources/jarvis-visual-spec.json` `faces`: 24 on
combined (20 abstract + redpanda, pygmyowl, seaotter, monkey), 23 on main.
- old: `An animated face shows what Jarvis is doing (20 designs), with themes and`
  new (combined): `An animated face shows what Jarvis is doing (24 designs, four of them animals), with themes and`
  (main: `23 designs, three of them animals`)

### D8 - jarvis-desktop/tests/README.md (low)

- old: `Ten checks that run the real frontend rather than a copy of it, plus a screenshot harness.`
  new: `Over a hundred test files (104 on 2026-09-28) that run the real frontend rather than a copy of it, plus a screenshot harness.`
- old: `` | `npm run test:all` | everything below, in order | ``
  new: `` | `npm run test:all` | the groups below, in order (not every suite: CI runs every tests/*.mjs; to do the same on Windows, in jarvis-desktop: `Get-ChildItem tests\*.mjs | Where-Object { $_.Name -notin 'uikit.mjs','shots.mjs' } | ForEach-Object { node $_.FullName }`) | ``
  (`package.json`'s scripts name 44 of the 104 suites; 60 - including chatbot,
  goals, jarvis-live, projects, sky's browser half, today, widget-board - are
  only reached by CI's glob.)

### D9 - INSTALL.md hotkeys (low)

`jarvis-desktop/src-tauri/src/hotkeys.rs` `ACTIONS` has 8 defaults on combined
(`toggle_floating` Alt+Shift+F, `talk_to_type` Alt+Shift+T beyond the six), 7 on main.
- old: `Six are registered at startup:` new (combined): `Eight are registered at startup:`
- add rows: `` | `Alt+Shift+F` | show or hide the floating face | `` and `` | `Alt+Shift+T` | talk-to-type (hold, speak, and the words are typed where the cursor is) | ``
- old: `` `Alt+Shift+S/N/W/X` clash with `` new: `` `Alt+Shift+S/N/W/X/F/T` clash with ``

### D10 - docs/README.md (the index) (low)

- old: `"Jarvis Live": a back-and-forth voice conversation, plus the phone's camera (design only, not built).`
  new: `"Jarvis Live": a back-and-forth voice conversation (built 2026-09-28), plus the phone's camera (built, switched off until the 12 GB card passes the photo test).` (LIVE-DESIGN.md's own status line says so.)
- old: `Draft designs not built yet (an MCP bridge, a skills system), each in its own subfolder with the draft's own README.`
  new: `Early drafts (an MCP bridge, a skills system), each with its own README. The MCP bridge has since been built differently - backend/jarvis_mcp.py and ARCHITECTURE section 4.`
- old: `There are about ninety documents here.` new: `There are about a hundred documents here.`
- Not indexed (combined): APP-BUILDER-DESIGN.md, AUDIT-2026-09-28-REPO-REFS.md,
  CHATBOT-DRIVER-DESIGN.md, CRITTERS.md, LIPSYNC.md, PROJECTS-DESIGN.md,
  SCREEN-DESIGN.md, STUDIO-REVIEW-2026-09-27.md, and folders clean-room/,
  critters/, studio-2026-09-27/, studio-2026-09-28/. (Main's index misses 31
  docs, fixed on the github-repos branch except these.)

### D11 - tool_eval "62" (low)

`tools/tool_eval/jarvis_tool_cases.py`: `len(CASES)` 43 + `len(HELD_OUT)` 22 = 65;
`ollama_tool_eval.py` line 347 runs `CASES + HELD_OUT`. Same on main.
- README.md line 17 old: `| picks the right tool | 62 requests:` new: `| picks the right tool | 65 requests:`
- ollama_tool_eval.py line 9 old: `fits (62 cases, jarvis_tool_cases.CASES + HELD_OUT)` new: `fits (65 cases, jarvis_tool_cases.CASES + HELD_OUT)`
Better: have `test_tool_eval.py` assert the README number, as other suites do.

### D12 - one stale section number from the renumbering (low)

`backend/chatbot-routes.patch` line 9: `+    # section 60): GET /api/chatbot/status, ...`.
The chatbot section is §87 now; §60 is the plan card. All ~70 other refs to
§60-64 and §85-89 checked and point at the right section. Changing a line of a
patch changes the patch, so `backend/patch-history` needs regenerating
(`python3 tools/build_patch_history.py`) in the same commit - a code change, low.

### D13 - JARVIS-API section gaps (low)

Headings go 64 -> 70 and 75 -> 77 (the competitors branch started at 70 to
avoid a clash, and skipped 76). No reference anywhere points at 65-69 or 76.
Suggest one line after §64: `(Sections 65-69 and 76 are not used: numbers kept free when two branches merged on 2026-09-28, so no reference had to change.)`

### D14 - jarvis-desktop/README.md (low)

- Hotkey table (lines 61-67) lacks `Alt+Shift+X` (Stop everything),
  `Alt+Shift+F`, `Alt+Shift+T`; the `Alt+Shift+W` row is on line 75, after the
  paragraph, so it renders as a broken one-row table. Move it into the table
  and add the three rows (wording as D9).
- "IPC surface - Commands exposed to the frontend" lists ~25; `lib.rs`'s
  `generate_handler!` has 249 (`check_command_acl.py`). Suggest old:
  `Commands exposed to the frontend (\`invoke("<name>", …)\`):` new:
  `Some of the commands exposed to the frontend (invoke("<name>", ...)) - the full list is generate_handler! in src-tauri/src/lib.rs (249 on 2026-09-28):`

### D15 - MODEL-TOPOLOGY.md two-line PowerShell (low)

Line 128-131, old:
```
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_KEEP_ALIVE -1
```
new: `setx OLLAMA_KV_CACHE_TYPE q8_0; setx OLLAMA_KEEP_ALIVE -1; Write-Host "Saved for new windows: close this one and Ollama, then start them again"`

### D16 - README "What it can do" (low, owner's call)

See Q2.

---

## Plain factual fixes (safe to apply)

D1, D2 (the two sentences and two new rows), D3, D4, D5, D7, D8, D9, D10,
D11, D13, D14, D15 - exact old -> new text above. D12 needs the patch-history
regenerated in the same commit.

## Code-vs-intent questions for the owner

- **Q1 (D6).** ARCHITECTURE.md should describe the plan card, Goals and the
  third card's lane. Write those three paragraphs now (recommended - they
  change how approvals work), or wait until the plan card is switched on?
- **Q2 (D16).** The top README lists only features from before 2026-09-27.
  Add the new ones, marked "ready" (built, off by default) or "built, not yet
  tried for real" as the video rule does (recommended), or keep the README short?
- **Q3 (D13).** Leave the JARVIS-API gaps (65-69, 76) with a one-line note
  (recommended), or renumber 70-89 down, which rewrites ~100 references?

(The publish-branch question for the workflows is in report 12b.)
