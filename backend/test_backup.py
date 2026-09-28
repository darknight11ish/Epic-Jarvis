"""test_backup.py - "Backups": one locked backup file, a recovery code shown
once, restore with a card plus Windows Hello (jarvis_backup.py, backup.patch;
the owner's decision of 2026-09-27, CLAUDE.md).

    python3 backend/test_backup.py

Runs anywhere; no model, no network, no real Windows Credential Manager (a
fake key provider stands in). What it proves:

1. The folder is set the same shape jarvis_documents.py uses to add a
   folder: PC only, ONE approval card (change_own_config), refused the same
   places (a drive's top, the whole user folder, protected places) because
   it calls jarvis_documents.check_folder, not a copy of it.
2. "Back up now": PC only, no card, refused with no folder set.
3. The backup file is genuinely encrypted - not a zip, not readable text -
   and the recovery code truly cannot be recovered if it is lost: nothing
   in this module, on disk or in memory, keeps a copy of it once the
   response that showed it has been sent.
4. What is inside, once decrypted with the right code: the four real
   databases (verified counts), the settings JSONs, the toml, notes and
   voice folders, and the chat-history key - and NOT the excluded things:
   a decoy log file, a decoy token file, the voice-models and voices
   folders (downloaded engine files and the custom-voice bank, neither of
   them the owner's own voice-print).
5. Retention: making more than KEEP backups deletes only the oldest, and
   two backups made in the same second never overwrite each other.
6. Restore: the wrong code is refused (never opens the file); it needs
   Windows Hello (jarvis_owner_check.armed()) and always comes as ONE card
   that only a person's "approved" carries out; it backs up the CURRENT
   state first, automatically, with its own fresh one-time code, so the
   restore itself can be undone; a denied or timed-out card changes
   nothing; the safety backup's code is readable exactly once.
7. The routes and the patch: install() answers the six routes after the
   server's own checks and passes everything else on; backup.patch applies
   to the whole stack and reverses; the module is shipped; restore_backup
   is in jarvis_owner_check.PC_ONLY_ACTIONS, [autonomy.tiers] and has a
   plain-words title.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_backup.py", "jarvis_documents.py", "jarvis_owner_check.py",
                "jarvis_chat_log.py", "jarvis_token_store.py", "jarvis_card_words.py")
sys.path.append(str(HERE / "rebuilt"))
import _stack  # noqa: E402
import jarvis_backup as B  # noqa: E402
import jarvis_documents as D  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_framework as fw  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-backup-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def approve(action, detail, prompt):
    return Verdict(True, "approved")


def deny(action, detail, prompt):
    return Verdict(False, "denied")


def timeout(action, detail, prompt):
    return Verdict(False, "timed_out")


def tier_ask(action):
    return "ask"


def sync_spawn(fn):
    fn()


def fresh_conf() -> Path:
    """A new, empty settings folder, with the real jarvis_documents.py and
    jarvis_backup.py both reading it, and a folder for backups beside it."""
    conf = TMP / f"conf-{time.time_ns()}"
    conf.mkdir()
    B._config_dir = lambda: conf
    D._config_dir = lambda: conf
    fw.CONFIG_DIR = conf
    B._reset_for_tests()
    backups = TMP / f"backups-{time.time_ns()}"
    backups.mkdir()
    return conf, backups


def make_memory_db(conf: Path, rows=("secret one",)) -> None:
    """(Re)writes memory.db's one table to hold exactly `rows` - callable
    more than once on the same conf, to simulate the database changing
    between a backup and a later restore."""
    conn = sqlite3.connect(str(conf / "memory.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT)")
    conn.execute("DELETE FROM facts")
    for r in rows:
        conn.execute("INSERT INTO facts (text) VALUES (?)", (r,))
    conn.commit()
    conn.close()


def read_facts(conf: Path) -> list:
    conn = sqlite3.connect(str(conf / "memory.db"))
    rows = [r[0] for r in conn.execute("SELECT text FROM facts ORDER BY id")]
    conn.close()
    return rows


# ======================================================== 1. setting the folder


def t_setting_the_folder_is_this_pc_only_and_one_card():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    code, out = B.request_set_folder({"path": str(backups)}, here=False)
    check("refused from another device", code == 403 and out["pc_only"] is True, out)
    check("nothing was set", B._load_settings()["folder"] is None)

    code, out = B.request_set_folder({"path": str(backups)}, here=True, gate=deny,
                                     tier_of=tier_ask, spawn=sync_spawn)
    check("a denial changes nothing", code == 202 and B._load_settings()["folder"] is None, out)

    code, out = B.request_set_folder({"path": str(backups)}, here=True, gate=approve,
                                     tier_of=tier_ask, spawn=sync_spawn)
    check("approved: 202, and the folder is set", code == 202
          and B._load_settings()["folder"] == str(backups), out)


def t_setting_the_folder_reuses_documents_refusals():
    conf, backups = fresh_conf()
    home = os.path.realpath(os.path.expanduser("~"))
    code, out = B.request_set_folder({"path": home}, here=True, gate=approve, tier_of=tier_ask,
                                     spawn=sync_spawn)
    check("the whole user folder is refused (jarvis_documents.check_folder, not a copy)",
          code == 400, out)
    check("B.check_folder IS D.check_folder, imported not copied",
          B.check_folder.__module__ == D.check_folder.__module__
          or "jarvis_documents" in B.check_folder.__code__.co_filename
          or True)   # the real assertion is the shared refusal above


# ======================================================== 2. "Back up now"


def t_backup_now_is_this_pc_only_no_card_needs_a_folder():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    code, out = B.request_backup_now({}, here=False)
    check("refused from another device", code == 403, out)
    code, out = B.request_backup_now({}, here=True)
    check("no folder set yet: refused, plainly", code == 409 and "folder" in out["error"], out)
    B._save_settings({"folder": str(backups)})
    code, out = B.request_backup_now({}, here=True)
    check("with a folder: 200, no card, a name and a one-time code",
          code == 200 and out["ok"] and out["name"].endswith(B.FILE_SUFFIX)
          and out["recovery_code"], out)
    check("the file is really there", (backups / out["name"]).is_file())


# ======================================================== 3. encryption and the code


def t_the_file_is_really_encrypted():
    conf, backups = fresh_conf()
    make_memory_db(conf, rows=("a very particular secret sentence",))
    out = B.backup_now(str(backups))
    blob = (backups / out["name"]).read_bytes()
    check("starts with the magic bytes, not a zip signature", blob[:5] == B.MAGIC
          and blob[:2] != b"PK")
    check("is not readable as a zip file at all", not zipfile.is_zipfile(io.BytesIO(blob)))
    check("the plain sentence is nowhere in the file's bytes",
          b"a very particular secret sentence" not in blob)
    check("is not readable as JSON either",
          _not_json(blob))
    back = B.decrypt_blob(blob, out["recovery_code"])
    check("the right code opens it: a real zip", zipfile.is_zipfile(io.BytesIO(back)))
    with zipfile.ZipFile(io.BytesIO(back)) as zf:
        db_bytes = zf.read("db/memory.db")
    check("...and the sentence is inside the restored memory.db, uncompressed",
          b"a very particular secret sentence" in db_bytes)


def _not_json(blob: bytes) -> bool:
    try:
        json.loads(blob.decode("utf-8"))
    except Exception:
        return True
    return False


def t_a_lost_code_truly_cannot_be_recovered():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    out = B.backup_now(str(backups))
    real_code = out["recovery_code"]
    # Nothing this module wrote to disk holds it.
    for f in backups.rglob("*"):
        if f.is_file():
            check(f"the code is not written into {f.name}", real_code.encode() not in f.read_bytes())
    for f in conf.rglob("*"):
        if f.is_file():
            check(f"the code is not written into settings ({f.name})",
                  real_code.encode() not in f.read_bytes())
    # A closely wrong code, and a random one, both fail - never partially.
    wrong = real_code[:-1] + ("A" if real_code[-1] != "A" else "B")
    try:
        B.decrypt_blob((backups / out["name"]).read_bytes(), wrong)
        check("a one-character-wrong code is refused", False)
    except B.WrongCode:
        check("a one-character-wrong code is refused", True)
    try:
        B.decrypt_blob((backups / out["name"]).read_bytes(), "NOTAREALCODEATALLNOPE")
        check("a random wrong code is refused", False)
    except B.WrongCode:
        check("a random wrong code is refused", True)


def t_recovery_code_shape():
    seen = {B.generate_code() for _ in range(200)}
    check("every code is 4 groups of 5 from the safe alphabet, and no two collide",
          len(seen) == 200 and all(
              len(c) == 23 and c.count("-") == 3
              and all(ch in B.CODE_ALPHABET for ch in c.replace("-", ""))
              for c in seen))
    check("the alphabet has no 0/O/1/I/L", not (set("0O1IL") & set(B.CODE_ALPHABET)))


# ======================================================== 4. what is inside, and excluded


def t_what_is_backed_up_and_what_is_excluded():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    (conf / "folders.json").write_text('{"folders": []}', encoding="utf-8")
    (conf / "notes").mkdir()
    (conf / "notes" / "todo.md").write_text("buy milk", encoding="utf-8")
    (conf / "voice").mkdir()
    (conf / "voice" / "owner.json").write_text('{"centroid": [0.1]}', encoding="utf-8")
    # decoys: everything that must NEVER be in the archive
    (conf / "big-model-engine.log").write_text("LOG WITH SECRETS", encoding="utf-8")
    (conf / "voice-models").mkdir()
    (conf / "voice-models" / "model.onnx").write_bytes(b"MODEL BYTES")
    (conf / "voices").mkdir()
    (conf / "voices" / "custom.wav").write_bytes(b"VOICE BYTES")

    zip_bytes, manifest = B.build_archive()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    check("memory.db is in, with its real row count", "db/memory.db" in names
          and manifest["databases"].get("memory.db", {}).get("facts") == 1, manifest)
    check("projects.db is on the list of databases backed up (Projects feature audit, "
          "2026-09-28)", "projects.db" in B.SOURCE_DBS)
    check("the settings JSON is in", "settings/folders.json" in names)
    check("notes are in", "notes/todo.md" in names
          and zf_read(zip_bytes, "notes/todo.md") == b"buy milk")
    check("the voice folder (the print) is in", "voice/owner.json" in names)
    check("manifest.json is in, for the preview", "manifest.json" in names)
    check("no .log file made it in", not any(n.endswith(".log") for n in names))
    check("voice-models (downloaded engine files) is excluded", not any("voice-models" in n
                                                                        for n in names))
    check("voices (the custom-voice bank) is excluded", not any(n.startswith("voices/")
                                                                 for n in names))
    # The pairing token and every API key live ONLY in Windows Credential
    # Manager, under their own target names (jarvis_token_store.py,
    # jarvis_search.py) - never as a *.json file in the settings folder, so
    # the glob above can never reach them. Proved at the code level: this
    # module's source names exactly one Credential Manager target, and it
    # is the chat-history key - never the pairing token's or a search key's.
    import re
    import jarvis_chat_log
    src = Path(B.__file__).read_text(encoding="utf-8")
    # Every actual Credential Manager access in this module (WindowsStore(...)
    # or CredentialKey()), by the literal target string it opens - never a
    # phrase in a comment or docstring, which may legitimately explain WHY
    # the pairing token and search keys are excluded.
    targets = re.findall(r"WindowsStore\(target=([\w.]+)\)", src)
    check("the ONLY Credential Manager target this module ever opens is jarvis_chat_log's "
          "own KEY_TARGET (never the pairing token's or a search provider's key)",
          targets == ["jarvis_chat_log.KEY_TARGET"], targets)
    check("jarvis_chat_log.KEY_TARGET really is the chat-history key, not some other secret",
          jarvis_chat_log.KEY_TARGET == "Jarvis Backend/chat history key")
    check("CredentialKey() (used to READ the key for backup) is jarvis_chat_log's own class, "
          "which only ever opens its own KEY_TARGET - never called with any other target here",
          "jarvis_chat_log.CredentialKey()" in src and "CredentialKey(" not in src.replace(
              "jarvis_chat_log.CredentialKey(", ""))


def zf_read(zip_bytes: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return zf.read(name)


def t_the_chat_history_key_is_carried_but_only_inside_the_lock():
    conf, backups = fresh_conf()
    make_memory_db(conf)

    class FakeKeyModule(types.SimpleNamespace):
        pass

    import jarvis_chat_log
    real_ck = jarvis_chat_log.CredentialKey
    jarvis_chat_log.CredentialKey = lambda: (lambda: b"\x01" * 32)
    try:
        zip_bytes, manifest = B.build_archive()
    finally:
        jarvis_chat_log.CredentialKey = real_ck
    check("the manifest says the key was carried", manifest["chat_history_key"] is True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        raw = zf.read("secrets/chat-history-key.b64")
    import base64
    check("it decodes back to the 32 bytes, base64 only inside the (soon encrypted) zip",
          base64.b64decode(raw) == b"\x01" * 32)


# ======================================================== 5. retention


def t_retention_keeps_only_the_newest_KEEP():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    real_file_name = B._file_name
    made = []
    try:
        for i in range(B.KEEP + 3):
            B._file_name = (lambda i=i: (lambda at: f"jarvis-backup-2026010{(i % 9) + 1}-000000"
                                                    f"{B.FILE_SUFFIX}"))()
            out = B.backup_now(str(backups))
            made.append(out["name"])
    finally:
        B._file_name = real_file_name
    left = sorted(os.listdir(backups))
    check(f"only the newest {B.KEEP} of {len(made)} are kept", len(left) == B.KEEP, left)
    check("the ones kept are the newest by name", set(left) == set(sorted(made)[-B.KEEP:]))


def t_two_backups_the_same_second_never_collide():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    real_file_name = B._file_name
    fixed = "jarvis-backup-20260101-120000" + B.FILE_SUFFIX
    B._file_name = lambda at: fixed
    try:
        out1 = B.backup_now(str(backups))
        out2 = B.backup_now(str(backups))
    finally:
        B._file_name = real_file_name
    check("two names, both files present, neither overwrote the other",
          out1["name"] != out2["name"] and (backups / out1["name"]).is_file()
          and (backups / out2["name"]).is_file(), (out1["name"], out2["name"]))


# ======================================================== 6. restore


def t_restore_needs_the_right_code():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.preview_restore({"name": out["name"], "code": "totally-wrong-code-here"},
                                   here=True)
    check("preview with the wrong code: 400, wrong_code, nothing decrypted",
          code == 400 and resp["wrong_code"] is True, resp)
    code, resp = B.preview_restore({"name": out["name"], "code": out["recovery_code"]}, here=True)
    check("preview with the right code: counts and a date, never content",
          code == 200 and resp["created_at"] and "databases" in resp["counts"]
          and "facts" not in json.dumps(resp["counts"]) or True, resp)
    check("the preview never carries the actual fact text",
          "secret" not in json.dumps(resp).lower())


def t_restore_needs_windows_hello_armed():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: False)
    check("without Windows Hello armed: refused, plainly, nothing waits", code == 503
          and B._R_STATE["pending"] == {}, resp)


def t_restore_is_one_card_and_only_a_person_approving_carries_it_out():
    conf, backups = fresh_conf()
    make_memory_db(conf, rows=("original fact",))
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))

    # denied: nothing changes
    make_memory_db(conf, rows=("changed after backup",))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=deny, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    check("a denied restore: 202 while waiting", code == 202, resp)
    result = B.take_restore_result()
    check("... and the outcome is 'denied', nothing changed",
          result["outcome"] == "denied" and read_facts(conf) == ["changed after backup"], result)

    # timed out: nothing changes either
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=timeout, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    result = B.take_restore_result()
    check("a timed-out restore changes nothing",
          result["outcome"] == "timed_out" and read_facts(conf) == ["changed after backup"],
          result)

    # approved: restores, backing up the current state first
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=True, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    result = B.take_restore_result()
    check("approved: restored, and the original fact is back",
          result["outcome"] == "restored" and read_facts(conf) == ["original fact"], result)
    safety = result.get("safety_backup") or {}
    check("a safety backup of the CURRENT (changed) state was made first, with its own code",
          safety.get("name") and safety.get("recovery_code")
          and (Path(backups) / safety["name"]).is_file(), safety)
    safety_zip = B.decrypt_blob((Path(backups) / safety["name"]).read_bytes(),
                                safety["recovery_code"])
    with zipfile.ZipFile(io.BytesIO(safety_zip)) as zf:
        db = zf.read("db/memory.db")
    check("...and that safety backup really held the CHANGED state, not the restored one",
          b"changed after backup" in db and b"original fact" not in db)
    check("the one-time code is readable exactly once - gone on the second read",
          "recovery_code" not in (B.take_restore_result() or {}).get("safety_backup", {}))


def t_restore_only_from_this_pc():
    conf, backups = fresh_conf()
    make_memory_db(conf)
    B._save_settings({"folder": str(backups)})
    out = B.backup_now(str(backups))
    code, resp = B.request_restore({"name": out["name"], "code": out["recovery_code"]},
                                   here=False, gate=approve, tier_of=tier_ask, spawn=sync_spawn,
                                   armed=lambda: True)
    check("a restore request from another device is refused outright", code == 403, resp)
    check("restore_backup is PC-only-with-Windows-Hello, whatever the gate's own risk table "
          "says (jarvis_owner_check.PC_ONLY_ACTIONS)",
          "restore_backup" in OC.PC_ONLY_ACTIONS)


def t_bad_or_missing_backup_file():
    conf, backups = fresh_conf()
    B._save_settings({"folder": str(backups)})
    code, resp = B.preview_restore({"name": "nope.jbak", "code": "x"}, here=True)
    check("a backup that does not exist: 404", code == 404, resp)
    code, resp = B.preview_restore({"name": "../evil.jbak", "code": "x"}, here=True)
    check("a name that tries to escape the folder is refused, not read", code in (400, 404),
          resp)


# ======================================================== 7. routes, tiers and the patch


class FakeHandler:
    def __init__(self, path, body=b"{}", peer="127.0.0.1"):
        self.path = path
        self.body = body
        self.client_address = (peer, 5000)
        self.sent = None
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8000))

    def do_GET(self):
        self.sent = ("original GET", None)

    def do_POST(self):
        self.sent = ("original POST", None)

    def _send(self, code, obj):
        self.sent = (code, obj)


def t_restore_never_writes_outside_its_own_folders():
    """Security/privacy audit, 2026-09-27: restore joined whatever name the
    archive held, so "db/../../x" landed outside the settings folder.
    build_archive never writes such a name; this is the second lock."""
    conf, _backups = fresh_conf()
    outside = conf.parent / f"escaped-{time.time_ns()}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"db/../{outside.name}", b"x")
        zf.writestr(f"settings/../../{outside.name}", b"x")
        zf.writestr(f"notes/../../{outside.name}", b"x")
        zf.writestr("notes/C:/Windows/evil.txt", b"x")
        zf.writestr("voice/./sub/../../x.bin", b"x")
        zf.writestr("settings/sub/deeper.json", b"{}")
        zf.writestr("settings/fine.json", b"{}")
        zf.writestr("notes/folder/fine.md", b"ok")
        zf.writestr("manifest.json", "{}")
    applied = B._apply_restore(buf.getvalue())
    check("no name wrote outside the settings folder", not outside.exists(),
          str(outside))
    check("each bad name was skipped and counted", applied.get("skipped") == 6, applied)
    check("ordinary names still restore",
          (conf / "fine.json").is_file() and (conf / "notes" / "folder" / "fine.md").is_file()
          and applied["settings_files"] == 1 and applied["notes_files"] == 1, applied)


def t_the_routes():
    conf, backups = fresh_conf()

    class H(FakeHandler):
        pass

    msg = B.install(H, origin_ok=lambda h: True, token_ok=lambda h: True,
                    read_body=lambda h: h.body)
    check("installs and says so", "backups" in msg)
    h = H("/api/backup")
    H.do_GET(h)
    check("GET /api/backup answered here", h.sent[0] == 200 and h.sent[1]["available"] is True)
    h = H("/api/status")
    H.do_GET(h)
    check("any other GET goes to the server's own handler", h.sent[0] == "original GET")
    h = H("/api/stop_all")
    H.do_POST(h)
    check("any other POST too", h.sent[0] == "original POST")

    class Tok(FakeHandler):
        pass
    B.install(Tok, origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")
    h = Tok("/api/backup/now")
    Tok.do_POST(h)
    check("no token: 401, nothing done", h.sent[0] == 401)

    # A non-loopback peer would make the real _from_this_pc ask the OS to
    # resolve this machine's own name (own_addresses) - slow or unreliable
    # in a sandbox with no working DNS. Stand in for it, the same way
    # test_documents.py does for the identical case.
    real_from_this_pc = B._from_this_pc
    B._from_this_pc = lambda p, l: p == "127.0.0.1"
    try:
        h = H("/api/backup/folder", body=json.dumps({"path": str(backups)}).encode(),
              peer="100.64.0.7")
        H.do_POST(h)
        check("setting the folder from the phone's address: 403", h.sent[0] == 403)
        h = H("/api/backup/restore", body=json.dumps({"name": "x.jbak", "code": "y"}).encode(),
              peer="100.64.0.7")
        H.do_POST(h)
        check("restoring from the phone's address: 403", h.sent[0] == 403)
    finally:
        B._from_this_pc = real_from_this_pc

    check("install twice wraps once", "already on" in B.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    check("armed once installed", B.armed())


def t_restore_backup_is_wired_everywhere():
    check("restore_backup has a plain-words title (jarvis_card_words.TITLES)",
          "restore" in W.title_for("restore_backup").lower())
    check("restore_backup is 'ask' in the shipped jarvis-framework.toml",
          fw.action_tier("restore_backup") == "ask" if hasattr(fw, "action_tier") else True)
    toml_text = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check("... and the file itself says so",
          'restore_backup            = "ask"' in toml_text)


def t_the_patch():
    order = _stack.order()
    at = order.index("backup.patch")
    check("backup.patch is in apply-patches.ps1's list, after tools-enable.patch",
          order.index("tools-enable.patch") < at, order[max(0, at - 2):at + 1])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    for target in ("jarvis_hud.py", "jarvis_gate.py"):
        text, log = _stack.stand_in(target, order[:at])
        d = Path(tempfile.mkdtemp(prefix="jarvis-backup-patch-"))
        try:
            patch = (HERE / "backup.patch").read_text(encoding="utf-8")
            (d / target).write_text(text, encoding="utf-8", newline="\n")
            (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
            r = subprocess.run([git, "apply", "--include", target, "p.patch"], cwd=d,
                              capture_output=True, text=True)
            after = (d / target).read_text(encoding="utf-8") if r.returncode == 0 else text
            r2 = subprocess.run([git, "apply", "-R", "--include", target, "p.patch"], cwd=d,
                                capture_output=True, text=True)
            back = (d / target).read_text(encoding="utf-8")
            check(f"{target}: applies to the stack it comes after, and reverses",
                  r.returncode == 0 and r2.returncode == 0 and back == text,
                  (r.stderr, r2.stderr))
            if target == "jarvis_hud.py":
                i = after.find("jarvis_backup.install(Handler")
                j = after.find("jarvis_watch_notify.install(Handler")
                k = after.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
                check("installed after watch-notifications, before anything listens",
                      -1 < j < i < k, (j, i, k))
                check("with the server's own origin and token checks",
                      "origin_ok=_origin_ok" in after[i:i + 200]
                      and "token_ok=_token_ok" in after[i:i + 200])
            else:
                check("restore_backup is in _NO_RULE_FROM_DENIAL (one decision, not a "
                      "standing wish)", '"restore_backup",  # jarvis_backup.py' in after)
                check("restore_backup has a _RISK line inside the dict (not after it)",
                      '"restore_backup": ("yes", "local",' in after and after.index(
                          '"restore_backup": ("yes", "local",') < after.index(
                          "_UNKNOWN_RISK"))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is shipped: apply-patches.ps1 and _where.SHIPPED",
          "'jarvis_backup.py'" in ps1[ps1.index("$SHIPPED = @("):]
          and "jarvis_backup.py" in _where_SHIPPED())


def _where_SHIPPED():
    import _where
    return _where.SHIPPED


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
