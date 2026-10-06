"""The memory pane's routes: see it, change it, forget it, take it with you.

Extraction now fills a review queue on its own. Until these routes existed
there was no way to read that queue, no way to see what had already been
accepted, and `MemoryStore.retire()` had no caller anywhere in the tree - so a
fact, once in, was in.

Four properties are worth pinning and are pinned here:

  * forgetting RETIRES, it does not delete. The row stays and stops being
    current. A bi-temporal store whose UI deletes rows is not bi-temporal.
  * editing SUPERSEDES. Overwriting the text in place would throw away when
    the old wording was true, which is the one thing this store is built for.
  * every write takes ONE integer id. There is no list form, because
    forgetting is irreversible.
  * the learning switch has a floor: JARVIS_EXTRACT=0 in the environment wins
    over anything the pane sets.

    python3 test_memory_pane.py
"""
import ast, json, os, sys, tempfile, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder
# in the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _stmt(src, marker):
    """The innermost statement of `src` that `marker` is part of, or None.

    This is what the route checks below read instead of a fixed window
    (`i = src.index(marker); src[i:i + 900]`). A window is a promise about how
    many characters away the next thing is, so any edit above it - a comment,
    a blank line, a longer local name - slides the code the window was written
    for out of view, and the check then reports on whatever moved in. This
    suite's own 1100-character sleep_time window did exactly that on
    2026-10-03: the block grew and two real lines read as missing. The AST node
    the marker opens travels with the edit, so the same assertion survives a
    refactor.

    None means the marker is gone. Every caller turns that into a red check -
    a marker that disappears must never read as "nothing to look at".
    """
    off = src.find(marker)
    if off < 0:
        return None
    line = src.count("\n", 0, off) + 1          # the marker's line, 1-based
    best = None
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.stmt):
            continue
        end = n.end_lineno or n.lineno
        if not (n.lineno <= line <= end):
            continue                            # does not span the marker
        if best is None or (n.lineno, -end) > (best.lineno,
                                               -(best.end_lineno or best.lineno)):
            best = n                            # innermost: latest start, then shortest
    return best


def _block(src, marker):
    """The source of that statement - what the fixed windows used to hold."""
    node = _stmt(src, marker)
    return ast.get_source_segment(src, node) if node is not None else ""


