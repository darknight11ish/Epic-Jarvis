"""jarvis_upload.py: a document from the owner's phone, and the Notion door.

    python3 test_upload.py

WHY THIS EXISTS. The owner's ask of 2026-11-05 - "upload any documents through
the jarvis app and have it be fully processed as if I was uploading it to the
jarvis desktop" - reverses a written promise (docs/DECISIONS.md:4943: "no upload
endpoint, now or later"), so the code that does it has to show, check by check,
that it kept every rule the promise was protecting:

  1. ONE card per file, raised BEFORE a byte is written, and nothing lands when
     it is denied, times out or is never answered (rule 4, taken at its word);
  2. a folder that is not on the owner's own "Folders Jarvis may look in" list
     is refused - the phone cannot create a grant;
  3. ANY file type lands as a PLAIN FILE COPY, and the kinds that claim to be a
     document or a photo are still checked by name AND by bytes; a `.docx` that
     is really a renamed archive never reaches a parser, a `.pdf` that is really
     a program is refused, and a landed `.zip`/`.exe`/`.dat` is still refused by
     every reader that turns bytes into words;
  4. the sha256 and the size are checked at finish, and a truncated or altered
     upload leaves nothing behind;
  5. staging is invisible to every reader before `finish`, and deleted on every
     path afterwards - success, refusal, a denied card, an error, a timeout;
  6. every request stays far under the server's 4 MiB body cap, because a Notion
     export cannot arrive in one POST;
  7. the two PC-only Notion routes are still refused from any other device, and
     the new phone door takes no path;
  8. the twins and the records are in step, so this is not only true in the
     development container.

No model, no network, no owner's file: everything happens in a scratch folder.

`JARVIS_TEST_SCRATCH` (an absolute path) moves that folder. It exists because
this PC has shown %TEMP% write refusals before (CLAUDE.md, the Rust tests), and
a suite that cannot write where it was told to is NOT RUN - never a pass.
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_upload.py", "jarvis_documents.py", "jarvis_attached_file.py",
                "jarvis_asks_first.py", "jarvis_card_words.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_asks_first as AF  # noqa: E402
import jarvis_attached_file as A  # noqa: E402
import jarvis_card_words as W  # noqa: E402
import jarvis_documents as D  # noqa: E402
import jarvis_notion_obsidian as N  # noqa: E402
import jarvis_receipts as R  # noqa: E402
import jarvis_upload as U  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def _scratch_root() -> Path:
    """One disposable folder. An absolute `JARVIS_TEST_SCRATCH` wins."""
    where = os.environ.get("JARVIS_TEST_SCRATCH", "").strip()
    if where and os.path.isabs(where):
        root = Path(where) / "jarvis-upload-tests"
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(tempfile.mkdtemp(prefix="jarvis-upload-tests-"))


try:
    TMP = _scratch_root()
    CONF = TMP / "config"
    CONF.mkdir(exist_ok=True)
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
    os.environ.pop("JARVIS_CONFIG_DIR", None)
    os.environ["JARVIS_UPLOADS_DIR"] = str(TMP / "uploads")
except OSError as exc:                       # a refused scratch folder is NOT a pass
    print(f"NOT RUN  the scratch folder could not be made ({type(exc).__name__}).")
    print("         A suite that tested nothing is not a pass. Set JARVIS_TEST_SCRATCH "
          "to a folder this machine will let it write to.")
    sys.exit(1)

# One settings folder and one uploads root for the whole run, so no check can
# reach the owner's real ~/.openjarvis or %LOCALAPPDATA%.
D._config_dir = lambda: CONF
R._config_dir = lambda: CONF
U.fw = None
N.fw = None
ROOT_FOLDERS = TMP / "listed"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   Stand-ins: a verdict, a gate, and the core's Handler
# --------------------------------------------------------------------------

class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def run_now(fn):
    fn()


def gate_yes(seen=None):
    def gate(action, detail, prompt):
        if seen is not None:
            seen.append((action, detail, prompt))
        return Verdict(True, "approved")
    return gate


def gate_no(outcome="denied", seen=None):
    def gate(action, detail, prompt):
        if seen is not None:
            seen.append((action, detail, prompt))
        return Verdict(False, outcome)
    return gate


class _FakeWFile:
    def __init__(self):
        self.buf = b""

    def write(self, data):
        self.buf += data


class _FakeConn:
    def __init__(self, addr):
        self._addr = addr

    def getsockname(self):
        return self._addr


class Stander:
    """A stand-in for the core's Handler and its three callbacks - the shape
    jarvis_plugins.py calls install() with, and a real answer to read."""

    def __init__(self, origin=True, token=True, peer="100.64.0.9", local="100.64.0.1"):
        self.calls, self.status, self.payload = [], None, None
        self.origin, self.token, self.peer, self.local = origin, token, peer, local
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}"):
                self.path, self.body = path, body
                self.wfile = _FakeWFile()
                self.client_address = (core.peer, 5000)
                self.connection = _FakeConn((core.local, 4719))

            def do_GET(self):
                core.calls.append(("GET", self.path))

            def do_POST(self):
                core.calls.append(("POST", self.path))

            def send_response(self, code):
                core.status = code

            def send_header(self, *args):
                pass

            def end_headers(self):
                pass

            def _send(self, code, payload):        # the core's own helper
                core.status = code
                self.wfile.write(json.dumps(payload).encode("utf-8"))

        self.Handler = Handler

    def origin_ok(self, req):
        return self.origin

    def token_ok(self, req):
        return self.token

    def read_body(self, req):
        return req.body

    def post(self, path, body, how="POST"):
        req = self.Handler(path, body if isinstance(body, bytes)
                           else json.dumps(body).encode("utf-8"))
        getattr(req, "do_" + how)()
        raw = req.wfile.buf.decode("utf-8") or "{}"
        self.payload = json.loads(raw)
        return self.status, self.payload

    def get(self, path):
        return self.post(path, b"{}", how="GET")


# --------------------------------------------------------------------------
#   Real data: a listed folder, the eight kinds, and a real vault
# --------------------------------------------------------------------------

def listed(*names) -> list:
    """A fresh root with one folder per name, on the owner's list."""
    if ROOT_FOLDERS.exists():
        shutil.rmtree(ROOT_FOLDERS)
    ROOT_FOLDERS.mkdir(parents=True)
    made = []
    for name in names or ("Documents",):
        folder = ROOT_FOLDERS / name
        folder.mkdir()
        made.append(folder)
    D._save([{"path": str(f), "added": 1.0} for f in made])
    return made


def pdf_bytes(body=b"Hello from a PDF.\n") -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + body + b"\n%%EOF\n"


def docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def chunks(data: bytes, size: int = U.CHUNK_BYTES) -> list:
    return [data[i:i + size] for i in range(0, len(data), size)] or [b""]


def begin(name, data, into, *, purpose="document", gate=None, spawn=run_now):
    return U.request_begin({"name": name, "size": len(data), "into": str(into),
                            "purpose": purpose,
                            "sha256": hashlib.sha256(data).hexdigest()},
                           gate=gate or gate_yes(), tier_of=lambda a: "ask",
                           spawn=spawn, sweep=False)


