#!/usr/bin/env python3
"""Writes the "private answers stay on screen" table for both apps, and checks it.

    python3 tools/gen_private_aloud_cases.py            # write both copies
    python3 tools/gen_private_aloud_cases.py --check    # compare only

The owner's rule for an answer to a question asked BY VOICE
(docs/JARVIS-API.md section 16, "What the apps must do about private
answers"), and the owner's decision of 2026-09-27: "Read aloud answers from
web search, weather and home status. Email, calendar, notes, memory and any
unknown tool still stay on screen."

So a tool that ran while the answer was written keeps it on screen UNLESS
that tool is on READ_ALOUD_TOOLS below. Everything else - email, calendar,
notes and the note writers, documents and folders, memory, a tool the PC
calls "unknown", a step with no tool name, and any tool added later - keeps
it on screen, as does not knowing (the event stream was stale or dropped).
Every earlier step of the rule (sensitive saved facts, `private_aloud`,
`question_private`, the router's private gate, remembered facts with
memory kept on screen) keeps its place and its priority.

Weather has no tool of its own: "what's the weather?" is answered by the
quick path from the owner's own Home Assistant with no model and no tool
(jarvis_quick._run_weather), and when the model looks, it reads the weather
device with `home_read`. So the list is `web_search` and `home_read`.

And `read_screen` (the owner's answer of 2026-09-28 to docs/SCREEN-DESIGN.md:
"screen answers are read aloud unless a sensitive fact was used or the
strict hands-free setting says otherwise", a named exception to "a reading
tool keeps the answer on screen"). It is not a model tool - it is the name
a "Look at this" or "Watch with me" turn records as read
(jarvis_screen.SCREEN_TOOL), sent in the `step` event like a tool's name -
so the check below accepts it from jarvis_screen instead of jarvis_agent.TOOLS.
Every earlier rule still comes first: a sensitive fact, a private question
or the router's private gate keeps a screen answer on screen too.

And the strict hands-free setting's part (the owner's decision of
2026-09-28, "Under 'Only trust the talk button', screen answers stay on
screen"): the utterance reply's `screen_aloud` says whether an answer about
the screen may be read aloud for this clip (jarvis_voice.screen_aloud:
true for the talk button and under "same as the talk button"; under "only
trust the talk button", true for "hey Jarvis" only when the owner allowed
it with the voice setting `hands_free_screen: screen_aloud`). When the
screen was read and `screen_aloud` is not true - missing counts as not
true, as for every other `*_aloud` - the answer stays on screen. It is
asked right after the sensitive-fact step, before anything can say "read
aloud", so nothing else lets it through.

And `read_camera` (the owner's answer of 2026-09-28 to docs/LIVE-DESIGN.md:
"answers about what the camera sees are read aloud, like screen answers,
unless a sensitive fact was used or the strict setting says otherwise"). The
name a Jarvis Live question sent with a camera picture records
(jarvis_live.CAMERA_TOOL), and it is governed by exactly the same rule as
`read_screen`, `screen_aloud` included: both are "a look". The camera is
switched off until the second card passes the photo test, so nothing sends
it yet - the apps are ready for it.

This writes the SAME table into

    jarvis-desktop/tests/fixtures/private-aloud-cases.json
    jarvis-client/app/src/test/resources/contract/private-aloud-cases.json

(byte-identical). The desktop's tests/private-speech.mjs and the phone's
PrivateAloudContractTest run every case through their own code, and
backend/test_private_aloud.py checks the copies are current and that every
name here is a real tool in jarvis_agent.TOOLS.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "private-aloud-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "private-aloud-cases.json")
COPIES = (DESKTOP, PHONE)

#: What both apps say instead of a private answer.
ON_SCREEN = "It's on your screen."

#: The only tools whose answers may be read aloud (owner, 2026-09-27; and
#: read_screen, owner, 2026-09-28). Exact names, as the `step` event carries
#: them (jarvis_agent._step_event).
#:
#: `read_page` is jarvis_readpage.read_web_page (2026-10-05): the owner's own
#: request, "post a webpage into jarvis and it can read the content out
#: loud". It belongs beside web_search - both are the public web the owner
#: asked for, with the address shown on a card first - and not beside email,
#: calendar, notes or memory. Every earlier rule still comes first: a
#: sensitive saved fact, a private question, the router's private gate, a
#: forgotten event stream. The owner can have it taken back off this list by
#: saying so; it is one name here and the generated copies follow it.
READ_ALOUD_TOOLS = ("home_read", "read_camera", "read_screen", "web_search",
                    "read_web_page")

#: Names on READ_ALOUD_TOOLS that are recorded reads, not model tools, and
#: the module constant that defines each one (checked in build()).
RECORDED_READS = {"read_screen": ("jarvis_screen", "SCREEN_TOOL"),
                  "read_camera": ("jarvis_live", "CAMERA_TOOL")}


def tool_names() -> list:
    """Every real tool name, from the PC's own registry."""
    import jarvis_agent
    return list(jarvis_agent.TOOLS)


