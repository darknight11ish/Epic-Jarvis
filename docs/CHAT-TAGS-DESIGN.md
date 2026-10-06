# Chat tags and sections in History: design (2026-09-30)

Status: **built** (re-checked 2026-10-05: `backend/jarvis_chat_log.py` holds the
tags from line 455, `backend/jarvis_quick.py` the asking, and JARVIS-API section
99 the shapes and words both apps build from; this page called itself a design
until the claims register re-checked it). The owner asked (2026-09-30) for
sections in History that separate tagged chats (educational, work and so on),
for a "nice visual system" to organise them, and for a way to ask Jarvis to
label a chat during the chat or later, including an older one.

## 1. The owner's answers (2026-09-30)

- **Tags:** a starter set (Work, Learning, Personal, Projects, Ideas) that can
  be renamed, deleted, added to.
- **One tag per chat.** Moving a chat means changing its tag.
- **Look:** collapsible sections. Each tag is a coloured header with an icon,
  its name and a count; a row of tag chips at the top filters to one tag;
  "Untagged" sits at the bottom. Colour is never the only clue.
- **Label by asking Jarvis:** applies at once, **no card**. Jarvis answers
  "Done, filed under Work. You can change it in History."
- **Older chats:** Jarvis never guesses. It shows the matching chats in History
  and the owner **taps the one** to file under the chosen tag.
- **No automatic tagging.** Jarvis tags only when asked.

## 2. Outside suggestions, checked (Gemini list, 2026-09-30)

All four exist but none is used.

| Project | Licence | Verdict |
|---|---|---|
| VectifyAI/ChatIndex | Apache-2.0 | No. A model-written tree of summaries of past chats is an index over encrypted chats (ARCHITECTURE §11: "No index, ever"; anything handing past chat words to the model waits on memory ideas 1-4). It calls OpenAI/Anthropic by default and saves plain JSON. |
| BERTopic | MIT | No. About 69 packages including torch and CUDA wheels; needs hundreds of documents to form topics; embeddings of chats are a content-leaking index. |
| text-clustering-via-llm | none (all rights reserved) | No. Research code hard-wired to OpenAI. |
| semantic-kernel reducers | MIT | No. They shorten the live prompt, and Jarvis never compresses stored transcripts (ARCHITECTURE line 1314). |

The tree index in the SQLite memory database: **no**. Revisit after memory
ideas 1-4 are measured.

## 3. Storage (`backend/jarvis_chat_log.py`, shipped whole)

- **Tag names are the owner's words**, so they are sealed like `title`: a small
  registry of tags `{id, name, colour, icon, order}` is kept as one sealed value
  in the `meta` table (key `tags`), with the same AAD pattern the title uses.
  Starter tags are written into it the first time it is read.
- **Each chat carries only an opaque `tag_id` INTEGER** in a new plain column,
  added by `_migrate` (`ALTER TABLE ... ADD COLUMN`, like `kind`). Not the
  existing `project` column: Projects step 4 owns that.
- The column must be carried by every path that copies a conversation row:
  `list`, `_row`, `get`, `take_out`, `put_back._put_one` (which pads to 7 fields
  today), `search`, `overlapping`, `brief`. Otherwise Undo of "Forget a time
  frame" would silently lose the tag.
- **Row copies are hand-written positional tuples** in `list`, `get`, `brief`,
  `overlapping`, `take_out` and `put_back` (`_put_one` writes `conv[:8]`, padding
  a held row from before `kind`/`tag_id`). A new column must be added to each by
  hand, in the same position, or a chat silently loses it on Undo. **Refactor
  before Fork (section 8):** replace the positional tuples with one named row
  helper (a column list read once) before "Fork from here" adds another copy
  path, so a fork cannot drop `tag_id` or `read_outside` the same way.
- **Tagging works while chat history is off** (owner, 2026-09-30): filing an
  already-saved chat records nothing new, so tag reads and writes need only the
  key. No key, nothing read or written; a chat never saved cannot be tagged.
- Deleting a tag sets its chats to untagged (after a confirm). Deleting a chat
  leaves the registry alone. Tag names never enter memory, facts, the learner or
  a search index.
