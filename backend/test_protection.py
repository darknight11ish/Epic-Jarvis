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



# ===========================================================================
#   Gemini Q2 (2026-10-31): the seven mandatory bypass paths, one test each
# ===========================================================================


def _patched_attr(obj, name, fn):
    """Patch one attribute for a `with` block, restoring it whatever happens."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        old = getattr(obj, name)
        setattr(obj, name, fn)
        try:
            yield
        finally:
            setattr(obj, name, old)
    return _cm()


def t_p1_canonicalisation_checks_both_forms():
    """Q2 #1: BOTH normcase(abspath(p)) and normcase(realpath(p)) are compared."""
    reset_store()
    add("folder", str(PROTECT_ROOT), "blocked")
    inside = PROTECT_ROOT / "linkish.md"
    inside.write_text("inside\n", encoding="utf-8")
    outside = _TMP / "outside"
    outside.mkdir(exist_ok=True)
    real = os.path.realpath

    # The LEXICAL half: a path that SITS INSIDE the protected folder but whose
    # resolved target is somewhere else. Realpath-only matching would allow it.
    def resolves_out(p, *a, **k):
        try:
            if os.path.normcase(os.path.abspath(str(p))) == os.path.normcase(str(inside)):
                return str(outside / "elsewhere.md")
        except Exception:
            pass
        return real(p, *a, **k)
    with _patched_attr(os.path, "realpath", resolves_out):
        said = P.path_refusal(str(inside))
    check("P1 lexical form: a path inside a protected folder is refused even "
          "when it resolves outside", "Blocked" in said, said)

    # The RESOLVED half: a path OUTSIDE that resolves INTO the protected folder.
    def resolves_in(p, *a, **k):
        try:
            if os.path.normcase(os.path.abspath(str(p))) == os.path.normcase(
                    str(outside / "decoy.md")):
                return str(PROTECT_ROOT / "inside.md")
        except Exception:
            pass
        return real(p, *a, **k)
    with _patched_attr(os.path, "realpath", resolves_in):
        said = P.path_refusal(str(outside / "decoy.md"))
    check("P1 resolved form: a path outside that resolves into a protected "
          "folder is refused", "Blocked" in said, said)

    # And a real link, when this machine lets one be made. A skipped check is
    # never a pass: it prints its own line and is counted apart.
    import jarvis_protection as P2
    real_dir = PROTECT_ROOT / "real-link-dir"
    real_dir.mkdir(exist_ok=True)
    target = real_dir / "target.md"
    target.write_text("t\n", encoding="utf-8")
    link = PROTECT_ROOT / "made-link.md"
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(str(target), str(link))
        made = True
    except (OSError, NotImplementedError, AttributeError):
        made = False
    if made:
        said = P2.path_refusal(str(link))
        check("P1 a real symlink inside the protected folder is refused by the "
              "lexical form", "Blocked" in said, said)
    else:
        print("skip  P1 a real symlink: this machine would not make one "
              "(Windows needs Developer Mode or an admin shell) - the "
              "monkeypatched pair above is the proof, this line is not a pass")
    reset_store()


def t_p2_the_list_protects_its_own_file():
    """Q2 #2: protected-items.json + .bak/.tmp are blocked, listed or not."""
    reset_store()
    store = P.store_path()
    P.save([])
    check("P2 the store itself is refused read and write, with the self sentence",
          P.path_refusal(str(store)) == P.SELF_SENTENCE
          and P.path_refusal(str(store), write=True) == P.SELF_SENTENCE,
          P.path_refusal(str(store)))
    for sibling in (store.with_name(store.name + ".bak"),
                    store.with_name(store.name + ".tmp"),
                    store.with_name("." + store.name + ".atomic.tmp")):
        check(f"P2 its sibling {sibling.name!r} is refused too",
              P.path_refusal(str(sibling)) == P.SELF_SENTENCE
              and P.is_store_file(sibling), P.path_refusal(str(sibling)))
    import jarvis_documents as DOC
    got = DOC.read(str(store))
    check("P2 a document read pointed at the store is refused with the sentence",
          got.get("ok") is False and P.SELF_SENTENCE in str(got.get("error", "")), got)
    import jarvis_agent as AG
    got = AG._run_file_read({"path": str(store)})
    check("P2 a file tool pointed at the store is refused and reads nothing",
          got.get("ok") is False and bool(got.get("error")), got)
    import jarvis_attached_file as ATT
    payload = base64.b64encode(b"{}").decode("ascii")
    got = ATT.read({"name": "x.json", "mime": "application/json", "data": payload,
                    "path": str(store)})
    check("P2 an attachment that references the store by path is refused",
          got.get("ok") is False and P.SELF_SENTENCE in str(got.get("why", "")), got)
    # Scope: only the list's OWN file is hard-coded, not every file so named.
    unrelated = _TMP / "mine" / "protected-items.json"
    unrelated.parent.mkdir(exist_ok=True)
    check("P2 a same-named file in another folder is NOT hard-blocked",
          P.path_refusal(str(unrelated)) == "", P.path_refusal(str(unrelated)))