def send(uid, data, *, size=U.CHUNK_BYTES):
    """Every chunk in order; returns (last code, last answer, codes)."""
    codes, out = [], {}
    for i, piece in enumerate(chunks(data, size)):
        code, out = U.request_chunk({"id": uid, "index": i,
                                     "data": base64.b64encode(piece).decode("ascii")})
        codes.append(code)
    return codes[-1] if codes else 0, out, codes


def whole(name, data, into, *, purpose="document", gate=None):
    code, out = begin(name, data, into, purpose=purpose, gate=gate)
    if code != 202:
        return code, out
    send(out["id"], data)
    return U.request_finish({"id": out["id"],
                             "sha256": hashlib.sha256(data).hexdigest()})


def fresh():
    U._reset_for_tests()
    N._reset_for_tests()
    shutil.rmtree(str(TMP / "uploads"), ignore_errors=True)
    for folder in ROOT_FOLDERS.glob("*") if ROOT_FOLDERS.exists() else []:
        shutil.rmtree(folder, ignore_errors=True)


# ==========================================================================
#   1. the route contract
# ==========================================================================

def t_the_route_contract():
    fresh()
    # The route test drives the REAL gate through the installed handler, and the
    # card is asked for on its own thread. On a machine whose gate answers in
    # microseconds (a CI runner with no approval UI), the answer could land
    # before begin read the state, so the same request said waiting: true or
    # false depending on timing - it flickered red on CI twice on 2026-11-06
    # while passing 180/180 here. This replaces the thread that raises the card
    # with one that leaves it raised and unanswered, which is exactly the state
    # a phone sees: "a card is waiting for your yes". The card path itself is
    # driven on a real thread by t_the_card_is_raised_before_anything_lands.
    saved_spawn = U._spawn
    U._spawn = lambda fn: None
    into, = listed("Documents")
    stand = Stander()
    line = U.install(stand.Handler, origin_ok=stand.origin_ok,
                     token_ok=stand.token_ok, read_body=stand.read_body)
    check("install() returns a banner line and arms the routes",
          isinstance(line, str) and "upload" in line and U.armed(), line)
    check("the three routes are the three documented ones",
          U.ROUTES == ("/api/upload/begin", "/api/upload/chunk",
                       "/api/upload/finish"), U.ROUTES)

    data = pdf_bytes()
    code, out = stand.post(U.BEGIN_ROUTE, {"name": "taxes.pdf", "size": len(data),
                                           "into": str(into)})
    check("begin from a PHONE address is answered, not refused (no from_this_pc)",
          code == 202 and out.get("id"), (code, out))
    check("... and it says the card is waiting",
          out.get("waiting") is True and out.get("chunk_bytes") == U.CHUNK_BYTES, out)
    uid = out["id"]
    code, out = stand.post("/api/not/a/route", {"x": 1})
    check("a route that is not ours falls through to the original handler",
          stand.calls and stand.calls[-1] == ("POST", "/api/not/a/route"), stand.calls)
    code, out = stand.get(U.BEGIN_ROUTE)
    check("a GET on an upload route is refused, not answered", code == 405, (code, out))

    stand.origin = False
    code, out = stand.post(U.BEGIN_ROUTE, {"name": "a.pdf", "size": 1})
    check("a cross-origin request is refused before anything else", code == 403, (code, out))
    stand.origin = True
    stand.token = False
    code, out = stand.post(U.BEGIN_ROUTE, {"name": "a.pdf", "size": 1})
    check("a bad or missing token is refused", code == 401, (code, out))
    stand.token = True

    stand2 = Stander()
    line2 = U.install(stand2.Handler, origin_ok=stand2.origin_ok,
                      token_ok=stand2.token_ok, read_body=stand2.read_body)
    check("install() arms a second handler with a banner line",
          isinstance(line2, str) and "upload" in line2, line2)
    line3 = U.install(stand2.Handler, origin_ok=stand2.origin_ok,
                      token_ok=stand2.token_ok, read_body=stand2.read_body)
    check("installing twice says it is already on instead of double-wrapping",
          "already on" in line3, line3)
    U._reset_for_tests()
    U._spawn = saved_spawn


# ==========================================================================
#   2. the happy path
# ==========================================================================

def t_the_happy_path_is_chunked_and_lands():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes(b"X" * 3000)
    check("the test file is bigger than one chunk, so the loop is real",
          len(chunks(data, 1024)) >= 3, len(chunks(data, 1024)))
    code, out = begin("Taxes 2025.pdf", data, into)
    check("begin: 202, one id, one chunk size", code == 202 and out.get("id"), (code, out))
    uid = out["id"]
    for i, piece in enumerate(chunks(data, 1024)):
        c, o = U.request_chunk({"id": uid, "index": i,
                                "data": base64.b64encode(piece).decode("ascii")})
        check(f"chunk {i}: 200 and the running total", c == 200
              and o.get("received") == min((i + 1) * 1024, len(data)), (c, o))
    c, fin = U.request_finish({"id": uid, "sha256": hashlib.sha256(data).hexdigest()})
    check("finish: saved", c == 200 and fin.get("saved") is True, (c, fin))
    landed = into / U.SUB / "Taxes 2025.pdf"
    check("it landed in '<the folder>/From my phone', under its own name",
          landed.is_file(), sorted(p.name for p in (into).iterdir()))
    check("the bytes are exactly what the phone sent", landed.read_bytes() == data)
    check("the answer names the folder and the subfolder, in plain words",
          fin.get("folder") == "Documents" and fin.get("sub") == U.SUB
          and "Documents" in fin.get("said", "") and "From my phone" in fin.get("said", ""),
          fin)
    check("NO path is in the answer the phone reads",
          "\\\\" not in json.dumps(fin) and str(TMP) not in json.dumps(fin), fin)
    check("the staging folder is gone", not any(
        p.name.startswith(U.STAGING_PREFIX) for p in into.iterdir()), list(into.iterdir()))
    check("the landed file passes the SAME allow-list every read uses",
          D.allowed_path(str(landed)) is not None)
    found = D.find("taxes", roots=[str(into)])
    check("the existing documents path finds it by name at once (no new code)",
          found.get("ok") and any("Taxes 2025.pdf" in (r.get("name") or "")
                                  for r in found.get("found") or []), found)
    c, again = U.request_finish({"id": uid})
    check("the id is single-use: a second finish saves nothing", c == 410, (c, again))
    c, again = whole("Taxes 2025.pdf", data, into)
    check("a second file of the same name never overwrites the owner's",
          c == 200 and (into / U.SUB / "Taxes 2025 (2).pdf").is_file(),
          sorted(p.name for p in (into / U.SUB).iterdir()))


# ==========================================================================
#   3. the card, and the order of things
# ==========================================================================

