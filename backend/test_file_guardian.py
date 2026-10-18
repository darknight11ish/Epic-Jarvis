"""test_file_guardian.py - Pillar 18, the local "time machine" for the files Jarvis changes
(jarvis_file_guardian.py, its journal, its content-addressed blob store, and the
EXISTING jarvis_receipts.py undo receipts).

    python -B backend/test_file_guardian.py

Runs anywhere: no network, no model, no real file of the owner's. Everything
lives in this suite's own temporary folder, and `OPENJARVIS_HOME`,
`OPENJARVIS_CONFIG_DIR`, `JARVIS_RECEIPTS_DB` and `JARVIS_GUARDIAN_FOLDERS` all
point into it, so nothing under `~/.openjarvis` is read or written.

What it proves:

 1. THE CONTRACT: the quota is 250 MB; the approval action is the EXISTING
    `undo_action` (the same string jarvis_receipts.py uses); a snapshot changes
    nothing; every result is a documented dict and never a traceback.
 2. THE COPY IS CONTENT-ADDRESSED: sha256 of the CURRENT bytes names the blob,
    the blob is gzip and decompresses byte-identically, the journal row carries
    timestamp/path/before_sha256/size/reason/receipt_id, and the receipt is a
    real jarvis_receipts row whose before snapshot carries the hash and an
    opaque copy id - never the path and never the file's words.
 3. DEDUP: the same bytes twice store ONE blob (and two rows); two files with
    the same bytes share it. A changed file gets a new blob.
 4. A DIFF: -old/+new lines and a hunk header; `same` when there is nothing to
    show; `binary` for a NUL byte; an unknown saved version is refused.
 5. A BOUNDED DIFF: a large difference is cut at MAX_DIFF_BYTES, says so
    (`truncated`), and is shorter than the whole difference would be.
 6. THE QUOTA: over the limit the OLDEST unpinned versions are removed first,
    what was removed is named, an under-quota store loses nothing, and a
    PINNED version is never removed - even when that leaves it over quota.
    A removed version can no longer be shown or restored.
 7. THE REFUSALS: a symlink, a path outside every allowed folder, a folder, a
    missing file, no allowed folder at all, a file over the per-file limit, and
    a file that cannot be read - all plain sentences, with no blob and no row
    created and the file intact. The size ceiling is checked BEFORE a byte is
    read: an oversized file is refused with `error="file_too_large_for_guardian"`
    plus `size_bytes`/`max_file_bytes`, the read is never called, and a caller
    may lower the ceiling for its own call.
 8. ALLOWED FOLDERS: the owner's own "Folders Jarvis may look in" list and the
    configured Obsidian vault both make a folder allowed, through the REAL
    jarvis_documents.py / jarvis_notes.py modules.
 9. THE HOME FOLDER: `OPENJARVIS_HOME` is honoured and a second one is a
    second, separate store; with it unset the settings-folder rule of
    jarvis_receipts.py is followed, never a guess at `~/.openjarvis`.
10. THE GATE: a restore is refused by a denied card, a timed-out card, a card
    that cannot be raised and `allowed=True` with an `auto`/`notify` outcome
    that is NOT a person's yes; the module's own jarvis_gate path is the one
    used when no gate is passed; there is no argument that skips it.
11. THE RESTORE: the bytes are put back EXACTLY; a NEW receipt is left whose
    Undo puts the restore back (live callable and, after a simulated restart,
    from the before snapshot); the snapshot receipt's own Undo does the same;
    a bad path or an unknown version is refused before any card.
12. A MISSING RECEIPT STORE does not stop the copy: the blob and the row are
    still saved, `receipt_id` is empty, and the answer says Undo cannot take
    that copy back.
13. THE REGISTRATION: the module is the LAST entry of `_where.SHIPPED` and the
    base's twin is byte-identical.
14. THE READ ROUTES (LM-2A): the two read-only routes answered by
    jarvis_brain_reads.install() - the bounded newest-first journal page (with
    label, size, when, reason and receipt id, and never the per-blob map or a
    file's contents) and the module's own bounded diff passed back unchanged; a
    missing pair, an unknown saved version and a path outside the allowed
    folders are refused in words; ONLY this PC may ask (403 before the journal
    is read, fail-closed with no owner-check module); a foreign origin or no
    token never reaches it; no write or restore function is called and not one
    store byte changes; and the route does not pretend a client-supplied lock
    flag withholds anything - the backend has no such flag, which is the one
    documented gap.
15. THE ONE WRITE ROUTE (LM-2B): POST /api/guardian/restore calls
    restore_version() with the EXISTING undo_action card - an approved restore
    puts exactly the saved bytes back and leaves a NEW receipt whose Undo
    restores what it replaced; a denied/timed-out/unraisable card, an unknown
    saved version or a path outside the allowed folders changes nothing (and a
    denial raises no write at all); a failed save-before-write aborts with the
    file untouched; another device is refused BEFORE the body is read; the
    route is POST-only (a GET goes to the original handler and calls nothing)
    and the HTTP door never names a gate - the module's real jarvis_gate.check()
    is the one asked.
14. THE PRE-WRITE HOOKS (Blueprint B): the approved Obsidian append in
    jarvis_note_capture.py takes the guardian copy of the daily note BEFORE it
    appends a byte, links the answer's `before_sha256`/`snapshot_id`/
    `receipt_id` to the real journal row and receipt, and writes NOTHING when
    the copy is refused or the guardian is absent (fail closed). The vault
    helper in jarvis_notes.py is scoped to the configured vault and fails
    closed with no vault and with no guardian module. jarvis_projects.py's
    Project Mode pointer file is snapshotted before its temp+replace, with the
    snapshot id and receipt id in its existing audit row; a broken guardian
    never blocks Project Mode and the audit row never claims a copy that did
    not happen; the guardian's own symlink refusal still applies.

Every check bites: the module was mutated deliberately (see the branch's
report) and this suite went red for each mutation, so no check is a check on
the constant True.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import gzip
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_file_guardian.py", "jarvis_receipts.py", "jarvis_scrub.py",
                 "jarvis_brain_reads.py")

#: Everything this suite touches lives in here, and the four environment
#: variables below point the real modules at it BEFORE any of them is imported.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-guardian-suite-"))
CONFIG = TMP / "config"
ALLOWED = TMP / "allowed"
HOME_A = TMP / "home-a"
HOME_B = TMP / "home-b"
CONFIG.mkdir(parents=True)
ALLOWED.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["JARVIS_RECEIPTS_DB"] = str(TMP / "receipts.db")
os.environ["OPENJARVIS_HOME"] = str(HOME_A)
os.environ["JARVIS_GUARDIAN_FOLDERS"] = str(ALLOWED)

import _where  # noqa: E402
import jarvis_file_guardian as G  # noqa: E402
import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402
import jarvis_projects as JP  # noqa: E402
import jarvis_receipts as R  # noqa: E402
import jarvis_brain_reads as B  # noqa: E402  (LM-2A's read routes)

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   Scaffolding
# --------------------------------------------------------------------------


class Verdict:
    """What jarvis_gate.check() hands back: allowed, tier, outcome, reason."""

    def __init__(self, allowed, tier, outcome, reason=""):
        self.allowed, self.tier, self.outcome, self.reason = allowed, tier, outcome, reason


class Cards:
    """A stub for the ONE approval card: records every card, answers with what
    this test set. `auto`/`notify` are the outcomes that carry allowed=True
    with nobody in the loop - the case a restore must NOT read as a yes."""

    def __init__(self, answer="approved", tier="ask"):
        self.answer, self.tier, self.cards = answer, tier, []

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": detail, "prompt": prompt})
        if self.answer == "approved":
            return Verdict(True, self.tier, "approved")
        if self.answer == "auto":
            return Verdict(True, self.tier, "auto")
        if self.answer == "notify":
            return Verdict(True, self.tier, "notify")
        return Verdict(False, self.tier, self.answer)


def fresh():
    """Empty stores in a fresh pair of home folders and the scratch allowed folder."""
    shutil.rmtree(HOME_A, ignore_errors=True)
    shutil.rmtree(HOME_B, ignore_errors=True)
    os.environ[G.HOME_ENV] = str(HOME_A)
    os.environ[G.FOLDERS_ENV] = str(ALLOWED)


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, data: bytes) -> Path:
    path = ALLOWED / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def blob_path(home, sha: str) -> Path:
    return Path(home) / G.GUARDIAN_DIR / G.BLOBS_DIR / f"{sha}.gz"


def blob_names(home=None) -> list:
    directory = Path(home or HOME_A) / G.GUARDIAN_DIR / G.BLOBS_DIR
    return sorted(p.name for p in directory.glob("*.gz")) if directory.is_dir() else []


def snapshot(path, **kwargs) -> dict:
    return G.snapshot_before_write(str(path), **kwargs)


@contextlib.contextmanager
def vault_env():
    """A real Obsidian vault folder under this suite's TMP, set as THE vault.

    Set through the module's own environment name and restored afterwards, so
    no other check in this suite sees a vault it did not ask for.
    """
    vault = TMP / "vault"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    saved = os.environ.get(N.OBSIDIAN_VAULT_ENV)
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(vault)
    try:
        yield vault
    finally:
        if saved is None:
            os.environ.pop(N.OBSIDIAN_VAULT_ENV, None)
        else:
            os.environ[N.OBSIDIAN_VAULT_ENV] = saved


def ok(result) -> bool:
    return isinstance(result, dict) and result.get("ok") is True


def refused(result, words: str) -> bool:
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    text = (str(result.get("error") or "") + " " + str(result.get("words") or "")).lower()
    return words.lower() in text


def row_list() -> list:
    return G.rows()


# --------------------------------------------------------------------------
#   1. The contract
# --------------------------------------------------------------------------


def t_the_contract():
    fresh()
    check("the store's quota is 250 MB", G.QUOTA_BYTES == 250 * 1024 * 1024,
          G.QUOTA_BYTES)
    check("the restore asks the EXISTING undo card action, not a new one",
          G.UNDO_ACTION == R.UNDO_ACTION == "undo_action", G.UNDO_ACTION)
    check("the two receipt tool names are distinct and non-empty",
          bool(G.TOOL_SNAPSHOT) and bool(G.TOOL_RESTORE)
          and G.TOOL_SNAPSHOT != G.TOOL_RESTORE,
          (G.TOOL_SNAPSHOT, G.TOOL_RESTORE))

    path = write("contract.txt", b"the file as it is now\n")
    before = path.read_bytes()
    result = snapshot(path, reason="a contract check")
    check("a snapshot answers the documented keys",
          set(result) >= {"ok", "path", "before_sha256", "size", "stored",
                          "receipt_id", "pruned", "prune_words", "words"}, result)
    check("a snapshot changes nothing in the file it copies",
          path.read_bytes() == before,
          "the file's bytes were changed by taking the copy")
    check("a snapshot never raises: a missing file is a plain answer",
          refused(snapshot(ALLOWED / "definitely-not-here.txt"), "no file at that path"))

    f2 = write("contract2.txt", b"version one\n")
    saved = snapshot(f2)
    f2.write_bytes(b"version two\n")
    diff = G.diff_versions(str(f2), saved["before_sha256"])
    check("a diff answers the documented keys",
          set(diff) >= {"ok", "path", "before_sha256", "after_sha256", "diff",
                        "truncated", "binary", "same", "words"}, diff)

    cards = Cards("denied")
    restore = G.restore_version(str(f2), saved["before_sha256"], gate=cards.gate)
    check("a restore answers the documented keys",
          set(restore) >= {"ok", "refused", "gated", "path", "error", "words"},
          restore)


# --------------------------------------------------------------------------
#   2. The copy is content-addressed, and recorded with the real receipts module
# --------------------------------------------------------------------------


def t_the_saved_version_is_the_current_bytes():
    fresh()
    body = b"note title\n\nfirst line\nsecond line\n"
    path = write("note.md", body)
    result = snapshot(path, reason="before the note tool writes")
    saved = sha256_of(body)

    check("the snapshot succeeds", ok(result), result)
    check("the version is named by the sha256 of the CURRENT bytes",
          result.get("before_sha256") == saved, result.get("before_sha256"))
    check("the row reports the file's size", result.get("size") == len(body),
          result.get("size"))
    packed = blob_path(HOME_A, saved)
    check("the copy is stored under $OPENJARVIS_HOME/guardian/blobs/<sha256>.gz",
          packed.is_file(), str(packed))
    check("the copy is a real gzip file",
          packed.is_file() and packed.read_bytes()[:2] == b"\x1f\x8b")
    check("the copy decompresses to the file's exact bytes",
          packed.is_file() and gzip.decompress(packed.read_bytes()) == body)

    rows = row_list()
    check("one journal row was appended", len(rows) == 1, rows)
    row = rows[0] if rows else {}
    check("the row keeps the timestamp, path, sha256, size and reason",
          isinstance(row.get("timestamp"), float)
          and row.get("path") == os.path.realpath(str(path))
          and row.get("before_sha256") == saved
          and row.get("size") == len(body)
          and row.get("reason") == "before the note tool writes", row)
    receipt_id = str(result.get("receipt_id") or "")
    check("the row carries the receipt id", row.get("receipt_id") == receipt_id
          and receipt_id.startswith("rc"), receipt_id)

    receipt = R.get(receipt_id) if receipt_id else None
    check("the receipt is a real jarvis_receipts row, under this module's tool name",
          receipt is not None and receipt.get("tool_name") == G.TOOL_SNAPSHOT,
          receipt and receipt.get("tool_name"))
    before = (receipt or {}).get("before") or {}
    check("the receipt's before snapshot names the saved version",
          before.get("sha256") == saved, before)
    check("the receipt carries an opaque copy id, not the file's path",
          isinstance(before.get("copy_id"), str) and before.get("copy_id").startswith("gc")
          and "path" not in before, before)
    check("the answer carries the same opaque copy id (snapshot_id) the row and receipt use",
          result.get("snapshot_id") == before.get("copy_id") == row.get("copy_id"),
          (result.get("snapshot_id"), before.get("copy_id"), row.get("copy_id")))
    check("neither the file's words nor its full path are in the receipt",
          json.dumps(receipt or {}) and str(path) not in json.dumps(receipt or {})
          and "first line" not in json.dumps(receipt or {}), receipt)
    check("the answer says one Undo puts it back",
          "undo" in str(result.get("words", "")).lower(), result.get("words"))


# --------------------------------------------------------------------------
#   3. Dedup: content-addressed, so the same bytes cost one copy
# --------------------------------------------------------------------------


def t_the_same_bytes_are_stored_once():
    fresh()
    body = b"the same bytes, saved more than once\n"
    path = write("same.txt", body)
    first = snapshot(path)
    second = snapshot(path)
    other = write("elsewhere.txt", body)
    third = snapshot(other)

    check("the first copy is stored", first.get("stored") is True, first)
    check("the same bytes again are NOT stored again", second.get("stored") is False, second)
    check("the same bytes in a different file are NOT stored again",
          third.get("stored") is False, third)
    check("three snapshots of identical bytes leave exactly ONE blob",
          len(blob_names()) == 1, blob_names())
    check("... but all three snapshots are recorded", len(row_list()) == 3, row_list())

    changed = b"a different version of the same file\n"
    path.write_bytes(changed)
    fourth = snapshot(path)
    check("a changed file gets its own copy", fourth.get("stored") is True, fourth)
    check("... and the store now holds exactly two blobs", len(blob_names()) == 2,
          blob_names())
    check("... named by the two sha256s",
          sorted(blob_names()) == sorted([sha256_of(body) + ".gz",
                                          sha256_of(changed) + ".gz"]),
          blob_names())


# --------------------------------------------------------------------------
#   4. The diff
# --------------------------------------------------------------------------


def t_the_diff_shows_what_changed():
    fresh()
    path = write("draft.md", b"alpha\nbeta\ngamma\n")
    old = b"alpha\nbeta\ngamma\n"
    saved = snapshot(path)
    new = b"alpha\nBETA\ngamma\ndelta\n"
    path.write_bytes(new)

    diff = G.diff_versions(str(path), saved["before_sha256"])
    check("a diff of a changed file succeeds", ok(diff), diff)
    check("the removed line is in the diff", "-beta" in diff.get("diff", ""),
          diff.get("diff"))
    check("the added line is in the diff", "+BETA" in diff.get("diff", ""),
          diff.get("diff"))
    check("the diff has a hunk header", "@@" in diff.get("diff", ""), diff.get("diff"))
    check("the diff names both sides' hashes",
          diff.get("before_sha256") == sha256_of(old)
          and diff.get("after_sha256") == sha256_of(new), diff)
    check("a changed file is not reported as the same", diff.get("same") is False)

    same_saved = snapshot(path)
    same = G.diff_versions(str(path), same_saved["before_sha256"])
    check("a diff against the file's own hash is `same`, with nothing to show",
          ok(same) and same.get("same") is True and same.get("diff") == "", same)

    unknown = G.diff_versions(str(path), "a" * 64)
    check("an unknown saved version is refused in plain words",
          refused(unknown, "not in the time machine"), unknown)

    path.write_bytes(b"\x00\x01a binary file\x00")
    binary = G.diff_versions(str(path), saved["before_sha256"])
    check("a binary pair answers binary, with no line diff",
          ok(binary) and binary.get("binary") is True and binary.get("diff") == "",
          binary)
    check("a binary answer says the version can still be put back",
          "put back" in str(binary.get("words", "")).lower(), binary.get("words"))


def t_the_diff_is_bounded():
    fresh()
    old_lines = "".join(f"line {i:05d} original text\n" for i in range(4000))
    new_lines = "".join(f"line {i:05d} changed text here\n" for i in range(4000))
    path = write("large.txt", old_lines.encode("utf-8"))
    saved = snapshot(path)
    path.write_bytes(new_lines.encode("utf-8"))

    diff = G.diff_versions(str(path), saved["before_sha256"])
    check("a large difference is marked truncated", diff.get("truncated") is True, diff)
    check("the returned difference is bounded by MAX_DIFF_BYTES",
          len(diff.get("diff", "")) <= G.MAX_DIFF_BYTES + 100,
          len(diff.get("diff", "")))
    check("the bounded answer says the rest is not shown",
          "not shown" in diff.get("diff", "") or "shown" in str(diff.get("words")),
          diff.get("words"))

    import difflib
    whole = "\n".join(difflib.unified_diff(
        old_lines.splitlines(), new_lines.splitlines(),
        fromfile="before", tofile="now", lineterm=""))
    check("... and it really is shorter than the whole difference",
          len(diff.get("diff", "")) < len(whole),
          (len(diff.get("diff", "")), len(whole)))


# --------------------------------------------------------------------------
#   5. The quota: oldest UNPINNED first, and a pinned version is never removed
# --------------------------------------------------------------------------


def t_the_quota_removes_the_oldest_unpinned_versions():
    fresh()
    real_quota = G.QUOTA_BYTES
    G.QUOTA_BYTES = 800
    try:
        a = write("a.bin", os.urandom(300))
        sa = snapshot(a, now=1000.0)
        b = write("b.bin", os.urandom(300))
        sb = snapshot(b, now=1001.0)
        c = write("c.bin", os.urandom(300))
        sc = snapshot(c, now=1002.0)

        check("three incompressible versions of ~300 bytes overrun an 800-byte limit",
              3 * 300 > G.QUOTA_BYTES)
        check("the oldest version was removed", not blob_path(HOME_A, sa["before_sha256"]).is_file())
        check("the next two versions were kept",
              blob_path(HOME_A, sb["before_sha256"]).is_file()
              and blob_path(HOME_A, sc["before_sha256"]).is_file(), blob_names())
        check("the store is back under the quota",
              G.usage().get("blob_bytes", 10 ** 9) <= G.QUOTA_BYTES, G.usage())
        check("the answer names what was pruned",
              [p.get("sha256") for p in sc.get("pruned", [])] == [sa["before_sha256"]],
              sc.get("pruned"))
        check("the pruning is reported in plain words",
              "removed" in str(sc.get("prune_words", "")).lower()
              and "old version" in str(sc.get("prune_words", "")).lower(),
              sc.get("prune_words"))
        check("a pruned version can no longer be shown as a diff",
              refused(G.diff_versions(str(a), sa["before_sha256"]), "not in the time machine"))

        check("an under-quota store loses nothing",
              G.prune().get("pruned") == []
              and "nothing needed removing" in str(G.prune().get("words", "")).lower(),
              G.prune())
    finally:
        G.QUOTA_BYTES = real_quota
    check("the quota constant is back to 250 MB after the check",
          G.QUOTA_BYTES == 250 * 1024 * 1024, G.QUOTA_BYTES)


def t_a_pinned_version_is_never_removed():
    fresh()
    real_quota = G.QUOTA_BYTES
    G.QUOTA_BYTES = 800
    try:
        a = write("a.bin", os.urandom(300))
        sa = snapshot(a, now=1000.0)
        pinned = G.pin(sa["before_sha256"])
        check("a version can be pinned", ok(pinned), pinned)
        check("the pin is remembered",
              G.pinned() == [sa["before_sha256"]], G.pinned())
        check("the pin is written beside the store",
              (Path(HOME_A) / G.GUARDIAN_DIR / G.PINS_NAME).is_file())

        b = write("b.bin", os.urandom(300))
        sb = snapshot(b, now=1001.0)
        c = write("c.bin", os.urandom(300))
        sc = snapshot(c, now=1002.0)

        check("the pinned version survived over-quota pruning",
              blob_path(HOME_A, sa["before_sha256"]).is_file(), blob_names())
        check("the OLDEST UNPINNED version was the one removed",
              not blob_path(HOME_A, sb["before_sha256"]).is_file(), blob_names())
        check("the newest version was kept",
              blob_path(HOME_A, sc["before_sha256"]).is_file(), blob_names())
        check("the pinned version can still be shown",
              ok(G.diff_versions(str(a), sa["before_sha256"])), a)
        check("the pruning answer says the pinned version was kept",
              "pinned" in str(sc.get("prune_words", "")).lower(), sc.get("prune_words"))
        check("the second version's pruning named the unpinned one",
              [p.get("sha256") for p in sb.get("pruned", [])] == [sa["before_sha256"]]
              or [p.get("sha256") for p in sc.get("pruned", [])] == [sb["before_sha256"]],
              (sb.get("pruned"), sc.get("pruned")))

        unpinned = G.unpin(sa["before_sha256"])
        check("a version can be unpinned", ok(unpinned) and G.pinned() == [], unpinned)

        # Every version pinned: nothing may be removed, even over the quota.
        fresh()
        G.QUOTA_BYTES = 500
        d = write("d.bin", os.urandom(300))
        sd = snapshot(d, now=1000.0)
        G.pin(sd["before_sha256"])
        e = write("e.bin", os.urandom(300))
        se = snapshot(e, now=1001.0)
        G.pin(se["before_sha256"])
        pruned = G.prune()
        check("every version pinned: pruning removes NOTHING",
              pruned.get("pruned") == [] and blob_path(HOME_A, sd["before_sha256"]).is_file()
              and blob_path(HOME_A, se["before_sha256"]).is_file(), pruned)
        check("... and the answer says a pinned version is never removed",
              "pinned" in str(pruned.get("words", "")).lower()
              and "never removed" in str(pruned.get("words", "")).lower(),
              pruned.get("words"))

        # A pins file that cannot be read must STOP the pruning, not be read as
        # "nothing is pinned" - that would delete a copy the owner pinned.
        G.pins_path().write_text("this is not the pins file any more", encoding="utf-8")
        pruned = G.prune()
        check("a damaged pins file stops pruning instead of guessing",
              pruned.get("pruned") == []
              and blob_path(HOME_A, sd["before_sha256"]).is_file()
              and blob_path(HOME_A, se["before_sha256"]).is_file(), pruned)
        check("... and says in plain words why nothing was removed",
              "could not be read" in str(pruned.get("words", "")).lower()
              and "never" in str(pruned.get("words", "")).lower(), pruned.get("words"))
    finally:
        G.QUOTA_BYTES = real_quota


# --------------------------------------------------------------------------
#   6. The refusals
# --------------------------------------------------------------------------


def t_a_link_is_refused():
    fresh()
    target = write("target.txt", b"the real file\n")
    link = ALLOWED / "link.txt"
    try:
        os.symlink(str(target), str(link))
    except OSError as exc:
        skip(f"a symlink cannot be made on this machine ({type(exc).__name__}), so the "
             f"link refusal was not driven")
        return
    result = snapshot(link)
    check("a symlink is refused in plain words",
          refused(result, "link"), result)
    check("... the refusal says a link can point somewhere else",
          "point somewhere else" in str(result.get("error", "")), result.get("error"))
    check("... and nothing was copied for it", blob_names() == [] and row_list() == [],
          (blob_names(), row_list()))
    check("... and the target file is untouched",
          target.read_bytes() == b"the real file\n")

    saved = snapshot(target)
    cards = Cards("approved")
    restored = G.restore_version(str(link), saved["before_sha256"], gate=cards.gate)
    check("a restore through a link is refused too",
          refused(restored, "link") and target.read_bytes() == b"the real file\n", restored)
    check("... and no card was raised for it", cards.cards == [], cards.cards)


def t_a_path_outside_the_allowed_folders_is_refused():
    fresh()
    outside = TMP / "outside"
    outside.mkdir(exist_ok=True)
    stranger = outside / "stranger.txt"
    stranger.write_bytes(b"not Jarvis's file\n")
    result = snapshot(stranger)
    check("a file outside every allowed folder is refused in plain words",
          refused(result, "not inside a folder"), result)
    check("... nothing was copied and no row was written",
          blob_names() == [] and row_list() == [], (blob_names(), row_list()))
    check("... and the outside file is untouched",
          stranger.read_bytes() == b"not Jarvis's file\n")

    cards = Cards("approved")
    restored = G.restore_version(str(stranger), "a" * 64, gate=cards.gate)
    check("a restore outside the allowed folders is refused",
          refused(restored, "not inside a folder")
          and stranger.read_bytes() == b"not Jarvis's file\n", restored)
    check("... and no card was raised for it", cards.cards == [])

    check("with no allowed folder at all, every path is refused (fail closed)",
          refused(snapshot(str(stranger), roots=[]), "no folder is on Jarvis's list"))


def t_a_folder_or_a_missing_file_is_refused():
    fresh()
    folder = ALLOWED / "a-folder"
    folder.mkdir(exist_ok=True)
    result = snapshot(folder)
    check("a folder is refused in plain words, not copied",
          refused(result, "folder, not a file"), result)
    check("a missing file is refused in plain words",
          refused(snapshot(ALLOWED / "never-here.txt"), "no file at that path"))
    check("a path that is not text is refused in plain words",
          refused(G.snapshot_before_write(42), "say which file"), G.snapshot_before_write(42))
    check("the per-file limit is not larger than the whole store's quota",
          G.MAX_FILE_BYTES <= G.QUOTA_BYTES, (G.MAX_FILE_BYTES, G.QUOTA_BYTES))


def t_the_size_ceiling_is_checked_before_any_read():
    """A file over the ceiling is refused by its SIZE alone, before any read.

    This is the large-file guard: the size is checked with `getsize` before a
    byte of the file is pulled into memory, so a file that could not be
    copied cannot first be read (or compressed) on the way to being refused.
    The refusal is machine-readable as `file_too_large_for_guardian` and it
    carries both numbers, because the caller has to say which limit it broke.
    """
    fresh()
    check("MAX_FILE_BYTES is the blueprint's 25 MiB N_placeholder",
          G.MAX_FILE_BYTES == 25 * 1024 * 1024, G.MAX_FILE_BYTES)

    big = ALLOWED / "too-big.bin"
    with open(big, "wb") as handle:
        handle.truncate(G.MAX_FILE_BYTES + 1)
    real_read = G._read_bytes
    reads = []

    def spy(real):
        reads.append(real)
        return real_read(real)

    G._read_bytes = spy
    try:
        oversized = snapshot(big)
    finally:
        G._read_bytes = real_read
    check("a file above the per-file limit is refused with error "
          "file_too_large_for_guardian",
          isinstance(oversized, dict) and oversized.get("ok") is False
          and oversized.get("error") == "file_too_large_for_guardian", oversized)
    check("... and the refusal carries the file's real size and the limit it broke",
          oversized.get("size_bytes") == G.MAX_FILE_BYTES + 1
          and oversized.get("max_file_bytes") == G.MAX_FILE_BYTES, oversized)
    check("... and the file's bytes were NEVER read (the size is checked first)",
          reads == [], reads)
    check("... and nothing was copied or recorded for it",
          blob_names() == [] and row_list() == [], (blob_names(), row_list()))
    check("... and the oversized file itself is untouched",
          big.is_file() and big.stat().st_size == G.MAX_FILE_BYTES + 1)
    try:
        big.unlink()
    except OSError:
        pass

    check("a caller can lower the ceiling for its own call",
          snapshot(write("small.txt", b"0123456789"), max_file_bytes=5).get("error")
          == "file_too_large_for_guardian",
          snapshot(ALLOWED / "small.txt", max_file_bytes=5))
    at_limit = snapshot(ALLOWED / "small.txt", max_file_bytes=10)
    check("... and a file exactly AT the caller's limit is copied",
          ok(at_limit) and at_limit.get("size") == 10, at_limit)
    fallback = snapshot(ALLOWED / "small.txt", max_file_bytes="not a number")
    check("... and a nonsense limit falls back to the real ceiling, never to refusing "
          "everything",
          ok(fallback) and fallback.get("before_sha256") == sha256_of(b"0123456789"),
          fallback)

    grows = write("grows.txt", b"short now\n")
    grown = b"x" * (G.MAX_FILE_BYTES + 7)
    real_read = G._read_bytes
    G._read_bytes = lambda _real: grown
    try:
        result = snapshot(grows)
    finally:
        G._read_bytes = real_read
    check("a file that GROWS between getsize and the read is refused by the read's own "
          "size, before it is hashed or stored",
          isinstance(result, dict) and result.get("ok") is False
          and result.get("error") == "file_too_large_for_guardian"
          and result.get("size_bytes") == len(grown), result)
    check("... and nothing was copied or recorded for the grown file",
          sha256_of(grown) + ".gz" not in blob_names()
          and all(row.get("before_sha256") != sha256_of(grown) for row in row_list()),
          (blob_names(), row_list()))


def t_an_unreadable_file_is_refused():
    fresh()
    path = write("locked.txt", b"cannot be read right now\n")
    real_read = G._read_bytes

    def boom(_real):
        raise PermissionError("denied")

    G._read_bytes = boom
    try:
        result = snapshot(path)
    finally:
        G._read_bytes = real_read
    check("a file whose read fails is refused in plain words",
          refused(result, "could not be read") and "PermissionError" in str(result),
          result)
    check("... and nothing was copied for it", blob_names() == [] and row_list() == [])
    check("... and the read failure did not escape as a traceback",
          isinstance(result, dict) and result.get("ok") is False)


# --------------------------------------------------------------------------
#   7. The owner's own lists make a folder allowed
# --------------------------------------------------------------------------


def t_the_allowed_folders_come_from_the_owners_lists():
    fresh()
    import jarvis_documents as D
    kept_env = os.environ.pop(G.FOLDERS_ENV, None)
    kept_vault = os.environ.get("JARVIS_OBSIDIAN_VAULT")
    try:
        D._save([{"path": str(ALLOWED), "added": 1.0}])
        roots = [os.path.realpath(r) for r in G.allowed_roots()]
        check("a folder on the owner's \"Folders Jarvis may look in\" list is allowed",
              os.path.realpath(str(ALLOWED)) in roots, roots)
        listed = write("listed.txt", b"a file in a listed folder\n")
        check("... and a file in it can be snapshotted with no extra argument",
              ok(snapshot(listed)), snapshot(listed))

        D._save([])
        vault = TMP / "vault"
        (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
        os.environ["JARVIS_OBSIDIAN_VAULT"] = str(vault)
        try:
            roots = [os.path.realpath(r) for r in G.allowed_roots()]
            check("the configured Obsidian vault is an allowed folder",
                  os.path.realpath(str(vault)) in roots, roots)
            note = vault / "a-note.md"
            note.write_bytes(b"# a note\n")
            result = snapshot(note)
            check("... and a file in the vault can be snapshotted",
                  ok(result), result)
            check("... with the copy stored in the same time machine",
                  ok(result) and blob_path(HOME_A, result["before_sha256"]).is_file())
        finally:
            if kept_vault is None:
                os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
            else:
                os.environ["JARVIS_OBSIDIAN_VAULT"] = kept_vault
    finally:
        D._save([])
        if kept_env is not None:
            os.environ[G.FOLDERS_ENV] = kept_env
        else:
            os.environ.pop(G.FOLDERS_ENV, None)


# --------------------------------------------------------------------------
#   8. The home folder
# --------------------------------------------------------------------------


def t_the_home_folder_is_honoured():
    fresh()
    check("OPENJARVIS_HOME is where the store lives",
          os.path.realpath(str(G.home_dir())) == os.path.realpath(str(HOME_A)),
          G.home_dir())
    os.environ[G.HOME_ENV] = str(HOME_B)
    path = write("home.txt", b"a version in the second home\n")
    result = snapshot(path)
    check("a snapshot in the second home succeeds", ok(result), result)
    check("the copy lands under the second $OPENJARVIS_HOME",
          ok(result) and blob_path(HOME_B, result["before_sha256"]).is_file()
          and not blob_path(HOME_A, result["before_sha256"]).is_file(),
          (blob_path(HOME_B, result["before_sha256"]),
           blob_path(HOME_A, result["before_sha256"])))
    check("the two homes are separate journals",
          len(row_list()) == 1 and row_list()[0].get("path") == os.path.realpath(str(path)),
          row_list())

    del os.environ[G.HOME_ENV]
    try:
        check("with OPENJARVIS_HOME unset the settings-folder rule is followed exactly",
              os.path.realpath(str(G.home_dir())) == os.path.realpath(str(CONFIG)),
              (G.home_dir(), CONFIG))
        check("... and the answer is never a guess at ~/.openjarvis",
              os.path.realpath(str(G.home_dir()))
              != os.path.realpath(os.path.expanduser("~/.openjarvis")), G.home_dir())
    finally:
        os.environ[G.HOME_ENV] = str(HOME_A)


# --------------------------------------------------------------------------
#   9. The gate: a restore happens on a person's yes and nothing less
# --------------------------------------------------------------------------


def t_the_restore_needs_the_gate():
    fresh()
    path = write("gated.txt", b"the first version\n")
    saved = snapshot(path)
    path.write_bytes(b"the second version\n")

    denied = Cards("denied")
    result = G.restore_version(str(path), saved["before_sha256"], gate=denied.gate)
    check("a denied card refuses the restore", refused(result, "turned down"), result)
    check("... and the file is byte-identical to what it was",
          path.read_bytes() == b"the second version\n")
    check("... and exactly ONE card was raised", len(denied.cards) == 1, denied.cards)
    card = denied.cards[0] if denied.cards else {}
    check("the card is the EXISTING undo action",
          card.get("action") == R.UNDO_ACTION, card.get("action"))
    prompt = str(card.get("prompt") or "")
    check("the card names the file and says refusing costs nothing",
          "gated.txt" in prompt and "nothing changes" in prompt.lower(), prompt)
    check("the card carries no file words and no full path",
          "the second version" not in prompt and str(path) not in prompt, prompt)

    timed = Cards("timed_out")
    result = G.restore_version(str(path), saved["before_sha256"], gate=timed.gate)
    check("a timed-out card refuses the restore",
          refused(result, "nobody answered") and path.read_bytes() == b"the second version\n",
          result)

    def raising(action, detail, prompt):
        raise RuntimeError("no gate today")

    result = G.restore_version(str(path), saved["before_sha256"], gate=raising)
    check("a card that cannot be raised refuses the restore",
          refused(result, "could not be raised")
          and path.read_bytes() == b"the second version\n", result)

    auto = Cards("auto")
    result = G.restore_version(str(path), saved["before_sha256"], gate=auto.gate)
    check("allowed=True at tier ask with an `auto` outcome is NOT a person's yes",
          refused(result, "not approved") and path.read_bytes() == b"the second version\n",
          result)
    notify = Cards("notify")
    result = G.restore_version(str(path), saved["before_sha256"], gate=notify.gate)
    check("allowed=True at tier ask with a `notify` outcome is NOT a person's yes either",
          refused(result, "not approved") and path.read_bytes() == b"the second version\n",
          result)

    # No explicit gate: the module's own jarvis_gate path must be the one asked.
    asked = []
    real_gate = G._gate

    def fake_gate(action, detail, prompt):
        asked.append((action, detail, prompt))
        return Verdict(False, "ask", "denied")

    G._gate = fake_gate
    try:
        result = G.restore_version(str(path), saved["before_sha256"])
    finally:
        G._gate = real_gate
    check("with no gate passed, the real jarvis_gate path is consulted",
          len(asked) == 1 and asked[0][0] == R.UNDO_ACTION, asked)
    check("... and its refusal changes nothing",
          refused(result, "turned down") and path.read_bytes() == b"the second version\n")

    params = list(inspect.signature(G.restore_version).parameters)
    check("a restore has a gate argument", "gate" in params, params)
    check("... and no argument that could skip it",
          not [p for p in params if p in ("approved", "force", "yes", "skip_gate",
                                          "silent", "skip", "no_gate")], params)


# --------------------------------------------------------------------------
#   10. The restore itself, and the Undo receipt it leaves behind
# --------------------------------------------------------------------------


def t_the_restore_puts_the_bytes_back_and_leaves_an_undo():
    fresh()
    original = b"the first version\nwith two lines\n"
    second = b"the second version\n"
    path = write("restore.txt", original)
    saved = snapshot(path)
    snapshot_sha = saved["before_sha256"]
    path.write_bytes(second)

    cards = Cards("approved")
    result = G.restore_version(str(path), snapshot_sha, gate=cards.gate)
    check("an approved restore succeeds", ok(result), result)
    check("... and the file is byte-for-byte the saved version",
          path.read_bytes() == original, path.read_bytes())
    check("... and the answer names what it put back and what it replaced",
          result.get("restored_sha256") == snapshot_sha
          and result.get("before_sha256") == sha256_of(second), result)
    receipt_id = str(result.get("receipt_id") or "")
    check("... and it left a NEW receipt that is not the snapshot's",
          receipt_id.startswith("rc") and receipt_id != saved.get("receipt_id"),
          (receipt_id, saved.get("receipt_id")))
    receipt = R.get(receipt_id) if receipt_id else None
    check("the new receipt is a restore receipt whose before is what it replaced",
          receipt is not None and receipt.get("tool_name") == G.TOOL_RESTORE
          and ((receipt.get("before") or {}).get("sha256")) == sha256_of(second), receipt)
    check("the restore raised exactly ONE card, and it was approved once",
          len(cards.cards) == 1 and cards.cards[0].get("action") == R.UNDO_ACTION,
          cards.cards)
    rows = row_list()
    check("the restore was recorded in the journal too",
          any(r.get("before_sha256") == sha256_of(second) for r in rows), rows)
    check("the answer says one Undo puts the newer version back",
          "undo" in str(result.get("words", "")).lower(), result.get("words"))

    undo = R.undo(receipt_id)
    check("the EXISTING Undo button reverses the restore",
          undo.get("ok") is True and path.read_bytes() == second,
          (undo, path.read_bytes()))
    check("... through the same code that made the restore, and it says so",
          undo.get("path") == "callable", undo)

    # After a restart the live callable is gone: the before snapshot and the
    # registered restorer are what is left, exactly as jarvis_receipts.py says.
    R._reset_for_tests()
    R._RESTORERS.clear()
    path.write_bytes(second)
    undo_snapshot = R.undo(saved["receipt_id"])
    check("the SNAPSHOT receipt's Undo puts the original back after a restart",
          undo_snapshot.get("ok") is True and path.read_bytes() == original,
          (undo_snapshot, path.read_bytes()))
    check("... from the before snapshot, not a live callable",
          undo_snapshot.get("path") == "snapshot", undo_snapshot)

    # And a restore receipt survives a restart the same way.
    second_restore = G.restore_version(str(path), sha256_of(second), gate=Cards("approved").gate)
    check("a second restore can put the newer version back",
          ok(second_restore) and path.read_bytes() == second, second_restore)
    R._reset_for_tests()
    R._RESTORERS.clear()
    undo_restore = R.undo(second_restore["receipt_id"])
    check("the RESTORE receipt's Undo puts the version it replaced back after a restart",
          undo_restore.get("ok") is True and path.read_bytes() == original,
          (undo_restore, path.read_bytes()))


def t_a_restore_of_a_version_it_does_not_have_is_refused():
    fresh()
    path = write("nover.txt", b"a version nobody saved\n")
    cards = Cards("approved")
    result = G.restore_version(str(path), "a" * 64, gate=cards.gate)
    check("a restore of an unknown saved version is refused",
          refused(result, "not in the time machine"), result)
    check("... before any card is raised", cards.cards == [], cards.cards)
    check("... and the file is untouched",
          path.read_bytes() == b"a version nobody saved\n")
    result = G.restore_version(str(path), "not-a-sha", gate=cards.gate)
    check("a restore with a nonsense version name is refused",
          refused(result, "not a saved version"), result)


def t_a_restore_that_changes_nothing_raises_no_card():
    fresh()
    path = write("already.txt", b"already this version\n")
    saved = snapshot(path)
    cards = Cards("approved")
    result = G.restore_version(str(path), saved["before_sha256"], gate=cards.gate)
    check("restoring the version a file already is, changes nothing",
          ok(result) and result.get("same") is True
          and path.read_bytes() == b"already this version\n", result)
    check("... and asks nobody, because there is nothing to approve", cards.cards == [],
          cards.cards)
    check("... and leaves no new receipt", result.get("receipt_id") == "", result)


# --------------------------------------------------------------------------
#   11. A missing receipt store still keeps the copy
# --------------------------------------------------------------------------


def t_a_missing_receipt_store_does_not_stop_the_copy():
    fresh()
    path = write("noreceipt.txt", b"kept even without receipts\n")
    real = G._receipts
    G._receipts = lambda: None
    try:
        result = snapshot(path)
    finally:
        G._receipts = real
    check("the copy is still saved when the receipt store is unavailable",
          ok(result) and blob_path(HOME_A, result["before_sha256"]).is_file(), result)
    check("... with an empty receipt id", result.get("receipt_id") == "", result)
    check("... and an answer that says Undo cannot take it back",
          "undo cannot" in str(result.get("words", "")).lower(), result.get("words"))
    check("... and the journal row is still written, without a receipt id",
          len(row_list()) == 1 and row_list()[0].get("receipt_id") == "", row_list())


# --------------------------------------------------------------------------
#   12. The pre-write hooks (Blueprint B): the approved vault append, and
#       Project Mode's pointer file
# --------------------------------------------------------------------------


def t_the_approved_vault_append_snapshots_the_note_first():
    """A real approved append through jarvis_note_capture.py, driven for real.

    The daily note is appended to only after the guardian has stored its
    previous bytes, and the answer links that copy's hash, its opaque snapshot
    id and its receipt id - so the append can be undone with the guard, not
    just with the writer's own read-back.
    """
    fresh()
    with vault_env() as vault:
        plan = NC.plan("obsidian", "a note from the capture",
                       now=dt.datetime(2026, 10, 17, 12, 0))
        path = Path(plan.file)
        check("the note plan names today's daily note inside the vault",
              plan.target == "obsidian" and plan.reason_empty == ""
              and G._inside(str(vault), os.path.realpath(str(path))), plan)
        path.parent.mkdir(parents=True, exist_ok=True)
        old = b"- earlier entry\n"
        path.write_bytes(old)
        result = NC.run(plan, approved=True)
        appended = path.read_bytes()

    check("the approved append succeeds", result.get("ok") is True, result)
    check("... and it only ADDS: the earlier bytes are still there, byte for byte",
          appended.startswith(old) and len(appended) > len(old), appended[:80])
    sha_old = sha256_of(old)
    check("the answer links the copy of the OLD bytes (before_sha256)",
          result.get("before_sha256") == sha_old, result.get("before_sha256"))
    blob = blob_path(HOME_A, sha_old)
    check("the guardian stored the PREVIOUS bytes before the append",
          blob.is_file() and gzip.decompress(blob.read_bytes()) == old, str(blob))
    row = next((r for r in row_list()
                if r.get("copy_id") == result.get("snapshot_id")), {})
    check("the answer's snapshot_id names a real journal row for that hash",
          row.get("before_sha256") == sha_old, (result.get("snapshot_id"), row))
    receipt = R.get(str(result.get("receipt_id") or ""))
    check("the answer's receipt_id is a real guardian snapshot receipt",
          receipt is not None and receipt.get("tool_name") == G.TOOL_SNAPSHOT,
          receipt)
    check("... so the copy comes BEFORE the append, never after it (the append's "
          "own bytes got no snapshot)",
          not blob_path(HOME_A, sha256_of(appended)).exists(), blob_names())


def t_an_append_whose_copy_is_refused_writes_nothing():
    """No copy, no append: a refusal is handed to the owner in plain words.

    The guardian's refusal is the writer's answer too - the note is not
    touched - and the structured reason (the large-file one, or an absent
    guardian) is passed back rather than swallowed.
    """
    fresh()
    with vault_env():
        plan = NC.plan("obsidian", "a note that must not land",
                       now=dt.datetime(2026, 10, 18, 12, 0))
        path = Path(plan.file)
        path.parent.mkdir(parents=True, exist_ok=True)
        old = b"- keep me exactly\n"
        path.write_bytes(old)
        real = NC._snapshot_daily_note

        NC._snapshot_daily_note = lambda _path: {
            "ok": False, "error": "file_too_large_for_guardian",
            "size_bytes": 26 * 1024 * 1024, "max_file_bytes": G.MAX_FILE_BYTES}
        try:
            refused = NC.run(plan, approved=True)
        finally:
            NC._snapshot_daily_note = real
        check("an append whose guardian copy is refused returns a plain refusal",
              refused.get("ok") is False
              and "could not be copied first" in str(refused.get("reason")), refused)
        check("... and writes NOTHING: the daily note is exactly the old bytes",
              path.read_bytes() == old, path.read_bytes()[:80])
        check("... and the structured guardian reason is handed back, not swallowed",
              refused.get("snapshot_error") == "file_too_large_for_guardian",
              refused)

        NC._snapshot_daily_note = lambda _path: {
            "ok": False, "error": "guardian_unavailable",
            "words": "the time machine is not on this backend"}
        try:
            absent = NC.run(plan, approved=True)
        finally:
            NC._snapshot_daily_note = real
        check("with the guardian absent the append is refused too (fail closed)",
              absent.get("ok") is False and path.read_bytes() == old, absent)

        new_day = NC.plan("obsidian", "the first note of the day",
                          now=dt.datetime(2026, 10, 19, 12, 0))
        new_path = Path(new_day.file)
        made = NC.run(new_day, approved=True)
    check("a daily note that does not exist yet is still created (nothing was there "
          "to lose, so no copy is needed)",
          made.get("ok") is True and new_path.is_file()
          and made.get("before_sha256") == "", made)


def t_the_vault_helper_is_scoped_to_the_configured_vault():
    """jarvis_notes.py stays read-only, but the one door a writer uses is guarded."""
    fresh()
    with vault_env() as vault:
        inside = vault / "inside.md"
        inside.write_bytes(b"inside the vault\n")
        outside_dir = TMP / "not-the-vault"
        outside_dir.mkdir(exist_ok=True)
        outside = outside_dir / "outside.md"
        outside.write_bytes(b"outside the vault\n")

        out = N.snapshot_vault_before_write(outside)
        check("the notes helper refuses a file outside the configured vault",
              out.get("ok") is False and "not inside a folder" in str(out.get("error")),
              out)
        check("... and nothing was copied for it",
              blob_names() == [] and row_list() == [], (blob_names(), row_list()))
        good = N.snapshot_vault_before_write(inside, reason="a test of the door")
        check("... and copies a file inside the vault, through the REAL guardian",
              good.get("ok") is True
              and good.get("before_sha256") == sha256_of(b"inside the vault\n"), good)

        saved = os.environ.pop(N.OBSIDIAN_VAULT_ENV, None)
        try:
            no_vault = N.snapshot_vault_before_write(inside)
        finally:
            if saved is not None:
                os.environ[N.OBSIDIAN_VAULT_ENV] = saved
    check("with NO vault configured the helper fails closed (no folder is on the list)",
          no_vault.get("ok") is False
          and "no folder is on jarvis's list" in str(no_vault.get("error")).lower(),
          no_vault)

    real_module = sys.modules.get("jarvis_file_guardian")
    sys.modules["jarvis_file_guardian"] = None
    try:
        absent = N.snapshot_vault_before_write(TMP / "anything.md")
    finally:
        if real_module is not None:
            sys.modules["jarvis_file_guardian"] = real_module
    check("with the guardian module absent the helper answers guardian_unavailable, "
          "never a traceback",
          absent.get("ok") is False
          and absent.get("error") == "guardian_unavailable", absent)


def t_the_project_pointer_is_snapshotted_before_it_is_replaced():
    """Project Mode's own file is copied before the temp+replace, and linked.

    The audit row carries the snapshot id, the receipt id and the copied hash -
    the ids are checked against the real journal row and the real receipt, so
    the link is a fact rather than a field.
    """
    fresh()
    mode = JP.mode_path()
    check("the Project Mode pointer is inside this suite's own config folder",
          str(mode).startswith(str(CONFIG)), (mode, CONFIG))
    mode.parent.mkdir(parents=True, exist_ok=True)
    old = b'{"active_project_id": "an-old-project-id"}'
    mode.write_bytes(old)
    audits = []
    real_audit = JP._audit
    JP._audit = lambda event, detail: audits.append((event, detail))
    try:
        left = JP.set_active_project(None, store=object())
    finally:
        JP._audit = real_audit
    check("leaving Project Mode returns cleanly", left is None)
    check("... and the pointer file is replaced with the empty mode",
          json.loads(mode.read_text(encoding="utf-8")) == {}, mode.read_text())
    sha_old = sha256_of(old)
    blob = blob_path(HOME_A, sha_old)
    check("the guardian copied the PREVIOUS pointer bytes before the replace",
          blob.is_file() and gzip.decompress(blob.read_bytes()) == old, str(blob))
    detail = audits[-1][1] if audits else {}
    check("the audit row says truthfully that a copy happened",
          detail.get("snapshot_ok") is True, detail)
    row = next((r for r in row_list()
                if r.get("copy_id") == str(detail.get("snapshot_id") or "")), {})
    receipt = R.get(str(detail.get("receipt_id") or ""))
    check("... and links a real snapshot id, receipt id and the copied hash",
          bool(detail.get("snapshot_id")) and row.get("before_sha256") == sha_old
          and receipt is not None and receipt.get("tool_name") == G.TOOL_SNAPSHOT
          and detail.get("before_sha256") == sha_old, (detail, row))
    check("... and the NEW pointer's bytes got no snapshot (the copy is the BEFORE "
          "state)",
          not blob_path(HOME_A, sha256_of(mode.read_bytes())).exists())


def t_a_broken_guardian_never_blocks_project_mode_and_never_lies():
    """Best-effort, said honestly: Project Mode still works, the audit row does
    not pretend a copy happened, and a first-time write says there was nothing
    to copy."""
    fresh()
    mode = JP.mode_path()
    mode.parent.mkdir(parents=True, exist_ok=True)
    mode.write_bytes(b'{"active_project_id": "an-old-project-id"}')
    real = JP._snapshot_mode_file
    JP._snapshot_mode_file = lambda _path: {
        "ok": False, "error": "guardian_unavailable (RuntimeError)",
        "words": "the time machine is not on this backend"}
    audits = []
    real_audit = JP._audit
    JP._audit = lambda event, detail: audits.append((event, detail))
    try:
        left = JP.set_active_project(None, store=object())
    finally:
        JP._audit = real_audit
        JP._snapshot_mode_file = real
    check("a REFUSED copy does NOT block Project Mode",
          left is None and mode.is_file()
          and json.loads(mode.read_text(encoding="utf-8")) == {}, mode.read_text())
    detail = audits[-1][1] if audits else {}
    check("the audit row says plainly that the copy did NOT happen",
          detail.get("snapshot_ok") is False
          and "guardian_unavailable" in str(detail.get("snapshot_error")), detail)
    check("... and never claims a snapshot that did not happen (no id fields)",
          "snapshot_id" not in detail and "receipt_id" not in detail, detail)

    fresh()
    mode = JP.mode_path()
    try:
        mode.unlink()
    except OSError:
        pass
    audits = []
    JP._audit = lambda event, detail: audits.append((event, detail))
    try:
        JP.set_active_project(None, store=object())
    finally:
        JP._audit = real_audit
    detail = audits[-1][1] if audits else {}
    check("a FIRST-TIME pointer write says there was no file to copy",
          detail.get("snapshot_ok") is False
          and detail.get("snapshot_reason") == "no file was there to copy", detail)


def t_the_project_hook_keeps_the_symlink_refusal():
    """The guardian's own link rule still runs through the Project Mode hook."""
    fresh()
    mode = JP.mode_path()
    mode.parent.mkdir(parents=True, exist_ok=True)
    target = CONFIG / "pointer-target.json"
    target.write_bytes(b'{"a": "link target"}')
    try:
        if mode.exists() or mode.is_symlink():
            mode.unlink()
        os.symlink(str(target), str(mode))
    except OSError as exc:
        skip(f"a symlink cannot be made on this machine ({type(exc).__name__}), so "
             f"the Project Mode link refusal was not driven")
        return
    audits = []
    real_audit = JP._audit
    JP._audit = lambda event, detail: audits.append((event, detail))
    try:
        JP.set_active_project(None, store=object())
    finally:
        JP._audit = real_audit
    detail = audits[-1][1] if audits else {}
    check("a symlinked pointer file is still refused by the guardian's own link rule",
          detail.get("snapshot_ok") is False
          and "link" in str(detail.get("snapshot_error")).lower(), detail)
    check("... and Project Mode still writes the pointer (best-effort)",
          mode.is_file() and not mode.is_symlink()
          and json.loads(mode.read_text(encoding="utf-8")) == {}, mode.read_text())
    check("... and the link's target was never written through",
          target.read_bytes() == b'{"a": "link target"}')