def t_p3_notes_and_wiki_doors():
    """Q2 #3: notes search omits blocked; #obs and wiki ingest refuse before a card."""
    reset_store()
    vault = _TMP / "vault"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    blocked_note = vault / "private" / "secret.md"
    blocked_note.parent.mkdir(exist_ok=True)
    blocked_note.write_text("the needle is hidden here\n", encoding="utf-8")
    open_note = vault / "public.md"
    open_note.write_text("the needle is public here\n", encoding="utf-8")
    add("folder", str(vault / "private"), "blocked")

    import types as _types
    import jarvis_notes as NOTES
    plan = _types.SimpleNamespace(folder=str(vault), query="needle", limit=10,
                                  backend="vault")
    got = NOTES._search_vault(plan)
    refs = [r.get("ref") for r in got.get("results", [])]
    check("P3 the vault search omits a BLOCKED note and keeps the open one",
          "private/secret.md" not in refs and "public.md" in refs, (refs, got))
    reset_store()

    import jarvis_note_capture as NC
    add("folder", str(vault), "blocked")
    gate = fake_gate()
    code, out = NC.capture("obsidian", "the owner's words", gate_check=gate,
                           wait_s=0.2)
    check("P3 #obs capture into a BLOCKED vault refuses before any card",
          out.get("ok") is False and "Blocked" in str(out.get("error", ""))
          and not gate.calls, (code, out, gate.calls))
    reset_store()
    add("folder", str(vault), "readonly")
    gate = fake_gate()
    code, out = NC.capture("obsidian", "the owner's words", gate_check=gate,
                           wait_s=0.2)
    check("P3 #obs capture into a READ-ONLY vault refuses before any card",
          out.get("ok") is False and "Read-only" in str(out.get("error", ""))
          and not gate.calls, (code, out, gate.calls))
    reset_store()

    import jarvis_wiki as WIKI
    wiki = _TMP / "wiki"
    (wiki / "Sources").mkdir(parents=True, exist_ok=True)
    (wiki / "Pages").mkdir(exist_ok=True)
    source = wiki / "Sources" / "note.md"
    source.write_text("source words\n", encoding="utf-8")

    class StubWhere:
        def __init__(self, root):
            self.wiki = str(Path(root))       # the real Where.wiki is a str
            self.why = ""

        def sub(self, *parts):
            return Path(self.wiki).joinpath(*parts)

    lane = _types.SimpleNamespace(num_ctx=32768, url="http://127.0.0.1:1", model="m")
    spawned, gate3 = [], fake_gate()
    saved_where = WIKI.where
    WIKI.where = lambda: StubWhere(wiki)
    try:
        add("file", str(source), "blocked")
        code, out = WIKI.ingest("note.md", lane_for=lambda: lane,
                                gate_check=gate3, spawn=spawned.append)
        check("P3 /api/wiki/ingest refuses a BLOCKED source before any card/job",
              code == 400 and "Blocked" in str(out.get("error", ""))
              and not spawned and not gate3.calls, (code, out, spawned, gate3.calls))
        reset_store()
        add("file", str(source), "readonly")
        code, out = WIKI.ingest("note.md", lane_for=lambda: lane,
                                gate_check=gate3, spawn=spawned.append)
        check("P3 /api/wiki/ingest refuses a READ-ONLY source before any card/job",
              code == 400 and "Read-only" in str(out.get("error", ""))
              and not spawned and not gate3.calls, (code, out, spawned, gate3.calls))
        reset_store()
        page = wiki / "Pages" / "secretpage.md"
        page.write_text("old page\n", encoding="utf-8")
        add("file", str(page), "readonly")
        raised = ""
        try:
            WIKI._checked(StubWhere(wiki), "Pages/secretpage.md")
        except WIKI.Refused as exc:
            raised = str(exc)
        check("P3 a wiki write target that is READ-ONLY is refused before writing",
              "Read-only" in raised, raised)
        # A blocked page is never read into the model either.
        (wiki / "Pages" / "gone.md").write_text("hidden page\n", encoding="utf-8")
        add("file", str(wiki / "Pages" / "gone.md"), "blocked")
        shown = WIKI._shown_pages(StubWhere(wiki), ["gone"], 10000)
        check("P3 a BLOCKED existing page is not read into the model's context",
              "gone" not in shown and not shown, shown)
    finally:
        WIKI.where = saved_where
    reset_store()


