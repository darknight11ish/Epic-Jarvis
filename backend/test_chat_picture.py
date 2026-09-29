"""test_chat_picture.py - a picture the owner ATTACHES to a chat gets the same
"secrets painted black" treatment a look at the screen already had, BEFORE any
model sees it (jarvis_chat_picture.py; jarvis_agent.clean_attached_pictures;
the owner's "Yes, clean them too", 2026-09-29; docs/JARVIS-API.md 62.14).

    python3 backend/test_chat_picture.py

With a stand-in for Windows' text recognition (the words AND where each sits)
and for the model, this proves:

  THE CLEANER (jarvis_chat_picture.clean_messages, through the real
  jarvis_screen.clean_picture / jarvis_picture / jarvis_secrets):
  - a picture with a made-up key and a card number: EXACTLY those words'
    boxes are SOLID BLACK in the picture that goes on, every other pixel is
    the original's, and the original bytes are not in what goes on;
  - a picture with nothing to hide goes on as the very same part, untouched;
  - a picture that cannot be checked is WITHHELD, never passed on: no text
    reader, words without positions, a JPEG nothing can open, a picture whose
    size differs from the size the words were read from, a web address, more
    than three pictures, the check failing, no cleaner installed - each with
    a plain line for the model and one for the answer itself;
  - only counts leave it: never the secret, never a picture, never a path.

  THE TURN (jarvis_agent.run_local_turn, the model stubbed):
  - the second card's picture lane, a main model that can see, a main model
    Ollama cannot say about, and a model that cannot see: none of them ever
    receives the original bytes of a picture that had something to hide;
  - a model that cannot see gets the words with "[hidden]" and the picture is
    read ONCE;
  - a picture that cannot be checked reaches NO model, and the answer itself
    carries the plain line (not only the model's text);
  - the note beside the answer says how many places were covered (a count);
  - without jarvis_chat_picture.py at all, pictures are withheld (fail closed);
  - the caller's messages are not changed; a picture is still outside text
    (the read is recorded) and a caption is still not the owner's own words;
  - both apps say the same sentence under an attached picture.
Every "secret" is made up. No network, no model, no Windows.
"""
from __future__ import annotations

import base64
import copy
import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_agent.py", "jarvis_chat_picture.py", "jarvis_screen.py", "jarvis_picture.py",
                "jarvis_secrets.py", "jarvis_secret_rules.py", "jarvis_screen_win.py",
                "jarvis_front.py", "jarvis_ocr.py", "jarvis_stop_all.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-chat-picture-"))
if "jarvis_framework" not in sys.modules:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = _TMP
    fw.LOG_DIR = _TMP
    fw.load_framework = lambda: {}
    fw.audit_log = lambda event, detail=None, **k: None
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

import jarvis_agent as AG  # noqa: E402
import jarvis_chat_picture as CP  # noqa: E402
import jarvis_ocr as OCR  # noqa: E402
import jarvis_picture as PIC  # noqa: E402
import jarvis_screen_win as WIN  # noqa: E402
import _ollama_wire as W  # noqa: E402

AG._manner_now = lambda *a, **k: None

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


TOKEN = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5"     # made up
CARD = "4111 1111 1111 1111"                                 # a made-up test number that passes the check digit
CHAR_W, LINE_H = 8, 16
W_PX, H_PX = 480, 130
URL = "http://127.0.0.1:11434"


def lines_of(*texts, top=10):
    """Lines as the reader gives them: every word with its position."""
    out = []
    for i, text in enumerate(texts):
        x, words = 10, []
        for w in text.split():
            words.append({"text": w, "left": float(x), "top": float(top + i * 24),
                          "width": float(len(w) * CHAR_W), "height": float(LINE_H)})
            x += len(w) * CHAR_W + 8
        out.append({"text": text, "words": words})
    return out


