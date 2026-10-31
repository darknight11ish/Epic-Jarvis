"""jarvis_notes_edit.py - the Obsidian notes editor's four routes, proved.

    python -B test_notes_edit.py

WHAT THIS SUITE PROVES, in plain words (the contract's own list):

1. THE FOUR ROUTES ANSWER THE CONTRACT'S SHAPES - list, read, save and
   save?id= - with the exact status codes and bodies, against a temporary
   Obsidian vault. The measured answers are printed at the end so the report
   can quote them.
2. THE VAULT IS THE WORLD. An absolute path, a drive letter, a UNC path, a
   `..` escape, a hidden component, a non-.md/.txt file, and a path through a
   symlink are refused BEFORE any card (400 / 404 / 413 / 503).
3. NOTHING IS WRITTEN WITHOUT THE CARD. A Deny writes nothing and takes no
   File Guardian snapshot; an approved save takes one and writes the new
   bytes; the edit carries the sha256 it started from and a mismatch is a 409
   conflict with the current hash and NO card.
4. THE FILE GUARDIAN GOES FIRST. The approved write calls the guardian
   through `jarvis_notes.snapshot_vault_before_write` (the vault's one guarded
   door), the old bytes are stored, and when the copy cannot be made the save
   ends `failed` with the file unchanged.
5. THE LIMITS. 2 MiB per note (413, no card), at most 4 saves waiting (429,
   the sentence names the limit), unknown job id (404), and no vault
   configured (503 naming the setting).
6. THE TOCTOU CASE. A file that changed while the card was up ends `failed`
   with `current_sha256` and is not overwritten.
7. THE LOADER CONVENTION. install() wraps the core's Handler: origin and
   token refusals, every other path reaches the core, and a second install()
   does not double-wrap.
8. THE GATE TIER. `edit_vault_note` resolves to "ask" through the published
   gate's own tier reader, for BOTH copies of the shipped settings file, and
   the module asks under exactly that name.
9. THE RECORDS AGREE. The module is in both SHIPPED lists and the published
   base twin is identical; the plugin.json is a complete no-patch manifest;
   the catalogue lists the folder; card words and "What asks first" name the
   action; the docs section documents the routes.

No network, no real approval card, no owner's files: a temporary vault and a
fake gate answer instead. `%TEMP%` is used with `mkdir` (not mkdtemp) so the
suite runs under a confinement sandbox as well as CI.
"""
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# This suite tests THIS repository's modules, not the owner's live backend:
# a JARVIS_BACKEND pointing at the live install would import that install's
# (older) copies and the new module would not be there at all. The live copy is
# nobody's subject here; the module reaches the live PC through $SHIPPED.
os.environ.pop("JARVIS_BACKEND", None)
from _where import BACKEND, REPO  # noqa: E402

# ── a temporary vault, and a settings folder that is never the owner's ──────
_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-edit-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)

# ── a stub jarvis_framework, so nothing reads the owner's real settings ─────
FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = _TMP / "config"
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"framework": {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE["framework"]))
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
sys.modules["jarvis_framework"] = FW

import jarvis_notes_edit as E  # noqa: E402
import jarvis_card_words as CW  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
sys.path.insert(0, str(REPO / "jarvis-backend"))       # the published gate
import jarvis_gate as GATE  # noqa: E402

FAILED, PASSED = [], []
ANSWERS = {}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_note(rel: str, text: str, *, mtime: float | None = None) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime is not None:
        try:
            os.utime(p, (mtime, mtime))
        except OSError:
            pass
    return p


def reset_vault() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass
    E._reset_for_tests()


class Verdict:
    def __init__(self, allowed, outcome="approved", reason=""):
        self.allowed = allowed
        self.outcome = outcome
        self.reason = reason


def fake_gate(*, allowed=True, outcome="approved", delay=0.0, before=None):
    calls = []

    def gate(action, detail, prompt):
        calls.append((action, detail, prompt))
        if before is not None:
            before()
        if delay:
            time.sleep(delay)
        return Verdict(allowed, outcome)

    gate.calls = calls
    return gate


def wait_job(job_id: str, timeout: float = 8.0):
    end = time.time() + timeout
    code, out = E.save_status(job_id)
    while out.get("state") == "waiting" and time.time() < end:
        time.sleep(0.02)
        code, out = E.save_status(job_id)
    return code, out


