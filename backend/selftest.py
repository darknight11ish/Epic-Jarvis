#!/usr/bin/env python3
"""First-run self test: does this Jarvis backend actually work?

    python backend\\selftest.py
    python backend\\selftest.py --preflight      the Jarvis that is RUNNING now

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
    Is the model downloaded, and is it on the graphics card?

It changes nothing. It writes no facts, approves nothing, and starts the server
on a port of its own so a Jarvis you already have running is not disturbed.

WHAT TO DO WITH THE OUTPUT

Paste the whole thing back. Every line is designed to be actionable on its own:
a failure says which file, which symptom, and what it means. There is a summary
at the end with a single verdict.

TWO MODES

With no option it is the first-run check above: it starts its own copy of
the backend on a spare port, asks it questions, and stops it again.

`--preflight` (added 2026-09-25, the owner's decision after the "Build Your
Own Jarvis" prompt pack) asks the Jarvis that is already running - the one
the apps talk to - every question a real chain depends on: is it up, does it
accept the token, is the model there and answering, is every patch and
module really the one in this repository, is the settings file kept off the
web, is the gate on, does the scheduler run, does the event stream deliver.
One line per check, PASS / FAIL / WARN, and "N pass, N fail, N warn" at the
end; exit code 1 on any FAIL. Read-only - see "--preflight" further down.
`--with-reads` also reads the calendar and email once; `--with-chat` sends
the one test question through Jarvis's chat even when tools are on.

It is a separate mode, not the default, because the two answer different
questions: a fresh copy can pass everything while the long-running one is
stuck or running an older file - and the first-run check must still work
before Jarvis has ever started.

ADD ONE CHECK PER REAL INCIDENT. When something breaks for real, add the
preflight check that would have caught it: one function with
@preflight_check, and a case in test_selftest_preflight.py.
"""
from __future__ import annotations

import json
import os
import re
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
    # First, and whether or not the gate imports: a way round the gate.
    say(*openjarvis_autoapprove())
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


#: How OpenJarvis switches its own asking off: a confirm callback that says
#: yes to everything. The same pattern the extraction research's PowerShell
#: line uses; against OpenJarvis e86c582 it finds all seven places.
_AUTO_APPROVE = r"confirm_callback\W{0,3}\s*=\s*lambda[^:]*:\s*True"


def openjarvis_autoapprove(package_dir=None) -> tuple:
    """(status, what, detail): does the installed OpenJarvis approve tools by
    itself anywhere? (Gate fix 4a, docs/EXTRACTION-RESEARCH-2026-09-23.md.)

    Jarvis's backend was built on OpenJarvis, and current OpenJarvis has
    seven places - four server routes, three commands - that hand a tool
    call a callback answering "yes" with nobody asked. A tool call through
    one of those never reaches jarvis_gate. Whether this backend ever calls
    them cannot be told from here, so a hit is reported for a person to look
    at, never guessed away. Reads files only; imports nothing from OpenJarvis.
    """
    import importlib.util
    import re
    if package_dir is None:
        try:
            spec = importlib.util.find_spec("openjarvis")
        except Exception:
            spec = None
        places = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
        if not places:
            return (SKIP, "OpenJarvis is not installed for this Python, so it cannot "
                          "approve anything by itself")
        package_dir = places[0]
    root = Path(package_dir)
    pattern = re.compile(_AUTO_APPROVE)
    hits = []
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(root)}:{n}")
    if not hits:
        return (PASS, "OpenJarvis has no place that approves tools by itself")
    shown = ", ".join(hits[:10]) + (f" and {len(hits) - 10} more" if len(hits) > 10 else "")
    return (FAIL, f"OpenJarvis approves tools by itself in {len(hits)} place(s)",
            f"In {root}: {shown}. A tool call made through one of these never "
            "reaches Jarvis's approval gate. This does not prove Jarvis uses "
            "them - send this output back so that can be checked. Until then, "
            "use Jarvis through its own apps, not OpenJarvis's own commands "
            "(such as `jarvis ask`).")


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
#   7. Is the model ready, and on the graphics card?  (the "doctor" step)
# ==========================================================================
#
# The self-test used to say nothing about Ollama at all, so the most common
# way Jarvis goes wrong - part of the model spilling off the graphics card
# onto the CPU, which makes every answer several times slower and produces
# no error anywhere - could pass every check above.
#
# READ-ONLY, AND IT LOADS NOTHING. Three GET requests, all to Ollama on this
# PC: /api/version (is it answering), /api/tags (what is downloaded) and
# /api/ps (what is in memory right now). None of them loads a model. So when
# no model is loaded, "is it on the graphics card?" cannot be answered without
# loading one, and the answer is "skipped", not a guess. `doctor()` takes its
# fetcher as a parameter so test_selftest_doctor.py can prove exactly which
# requests it makes.

OLLAMA_PATHS = ("/api/version", "/api/tags", "/api/ps")


def _ollama_base() -> str:
    """Where Ollama is: OLLAMA_URL, else OLLAMA_HOST, else jarvis_models'
    own setting, else the default port on this machine."""
    for name in ("OLLAMA_URL", "OLLAMA_HOST"):
        v = (os.environ.get(name) or "").strip()
        if v:
            if "://" not in v:
                v = "http://" + v
            # 0.0.0.0 tells a server to listen everywhere; it is not an
            # address anything connects TO. This machine is.
            return v.rstrip("/").replace("://0.0.0.0", "://127.0.0.1")
    try:
        sys.path.insert(0, str(BACKEND))
        import jarvis_models as MM
        v = str(getattr(MM, "OLLAMA", "") or "").strip()
        if v:
            return v.rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:11434"


def _is_loopback(url: str) -> bool:
    import ipaddress
    import urllib.parse
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _configured_model():
    """The model Jarvis is set to use, from jarvis_models.current_model() -
    the same call the Models screen makes. None if it cannot be told."""
    try:
        sys.path.insert(0, str(BACKEND))
        import jarvis_models as MM
        cur = MM.current_model()
    except Exception:
        cur = None
    if isinstance(cur, dict):
        cur = cur.get("ref") or cur.get("name") or cur.get("model")
    if isinstance(cur, str) and cur.strip():
        return cur.strip()
    env = (os.environ.get("JARVIS_MODEL") or "").strip()
    return env or None


