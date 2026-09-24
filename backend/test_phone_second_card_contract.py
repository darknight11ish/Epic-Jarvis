"""The phone's side of the second graphics card, checked against the
backend's own functions and written down for the phone's JVM tests: the
picture turn, the route line, and what a switch's POST really answers.

(GET /api/second-card's own answers are shared with the desktop in
second-card-cases.json, written by tools/gen_second_card_cases.py.)

WHAT THIS IS

The phone sends a photo in chat only while the second graphics card's
Pictures feature is working. It must send EXACTLY the request the desktop
sends - the desktop's shape is the one known to work against the real server:

    jarvis-desktop/src/main.js, `send`: the picture rides INSIDE the newest
      user message, `content: [{type: "text", text}, {type: "image_url",
      image_url: {url: <data URI>}}]`, with `hasImage` beside `messages`;
    jarvis-desktop/src-tauri/src/commands.rs, `stream_chat`: the body is
      {"messages", "has_image", "stream": true, "auto"}; captures are JPEG
      (`data:image/jpeg;base64,`), at most MAX_CAPTURE_WIDTH wide, quality
      JPEG_QUALITY.

This file builds that request the desktop's way and runs it through what the
PC does with it:

    jarvis_agent.newest_turn_has_image   - does the PC see the picture?
    jarvis_agent.choose_lane             - does it go to the Pictures lane?
    jarvis_router.choose(has_image=...)  - is it kept on this PC? (rule 1)

and checks the largest picture the phone will send, with the most
conversation it will send beside it, fits under the PC's MAX_BODY (read from
the patch that shows jarvis_hud.py's line, since jarvis_hud.py itself is not
in this repository).

Then it writes every case, body and all, to

    jarvis-client/app/src/test/resources/contract/phone-second-card-cases.json

where ChatPictureContractTest.kt builds each request with the phone's own
encoder (ChatHistory.requestBody + ChatPicture) and checks it is the same
JSON, and reads each X-Jarvis-Route header with SecondCard.routeFromHeader;
SecondCardContractTest.kt reads the POST answers (`post_replies`) - each one
jarvis_second_card.request_change itself, run in the same stand-in world the
status() fixture uses - with SecondCard.classifyPost and replyLine.
The route headers are made the way second-card.patch makes them: the real
router's decision, `lane`/`where` as chat-stream.patch sets them, then
`lane` = the second card's model and `second_card` = the feature.

WHAT IT CANNOT CHECK. jarvis_hud.py's chat route (which reads the body and
calls the two functions above) lives only on the owner's PC; test_second_card.py
checks the patch text that wires them. The phone's picture shrinking runs on
Android (ImageDecoder, Bitmap.compress) and is not run here or in a JVM test.

    python3 test_phone_second_card_contract.py            check
    python3 test_phone_second_card_contract.py --write    regenerate the fixture
"""
import base64
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_second_card.py")
for p in (HERE / "rebuilt", REPO / "tools"):
    if str(p) not in sys.path:
        sys.path.append(str(p))
# An empty settings folder, always: the fixture must not depend on whose
# jarvis-framework.toml the router happens to read.
os.environ["OPENJARVIS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="jarvis-phone-card-")
os.environ.pop("JARVIS_CONFIG_DIR", None)

import jarvis_agent as AG  # noqa: E402
import jarvis_router as RT  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import gen_second_card_cases as G  # noqa: E402

FIXTURE = (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
           / "phone-second-card-cases.json")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# A real 8 x 6 JPEG, made once with Pillow at quality 82. The PC never
# decodes the picture itself - it forwards it to the model - so any real
# JPEG will do; a real one keeps the fixture honest.
JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBAUEBAYFBQUGBgYHCQ4JCQgICRINDQoOFRIWFhUSFBQXGiEcFxgf"
    "GRQUHScdHyIjJSUlFhwpLCgkKyEkJST/2wBDAQYGBgkICREJCREkGBQYJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk"
    "JCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCT/wAARCAAGAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAA"
    "AAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
    "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKT"
    "lJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QA"
    "HwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDGt7241KG61qKTydW06ITXMxAZbyJnWIl1OQXJlAbIKyKWLfMG"
    "MhRRX2cYRbaa2/yPmnJpKzP/2Q=="
)

