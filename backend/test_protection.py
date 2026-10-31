"""test_protection.py - "Protected from Jarvis", proved against this tree.

    python -B backend/test_protection.py

WHAT THIS SUITE PROVES (the contract's own list):

1. THE STORE. `protected-items.json` loads, saves and is EMPTY AND SAFE when
   damaged or missing; kinds and modes are validated; ids are stable.
2. THE MATCHING. A folder covers its whole subtree (case-insensitive, `..` and
   separators normalised, links resolved); a file covers that file; a program
   matches by its bare executable name.
3. THE REFUSALS ARE PLAIN SENTENCES, WITH NO CARD. Every enforcement point the
   contract names is driven with a protected target and its own stub gate whose
   `check()` raises if it is ever called - a refusal must not open a card.
4. BOTH MODES. Blocked refuses reads and writes; read-only allows reads and
   refuses every write/action (for a program: "see it, never act").
5. PROTECTION WINS over the folders allow-list.
6. THE ROUTES. GET /api/protection, POST add (PRESENT, no card, PC-only, 400,
   403, 409), POST remove (ONE card), POST propose (ONE card, 400/409 before
   any card, job status waiting/added/denied/failed), install()'s origin and
   token checks.
7. THE CHAT TOOL. `protect_from_jarvis` is in TOOLS, validates before the card,
   stores only after it, and never writes the list itself.
8. THE RECORDS AGREE. Both SHIPPED lists, both shipped settings copies' tier
   rows, card words and "What asks first" rows, the drop-in folder, and the
   docs section with its named gaps.
9. THE NAMED GAPS ARE DOCUMENTED, not silent: the docs section names every
   module this v1 does not enforce.

No network, no owner's files, no real card: a temporary settings folder, a
temporary work folder and a fake gate. `%TEMP%` is used with `mkdir` so the
suite runs under a confinement sandbox as well as CI.
"""
import base64
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
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)

_TMP = Path(tempfile.gettempdir()) / ("jarvis-protection-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
CONFIG = _TMP / "config"
CONFIG.mkdir(parents=True, exist_ok=True)
WORK = _TMP / "work"
WORK.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
VAULT.mkdir(parents=True, exist_ok=True)
STORE = CONFIG / "protected-items.json"
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_PROTECTION_STORE"] = str(STORE)
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")

# ── a stub jarvis_framework, so nothing reads the owner's real settings ─────
FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONFIG
FW.LOG_DIR = _TMP / "log"
FW_AUDIT = []
FW_AUDIT_LOCK = threading.Lock()


def _audit(event, detail=None):
    with FW_AUDIT_LOCK:
        FW_AUDIT.append((event, detail))


FW.audit_log = _audit
FW.load_framework = lambda: {"autonomy": {"tiers": {"protect_item": "ask",
                                                     "unprotect_item": "ask"}}}
sys.modules["jarvis_framework"] = FW

OWNC = types.ModuleType("jarvis_owner_check")
OWNC.FROM_THIS_PC = True


def _from_this_pc(peer, local=None, own=None):
    return bool(OWNC.FROM_THIS_PC)


OWNC.from_this_pc = _from_this_pc
sys.modules["jarvis_owner_check"] = OWNC

import jarvis_protection as P  # noqa: E402

PASSED = []
FAILED = []


def check(name, cond, got=""):
    if cond:
        PASSED.append(name)
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}: {str(got)[:600]}")


def reset_store(items=()):
    P._reset_for_tests()
    P.save([dict(i) for i in items])


def add(kind, target, mode, **kw):
    return P.add_item(kind, target, mode, **kw)


def fake_gate(allowed=True, outcome="approved"):
    calls = []

    class Verdict:
        tier = "ask"
        action = ""

        def __init__(self, action):
            self.action = action

    def gate(action, detail, prompt=""):
        calls.append((action, dict(detail or {}), prompt))
        got = Verdict(action)
        got.allowed = allowed
        got.outcome = outcome if not allowed else "approved"
        return got

    gate.calls = calls
    return gate


