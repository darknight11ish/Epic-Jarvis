"""jarvis_note_capture.py and note-capture.patch - notes that actually get saved.

    python3 test_note_capture.py

No Logseq, no Joplin, no network, no real gate: a temp folder is the Logseq
graph, a fake callable is Joplin's service, a fake gate answers. What is
pinned, in plain words:

1. NOTHING IS WRITTEN WITHOUT THE GATE. run() refuses without approved=True;
   capture() writes only after an allowed verdict, and a denied, timed-out
   or broken gate writes nothing and SAYS so.
2. NEVER OVERWRITES. Logseq: appended to the end, earlier text byte for byte
   intact, file made only if missing. Joplin: only ever POST /notes (a new
   note), a notebook looked up by name and never created.
3. THE JOPLIN TOKEN IS NEVER SHOWN. Not on the card, not in a plan, not in a
   result or error - including the ValueError urllib raises with the whole
   URL in it (the leak found in jarvis_notes.py, fixed there too, and
   checked below). It is only ever sent to this PC.
4. THE STATUS IS HONEST. "filed" only after the text was read back.
5. THE PATCH applies to the text the earlier patches wrote, and reverts.
"""
import json
import os
import socket
import sys
import tempfile
import time
import traceback
import types
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, require_shipped  # noqa: E402

require_shipped("jarvis_note_capture.py")
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-notes-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
AUDIT = []
fw.audit_log = lambda e, d: AUDIT.append((e, json.dumps(d)))
sys.modules["jarvis_framework"] = fw

import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402

FAILED, PASSED = [], []
TOKEN = "s3cr3t+tok/en=="


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class NoNetwork:
    """plan(), describe() and the Logseq path must open no socket at all."""
    def __enter__(self):
        self.real = socket.socket.connect
        def boom(*a, **k):
            raise AssertionError("a socket was opened")
        socket.socket.connect = boom
        return self

    def __exit__(self, *a):
        socket.socket.connect = self.real
        return False


class Verdict:
    def __init__(self, allowed, outcome, reason=""):
        self.allowed, self.outcome, self.reason = allowed, outcome, reason


def graph():
    g = _TMP / f"graph{time.time_ns()}"
    (g / "logseq").mkdir(parents=True)
    (g / "journals").mkdir()
    os.environ[NC.LOGSEQ_GRAPH_ENV] = str(g)
    return g


def t_logseq_plan_and_card():
    g = graph()
    import datetime as dt
    with NoNetwork():
        p = NC.plan("log", "buy milk\nand eggs", now=dt.datetime(2026, 9, 23, 10, 0))
        card = NC.describe(p)
    check("#log maps to Logseq, today's journal file, Logseq's default name",
          p.target == "logseq" and p.file == str(g / "journals" / "2026_09_23.md"), p.file)
    check("the card shows the exact block, both lines",
          "- buy milk\n  and eggs" in card, card)
    check("the card shows the exact file", str(g / "journals" / "2026_09_23.md") in card)
    check("the card says what refusing costs", "If you say no: nothing is written" in card)
    check("the card says nothing leaves this PC", "Nothing leaves this PC" in card)


def t_logseq_appends_and_never_overwrites():
    g = graph()
    f = g / "journals" / "2026_09_23.md"
    f.write_text("- earlier entry", encoding="utf-8")        # no trailing newline
    import datetime as dt
    p = NC.plan("logseq", "second", now=dt.datetime(2026, 9, 23, 12))
    check("run() without approval writes nothing",
          NC.run(p)["ok"] is False and f.read_text() == "- earlier entry")
    with NoNetwork():
        out = NC.run(p, approved=True)
    check("an approved append succeeds", out.get("ok") is True, repr(out))
    check("the earlier text is intact, and the new block starts on its own line",
          f.read_text(encoding="utf-8") == "- earlier entry\n- second\n", repr(f.read_text()))
    p2 = NC.plan("logseq", "third", now=dt.datetime(2026, 9, 24, 9))
    NC.run(p2, approved=True)
    check("a new day's file is made when missing",
          (g / "journals" / "2026_09_24.md").read_text() == "- third\n")
    check("and yesterday's is untouched", f.read_text() == "- earlier entry\n- second\n")


