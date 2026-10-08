"""test_screen_attach.py - "look at this" can hand the owner the CLEANED
picture of the look, for the question box (the owner's decision of 2026-10-07;
`.dsh-scratch/SCREEN-ATTACH-DESIGN.md`; jarvis_screen_attach.py, its route
wrapper installed by screen-attach.patch).

    python3 backend/test_screen_attach.py

What it proves, on the REAL route (no network, no Windows, made-up words):
  - the picture the app is handed IS the cleaner's own output
    (`jarvis_picture.clean(..., want_png=True)`): the secret's place is SOLID
    BLACK in it, every other pixel is the picture's, and the base64 the app
    receives decodes to exactly those bytes - THE RAW CAPTURE NEVER CROSSES,
    which is the one thing the retired whole-monitor grab got wrong;
  - `ok: False`, `unchecked: True` and `blocked: True` hand back NO picture
    and one plain sentence; so do a body that is not a PNG, and a picture
    whose size the words were not read from (the design's one security
    decision: an unverified picture is not attached);
  - the look itself is UNCHANGED: the same pause rules in their one order
    (password box, Never look at, capture protection), the same note, the
    words held for the question as outside text, and the picture riding on
    that same message - `turn_has_screen` still true, so the turn stays on
    this PC;
  - the route: origin and token first, THIS PC only (a phone's address gets
    403 and no picture is taken), a look that does not ask for a picture is
    bit-for-bit what it was, every other verb and path is somebody else's;
  - THE PRIVACY LAW still holds with a picture in play: the made-up secret
    and the made-up words reach the question's own text (hidden) and NOWHERE
    else - not the answer, not status(), not the events, not the audit log;
  - the module touches no file, no socket and prints nothing (so nothing of
    the picture can reach a disk or a log), and it is shipped by both lists.
Every "secret" here is made up. No network, no model, no Windows.
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_screen.py", "jarvis_screen_attach.py", "jarvis_picture.py",
                "jarvis_secrets.py", "jarvis_secret_rules.py", "jarvis_screen_win.py",
                "jarvis_front.py", "jarvis_stop_all.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-screen-attach-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
AUDIT = []
fw.audit_log = lambda event, detail=None, **k: AUDIT.append((event, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_picture as P  # noqa: E402
import jarvis_screen as SC  # noqa: E402
import jarvis_screen_attach as SA  # noqa: E402
import jarvis_screen_win as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


TOKEN = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5"          # made up
WORDS = ("Quarterly chart", "balance owed 41,20", "key " + TOKEN, "thanks")
CHAR_W, LINE_H = 8, 16
LOOPBACK, PHONE_IP = "127.0.0.1", "100.101.102.103"


def lines_of(*texts, top=20):
    """Lines as the reader gives them, with positions (CHAR_W per letter)."""
    out = []
    for i, text in enumerate(texts):
        x, words = 10, []
        for w in text.split():
            words.append({"text": w, "left": float(x), "top": float(top + i * 24),
                          "width": float(len(w) * CHAR_W), "height": float(LINE_H)})
            x += len(w) * CHAR_W + 8
        out.append({"text": text, "words": words})
    return out


def picture(w=400, h=120, fill=(230, 230, 230)):
    """A PNG this PC makes (filter 0), with a stripe so a wrong offset shows."""
    bgra = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = (200, 30, 30) if (x // 20 + y // 20) % 3 == 0 else fill
            bgra += bytes((b, g, r, 255))
    return bytes(bgra), W.png_from_bgra(bytes(bgra), w, h), w, h


def pix_at(bgra, w, x, y):
    return bytes(bgra[(y * w + x) * 4:(y * w + x) * 4 + 4])


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class World:
    """One PC: an ordinary window in front, a real PNG, made-up words."""

    def __init__(self, lines=None, *, front=None):
        self.clock = Clock()
        self.bgra, self.png, self.w, self.h = picture()
        self.lines = lines if lines is not None else lines_of(*WORDS)
        self.captures = 0
        self.events = []
        self.never = SC.NeverLook(_TMP / "never-look.json")
        self.front_now = front or {"exe": r"C:\Games\Zqxwarble.exe", "title": "Glorbnax",
                                   "cls": "G", "host": "", "hwnd": 101,
                                   "password_focused": False, "capture_protected": False}
        self.engine = SC.Screen(clock=self.clock, front_reader=lambda: self.front_now,
                                capture=self._capture, ocr=self._ocr,
                                ui_text=lambda s: [{"text": "Account name"},
                                                   {"text": "hunter2-vlorpt", "password": True}],
                                never=self.never,
                                publish=lambda k, d: self.events.append(
                                    (k, json.loads(json.dumps(d)))),
                                run_loop=False)

    def _capture(self, snap, whole):
        self.captures += 1
        return self.png

    def _ocr(self, image):
        return {"ok": True, "text": "\n".join(l["text"] for l in self.lines),
                "left_out": 0, "why": "", "lines": self.lines, "size": (self.w, self.h)}


def decoded(out):
    """(BGRA, w, h) of the answer's picture, or None when it handed back none."""
    pic = out.get("picture")
    if not isinstance(pic, dict):
        return None
    raw = base64.b64decode(pic["data"])
    got = P.decode_png(raw)
    return None if got is None else (got[0], got[1], got[2])


