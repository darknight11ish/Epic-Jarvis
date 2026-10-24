#!/usr/bin/env python3
"""smoke_airgap_boot.py - the air-gapped cold-boot hermeticity harness.

    python -B tools/smoke_airgap_boot.py

WHY THIS EXISTS (Review V, 2026-10-23). Jarvis's brain, embeddings, voice and
databases are local. When the router's internet drops, nothing should hang or
show a traceback: the code paths that might reach out must fail fast, in calm
words, and the rest must boot and run. This harness proves that with the
network blocked at the Python level - not by relying on the real router being
up, down, slow or intercepted.

WHAT IT DOES, in order:
  1. installs a guard on `socket.create_connection`, `socket.getaddrinfo`,
     `socket.gethostbyname` and the socket object's own `connect`/`connect_ex`:
     loopback (127.0.0.0/8, ::1, `localhost`) is allowed; anything else raises
     `OSError(ENETUNREACH)` **before** a DNS lookup or a packet - so a probe
     fails in microseconds even on a machine whose network silently swallows
     traffic;
  2. puts the SAME guard in every Python child it starts, through a temporary
     `sitecustomize.py`, so a child cannot reach the network by accident;
  3. imports the backend's core modules and runs harmless loops in a guarded
     child, timing each import;
  4. runs external probes (create_connection, getaddrinfo, urllib, a raw
     socket connect) and requires each to fail in under 2.0 s with the calm
     offline sentence, never a hang and never a traceback;
  5. audits the work order's claim that `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`
     are set with `os.environ.setdefault(...)` at the top of `jarvis_hud.py` and
     `jarvis_memory.py` - reporting honestly where the claim is stale;
  6. a deliberate BITE PROOF: the same non-loopback probe against a temporarily
     weakened copy of the guard (a simulated black-hole link, 2.5 s) is measured
     and must fail fast with the real guard. The weakened number is simulated
     on purpose: measured on this machine, non-routable addresses such as
     10.255.255.1 answer immediately through a local network intercept, so a
     real "hang" cannot be produced honestly here.

WHAT IT DOES NOT TEST: a real unplugged router (owner-assisted), a non-Python
child program, or the OS firewall itself. It proves the CODE path, not the
network. Exit code 0 only when every required check passes; findings about the
stale doc claims are REPORTED but do not fail the run.
"""
from __future__ import annotations

import errno
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
REBUILT = BACKEND / "rebuilt"

#: The two Hugging Face offline switches the work order's rule names.
ENV_KEYS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

#: The document's own fail-fast ceiling, in seconds.
MAX_PROBE_SECONDS = 2.0

#: The one sentence a blocked probe shows a person - calm, no traceback.
CALM_OFFLINE = ("Offline: this PC has no internet connection, so Jarvis did "
                "not send anything.")

#: The marker a child reads; the guard is always installed when this module
#: runs, and the value only tells a child the run is intentional.
GUARD_MARKER = "JARVIS_AIRGAP_GUARD"

#: Modules the doc calls core. `jarvis_gate.py` and `jarvis_hud.py` are NOT in
#: this repository (they are patch-carried files on the owner's PC); the doc's
#: claim about them is audited separately in `audit_env_guards()`.
CORE_MODULES = ("jarvis_schedule", "jarvis_scrub", "jarvis_agent", "jarvis_quick",
                "jarvis_search", "jarvis_notes", "jarvis_briefing")

#: Harmless calls that prove each module's basic loop runs with no network.
CORE_LOOPS = (
    ("jarvis_schedule", "length_words", (90,)),
    ("jarvis_scrub", "scrub_text", ("hello world",)),
    ("jarvis_agent", "strip_chat_markers", ("<|im_start|>x",)),
)