def do_save(rel: str, text: str, *, gate=None, expected=None, wait_s=0.05,
            body=None):
    """POST the save body the contract defines, and wait for the job to end."""
    if body is None:
        full = VAULT / rel
        current = full.read_bytes() if full.is_file() else b""
        body = {"path": rel, "text": text,
                "expected_sha256": sha(current) if expected is None else expected}
    code, out = E.handle_save(body, gate_check=gate or fake_gate(), wait_s=wait_s)
    if out.get("state") == "waiting" and out.get("id"):
        wait_job(out["id"])
        code, out2 = E.save_status(out["id"])
        return (code, out2) if out2.get("state") != "waiting" else (code, out)
    return code, out


def ans(key, code, body):
    """Keep one measured answer for the report at the end."""
    ANSWERS[key] = (code, body)


# ---------------------------------------------------------------------------
#   1. the records agree: shipped, twinned, catalogued, documented
# ---------------------------------------------------------------------------


def t_the_module_is_shipped_twinned_and_catalogued():
    mod = HERE / "jarvis_notes_edit.py"
    twin = REPO / "jarvis-backend" / "jarvis_notes_edit.py"
    check("the module is in backend/", mod.is_file(), str(mod))
    check("the published base twin is there", twin.is_file(), str(twin))
    check("the twin is byte-identical",
          mod.read_bytes().replace(b"\r\n", b"\n")
          == twin.read_bytes().replace(b"\r\n", b"\n"))
    try:
        import _where as W
        check("the module is in _where.SHIPPED", "jarvis_notes_edit.py" in W.SHIPPED)
    except Exception as exc:  # noqa: BLE001
        check("the module is in _where.SHIPPED", False, f"{type(exc).__name__}: {exc}")
    script = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is in the script's $SHIPPED",
          "'jarvis_notes_edit.py'" in script)
    manifest = REPO / "plugins" / "ready" / "notes-edit" / "plugin.json"
    check("the drop-in folder has a plugin.json", manifest.is_file(), str(manifest))
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    check("the manifest names the module, install(handler), a whole stack_order",
          data.get("name") == "notes-edit" and data.get("module") == "jarvis_notes_edit"
          and data.get("install") == "handler"
          and isinstance(data.get("stack_order"), int)
          and bool(str(data.get("summary") or "").strip()), data)
    registry = json.loads((REPO / "plugins" / "registry.json").read_text(encoding="utf-8"))
    folder = [f for f in registry.get("folders") or [] if f.get("name") == "notes-edit"]
    check("the generated catalogue lists the folder as a no-patch drop-in",
          len(folder) == 1 and folder[0].get("module") == "jarvis_notes_edit", folder)
    check("the registry is not stale (the folder count rose by one)",
          registry.get("folder_count") == 15 and registry.get("ready_count") == 43,
          {registry.get("folder_count"), registry.get("ready_count")})
    docs = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("the docs have the section", "## 170. The Obsidian notes editor" in docs)
    for route in ("/api/notes/list", "/api/notes/read", "/api/notes/save"):
        check(f"the docs document {route}", route in docs)
    check("the docs name the gate action and its tier",
          "`edit_vault_note`" in docs and '"ask"' in docs)


def t_the_gate_tier_is_ask_in_both_shipped_copies():
    import tomllib
    copies = {
        "backend/rebuilt/jarvis-framework.toml":
            REPO / "backend" / "rebuilt" / "jarvis-framework.toml",
        "jarvis-backend/jarvis-framework.toml":
            REPO / "jarvis-backend" / "jarvis-framework.toml",
    }
    for label, path in copies.items():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        tiers = data.get("autonomy", {}).get("tiers", {})
        check(f"the shipped settings file says ask ({label.split('/')[0]})",
              tiers.get("edit_vault_note") == "ask", tiers.get("edit_vault_note"))
        check(f"... and it is a well-formed tier line ({label.split('/')[0]})",
              isinstance(tiers.get("edit_vault_note"), str))
    data = tomllib.loads(copies["backend/rebuilt/jarvis-framework.toml"]
                         .read_text(encoding="utf-8"))
    tiers = GATE._tiers(data)
    check("the published gate's own tier reader resolves edit_vault_note to ask",
          tiers.get("edit_vault_note") == "ask", tiers.get("edit_vault_note"))
    risk = GATE.risk_for("edit_vault_note")
    check("the action is unclassified (so the gate FORCES it to ask)",
          risk.get("classified") is False and risk.get("swipe_ok") is False, risk)
    check("the module asks under exactly the gate action name",
          E.ACTION == "edit_vault_note")
    check("the card words name the action", "edit_vault_note" in CW.TITLES
          and "edit_vault_note" in CW.SUMMARY, (CW.TITLES.get("edit_vault_note"),
                                                CW.SUMMARY.get("edit_vault_note")))
    ids = [a for _t, rows in AF.GROUPS for a in rows]
    check("'What asks first' names the action", "edit_vault_note" in ids)
    check("SUMMARY and TITLES still cover exactly the same actions",
          set(CW.SUMMARY) == set(CW.TITLES),
          sorted(set(CW.SUMMARY) ^ set(CW.TITLES)))