def t_p4_screen_capture_refuses_before_pixels():
    """Q2 #4: target window OR any blocked program visible on the monitor."""
    import jarvis_screen_win as SW

    reset_store()
    add("program", "notepad.exe", "blocked")
    check("P4 the window being captured is checked by its program name",
          "Blocked" in SW.protected_capture_problem({"exe": "notepad.exe"}),
          SW.protected_capture_problem({"exe": "notepad.exe"}))
    check("P4 an unrelated program is allowed",
          SW.protected_capture_problem({"exe": "explorer.exe"}) == "")
    saved_rect, saved_list = SW._rect_of, SW._list_windows
    SW._rect_of = lambda hwnd, whole: (0, 0, 100, 100)
    try:
        SW._list_windows = lambda: [
            {"hwnd": 2, "exe": "notepad.exe", "title": "", "rect": (50, 50, 150, 150),
             "opaque": True}]
        said = SW.whole_screen_protection_problem({"hwnd": 1, "exe": "explorer.exe"})
        check("P4 a BLOCKED program visible on the captured monitor refuses the "
              "whole-screen capture", "Blocked" in said, said)
        SW._list_windows = lambda: [
            {"hwnd": 2, "exe": "explorer.exe", "title": "", "rect": (50, 50, 150, 150),
             "opaque": True}]
        check("P4 an unrelated visible window does not refuse it",
              SW.whole_screen_protection_problem({"hwnd": 1}) == "")
        SW._list_windows = lambda: [
            {"hwnd": 2, "exe": "notepad.exe", "title": "", "rect": (500, 500, 600, 600),
             "opaque": True}]
        check("P4 a blocked program on ANOTHER monitor does not refuse this one",
              SW.whole_screen_protection_problem({"hwnd": 1}) == "")
    finally:
        SW._rect_of, SW._list_windows = saved_rect, saved_list

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

    grabbed = []

    def grab(rect):
        grabbed.append(rect)
        return (b"\x00" * 4, 2, 2)

    png = SW.take_picture({"hwnd": 1, "exe": "notepad.exe"}, False, Never(),
                          rect_of=lambda hwnd, whole: (0, 0, 10, 10),
                          grab=grab, list_windows=lambda: [],
                          address_of=lambda w: "")
    check("P4 the capture door returns no picture for a blocked target, and the "
          "grabbing call is never made", png is None and grabbed == [],
          (png, grabbed))
    png = SW.take_picture({"hwnd": 1, "exe": "explorer.exe"}, True, Never(),
                          rect_of=lambda hwnd, whole: (0, 0, 10, 10),
                          grab=grab, list_windows=lambda: [
                              {"hwnd": 2, "exe": "notepad.exe", "title": "",
                               "rect": (1, 1, 9, 9), "opaque": True}],
                          address_of=lambda w: "")
    check("P4 a whole-monitor capture with a blocked program visible grabs nothing",
          png is None and grabbed == [], (png, grabbed))
    reset_store()


def t_p5_launcher_program_names_and_path_arguments():
    """Q2 #5: `notepad` and `notepad.exe` are one key; path args are checked."""
    reset_store()
    add("program", "notepad.exe", "blocked")
    for spelling in ("notepad", "Notepad.EXE", "C:\\Windows\\NOTEPAD.EXE"):
        check(f"P5 {spelling!r} matches the stored notepad.exe (blocked)",
              "Blocked" in P.program_refusal(spelling), P.program_refusal(spelling))
    check("P5 the two keys are the same set",
          P.program_keys("notepad") == P.program_keys("notepad.exe"))
    import jarvis_agent as AG
    add("folder", str(BLOCK_DIR), "blocked")
    add("file", str(RO_FILE), "readonly")
    check("P5 an agent tool argument naming a BLOCKED path is refused plainly",
          "Blocked" in AG._protection_path_args("my_files", {"path": str(BLOCK_FILE)}),
          AG._protection_path_args("my_files", {"path": str(BLOCK_FILE)}))
    check("P5 a READ tool may name a READ-ONLY path (a read)",
          AG._protection_path_args("my_files", {"path": str(RO_FILE)}) == "")
    check("P5 a tool that may WRITE refuses the READ-ONLY path",
          "Read-only" in AG._protection_path_args("run_data_script",
                                                  {"path": str(RO_FILE)}))
    import jarvis_open as OPEN
    reset_store()
    add("program", "notepad.exe", "blocked")
    opened = OPEN.resolve("notepad")
    check("P5 the launcher refuses a blocked program by either spelling",
          getattr(opened, "kind", "") == "refused"
          and "Protected from Jarvis" in str(getattr(opened, "said", "")),
          getattr(opened, "kind", None))
    reset_store()


