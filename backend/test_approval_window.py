"""The approval card's window: 15 minutes by default, and changeable in Settings.

Two things are proved here, and each has been shown to FAIL when it is untrue:

  1. the shipped default is 900 seconds (15 minutes), and jarvis_gate's own
     APPROVAL_TIMEOUT really takes that value from the settings file - not from a
     code literal somewhere else;
  2. changing it through the limits table (the row both apps draw, written by
     jarvis_limits.set_limit) reaches the very key jarvis_gate reads, so the
     control and the behaviour cannot drift apart.

Run: python backend/test_approval_window.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
sys.path.insert(0, str(BASE))

PASSED, FAILED = [], []


def check(what: str, ok: bool, detail=""):
    (PASSED if ok else FAILED).append(what)
    print(("ok    " if ok else "FAIL  ") + what + ("" if ok else f"  <-- {detail}"))


def _shipped_toml() -> Path:
    return BASE / "jarvis-framework.toml"


def _value_in(path: Path, key: str):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(key + " "):
            return line.split("=", 1)[1].strip()
    return None


def t_default_is_fifteen_minutes():
    v = _value_in(_shipped_toml(), "approval_timeout_seconds")
    check("the shipped settings file says 900 seconds for the approval window",
          v == "900", f"found {v!r}")
    import jarvis_limits as L
    row = L.find("approval_wait")
    check("the limits table has the row both apps draw", row is not None)
    if row is not None:
        check("... whose default is also 900", float(row.default) == 900.0,
              str(row.default))
        check("... and whose bounds are finite, with no zero",
              row.low == 300 and row.high == 3600 and 0 not in row.choices
              and row.choices == (300, 900, 1800, 3600),
              f"low={row.low} high={row.high} choices={row.choices}")
        check("... and it reads as words, never a raw number of seconds",
              row.words(900) == "wait 15 minutes", row.words(900))


def t_the_gate_takes_the_value_from_the_file():
    """jarvis_gate must read the settings file, not a literal of its own."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-approval-"))
    try:
        cfg = tmp / "jarvis-framework.toml"
        shutil.copyfile(_shipped_toml(), cfg)
        # Same file, a different number: only a gate that really reads it moves.
        text = cfg.read_text(encoding="utf-8").replace(
            "approval_timeout_seconds = 900", "approval_timeout_seconds = 1234")
        cfg.write_text(text, encoding="utf-8")
        os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
        import jarvis_framework as fw
        old = getattr(fw, "CONFIG_DIR", None)
        fw.CONFIG_DIR = tmp
        for mod in ("jarvis_gate",):
            sys.modules.pop(mod, None)
        try:
            import jarvis_gate as G
            check("jarvis_gate.APPROVAL_TIMEOUT follows the settings file",
                  float(G.APPROVAL_TIMEOUT) == 1234.0, str(G.APPROVAL_TIMEOUT))
        finally:
            if old is not None:
                fw.CONFIG_DIR = old
            sys.modules.pop("jarvis_gate", None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_settings_reaches_the_key_the_gate_reads():
    """The row both apps draw writes [autonomy].approval_timeout_seconds."""
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-approval-"))
    try:
        cfg = tmp / "jarvis-framework.toml"
        shutil.copyfile(_shipped_toml(), cfg)
        import jarvis_limits as L
        L.set_limit("approval_wait", 1800, path=cfg)
        v = _value_in(cfg, "approval_timeout_seconds")
        check("changing the row in Settings writes the key the gate reads",
              v == "1800", f"found {v!r}")
        # And the gate, reading that same file, now waits longer.
        os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
        import jarvis_framework as fw
        old = getattr(fw, "CONFIG_DIR", None)
        fw.CONFIG_DIR = tmp
        sys.modules.pop("jarvis_gate", None)
        try:
            import jarvis_gate as G
            check("... and the gate waits the new number of seconds",
                  float(G.APPROVAL_TIMEOUT) == 1800.0, str(G.APPROVAL_TIMEOUT))
        finally:
            if old is not None:
                fw.CONFIG_DIR = old
            sys.modules.pop("jarvis_gate", None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_the_hello_stamp_outlives_the_window():
    """A stamp must not expire exactly when the card does."""
    import jarvis_owner_check as OC
    import jarvis_limits as L
    window = float(L.find("approval_wait").default)
    check("the Windows Hello stamp lasts longer than a card can wait",
          float(OC._STAMP_TTL) > window,
          f"_STAMP_TTL={OC._STAMP_TTL} window={window}")


if __name__ == "__main__":
    for fn in (t_default_is_fifteen_minutes, t_the_gate_takes_the_value_from_the_file,
               t_settings_reaches_the_key_the_gate_reads,
               t_the_hello_stamp_outlives_the_window):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__} raised {type(exc).__name__}: {exc}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
