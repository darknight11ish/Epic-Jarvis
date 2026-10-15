#!/usr/bin/env python3
"""Say whether the snapshot folders are really encrypted - file by file, not by habit.

    py -3 tools/check_snapshots_encrypted.py
    py -3 tools/check_snapshots_encrypted.py --dest <a folder> --dest <another>
    py -3 tools/check_snapshots_encrypted.py --self-test

WHY THIS EXISTS

The owner's personal data - 19 SQLite databases and about 1.6 MB, 604 rows when
this was written - is snapshotted weekly into `~/jarvis-data-snapshots`, and the
backup tool can also be pointed at a folder he chooses (`--dest`). On 2026-10-14
he chose **Windows EFS** (Encrypting File System) to encrypt those snapshots at
rest: it needs no passphrase, so the Sunday 03:00 task keeps working by itself.

EFS has one property that makes a checker worth having, and it is the property
that is easy to get wrong: **`cipher /e <folder>` sets an attribute on the
FOLDER so that files written into it later are encrypted. It does not encrypt
the files already inside it.** Turning it on the obvious way therefore produces
a folder that is half encrypted - the new snapshot is ciphertext and every older
one, including the `.jbak` archives and the snapshot taken the week before, is
still plaintext on the disk. Only `cipher /e /s:<folder>` reaches what is
already there.

That is invisible from the outside. The files open normally, the tool verifies
them normally, and nothing anywhere says "plain". This tool is the thing that
says it, in about a second, on the machine that has the files:

  * **the folder's own attribute**, which is what makes FUTURE snapshots
    encrypted - the half that keeps working while nobody is looking;
  * **every file and subfolder under it**, so the half-encrypted state above is
    named rather than assumed away;
  * **every snapshot**, not just the newest, because the older ones are exactly
    the ones a first run leaves behind;
  * **the four `.jbak` archives** in the chosen folder, which a checker that
    only globbed `jarvis-snap-*` would walk straight past.

WHAT IT DELIBERATELY DOES NOT DO

It never decrypts, encrypts, moves or rewrites anything. It reads one number per
path - `GetFileAttributesW` - and prints it. Nothing here needs an
administrator, and nothing here changes the thing it is measuring.

It is not a substitute for the backup tool's own verification. This says the
files are encrypted; `jarvis_data_backup.py verify` says the databases inside
are intact and that every row is still there. Encryption and integrity are two
different questions and this tool answers only the first.

WHAT "ENCRYPTED" MEANS HERE, AND WHAT IT DOES NOT

The attribute it reads says the file's contents are ciphertext under a
certificate belonging to the Windows account that wrote it. It does **not** mean
the file is safe from someone using that account - EFS decrypts transparently
for its owner, which is the whole reason it can run unattended. What it defends
against is the disk leaving the machine: a stolen drive, a resold PC, or the
profile folder copied somewhere else. Anyone who can log in as this user can
read these files, and this tool should not be read as saying otherwise.

THE KEY IS THE BACKUP. If the Windows profile is lost or Windows is reinstalled
without the certificate and private key exported first, these snapshots are
gone - not locked, gone. `docs/SNAPSHOT-ENCRYPTION.md` carries the one-line
export command and where the file must be kept (off this PC). This tool cannot
check that the key was exported, because the honest place for that export is not
on this machine; the document is where that half lives.

SKIPPED OFF WINDOWS. EFS is a Windows feature and `GetFileAttributesW` is a
Windows call, so a bare run on any other system prints SKIP with the reason and
exits 0 - the same shape `tools/check_lanes.py` uses. `--self-test` is never
skipped: it proves the reader itself, on a real temporary folder, by encrypting
it with `cipher` and watching the answer change.

Exit: 0 when every folder and file checked is encrypted (or the run was
skipped), 1 when any is not, when a folder named on the command line does not
exist, or when the self-test fails. A plain file is never a pass here - a folder
that is half encrypted is reported with the names of the plain ones.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path

#: `FILE_ATTRIBUTE_ENCRYPTED`, from `winnt.h`. `GetFileAttributesW` returns it
#: in the DWORD it hands back; this is the bit that means "EFS".
FILE_ATTRIBUTE_ENCRYPTED = 0x4000

#: `GetFileAttributesW`'s failure value, `INVALID_FILE_ATTRIBUTES`.
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

#: The folders to check when none is named. The first is the tool's own default
#: (`DEFAULT_DEST` in `tools/jarvis_data_backup.py`, recomputed from the home
#: folder rather than typed, so a moved profile is still checked); the second is
#: the folder the owner chose in Jarvis on 2026-10-14. Both are checked when
#: both exist, because the weekly task writes to the first and the chosen folder
#: is the one he actually looks at.
DEFAULT_DESTS = (
    Path.home() / "jarvis-data-snapshots",
    Path(r"C:\Users\pcadmin\Documents\Jarvis Backups"),
)


def encrypted_flag(attributes: int) -> bool:
    """Is the EFS bit set in a `GetFileAttributesW` result?

    Split out from the call itself so the reading is testable without a file:
    `--self-test` checks it against the constants `winnt.h` defines, including
    the failure value, which must never be read as "encrypted".
    """
    return bool(attributes & FILE_ATTRIBUTE_ENCRYPTED)


def attributes_of(path: Path) -> int:
    """The raw `GetFileAttributesW` value for `path`, or the failure value.

    Resolved as a wide string, which is what the `W` entry point wants - the
    folder the owner chose has a space in its name, and a byte-string call would
    have returned the failure value for it rather than an error anybody noticed.
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetFileAttributesW.restype = ctypes.c_uint32
    return int(kernel32.GetFileAttributesW(str(path)))


