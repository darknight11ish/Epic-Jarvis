#!/usr/bin/env python3
"""Every native library in the Android APK must be loadable on a 16 KB page
device (Android 15+).

    python3 tools/check_apk_16kb.py [APK] [-v]

Android 15 lets a device run with 16 KB memory pages. A shared object built
for it must pass BOTH of these, and they are independent - a library can pass
the first and still fault on the second:

  1. **ELF segment alignment.** Every `PT_LOAD` segment must have
     `p_align >= 0x4000` with `p_vaddr` congruent to `p_offset` modulo that
     alignment. A library whose segments are 4 KB aligned does not fail at
     build time and does not fail on a 4 KB phone: `dlopen` fails on the 16 KB
     device alone.

  2. **RELRO.** The platform linker `mprotect`s the `PT_GNU_RELRO` range
     ROUNDED UP to the page size, so on a 16 KB device
     `[relro_end, round_up_16k(relro_end))` becomes read-only too. If anything
     WRITABLE lives in that window, the app segfaults the moment it writes
     there. Google's guide gives the proxy test
     `(GNU_RELRO p_vaddr + p_memsz) % 0x4000 == 0`; this script uses the
     narrower, exact rule instead (an overlapping `PF_W` `PT_LOAD`), because
     the proxy on its own flags Google's own androidx libraries and would make
     this check cry wolf.

For this app the second library that matters is the "hey Jarvis" spotter:
`libonnxruntime.so` and `libonnxruntime4j_jni.so` are prebuilt by Microsoft
and shipped inside `com.microsoft.onnxruntime:onnxruntime-android`, and
nothing in this repository can re-align them - the fix, if one is ever needed,
is upstream or a different ABI list.

Why a check and not a comment. `jarvis-client/app/build.gradle.kts` says of
`useLegacyPackaging = true`: "Its .so files are 16 KB page-aligned (checked),
so either way loads on Android 15's 16 KB devices." That was true on
2026-10-09 and nothing kept it true - the pin is 1.22.0 and the file's own
comment invites a bump ("PINNED to 1.22.0 and not to be bumped without
unzipping the new AAR first"), which is exactly the change that could quietly
ship a 4 KB library. This is that "checked", made repeatable, in the same
spirit as the other `tools/check_*.py` scripts: one new check per real risk.

Note which half of "16 KB alignment" the APK's own layout is. The zip-entry
alignment `zipalign -P 16` checks only matters for libraries stored
UNCOMPRESSED (`extractNativeLibs="false"`), where the loader mmaps them
straight out of the APK. This app sets `useLegacyPackaging = true`, which is
`extractNativeLibs="true"` - Google's own documented workaround for the zip
half - so its .so files are compressed and unpacked at install and no zip
offset is load-bearing. The script prints which of the two layouts the APK
actually has rather than assuming it.

What it reads: only the APK named (or found), and nothing else. It does not
build anything and does not need the Android SDK or NDK - the ELF headers are
parsed in Python so the check runs anywhere, including a CI runner with no
NDK installed.

With no APK named it looks at the release APK, then the debug APK, then the
newest APK anywhere under a `build/` directory - the release one first because
that is the artifact the owner installs. Nothing found is an error, not a
pass: a check that reports success because it looked at nothing is the failure
mode `tools/check_vacuous_checks.py` exists for.

Exit 0 when every library passes both checks, 1 otherwise.
"""

from __future__ import annotations

import os
import struct
import sys
import zipfile

# The 16 KB page size Android 15 introduced, and the smallest p_align a
# PT_LOAD segment may carry to be loadable there.
PAGE_16K = 16384

PT_LOAD = 1
PT_GNU_RELRO = 0x6474E552
PF_W = 0x2

# The ABIs this app ships (app/build.gradle.kts `abiFilters`). Named so a
# missing one is reported rather than silently skipped - an APK with no
# arm64 library at all would otherwise "pass" every check here.
EXPECTED_ABIS = ("arm64-v8a", "x86_64")

DEFAULT_APKS = (
    "jarvis-client/app/build/outputs/apk/release/app-release.apk",
    "jarvis-client/app/build/outputs/apk/debug/app-debug.apk",
)