# --------------------------------------------------------------------------
#   The rule, once, in Python - the reference both apps are held to
# --------------------------------------------------------------------------

def is_tool_run(step) -> bool:
    return isinstance(step, dict) and step.get("phase") in ("tool_started", "tool_finished")


def is_private_tool_run(step) -> bool:
    """A tool ran, and it is not on READ_ALOUD_TOOLS - or it has no name."""
    if not is_tool_run(step):
        return False
    tool = step.get("tool")
    return not isinstance(tool, str) or tool not in READ_ALOUD_TOOLS


#: The recorded read that is an answer about the screen (jarvis_screen.SCREEN_TOOL).
SCREEN_READ = "read_screen"
#: The recorded read that is an answer about what the camera sees
#: (jarvis_live.CAMERA_TOOL) - the same rule as the screen.
CAMERA_READ = "read_camera"
#: Every "look": an answer about something Jarvis was shown.
LOOK_READS = (SCREEN_READ, CAMERA_READ)


def is_screen_read(step) -> bool:
    """The screen or the camera was read: a tool step named exactly
    `read_screen` or `read_camera`."""
    return is_tool_run(step) and step.get("tool") in LOOK_READS


def _count(route, key):
    v = route.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        return None
    return v


def may_read(heard: dict, route, steps: list, stream: str) -> bool:
    r = route if isinstance(route, dict) else {}
    facts = _count(r, "injected_facts") or 0
    sensitive = _count(r, "injected_sensitive")
    if sensitive is None:
        sensitive = facts
    if sensitive > 0 and not heard["sensitive_aloud"]:
        return False
    if any(is_screen_read(s) for s in steps) and heard.get("screen_aloud") is not True:
        return False
    if heard["private_aloud"]:
        return True
    if heard["question_private"]:
        return False
    if str(r.get("gate") or "").strip().lower() == "private":
        return False
    if facts > 0 and not heard["memory_aloud"]:
        return False
    if any(is_private_tool_run(s) for s in steps):
        return False
    if stream != "live":
        return False
    return True


# --------------------------------------------------------------------------
#   The cases
# --------------------------------------------------------------------------

#: How the event stream behaved between the question and the sentence:
#: "live" the whole time, "dropped" (went stale and came back),
#: "stale_at_start" (not live when the question was asked), "stale_now".
STREAMS = ("live", "dropped", "stale_at_start", "stale_now")

PLAIN = {"private_aloud": False, "question_private": False,
         "memory_aloud": True, "sensitive_aloud": False, "screen_aloud": True}
ROUTE = {"gate": "offer", "injected_facts": 0, "injected_sensitive": 0}
#: A "hey Jarvis" clip under "Only trust the talk button", with the screen
#: setting at its default: the PC sends every *_aloud false.
STRICT_WAKE = {"memory_aloud": False, "private_aloud": False,
               "sensitive_aloud": False, "screen_aloud": False}