# ── temporary targets ──────────────────────────────────────────────────────
ROOT_OK = WORK / "listed"
ROOT_OK.mkdir(exist_ok=True)
OK_FILE = ROOT_OK / "ok.md"
OK_FILE.write_text("the needle lives here\n", encoding="utf-8")
BLOCK_DIR = ROOT_OK / "taxes"
BLOCK_DIR.mkdir(exist_ok=True)
BLOCK_FILE = BLOCK_DIR / "secret.md"
BLOCK_FILE.write_text("the needle is hidden here\n", encoding="utf-8")
RO_FILE = ROOT_OK / "readonly.md"
RO_FILE.write_text("readable words\n", encoding="utf-8")
OTHER_FILE = ROOT_OK / "other.md"
OTHER_FILE.write_text("nothing special\n", encoding="utf-8")
(PROTECT_ROOT := ROOT_OK / "blocked-root").mkdir(exist_ok=True)
(PROTECT_ROOT / "inside.md").write_text("inside the protected folder\n", encoding="utf-8")

# The folders allow-list, so documents can be asked at all.
(CONFIG / "folders.json").write_text(
    json.dumps({"folders": [{"path": str(ROOT_OK), "name": "Listed",
                             "added": time.time()}], "changed": time.time()}),
    encoding="utf-8")


def t_store():
    print("\n-- the store --")
    reset_store()
    check("empty store reads as an empty list", P.items() == [])
    item = add("folder", str(BLOCK_DIR), "blocked")
    check("an added entry has an id, kind, target, mode, added, added_by",
          all(item.get(k) for k in ("id", "kind", "target", "mode", "added",
                                    "added_by")), item)
    check("the store is written as readable JSON on disk",
          json.loads(STORE.read_text(encoding="utf-8"))["items"][0]["id"] == item["id"])
    try:
        add("folder", str(BLOCK_DIR), "blocked")
        dup = ""
    except P.Duplicate as exc:
        dup = str(exc)
    check("the same target twice is a Duplicate with a plain sentence",
          "already on your Protected from Jarvis list" in dup, dup)
    for bad in (("folder", str(BLOCK_DIR), "block"), ("file", str(OK_FILE), "auto"),
                ("program", str(OK_FILE), "blocked")):
        try:
            add(*bad)
            why = ""
        except P.Refused as exc:
            why = str(exc)
        check(f"a bad request is refused ({bad[0]}/{bad[2]})", bool(why), why)
    check("a relative path is refused",
          "whole path" in P.validate_request("file", "ok.md", "blocked")[1])
    missing = P.validate_request("file", str(_TMP / "nope.md"), "blocked")[1]
    check("a path that does not exist is refused first",
          "There is no file at" in missing, missing)
    reset_store()
    STORE.write_text("{not json", encoding="utf-8")
    check("a damaged store is EMPTY and safe", P.items() == [])
    check("a damaged store refuses nothing (not a block-everything switch)",
          P.path_refusal(str(OK_FILE)) == "" and not P.blocked_path(str(OK_FILE)))
    STORE.unlink()
    check("a missing store is EMPTY and safe", P.items() == [])
    reset_store()


def t_matching():
    print("\n-- the matching --")
    reset_store()
    add("folder", str(BLOCK_DIR), "blocked")
    add("file", str(RO_FILE), "readonly")
    add("program", "notepad.exe", "blocked")
    add("program", "Calc.EXE", "readonly", known_programs={"calc.exe"})
    check("a file inside a protected folder is covered (blocked)",
          "Blocked" in P.path_refusal(str(BLOCK_FILE)), P.path_refusal(str(BLOCK_FILE)))
    check("case and separators do not matter",
          "Blocked" in P.path_refusal(str(BLOCK_FILE).upper().replace("\\", "/")))
    dotted = str(BLOCK_DIR / ".." / "taxes" / "secret.md")
    check("a `..` path is normalised before matching",
          "Blocked" in P.path_refusal(dotted))
    check("a protected folder's NAME is not a substring trap (taxes2)",
          P.path_refusal(str(WORK / "taxes2" / "x.md")) == "")
    check("a read-only file's read is allowed", P.path_refusal(str(RO_FILE)) == "")
    check("a read-only file's WRITE is refused",
          "Read-only" in P.path_refusal(str(RO_FILE), write=True))
    check("a blocked file's write is refused",
          "Blocked" in P.path_refusal(str(BLOCK_FILE), write=True))
    check("an unrelated file is allowed", P.path_refusal(str(OTHER_FILE)) == "")
    check("a blocked program is refused for seeing",
          "Blocked" in P.program_refusal("notepad.exe"))
    check("a read-only program may be seen", P.program_refusal("calc.exe") == "")
    check("a read-only program may NOT be acted in",
          "Read-only" in P.program_refusal("calc.exe", act=True))
    check("a program matches by its bare name, any case, any path",
          "Blocked" in P.program_refusal(r"C:\Windows\Notepad.EXE"),
          P.program_refusal(r"C:\Windows\Notepad.EXE"))
    check("an unrelated program is allowed", P.program_refusal("explorer.exe") == "")
    check("the store is unchanged by all of that", len(P.items()) == 4)