#: The pieces of the guard, kept in ONE string so the in-process guard and the
#: child's sitecustomize guard cannot drift. This is a written file, never
#: imported from the repository.
GUARD_SOURCE = r'''
"""Injected air-gap guard: non-loopback sockets fail fast, in plain words."""
import errno
import ipaddress
import os
import socket
import time

CALM = ("Offline: this PC has no internet connection, so Jarvis did not send anything.")
WEAKENED = os.environ.get("JARVIS_AIRGAP_WEAKENED") == "1"
SLOW_SECONDS = 2.5
_ORIG = {}
_INSTALLED = False


def is_loopback(host):
    text = str(host or "").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if "%" in text:
        text = text.split("%", 1)[0]
    if text.lower().rstrip(".") in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _refuse(host):
    if WEAKENED:
        # Simulated black-hole link: what a network that silently drops packets
        # does to an unguarded call (measured, never a real connect here).
        time.sleep(SLOW_SECONDS)
    raise OSError(errno.ENETUNREACH, CALM)


def install():
    global _INSTALLED
    if _INSTALLED:
        return True
    _ORIG["create_connection"] = socket.create_connection
    _ORIG["getaddrinfo"] = socket.getaddrinfo
    _ORIG["gethostbyname"] = socket.gethostbyname

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if not is_loopback(host):
            _refuse(host)
        return _ORIG["create_connection"](address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not is_loopback(host):
            _refuse(host)
        return _ORIG["getaddrinfo"](host, *args, **kwargs)

    def guarded_gethostbyname(host, *args, **kwargs):
        if not is_loopback(host):
            _refuse(host)
        return _ORIG["gethostbyname"](host, *args, **kwargs)

    class GuardedSocket(socket.socket):
        def connect(self, address):
            host = address[0] if isinstance(address, tuple) else address
            if not is_loopback(host):
                _refuse(host)
            return super().connect(address)

        def connect_ex(self, address):
            host = address[0] if isinstance(address, tuple) else address
            if not is_loopback(host):
                if WEAKENED:
                    time.sleep(SLOW_SECONDS)
                return errno.ENETUNREACH
            return super().connect_ex(address)

    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyname = guarded_gethostbyname
    socket.socket = GuardedSocket
    _INSTALLED = True
    return True
'''

_SITECUSTOMIZE = ("try:\n"
                  "    from _jarvis_airgap_guard import install\n"
                  "    install()\n"
                  "except Exception:\n"
                  "    pass\n")

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def install_guard() -> dict:
    """Install the guard in THIS process; returns its namespace (for tests)."""
    os.environ.setdefault(GUARD_MARKER, "1")
    for key in ENV_KEYS:
        os.environ.setdefault(key, "1")
    namespace: dict = {"__name__": "_jarvis_airgap_guard"}
    exec(compile(GUARD_SOURCE, "<airgap-guard>", "exec"), namespace)
    namespace["install"]()
    return namespace