def with_engine(world, fn):
    real = SC.ENGINE
    SC.ENGINE = world.engine
    try:
        return fn()
    finally:
        SC.ENGINE = real


# ------------------------------------------------------- the picture itself

def t_the_picture_is_the_cleaners_output():
    w = World()
    out = with_engine(w, lambda: SA.look_with_picture(w.engine))
    check("a look that asked for the picture answers ok, with the ordinary note",
          out.get("ok") is True and out.get("note") == SC.looked_note(w.engine._look), out)
    pic = out.get("picture") or {}
    check("the answer carries a picture, its type, its size and its byte count",
          pic.get("mime") == "image/png" and pic.get("width") == w.w and pic.get("height") == w.h
          and pic.get("bytes") == len(base64.b64decode(pic.get("data", ""))), pic and list(pic))
    check("... and no `part` (the words) is handed to an app", "part" not in out)
    check("... and no reason why not, because there is a picture",
          not out.get("picture_why"), out)

    # THE ONE THAT MATTERS: what crossed is the CLEANER's picture.
    dec = decoded(out)
    check("the answer's picture really is a PNG this module can decode", dec is not None)
    bgra, dw, dh = dec
    wd = next(word for l in w.lines for word in l["words"] if TOKEN[:12] in word["text"])
    cx, cy = int(wd["left"] + wd["width"] / 2), int(wd["top"] + wd["height"] / 2)
    check("the secret's place is SOLID BLACK in the picture the app gets",
          pix_at(bgra, dw, cx, cy) == b"\x00\x00\x00\xff", pix_at(bgra, dw, cx, cy))
    check("... and it is NOT black in the capture (so something really painted it)",
          pix_at(w.bgra, w.w, cx, cy) != b"\x00\x00\x00\xff")
    cleaned = P.clean(w.png, ocr=w.engine.ocr, want_png=True)
    check("the bytes the app gets are the cleaner's own bytes, byte for byte",
          base64.b64decode(pic["data"]) == cleaned["png"])
    # Every pixel outside a box is the original's: nothing else was painted.
    import jarvis_secrets as SEC
    real_boxes = SEC.redact(w.lines).boxes

    def in_box(x, y):
        return any(int(b[0]) <= x <= int(b[2]) and int(b[1]) <= y <= int(b[3]) for b in real_boxes)
    same = all(pix_at(bgra, dw, x, y) == pix_at(w.bgra, w.w, x, y)
               for x in range(w.w) for y in range(w.h) if not in_box(x, y))
    check("every pixel outside the hidden boxes is the picture's own - nothing else is painted",
          same)
    check("a raw capture never appears anywhere in the answer",
          "PICTURE" not in json.dumps(out) and w.png.hex()[:40] not in json.dumps(out))
    return w, out