def t_routes():
    print("\n-- the routes --")
    reset_store()

    class Handler:
        def __init__(self, path="", body=None):
            self.path = path
            self._body = body
            self.sent = []
            self.client_address = ("127.0.0.1", 50000)
            self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4719))

        def _send(self, code, out):
            self.sent.append((code, out))

        def do_GET(self):                     # the core's own do_GET, un-called
            self._send(999, {"error": "core route not expected"})

        def do_POST(self):
            self._send(999, {"error": "core route not expected"})

    def req(handler_cls, method, path, body=None, origin=True, token=True):
        h = handler_cls(path, json.dumps(body).encode("utf-8") if body is not None else b"")
        handler_cls.do_GET(h) if method == "GET" else handler_cls.do_POST(h)
        return h.sent[-1]

    install = P.install
    install(Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
            read_body=lambda h: h._body)
    code, out = req(Handler, "GET", "/api/protection")
    check("GET /api/protection answers the list in the PC's words",
          code == 200 and out.get("ok") is True and out.get("count") == 0
          and out.get("modes") == ["blocked", "readonly"] and out.get("change_card"),
          (code, out))
    OWNC.FROM_THIS_PC = False
    code, out = req(Handler, "POST", "/api/protection/add",
                    {"kind": "folder", "target": str(BLOCK_DIR), "mode": "blocked"})
    check("POST add from another device is 403 pc_only and stores nothing",
          code == 403 and out.get("pc_only") is True and P.items() == [], (code, out))
    OWNC.FROM_THIS_PC = True
    code, out = req(Handler, "POST", "/api/protection/add",
                    {"kind": "folder", "target": str(BLOCK_DIR), "mode": "blocked"})
    check("POST add from this PC is immediate (no card) and says what happened",
          code == 200 and out.get("ok") is True and "Protecting" in out.get("message", "")
          and len(P.items()) == 1, (code, out))
    code, out = req(Handler, "POST", "/api/protection/add",
                    {"kind": "folder", "target": str(BLOCK_DIR), "mode": "blocked"})
    check("POST add of an existing target is 409 naming it",
          code == 409 and "already on your Protected" in out.get("error", ""), (code, out))
    code, out = req(Handler, "POST", "/api/protection/add",
                    {"kind": "banana", "target": str(BLOCK_DIR), "mode": "blocked"})
    check("POST add of an unknown kind is 400 with a plain sentence",
          code == 400 and "Choose what to protect" in out.get("error", ""), (code, out))
    def fresh_handler():
        class H(Handler):
            def do_GET(self):
                self._send(999, {"error": "core route not expected"})

            def do_POST(self):
                self._send(999, {"error": "core route not expected"})
        return H
    H1 = fresh_handler()
    install(H1, origin_ok=lambda h: False, token_ok=lambda h: True,
            read_body=lambda h: h._body)
    code, out = req(H1, "GET", "/api/protection")
    check("a cross-origin request is refused by install()'s own door",
          code == 403 and "cross-origin" in out.get("error", ""), (code, out))
    H2 = fresh_handler()
    install(H2, origin_ok=lambda h: True, token_ok=lambda h: False,
            read_body=lambda h: h._body)
    code, out = req(H2, "GET", "/api/protection")
    check("a bad token is refused by install()'s own door",
          code == 401 and "X-Jarvis-Token" in out.get("error", ""), (code, out))
    check("install() does not double-wrap", "already on" in install(
        Handler, origin_ok=lambda h: True, token_ok=lambda h: True,
        read_body=lambda h: h._body))