# --------------------------------------------------------------------------
#   13. The registration, and the twin
# --------------------------------------------------------------------------


def t_the_module_is_registered_in_the_shipped_lists():
    check("the module is in _where.SHIPPED", "jarvis_file_guardian.py" in _where.SHIPPED,
          _where.SHIPPED[-3:])
    shipped = list(_where.SHIPPED)
    check("... appended after the earlier Pillar 15 entry (nothing was inserted before it)",
          "jarvis_sandbox_exec.py" in shipped
          and "jarvis_file_guardian.py" in shipped
          and shipped.index("jarvis_file_guardian.py")
          > shipped.index("jarvis_sandbox_exec.py"),
          shipped[-3:])
    twin = REPO / "jarvis-backend" / "jarvis_file_guardian.py"
    check("the base's twin exists", twin.is_file(), str(twin))
    ours = HERE / "jarvis_file_guardian.py"
    check("the twin is byte-identical to backend/jarvis_file_guardian.py",
          twin.is_file() and twin.read_bytes() == ours.read_bytes(),
          (sha256_of(twin.read_bytes()) if twin.is_file() else None,
           sha256_of(ours.read_bytes())))



# --------------------------------------------------------------------------
#   14. The two READ-ONLY history routes (LM-2A, JARVIS-API section 140)
# --------------------------------------------------------------------------