def t_the_raw_capture_can_never_cross():
    """The design's first "must be true": the only picture at the boundary is
    the cleaner's output. Proved by making the cleaner answer with a picture
    that is nowhere near the capture, and by making it answer with none."""
    w = World()
    marked = picture(40, 30)[1]
    real = SC.clean_picture
    SC.clean_picture = lambda image, ocr=None, **k: {
        "ok": True, "text": "nothing to hide", "left_out": 0, "hidden": 0, "kinds": [],
        "png": marked, "png_why": "", "why": "", "unchecked": False}
    try:
        out = with_engine(w, lambda: SA.look_with_picture(w.engine))
    finally:
        SC.clean_picture = real
    check("what crosses is what the cleaner returned, not the capture",
          base64.b64decode((out.get("picture") or {}).get("data", "")) == marked
          and marked != w.png, out.get("picture_why"))
    w2 = World()
    SC.clean_picture = lambda image, ocr=None, **k: {
        "ok": True, "text": "", "left_out": 0, "hidden": 0, "kinds": [], "png": None,
        "png_why": P.NOT_DECODED, "why": "", "unchecked": False}
    try:
        out2 = with_engine(w2, lambda: SA.look_with_picture(w2.engine))
    finally:
        SC.clean_picture = real
    check("a cleaner that could not make a picture hands back NO picture, with a plain reason",
          "picture" not in out2 and out2.get("ok") is True and out2.get("picture_why") == SA.NOT_MADE,
          out2)


def t_a_picture_that_could_not_be_checked_is_not_attached():
    """The design's one security decision, in all its shapes."""
    cases = [
        ("ok False", {"ok": False, "text": "", "png": None, "png_why": "no words",
                      "unchecked": False}),
        ("unchecked", {"ok": True, "text": "x", "png": None, "png_why": "no positions",
                       "unchecked": True}),
        ("blocked", {"ok": True, "text": "x", "png": None, "png_why": "", "blocked": True}),
        ("not a PNG", {"ok": True, "text": "x", "png": b"not a png at all", "unchecked": False}),
        ("size not read from", {"ok": True, "text": "x", "png": None,
                                "png_why": P.SIZE_DIFFERS, "unchecked": False}),
    ]
    real = SC.clean_picture
    for label, got in cases:
        w = World()
        SC.clean_picture = lambda image, ocr=None, **k: dict(got)
        try:
            out = with_engine(w, lambda: SA.look_with_picture(w.engine))
        finally:
            SC.clean_picture = real
        why = out.get("picture_why") or ""
        check(f"{label}: no attachment, and the look itself still happened",
              out.get("ok") is True and "picture" not in out and why in
              (SA.NOT_CHECKED, SA.NOT_MADE, SA.BLOCKED), out)
        check(f"... and the sentence is plain words, naming nothing of the screen",
              bool(why) and not any(x in why for x in ("Glorbnax", "Zqxwarble", TOKEN, "{")))
    # Nothing predicted: refused in plain words, never raised, never a class name.
    w = World()

    def boom(image, ocr=None, **k):
        raise RuntimeError("something nobody predicted")
    SC.clean_picture = boom
    try:
        out = with_engine(w, lambda: SA.look_with_picture(w.engine))
    finally:
        SC.clean_picture = real
    check("a cleaner that raises: refused in plain words, and the promise holds",
          out.get("ok") is False and out.get("said") == SA.LOOK_FAILED
          and "RuntimeError" not in json.dumps(out), out)


def t_a_refused_look_hands_back_nothing():
    for label, front, why in (
        ("a password box", {"password_focused": True}, "password_box"),
        ("capture protection", {"capture_protected": True}, "protected"),
        ("a Never look at window", {"exe": r"C:\Games\Keepass.exe"}, "never_look"),
    ):
        w = World(front={"exe": r"C:\Games\Zqxwarble.exe", "title": "Glorbnax", "cls": "G",
                         "host": "", "hwnd": 101, "password_focused": False,
                         "capture_protected": False, **front})
        out = with_engine(w, lambda: SA.look_with_picture(w.engine))
        check(f"{label}: no look, no picture, and the PC's own plain reason",
              out.get("ok") is False and out.get("paused") == why and "picture" not in out
              and out.get("said") == SC.said_for(why), out)


def t_the_picture_goes_through_the_one_cleaner_once():
    """`Screen._read` cleans the picture for its words; this look has to clean it
    for the picture too. It must be ONE pass, asking for the PNG - a second pass
    would read the screen's words twice and could disagree with itself."""
    w = World()
    real = SC.clean_picture
    calls = []

    def counting(image, ocr=None, **k):
        calls.append(bool(k.get("want_png")))
        return real(image, ocr=ocr, **k)
    SC.clean_picture = counting
    try:
        out = with_engine(w, lambda: SA.look_with_picture(w.engine))
    finally:
        SC.clean_picture = real
    check("the picture goes through the ONE cleaner exactly once, asking for the PNG",
          calls == [True] and out.get("ok") is True, calls)