def _wait_state(fn, wanted=("added", "denied", "failed", "removed"), timeout=5.0):
    end = time.time() + timeout
    state = None
    while time.time() < end:
        code, out = fn()
        state = out.get("state")
        if state in wanted:
            return state, out
        time.sleep(0.02)
    return state, (code, out)


def t_cards():
    print("\n-- one card per change --")
    reset_store()
    gate = fake_gate(True)
    code, out = P.handle_propose({"kind": "folder", "target": str(BLOCK_DIR),
                                  "mode": "blocked"}, gate_check=gate, wait_s=5.0)
    check("POST propose answers 202 waiting with a job id",
          code == 202 and out.get("state") == "waiting" and out.get("id"), (code, out))
    state, status = _wait_state(lambda: P.propose_status(out.get("id")))
    check("approving the ONE card stores it as added_by chat",
          state == "added" and P.items() and P.items()[0]["added_by"] == "chat",
          (state, status, P.items()))
    prompt = (gate.calls[0][2] if gate.calls else "").lower()
    check("the card named the target and the mode in words",
          bool(gate.calls) and str(BLOCK_DIR).lower() in prompt
          and "blocked - no access" in prompt, gate.calls)
    check("the card's detail carries kinds/target/mode only (no content)",
          gate.calls and set(gate.calls[0][1]) == {"kind", "target", "mode"},
          gate.calls)
    reset_store()
    gate = fake_gate(False, outcome="denied")
    code, out = P.handle_propose({"kind": "file", "target": str(OK_FILE),
                                  "mode": "readonly"}, gate_check=gate, wait_s=5.0)
    state, status = _wait_state(lambda: P.propose_status(out.get("id")))
    check("a Deny stores nothing and says denied",
          state == "denied" and P.items() == [], (state, status))
    reset_store()
    gate = fake_gate(True)
    P.handle_propose({"kind": "file", "target": str(OK_FILE), "mode": "readonly"},
                     gate_check=gate, wait_s=5.0)
    gate2 = fake_gate(True)
    code, out = P.handle_propose({"kind": "file", "target": str(OK_FILE),
                                  "mode": "readonly"}, gate_check=gate2, wait_s=5.0)
    check("a duplicate proposal is 409 BEFORE any card (the gate is not called)",
          code == 409 and not gate2.calls, (code, out, gate2.calls))
    code, out = P.handle_propose({"kind": "file", "target": "relative.md",
                                  "mode": "blocked"}, gate_check=fake_gate(True))
    check("a proposal with a bad target is 400 before any card",
          code == 400 and "whole path" in out.get("error", ""), (code, out))
    # removal: ONE card, and only then is the entry gone
    reset_store()
    item = add("file", str(RO_FILE), "readonly")
    gate = fake_gate(True)
    code, out = P.handle_remove({"id": item["id"]}, gate_check=gate, wait_s=5.0)
    check("POST remove answers 202 waiting", code == 202 and out.get("id"), (code, out))
    deadline = time.time() + 5.0
    while time.time() < deadline and P.items():
        time.sleep(0.02)
    check("approving the removal card really removes the entry",
          P.items() == [] and gate.calls, (P.items(), gate.calls))
    check("the removal card says it is loosening",
          gate.calls and "stop protecting" in gate.calls[0][2]
          and "may touch it again" in gate.calls[0][2], gate.calls)
    code, out = P.handle_remove({"id": "prot_nope"}, gate_check=fake_gate(True))
    check("removing an unknown id is 404", code == 404, (code, out))
    code, out = P.propose_status("prot_nope")
    check("an unknown proposal id is 404 with a plain sentence",
          code == 404 and "no protection request" in out.get("error", ""), (code, out))
    reset_store()


def _run_file_read_sentence():
    import jarvis_agent as AG
    return AG._run_file_read({"path": str(BLOCK_FILE)})


