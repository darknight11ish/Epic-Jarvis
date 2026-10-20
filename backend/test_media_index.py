"""test_media_index.py - F5 S2: the searchable index of recordings and videos.

    python -B backend/test_media_index.py

THE OWNER'S DECISION (2026-10-19 14:50 PT, `.dsh-scratch/
BRIEF-F5-S2-MEDIA-INDEX-2026-10-19.md`): keep READABLE transcript text in the
PC-side index, and ship the switch ON by default. The brief's safeguards are
not optional, and this suite is where each one is checked:

  1. ONLY THE LISTED FOLDERS. A recording outside "Folders Jarvis may look
     in" is refused by the same `jarvis_documents.allowed_path()` rule S1
     uses; an index run only walks those folders.
  2. THE WORDS, NEVER THE MEDIA. The index stores the readable lines; no
     audio/video copy is made, the original files are untouched, and the
     index file is the only thing created.
  3. A SEARCH ANSWERS WITH THE EXACT STORED LINE - its file, its time, its
     words - with no second read of the recording.
  4. ONE DELETE THAT REALLY DELETES. Delete-one removes that file's rows and
     rewrites/checkpoints the database so no readable copy survives; Delete-all
     removes the index file AND its `-wal`/`-shm` siblings. The raw-byte
     canary test forces WAL mode, deletes, then reads every `media-index.db*`
     file and requires zero occurrences of a unique canary word (Gemini's
     evidence bar). `jarvis_backup.py` excludes `media-index.db` and its own
     decision function says why, so no backup holds a copy a Delete cannot
     reach (the test drives that real function).
  5. THE SWITCH: ON by default (the owner's override), OFF instant (nothing
     more read or written, a waiting ON card taken back), ON one approval
     card.
  6. GONE/MOVED FILES LEAVE. A deleted or renamed recording's rows are
     dropped on the next run; a row is never kept for a file that is not
     there.
  7. NOT A LEARNED FACT, AND THE LOCAL LANE. The module imports no
     memory/learning module, the tool result is outside text by the existing
     my_files rule, the result carries no fact/learned field, and a result
     carrying stored lines latches the conversation private
     (`jarvis_gate.latch_taint`, why `media_index_search`) so a later turn
     cannot be offered a cloud lane carrying what was said.

The READ seam is injected (a fake returns fixed segments), so no model, no
ffmpeg, no network and no real recording is needed. The one real module driven
end-to-end is `jarvis_backup.py`'s exclusion decision.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_media_index.py", "jarvis_media_read.py",
                "jarvis_documents.py", "jarvis_backup.py",
                "jarvis_agent.py", "jarvis_settings_registry.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_backup as B  # noqa: E402
import jarvis_documents as DOCS  # noqa: E402
import jarvis_media_index as MI  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-media-index-"))
CFG = TMP / "config"
CFG.mkdir(parents=True)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh(name: str) -> Path:
    """A root only this test uses: one root's files must never leak into the
    next test's walk (the first version of this suite did exactly that)."""
    root = TMP / "roots" / name
    root.mkdir(parents=True)
    return root


class FakeRead:
    """The S1 read seam: a fixed transcript per file stem, and a call count."""

    def __init__(self, table=None):
        self.table = table or {}
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        stem = Path(path).stem
        lines = self.table.get(stem)
        if lines is None:
            lines, seconds = [("line about " + stem, 0.0, 3.5)], 3.5
        else:
            seconds = max((b for _t, _a, b in lines), default=3.5)
        return {"ok": True, "path": path, "seconds": seconds,
                "segments": [{"start": a, "end": b, "text": t} for t, a, b in lines],
                "text": "\n".join(t for t, _a, _b in lines)}


def media_file(folder: Path, name: str = "memo.wav", data: bytes = b"RIFF....WAVE") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_bytes(data)
    return p


class Env:
    """A temp settings folder and the owner's folder list, as the suite needs
    them. The switch's shipped default is ON, which the owner chose."""

    def __init__(self, roots):
        self.roots = [str(r) for r in roots]

    def __enter__(self):
        self.patches = [
            mock.patch.object(MI, "_config_dir", return_value=CFG),
            mock.patch.object(MI, "framework_default", return_value=True),
            mock.patch.object(DOCS, "folders", return_value=list(self.roots)),
        ]
        for p in self.patches:
            p.start()
        MI._reset_for_tests()
        MI.delete()
        for name in ("media-index.db-wal", "media-index.db-shm", "media-index.json"):
            p = CFG / name
            if p.is_file():
                p.unlink()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        return False