def find_apk(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for rel in DEFAULT_APKS:
        if os.path.isfile(rel):
            return rel
    # Any other module's output, newest first, so a differently-named variant
    # (a split, a benchmark build) is still checked rather than missed.
    found: list[tuple[float, str]] = []
    for root, _dirs, names in os.walk("."):
        if os.sep + "build" + os.sep not in root + os.sep:
            continue
        for name in names:
            if name.endswith(".apk"):
                path = os.path.join(root, name)
                found.append((os.path.getmtime(path), path))
    return max(found)[1] if found else None


def elf_program_headers(blob: bytes) -> list[dict] | None:
    """Every program header, or None when this is not a 64-bit ELF file."""
    if len(blob) < 64 or blob[:4] != b"\x7fELF":
        return None
    if blob[4] != 2:  # not ELF64 - no ABI this app ships is 32-bit
        return None
    end = "<" if blob[5] == 1 else ">"
    try:
        (e_phoff,) = struct.unpack_from(end + "Q", blob, 0x20)
        e_phentsize, e_phnum = struct.unpack_from(end + "HH", blob, 0x36)
    except struct.error:
        return None
    if e_phentsize == 0 or e_phnum == 0:
        return []
    out = []
    for i in range(e_phnum):
        try:
            p_type, p_flags, p_offset, p_vaddr, _paddr, p_filesz, p_memsz, p_align = (
                struct.unpack_from(end + "IIQQQQQQ", blob, e_phoff + i * e_phentsize)
            )
        except struct.error:
            return None
        out.append(
            {
                "type": p_type,
                "flags": p_flags,
                "offset": p_offset,
                "vaddr": p_vaddr,
                "filesz": p_filesz,
                "memsz": p_memsz,
                "align": p_align,
            }
        )
    return out


def round_up_16k(value: int) -> int:
    return (value + PAGE_16K - 1) // PAGE_16K * PAGE_16K


def load_problems(phdrs: list[dict]) -> tuple[list[str], int, int]:
    """(problems, number of PT_LOAD segments, smallest p_align)."""
    loads = [p for p in phdrs if p["type"] == PT_LOAD]
    if not loads:
        return (["no PT_LOAD segments, which no real library has"], 0, 0)
    problems = []
    for p in loads:
        a = p["align"]
        congruent = a != 0 and (p["vaddr"] - p["offset"]) % a == 0
        if a < PAGE_16K or not congruent:
            problems.append(
                f"a PT_LOAD segment is not 16 KB aligned "
                f"(p_align={a}, vaddr=0x{p['vaddr']:x}, offset=0x{p['offset']:x}, "
                f"congruent={congruent})"
            )
    return (problems, len(loads), min(p["align"] for p in loads))


def relro_problem(phdrs: list[dict]) -> str | None:
    """The exact RELRO failure, or None.

    Only a WRITABLE region inside the page-size round-up window matters; an
    unaligned RELRO whose window holds nothing writable is harmless, which is
    why the guide's `% 0x4000 == 0` proxy is not used as the verdict here.
    """
    relros = [p for p in phdrs if p["type"] == PT_GNU_RELRO]
    if not relros:
        return None
    relro = relros[0]
    relro_end = relro["vaddr"] + relro["memsz"]
    window_end = round_up_16k(relro_end)
    if window_end == relro_end:
        return None  # already page aligned: nothing to round up over
    for p in phdrs:
        if p["type"] != PT_LOAD or not (p["flags"] & PF_W):
            continue
        lo = max(p["vaddr"], relro_end)
        hi = min(p["vaddr"] + p["memsz"], window_end)
        if lo < hi:
            return (
                f"writable memory [0x{lo:x}, 0x{hi:x}) falls inside the RELRO "
                f"page round-up window [0x{relro_end:x}, 0x{window_end:x}) - the "
                f"linker mprotects that whole page read-only on a 16 KB device, "
                f"so this faults on the first write there. Rebuild the library "
                f"with -Wl,-z,max-page-size=16384 and -Wl,-z,common-page-size=16384"
            )
    return None


def zip_layout_note(apk: str) -> str:
    """Which packaging layout is in play, read from the APK itself.

    Printed, not asserted on: it says which half of "16 KB alignment" the zip
    can be judged on, so a reader is not left guessing why a zip-offset check
    was not reported.
    """
    try:
        with zipfile.ZipFile(apk) as zf:
            so_entries = [i for i in zf.infolist() if i.filename.startswith("lib/")]
    except (OSError, zipfile.BadZipFile) as exc:
        return f"could not read the APK as a zip: {exc}"
    if not so_entries:
        return "no lib/ entries at all - nothing native is packaged"
    stored = [i.filename for i in so_entries if i.compress_type == zipfile.ZIP_STORED]
    compressed = len(so_entries) - len(stored)
    out = f"{len(so_entries)} native entries: {compressed} compressed, {len(stored)} stored"
    if stored:
        out += (
            " - the uncompressed ones are mmapped straight out of the APK, so "
            "their zip offsets matter too and `zipalign -c -P 16 -v 4` is the "
            "other half of this check"
        )
    else:
        out += (
            " - all compressed, so extractNativeLibs is on and the libraries are "
            "unpacked at install; their ELF headers below are what decides whether "
            "they load on a 16 KB device"
        )
    return out


def main(argv: list[str]) -> int:
    verbose = "-v" in argv
    rest = [a for a in argv if a != "-v"]
    explicit = rest[0] if rest else None

    apk = find_apk(explicit)
    if apk is None:
        if explicit:
            print(f"error: {explicit} does not exist, so nothing was checked.")
        else:
            print(
                "error: no APK found. Build one first "
                "(cd jarvis-client && ./gradlew assembleDebug or assembleRelease), "
                "or name one: python3 tools/check_apk_16kb.py path/to/app.apk",
            )
        return 1

    print(f"APK: {apk}")
    print(f"  {zip_layout_note(apk)}")

    problems: list[str] = []
    abis_seen: set[str] = set()
    with zipfile.ZipFile(apk) as zf:
        lib_names = sorted(
            i.filename
            for i in zf.infolist()
            if i.filename.startswith("lib/") and i.filename.endswith(".so")
        )
        if not lib_names:
            print("error: the APK carries no lib/<abi>/*.so at all, so there is "
                  "nothing to check and no evidence of a pass.")
            return 1

        for name in lib_names:
            parts = name.split("/")
            if len(parts) >= 3:
                abis_seen.add(parts[1])
            phdrs = elf_program_headers(zf.read(name))
            if phdrs is None:
                problems.append(f"{name}: not a 64-bit ELF file, so its alignment "
                                f"cannot be read")
                continue
            found, count, worst = load_problems(phdrs)
            relro = relro_problem(phdrs)
            for f in found:
                problems.append(f"{name}: {f}")
            if relro:
                problems.append(f"{name}: {relro}")
            verdict = "16 KB OK" if not found and not relro else "NOT 16 KB"
            print(f"  {name:<48} {count} LOAD, min p_align={worst:<7} "
                  f"relro={'OK' if not relro else 'RISK'}  {verdict}")
            if verbose:
                for p in phdrs:
                    print(
                        f"      type=0x{p['type']:<9x} off=0x{p['offset']:<9x} "
                        f"vaddr=0x{p['vaddr']:<11x} filesz=0x{p['filesz']:<9x} "
                        f"memsz=0x{p['memsz']:<9x} align=0x{p['align']:x}"
                    )

    missing = [a for a in EXPECTED_ABIS if a not in abis_seen]
    if missing:
        problems.append(
            f"no native library for {', '.join(missing)} - abiFilters in "
            f"app/build.gradle.kts names those ABIs, so this is not the APK that "
            f"is supposed to ship"
        )

    if problems:
        print()
        for p in problems:
            print(f"FAIL: {p}")
        print(f"\n{len(problems)} problem(s).")
        return 1

    print(
        f"\nAll {len(lib_names)} native libraries pass both 16 KB checks "
        f"({', '.join(sorted(abis_seen))})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
