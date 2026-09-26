#!/usr/bin/env python3
"""One version number, one maker's name, everywhere they are written.

The professionalism audit of 2026-09-26 found three numbers (the desktop
"0.1.x", the phone always "0.1", the backend none) and an invented company
name as publisher. The owner decided (CLAUDE.md, 2026-09-26): the maker is
"darknight11ish"; and one version, 0.2.0, is shared by the desktop, the phone
and the backend. VERSION at the top of the repository is that number. It is
also written, because each tool reads its own file, in:

  jarvis-desktop/src-tauri/tauri.conf.json, Cargo.toml, package.json and
  package-lock.json (the desktop; CI replaces the last part with its run
  number, 0.2.<n>, so the updater sees every build as newer);
  jarvis-client/app/build.gradle.kts reads VERSION itself (the phone; CI
  builds read 0.2.<n> the same way);
  backend/selftest.py reads VERSION itself and prints it.

This suite fails when any of them disagree, so a version change is one edit
per file and none is forgotten. It also checks the maker's name and that the
changelog has an entry for the version.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def main() -> int:
    version = read("VERSION").strip()
    check("VERSION is major.minor.patch", re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
          version)
    conf = json.loads(read("jarvis-desktop/src-tauri/tauri.conf.json"))
    check("tauri.conf.json has the same version", conf.get("version") == version,
          conf.get("version"))
    cargo = read("jarvis-desktop/src-tauri/Cargo.toml")
    m = re.search(r'^\[package\].*?^version = "([^"]+)"', cargo, re.S | re.M)
    check("Cargo.toml has the same version", m is not None and m.group(1) == version,
          m and m.group(1))
    pkg = json.loads(read("jarvis-desktop/package.json"))
    check("package.json has the same version", pkg.get("version") == version, pkg.get("version"))
    lock = json.loads(read("jarvis-desktop/package-lock.json"))
    check("package-lock.json has the same version",
          lock.get("version") == version
          and (lock.get("packages") or {}).get("", {}).get("version") == version)
    gradle = read("jarvis-client/app/build.gradle.kts")
    check("the phone reads VERSION for its versionName (no hand-typed copy)",
          'file("../../VERSION")' in gradle and "versionName = buildVersionName()" in gradle
          and not re.search(r'versionName\s*=\s*"', gradle))
    import selftest
    check("selftest reports the same version", selftest.jarvis_version() == version,
          selftest.jarvis_version())
    client = read(".github/workflows/jarvis-client.yml")
    check("the phone's release notes read VERSION", "< VERSION)" in client)
    release = read(".github/workflows/desktop-release.yml")
    check("the desktop release keeps tauri.conf.json's major.minor",
          'version="${base%.*}.${GITHUB_RUN_NUMBER}"' in release)

    # The maker's name.
    check("tauri.conf.json: publisher and copyright are darknight11ish",
          conf["bundle"].get("publisher") == "darknight11ish"
          and "darknight11ish" in conf["bundle"].get("copyright", ""))
    check("Cargo.toml: authors are darknight11ish", 'authors = ["darknight11ish"]' in cargo)
    lic = read("LICENSE")
    check("LICENSE: copyright darknight11ish, and third-party files keep their own licences",
          "Copyright (c) 2026 darknight11ish" in lic and "THIRD-PARTY-NOTICES.txt" in lic)
    for rel in ("LICENSE", "jarvis-desktop/src-tauri/tauri.conf.json",
                "jarvis-desktop/src-tauri/Cargo.toml",
                "jarvis-desktop/src/settings.html",
                "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaqScreen.kt"):
        check(f"no 'Jarvis Labs' in {rel}", "Jarvis Labs" not in read(rel))
    faq = read("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaqScreen.kt")
    check("the phone's About shows BuildConfig.VERSION_NAME, the maker and the notices",
          'AboutFact("Version", BuildConfig.VERSION_NAME)' in faq and "darknight11ish" in faq
          and '"licenses/NOTICES.txt"' in faq)
    check("the phone's notices file is in its assets",
          (REPO / "jarvis-client/app/src/main/assets/licenses/NOTICES.txt").is_file())

    changelog = read("CHANGELOG.md")
    check(f"CHANGELOG.md has an entry for {version}", f"## {version}" in changelog)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