#: The same, after the owner allowed screen answers aloud (the voice setting
#: `hands_free_screen: screen_aloud`, approved with a card).
STRICT_WAKE_SCREEN_ALLOWED = dict(STRICT_WAKE, screen_aloud=True)


def ran(tool) -> list:
    """The two `step` events a tool that ran sends. None: no name at all."""
    a = {"phase": "tool_started"}
    b = {"phase": "tool_finished", "ok": True}
    if tool is not None:
        a["tool"] = tool
        b["tool"] = tool
    return [a, b]


def build_cases() -> list:
    cases = []

    def add(name, steps, heard=None, route=ROUTE, stream="live", drop=()):
        h = dict(PLAIN, **(heard or {}))
        for key in drop:            # a field an older PC does not send
            h.pop(key, None)
        cases.append({"name": name, "heard": h, "route": route, "steps": steps,
                      "stream": stream, "read": may_read(h, route, steps, stream)})

    add("CONTROL: no tool, nothing private", [])
    add("CONTROL: no route header at all (an older PC)", [], route=None)

    # Every real tool, one at a time: only the read-aloud list is read aloud.
    for tool in tool_names():
        add(f"the tool {tool} ran", ran(tool))
    add("a tool the PC calls unknown ran", ran("unknown"))
    add("a tool step with no name ran", ran(None))
    add("a name that is not exact (Web_Search) counts as unknown", ran("Web_Search"))
    add("a name that is not text counts as unknown",
        [{"phase": "tool_started", "tool": 7}])
    add("only tool_finished was heard, for web_search", ran("web_search")[1:])
    add("only tool_started was heard, for email_check", ran("email_check")[:1])

    # Several tools: any private one keeps it on screen.
    add("web_search then home_read", ran("web_search") + ran("home_read"))
    add("web_search then email_check", ran("web_search") + ran("email_check"))
    add("calendar_read then web_search", ran("calendar_read") + ran("web_search"))
    add("web_search then memory_search", ran("web_search") + ran("memory_search"))
    add("home_read then an unknown tool", ran("home_read") + ran("unknown"))

    # A refused tool did not run; a model step is not a tool.
    add("email_check refused, then web_search ran",
        [{"phase": "tool_refused", "tool": "email_check"}] + ran("web_search"))
    add("only a refused email_check", [{"phase": "tool_refused", "tool": "email_check"}])
    add("model and answer steps only",
        [{"phase": "model", "round": 1}, {"phase": "answer", "round": 1}])

    # Not knowing: a safe tool, or none, with the stream not live the whole time.
    for stream in STREAMS[1:]:
        add(f"web_search ran, stream {stream}", ran("web_search"), stream=stream)
        add(f"no tool, stream {stream}", [], stream=stream)

    # Every earlier rule keeps its priority over a read-aloud tool.
    add("web_search, but the PC marked the question private",
        ran("web_search"), heard={"question_private": True})
    add("home_read, but the router's gate is private",
        ran("home_read"), route={"gate": "private", "injected_facts": 0, "injected_sensitive": 0})
    add("web_search with remembered facts, memory kept on screen",
        ran("web_search"), heard={"memory_aloud": False},
        route={"gate": "offer", "injected_facts": 2, "injected_sensitive": 0})
    add("web_search with remembered facts, memory read aloud",
        ran("web_search"), route={"gate": "offer", "injected_facts": 2, "injected_sensitive": 0})
    add("web_search with a sensitive saved fact",
        ran("web_search"), route={"gate": "offer", "injected_facts": 2, "injected_sensitive": 1})
    add("web_search with facts from a PC that does not count sensitive ones",
        ran("web_search"), route={"gate": "offer", "injected_facts": 1})
    add("web_search, a sensitive fact, the owner chose to hear those",
        ran("web_search"), heard={"sensitive_aloud": True},
        route={"gate": "offer", "injected_facts": 2, "injected_sensitive": 1})
    add("voice check is enough, a sensitive fact, not chosen to hear",
        ran("web_search"), heard={"private_aloud": True},
        route={"gate": "offer", "injected_facts": 2, "injected_sensitive": 1})
    add("voice check is enough reads an email answer (unchanged)",
        ran("email_check"), heard={"private_aloud": True})
    add("an older PC's reply (every *_aloud false), web_search",
        ran("web_search"), heard={"memory_aloud": False, "screen_aloud": False})
    add("hands-free under 'Only trust the talk button' (PC sends every *_aloud false), home_read",
        ran("home_read"), heard=STRICT_WAKE)

    # Looking at the screen (owner, 2026-09-28): read aloud like web search,
    # and every earlier rule keeps its priority over it.
    add("the screen was read (read_screen)", ran("read_screen"))
    add("the screen was read, then email_check", ran("read_screen") + ran("email_check"))
    add("web_search then the screen was read", ran("web_search") + ran("read_screen"))
    add("the screen was read, with a sensitive saved fact",
        ran("read_screen"), route={"gate": "screen", "injected_facts": 1, "injected_sensitive": 1})
    add("the screen was read, the router kept it here (gate screen), no facts",
        ran("read_screen"), route={"gate": "screen", "injected_facts": 0, "injected_sensitive": 0})
    add("the screen was read, but the PC marked the question private",
        ran("read_screen"), heard={"question_private": True})
    add("the screen was read, with remembered facts, memory kept on screen",
        ran("read_screen"), heard={"memory_aloud": False},
        route={"gate": "screen", "injected_facts": 2, "injected_sensitive": 0})
    add("the screen was read, stream dropped", ran("read_screen"), stream="dropped")
    add("a name that is not exact (Read_Screen) counts as unknown", ran("Read_Screen"))

    # Under "Only trust the talk button" (owner, 2026-09-28): a "hey Jarvis"
    # turn's answer about the screen stays on screen, unless the owner
    # allowed it (screen_aloud). Every earlier rule still comes first, and
    # the setting touches only the screen.
    add("hey Jarvis under 'Only trust the talk button': the screen was read, stays on screen",
        ran("read_screen"), heard=STRICT_WAKE)
    add("hey Jarvis under 'Only trust the talk button', screen answers allowed aloud: read aloud",
        ran("read_screen"), heard=STRICT_WAKE_SCREEN_ALLOWED)
    add("hey Jarvis, screen answers allowed aloud, but a sensitive saved fact",
        ran("read_screen"), heard=STRICT_WAKE_SCREEN_ALLOWED,
        route={"gate": "screen", "injected_facts": 1, "injected_sensitive": 1})
    add("hey Jarvis, screen answers allowed aloud, but the PC marked the question private",
        ran("read_screen"), heard=dict(STRICT_WAKE_SCREEN_ALLOWED, question_private=True))
    add("hey Jarvis, screen answers allowed aloud, then email_check",
        ran("read_screen") + ran("email_check"), heard=STRICT_WAKE_SCREEN_ALLOWED)
    add("hey Jarvis, screen answers allowed aloud, with remembered facts (memory kept here)",
        ran("read_screen"), heard=STRICT_WAKE_SCREEN_ALLOWED,
        route={"gate": "screen", "injected_facts": 2, "injected_sensitive": 0})
    add("hey Jarvis, screen answers allowed aloud, stream dropped",
        ran("read_screen"), heard=STRICT_WAKE_SCREEN_ALLOWED, stream="dropped")
    add("hey Jarvis under 'Only trust the talk button': web_search then the screen was read",
        ran("web_search") + ran("read_screen"), heard=STRICT_WAKE)
    add("hey Jarvis under 'Only trust the talk button': web_search only (the screen setting "
        "does not touch it)", ran("web_search"), heard=STRICT_WAKE)
    add("hey Jarvis under 'Only trust the talk button': only tool_finished was heard, for "
        "read_screen", ran("read_screen")[1:], heard=STRICT_WAKE)
    add("hey Jarvis under 'Only trust the talk button': a refused read_screen did not run",
        [{"phase": "tool_refused", "tool": "read_screen"}], heard=STRICT_WAKE)
    add("screen_aloud false comes before 'voice check is enough' (a reply no PC sends)",
        ran("read_screen"), heard={"private_aloud": True, "screen_aloud": False})
    add("an older PC's reply with no screen_aloud field: the screen was read, on screen",
        ran("read_screen"), drop=("screen_aloud",))
    add("an older PC's reply with no screen_aloud field: web_search is read aloud",
        ran("web_search"), drop=("screen_aloud",))

    # The camera in Jarvis Live (owner, 2026-09-28): read aloud like an
    # answer about the screen, under the same screen_aloud, with every
    # earlier rule first.
    add("the camera was read (read_camera)", ran("read_camera"))
    add("the camera was read, then email_check", ran("read_camera") + ran("email_check"))
    add("the camera was read, with a sensitive saved fact",
        ran("read_camera"), route={"gate": "offer", "injected_facts": 1, "injected_sensitive": 1})
    add("the camera was read, but the PC marked the question private",
        ran("read_camera"), heard={"question_private": True})
    add("the camera was read, stream dropped", ran("read_camera"), stream="dropped")
    add("a name that is not exact (Read_Camera) counts as unknown", ran("Read_Camera"))
    add("Live with the 'Hey Jarvis' caution under 'Only trust the talk button': the camera "
        "was read, stays on screen", ran("read_camera"), heard=STRICT_WAKE)
    add("Live with the 'Hey Jarvis' caution, screen answers allowed aloud: the camera is "
        "read aloud", ran("read_camera"), heard=STRICT_WAKE_SCREEN_ALLOWED)
    add("an older PC's reply with no screen_aloud field: the camera was read, on screen",
        ran("read_camera"), drop=("screen_aloud",))
    add("a refused read_camera did not run",
        [{"phase": "tool_refused", "tool": "read_camera"}], heard=STRICT_WAKE)
    return cases