def t_logseq_refuses_what_it_should():
    os.environ[NC.LOGSEQ_GRAPH_ENV] = str(_TMP / "no-such-graph")
    p = NC.plan("logseq", "x")
    check("no graph folder: refused at plan time, with where to set it",
          p.reason_empty and "graph_directory" in p.reason_empty)
    check("and run() writes nothing", NC.run(p, approved=True)["ok"] is False)
    plain = _TMP / f"plain{time.time_ns()}"
    plain.mkdir()
    os.environ[NC.LOGSEQ_GRAPH_ENV] = str(plain)
    check("a folder that is not a Logseq graph is refused",
          "does not look like a Logseq graph" in NC.plan("logseq", "x").reason_empty)
    check("an empty note is refused", NC.plan("logseq", "   ").reason_empty == "the note is empty")
    g = graph()
    big = "y" * (NC.MAX_NOTE_CHARS + 500)
    check("a long note is cut to the bound", len(NC.plan("logseq", big).text) == NC.MAX_NOTE_CHARS)
    f = g / "journals" / "2026_01_01.md"
    target = _TMP / "elsewhere.txt"
    target.write_text("do not touch")
    try:
        f.symlink_to(target)
        import datetime as dt
        out = NC.run(NC.plan("logseq", "z", now=dt.datetime(2026, 1, 1)), approved=True)
        check("a journal file that is a link elsewhere is refused",
              out["ok"] is False and target.read_text() == "do not touch", repr(out))
    except (OSError, NotImplementedError):
        check("SKIP - cannot make a symlink here", True)


def t_joplin_plan_card_and_token():
    os.environ[NC.JOPLIN_TOKEN_ENV] = TOKEN
    os.environ.pop(NC.JOPLIN_URL_ENV, None)
    with NoNetwork():
        p = NC.plan("joplin", "Call the dentist\nbefore Friday", notebook="Home")
        card = NC.describe(p)
    check("#joplin maps to Joplin, title from the first line",
          p.target == "joplin" and p.title == "Call the dentist")
    check("the address is this PC, port 41184", p.url == "http://127.0.0.1:41184")
    check("the token is not in the plan", TOKEN not in json.dumps(p.as_dict()))
    check("the token is not on the card", TOKEN not in card)
    check("the card names the notebook and says it will not be created",
          '"Home"' in card and "not created" in card)
    os.environ[NC.JOPLIN_URL_ENV] = "http://192.168.1.20:41184"
    check("a Joplin address that is not this PC is refused (the token stays here)",
          "not this PC" in NC.plan("joplin", "x").reason_empty)
    os.environ.pop(NC.JOPLIN_URL_ENV, None)
    os.environ.pop(NC.JOPLIN_TOKEN_ENV, None)
    check("no token: refused, saying where to get one",
          "Web Clipper" in NC.plan("joplin", "x").reason_empty)


def t_joplin_creates_only_new_notes():
    os.environ[NC.JOPLIN_TOKEN_ENV] = TOKEN
    calls = []

    def fake(method, path, query, body=None):
        calls.append((method, path, dict(query), body))
        if path == "/folders":
            page = query["page"]
            if page == 1:
                return {"items": [{"id": "f1", "title": "Work"}], "has_more": True}
            return {"items": [{"id": "f2", "title": "home"}], "has_more": False}
        return {"id": "n42", "title": body["title"]}
    p = NC.plan("joplin", "hello", title="T", notebook="Home")
    out = NC.run(p, approved=True, joplin_call=fake)
    check("the note is created in the notebook found by name (case-blind, all pages)",
          out.get("ok") and calls[-1][3].get("parent_id") == "f2", repr((out, calls)))
    check("only GETs and ONE POST /notes: nothing is edited, no notebook is made",
          [c[:2] for c in calls] == [("GET", "/folders"), ("GET", "/folders"), ("POST", "/notes")])
    calls.clear()
    out = NC.run(NC.plan("joplin", "x", notebook="Nope"), approved=True, joplin_call=fake)
    check("a notebook that does not exist: nothing created, and says so",
          out["ok"] is False and "no notebook" in out["reason"]
          and not any(c[0] == "POST" for c in calls))
    check("the fake saw no token - it is only added inside the real sender",
          all("token" not in c[2] for c in calls))


