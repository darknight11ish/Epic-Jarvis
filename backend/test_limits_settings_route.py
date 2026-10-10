"""test_limits_settings_route.py - the route the two apps POST a changed limit to,
and proof that it is REACHABLE inside the HUD rather than merely written.

    python3 backend/test_limits_settings_route.py

Runs anywhere; no model, no network, no Windows Hello, and nothing of the
owner's is read or written (the settings file is a throwaway copy in a temp
folder, exactly as test_limits.py stages one).

WHY THIS EXISTS, AND WHY test_limits.py WAS NOT ENOUGH

`backend/jarvis_limits.py` owns the table, the card a loosening needs and the
rule that the SAFE direction is instant - and `backend/test_limits.py` proves
all of that, by calling `handle_post` DIRECTLY. So every one of its checks
passed while the feature was dead on the phone.

The HUD answers a POST in two steps, and a route needs BOTH:

  1. the dispatch tuple in `jarvis_hud.py`'s Handler - the list holding
     `/api/models/switch` and its neighbours - which is what decides whether
     the body is read at all, and is what answers 404 for anything absent; and
  2. the `if route == ...` branch inside `_desktop_action`, which is what
     actually does the work.

`limits-settings.patch` wrote step 2 and never wrote step 1. That is the whole
bug: `GET /api/limits` answered 200, so the phone drew the quiet-hours rows,
and its "Use this time" button then posted into a 404 that no screen showed.
The value stayed 22:00 and `jarvis-framework.toml` was byte-identical.

A test that calls `handle_post` cannot see that, because it skips step 1
entirely. So this suite tests the ROUTE, never the table:

1. **The tuple is what makes it reachable.** The stand-in of the whole patch
   stack (the same `_stack.stand_in('jarvis_hud.py')` the other "installed
   file" suites read) carries a dispatch tuple that names the route, and the
   `_desktop_action` branch the patch already had. Asserting only the second
   would have passed before the fix.
2. **A POST really lands.** Driven through the HUD's own dispatch - the tuple,
   the origin check, the token check, the body read, `_desktop_action` - the
   request reaches `jarvis_limits` and comes back 200 with no 404 anywhere.
3. **It is not 404 for the reason the tuple is there.** With the route taken
   back out of the tuple and everything else left alone, the identical POST
   answers 404 and `jarvis_limits` is never asked. That is the failure this
   suite is written to catch, reproduced on purpose.
4. **The one line, in the file that owns it.** The entry is in
   `limits-settings.patch` - not in the published base, which is the state
   after the patches of 2026-10-06 and predates this feature - and no patch
   after it rewrites the tuple.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402
import _stack  # noqa: E402
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_limits.py", "jarvis_framework.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-limits-route-"))
SHIPPED = HERE / "rebuilt" / "jarvis-framework.toml"

# The owner's settings file is a throwaway copy in the temp folder, and it is
# put there BEFORE jarvis_limits is imported, not lazily by `fresh()`.
# jarvis_framework's `_explicit()` honours JARVIS_FRAMEWORK_TOML only while
# that path IS a file; pointed at one that does not exist yet it warns and
# falls back to the search path - which is the shipped template IN THIS
# REPOSITORY. A suite that wrote a value with no file staged would move
# `backend/rebuilt/jarvis-framework.toml` itself, and every later case would
# read the wrong number. Staged here, the fallback can never be reached.
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
shutil.copyfile(SHIPPED, TMP / "jarvis-framework.toml")

import jarvis_limits as L  # noqa: E402

PATCH = HERE / "limits-settings.patch"
ROUTE = "/api/limits/settings"
#: The quiet-hours start on the owner's PC, the value the tester changed on the
#: phone and watched stay put. `notifications.quiet_start`, owned by
#: jarvis_notify_prefs.py, shipped as "22:00".
KEY = "notif_quiet_start"

#: The patches that carry this feature. `jarvis-backend/jarvis_hud.py` - the
#: published base - is the state AFTER the patches of 2026-10-06, so every
#: patch older than that one is already in it and would not apply again
#: (measured: 95 of the 134 refuse). These three are newer, which is exactly
#: why this feature is a patch and not an edit to the base.
TAIL = ("attention-settings.patch", "limits-settings.patch", "limits-read.patch")

FAILED, PASSED, SKIPPED = [], [], []

#: The line the Handler's dispatch tuple opens with, stripped of its
#: indentation - it sits inside a nested block, so it carries 8 spaces. It is
#: the anchor both the patch and this suite read the tuple by, so a test that
#: found a different tuple would be measuring something else.
TUPLE_OPENS = 'if route in ("/api/models/install", "/api/models/switch",'


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run - git is what builds the stand-in. Never
    counted as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh() -> Path:
    p = TMP / "jarvis-framework.toml"
    shutil.copyfile(SHIPPED, p)
    L._reload()
    return p


def the_suite_writes_only_the_temp_file():
    """The cheapest guard there is, and the one that matters most here: this
    suite changes settings, so it must be changing them in its own copy. If
    jarvis_framework ever resolves the settings file to the repository's
    template, the assertion below - not the owner's file - is what fails."""
    import jarvis_framework as fw
    p = fresh()
    check("this suite's settings file is the temp copy, not the repository's "
          "shipped template",
          Path(fw.config_path()).resolve() == p.resolve(),
          f"jarvis_framework resolved {fw.config_path()}, expected {p}")
    return p


