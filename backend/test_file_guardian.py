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
    missing file, no allowed folder at all, a file over the per-file limit,
    and a file that cannot be read - all plain sentences, with no blob and no
    row created and the file intact.
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

Every check bites: the module was mutated deliberately (see the branch's
report) and this suite went red for each mutation, so no check is a check on
the constant True.
"""
from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_file_guardian.py", "jarvis_receipts.py", "jarvis_scrub.py")

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
import jarvis_receipts as R  # noqa: E402

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

    big = ALLOWED / "too-big.bin"
    try:
        with open(big, "wb") as handle:
            handle.truncate(G.MAX_FILE_BYTES + 1)
        oversized = snapshot(big)
        check("a file above the per-file limit is refused in plain words",
              refused(oversized, "bigger than"), oversized)
        check("... and nothing was copied or recorded for it",
              blob_names() == [] and row_list() == [], (blob_names(), row_list()))
    finally:
        try:
            big.unlink()
        except OSError:
            pass


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
#   12. The registration, and the twin
# --------------------------------------------------------------------------


def t_the_module_is_registered_in_the_shipped_lists():
    check("the module is in _where.SHIPPED", "jarvis_file_guardian.py" in _where.SHIPPED,
          _where.SHIPPED[-3:])
    check("... at the END of _where.SHIPPED (a new entry goes at the end)",
          _where.SHIPPED and _where.SHIPPED[-1] == "jarvis_file_guardian.py",
          _where.SHIPPED[-1])
    twin = REPO / "jarvis-backend" / "jarvis_file_guardian.py"
    check("the base's twin exists", twin.is_file(), str(twin))
    ours = HERE / "jarvis_file_guardian.py"
    check("the twin is byte-identical to backend/jarvis_file_guardian.py",
          twin.is_file() and twin.read_bytes() == ours.read_bytes(),
          (sha256_of(twin.read_bytes()) if twin.is_file() else None,
           sha256_of(ours.read_bytes())))


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