def t_the_card_is_raised_before_anything_lands():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes()
    seen, released = [], threading.Event()
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail, prompt))
        released.wait(5)
        return Verdict(True, "approved")

    code, out = U.request_begin({"name": "taxes.pdf", "size": len(data),
                                 "into": str(into)},
                                gate=gate, tier_of=lambda a: "ask",
                                spawn=lambda fn: threading.Thread(target=fn,
                                                                  daemon=True).start())
    check("begin answers at once, while the card is unanswered",
          code == 202 and out.get("waiting") is True, (code, out))
    uid = out["id"]
    for _ in range(200):                     # the card runs on its own thread
        if asked:
            break
        threading.Event().wait(0.02)
    check("ONE card was raised, before any byte was written", len(asked) == 1, asked)
    action, detail, prompt = asked[0]
    check("the card's action is receive_uploaded_document",
          action == "receive_uploaded_document" == U.CARD_ACTION, action)
    check("nothing at all is on disk while the card waits",
          list(into.iterdir()) == [], list(into.iterdir()))
    c, o = U.request_chunk({"id": uid, "index": 0,
                            "data": base64.b64encode(data).decode("ascii")})
    check("a chunk while the card waits: 409 waiting, nothing written",
          c == 409 and o.get("waiting") is True and list(into.iterdir()) == [], (c, o))
    released.set()
    for _ in range(100):
        if U._UP.get(uid, {}).get("state") != "waiting":
            break
        threading.Event().wait(0.02)
    check("after the yes, the entry is approved", U._UP[uid]["state"] == "approved",
          U._UP.get(uid))
    c, o = U.request_chunk({"id": uid, "index": 0,
                            "data": base64.b64encode(data).decode("ascii")})
    check("the same chunk now goes in", c == 200, (c, o))
    c, fin = U.request_finish({"id": uid})
    check("and finish lands it", c == 200 and fin.get("saved") is True, (c, fin))
    check("the card names the file, the size and the folder's NAME",
          "taxes.pdf" in prompt and "Documents" in prompt and str(TMP) not in prompt,
          prompt)
    check("the card carries no path and no bytes in its detail",
          str(TMP) not in json.dumps(detail) and "data" not in detail, detail)
    check("the card does not claim Jarvis opens or runs it",
          "never opened, run or sent" in prompt and "outside text" in prompt, prompt)
    check("the card shows the ONE cap in words",
          f"Files up to {U._cap_words('document')} can be sent from your phone." in prompt,
          prompt)
    check("... and the approval detail carries that same number",
          detail.get("max_bytes") == U.MAX_FILE_BYTES, detail)


def t_a_denied_card_leaves_nothing():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes()
    code, out = begin("taxes.pdf", data, into, gate=gate_no("denied"))
    check("a denied card still answers begin with 202 and an id",
          code == 202 and out.get("waiting") is False, (code, out))
    uid = out["id"]
    c, o = U.request_chunk({"id": uid, "index": 0,
                            "data": base64.b64encode(data).decode("ascii")})
    check("a chunk after a denial: 403 denied, and nothing on disk",
          c == 403 and o.get("denied") is True and list(into.iterdir()) == [], (c, o))
    check("the DENIED words are the app's own sentence",
          o.get("said") == U.DENIED, o)
    check("nothing landed anywhere", not (into / U.SUB).exists())
    c, fin = U.request_finish({"id": uid})
    check("finish after a denial is refused too", c == 403, (c, fin))
    code, out = begin("taxes.pdf", data, into, gate=gate_no("timed_out"))
    c, o = U.request_chunk({"id": out["id"], "index": 0,
                            "data": base64.b64encode(b"x").decode("ascii")})
    check("a card nobody answered leaves nothing either", c == 403
          and list(into.iterdir()) == [], (c, o))
    code, out = begin("t.pdf", data, into,
                      gate=lambda a, d, p: Verdict(True, "approved", tier="auto"))
    check("a gate that answers at a tier other than 'ask' is not a person's yes",
          U._UP[out["id"]]["state"] == "refused", U._UP.get(out["id"]))
    check("... and nothing landed for it", not (into / U.SUB).exists())


# ==========================================================================
#   4. the bytes are checked
# ==========================================================================

def t_the_sha256_and_the_size_are_checked():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes(b"Y" * 2000)
    code, out = begin("taxes.pdf", data, into)
    uid = out["id"]
    send(uid, data, size=1024)
    c, fin = U.request_finish({"id": uid, "sha256": "0" * 64})
    check("a sha256 that does not match is refused", c == 200
          and fin.get("ok") is False and fin.get("said") == U.SHA_BAD, (c, fin))
    check("... and nothing landed", not (into / U.SUB).exists())
    check("... and the staged bytes are gone",
          not (TMP / "uploads").exists() or not any((TMP / "uploads").iterdir()))

    code, out = begin("short.pdf", data, into)
    uid = out["id"]
    send(uid, data[:1000], size=1024)
    c, fin = U.request_finish({"id": uid})
    check("an upload that arrived short is refused, not saved short",
          c == 200 and fin.get("ok") is False and fin.get("said") == U.DID_NOT_ARRIVE,
          (c, fin))
    check("... and nothing landed", not (into / U.SUB).exists())

    code, out = begin("empty.pdf", b"", into)
    check("a zero-byte begin is refused before a card", code == 400, (code, out))