class RouteHandler:
    """A stand-in for the server's own Handler, the shape install() wraps."""

    def __init__(self, path, peer="127.0.0.1"):
        self.path = path
        self.sent = None
        self.client_address = (peer, 50123)
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4719))

    def do_GET(self):
        self.sent = ("original", self.path)

    def _send(self, code, body):
        self.sent = (code, body)


def routed(origin=True, token=True):
    class Hd(RouteHandler):
        pass
    B.install(Hd, origin_ok=lambda s: origin, token_ok=lambda s: token, read_body=None)
    return Hd


def call(path, query="", *, peer="127.0.0.1"):
    Hd = routed()
    h = Hd(path + ("?" + query if query else ""), peer=peer)
    h.do_GET()
    return h.sent


def tree_bytes(root) -> dict:
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


def two_versions():
    """A store with two saved versions of one file, newest = the second."""
    fresh()
    path = write("note.txt", b"one\n")
    first = snapshot(path, reason="first edit")
    path.write_bytes(b"two\n")
    second = snapshot(path, reason="second edit")
    return path, first, second


def t_the_history_is_installed_and_lists_this_pcs_snapshots():
    path, first, second = two_versions()
    code, body = call("/api/guardian/snapshots")
    check("install() answers the guardian's snapshot index", code == 200
          and body.get("ok") is True, (code, body))
    check("... newest saved version first",
          [r["before_sha256"] for r in body["snapshots"]][:2]
          == [second["before_sha256"], first["before_sha256"]],
          [r["before_sha256"] for r in body["snapshots"]])
    row = body["snapshots"][0]
    check("a row carries the full path and a display label", row["path"] == str(path)
          and row["label"] == "note.txt", row)
    check("a row carries its size, when, reason and receipt id",
          row["size"] == 4 and bool(row["when"]) and row["reason"] == "second edit"
          and row["receipt_id"] == second["receipt_id"], row)
    check("the answer carries no file contents or blob bytes",
          not any(k in row for k in ("content", "text", "bytes", "blob"))
          and "one\n" not in json.dumps(body), sorted(row))
    check("usage is the bounded summary, never the per-blob map",
          "sizes" not in body["usage"] and "blob_bytes" in body["usage"],
          sorted(body["usage"]))
    line = B.install(routed(), origin_ok=lambda s: True, token_ok=lambda s: True,
                     read_body=None)
    check("the install banner names the new history", "guardian" in line, line)