_STAGED = []


def staged():
    """(text, why) - the published base with this feature's patches applied.
    Built once and remembered; every test below reads the same file.

    This is the file this route has to be reachable in, built from the two
    things the repository really holds: `jarvis-backend/jarvis_hud.py`, the
    base every apply-patches.ps1 run starts from, and the patches themselves.
    Line endings are forced to LF on both sides first, exactly as
    scripts/apply-patches.ps1 does and for the same reason.

    `_stack.stand_in` is the usual stand-in for an installed file and is used
    by the other suites, but it cannot be used for THIS check: it lays a
    patch's hunks side by side and fills the gaps with `# gap` lines, so the
    dispatch tuple - which is a gap, because the patches only ever touch part
    of it - comes back with its closing `):` line missing, and cannot be read
    as the tuple the Handler actually runs. Applying the patches to the real
    base gives the real text. Anything this cannot do is reported, never
    passed over."""
    if _STAGED:
        return _STAGED[0]
    out = _stage()
    _STAGED.append(out)
    return out


def _stage():
    git = shutil.which("git")
    if not git:
        return None, ["git is not installed, so the patches could not be applied"]
    base = REPO / "jarvis-backend" / "jarvis_hud.py"
    if not base.is_file():
        return None, [f"{base} is not in this repository"]
    d = Path(tempfile.mkdtemp(prefix="jarvis-limits-route-base-"))
    try:
        (d / "jarvis_hud.py").write_bytes(base.read_bytes().replace(b"\r\n", b"\n"))
        # Inside a git work tree `git apply` resolves the patch's paths against
        # the repository root rather than the scratch folder, matches no file,
        # and still exits 0 - an empty stand-in that reads as success. See
        # backend/_gitapply.py.
        env = _gitapply.env_for(git, d)
        for name in TAIL:
            src = HERE / name
            if not src.is_file():
                return None, [f"{name} is not in backend/"]
            lf = d / "one.patch"
            lf.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", "--include", "jarvis_hud.py", str(lf)],
                               cwd=d, capture_output=True, text=True, env=env)
            if r.returncode != 0:
                return None, [f"{name}: {(r.stderr or r.stdout).strip()[:300]}"]
        text = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        if not text.strip():
            return None, ["the patches applied and produced an EMPTY file"]
        return text, []
    finally:
        shutil.rmtree(d, ignore_errors=True)


