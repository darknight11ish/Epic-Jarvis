"""Which tools' answers may be read aloud to a voice question - one table
for both apps.

    python3 test_private_aloud.py

The owner's decision of 2026-09-27: "Read aloud answers from web search,
weather and home status. Email, calendar, notes, memory and any unknown tool
still stay on screen." The rule lives in the two apps
(jarvis-client voice/PrivateAloud.kt, jarvis-desktop src/private-speech.js);
tools/gen_private_aloud_cases.py writes the table both are held to. This
checks:

  1. every name on the read-aloud list is a real tool, and is one that only
     READS - web search and home status - never email, calendar, notes,
     files, memory or a tool that changes anything;
  2. the `step` event carries exactly those names (jarvis_agent._step_event),
     and turns a name the PC does not know into "unknown", which stays on
     screen;
  3. both copies of the table are what the generator makes today;
  4. the table's own answers: every tool not on the list stays on screen,
     and not knowing (a stale or dropped event stream) stays on screen;
  5. under "Only trust the talk button" (owner, 2026-09-28), a screen answer
     whose utterance reply does not say `screen_aloud: true` stays on
     screen - and a missing field counts as false.

Runs anywhere: standard library only, no owner's files.
"""
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import gen_private_aloud_cases as G  # noqa: E402
import jarvis_agent  # noqa: E402

FAILED, PASSED = [], []


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    print(("ok    " if ok else "FAIL  ") + name + ("" if ok else f"  ({detail})"))


def t_the_list_is_real_and_only_reads():
    check("the list is web_search, home_read, read_screen and read_camera, nothing else",
          sorted(G.READ_ALOUD_TOOLS) == ["home_read", "read_camera", "read_screen",
                                         "web_search"],
          G.READ_ALOUD_TOOLS)
    for name in G.READ_ALOUD_TOOLS:
        if name in G.RECORDED_READS:
            continue
        check(f"{name} is a real tool", name in jarvis_agent.TOOLS)
    # read_screen is not a model tool: it is the read a screen turn records
    # (the owner's answer of 2026-09-28, docs/SCREEN-DESIGN.md).
    import jarvis_screen
    check("read_screen is jarvis_screen's own name for a screen read",
          jarvis_screen.SCREEN_TOOL == "read_screen" and "read_screen" in G.RECORDED_READS)
    check("... and it is not a tool the model can call (nothing on the screen starts a look)",
          "read_screen" not in jarvis_agent.TOOLS)
    # read_camera: the read a Jarvis Live camera question records (the
    # owner's answer of 2026-09-28, docs/LIVE-DESIGN.md) - not a model tool
    # either, and on the step event's list so it reaches the apps by name.
    import jarvis_live
    check("read_camera is jarvis_live's own name for a camera read",
          jarvis_live.CAMERA_TOOL == "read_camera" and "read_camera" in G.RECORDED_READS)
    check("... not a tool the model can call (nothing the camera sees starts a look)",
          "read_camera" not in jarvis_agent.TOOLS)
    check("... and on jarvis_agent.STEP_READS, like read_screen",
          {"read_screen", "read_camera"} <= set(jarvis_agent.STEP_READS))
    check("a camera read is governed by the screen's rule (is_screen_read)",
          G.is_screen_read({"phase": "tool_finished", "tool": "read_camera", "ok": True}))
    check("RECORDED_READS names nothing that is not on the list",
          set(G.RECORDED_READS) <= set(G.READ_ALOUD_TOOLS), G.RECORDED_READS)
    for private in ("email_check", "calendar_read", "notes_search", "memory_search",
                    "my_files", "file_read", "send_email", "draft_email", "home_control",
                    "append_obsidian_daily", "append_logseq_journal", "create_joplin_note",
                    "coming_up"):
        check(f"{private} is not on it", private not in G.READ_ALOUD_TOOLS)


def t_the_step_event_carries_the_real_name():
    for name in G.READ_ALOUD_TOOLS:
        got = jarvis_agent._step_event("tool_started", name)
        check(f"a {name} step says {name}", got.get("tool") == name, got)
    got = jarvis_agent._step_event("tool_started", "web_search_but_made_up")
    check("a name the model made up is 'unknown'", got.get("tool") == "unknown", got)
    check("... and 'unknown' is not on the list", "unknown" not in G.READ_ALOUD_TOOLS)
    check("STEP_READS is exactly the recorded reads on the list",
          set(jarvis_agent.STEP_READS) == set(G.RECORDED_READS), jarvis_agent.STEP_READS)