def t_the_caps():
    fresh()
    into, = listed("Documents")
    # ONE constant, 2 GiB (2026-11-13). The next checks raise/lower the module's
    # own constant at run time instead of writing 2 GiB to disk: the card, the
    # refusal sentence and the begin answer must all read the patched number, so
    # none of them can carry a copy of it.
    check("the ONE file cap is 2 GiB (the owner's 2026-11-13 number)",
          U.MAX_FILE_BYTES == 2 * 1024 * 1024 * 1024, U.MAX_FILE_BYTES)
    check("... and the old name is that same number, not a second literal",
          U.MAX_DOC_BYTES == U.MAX_FILE_BYTES
          and "MAX_DOC_BYTES = MAX_FILE_BYTES" in _read(HERE / "jarvis_upload.py"),
          (U.MAX_DOC_BYTES, U.MAX_FILE_BYTES))
    code, out = U.request_begin({"name": "big.pdf", "size": U.MAX_FILE_BYTES + 1,
                                 "into": str(into)}, gate=gate_yes(),
                                tier_of=lambda a: "ask", spawn=run_now, sweep=False)
    exact = U.TOO_BIG_DOC.format(size=U._said_size(U.MAX_FILE_BYTES + 1),
                                 cap=U._cap_words("document"))
    check("a file over the cap is refused with the EXACT sentence",
          code == 413 and out.get("said") == exact, (code, out, exact))
    check("... the sentence names the cap the owner reads: 2 GB",
          "2 GB" in out.get("said", ""), out)
    check("... and the answer carries the same number it enforced",
          out.get("max_bytes") == U.MAX_FILE_BYTES, out)
    code, out = U.request_begin({"name": "big.zip", "size": U.MAX_NOTION_BYTES + 1,
                                 "purpose": "notion", "into": str(into)},
                                spawn=run_now, sweep=False)
    notion_exact = U.TOO_BIG_NOTION.format(size=U._said_size(U.MAX_NOTION_BYTES + 1),
                                           cap=U._cap_words("notion"))
    check("a Notion export over its own cap is refused, with its own exact sentence",
          code == 413 and out.get("said") == notion_exact, (code, out, notion_exact))
    check("... and that sentence says 4 GB, not 4096.0 MB",
          "4 GB" in out.get("said", ""), out)
    check("the two caps are the owner's numbers (Notion raised to 4 GiB 2026-11-09)",
          U.MAX_NOTION_BYTES == 4 * 1024 * 1024 * 1024
          and U.MAX_NOTION_BYTES > U.MAX_FILE_BYTES, U.MAX_NOTION_BYTES)
    check("the staging ceiling can hold one full Notion export",
          U.STAGING_MAX >= U.MAX_NOTION_BYTES, (U.STAGING_MAX, U.MAX_NOTION_BYTES))

    # THE LARGE-FILE PROOF, WITHOUT 2 GiB ON DISK. The cap is moved to 4 KiB for
    # the duration of this block; a real 4,000-byte file is then accepted through
    # the same begin/chunk/finish path and landed byte for byte, and a 5,000-byte
    # one is refused with the sentence naming the PATCHED cap. If any message
    # carried "2 GB" as a literal, these checks fail.
    real = U.MAX_FILE_BYTES
    try:
        U.MAX_FILE_BYTES = 4096
        under = b"Z" * 4000
        code, out = begin("near-cap.dat", under, into)
        check("with a test-only 4 KiB cap, a 4,000-byte file is accepted",
              code == 202 and out.get("max_bytes") == 4096, (code, out))
        uid = out["id"]
        send(uid, under)
        c, fin = U.request_finish({"id": uid})
        landed = into / U.SUB / "near-cap.dat"
        check("... it lands through the SAME finish, byte for byte",
              c == 200 and fin.get("saved") is True and landed.is_file()
              and landed.read_bytes() == under, (c, fin, landed))
        over = b"Z" * 5000
        code, out = U.request_begin({"name": "over.dat", "size": len(over),
                                     "into": str(into)}, gate=gate_yes(),
                                    tier_of=lambda a: "ask", spawn=run_now,
                                    sweep=False)
        patched = U.TOO_BIG_DOC.format(size=U._said_size(len(over)),
                                       cap=U._cap_words("document"))
        check("... and a 5,000-byte one is refused with the PATCHED cap in the sentence",
              code == 413 and out.get("said") == patched and "4 KB" in patched,
              (code, out, patched))
        card = U.card("near-cap.dat", 4000, str(into))
        check("... and the card shows that same patched cap, so it reads the constant",
              "Files up to 4 KB can be sent from your phone." in card, card)
    finally:
        U.MAX_FILE_BYTES = real

    data = b"%PDF-1.4\n" + b"z" * 5000
    code, out = begin("taxes.pdf", data, into)
    uid = out["id"]
    c, o = U.request_chunk({"id": uid, "index": 0,
                            "data": base64.b64encode(b"z" * (U.CHUNK_BYTES + 1)).decode()})
    check("a piece bigger than 1 MiB is refused", c == 413 and o.get("said")
          == U.CHUNK_TOO_BIG, (c, o))
    send(uid, data, size=4096)
    c, o = U.request_chunk({"id": uid, "index": 2,
                            "data": base64.b64encode(b"w" * 10).decode()})
    check("a piece that would run past the declared size is refused",
          c == 413, (c, o))
    U._reset_for_tests()


