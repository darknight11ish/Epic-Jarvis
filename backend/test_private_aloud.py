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
     and not knowing (a stale or dropped event stream) stays on screen.

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
    check("the list is web_search and home_read, nothing else",
          sorted(G.READ_ALOUD_TOOLS) == ["home_read", "web_search"], G.READ_ALOUD_TOOLS)
    for name in G.READ_ALOUD_TOOLS:
        check(f"{name} is a real tool", name in jarvis_agent.TOOLS)
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
