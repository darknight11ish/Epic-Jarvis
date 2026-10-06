#!/usr/bin/env python3
"""Run a suite or a fixture generator with the platform pretending to be Linux.

WHY THIS EXISTS

CI is Linux and the owner's PC is Windows, and a handful of suites compare a
committed contract file against a fresh run - so a value that comes from the
platform makes the file right on one and wrong on the other. That is exactly
what CI reported for seven suites on 2026-10-04, every one a Windows-only habit
or fix: git objects chmodded to 0o200 (which strips a POSIX directory's read
and execute bits), files written CRLF so the committed blob and its commit id
differ, a scrub that normalised one nested folder value only, two generators
that did not stand in for the platform, and one test premise left to Ollama's
own answer.

CI cannot be read from a terminal (job logs need a signed-in browser) and a
Linux container cannot be started on this machine (Docker Desktop's engine needs
a WSL distribution, and none is installed), so this is how such a failure is
made to happen locally:

    py -3 tools/pretend_linux.py gen_wiki_cases.py     # a generator's --check
    py -3 tools/pretend_linux.py test_wiki.py          # a whole suite

HOW IT PRETENDS

`os.name` is NOT patched globally: pathlib picks its flavour from it at call
time, so faking it makes pathlib build a PosixPath on Windows and raise. The
same goes for `sys.platform` - `shutil.which("git")` returns None the moment it
says Linux on a Windows interpreter. Instead an import hook hands a proxy `os`
(naming "posix"), proxy `sys` and proxy `platform` (Linux) to each `jarvis_*`
and `gen_*` module as it is imported, so only the code whose platform checks
matter sees Linux and the rest of the interpreter is untouched. Directory
listings come back reversed, which is not what Linux does (ext4 hands names back
in hash order) but is the property that matters: a fixture whose content depends
on the order a file system happens to return names in is stable on one machine
and different on the next.

It is a simulation, not Linux, and it should be treated as one: it found two of
those seven, and CI's own annotations found the rest. Anything it misses shows
as a pass.
"""
from __future__ import annotations

import importlib.abc
import os as _real_os
import platform as _real_platform
import runpy
import shutil
import sys
import sys as _real_sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Tools CI does not have: asking for one is the same as it not being installed.
WINDOWS_ONLY_TOOLS = ("reg", "pwsh", "powershell", "nvidia-smi", "wmic", "where",
                      "netstat", "tasklist", "schtasks", "cmd")
PATCHED_MODULES: list = []


class _PosixOS:
    """The real os module, but saying "posix" when its name is read."""

    name = "posix"

    def listdir(self, path="."):
        return list(reversed(sorted(_real_os.listdir(path))))

    def scandir(self, path="."):
        return iter(list(reversed(list(_real_os.scandir(path)))))

    def __getattr__(self, attr):
        return getattr(_real_os, attr)


class _LinuxSys:
    """The real sys module, but saying "linux" when its platform is read."""

    platform = "linux"

    def __getattr__(self, attr):
        return getattr(_real_sys, attr)


class _LinuxPlatform:
    """platform.*, Linux-shaped, for the modules that ask."""

    def system(self):
        return "Linux"

    def machine(self):
        return "x86_64"

    def release(self):
        return "6.8.0-generic"

    def version(self):
        return "#1 SMP PREEMPT_DYNAMIC"

    def platform(self, *a, **k):
        return "Linux-6.8.0-generic-x86_64-with-glibc2.39"

    def node(self):
        return "runner"

    def __getattr__(self, attr):
        return getattr(_real_platform, attr)


_proxy = _PosixOS()
_sys_proxy = _LinuxSys()
_platform_proxy = _LinuxPlatform()
_real_which = shutil.which


class _LinuxPretence(importlib.abc.MetaPathFinder):
    """Give every product module the Linux-shaped proxies once it is imported."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(("jarvis_", "gen_")):
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            try:
                spec = finder.find_spec(fullname, path, target)
            except (ImportError, AttributeError):
                continue
            if spec is None or spec.loader is None:
                continue
            real_exec = spec.loader.exec_module

            def exec_module(module, _real=real_exec):
                _real(module)
                seen = []
                for attr, proxy in (("os", _proxy), ("sys", _sys_proxy),
                                    ("platform", _platform_proxy)):
                    if getattr(module, attr, None) in (_real_os, _real_sys, _real_platform):
                        setattr(module, attr, proxy)
                        seen.append(attr)
                if seen:
                    PATCHED_MODULES.append(f"{module.__name__}[{','.join(seen)}]")
            spec.loader.exec_module = exec_module
            return spec
        return None


def pretend_linux() -> None:
    """Install the pretence in this process. Call before importing anything."""
    _real_os.environ["HOME"] = "/home/runner"
    _real_os.environ["USERPROFILE"] = "/home/runner"

    def which(name, *a, **k):
        if str(name).lower() in WINDOWS_ONLY_TOOLS:
            return None
        return _real_which(name, *a, **k)

    shutil.which = which
    sys.meta_path.insert(0, _LinuxPretence())


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip())
        print("\nsay which one: a suite (test_*.py) or a fixture generator (gen_*.py)")
        return 2
    target = argv[0]
    pretend_linux()
    for p in (REPO / "tools", REPO / "backend", REPO / "backend" / "rebuilt"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    is_suite = target.startswith("test_")
    path = (REPO / "backend" / target) if is_suite else (REPO / "tools" / target)
    if not path.is_file():
        print(f"there is no {path.relative_to(REPO)}")
        return 2
    print(f"### {target}, platform pretending to be Linux")
    sys.argv = [target] if is_suite else [target, "--check"]
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        print(f"    (exit {exc.code})")
    print(f"    (pretence installed on: {', '.join(PATCHED_MODULES) or 'nothing'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