def _strings_in_test(src, marker):
    """Every string constant in the marker statement's own condition.

    A whitelist is checked by reading the `in (...)` it actually is, rather
    than by looking for the name within N characters of the branch: the old
    `"/api/memory/sleep_time" in src[i:][:200]` was a question about layout.
    It lists no strings, or names the branch differently, for a condition
    built out of a constant, so a red check there means "read this by hand".
    """
    node = _stmt(src, marker)
    test = getattr(node, "test", None)
    if test is None:
        return set()
    return {n.value for n in ast.walk(test)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _after(src, branch, guard):
    """The part of `branch`'s body that follows the statement holding `guard`.

    The edit path has no `if` of its own - it is the code that falls through
    after the forget branch, marked only by a `# /api/memory/edit` comment.
    A comment is not a boundary the tree knows about; a body position is.
    """
    node = _stmt(src, branch)
    body = getattr(node, "body", [])
    for i, st in enumerate(body):
        if guard in (ast.get_source_segment(src, st) or ""):
            return "\n".join(ast.get_source_segment(src, s) or ""
                             for s in body[i + 1:])
    return ""


def lift(*names, **extra):
    """Named top-level functions out of jarvis_hud.py, run in isolation."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    want, body = set(names), []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in want:
            body.append(node)
    missing = want - {getattr(n, "name", "") for n in body}
    if missing:
        raise AssertionError(f"not at module level in jarvis_hud.py: {sorted(missing)}")
    ns = {"json": json, "time": time, "Path": Path, "os": os}
    ns.update(extra)
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    return ns


# ---- the learning switch ------------------------------------------------

def t_learning_switch():
    tmp = Path(tempfile.mkdtemp())
    ns = lift("learning_enabled", "set_learning",
              CONFIG_DIR=tmp, LEARNING_FILE=tmp / "learning.json",
              EXTRACT_ENABLED=True)
    check("an absent file reads as on", ns["learning_enabled"]() is True,
          "inventing 'off' from a missing file would silently disable a "
          "feature the boot banner says is running")
    r = ns["set_learning"](False)
    check("turning it off sticks", r["ok"] and ns["learning_enabled"]() is False, repr(r))
    check("and the file is real json",
          json.loads((tmp / "learning.json").read_text())["enabled"] is False)
    ns["set_learning"](True)
    check("turning it back on sticks", ns["learning_enabled"]() is True)

    # The floor. An environment variable is the owner speaking before the
    # process started; a switch in a window must not override that.
    tmp2 = Path(tempfile.mkdtemp())
    off = lift("learning_enabled", "set_learning",
               CONFIG_DIR=tmp2, LEARNING_FILE=tmp2 / "learning.json",
               EXTRACT_ENABLED=False)
    check("JARVIS_EXTRACT=0 is a floor the pane cannot lift",
          off["learning_enabled"]() is False)
    r = off["set_learning"](True)
    check("and setting it on says so plainly rather than lying",
          r["enabled"] is False and "overrides this switch" in (r.get("note") or ""),
          repr(r))

    # A corrupt file must not take the surface down.
    (tmp / "learning.json").write_text("{not json")
    check("a corrupt switch file reads as on rather than raising",
          ns["learning_enabled"]() is True)


def t_qs_int():
    ns = lift("_qs_int")
    class H:
        def __init__(self, p): self.path = p
    q = ns["_qs_int"]
    check("a plain value is read", q(H("/api/memory/facts?limit=42"), "limit", 500) == 42)
    check("no query string gives the default", q(H("/api/memory/facts"), "limit", 500) == 500)
    check("garbage gives the default", q(H("/x?limit=all"), "limit", 500) == 500)
    check("negative is clamped up, not passed to LIMIT",
          q(H("/x?limit=-1"), "limit", 500) == 1)
    check("absurd is clamped down", q(H("/x?limit=99999999"), "limit", 500) == 5000)
    check("a missing key gives the default", q(H("/x?other=3"), "limit", 500) == 500)


# ---- the routes, as source assertions -----------------------------------
# The handler cannot be executed without standing up the whole server, so
# these read the tree. They are controls on shape, not on behaviour. The
# shape is found with ast (`_block`) rather than by character offset, so a
# refactor that moves the route cannot quietly move it out of the assertion.

def t_one_id_at_a_time():
    src = SRC.read_text(encoding="utf-8")
    block = _block(src, 'if route in ("/api/memory/forget"')
    check("the write routes are still there to check", bool(block),
          "the /api/memory/forget, /edit, /learning branch is gone from jarvis_hud.py")
    check("the write routes demand an integer id",
          'isinstance(body.get("id"), int)' in block)
    check("there is no list form anywhere in them",
          '"ids"' not in block and "body.get('ids')" not in block,
          "forgetting is irreversible; a list form is an approve-all with "
          "another name")
    check("an unknown id is 404, not a silent success", '"no fact with that id"' in block)
    check("forget calls retire(), not a delete", "st.retire(" in block
          and "DELETE FROM facts" not in block)
    check("and says out loud that it is not a delete",
          "retired, not deleted" in block and "no undo" in block)
    check("edit supersedes rather than overwriting",
          "supersedes=body[\"id\"]" in block and "UPDATE facts" not in block)
    check("an edit that changes nothing is a no-op, not a new row",
          '"unchanged": True' in block)


def t_backdated_corrections_are_reachable():
    """The gap a prior audit found: the store has supported "this was true
    until date X" since bitemporal.patch (retire(valid_to=...), add()'s
    supersede fallback), but nothing ever let a caller supply a date - both
    routes always retired at "now". These pin that a caller finally can.
    """
    src = SRC.read_text(encoding="utf-8")
    block = _block(src, 'if route in ("/api/memory/forget"')
    check("the write routes are still there to check", bool(block))

    check("forget accepts an optional valid_to",
          'valid_to = body.get("valid_to")' in block)
    check("forget passes it straight through to retire(), not just to now",
          'st.retire(body["id"], valid_to=valid_to)' in block)
    check("edit accepts the same optional field",
          block.count('valid_to = body.get("valid_to")') == 2,
          "both forget and edit need their own valid_to, since they are two "
          "separate branches of the same route")
    check("a non-numeric valid_to is refused, not coerced or ignored",
          block.count("valid_to must be a unix timestamp") == 2)

    # Ordering matters: add()'s own supersede fallback ("callers that know
    # the real date call retire() with it before adding", jarvis_memory.py)
    # only works if retire() actually runs BEFORE add_fact() in the edit
    # branch - the other order silently retires at "now" regardless of what
    # the caller sent. The edit path is the write-routes body after the
    # edit-only guard, taken from the tree, so nothing here is an offset.
    edit_block = _after(src, 'if route in ("/api/memory/forget"',
                        'text == str(fact.get("text") or "") and valid_to is None')
    check("the edit branch is still there to check", bool(edit_block))
    retire_at = edit_block.find('st.retire(body["id"], valid_to=valid_to)')
    add_at = edit_block.find('add_fact(text, source="edited"')
    check("a backdated edit retires the old fact BEFORE superseding it",
          -1 < retire_at < add_at,
          "add()'s same-fact supersede path only backdates correctly when "
          "retire(valid_to=...) has already run")

    check("an edit with the same wording but a new valid_to is NOT a no-op",
          'text == str(fact.get("text") or "") and valid_to is None' in block,
          "supplying only a date to correct is a real correction, not "
          "nothing happening")


def t_reads_are_honest():
    src = SRC.read_text(encoding="utf-8")
    block = _block(src, 'if path == "/api/memory/facts":')
    check("the facts list is still there to check", bool(block))
    check("the facts list includes retired rows",
          "ORDER BY valid_from DESC" in block and "WHERE valid_to IS NULL" not in block,
          "hiding retired facts makes a superseded fact look deleted")
    check("each row is marked current or not", '"current"' in block)
    check("the export says nothing was sent anywhere",
          "Nothing was sent anywhere" in src)
    check("both reads close their connection",
          block.count("finally:") >= 1 and block.count("c.close()") >= 1)


def t_sleep_time_offer():
    """The overnight-memory card, and its two backend-facing actions."""
    src = SRC.read_text(encoding="utf-8")
    block = _block(src, 'if path == "/api/memory/pending":')
    check("the pending route is still there to check", bool(block))
    check("the pending route carries the daily card",
          "jarvis_sleep.reminder_card()" in block)
    check("the card rides inside setup, not a second top-level key",
          '"sleep_time_offer"' in block and 'setup["sleep_time_offer"]' in block,
          "a client already reading setup for one thing should not have to "
          "read a second field for a related one")

    # The sleep_time ACTION is a branch of the write-routes statement, not a
    # route of its own - so the block is that branch, found by its own marker.
    # The old form was a 1100-character window, which the block outgrew.
    route_block = _block(src, 'if route == "/api/memory/sleep_time"')
    check("the sleep_time action is still there to check", bool(route_block))
    check("the enable action calls set_enabled", "jarvis_sleep.set_enabled(" in route_block)
    check("the stop-asking action calls set_remind", "jarvis_sleep.set_remind(" in route_block)
    check("a body with neither key is refused, not silently accepted",
          "not isinstance(sleep_enabled, bool) and not isinstance(sleep_remind, bool)"
          in route_block)
    check("a write that failed to persist is reported as a failure, not 200",
          "200 if out.get(\"ok\") else 500" in route_block)
    check("sleep_time is in the shared write whitelist",
          "/api/memory/sleep_time"
          in _strings_in_test(src, 'if route in ("/api/memory/forget"'),
          "the write-routes branch no longer lists /api/memory/sleep_time - "
          "if its condition is no longer a literal `in (...)`, read it by hand")


def t_it_is_reachable():
    """CONTROL. A route nothing can call is the defect this project keeps
    producing, so check both whitelists actually name them."""
    src = SRC.read_text(encoding="utf-8")
    getw = _block(src, 'if path in ("/api/memory/pending"')
    check("the GET memory whitelist is still there to check", bool(getw))
    for r in ("/api/memory/facts", "/api/memory/export"):
        check(f"GET {r} is in the read whitelist", r in getw, getw[:200])
    check("the three write routes share one guarded branch",
          all(r in src for r in ('"/api/memory/forget"', '"/api/memory/edit"',
                                 '"/api/memory/learning"')))
    # Every one of them must be behind both checks. The branch is the whole
    # write-routes statement, whatever it has grown to.
    block = _block(src, 'if route in ("/api/memory/forget"')
    check("they check the origin", "_origin_ok(self)" in block)
    check("they check the token", "_token_ok(self)" in block)


if __name__ == "__main__":
    for fn in (t_learning_switch, t_qs_int, t_one_id_at_a_time,
               t_backdated_corrections_are_reachable,
               t_reads_are_honest, t_sleep_time_offer, t_it_is_reachable):
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