def t_errors_never_carry_the_token():
    os.environ[NC.JOPLIN_TOKEN_ENV] = TOKEN
    os.environ[NC.JOPLIN_URL_ENV] = "http://127.0.0.1:41184"
    p = NC.plan("joplin", "x")

    def leaky(method, path, query, body=None):
        raise ValueError(f"unknown url type: '127.0.0.1:41184/notes?token={TOKEN}'")
    out = NC.run(p, approved=True, joplin_call=leaky)
    check("an error quoting the URL has the token scrubbed out",
          TOKEN not in json.dumps(out) and "[token hidden]" in out["reason"], repr(out))
    import urllib.parse
    q = urllib.parse.quote(TOKEN, safe="")

    def leaky2(method, path, query, body=None):
        raise RuntimeError(f"bad: /notes?token={q}")
    out = NC.run(p, approved=True, joplin_call=leaky2)
    check("the URL-encoded form of the token is scrubbed too", q not in json.dumps(out), repr(out))

    def denied(method, path, query, body=None):
        raise urllib.error.HTTPError("http://127.0.0.1/x", 403, "Forbidden", {}, None)
    out = NC.run(p, approved=True, joplin_call=denied)
    check("a refused token says so in plain words", "refused the token" in out["reason"])
    os.environ.pop(NC.JOPLIN_URL_ENV, None)


def t_the_real_sender_refuses_other_hosts_and_scrubs():
    os.environ[NC.JOPLIN_TOKEN_ENV] = TOKEN
    raised = None
    try:
        NC._joplin_call("GET", "http://example.com", "/folders", {})
    except ValueError as exc:
        raised = exc
    check("the sender itself refuses a non-local address", raised is not None
          and TOKEN not in str(raised))
    # The actual ValueError urllib raises for an address with no scheme:
    p = NC.Plan(target="joplin", text="x", title="x", url="127.0.0.1:41184")
    out = NC.run(p, approved=True)
    check("a scheme-less address fails without the token in the answer",
          out["ok"] is False and TOKEN not in json.dumps(out), repr(out))


def t_jarvis_notes_leak_is_fixed():
    """The audit's finding: jarvis_notes.run() put the token in a ValueError."""
    os.environ[N.JOPLIN_TOKEN_ENV] = TOKEN
    os.environ[N.JOPLIN_URL_ENV] = "localhost"   # no http:// - the audit's trigger
    os.environ.pop(N.BACKEND_ENV, None)
    try:
        p = N.plan("budget", 3)
        with NoNetwork():
            out = N.run(p, approved=True)
    finally:
        os.environ.pop(N.JOPLIN_URL_ENV, None)
    blob = json.dumps(out)
    check("jarvis_notes: the search failed (as it should, bad address)", out["ok"] is False)
    check("jarvis_notes: the error no longer contains the token",
          TOKEN not in blob and urllib.parse.quote(TOKEN, safe="") not in blob, blob)
    check("jarvis_notes: CONTROL - the error is still there, with the token hidden",
          "unknown url type" in blob and "[secret hidden]" in blob, blob)


import urllib.parse  # noqa: E402


def t_capture_goes_through_the_gate():
    g = graph()
    seen = []

    def ask(action, detail, prompt):
        seen.append((action, detail["text"], prompt))
        return Verdict(True, "approved")
    code, out = NC.capture("log", "from the widget", gate_check=ask)
    check("capture waited for the answer and reports filed", code == 200
          and out["state"] == "filed", repr(out))
    check("the gate was asked with the owner's own action name",
          seen and seen[0][0] == "append_logseq_journal")
    check("the gate saw the exact text in the card", "- from the widget" in seen[0][1])
    check("the gate's prompt does not repeat the note", "from the widget" not in seen[0][2])
    days = list((g / "journals").glob("*.md"))
    check("the note is really in the journal", days and "- from the widget\n" in days[0].read_text())
    check("the status never carries the note's text", "from the widget" not in json.dumps(out))
    check("audited by length, never the words",
          any(e == "notes.captured" for e, _ in AUDIT)
          and all("from the widget" not in d for _, d in AUDIT))


