"""A token nobody creates is not a default, it is a missing feature.

Two separate problems, one fix.

The phone authenticates by token ALONE - it sends no Origin, so the origin
check cannot help it - and nothing in this project has ever generated one.
docs/INSTALL.md lists that as unbuilt. So the Android client has never been
pairable, on any install, since the day it was written.

And with no token every process on this machine can open /api/events with a
bare GET and read the doorbell. Smaller: anything that could subscribe could
also read ~/.openjarvis directly. But it costs nothing to close.

    python3 test_token_file.py
"""
import ast, os, stat, sys, tempfile, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def lift(config_dir):
    """The real _resolve_token, run against a scratch config directory."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_resolve_token"]
    if not body:
        raise AssertionError("_resolve_token is not defined at module level")
    ns = {"os": os, "Path": Path, "CONFIG_DIR": config_dir,
          "TOKEN_FILE": config_dir / "token"}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
    return ns["_resolve_token"], config_dir / "token"


def t_it_makes_one():
    d = Path(tempfile.mkdtemp()) / "cfg"      # deliberately does not exist yet
    resolve, path = lift(d)
    os.environ.pop("HUD_TOKEN", None)
    tok = resolve()
    check("a token is produced on first run", bool(tok), repr(tok))
    check("and written where the phone can be pointed at it", path.is_file())
    check("the directory is created if missing", d.is_dir())
    check("it is long enough to be worth having", len(tok) >= 32, f"{len(tok)} chars")
    check("the file holds exactly that token",
          path.read_text(encoding="utf-8").strip() == tok)
    check("no temp file is left beside it",
          not list(d.glob("*.tmp")), [p.name for p in d.glob("*")])

    # Stable across restarts, or every boot silently unpairs the phone.
    again = resolve()
    check("a second call returns the SAME token", again == tok,
          "regenerating on every boot would unpair the phone on every boot")


def t_the_environment_still_wins():
    d = Path(tempfile.mkdtemp()) / "cfg"
    resolve, path = lift(d)
    os.environ["HUD_TOKEN"] = "  set-by-hand  "
    try:
        check("HUD_TOKEN beats the file", resolve() == "set-by-hand")
        check("and nothing is written when it is set", not path.exists(),
              "someone who set it meant it; do not generate a rival")
    finally:
        os.environ.pop("HUD_TOKEN", None)

    # An empty variable is not a choice, it is a typo. PowerShell's
    # `$env:HUD_TOKEN=""` sets it to empty rather than unsetting it.
    os.environ["HUD_TOKEN"] = "   "
    try:
        check("an all-whitespace HUD_TOKEN falls through instead of disabling auth",
              bool(resolve()))
    finally:
        os.environ.pop("HUD_TOKEN", None)


def t_it_degrades_rather_than_dying():
    """A read-only config directory should cost the phone its pairing, not
    cost the owner their assistant."""
    d = Path(tempfile.mkdtemp()) / "cfg"
    d.mkdir(parents=True)
    resolve, path = lift(d)
    os.environ.pop("HUD_TOKEN", None)

    # The write is made to fail directly rather than by chmod-ing the
    # directory. Two reasons: root ignores directory permissions, so the chmod
    # version passes for the wrong reason whenever the suite runs as root, and
    # Windows does not honour the mode bits at all - which is the platform this
    # actually ships on.
    real = Path.write_text
    def refuse(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))
    Path.write_text = refuse
    try:
        out = resolve()
        check("an unwritable config dir returns empty rather than raising",
              out == "", repr(out))
    except Exception as exc:
        check("an unwritable config dir returns empty rather than raising",
              False, f"raised {type(exc).__name__}: {exc}")
    finally:
        Path.write_text = real
    check("and nothing was left behind by the failed write",
          not list(d.glob("*")), [q.name for q in d.glob("*")])

    # A junk file is not a token.
    path.write_text("   \n", encoding="utf-8")
    out = resolve()
    check("a blank token file is replaced, not returned", out.strip() != "", repr(out))


def t_the_banner_and_the_refusal():
    """CONTROL on the wiring, since _resolve_token alone proves nothing."""
    src = SRC.read_text(encoding="utf-8")
    check("HUD_TOKEN is the resolved value, not a bare env read",
          "HUD_TOKEN = _resolve_token()" in src)
    check("boot says where the token is", "token      {TOKEN_FILE}" in src
          or "TOKEN_FILE}" in src)
    check("the banner prints the PATH, never the token itself",
          "{HUD_TOKEN}" not in src.split("def main")[-1],
          "a token echoed to a terminal is a token in a scrollback buffer")
    check("the refusal explains that a token is normally made for you",
          "A token is normally made for you" in src,
          "reaching that message now means the file could not be written")


if __name__ == "__main__":
    for fn in (t_it_makes_one, t_the_environment_still_wins,
               t_it_degrades_rather_than_dying, t_the_banner_and_the_refusal):
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