# ------------------------------------------------------------- the words

def t_the_words_are_held_for_the_question_and_are_outside_text():
    w = World()
    out = with_engine(w, lambda: SA.look_with_picture(w.engine))
    # A question that carries the mark reads the look, exactly as before.
    msgs = [{"role": "user", "content": [{"type": "text", "text": "what is this?"},
                                         {"type": "image_url",
                                          "image_url": {"url": "data:image/png;base64,"
                                                        + (out["picture"]["data"] if out.get("picture") else "")}}],
             "screen": "look"}]
    got, info = SC.with_screen(msgs, "look", engine=w.engine)
    flat = json.dumps(got)
    check("the marked question gets the look's words as its OWN part, labelled outside text",
          info["read"] and SC.SCREEN_TEXT_HEAD in flat, flat[:200])
    check("... with the secret hidden, and never the secret itself",
          "[hidden]" in flat and TOKEN not in flat, flat[:300])
    check("... the password box's value is not there either", "hunter2-vlorpt" not in flat)
    check("... and the picture the app attached rides on that same message",
          any(isinstance(p, dict) and p.get("type") == "image_url"
              for p in got[0]["content"]), repr(got[0]["content"])[:200])
    check("... so the turn is still a screen turn, and stays on this PC",
          SC.turn_has_screen(got) is True)
    check("THE PRIVACY LAW: the secret is in the model's text only as [hidden] - nowhere else",
          all(TOKEN not in json.dumps(x) for x in (out, w.engine.status(), w.events, AUDIT)))
    check("the audit line carries counts only, and says this look attached a picture",
          any(e == "screen.look" and d.get("attach") is True and d.get("hidden") == 1
              and d.get("png_bytes") and TOKEN not in json.dumps(d) for e, d in AUDIT), AUDIT[-3:])


# ---------------------------------------------------------------- the route

class FakeHandler:
    """Just enough of the server's handler for install()."""
    sent = []

    def __init__(self, path, ip=LOOPBACK, body=b""):
        self.path, self.client_address, self.body = path, (ip, 5555), body
        self.connection = types.SimpleNamespace(getsockname=lambda: (LOOPBACK, 4719))

    def _send(self, code, obj):
        FakeHandler.sent.append((code, obj))

    def do_GET(self):
        FakeHandler.sent.append(("orig-get", self.path))

    def do_POST(self):
        FakeHandler.sent.append(("orig-post", self.path))