def t_a_page_is_bounded_and_says_so():
    fresh()
    path = write("note.txt", b"0\n")
    for n in range(1, 7):
        path.write_bytes(f"{n}\n".encode())
        snapshot(path, reason=f"edit {n}")
    code, body = call("/api/guardian/snapshots", "limit=3")
    check("limit=3 gives three of the six rows, and says there are more",
          code == 200 and body["count"] == 3 and body["total"] == 6
          and body["limit"] == 3 and body["more"] is True, body)
    check("... and they are the newest three, newest first",
          [r["reason"] for r in body["snapshots"]] == ["edit 6", "edit 5", "edit 4"],
          [r["reason"] for r in body["snapshots"]])
    for bad in ("0", "201", "abc", "-3"):
        code, body = call("/api/guardian/snapshots", f"limit={bad}")
        check(f"limit={bad} is refused in plain words, not silently clamped",
              code == 400 and body["why"] == "bad_limit", (bad, code, body.get("why")))
    code, body = call("/api/guardian/snapshots")
    check("the default page is 50 and this six-row journal fits",
          code == 200 and body["limit"] == 50 and body["count"] == 6
          and body["more"] is False, body)


def t_the_diff_is_the_modules_own_answer_and_is_bounded():
    fresh()
    rows = b"".join(f"line {i:04d} ".encode() + b"x" * 60 + b"\n" for i in range(4000))
    path = write("big.txt", rows)
    first = snapshot(path, reason="before the change")
    path.write_bytes(b"".join(f"changed {i:04d} ".encode() + b"y" * 60 + b"\n"
                              for i in range(4000)))
    direct = G.diff_versions(str(path), first["before_sha256"])
    code, body = call("/api/guardian/diff",
                      "path=" + quote(str(path)) + "&sha_before=" + first["before_sha256"])
    check("the route answers 200 with the module's own dict, unchanged",
          code == 200 and body == direct, (code, body.get("ok")))
    check("the diff is bounded by the module and says it was cut",
          direct["truncated"] is True
          and "the rest of the difference is not shown" in direct["diff"]
          and len(direct["diff"]) <= G.MAX_DIFF_BYTES + 80, len(direct["diff"]))
    small = write("small.txt", b"one\n")
    snap = snapshot(small, reason="small")
    small.write_bytes(b"two\n")
    code, body = call("/api/guardian/diff",
                      "path=" + quote(str(small)) + "&sha_before=" + snap["before_sha256"])
    check("a small change shows the -old/+new lines", code == 200
          and "-one" in body["diff"] and "+two" in body["diff"], body.get("diff", ""))