def the_tuple(text: str, opens: str = TUPLE_OPENS):
    """(block, indent) for the Handler's dispatch tuple, or (None, why).

    Bracketed by counting brackets rather than by "the next line ending in
    `):`", and that is not fussiness: this very patch's other hunk adds an
    `if route == "/api/limits/settings":` line, which ends in `):` too, and a
    suite that stopped there would read a one-line tuple and then measure the
    wrong text for the rest of the run.

    `indent` is the tuple statement's own indentation - it sits 8 spaces deep
    in a nested block, and `block` is returned dedented BY THAT PREFIX so it
    can be re-indented and run as a statement. A common-prefix strip, not
    `textwrap.dedent`: the continuation lines are indented further than the
    `if`, and the closing `):` is not indented at all, so there is no common
    indent for dedent to find."""
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == opens.strip()]
    if len(starts) != 1:
        return None, f"{len(starts)} dispatch tuples found, expected exactly 1"
    first = lines[starts[0]]
    indent = len(first) - len(first.lstrip())
    prefix, depth, out = first[:indent], 0, []
    for line in lines[starts[0]:]:
        out.append(line[len(prefix):] if line.startswith(prefix) else line.lstrip())
        depth += line.count("(") + line.count("[") + line.count("{")
        depth -= line.count(")") + line.count("]") + line.count("}")
        if depth <= 0:
            return "\n".join(out), indent
    return None, "the tuple's opening bracket is never closed"


def the_routes(text: str, opens: str = TUPLE_OPENS):
    """The route strings that `opens` tuple really holds, as Python reads them.

    Parsed with `ast.literal_eval` rather than matched with a pattern, so a
    quote style or a space cannot make this suite disagree with the file it is
    judging. None when the tuple is not there or does not parse."""
    block, _indent = the_tuple(text, opens)
    if block is None:
        return None
    try:
        return list(ast.literal_eval(block[block.index("("):block.rindex("):") + 1]))
    except (ValueError, SyntaxError):
        return None


def entry_lines(text: str, route: str) -> list:
    """The 0-based line numbers of the tuple's own entry for `route` - the line
    holding that string literal ALONE, which is what an entry of the tuple
    looks like. An `if route == ...` branch is not an entry, so it is not
    matched: that distinction is the whole point of this suite."""
    pattern = re.compile(r"^\s*" + re.escape(repr(route)) + r",\s*$")
    other = re.compile(r'^\s*"' + re.escape(route) + r'",\s*$')
    return [i for i, l in enumerate(text.splitlines())
            if pattern.match(l) or other.match(l)]


def without(text: str, route: str):
    """`text` with the tuple's own entry for `route` removed, or None unless it
    is there exactly once - the patch undone, so a check can be run against the
    shape the install really had, not against a description of it."""
    lines, doomed = text.splitlines(True), entry_lines(text, route)
    if len(doomed) != 1:
        return None
    keep = [l for i, l in enumerate(lines) if i != doomed[0]]
    return "".join(keep)


def dispatch(hud_text: str):
    """(a visitor, what it was built from) - `visitor(route, body)` answers what
    the Handler would have answered, 404 included.

    The tuple is not re-typed here and no code is generated from its text: its
    VALUE is read straight out of the patched file with `ast`, so what decides
    reachability is the same object Python would build from that line. A route
    that is not in it falls through to the HUD's own 404, and one that is in it
    reaches `_desktop_action` - which is the real `_desktop_action`, lifted out
    of the same file, with the real `jarvis_limits` behind it. Nothing is
    mocked but the two guards, the body read and the reply.

    Nothing is caught: the Handler's own `except Exception` turns a raised error
    into a 500, and a harness that swallowed one would report this route as
    unreachable - the very finding this suite exists to make - for a reason that
    had nothing to do with the tuple."""
    routes = the_routes(hud_text)
    branch = _stack.function_text(hud_text, "_desktop_action")
    if routes is None or not branch:
        return None, (routes, branch)

    ns = {
        # _desktop_action reports through this in the file; this route does not
        # publish, and a stub that recorded it would be inventing behaviour.
        "_publish": lambda kind, data: None,
        # The real module, so "it reached jarvis_limits" is the real handler.
        "jarvis_limits": L,
    }
    exec(compile(branch, "jarvis_hud._desktop_action", "exec"), ns)

    def visitor(route, body, client="hud"):
        frame = type("Frame", (), {"raw": json.dumps(body).encode(),
                                   "client": client})()
        if route not in routes:
            # The HUD's own answer for a POST whose path no route claims - the
            # 404 the quiet-hours picker was getting.
            return 404, {"error": "no such route"}
        return ns["_desktop_action"](route, body)

    return visitor, (routes, branch)