def t_the_route():
    w = World()
    ok = {"origin": True, "token": True}
    FakeHandler.sent = []
    try:
        SC.install(FakeHandler, origin_ok=lambda h: ok["origin"], token_ok=lambda h: ok["token"],
                   read_body=lambda h: h.body)
        banner = SA.install(FakeHandler, origin_ok=lambda h: ok["origin"],
                            token_ok=lambda h: ok["token"], read_body=lambda h: h.body)
        check("install says what it is", "cleaned picture" in banner, banner)
        check("installing twice does nothing", "already on" in SA.install(
            FakeHandler, origin_ok=lambda h: True, token_ok=lambda h: True,
            read_body=lambda h: b""))
        SC.ENGINE = w.engine
        FakeHandler("/api/models").do_GET()
        FakeHandler("/api/chat").do_POST()
        check("every other path goes to the original",
              FakeHandler.sent == [("orig-get", "/api/models"), ("orig-post", "/api/chat")],
              FakeHandler.sent)
        FakeHandler.sent = []
        FakeHandler("/api/screen").do_GET()
        check("GET /api/screen is still the screen route's own", FakeHandler.sent[0][0] == 200,
              FakeHandler.sent)
        # A look that does not ask for a picture is exactly what it was.
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"look"}').do_POST()
        code, plain = FakeHandler.sent[0]
        check("a look with no `want` is unchanged, and has no picture key at all",
              code == 200 and plain.get("ok") is True and "picture" not in plain
              and "picture_why" not in plain and "part" not in plain, plain)
        w.captures = 0
        # ... and the one that does ask.
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"look","want":"picture"}').do_POST()
        code, out = FakeHandler.sent[0]
        check("a look that asks for the picture answers 200 with a cleaned one",
              code == 200 and out.get("ok") is True
              and (out.get("picture") or {}).get("mime") == "image/png"
              and w.captures == 1, out)
        check("... and still no `part`", "part" not in out)
        # The checks come first.
        FakeHandler.sent = []
        ok["token"] = False
        FakeHandler("/api/screen", body=b'{"do":"look","want":"picture"}').do_POST()
        check("the token check comes first: no picture without it",
              FakeHandler.sent == [(401, {"error": "bad or missing X-Jarvis-Token"})]
              and w.captures == 1, FakeHandler.sent)
        ok["token"], ok["origin"] = True, False
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"look","want":"picture"}').do_POST()
        check("... and the origin check", FakeHandler.sent[0][0] == 403 and w.captures == 1)
        ok["origin"] = True
        FakeHandler.sent = []
        FakeHandler("/api/screen", ip=PHONE_IP, body=b'{"do":"look","want":"picture"}').do_POST()
        check("a picture from a phone's address: 403, and the screen is never captured",
              FakeHandler.sent[0][0] == 403 and FakeHandler.sent[0][1].get("error")
              == SC.LOCAL_ONLY_SAYS and w.captures == 1, FakeHandler.sent)
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b"not json").do_POST()
        check("a body that is not JSON: 400", FakeHandler.sent[0][0] == 400)
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'["a list"]').do_POST()
        check("a body that is not an object: the screen route's own 400",
              FakeHandler.sent[0][0] == 400, FakeHandler.sent)
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"peek","want":"picture"}').do_POST()
        check("an unknown verb is still the screen route's own 400",
              FakeHandler.sent[0][0] == 400, FakeHandler.sent)
        # The session verbs are untouched.
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"start","minutes":20}').do_POST()
        check("Watch with me still starts through the same route",
              FakeHandler.sent[0][0] == 200 and FakeHandler.sent[0][1]["on"] is True,
              FakeHandler.sent)
        FakeHandler.sent = []
        FakeHandler("/api/screen", body=b'{"do":"stop"}').do_POST()
        check("... and stops", FakeHandler.sent[0][0] == 200)
    finally:
        SC.ENGINE = SC_REAL
        ok["origin"] = ok["token"] = True


SC_REAL = SC.ENGINE


# ------------------------------------------------------------- the module

def t_hygiene():
    src = (HERE / "jarvis_screen_attach.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    # `urllib.parse.urlsplit` is allowed - it is pure text parsing, the same
    # import jarvis_screen.py's own wrapper uses; anything that could open a
    # file, a socket or a log is not.
    check("the module opens no file, writes nothing, and reaches no network",
          "urllib.request" not in code
          and not any(x in code for x in ("open(", "write_bytes", "write_text", "urlopen",
                                          "urlretrieve", "socket.", "http.client", "requests.",
                                          "subprocess", "tempfile", "logging")))
    check("... and it prints nothing at all, so no picture or word can reach a log",
          "print(" not in code and "eprintln" not in code)
    check("... and it is the ONE cleaner it uses: no second painting anywhere",
          "clean_picture" in code and "paint_black" not in code and "decode_png" not in code)
    check("... and it never takes a picture of its own: the engine's grab does that",
          "SC.ENGINE.never" not in code and "_grab(" in code and "capture(" not in code)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("it is shipped whole (apply-patches.ps1), and in the same list the suites read",
          "'jarvis_screen_attach.py'" in ps1
          and "jarvis_screen_attach.py" in __import__("_where").SHIPPED)
    check("its base copy is in the published backend too",
          (REPO / "jarvis-backend" / "jarvis_screen_attach.py").is_file())
    check("the patch that wires it is in the script's list, and last",
          "'screen-attach.patch'" in ps1 and "screen-attach.patch" in __import__("_stack").order()
          and __import__("_stack").order()[-1] == "screen-attach.patch")
    patch = (HERE / "screen-attach.patch").read_text(encoding="utf-8")
    check("the patch wires it into jarvis_hud.py and edits no shipped file",
          "jarvis_screen_attach.install(Handler" in patch and "+++ b/jarvis_hud.py" in patch
          and "+++ b/jarvis_screen" not in patch)


def main():
    for fn in (t_the_picture_is_the_cleaners_output, t_the_raw_capture_can_never_cross,
               t_a_picture_that_could_not_be_checked_is_not_attached,
               t_a_refused_look_hands_back_nothing, t_the_picture_goes_through_the_one_cleaner_once,
               t_the_words_are_held_for_the_question_and_are_outside_text,
               t_the_route, t_hygiene):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print("FAIL " + fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