def t_a_missing_saved_version_is_refused_plainly():
    fresh()
    path = write("note.txt", b"one\n")
    snapshot(path)
    code, body = call("/api/guardian/diff",
                      "path=" + quote(str(path)) + "&sha_before=" + "0" * 64)
    check("an unknown saved version is a 200 answer with a plain refusal",
          code == 200 and body["ok"] is False and body["refused"] is True
          and "not in the time machine" in body["words"], body)
    for query in ("path=" + quote(str(path)), "sha_before=" + "0" * 64, ""):
        code, body = call("/api/guardian/diff", query)
        check(f"a difference with {query!r} is a 400, not a guess",
              code == 400 and body["why"] == "bad_request", (query, code, body.get("why")))
    outside = TMP / "outside.txt"
    outside.write_bytes(b"x")
    code, body = call("/api/guardian/diff",
                      "path=" + quote(str(outside)) + "&sha_before=" + "0" * 64)
    check("a file outside the allowed folders is refused by the module",
          code == 200 and body["ok"] is False and "allowed to change" in body["words"],
          body)


def t_only_this_pc_may_ask_and_nothing_is_read_first():
    fresh()
    path = write("note.txt", b"one\n")
    snapshot(path)
    reads = []
    real_rows = G.rows
    real_check = B._from_this_pc
    G.rows = lambda: (reads.append(1), real_rows())[1]
    try:
        B._from_this_pc = lambda peer, local: False
        code, body = call("/api/guardian/snapshots")
        code2, body2 = call("/api/guardian/diff",
                            "path=" + quote(str(path)) + "&sha_before=" + "0" * 64)
    finally:
        B._from_this_pc = real_check
        G.rows = real_rows
    check("a request from another device gets 403 with the route's own empty shape",
          code == 403 and body["ok"] is False and body["why"] == "not_this_pc"
          and body["snapshots"] == [], (code, body))
    check("... and the same 403 for the diff route", code2 == 403
          and body2["why"] == "not_this_pc" and body2["diff"] == "", (code2, body2))
    check("... and the guardian's journal was never read", reads == [], reads)
    check("the real owner check calls loopback this PC",
          B._from_this_pc("127.0.0.1", "127.0.0.1") is True)
    check("... and treats no peer as the in-process caller it is",
          B._from_this_pc(None, None) is True)
    saved = sys.modules.get("jarvis_owner_check")
    sys.modules["jarvis_owner_check"] = None
    try:
        got = B._from_this_pc("100.64.0.9", "127.0.0.1")
    finally:
        if saved is None:
            sys.modules.pop("jarvis_owner_check", None)
        else:
            sys.modules["jarvis_owner_check"] = saved
    check("with no owner-check module the route fails CLOSED", got is False, got)


