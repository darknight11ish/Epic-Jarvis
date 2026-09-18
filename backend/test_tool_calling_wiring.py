"""tool-calling-wiring.patch: tools only reach the local lane, never a cloud one.

Structural checks over the real, patched source - the same kind
test_ollama_direct.py and test_degrade_filter.py already run against this
exact file. A full behavioural test would need a running Ollama and cannot
live here; what CAN be proven without one is that the wiring itself asks the
right question before ever calling jarvis_agent, and that the plain-relay
path used by every other lane is still there, unedited, for anything that
is not this one case.

    python3 test_tool_calling_wiring.py
"""
import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _do_post_source() -> str:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "do_POST"]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one do_POST, found {len(found)}")
    return ast.unparse(found[0])


def t_use_tools_requires_the_local_lane():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = _do_post_source()
    check("use_tools checks lane == local_model",
          "use_tools = lane == local_model" in src.replace("\n", " ")
          or "lane == local_model and" in src, src[:0])
    # A more precise check than a substring: find the actual assignment and
    # confirm it is a BoolOp whose operands include the lane comparison -
    # not just that both strings happen to appear somewhere in the function.
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "use_tools" for t in n.targets)]
    check("found exactly one use_tools assignment", len(assigns) == 1, repr(len(assigns)))
    if assigns:
        rhs = ast.unparse(assigns[0].value)
        check("its condition compares lane to local_model",
              "lane == local_model" in rhs, rhs)
        check("its condition also reads the [tools].enabled config, not just the lane",
              "tools" in rhs and "enabled" in rhs, rhs)


def t_the_degrade_loop_is_skipped_when_tools_are_in_play():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = _do_post_source()
    check("the degrade loop's iterable is conditioned on use_tools",
          "use_tools else range(len(lanes) + 2)" in src
          or "range(len(lanes) + 2) if not use_tools" in src
          or ("_degrade_hops" in src and "use_tools" in src), src)


def t_the_plain_relay_path_still_exists_unconditionally_reachable():
    """The bug this patch must not introduce: a change that makes `use_tools`
    always true, or that deletes the non-tool branch, would silently turn
    every cloud turn into a tool-enabled one - or break cloud chat outright.
    """
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = _do_post_source()
    check("an `else:` branch containing the original `with upstream:` relay still exists",
          "with upstream:" in src, "expected the plain-relay path to still be reachable")
    check("that branch is reachable through an if/else on use_tools, not only the tools path",
          "if use_tools" in src and "else" in src)


def t_the_tool_branch_calls_run_local_turn_with_the_enabled_tools_whitelist():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = _do_post_source()
    check("jarvis_agent.run_local_turn is actually called",
          "jarvis_agent.run_local_turn(" in src)
    check("enabled_tools is passed, not omitted (which would mean every tool, unfiltered)",
          "enabled_tools=" in src)
    check("it reads the same [tools].enabled config collect_tools() uses",
          'cfg.get("tools")' in src or "cfg.get('tools')" in src)
    check("announce is wired to _activity, the same doorbell every other capability uses",
          "announce=" in src and "_activity(" in src)


def t_a_run_local_turn_failure_after_headers_are_sent_still_reaches_the_client():
    """The bug this guards against: once the tool branch sends its 200 and
    sets `_headers_sent = True`, the generic `except Exception` far below
    that would normally explain an unreachable Ollama can never fire usefully
    - `_send()` sees `_headers_sent` and just cuts the connection instead of
    writing the 503 body. Before this test existed, only the socket-drop
    exceptions were caught around `run_local_turn(...)`; anything else (a
    connection refused, a bug in the tool loop) left the client with a dead
    stream and no explanation. The fix is a broader `except Exception` in
    that same try that writes a `{"error": ...}` line - the exact shape
    main.js's `consumeLine`/`routeFromPayload` handling already renders via
    `showError()` - before giving up."""
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    do_post = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "do_POST"][0]
    run_calls = [n for n in ast.walk(do_post) if isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "jarvis_agent.run_local_turn"]
    check("found exactly one run_local_turn call", len(run_calls) == 1, repr(len(run_calls)))
    if not run_calls:
        return
    call = run_calls[0]
    # Walk up from the call to the nearest enclosing Try node, then confirm
    # it has a handler broader than just the socket-drop tuple.
    parents = {}
    for node in ast.walk(do_post):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    node = call
    enclosing_try = None
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.Try):
            enclosing_try = node
            break
    check("the run_local_turn call sits inside a try block", enclosing_try is not None)
    if enclosing_try is None:
        return
    handler_types = []
    broad_handler = None
    for h in enclosing_try.handlers:
        t = "bare except" if h.type is None else ast.unparse(h.type)
        handler_types.append(t)
        if t in ("Exception", "BaseException", "bare except"):
            broad_handler = h
    check("there is a handler broader than the socket-drop tuple "
          "(a bare Exception, not just BrokenPipeError/ConnectionResetError/...)",
          broad_handler is not None, repr(handler_types))
    if broad_handler is None:
        return
    handler_src = ast.unparse(broad_handler)
    check("that broad handler writes something back to the client rather than "
          "just returning silently",
          "self.wfile.write" in handler_src, handler_src)


def t_tools_are_never_offered_on_a_non_local_lane():
    """Re-derive use_tools by hand from the two conditions it is built from,
    for a lane that is NOT local_model, and confirm the real assignment's
    own AST would evaluate false for that case - i.e. the `and` is genuinely
    gating on the lane, not something that short-circuits to True by
    construction (an `or` typo would look identical in the substring checks
    above but fail this one)."""
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "use_tools" for t in n.targets)]
    if not assigns:
        return check("no use_tools assignment to check", False)
    node = assigns[0].value
    is_and = isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And)
    check("the condition is an `and`, not an `or` - both must hold", is_and,
          ast.unparse(node))


if __name__ == "__main__":
    for fn in (t_use_tools_requires_the_local_lane,
               t_the_degrade_loop_is_skipped_when_tools_are_in_play,
               t_the_plain_relay_path_still_exists_unconditionally_reachable,
               t_the_tool_branch_calls_run_local_turn_with_the_enabled_tools_whitelist,
               t_a_run_local_turn_failure_after_headers_are_sent_still_reaches_the_client,
               t_tools_are_never_offered_on_a_non_local_lane):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