# --------------------------------------------------------------------------
#   1. only the listed folders
# --------------------------------------------------------------------------

def t_indexes_only_the_listed_folders():
    root = fresh("only")
    inside = media_file(root / "home", "inside.wav")
    outside = media_file(TMP / "outside", "outside.wav")
    other = media_file(root / "other", "other.mp4")
    fake = FakeRead()
    with Env([root]):
        got = MI.reconcile(read=fake)
        check("the index run reaches the listed folders only",
              got["ok"] is True and got["indexed"] >= 1, got)
        paths = {m["path"] for m in MI.search("line about", read=fake).get("matches", [])}
        check("...a recording inside the listed folder is searchable",
              str(inside) in paths, paths)
        check("...a recording outside it is never touched",
              str(outside) not in paths and str(outside) not in fake.calls,
              fake.calls)
        check("...and a video in a listed folder is indexed too (from its words)",
              str(other) in paths)
        before = list(fake.calls)
        got = MI.index_file(str(outside), read=fake)
        check("indexing a named file outside the list is refused before it is opened",
              got["ok"] is False and "not inside a folder on your list" in got["error"]
              and fake.calls == before, got)


# --------------------------------------------------------------------------
#   2. the words, never the media
# --------------------------------------------------------------------------

def t_stores_the_readable_text_not_the_media():
    root = fresh("stores")
    folder = root / "text"
    rec = media_file(folder, "talk.wav", b"RIFF....WAVEaudio-bytes")
    original = rec.read_bytes()
    size_before = {p: p.stat().st_size for p in folder.iterdir()}
    fake = FakeRead({"talk": [("the gate code is ruby", 0.0, 4.0)]})
    with Env([root]):
        got = MI.reconcile(read=fake)
        check("the owner's chosen version stores the transcript text as readable rows",
              got["indexed"] == 1, got)
        check("...the line is readable in the index (not just a word hash)",
              "the gate code is ruby" in MI.index_path().read_bytes().decode("utf-8", "replace"))
        check("...the recording itself is byte-identical after indexing",
              rec.read_bytes() == original)
        check("...and no audio/video copy is made beside it",
              {p: p.stat().st_size for p in folder.iterdir()} == size_before
              and not list(root.rglob("*.wav.bak")))
        check("...and the index file lives in the settings folder, not in a listed one",
              MI.index_path() == CFG / "media-index.db"
              and not list(root.rglob("media-index.db")))
        check("the disclosure says readable private speech is kept on this PC until deleted",
              "readable" in MI.DISCLOSURE.lower()
              and "until you delete" in MI.DISCLOSURE.lower())
        check("...and it says the audio/video is never copied",
              "never copies the audio or video" in MI.DISCLOSURE.lower())


# --------------------------------------------------------------------------
#   3. a search answers with the exact stored line
# --------------------------------------------------------------------------