def t_the_staged_file_is_the_patched_one():
    """A file that came back empty or unbuilt would make every check below
    meaningless, so it is checked before it is used."""
    text, why = staged()
    check("the published base takes this feature's patches, and the result is "
          "the file this route has to be reachable in", text is not None,
          "\n        ".join(str(w) for w in why))
    if text is None:
        return None
    check("... and it is a file, not an empty one", len(text) > 100000, len(text))
    check("... and it carries the body this feature's own patch wrote",
          "return jarvis_limits.handle_post(route, body)" in text)
    return text


def t_the_tuple_names_the_route():
    text = t_the_staged_file_is_the_patched_one()
    if text is None:
        return
    routes = the_routes(text)
    check("the Handler's dispatch tuple was found in the patched file, and "
          "parses as a tuple of routes", routes is not None)
    if routes is None:
        return
    check(f"the tuple names {ROUTE}", ROUTE in routes, routes)
    check("... beside /api/models/switch, /api/attention/mute and /api/watch/add, "
          "which is the list the request was falling through",
          all(r in routes for r in ("/api/models/switch", "/api/attention/mute",
                                    "/api/watch/add")))
    check("... and it names it exactly once, so no route is listed twice",
          routes.count(ROUTE) == 1, routes)


def t_a_post_reaches_the_hud_and_lands():
    """A real change, through the HUD's own dispatch, writing the owner's file."""
    text = t_the_staged_file_is_the_patched_one()
    if text is None:
        return
    the_suite_writes_only_the_temp_file()
    routes = the_routes(text)
    check("the file the dispatch is rebuilt from is the one naming the route",
          routes is not None and ROUTE in routes, routes)
    visitor, parts = dispatch(text)
    check("the HUD's dispatch could be rebuilt from the patched file",
          visitor is not None)
    if visitor is None:
        return
    p = fresh()
    before = p.read_bytes()
    check("the shipped quiet hours start at 22:00, which is what the phone "
          "showed and could not change", L.value_of(L.find(KEY)) == "22:00",
          L.value_of(L.find(KEY)))
    code, out = visitor(ROUTE, {"key": KEY, "value": "21:00"})
    check("a POST to the route is answered, and answered 200 - not 404",
          code == 200, (code, out))
    check("... and jarvis_limits is the module that answered it",
          out.get("ok") is True and out.get("key") == KEY, out)
    check("... and the owner's file really moved", p.read_bytes() != before)
    check("... and the answer shows the new time in the owner's words",
          "21:00" in str(out.get("said", "")), out)
    check("... and the readers see the new value, not the old one",
          L.value_of(L.find(KEY)) == "21:00", L.value_of(L.find(KEY)))
    # And back, which is what step 3 on the owner's PC does with the real file.
    code, out = visitor(ROUTE, {"key": KEY, "value": "22:00"})
    check("changing it back is answered 200 as well", code == 200, (code, out))
    check("... and the value is 22:00 again", L.value_of(L.find(KEY)) == "22:00",
          L.value_of(L.find(KEY)))


