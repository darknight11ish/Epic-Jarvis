"""test_file_to_phone.py - the backend half of "send a file to the phone".

    python -B backend/test_file_to_phone.py

Proves, against a temporary settings folder and a temporary "Folders Jarvis may
look in" folder (never the owner's):

1. SEARCH is the allow-list only: a file outside it is never a candidate, and
   `prepare(path=...)` refuses it with the list's own sentence.
2. THE PROTECTION HOOK: when a `jarvis_protection` module is importable, its
   ONE `path_refusal` is asked and a blocked file is neither searched nor sent;
   this module never duplicates that check.
3. THE ONE CARD's words name the EXACT filename, the folder, the byte size and
   the 10 MiB cap; `prepare()` raises (no card) for over-cap and several-match
   and no-match cases.
4. THE FETCH: nothing is available before approval; after `approve()` the phone
   list carries the id and the download is byte-for-byte the file. Ids are
   single-use, expire after ten minutes, and unknown/expired ids are 404 with a
   plain sentence.
5. THE ROUTE takes only `id` - a `path=` parameter is refused - and its answer
   carries no path; origin/token refusals are install()'s own.
6. THE RECORDS agree: TWIN, SHIPPED, plugin folder, catalogue, the tier row in
   both shipped settings copies, card words, asks-first, the agent tool, the
   parity rows, the changelog fragment and docs section 172.
7. NO CARD ON A SEARCH: no gate module is imported or called by prepare/search
   (a stub whose `check()` raises is never reached).
"""
import base64
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)

_TMP = Path(tempfile.gettempdir()) / ("jarvis-send-file-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
CONFIG = _TMP / "config"
CONFIG.mkdir(parents=True, exist_ok=True)
ALLOW = _TMP / "allowed"
ALLOW.mkdir(parents=True, exist_ok=True)
OUTSIDE = _TMP / "outside"
OUTSIDE.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONFIG)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONFIG
FW.LOG_DIR = _TMP / "log"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
FW.load_framework = lambda: {"notes": {}}
sys.modules["jarvis_framework"] = FW

(CONFIG / "folders.json").write_text(
    json.dumps({"folders": [{"path": str(ALLOW), "name": "mine", "added": time.time()}],
                "changed": time.time()}), encoding="utf-8")

INVOICE = ALLOW / "invoice.pdf"
INVOICE.write_bytes(b"%PDF-1.4\n% the invoice, one page\n" + bytes(range(256)))
NOTES = ALLOW / "meeting notes.txt"
NOTES.write_text("the notes\n", encoding="utf-8")
BIG = ALLOW / "big-video.bin"
with open(BIG, "wb") as _fh:
    _fh.truncate(11 * 1024 * 1024)          # sparse: 11 MiB, never read whole
SECRET = OUTSIDE / "secret-plans.txt"
SECRET.write_text("outside the allow-list\n", encoding="utf-8")
R1 = ALLOW / "receipt-one.txt"
R1.write_text("one\n", encoding="utf-8")
R2 = ALLOW / "receipt-two.txt"
R2.write_text("two\n", encoding="utf-8")

import jarvis_send_file as SF  # noqa: E402
import jarvis_documents as DOCS  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def fresh():
    SF._reset_for_tests()
    AUDIT.clear()


def prepare(args):
    return SF.prepare(args)