def _same_model(a: str, b: str) -> bool:
    """`qwen3` and `qwen3:latest` are the same model to Ollama."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False

    def bare(s: str) -> str:
        return s[:-7] if s.endswith(":latest") else s
    return a == b or bare(a) == bare(b)


def _get_json(url: str, timeout: float = 4.0):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def doctor(fetch=None, base=None, model=None, env=None) -> list:
    """The checks, as (status, what, detail) rows. Never raises.

    `fetch(url)` returns parsed JSON or raises. `model` is the configured
    model's name, or None when it could not be told.
    """
    fetch = fetch or _get_json
    base = (base or _ollama_base()).rstrip("/")
    env = os.environ if env is None else env
    rows = []

    if not _is_loopback(base):
        rows.append((WARN, f"Ollama is set to {base}, which is not this PC",
                     "The self-test only checks Ollama on this PC, so nothing was "
                     "sent there. Jarvis's rule is that the model runs here; if "
                     "that address is deliberate, check it by hand."))
        return rows

    try:
        ver = fetch(f"{base}/api/version")
        v = ver.get("version") if isinstance(ver, dict) else None
        rows.append((PASS, f"Ollama is answering at {base}"
                     + (f" (version {v})" if v else "")))
    except Exception as exc:
        rows.append((FAIL, f"Ollama is not answering at {base}",
                     f"{type(exc).__name__}: {exc}\n"
                     "Jarvis cannot answer anything without it. Start the Ollama "
                     "app from the Start menu, or run: ollama serve"))
        rows.append((SKIP, "the model checks, because Ollama is not answering"))
        return rows

    if not model:
        rows.append((SKIP, "could not tell which model Jarvis is set to use",
                     "jarvis_models.current_model() gave no name and JARVIS_MODEL "
                     "is not set, so there is nothing to check for."))
        return rows

    names = None
    try:
        tags = fetch(f"{base}/api/tags")
        names = [str(m.get("name") or m.get("model") or "")
                 for m in (tags or {}).get("models") or [] if isinstance(m, dict)]
    except Exception as exc:
        rows.append((WARN, "could not list the downloaded models",
                     f"{type(exc).__name__}: {exc}"))
    if names is not None:
        if any(_same_model(n, model) for n in names):
            rows.append((PASS, f"the configured model, {model}, is downloaded"))
        else:
            fix = ("ollama create jarvis-primary -f backend\\jarvis-primary.Modelfile"
                   if model.split(":")[0] == "jarvis-primary" else f"ollama pull {model}")
            rows.append((FAIL, f"the configured model, {model}, is not downloaded",
                         f"Downloaded here: {', '.join(names) or 'nothing'}.\n"
                         f"Get it with: {fix}"))

    try:
        ps = fetch(f"{base}/api/ps")
        running = [m for m in (ps or {}).get("models") or [] if isinstance(m, dict)]
    except Exception as exc:
        rows.append((WARN, "could not ask Ollama what is loaded",
                     f"{type(exc).__name__}: {exc}"))
        return rows

    mine = [m for m in running
            if _same_model(str(m.get("name") or m.get("model") or ""), model)]
    if not running:
        rows.append((SKIP, "whether the model fits on the graphics card",
                     "No model is loaded right now, and this test loads nothing. "
                     "Ask Jarvis anything, then run this again to check it."))
        return rows
    if not mine:
        others = ", ".join(str(m.get("name") or m.get("model")) for m in running)
        rows.append((WARN, f"{model} is not the model loaded right now ({others} is)",
                     "So whether it fits on the graphics card was not checked. "
                     "Something other than Jarvis may be using Ollama."))
        return rows

    m = mine[0]
    total = int(m.get("size") or 0)
    vram = int(m.get("size_vram") or 0)
    # A zero total happens while a model is still loading.
    pct = 100 if total <= 0 else max(0, min(100, round(vram * 100 / total)))
    if pct >= 99:
        rows.append((PASS, f"{model} is fully on the graphics card"))
    elif pct <= 1:
        rows.append((FAIL, f"{model} is running on the CPU, not the graphics card",
                     "Every answer will be several times slower, and nothing "
                     "else says so. Usually another program is holding video "
                     "memory, or the model is too big for the card. Close games "
                     "and video tools, restart Ollama, and run this again."))
    else:
        rows.append((FAIL, f"only {pct}% of {model} is on the graphics card",
                     "The rest is on the CPU, which makes every answer slower. "
                     "Another program may be holding video memory, or the "
                     "context is too big for the card (docs/MODEL-TOPOLOGY.md)."))

    # The cache-size checks. WARNINGS ONLY, never a failure: the right numbers
    # depend on the card and the model, and a smaller cache means a shorter
    # memory of the conversation, not something broken.
    ctx = m.get("context_length")
    if isinstance(ctx, int) and not isinstance(ctx, bool) and 0 < ctx < 8192:
        rows.append((WARN, f"Ollama gave {model} only {ctx} tokens of context",
                     "jarvis-primary.Modelfile asks for 16384. Ollama falls back "
                     "to 4096 when the bigger size would not fit, and long "
                     "conversations then lose their beginning. See "
                     "docs/MODEL-TOPOLOGY.md."))
    kv = (env.get("OLLAMA_KV_CACHE_TYPE") or "").strip()
    if kv != "q8_0":
        rows.append((WARN, "OLLAMA_KV_CACHE_TYPE is "
                     + (repr(kv) if kv else "not set") + " in this window, not 'q8_0'",
                     "If Ollama was started with the same settings, its memory "
                     "cache is the larger kind, which may not fit on the card. "
                     "This only sees this window's settings, not Ollama's own. "
                     "docs/MODEL-TOPOLOGY.md, 'Setup', says how to set it."))
    return rows


def stage_ollama() -> None:
    header("7. Is the model ready, and on the graphics card?")
    print("  (read-only: asks Ollama three questions and loads nothing)\n")
    for row in doctor(model=_configured_model()):
        say(row[0], row[1], row[2] if len(row) > 2 else "")


# ==========================================================================
#   --preflight: the Jarvis that is RUNNING, every live chain
# ==========================================================================
#
# Everything above tests a fresh copy of the backend, started on a spare
# port and stopped again. That answers "does it work at all?". It cannot
# answer "does the Jarvis I am using right now work?" - a long-running
# server can be stuck, running an older copy of a file, or missing a patch
# while a fresh one passes everything (the prompt pack's "Field Proof":
# read it from the RUNNING server).
#
# So `--preflight` asks the running Jarvis itself, on 127.0.0.1, with the
# pairing token, and prints one line per check: PASS, FAIL or WARN, one
# plain sentence, and the fix. It ends "N pass, N fail, N warn" and exits
# with 1 when anything failed.
#
# READ-ONLY. It never approves or denies anything, never sends an email,
# never unloads a model, and never changes a setting. It searches the web
# only when web search is switched on and a provider is chosen, and then
# only through the Test search button's own route (one search for the word
# "wikipedia"). It asks the model one fixed question ("Reply with the single
# word: ready"), which may load the model - the same as asking Jarvis
# anything. It sends that question through Jarvis's own chat only as a
# temporary chat (nothing remembered, nothing kept) and only when no tool is
# switched on - otherwise the model could choose one; `--with-chat` sends it
# anyway. It reads the calendar and email only with `--with-reads`.
#
# ADD ONE CHECK PER REAL INCIDENT. When something breaks for real, write the
# check that would have caught it: one function, decorated with
# @preflight_check, returning rows. It runs in the order it is written.
# Everything it touches goes through `live` (a Live), so its test can hand in
# stand-ins and needs no network (test_selftest_preflight.py).

#: The checks, in order: (key, title, function). Filled by @preflight_check.
PREFLIGHT: list = []


def preflight_check(key: str, title: str):
    """Register one preflight check. `fn(live)` returns a list of
    (status, what, detail) rows; `what` is one plain sentence and `detail`
    says what to do about it."""
    def deco(fn):
        if any(k == key for k, _t, _f in PREFLIGHT):
            raise ValueError(f"two preflight checks are called {key!r}")
        PREFLIGHT.append((key, title, fn))
        return fn
    return deco


#: The port jarvis_hud.py listens on unless JARVIS_HUD_PORT says otherwise
#: (the desktop's DEFAULT_BASE, commands.rs, says the same).
DEFAULT_PORT = 4719

#: The API version both apps speak (jarvis_events.API_VERSION; the desktop's
#: handshake and the phone read it).
APPS_SPEAK_API = 1

#: The one question the preflight asks the model. About nothing.
READY_QUESTION = "Reply with the single word: ready"

#: Paths that must never serve a file. Each is asked with no token and with
#: the token; a 200 that holds the file's own text is a FAIL.
PRIVATE_PROBES = (
    "/jarvis-framework.toml", "/../jarvis-framework.toml",
    "/%2e%2e/jarvis-framework.toml", "/..%2fjarvis-framework.toml",
    "/static/../jarvis-framework.toml", "/config/jarvis-framework.toml",
    "/.openjarvis/jarvis-framework.toml", "/jarvis_hud.py", "/jarvis_gate.py",
    "/token", "/.env", "/approvals.db", "/memory.db", "/web-search.json",
    "/backend.log",
)

#: Where the desktop app keeps its logs on Windows (Tauri's app_log_dir for
#: the identifier in tauri.conf.json).
DESKTOP_ID = "com.jarvis.desktop"


def _no_proxy_open(req, timeout):
    # Straight to 127.0.0.1, never through a proxy a variable points at.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def _http(method: str, url: str, headers: dict, body, timeout: float) -> tuple:
    """(status, headers with lower-case names, body bytes). A refused
    connection raises; an HTTP error status is an answer, not a raise."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _no_proxy_open(req, timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
        except Exception:
            raw = b""
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, raw


