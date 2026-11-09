"""test_recent_changes_read.py - "What's new in Jarvis" quotes the record (Task-50).

    python -B backend/test_recent_changes_read.py

The Brain's Tutorials and the FAQ tab draws a "What's new in Jarvis" pane.
The words in it are NOT the desktop's: `GET /api/recent-changes` carries the
generated `jarvis_recent_changes.py` module - the same bullets the chat's
"what changed in your last update?" answer reads (JARVIS-API section 158.2) -
and this suite proves the route is a faithful read of it.

What is proved here, with no server, no network and no model:

  * the route is one of `jarvis_brain_reads`'s own PATHS, so `install()` puts
    the same token and origin checks in front of it as every other Brain read;
  * a module with bullets answers 200 with EXACTLY those bullets, in the
    record's own order, plus the module's own VERSION (read beside it) and a
    `source` naming the module - so a screen has nothing to invent;
  * a module with NO bullets answers 200, `available: true`, an empty list,
    and the module's own `NO_RECORD_WORDS` - the pane's sentence is the
    backend's, never the desktop's guess;
  * the module missing from this PC answers 501 with `available: false` and
    the standard "run apply-patches.ps1" sentence, and the pane says that
    instead of an empty "up to date" list;
  * a module that raises answers 500 with `available: false` and a plain
    sentence - never a traceback and never an invented list;
  * the read is bounded: at most MAX_RECENT_BULLETS bullets, each cut to
    MAX_RECENT_BULLET_CHARS, so a runaway record cannot flood a window;
  * the module is a shipped file (`_where.SHIPPED`), and the route is not
    something the AI model can call.
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_brain_reads.py", "jarvis_recent_changes.py")

import jarvis_brain_reads as B  # noqa: E402
import jarvis_recent_changes as RC  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_the_route_is_an_install_path():
    check("the route is one of this module's own PATHS",
          B.RECENT_CHANGES_PATH in B.PATHS, B.PATHS)
    check("the route is a GET (never a POST)",
          B.RECENT_CHANGES_PATH not in B.POST_PATHS)
    check("handle_get answers the route without a query",
          callable(getattr(B, "handle_get", None)))
    code, out = B.handle_get(B.RECENT_CHANGES_PATH)
    check("a direct call answers 200", code == 200, (code, out))


def t_the_bullets_are_the_modules_own():
    code, out = B.handle_get(B.RECENT_CHANGES_PATH)
    check("the answer says the module is available",
          code == 200 and out.get("available") is True, (code, out))
    expected = [b for b in RC.bullets(limit=B.MAX_RECENT_BULLETS) if b]
    check("every bullet is the module's, in the record's own order",
          out.get("bullets") == expected, (out.get("bullets"), expected))
    check("the answer never carries a bullet the module does not have",
          all(b in list(RC.BULLETS) for b in out.get("bullets") or []),
          out.get("bullets"))
    check("the version is read beside the module, not kept here",
          out.get("version") == RC.version(), (out.get("version"), RC.version()))
    check("the answer names the module it read",
          out.get("source") == "jarvis_recent_changes.py", out.get("source"))
    check("the record's own empty-sentence travels with it",
          out.get("empty_words") == RC.NO_RECORD_WORDS.strip(),
          out.get("empty_words"))
    check("the record really has content today (so the pane is not vacuous)",
          bool(expected), expected)


def t_an_empty_record_says_so():
    real = RC.BULLETS
    try:
        RC.BULLETS = ()
        code, out = B.handle_get(B.RECENT_CHANGES_PATH)
        check("an empty record is still a successful read",
              code == 200 and out.get("available") is True, (code, out))
        check("an empty record carries no bullets", out.get("bullets") == [],
              out.get("bullets"))
        check("an empty record carries the module's own sentence",
              out.get("empty_words") == RC.NO_RECORD_WORDS.strip(),
              out.get("empty_words"))
    finally:
        RC.BULLETS = real


def t_a_missing_module_says_update():
    saved = sys.modules.get("jarvis_recent_changes")
    try:
        sys.modules["jarvis_recent_changes"] = None   # import now raises
        code, out = B.handle_get(B.RECENT_CHANGES_PATH)
        check("an older PC answers 501", code == 501, (code, out))
        check("an older PC says the module is not available",
              out.get("available") is False, out)
        check("an older PC says to run apply-patches.ps1",
              out.get("why") == B.UPDATE, out.get("why"))
        check("an older PC is given no invented list",
              out.get("bullets") == [], out.get("bullets"))
    finally:
        if saved is None:
            sys.modules.pop("jarvis_recent_changes", None)
        else:
            sys.modules["jarvis_recent_changes"] = saved


def t_a_broken_module_never_raises():
    real = RC.bullets
    try:
        def boom(limit=3):
            raise RuntimeError("the record is unreadable")
        RC.bullets = boom
        code, out = B.handle_get(B.RECENT_CHANGES_PATH)
        check("a record that raises answers 500", code == 500, (code, out))
        check("a record that raises is not called available",
              out.get("available") is False, out)
        check("a record that raises is said in plain words",
              isinstance(out.get("why"), str) and "could not be read" in out["why"],
              out.get("why"))
        check("a record that raises still invents nothing",
              out.get("bullets") == [], out.get("bullets"))
    finally:
        RC.bullets = real


def t_the_read_is_bounded():
    real_bullets, real_bounds = RC.BULLETS, (B.MAX_RECENT_BULLETS, B.MAX_RECENT_BULLET_CHARS)
    try:
        RC.BULLETS = tuple("change %d" % n for n in range(60))
        code, out = B.handle_get(B.RECENT_CHANGES_PATH)
        check("at most MAX_RECENT_BULLETS bullets are carried",
              code == 200 and len(out.get("bullets") or []) == B.MAX_RECENT_BULLETS,
              (code, len(out.get("bullets") or [])))
        RC.BULLETS = ("x" * 1000,)
        code, out = B.handle_get(B.RECENT_CHANGES_PATH)
        got = (out.get("bullets") or [""])[0]
        check("one bullet is cut to MAX_RECENT_BULLET_CHARS",
              code == 200 and len(got) == B.MAX_RECENT_BULLET_CHARS, len(got))
    finally:
        RC.BULLETS = real_bullets
        assert (B.MAX_RECENT_BULLETS, B.MAX_RECENT_BULLET_CHARS) == real_bounds


def t_not_a_tool_the_model_can_call():
    """The route is not reachable from the agent - checked by AST, not by text.

    A pin on source TEXT goes red when the code is renamed or improved and stays
    green when the behaviour is wrong (tools/check_no_source_pins.py). So the
    agent's file is parsed: no string constant may name the route, and no name
    or attribute may reach jarvis_brain_reads.
    """
    tree = ast.parse((HERE / "jarvis_agent.py").read_text(encoding="utf-8"))
    strings = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    bad_strings = [s for s in strings
                   if "recent-changes" in s or "recent_changes_api" in s]
    check("no string in jarvis_agent.py names the recent-changes route",
          not bad_strings, bad_strings[:3])
    names = [getattr(n, "id", None) or getattr(n, "attr", None)
             for n in ast.walk(tree)]
    bad_names = [n for n in names if n and "jarvis_brain_reads" in n]
    check("no code path in jarvis_agent.py reaches jarvis_brain_reads",
          not bad_names, bad_names[:3])


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