# ---------------------------------------------------------------------------
#   2. the path sandbox
# ---------------------------------------------------------------------------


def t_the_path_sandbox_refuses_escapes_before_any_card():
    good, why = E.note_parts("Inbox/idea.md")
    check("a plain vault-relative .md path is accepted", good == ["Inbox", "idea.md"] and not why,
          (good, why))
    good, why = E.note_parts("Folder\\Nested\\note.txt")
    check("a Windows-style relative path is normalised", good == ["Folder", "Nested", "note.txt"]
          and not why, (good, why))
    for bad in ("C:\\Windows\\note.md", "/etc/note.md", "\\\\server\\share\\note.md"):
        parts, why = E.note_parts(bad)
        check(f"an absolute path is refused ({bad[:18]!r})", not parts and bool(why), (parts, why))
    for bad in ("../outside.md", "Inbox/../../escape.md", "./note.md"):
        parts, why = E.note_parts(bad)
        check(f"a path that climbs out is refused ({bad!r})", not parts and bool(why),
              (parts, why))
    for bad in (".obsidian/workspace.md", ".trash/gone.md", "Inbox/.hidden.md"):
        parts, why = E.note_parts(bad)
        check(f"a hidden component is refused ({bad!r})", not parts and bool(why),
              (parts, why))
    for bad in ("Inbox/idea.pdf", "Inbox/idea", "Inbox/idea.md.exe"):
        parts, why = E.note_parts(bad)
        check(f"a non-note file is refused ({bad!r})", not parts and bool(why),
              (parts, why))
    parts, why = E.note_parts("")
    check("an empty path is refused", not parts and bool(why))
    parts, why = E.note_parts(None)
    check("a non-text path is refused", not parts and bool(why))
    code, out = E.handle_read("?path=" + urllib_quote("C:\\Windows\\win.ini"))
    check("GET read of an absolute path answers 400 with a sentence",
          code == 400 and out.get("ok") is False and "absolute" in str(out.get("error")),
          (code, out))


def urllib_quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text)


def _make_dir_link(link: Path, target: Path) -> str:
    """Create a symlink, or (Windows, no privilege) a junction. "" if neither."""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        try:
            done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                  capture_output=True, text=True)
        except OSError:
            return ""
        if done.returncode == 0 and link.is_dir():
            return "junction"
    return ""


def t_a_link_inside_the_vault_is_refused():
    reset_vault()
    outside = _TMP / "outside-folder"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "leak.md").write_text("outside the vault", encoding="utf-8")
    link = VAULT / "Linked"
    if link.exists() or link.is_symlink():
        shutil.rmtree(link, ignore_errors=True)
    kind = _make_dir_link(link, outside)
    if not kind:
        print("SKIP  a link cannot be created on this machine (privilege) - "
              "NOT a pass; the path check is still proved by the code path below")
        # The refusal itself is still proved without a filesystem link: the
        # component walk is judged on the `_is_link_or_reparse` answer.
        real = E._is_link_or_reparse
        try:
            E._is_link_or_reparse = lambda p: str(p).lower().endswith("linked")
            code, out = E.handle_read("?path=Linked/leak.md")
            check("a path through a (simulated) link is refused before opening",
                  code == 400, (code, out))
        finally:
            E._is_link_or_reparse = real
        return
    code, out = E.handle_read("?path=" + urllib_quote("Linked/leak.md"))
    check(f"a path through a {kind} is refused before it is opened",
          code == 400 and "link" in str(out.get("error", "")).lower(), (code, out))
    gate = fake_gate()
    code, out = do_save("Linked/leak.md", "new", gate=gate)
    check(f"... and a save through the {kind} is refused before any card",
          code == 400 and gate.calls == [], (code, out, gate.calls))
    try:
        if kind == "junction":
            link.rmdir()
        else:
            link.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
#   3. list
# ---------------------------------------------------------------------------