def t_the_file_both_apps_read_is_current():
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_private_aloud_cases.py)",
              have == doc)


def t_the_table_says_what_the_owner_said():
    table = json.loads(G.document())
    by_tool = {}
    for c in table["cases"]:
        if c["name"].startswith("the tool "):
            by_tool[c["name"][len("the tool "):-len(" ran")]] = c["read"]
    check("every real tool has a row", set(by_tool) == set(jarvis_agent.TOOLS),
          sorted(set(jarvis_agent.TOOLS) ^ set(by_tool)))
    for tool, read in sorted(by_tool.items()):
        check(f"{tool}: {'read aloud' if read else 'on screen'}",
              read == (tool in G.READ_ALOUD_TOOLS))
    for c in table["cases"]:
        if c["stream"] != "live" and not c["heard"]["private_aloud"]:
            check(f"not knowing stays on screen: {c['name']}", c["read"] is False)
    # The screen (owner, 2026-09-28): read aloud, with every earlier rule first.
    screen = {c["name"]: c["read"] for c in table["cases"] if "screen" in c["name"].lower()}
    want = {
        "the screen was read (read_screen)": True,
        "the screen was read, then email_check": False,
        "web_search then the screen was read": True,
        "the screen was read, with a sensitive saved fact": False,
        "the screen was read, the router kept it here (gate screen), no facts": True,
        "the screen was read, but the PC marked the question private": False,
        "the screen was read, with remembered facts, memory kept on screen": False,
        "the screen was read, stream dropped": False,
        "a name that is not exact (Read_Screen) counts as unknown": False,
    }
    for name, read in want.items():
        check(f"screen: {name} -> {'read aloud' if read else 'on screen'}",
              screen.get(name) is read, screen.get(name))
    # Under "Only trust the talk button" (owner, 2026-09-28): a "hey Jarvis"
    # turn's screen answer stays on screen unless the owner allowed it
    # (`screen_aloud`), and the setting touches only the screen.
    rows = {c["name"]: c for c in table["cases"]}
    strict = {
        "hey Jarvis under 'Only trust the talk button': the screen was read, stays on screen":
            False,
        "hey Jarvis under 'Only trust the talk button', screen answers allowed aloud: read aloud":
            True,
        "hey Jarvis, screen answers allowed aloud, but a sensitive saved fact": False,
        "hey Jarvis, screen answers allowed aloud, but the PC marked the question private": False,
        "hey Jarvis, screen answers allowed aloud, then email_check": False,
        "hey Jarvis, screen answers allowed aloud, stream dropped": False,
        "hey Jarvis under 'Only trust the talk button': web_search then the screen was read":
            False,
        "hey Jarvis under 'Only trust the talk button': web_search only (the screen setting "
        "does not touch it)": True,
        "screen_aloud false comes before 'voice check is enough' (a reply no PC sends)": False,
        "an older PC's reply with no screen_aloud field: the screen was read, on screen": False,
        "an older PC's reply with no screen_aloud field: web_search is read aloud": True,
    }
    for name, read in strict.items():
        check(f"strict hands-free: {name} -> {'read aloud' if read else 'on screen'}",
              name in rows and rows[name]["read"] is read, rows.get(name))
    older = [c for c in table["cases"] if "no screen_aloud field" in c["name"]]
    check("the older-PC rows really leave the field out (so both apps' 'missing = false' "
          "is tested)", len(older) == 3 and all("screen_aloud" not in c["heard"] for c in older),
          older)
    check("every other row says screen_aloud",
          all("screen_aloud" in c["heard"] for c in table["cases"] if c not in older))
    for c in table["cases"]:
        steps = c["steps"]
        if (any(G.is_screen_read(s) for s in steps)
                and c["heard"].get("screen_aloud") is not True):
            check(f"a screen read without screen_aloud stays on screen: {c['name']}",
                  c["read"] is False)
    check("the fixed line", table["on_screen"] == "It's on your screen.")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
