"""The token the installed jarvis_hud.py makes is kept in Credential Manager,
and no file is ever written.

History, in two steps. token-file.patch fixed "a token nobody creates is not
a default, it is a missing feature": the phone authenticates by token ALONE,
nothing had ever generated one, so it had never been pairable. But it kept
the token in ~/.openjarvis/token as plain text, which CLAUDE.md rule 3
forbids. token-store.patch keeps the same promises - made on first run, the
SAME token every restart, HUD_TOKEN still wins, a failure costs the phone its
pairing rather than the owner their assistant - with the token in Windows
Credential Manager (jarvis_token_store.py) and the old file moved in.

This runs the REAL _resolve_token from the installed jarvis_hud.py, lifted
with ast, against a scratch folder and a STAND-IN store: it must never read,
replace or delete the owner's real saved token. test_token_store.py covers
the store itself, including a live round trip on Windows.

    python3 test_token_file.py
"""
import ast, os, sys, tempfile, traceback, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
import jarvis_token_store as ts
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Store:
    """Credential Manager, in memory."""
    def __init__(self, refuse=False):
        self.value, self.refuse = None, refuse

    def read(self):
        return self.value

    def write(self, token):
        if self.refuse:
            raise ts.StoreError("saving failed (Windows error 1312)")
        self.value = token

    def delete(self):
        had, self.value = self.value is not None, None
        return had


def _function_text(name):
    """One top-level function's text, cut out by its lines rather than by
    parsing the whole file - so this also runs on a rehearsal stand-in, which
    is fragments and filler, not a module Python can parse."""
    lines = SRC.read_text(encoding="utf-8").splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith(f"def {name}(")]
    if len(starts) != 1:
        raise AssertionError(f"{name} is defined {len(starts)} times at module level, not once")
    out = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if line and not line[0].isspace():
            break
        out.append(line)
    return "\n".join(out) + "\n"


def run(config_dir, store, environ=None):
    """The installed _resolve_token, run once. Returns (token, banner)."""
    ns = {"os": os, "Path": Path, "CONFIG_DIR": config_dir,
          "TOKEN_FILE": config_dir / "token", "TOKEN_BANNER": []}
    exec(compile(ast.parse(_function_text("_resolve_token")), "<lifted>", "exec"), ns)
    stand_in = types.SimpleNamespace(
        resolve=lambda token_file: ts.resolve(token_file, store=store, environ=environ or {}))
    saved = sys.modules.get("jarvis_token_store")
    sys.modules["jarvis_token_store"] = stand_in
    try:
        return ns["_resolve_token"](), ns["TOKEN_BANNER"]
    finally:
        sys.modules["jarvis_token_store"] = saved


def scratch():
    d = Path(tempfile.mkdtemp()) / "cfg"
    d.mkdir(parents=True)
    return d


def t_it_makes_one_and_keeps_it():
    d, store = scratch(), Store()
    tok, banner = run(d, store)
    check("a token is produced on first run", bool(tok), repr(tok))
    check("it is long enough to be worth having", len(tok) >= 32, f"{len(tok)} chars")
    check("it is kept in Credential Manager", store.value == tok)
    check("and NO file is written", not list(d.iterdir()), [p.name for p in d.iterdir()])
    check("the banner says where, never what",
          "Credential Manager" in "\n".join(banner) and tok not in "\n".join(banner))
    again, _ = run(d, store)
    check("a second start returns the SAME token", again == tok,
          "regenerating on every boot would unpair the phone on every boot")


def t_the_old_file_is_moved_in():
    d, store = scratch(), Store()
    (d / "token").write_text("paired-long-ago\n", encoding="utf-8")
    tok, _ = run(d, store)
    check("the old file's token is kept, so the phone stays paired", tok == "paired-long-ago")
    check("and the plain-text file is gone", not (d / "token").exists())


def t_the_environment_still_wins():
    d, store = scratch(), Store()
    tok, _ = run(d, store, {"HUD_TOKEN": "  set-by-hand  "})
    check("HUD_TOKEN beats the store", tok == "set-by-hand")
    check("and nothing is stored or written when it is set",
          store.value is None and not list(d.iterdir()))
    tok, _ = run(d, store, {"HUD_TOKEN": "   "})
    check("an all-whitespace HUD_TOKEN falls through instead of disabling auth", bool(tok))


def t_a_refusal_writes_nothing():
    d = scratch()
    tok, banner = run(d, Store(refuse=True))
    check("Credential Manager refusing still gives a token for this run", bool(tok))
    check("and writes nothing to disk", not list(d.iterdir()), [p.name for p in d.iterdir()])
    check("and the banner says it will not survive a restart",
          "pairing again" in "\n".join(banner), banner)


def t_the_banner_and_the_refusal():
    """CONTROL on the wiring, since _resolve_token alone proves nothing."""
    src = SRC.read_text(encoding="utf-8")
    check("HUD_TOKEN is the resolved value, not a bare env read",
          "HUD_TOKEN = _resolve_token()" in src)
    check("the banner prints TOKEN_BANNER", "for line in TOKEN_BANNER:" in src)
    check("the banner never prints the token itself",
          "{HUD_TOKEN}" not in src.split("def main")[-1],
          "a token echoed to a terminal is a token in a scrollback buffer")
    check("nothing in jarvis_hud.py writes TOKEN_FILE any more",
          "tmp.replace(TOKEN_FILE)" not in src and "TOKEN_FILE.write_text" not in src)
    check("jarvis_token_store.py is beside it", (BACKEND / "jarvis_token_store.py").is_file(),
          "run apply-patches.ps1 again to copy it in")


if __name__ == "__main__":
    if missing("jarvis_hud.py"):
        print("skip  " + explain())
        sys.exit(0)
    for fn in (t_it_makes_one_and_keeps_it, t_the_old_file_is_moved_in,
               t_the_environment_still_wins, t_a_refusal_writes_nothing,
               t_the_banner_and_the_refusal):
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