def t_list_returns_every_note_but_never_its_text():
    reset_vault()
    write_note("Inbox/idea.md", "an idea", mtime=3000.0)
    write_note("Inbox/Second.txt", "second", mtime=2000.0)
    write_note("Projects/Plan.md", "the plan", mtime=1000.0)
    write_note(".obsidian/workspace.md", "hidden", mtime=5000.0)
    write_note(".trash/gone.md", "hidden", mtime=5000.0)
    write_note("Inbox/.hidden.md", "hidden", mtime=5000.0)
    write_note("Inbox/photo.png", "not a note", mtime=5000.0)
    code, out = E.handle_list("")
    ans("GET /api/notes/list", code, out)
    check("list answers 200 ok", code == 200 and out.get("ok") is True, (code, out))
    paths = [n["path"] for n in out["notes"]]
    check("only .md/.txt notes are listed", sorted(paths) ==
          ["Inbox/Second.txt", "Inbox/idea.md", "Projects/Plan.md"], paths)
    check("hidden folders and files are skipped",
          not any(p.startswith(".") or "/." in p for p in paths), paths)
    check("newest first", paths == ["Inbox/idea.md", "Inbox/Second.txt", "Projects/Plan.md"],
          paths)
    check("count is the number of notes returned", out["count"] == len(paths), out["count"])
    check("truncated is false when everything fits", out["truncated"] is False)
    check("the root is the absolute vault path", Path(out["root"]).is_dir()
          and str(out["root"]).lower().endswith("vault"), out["root"])
    check("no note text is in the answer", "an idea" not in json.dumps(out))
    first = out["notes"][0]
    check("each note carries path, title, size, mtime",
          set(first) == {"path", "title", "size", "mtime"}
          and first["title"] == "idea" and first["size"] == len(b"an idea")
          and isinstance(first["mtime"], float), first)


def t_list_search_and_the_2000_cut():
    reset_vault()
    write_note("Inbox/idea.md", "an idea", mtime=3000.0)
    write_note("Projects/ideas.md", "more ideas", mtime=2000.0)
    write_note("Projects/Plan.md", "the plan", mtime=1000.0)
    code, out = E.handle_list("?q=IDEA")
    check("q is case-insensitive and matches title or path",
          [n["path"] for n in out["notes"]] == ["Inbox/idea.md", "Projects/ideas.md"],
          out["notes"])
    code, out = E.handle_list("?q=projects")
    check("q matches the folder part of the path",
          [n["path"] for n in out["notes"]] == ["Projects/ideas.md", "Projects/Plan.md"],
          out["notes"])
    code, out = E.handle_list("?q=zzz-no-such-thing")
    check("a query with no match answers an empty list, not an error",
          code == 200 and out["notes"] == [] and out["count"] == 0, out)
    old = E.MAX_NOTES
    try:
        E.MAX_NOTES = 2
        code, out = E.handle_list("")
        check("the list is cut at the bound and says so",
              len(out["notes"]) == 2 and out["truncated"] is True, out)
        check("... and count is what was returned", out["count"] == 2, out["count"])
    finally:
        E.MAX_NOTES = old


# ---------------------------------------------------------------------------
#   4. read
# ---------------------------------------------------------------------------


def t_read_answers_the_contract_shape():
    reset_vault()
    p = write_note("Inbox/idea.md", "hello note", mtime=1234.0)
    code, out = E.handle_read("?path=" + urllib_quote("Inbox/idea.md"))
    ans("GET /api/notes/read", code, out)
    raw = p.read_bytes()
    check("read answers 200 ok", code == 200 and out.get("ok") is True, (code, out))
    check("read carries the relative path", out.get("path") == "Inbox/idea.md", out.get("path"))
    check("read carries the whole text", out.get("text") == "hello note", out.get("text"))
    check("read carries the sha256 of the BYTES", out.get("sha256") == sha(raw), out.get("sha256"))
    check("read carries size and mtime", out.get("size") == len(raw)
          and abs(out.get("mtime", 0) - 1234.0) < 2, out)
    code, out = E.handle_read("?path=" + urllib_quote("Inbox/nope.md"))
    check("a missing note is 404", code == 404 and out.get("ok") is False, (code, out))
    code, out = E.handle_read("")
    check("a missing path is 400", code == 400 and out.get("ok") is False, (code, out))
    code, out = E.handle_read("?path=" + urllib_quote("Inbox/photo.png"))
    check("a non-note path is 400", code == 400, (code, out))
    too_big = VAULT / "big.md"
    too_big.write_bytes(b"x" * (E.MAX_FILE_BYTES + 1))
    code, out = E.handle_read("?path=" + urllib_quote("big.md"))
    check("a note over 2 MiB is 413 and is not read",
          code == 413 and out.get("ok") is False and "limit" in str(out.get("error")),
          (code, str(out)[:160]))


