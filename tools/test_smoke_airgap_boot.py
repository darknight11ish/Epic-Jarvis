"""test_smoke_airgap_boot.py - the air-gap harness's own tests.

    python -B tools/test_smoke_airgap_boot.py

Every check is hermetic: no real network, no owner data, no product wiring.
The tests install the harness's guard in THIS process (so a mistake in the
guard is caught here, not only in a child) and use only loopback sockets and
child processes.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smoke_airgap_boot as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def t_loopback_matrix():
    ns = S.install_guard()
    is_loopback = ns["is_loopback"]
    for host in ("127.0.0.1", "127.9.9.9", "::1", "localhost", "LOCALHOST",
                 "[::1]", "::1%lo0"):
        check(f"{host!r} is loopback", is_loopback(host) is True)
    for host in ("8.8.8.8", "example.com", "huggingface.co", "10.0.0.1",
                 "203.0.113.9", ""):
        check(f"{host!r} is not loopback", is_loopback(host) is False)


def t_the_guard_blocks_and_fails_fast():
    for label, fn in (
        ("create_connection",
         lambda: socket.create_connection(("api.github.com", 443), timeout=1.0)),
        ("getaddrinfo", lambda: socket.getaddrinfo("huggingface.co", 443)),
        ("raw socket connect", lambda: socket.socket().connect(("1.1.1.1", 443))),
    ):
        blocked, ms, kind, words = S._probe_ms(fn)
        check(f"the guard blocks {label}", blocked, kind)
        check(f"... fast, under {S.MAX_PROBE_SECONDS:.1f} s ({label})",
              ms < S.MAX_PROBE_SECONDS * 1000.0, f"{ms:.1f} ms")
        check(f"... with the calm offline sentence ({label})",
              S.CALM_OFFLINE[:20] in words and "Traceback" not in words, words[:120])


def t_loopback_still_connects():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        client = socket.create_connection(("127.0.0.1", server.getsockname()[1]),
                                          timeout=1.0)
        client.close()
        check("a loopback connection still works through the guard", True)
    finally:
        server.close()


def t_children_inherit_the_guard_and_boot_the_core():
    got = S._run_child(S.CHILD_CORE_CODE)
    data = got.get("data") or {}
    check("the guarded child starts and answers",
          got.get("returncode") == 0 and isinstance(data, dict),
          (got.get("stderr") or "")[-300:])
    imports = data.get("imports") or {}
    check("every core module imports in a guarded child",
          len(imports) == len(S.CORE_MODULES)
          and all(v.get("ok") for v in imports.values()),
          {k: v for k, v in imports.items() if not v.get("ok")})
    loops = data.get("loops") or {}
    check("the basic loops run in a guarded child",
          len(loops) == len(S.CORE_LOOPS) and all(v.get("ok") for v in loops.values()),
          {k: v for k, v in loops.items() if not v.get("ok")})
    probes = data.get("probes") or []
    check("a child's external probes are blocked fast and calmly",
          len(probes) == 2 and all(p.get("blocked") is True
                                   and p.get("ms", 9999) < S.MAX_PROBE_SECONDS * 1000.0
                                   and S.CALM_OFFLINE[:20] in str(p.get("words"))
                                   for p in probes), probes)


def t_bite_proof_is_measured_and_real():
    guard_got = S._run_child(S.CHILD_BITE_CODE)
    weak_got = S._run_child(S.CHILD_BITE_CODE, weakened=True)
    guard_data = guard_got.get("data") or {}
    weak_data = weak_got.get("data") or {}
    check("the real guard blocks the bite probe under 2 s",
          guard_data.get("blocked") is True
          and guard_data.get("ms", 9999) < S.MAX_PROBE_SECONDS * 1000.0, guard_data)
    check("the weakened copy takes the simulated link's 2.5 s",
          weak_data.get("blocked") is True and weak_got.get("wall_ms", 0) > 2000.0,
          weak_got.get("wall_ms"))
    check("the guard child is at least 4x faster wall-clock",
          guard_got.get("wall_ms", 99999) * 4.0 < weak_got.get("wall_ms", 0),
          (guard_got.get("wall_ms"), weak_got.get("wall_ms")))


def t_env_claim_audit_matches_the_real_tree():
    def text(path):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    check("the documented jarvis_hud.py claim is unverifiable in the repo (no such file)",
          not (S.BACKEND / "jarvis_hud.py").is_file())
    memory = text(S.REBUILT / "jarvis_memory.py")
    check("jarvis_memory.py honours HF_HUB_OFFLINE but does not setdefault it "
          "(the doc's 'at the top' claim is stale)",
          "os.environ.setdefault" not in memory
          and '_OFFLINE_ENV = ("HF_HUB_OFFLINE"' in memory)
    check("jarvis_f5_worker.py DOES setdefault the offline env for its child",
          'os.environ.setdefault(k, "1")' in text(S.BACKEND / "jarvis_f5_worker.py"))
    check("jarvis_voices.py gives its worker the offline env",
          '"HF_HUB_OFFLINE": "1"' in text(S.BACKEND / "jarvis_voices.py"))
    check("run_suites.py sets both offline switches for every suite",
          '"HF_HUB_OFFLINE": "1"' in text(S.BACKEND / "run_suites.py")
          and '"TRANSFORMERS_OFFLINE": "1"' in text(S.BACKEND / "run_suites.py"))


def t_the_harness_itself_passes():
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, "-B", str(HERE / "smoke_airgap_boot.py")],
                          capture_output=True, text=True, timeout=180)
    elapsed = time.perf_counter() - started
    out = (proc.stdout or "") + (proc.stderr or "")
    check("python -B tools/smoke_airgap_boot.py exits 0", proc.returncode == 0,
          out[-800:])
    check("... prints a measured bite proof line", "bite proof (measured)" in out)
    check("... and reports zero failures", "0 failed" in out)
    check("... within a sensible wall time", elapsed < 60.0, f"{elapsed:.1f} s")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
