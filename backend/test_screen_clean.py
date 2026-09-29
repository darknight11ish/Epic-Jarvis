"""test_screen_clean.py - the picture half of screen safety: secrets in a
picture of the screen are painted SOLID BLACK before anything reads it or
looks at it (jarvis_picture.py, jarvis_screen.clean_picture, and the places
in jarvis_screen.py that use them).

    python3 backend/test_screen_clean.py

What it proves (the owner's "all three", 2026-09-29, part 1):
  - the small PNG reader gets back every pixel of a PNG this PC makes, and of
    ordinary PNGs written with each of the five row filters, in grey, RGB,
    RGBA and palette; it refuses what it cannot read (16-bit, interlaced,
    truncated, too big) instead of guessing;
  - the black box: EXACTLY the box is (0, 0, 0), everything outside it is
    untouched, a box is rounded OUT, one past the edge is clipped, one wholly
    outside is nothing;
  - clean(): a secret in the words is replaced by "[hidden]"; with a picture,
    the returned PNG has black where the secret was and is otherwise the
    same picture; the original bytes are handed on ONLY when nothing was
    hidden; and every way it cannot be done gives NO picture - words without
    positions, a JPEG nothing can open, a picture whose size is not the size
    the words came from, the check itself failing;
  - the doors in jarvis_screen.py: a look's words, the window's own text, the
    phone's screen text and the phone's screen PICTURE all have secrets
    hidden, and the cut to 4,500 characters can never leave half a secret
    in; a check that cannot run says so to the model instead of handing on
    unchecked words;
  - the new pause: the front window is a private browser window;
  - the streaming sites are on the built-in Never look at list;
  - THE PRIVACY LAW still holds: a made-up secret and made-up words reach
    the model's text (hidden) and NOWHERE else - not status(), the events or
    the audit log.
Every "secret" here is made up. No network, no model, no Windows.
"""
from __future__ import annotations

import base64
import struct
import sys
import tempfile
import traceback
import types
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_screen.py", "jarvis_picture.py", "jarvis_secrets.py",
                "jarvis_secret_rules.py", "jarvis_screen_win.py", "jarvis_front.py",
                "jarvis_stop_all.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-screen-clean-"))
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
import jarvis_screen_win as W  # noqa: E402
import jarvis_secrets as SEC  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


TOKEN = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5"         # made up
CHAR_W, LINE_H = 8, 16


