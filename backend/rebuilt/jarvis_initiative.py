"""jarvis_initiative.py - Jarvis noticing things without being asked.

REBUILT. One call site, and it is the whole contract:

    jarvis_hud.py:2240   _ENGINE = jarvis_initiative.build_from_config()
    jarvis_hud.py:2241   _ENGINE.start()

guarded by `if _fw2.load_framework().get("initiative", {}).get("enabled", True)`.
`_ENGINE` is also handed to the event pump as `Pump(engine=_ENGINE)`.

The config says what it is for:

    [initiative]
    enabled = true
    heartbeat_minutes = 30
    # Every finding or event that turns into an ACTION still goes through the
    # autonomy gate. A proactive Jarvis is not a Jarvis with fewer rules.

THE CHECKS THEMSELVES ARE NOT REBUILT, AND THAT IS DELIBERATE.

This engine's job is to run checks on a timer and file what they find. WHICH
checks is not recoverable - the config points at a `HEARTBEAT.md` in the
config directory that "lists the checks in plain words", and that file is not
on the machine either. Inventing a set of background checks would mean a
rebuilt Jarvis doing unattended things nobody chose, which is the opposite of
what this project is about.

So: the engine runs, the timer ticks, the finding queue works, and the
check list is EMPTY until someone registers one. The HUD starts cleanly, the
pump gets its engine, and nothing happens on its own that was not asked for.
`status()["checks"]` being 0 is the honest signal that this is a shell.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("initiative", {}).get(key, default)
    except Exception:
        return default


class Engine:
    """Runs registered checks on a heartbeat and collects what they find."""

    def __init__(self, heartbeat_minutes: float = 30.0, enabled: bool = True) -> None:
        self.heartbeat = max(1.0, float(heartbeat_minutes)) * 60.0
        self.enabled = bool(enabled)
        self.checks: list = []
        self.findings: list = []
        self.beats = 0
        self.errors = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ---- registration ------------------------------------------------------

    def register(self, name: str, fn: Callable) -> "Engine":
        with self._lock:
            self.checks.append((str(name), fn))
        return self

    # ---- running -----------------------------------------------------------

    def start(self) -> "Engine":
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-initiative",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def beat(self) -> list:
        """One pass over the checks. Returns what was newly found.

        Separate from the thread so a test can drive it without waiting half
        an hour, and so a check can be exercised on demand.
        """
        new = []
        with self._lock:
            checks = list(self.checks)
        for name, fn in checks:
            try:
                got = fn()
            except Exception:
                # A check that throws must not stop the others or kill the
                # heartbeat. Counted so a permanently broken check is visible
                # in status() rather than merely silent.
                self.errors += 1
                continue
            if not got:
                continue
            for item in (got if isinstance(got, list) else [got]):
                new.append(self.file(name, item))
        self.beats += 1
        return new

    def file(self, source: str, finding) -> dict:
        """Record something noticed. Announces a COUNT, never the content.

        The finding's text came from reading something - a mailbox, a page, a
        file - and `[privacy] never_leaves_device` covers all three. The event
        bus reaches a lock screen, so the doorbell carries how many, not what.
        """
        row = {"id": f"f{int(time.time()*1000)}{len(self.findings)}",
               "source": str(source), "at": time.time(),
               "finding": finding, "seen": False}
        with self._lock:
            self.findings.append(row)
            n = len([f for f in self.findings if not f["seen"]])
        try:
            import jarvis_events
            jarvis_events.BUS.note("findings", n, "finding")
        except Exception:
            pass
        return row

    def inbox(self, unseen_only: bool = False) -> list:
        with self._lock:
            return [dict(f) for f in self.findings
                    if not (unseen_only and f["seen"])]

    def mark_seen(self, ids: Optional[list] = None) -> int:
        """Mark findings read. Reading is not approving - nothing here acts."""
        with self._lock:
            n = 0
            for f in self.findings:
                if ids is None or f["id"] in ids:
                    if not f["seen"]:
                        f["seen"] = True
                        n += 1
            return n

    def _run(self) -> None:
        while not self._stop.is_set():
            self.beat()
            self._stop.wait(self.heartbeat)

    def status(self) -> dict:
        with self._lock:
            return {"enabled": self.enabled, "running": self.running,
                    "heartbeat_minutes": round(self.heartbeat / 60, 1),
                    "checks": len(self.checks), "beats": self.beats,
                    "errors": self.errors, "findings": len(self.findings),
                    "unseen": len([f for f in self.findings if not f["seen"]]),
                    "note": ("no checks are registered - the original check "
                             "list is not recoverable, see the module docstring")
                            if not self.checks else ""}


def build_from_config() -> Engine:
    """The engine the HUD starts. Never raises: a bad config must not stop
    the backend booting, and `enabled=false` is a legitimate answer."""
    try:
        beats = float(_cfg("heartbeat_minutes", 30) or 30)
    except (TypeError, ValueError):
        beats = 30.0
    return Engine(heartbeat_minutes=beats, enabled=bool(_cfg("enabled", True)))