def t_the_four_mib_body_cap_is_respected():
    check("one piece is 1 MiB of raw bytes", U.CHUNK_BYTES == 1024 * 1024, U.CHUNK_BYTES)
    check("a 2 GiB file is 2,048 pieces, and no piece is bigger than one MiB",
          U.MAX_FILE_BYTES // U.CHUNK_BYTES == 2048, U.MAX_FILE_BYTES // U.CHUNK_BYTES)
    piece = base64.b64encode(b"x" * U.CHUNK_BYTES).decode("ascii")
    body = len(json.dumps({"id": "0" * 32, "index": 0, "data": piece}).encode("utf-8"))
    check("a full chunk's whole request body is far under the server's 4 MiB cap",
          body < 4 * 1024 * 1024 and body < 2 * 1024 * 1024, body)
    check("... and it is under a third of the cap, so a stricter reading still fits",
          body / (4 * 1024 * 1024) < 0.34, body / (4 * 1024 * 1024))


# ==========================================================================
#   5. what may land, and where
# ==========================================================================

def t_the_folder_must_be_on_the_owners_list():
    fresh()
    into, other = listed("Documents", "Photos")
    data = pdf_bytes()
    code, out = begin("taxes.pdf", data, other)
    check("a folder that IS on the list is accepted", code == 202, (code, out))
    code, out = U.request_begin({"name": "t.pdf", "size": 10,
                                 "into": str(TMP / "not-listed")},
                                gate=gate_yes(), tier_of=lambda a: "ask",
                                spawn=run_now, sweep=False)
    check("a folder that is NOT on the list is refused", code == 400, (code, out))
    check("... with the project's own sentence",
          out.get("said", "").startswith(U.FOLDER_NOT_LISTED[:40]), out)
    code, out = U.request_begin({"name": "t.pdf", "size": 10, "into": ""},
                                gate=gate_yes(), tier_of=lambda a: "ask",
                                spawn=run_now, sweep=False)
    check("no folder at all is refused", code == 400, (code, out))

    D._save([])
    code, out = U.request_begin({"name": "t.pdf", "size": 10, "into": str(into)},
                                gate=gate_yes(), tier_of=lambda a: "ask",
                                spawn=run_now, sweep=False)
    check("an empty list says the PC's own line and nothing else",
          code == 409 and out.get("said") == D.PHONE_ADD, (code, out))
    (CONF / "folders.json").write_text("{not json", encoding="utf-8")
    code, out = U.request_begin({"name": "t.pdf", "size": 10, "into": str(into)},
                                gate=gate_yes(), tier_of=lambda a: "ask",
                                spawn=run_now, sweep=False)
    check("a damaged list is refused in the module's own words",
          code == 409 and "damaged" in out.get("said", "").lower(), (code, out))
    listed("Documents")


def t_any_kind_lands_as_a_plain_file():
    """2026-11-13: ANY file type lands as a PLAIN FILE COPY, and nothing reads it.

    The owner asked to "transfer any file type ... up to a reasonably large
    size". The safety shape is the one the document door always had: the bytes
    land unchanged in `From my phone`, nothing runs or opens them, and the
    modules that turn bytes into words still refuse an unfamiliar kind.
    """
    fresh()
    into, = listed("Documents")
    cases = {
        "notes.zip": zip_bytes({"inner.txt": "hi"}),
        "tool.exe": b"MZ\x90\x00" + bytes(60),
        "raw.dat": bytes(range(64)) * 2,
        "clip.mp4": b"\x00\x00\x00\x18ftypmp42" + bytes(60),
        "archive.tar.gz": b"\x1f\x8b\x08" + bytes(60),
        "no-extension": b"plain bytes",
    }
    for name, data in cases.items():
        U._reset_for_tests()
        c, o = whole(name, data, into)
        landed = into / U.SUB / name
        check(f"{name} is accepted and lands byte for byte ({len(data)} bytes)",
              c == 200 and o.get("saved") is True and landed.is_file()
              and landed.read_bytes() == data,
              (c, o, sorted(p.name for p in (into / U.SUB).iterdir())))
    # A `.zip` is NOT the Office kinds' business on this purpose: it is stored,
    # never unpacked. If the door ever sent it through the .docx zip guards this
    # 26 MB-declared bomb would be refused instead of landed.
    bomb = zip_bytes({"word/document.xml": "0" * (26 * 1024 * 1024)})
    U._reset_for_tests()
    c, o = whole("bomb.zip", bomb, into)
    check("a .zip is stored and NEVER unpacked - a zip bomb named .zip lands as bytes",
          c == 200 and o.get("saved") is True
          and (into / U.SUB / "bomb.zip").read_bytes() == bomb, (c, o))

    text = U.card("tool.exe", len(cases["tool.exe"]), str(into))
    check("the card names the file, its size and the folder",
          "File: tool.exe" in text and "Size:" in text
          and "Into: Documents > From my phone" in text, text)
    check("... says it is never opened, run, read, indexed or shown to a model",
          "does not open it, run it, read it, index it or show it to a model" in text, text)
    check("... and does not claim its words were read as outside text",
          "outside text" not in text, text)
    check("... and shows the ONE cap in words",
          "Files up to 2 GB can be sent from your phone." in text, text)

    # THE PRIVACY LINE, on the landed file and the real modules.
    landed = into / U.SUB / "raw.dat"
    got = D.read(str(landed))
    check("the documents reader refuses a .dat", got.get("ok") is False, got)
    attachment = A.read({"name": "raw.dat",
                         "data": base64.b64encode(cases["raw.dat"]).decode("ascii")})
    check("the chat attachment reader refuses a .dat", attachment.get("ok") is False,
          attachment)
    check("the index's own kind set holds no .dat/.zip/.exe/.mp4/.gz",
          not ({".dat", ".zip", ".exe", ".mp4", ".gz"} & set(D.the_index().kinds)),
          sorted(D.the_index().kinds))
    found = D.search("plain bytes", roots=[into])
    check("a folder search never opens a .dat",
          all(row.get("path") != str(landed) for row in found.get("results") or []), found)
    by_name = D.find("raw", roots=[into])
    check("find still reaches it by name - it is a plain file in a listed folder",
          by_name.get("ok") and any("raw.dat" in (r.get("name") or "")
                                    for r in by_name.get("found") or []), by_name)


def t_the_known_kinds_are_still_checked_by_their_bytes():
    """Any TYPE may land; a file that CLAIMS a known kind still has its bytes checked."""
    fresh()
    into, = listed("Documents")
    check("the kinds are the phone's and the attachment reader's SAME eight",
          set(A.KINDS) == set(U._kinds()) == {
              ".pdf", ".docx", ".xlsx", ".pptx", ".md", ".markdown", ".txt", ".csv"},
          sorted(U._kinds()))
    c, o = whole("notes.txt", b"a\x00b", into)
    check("a text file that is really binary is refused at finish", c == 200
          and o.get("said") == U.NOT_PLAIN_TEXT, (c, o))
    c, o = whole("paper.pdf", b"MZ\x90\x00this is not a pdf", into)
    check("a .pdf that is really a program is refused", c == 200
          and "not one" in o.get("said", ""), (c, o))
    c, o = whole("locked.pdf", pdf_bytes(b"/Encrypt 4 0 R"), into)
    check("an encrypted PDF is refused in its own words",
          c == 200 and o.get("said") == U.ENCRYPTED_PDF, (c, o))
    c, o = whole("fake.docx", zip_bytes({"notes.txt": "hi"}), into)
    check("a .docx whose zip holds no word/ part is refused",
          c == 200 and "not one" in o.get("said", ""), (c, o))
    bomb = zip_bytes({"word/document.xml": "0" * (26 * 1024 * 1024)})
    c, o = whole("bomb.docx", bomb, into)
    check("a zip bomb dressed as a .docx is refused from its own directory",
          c == 200 and "unpacks to more than" in o.get("said", ""), (c, o))
    c, o = whole("real.docx", docx_bytes(), into)
    check("a real .docx lands", c == 200 and o.get("saved") is True, (c, o))
    c, o = whole("real.pdf", pdf_bytes(), into)
    check("a real PDF lands", c == 200 and o.get("saved") is True, (c, o))
    check("nothing a refusal touched was written into the folder",
          sorted(p.name for p in (into / U.SUB).iterdir()) == ["real.docx", "real.pdf"],
          sorted(p.name for p in (into / U.SUB).iterdir()))


def t_a_photo_lands_as_a_plain_file():
    """2026-11-13: a photo rides the SAME door, unchanged, and is never read.

    The owner asked Jarvis to send a photo on his phone to the PC and was told
    it could not. The half that was genuinely missing is this one: the folder
    door accepted only the eight document kinds. What must stay true is the
    other half of the answer - no model ever sees the picture's bytes on this
    path - so this test proves the landing AND both readers' refusals.
    """
    fresh()
    into, = listed("Documents")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + bytes(48)
    others = {
        "holiday.jpg": b"\xff\xd8\xff\xe0" + bytes(60),
        "scan.gif": b"GIF89a" + bytes(60),
        "drawing.bmp": b"BM" + bytes(60),
        "picture.webp": b"RIFF" + (60).to_bytes(4, "little") + b"WEBP" + bytes(60),
        "photo.heic": b"\x00\x00\x00\x18ftypheic" + bytes(60),
    }
    code, out = whole("holiday.png", png, into)
    landed = into / U.SUB / "holiday.png"
    check("a photo is accepted by the SAME route, with no new route", code == 200
          and out.get("saved") is True, (code, out))
    check("it lands in '<the folder>/From my phone', under its own name",
          landed.is_file() and out.get("sub") == U.SUB,
          (code, out, sorted(p.name for p in into.iterdir())))
    check("it is a PLAIN FILE COPY: every byte is unchanged, no conversion",
          landed.is_file() and landed.read_bytes() == png, landed)
    check("the answer's sentence names the folder it went into",
          "From my phone" in out.get("said", "") and "Documents" in out.get("said", ""),
          out)
    for name, data in others.items():
        U._reset_for_tests()
        c, o = whole(name, data, into)
        check(f"the same door carries {name} as a plain file",
              c == 200 and o.get("saved") is True and (into / U.SUB / name).read_bytes() == data,
              (c, o))

    # The card says what a photo really is: saved, never read, never modelled.
    text = U.card("holiday.png", len(png), str(into))
    check("a photo's card says it is a photo", "It is a photo" in text, text)
    check("... that Jarvis does not open it or show it to a model on this path",
          "does not open it" in text and "model" in text, text)
    check("... and it does not claim a photo's words were read as outside text",
          "words\nin it count as outside text" not in text, text)
    check("a document's card is unchanged", "outside text" in U.card(
        "taxes.pdf", len(png), str(into)))

    # Other types take the same plain-file road (2026-11-13): a photo is no
    # longer a special allowance - it is one of many plain copies now, and a
    # `.zip`/`.exe`/`.mp4` is accepted on exactly the same terms.
    for ext in (".svg", ".tif", ".mp4", ".zip", ".exe"):
        U._reset_for_tests()
        payload = b"plain bytes for " + ext.encode("ascii")
        c, o = whole("thing" + ext, payload, into)
        check(f"{ext} lands as a plain file too, byte for byte",
              c == 200 and o.get("saved") is True
              and (into / U.SUB / ("thing" + ext)).read_bytes() == payload, (c, o))
    U._reset_for_tests()
    c, o = whole("fake.png", b"MZ\x90\x00" + bytes(60), into)
    check("a program renamed .png is refused by its bytes", c == 200
          and "not one" in o.get("said", "") and not (into / U.SUB / "fake.png").exists(),
          (c, o))
    c, o = whole("fake.heic", b"not a heif at all", into)
    check("a .heic that is not one is refused too", c == 200
          and "not one" in o.get("said", ""), (c, o))

    # THE PRIVACY LINE, MEASURED ON THE LANDED FILE - not asserted in a comment.
    got = D.read(str(landed))
    check("the documents reader still refuses a landed photo", got.get("ok") is False, got)
    check("... saying what it does read",
          "PDF, Word" in got.get("error", "") and "Markdown" in got.get("error", ""), got)
    check("the index never carries a picture kind",
          not any(ext in D.TEXT_KINDS or ext in D.DOC_KINDS
                  for ext in U.PHOTO_EXTENSIONS),
          (sorted(D.TEXT_KINDS), sorted(D.DOC_KINDS)))
    check("the index's own kind set excludes every photo extension",
          not (set(U.PHOTO_EXTENSIONS) & set(D.the_index().kinds)),
          sorted(D.the_index().kinds))
    found = D.search("IHDR", roots=[into])
    check("a folder search never opens a picture",
          all(row.get("path") != str(landed) for row in found.get("results") or []), found)
    attachment = A.read({"name": "holiday.png",
                         "data": base64.b64encode(png).decode("ascii")})
    check("the chat attachment reader still refuses a photo as a document",
          attachment.get("ok") is False and attachment.get("why") == A.WHY_PICTURE,
          attachment)
    check("a photo is not one of the attachment reader's kinds",
          ".png" not in A.KINDS and ".heic" not in A.KINDS, sorted(A.KINDS))


def t_a_name_with_a_path_is_refused():
    fresh()
    into, = listed("Documents")
    for name in ("..\\evil.pdf", "sub/taxes.pdf", "..", ".hidden.pdf", "CON.pdf",
                 "nul.txt", "a" * 200 + ".pdf", "bad\x01name.txt"):
        code, out = U.request_begin({"name": name, "size": 10, "into": str(into)},
                                    gate=gate_yes(), tier_of=lambda a: "ask",
                                    spawn=run_now, sweep=False)
        check(f"{name[:24]!r} is refused", code == 400 and out.get("said") == U.NAME_BAD,
              (code, out))
    check("a name with no folder part is kept exactly", U.safe_name("Taxes 2025.pdf")
          == "Taxes 2025.pdf")


def t_the_staging_folder_is_invisible_before_finish():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes(b"Q" * 4000)
    code, out = begin("secret.pdf", data, into)
    uid = out["id"]
    send(uid, data, size=1024)
    staged = list(into.glob(U.STAGING_PREFIX + "*"))
    check("the staging folder really exists while the upload is in flight",
          len(staged) == 1 and staged[0].is_dir(), staged)
    part = staged[0] / "secret.pdf.part"
    check("the half-written file is there with a .part name", part.is_file(), part)
    check("... and the SAME allow-list every read uses refuses it",
          D.allowed_path(str(part)) is None)
    found = D.find("secret", roots=[str(into)])
    check("find cannot see it", found.get("ok") and not found.get("found"), found)
    read = D.read(str(part)) if hasattr(D, "read") else {"ok": False}
    check("a direct read of it is refused too", read.get("ok") is not True, read)
    U.request_finish({"id": uid})
    check("after finish the .part file is gone",
          not part.exists() and not staged[0].exists(), list(into.iterdir()))


def t_expiry_and_the_sweep():
    fresh()
    into, = listed("Documents")
    data = pdf_bytes()
    code, out = begin("old.pdf", data, into)
    uid = out["id"]
    send(uid, data)
    real = U.LIFETIME
    U.LIFETIME = 0
    try:
        c, o = U.request_chunk({"id": uid, "index": 1,
                                "data": base64.b64encode(b"x").decode()})
        check("an id past its life answers 410, not 200", c == 410 and o.get("said")
              == U.UNKNOWN, (c, o))
        check("... and its staging is deleted with it",
              not any(into.iterdir()), list(into.iterdir()))
    finally:
        U.LIFETIME = real

    # A folder nothing owns (a phone that died mid-upload) is swept on begin.
    stale = TMP / "uploads" / "deadbeef"
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "x.zip").write_bytes(b"junk")
    os.utime(stale, (0, 0))
    code, out = U.request_begin({"name": "new.pdf", "size": len(data), "into": str(into)},
                                gate=gate_yes(), tier_of=lambda a: "ask",
                                spawn=run_now)
    check("a staging folder nobody owns, older than the life, is swept on begin",
          not stale.exists(), list((TMP / "uploads").iterdir())
          if (TMP / "uploads").exists() else "none")
    U._reset_for_tests()


