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

#: The only tools whose answers may be read aloud (owner, 2026-09-27). Exact
#: names, as the `step` event carries them (jarvis_agent._step_event).
READ_ALOUD_TOOLS = ("home_read", "web_search")


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
         "memory_aloud": True, "sensitive_aloud": False}
ROUTE = {"gate": "offer", "injected_facts": 0, "injected_sensitive": 0}


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

    def add(name, steps, heard=None, route=ROUTE, stream="live"):
        h = dict(PLAIN, **(heard or {}))
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
        ran("web_search"), heard={"memory_aloud": False})
    add("hands-free under 'Only trust the talk button' (PC sends every *_aloud false), home_read",
        ran("home_read"), heard={"memory_aloud": False, "private_aloud": False,
                                 "sensitive_aloud": False})
    return cases


def build() -> dict:
    names = tool_names()
    missing = [t for t in READ_ALOUD_TOOLS if t not in names]
    if missing:
        raise SystemExit(f"READ_ALOUD_TOOLS names a tool the PC does not have: {missing}")
    return {
        "_comment": ("Generated by tools/gen_private_aloud_cases.py. Do not edit by hand. "
                     "Owner, 2026-09-27: answers from web search, weather and home status "
                     "are read aloud; email, calendar, notes, memory and any unknown tool "
                     "stay on screen."),
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