def t_a_foreign_origin_or_no_token_never_reaches_the_guardian():
    for origin, token, expected in ((True, False, 401), (False, True, 403)):
        Hd = routed(origin=origin, token=token)
        h = Hd("/api/guardian/snapshots")
        h.do_GET()
        check(f"origin={origin} token={token} never reaches the guardian",
              h.sent is not None and h.sent[0] == expected, h.sent)
    Hd = routed()
    h = Hd("/api/not-a-route")
    h.do_GET()
    check("every other request still goes to the original handler",
          h.sent == ("original", "/api/not-a-route"), h.sent)


def t_no_restore_or_write_is_reachable_from_the_read_routes():
    fresh()
    path = write("note.txt", b"one\n")
    snap = snapshot(path)
    path.write_bytes(b"two\n")
    store = Path(HOME_A) / G.GUARDIAN_DIR
    before = tree_bytes(store)
    names = ("snapshot_before_write", "restore_version", "_append_row", "_write_file",
             "prune", "pin", "unpin", "_record_restore", "_save_pins")

    def boom(*a, **k):
        raise AssertionError("a READ route called a write function")

    saved = {name: getattr(G, name) for name in names}
    for name in names:
        setattr(G, name, boom)
    try:
        a = call("/api/guardian/snapshots")
        b = call("/api/guardian/diff",
                 "path=" + quote(str(path)) + "&sha_before=" + snap["before_sha256"])
    finally:
        for name, fn in saved.items():
            setattr(G, name, fn)
    check("both routes answer with every write/restore function replaced by one "
          "that raises", a[0] == 200 and b[0] == 200, (a[0], b[0]))
    check("... and not one store byte changed", tree_bytes(store) == before)
    check("there is no restore route in this slice",
          not any("restore" in route for route in B.PATHS), B.PATHS)