def raises(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
        return ""
    except ValueError as exc:
        return str(exc)


# ---------------------------------------------------------------------------
#   1-3. search, the protection hook, the card's words and the refusals
# ---------------------------------------------------------------------------


def t_search_is_the_allow_list_only():
    fresh()
    got = SF.search("invoice")
    check("search finds the file inside the listed folder",
          got["ok"] and [m["name"] for m in got["matches"]] == ["invoice.pdf"], got)
    got = SF.search("secret")
    check("search never returns a file outside the listed folders",
          not got["ok"] and got["matches"] == [], got)
    why = raises(prepare, {"path": str(SECRET)})
    check("prepare(path=outside) refuses with the allow-list sentence",
          "Folders Jarvis may look in" in why, why)


def t_protection_hook_is_asked_when_present():
    fresh()
    stub = types.ModuleType("jarvis_protection")
    blocked = os.path.normcase(str(INVOICE))

    def path_refusal(path, *, write=False, what=""):
        try:
            if os.path.normcase(str(path)) == blocked:
                return ("invoice.pdf is on your Protected from Jarvis list as Blocked - "
                        "no access, so Jarvis will not read it.")
        except Exception:                                   # noqa: BLE001
            pass
        return ""

    stub.path_refusal = path_refusal
    stub.blocked_path = lambda path: os.path.normcase(str(path)) == blocked
    saved = sys.modules.get("jarvis_protection")
    sys.modules["jarvis_protection"] = stub
    try:
        got = SF.search("invoice")
        check("a BLOCKED file is never a search result (soft protection hook)",
              not got["ok"] and got["matches"] == [], got)
        why = raises(prepare, {"path": str(INVOICE)})
        check("prepare refuses a blocked file with the protection sentence",
              "Protected from Jarvis" in why, why)
    finally:
        if saved is not None:
            sys.modules["jarvis_protection"] = saved
        else:
            sys.modules.pop("jarvis_protection", None)


def t_the_card_names_exactly_and_refuses_before_it():
    fresh()
    state, words = prepare({"query": "invoice"})
    check("prepare returns the candidate's display state and the card's words",
          state and state.get("name") == "invoice.pdf" and words, (state, words))
    check("the card names the EXACT filename", '"invoice.pdf"' in words, words)
    check("the card names the folder it came from", str(ALLOW) in words, words)
    check("the card names the exact byte size",
          f"{INVOICE.stat().st_size:,} bytes" in words, words)
    check("the card states the 10 MiB cap", "10,485,760 bytes" in words, words)
    check("the card states the one-file and one-download life",
          "ONE file at a time" in words and "10 minutes" in words
          and "works once" in words, words)
    fresh()
    why = raises(prepare, {"query": "big-video"})
    check("a file over the cap is refused in words, before any card",
          "over the 10 MiB" in why and "10,485,760" in why, why)
    fresh()
    why = raises(prepare, {"query": "receipt"})
    check("several matches are refused and the sentence asks to narrow",
          "files match" in why and "Only ONE file" in why, why)
    fresh()
    why = raises(prepare, {"query": "no-such-file-xyz"})
    check("no match is a plain refusal, not an empty card",
          "No file in your listed folders matches" in why, why)


def t_no_card_on_a_search():
    fresh()
    class NoGate:
        @staticmethod
        def check(*a, **k):
            raise AssertionError("a card was raised by a search")

    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = NoGate
    try:
        SF.search("invoice")
        prepare({"query": "invoice"})
    finally:
        if saved is not None:
            sys.modules["jarvis_gate"] = saved
        else:
            sys.modules.pop("jarvis_gate", None)
    check("search/prepare never call the gate (no card on a search)", True)


# ---------------------------------------------------------------------------
#   4-5. approval, the fetch, single use, expiry, the route
# ---------------------------------------------------------------------------


def t_approval_then_one_byte_for_byte_fetch():
    fresh()
    state, words = prepare({"query": "invoice"})
    check("nothing is listed for the phone before the card's yes",
          SF.pending() == [], SF.pending())
    got = SF.approve(state)
    check("the approved tool result says the file is waiting and for how long",
          got.get("ok") is True and "ten minutes" in got.get("said", "")
          and got["file"]["name"] == "invoice.pdf", got)
    listed = SF.pending()
    check("after approval the phone list carries an opaque id and no path",
          len(listed) == 1 and listed[0]["id"].startswith("file_")
          and listed[0]["name"] == "invoice.pdf"
          and listed[0]["size_bytes"] == INVOICE.stat().st_size
          and "path" not in listed[0], listed)
    ident = listed[0]["id"]
    check("the id is random and not derived from the path",
          len(ident) > 20 and "invoice" not in ident and str(ALLOW) not in ident, ident)
    code, out = SF.download(ident)
    data = base64.b64decode(out.get("data") or "")
    check("the download is the file, byte for byte",
          code == 200 and data == INVOICE.read_bytes(), (code, len(data)))
    check("the download answer carries name/size/mime/sha, never a path",
          out.get("name") == "invoice.pdf" and out.get("size_bytes") == len(data)
          and out.get("mime") == "application/pdf" and len(out.get("sha256", "")) == 64
          and "path" not in out and "folder" not in out
          and str(ALLOW) not in json.dumps(out), {k: v for k, v in out.items() if k != "data"})
    code, out = SF.download(ident)
    check("the id is single use: a second fetch is a plain 404",
          code == 404 and "already been downloaded" in out.get("error", ""), (code, out))
    check("the used id left the pending list", SF.pending() == [])


def t_unknown_expired_and_gone_files_answer_plainly():
    fresh()
    code, out = SF.download("file_" + "x" * 24)
    check("an unknown id is 404 in plain words",
          code == 404 and "not waiting for your phone" in out.get("error", ""), (code, out))
    code, out = SF.download("C:\\Windows\\notepad.exe")
    check("a path is not an id: a path-shaped request is 404 too, not a read",
          code == 404 and "not waiting" in out.get("error", ""), (code, out))
    state, _ = prepare({"query": "invoice"})
    SF._files[state["id"]]["expires"] = time.time() - 1
    code, out = SF.download(state["id"])
    check("an expired candidate id is 404", code == 404, (code, out))
    state, _ = prepare({"query": "invoice"})
    SF.approve(state)
    gone = ALLOW / "gone-away.txt"
    gone.write_text("here now\n", encoding="utf-8")
    state2, _ = prepare({"path": str(gone)})
    SF.approve(state2)
    gone.unlink()
    code, out = SF.download(state2["id"])
    check("a file that vanished between card and fetch is 404 with plain words",
          code == 404 and "nothing to send" in out.get("error", ""), (code, out))


class Handler:
    def __init__(self, path="", body=b""):
        self.path = path
        self._body = body
        self.sent = []

    def _send(self, code, out):
        self.sent.append((code, out))

    def do_GET(self):
        self._send(999, {"error": "core route not expected"})


def _req(handler_cls, path, query="", origin=True, token=True):
    class H(handler_cls):
        def do_GET(self):
            self._send(999, {"error": "core route not expected"})

    SF.install(H, origin_ok=lambda h: origin, token_ok=lambda h: token,
               read_body=lambda h: h._body)
    h = H(path + ("?" + query if query else ""))
    h.do_GET()
    return h.sent[-1]


def t_the_two_routes_never_take_a_path():
    fresh()
    code, out = _req(Handler, "/api/files/send")
    check("GET /api/files/send answers 200 with an empty list and the limits",
          code == 200 and out.get("ok") is True and out.get("count") == 0
          and out.get("cap_bytes") == 10 * 1024 * 1024
          and out.get("ttl_seconds") == 10 * 60 and out.get("single_use") is True,
          (code, out))
    code, out = _req(Handler, "/api/files/send", origin=False)
    check("a cross-origin request is refused by install()", code == 403, (code, out))
    code, out = _req(Handler, "/api/files/send", token=False)
    check("a bad token is refused by install()", code == 401, (code, out))
    state, _ = prepare({"query": "invoice"})
    SF.approve(state)
    code, out = _req(Handler, "/api/files/send")
    check("after approval the list carries the id and its file's name",
          code == 200 and out["files"][0]["id"] == state["id"]
          and out["files"][0]["name"] == "invoice.pdf", (code, out))
    code, out = _req(Handler, "/api/files/download", "id=" + state["id"])
    check("the download route serves the bytes by id",
          code == 200 and base64.b64decode(out["data"]) == INVOICE.read_bytes(),
          (code, out.get("name")))
    check("the fetch answer carries no path",
          str(ALLOW) not in json.dumps({k: v for k, v in out.items() if k != "data"}))
    code, out = _req(Handler, "/api/files/download",
                     "path=" + INVOICE.as_posix())
    check("a path= parameter is refused: the route takes only an id",
          code == 400 and "no path is needed" in out.get("error", ""), (code, out))
    code, out = _req(Handler, "/api/files/download")
    check("a bare download request asks for the id in plain words",
          code == 400 and "Say which file" in out.get("error", ""), (code, out))


# ---------------------------------------------------------------------------
#   6. the records agree
# ---------------------------------------------------------------------------


def t_the_records_agree():
    repo = HERE.parent
    shipped = (repo / "backend" / "_where.py").read_text(encoding="utf-8")
    twin_where = (repo / "jarvis-backend" / "_where.py").read_text(encoding="utf-8")
    script = (repo / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is on both SHIPPED lists and in the script",
          '"jarvis_send_file.py"' in shipped and '"jarvis_send_file.py"' in twin_where
          and "'jarvis_send_file.py'" in script)
    check("the published base twin is byte-identical",
          (HERE / "jarvis_send_file.py").read_bytes()
          == (repo / "jarvis-backend" / "jarvis_send_file.py").read_bytes())
    manifest = json.loads((repo / "plugins" / "ready" / "send-file" /
                           "plugin.json").read_text(encoding="utf-8"))
    check("the drop-in folder is a complete handler manifest",
          manifest.get("module") == "jarvis_send_file"
          and manifest.get("install") == "handler"
          and isinstance(manifest.get("stack_order"), int))
    catalogue = (repo / "plugins" / "registry.json").read_text(encoding="utf-8")
    check("the generated catalogue lists the folder", '"send-file"' in catalogue)
    for label, path in (
            ("backend/rebuilt", repo / "backend" / "rebuilt" / "jarvis-framework.toml"),
            ("jarvis-backend", repo / "jarvis-backend" / "jarvis-framework.toml")):
        rows = path.read_text(encoding="utf-8")
        check(f"the tier row lives in {label}'s shipped settings",
              'send_file_to_phone       = "ask"' in rows)
        check(f"the tool is NOT a fresh-install default in {label}'s shipped settings",
              '"send_file_to_phone"]' not in rows)
    words = (repo / "backend" / "jarvis_card_words.py").read_text(encoding="utf-8")
    check("card words name the action", '"send_file_to_phone"' in words)
    asks = (repo / "backend" / "jarvis_asks_first.py").read_text(encoding="utf-8")
    check("'What asks first' lists the action", '"send_file_to_phone"' in asks)
    docs = (repo / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("docs section 172 documents both routes and the limits",
          "## 172. Send one file from the PC to the phone" in docs
          and "GET /api/files/download?id=" in docs
          and "10,485,760" in docs and "single use" in docs and "10 minutes" in docs)
    parity = (repo / "tools" / "check_parity.py").read_text(encoding="utf-8")
    check("parity classifies both routes phone-only (the phone calls them)",
          '"/api/files/send"' in parity and '"/api/files/download"' in parity
          and '"phone-only"' in parity)
    frag = repo / "changelog.d" / "2026-10-31-send-file-to-phone.md"
    check("ONE changelog fragment is there with one bold bullet",
          frag.is_file() and frag.read_text(encoding="utf-8").count("\n- **") == 0
          and frag.read_text(encoding="utf-8").startswith("- **"))
    check("no decisions fragment was added by this lane",
          not (repo / "decisions.d" / "2026-10-31-send-file-to-phone.md").exists())


def t_the_agent_tool_is_registered_and_asks():
    import jarvis_agent as AG
    check("the model tool is in TOOLS",
          AG.SEND_FILE_TOOL in AG.TOOLS and AG.TOOLS[AG.SEND_FILE_TOOL].schema
          if hasattr(AG.TOOLS[AG.SEND_FILE_TOOL], "schema") else True)
    tool = AG.TOOLS[AG.SEND_FILE_TOOL]
    check("its action name is its own (the gate keeps an unknown action at ask)",
          AG.SEND_FILE_ACTION == "send_file_to_phone")
    check("it is offered in exactly one tool group",
          sum(1 for _g, _w, members in AG.TOOL_GROUPS
              if AG.SEND_FILE_TOOL in members) == 1)
    check("it needs a person's yes even if a config loosens the tier",
          AG.SEND_FILE_TOOL in AG.NEEDS_A_PERSON)
    check("a plan cannot name it (one card, one deliberate act)",
          "send_file_to_phone" in AG._PLAN_EXCLUDED_STEPS)
    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    check("the card prompt is the file's own words, not the generic tool line",
          "prompt = plan_text if name == SEND_FILE_TOOL" in src)
    check("the tool's prepare/execute are wired",
          "_prepare_send_file" in src and "_run_send_file" in src)


def main() -> int:
    tests = (
        t_search_is_the_allow_list_only,
        t_protection_hook_is_asked_when_present,
        t_the_card_names_exactly_and_refuses_before_it,
        t_no_card_on_a_search,
        t_approval_then_one_byte_for_byte_fetch,
        t_unknown_expired_and_gone_files_answer_plainly,
        t_the_two_routes_never_take_a_path,
        t_the_records_agree,
        t_the_agent_tool_is_registered_and_asks,
    )
    for fn in tests:
        print(f"\n--- {fn.__name__}")
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
    tail = f"; {len(SKIPPED)} SKIPPED (not passed)" if SKIPPED else ""
    print(f"{len(PASSED)} passed, 0 failed - one fine result file can be searched in "
          f"the allowed folders, shown on ONE card, and fetched byte-for-byte by an "
          f"opaque id for ten minutes, once, under 10 MiB{tail}")
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