def lines_of(*texts, top=20):
    """Lines as the reader gives them, with positions (words CHAR_W per letter)."""
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
    """A PNG this PC makes (filter 0), all one colour but with a stripe so a
    wrong offset would show."""
    bgra = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = (200, 30, 30) if (x // 20 + y // 20) % 3 == 0 else fill
            bgra += bytes((b, g, r, 255))
    return bytes(bgra), W.png_from_bgra(bytes(bgra), w, h), w, h


# ---------------------------------------------------------------- PNG reader

def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_with_filters(rows, w, ctype, chans, plte=b"", depth=8, interlace=0, filters=None):
    """Encode `rows` (lists of channel bytes) with a chosen row filter each."""
    stride = w * chans
    raw, prev = bytearray(), bytearray(stride)
    for y, row in enumerate(rows):
        f = (filters or [0])[y % len(filters or [0])]
        cur = bytearray(row)
        out = bytearray(stride)
        for i in range(stride):
            a = cur[i - chans] if i >= chans else 0
            b = prev[i]
            c = prev[i - chans] if i >= chans else 0
            if f == 0:
                pred = 0
            elif f == 1:
                pred = a
            elif f == 2:
                pred = b
            elif f == 3:
                pred = (a + b) >> 1
            else:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[i] = (cur[i] - pred) & 255
        raw += bytes([f]) + out
        prev = cur
    body = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, len(rows), depth, ctype, 0, 0, interlace)))
    if plte:
        body += chunk(b"PLTE", plte)
    return body + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def t_png():
    bgra, png, w, h = picture(60, 40)
    got = P.decode_png(png)
    check("a PNG this PC made is read back pixel for pixel",
          got is not None and got[1:] == (w, h) and bytes(got[0]) == bgra)
    w, h = 9, 7
    rgb = [[(x * 30 + y * 7 + c * 50) % 256 for x in range(w) for c in range(3)] for y in range(h)]
    want = bytearray()
    for row in rgb:
        for x in range(w):
            want += bytes((row[x * 3 + 2], row[x * 3 + 1], row[x * 3], 255))
    for f in range(5):
        p = png_with_filters(rgb, w, 2, 3, filters=[f])
        g = P.decode_png(p)
        check(f"RGB with row filter {f} is read correctly", g is not None and bytes(g[0]) == bytes(want))
    p = png_with_filters(rgb, w, 2, 3, filters=[1, 2, 3, 4, 0, 4, 3])
    g = P.decode_png(p)
    check("... and with a different filter on every row", g is not None and bytes(g[0]) == bytes(want))
    rgba = [[(x * 40 + y * 9 + c * 13) % 256 for x in range(w) for c in range(4)] for y in range(h)]
    wa = bytearray()
    for row in rgba:
        for x in range(w):
            wa += bytes((row[x * 4 + 2], row[x * 4 + 1], row[x * 4], row[x * 4 + 3]))
    g = P.decode_png(png_with_filters(rgba, w, 6, 4, filters=[4, 1]))
    check("RGBA keeps its alpha", g is not None and bytes(g[0]) == bytes(wa))
    grey = [[(x * 20 + y) % 256 for x in range(w)] for y in range(h)]
    g = P.decode_png(png_with_filters(grey, w, 0, 1, filters=[2]))
    check("grey is read as grey", g is not None and g[0][0:4] == bytes((grey[0][0],) * 3 + (255,)))
    pal = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])
    idx = [[(x + y) % 3 for x in range(w)] for y in range(h)]
    g = P.decode_png(png_with_filters(idx, w, 3, 1, plte=pal))
    check("a palette picture is read through its palette (red first, as B G R A)",
          g is not None and bytes(g[0][0:4]) == bytes((0, 0, 255, 255)))
    old_f = P.MAX_FILTERED_PIXELS
    P.MAX_FILTERED_PIXELS = 10
    try:
        check("a big PNG that needs the slow row filters is refused (this PC's own never does)",
              P.decode_png(png_with_filters(rgb, w, 2, 3, filters=[1])) is None)
        check("... a big one with no filters is still read quickly",
              P.decode_png(png_with_filters(rgb, w, 2, 3, filters=[0])) is not None)
    finally:
        P.MAX_FILTERED_PIXELS = old_f
    check("16-bit is refused, not guessed", P.decode_png(png_with_filters(grey, w, 0, 1, depth=16)) is None)
    check("an interlaced PNG is refused",
          P.decode_png(png_with_filters(grey, w, 0, 1, interlace=1)) is None)
    check("a truncated PNG is refused", P.decode_png(png[:len(png) // 2]) is None)
    check("garbage and a JPEG are refused",
          P.decode_png(b"\xff\xd8\xff\xe0not a png") is None and P.decode_png(b"") is None)
    big = png_with_filters([[0] * 9], 3, 2, 3)
    old = P.MAX_PIXELS
    P.MAX_PIXELS = 2
    try:
        check("more pixels than the limit are refused", P.decode_png(big) is None)
    finally:
        P.MAX_PIXELS = old


def t_paint():
    w, h = 20, 10
    src = bytearray(bytes((10, 20, 30, 255)) * (w * h))
    pix = bytearray(src)
    n = P.paint_black(pix, w, h, [(5.2, 2.1, 9.4, 4.6)])
    inside = {(x, y) for x in range(5, 10) for y in range(2, 5)}          # rounded OUT
    ok_in = all(pix[(y * w + x) * 4:(y * w + x) * 4 + 4] == b"\x00\x00\x00\xff" for x, y in inside)
    ok_out = all(pix[(y * w + x) * 4:(y * w + x) * 4 + 4] == b"\x0a\x14\x1e\xff"
                 for x in range(w) for y in range(h) if (x, y) not in inside)
    check("a box is rounded OUT and is exactly solid black inside", n == 1 and ok_in)
    check("... and nothing outside it changes", ok_out)
    pix = bytearray(src)
    P.paint_black(pix, w, h, [(-5, -5, 3, 3), (18, 8, 40, 40)])
    check("a box past the edge is clipped to the picture",
          pix[0:4] == b"\x00\x00\x00\xff" and pix[((h - 1) * w + w - 1) * 4:((h - 1) * w + w - 1) * 4 + 4]
          == b"\x00\x00\x00\xff" and pix[(3 * w + 3) * 4:(3 * w + 3) * 4 + 4] == b"\x0a\x14\x1e\xff")
    pix = bytearray(src)
    n = P.paint_black(pix, w, h, [(50, 50, 60, 60), (5, 5, 5, 9), (-9, 0, -1, 5)])
    check("a box wholly outside, or with no area, paints nothing", n == 0 and pix == src)


# ---------------------------------------------------------------- clean()

def reader(lines, ok=True, size=None, text=None):
    def read(image):
        if not ok:
            return {"ok": False, "text": "", "left_out": 0, "why": "no words"}
        return {"ok": True, "text": text if text is not None else "\n".join(l["text"] for l in lines),
                "left_out": 0, "why": "", "lines": lines, "size": size}
    return read


def pix_at(bgra, w, x, y):
    return bytes(bgra[(y * w + x) * 4:(y * w + x) * 4 + 4])


def t_clean():
    bgra, png, w, h = picture()
    L = lines_of("nothing here", "my token is " + TOKEN + " ok", "bye")
    res = P.clean(png, ocr=reader(L, size=(w, h)), want_png=True)
    check("the words come back with the secret hidden", res["ok"] and "[hidden]" in res["text"]
          and TOKEN not in res["text"] and res["hidden"] == 1, str(res)[:200])
    check("a cleaned PNG comes back, and it is not the original", res["png"] and res["png"] != png)
    dec = P.decode_png(res["png"])
    wd = L[1]["words"][3]
    cx, cy = int(wd["left"] + wd["width"] / 2), int(wd["top"] + wd["height"] / 2)
    check("the secret's place is SOLID BLACK in it", dec is not None and pix_at(dec[0], w, cx, cy) == b"\x00\x00\x00\xff"
          and pix_at(dec[0], w, int(wd["left"]) + 1, int(wd["top"]) + 1) == b"\x00\x00\x00\xff")
    # Every pixel that is not in a box is the original's.
    boxes = SEC.redact(L).boxes
    inbox = lambda x, y: any(int(b[0]) <= x < int(b[2]) + 1 and int(b[1]) <= y < int(b[3]) + 1 for b in boxes)  # noqa: E731
    same = all(pix_at(dec[0], w, x, y) == pix_at(bgra, w, x, y) for x in range(w) for y in range(h)
               if not inbox(x, y))
    check("... and every pixel outside the boxes is the original's", same)
    check("the text is not cut to any length here (the caller cuts it)", res["left_out"] == 0)

    res = P.clean(png, ocr=reader(lines_of("all quiet", "on the screen"), size=(w, h)), want_png=True)
    check("nothing hidden: the ORIGINAL bytes come back, nothing to paint",
          res["ok"] and res["hidden"] == 0 and res["png"] == png)
    res = P.clean(png, ocr=reader([], size=(w, h), text=""), want_png=True)
    check("a reader that gives positions and found NO words: nothing to hide, the picture as it was",
          res["ok"] and res["text"] == "" and res["png"] == png)
    res = P.clean(png, ocr=reader(L, size=(w, h)), want_png=False)
    check("without want_png no picture is made", res["ok"] and res["png"] is None)

    # ---- every way the picture cannot be made: NO picture, but the words stay hidden
    plain = "Password: hunter2 and more"
    res = P.clean(png, ocr=lambda image: plain, want_png=True)
    check("words with no positions: hidden in the text, NO picture (fail closed)",
          res["ok"] and "[hidden]" in res["text"] and res["png"] is None
          and res["png_why"] == P.NO_POSITIONS)
    unpos = [{"text": "Password: hunter2", "words": [{"text": "Password:"}, {"text": "hunter2"}]}]
    res = P.clean(png, ocr=reader(unpos), want_png=True)
    check("a hidden word the reader gave no position for: NO picture",
          res["ok"] and res["png"] is None and res["png_why"] == P.NO_POSITIONS)
    res = P.clean(b"\xff\xd8\xff\xe0jpegish", ocr=reader(L, size=(w, h)), want_png=True,
                  reader_with_pixels=lambda image: {})
    check("a picture nothing can open (a JPEG, no Windows): NO picture",
          res["ok"] and res["png"] is None and res["png_why"] == P.NOT_DECODED)
    res = P.clean(b"\xff\xd8\xff\xe0jpegish", ocr=reader(L, size=(w, h)), want_png=True,
                  reader_with_pixels=lambda image: {"pixels": (bgra, w, h)})
    d2 = P.decode_png(res["png"]) if res["png"] else None
    check("a JPEG Windows itself opened is painted on the pixels Windows gave",
          d2 is not None and pix_at(d2[0], w, cx, cy) == b"\x00\x00\x00\xff")
    res = P.clean(png, ocr=reader(L, size=(w + 1, h)), want_png=True)
    check("a picture whose size is not the size the words came from: NO picture",
          res["ok"] and res["png"] is None and res["png_why"] == P.SIZE_DIFFERS)
    res = P.clean(png, ocr=reader([], ok=False), want_png=True)
    check("the reader failing: not ok, no words, no picture",
          res["ok"] is False and res["text"] == "" and res["png"] is None)
    res = P.clean(png, ocr=lambda image: 1 / 0, want_png=True)
    check("the reader raising: the same, quietly", res["ok"] is False and res["png"] is None)
    res = P.clean(png, ocr=lambda image: 42, want_png=True)
    check("a reader that answers nonsense: the same", res["ok"] is False and res["png"] is None)
    real = SEC.check

    def cannot(lines, **k):
        raise SEC.Unchecked("test")
    SEC.check = cannot
    try:
        res = P.clean(png, ocr=reader(L, size=(w, h)), want_png=True)
    finally:
        SEC.check = real
    check("the secret check failing: NO words, NO picture, and it says the check could not run",
          res["ok"] is False and res["text"] == "" and res["png"] is None and res["unchecked"] is True)

    def boom(lines, **k):
        raise ValueError("odd")
    SEC.check = boom
    try:
        res = P.clean(png, ocr=reader(L, size=(w, h)), want_png=True)
    finally:
        SEC.check = real
    check("... whatever went wrong in it", res["ok"] is False and res["unchecked"] is True)


# ---------------------------------------------------------------- jarvis_screen

class World:
    def __init__(self, ocr):
        self.events, self.now = [], 1_800_000_000.0
        self.never = SC.NeverLook(Path(tempfile.mkdtemp(prefix="jarvis-never-")) / "n.json")
        self.front_now = {"exe": r"C:\Games\Zqxwarble.exe", "title": "Glorbnax", "cls": "G", "host": "",
                          "hwnd": 7, "password_focused": False, "capture_protected": False}
        self.engine = SC.Screen(clock=lambda: self.now, front_reader=lambda: self.front_now,
                                capture=lambda s, whole: b"PICTURE", ocr=ocr,
                                ui_text=lambda s: [{"text": "Account"}, {"text": "hunter2-vlorpt", "password": True}],
                                never=self.never, publish=lambda k, d: self.events.append((k, d)),
                                run_loop=False)


def t_screen():
    L = lines_of("Balance owed", "key " + TOKEN, "thanks")
    w = World(reader(L, size=(400, 120)))
    out = w.engine.look_at_this()
    part = out["part"]
    check("a look's words have the secret hidden, and the model is told something was hidden",
          out["ok"] and "[hidden]" in part and TOKEN not in part and SC.SCREEN_TEXT_HIDDEN.format(n=1) in part,
          part)
    check("the words that are not secrets are still there", "Balance owed" in part and "thanks" in part)
    check("the password box's value is still skipped", "hunter2-vlorpt" not in part)
    leaks = repr(w.engine.status()) + repr(w.events) + repr(AUDIT)
    check("THE PRIVACY LAW: the secret is nowhere but hidden - not in status, events or the audit log",
          TOKEN not in leaks and TOKEN[:12] not in leaks and "aB3dE5" not in leaks)
    check("the audit log carries only a count of what was hidden",
          any(e == "screen.look" and d.get("hidden") == 1 for e, d in AUDIT))
    check("status() has exactly its fixed keys", tuple(w.engine.status()) == SC.STATUS_KEYS)

    # the cut cannot leave half a secret in
    pad = " ".join(["filler"] * 640)                    # about 4,480 characters
    text_lines = lines_of(pad[:4470], "abc " + TOKEN + " tail")
    w = World(reader(text_lines, size=(400, 120)))
    part = w.engine.look_at_this()["part"]
    bits = [TOKEN[:6], TOKEN[6:14], TOKEN[14:22], TOKEN[22:30], TOKEN[30:]]
    check("the cut to 4,500 characters cannot leave part of a secret behind",
          not any(b in part for b in bits), part[-300:])

    def cannot(lines, **k):
        raise SEC.Unchecked("test")
    real = SEC.check
    SEC.check = cannot
    try:
        w = World(reader(L, size=(400, 120)))
        part = w.engine.look_at_this()["part"]
    finally:
        SEC.check = real
    check("when the check cannot run, the model is told so and given NO words",
          SC.SCREEN_TEXT_UNCHECKED in part and "Balance owed" not in part and TOKEN not in part, part)

    w = World(reader(lines_of("plain words"), size=(400, 120)))
    w.front_now["title"] = "notes " + TOKEN
    out = w.engine.look_at_this()
    check("a window's TITLE has secrets hidden too (a tab can be named after a token)",
          TOKEN not in out["part"] and "notes [hidden]" in out["part"], out["part"])
    text, left = SC.ui_words([{"text": "Name"}, {"text": "token " + TOKEN}, {"text": "x", "password": True}])
    check("the window's own text has secrets hidden too, before the cut",
          "[hidden]" in text and TOKEN not in text and "Name" in text and left == 0, text)
    check("... and comes back exactly as it was when there is nothing to hide",
          SC.ui_words([{"text": "Name"}, {"text": "Pay now"}])[0] == "Name\nPay now")
    saved = SEC.redact_text

    def cannot_text(t):
        raise SEC.Unchecked("test")
    SEC.redact_text = cannot_text
    try:
        check("... and gives NOTHING when it cannot be checked", SC.ui_words([{"text": "Name"}]) == ("", 0))
    finally:
        SEC.redact_text = saved
    saved = SEC.redact_text
    SEC.redact_text = cannot_text
    try:
        lab_bad = SC.label_phone_text("Settings\nsome words")
        w = World(reader(lines_of("plain words"), size=(400, 120)))
        part = w.engine.look_at_this()["part"]
    finally:
        SEC.redact_text = saved
    check("the phone's screen text that cannot be checked says so - never 'could not read any words'",
          SC.SCREEN_TEXT_UNCHECKED in lab_bad and SC.SCREEN_TEXT_NONE not in lab_bad
          and "some words" not in lab_bad)
    check("the window's own text that cannot be checked marks the whole look unchecked",
          SC.SCREEN_TEXT_UNCHECKED in part and "plain words" not in part, part)
    lab = SC.label_phone_text("Settings\napi_key = 'kJ8dLq2Zx9Vw3RtY7uBnM4pAs6DfGh1C'")
    check("the phone's screen text has secrets hidden, and says how many", "kJ8dLq2Zx9" not in lab
          and "[hidden]" in lab and SC.SCREEN_TEXT_HEAD in lab and SC.SCREEN_TEXT_HIDDEN.format(n=1) in lab, lab)

    # the phone's screen PICTURE
    uri = "data:image/png;base64," + base64.b64encode(picture()[1]).decode("ascii")
    msgs = [{"role": "user", "content": [{"type": "text", "text": "what is on my phone?"},
                                          {"type": "image_url", "image_url": {"url": uri}}],
             "screen": "phone"}]
    out, info = SC.with_screen(msgs, "phone", read=reader(lines_of("hello", "my key " + TOKEN), size=(400, 120)))
    flat = repr(out)
    check("the phone's screen picture: its words come with the secret hidden, and no picture goes on",
          info["read"] and "[hidden]" in flat and TOKEN not in flat and "image_url" not in flat, flat[:300])
    out, info = SC.with_screen(msgs, "phone", read=lambda image: 1 / 0)
    check("... and a reader that fails gives 'could not read any words', never the picture",
          "image_url" not in repr(out))


def t_rules():
    snap = lambda **kw: dict({"exe": "chrome.exe", "title": "Some page - Google Chrome", "cls": "C",  # noqa: E731
                              "host": "example.com", "hwnd": 1, "password_focused": False,
                              "capture_protected": False}, **kw)
    never = SC.NeverLook(Path(tempfile.mkdtemp(prefix="jarvis-never-")) / "n.json")
    check("an ordinary browser window may be looked at", SC.pause_reason(snap(), never) is None)
    for t in ("New tab - [InPrivate] - Microsoft Edge", "Incognito - Google Chrome",
              "Mozilla Firefox Private Browsing", "GitHub \u2014 Private Browsing \u2014 Mozilla Firefox"):
        exe = "firefox.exe" if "Firefox" in t else ("msedge.exe" if "Edge" in t else "chrome.exe")
        check("a private window pauses: " + t[:40], SC.pause_reason(snap(exe=exe, title=t), never) == "private_window")
    check("a page that only talks about it does not pause a NON-browser",
          SC.pause_reason(snap(exe="winword.exe", title="Incognito mode - notes.docx", host=""), never) is None)
    check("the pause has plain words the apps show",
          SC.PAUSE_WORDS["private_window"] == "a private browser window" and "private" in SC.PAUSE_SAID["private_window"])
    check("the words are in both apps' shared table", all(
        "private_window" in (Path(SC.__file__).resolve().parent.parent / p).read_text(encoding="utf-8")
        for p in ("jarvis-desktop/tests/fixtures/screen-cases.json",
                  "jarvis-client/app/src/test/resources/contract/screen-cases.json")))
    for site in ("netflix.com", "primevideo.com", "disneyplus.com", "hulu.com", "tv.apple.com"):
        check("streaming video is on the built-in list: " + site, never.has_site(site))
    check("... and covers a subdomain, like every entry", never.has_site("www.netflix.com"))
    check("a private-window rule needs a browser: the list is unchanged for other things",
          SC.pause_reason(snap(host="netflix.com"), never) == "never_look")
    check("the words the model gets never name what was hidden",
          "{n}" in SC.SCREEN_TEXT_HIDDEN and "password" in SC.SCREEN_TEXT_HIDDEN)


def t_owner_tool():
    """tools/check_screen_safety.py, the owner's-PC check: its reporting part, with a stand-in reader."""
    sys.path.insert(0, str(HERE.parent / "tools"))
    import check_screen_safety as T
    _bgra, png, w, h = picture()
    out = _TMP / "cleaned.png"
    lines = []
    code = T.report(png, out, ocr=reader(lines_of("Meeting", "key " + TOKEN), size=(w, h)),
                    say=lines.append)
    said = "\n".join(lines)
    check("the owner's check reads, hides and writes a cleaned picture it names",
          code == 0 and out.is_file() and P.decode_png(out.read_bytes()) is not None and str(out) in said, said)
    check("... says how many it hid but never what", "1 hidden" in said and TOKEN not in said, said)
    out.unlink()
    lines = []
    code = T.report(png, out, ocr=lambda image: {"ok": False, "why": "no words"}, say=lines.append)
    check("... and says plainly when it could not, and writes nothing",
          code == 1 and not out.exists() and "NOT OK" in lines[-1])


def t_hygiene():
    src = (HERE / "jarvis_picture.py").read_text(encoding="utf-8")
    check("the picture code opens no socket, no file and starts nothing",
          not any(x in src for x in ("socket", "urllib", "requests", "subprocess", "open(", "write_bytes",
                                      "write_text", "tempfile")))
    ok = all(name in (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
             for name in ("jarvis_picture.py", "jarvis_secrets.py", "jarvis_secret_rules.py"))
    check("the three new modules are shipped by apply-patches.ps1", ok)
    check("clean_picture is the one door: _read and the phone's picture both use it",
          SC.Screen._read.__code__.co_names.count("clean_picture") == 1
          and "clean_picture" in SC.with_screen.__code__.co_names)


def main():
    for fn in (t_png, t_paint, t_clean, t_screen, t_rules, t_owner_tool, t_hygiene):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print("FAIL " + fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
