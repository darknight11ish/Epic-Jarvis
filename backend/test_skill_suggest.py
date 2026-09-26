"""skill-suggest.patch: GET /api/skills/suggestions, read-only.

Two kinds of check, because this patch edits jarvis_hud.py, which is not in
this repository:

  1. ALWAYS: every context and removed line of the patch is text that
     appearance.patch's output actually contains, contiguously and in order.
     That is the only source of truth this repository has for those lines,
     so it is checked from the patch file itself rather than assumed.
  2. When jarvis_hud.py is present (the owner's machine, after
     apply-patches.ps1): the route is in the GET list, it calls
     jarvis_skill_discovery.view() and nothing that writes or approves, and
     it answers "not available" instead of failing when the module is
     missing.

    python3 test_skill_suggest.py
"""
import ast
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain  # noqa: E402

PATCH = HERE / "skill-suggest.patch"
BASE = HERE / "appearance.patch"
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _hunks(text: str, target: str):
    """[(old_lines, new_lines)] for one file in a unified diff."""
    out, cur, in_file = [], None, False
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            in_file = raw[4:].split("\t")[0].strip().endswith(target)
            continue
        if raw.startswith("--- "):
            continue
        if raw.startswith("@@"):
            cur = ([], [])
            if in_file:
                out.append(cur)
            continue
        if cur is None or not in_file:
            continue
        tag, body = raw[:1], raw[1:]
        if tag in (" ", ""):
            cur[0].append(body)
            cur[1].append(body)
        elif tag == "-":
            cur[0].append(body)
        elif tag == "+":
            cur[1].append(body)
    return out


def _contains(hay, needle):
    n = len(needle)
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def t_every_context_line_is_appearance_patch_output():
    base_new = [new for _, new in _hunks(BASE.read_text(encoding="utf-8"), "jarvis_hud.py")]
    mine = _hunks(PATCH.read_text(encoding="utf-8"), "jarvis_hud.py")
    check("the patch has two hunks", len(mine) == 2, repr(len(mine)))
    for i, (old, _new) in enumerate(mine, 1):
        check(f"hunk {i}: its pre-image is a contiguous run of appearance.patch's output",
              any(_contains(b, old) for b in base_new), "\n".join(old))


def t_the_patch_only_adds_a_read():
    added = "\n".join(l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines()
                      if l.startswith("+") and not l.startswith("+++"))
    for bad in ("offer(", "run(", "maybe_offer", "record_turn", "_append", "check(",
                "approved=", "write_text", "do_POST"):
        check(f"no {bad!r} in what the patch adds", bad not in added, added)
    check("it calls view()", "jarvis_skill_discovery.view()" in added, added)


def _do_get_source() -> str:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "do_GET"]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one do_GET, found {len(found)}")
    return ast.unparse(found[0])


def t_the_route_is_wired_in_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = _do_get_source()
    check("GET list includes /api/skills/suggestions",
          re.search(r"path in \([^)]*'/api/skills/suggestions'", src) is not None, src[:0])
    check("the branch answers with jarvis_skill_discovery.view()",
          "jarvis_skill_discovery.view()" in src, src[:0])
    check("a missing module is 'not available', not an error",
          "is not beside" in src and "'available': False" in src, src[:0])


if __name__ == "__main__":
    for fn in (t_every_context_line_is_appearance_patch_output,
               t_the_patch_only_adds_a_read,
               t_the_route_is_wired_in_the_real_file):
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
