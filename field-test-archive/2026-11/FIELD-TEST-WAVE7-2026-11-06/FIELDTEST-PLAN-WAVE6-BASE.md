# Wave-6 field-test plan — 2026-11-06

**Target:** the Wave-6 deploy (`#1194`, the Wave-3 bundle: packs + notes + quotes,
plus upload, the approval policy tool, the repository map and the 3-GPU planned
presets). **Written:** 2026-11-06, before the deploy; nothing here has been run
against the deployed build.

**This plan is read-only.** `field_test.py` sends GETs and four documented
card-free chat fast paths; it never approves a card, never changes a setting,
never installs anything. `screens.py` launches the app, taps only the labels
named in its plan, and captures images. Anything that needs a card, a tap on
Approve, a voice, or a stopwatch is a **manual step** in this document — never a
script pretending to have proved it.

---

## 1. How to read a verdict

| label | means | counts as a pass? |
|---|---|---|
| `PASS` | the check's own assertion held against the deployed build | yes |
| `FAIL` | it was reached and the answer was wrong, or a required route/tool is missing | no |
| `BLOCKED` | it could not be reached (no token, no phone, asleep, no vault) | **never** |
| `NOT-MEASURED` | deliberately not run (an opt-in model turn, or a step only a person can do) | **never** |
| manual row | a person drove it on real hardware and wrote down what they saw | only then |

This is the project's own rule: `BLOCKED`, `PARTIAL` and `NOT-TESTABLE` are never
counted as passes (`CLAUDE.md`, "The five rules that are not negotiable" — the
2026-10-11 bullet; `docs/FIELD-TEST-MATRIX-2026-10-11.md`).

## 2. The documented evidence this harness is built on

Every assertion below comes from a line in the repository, not from memory.
Quoted from `.dsh-scratch/WAVE3-BUNDLE-2026-11-05/wt/docs/JARVIS-API.md` (the
bundle tree, at `776ee49b1e`), because that is the tree being deployed:

- **§196, lines 35431-35445** — `POST /api/upload/begin|chunk|finish`;
  `begin` answers `202 {"ok": true, "id": "<32 hex>", "waiting": true|false,
  "chunk_bytes": 1048576, "max_bytes": 52428800, "said": "..."}` and, for
  `purpose: "document"`, **ONE approval card**, raised before a byte is written.
  `finish` answers `200 {"ok": true, "saved": true, "name", "folder", "sub",
  "size", "said"}` for a document. Line 35481 says the phone's screen is "the
  next lane" — the phone code in the same tree contradicts that (see §7).
- **§197, lines 35506-35513** — "There is no route in this section. All four
  doors are model tools in `jarvis_agent.py`": `pack_list` (no card),
  `pack_inspect` (no card), `pack_install` (ONE card), `pack_remove` (ONE card).
- **§198, lines 35598-35606** — the note intents and their exact shapes:
  `You have N notes.` then up to five `"Title" (first line)` rows then
  `Tell me which one to read.`; a vault with exactly one note is simply read
  (`"Title" says:`); no vault is `I cannot read a note:` naming the setting;
  the old `NOTE_READ_HONEST` was **deleted** (line 35617).
- **§199.3, lines 35680-35707** — `quote_now` is a **model-free fast path**;
  the reply is `quick: quote_now`, with the words and the attribution
  `"<text> - <Author> - <Work> (<year>)"` (`jarvis_quotes.py:228`).
- **§199.4, lines 35711-35717** — the `quote` kind rides the existing
  `POST /api/schedule/add` and `/act`; a repeating quote raises ONE
  `schedule_repeat` card, a one-off needs no card.
- **§195, lines 35332-35356** — `GET /api/projects/<id>/map?q=...&tokens=...`
  answers `{"ok", "available", "project", "folder", "map", "files", "symbols",
  "ranked", ...}` and writes nothing.
- **§145/§160, lines 25913, 28761** — `GET /api/presets` is the read-only alias
  of `GET /api/work`; the 1/2/3-GPU recommendation rows live in it.
- **`docs/MODEL-TOPOLOGY.md:771-800`** — the 3-GPU presets are **planned and
  UNMEASURED**; `deep_think` and `creative` "refuse until measured". Naming only,
  never a claim that a third card exists.