- Any kind of chat (chat, Live, support, chatbot, comparison, a "difficult
  moment") may be tagged by the owner. Nothing is ever tagged automatically.

## 4. Routes (JARVIS-API section 99, to be written with the build)

| Route | Body | Notes |
|---|---|---|
| `GET /api/history/tags` | - | the registry, plus counts per tag |
| `POST /api/history/tags` | `{"op": "add"\|"rename"\|"recolor"\|"delete"\|"move", ...}` | no card; delete asks a confirm in the app |
| `POST /api/history/tag` | `{"id": chat_id, "tag_id": int \| null}` | file or unfile one chat; no card |
| `GET /api/history` | new `tag` filter (`tag=<id>` or `tag=none`); rows gain `tag_id` | |

Routes go through `chat-history.patch`'s whitelists (or a shipped-whole module
like `jarvis_brain_reads.py`); run `python3 tools/build_patch_history.py` after
any patch edit. Add rows to `tools/check_parity.py`.

## 5. Asking Jarvis (`backend/jarvis_quick.py`)

- New quick intent beside `_FROM_NOW_ON` and `_forget_range`, e.g. "label this
  chat Work", "file this under Learning", "tag this as Ideas". It acts on the
  conversation the request carries, at once, with no card, and only from the
  owner's newest typed or spoken words (`newest_own_words`): never after outside
  text, never from a pasted or shared message.
- A tag name that does not exist: Jarvis lists the tags that do and says tags
  are made in History. It does not create tags by voice.
- Older chat ("label my chat about the boiler as Home"): the quick answer sets
  `open_brain: "history"` with a pending "file under Home" and the search words;
  History shows the matches and the banner "Tap the chat to file it under Home."
  Nothing changes until the owner taps. The new route field needs the desktop
  whitelist (`commands.rs` ~1846 and its test) and the phone's `ChatSession.kt`
  reader. The on-screen History search (§71) does the matching, so no chat text
  is handed to the model.
- Add the phrases to the "what can I say" list (`tools/gen_sayable_cases.py`).

## 6. The visual system (both apps, one shared fixture)

- **Eight colour slots**, each tested for contrast against both themes' surfaces
  (text on tinted header at least 4.5:1) and a light and a dark variant; a
  colour is never the only clue: every tag also shows its **icon** and its
  **name**. Icons are named in a shared list and drawn with each app's own icon
  set (no emoji, so both apps match).
- Starter tags: Work (briefcase, blue), Learning (book, green), Personal (home,
  amber), Projects (folder, violet), Ideas (lightbulb, teal).
- Collapsible sections, newest chat first inside each; the open/closed state is
  remembered per device (a harmless view preference, not chat content).
  "Untagged" is last. The chip row filters to one tag; "All" clears it. The
  Live/support filter ("Show") keeps working with the tags.
- A "Tags" editor in History: add, rename, recolour, reorder, delete.
- Under "Hide memory lists and chat history": tag names are hidden along with
  titles (the Rust side must call `lock::private_hidden`); both apps show the
  hidden list as one flat block, "N conversations, hidden", not sections with a
  count. Screenshots stay blocked as today. With no tags at all the list is
  flat too (sections appear once at least one tag exists).
- Screen readers: the phone reads "Work, 12 chats, collapsed" (a merged
  description); the desktop's header says "Work, 12 chats" and carries the
  open/closed state in `aria-expanded`, so it is not said twice. Both read the
  tag on each row.

## 7. Files and tests