def _stream_head(url: str, headers: dict, timeout: float) -> str:
    """The first five lines of an event stream, then let go (readline, not
    read(n) - see stage_server)."""
    req = urllib.request.Request(url, headers=headers)
    with _no_proxy_open(req, timeout) as r:
        return b"".join(r.readline() for _ in range(5)).decode("utf-8", "replace")


def _token_sources(env, store_for=None) -> list:
    """[(where, token)] - every place the running backend's token may be,
    in the order the backend itself prefers them. Never printed: only
    `where` ever reaches the output."""
    out = []
    t = (env.get("HUD_TOKEN") or "").strip()
    if t:
        out.append(("HUD_TOKEN in this window", t))
    try:
        import jarvis_token_store as TS
    except Exception:
        return out
    make = store_for or (lambda target: TS.WindowsStore(target))
    for target, where in ((TS.TARGET, "Windows Credential Manager (the backend's own)"),
                          (TS.DESKTOP_TARGET, "Windows Credential Manager (typed into the "
                                              "desktop app's Settings)")):
        try:
            t = make(target).read()
        except Exception:
            t = None
        if t:
            out.append((where, t))
    try:
        old = Path(os.path.expanduser("~")) / ".openjarvis" / "token"
        t, _problem = TS._read_file(old)
        if t:
            out.append(("the old ~/.openjarvis/token file", t))
    except Exception:
        pass
    return out