def t_busy_and_the_staging_quota():
    fresh()
    into, = listed("Documents")
    data = b"%PDF-1.4\n" + b"a" * 100
    ids = []
    for i in range(U.MAX_ACTIVE):
        code, out = begin(f"f{i}.pdf", data, into)
        check(f"upload {i + 1} of {U.MAX_ACTIVE} is accepted", code == 202, (code, out))
        ids.append(out["id"])
    code, out = begin("extra.pdf", data, into)
    check("one more is refused, in plain words", code == 409 and out.get("said")
          == U.BUSY, (code, out))
    U._reset_for_tests()
    real = U.STAGING_MAX
    U.STAGING_MAX = 1000
    try:
        code, out = begin("big.pdf", data * 20, into)
        check("the staging quota refuses a file that would overflow it",
              code == 409 and out.get("said") == U.FULL, (code, out))
    finally:
        U.STAGING_MAX = real
    U._reset_for_tests()


# ==========================================================================
#   6. the Notion export, and the phone's two routes
# ==========================================================================

def make_vault(name="My Vault") -> Path:
    vault = TMP / name
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    return vault


def notion_zip() -> bytes:
    return zip_bytes({
        "Export/Meeting Notes 0123456789abcdef0123456789abcdef.md":
            "Meeting Notes\nName: Meeting Notes\nStatus: Done\n\nA body.\n",
        "Export/Tasks 0123456789abcdef0123456789abcdef_all.csv":
            "Name,Status\nShip it,Done\n",
    })