Backend: `jarvis_chat_log.py` (column, registry, list filter), `chat-history.patch`,
`jarvis_quick.py` grammar, `test_chat_tags.py`; fix `test_chat_kinds.py` (project
None; the migration's column set) and `test_forget_range.py` (Undo keeps tags).
Desktop: `history-view.js` (row parser, grouping), `brain.js` (`paintHistoryListNow`
sections and chips, editor), `src-tauri/src/brain/history.rs` (commands, redact,
`private_hidden`), `lib.rs`, `capabilities/brain.json`, permission tomls.
Phone: `net/ChatLog.kt`, `ui/screens/HistoryScreen.kt`, `JarvisRuntime.kt`,
`JarvisApi.kt`, `net/ChatSession.kt` (route field). Shared:
`tools/gen_history_cases.py` (tag words, palette, icon names), then regenerate;
`tools/check_parity.py`; `docs/JARVIS-API.md`. The feature audit runs with it.

## 8. Fork a chat (owner said yes, 2026-09-30; built after tags)

"Fork from here" on a message in History copies the first N turns into a NEW
conversation (new id, title "Fork of ..."), in both apps. No tree, no new table.
Rules: each turn is re-sealed under the new id (the seal is bound to id + index,
as `take_out`/`put_back` already do); the fork keeps the source's tag unless
changed; copies `read_outside`; never forks a crisis chat, or a support, chatbot or
comparison record; does not carry a Forget/Erase "hush" floor; a test must show
copied turns do not teach the learner the same facts twice. No card (the owner's
own kept words, nothing leaves the PC); hidden under "Hide memory lists". Full
branching (tldraw canvas, a node graph) stays closed: JARVIS-API §18.6 keeps it
a proposal.

## 9. Not decided / later

Suggesting tags by the model (owner said no; a later, cards-only overnight opt-in could be asked again if many chats stay untagged). A manual "new section here" marker inside a long chat. A cross-chat question across old
chats (waits on memory ideas 1-4). Tag-based auto-delete rules.

## 10. Slice contract (frozen 2026-09-30; JARVIS-API section 99)

Three builders (backend, desktop, phone) work from this. Sections 1-9 are the
decisions; this section is the exact shape.

**Tags.** `Tag` = `{"id": int, "name": str (1-24 code points, NFC, trimmed, at least one
visible character, unique ignoring case and NFC/NFD),
"colour": 0-7, "icon": str, "order": int}`. At most **12** tags. The starter tags
are created the first time the registry is read: ids 1-5 = Work (colour 0 blue,
icon `briefcase`), Learning (1 green, `book`), Personal (2 amber, `home`),
Projects (3 violet, `folder`), Ideas (4 teal, `lightbulb`). New tags take the next
unused id (never reuse a deleted id). Icon names (shared list, each app draws them
with its own icon set): `briefcase book home folder lightbulb star flag wrench leaf music`.

**Colour slots** (0-7: blue, green, amber, violet, teal, rose, slate, orange). Text
ink on a tinted header, contrast 4.5:1 or better in both themes (checked):

| slot | name | light ink | dark ink |
|---|---|---|---|
| 0 | blue | #1d4ed8 | #93b4ff |
| 1 | green | #146c36 | #86e0a6 |
| 2 | amber | #8a5300 | #f5c26b |
| 3 | violet | #6d28d9 | #c4a8ff |
| 4 | teal | #0f766e | #7adfd3 |
| 5 | rose | #be123c | #ff9ab5 |
| 6 | slate | #475569 | #b6c2d1 |
| 7 | orange | #b43a00 | #ffb385 |

The header tint is the ink at 12% (light) or 16% (dark) over the surface. The
palette and icon list live in the shared fixture `history-cases.json`
(`tools/gen_history_cases.py`, owned by the backend builder), which both apps'
tests read; colour is never the only clue (icon + name + count always show).

**Routes.**

| Route | Body | Answer |
|---|---|---|
| `GET /api/history/tags` | - | `{"ok": true, "tags": [Tag + "count"], "untagged": int}`; while private lists are hidden the desktop/phone redact names |
| `POST /api/history/tags` | `{"op": "add", "name", "colour"?, "icon"?}` | `{"ok": true, "tag": Tag, "tags": [...]}` |
| | `{"op": "rename", "id", "name"}` / `{"op": "style", "id", "colour"?, "icon"?}` / `{"op": "move", "id", "before": id \| null}` / `{"op": "delete", "id"}` | same answer; delete makes its chats untagged |
| `POST /api/history/tag` | `{"id": chat_id, "tag_id": int \| null}` | `{"ok": true, "id", "tag_id"}` |
| `GET /api/history` | new `tag=<id>` or `tag=none` filter | rows and the single-conversation read gain `"tag_id": int \| null` |

Errors (sentence choice in JARVIS-API §99.2: **the PC's `message` wins when it is not empty, then the code's fixed sentence, then the fallback** - one rule for tags and fork, both apps) `{"ok": false, "error", "message"}`: `bad_name`, `name_taken`, `too_many_tags`,
`bad_colour`, `bad_icon`, `tag_not_found`, `not_found` (chat), `bad_request`.
No card anywhere (the owner's own organisation, nothing leaves the PC). Every
write is held on a stale link (rule 4).

**Storage** exactly as section 3: registry sealed in `meta` key `tags`; plain
`conversations.tag_id INTEGER` column; carried by every row-copy path incl.
`take_out`/`put_back`; never in memory, facts, learner or search index.

**Asking Jarvis** (`jarvis_quick.py`, backend only; the apps just show the reply).
Current chat: "label this chat Work", "file this under Learning", "tag this as Ideas",
"remove the tag from this chat" -> acts on the request's conversation at once,
reply `Done, filed under Work. You can change it in History.` Unknown name -> `I
do not have a tag called Garage. Your tags are: Work, Learning. Make new ones in
History.` Only from the newest typed/spoken words. Older chat ("label my chat
about the boiler as Home"): reply `Tap the chat you mean in History and I will file
it under Home.` and add route fields `open_brain: "history"`, `file_under: <tag id>`,
`history_q: "<search words>"`. The apps whitelist those two new keys (desktop
`commands.rs` route-key list and its test; phone `net/ChatSession.kt`), open
History with the search prefilled and the banner `Tap the chat to file it under
Home.`; tapping a row files it (POST /api/history/tag) and clears the banner;
Cancel clears it. Nothing is filed until the owner taps.

**Shared words** (both apps, word for word): `Untagged`, `All`, `Tags` (editor
title), `Add a tag`, `Rename`, `Delete this tag`, `Move to`, `No tag`, section
header `{name} ({count})` with the screen-reader form `{name}, {count} chats,
collapsed|expanded` (the phone's merged description; the desktop conveys the
state through `aria-expanded` and labels the header `{name}, {count} chats`),
delete confirm `Delete the tag {name}? Its {count} chats
become untagged.`, banner `Tap the chat to file it under {name}.`, editor errors
one plain sentence per code above.

**Filter chips.** Both apps show the chip row as `All`, then one chip per tag
in the owner's order, then `Untagged` (the backend takes `tag=none`). Decided
2026-09-30 so the two apps behave the same; the PC and the phone both show the
count on the Untagged chip. Also shared, word for word: `Filed under {name}.`,
`Tag taken off.`, `Move to…` (the desktop's list placeholder) and the
banner button `File under {name}` (fixture keys `tag_filed`, `tag_unfiled`,
`tag_move_placeholder`, `tag_file_under`). An opened conversation shows its tag
and the same "Move to" list on both apps.

**Owned files.** Backend: `jarvis_chat_log.py`, `chat-history.patch`,
`jarvis_quick.py` grammar (+ `tools/gen_sayable_cases.py`), `test_chat_tags.py`,
fixes to `test_chat_kinds.py`/`test_forget_range.py`, `tools/gen_history_cases.py`
(writes both apps' fixture copies), `tools/check_parity.py` rows, JARVIS-API §99,
`apply-patches.ps1`/`_where.py` lists if needed. Desktop: everything under
`jarvis-desktop/` (history-view.js, brain.js/html/css History parts,
`src-tauri/src/brain/history.rs` + lib.rs/capabilities/permissions, commands.rs
route keys, tests). Phone: everything under `jarvis-client/` (ChatLog.kt,
HistoryScreen.kt, JarvisApi/JarvisRuntime, ChatSession.kt, tests). Collapsed/open
state of each section is remembered per device (a harmless view preference);
nothing else about tags is stored on a device, apart from the desktop's brief
hand-over key for "label my chat about the boiler as Home" (`jarvis.brain.place`,
holding a tag id and the search words), which is removed the moment the Brain
reads it, and after a minute if it never does.

## Fork contract (frozen)

Frozen 2026-09-30 for the desktop and phone builders (backend built and tested:
`backend/test_chat_fork.py`, JARVIS-API section 110). Section 8 holds the
decision; this is the exact shape. Where this and section 8 differ, this wins.

**Route.** `POST /api/history/fork` with exactly `{"id": "<chat id>", "upto": <int>}`
(no other keys). `upto` is the `idx` of a turn, taken from the opened chat's
`turns[].idx` (a new field on every turn of `GET /api/history/conversation`).
Turns `0..upto` are copied. Answer `200`:
`{"ok": true, "id": "<new id>", "title": "Fork of ...", "turns": <int>, "tag_id": <int | null>}`.
After a fork the desktop clears any kind, tag chip and search words so the new chat
cannot be filtered out, and keeps it open (the phone already opens it by id).

**The opened chat** (`GET /api/history/conversation`) also gains, on the chat,
`"forkable": true | false` and `"fork_why": ""` (or a sentence when not
forkable). Forkable = a chat or a Live session that is not "A difficult moment".
Apps show the button only when `forkable` is true; when false they show
`fork_why` where the button would be (like `continue_why`) and no button.

**Errors** `{"ok": false, "error", "message"}` (one plain sentence, show
`message`; the rule is: the PC's `message` wins when it is not empty, then the
code's fixed sentence, then the shared fallback - the same as for tags; fixture
`fork_error_cases` has worked cases, including a known code plus a different
message): `bad_request` (400, also for an `upto` that is not a whole number or is
absurdly large,
or 503 when the key is missing or wrong: "... The chat was not forked."),
`not_found` (404), `not_forkable` (409). Nothing is retried. No card anywhere.

**What the backend decided** (the apps need not re-check, but must not contradict):
the fork is kind `chat` (also from a Live session), keeps the source's tag,
outside-text marks and device, keeps the source's `started`, has `updated` = the
moment of the fork (owner, 2026-09-30: it counts as new, so it is at the top of
History with a full keep period), has its own learning hush (copying the
source's `erased` flag) so its copied messages are not
learned twice, and works while chat history is off (only the key matters).
A user message as fork point is copied without its answer.

**Words** (fixture `history-cases.json`, `words.fork*`, word for word in both
apps): button `Fork from here` (`fork`); its hover/help text `fork_title`;
screen-reader names `Fork from here, after your message` and `Fork from here,
after Jarvis's answer` (`fork_labels`; both contain the visible text); while
waiting `Forking…`; on success `Forked into "{title}".` (`fork_done`, with the
title the backend sent); a chat that cannot be forked: the backend's `fork_why`
(`fork_why_kind`, `fork_why_crisis`), else `This chat cannot be forked.`
(`fork_no`); other errors by `fork_error_cases`, fallback `Your PC did not fork
that chat.` The title `Fork of {title}` is made by the backend; apps never
build it.

**What each app builds.**

* *Both:* in the opened chat in History, a **Fork from here** button on every
  message the owner sent and every answer Jarvis kept (turns with role `user` or
  `assistant`; never on a support, chatbot or comparison record, which are not
  forkable anyway). Pressing it sends the route with that turn's `idx`. On
  success the app **opens the new chat in History** (the same open as tapping
  its row: read `GET /api/history/conversation?id=<new id>`), refreshes the list
  so the fork appears (at the top, as it counts as new), and shows `fork_done`. The
  original stays as it was. On a refusal the app stays on the original chat and
  shows the sentence. The button is disabled with `Forking…` while the request
  runs (one at a time). A fork is offered to nothing else: no card, no undo (a
  fork is deleted like any chat), no automatic fork.
* *Stale link (rule 4):* forking writes a new chat, so the button is held
  (disabled, with the app's usual stale-link reason) while the link to the PC is
  stale, like tagging.
* *Hidden lists:* under "Hide memory lists and chat history" the opened chat is
  hidden already, so no button shows; nothing is forked from a hidden list.
* *Screen readers:* each button's accessible name is the `fork_labels` sentence
  for its message's role; the success and error sentences are announced politely.
* *Desktop:* `brain/history.rs` gets one command (`brain_history_fork`, exactly
  the two keys; the answer reduced to `ok`, `id`, `title`, `turns`, `tag_id` or
  the refusal's `error` and `message`; title redacted while private lists are
  hidden like other titles), registered in `lib.rs` and the Brain's capability
  and permission files; `brain.js` (History) draws the buttons and follows the
  new id; the opened-chat reader keeps `idx`, `forkable`, `fork_why`; tests read
  `words.fork*` and `fork_error_cases` from the fixture.
* *Phone:* `net/ChatLog.kt` parses `idx`, `forkable`, `fork_why` and the answer;
  `JarvisApi.kt` and `JarvisRuntime.forkChat` call the route (held on a stale
  link); `HistoryScreen.kt` draws the button on each message and, on success,
  opens the new chat; tests read the same fixture keys.
* *Neither app* computes the title, checks the kind itself beyond `forkable`, or
  keeps anything about a fork on the device.

**Parity:** `tools/check_parity.py` already classifies `/api/history/fork` as
`ported`; it stays red ("classified here but the desktop no longer calls it")
until the desktop's Rust calls the route.