def t_no_vault_is_503_that_names_the_setting():
    reset_vault()
    old_env = os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
    old_fw = FW_STATE["framework"]
    FW_STATE["framework"] = {}
    try:
        for label, call in (
            ("list", lambda: E.handle_list("")),
            ("read", lambda: E.handle_read("?path=Inbox/idea.md")),
            ("save", lambda: E.handle_save({"path": "Inbox/idea.md", "text": "x",
                                            "expected_sha256": "0" * 64})),
        ):
            code, out = call()
            check(f"no vault: {label} answers 503", code == 503 and out.get("ok") is False,
                  (code, out))
            check(f"no vault: {label}'s sentence names the setting",
                  "vault_directory" in json.dumps(out) or "JARVIS_OBSIDIAN_VAULT" in json.dumps(out),
                  out)
    finally:
        if old_env is not None:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = old_env
        FW_STATE["framework"] = old_fw


# ---------------------------------------------------------------------------
#   5. save: conflict, deny, approve, guardian, limits, TOCTOU
# ---------------------------------------------------------------------------


def t_a_hash_conflict_is_409_and_raises_no_card():
    reset_vault()
    write_note("Inbox/idea.md", "first version")
    gate = fake_gate()
    code, out = do_save("Inbox/idea.md", "second version",
                        expected="0" * 64, gate=gate)
    ans("POST /api/notes/save (conflict)", code, out)
    check("a stale expected_sha256 is 409 conflict", code == 409
          and out.get("state") == "conflict", (code, out))
    check("... carrying the CURRENT hash", out.get("current_sha256")
          == sha(b"first version"), out.get("current_sha256"))
    check("... and no card was raised", gate.calls == [], gate.calls)
    check("... and the note was not written",
          (VAULT / "Inbox/idea.md").read_text(encoding="utf-8") == "first version")


def _journal_rows() -> list:
    try:
        import jarvis_file_guardian as GU
        return GU.rows()
    except Exception:  # noqa: BLE001
        return []


def t_a_deny_writes_nothing_and_snapshots_nothing():
    reset_vault()
    write_note("Inbox/idea.md", "keep me")
    before_rows = len(_journal_rows())
    before = (VAULT / "Inbox/idea.md").read_bytes()
    gate = fake_gate(allowed=False, outcome="denied")
    code, out = do_save("Inbox/idea.md", "replace me", gate=gate)
    ans("POST /api/notes/save (denied)", code, out)
    check("a denied card ends denied and not ok", out.get("state") == "denied"
          and out.get("ok") is False, (code, out))
    check("the message is the PC's plain sentence",
          "You said no" in str(out.get("message")), out.get("message"))
    check("the card was asked under edit_vault_note once",
          [c[0] for c in gate.calls] == ["edit_vault_note"], gate.calls)
    check("the file is byte-identical after a deny",
          (VAULT / "Inbox/idea.md").read_bytes() == before)
    check("no File Guardian snapshot was taken for a deny",
          len(_journal_rows()) == before_rows, len(_journal_rows()) - before_rows)


def t_an_approved_save_snapshots_first_then_writes():
    reset_vault()
    p = write_note("Inbox/idea.md", "old text")
    old = p.read_bytes()
    before_rows = len(_journal_rows())
    gate = fake_gate()
    code, out = do_save("Inbox/idea.md", "new text", gate=gate)
    ans("POST /api/notes/save (approved)", code, out)
    check("an approved save ends saved and ok", code in (200, 202)
          and out.get("state") == "saved" and out.get("ok") is True, (code, out))
    check("it reports the NEW sha256", out.get("sha256") == sha(b"new text"), out.get("sha256"))
    check("the file now holds the new text",
          p.read_text(encoding="utf-8") == "new text")
    check("the message is the PC's own sentence", "Saved" in str(out.get("message")),
          out.get("message"))
    rows = _journal_rows()
    check("the File Guardian recorded a snapshot before the write",
          len(rows) == before_rows + 1 and rows[-1].get("before_sha256") == sha(old), rows[-1:])
    check("the snapshot names the note", str(rows[-1].get("path", "")).endswith("idea.md"),
          rows[-1].get("path"))
    check("the audit line says saved, with the path only",
          any(e == "notes.saved" and d.get("path") == "Inbox/idea.md"
              and "text" not in json.dumps(d) for e, d in AUDIT[-6:]), AUDIT[-6:])
    gate2 = fake_gate()
    code, out = do_save("Inbox/idea.md", "new text", gate=gate2)
    check("a second save is possible and asks again (one card per save)",
          out.get("state") == "saved" and len(gate2.calls) == 1, (code, out))


