#!/usr/bin/env python3
"""Verify one downloaded file against a minisign signature - before it runs.

    python scripts/verify_minisign.py --pubkey-base64 <b64> \
        --signature-base64 <b64> --file <path-to-installer>

WHY THIS EXISTS

`scripts/update-jarvis.ps1` downloads the published desktop installer and runs
it silently. The app itself verifies the minisign signature before installing
(tauri-plugin-updater, pubkey in tauri.conf.json), but Windows PowerShell 5.1
has no minisign verifier and the Tauri CLI has no `signer verify` command, so
that script used to run whatever the release page served. The security audit of
2026-10-18 (supply chain H-2) made that download verify first: this small
helper is the verifier, using the same public key the app is built with, and it
matches the minisign-verify crate the app uses:

  * a minisign signature is Ed25519 over the file's BLAKE2b-512 digest
    (algorithm "ED") or, for older signatures, over the raw bytes ("Ed");
  * the trusted comment is covered by a second Ed25519 signature over the
    signature bytes followed by the comment (without its "trusted comment: "
    prefix);
  * the signature's 8-byte key id must match the public key's.

The signature in `latest.json` is base64 of the four-line `.sig` file (as
tauri-plugin-updater stores it); the configured pubkey is base64 of a public-key
file (`untrusted comment` line plus the base64 key).

Exit codes: 0 verified (prints one line), 1 refused/unverifiable (prints the
reason in plain words), 2 bad arguments. This script never writes a file.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import sys
from pathlib import Path

TRUSTED_PREFIX = "trusted comment: "
BLOCK = 1024 * 1024


def _die(msg: str) -> int:
    print(f"MINISIGN: {msg}", file=sys.stderr)
    return 1


def _b64(text: str, what: str) -> bytes:
    try:
        return base64.b64decode("".join(str(text).split()), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"the {what} is not valid base64")


def _decode_pubkey(configured: str) -> tuple:
    """(key_id, raw public key) from the configured base64 string."""
    blob = _b64(configured, "configured public key")
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("the configured public key is not the app's minisign key")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("the configured public key is empty")
    # The config value is base64 of a minisign public-key file: an untrusted
    # comment line, then the key line. Accept a bare key line too.
    key_line = lines[1] if len(lines) > 1 and lines[0].startswith("untrusted comment:") else lines[-1]
    raw = _b64(key_line, "public key")
    if len(raw) != 42:
        raise ValueError("the configured public key is not a minisign public key")
    if raw[:2] not in (b"Ed", b"ED"):
        raise ValueError("the configured public key names an unsupported signature algorithm")
    return raw[2:10], raw[10:42]


def _decode_signature(configured: str) -> tuple:
    """(algorithm, key_id, signature, trusted_comment, global_signature)."""
    blob = _b64(configured, "published signature")
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("the published signature is not a minisign signature")
    lines = text.splitlines()
    if len(lines) < 4:
        raise ValueError("the published signature is incomplete")
    raw = _b64(lines[1], "signature")
    if len(raw) != 74:
        raise ValueError("the published signature is not a minisign signature")
    trusted = lines[2]
    if not trusted.startswith(TRUSTED_PREFIX):
        raise ValueError("the published signature has no trusted comment")
    global_sig = _b64(lines[3], "signature's trusted-comment signature")
    if len(global_sig) != 64:
        raise ValueError("the published signature is not a minisign signature")
    algorithm = raw[:2]
    if algorithm not in (b"Ed", b"ED"):
        raise ValueError("the published signature names an unsupported algorithm")
    return algorithm, raw[2:10], raw[10:74], trusted[len(TRUSTED_PREFIX):], global_sig


def verify(pubkey_b64: str, signature_b64: str, file_path: str) -> str:
    """Verified: one plain line. Refused: ValueError with the reason.

    Never a partial success: every check below must pass.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception:
        raise ValueError(
            "the update cannot be verified because Python's `cryptography` package is "
            "not installed on this PC; nothing was run. Use Jarvis's own "
            "Settings -> Updates, or run this script with -FromSource")

    path = Path(file_path)
    if not path.is_file():
        raise ValueError("the downloaded file is missing, so nothing was verified")
    key_id, raw_key = _decode_pubkey(pubkey_b64)
    algorithm, sig_key_id, signature, trusted, global_sig = _decode_signature(signature_b64)
    if key_id != sig_key_id:
        raise ValueError("the published signature was made with a different key than the app's")
    if algorithm == b"ED":
        hasher = hashlib.blake2b(digest_size=64)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(BLOCK)
                if not chunk:
                    break
                hasher.update(chunk)
        message = hasher.digest()
    else:
        message = path.read_bytes()
    key = Ed25519PublicKey.from_public_bytes(raw_key)
    try:
        key.verify(signature, message)
        key.verify(global_sig, signature + trusted.encode("utf-8"))
    except InvalidSignature:
        raise ValueError(
            "the downloaded file's minisign signature did not verify, so it was not "
            "run. The release page may be serving a file that is not the signed one")
    except Exception as exc:
        raise ValueError(f"the downloaded file could not be verified ({type(exc).__name__})")
    return f"MINISIGN: verified {path.name} against key {key_id.hex()}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify a downloaded file's minisign signature.")
    ap.add_argument("--pubkey-base64", required=True)
    ap.add_argument("--signature-base64", required=True)
    ap.add_argument("--file", required=True)
    args = ap.parse_args(argv)
    try:
        print(verify(args.pubkey_base64, args.signature_base64, args.file))
    except ValueError as exc:
        return _die(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