def t_a_typed_prefix_note_stays_instant():
    """The owner's decision of 2026-09-24 (note writes wait for a yes after
    outside text) is about the CHAT's tool loop: a turn where Jarvis read an
    email, a page or a file. A #log / #obs / #joplin note or the quick-note
    field never goes through that loop - no model reads anything, the
    owner's words go straight to /api/notes/capture - so it is asked under
    the note's own action, whose tier (auto as shipped) decides: filed at
    once, no card. A control: it passes before and after the change."""
    g = graph()
    seen = []

    def shipped(action, detail, prompt):
        seen.append(action)
        # The shipped tiers: the Logseq journal at auto, anything else asks.
        return (Verdict(True, "auto") if action == "append_logseq_journal"
                else Verdict(False, "denied"))
    code, out = NC.capture("log", "typed after #log", gate_check=shipped, wait_s=2.0)
    check("a typed #log note at the shipped tier: filed at once, no card",
          code == 200 and out["state"] == "filed" and seen == ["append_logseq_journal"],
          (code, out, seen))
    check("... and it is in the journal",
          "- typed after #log\n" in next((g / "journals").glob("*.md")).read_text())
    src = (BACKEND / "jarvis_note_capture.py").read_text(encoding="utf-8")
    check("the capture route never goes through the chat's tool loop",
          "jarvis_agent" not in src.replace("jarvis_agent.py", "")
          and "write_notes_after_outside_text" not in src)


def t_a_refused_capture_writes_nothing_and_says_why():
    for outcome, words in (("denied", "You said no"), ("timed_out", "Nobody answered"),
                           ("refused", "refused it")):
        g = graph()
        code, out = NC.capture("logseq", "no thanks",
                               gate_check=lambda *a, o=outcome: Verdict(False, o, "policy"))
        check(f"{outcome}: not filed, and the message says why",
              out["state"] == "not_filed" and words in out["message"], repr(out))
        check(f"{outcome}: nothing was written", not list((g / "journals").glob("*.md")))

    def boom(*a):
        raise RuntimeError("gate exploded")
    gm = types.ModuleType("jarvis_gate")
    gm.check = lambda *a, **k: boom()
    sys.modules["jarvis_gate"] = gm
    try:
        g = graph()
        code, out = NC.capture("logseq", "x")
    finally:
        sys.modules.pop("jarvis_gate", None)
    check("a gate that raises writes nothing (fails closed)",
          out["state"] == "not_filed" and not list((g / "journals").glob("*.md")), repr(out))


def t_a_waiting_card_reports_waiting_then_the_end():
    import threading
    g = graph()
    release = threading.Event()

    def slow(*a):
        release.wait(5)
        return Verdict(True, "approved")
    code, out = NC.capture("logseq", "later", gate_check=slow, wait_s=0.05)
    check("while the card waits: 202, state waiting", code == 202 and out["state"] == "waiting",
          repr((code, out)))
    release.set()
    for _ in range(100):
        code, got = NC.capture_status(out["id"])
        if got["state"] != "waiting":
            break
        time.sleep(0.02)
    check("then the status says filed", got["state"] == "filed", repr(got))
    check("an unknown id is a 404", NC.capture_status("note_nope")[0] == 404)


def t_every_refusal_says_why_in_message():
    """K10: the phone shows `message`. The 429 for "four notes already
    waiting" had only `error`, so the phone said "Not filed" with no reason."""
    import threading
    graph()
    hold = threading.Event()

    def slow(*a):
        hold.wait(5)
        return Verdict(False, "timed_out")
    try:
        answers = [NC.capture("logseq", f"note {i}", gate_check=slow, wait_s=0.05)
                   for i in range(NC._MAX_WAITING + 1)]
    finally:
        hold.set()
    code, out = answers[-1]
    check("one note more than may wait is a 429, not filed",
          code == 429 and out["state"] == "not_filed", repr((code, out)))
    check("and it says why in message, the field the phone shows",
          out.get("message") == "Not filed: several notes are already waiting for approval - "
                                "answer those first.", repr(out))
    for label, (code, out) in (
            ("an empty note", NC.handle_post({"target": "logseq", "text": ""})),
            ("an unknown target", NC.handle_post({"target": "x", "text": "y"})),
            ("a non-object body", NC.handle_post(["x"]))):
        check(f"{label} ({code}) carries a message too",
              code >= 400 and isinstance(out.get("message"), str) and out["message"].strip(),
              repr(out))
    # Not a refusal: a status poll for an id this PC does not know. Its 404
    # body is also what an older backend answers (the phone's note-targets
    # contract fixture), so it stays as it was.
    time.sleep(0.05)