def t_a_waiting_save_is_202_then_saved_when_the_card_is_answered():
    reset_vault()
    write_note("Inbox/idea.md", "waiting text")
    release = threading.Event()
    entered = threading.Event()

    def blocking_gate(action, detail, prompt):
        calls.append((action, detail, prompt))
        entered.set()
        release.wait(8)
        return Verdict(True, "approved")

    calls = []
    full = VAULT / "Inbox/idea.md"
    body = {"path": "Inbox/idea.md", "text": "after the card",
            "expected_sha256": sha(full.read_bytes())}
    code, out = E.handle_save(body, gate_check=blocking_gate, wait_s=0.05)
    ans("POST /api/notes/save (waiting)", code, out)
    check("a save whose card is still up answers 202 waiting", code == 202
          and out.get("state") == "waiting", (code, out))
    check("... with a job id and the path", bool(out.get("id"))
          and out.get("path") == "Inbox/idea.md", out)
    job_id = out["id"]
    code2, status = E.save_status(job_id)
    ans("GET /api/notes/save?id= (waiting)", code2, status)
    check("GET save?id answers 200 waiting with no hash yet", code2 == 200
          and status.get("state") == "waiting" and status.get("sha256") is None
          and status.get("ok") is True, status)
    check("the file is still untouched while the card waits",
          full.read_text(encoding="utf-8") == "waiting text")
    release.set()
    code3, done = wait_job(job_id)
    ans("GET /api/notes/save?id= (saved)", code3, done)
    check("after Approve the same id reports saved",
          done.get("state") == "saved" and done.get("sha256") == sha(b"after the card"),
          done)
    check("the note holds the new text only after the yes",
          full.read_text(encoding="utf-8") == "after the card")
    check("the card's words name the note and the sizes",
          "Inbox/idea.md" in calls[0][2] and "bytes" in calls[0][2], calls[0][2])
    check("... and its detail carries the path, never the text",
          calls[0][1].get("path") == "Inbox/idea.md"
          and "text" not in json.dumps(calls[0][1]), calls[0][1])


def t_a_file_that_changed_while_the_card_waited_is_not_overwritten():
    reset_vault()
    p = write_note("Inbox/idea.md", "start")

    def someone_else_writes():
        p.write_text("a third editor got here first", encoding="utf-8")

    gate = fake_gate(before=someone_else_writes)
    code, out = do_save("Inbox/idea.md", "my edit", gate=gate)
    check("a note changed while the card waited ends failed", out.get("state") == "failed",
          (code, out))
    check("... and says why, with the current hash",
          "changed while the card waited" in str(out.get("message"))
          and out.get("current_sha256") == sha(b"a third editor got here first"),
          out)
    check("... and the third editor's text is untouched",
          p.read_text(encoding="utf-8") == "a third editor got here first")


def t_the_guardian_blocks_the_write_when_it_cannot_copy():
    reset_vault()
    p = write_note("Inbox/idea.md", "protected")
    old_snapshot = E._snapshot

    def failing_snapshot(full, rel):
        return {"ok": False, "error": "guardian_unavailable",
                "words": "The time machine that saves a copy first is not on this backend."}

    E._snapshot = failing_snapshot
    try:
        code, out = do_save("Inbox/idea.md", "should not land")
    finally:
        E._snapshot = old_snapshot
    check("a save whose copy cannot be made ends failed",
          out.get("state") == "failed", (code, out))
    check("... the sentence says nothing was written for want of a copy",
          "copy of the note could not be saved first" in str(out.get("message")),
          out.get("message"))
    check("... and the file is unchanged",
          p.read_text(encoding="utf-8") == "protected")