def _guard_dir(root: Path) -> Path:
    """A folder whose sitecustomize installs the guard in every Python child."""
    folder = root / "airgap_guard"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "_jarvis_airgap_guard.py").write_text(GUARD_SOURCE, encoding="utf-8")
    (folder / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    return folder


def _child_env(guard_dir: Path, *, weakened: bool = False) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(guard_dir)
    env[GUARD_MARKER] = "1"
    for key in ENV_KEYS:
        env[key] = "1"
    if weakened:
        env["JARVIS_AIRGAP_WEAKENED"] = "1"
    else:
        env.pop("JARVIS_AIRGAP_WEAKENED", None)
    return env


def _run_child(code: str, *, weakened: bool = False, timeout: float = 30.0) -> dict:
    """Run a child with the guard injected; its last stdout line is JSON."""
    with tempfile.TemporaryDirectory(prefix="jarvis-airgap-") as tmp:
        guard_dir = _guard_dir(Path(tmp))
        env = _child_env(guard_dir, weakened=weakened)
        started = time.perf_counter()
        proc = subprocess.run([sys.executable, "-B", "-c", textwrap.dedent(code)],
                              cwd=str(BACKEND), env=env, capture_output=True,
                              text=True, timeout=timeout)
        wall_ms = (time.perf_counter() - started) * 1000.0
    out = {"returncode": proc.returncode, "wall_ms": wall_ms,
           "stdout": proc.stdout, "stderr": proc.stderr}
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                out["data"] = json.loads(line)
                break
            except ValueError:
                continue
    return out


CHILD_CORE_CODE = r"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "rebuilt"))
CORE = %r
LOOPS = %r
data = {"imports": {}, "loops": {}, "probes": []}
for name in CORE:
    t0 = time.perf_counter()
    try:
        __import__(name)
        data["imports"][name] = {"ok": True, "ms": (time.perf_counter() - t0) * 1000}
    except Exception as exc:
        data["imports"][name] = {"ok": False, "error": type(exc).__name__,
                                 "ms": (time.perf_counter() - t0) * 1000}
for mod_name, fn_name, args in LOOPS:
    try:
        mod = __import__(mod_name)
        value = getattr(mod, fn_name)(*args)
        data["loops"][fn_name] = {"ok": True, "words": str(value)[:80]}
    except Exception as exc:
        data["loops"][fn_name] = {"ok": False, "error": type(exc).__name__}


def probe(label, fn):
    t0 = time.perf_counter()
    try:
        fn()
        data["probes"].append({"label": label, "blocked": False,
                               "ms": (time.perf_counter() - t0) * 1000})
    except Exception as exc:
        data["probes"].append({"label": label, "blocked": True,
                               "ms": (time.perf_counter() - t0) * 1000,
                               "kind": type(exc).__name__,
                               "words": str(exc)[:200]})


probe("create_connection", lambda: __import__("socket").create_connection(
    ("api.github.com", 443), timeout=1.0))
probe("urllib", lambda: urllib.request.urlopen(
    "https://open-meteo.com/", timeout=1.0))
print(json.dumps(data))
""" % (CORE_MODULES, CORE_LOOPS)

CHILD_BITE_CODE = r"""
import json, socket, time
t0 = time.perf_counter()
try:
    socket.create_connection(("203.0.113.9", 443), timeout=1.0)
    print(json.dumps({"blocked": False, "ms": (time.perf_counter() - t0) * 1000}))
except Exception as exc:
    print(json.dumps({"blocked": True, "ms": (time.perf_counter() - t0) * 1000,
                      "kind": type(exc).__name__, "words": str(exc)[:200]}))
"""


def _probe_ms(fn) -> tuple:
    """(blocked, ms, kind, words) for one expected-to-fail probe."""
    started = time.perf_counter()
    try:
        fn()
        return False, (time.perf_counter() - started) * 1000.0, "", ""
    except OSError as exc:
        return True, (time.perf_counter() - started) * 1000.0, type(exc).__name__, str(exc)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return False, (time.perf_counter() - started) * 1000.0, type(exc).__name__, str(exc)


def t_the_guard_blocks_every_external_probe_fast():
    probes = [
        ("create_connection to api.github.com",
         lambda: socket.create_connection(("api.github.com", 443), timeout=1.0)),
        ("create_connection to 1.1.1.1",
         lambda: socket.create_connection(("1.1.1.1", 443), timeout=1.0)),
        ("getaddrinfo to huggingface.co",
         lambda: socket.getaddrinfo("huggingface.co", 443)),
        ("urllib to open-meteo.com",
         lambda: urllib.request.urlopen("https://open-meteo.com/", timeout=1.0)),
        ("raw socket connect to 203.0.113.5",
         lambda: socket.socket().connect(("203.0.113.5", 443))),
    ]
    for label, fn in probes:
        blocked, ms, kind, words = _probe_ms(fn)
        check(f"{label} is blocked", blocked, kind)
        check(f"... in under {MAX_PROBE_SECONDS:.1f} s ({label})",
              ms < MAX_PROBE_SECONDS * 1000.0, f"{ms:.1f} ms")
        check(f"... with calm offline words ({label})",
              blocked and CALM_OFFLINE[:20] in words and "Traceback" not in words,
              words[:120])
    print(f"      measured: " + ", ".join(
        f"{label.split()[0]} {_probe_ms(fn)[1]:.3f} ms" for label, fn in probes[:3]))


def t_loopback_is_still_allowed():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        client.close()
        check("a loopback connection is still allowed", True)
    finally:
        server.close()


def t_child_inherits_the_guard_and_boots_core_modules():
    got = _run_child(CHILD_CORE_CODE)
    data = got.get("data") or {}
    check("the guarded child process starts and answers",
          got.get("returncode") == 0 and isinstance(data, dict),
          got.get("stderr", "")[-300:])
    imports = data.get("imports") or {}
    bad = {n: v for n, v in imports.items() if not v.get("ok")}
    check("every core module imports with the network blocked",
          len(imports) == len(CORE_MODULES) and not bad, bad or sorted(imports))
    loops = data.get("loops") or {}
    bad_loops = {n: v for n, v in loops.items() if not v.get("ok")}
    check("the basic loops run with the network blocked",
          len(loops) == len(CORE_LOOPS) and not bad_loops, bad_loops or sorted(loops))
    probes = data.get("probes") or []
    check("a child's external probes are blocked too",
          len(probes) == 2 and all(p.get("blocked") for p in probes), probes)
    check("... and blocked fast, with calm words",
          all(p.get("ms", 9999) < MAX_PROBE_SECONDS * 1000.0
              and CALM_OFFLINE[:20] in str(p.get("words")) for p in probes), probes)
    for name, info in sorted(imports.items()):
        print(f"      import {name:<20s} {info.get('ms', 0):7.1f} ms")
    print(f"      child total {got.get('wall_ms', 0):.0f} ms")


def t_no_env_claim_rule_is_left_unchecked():
    """The document's required rule: setdefault at the TOP of jarvis_hud.py and
    jarvis_memory.py. Checked against the real tree, reported honestly."""
    hud = BACKEND / "jarvis_hud.py"
    memory = REBUILT / "jarvis_memory.py"
    f5 = BACKEND / "jarvis_f5_worker.py"
    voices = BACKEND / "jarvis_voices.py"
    suites = BACKEND / "run_suites.py"

    def text(path):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    memory_text = text(memory)
    check("the doc claim about jarvis_hud.py is reported as unverifiable here",
          not hud.is_file(),
          "backend/jarvis_hud.py exists after all - check it")
    check("the doc claim about a setdefault at the top of jarvis_memory.py is "
          "reported stale (it honours the env, it does not set it)",
          "os.environ.setdefault" not in memory_text
          and '_OFFLINE_ENV = ("HF_HUB_OFFLINE"' in memory_text, "the claim may now be true")
    check("jarvis_f5_worker.py DOES setdefault HF_HUB_OFFLINE for its child",
          'os.environ.setdefault(k, "1")' in text(f5))
    check("jarvis_voices.py gives its voice worker the offline env",
          '"HF_HUB_OFFLINE": "1"' in text(voices))
    check("run_suites.py sets both offline switches for every suite",
          '"HF_HUB_OFFLINE": "1"' in text(suites)
          and '"TRANSFORMERS_OFFLINE": "1"' in text(suites))
    print("      claim audit: jarvis_hud.py NOT in repo (patch-carried live file); "
          "jarvis_memory.py honours HF_HUB_OFFLINE but does not setdefault it; "
          "f5 worker / voices worker / run_suites do set it for their children.")


def t_bite_proof_the_guard_prevents_the_slow_failure():
    guard_got = _run_child(CHILD_BITE_CODE)
    weak_got = _run_child(CHILD_BITE_CODE, weakened=True)
    guard_data = guard_got.get("data") or {}
    weak_data = weak_got.get("data") or {}
    check("with the REAL guard, the same probe is blocked fast",
          guard_data.get("blocked") is True
          and guard_data.get("ms", 9999) < MAX_PROBE_SECONDS * 1000.0, guard_data)
    check("with a WEAKENED copy, the same probe takes the simulated link's time",
          weak_data.get("blocked") is True
          and weak_got.get("wall_ms", 0) > 2000.0, weak_data)
    check("... so the guard is what keeps the failure under 2 s",
          guard_got.get("wall_ms", 9999) * 4.0 < weak_got.get("wall_ms", 0),
          (guard_got.get("wall_ms"), weak_got.get("wall_ms")))
    print(f"      bite proof (measured): real guard {guard_data.get('ms', 0):.3f} ms "
          f"(child {guard_got.get('wall_ms', 0):.0f} ms) vs weakened copy "
          f"{weak_data.get('ms', 0):.1f} ms (child {weak_got.get('wall_ms', 0):.0f} ms; "
          f"the 2.5 s hang is simulated - this machine's network answers "
          f"non-routable addresses immediately)")


def main() -> int:
    install_guard()
    print("air-gap boot harness: a hermetic, unplugged-in-software boot")
    t_the_guard_blocks_every_external_probe_fast()
    t_loopback_is_still_allowed()
    t_child_inherits_the_guard_and_boots_core_modules()
    t_no_env_claim_rule_is_left_unchecked()
    t_bite_proof_the_guard_prevents_the_slow_failure()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