VISION_LANE = SC.Lane("http://127.0.0.1:11435", SC.VISION_MODEL, 16384, "test")
LONG_LANE = SC.Lane("http://127.0.0.1:11435", "qwen3:14b", 16384, "test")

#: The phone's own numbers (net/ChatPicture.kt). The Kotlin test checks the
#: phone still uses these; this file checks they fit what the PC accepts.
PHONE_MAX_JPEG_BYTES = 1_500_000
#: ChatHistory.kt's MAX_CHARS - the most earlier conversation the phone sends.
PHONE_MAX_HISTORY_CHARS = 18_000


# ---------------------------------------------------------------- limits --

def backend_max_body() -> int:
    """jarvis_hud.py's MAX_BODY, from the patch that shows the line."""
    text = (HERE / "token-store.patch").read_text(encoding="utf-8")
    m = re.search(r"^ MAX_BODY = (\d+) \* (\d+) \* (\d+)", text, re.M)
    assert m, "MAX_BODY line not found in token-store.patch"
    return int(m.group(1)) * int(m.group(2)) * int(m.group(3))


def desktop_limits() -> dict:
    """The desktop's picture numbers, from commands.rs itself."""
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
    width = re.search(r"const MAX_CAPTURE_WIDTH: u32 = (\d+);", rs)
    quality = re.search(r"const JPEG_QUALITY: u8 = (\d+);", rs)
    assert width and quality, "picture constants not found in commands.rs"
    return {"max_long_edge": int(width.group(1)), "jpeg_quality": int(quality.group(1))}


# ---------------------------------------------------------------- bodies --

def desktop_body(history, question, jpeg_b64):
    """The request exactly as the desktop builds it (main.js `send` +
    commands.rs `stream_chat`). `history` is [(question, answer), ...]."""
    messages = []
    for q, a in history:
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": a})
    if jpeg_b64 is None:
        content = question
    else:
        content = [{"type": "text", "text": question},
                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + jpeg_b64}}]
    messages.append({"role": "user", "content": content})
    return {"messages": messages, "has_image": jpeg_b64 is not None, "stream": True, "auto": True}


CASES = [
    ("a picture with the first question", [], "What is in this picture?", JPEG_B64),
    ("a picture after two earlier questions",
     [("When is the dentist?", "Tuesday at 10."), ("And the vet?", "Friday \"after work\".")],
     "Is this the right form? ✓", JPEG_B64),
    ("words only, no picture", [("hi", "Hello.")], "and now?", None),
]


def what_the_pc_does(body):
    msgs = body["messages"]
    seen = AG.newest_turn_has_image(msgs)
    lane = AG.choose_lane(msgs, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
                          lane_for=lambda f: VISION_LANE if f == "vision" else None)
    newest = msgs[-1]["content"]
    text = newest if isinstance(newest, str) else newest[0]["text"]
    d = RT.choose(text, local_model="jarvis-primary", lanes=["jarvis-escalate"],
                  has_image=body["has_image"], budget=RT.Budget(path=None))
    return seen, lane, d


def build_requests():
    out = []
    for name, history, question, jpeg in CASES:
        body = desktop_body(history, question, jpeg)
        seen, lane, d = what_the_pc_does(body)
        out.append({
            "name": name,
            "history": [{"question": q, "answer": a} for q, a in history],
            "question": question,
            "jpeg_b64": jpeg,
            "body": body,
            "expect": {"pc_sees_picture": seen,
                       "lane": lane.feature if lane else None,
                       "stays_local": d.gate != "escalate",
                       "router_gate": d.gate},
        })
    return out


# ----------------------------------------------------------------- route --

