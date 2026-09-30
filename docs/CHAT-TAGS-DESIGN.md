# Chat tags and sections in History: design (2026-09-30)

Status: **designed, not built.** The owner asked (2026-09-30) for sections in
History that separate tagged chats (educational, work and so on), for a
"nice visual system" to organise them, and for a way to ask Jarvis to label a
chat during the chat or later, including an older one. Built after the Quiz
Slice A builders finish, because both touch `brain.html`, `lib.rs`,
`check_parity.py` and `docs/JARVIS-API.md`.

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
  titles (the Rust side must call `lock::private_hidden`), sections show only
  a count. Screenshots stay blocked as today.
- Screen readers read "Work, 12 chats, collapsed" and the tag on each row.

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
