"""test_supply_chain.py - the supply-chain half of the 2026-10-18 security audit.

    python3 backend/test_supply_chain.py

WHAT IT PROVES, and why each check is here:

1. `scripts/verify_minisign.py` really verifies a minisign signature, in both
   formats the app accepts: the legacy one ("Ed") and the prehashed one ("ED",
   what current minisign/tauri signing writes). The two fixtures are the
   minisign project's own published test vectors, the same ones the
   minisign-verify crate uses; "test" verifies and "Test" is refused.
2. `scripts/update-jarvis.ps1` calls that verifier BEFORE the downloaded
   installer can run, never with the older "signature not checked" path, and no
   longer downloads and runs an unverified source archive.
3. `scripts/apply-patches.ps1` installs `backend/requirements.lock`, not the
   loose `requirements.txt`: the command in the script asks pip for
   `--require-hashes` on the lock. A tiny local wheel with a wrong hash is
   refused by that pip mode with the "HASHES" sentence - the fail-closed shape
   the change relies on - and the same wheel with its real hash installs.

No network, no real installer and no real model download is used.
"""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VERIFIER = REPO / "scripts" / "verify_minisign.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# The minisign project's test vectors, as used by minisign-verify 0.2.5's own
# tests (cargo registry: minisign-verify-0.2.5/src/lib.rs).
_MINISIGN_PUBKEY = "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3"
_LEGACY_SIG = (
    "untrusted comment: signature from minisign secret key\n"
    "RWQf6LRCGA9i59SLOFxz6NxvASXDJeRtuZykwQepbDEGt87ig1BNpWaVWuNrm73YiIiJbq71Wi+dP9eKL8OC351vwIasSSbXxwA=\n"
    "trusted comment: timestamp:1555779966\tfile:test\n"
    "QtKMXWyYcwdpZAlPF7tE2ENJkRd1ujvKjlj1m9RtHTBnZPa5WKU5uWRs5GoP5M/VqE81QFuMKI5k/SfNQUaOAA==")
