# File guardian, and its File history drawer

The local "time machine" for files Jarvis changes (`backend/jarvis_file_guardian.py`,
Pillar 18), and the desktop drawer the owner actually uses (LM-2C, 2026-10-18).
JARVIS-API section 140 is the route contract; this page is the design record:
what is built, what it deliberately is not, and the rules that must not move.

## What the guardian keeps

Before a write over a file inside a folder the owner already allows Jarvis to
change, it stores a gzip copy of the file's CURRENT bytes under the sha256 of
those bytes, and appends one row to `guardian.jsonl`: when, the full path, the
saved sha256, the size, why, and the id of the EXISTING `jarvis_receipts`
receipt it leaves. The same bytes are stored once. The store prunes its OLDEST
unpinned copies to 250 MB and never removes a pinned one. It is not a backup and
not encryption: the copies are in the owner's settings folder on this PC.

Already wired before this slice: `jarvis_note_capture.py` snapshots the daily
note before an approved append, and `jarvis_projects.py` snapshots Project
Mode's pointer file before replacing it. The restore path stores the version
here now and a NEW receipt BEFORE it writes, so the existing Undo reverses the
restore in one click.

## The routes (all in the existing brain-reads install)

| Route | What it does |
| --- | --- |
| `GET /api/guardian/snapshots?limit=` | the journal, newest first, one bounded page (50 default, 200 max), only the contract's fields |
| `GET /api/guardian/diff?path=&sha_before=` | the module's own bounded unified diff, passed back unchanged |
| `POST /api/guardian/restore` | the ONE write: the module raises the EXISTING `undo_action` card through the real `jarvis_gate.check()`, saves the current version and a new receipt, then writes |

No restore happens without a person's yes, no gate can be named over the wire,
and a request from another device is refused before the body is read
(`jarvis_owner_check.from_this_pc`). The routes are PC-only by design: the
copies are files on the PC, and the phone has no PC folder to show
(ARCHITECTURE section 8; `tools/check_parity.py` carries them `deliberate`).

## The desktop drawer (LM-2C)

Brain -> **Projects** -> **File history** (`jarvis-desktop/src/guardian-panel.js`
draws it; `guardian.js` holds the words and decisions, pure and tested in node).
It sits beside Progress and Pictures because the files it keeps copies of are
project files and notes.

* the list is **newest first** and shows a copy's file name, when, why and size -
  never a file's words, and only the fields the contract names;
* "Show the difference" asks `guardian_diff` and draws the module's bounded diff
  in one `<pre>`, saying when it was cut;
* "Put this version back" asks "are you sure?" on the PC, then calls
  `guardian_restore`. The PC raises the EXISTING `undo_action` card in the
  Jarvis bar; **this page approves nothing** and shows the PC's own sentence for
  every outcome. A refused restore changes nothing, so nothing is re-read and
  nothing is re-sent;
* the whole drawer **hides** while App lock is locked OR "Hide memory lists and
  chat history" is on. The decision is made in Rust (`brain/guardian.rs`,
  `words_hidden`), not on the page: while hidden the answer is ONE sentence that
  names no file, no count and no folder, and neither `brain_read`'s list section
  nor the two commands ask the PC for anything - so while hidden no file name
  crosses the loopback wire. `security-changed` clears the rows and an open
  difference at once, before the next read is asked for, and a restore answer
  that comes back after a flag changed is re-hidden before the page sees it.
  This is the desktop half of the gap JARVIS-API section 140.3 records:  the backend cannot see either flag, so the desktop is the only place it can be
  enforced.

**Least privilege:** the list rides on the existing `brain_read` allowlist
(`guardian_history` -> the snapshots route); the two commands that need
arguments are in one `brain-guardian` permission set held by the Brain window
only (`allow-guardian-diff`, `allow-guardian-restore`). The restore waits up to
twenty minutes in Rust because the card waits for a person (the PC's gate allows
fifteen). No HUD page, no new window, and no change to `commands.rs`.

## What this slice deliberately does not do

* **No phone page.** It is not a gap: the copies are PC files, and the PC
  refuses another device before it reads.
* **No pin, prune, usage or quota screen.** Those functions exist in the module
  and stay unexposed until someone asks for them; the drawer only lists, diffs
  and restores.
* **No per-project filter or search.** The page shows the whole journal a page
  at a time; project grouping would need a route decision (what a project's
  files are) that has not been made.
* **No link from the Receipts list into a copy.** Receipts already have an Undo;
  the guardian drawer is the file-level view, and joining the two is a design
  question for later.
* **No automatic tidy of the drawer**: it is a page, not a store.

## Tests that hold this

* `backend/test_file_guardian.py` (263 checks): the store, the refusals, the
  restore on a person's yes, and the three routes - another device 403 before
  the body is read, an approved restore writes the saved bytes and leaves a
  receipt whose Undo restores what it replaced, a denied/timed-out/unraisable
  card writes nothing, a failed save-before-write aborts, and a GET of the
  restore path is never answered by the routes.
* `jarvis-desktop/src-tauri/src/brain/guardian.rs` `#[cfg(test)]`: both flags
  hide the drawer, the hidden answer carries no file and no count, a path is
  escaped into the diff request, and the restore waits for a person's card.
* `jarvis-desktop/tests/guardian-drawer.mjs`: the pure rules (newest first, no
  contents, hidden whole, bounded diff, one restore request, a refused restore
  refreshes nothing) and the wiring (capability, ACL, parity, docs).
* `node tests/guardian-drawer.mjs`, `cargo test`, and the two app checks
  (`check_command_acl`, `check_invoke_grants`) agree about every command.