def build() -> dict:
    names = tool_names()
    import importlib
    for name, (module, attr) in RECORDED_READS.items():
        if getattr(importlib.import_module(module), attr, None) == name:
            names.append(name)
    missing = [t for t in READ_ALOUD_TOOLS if t not in names]
    if missing:
        raise SystemExit(f"READ_ALOUD_TOOLS names a tool the PC does not have: {missing}")
    return {
        "_comment": ("Generated by tools/gen_private_aloud_cases.py. Do not edit by hand. "
                     "Owner, 2026-09-27: answers from web search, weather and home status "
                     "are read aloud; email, calendar, notes, memory and any unknown tool "
                     "stay on screen. Owner, 2026-09-28: answers about the screen "
                     "(read_screen) are read aloud too, with every earlier rule first - "
                     "and under 'Only trust the talk button' a 'Hey Jarvis' turn's screen "
                     "answer stays on screen unless the utterance reply says "
                     "screen_aloud: true (missing = false). Owner, 2026-09-28: answers "
                     "about what the camera sees in Jarvis Live (read_camera) follow "
                     "exactly the same rule as the screen."),
        "on_screen": ON_SCREEN,
        "read_aloud_tools": list(READ_ALOUD_TOOLS),
        "cases": build_cases(),
    }


def document() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    doc = document()
    if "--check" in sys.argv:
        bad = [p for p in COPIES
               if not p.exists() or p.read_text(encoding="utf-8") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_private_aloud_cases.py")
        if not bad:
            print("private-aloud-cases.json: both copies match")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
