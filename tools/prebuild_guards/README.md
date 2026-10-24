# Pre-build guards for P-Doc, P-GH and P-Pub

**Status: spec + drop-in helpers + adversarial tests. Nothing is wired into the
product and no CI file is touched; the tests are a desk gate until someone adds
them to the audit job.** This is Section 7 of the owner's work order ("COMPLETE
EXECUTION OF ALL 8 REMAINING SYSTEM REVIEWS"), written before the three waves
exist so their implementation starts with the guards already in place.

The worktree was `review/7-pre-build-guards` off `origin/main` `014af87f5`; it
was merged with newer `main` before its pull request (new files only, no
existing file changed on either side).

| File | What it is | Trap |
|---|---|---|
| `safe_archive.py` | bounded read + XML-bomb refusal for zip members | 1 |
| `windows_names.py` | phone-upload name sanitation and `safe_join` | 2 |
| `github_tree.py` | `base_tree` payload guard and delete counts | 4 |
| `filesystem_walk.py` | project walk that refuses shortcuts | 5 |
| `html_sanitize.py` | EPUB/KDP XHTML allow-list and picture paths | 6 |
| `test_guards.py` | adversarial tests for every guard above | 1, 2, 4, 5, 6 |
| `README.md` | this spec | 3 is spec-only |

Run the proof from the repository root:

```
py -3 -B tools/prebuild_guards/test_guards.py
```

`56 tests run, 56 passed, 0 failed, 0 NOT-TESTABLE/skipped` on 2026-10-23,
including a real Windows directory junction (the machine allowed `mklink /J`,
so the real-shortcut branch was exercised rather than skipped). The tests use
only the standard library, open no socket, and make their folders under the
git-ignored `.dsh-scratch/prebuild-guard-tests` because `%TEMP%` on this PC
refuses writes.

## How to use these modules when the waves are built

Each module is deliberately self-contained: a standard-library import, one
`GuardRefusal` class, plain functions that return a value or raise. Copy the
file into `backend/` beside the module that needs it (the same way
`jarvis_news.py` carries its own small DOCTYPE check), or import it from a
shared helper folder if the Lead prefers. There is no package `__init__.py`,
no third-party dependency and no network code.

**Every refusal is a sentence for the owner**, in beginner words. The module
never returns a partial result: the walk returns nothing, the archive reader
returns nothing, the sanitizer returns nothing. The caller catches
`GuardRefusal` and shows `str(exc)`.

**These are not a second permission model.** None of them approves, logs or
raises a card. P-Doc/P-GH/P-Pub still use `plan` / `describe` / gate / `run`
(`docs/ARCHITECTURE.md` section 3), and the same one gate. The guards only make
the plan safe to show and the run safe to perform.

**A note for the wave PR that copies one of these into `backend/`.** CLAUDE.md's
two-file rule applies: a new `backend/<file>` must also land as
`jarvis-backend/<file>`, and `tools/gen_base_from_backend.py`'s list decides
what is carried. This lane deliberately does neither - it changes no product
file and no published base.

## Step 0 - what this tree already had (reconciliation)