def t_bad_requests():
    check("an empty note is a 400", NC.handle_post({"target": "logseq", "text": ""})[0] == 400)
    check("an unknown target is a 400", NC.handle_post({"target": "x", "text": "y"})[0] == 400)
    check("a non-object body is a 400", NC.handle_post(["x"])[0] == 400)


def t_the_agent_offers_the_two_tools_gated_by_their_own_names():
    import jarvis_agent as AG
    check("append_logseq_journal is a tool", "append_logseq_journal" in AG.TOOLS)
    check("create_joplin_note is a tool", "create_joplin_note" in AG.TOOLS)
    check("each is gated under its own action name",
          AG.TOOLS["append_logseq_journal"].gate_lookup_name({}) == "append_logseq_journal"
          and AG.TOOLS["create_joplin_note"].gate_lookup_name({}) == "create_joplin_note")
    g = graph()
    state, card = AG.TOOLS["append_logseq_journal"].prepare({"text": "from chat"})
    check("prepare() gives the same card the route shows", "- from chat" in card)
    check("execute() writes the prepared plan",
          AG.TOOLS["append_logseq_journal"].execute({}, state).get("ok") is True
          and "- from chat\n" in next((g / "journals").glob("*.md")).read_text())


# ---- the patch --------------------------------------------------------------

def t_the_patch():
    import shutil
    import subprocess
    sys.path.insert(0, str(HERE))
    import test_task_control as TT     # its stand-in builder and rehearsal
    import _skeleton
    ok, out = TT.rehearse(["task-control.patch", "note-capture.patch"], TT.stack_skeleton())
    if ok is None:
        return check("SKIP - " + out, True)
    check("note-capture.patch applies after task-control.patch, and reverts", ok is True, out)
    if ok:
        i = out.index('if route == "/api/notes/capture":')
        window = out[i:i + 1200]
        check("POST /api/notes/capture checks origin and token",
              "_origin_ok(self)" in window and "_token_ok(self)" in window)
        check("and hands the body to jarvis_note_capture", "jarvis_note_capture.handle_post" in window)
        check("GET /api/notes/capture is there", 'if path == "/api/notes/capture":' in out)
    # The jarvis_gate.py half: the risk lines and tool names, after ui-control-wiring.
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-gate-"))
    try:
        (d / "jarvis_gate.py").write_text(_skeleton.build("ui-control-wiring.patch",
                                                          target="jarvis_gate.py"))
        lf = d / "p.patch"
        lf.write_bytes((HERE / "note-capture.patch").read_bytes().replace(b"\r\n", b"\n"))
        r = subprocess.run([git, "apply", "--include=jarvis_gate.py", str(lf)], cwd=d,
                           capture_output=True, text=True)
        check("its jarvis_gate.py half applies after ui-control-wiring", r.returncode == 0,
              r.stderr)
        g = (d / "jarvis_gate.py").read_text()
        check("the card for a note says it stays on this PC",
              '"append_logseq_journal": ("yes", "local"' in g
              and "\"create_joplin_note\":    (\"yes\", \"local\"" in g)
        check("the two tools map to their own action names",
              '"append_logseq_journal": "append_logseq_journal"' in g
              and '"create_joplin_note": "create_joplin_note"' in g)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("the script applies it right after task-control.patch",
          "note-capture.patch" in names
          and names.index("note-capture.patch") == names.index("task-control.patch") + 1)
    check("the script copies jarvis_note_capture.py in",
          "'jarvis_note_capture.py'" in ps1[ps1.index("$SHIPPED = @("):])


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has the notes route (note-capture.patch applied)",
          '"/api/notes/capture"' in s)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