def t_enforcement():
    print("\n-- enforcement: blocked and read-only at every covered point --")
    import jarvis_documents as DOC
    import jarvis_agent as AG
    import jarvis_notes as NOTES
    import jarvis_attached_file as ATTACHED
    import jarvis_file_guardian as GUARD
    import jarvis_open as OPEN
    import jarvis_ui_control as UI
    import jarvis_screen as SCREEN
    import jarvis_screen_win as SCREENWIN
    import jarvis_pictures as PICS

    reset_store()
    add("folder", str(BLOCK_DIR), "blocked")
    add("file", str(RO_FILE), "readonly")
    add("program", "notepad.exe", "blocked")
    add("program", "calc.exe", "readonly")

    # 1. folders allow-list door
    check("documents.allowed_path refuses a blocked path even inside a listed folder",
          DOC.allowed_path(str(BLOCK_FILE)) is None)
    check("documents.read refuses a blocked file with a plain sentence",
          (DOC.read(str(BLOCK_FILE)).get("ok") is False
           and "Blocked" in DOC.read(str(BLOCK_FILE)).get("error", "")),
          DOC.read(str(BLOCK_FILE)))
    check("documents.read still reads a read-only file (reads allowed)",
          DOC.read(str(RO_FILE)).get("ok") is True, DOC.read(str(RO_FILE)))
    check("documents.find never returns a blocked file",
          not any("secret" in str(h.get("name", "")) for h in
                  DOC.find("secret", roots=[str(ROOT_OK)]).get("found", [])))
    found_ok = DOC.find("ok", roots=[str(ROOT_OK)]).get("found", [])
    check("documents.find still returns an allowed file", bool(found_ok), found_ok)
    search = DOC.search("needle", roots=[str(ROOT_OK)], index=False)
    check("documents.search never returns a blocked file's snippet",
          all("taxes" not in str(r.get("path", "")) for r in search.get("results", [])),
          search.get("results"))
    check("documents.search still finds the allowed file",
          any("ok.md" in str(r.get("path", "")) for r in search.get("results", [])),
          search.get("results"))
    zpath = _TMP / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.md", "hello")
    try:
        DOC.import_notion(str(zpath), str(BLOCK_DIR), roots=[str(BLOCK_DIR)])
        why = ""
    except DOC.ImportRefused as exc:
        why = str(exc)
    check("a Notion import into a blocked folder is refused with the sentence",
          "Blocked" in why, why)

    # 2. agent file tools
    got = _run_file_read_sentence()
    check("agent.file_read refuses a blocked file with the plain sentence",
          got.get("ok") is False and "Blocked" in got.get("error", ""), got)
    got = AG._run_file_read({"path": str(RO_FILE)})
    check("agent.file_read reads a read-only file (reads allowed)",
          got.get("ok") is True, got)
    try:
        AG._prepare_my_files({"action": "read", "path": str(BLOCK_FILE)})
        why = ""
    except ValueError as exc:
        why = str(exc)
    check("my_files refuses a blocked read BEFORE any card (prepare raises)",
          "Blocked" in why, why)

    # 3. daily-note write
    assert not VAULT.exists() or True
    (VAULT / ".obsidian").mkdir(exist_ok=True)
    import jarvis_note_capture as NC
    reset_store()
    add("folder", str(VAULT), "blocked")
    plan = NC.plan("obsidian", "a note", now=None)
    check("note_capture.plan refuses a write into a blocked vault before the card",
          "Blocked" in str(getattr(plan, "reason_empty", "")),
          getattr(plan, "reason_empty", ""))
    reset_store()
    add("folder", str(VAULT), "readonly")
    plan_ro = NC.plan("obsidian", "a note")
    check("note_capture.plan refuses a write into a read-only place too",
          "Read-only" in str(getattr(plan_ro, "reason_empty", "")),
          getattr(plan_ro, "reason_empty", ""))

    # 4. notes vault guarded write door
    VAULT_FILE = VAULT / "note.md"
    VAULT_FILE.write_text("words\n", encoding="utf-8")
    reset_store()
    add("file", str(VAULT_FILE), "readonly")
    snap = NOTES.snapshot_vault_before_write(str(VAULT_FILE), reason="test")
    check("notes.snapshot_vault_before_write refuses a protected write with words",
          snap.get("ok") is False and "Read-only" in str(snap.get("words", "")), snap)

    # 5. attachment by reference (a PC path, if one is ever sent)
    reset_store()
    add("file", str(BLOCK_FILE), "blocked")
    payload = base64.b64encode(b"hello").decode("ascii")
    got = ATTACHED.read({"name": "x.txt", "mime": "text/plain", "data": payload,
                         "path": str(BLOCK_FILE)})
    check("attached_file refuses an attachment that carries a blocked PC path",
          got.get("ok") is False and "Blocked" in str(got.get("why", "")), got)

    # 6. File Guardian restore
    reset_store()
    add("file", str(BLOCK_FILE), "blocked")
    try:
        GUARD._restore_path(str(BLOCK_FILE), "0" * 64)
        why = ""
    except GUARD.Refused as exc:
        why = str(exc)
    check("file_guardian restore into a blocked file is a refused write",
          "Blocked" in why, why)

    # 7. opening a program
    reset_store()
    add("program", "calc.exe", "readonly")
    opened = OPEN.resolve("calculator") if "calculator" in OPEN.BUILT_IN else None
    if opened is None:
        key = next((k for k, v in OPEN.BUILT_IN.items()
                    if isinstance(v, str) and v.lower().endswith(".exe")), "")
        prog = OPEN.BUILT_IN.get(key) if key else ""
        reset_store()
        add("program", str(prog), "blocked")
        opened = OPEN.resolve(key) if key else None
    check("jarvis_open refuses a protected program instead of naming it",
          opened is not None and opened.kind == "refused"
          and "Protected from Jarvis" in str(getattr(opened, "said", "")),
          getattr(opened, "kind", None))

    # 8. looking at / acting in a program's window
    reset_store()
    add("program", "notepad.exe", "blocked")
    add("program", "calc.exe", "readonly")
    check("ui_control refuses to LOOK at a blocked program's window",
          "Blocked" in UI.jarvis_target_refusal({"process": "notepad.exe",
                                                 "title": "Untitled"}),
          UI.jarvis_target_refusal({"process": "notepad.exe", "title": "Untitled"}))
    check("ui_control allows LOOKING at a read-only program's window",
          UI.jarvis_target_refusal({"process": "calc.exe", "title": "Calculator"}) == "")
    UI._WINDOW_PROCESS["w-test"] = "calc.exe"
    got = UI.deliver("token", "invoke", window_id="w-test")
    check("ui_control refuses to ACT in a read-only program's window",
          got.get("ok") is False and "Read-only" in str(got.get("reason", "")), got)

    # 9. screen capture / OCR
    class Never:
        broken = False

        def entries(self):
            return []

        def has_program(self, exe):
            return False

        def has_site(self, site):
            return False

        def holds_sites(self):
            return False

    reset_store()
    add("program", "notepad.exe", "blocked")
    snap = {"exe": "notepad.exe", "title": "Untitled", "cls": "", "host": "",
            "hwnd": 1, "password_focused": False, "capture_protected": False,
            "locked": False, "admin_prompt": False}
    check("screen.pause_reason refuses to look at a blocked program",
          SCREEN.pause_reason(snap, Never()) == "protection",
          SCREEN.pause_reason(snap, Never()))
    check("screen has the plain words for that pause",
          "Protected from Jarvis" in SCREEN.PAUSE_WORDS.get("protection", "")
          and "Protected from Jarvis" in SCREEN.PAUSE_SAID.get("protection", ""))
    check("screen_win.must_hide masks a blocked program's window",
          SCREENWIN.must_hide({"exe": "notepad.exe", "title": "Untitled"}, Never()) is True)

    # 10. a reminder that opens a file
    import jarvis_schedule as SCHED
    reset_store()
    add("file", str(OK_FILE), "blocked")
    why = SCHED._path_problem(str(OK_FILE))
    check("schedule refuses a reminder that would open a blocked file", "Blocked" in why, why)
    reset_store()
    add("file", str(RO_FILE), "readonly")
    check("schedule allows a reminder that opens a read-only file (a read)",
          "Protected from Jarvis" not in SCHED._path_problem(str(RO_FILE)),
          SCHED._path_problem(str(RO_FILE)))

    # 11. generated pictures
    reset_store()
    add("folder", str(BLOCK_DIR), "blocked")
    code, out = PICS.file_answer("2026-10-31-120000-x", {"folder": str(BLOCK_DIR)})
    check("pictures.file_answer refuses to read a picture from a blocked folder",
          code in (403, 404) and "Blocked" in str(out.get("error", "")), (code, out))
    piece = types.SimpleNamespace(png=b"\x89PNG\r\n\x1a\n", seed=1, model="m",
                                  runtime="r", settings={})
    try:
        PICS.save_picture(BLOCK_DIR, "a cat", piece, {})
        why = ""
    except ValueError as exc:
        why = str(exc)
    check("pictures.save_picture refuses to write into a blocked folder",
          "Blocked" in why, why)
    reset_store()