def t_search_returns_the_exact_line_with_file_and_time():
    root = fresh("search")
    folder = root / "exact"
    media_file(folder, "dentist.wav")
    media_file(folder, "garden.wav")
    fake = FakeRead({"dentist": [("remember the dentist on Tuesday", 12.0, 16.0)],
                     "garden": [("the tomatoes need water", 2.0, 6.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        calls = len(fake.calls)
        got = MI.search("dentist tuesday", read=fake)
        check("a search finds the recording that says the words",
              got["ok"] is True and len(got["matches"]) == 1, got["matches"])
        match = got["matches"][0] if got["matches"] else {}
        check("...with the EXACT stored line, not a re-read",
              match.get("text") == "remember the dentist on Tuesday", match)
        check("...its file name and time",
              match.get("name") == "dentist.wav" and match.get("start") == 12.0
              and match.get("end") == 16.0, match)
        check("...and no second read of the recording was needed",
              len(fake.calls) == calls, (calls, len(fake.calls)))
        got = MI.search("tomatoes", read=fake)
        check("a different search returns the other recording, not both",
              [m["name"] for m in got["matches"]] == ["garden.wav"], got["matches"])
        check("words with nothing matching answer plainly",
              MI.search("zebra", read=fake)["matches"] == [])


# --------------------------------------------------------------------------
#   4. the one Delete, and the backup exclusion that makes it real
# --------------------------------------------------------------------------

def t_delete_really_deletes_and_backups_cannot_restore_it():
    root = fresh("delete")
    folder = root / "recording"
    rec = media_file(folder, "private.wav", b"RIFFaudio")
    fake = FakeRead({"private": [("my passport number is not written here", 0.0, 5.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        check("the words are searchable before the Delete",
              bool(MI.search("passport", read=fake)["matches"]))
        one = MI.delete(str(rec))
        check("Delete-one removes that recording's stored words",
              one.get("ok") is True and one.get("deleted", 0) >= 1, one)
        check("...never opens or deletes the original recording", rec.is_file())
        with MI._db() as c:
            MI._ready(c)
            left = c.execute("SELECT count(*) AS n FROM media_lines "
                             "WHERE text LIKE ?", ("%passport%",)).fetchone()["n"]
        check("...the rows are gone, and SQLite secure_delete leaves no text behind",
              left == 0
              and "passport" not in MI.index_path().read_bytes().decode("utf-8", "replace"))
        MI.reconcile(read=fake)
        got = MI.delete()
        check("Delete-all removes the index file itself",
              got.get("ok") is True and got.get("index_file") is True
              and not MI.index_path().exists(), got)
        check("...and the recording is still there, untouched", rec.is_file())
        why = B.not_backed_up_reason("media-index.db")
        check("the backup module EXCLUDES media-index.db, with a reason",
              bool(why) and "backup" in why.lower(), why)
        check("...and the exclusion is in the shipped table, not a test fake",
              "media-index.db" in B.NOT_BACKED_UP, sorted(B.NOT_BACKED_UP))
        check("...so no backup can hold a copy a Delete cannot reach",
              "delete" in why.lower(), why)


def t_a_deleted_word_is_gone_from_every_index_file():
    """Gemini's RAW-BYTE CANARY bar (2026-10-20).

    The disclosure promises readable private speech is kept only until deleted.
    So: index one clip containing a unique word, prove `search_media` returns
    it, Delete, then read the raw bytes of EVERY `media-index.db*` file
    (including `-wal`/`-shm` if present) and require ZERO occurrences. The WAL
    mode is forced first, because plaintext pages can otherwise sit in
    `media-index.db-wal` until a checkpoint - the gap the review found."""
    canary = "zorblatcanaryword"
    # Delete ONE recording: the database file still exists, so this is the
    # harder half - the word must be gone from the surviving db and its WAL.
    root = fresh("canary-one")
    rec = media_file(root, "one.wav")
    fake = FakeRead({"one": [("the unique word is " + canary, 0.0, 2.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        got = AG._run_my_files({"action": "search_media", "words": canary}, None)
        check("search_media returns the stored canary line before the Delete",
              got.get("ok") is True
              and any(canary in (m.get("line") or "") for m in got.get("matches") or []),
              got)
        with MI._db() as c:              # make a -wal possible at all
            c.execute("PRAGMA journal_mode=WAL")
            c.commit()
        MI.delete(str(rec))
        files = sorted(CFG.glob("media-index.db*"))
        blob = b"".join(p.read_bytes() for p in files)
        check("after Delete-one, NO index file (including -wal/-shm) contains the word",
              bool(files) and canary.encode() not in blob, [p.name for p in files])
    # Delete ALL: no media-index.db* file at all survives, so nothing can hold it.
    root = fresh("canary-all")
    media_file(root, "two.wav")
    fake = FakeRead({"two": [("the unique word is " + canary, 0.0, 2.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        with MI._db() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.commit()
        MI.search(canary, read=fake)
        MI.delete()
        files = sorted(CFG.glob("media-index.db*"))
        blob = b"".join(p.read_bytes() for p in files)
        check("Delete-all unlinks the db, the -wal and the -shm (nothing left to hold it)",
              files == [], [p.name for p in files])
        check("...and no surviving index file contains the deleted word",
              canary.encode() not in blob, [p.name for p in files])
        check("...and the raw-byte canary count is exactly 0",
              blob.count(canary.encode()) == 0, blob.count(canary.encode()))


def t_search_media_latches_the_private_lane():
    """Gemini's §2 (2026-10-20): a transcript reaching the model must latch the
    turn private, same as every other reading tool, so a later turn cannot be
    offered a cloud lane."""
    calls = []

    class FakeGate:
        @staticmethod
        def latch_taint(*, why=""):
            calls.append(why)
            return True

        @staticmethod
        def taint_active():
            return True

    found = {"ok": True, "words": "found", "matches": [
        {"path": "/r/a.wav", "name": "a.wav", "start": 0.0, "end": 1.0,
         "text": "a stored line"}], "files": 1, "pending": 0}
    empty = {"ok": True, "words": "none", "matches": [], "files": 1, "pending": 0}
    with Env([fresh("taint")]):
        with mock.patch.object(MI, "search", return_value=found), \
                mock.patch.dict(sys.modules, {"jarvis_gate": FakeGate}):
            AG._run_my_files({"action": "search_media", "words": "line"}, None)
        check("a search that returns stored lines latches the turn private",
              calls == ["media_index_search"], calls)
        calls.clear()
        with mock.patch.object(MI, "search", return_value=empty), \
                mock.patch.dict(sys.modules, {"jarvis_gate": FakeGate}):
            AG._run_my_files({"action": "search_media", "words": "line"}, None)
        check("...but a search that found nothing latches nothing", calls == [], calls)


# --------------------------------------------------------------------------
#   5. the switch: ON by default, OFF instant, ON one card
# --------------------------------------------------------------------------

def deny_gate(action, detail, prompt=""):
    class V:
        allowed, outcome, tier, reason = False, "denied", "ask", "denied by a human"
        request_id = None
    return V()


def approve_gate(action, detail, prompt=""):
    class V:
        allowed, outcome, tier, reason = True, "approved", "ask", ""
        request_id = "r1"
    return V()


def t_the_switch_ships_on_and_off_is_instant():
    text = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    twin = (REPO / "jarvis-backend" / "jarvis-framework.toml").read_text(encoding="utf-8")
    section = text.split("[media_index]", 1)[1].split("\n[", 1)[0] \
        if "[media_index]" in text else ""
    check("both shipped framework templates say [media_index] enabled = true",
          "enabled = true" in section and twin == text, section[:80])
    root = fresh("switch")
    media_file(root / "a.wav")
    fake = FakeRead({"a": [("hello", 0.0, 1.0)]})
    with Env([root]):
        check("with no owner file, the shipped default is ON (the owner's override)",
              MI.enabled() is True and MI.settings()["enabled"] is True)
        code, out = MI.request_enabled(False)
        check("turning it OFF is immediate - no card, waiting False",
              code == 200 and out.get("enabled") is False and out.get("waiting") is False,
              (code, out))
        check("...and the very next run reads nothing", MI.search("hello", read=fake)["off"]
              is True and fake.calls == [], fake.calls)
        check("...and says so plainly", "off" in MI.OFF_WORDS.lower())
        code, out = MI.request_enabled(
            True, gate=deny_gate, tier_of=lambda _a: "ask", spawn=lambda fn: fn())
        check("turning it back ON raises a card instead of writing",
              code == 202 and out.get("waiting") is True, (code, out))
        check("...a denied card leaves it OFF and says so",
              MI.enabled() is False
              and (MI.switch_state()["last"] or {}).get("outcome") == "denied",
              MI.switch_state())
        code, out = MI.request_enabled(
            True, gate=approve_gate, tier_of=lambda _a: "ask", spawn=lambda fn: fn())
        check("an approved card turns it ON", MI.enabled() is True, (code, out))
        check("the switch's card words say it keeps readable text until deleted",
              "readable" in MI.SWITCH_CARD.lower() and "delete" in MI.SWITCH_CARD.lower())
        check("...and that OFF is instant", "instant" in MI.SWITCH_CARD.lower())


def t_the_spoken_switch_reaches_the_same_route():
    setting = next((b for b in R.BOOL_SETTINGS if b.key == "media_index"), None)
    check("the settings table has one spoken switch for this feature",
          setting is not None and "searchable recordings" in setting.names,
          getattr(setting, "names", None))
    calls = []
    with mock.patch.object(MI, "request_enabled",
                           side_effect=lambda on: calls.append(bool(on))
                           or (200, {"ok": True, "enabled": bool(on), "waiting": False,
                                     "message": "Off."})):
        out = R.set_media_index(False)
    check("the registry setter calls the module's own request_enabled",
          calls == [False] and out.ok is True, (calls, out))
    my_files = AG.TOOLS["my_files"]
    check("search_media is decided under the existing read-files action (no new tier)",
          my_files.gate_lookup_name({"action": "search_media"}) == "file_read")
    check("...and the action is in the tool's own schema",
          "search_media" in my_files.parameters["properties"]["action"]["enum"])


# --------------------------------------------------------------------------
#   6. gone and moved files leave the index
# --------------------------------------------------------------------------

def t_deleted_and_moved_recordings_leave():
    root = fresh("gone")
    folder = root / "move"
    keep = media_file(folder, "keep.wav")
    gone = media_file(folder, "gone.wav")
    fake = FakeRead({"keep": [("keep this line", 0.0, 1.0)],
                     "gone": [("gone words", 0.0, 1.0)],
                     "renamed": [("keep this line", 0.0, 1.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        check("both recordings start in the index",
              bool(MI.search("keep", read=fake)["matches"])
              and bool(MI.search("gone", read=fake)["matches"]))
        gone.unlink()
        out = MI.reconcile(read=fake)
        check("the next run drops the row for a deleted recording",
              out["dropped"] >= 1 and MI.search("gone", read=fake)["matches"] == [], out)
        check("...and keeps the one that is still there",
              bool(MI.search("keep", read=fake)["matches"]))
        keep.rename(folder / "renamed.wav")
        out = MI.reconcile(read=fake, index_at_most=2)
        check("a moved/renamed recording's old row leaves and the new one arrives",
              out["dropped"] >= 1 and out["indexed"] >= 1
              and bool(MI.search("keep", read=fake)["matches"]), out)


# --------------------------------------------------------------------------
#   7. not a learned fact
# --------------------------------------------------------------------------

def raises_value(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def t_the_index_is_not_a_learned_fact():
    import ast
    tree = ast.parse((HERE / "jarvis_media_index.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    check("the index module imports no memory or learning module",
          not (imported & {"jarvis_memory", "jarvis_auto_learn", "jarvis_chat_log"}),
          sorted(imported))
    check("a my_files read is outside text by the existing rule (no new exception)",
          "my_files" not in AG._NOT_READING)
    with Env([fresh("facts")]):
        with mock.patch.object(MI, "search", return_value={
                "ok": True, "words": "found", "matches": [
                    {"path": "/r/a.wav", "name": "a.wav", "start": 0.0, "end": 1.0,
                     "text": "I love the seaside"}], "files": 1, "pending": 0}):
            got = AG._run_my_files({"action": "search_media", "words": "seaside"}, None)
        text = json.dumps(got).lower()
        check("the tool result carries the stored LINES and no learned fact",
              got.get("ok") is True and got.get("matches")
              and "fact" not in text and "learn" not in text, got)
        check("...and asks for words when none were given",
              raises_value(lambda: AG._prepare_my_files(
                  {"action": "search_media", "words": " "})))


# --------------------------------------------------------------------------
#   8. the route (a drop-in plugin folder; no patch, no core edit)
# --------------------------------------------------------------------------

def t_the_route_reads_switches_and_deletes():
    plugin_dir = REPO / "plugins" / "ready" / "media-index"
    manifest = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    check("the drop-in folder names the module and a handler install",
          manifest.get("module") == "jarvis_media_index"
          and manifest.get("install") == "handler", manifest)
    check("...its loader position is a whole number of its own",
          isinstance(manifest.get("stack_order"), int)
          # 152: after setup's drop-in landed, `sandbox` moved to 151, so this
          # folder takes the first free slot after it (the stack-order suite
          # refuses a tie and would otherwise order the pair by folder name).
          and manifest["stack_order"] == 152, manifest.get("stack_order"))
    check("...and the README says it replaces no patch", "replaces NO patch"
          in (plugin_dir / "README.md").read_text(encoding="utf-8"))

    def handler_class():
        class Handler:
            def do_GET(self):
                raise AssertionError("the core GET handler must not run for our route")

            def do_POST(self):
                raise AssertionError("the core POST handler must not run for our route")
        return Handler

    def call(handler, method, body=None):
        inst = object.__new__(handler)
        inst.path = "/api/media-index"
        inst._send = lambda code, out: {"code": code, "out": out}
        if method == "GET":
            return handler.do_GET(inst)
        return handler.do_POST(inst)

    with Env([fresh("route")]):
        H = handler_class()
        bodies = [b"{}"]
        line = MI.install(H, origin_ok=lambda _h: True, token_ok=lambda _h: True,
                          read_body=lambda _h: bodies[0])
        got = call(H, "GET")
        check("GET /api/media-index reports the switch and the disclosure",
              got["code"] == 200 and "disclosure" in got["out"]
              and got["out"]["enabled"] is True, got)
        bodies[0] = b'{"enabled": false}'
        got = call(H, "POST")
        check("POST off is 200 at once",
              got["code"] == 200 and got["out"].get("enabled") is False, got)
        bodies[0] = b'{"action": "delete"}'
        got = call(H, "POST")
        check("POST delete removes the index and says so",
              got["code"] == 200 and got["out"].get("index_file") is True, got)
        bodies[0] = b'{"enabled": true}'
        got = call(H, "POST")
        check("POST on raises one card (202 waiting), never a write",
              got["code"] == 202 and got["out"].get("waiting") is True, got)
        H2 = handler_class()
        MI.install(H2, origin_ok=lambda _h: False, token_ok=lambda _h: True,
                   read_body=lambda _h: b"{}")
        inst = object.__new__(H2)
        inst.path = "/api/media-index"
        sent = []
        inst._send = lambda code, out: sent.append((code, out))
        H2.do_GET(inst)
        check("a cross-origin read is refused 403 before any data",
              sent and sent[0][0] == 403, sent)
        H3 = handler_class()
        MI.install(H3, origin_ok=lambda _h: True, token_ok=lambda _h: False,
                   read_body=lambda _h: b"{}")
        inst = object.__new__(H3)
        inst.path = "/api/media-index"
        sent = []
        inst._send = lambda code, out: sent.append((code, out))
        H3.do_GET(inst)
        check("a wrong token is 401", sent and sent[0][0] == 401, sent)
        check("...the banner says which state the PC is in", "media-index" in line)


# --------------------------------------------------------------------------
#   9. the saved truths around the switch and the view
# --------------------------------------------------------------------------

def t_no_double_write_and_the_view_is_the_plain_one():
    root = fresh("view")
    media_file(root / "a.wav")
    fake = FakeRead({"a": [("line one", 0.0, 1.0)]})
    with Env([root]):
        MI.reconcile(read=fake)
        MI.reconcile(read=fake)
        check("a second run does not re-read an unchanged recording",
              len(fake.calls) == 1, fake.calls)
        MI.set_enabled(False)
        check("index_file refuses when the switch is off",
              MI.index_file(str(root / "a.wav"), read=fake).get("off") is True)
        MI.set_enabled(True)
        view = MI.view()
        check("the Settings view carries the switch, counts and the one disclosure",
              set(view) >= {"enabled", "files", "lines", "bytes", "disclosure",
                            "pending", "last", "waiting", "index_file"}, sorted(view))
        check("...the disclosure is the plain-language one, word for word",
              view["disclosure"] == MI.DISCLOSURE)
        check("...and the view carries no fact/learned field",
              not (set(view) & {"fact", "facts", "learned", "learned_fact"}))


if __name__ == "__main__":
    for fn in (t_indexes_only_the_listed_folders,
               t_stores_the_readable_text_not_the_media,
               t_search_returns_the_exact_line_with_file_and_time,
               t_delete_really_deletes_and_backups_cannot_restore_it,
               t_a_deleted_word_is_gone_from_every_index_file,
               t_search_media_latches_the_private_lane,
               t_the_switch_ships_on_and_off_is_instant,
               t_the_spoken_switch_reaches_the_same_route,
               t_deleted_and_moved_recordings_leave,
               t_the_index_is_not_a_learned_fact,
               t_the_route_reads_switches_and_deletes,
               t_no_double_write_and_the_view_is_the_plain_one):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