def _json(raw):
    try:
        return json.loads((raw or b"").decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return None


class Live:
    """Everything a preflight check may touch, in one place, so a test can
    hand in stand-ins: the HTTP calls, the event stream, Ollama, the token
    sources, the folders, and the window's environment."""

    def __init__(self, *, port=None, http=None, stream_head=None, ollama=None,
                 ollama_post=None, ollama_base=None, tokens=None, backend=None, repo=None, env=None, with_reads=False,
                 with_chat=False, log_dir=None, token_store=None, reads=None):
        self.env = os.environ if env is None else env
        p = port or (self.env.get("JARVIS_HUD_PORT") or "").strip() or DEFAULT_PORT
        try:
            self.port = int(p)
        except ValueError:
            self.port = DEFAULT_PORT
        # 127.0.0.1 only: the token is sent, and this PC is the one place it
        # belongs. A backend bound to a Tailscale address still answers here
        # (loopback-too.patch).
        self.base = f"http://127.0.0.1:{self.port}"
        self.http = http or _http
        self.stream_head = stream_head or _stream_head
        self.ollama = ollama            # doctor()'s fetch, or None for the real one
        self.ollama_post = ollama_post  # (url, body) -> parsed JSON, or None for the real one
        self.ollama_base = ollama_base  # None: worked out as doctor() does
        self._tokens = tokens           # [(where, token)] or None: look them up
        self.backend = Path(backend) if backend is not None else BACKEND
        self.repo = Path(repo) if repo is not None else HERE.parent
        self.with_reads = bool(with_reads)
        self.with_chat = bool(with_chat)
        self.log_dir = log_dir
        self.token_store = token_store  # target -> store, for the Credential Manager check
        self.reads = reads              # {"email": fn, "calendar": fn} stand-ins
        self.token = None
        self.token_where = None
        self.up = False
        self.version = None
        self.status = None
        self.reach = None

    # -- tokens ----------------------------------------------------------
    def token_sources(self) -> list:
        if self._tokens is None:
            self._tokens = _token_sources(self.env)
        return list(self._tokens)

    # -- HTTP --------------------------------------------------------------
    def _headers(self, token: bool) -> dict:
        h = {"X-Jarvis-Client": "hud", "Origin": self.base}
        if token and self.token:
            h["X-Jarvis-Token"] = self.token
        return h

    def get(self, path: str, *, token=True, timeout=8.0, as_token=None) -> tuple:
        """(status, parsed JSON or None, raw bytes, headers)."""
        h = self._headers(token)
        if as_token is not None:
            h["X-Jarvis-Token"] = as_token
        code, hdrs, raw = self.http("GET", self.base + path, h, None, timeout)
        return code, _json(raw), raw, hdrs

    def post(self, path: str, body: dict, *, timeout=30.0) -> tuple:
        h = dict(self._headers(True), **{"Content-Type": "application/json"})
        code, hdrs, raw = self.http("POST", self.base + path, h,
                                    json.dumps(body).encode("utf-8"), timeout)
        return code, _json(raw), raw, hdrs

    def events_head(self, timeout=8.0) -> str:
        return self.stream_head(self.base + "/api/events", self._headers(True), timeout)

    # -- files -------------------------------------------------------------
    def desktop_logs(self):
        if self.log_dir is not None:
            return Path(self.log_dir)
        base = self.env.get("LOCALAPPDATA")
        return Path(base) / DESKTOP_ID / "logs" if base else None


def _on_path(folder: Path) -> None:
    """Put the backend folder first on sys.path, once."""
    f = str(folder)
    if f in sys.path:
        sys.path.remove(f)
    sys.path.insert(0, f)


def _needs_backend(live: Live, what: str):
    """The row for a check that cannot run because Jarvis did not answer."""
    return [(SKIP, f"{what}, because Jarvis is not answering (see the first check)")]


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _repo_version(repo: Path):
    try:
        conf = json.loads((repo / "jarvis-desktop" / "src-tauri" / "tauri.conf.json")
                          .read_text(encoding="utf-8"))
        return str(conf.get("version") or "") or None
    except Exception:
        return None


def _version_tuple(v: str) -> tuple:
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


# ---------------------------------------------------------------- checks

@preflight_check("backend", "Is Jarvis running, and does it know its token?")
def pf_backend(live: Live) -> list:
    sources = live.token_sources()
    if not sources:
        return [(FAIL, "no pairing token was found on this PC",
                 "Jarvis keeps it in Windows Credential Manager once it has started "
                 "once. Start the desktop app (it starts Jarvis), then run this again. "
                 "If you set HUD_TOKEN yourself, set it in this window too.")]
    rows = []
    refused = []
    for where, tok in sources:
        live.token = tok
        try:
            code, body, _raw, _h = live.get("/api/status")
        except Exception as exc:
            live.token = None
            return [(FAIL, f"Jarvis is not answering at {live.base}",
                     f"{type(exc).__name__}. Start the desktop app (it starts Jarvis), "
                     f"or in the backend folder run: py -3 jarvis_hud.py. If Jarvis uses "
                     f"another port, set JARVIS_HUD_PORT in this window first.")]
        if code == 200:
            live.token_where = where
            live.up = True
            live.status = body if isinstance(body, dict) else {}
            rows.append((PASS, f"Jarvis is answering at {live.base}, and accepts the "
                               f"pairing token from {where}"))
            break
        refused.append(f"{where}: {code}")
    if not live.up:
        live.token = None
        return [(FAIL, "Jarvis is running but accepts none of the pairing tokens on this PC",
                 "Tried (never shown): " + "; ".join(refused) + ". The running Jarvis "
                 "was probably started with a different HUD_TOKEN. Restart it from the "
                 "desktop app, or set HUD_TOKEN in this window to the one it uses.")]
    try:
        code, _b, _r, _h = live.get("/api/pending", token=False)
        if code in (401, 403):
            rows.append((PASS, f"a request with no token is refused ({code})"))
        else:
            rows.append((FAIL, f"a request with NO TOKEN got {code}",
                         "Anything that can reach the port can read your approval "
                         "queue. token-file.patch makes the token required; run "
                         "apply-patches.ps1."))
    except Exception as exc:
        rows.append((WARN, "could not test a request with no token", type(exc).__name__))
    return rows


@preflight_check("handshake", "Does it say what it can do?")
def pf_handshake(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the handshake")
    rows = []
    try:
        code, body, _r, _h = live.get("/api/version")
    except Exception as exc:
        return [(FAIL, "/api/version did not answer", type(exc).__name__)]
    if code != 200 or not isinstance(body, dict):
        return [(FAIL, f"/api/version answered {code}",
                 "Both apps start by reading it. Restart Jarvis; if it stays, send "
                 "this output back.")]
    live.version = body
    api = body.get("api")
    if api == APPS_SPEAK_API:
        rows.append((PASS, f"it speaks API version {api}, the one both apps speak"))
    else:
        rows.append((FAIL, f"it speaks API version {api!r}; both apps speak {APPS_SPEAK_API}",
                     "The apps and the backend do not match. Run apply-patches.ps1 so "
                     "the backend's files are this repository's."))
    caps = body.get("capabilities")
    if isinstance(caps, dict) and caps:
        off = sorted(k for k, v in caps.items() if v is False)
        rows.append((PASS, f"it lists {len(caps)} capabilities"
                     + (f" ({', '.join(off)} off)" if off else "")))
    else:
        rows.append((FAIL, "its handshake lists no capabilities",
                     "Both apps hide every feature they cannot see listed. The rebuilt "
                     "jarvis_events.py sends them; run apply-patches.ps1."))
    st = live.status or {}
    missing = [k for k in ("lane", "model", "power", "activity") if k not in st]
    if missing:
        rows.append((WARN, f"/api/status leaves out {', '.join(missing)}",
                     "The apps show those in the header; they fall back to blanks. Not "
                     "broken by itself."))
    else:
        rows.append((PASS, f"/api/status says: model {st.get('model')}, power "
                           f"{st.get('power')}, {st.get('activity')}"))
    # The desktop app installed on this PC, from its own log.
    ours = _repo_version(live.repo)
    logs = live.desktop_logs()
    seen = None
    if logs is not None:
        try:
            text = (logs / "jarvis-desktop.log").read_text(encoding="utf-8", errors="replace")
            found = re.findall(r"===== Jarvis Desktop (\S+) starting", text)
            seen = found[-1] if found else None
        except OSError:
            seen = None
    if seen is None:
        rows.append((SKIP, "which desktop app version is installed",
                     "No desktop app log was found on this PC, so it could not be "
                     "told. That is normal if the desktop app has never run here."))
    elif ours and _version_tuple(seen) < _version_tuple(ours):
        rows.append((WARN, f"the desktop app last started here is version {seen}; this "
                           f"repository is {ours}",
                     "Buttons in the older app may call routes this backend changed. "
                     "Build and install the new one (docs/INSTALL.md)."))
    else:
        rows.append((PASS, f"the desktop app last started here is version {seen}"
                     + (f", the same as this repository" if seen == ours else "")))
    return rows


@preflight_check("model", "Is the model downloaded, loadable, and answering?")
def pf_model(live: Live) -> list:
    model = None
    # The running Jarvis's own word for its model - but only for the local
    # lane: a cloud lane's model is not an Ollama model.
    if isinstance(live.status, dict) and str(live.status.get("lane") or "local") == "local":
        m = live.status.get("model")
        if isinstance(m, str) and m.strip() and m.strip().lower() not in ("none", "offline"):
            model = m.strip()
    model = model or _configured_model()
    base = (live.ollama_base or _ollama_base()).rstrip("/")
    rows = [r if len(r) == 3 else (r[0], r[1], "")
            for r in doctor(fetch=live.ollama, base=base, model=model, env=live.env)]
    if not model or not _is_loopback(base):
        return rows
    if any(r[0] == FAIL and "is not answering" in r[1] for r in rows):
        return rows
    # One fixed question, straight to Ollama: the model loads (if it was not
    # loaded) and answers. No tools are offered and no size is sent, so
    # nothing is reloaded; nothing is unloaded.
    t0 = time.time()
    try:
        post = live.ollama_post
        body = {"model": model, "stream": False,
                "messages": [{"role": "user", "content": READY_QUESTION}],
                "options": {"num_predict": 200}}
        if post is not None:
            got = post(f"{base}/api/chat", body)
        else:
            req = urllib.request.Request(f"{base}/api/chat", method="POST",
                                         data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            with _no_proxy_open(req, 180) as r:
                got = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        rows.append((FAIL, f"{model} did not answer a one-word question",
                     f"{type(exc).__name__}. Jarvis cannot answer anything until it "
                     f"does. Restart Ollama; if it keeps failing, the model may be too "
                     f"big for the card (docs/MODEL-TOPOLOGY.md)."))
        return rows
    took = time.time() - t0
    if isinstance(got, dict) and got.get("error"):
        rows.append((FAIL, f"Ollama refused to run {model}",
                     "Its own words: " + str(got.get("error"))[:200]))
    elif isinstance(got, dict) and (got.get("done") or (got.get("message") or {}).get("content")):
        rows.append((PASS, f"{model} loaded and answered a one-word question "
                           f"in {took:.1f} seconds"))
    else:
        rows.append((FAIL, f"{model} gave an answer Jarvis could not read",
                     "Restart Ollama and run this again."))
    return rows


@preflight_check("chat", "Does a question go all the way through Jarvis?")
def pf_chat(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the chat round trip")
    caps = (live.version or {}).get("capabilities") or {}
    temporary = caps.get("temporary_chat") is True
    tools = None
    try:
        code, body, _r, _h = live.get("/api/reach")
        if code == 200 and isinstance(body, dict):
            live.reach = body
            tools = [t.get("id") for t in body.get("tools") or [] if isinstance(t, dict)]
    except Exception:
        tools = None
    if not live.with_chat:
        if not temporary:
            return [(SKIP, "a question through Jarvis's own chat",
                     "This Jarvis cannot hold a temporary chat (temporary-chat.patch), "
                     "so the question would be kept and learned from. Run with "
                     "--with-chat to send it anyway.")]
        if tools is None:
            return [(SKIP, "a question through Jarvis's own chat",
                     "Could not tell which tools are switched on (/api/reach), and the "
                     "model could choose one. Run with --with-chat to send it anyway.")]
        if tools:
            return [(SKIP, "a question through Jarvis's own chat",
                     f"Tools are switched on ({', '.join(str(t) for t in tools)}), so "
                     "the model could choose one - which might raise a card or read "
                     "your email. Run with --with-chat to send it anyway; deny any "
                     "card it raises.")]
    body = {"messages": [{"role": "user", "content": READY_QUESTION}], "stream": False}
    if temporary:
        body["temporary"] = True
    t0 = time.time()
    try:
        code, got, raw, hdrs = live.post("/api/chat", body, timeout=180)
    except Exception as exc:
        return [(FAIL, "a question through Jarvis's own chat got no answer",
                 f"{type(exc).__name__}. The model check above says whether Ollama "
                 f"works; if it does, restart Jarvis.")]
    took = time.time() - t0
    if code != 200 or not isinstance(got, dict):
        return [(FAIL, f"Jarvis's chat answered {code}",
                 (raw or b"")[:200].decode("utf-8", "replace"))]
    if got.get("error"):
        return [(FAIL, "Jarvis's chat answered with an error",
                 str(got.get("error"))[:300])]
    try:
        text = got["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = None
    if not isinstance(text, str):
        return [(FAIL, "Jarvis's chat answer is not in the shape the apps read",
                 "Send this output back.")]
    route = _json((hdrs.get("x-jarvis-route") or "").encode("utf-8")) or {}
    where = route.get("where")
    if where and where != "local":
        return [(WARN, f"a question went through Jarvis's chat in {took:.1f} seconds, "
                       f"but was answered by the {where} lane, not this PC",
                 "Fine for a question about nothing, but check the lane settings if "
                 "you meant everything to stay on this PC.")]
    return [(PASS, f"a question went all the way through Jarvis's chat and back in "
                   f"{took:.1f} seconds" + (" (a temporary chat: nothing kept)" if temporary
                                            else ""))]


def _patch_targets(text: str) -> list:
    return sorted(set(re.findall(r"^\+\+\+ b/(\S+)", text, re.M)))


def patch_states(backend: Path, *, order=None, read=None) -> list:
    """[(patch, file, state, present, total)] - state is "applied",
    "partly", "not applied", "no file" or "nothing to look for".

    A patch counts as applied when most of the lines it adds are in the
    file. Lines a LATER patch in the order takes out again are not counted,
    and neither are lines the patch's own context already had."""
    import _stack
    names = order if order is not None else _stack.order()
    texts = {n: (HERE / n).read_text(encoding="utf-8") for n in names}
    read = read or (lambda f: (backend / f).read_text(encoding="utf-8", errors="replace"))
    files: dict = {}
    out = []
    # How many patches add each line, per file: a line two patches both add
    # (a shared "token_ok=_token_ok, read_body=_read_body))") proves neither.
    shared: dict = {}
    for name in names:
        for f in _patch_targets(texts[name]):
            seen = set()
            for h, _p in _stack.hunks(texts[name], f):
                seen |= {l[1:].strip() for l in h.splitlines()
                         if l.startswith("+") and not l.startswith("+++")}
            for line in seen:
                shared[(f, line)] = shared.get((f, line), 0) + 1
    for i, name in enumerate(names):
        for f in _patch_targets(texts[name]):
            if f not in files:
                try:
                    files[f] = {l.strip() for l in read(f).splitlines()}
                except OSError:
                    files[f] = None
            if files[f] is None:
                out.append((name, f, "no file", 0, 0))
                continue
            removed, pre = set(), set()
            for later in names[i + 1:]:
                for hunk, _p in _stack.hunks(texts[later], f):
                    removed |= {l[1:].strip() for l in hunk.splitlines()
                                if l.startswith("-") and not l.startswith("---")}
            hunks = _stack.hunks(texts[name], f)
            for _h, p in hunks:
                pre |= {x.strip() for x in p}
            adds = []
            for h, _p in hunks:
                for l in h.splitlines():
                    s = l[1:].strip()
                    if (l.startswith("+") and not l.startswith("+++") and len(s) >= 12
                            and s not in removed and s not in pre
                            and shared.get((f, s), 0) == 1):
                        adds.append(s)
            if not adds:
                out.append((name, f, "nothing to look for", 0, 0))
                continue
            present = sum(1 for a in adds if a in files[f])
            state = ("applied" if present >= 0.8 * len(adds)
                     else "not applied" if present == 0 else "partly")
            out.append((name, f, state, present, len(adds)))
    return out


@preflight_check("patches", "Is every patch really in your files?")
def pf_patches(live: Live) -> list:
    try:
        states = patch_states(live.backend)
    except Exception as exc:
        return [(WARN, "could not read the patch list", f"{type(exc).__name__}: {exc}")]
    rows = []
    no_file = sorted({f for _n, f, s, _p, _t in states if s == "no file"})
    for f in no_file:
        rows.append((FAIL, f"{f} is not in {live.backend}",
                     "The patches for it cannot be there. Set JARVIS_BACKEND to the folder "
                     "holding jarvis_hud.py, or find the file (scripts/check-backend.ps1)."))
    bad = [s for s in states if s[2] in ("not applied", "partly")]
    for name, f, state, present, total in bad:
        if state == "not applied":
            rows.append((FAIL, f"{name} is not in {f}",
                         "Its fix is not running. Run apply-patches.ps1 (backend/README.md, "
                         "'Apply them'), then restart Jarvis."))
        else:
            rows.append((FAIL, f"only part of {name} is in {f} ({present} of {total} lines)",
                         "An older version of it, or the file was edited by hand. "
                         "apply-patches.ps1 replaces an older version; then restart Jarvis."))
    names = {n for n, *_ in states}
    broken = {n for n, _f, s, _p, _t in states if s not in ("applied", "nothing to look for")}
    if names - broken:
        rows.append((PASS, f"{len(names - broken)} of {len(names)} patches are in your files"))
    return rows


@preflight_check("modules", "Is the file Jarvis runs the file you think?")
def pf_modules(live: Live) -> list:
    try:
        from _where import SHIPPED
    except Exception as exc:
        return [(WARN, "could not read the list of shipped modules", type(exc).__name__)]
    rows = []
    same = 0
    newer_than_start = []
    started = (live.version or {}).get("started")
    for rel in SHIPPED:
        leaf = rel.rsplit("/", 1)[-1]
        theirs, ours = live.backend / leaf, HERE / rel
        if not theirs.is_file():
            rows.append((FAIL, f"{leaf} is not in the backend folder",
                         "The feature it carries is switched off. Run apply-patches.ps1 "
                         "(it copies every shipped module in), then restart Jarvis."))
            continue
        if not ours.is_file():
            continue
        a, b = _sha(theirs), _sha(ours)
        if a != b:
            rows.append((FAIL, f"{leaf} in the backend folder is not this repository's copy "
                               f"({a[:8]} there, {b[:8]} here)",
                         "Most likely an older one. Run apply-patches.ps1, then restart "
                         "Jarvis."))
            continue
        same += 1
        if isinstance(started, (int, float)) and not isinstance(started, bool):
            try:
                if theirs.stat().st_mtime > started + 2:
                    newer_than_start.append(leaf)
            except OSError:
                pass
    if same:
        rows.append((PASS, f"{same} of {len(SHIPPED)} shipped modules are identical to "
                           f"this repository's copies"))
    if newer_than_start:
        shown = ", ".join(newer_than_start[:6]) + (" and more" if len(newer_than_start) > 6
                                                   else "")
        rows.append((WARN, f"{len(newer_than_start)} module(s) changed after Jarvis started: "
                           f"{shown}",
                     "The running Jarvis may still use the old code for them. Restart "
                     "Jarvis (quit the desktop app and open it again)."))
    return rows


def _settings_marker(backend: Path):
    """(path, [lines]) - a few `key = value` lines of the owner's settings
    file, which no web page would have. (Section headers like "[voice]" are
    not used: jarvis_hud.html itself mentions some.)"""
    try:
        _on_path(backend)
        import jarvis_framework as fw
        path = fw.config_path()
    except Exception:
        path = None
    if path is None:
        for c in (backend / "jarvis-framework.toml", backend.parent / "jarvis-framework.toml"):
            if c.is_file():
                path = c
                break
    if path is None:
        return None, []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return path, []
    out = []
    for l in lines:
        s = l.strip()
        if "=" in s and not s.startswith("#") and len(s) >= 16:
            out.append(s)
        if len(out) >= 3:
            break
    return path, out


@preflight_check("private_files", "Is the settings file kept off the web?")
def pf_private_files(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the settings-file check")
    path, markers = _settings_marker(live.backend)
    leaks = []
    for probe in PRIVATE_PROBES:
        for with_token in (False, True):
            try:
                code, _b, raw, _h = live.get(probe, token=with_token, timeout=5.0)
            except Exception:
                continue
            if code != 200 or not raw:
                continue
            text = raw[:200_000].decode("utf-8", "replace")
            if (any(m in text for m in markers) or "[autonomy." in text
                    or raw.startswith(b"SQLite format 3")
                    or ("def " in text and "jarvis" in text and "<html" not in text.lower())
                    or (live.token and live.token in text)):
                leaks.append(probe + (" (with the token)" if with_token else " (with NO token)"))
    if leaks:
        return [(FAIL, f"Jarvis SERVES A PRIVATE FILE over HTTP: {', '.join(leaks[:4])}",
                 "Anything that can reach the port can read it - your settings, code or "
                 "data. Stop Jarvis now and send this output back; do not use the phone "
                 "until it is fixed.")]
    said = f" (your settings are in {path})" if path else ""
    return [(PASS, f"none of {len(PRIVATE_PROBES)} addresses serves the settings file or "
                   f"another private file{said}")]


def _banner_line(logs, prefix: str):
    """The newest line of backend.log that starts with `prefix` (after the
    two-space indent the banner uses), or None."""
    if logs is None:
        return None
    try:
        text = (logs / "backend.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hits = [l.strip() for l in text.splitlines() if l.strip().startswith(prefix)]
    return hits[-1] if hits else None


@preflight_check("gate", "Does the approval gate stop what it should?")
def pf_gate(live: Live) -> list:
    rows = []
    try:
        _on_path(live.backend)
        import jarvis_gate as G
        v = G.check("post_to_external_service", {"probe": True}, timeout=0.1)
        refused = not getattr(v, "allowed", True)
        rows.append((PASS if refused else FAIL,
                     "a 'never' action is refused" if refused
                     else "a 'never' action was ALLOWED",
                     "" if refused else "This is the control the whole project is built "
                     "around. Send this output back before using Jarvis."))
    except Exception as exc:
        rows.append((FAIL, "the approval gate could not be asked", f"{type(exc).__name__}: "
                     f"{exc}"))
    # owner-check.patch: in the files, and switched on at start-up?
    try:
        gate_src = (live.backend / "jarvis_gate.py").read_text(encoding="utf-8",
                                                                errors="replace")
    except OSError:
        gate_src = ""
    if "_approval_stamped" in gate_src:
        caps = (live.version or {}).get("capabilities") or {}
        line = _banner_line(live.desktop_logs(), "approvals")
        if live.version is not None and caps.get("owner_check") != "backend":
            rows.append((FAIL, "owner-check.patch is in your files, but the running Jarvis "
                               "did not switch it on",
                         "Until it does, EVERY approval is refused. Check that "
                         "jarvis_owner_check.py is in the backend folder (apply-patches.ps1 "
                         "copies it), then restart Jarvis."
                         + (f" Its start-up line said: {line}" if line else "")))
        elif line and "NOT CHECKED" in line:
            rows.append((FAIL, "the last start-up said approvals are NOT CHECKED",
                         f"{line}. Run apply-patches.ps1, then restart Jarvis."))
        elif live.version is not None:
            rows.append((PASS, "the PC's own Windows Hello check for risky approvals is on"
                         + (" (its start-up line is in backend.log)" if line else "")))
    return rows


@preflight_check("stop_all", "Does Stop everything reach the running Jarvis?")
def pf_stop_all(live: Live) -> list:
    if not live.up or live.version is None:
        return _needs_backend(live, "Stop everything")
    caps = live.version.get("capabilities") or {}
    if caps.get("stop_all") is True:
        return [(PASS, "Stop everything (the hotkey and the phone's button) reaches it")]
    return [(WARN, "Stop everything cannot reach the running Jarvis yet",
             "The hotkey and the phone's button still stop speech, and the task Stop "
             "button still works. Run apply-patches.ps1 (stop-all.patch and "
             "jarvis_stop_all.py), then restart Jarvis.")]


@preflight_check("scheduler", "Is the scheduler running?")
def pf_scheduler(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the scheduler")
    try:
        code, body, _r, _h = live.get("/api/schedule")
    except Exception as exc:
        return [(FAIL, "/api/schedule did not answer", type(exc).__name__)]
    if code == 404:
        return [(WARN, "this Jarvis has no scheduler yet",
                 "Timers, reminders and the briefing need schedule.patch. Run "
                 "apply-patches.ps1.")]
    if code == 503 or not isinstance(body, dict):
        return [(WARN, "the scheduler is not installed",
                 "Copy jarvis_schedule.py in (apply-patches.ps1 does), then restart Jarvis.")]
    if body.get("running") is True:
        n = len(body.get("jobs") or [])
        return [(PASS, f"the scheduler is running ({n} timer(s), reminder(s) or "
                       f"repeat(s) waiting)")]
    return [(FAIL, "the scheduler's loop is NOT running",
             "Timers, reminders and the morning briefing will not go off. Restart "
             "Jarvis; if it stays, send backend.log back.")]


@preflight_check("events", "Does the event stream deliver?")
def pf_events(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the event stream")
    try:
        head = live.events_head()
    except Exception as exc:
        return [(FAIL, "the event stream did not open", f"{type(exc).__name__}. Both apps "
                 "hold approvals while it is down. Restart Jarvis.")]
    if "retry:" in head and "hello" in head:
        return [(PASS, "the event stream delivers (approvals and live status reach the apps)")]
    return [(FAIL, "the event stream opened but sent no hello",
             f"Got: {head[:120]!r}. Both apps will call the link stale. Restart Jarvis.")]


@preflight_check("voice", "Are the voice models there?")
def pf_voice(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "the voice models")
    try:
        code, body, _r, _h = live.get("/api/voice/status")
    except Exception as exc:
        return [(WARN, "/api/voice/status did not answer", type(exc).__name__)]
    if code != 200 or not isinstance(body, dict):
        return [(WARN, "voice is not installed on this PC",
                 "Typing works without it. To talk to Jarvis, see backend/README.md, "
                 "'Voice that works'.")]
    rows = []
    for key, name in (("stt", "speech-to-text (hearing you)"),
                      ("tts", "the voice (Jarvis speaking)")):
        part = body.get(key) if isinstance(body.get(key), dict) else {}
        if part.get("available") is True:
            rows.append((PASS, f"{name} is installed"))
        else:
            rows.append((WARN, f"{name} is not installed",
                         (str(part.get("status") or "") + ". ").lstrip(". ")
                         + "See backend/README.md, 'Voice that works'."))
    return rows


@preflight_check("reach", "Calendar, email and web search")
def pf_reach(live: Live) -> list:
    if not live.up:
        return _needs_backend(live, "calendar, email and web search")
    body = live.reach
    if body is None:
        try:
            code, body, _r, _h = live.get("/api/reach")
            body = body if code == 200 and isinstance(body, dict) else None
        except Exception:
            body = None
    if body is None:
        return [(WARN, "this Jarvis cannot list what it can reach yet",
                 "reach.patch and jarvis_reach.py; run apply-patches.ps1.")]
    rows = []
    by_id = {r.get("id"): r for r in body.get("rows") or [] if isinstance(r, dict)}
    for rid, name, kind in (("calendar", "Calendar reading", "calendar"),
                            ("email_read", "Email reading", "email")):
        row = by_id.get(rid)
        state = (row or {}).get("state")
        if state != "on":
            rows.append((SKIP, f"{name} is not set up ({(row or {}).get('state_words') or 'off'})"))
            continue
        if not live.with_reads:
            rows.append((PASS, f"{name} is set up (not read: add --with-reads to read it once)"))
            continue
        rows.append(_read_once(live, kind, name))
    tools = [t.get("id") for t in body.get("tools") or [] if isinstance(t, dict)]
    if "web_search" not in tools:
        rows.append((SKIP, "web search is not switched on, so nothing was searched"))
        return rows
    try:
        code, view, _r, _h = live.get("/api/search")
    except Exception as exc:
        rows.append((WARN, "/api/search did not answer", type(exc).__name__))
        return rows
    if code != 200 or not isinstance(view, dict) or not view.get("provider"):
        why = (view or {}).get("why") if isinstance(view, dict) else ""
        rows.append((SKIP, "no web search provider is chosen, so nothing was searched",
                     str(why or "")))
        return rows
    try:
        code, got, _r, _h = live.post("/api/search/test", {}, timeout=60)
    except Exception as exc:
        rows.append((FAIL, "Test search did not answer", type(exc).__name__))
        return rows
    got = got if isinstance(got, dict) else {}
    said = str(got.get("said") or "")
    if got.get("ok") is True or got.get("state") == "works":
        rows.append((PASS, f"web search works through {view.get('provider')} "
                           f"(one search for the word 'wikipedia')"))
    else:
        rows.append((FAIL, f"web search through {view.get('provider')} does not work",
                     said or f"state: {got.get('state')}. Settings -> Web search says more."))
    return rows


def _read_once(live: Live, kind: str, name: str) -> tuple:
    """One real read, asked for with --with-reads: a number, never a word of
    what was read. Uses THIS window's settings, which may differ from the
    running Jarvis's."""
    fn = (live.reads or {}).get(kind)
    try:
        if fn is None:
            if kind == "email":
                import jarvis_email as M
                got = M.count(M.plan(), approved=True)
            else:
                import jarvis_calendar as M
                got = M.run(M.plan(days_ahead=1), approved=True)
        else:
            got = fn()
    except Exception as exc:
        return (FAIL, f"{name} failed", f"{type(exc).__name__}")
    if isinstance(got, dict) and got.get("ok"):
        if kind == "email":
            return (PASS, f"{name} works ({got.get('count', '?')} unread)")
        return (PASS, f"{name} works ({len(got.get('events') or [])} event(s) in the next day)")
    reason = str((got or {}).get("reason") or "no reason given")[:200]
    return (FAIL, f"{name} is set up but reading failed",
            f"{reason}. This window's settings were used; if Jarvis's differ, check "
            f"Settings -> What Jarvis can reach.")


@preflight_check("credentials", "Is Windows Credential Manager reachable?")
def pf_credentials(live: Live) -> list:
    try:
        import jarvis_token_store as TS
    except Exception as exc:
        return [(WARN, "jarvis_token_store.py is not in the backend folder",
                 f"{type(exc).__name__}. Run apply-patches.ps1.")]
    make = live.token_store or (lambda target: TS.WindowsStore(target))
    try:
        store = make(TS.TARGET)
        store.read()           # found or not found: either way it answered
    except TS.Unavailable:
        return [(SKIP, "Credential Manager, because this is not Windows")]
    except Exception as exc:
        return [(FAIL, "Windows Credential Manager did not answer",
                 f"{type(exc).__name__}. Jarvis keeps its pairing token and search keys "
                 f"there; without it the phone needs pairing again after every restart. "
                 f"Restart the PC; if it stays, send this output back.")]
    return [(PASS, "Windows Credential Manager answers (the pairing token and keys are kept "
                   "there)")]


# ---------------------------------------------------------------- running

_SHOW = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", SKIP: "skip"}


def run_preflight(live: Live, *, only=None, out=print) -> tuple:
    """Run every check (or only the keys in `only`), print each row, and
    return (pass, fail, warn, skip, rows). A check that raises is a FAIL of
    its own - it never stops the others."""
    rows = []
    for key, title, fn in PREFLIGHT:
        if only and key not in only:
            continue
        out(f"\n{title}")
        try:
            got = fn(live) or []
        except Exception as exc:
            got = [(FAIL, f"the {key} check itself broke",
                    f"{type(exc).__name__}: {exc}. Send this output back.")]
        for r in got:
            status, what = r[0], r[1]
            detail = r[2] if len(r) > 2 else ""
            rows.append((key, status, what, detail))
            out(f"  {_SHOW.get(status, status)}  {what}")
            for d in str(detail or "").rstrip().splitlines()[:6]:
                out(f"          {d}")
    n = {s: sum(1 for r in rows if r[1] == s) for s in (PASS, FAIL, WARN, SKIP)}
    out("")
    out(f"{n[PASS]} pass, {n[FAIL]} fail, {n[WARN]} warn"
        + (f" ({n[SKIP]} skipped)" if n[SKIP] else ""))
    return n[PASS], n[FAIL], n[WARN], n[SKIP], rows


def jarvis_version() -> str:
    """The one version number Jarvis shares across the desktop app, the phone
    app and these backend files: VERSION at the top of this copy of the
    repository (the one apply-patches.ps1 installed from). "unknown" when
    the file is missing or not major.minor.patch."""
    try:
        v = (HERE.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return v if re.fullmatch(r"\d+\.\d+\.\d+", v) else "unknown"


def preflight_main(argv) -> int:
    print("Preflight: the Jarvis that is running now, every chain end to end.")
    print("Read-only: it approves nothing, sends no email, unloads no model and")
    print("changes no setting. The pairing token is used, never shown.")
    print(f"\nversion : {jarvis_version()} (this copy of the Jarvis files)")
    print(f"backend : {BACKEND}")
    live = Live(with_reads="--with-reads" in argv, with_chat="--with-chat" in argv)
    print(f"jarvis  : {live.base}")
    _p, failed, _w, _s, _rows = run_preflight(live)
    if failed:
        print("VERDICT: something is broken. Each FAIL above says what to do.")
        return 1
    print("VERDICT: every chain that could be checked works.")
    return 0


# ==========================================================================

def main() -> int:
    print(__doc__.split("WHY THIS EXISTS")[0].strip())
    print(f"\nversion : {jarvis_version()} (this copy of the Jarvis files)")
    print(f"backend : {BACKEND}")
    print(f"python  : {sys.version.split()[0]}  ({sys.executable})")

    if stage_files() and stage_imports():
        stage_config()
        stage_gate()
        stage_memory()
        stage_server()
    # Outside the `if`: whether Ollama and the model are ready does not
    # depend on the backend files, and it is worth knowing even when they
    # are missing.
    stage_ollama()

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
        if "--preflight" in sys.argv[1:]:
            sys.exit(preflight_main(sys.argv[1:]))
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped")
        sys.exit(130)
