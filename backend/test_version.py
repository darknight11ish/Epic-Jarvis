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

It also pins the PHONE's versionCode scheme (the block below "the phone's
versionCode"): a fixed base added to CI's run number, never the run number on
its own. That scheme exists because the two numbers drifted apart with nothing
holding them: the owner's phone held versionCode 10009 while the published
APK was 1299, which made every future release an Android "version downgrade"
and left an uninstall - wiping the pairing token - as the only way in. A
versionCode scheme with no test is what let that happen, so the arithmetic is
asserted here rather than left in a comment.
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


def declared_int(source: str, name: str):
    """The value of `val NAME = 1_000_000` in a Kotlin file, or None."""
    m = re.search(rf"^val {name} = ([\d_]+)$", source, re.M)
    return int(m.group(1).replace("_", "")) if m else None


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

    # The phone's versionCode: a fixed base plus CI's run number.
    #
    # MEASURED 2026-10-11/12, and why this block is here. `versionCode` WAS
    # CI's run number. The owner's phone (CPH2419, over adb) held
    # `com.jarvis.client` versionCode=10009 / versionName=0.2.10009, while the
    # published `client-latest` APK (jarvis-client-8518e53.apk) was
    # versionCode=1299 / versionName=0.2.1299 - read with `aapt2 dump badging`.
    # A workflow run number climbs by one per run, so every release CI could
    # produce for years sat BELOW 10009: `adb install -r` answers
    # INSTALL_FAILED_VERSION_DOWNGRADE, and the only way past it is an
    # uninstall, which wipes the app's data and with it the pairing token.
    # Nothing in the repository contained "10009" and nothing asserted the
    # scheme, so nothing stopped the two numbers drifting apart. Both numbers
    # below are those measured ones, so the arithmetic tested here is about the
    # real phone rather than two made-up values.
    INSTALLED_VERSION_CODE = 10009      # the phone, 2026-10-11 (adb dumpsys package)
    PUBLISHED_RUN = 1299                # client-latest, jarvis-client-8518e53.apk
    NEXT_RUN = PUBLISHED_RUN + 1        # the next release CI would cut

    base = declared_int(gradle, "VERSION_CODE_BASE")
    check("build.gradle.kts declares versionCode's base", base is not None)
    top_run = declared_int(gradle, "VERSION_CODE_MAX_RUN")
    check("build.gradle.kts declares the largest run number it will add",
          top_run is not None)
    base = base if base is not None else -1
    top_run = top_run if top_run is not None else -1
    check("versionCode is the base plus CI's run number, never the run number alone",
          re.search(r"fun buildVersionCode\(\): Int\s*=\s*VERSION_CODE_BASE \+ "
                    r"\(ciRunNumber\(\) \?: 0\)", gradle) is not None)
    check("versionCode is only ever assigned from buildVersionCode()",
          len(re.findall(r"^\s*versionCode = ", gradle, re.M)) == 1
          and "versionCode = buildVersionCode()" in gradle)
    check("the old default of 1 is gone, so no path can fall back to it",
          "?: 1" not in gradle and "takeIf { it in 1..2_100_000_000 }" not in gradle)
    check("the run number is only trusted inside GitHub Actions, where a local "
          "build's stale GITHUB_RUN_NUMBER cannot reach it",
          'providers.environmentVariable("GITHUB_ACTIONS")' in gradle)
    check("the versionName still takes its run number from the same reading, "
          "so a build outside CI reads plain VERSION",
          "val run = ciRunNumber()" in gradle)
    check("a re-run keeps its number: nothing counts attempts, commits or a file "
          "into versionCode",
          "GITHUB_RUN_ATTEMPT" not in gradle and "rev-list --count" not in gradle)
    check("the highest reachable versionCode stays inside Android's 2.1e9 ceiling",
          base >= 1 and top_run >= 1 and base + top_run < 2_100_000_000,
          f"base {base} + largest run {top_run} = {base + top_run}")
    check("the base alone already clears the 10009 installed on the phone",
          base > INSTALLED_VERSION_CODE,
          f"base {base} vs installed {INSTALLED_VERSION_CODE}")
    check("even CI's first run would clear it",
          base + 1 > INSTALLED_VERSION_CODE,
          f"run 1 -> {base + 1} vs installed {INSTALLED_VERSION_CODE}")
    check(f"the next CI run gives {base + NEXT_RUN}, above the phone's "
          f"{INSTALLED_VERSION_CODE}",
          base + NEXT_RUN == 1_000_001_300
          and base + NEXT_RUN > INSTALLED_VERSION_CODE,
          f"run {NEXT_RUN} -> {base + NEXT_RUN}")
    print(f"        versionCode = {base} + run: run {PUBLISHED_RUN} -> "
          f"{base + PUBLISHED_RUN}, run {NEXT_RUN} -> {base + NEXT_RUN}, "
          f"no CI -> {base} (installed {INSTALLED_VERSION_CODE} is cleared by "
          f"{base - INSTALLED_VERSION_CODE})")

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
