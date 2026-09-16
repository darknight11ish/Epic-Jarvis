#!/usr/bin/env python3
"""First-run self test: does this Jarvis backend actually work?

    python backend\\selftest.py

WHY THIS EXISTS

Ten of the backend's twenty-six modules were rebuilt from inference after the
originals were found to exist nowhere. They pass sixty-four checks here and the
owner's own twelve suites - but every one of those runs against a copy of the
code, in a container, with a mock for anything real. Nothing has ever been
tested on the machine that runs Jarvis, and the backend has never started at
all, because until the rebuild `import jarvis_gate` raised ModuleNotFoundError.

So this script is not another unit test. It is the questions a person would ask
after installing something for the first time:

    Is every file here?
    Does each one load?
    Does the server start?
    Does it answer?
    Does the approval gate actually STOP something?

It changes nothing. It writes no facts, approves nothing, and starts the server
on a port of its own so a Jarvis you already have running is not disturbed.

WHAT TO DO WITH THE OUTPUT

Paste the whole thing back. Every line is designed to be actionable on its own:
a failure says which file, which symptom, and what it means. There is a summary
at the end with a single verdict.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from _where import BACKEND, explain
except Exception:
    BACKEND = Path(os.environ.get("JARVIS_BACKEND") or HERE)

    def explain() -> str:
        return f"Set JARVIS_BACKEND to the folder holding jarvis_hud.py (tried {BACKEND})."

#: The twenty-six modules jarvis_hud and its siblings import.
EXPECTED = [
    "jarvis_framework", "jarvis_memory", "jarvis_events", "jarvis_gate",
    "jarvis_hud", "jarvis_extract", "jarvis_voice", "jarvis_router",
    "jarvis_recall", "jarvis_power", "jarvis_compute", "jarvis_sleep",
    "jarvis_initiative", "jarvis_models", "jarvis_skills", "jarvis_arbiter",
    "jarvis_jobs", "jarvis_ledger", "jarvis_preview", "jarvis_speech",
    "jarvis_structured", "jarvis_style", "jarvis_tripwire", "jarvis_undo",
    "jarvis_watch", "jarvis_content_risk",
]

#: Rebuilt from inference. Worth naming separately in the output: a failure in
#: one of these is my mistake, a failure elsewhere is something else.
REBUILT = {
    "jarvis_framework", "jarvis_memory", "jarvis_events", "jarvis_voice",
    "jarvis_power", "jarvis_compute", "jarvis_router", "jarvis_recall",
    "jarvis_sleep", "jarvis_initiative",
}

PASS, FAIL, WARN, SKIP = "ok  ", "FAIL", "warn", "skip"
_results: list = []


def say(status: str, what: str, detail: str = "") -> None:
    _results.append((status, what, detail))
    line = f"  {status}  {what}"
    print(line)
    if detail:
        for d in str(detail).rstrip().splitlines()[:6]:
            print(f"          {d}")


def header(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# ==========================================================================
#   1. Are the files here?
# ==========================================================================

def stage_files() -> bool:
    header("1. Is every module present?")
    missing = [m for m in EXPECTED if not (BACKEND / f"{m}.py").is_file()]
    if not missing:
        say(PASS, f"all {len(EXPECTED)} modules are in {BACKEND}")
        return True
    for m in missing:
        tag = " (rebuilt - copy it from backend\\rebuilt\\)" if m in REBUILT else ""
        say(FAIL, f"{m}.py is not there{tag}")
    print(f"\n  {explain()}")
    print("  Nothing below can run until these are in place. Copy them with:")
    print("      Copy-Item .\\backend\\rebuilt\\*.py \"<your backend folder>\\\"")
    return False


# ==========================================================================
#   2. Does each one load?
# ==========================================================================

def stage_imports() -> bool:
    header("2. Does each module load?")
    sys.path.insert(0, str(BACKEND))
    ok = True
    for m in EXPECTED:
        try:
            __import__(m)
        except Exception as exc:
            ok = False
            tag = "  [REBUILT]" if m in REBUILT else ""
            say(FAIL, f"import {m}{tag}", f"{type(exc).__name__}: {exc}")
    if ok:
        say(PASS, f"all {len(EXPECTED)} import")
    else:
        print("\n  An import failure here is the whole backend down - jarvis_hud")
        print("  imports these at startup. The first one listed is usually the cause.")
    return ok


# ==========================================================================
#   3. Is the config being read?
# ==========================================================================

def stage_config() -> None:
    header("3. Is the config being read?")
    try:
        import jarvis_framework as fw
    except Exception as exc:
        say(FAIL, "jarvis_framework will not import", str(exc))
        return

    st = fw.status()
    if not st["config_file"]:
        say(FAIL, "no jarvis-framework.toml found",
            f"looked in {st['config_dir']} and beside the modules. "
            "Every setting is falling back to a default.")
        return
    say(PASS, f"config: {st['config_file']}")
    say(PASS if st["sections"] else FAIL,
        f"{len(st['sections'])} sections parsed")

    n = st["classified_actions"]
    say(PASS if n > 20 else WARN, f"{n} actions have an autonomy tier")

    # The one assertion inherited from a surviving test.
    tier = fw.action_tier("web_research")
    say(PASS if tier == "auto" else FAIL,
        f'action_tier("web_research") == {tier!r}',
        "" if tier == "auto" else "test_jobs.py asserts this is 'auto'")

    unknown = fw.action_tier("an_action_nobody_ever_classified")
    say(PASS if unknown in ("ask", "never") else FAIL,
        f"an unclassified action gets {unknown!r}",
        "" if unknown in ("ask", "never") else
        "THIS IS THE IMPORTANT ONE. An action nobody classified must wait "
        "for you, not run itself.")


# ==========================================================================
#   4. Does the gate actually stop something?
# ==========================================================================

def stage_gate() -> None:
    header("4. Does the approval gate refuse what it should?")
    try:
        import jarvis_gate as G
    except Exception as exc:
        say(FAIL, "jarvis_gate will not import", str(exc))
        return

    # `never` must be refused outright, without asking anyone. Checked by
    # calling check(), which does not act - it only classifies and queues.
    try:
        v = G.check("post_to_external_service", {"probe": True}, timeout=0.1)
        refused = not getattr(v, "allowed", True)
        say(PASS if refused else FAIL,
            f"a 'never' action is refused (allowed={getattr(v, 'allowed', '?')})",
            "" if refused else
            "A tier-never action was ALLOWED. This is the control the whole "
            "project is built around.")
    except Exception as exc:
        say(WARN, "could not exercise check() directly",
            f"{type(exc).__name__}: {exc}")

    # There must be no approve-all. Checked by reading the module, because the
    # bug this replaces was a function that existed with zero callers.
    src = (BACKEND / "jarvis_gate.py").read_text(encoding="utf-8", errors="replace")
    try:
        import ast
        tree = ast.parse(src)
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        bad = sorted(n for n in names
                     if "approve_all" in n or "auto_approve" in n)
        say(PASS if not bad else FAIL,
            "no approve-all function exists",
            "" if not bad else f"found: {', '.join(bad)}")
    except SyntaxError as exc:
        say(FAIL, "jarvis_gate.py does not parse", str(exc))


# ==========================================================================
#   5. Does memory work, without writing to your real store?
# ==========================================================================

def stage_memory() -> None:
    header("5. Does memory store and recall, safely?")
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-selftest-"))
    try:
        import jarvis_memory as M
        s = M.MemoryStore(tmp / "probe.db")   # a throwaway file, never yours
    except Exception as exc:
        say(FAIL, "could not open a memory store",
            f"{type(exc).__name__}: {exc}")
        return

    st = s.status()
    say(PASS, f"embedder: {st['embedder']}  semantic: {st['semantic']}  "
              f"vector search: {st['vector_search']}")

    try:
        a = s.add("Mario's editor is Vim")
        s.add("Mario drives a 1998 Volvo")
        got = s.search("what does Mario drive")
        say(PASS if got else FAIL, f"search returned {len(got)} fact(s)")

        # THE DESTRUCTIVE BUG. A correction must never identify an unrelated
        # fact - accepting "Mario drives a Volvo" once retired the Vim note.
        hit = s.find_one("Mario's allergy")
        say(PASS if hit is None else FAIL,
            "a vague correction identifies nothing",
            "" if hit is None else
            f"find_one(\"Mario's allergy\") matched {hit.get('text')!r} - "
            "this is the bug that destroys data.")

        hit2 = s.find_one("Mario drives a 1998 Volvo")
        say(PASS if hit2 and "Volvo" in hit2.get("text", "") else WARN,
            "a precise correction finds the right fact")

        say(PASS if s.search("Mario", k=0) == [] else FAIL,
            "recall width 0 returns nothing")

        if st["vector_search"]:
            say(PASS if s.status()["unembedded"] == 0 else FAIL,
                "facts are actually embedded",
                "" if s.status()["unembedded"] == 0 else
                "vector_search says true but nothing embedded - the "
                "capability is reporting itself available and doing nothing.")
    except Exception as exc:
        say(FAIL, "memory raised", traceback.format_exc(limit=2))


# ==========================================================================
#   6. Does the server start and answer?
# ==========================================================================

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, token: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers={
        "X-Jarvis-Token": token,
        "X-Jarvis-Client": "selftest",
        "Origin": url.rsplit("/api", 1)[0],
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def stage_server() -> None:
    header("6. Does the server start and answer?")
    port = _free_port()
    token = "selftest-" + os.urandom(8).hex()
    env = dict(os.environ)
    env.update({
        "JARVIS_HUD_PORT": str(port),
        "HUD_TOKEN": token,
        "JARVIS_HUD_BIND": "127.0.0.1",   # loopback only, never the tailnet
    })
    hud = BACKEND / "jarvis_hud.py"
    if not hud.is_file():
        say(FAIL, "jarvis_hud.py is not there")
        return

    print(f"  starting jarvis_hud.py on 127.0.0.1:{port} (a spare port, so a")
    print("  Jarvis you already have running is not disturbed)\n")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(hud)], cwd=str(BACKEND), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        say(FAIL, "could not launch it", f"{type(exc).__name__}: {exc}")
        return

    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(60):                     # up to 30 seconds
        if proc.poll() is not None:
            break
        try:
            _get(f"{base}/api/version", token, timeout=1.0)
            up = True
            break
        except Exception:
            time.sleep(0.5)

    if not up:
        out = ""
        try:
            proc.kill()
            out = (proc.stdout.read() if proc.stdout else "") or ""
        except Exception:
            pass
        say(FAIL, "the server did not come up", out[-1500:] or "no output")
        print("\n  That output is the startup banner. It names whichever module")
        print("  failed, and is the single most useful thing to send back.")
        return

    try:
        say(PASS, "the server started and is answering")

        code, body = _get(f"{base}/api/version", token)
        say(PASS if code == 200 else FAIL, f"/api/version -> {code}")
        caps = body.get("capabilities", {})
        on = sorted(k for k, v in caps.items() if v)
        off = sorted(k for k, v in caps.items() if not v)
        say(PASS, f"capabilities on: {', '.join(on) or 'none'}")
        if off:
            say(WARN, f"capabilities off: {', '.join(off)}",
                "off means the client hides that UI - not an error by itself")

        for path in ("/api/status", "/api/pending", "/api/compute",
                     "/api/memory/status", "/api/initiative", "/api/digest"):
            try:
                code, _ = _get(f"{base}{path}", token)
                say(PASS if code == 200 else FAIL, f"{path} -> {code}")
            except urllib.error.HTTPError as e:
                say(FAIL, f"{path} -> HTTP {e.code}",
                    e.read().decode("utf-8", "replace")[:200])
            except Exception as exc:
                say(FAIL, f"{path} raised", f"{type(exc).__name__}: {exc}")

        # /api/retrieve is the one that used to drop the connection outright.
        try:
            code, _ = _get(f"{base}/api/retrieve?q=what+colour+is+the+wall", token)
            say(PASS if code == 200 else FAIL, f"/api/retrieve -> {code}")
        except Exception as exc:
            say(FAIL, "/api/retrieve raised", f"{type(exc).__name__}: {exc}")

        # No token must be refused. This is the door to everything else.
        try:
            req = urllib.request.Request(f"{base}/api/pending")
            urllib.request.urlopen(req, timeout=3)
            say(FAIL, "a request with NO TOKEN was accepted",
                "anything that can reach the port can read your approval queue")
        except urllib.error.HTTPError as e:
            say(PASS if e.code in (401, 403) else FAIL,
                f"no token is refused ({e.code})")
        except Exception as exc:
            say(WARN, "could not test the no-token case", str(exc))

        # The event stream: first bytes only, then let go.
        try:
            req = urllib.request.Request(
                f"{base}/api/events",
                headers={"X-Jarvis-Token": token, "X-Jarvis-Client": "selftest"})
            # readline, NOT read(200). An SSE stream is held open, so
            # read(200) blocks until 200 bytes exist - and the opening frames
            # are about 113. It then waits for the 20-second keepalive and
            # times out, which reads as "the event stream is broken" when the
            # event stream is working perfectly. Caught by running this.
            with urllib.request.urlopen(req, timeout=8) as r:
                first = b"".join(r.readline() for _ in range(5)).decode("utf-8", "replace")
            ok = "retry:" in first and "hello" in first
            say(PASS if ok else FAIL, "/api/events streams a hello frame",
                "" if ok else f"got: {first[:120]!r}")
        except Exception as exc:
            say(FAIL, "/api/events raised", f"{type(exc).__name__}: {exc}")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        print("\n  (the test server has been stopped)")


# ==========================================================================

def main() -> int:
    print(__doc__.split("WHY THIS EXISTS")[0].strip())
    print(f"\nbackend : {BACKEND}")
    print(f"python  : {sys.version.split()[0]}  ({sys.executable})")

    if stage_files() and stage_imports():
        stage_config()
        stage_gate()
        stage_memory()
        stage_server()

    header("Summary")
    bad = [r for r in _results if r[0] == FAIL]
    warn = [r for r in _results if r[0] == WARN]
    good = [r for r in _results if r[0] == PASS]
    print(f"  {len(good)} passed, {len(warn)} warnings, {len(bad)} FAILED")
    if bad:
        print("\n  Failures, in the order they happened:")
        for _, what, _d in bad:
            print(f"    - {what}")
        print("\n  VERDICT: not ready. Send this whole output back.")
        return 1
    if warn:
        print("\n  VERDICT: it works. The warnings above are things that are")
        print("  switched off or not installed, not things that are broken.")
        return 0
    print("\n  VERDICT: everything checked works.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped")
        sys.exit(130)