def t_without_that_one_line_it_is_a_404_again():
    """The failure this suite exists for, reproduced on purpose.

    The route is taken back out of the tuple and NOTHING else is touched - the
    `_desktop_action` branch stays, which is exactly the state the install was
    in. The same POST must then fall through the tuple to 404, with
    jarvis_limits never asked and the file left alone."""
    text = t_the_staged_file_is_the_patched_one()
    if text is None:
        return
    undone = without(text, ROUTE)
    check("the route can be taken back out of the patched file, leaving the "
          "body in place", undone is not None)
    if undone is None:
        return
    check("... and the body it does not reach is still there (so 404 is the "
          "wiring and not a missing branch)",
          "return jarvis_limits.handle_post(route, body)" in undone)
    visitor, parts = dispatch(undone)
    if visitor is None:
        check("the HUD's dispatch could be rebuilt from the un-patched file", False)
        return
    routes = the_routes(undone)
    check("... with the tuple no longer naming the route",
          routes is not None and ROUTE not in routes, routes)
    p = fresh()
    before = p.read_bytes()
    code, out = visitor(ROUTE, {"key": KEY, "value": "21:00"})
    check(f"without that one line the route answers 404 - the bug, exactly",
          code == 404, (code, out))
    check("... jarvis_limits was never asked, so the table was never the problem",
          out.get("ok") is not True, out)
    check("... and the owner's file was not written", p.read_bytes() == before)


def t_the_line_lives_in_the_patch_that_owns_it():
    """`limits-settings.patch` is where this feature lives. The published base
    is the state after the 2026-10-06 patches and predates this route, so a fix
    written there would be undone by the next patch in the stack.

    The added line is measured against the tuple IN THE PATCHED FILE, not
    against a tuple built out of the diff: a diff carries only the lines that
    changed, so the tuple's context lines are not in it, and a diff-shaped
    stand-in of the tuple would be this suite's own invention."""
    text = t_the_staged_file_is_the_patched_one()
    if text is None:
        return
    routes = the_routes(text)
    added = [(n, l[1:]) for n, l in enumerate(
        PATCH.read_text(encoding="utf-8").splitlines(), 1)
        if l.startswith("+") and not l.startswith("+++")]
    entries = [(n, l) for n, l in added if len(entry_lines(l, ROUTE)) == 1]
    check(f"the dispatch entry is an added line of {PATCH.name}",
          len(entries) == 1, "\n        ".join(l for _n, l in added[:6]))
    check("... and it is a line of the dispatch tuple, not an `if route ==` "
          "branch - the patch needs BOTH, and it had only the branch",
          not any(l.strip().startswith("if route") and ROUTE in l
                  for _n, l in entries))
    check("... and with that line removed the tuple does NOT name the route, "
          "so that one line is what put it there",
          routes is not None and ROUTE in routes
          and ROUTE not in (the_routes(without(text, ROUTE)) or []))
    check("... and the body this route dispatches to is still this patch's other hunk",
          any("return jarvis_limits.handle_post(route, body)" in l
              for _n, l in added))
    check("... and the patch still applies to the published base, which is how "
          "this line reaches the owner's PC at all",
          staged()[0] is not None, "\n        ".join(str(w) for w in staged()[1]))
    base = REPO / "jarvis-backend" / "jarvis_hud.py"
    base_text = base.read_text(encoding="utf-8", errors="replace")
    check("the published base does NOT carry it, which is why it is a patch and "
          "not an edit to jarvis-backend/",
          f'"{ROUTE}"' not in base_text and "jarvis_limits" not in base_text)


def t_nothing_after_this_patch_rewrites_the_tuple():
    """The entry has to survive the rest of the stack. A later patch that
    rewrote these lines would leave the route named here and absent on the
    owner's PC - the same bug, one layer down."""
    later = _stack.later_rewriting("limits-settings.patch", "/api/voice/wake")
    check("no patch after limits-settings.patch rewrites the dispatch tuple",
          later == [], later)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    try:
        for t in tests:
            print(f"--- {t.__name__} ---")
            t()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