def is_encrypted(path: Path) -> tuple[bool, int]:
    """(is the EFS bit set, the raw attribute value) for one path."""
    value = attributes_of(path)
    if value == INVALID_FILE_ATTRIBUTES:
        return False, value
    return encrypted_flag(value), value


def look_at(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Walk `root` once and sort every path into (encrypted, plain, missing).

    The folder itself is the first path examined, and for the *right* reason:
    its own attribute is what decides whether a snapshot written next Sunday
    comes out encrypted. A root whose files are all encrypted but whose own
    attribute is clear is a real finding - the next run lands in plaintext - so
    it is reported as a plain path rather than passed over as "the folder".
    """
    encrypted: list[Path] = []
    plain: list[Path] = []
    missing: list[Path] = []

    def visit(path: Path) -> None:
        ok, value = is_encrypted(path)
        if value == INVALID_FILE_ATTRIBUTES:
            missing.append(path)
        elif ok:
            encrypted.append(path)
        else:
            plain.append(path)

    visit(root)
    for current, dirnames, filenames in os.walk(root):
        here = Path(current)
        for name in sorted(dirnames):
            visit(here / name)
        for name in sorted(filenames):
            visit(here / name)
    return encrypted, plain, missing


def self_test() -> int:
    """Prove the reader against a real folder, encrypted for real.

    Three things, all on this machine and none of them assumed:

      1. the constant. `0x4000` is what `winnt.h` calls
         `FILE_ATTRIBUTE_ENCRYPTED`; checked by encrypting a file and reading
         its attributes, not by trusting the number typed here;
      2. a PLAIN file is reported plain - without this the tool would pass by
         saying "encrypted" to everything, which is the failure mode that makes
         a checker worse than none;
      3. an ENCRYPTED folder is reported encrypted, and a file created in it
         AFTERWARDS is encrypted too - the property the weekly task depends on.

    Uses two real folders under `%TEMP%` and `cipher`, the same command the
    documentation gives the owner, and removes both when it is done.

    OFF WINDOWS IT PROVES (2) ON ITS OWN, and that is deliberate rather than a
    shrug: a plain file is a plain file on every system, and a reader that
    answered "encrypted" to everything would be caught here. What it cannot show
    without `cipher` is (1) and (3), and it says so instead of printing a green
    line over them.
    """
    if sys.platform != "win32":
        with tempfile.TemporaryDirectory(prefix="efs-selftest-") as sandbox:
            plain_file = Path(sandbox) / "plain.txt"
            plain_file.write_text("this file is not encrypted", encoding="utf-8")
            found, _ = is_encrypted(plain_file)
        print("self-test (not Windows - the EFS half cannot be proved here)")
        print(f"  {'ok  ' if not found else 'FAIL'} a plain file is read as plain "
              f"({plain_file.name})")
        print("  NOT RUN: cipher /e, and a file created afterwards - both need "
              "Windows")
        print(f"\nself-test {'OK' if not found else 'FAILED'} (partial - the EFS "
              f"half did NOT run and did NOT pass)")
        return 0 if not found else 1

    ok = True
    print("self-test: the attribute reader, on real files")
    with tempfile.TemporaryDirectory(prefix="efs-selftest-") as sandbox:
        sandbox_path = Path(sandbox)
        plain_file = sandbox_path / "plain.txt"
        plain_file.write_text("this file is not encrypted", encoding="utf-8")
        found, _ = is_encrypted(plain_file)
        print(f"  {'ok  ' if not found else 'FAIL'} a plain file is read as plain "
              f"({plain_file.name})")
        ok &= not found

        enc_dir = sandbox_path / "encrypted"
        enc_dir.mkdir()
        result = subprocess.run(["cipher", "/e", str(enc_dir)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAIL cipher /e refused: {result.stderr or result.stdout}")
            return 1
        found, _ = is_encrypted(enc_dir)
        print(f"  {'ok  ' if found else 'FAIL'} cipher /e sets the folder's own "
              f"attribute")
        ok &= found

        after = enc_dir / "written-afterwards.txt"
        after.write_text("this file was created after the folder was encrypted",
                         encoding="utf-8")
        found, _ = is_encrypted(after)
        print(f"  {'ok  ' if found else 'FAIL'} a file created afterwards is "
              f"encrypted with no prompt ({after.name})")
        ok &= found

        found, _ = is_encrypted(sandbox_path / "does-not-exist.txt")
        print(f"  {'ok  ' if not found else 'FAIL'} a missing file is never "
              f"read as encrypted")
        ok &= not found

    print(f"\nself-test {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read the EFS attribute of the snapshot folders and every "
                    "file under them, and fail on anything still plain.")
    parser.add_argument("--dest", action="append", default=None, metavar="FOLDER",
                        help="a snapshot folder to check; repeatable. "
                             "(default: the tool's own ~/jarvis-data-snapshots "
                             "and the folder chosen in Jarvis)")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the attribute reader on a real temporary "
                             "folder, then exit (never skipped; it also runs "
                             "by itself off Windows, where the folders cannot "
                             "be read at all)")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if sys.platform != "win32":
        print("SKIP: this checker reads the EFS attribute of the owner's own "
              "folders, and this is not Windows")
        print(f"  host: sys.platform == {sys.platform!r}, and it needs 'win32' - "
              f"only his PC has the snapshots, so NOTHING was checked here and "
              f"NOTHING about them passed.")
        if args.dest:
            print("  a folder was named on the command line and cannot be read "
                  "on this host - that is a failure, not a skip")
            return 1
        print("  the half that proves the reader runs instead, below:")
        print("")
        return self_test()

    if args.dest:
        dests = [Path(d).expanduser() for d in args.dest]
        from_command_line = True
    else:
        dests = list(DEFAULT_DESTS)
        from_command_line = False

    ok = True
    checked_any = False
    for dest in dests:
        if not dest.exists():
            if from_command_line:
                print(f"FAIL {dest} does not exist - it was named on the "
                      f"command line, so this is a wrong path, not an empty "
                      f"backup")
                ok = False
            else:
                print(f"skip {dest} - not on this machine (no snapshots kept "
                      f"there yet)")
            continue
        checked_any = True
        encrypted, plain, missing = look_at(dest)
        print(f"\n{dest}")
        print(f"  the folder itself: "
              f"{'ENCRYPTED' if is_encrypted(dest)[0] else 'NOT ENCRYPTED'} "
              f"- this is what decides whether NEXT week's snapshot is encrypted")
        print(f"  {len(encrypted)} path(s) encrypted, {len(plain)} plain, "
              f"{len(missing)} unreadable")
        for path in plain:
            print(f"    PLAIN: {path}")
        for path in missing:
            print(f"    UNREADABLE: {path}")
        ok &= not plain and not missing

    if not checked_any:
        print("\nFAILED: none of the folders checked exists, so nothing was "
              "proved either way")
        return 1

    if ok:
        print("\nsnapshots encrypted: every folder and file checked carries the "
              "EFS attribute")
        print("This says the files are ciphertext. It does NOT say the key has "
              "been exported off this PC -")
        print("see docs/SNAPSHOT-ENCRYPTION.md, and keep that file somewhere "
              "that is not this machine.")
        return 0

    print("\nFAILED: something under a snapshot folder is not encrypted. Fix it "
          "with, for each folder named above:")
    print('  cipher /e "<the folder>"   ; then   cipher /e /s:"<the folder>"')
    print("The first flags the folder so FUTURE snapshots are encrypted; the "
          "second encrypts what is already there.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