def t_a_notion_export_waiting_for_the_import():
    fresh()
    vault = make_vault()
    listed("Documents")
    data = notion_zip()
    code, out = U.request_begin({"name": "Export.zip", "size": len(data),
                                 "purpose": "notion"},
                                spawn=run_now, sweep=False)
    check("a Notion upload needs no folder and raises NO card here",
          code == 202 and out.get("waiting") is False, (code, out))
    uid = out["id"]
    send(uid, data)
    c, fin = U.request_finish({"id": uid})
    check("finish stages it and says what happens next",
          c == 200 and fin.get("ready") is True and fin.get("said") == U.EXPORT_ARRIVED,
          (c, fin))
    staged = U.staging_file(uid)
    check("the staged file is a real .zip (the importer reads only those)",
          bool(staged) and staged.lower().endswith(".zip") and os.path.isfile(staged),
          staged)
    check("it waits under the uploads root, never under ~/.openjarvis",
          str(staged).startswith(str(TMP / "uploads")), staged)
    check("staging_file is empty for a document id and for junk",
          U.staging_file("nope") == "" and U.staging_file("") == "", "junk")

    code, out = N.phone_import({"upload": uid, "vault": "nope"})
    check("a vault id Jarvis never offered is refused", code == 400
          and out.get("reason") == N.VAULT_NOT_OFFERED, (code, out))
    code, out = N.phone_import({"upload": "nope", "vault": "nope"})
    check("an unknown upload is refused before anything else", code == 410, (code, out))


def t_the_vault_list_and_the_phone_import():
    fresh()
    vault = make_vault("My Vault")
    plain = TMP / "NotAVault"
    plain.mkdir(exist_ok=True)
    import jarvis_notes
    real = jarvis_notes.obsidian_vault
    jarvis_notes.obsidian_vault = lambda: vault
    try:
        out = N.vault_list()
        check("the listed vault is offered, by name, with an opaque id",
              out["ok"] and out["ready"] is True and len(out["vaults"]) == 1
              and out["vaults"][0]["name"] == "My Vault"
              and len(out["vaults"][0]["id"]) == 12, out)
        jarvis_notes.obsidian_vault = lambda: plain
        out = N.vault_list()
        check("a folder with no .obsidian is NOT offered (so it cannot be picked)",
              out["ready"] is False and out["vaults"] == [] and out["said"] == N.VAULTS_SAID,
              out)
    finally:
        jarvis_notes.obsidian_vault = real

    # `plan_import` extracts into a throw-away folder under the OS temp folder,
    # and this PC's temp folder has refused writes before (CLAUDE.md: the Rust
    # tests). Probe it rather than assume: a run that cannot plan is NOT RUN,
    # said out loud - never a pass.
    probe = tempfile.mkdtemp(prefix="jarvis-notion-plan-probe-")
    try:
        Path(probe, "x").write_bytes(b"x")
    except OSError as exc:
        skip(f"the OS temp folder refuses a write, which plan_import needs "
             f"({type(exc).__name__}) - the Notion dry run and import did NOT run")
        shutil.rmtree(probe, ignore_errors=True)
        return
    shutil.rmtree(probe, ignore_errors=True)

    # The dry run: plan only, no card, nothing written into the vault.
    fresh()
    listed("Documents")
    jarvis_notes.obsidian_vault = lambda: vault
    data = notion_zip()
    code, out = U.request_begin({"name": "Export.zip", "size": len(data),
                                 "purpose": "notion"}, spawn=run_now, sweep=False)
    uid = out["id"]
    send(uid, data)
    U.request_finish({"id": uid})
    offered = N.vault_list()["vaults"][0]
    before = sorted(p.name for p in vault.iterdir())
    asked = []
    real_gate = N._gate
    N._gate = gate_yes(asked)
    try:
        code, plan = N.phone_import({"upload": uid, "vault": offered["id"]})
        check("the dry run answers a plan", code == 200 and plan.get("ok") is True
              and isinstance(plan.get("plan"), dict), (code, plan))
        check("the plan names the vault, never a path",
              plan.get("vault") == "My Vault" and str(TMP) not in json.dumps(plan), plan)
        check("the plan hides Jarvis's own staging path",
              "source" not in (plan.get("plan") or {}), plan.get("plan"))
        check("the dry run writes NOTHING into the vault",
              sorted(p.name for p in vault.iterdir()) == before, list(vault.iterdir()))
        check("the dry run raises NO card", asked == [], asked)
        digest = plan["plan"]["digest"]
        check("the plan still has its digest, so the import can be pinned to it",
              isinstance(digest, str) and len(digest) == 16, digest)
        code, done = N.phone_import({"upload": uid, "vault": offered["id"],
                                     "digest": digest})
        check("the import goes through the EXISTING request_import: one card",
              code == 200 and done.get("ok") is True and len(asked) == 1, (code, done))
        check("... and the card is the existing import_notion_export one",
              asked and asked[0][0] == "import_notion_export", asked)
        check("the new folder is in the vault", (vault / done.get("folder", "?")).is_dir(),
              sorted(p.name for p in vault.iterdir()))
        check("the answer names the folder and the vault, never a path",
              "/" not in str(done.get("folder")) and "\\" not in str(done.get("folder"))
              and done.get("vault") == "My Vault" and str(TMP) not in json.dumps(done),
              done)
        check("Undo is kept: a receipt id came back", bool(done.get("receipt_id")), done)
        check("the staged export is deleted once the import attempt ends",
              U.staging_file(uid) == "" and not (TMP / "uploads" / uid).exists())
        check("the vault the import used is remembered for next time",
              N._remembered_vault() == str(vault), N._remembered_vault())

        # A second export, imported with a digest that no longer matches.
        code, out = U.request_begin({"name": "Export2.zip", "size": len(data),
                                     "purpose": "notion"}, spawn=run_now, sweep=False)
        uid2 = out["id"]
        send(uid2, data)
        U.request_finish({"id": uid2})
        code, wrong = N.phone_import({"upload": uid2, "vault": offered["id"],
                                      "digest": "0" * 16})
        check("a digest that no longer matches refuses the import", code == 200
              and wrong.get("ok") is False and len(asked) == 1, (code, wrong))
        check("... and a refused import still deletes the staged export", 
              U.staging_file(uid2) == "")
    finally:
        N._gate = real_gate
    jarvis_notes.obsidian_vault = real