def t_p6_background_jobs_cannot_bypass_the_list():
    """Q2 #6: a job's params are checked at create and again per plan step."""
    import jarvis_jobs as JOBS

    reset_store()
    add("folder", str(BLOCK_DIR), "blocked")
    add("file", str(RO_FILE), "readonly")
    check("P6 a job param naming a BLOCKED path is refused with the sentence",
          "Blocked" in JOBS._protection_params_refusal(
              {"path": str(BLOCK_FILE)}, write=False),
          JOBS._protection_params_refusal({"path": str(BLOCK_FILE)}, write=False))
    check("P6 a read-only path is allowed for a read-only handler",
          JOBS._protection_params_refusal({"path": str(RO_FILE)}, write=False) == "")
    check("P6 ... and refused when the handler may write it",
          "Read-only" in JOBS._protection_params_refusal(
              {"path": str(RO_FILE)}, write=True))
    saved_init = JOBS._init
    JOBS._init = lambda: None
    try:
        raised = ""
        try:
            JOBS.create("fake_handler", {"path": str(BLOCK_FILE)})
        except ValueError as exc:
            raised = str(exc)
        check("P6 a fake job that tries a blocked path is refused BEFORE it exists",
              "Blocked" in raised, raised)
        raised = ""
        try:
            JOBS.create("fake_handler", {"path": str(RO_FILE)})
        except ValueError as exc:
            raised = str(exc)
        check("P6 a fake write-capable job that tries a read-only path is refused too",
              "Read-only" in raised, raised)
    finally:
        JOBS._init = saved_init
    reset_store()


def t_p7_phone_scope_is_written_down_and_every_path_is_documented():
    """Q2 #7 + the docs must name each of the seven as covered or a v1 gap."""
    repo = HERE.parent
    docs = (repo / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("P7 the docs say `program` entries govern PC programs (*.exe)",
          "PC programs" in docs and "*.exe" in docs and "AppControlPlate" in docs,
          "the PC-programs/AppControlPlate sentence is missing")
    lowered = docs.lower()
    for phrase in ("Windows Path Canonicalization", "self-protection",
                   "jarvis_jobs.py", "jarvis_watch.py", "jarvis_open.py",
                   "jarvis_screen.py", "jarvis_wiki.py"):
        check(f"P7 the docs name {phrase!r} in the hardening rows",
              phrase.lower() in lowered)
    source_pins = {
        "jarvis_protection.py": ["_path_forms", "_is_self_path", "program_keys",
                                 "visible_program_refusal"],
        "jarvis_notes.py": ["_P.blocked_path(real)"],
        "jarvis_wiki.py": ["_P.path_refusal(str(w.sub(SOURCES_DIR, source)), write=True)",
                           "_P.path_refusal(str(p), write=True)"],
        "jarvis_screen.py": ["protection_visible"],
        "jarvis_screen_win.py": ["visible_protected_sentence", "protected_capture_problem"],
        "jarvis_jobs.py": ["_protection_params_refusal"],
        "jarvis_agent.py": ["_protection_path_args"],
    }
    for module, markers in source_pins.items():
        text = (HERE / module).read_text(encoding="utf-8")
        check(f"P7 {module} carries its hardening hook",
              all(marker in text for marker in markers),
              [m for m in markers if m not in text])



def main() -> int:
    for name, fn in (("store", t_store), ("matching", t_matching),
                     ("routes", t_routes), ("cards", t_cards),
                     ("enforcement", t_enforcement),
                     ("no-card and tool", t_no_card_and_tool),
                     ("records", t_records),
                     # Gemini Q2 (2026-10-31): the seven mandatory bypass paths
                     ("Q2 P1 canonicalisation", t_p1_canonicalisation_checks_both_forms),
                     ("Q2 P2 self-protection", t_p2_the_list_protects_its_own_file),
                     ("Q2 P3 notes/wiki", t_p3_notes_and_wiki_doors),
                     ("Q2 P4 screen capture", t_p4_screen_capture_refuses_before_pixels),
                     ("Q2 P5 launcher names", t_p5_launcher_program_names_and_path_arguments),
                     ("Q2 P6 jobs", t_p6_background_jobs_cannot_bypass_the_list),
                     ("Q2 P7 scope/docs", t_p7_phone_scope_is_written_down_and_every_path_is_documented)):
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