def t_a_client_lock_flag_is_not_faked():
    fresh()
    path = write("note.txt", b"one\n")
    snapshot(path)
    plain = call("/api/guardian/snapshots")[1]
    claimed = call("/api/guardian/snapshots",
                   "app_locked=1&hide_memory=1&private=1")[1]
    check("the route takes no client-supplied lock flag: it answers the same either way",
          claimed == plain)
    check("... and it does not pretend to have withheld anything",
          "withheld" not in json.dumps(claimed).lower(), claimed.get("words"))


def t_an_older_backend_says_update_in_the_same_shape():
    fresh()
    path = write("note.txt", b"one\n")
    snapshot(path)
    real_rows, real_diff = G.rows, G.diff_versions
    try:
        delattr(G, "rows")
        code, body = call("/api/guardian/snapshots")
    finally:
        G.rows = real_rows
    check("an older guardian: 501 in the snapshot shape, with the update sentence",
          code == 501 and body["ok"] is False and body["refused"] is True
          and body["snapshots"] == [] and "apply-patches.ps1" in body["words"],
          (code, body))
    try:
        delattr(G, "diff_versions")
        code, body = call("/api/guardian/diff",
                          "path=" + quote(str(path)) + "&sha_before=" + "0" * 64)
    finally:
        G.diff_versions = real_diff
    check("an older guardian: 501 in the diff shape",
          code == 501 and body["ok"] is False and "apply-patches.ps1" in body["words"],
          (code, body))



# --------------------------------------------------------------------------
#   15. The one WRITE route: POST /api/guardian/restore (LM-2B)
# --------------------------------------------------------------------------


def post_door(body=None, *, origin=True, token=True, peer="127.0.0.1",
              read=None, raw=None, path="/api/guardian/restore"):
    """One POST through the real stack (the suite's handler, install(), body)."""
    payload = raw if raw is not None else json.dumps(body or {}).encode()

    def _read(_handler):
        return payload

    class Hd(RouteHandler):
        def do_POST(self):
            self.sent = ("original-post", self.path)

    B.install(Hd, origin_ok=lambda s: origin, token_ok=lambda s: token,
              read_body=(read if read is not None else _read))
    h = Hd(path, peer=peer)
    h.do_POST()
    return h.sent


def receipts_count() -> int:
    return len(R.recent(limit=500))


def journal_rows() -> int:
    return len(G.rows())


def route_restore(path, sha_before, gate):
    return B.handle_post(B.GUARDIAN_RESTORE_PATH,
                         {"path": str(path), "sha_before": sha_before}, gate=gate)


def t_the_restore_route_puts_the_version_back_on_a_persons_yes():
    fresh()
    original = b"the first version\nwith two lines\n"
    second = b"the second version\n"
    path = write("route-restore.txt", original)
    saved = snapshot(path)
    path.write_bytes(second)
    cards = Cards("approved")
    code, body = route_restore(path, saved["before_sha256"], cards.gate)
    check("the route answers 200 with the module's own success dict",
          code == 200 and body.get("ok") is True and body.get("changed") is True, body)
    check("... and the file is byte-for-byte the saved version",
          path.read_bytes() == original, path.read_bytes())
    check("... it raised exactly ONE card, and it was the EXISTING undo_action",
          len(cards.cards) == 1 and cards.cards[0].get("action") == R.UNDO_ACTION,
          cards.cards)
    receipt_id = str(body.get("receipt_id") or "")
    check("... and left a NEW receipt, not the snapshot's",
          receipt_id.startswith("rc") and receipt_id != saved.get("receipt_id"),
          (receipt_id, saved.get("receipt_id")))
    receipt = R.get(receipt_id) if receipt_id else None
    check("the new receipt says what the restore replaced",
          receipt is not None and receipt.get("tool_name") == G.TOOL_RESTORE
          and ((receipt.get("before") or {}).get("sha256")) == sha256_of(second),
          receipt)
    undo = R.undo(receipt_id)
    check("the EXISTING Undo puts back the bytes that were here before",
          undo.get("ok") is True and path.read_bytes() == second,
          (undo, path.read_bytes()))


def t_a_denied_timed_out_or_unraisable_card_writes_nothing():
    fresh()
    path = write("denied.txt", b"the first\n")
    saved = snapshot(path)
    path.write_bytes(b"the second\n")
    store = Path(HOME_A) / G.GUARDIAN_DIR

    def boom(action, detail, prompt):
        raise RuntimeError("no gate on this PC")

    for label, gate, words in (("denied", Cards("denied").gate, "turned down"),
                               ("timed_out", Cards("timed_out").gate, "nobody"),
                               ("unraisable", boom, "could not be raised")):
        before_file, before_store = path.read_bytes(), tree_bytes(store)
        before_receipts, before_rows = receipts_count(), journal_rows()
        code, body = route_restore(path, saved["before_sha256"], gate)
        check(f"a {label} card is a 200 refusal, not a traceback",
              code == 200 and body.get("ok") is False and body.get("refused") is True,
              (code, body))
        check(f"... a {label} card writes nothing at all",
              path.read_bytes() == before_file and tree_bytes(store) == before_store
              and receipts_count() == before_receipts
              and journal_rows() == before_rows, body)
        check(f"... and says why in plain words ({label})",
              words in str(body.get("words", "")).lower(), body.get("words"))


def t_an_unknown_version_or_outside_path_is_refused_before_any_card():
    fresh()
    path = write("checked.txt", b"the first\n")
    saved = snapshot(path)
    path.write_bytes(b"the second\n")
    outside = TMP / "outside-restore.txt"
    outside.write_bytes(b"not jarvis's\n")
    cards = Cards("approved")
    for label, target, sha in (
            ("a path outside the allowed folders", str(outside), saved["before_sha256"]),
            ("an unknown saved version", str(path), "0" * 64),
            ("a sha that is not a sha", str(path), "not-a-sha")):
        before = path.read_bytes()
        code, body = route_restore(target, sha, cards.gate)
        check(f"the route refuses {label} with the module's own words",
              code == 200 and body.get("ok") is False and body.get("refused") is True
              and bool(body.get("words")), (label, code, body))
        check(f"... and {label} wrote nothing and raised no card",
              path.read_bytes() == before and outside.read_bytes() == b"not jarvis's\n"
              and cards.cards == [], (cards.cards, body))
    code, body = B.handle_post(B.GUARDIAN_RESTORE_PATH, "not a dict", gate=cards.gate)
    check("a body that is not a JSON object is a 400 request refusal",
          code == 400 and body.get("why") == "bad_request", (code, body))
    for missing in ({"path": str(path)}, {"sha_before": "0" * 64}, {}):
        code, body = B.handle_post(B.GUARDIAN_RESTORE_PATH, missing, gate=cards.gate)
        check(f"a body missing one of the two strings is a 400 ({sorted(missing)})",
              code == 400 and body.get("why") == "bad_request", (missing, code, body))


def t_a_failed_save_before_write_aborts_before_any_write():
    fresh()
    path = write("abort.txt", b"the first\n")
    saved = snapshot(path)
    path.write_bytes(b"the second\n")
    store = Path(HOME_A) / G.GUARDIAN_DIR
    before_file, before_store = path.read_bytes(), tree_bytes(store)
    before_receipts, before_rows = receipts_count(), journal_rows()
    real_store_blob = G._store_blob

    def no_room(data, sha):
        raise OSError("the store is full")

    G._store_blob = no_room
    try:
        code, body = route_restore(path, saved["before_sha256"], Cards("approved").gate)
    finally:
        G._store_blob = real_store_blob
    check("a store that cannot save the version here now aborts the restore plainly",
          code == 200 and body.get("ok") is False, (code, body))
    check("... and the file is untouched", path.read_bytes() == before_file)
    check("... with no new receipt and no new journal row",
          receipts_count() == before_receipts and journal_rows() == before_rows
          and tree_bytes(store) == before_store, (receipts_count(), journal_rows()))


def t_another_device_is_refused_before_the_body_is_read():
    fresh()
    read_calls = []

    def read_body(_handler):
        read_calls.append(1)
        return b'{"path": "x", "sha_before": "y"}'

    real_check = B._from_this_pc
    try:
        B._from_this_pc = lambda peer, local: False
        code, body = post_door(read=read_body)
    finally:
        B._from_this_pc = real_check
    check("a request from another device gets 403 with the restore's own shape",
          code == 403 and body.get("ok") is False and body.get("why") == "not_this_pc"
          and body.get("receipt_id") == "", (code, body))
    check("... and the request body was never read", read_calls == [], read_calls)