_PREHASHED_SIG = (
    "untrusted comment: signature from minisign secret key\n"
    "RUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\n"
    "trusted comment: timestamp:1556193335\tfile:test\n"
    "y/rUw2y8/hOUYjZU71eHp/Wo1KZ40fGy2VJEDl34XMJM+TX48Ss/17u3IvIfbVR1FkZZSNCisQbuQY+bHwhEBg==")


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _verifier_run(tmp: Path, content: bytes, signature: str) -> tuple:
    """(exit code, stdout+stderr)."""
    installer = tmp / "installer.exe"
    installer.write_bytes(content)
    pubkey = _b64("untrusted comment: minisign public key E7620F1842B4E81F\n"
                  + _MINISIGN_PUBKEY + "\n")
    r = subprocess.run(
        [sys.executable, str(VERIFIER), "--pubkey-base64", pubkey,
         "--signature-base64", _b64(signature), "--file", str(installer)],
        capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def t_minisign_verifier_accepts_both_formats_and_refuses_a_changed_file():
    with tempfile.TemporaryDirectory(prefix="jarvis-minisign-") as d:
        tmp = Path(d)
        for label, sig in (("legacy", _LEGACY_SIG), ("prehashed", _PREHASHED_SIG)):
            code, out = _verifier_run(tmp, b"test", sig)
            check(f"minisign {label} signature verifies the signed bytes",
                  code == 0 and "verified" in out, (code, out))
            code, out = _verifier_run(tmp, b"Test", sig)
            check(f"minisign {label}: one changed byte is refused, in plain words",
                  code != 0 and "did not verify" in out and "not run" in out,
                  (code, out))
        sig_lines = _LEGACY_SIG.splitlines()
        # Change one byte inside the base64 signature itself (not a comment).
        sig_lines[1] = sig_lines[1][:20] + ("A" if sig_lines[1][20] != "A" else "B") + sig_lines[1][21:]
        code, out = _verifier_run(tmp, b"test", "\n".join(sig_lines))
        check("a tampered signature is refused too", code != 0 and "MINISIGN:" in out,
              (code, out))


def t_update_script_verifies_before_it_can_run_anything():
    text = (REPO / "scripts" / "update-jarvis.ps1").read_text(encoding="utf-8")
    check("update-jarvis.ps1 calls the minisign verifier",
          "verify_minisign.py" in text and "Test-InstallerSignature" in text)
    call = text.find("Test-InstallerSignature $dest $Release.Signature $Repo")
    install = text.find("Invoke-SilentInstaller $dest")
    check("the verifier is called BEFORE the installer can run",
          0 <= call < install, (call, install))
    check("no path still says the signature is 'NOT checked here'",
          "NOT checked here" not in text)
    check("the unverified main.zip source download is gone",
          "archive/refs/heads/main.zip" not in text and "Expand-Archive" not in text
          and "source.zip" not in text)


def _tiny_wheel(folder: Path) -> Path:
    """A real, installable pure-Python wheel, so pip can hash it offline."""
    wheel = folder / "jarvis_lock_probe-1.0-py3-none-any.whl"
    files = {
        "jarvis_lock_probe/__init__.py": "VALUE = 1\n",
        "jarvis_lock_probe-1.0.dist-info/METADATA":
            "Metadata-Version: 2.1\nName: jarvis-lock-probe\nVersion: 1.0\n",
        "jarvis_lock_probe-1.0.dist-info/WHEEL":
            "Wheel-Version: 1.0\nGenerator: supply-chain-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        "jarvis_lock_probe-1.0.dist-info/RECORD": "",
    }
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return wheel


def _pip_install(wheel_dir: Path, lock: Path, target: Path) -> tuple:
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
           "--no-index", "--find-links", str(wheel_dir), "--require-hashes",
           "--target", str(target), "-r", str(lock)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return r.returncode, (r.stdout + r.stderr)


def t_the_hash_locked_list_is_what_the_patcher_installs():
    text = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 installs from requirements.lock with --require-hashes",
          "pip install --disable-pip-version-check --require-hashes -r $lock" in text
          and "$lock = Join-Path $PatchDir 'requirements.lock'" in text)
    check("... and no pip command installs the loose requirements.txt by name",
          "pip install --disable-pip-version-check -r $reqs" not in text)

    if subprocess.run([sys.executable, "-m", "pip", "--version"],
                     capture_output=True).returncode != 0:
        check("pip is not installed here, so the hash-mode refusal cannot be tested", False)
        return
    with tempfile.TemporaryDirectory(prefix="jarvis-lock-") as d:
        root = Path(d)
        wheel_dir = root / "wheels"
        wheel_dir.mkdir()
        wheel = _tiny_wheel(wheel_dir)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        lock = root / "requirements.lock"
        target = root / "target"
        lock.write_text(f"jarvis-lock-probe==1.0 --hash=sha256:{digest}\n", encoding="utf-8")
        code, out = _pip_install(wheel_dir, lock, target)
        check("a lock whose hash matches installs the wheel",
              code == 0 and (target / "jarvis_lock_probe" / "__init__.py").is_file(),
              (code, out[-600:]))
        bad = root / "bad.lock"
        bad.write_text("jarvis-lock-probe==1.0 --hash=sha256:" + "0" * 64 + "\n",
                       encoding="utf-8")
        bad_target = root / "bad-target"
        code, out = _pip_install(wheel_dir, bad, bad_target)
        check("a lock whose hash does NOT match is refused, in plain words",
              code != 0 and "HASHES" in out.upper() and
              not (bad_target / "jarvis_lock_probe" / "__init__.py").is_file(),
              (code, out[-600:]))


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:
                traceback.print_exc()
                check(f"{name} raised {type(exc).__name__}: {exc}", False)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