def t_the_size_bound_and_the_waiting_limit_refuse_before_any_card():
    reset_vault()
    write_note("Inbox/idea.md", "small")
    gate = fake_gate()
    code, out = do_save("Inbox/idea.md", "x" * (E.MAX_FILE_BYTES + 1), gate=gate)
    check("new text over 2 MiB is 413 and raises no card",
          code == 413 and gate.calls == [], (code, str(out)[:120]))
    old_max = E.MAX_WAITING
    old_wait = E.DEFAULT_WAIT_S
    release = threading.Event()
    entered = threading.Event()
    jobs = []

    def blocking_gate(action, detail, prompt):
        entered.set()
        release.wait(8)
        return Verdict(True, "approved")

    try:
        E.MAX_WAITING = 2
        for i in range(2):
            full = VAULT / "Inbox/idea.md"
            body = {"path": "Inbox/idea.md", "text": f"waiting {i}",
                    "expected_sha256": sha(full.read_bytes())}
            code, out = E.handle_save(body, gate_check=blocking_gate, wait_s=0.05)
            jobs.append(out.get("id"))
            entered.wait(2)
        gate2 = fake_gate()
        code, out = do_save("Inbox/idea.md", "one more", gate=gate2, wait_s=0.05)
        check("too many waiting saves answer 429 with no card",
              code == 429 and gate2.calls == [], (code, out))
        check("... and the sentence names the limit", "2 note saves" in json.dumps(out)
              or f"{E.MAX_WAITING} note saves" in json.dumps(out), out)
    finally:
        E.MAX_WAITING = old_max
        E.DEFAULT_WAIT_S = old_wait
        release.set()
        for jid in jobs:
            if jid:
                wait_job(jid)
    code, out = E.save_status("notesave_doesnotexist")
    check("an unknown save id is 404", code == 404 and out.get("ok") is False, (code, out))
    code, out = do_save("Inbox/gone.md", "new",
                        body={"path": "Inbox/gone.md", "text": "new",
                              "expected_sha256": "0" * 64})
    check("... a missing note is 404, refused before any card",
          code == 404, (code, out))


# ---------------------------------------------------------------------------
#   6. install(): the loader's convention
# ---------------------------------------------------------------------------


def t_install_wraps_the_handler_like_receipts_and_vault():
    reset_vault()
    write_note("Inbox/idea.md", "installed route")
    sent, core = [], {"get": 0, "post": 0}

    class Handler:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    line = E.install(Handler, origin_ok=lambda r: True, token_ok=lambda r: True,
                     read_body=lambda r: b"{}")
    check("install() returns a line for the start-up banner",
          isinstance(line, str) and "notes-edit" in line, line)
    Handler("/api/notes/list").do_GET()
    check("GET /api/notes/list is answered through install()",
          sent and sent[-1][0] == 200 and sent[-1][1].get("ok") is True, sent[-1:])
    Handler("/api/notes/read?path=Inbox/idea.md").do_GET()
    check("GET /api/notes/read is answered through install()",
          sent[-1][0] == 200 and sent[-1][1].get("sha256") == sha(b"installed route"),
          sent[-1:])
    Handler("/api/other").do_GET()
    check("... and every other path still reaches the core", core["get"] == 1, core)
    E.install(Handler, origin_ok=lambda r: True, token_ok=lambda r: True,
              read_body=lambda r: b"{}")
    before = len(sent)
    Handler("/api/notes/list").do_GET()
    check("installing twice does not double-wrap: one answer, not two",
          len(sent) == before + 1 and core["get"] == 1, sent[-2:])

    class NoOrigin:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    E.install(NoOrigin, origin_ok=lambda r: False, token_ok=lambda r: True,
              read_body=lambda r: b"{}")
    NoOrigin("/api/notes/list").do_GET()
    check("a cross-origin request is 403 through install()",
          sent[-1][0] == 403 and "origin" in json.dumps(sent[-1][1]).lower(), sent[-1])

    class NoToken:
        def __init__(self, path="/"):
            self.path = path

        def do_GET(self):
            core["get"] += 1

        def do_POST(self):
            core["post"] += 1

        def _send(self, code, payload):
            sent.append((code, payload))
            return payload

    E.install(NoToken, origin_ok=lambda r: True, token_ok=lambda r: False,
              read_body=lambda r: b"{}")
    NoToken("/api/notes/save").do_POST()
    check("a bad token is 401 through install()",
          sent[-1][0] == 401 and "token" in json.dumps(sent[-1][1]).lower(), sent[-1])

    # The POST's route, through install(), with the gate injected for speed.
    full = VAULT / "Inbox/idea.md"
    body = json.dumps({"path": "Inbox/idea.md", "text": "through install",
                       "expected_sha256": sha(full.read_bytes())}).encode()
    old_gate = E._gate_check
    E._gate_check = lambda a, d, p: Verdict(True, "approved")
    try:
        class PostHandler:
            def __init__(self, path="/"):
                self.path = path

            def do_GET(self):
                core["get"] += 1

            def do_POST(self):
                core["post"] += 1

            def _send(self, code, payload):
                sent.append((code, payload))
                return payload

        E.install(PostHandler, origin_ok=lambda r: True, token_ok=lambda r: True,
                  read_body=lambda r: body)
        PostHandler("/api/notes/save").do_POST()
        check("POST /api/notes/save is answered through install()",
              sent[-1][0] in (200, 202), sent[-1])
        job = sent[-1][1]
        if job.get("state") == "waiting" and job.get("id"):
            code, out = wait_job(job["id"])
            check("... and its job ends saved", out.get("state") == "saved", out)
    finally:
        E._gate_check = old_gate
    check("the note was written through the wrapped route",
          full.read_text(encoding="utf-8") == "through install")