- **`jarvis-client`** — the phone's two doors are `Settings → Folders →
  "Send a document"` and `"Bring in a Notion export"`
  (`MainActivity.kt:746`, `Folders.kt:25`, `Upload.kt:93`, `NotionImport.kt:50`);
  `ClientSettings.kt:110-127` defines `readMemoriesAloud`, **"OFF by default"**
  (the owner's setting of 2026-11-05). The row's words are *"Read out answers
  that use what Jarvis remembers"* (`MemoryAloud.kt:43`), and its own docstring
  says it covers **the mic on this phone while unlocked only — not "hey Jarvis",
  not Jarvis Live** (`MemoryAloud.kt:16-35`).

## 3. Feature → check → manual step → what I accept as evidence

Fill the last column with the **real** label after the run, not the hoped one.
Every row reads `NOT-MEASURED` in the last column **because the deploy had not
happened when this document was written** — replace it with what actually
happened. §6 is the one set of numbers measured already, on the old build, and
it is a control, not a result.

| # | Feature (owner's ask) | Check id that proves the mechanical half | Manual / vision step | What I accept as evidence | Status when written |
|---|---|---|---|---|---|
| 1 | **Phone: send a document** | `routes_present` (the upload plugin is loaded; `POST /api/upload/begin` exists only with `--allow-upload-probe`) | Settings → Folders → **Send a document** → pick a `.pdf/.docx/.md/...` → answer the ONE PC card (the owner's tap) → check the file | `screens/03-settings-folders.png`; the card's text names the file, its size and the **folder name only**; the file at `<folder>\From my phone\<name>` with the right size; `my_files` "find <name>" in chat finds it | `NOT-MEASURED` until a real file lands |
| 2 | **Phone: Notion export import** | `routes_present` (same upload plugin; a Notion export is staged, no card at `begin`) | Settings → Folders → **Bring in a Notion export** → pick the `.zip` → read the preview counts → approve the ONE `import_notion_export` card → check the vault | `screens/03`; the preview's note/attachment/database counts; the card; the vault's file count before/after; Undo offered. Never the note bodies | `NOT-MEASURED` |
| 3 | **Phone: read remembered answers aloud — default OFF** | none mechanical (the setting is phone-local; no route). `phone_app_foreground` only proves the phone is ready | Open Settings → Voice **before touching anything**: the switch must read **OFF** ("Off by default: ..."). Then press the phone's **talk button** (its mic; unlocked) and ask a spoken question that uses a remembered fact — this switch covers the mic on this phone only, **not "hey Jarvis" and not Live** (`MemoryAloud.kt:16-35`). Turn it back OFF. | `screens/04-settings-voice.png` with the switch visibly OFF, taken **before** the change; the OFF line; the spoken answer heard; the switch back OFF at the end | `NOT-MEASURED` mechanically |
| 4 | **Chat reads a note** | `chat_notes_list` — must NOT say *"Chat does not read note text today"* (that is the pre-deploy answer) | In chat: "what notes do I have", then "read my Welcome note", then "what did I write about milk" | The check's `quick=note_list/note_read` + shape; the owner sees the note text on screen (the harness prints **no** note text or title) | `NOT-MEASURED` |
| 5 | **Quotes fast path + schedule kind** | `chat_quote` — `quick=quote_now` and a ` - Author - Work (Year)` attribution | Chat "send me a quote" (instant, no card). Then "send me a quote every morning at 8" → ONE card listing the next three firings (do **not** approve unless the owner wants it); "send me a quote tomorrow at 6" → no card; watch Coming up / the fired toast | The fast-path answer with attribution; the one card's three times and its "real public-domain quotations on the PC" words; the Coming up "Quote of the day" row; the fired event's own words for that day | `NOT-MEASURED` |
| 6 | **Pack manager: list / inspect / install / remove** | `chat_packs_list` (model turn, `--allow-live-turns`) + `routes_present` (the four `pack_*` tools in `/api/self`) + `skills_read` (supporting) | "list my packs" (no card); "inspect the pack at C:\...\my-skill" (no card, scan only); "install the pack at ..." → ONE `modify_own_code` card showing the whole scan, nothing written before the yes, installed **OFF**; "remove <name>" → ONE card naming the exact files | The list's names/states; the scan's four headings (what/changes/safe/works) and the code-file refusal; the card text; `jarvis-packs.json` entry and the receipt file; the installed pack OFF | `NOT-MEASURED` |
| 7 | **Approval policy changed through chat** | `chat_approval_policy_read` (the read half: the model-free "what asks first" answer; `--allow-live-turns` adds "what needs an approval card?" through the new tool) | Ask what needs a card (no card). Then one **tightening** ("make <action> ask twice") — instant; and one **loosening** ("stop asking before <action>") — ONE `change_approval_policy` card with Windows Hello on the PC, nothing changed until yes | The read answer; the card; the one edited line in `jarvis-framework.toml`; the same row on the asks-first page | `NOT-MEASURED` |
| 8 | **Live read-aloud** | none (no route or §195-199 line names a new Live read-aloud; the bundle's new `MemoryAloud` switch explicitly says it is **not Jarvis Live** — `MemoryAloud.kt:28-30`) | With the remembered-answers switch ON, press the **talk button** and ask a remembered-fact question — the switch covers that, not Live. For Live, press Live and listen; that is the existing spoken session | Your ears and `screens/05-desktop-jarvis.png`; no mechanical claim | `NOT-MEASURED` — not in this target |
| 9 | **Live first turn warm / startup** | none (timing is a stopwatch; `GET /api/voice/live` only shows `on/state/model/turns`) | Press Live and time the first answer; press it again after a minute idle and time it | Two times written down, and the `GET /api/voice/live` body as supporting state. Not a route to prove | `NOT-MEASURED` — timing |
| 10 | **Project repo map** | `repo_map` — `GET /api/projects` then `GET /api/projects/<id>/map` | Ask "map this project" in chat, or open the project | The check's `ok/available/files/symbols/tokens/ranked`; the map text names files and symbols and contains **no** function bodies | `NOT-MEASURED` |
| 11 | **Skills remove when turned off** | `skills_read` (supporting only: `GET /api/skills` count/states; an empty list is BLOCKED, never a pass) | Settings → Skills → turn one OFF → its Remove is offered → Remove asks "are you sure?" → deletes only that folder | The before/after `GET /api/skills` state; the confirmation; the folder gone under `skills-off` and nowhere else | `NOT-MEASURED` |
| 12 | **3-GPU preset naming** | `presets_3gpu` — `GET /api/presets` has `recommendations.by_gpu_count` for 1, 2 and 3, and names them | Look at the Model preset rows for `deep_think` / `creative` and read their "planned / unmeasured / refuses until measured" words | The JSON names; the screen; `MODEL-TOPOLOGY.md:771-800`. **Never** a claim that the third card is installed (the check reports `detected cards: 2`) | `NOT-MEASURED` until looked at |

## 4. The three phone asks, in the owner's order

1. **Send a document.** Backend: §196 is real and read-only-checkable
   (`routes_present`). Phone: the two doors are in `FoldersPlate`. The card is
   `receive_uploaded_document`, tier `ask`, in both `HARD_LIMITS` and
   `MUST_ASK` — no settings line can turn it off. The file lands at
   `<chosen listed folder>\From my phone\<name>`, never overwriting (a taken name
   gets ` (2)`). **Accepted evidence:** the card says name, size and folder name
   only; the file exists with that size; `my_files` finds it.
2. **Notion export import.** The export is only *staged* by the upload path (no
   card at `begin`); the card is the existing `import_notion_export`, raised on
   the preview with the real counts. **Accepted evidence:** the preview counts,
   the card, the vault before/after, Undo. "Refuses until measured" applies to
   nothing here — this is an existing, measured path.
3. **Read remembered answers aloud.** Phone-local, **OFF by default**
   (`ClientSettings.kt:115`), the row named exactly *"Read out answers that use
   what Jarvis remembers"* (`MemoryAloud.kt:43`), with the OFF line *"Off by
   default: an answer that uses what Jarvis remembers stays on your screen"*.
   It covers **only the mic/talk button on this phone while it is unlocked** —
   not "hey Jarvis", and not Jarvis Live (`MemoryAloud.kt:16-35`). So the proof
   is a screenshot of the OFF switch *before* the change, then a spoken
   talk-button question that uses a remembered fact and your ears. The harness
   deliberately does **not** touch it: it is a setting, and settings are the
   owner's.

## 5. What is NOT measured mechanically, and why

| Row | Why not |
|---|---|
| Live read-aloud | No route, tool or §195-199 line in this target adds a Live read-aloud. The phone's default-OFF remembered-answers switch is a **different** thing and says so itself ("not Jarvis Live"). Claiming a PASS would be inventing a feature. |
| Live first turn warm | It is latency; only a person with a stopwatch can measure it. `GET /api/voice/live` shows state, not warm time. |
| Skills remove-when-turned-off | The remove is a UI action with a confirmation; `GET /api/skills` can only show the state before/after. |
| Pack install / remove | Each is ONE card and writes files; the harness must not raise them. `chat_packs_list` (read) and `routes_present` (the tools exist) are the mechanical half. |
| Approval-policy changes | A loosening raises a PC-only Windows Hello card and writes the settings file. The read is mechanical; the change is the owner's. |
| The three phone asks' cards | Each needs the owner's tap on Approve. Screenshots + the file/vault result are the evidence. |
| 3-GPU hardware | The third card is not installed (`detected cards: 2`). Only the naming is checkable. |

## 6. What the harness already measured on the PRE-deploy build (2026-11-06, 0.2.421)

This is the control run: it proves the checks discriminate, and it is not a
result about the deployed build. Run with the live backend PID 18048, the token
read from Credential Manager, no card raised (`pending 0 → 0`), and the token
absent from every written byte. The full JSON is preserved beside this plan as
`results-pre-deploy-control.json` (the Lead's run overwrites `results.json`, not
that file):

```
live_status                  PASS          HTTP 200 with the token
chat_quote                   FAIL          quick='none' - a model answer, not the corpus fast path
chat_packs_list              NOT-MEASURED  model turn; add --allow-live-turns
chat_notes_list              FAIL          the OLD refusal "Chat does not read note text today" (quick=note_read_honest)
chat_approval_policy_read    PASS          the model-free "what asks first" answer
routes_present               FAIL          pack_* and approval_policy missing; no upload plugin
version_identity             PASS          backend 0.2.421 | desktop 0.2.421 | phone 0.2.3845
phone_app_foreground         BLOCKED       the phone is ASLEEP (Dozing, mDreamingLockscreen=true, focus=NotificationShade)
repo_map                     FAIL          GET /api/projects/<id>/map = 404
presets_3gpu                 PASS          1/2/3-GPU rows present; detected cards: 2
skills_read                  BLOCKED       route works, list empty - nothing to observe
11 checks: 4 PASS, 4 FAIL, 2 BLOCKED, 1 NOT-MEASURED
```

Two measured corrections to assumptions in the brief, both encoded in the
harness so the Lead is not chasing a phantom failure:

- **`/api/status` without a token is 401, not 403 — when `X-Jarvis-Client: hud`
  is sent.** 403 is the **cross-origin** refusal (no client header). Measured:
  no headers → `403 {"error": "cross-origin request refused"}`; client header,
  no token → `401 {"error": "bad or missing X-Jarvis-Token"}`. Both are
  BLOCKED; the harness reports which.
- **`GET /api/upload/begin` cannot be `405`.** This server answers
  `404 {"error": "not found"}` for **every** POST-only route asked with GET —
  measured on `/api/schedule/add` and `/api/schedule/act`, which are certainly
  present. So the harness records that code and does not score it; the upload
  route's presence is proved by the plugin in `/api/self` (and, only with
  `--allow-upload-probe`, by a `{}` body that the docs say is refused before a
  card).

## 7. One inconsistency to know before reading the phone screens

§196 line 35481 says the phone's "Send a document" button and folder picker are
"the next lane" — but `jarvis-client` in the **same** tree already ships both
doors (`MainActivity.kt:746`, `Folders.kt:25`, `Upload.kt:93`,
`NotionImport.kt:50`). The doc sentence is stale against the code. The screens
plan therefore expects both doors on `Settings → Folders`; if the deployed APK
does not show them, that is a **FAIL of the phone half**, not a doc typo.

## 8. The one check most likely to reveal a broken deploy

**`chat_notes_list`.** It is the only check with a known **wrong answer to
compare against**: before the deploy the same question answers *"Chat does not
read note text today"* with `quick=note_read_honest`, and §198 deleted that
branch. A deploy that copies the new modules but silently **fails to update
`jarvis_quick.py`** (27 updates, the largest part of the tool's work) leaves
every other surface looking fine — packs and the approval tool can be present in
`/api/self` while chat still speaks the old refusal. This check flips from the
old sentence to `note_list`/`note_read` only when the quick matcher, the notes
helper and the SSE path are all new, so it is the sharpest single signal. If it
still says "Chat does not read note text today", stop and read the deploy log
for `jarvis_quick.py` before testing anything else.

Second: `routes_present` — a missing `pack_list` or upload plugin means a
shipped module or plugin folder did not land.

## 9. Order of operations after the deploy

1. Wake and unlock the phone; run `py -3 screens.py doctor` — it must say
   `ready : True`.
2. Run `py -3 field_test.py` (no opt-ins). Expect `chat_packs_list` and the
   policy tool read to be `NOT-MEASURED`; everything else measured.
3. If the read turn matters, run `py -3 field_test.py --allow-live-turns` — this
   sends two model turns (`list my packs`, `what needs an approval card?`), both
   read-only, and both guarded: a card appearing during them is a `FAIL`.
4. Run `py -3 screens.py run` and look at every PNG. If `04-settings-voice.png`
   does not show the remembered-answers row (it can be below the fold), scroll
   and capture `04b-voice-scrolled` before writing row 3.
5. Do the manual rows in §3 in the owner's order, writing the real label and the
   evidence next to each row. Do not answer a card the owner did not ask to
   answer; do not turn on the remembered-answers switch permanently.
6. Roll the labels into one honest sentence per row, and count `PASS` only where
   the check or your own eyes did the work.