Searched `origin/main` at `014af87f5` (the worktree's own HEAD), with
`git grep` over the tree and `git ls-tree` over `tools/`. Said which tree
because this repository is worked in parallel worktrees (CLAUDE.md).

| Work-order claim | What is already in `origin/main` | Verdict |
|---|---|---|
| Zip path escape and declared-size bomb before an Office parser | `backend/jarvis_documents.py:699` `zip_path_problem`; `:717` `zip_bomb_problem`; `:236` `DOC_UNCOMPRESSED_MAX` (100 MiB); used before MarkItDown at `:1847-1857` | **ALREADY PRESENT** for the declared-total and member-path halves of Trap 1. **Not present:** a bounded read of one XML member, the DOCTYPE/ENTITY pre-check in the document path, the member-count cap and the ratio cap are not applied to Office/EPUB reading. |
| Member count and compression ratio | `backend/jarvis_notion_obsidian.py:329` `_zip_problem`; count at `:345`; ratio at `:372` | **ALREADY PRESENT** for the Notion/Obsidian import only. Not used by any Office/EPUB reader, because none parses XML itself yet. |
| DOCTYPE / ENTITY refusal before the parser | `backend/jarvis_news.py:283` `_declares_doctype` (byte search plus an expat declaration handler, so UTF-16 is caught); used at `:320` and `:347`. `backend/jarvis_android_control.py:656` has the same rule for a phone UI dump | **ALREADY PRESENT** for news feeds and phone UI dumps. Not present in any document reader. |
| Phone-upload filename sanitation, reserved names, `safe_join` | `backend/jarvis_agent.py:212-224` has `_RESERVED_WINDOWS_NAMES` and `_is_reserved_windows_name` (used for `file_read` at `:305`). `backend/jarvis_documents.py:1976-2007` has `_BAD_CHARS`, `_RESERVED` and `safe_parts`, for names inside a Notion import | **PARTIAL.** There is no upload route (`project-uploads` does not appear anywhere), no extension allow-list for phone uploads, and no `safe_join`. A reserved-device check exists but is a path check, not a name sanitiser; `safe_parts` rewrites an import entry, it does not decide what an owner's upload is called. |
| Junction / reparse-point refusal while walking | `backend/jarvis_file_guardian.py:588` `_refuse_reparse` walks a *destination* path with `lstat` and refuses `0x400` at `:609`, at write time. `backend/jarvis_documents.py:769-797` `_walk` prunes a listed folder's directories whose real path leaves the root | **PARTIAL.** Neither is a project-file walker: one guards a write destination, the other reads the owner's listed folders and prunes rather than refuses. No project walker returns stageable relative paths. |
| XHTML sanitisation for EPUB / KDP | `backend/jarvis_readpage.py:269-292` uses `html.parser` to extract the words a reader would see and hides `script`, `style`, `iframe`, `object`, `form` at `:222` for *reading a web page* | **NOT PRESENT** as an output sanitiser. It produces plain text, not XHTML, and has no `<img>` path rule. |
| GitHub `POST /git/trees` writer with `base_tree` | `git grep base_tree` finds nothing. `backend/jarvis_agent.py:2194` has `github_search` (read-only). There is no `jarvis_github_write.py` and no tree/commit writer. | **MISSING.** Built here. |
| Publishing / EPUB XHTML writer | No `jarvis_publishing.py` and no EPUB code anywhere in the tree. | **MISSING.** Built here. |
| Project documents latch `project_docs` **and** `read_outside` | `jarvis_gate.py:2046` (`jarvis-backend/`; the live gate is a patch target) has **one** `latch_taint(minutes=None, why="")`, one database key `'conversation'`. There is no named taint kind and no `source=` argument. `read_outside` is a per-turn chat-history column (`backend/jarvis_chat_log.py:1585`, `:1725`), computed from whether tools ran - not a gate taint. | **MISSING, and the work order's call shape does not match this tree** (see Trap 3). Spec only; the gate lane owns it. |

So the new files are not a second copy of an existing helper:

* `safe_archive.py` does not unpack and does not re-check the declared total
  for `.docx`/`.xlsx`/`.pptx`; P-Doc should still call
  `jarvis_documents.zip_problem` first for those. What is new is the XML half:
  one bounded read of a named member and the DOCTYPE/ENTITY refusal before
  `ElementTree`. For `.epub`, which no existing module reads, it carries the
  archive-level checks itself.
* `windows_names.py` is about **upload names**, not about opening a path.
* `filesystem_walk.py` is the **read/stage** walk; `_refuse_reparse` is the
  write-destination guard and stays the authority there.
* `html_sanitize.py` is an **output** allow-list; `jarvis_readpage.py` is an
  input text extractor.
* `github_tree.py` and the EPUB reader have no existing equivalent to reuse.

`tools/` convention: checkers are standalone `tools/check_*.py` scripts with
`--check` where they gate, and their tests live under `backend/test_*.py` (the
runner globs those). This lane is different on purpose: the deliverable is a
drop-in helper folder plus its own test, and **no existing file - including
`.github/workflows/` - may change under the merge freeze**. The test therefore
does not run in CI yet; that is a known gap, recorded at the end.

---

## Trap 1 - OOXML / EPUB zip bomb and XML bomb (P-Doc-1, P-Pub-1)

**The attack, in two sentences.** A `.docx`, `.xlsx`, `.pptx` or `.epub` is a
zip, and a 1 MB file can hold a part that unpacks to gigabytes. Separately, a
small XML part can define entities that expand to gigabytes, and the standard
parser starts expanding them before it can raise an error. Either one can take
all the PC's memory before a single word is read.

**Guard:** `safe_archive.py`

```python
read_xml_member(zf, member_name, *,
                max_member_bytes=25 * 1024 * 1024,
                max_total_bytes=100 * 1024 * 1024,
                max_members=2_000,
                max_ratio=100) -> xml.etree.ElementTree.Element
```

It raises `safe_archive.GuardRefusal`. The caller opens the zip itself, so it
can catch `zipfile.BadZipFile` and say the file is not a readable document.

What it refuses, in order:

1. more than 2,000 members;
2. a member name that is empty, absolute, drive-qualified (`C:`), holds a
   backslash, is longer than 512 characters, or has any `..` segment;
3. the member it is asked to read, when its header claims more than 25 MB - an
   early refusal, and a safe one, because a header can only make this guard
   refuse, never allow. A large picture elsewhere in the same zip does not
   block the XML part being read;
4. a claimed total over 100 MB;
5. a claimed compression ratio over 100:1, or data with no compressed bytes;
6. a missing member, a folder member, or a password-locked member;
7. a **bounded read**: `fp.read(max_member_bytes + 1)`, deciding on the bytes
   actually returned, never on `ZipInfo.file_size`;
8. a `DOCTYPE` or `ENTITY` declaration, **before** `ElementTree` sees the
   bytes. A byte search is not enough for UTF-16, so expat's declaration
   handlers stop the parse the moment either appears.
9. a parse error or non-well-formed XML.

The 100:1 ratio is deliberately fail-closed: a real Office XML part usually
compresses by 10-50:1, but an extraordinarily repetitive one could pass 100:1
and be refused. If a measured real document ever does, the caller can pass a
higher `max_ratio` for that format rather than removing the cap; the declared
total and the bounded read still protect memory on their own.

The module docstring states exactly what `ElementTree` does and does not
protect against, and why the pre-check cannot be replaced by catching
`ParseError`: by then the entities have already expanded.

**Where it must be called (planned functions - names are placeholders):**

* P-Doc-1: `jarvis_project_docs.read_document_text(path)` - before any office
  converter or XML parse. For `.docx` call
  `read_xml_member(zf, "word/document.xml")`; for `.xlsx`
  `"xl/sharedStrings.xml"`; for `.pptx` the `ppt/slides/slideN.xml` parts.
  Call `jarvis_documents.zip_problem(zf, DOC_UNCOMPRESSED_MAX)` first for
  these three, because that guard already exists.
* P-Pub-1: `jarvis_publishing.read_epub_part(path, name)` - for
  `META-INF/container.xml`, `content.opf`, `toc.ncx` and each chapter
  `.xhtml`. No existing guard covers `.epub`, so this call is the whole
  archive check.
* Read each XML member through this one function; never call `zf.read(name)`
  beside it.

**Refusal the owner reads:**

> Jarvis will not open this file: it is a zip holding more than 2,000 separate
> parts, which is more than a normal document or book has. Nothing was opened.

> Jarvis will not open this file: it carries instructions for defining its own
> text shortcuts (a DOCTYPE or ENTITY). A real document never needs those, and
> they can make one small file expand until the PC runs out of memory. Nothing
> was opened.

**Tests that prove it:** `test_too_many_members_is_refused`,
`test_a_declared_total_over_the_cap_is_refused`,
`test_a_real_high_ratio_zip_is_refused` (4 MiB of zeros, not 4 GB),
`test_a_header_that_lies_about_size_is_refused`,
`test_the_bytes_actually_read_are_capped_even_when_the_header_lies`,
`test_member_names_that_escape_are_refused`,
`test_doctype_is_refused_before_the_parser`,
`test_utf16_doctype_is_refused_too`,
`test_a_large_non_xml_member_does_not_block_the_xml_read`,
`test_a_missing_member_is_refused`,
`test_an_encrypted_member_is_refused`,
`test_a_normal_document_part_is_parsed`.

Remove any one check and its test fails: the member-count test checks the
2,000 sentence, the total test checks the 100 MB sentence, the ratio test
checks the zip-bomb sentence, and the lying-header test drives the fake stream
that declares 10 bytes and yields 4,097.

---

## Trap 2 - phone-upload names on Windows NTFS (P-Doc-1)

**The attack, in two sentences.** The phone sends a name such as `CON.txt`,
`NUL.md`, `COM1.pdf`, `report.pdf:zone.identifier`, `invoice.pdf.` or
`..%2f..%2fsettings.json`, and the backend writes it into the project's upload
folder on a Windows PC. Some of those names open a device instead of a file,
some create a hidden second stream, some are silently changed by Windows, and
some point outside the folder.

**Guard:** `windows_names.py`

```python
sanitize_upload_name(raw_name, *,
                     max_chars=120,
                     allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS) -> str

safe_join(root, raw_name) -> pathlib.Path
```

Both raise `windows_names.GuardRefusal`. The allow-list is `.pdf`, `.docx`,
`.xlsx`, `.pptx`, `.md`, `.txt`, `.csv`.

It refuses the reserved device names (case-insensitive, with an extension, and
the `CONIN$` / `CONOUT$` / `CLOCK$` relatives), any colon, a trailing dot or
space, a leading/trailing space, `/` and `\`, `.` and `..`, control or invisible
format characters, a percent-encoded path, any Windows-forbidden character
(`< > " | ? *`), an extension outside the allow-list, and a name that is empty
after shortening. It normalises to NFKC first (a full-width `：` becomes `:`
and is then refused), lowercases the extension, and shortens a long stem while
keeping the extension.

`safe_join` resolves the upload folder and the joined path, follows links, and
refuses when the result is not under the folder. It writes nothing; the caller
opens the returned path with `"xb"` so an existing file is never silently
replaced.

**Where it must be called:**

* P-Doc-1: `jarvis_project_docs.save_phone_upload(project_id, raw_name,
  data)` - the **first** statement is
  `target = safe_join(upload_root(project_id), raw_name)`, then
  `open(target, "xb")`. Never `os.path.join` the raw name, and never trust the
  multipart layer to have decoded or cleaned it.
* The same function is what the upload route calls before it raises any card:
  a refused name is a `400` with `str(exc)`, and nothing is written.

**Refusal the owner reads:**

> The file name contains a colon (:). On Windows the part after a colon is a
> hidden second file joined to the same name, so it is refused. Please rename
> the file without a colon.

> The file name ends with a dot or a space. Windows quietly removes those, so
> the saved name would not be the name you chose. Please rename the file and
> try again.

**Tests that prove it:** `test_reserved_device_names_are_refused`,
`test_a_colon_is_refused`, `test_a_trailing_dot_or_space_is_refused`,
`test_path_separators_are_refused`, `test_an_encoded_path_is_refused`,
`test_control_and_empty_names_are_refused`,
`test_the_extension_allow_list_is_enforced`, `test_ordinary_names_survive`,
`test_unicode_is_normalised_before_the_checks`,
`test_a_long_name_keeps_its_extension`,
`test_safe_join_stays_under_the_root`,
`test_safe_join_refuses_a_path_that_resolves_outside`.

---

## Trap 3 - project documents must latch BOTH taints (P-Doc-2) - **SPEC ONLY**

**This section has no code in this lane.** It touches `jarvis_gate`, which
another lane owns; writing a second taint path here would be a second approval
mechanism, and `docs/ARCHITECTURE.md` section 3 forbids that. The gate lane and
the P-Doc-2 implementer must agree the representation first.

**The attack, in two sentences.** A project can hold a third-party PDF, a
scraped article or an external `.docx` that was not written by the owner, and
its text can carry an indirect instruction ("turn on the lights", "search the
web and send this"). Entering Project Mode already latches `project_docs` so
the turn stays on the local model, but that latch is about **privacy**; it does
not mark the turn as **shaped by outside text**, so a risky tool can still be
offered as if the owner's own words had asked for it.

**The rule to implement:** whenever `<project_workspace>` injects chunks from a
document that is not explicitly marked `owner_authored_only`, record BOTH
facts before the model sees the text:

1. the project-document privacy latch (`project_docs`), so the turn stays
   local; and
2. the outside-text provenance (`read_outside`), so the card shows "What shaped
   this request" and the tools that ask after outside text ask here too
   (`docs/ARCHITECTURE.md` section 3, "Outside text in the tool loop").

**The work order's proposed call does not match this tree, and the gate lane
must be told.** Today `jarvis-backend/jarvis_gate.py:2046` has:

```python
def latch_taint(minutes: Optional[float] = None, why: str = "") -> bool:
```

There is **one** latch, one database key (`key='conversation'`), no named taint
kind and no `source=` argument. `latch_taint("project_docs")` would pass the
string as `minutes`, `float()` would raise, the function would fall back to 30
minutes and record an empty `why`. `latch_taint("read_outside",
source="project_doc")` cannot run at all: the second positional argument would
land in `minutes` and `source=` is not a keyword. `read_outside` is a per-turn
column in `jarvis_chat_log` (`backend/jarvis_chat_log.py:1585`, written at
`:1725`), not a gate taint.

So the spec is deliberately about the **facts**, not the call shape:

* the gate lane decides whether to add a named reason/kind, a second latch row,
  or to drive the existing per-turn `read_outside` flag through the tool/turn
  path;
* P-Doc-2 then calls **one** agreed entry point, once, before the chunks are
  injected;
* P-Doc-2 must not call `latch_taint` twice and claim "both taints" when the
  gate stores one row; that is a fake pass.

**Where it must be called (placeholder):**
`jarvis_project_docs.build_project_workspace(project_id)` - inside the loop
that injects a document's chunks, before the chunk is added to the prompt.
Chunks marked `owner_authored_only` are the only ones that may skip it.

**What the owner would read (suggested card line, for the gate lane to own):**

> This request was shaped by a document you did not write, so it stays on this
> PC and anything that changes something asks you first.

**Test to write when it is built:** call `build_project_workspace` with one
third-party document and assert (a) the project-document latch is active and
(b) the turn is marked by outside text - on the real gate and the real turn
record, not on a stub. Remove either half and the test must fail. It is not in
`test_guards.py` because no product function exists to drive yet; faking it
would be exactly the "check that proves nothing" this project keeps finding.

---

## Trap 4 - GitHub `base_tree` omission (P-GH-1) - **critical data loss**

**The attack, in two sentences.** GitHub's `POST /git/trees` creates a brand-new
root tree when `base_tree` is missing, so a request that means "change
README.md" becomes "the repository now contains only README.md". The next
commit deletes every other file in the owner's repository.

**Guard:** `github_tree.py`

```python
build_tree_payload(entries, *, base_tree=None,
                   updating_existing_branch=True) -> dict
validate_tree_payload(payload, *, updating_existing_branch=True) -> dict
compare_trees(proposed, current, *, deletion_requested=()) -> dict
counts_line(report) -> str        # "Added: X · Modified: Y · Deleted: 0"
```

`build_tree_payload` and `compare_trees` raise `github_tree.GuardRefusal`. No
network code and no token: they are pure functions over dictionaries.

`build_tree_payload`:

* requires a non-empty (not whitespace) `base_tree` when
  `updating_existing_branch` is true - the safe default;
* refuses an unknown top-level field, naming `baseTree` in particular, because
  a misspelling is the same as leaving `base_tree` out;
* refuses a path that is empty, absolute, drive-qualified, backslash-bearing,
  or has `..` / empty / `.` segments;
* refuses duplicate paths, an unknown `type`/`mode`, both `content` and `sha`,
  neither, or an empty sha;
* allows `updating_existing_branch=False` only for the first commit to a
  brand-new, empty repository.

`compare_trees` compares the proposed paths with `{path: blob sha}` from the
current tree and returns exact `added`, `modified`, `deleted`, `unchanged`
counts and the path lists. It refuses **by default** when anything would be
deleted; a deletion is allowed only when the path is named in
`deletion_requested`, which is the owner's explicit "yes, delete this file".
A path present in both trees counts as modified unless both sides carry the
same non-empty sha; a proposed `content` entry counts as modified, so the card
never understates a change. It compares content, not the file mode: a
mode-only change (100644 to 100755) needs a current tree that carries modes,
which this function does not take, so the caller that reads the tree compares
modes itself and adds them to the card.

**Where it must be called:**

* P-GH-1: `jarvis_github_write.propose_tree_change(branch, entries)`:
  1. read the branch's current commit and its `tree.sha`;
  2. `payload = build_tree_payload(entries, base_tree=that_sha)`;
  3. read the current tree's paths and blob shas
     (`GET /git/trees/{sha}?recursive=1`);
  4. `report = compare_trees(payload["tree"], current,
     deletion_requested=owner_requested_deletions)`;
  5. show `counts_line(report)` on the `github_push` approval card, with the
     changed paths;
  6. only after approval, `POST /git/trees` using `payload`, then the commit,
     then move the branch.
* `jarvis_github_write.commit_and_push(...)` must not build its own tree
  dictionary; it takes the payload this function returned.

**Refusal the owner reads:**

> Jarvis will not send this change to GitHub: the request does not say which
> version of the repository it starts from. Without that, GitHub would make a
> new repository holding only the files in this change, and every other file
> would be deleted. Nothing was sent.

> Jarvis will not send this change to GitHub: it would delete 2 file(s) that
> are in the repository now ('old.md', 'src/gone.py'). Nothing was sent. If
> you really asked for those files to be deleted, name them in the request.

**Tests that prove it:** `test_a_payload_with_no_base_tree_is_refused`,
`test_a_blank_base_tree_is_refused`,
`test_a_misspelled_base_tree_is_refused`,
`test_a_valid_payload_keeps_the_base_tree`,
`test_only_a_new_repository_may_omit_the_base_tree`,
`test_bad_entries_are_refused`,
`test_a_payload_that_deletes_a_file_is_refused`,
`test_an_explicitly_requested_delete_is_allowed_and_counted`,
`test_added_modified_unchanged_and_deleted_are_exact`.

---

## Trap 5 - junctions and reparse points inside a project (P-GH-1)

**The attack, in two sentences.** A project folder can contain a directory
junction (`mklink /J`) or a symbolic link that looks like an ordinary folder
but points at `~/.ssh` or Jarvis's own settings. A walker that follows it reads
and stages private files from outside the project, and a naive
`os.walk(followlinks=False)` can still descend into a junction because a
junction is not a symlink on every Python version.

**Guard:** `filesystem_walk.py`

```python
walk_project_files(root, *,
                   max_files=100_000,
                   max_seconds=30.0,
                   clock=time.monotonic) -> list[str]
```

It raises `filesystem_walk.GuardRefusal` and returns nothing on refusal. It
returns the ordinary files as sorted, `/`-separated paths relative to the root.

It walks top-down with its own `os.scandir` and checks **every** folder with
`os.lstat` before entering it, and every file with `os.lstat` before returning
it. A path is refused when:

* it is a symlink (`stat.S_ISLNK`) **or** its Windows attributes carry
  `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) - both signs are checked, because a
  junction is not always `islink()`;
* its resolved path is outside `root.resolve()` (links followed);
* it is neither an ordinary file nor a folder (a device, pipe or socket);
* a folder changes or cannot be read mid-walk;
* the file cap, time cap or depth cap is hit.

The root itself is checked too: a project folder that is a junction is refused
rather than resolved. A shortcut is **refused**, not skipped, because silently
staging the rest hides that the project is not what the owner thinks it is.

Note for the implementer: OneDrive/NordLocker placeholders also carry 0x400.
This guard refuses them too; copy the project out of the sync folder (or
hydrate it) before staging it. That is deliberate - a file that is a placeholder
is not a local file yet - and should be said in the card, not worked around.

**Where it must be called:**

* P-GH-1: `jarvis_github_write.stage_project_files(project_root)` - the first
  statement is `paths = walk_project_files(project_root)`; only those paths may
  be opened, and each is joined back to the resolved root, never to a name from
  the walk's raw directory listing.
* If a file changes after the walk, the staging read still checks that the
  opened file is the one the walk saw (the same "open the handle and check it"
  shape `jarvis_file_guardian` uses for writes).

**Refusal the owner reads:**

> Jarvis will not read this project folder: it contains a shortcut (a link to
> another place on the PC) at 'linked'. A shortcut like that can make Jarvis
> read private files outside the project, so nothing was read.

**Tests that prove it:** `test_a_normal_tree_walks`,
`test_the_root_must_be_a_folder`,
`test_a_file_symlink_is_refused_by_its_mode` (monkeypatched `os.lstat`),
`test_a_reparse_flagged_folder_is_refused_by_its_attributes` (monkeypatched
0x400), `test_a_file_that_resolves_outside_is_refused` (monkeypatched
`Path.resolve`), `test_a_special_file_is_refused`,
`test_the_file_cap_is_enforced`, `test_the_time_cap_is_enforced`,
`test_the_project_folder_itself_must_not_be_a_shortcut`,
`test_a_real_junction_is_refused_or_not_testable`.

The real-junction test creates an actual `mklink /J` to a sibling folder
holding `secret.txt`; if this machine refused the privilege it reports
`NOT-TESTABLE` and skips - a skip is never counted as a pass. On this run it
was made and the refusal passed.

---

## Trap 6 - EPUB / KDP XHTML and `file://` reads (P-Pub-1)

**The attack, in two sentences.** A chapter pasted from a web page or a
third-party document can carry `<script>`, an `onerror=` attribute, an
`<iframe>` or `<img src="file:///C:/Users/...">`. In the KDP previewer that can
run code or pull a local file into the page, and in the exported EPUB it ships
the hostile markup to every reader.

**Guard:** `html_sanitize.py`

```python
sanitize_xhtml(xhtml, *, assets_dir) -> str
```

It raises `html_sanitize.GuardRefusal` for an unsafe picture path or markup
that cannot be made well-formed; it returns safe XHTML otherwise.

It uses the standard library's `html.parser` with `convert_charrefs=True`, so
quoted attributes, unquoted attributes and entities are handled by the parser,
then rebuilds the markup from a closed world:

* **dropped with contents:** `script`, `style`, `iframe`, `object`, `embed`,
  `form`, `link`, `base`, `meta`, `template`, `noscript`;
* **every `on*` attribute** is dropped (including `on-error` spellings), and
  every attribute not on a small allow-list (`style`, `srcset`, `formaction`
  and friends cannot get through);
* tags not on the allow-list lose the tag but keep their text;
* `<a href>` may be `http:`, `https:`, `mailto:`, a `#` anchor, or a relative
  path with no `..`; `javascript:`, `data:`, `file:` and absolute paths lose
  the attribute;
* `<img src>` must be a **relative** path inside `assets_dir`. Absolute paths,
  drive letters, UNC paths, backslashes, `..` segments, percent-encoded
  traversals (`..%2f`, including double encoding) and every scheme (`file:`,
  `http:`, `data:`) are refused for the whole chapter. A picture reference is
  meaningful, so it is not silently dropped - the owner is told which picture
  is outside and can move it or fix the path;
* the result is parsed again with `ElementTree` before it is returned, so
  mismatched tags are refused instead of producing a broken EPUB.

**Where it must be called:**

* P-Pub-1: `jarvis_publishing.render_chapter_xhtml(chapter, assets_dir)` -
  immediately after Markdown is rendered to HTML and **before** the string is
  written to `OEBPS/chapter-N.xhtml`. The book's own stylesheet is added by
  P-Pub **after** this call; a chapter's own `<style>`/`<link>` is deliberately
  thrown away.
* The same call is used for the Desktop WebView2 KDP print preview, so the
  preview and the exported EPUB get exactly the same text.

**Refusal the owner reads:**

> Jarvis will not build this chapter: the picture
> 'file:///C:/Users/me/secret.png' points at a file on this PC, which a book
> chapter may not do. A picture path can make the previewer read a file
> elsewhere on the PC, so nothing was built. Move the picture into the book's
> pictures folder and use a path relative to it.

**Tests that prove it:** `test_script_and_event_handlers_are_removed`,
`test_a_file_url_picture_is_refused`,
`test_a_path_above_the_assets_folder_is_refused`,
`test_a_percent_encoded_escape_is_refused`,
`test_absolute_and_unc_pictures_are_refused`,
`test_a_javascript_link_loses_its_href`,
`test_harmless_markup_and_entities_survive`,
`test_a_picture_inside_the_assets_folder_is_kept`,
`test_mismatched_markup_is_refused`,
`test_a_picture_that_resolves_outside_the_assets_folder_is_refused`,
`test_dangerous_containers_are_dropped_with_their_contents`,
`test_a_void_tag_inside_a_dropped_container_does_not_swallow_the_rest`,
`test_a_full_document_keeps_its_structure_but_loses_style_and_link`.

The crafted chapter used by the work order (script, `onerror=`,
`file:///C:/...`, `../../secret`) is split across those tests: the first
asserts the script and the event handler are gone, the others assert each
local-file path is refused.

---

## What is deliberately not here

* **No product code, no wiring, no call sites.** The wave modules
  (`jarvis_project_docs.py`, `jarvis_github_write.py`, `jarvis_publishing.py`)
  do not exist; the function names above are placeholders.
* **Trap 3 has no code.** It belongs to the gate lane; the work order's call
  shape does not match the gate in this tree (see Trap 3).
* **No CI changes.** Under the merge freeze this lane may not edit
  `.github/workflows/`, so `test_guards.py` is a desk gate run by the command
  above, not a CI job yet. The Lead should wire it when the freeze lifts (a
  single `py -3 -B tools/prebuild_guards/test_guards.py` step, or a
  `backend/test_*.py` wrapper if the runner's glob is preferred).
* **No `docs/` changes.** This README is under `tools/`, so the document count
  and size at the top of `docs/README.md` are untouched.
* **Nothing scanned by the zero-jargon or claims checkers.** `check_zero_jargon.py`
  reads the shipped backend modules, the HUD, Rust and Android resources - not
  `tools/`; `check_claims.py` reads `docs/CLAIMS.tsv`, which is unchanged. Both
  stay as they were.
* **No network, no token, no third-party dependency.** Every module imports
  only the standard library. The GitHub module never sends the payload; it
  only builds and checks it.
* **Not tested here:** how the real P-Doc/P-GH/P-Pub routes behave on the
  owner's live backend (they do not exist), the KDP previewer's own behaviour
  with the sanitised XHTML, and whether a real 25 MB XML member is refused
  quickly enough on his PC. Those become field-test rows when the waves are
  built; they are not claimed as passes.