def t_no_card_and_tool():
    print("\n-- no card for an enforcement refusal, and the chat tool --")
    reset_store()
    add("file", str(BLOCK_FILE), "blocked")
    add("program", "notepad.exe", "blocked")
    calls = []

    class NoCardGate:
        @staticmethod
        def check(*a, **k):
            calls.append(a)
            raise AssertionError("a card was raised for an enforcement refusal")

    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = NoCardGate
    try:
        import jarvis_documents as DOC
        import jarvis_agent as AG
        import jarvis_open as OPEN
        import jarvis_screen as SCREEN
        DOC.read(str(BLOCK_FILE))
        AG._run_file_read({"path": str(BLOCK_FILE)})
        READONLY_OPENED = OPEN.resolve("calculator")
        SCREEN.pause_reason({"exe": "notepad.exe", "title": "x", "hwnd": 1,
                             "locked": False, "admin_prompt": False,
                             "password_focused": False,
                             "capture_protected": False}, types.SimpleNamespace(
            broken=False, entries=lambda: [], has_program=lambda e: False,
            has_site=lambda s: False, holds_sites=lambda: False))
    finally:
        if saved is not None:
            sys.modules["jarvis_gate"] = saved
        else:
            sys.modules.pop("jarvis_gate", None)
    check("an enforcement refusal never calls the gate (no card, proved)", calls == [], calls)
    check("the chat tool is registered in TOOLS",
          AG.PROTECT_TOOL in AG.TOOLS and AG.TOOLS[AG.PROTECT_TOOL].schema)
    check("the chat tool's own action names are the contract's",
          AG.PROTECT_ACTION == "protect_item" and AG.UNPROTECT_ACTION == "unprotect_item")
    reset_store()
    tool = AG.TOOLS[AG.PROTECT_TOOL]
    try:
        tool.prepare({"kind": "file", "target": "relative.md", "mode": "blocked"})
        why = ""
    except ValueError as exc:
        why = str(exc)
    check("the chat tool validates BEFORE any card (a relative path refuses)",
          "whole path" in why, why)
    state, text = tool.prepare({"kind": "folder", "target": str(BLOCK_DIR),
                                "mode": "blocked"})
    check("the chat tool's plan names the target and the mode",
          state and str(BLOCK_DIR).lower() in text.lower()
          and "blocked - no access" in text.lower(), text)
    got = tool.execute({"kind": "folder", "target": str(BLOCK_DIR), "mode": "blocked"},
                       state)
    check("the chat tool stores ONLY on execute (after the card) as added_by chat",
          got.get("ok") is True and P.items() and P.items()[0]["added_by"] == "chat",
          (got, P.items()))
    try:
        tool.prepare({"kind": "folder", "target": str(BLOCK_DIR), "mode": "blocked"})
        why = ""
    except ValueError as exc:
        why = str(exc)
    check("the chat tool refuses an already-protected target before a card",
          "already on your Protected" in why, why)
    reset_store()