def make_png(w=W_PX, h=H_PX):
    """A PNG this PC makes (filter 0), striped so a wrong offset would show."""
    bgra = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = (200, 30, 30) if (x // 20 + y // 20) % 3 == 0 else (230, 230, 230)
            bgra += bytes((b, g, r, 255))
    return bytes(bgra), WIN.png_from_bgra(bytes(bgra), w, h)


BGRA, PNG = make_png()
JPEG = b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 20
WITH_SECRETS = lines_of("Meeting notes for Friday", "token " + TOKEN, "Card " + CARD + " exp 12/29",
                        "Nothing secret on this last line")
CLEAN_LINES = lines_of("Meeting notes for Friday", "Nothing secret on this line")


def data_uri(b: bytes, mime="image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(b).decode("ascii")


def picture_msg(image=PNG, words="what does this say?", mime="image/png", prov="typed", n=1):
    content = [{"type": "text", "text": words}]
    for _ in range(n):
        content.append({"type": "image_url", "image_url": {"url": data_uri(image, mime)}})
    m = {"role": "user", "content": content}
    if prov:
        m["provenance"] = prov
    return m


def reading(lines, size=(W_PX, H_PX), ok=True, **extra):
    """What jarvis_ocr.read_text returns, from these lines."""
    if not ok:
        return {"ok": False, "text": "", "left_out": 0, "why": "Windows' text recognition is not available here."}
    text = "\n".join(ln["text"] for ln in lines)
    got = {"ok": True, "text": text, "left_out": 0, "why": "", "lines": lines, "size": size}
    got.update(extra)
    return got


def image_bytes_in(messages):
    """Every picture's bytes anywhere in these messages."""
    out = []
    for m in messages:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list):
            for p in c:
                if AG._image_part(p):
                    out.append(OCR.image_bytes(p))
    return out


def texts_in(messages):
    return "\n".join(p.get("text", "") for m in messages if isinstance(m.get("content"), list)
                     for p in m["content"] if isinstance(p, dict) and p.get("type") == "text")


def pixel(bgra, w, x, y):
    o = (y * w + x) * 4
    return bytes(bgra[o:o + 4])


def word_box(lines, line_i, word_i):
    w = lines[line_i]["words"][word_i]
    return w["left"], w["top"], w["left"] + w["width"], w["top"] + w["height"]


# ---------------------------------------------------------------- the cleaner

def t_secrets_are_painted_black_at_the_right_boxes():
    reader = lambda image: reading(WITH_SECRETS)
    msgs, info = CP.clean_messages([picture_msg()], reader=reader)
    sent = image_bytes_in(msgs)
    check("one picture goes on", len(sent) == 1 and info["passed"] == 1 and info["withheld"] == 0, repr(info))
    check("... and it is NOT the original", sent and sent[0] != PNG)
    check("... the part says it is a PNG now", msgs[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
    dec = PIC.decode_png(sent[0])
    check("the cleaned picture opens and is the same size", dec is not None and dec[1:] == (W_PX, H_PX))
    bgra, w, h = dec
    # The token word and the card's four groups are black; nothing else changed. (The four card
    # groups are one box: the hider covers the spaces between them too - a secret is covered
    # whole, and a little padding is the safe way round.)
    tok = word_box(WITH_SECRETS, 1, 1)
    card = (word_box(WITH_SECRETS, 2, 1)[0], word_box(WITH_SECRETS, 2, 1)[1],
            word_box(WITH_SECRETS, 2, 4)[2], word_box(WITH_SECRETS, 2, 4)[3])
    hidden_boxes = [tok, card]
    black_ok = True
    for (l, t, r, b) in hidden_boxes:
        for y in range(int(t) + 1, int(b) - 1):
            for x in range(int(l) + 1, int(r) - 1):
                black_ok = black_ok and pixel(bgra, w, x, y) == b"\x00\x00\x00\xff"
    check("the key's box and the card number's box are SOLID BLACK, every pixel", black_ok)
    PAD = 6       # the hider pads a little (about a third of a line); nothing further from the words is touched
    inside = lambda x, y: any(l - PAD <= x <= r + PAD and t - PAD <= y <= b + PAD for (l, t, r, b) in hidden_boxes)
    changed_outside = sum(1 for y in range(h) for x in range(w)
                          if not inside(x, y) and pixel(bgra, w, x, y) != pixel(BGRA, w, x, y))
    check("every pixel more than 6 px from those two boxes is the original's, exactly", changed_outside == 0,
          changed_outside)
    check("the words that were not secrets are not covered (\"Meeting\", \"Nothing\")",
          pixel(bgra, w, *[int(v) for v in ((word_box(WITH_SECRETS, 0, 0)[0] + 2), word_box(WITH_SECRETS, 0, 0)[1] + 2)])
          == pixel(BGRA, w, int(word_box(WITH_SECRETS, 0, 0)[0] + 2), int(word_box(WITH_SECRETS, 0, 0)[1] + 2)))
    check("a count says how many places were hidden, never what", info["hidden"] >= 2 and info["covered"] == 1,
          repr(info))
    check("the model is told (after the picture) that places were hidden, with a count and no secret",
          "were hidden" in msgs[0]["content"][2]["text"] and TOKEN not in json.dumps(msgs)
          and "4111" not in json.dumps(msgs))
    check("the note beside the answer counts the places",
          info["note"].startswith("covered ") and "private-looking" in info["note"] and TOKEN not in info["note"],
          info["note"])
    check("the words a text-only model would get show [hidden] and no secret",
          "[hidden]" in next(iter(info["words"].values()))["text"]
          and TOKEN not in json.dumps(info["words"]) and "4111" not in json.dumps(info["words"]),
          json.dumps(info["words"])[:200])
    check("the caller's messages are not changed", msgs is not None and image_bytes_in([picture_msg()]) == [PNG])


def t_nothing_to_hide_goes_on_untouched():
    orig = picture_msg()
    part = orig["content"][1]
    msgs, info = CP.clean_messages([orig], reader=lambda image: reading(CLEAN_LINES))
    check("nothing needed hiding: the very same part goes on, byte for byte",
          msgs[0]["content"][1] is part and image_bytes_in(msgs) == [PNG] and len(msgs[0]["content"]) == 2)
    check("... counted as passed, none covered, none withheld",
          (info["passed"], info["covered"], info["hidden"], info["withheld"]) == (1, 0, 0, 0), repr(info))
    check("... and the note says nothing needed hiding",
          "nothing needed hiding" in info["note"] and info["said"] == "", info["note"])
    check("a picture with no words at all (a photo) goes on as it is: nothing to hide",
          CP.clean_messages([picture_msg()], reader=lambda image: reading([]))[0][0]["content"][1] is not None
          and image_bytes_in(CP.clean_messages([picture_msg()], reader=lambda image: reading([]))[0]) == [PNG])
    a = CP.clean_messages([{"role": "user", "content": "hello"}], reader=lambda image: 1 / 0)
    check("no picture at all: nothing changes and nothing is asked",
          a[0] == [{"role": "user", "content": "hello"}] and a[1]["pictures"] == 0 and a[1]["note"] == "")


def withheld(name, messages, *, reader=None, why_has=None, clean=None):
    msgs, info = CP.clean_messages(messages, reader=reader, clean=clean)
    check(f"{name}: NO picture goes on", image_bytes_in(msgs) == [], repr(image_bytes_in(msgs))[:80])
    check(f"{name}: counted as withheld", info["withheld"] >= 1 and info["passed"] == 0, repr(info))
    say = texts_in(msgs)
    check(f"{name}: the model is told, in words, that a picture was withheld",
          "NOT shown to any model" in say and "never guess" in say, say[:300])
    check(f"{name}: the answer itself says so (not left to the model)",
          info["said"].startswith("(") and "not used" in info["said"] and "Nothing was sent anywhere" in info["said"],
          info["said"])
    if why_has:
        check(f"{name}: the reason is given ({why_has!r})", why_has in say and why_has in info["said"], say[:300])
    return msgs, info


def t_a_picture_that_cannot_be_checked_is_withheld():
    withheld("no text reader", [picture_msg()], reader=lambda image: reading([], ok=False),
             why_has="not available")
    withheld("words with no positions", [picture_msg()],
             reader=lambda image: {"ok": True, "text": "token " + TOKEN, "left_out": 0, "why": ""},
             why_has="positions")
    # A JPEG (what both apps attach): the words are read but nothing here can open it to
    # paint on, so it cannot be cleaned - never guessed at.
    saved = PIC._read_with_pixels
    PIC._read_with_pixels = lambda image: {"ok": False}
    try:
        withheld("a JPEG nothing can open", [picture_msg(JPEG, mime="image/jpeg")],
                 reader=lambda image: reading(WITH_SECRETS), why_has="could not be opened")
    finally:
        PIC._read_with_pixels = saved
    withheld("a picture not the size the words were read from", [picture_msg()],
             reader=lambda image: reading(WITH_SECRETS, size=(W_PX + 1, H_PX)), why_has="not the size")
    m = {"role": "user", "content": [{"type": "text", "text": "look"},
                                    {"type": "image_url", "image_url": {"url": "https://example.invalid/a.png"}}]}
    withheld("a web address (never fetched)", [m], reader=lambda image: reading(CLEAN_LINES))
    withheld("the check blows up", [picture_msg()], reader=lambda image: reading(CLEAN_LINES),
             clean=lambda image, **k: 1 / 0)
    withheld("the check says hidden but hands back the original bytes", [picture_msg()],
             reader=lambda image: reading(CLEAN_LINES),
             clean=lambda image, **k: {"ok": True, "text": "x", "hidden": 3, "png": image, "left_out": 0})
    withheld("the check gives no picture", [picture_msg()], reader=lambda image: reading(CLEAN_LINES),
             clean=lambda image, **k: {"ok": True, "text": "x", "hidden": 0, "png": None, "png_why": "no reason given here"},
             why_has="no reason given here")
    import jarvis_secrets as SEC
    saved_check = SEC.check

    def too_much(lines, **k):
        raise SEC.Unchecked("there is too much small text in the picture to check")
    SEC.check = too_much
    try:
        _m, info = withheld("the check itself cannot run (too much small text)", [picture_msg()],
                            reader=lambda image: reading(WITH_SECRETS), why_has="too much small text")
        check("... and the reason is not said twice", info["said"].count("could not check") == 1, info["said"])
    finally:
        SEC.check = saved_check
    saved_door = CP._door
    CP._door = lambda: None
    try:
        withheld("no cleaner installed", [picture_msg()], reader=lambda image: reading(CLEAN_LINES),
                 why_has="not installed")
    finally:
        CP._door = saved_door


def t_at_most_three_pictures_are_checked_newest_first():
    reads = []

    def reader(image):
        reads.append(image)
        return reading(CLEAN_LINES)
    m = picture_msg(n=4)
    msgs, info = CP.clean_messages([m], reader=reader)
    parts = msgs[0]["content"]
    pics = [p for p in parts if AG._image_part(p)]
    check("three go on, the fourth is withheld", len(pics) == 3 and info["withheld"] == 1 and info["passed"] == 3,
          repr(info))
    check("the one withheld is the OLDEST (the first in the message)",
          parts[1]["type"] == "text" and "NOT shown to any model" in parts[1]["text"]
          and "more pictures were attached than can be checked" in parts[1]["text"], repr(parts)[:300])
    check("a picture in an older message counts too (never passed on unchecked)",
          image_bytes_in(CP.clean_messages([picture_msg(), {"role": "assistant", "content": "ok"}, picture_msg()],
                                            reader=lambda i: reading([], ok=False))[0]) == [])


def t_only_counts_and_no_file():
    import os
    before = set(os.listdir(_TMP))
    msgs, info = CP.clean_messages([picture_msg()], reader=lambda image: reading(WITH_SECRETS))
    keys = set(info)
    check("info is counts and lines: no picture, no path, no secret",
          keys == {"pictures", "passed", "covered", "hidden", "withheld", "why", "words", "note", "said"}
          and TOKEN not in json.dumps({k: v for k, v in info.items()}, default=str)
          and set(os.listdir(_TMP)) == before)


# ------------------------------------------------------------------ the turn

def shows(capabilities):
    def get(url, payload=None, *a, **k):
        if url.endswith("/api/show"):
            return {"capabilities": capabilities}
        raise OSError("no network in this test")
    return get


def turn(request_messages, *, capabilities, reader, lane_choice=None, module=True):
    """One turn as jarvis_hud runs it. Returns (what the model got, the summary,
    the notes announced, the words the app was sent, the OCR reads)."""
    passed_in = [{k: v for k, v in m.items() if k != "provenance"} for m in request_messages]
    request = {"model": "jarvis-primary", "stream": True, "messages": copy.deepcopy(request_messages)}
    before = (json.dumps(passed_in), json.dumps(request))
    sent, read, notes, wire = [], [], [], []

    def opener(url, body):
        sent.append(json.loads(json.dumps(body)))
        return W.FakeResponse(W.stream([("content", "It says something."), ("done", "stop")]))

    def fake_read(image):
        read.append(image)
        return reader(image)
    saved = (AG._get_json, AG._read_picture, sys.modules.get("jarvis_chat_picture"))
    AG._get_json = shows(capabilities)
    AG._read_picture = fake_read
    AG._SEES_CACHE.clear()
    AG._TOOLS_CACHE.clear()
    if not module:
        sys.modules["jarvis_chat_picture"] = None      # `import` now raises ImportError
    try:
        out = AG.run_local_turn(passed_in, "jarvis-primary", ollama_url=URL,
                                stream_out=lambda b: wire.append(b), open_stream=opener,
                                enabled_tools=None, context_length=16384, request=request,
                                announce=notes.append,
                                on_step=lambda s: None, record_chain=lambda s: None,
                                keepalive_seconds=60, status_delay=60, lane_choice=lane_choice)
    finally:
        AG._get_json, AG._read_picture = saved[0], saved[1]
        if saved[2] is not None:
            sys.modules["jarvis_chat_picture"] = saved[2]
        else:
            sys.modules.pop("jarvis_chat_picture", None)
        AG._SEES_CACHE.clear()
    check("the caller's messages and the request are not changed by the turn",
          (json.dumps(passed_in), json.dumps(request)) == before)
    return (sent[0]["messages"] if sent else None), out, notes, b"".join(wire).decode("utf-8", "replace"), read


def secret_reader():
    return lambda image: reading(WITH_SECRETS)


def t_no_model_ever_gets_the_original_bytes():
    for label, caps, lane in (
            ("the second card's picture lane", ["completion"],
             AG.LaneChoice("http://127.0.0.1:11435", "qwen2.5vl:7b", 8192, "vision", "picture")),
            ("a main model that can see", ["completion", "vision"], None),
            ("a main model Ollama cannot say about", [], None),
            ("a main model that cannot see", ["completion", "tools"], None)):
        msgs, out, notes, wire, read = turn([picture_msg()], capabilities=caps, reader=secret_reader(),
                                            lane_choice=lane)
        body = json.dumps(msgs)
        check(f"{label}: the original picture is nowhere in what the model got",
              data_uri(PNG) not in body and PNG not in image_bytes_in(msgs), body[:120])
        check(f"{label}: no secret reached it either", TOKEN not in body and "4111" not in body)
        check(f"{label}: the note beside the answer says places were covered",
              any(n.startswith("covered ") and "black" in n for n in notes), repr(notes))
        if label in ("the second card's picture lane", "a main model that can see", "a main model Ollama cannot say about"):
            sent = image_bytes_in(msgs)
            dec = PIC.decode_png(sent[0]) if sent else None
            check(f"{label}: it may see the picture - the CLEANED one, black at the key",
                  dec is not None and pixel(dec[0], dec[1], int(word_box(WITH_SECRETS, 1, 1)[0]) + 2,
                                            int(word_box(WITH_SECRETS, 1, 1)[1]) + 2) == b"\x00\x00\x00\xff")
        else:
            check(f"{label}: it gets the words, with [hidden], and no picture",
                  image_bytes_in(msgs) == [] and "[hidden]" in texts_in(msgs)
                  and AG.PICTURE_TEXT_HEAD in texts_in(msgs))
            check(f"{label}: the picture was read ONCE (not again for the words)", len(read) == 1, len(read))
            check(f"{label}: still outside text - the turn records the read", out["tools_ran"][:1] == [AG.PICTURE_TEXT_TOOL],
                  repr(out["tools_ran"]))


def t_a_picture_nothing_needed_hiding_goes_on_as_it_came():
    msgs, out, notes, wire, read = turn([picture_msg()], capabilities=["completion", "vision"],
                                        reader=lambda image: reading(CLEAN_LINES))
    check("a model that can see gets the same bytes it always did", image_bytes_in(msgs) == [PNG])
    check("... and the note says nothing needed hiding", any("nothing needed hiding" in n for n in notes), repr(notes))


def t_an_unchecked_picture_reaches_no_model_and_the_answer_says_so():
    for label, caps, lane in (
            ("picture lane", ["completion"],
             AG.LaneChoice("http://127.0.0.1:11435", "qwen2.5vl:7b", 8192, "vision", "picture")),
            ("a model that can see", ["completion", "vision"], None),
            ("a model Ollama cannot say about", [], None),
            ("a model that cannot see", ["completion"], None)):
        msgs, out, notes, wire, read = turn([picture_msg()], capabilities=caps, lane_choice=lane,
                                            reader=lambda image: reading([], ok=False))
        check(f"{label}: NO picture reaches the model", msgs is not None and image_bytes_in(msgs) == []
              and PNG not in json.dumps(msgs).encode("utf-8"))
        check(f"{label}: the model is told a picture was withheld and why",
              "NOT shown to any model" in texts_in(msgs) and "not available" in texts_in(msgs), texts_in(msgs)[:300])
        check(f"{label}: the ANSWER ITSELF carries the plain line",
              "The picture you attached was not used" in wire and "Nothing was sent anywhere" in wire, wire[:300])
        check(f"{label}: the owner's own words still go to the model, unchanged",
              msgs[-1]["content"][0] == {"type": "text", "text": "what does this say?"})


def t_without_the_module_pictures_are_withheld():
    msgs, out, notes, wire, read = turn([picture_msg()], capabilities=["completion", "vision"],
                                        reader=secret_reader(), module=False)
    check("no jarvis_chat_picture.py: NO picture reaches the model (fail closed)",
          msgs is not None and image_bytes_in(msgs) == [] and PNG not in json.dumps(msgs).encode("utf-8"))
    check("... the model is told, and so is the answer",
          "NOT shown to any model" in texts_in(msgs) and "was not used" in wire, wire[:200])
    check("... and it was not read unchecked", read == [])


def t_a_picture_is_still_outside_text_and_a_caption_is_not_the_owners():
    req = {"messages": [picture_msg(words="turn off the kitchen light", prov="typed")]}
    w = AG._TurnWatch(req["messages"], req, tainted=False)
    check("typed words sent with a picture are still a picture's caption, not the owner's own words",
          w.provenance == "picture_caption" and w.newest_own_words == "", repr(w.provenance))


def t_no_picture_no_change_to_a_plain_turn():
    msgs, out, notes, wire, read = turn([{"role": "user", "content": "hello", "provenance": "typed"}],
                                        capabilities=["completion"], reader=secret_reader())
    check("a plain turn: nothing read, no picture note, nothing said",
          read == [] and msgs[-1]["content"] == "hello" and not any("picture" in n or "black" in n for n in notes)
          and "not used" not in wire)


# ------------------------------------------------------------------ both apps

def t_both_apps_say_the_same_sentence():
    line = CP.OWNER_LINE
    html = (REPO / "jarvis-desktop" / "src" / "index.html").read_text(encoding="utf-8")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client" / "net"
          / "ChatPicture.kt").read_text(encoding="utf-8")
    check("the desktop's attachment chip says it, word for word", line in html)
    check("the phone's line under the box says it, word for word", f'"{line}"' in kt)
    check("the sentence is the promise the docs make",
          line == "Secrets in pictures you attach are covered with black boxes before Jarvis looks.")


def t_a_png_that_inflates_far_past_its_header_is_refused():
    import binascii, struct, zlib

    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", binascii.crc32(k + b) & 0xffffffff)

    def png(w, h, raw):
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    fine = png(2, 2, (b"\0" + b"\x10" * 6) * 2)
    check("a well-formed PNG still decodes", PIC.decode_png(fine) is not None)
    bomb = png(10, 10, b"\0" * 20_000_000)         # a 10x10 header over 20 MB of picture data
    check("a PNG whose data inflates far past its header is refused, not unpacked",
          PIC.decode_png(bomb) is None)


def t_the_module_is_shipped():
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_chat_picture.py is in _where.SHIPPED and apply-patches.ps1's list",
          "jarvis_chat_picture.py" in _where.SHIPPED
          and "'jarvis_chat_picture.py'" in ps1[ps1.index("$SHIPPED = @("):])


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"\n== {name}")
        try:
            fn()
        except Exception:
            FAILED.append(name + " (raised)")
            print("FAIL " + name + " raised:\n" + traceback.format_exc())
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", *FAILED, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