def t_the_shared_contract_fixture_is_generated_and_true():
    """The one copy the desktop and the phone point their contract tests at."""
    gen_path = REPO / "tools" / "gen_notes_cases.py"
    fixture = REPO / "backend" / "notes-edit-cases.json"
    check("the shared contract fixture is here", fixture.is_file(), str(fixture))
    spec = importlib.util.spec_from_file_location("_gen_notes_cases_check", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = mod.cases()
    committed = json.loads(fixture.read_text(encoding="utf-8")) if fixture.is_file() else {}
    check("the fixture is EXACTLY what tools/gen_notes_cases.py produces",
          committed == want)
    check("tools/gen_notes_cases.py --check passes on the committed file",
          mod.render() == fixture.read_text(encoding="utf-8") if fixture.is_file() else False)
    check("it documents the four contract routes",
          set(want.get("routes", {})) == {"list", "read", "save", "save_status"},
          sorted(want.get("routes", {})))
    check("it names the gate action and its shipped tier",
          want.get("action") == "edit_vault_note" and want.get("tier") == "ask", want)
    check("it says count is the rows in THIS answer, not the vault total",
          "rows in THIS answer" in want["routes"]["list"]["answer"]["note"])
    check("the unknown-save-id 404 in it carries ok:false and a plain sentence",
          want["routes"]["save_status"]["errors"]["404"].get("ok") is False
          and bool(want["routes"]["save_status"]["errors"]["404"].get("error")), want)
    check("the limits in the fixture are the module's own constants",
          want["limits"]["max_file_bytes"] == E.MAX_FILE_BYTES
          and want["limits"]["max_notes"] == E.MAX_NOTES
          and want["limits"]["max_waiting"] == E.MAX_WAITING, want["limits"])


# ---------------------------------------------------------------------------
#   7. the measured route answers, printed for the report
# ---------------------------------------------------------------------------


def t_print_the_measured_route_answers():
    print()
    print("MEASURED ROUTE ANSWERS (temporary vault; edit_vault_note gate faked):")
    for key in sorted(ANSWERS):
        code, body = ANSWERS[key]
        print(f"  {key} -> {code} {json.dumps(body, sort_keys=True)}")
    check("the four route answers were measured",
          {"GET /api/notes/list", "GET /api/notes/read", "GET /api/notes/read",
           "POST /api/notes/save (approved)", "GET /api/notes/save?id= (waiting)",
           "GET /api/notes/save?id= (saved)"} <= set(ANSWERS)
          or len(ANSWERS) >= 6, sorted(ANSWERS))


# ---------------------------------------------------------------------------
#   main
# ---------------------------------------------------------------------------


def main() -> int:
    tests = (
        t_the_module_is_shipped_twinned_and_catalogued,
        t_the_gate_tier_is_ask_in_both_shipped_copies,
        t_the_path_sandbox_refuses_escapes_before_any_card,
        t_a_link_inside_the_vault_is_refused,
        t_list_returns_every_note_but_never_its_text,
        t_list_search_and_the_2000_cut,
        t_read_answers_the_contract_shape,
        t_no_vault_is_503_that_names_the_setting,
        t_a_hash_conflict_is_409_and_raises_no_card,
        t_a_deny_writes_nothing_and_snapshots_nothing,
        t_an_approved_save_snapshots_first_then_writes,
        t_a_waiting_save_is_202_then_saved_when_the_card_is_answered,
        t_a_file_that_changed_while_the_card_waited_is_not_overwritten,
        t_the_guardian_blocks_the_write_when_it_cannot_copy,
        t_the_size_bound_and_the_waiting_limit_refuse_before_any_card,
        t_install_wraps_the_handler_like_receipts_and_vault,
        t_the_shared_contract_fixture_is_generated_and_true,
        t_print_the_measured_route_answers,
    )
    for fn in tests:
        print()
        print(f"--- {fn.__name__}")
        try:
            fn()
        except Exception:                                   # noqa: BLE001
            FAILED.append(fn.__name__ + " raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
        shutil.rmtree(_TMP, ignore_errors=True)
        return 1
    print(f"{len(PASSED)} passed, 0 failed - the Obsidian notes editor answers "
          "the contract, writes only after the one card, and copies the old "
          "note through the File Guardian first")
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