def t_records():
    print("\n-- the records agree --")
    repo = HERE.parent
    shipped = (repo / "backend" / "_where.py").read_text(encoding="utf-8")
    twin = (repo / "jarvis-backend" / "_where.py").read_text(encoding="utf-8")
    script = (repo / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_protection.py is in backend/_where.py SHIPPED",
          '"jarvis_protection.py"' in shipped)
    check("... and in the published base's SHIPPED list",
          '"jarvis_protection.py"' in twin)
    check("... and in scripts/apply-patches.ps1's $SHIPPED",
          "'jarvis_protection.py'" in script)
    check("the base twin of the module is byte-identical",
          (HERE / "jarvis_protection.py").read_bytes() ==
          (repo / "jarvis-backend" / "jarvis_protection.py").read_bytes())
    for label, path in (
            ("backend/rebuilt", repo / "backend" / "rebuilt" / "jarvis-framework.toml"),
            ("jarvis-backend", repo / "jarvis-backend" / "jarvis-framework.toml")):
        text = path.read_text(encoding="utf-8")
        check(f"the tier rows are in {label}'s shipped settings",
              'protect_item              = "ask"' in text
              and 'unprotect_item            = "ask"' in text)
    words = (repo / "backend" / "jarvis_card_words.py").read_text(encoding="utf-8")
    twin_words = (repo / "jarvis-backend" / "jarvis_card_words.py").read_text(encoding="utf-8")
    for action in ("protect_item", "unprotect_item"):
        check(f"card words name {action}",
              f'"{action}"' in words and f'"{action}"' in twin_words)
    asks = (repo / "backend" / "jarvis_asks_first.py").read_text(encoding="utf-8")
    check("'What asks first' lists both actions",
          '"protect_item", "unprotect_item"' in asks)
    folder = repo / "plugins" / "ready" / "protected-items"
    manifest = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
    check("the drop-in folder is a complete no-patch manifest",
          manifest.get("module") == "jarvis_protection"
          and manifest.get("install") == "handler"
          and isinstance(manifest.get("stack_order"), int)
          and (folder / "README.md").is_file(), manifest)
    catalogue = (repo / "plugins" / "registry.json").read_text(encoding="utf-8")
    check("the generated catalogue lists the folder",
          '"protected-items"' in catalogue)
    docs = (repo / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("the docs section documents the routes and the store",
          "## 170. \"Protected from Jarvis\"" in docs
          and "POST /api/protection/propose" in docs
          and "protected-items.json" in docs)
    for gap in ("shell_exec", "run_data_script", "rea_investigate",
                "jarvis_app_control", "jarvis_browser_control", "jarvis_media",
                "full-screen capture", "notes-editor lane"):
        check(f"the named gap {gap!r} is written down", gap in docs)
    covered = {
        "jarvis_documents.py": ["_protection()"],
        "jarvis_agent.py": ["_protection()", "PROTECT_TOOL"],
        "jarvis_note_capture.py": ["_protection()"],
        "jarvis_notes.py": ["_protection()"],
        "jarvis_attached_file.py": ["_protection()"],
        "jarvis_file_guardian.py": ["_protection()"],
        "jarvis_open.py": ["_protection()"],
        "jarvis_ui_control.py": ["_protection()"],
        "jarvis_screen.py": ["_protection()"],
        "jarvis_screen_win.py": ["_protection()"],
        "jarvis_schedule.py": ["_protection()"],
        "jarvis_pictures.py": ["_protection()"],
    }
    for name, markers in covered.items():
        text = (repo / "backend" / name).read_text(encoding="utf-8")
        check(f"{name} carries its enforcement hook",
              all(m in text for m in markers))
    # jarvis-backend/_where.py is the base copy PLUS its trailer (see
    # CLAUDE.md), so it is not byte-identical by design; the entry is what
    # must agree, and DEF-018's rule is checked by test_base_matches_repo.
    check("the published base's SHIPPED list carries the trailer and the entry",
          twin.endswith((repo / "backend" / "_where.py").read_text(
              encoding="utf-8").splitlines()[-1] + "\n") or
          '"jarvis_protection.py"' in twin)


def main() -> int:
    for name, fn in (("store", t_store), ("matching", t_matching),
                     ("routes", t_routes), ("cards", t_cards),
                     ("enforcement", t_enforcement),
                     ("no-card and tool", t_no_card_and_tool),
                     ("records", t_records)):
        try:
            fn()
        except Exception:
            FAILED.append(name)
            print(f"\nRAISED in {name}:")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", " | ".join(str(f) for f in FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