def build_route_headers():
    """X-Jarvis-Route as second-card.patch sends it on a second-card turn:
    the router's decision, chat-stream.patch's lane/where, then `lane` set
    to the model the second card ran and `second_card` to the feature -
    for a real jarvis_agent.choose_lane answer, not a typed one."""
    out = []
    pic = desktop_body([], "what is this?", JPEG_B64)
    long_msgs = [{"role": "user", "content": "x " * 40000}]
    for name, msgs, has_image, lane_for, ctx in (
        ("a picture, on the second card", pic["messages"], True,
         lambda f: VISION_LANE if f == "vision" else None, None),
        ("a long conversation, on the second card", long_msgs, False,
         lambda f: LONG_LANE if f == "long_context" else None, 4096),
        ("an everyday answer, main card", [{"role": "user", "content": "hi"}], False,
         lambda f: None, None),
    ):
        # The patch only asks choose_lane on the LOCAL branch, so the router's
        # decision here must be a local one: a short question for it to read.
        h = RT.choose("what is this?" if has_image else "and what did we say?",
                      local_model="jarvis-primary", lanes=["jarvis-escalate"],
                      has_image=has_image, budget=RT.Budget(path=None)).as_dict()
        assert h["gate"] != "escalate", h
        h.update({"lane": "jarvis-primary", "where": "local"})
        choice = AG.choose_lane(msgs, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
                                lane_for=lane_for, context_length=ctx)
        if choice is not None:
            h["lane"] = choice.model
            h["second_card"] = choice.feature
        out.append({"name": name, "header": json.dumps(h),
                    "expect": {"second_card": choice.feature if choice else None,
                               "model": choice.model if choice else None,
                               "where": "local"}})
    return out


# ------------------------------------------------------------------ post --

def build_post_replies():
    """What POST /api/second-card answers, (status code, body), from the real
    request_change - in the stand-in world tools/gen_second_card_cases.py
    uses for the status() fixture (nvidia-smi's format, made-up values)."""
    out = []

    def case(name, world, feature, enabled, **switches):
        with world as w:
            w.switches(**switches)
            # `spawn` does nothing: a card is raised and waits, as on the PC
            # until the owner answers it.
            code, body = SC.request_change(feature, enabled, spawn=lambda fn: None)
            if name == "a card is already waiting":
                code, body = SC.request_change(feature, enabled, spawn=lambda fn: None)
        out.append({"name": name, "feature": feature, "enabled": enabled,
                    "status": code, "body": body})

    capable = lambda: G.World(G.SMI["2080s_2060"], windows=True, user_env=G.U_2080S)
    case("turning on raises a card", capable(), "long_context", True, master=True)
    case("a card is already waiting", capable(), "long_context", True, master=True)
    case("turning off is immediate", capable(), "vision", False, master=True, vision=True)
    case("already on", capable(), "long_context", True, master=True, long_context=True)
    case("the main switch is off", capable(), "vision", True, master=False)
    case("a needed switch is off", capable(), "browser_control", True, master=True)
    case("no capable second card", G.World(G.SMI["one_card"]), "master", True)
    case("an unknown switch", capable(), "telepathy", True, master=True)
    return out