def t_the_phone_refusals_still_hold():
    """The two PC-only Notion routes are untouched; the new door is not PC-only."""
    fresh()
    vault = make_vault()
    listed("Documents")
    phone = Stander(peer="100.64.0.9", local="100.64.0.1")
    N._reset_for_tests()
    N.install(phone.Handler, origin_ok=phone.origin_ok, token_ok=phone.token_ok,
              read_body=phone.read_body)
    asked = []
    real_gate = N._gate
    N._gate = gate_yes(asked)
    try:
        for path in N.PATHS:
            code, out = phone.post(path, {"source": str(vault), "vault": str(vault)})
            check(f"the PC-only route {path} still refuses a phone",
                  code == 403 and out.get("pc_only") is True, (code, out))
            check(f"... and names no path and no folder", str(TMP) not in json.dumps(out),
                  out)
        check("... and raises no card", asked == [], asked)
        code, out = phone.get(N.PHONE_PATHS[0])
        check("the vault list is NOT PC-only: a phone reads it", code == 200, (code, out))
        code, out = phone.post(N.PHONE_PATHS[1], {"upload": "", "vault": ""})
        check("the phone import is NOT PC-only either - it answers about the upload",
              code == 410 and out.get("ok") is False, (code, out))
        check("the two PC-only path routes are still exactly two",
              N.PATHS == ("/api/notion/preview", "/api/notion/import"), N.PATHS)
        check("the phone's two doors take no path",
              N.PHONE_PATHS == ("/api/notion/vaults", "/api/notion/phone-import"),
              N.PHONE_PATHS)
        code, out = D.request_import({"zip": str(vault), "into": str(vault)},
                                     here=False)
        check("/api/folders/import still refuses a phone", code == 403
              and out.get("pc_only") is True, (code, out))
    finally:
        N._gate = real_gate
        N._reset_for_tests()


# ==========================================================================
#   7. the records, the twins and the wiring
# ==========================================================================

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def t_the_card_words_and_the_gate_lists():
    check("TITLES has a plain phrase for the new action",
          W.TITLES.get(U.CARD_ACTION) == "save a document your phone sent",
          W.TITLES.get(U.CARD_ACTION))
    check("SUMMARY has a short one, inside the nine-word limit",
          W.SUMMARY.get(U.CARD_ACTION) == "save a document from your phone"
          and W._short_enough(W.SUMMARY[U.CARD_ACTION]),
          W.SUMMARY.get(U.CARD_ACTION))
    check("it is a HARD LIMIT, so no app can loosen it",
          U.CARD_ACTION in AF.HARD_LIMITS)
    check("... and MUST_ASK, because the module refuses any other tier",
          U.CARD_ACTION in AF.MUST_ASK)
    page = [a for _title, rows in AF.GROUPS for a in rows]
    check("the asks-first page names it, or test_asks_first fails",
          U.CARD_ACTION in page)
    toml = _read(HERE / "rebuilt" / "jarvis-framework.toml")
    check("the shipped settings file gives it its own 'ask' line",
          'receive_uploaded_document = "ask"' in toml)
    check("the three lists and the code agree on the action's name",
          "receive_uploaded_document" in _read(HERE / "jarvis_asks_first.py")
          and "receive_uploaded_document" in _read(HERE / "jarvis_card_words.py")
          and 'CARD_ACTION = "receive_uploaded_document"' in _read(HERE
                                                                   / "jarvis_upload.py"))


def t_the_records_and_the_wiring_are_in_step():
    where = _read(HERE / "_where.py")
    check("the module is on _where.py's SHIPPED list, so it reaches the PC",
          '"jarvis_upload.py"' in where)
    ps1 = _read(REPO / "scripts" / "apply-patches.ps1")
    check("... and on the script's $SHIPPED list too (both or neither)", 
          "'jarvis_upload.py'" in ps1)
    check("_where.py keeps its last-entry property for the jargon ratchet",
          '"jarvis_bench.py"\n' in where and '"jarvis_upload.py",' in where)
    manifest = json.loads(_read(REPO / "plugins" / "ready" / "upload" / "plugin.json")
                          or "{}")
    check("the drop-in folder's manifest names the module and install()",
          manifest.get("module") == "jarvis_upload"
          and manifest.get("install") == "handler"
          and isinstance(manifest.get("stack_order"), int), manifest)
    check("the module has the install() the loader calls", callable(U.install))
    check("the plugin catalogue counts it (regenerated, never hand-typed)",
          '"upload"' in _read(REPO / "plugins" / "registry.json"))
    source = _read(HERE / "jarvis_upload.py")
    check("the file cap is ONE named constant (MAX_FILE_BYTES), not a number in three places",
          source.count("MAX_FILE_BYTES = ") == 1
          and "MAX_DOC_BYTES = MAX_FILE_BYTES" in source
          and source.count("50 * 1024 * 1024") == 0,
          (source.count("MAX_FILE_BYTES = "), source.count("50 * 1024 * 1024")))


def t_the_twins_are_identical():
    pairs = ["jarvis_upload.py", "jarvis_asks_first.py", "jarvis_card_words.py",
             "jarvis_notion_obsidian.py"]
    for name in pairs:
        ours = _read(HERE / name)
        theirs = _read(REPO / "jarvis-backend" / name)
        check(f"jarvis-backend/{name} is this repository's copy",
              bool(ours) and ours == theirs, f"{len(ours)} vs {len(theirs)}")
    toml = _read(HERE / "rebuilt" / "jarvis-framework.toml")
    check("jarvis-backend/jarvis-framework.toml is the rebuilt template",
          toml == _read(REPO / "jarvis-backend" / "jarvis-framework.toml"))


def t_it_opens_no_socket_and_runs_no_program():
    source = _read(HERE / "jarvis_upload.py")
    for banned in ("import socket", "import subprocess", "urllib.request",
                   "http.client", "os.system", "shell=True"):
        check(f"the module never uses {banned}", banned not in source)
    check("it is standard library only, apart from the modules beside it",
          "import requests" not in source and "import aiohttp" not in source)


# ==========================================================================
#   main
# ==========================================================================

def main() -> int:
    tests = (t_the_route_contract,
             t_the_happy_path_is_chunked_and_lands,
             t_the_card_is_raised_before_anything_lands,
             t_a_denied_card_leaves_nothing,
             t_the_sha256_and_the_size_are_checked,
             t_the_caps,
             t_the_four_mib_body_cap_is_respected,
             t_the_folder_must_be_on_the_owners_list,
             t_any_kind_lands_as_a_plain_file,
             t_the_known_kinds_are_still_checked_by_their_bytes,
             t_a_photo_lands_as_a_plain_file,
             t_a_name_with_a_path_is_refused,
             t_the_staging_folder_is_invisible_before_finish,
             t_expiry_and_the_sweep,
             t_busy_and_the_staging_quota,
             t_a_notion_export_waiting_for_the_import,
             t_the_vault_list_and_the_phone_import,
             t_the_phone_refusals_still_hold,
             t_the_card_words_and_the_gate_lists,
             t_the_records_and_the_wiring_are_in_step,
             t_the_twins_are_identical,
             t_it_opens_no_socket_and_runs_no_program)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(str(TMP), ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
