"""test_front.py - jarvis_front.py, the one front-window reader focus
sessions and "Watch with me" share (split out of jarvis_focus.py on
2026-09-28, docs/SCREEN-DESIGN.md build step 1).

    python3 backend/test_front.py

What it proves:
  - jarvis_focus imports every moved name back, and they are the SAME
    objects (so focus behaves exactly as before - test_focus.py, unchanged,
    is the full proof);
  - the address box is cut down to the host inside the reader, and a search
    typed there is not a host;
  - the reader never walks into the page (a Document control is skipped)
    and keeps nothing between calls (no module-level state);
  - off Windows it says so rather than pretending.
No network, no Windows.
"""
from __future__ import annotations

import re
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_front.py", "jarvis_focus.py")

fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = Path(tempfile.mkdtemp(prefix="jarvis-front-"))
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "auto"
sys.modules.setdefault("jarvis_framework", fw)

import jarvis_front as FR  # noqa: E402
import jarvis_focus as F  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


MOVED = ("BROWSERS", "JARVIS_EXES", "NEUTRAL_CLASSES", "NEUTRAL_EXES", "host_of", "site_of",
         "_registrable", "_is_jarvis_title", "_windows_front", "_address_box_value",
         "windows_probe", "probe_available", "_thread_context")


def t_focus_uses_the_shared_reader():
    for name in MOVED:
        check(f"jarvis_focus.{name} is jarvis_front.{name}",
              getattr(F, name, None) is getattr(FR, name))
    src = (HERE / "jarvis_focus.py").read_text(encoding="utf-8")
    check("jarvis_focus.py no longer carries its own copy of the reader",
          "def windows_probe" not in src and "def _address_box_value" not in src
          and "def _windows_front" not in src)
    check("the Engine's default probe is the shared one", F.Engine().probe is FR.windows_probe)


def t_the_host_and_nothing_else():
    check("an address becomes its host",
          FR.host_of("https://www.example.com/private/path?token=abc") == "www.example.com")
    check("a bare host is read", FR.host_of("docs.google.com") == "docs.google.com")
    check("a search typed in the address box is not a host",
          FR.host_of("how do rivers work") == "" and FR.host_of("rivers") == "")
    check("one site: www. and m. are dropped, other subdomains kept",
          FR.site_of("www.youtube.com") == "youtube.com" == FR.site_of("m.youtube.com")
          and FR.site_of("mail.google.com") == "mail.google.com")
    check("nothing past the host survives", "token" not in FR.host_of(
        "https://bank.example/login?token=abc#frag"))


def t_the_reader_never_reads_the_page_and_keeps_nothing():
    src = (HERE / "jarvis_front.py").read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"#.*", "", code)
    check("a Document control (the page itself) is skipped, never walked into",
          re.search(r'ctype == "DocumentControl":\s*\n\s*continue', code) is not None)
    check("the walk has a budget", "_UIA_READ_BUDGET" in code)
    globals_assigned = re.findall(r"^([a-z_][a-z0-9_]*)\s*=", code, re.M)
    check("no module-level state (every call reads fresh)", not [
        g for g in globals_assigned if g not in ("_uia_read_budget", "_uia_read_depth")],
        globals_assigned)
    check("no socket, no file, no model", not re.search(
        r"socket|urlopen|open\(|write_text|ollama|jarvis_agent", code, re.I))


def t_off_windows_it_says_so():
    import os
    check("probe_available is True only on Windows", FR.probe_available() == (os.name == "nt"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