def t_the_route_is_post_only_and_a_get_cannot_mutate():
    fresh()
    path = write("get.txt", b"the first\n")
    snapshot(path)
    real = G.restore_version
    calls = []

    def forbidden(*a, **k):
        calls.append(1)
        raise AssertionError("a GET must never reach the restore")

    G.restore_version = forbidden
    try:
        code, _body = call("/api/guardian/restore")
        code2, _body2 = call("/api/guardian/restore", "path=x&sha_before=y")
        sent = post_door(raw=b'{"path": "x", "sha_before": "y"}',
                         path="/api/not-a-route")
    finally:
        G.restore_version = real
    check("a GET of the restore path is not answered by this module (it goes on)",
          code == "original" or code2 == "original",
          (code, code2))
    check("... and the restore was never called by a GET", calls == [], calls)
    check("a POST to any other path goes to the original handler",
          sent is not None and sent[0] == "original-post", sent)
    check("there is no GET route for the restore", B.GUARDIAN_RESTORE_PATH not in B.PATHS,
          B.PATHS)
    check("... and POST_PATHS holds exactly that one route", B.POST_PATHS
          == (B.GUARDIAN_RESTORE_PATH,), B.POST_PATHS)


def t_the_http_door_passes_the_two_strings_and_names_no_gate():
    fresh()
    path = write("door.txt", b"the first\n")
    saved = snapshot(path)
    path.write_bytes(b"the second\n")
    real = G.restore_version
    seen = []

    def fake_restore(shown_path, shown_sha, gate=None):
        seen.append((shown_path, shown_sha, gate))
        return {"ok": True, "changed": False, "same": True, "path": shown_path,
                "words": "pretend"}

    G.restore_version = fake_restore
    try:
        code, body = post_door({"path": str(path), "sha_before": saved["before_sha256"]})
    finally:
        G.restore_version = real
    check("the HTTP door answers with the module's dict unchanged",
          code == 200 and body.get("ok") is True and body.get("words") == "pretend",
          (code, body))
    check("... hands the module the path and sha_before from the body",
          len(seen) == 1 and seen[0][0] == str(path)
          and seen[0][1] == saved["before_sha256"], seen)
    check("... and names no gate over the wire (the real jarvis_gate.check() is asked)",
          seen and seen[0][2] is None, seen)
    check("a request body over 16 KiB is refused before it is parsed",
          post_door(raw=b"{}" + b" " * (17 * 1024))[0] == 413,
          post_door(raw=b"{}" + b" " * (17 * 1024)))
    check("a body that is not JSON is a 400, never a traceback",
          post_door(raw=b"not json")[0] == 400)
    check("no token and another origin never reach the restore",
          post_door(token=False)[0] == 401 and post_door(origin=False)[0] == 403,
          (post_door(token=False)[0], post_door(origin=False)[0]))


def t_an_older_backend_says_update_in_the_same_shape():
    fresh()
    path = write("older.txt", b"the first\n")
    saved = snapshot(path)
    real = G.restore_version
    del G.restore_version
    try:
        code, body = post_door({"path": str(path),
                                "sha_before": saved["before_sha256"]})
    finally:
        G.restore_version = real
    check("an older guardian: 501 in the restore shape with the update sentence",
          code == 501 and body.get("ok") is False and body.get("refused") is True
          and body.get("receipt_id") == "" and "apply-patches.ps1" in str(body.get("words")),
          (code, body))
    class NoReader(RouteHandler):
        def do_POST(self):
            self.sent = ("original-post", self.path)

    B.install(NoReader, origin_ok=lambda s: True, token_ok=lambda s: True,
              read_body=None)
    h = NoReader("/api/guardian/restore")
    h.do_POST()
    check("a server with no body reader answers 501 and changes nothing",
          h.sent[0] == 501 and h.sent[1].get("why") == "update", h.sent)


# --------------------------------------------------------------------------
#   16. The 2026-10-18 integrity fixes (review F1-F5)
# --------------------------------------------------------------------------


def t_a_tampered_blob_is_refused_before_the_card():
    fresh()
    p = write("tamper.txt", b"the real saved version\n")
    saved = snapshot(p)
    blob = blob_path(HOME_A, saved["before_sha256"])
    blob.write_bytes(gzip.compress(b"NOT THE VERSION THE CARD NAMES\n"))
    p.write_bytes(b"a later version\n")
    cards = Cards("approved")
    result = G.restore_version(str(p), saved["before_sha256"], gate=cards.gate)
    check("a blob that does not match its own content address is refused",
          refused(result, "does not match its own content address"), result)
    check("... before any card is raised", cards.cards == [], cards.cards)
    check("... and the file is untouched", p.read_bytes() == b"a later version\n")


def t_a_blob_that_unpacks_over_the_file_limit_is_refused():
    fresh()
    p = write("bomb.txt", b"the real saved version\n")
    saved = snapshot(p)
    blob = blob_path(HOME_A, saved["before_sha256"])
    blob.write_bytes(gzip.compress(b"z" * (G.MAX_FILE_BYTES + 4096)))
    p.write_bytes(b"a later version\n")
    cards = Cards("approved")
    result = G.restore_version(str(p), saved["before_sha256"], gate=cards.gate)
    check("a blob that unpacks over the one-file limit is refused, not written",
          refused(result, "unpacks to more than"), result)
    check("... before any card is raised", cards.cards == [], cards.cards)
    check("... and the file is untouched", p.read_bytes() == b"a later version\n")


def t_an_edit_while_the_card_is_up_is_the_version_saved_and_restored():
    edited = b"v3 edited while the card was up\n"

    class EditingCard:
        def __init__(self, path):
            self.path, self.cards = path, []

        def gate(self, action, detail, prompt):
            self.cards.append((action, detail, prompt))
            self.path.write_bytes(edited)       # the edit made during the wait
            return Verdict(True, "ask", "approved")

    fresh()
    p = write("race.txt", b"v1\n")
    saved = snapshot(p)
    p.write_bytes(b"v2\n")
    card = EditingCard(p)
    result = G.restore_version(str(p), saved["before_sha256"], gate=card.gate)
    check("an approved restore still puts the saved version back",
          ok(result) and result.get("changed") is True and p.read_bytes() == b"v1\n",
          result)
    check("... and the version saved for Undo is what the file held AFTER the card",
          result.get("before_sha256") == sha256_of(edited), result.get("before_sha256"))
    receipt = R.get(result.get("receipt_id")) if result.get("receipt_id") else None
    check("... the receipt's before snapshot agrees",
          receipt is not None
          and ((receipt.get("before") or {}).get("sha256")) == sha256_of(edited),
          receipt)
    undo = R.undo(result["receipt_id"]) if result.get("receipt_id") else None
    check("... so Undo brings the edit made during the card back",
          undo is not None and undo.get("ok") is True and p.read_bytes() == edited, undo)


def t_a_version_saved_from_another_file_is_refused():
    fresh()
    a = write("other-a.txt", b"file A's saved words\n")
    saved = snapshot(a)
    b = write("other-b.txt", b"file B's own words\n")
    cards = Cards("approved")
    result = G.restore_version(str(b), saved["before_sha256"], gate=cards.gate)
    check("a version saved from another file is refused",
          refused(result, "different file"), result)
    check("... before any card is raised", cards.cards == [], cards.cards)
    check("... and the target file is untouched",
          b.read_bytes() == b"file B's own words\n")
    again = G.restore_version(str(a), saved["before_sha256"], gate=Cards("approved").gate)
    check("a version saved from THIS file is still restorable", ok(again))


def t_a_restore_that_cannot_be_receipted_aborts_before_the_write():
    fresh()
    p = write("receipt-fail.txt", b"v1\n")
    saved = snapshot(p)
    p.write_bytes(b"v2\n")
    before_receipts, before_rows = receipts_count(), journal_rows()
    real_record = R.record

    def no_record(*a, **k):
        raise RuntimeError("the receipt store is down")

    R.record = no_record
    try:
        result = G.restore_version(str(p), saved["before_sha256"],
                                   gate=Cards("approved").gate)
    finally:
        R.record = real_record
    check("a restore whose receipt cannot be recorded is refused",
          refused(result, "could not be recorded"), result)
    check("... nothing was written", p.read_bytes() == b"v2\n")
    check("... and no receipt or journal row was left behind",
          receipts_count() == before_receipts and journal_rows() == before_rows,
          (receipts_count(), journal_rows()))


def t_a_restore_that_cannot_be_journalled_aborts_and_takes_its_receipt_back():
    fresh()
    p = write("journal-fail.txt", b"v1\n")
    saved = snapshot(p)
    p.write_bytes(b"v2\n")
    before_receipts, before_rows = receipts_count(), journal_rows()
    real_append = G._append_row

    def no_row(row):
        raise OSError("disk full")

    G._append_row = no_row
    try:
        result = G.restore_version(str(p), saved["before_sha256"],
                                   gate=Cards("approved").gate)
    finally:
        G._append_row = real_append
    check("a restore whose journal row cannot be written is refused",
          refused(result, "file history"), result)
    check("... nothing was written", p.read_bytes() == b"v2\n")
    check("... its receipt was taken back, so it cannot claim a restore",
          receipts_count() == before_receipts and journal_rows() == before_rows,
          (receipts_count(), journal_rows()))


def t_a_restore_whose_write_fails_leaves_no_receipt():
    fresh()
    p = write("write-fail.txt", b"v1\n")
    saved = snapshot(p)
    p.write_bytes(b"v2\n")
    before_receipts = receipts_count()
    real_write = G._write_file

    def no_write(real, data):
        raise G.Refused("the write failed (simulated)")

    G._write_file = no_write
    try:
        result = G.restore_version(str(p), saved["before_sha256"],
                                   gate=Cards("approved").gate)
    finally:
        G._write_file = real_write
    check("a restore whose write fails is refused", refused(result, "write failed"), result)
    check("... nothing was written", p.read_bytes() == b"v2\n")
    check("... and no receipt claims a restore that did not happen",
          receipts_count() == before_receipts, receipts_count())


def t_a_verdict_that_is_not_exactly_approved_writes_nothing():
    fresh()
    p = write("outcome.txt", b"v1\n")
    saved = snapshot(p)
    p.write_bytes(b"v2\n")

    class NoOutcome:
        def __call__(self, action, detail, prompt):
            return Verdict(True, "ask", None)

    result = G.restore_version(str(p), saved["before_sha256"], gate=NoOutcome())
    check("allowed=True at tier ask with no outcome is NOT a person's yes",
          refused(result, "not approved"), result)
    check("... and nothing was written", p.read_bytes() == b"v2\n")

    class NotifyOutcome:
        def __call__(self, action, detail, prompt):
            return Verdict(True, "notify", "notify")

    result = G.restore_version(str(p), saved["before_sha256"], gate=NotifyOutcome())
    check("allowed=True with a notify outcome is not a yes either",
          refused(result, "not approved") and p.read_bytes() == b"v2\n", result)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    try:
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