def document() -> str:
    return json.dumps({
        "_about": ("Made by backend/test_phone_second_card_contract.py --write: the desktop's "
                   "picture request, as the PC's own functions read it, and the second "
                   "card's X-Jarvis-Route and what a switch's POST answers. Do not edit by hand."),
        "limits": {"backend_max_body": backend_max_body(),
                   "max_jpeg_bytes": PHONE_MAX_JPEG_BYTES,
                   **desktop_limits()},
        "requests": build_requests(),
        "route_headers": build_route_headers(),
        "post_replies": build_post_replies(),
    }, indent=2, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------- tests --

def t_the_pc_reads_a_picture_turn_the_way_the_phone_needs():
    for r in build_requests():
        e = r["expect"]
        if r["jpeg_b64"]:
            check(f"{r['name']}: the PC sees the picture", e["pc_sees_picture"])
            check(f"{r['name']}: it goes to the Pictures lane", e["lane"] == "vision", e)
            check(f"{r['name']}: the router keeps it on this PC", e["stays_local"]
                  and e["router_gate"] == "image", e)
            check(f"{r['name']}: has_image is true", r["body"]["has_image"] is True)
        else:
            check(f"{r['name']}: no picture seen, no Pictures lane",
                  not e["pc_sees_picture"] and e["lane"] is None, e)
            check(f"{r['name']}: has_image is false", r["body"]["has_image"] is False)


def t_earlier_turns_never_carry_a_picture():
    for r in build_requests():
        earlier = r["body"]["messages"][:-1]
        check(f"{r['name']}: earlier turns are words only",
              all(isinstance(m["content"], str) for m in earlier))


def t_the_biggest_picture_fits_what_the_pc_accepts():
    limit = backend_max_body()
    check("MAX_BODY is 4 MiB, as jarvis_voice_enroll.py also assumes", limit == 4 * 1024 * 1024, limit)
    jpeg = base64.b64encode(b"\xff" * PHONE_MAX_JPEG_BYTES).decode()
    # The most conversation the phone sends, in three-byte characters, and a
    # long question: well past anything typed on a phone.
    per = PHONE_MAX_HISTORY_CHARS // 20
    history = [("€" * per, "€" * per) for _ in range(10)]
    body = desktop_body(history, "€" * 20000, jpeg)
    size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    check(f"the largest picture request ({size:,} bytes) is under MAX_BODY ({limit:,})",
          size < limit, size)


def t_the_second_card_route_header():
    rows = build_route_headers()
    by = {r["name"]: r for r in rows}
    check("a picture turn says second_card: vision, lane = the picture model",
          by["a picture, on the second card"]["expect"] == {
              "second_card": "vision", "model": SC.VISION_MODEL, "where": "local"})
    check("a long conversation says second_card: long_context",
          by["a long conversation, on the second card"]["expect"]["second_card"] == "long_context")
    check("an everyday answer has no second_card at all",
          "second_card" not in json.loads(by["an everyday answer, main card"]["header"]))
    for r in rows:
        check(f"{r['name']}: where stays local", json.loads(r["header"])["where"] == "local")


def t_the_post_answers_are_the_documented_ones():
    by = {r["name"]: r for r in build_post_replies()}
    r = by["turning on raises a card"]
    check("ON: 200, pending, not enabled", r["status"] == 200 and r["body"]["pending"] is True
          and r["body"]["enabled"] is False, r)
    check("a second ON while its card waits: 409 with a sentence",
          by["a card is already waiting"]["status"] == 409
          and "already waiting" in by["a card is already waiting"]["body"]["error"])
    r = by["turning off is immediate"]
    check("OFF: 200, off, no card", r["status"] == 200 and r["body"]["enabled"] is False
          and r["body"]["pending"] is False, r)
    check("the main switch off: 400 with a sentence",
          by["the main switch is off"]["status"] == 400 and by["the main switch is off"]["body"]["error"])
    check("a needed switch off: 400 naming it",
          by["a needed switch is off"]["status"] == 400
          and "Longer conversations" in by["a needed switch is off"]["body"]["error"])
    check("no capable card: 503 with the reason",
          by["no capable second card"]["status"] == 503
          and "only one graphics card" in by["no capable second card"]["body"]["error"])
    check("an unknown switch: 400", by["an unknown switch"]["status"] == 400)


def t_the_fixture_is_what_this_makes_today():
    doc = document()
    if "--write" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {FIXTURE.relative_to(REPO)}")
    have = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
    check(f"{FIXTURE.relative_to(REPO)} matches (run with --write after changing a case)",
          have.replace("\r\n", "\n") == doc, "stale or missing")


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
    sys.exit(1 if FAILED else 0)
