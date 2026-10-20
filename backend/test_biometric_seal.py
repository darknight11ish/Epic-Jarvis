"""test_biometric_seal.py - the owner's voice files sealed at rest (audit D2/M2).

    python -B backend/test_biometric_seal.py

Runs anywhere: a temporary folder, an injected 32-byte key provider, no
Credential Manager, no model, no socket. The fixture escape hatch
`JARVIS_TEST_UNSEALED_FIXTURES=1` is what keeps the engine suites' plaintext
fixtures working; this suite tests both modes.

What it proves:
  1. THE ENVELOPE IS THE RULED ONE and it round-trips: a sealed voice file on
     disk holds exactly {"sealed_v": 1, "alg": "AES-256-GCM", "nonce_b64",
     "ciphertext_b64"}; the plaintext (a canary string and raw WAV-like bytes)
     is NOT in the file; reading returns the dict/bytes byte-identically.
  2. TAMPERING AND A WRONG KEY ARE PLAIN REFUSALS: a changed ciphertext, a
     changed nonce, or a different key raises BiometricKeyUnavailable with a
     sentence naming the voice check - never a traceback and never the words.
  3. A LEGACY PLAINTEXT FILE IS READ AND RE-SEALED IN PLACE, once (one-way
     migration), through both the profile path and the wake-verifier path.
  4. A MISSING KEY FAILS CLOSED: a write raises and leaves NO file (or leaves
     an existing file byte-identical); a read raises and migrates nothing.
  5. FIXTURE MODE reads and writes plaintext and migrates nothing, so the
     engine suites are tests of the engine, not of this envelope.
  6. THE WIRED CONSUMERS use it: VoiceProfile.save seals, load_profile opens
     and migrates, and jarvis_wakeword reads a sealed verifier (and migrates a
     legacy plaintext one).

Needs the `cryptography` package (skip those checks without it) and numpy for
the verifier check (skip that one).
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-bioseal-"))
# This suite tests the PRODUCTION behaviour first; each test sets what it needs.
os.environ.pop("JARVIS_TEST_UNSEALED_FIXTURES", None)

import jarvis_voice as V  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
KEY = bytes(range(1, 33))
OTHER_KEY = bytes(range(101, 133))
CANARY = "VOICE-CANARY-4f19-do-not-leak"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


def have_crypto() -> bool:
    return V._seal_aes() is not None


class Provider:
    """The injected key provider: `callable(create: bool) -> 32 raw bytes`."""

    def __init__(self, key=KEY, available=True):
        self.key, self.available = key, available

    def __call__(self, create):
        if not self.available:
            raise V.BiometricKeyUnavailable("this test has no key")
        return self.key


@contextlib.contextmanager
def live(provider):
    saved_env = os.environ.pop("JARVIS_TEST_UNSEALED_FIXTURES", None)
    saved = V.KEY_PROVIDER
    V.KEY_PROVIDER = provider
    try:
        yield
    finally:
        V.KEY_PROVIDER = saved
        if saved_env is not None:
            os.environ["JARVIS_TEST_UNSEALED_FIXTURES"] = saved_env


@contextlib.contextmanager
def fixtures():
    saved = os.environ.get("JARVIS_TEST_UNSEALED_FIXTURES")
    saved_provider = V.KEY_PROVIDER
    os.environ["JARVIS_TEST_UNSEALED_FIXTURES"] = "1"
    V.KEY_PROVIDER = None
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("JARVIS_TEST_UNSEALED_FIXTURES", None)
        else:
            os.environ["JARVIS_TEST_UNSEALED_FIXTURES"] = saved
        V.KEY_PROVIDER = saved_provider


def _path(name="voice-file.json") -> Path:
    folder = Path(tempfile.mkdtemp(prefix="bio-", dir=_TMP))
    return folder / name


def _raised(fn):
    try:
        fn()
    except Exception as exc:      # noqa: BLE001 - the point is to inspect it
        return exc
    return None


def t_the_envelope_is_the_ruled_one_and_round_trips():
    if not have_crypto():
        skip("the envelope round-trips", "the `cryptography` package is not installed")
        return
    with live(Provider()):
        path = _path()
        doc = {"canary": CANARY, "centroid": [1.0, 0.0], "samples": 5}
        V.write_biometric_json(path, doc)
        raw = path.read_bytes()
        envelope = json.loads(raw)
        check("the file on disk is the ruled envelope, exactly",
              sorted(envelope) == ["alg", "ciphertext_b64", "nonce_b64", "sealed_v"],
              sorted(envelope))
        check("... sealed_v 1 and alg AES-256-GCM",
              envelope["sealed_v"] == 1 and envelope["alg"] == "AES-256-GCM", envelope)
        check("... nonce and ciphertext are base64 and the nonce is 12 bytes",
              len(base64.b64decode(envelope["nonce_b64"])) == 12
              and bool(base64.b64decode(envelope["ciphertext_b64"])))
        check("NO plaintext canary in the sealed file", CANARY.encode() not in raw)
        check("... and it is not a JSON object a plain reader could use",
              "centroid" not in raw.decode("utf-8", "replace"))
        check("reading it back returns the dict", V.read_biometric_json(path) == doc)
        # raw bytes (an enrolled WAV, if a consumer can take bytes): same envelope
        wav = b"RIFF" + bytes(range(64)) + b"WAVE" + CANARY.encode()
        bpath = _path("sample.wav")
        V.write_biometric_bytes(bpath, wav)
        check("raw bytes round-trip byte-identically", V.read_biometric_bytes(bpath) == wav)
        check("... and their canary is not on disk, either", CANARY.encode() not in bpath.read_bytes())


def t_tampering_and_a_wrong_key_are_plain_refusals():
    if not have_crypto():
        skip("tamper and wrong-key refusals", "the `cryptography` package is not installed")
        return
    with live(Provider()):
        path = _path()
        V.write_biometric_json(path, {"positives": 6, "canary": CANARY})
        envelope = json.loads(path.read_bytes())
        # 1. a changed ciphertext
        cipher = bytearray(base64.b64decode(envelope["ciphertext_b64"]))
        cipher[0] ^= 0xFF
        tampered = dict(envelope, ciphertext_b64=base64.b64encode(bytes(cipher)).decode("ascii"))
        path.write_text(json.dumps(tampered), encoding="utf-8")
        exc = _raised(lambda: V.read_biometric_json(path))
        check("a changed ciphertext raises BiometricKeyUnavailable",
              isinstance(exc, V.BiometricKeyUnavailable), repr(exc))
        check("... with a plain sentence naming the voice check",
              exc is not None and "voice check refuses" in str(exc), str(exc))
        # 2. a changed nonce
        path.write_text(json.dumps(dict(envelope, nonce_b64=base64.b64encode(b"0" * 12).decode())),
                        encoding="utf-8")
        check("a changed nonce is refused too",
              isinstance(_raised(lambda: V.read_biometric_json(path)),
                         V.BiometricKeyUnavailable))
        # 3. a different key
        path.write_text(json.dumps(envelope), encoding="utf-8")
        saved = V.KEY_PROVIDER
        V.KEY_PROVIDER = Provider(OTHER_KEY)
        try:
            check("a DIFFERENT key cannot open it",
                  isinstance(_raised(lambda: V.read_biometric_json(path)),
                             V.BiometricKeyUnavailable))
        finally:
            V.KEY_PROVIDER = saved


def t_a_legacy_plaintext_profile_is_migrated_in_place_once():
    if not have_crypto():
        skip("legacy plaintext migration", "the `cryptography` package is not installed")
        return
    with live(Provider()):
        path = _path("owner.json")
        legacy = {"centroid": [1.0, 0.0], "samples": 5, "canary": CANARY}
        path.write_text(json.dumps(legacy), encoding="utf-8")
        before = path.read_bytes()
        profile = V.load_profile(path)
        after = path.read_bytes()
        check("a legacy plaintext voice template still loads", profile is not None
              and getattr(profile, "samples", 0) == 5, profile)
        check("... and the file is now THE SEALED ENVELOPE", after != before
              and b'"sealed_v"' in after and json.loads(after)["sealed_v"] == 1)
        check("... the old plaintext canary is gone from it", CANARY.encode() not in after)
        snapshot = after
        check("... a second read migrates nothing again (one-way, once)",
              V.load_profile(path) is not None and path.read_bytes() == snapshot)
        # a sealed file must not be re-migrated into a different envelope
        check("the envelope is stable across reads",
              json.loads(path.read_bytes())["ciphertext_b64"]
              == json.loads(snapshot)["ciphertext_b64"])


def t_a_missing_key_writes_nothing_and_refuses_reads():
    if not have_crypto():
        skip("missing-key fail-closed", "the `cryptography` package is not installed")
        return
    with live(Provider(available=False)):
        target = _path("must-not-exist.json")
        exc = _raised(lambda: V.write_biometric_json(target, {"canary": CANARY}))
        check("a write with no key raises BiometricKeyUnavailable",
              isinstance(exc, V.BiometricKeyUnavailable), repr(exc))
        check("... and writes NO file at all", not target.exists(), target)
        legacy = _path("legacy.json")
        legacy.write_text(json.dumps({"samples": 3}), encoding="utf-8")
        before = legacy.read_bytes()
        exc = _raised(lambda: V.read_biometric_json(legacy))
        check("a read of a legacy plaintext file refuses when the key is unavailable",
              isinstance(exc, V.BiometricKeyUnavailable), repr(exc))
        check("... and migrates NOTHING (the file is byte-identical)", legacy.read_bytes() == before)
    # an existing sealed file with the key gone
    if have_crypto():
        with live(Provider()):
            sealed = _path("sealed.json")
            V.write_biometric_json(sealed, {"samples": 1})
            sealed_bytes = sealed.read_bytes()
        with live(Provider(available=False)):
            check("a sealed file cannot be read when the key is gone",
                  isinstance(_raised(lambda: V.read_biometric_json(sealed)),
                             V.BiometricKeyUnavailable))
            check("... and the sealed file is untouched", sealed.read_bytes() == sealed_bytes)


def t_fixture_mode_reads_and_writes_plaintext_and_migrates_nothing():
    with fixtures():
        path = _path("fixture-owner.json")
        legacy = {"centroid": [1.0, 0.0], "samples": 5}
        path.write_text(json.dumps(legacy), encoding="utf-8")
        before = path.read_bytes()
        check("fixture mode reads a plaintext fixture without a key",
              V.read_biometric_json(path) == legacy)
        check("... and does NOT migrate it", path.read_bytes() == before)
        V.write_biometric_json(path, {"centroid": [1.0, 0.0], "samples": 9,
                                      "canary": CANARY})
        after = path.read_bytes()
        check("fixture mode WRITES plaintext", CANARY.encode() in after
              and b'"sealed_v"' not in after)
        check("... which a plaintext reader can still load", V.load_profile(path) is not None)


def t_the_wired_consumers_use_the_envelope():
    if not have_crypto():
        skip("wired consumers", "the `cryptography` package is not installed")
        return
    try:
        import numpy as np  # noqa: F401
        import jarvis_wakeword as W
    except Exception as exc:
        skip("wired consumers", f"jarvis_wakeword is not installed ({type(exc).__name__})")
        return
    with live(Provider()):
        # VoiceProfile.save seals; load_profile opens it
        prof_path = _path("profile.json")
        V.VoiceProfile(centroid=[1.0, 0.0], samples=5).save(prof_path)
        check("VoiceProfile.save writes the sealed envelope",
              json.loads(prof_path.read_bytes()).get("sealed_v") == 1)
        check("... and load_profile opens it", V.load_profile(prof_path) is not None)
        # wake verifier: sealed file is read by the real wakeword reader
        ver_path = _path("wake-verifier.json")
        verifier = {"version": W.VERIFIER_VERSION, "positives": 6, "b": 0.0,
                    "w": [0.0] * (W.EMB_WINDOW * 96)}
        V.write_biometric_json(ver_path, verifier)
        check("the verifier file on disk is sealed",
              json.loads(ver_path.read_bytes()).get("sealed_v") == 1)
        loaded = W._read_verifier(ver_path)
        check("jarvis_wakeword reads the sealed verifier", loaded is not None
              and loaded.positives == 6, loaded)
        # a legacy plaintext verifier is migrated by the wakeword reader
        legacy = _path("wake-verifier-legacy.json")
        legacy.write_text(json.dumps(verifier), encoding="utf-8")
        loaded = W._read_verifier(legacy)
        check("a legacy plaintext verifier still loads", loaded is not None)
        check("... and was migrated to the envelope by that read",
              json.loads(legacy.read_bytes()).get("sealed_v") == 1)


def t_the_atomic_write_fsyncs_the_temp_file_before_the_swap():
    """#600 (the 2026-10-20 audit): .tmp + os.replace is only half the promise.

    A crash after the rename but before the bytes reach the disk can leave an
    empty or partial file where the owner's print used to be. The write must
    flush AND fsync the temp file before replacing it. The swap itself is
    recorded here too, so the shape cannot drift back to write_bytes."""
    if not have_crypto():
        skip("atomic write fsync", "the `cryptography` package is not installed")
        return
    import unittest.mock as mock
    with live(Provider()):
        path = _path("fsync.json")
        calls = []
        real_replace, real_fsync = os.replace, os.fsync

        def fake_fsync(fd):
            calls.append(("fsync", fd))
            return real_fsync(fd)

        def fake_replace(src, dst):
            calls.append(("replace", str(src), str(dst)))
            return real_replace(src, dst)

        with mock.patch("os.fsync", side_effect=fake_fsync), \
                mock.patch("os.replace", side_effect=fake_replace):
            V.write_biometric_json(path, {"samples": 1})
        kinds = [c[0] for c in calls]
        check("the temp file is fsynced BEFORE it is renamed over the real one",
              kinds == ["fsync", "replace"], calls)
        check("... the rename's source is the .tmp sibling",
              calls[1][1].endswith(".tmp"), calls)
        check("... and no .tmp copy is left behind",
              not path.with_name(path.name + ".tmp").exists())


def t_an_interrupted_write_or_replace_leaves_the_old_file():
    """A failed swap must refuse, not report success: the old sealed file stays
    byte-identical and the half-written .tmp is removed (it is biometric too)."""
    if not have_crypto():
        skip("interrupted atomic write", "the `cryptography` package is not installed")
        return
    import unittest.mock as mock
    with live(Provider()):
        path = _path("interrupted.json")
        V.write_biometric_json(path, {"samples": 1})
        before = path.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("in use by another process")):
            exc = _raised(lambda: V.write_biometric_json(path, {"samples": 2}))
        check("a failed replace raises instead of claiming the write happened",
              isinstance(exc, OSError), repr(exc))
        check("... the old sealed file is byte-identical", path.read_bytes() == before)
        check("... and the .tmp copy is gone", not path.with_name(path.name + ".tmp").exists())
        # An interruption during the durable write itself (fsync fails) is the
        # same contract: nothing is renamed, the old file still opens.
        with mock.patch("os.fsync", side_effect=OSError("disk went away")):
            exc = _raised(lambda: V.write_biometric_json(path, {"samples": 3}))
        check("an interrupted fsync also refuses", isinstance(exc, OSError), repr(exc))
        check("... leaving the old file untouched and readable",
              path.read_bytes() == before and V.read_biometric_json(path)["samples"] == 1)
        check("... with no .tmp hair left", not path.with_name(path.name + ".tmp").exists())


def t_a_legacy_migration_uses_the_durable_atomic_swap():
    """The first-read migration (the one that runs on the owner's real files)
    goes through the same .tmp/fsync/replace path, not a direct write."""
    if not have_crypto():
        skip("migration atomic swap", "the `cryptography` package is not installed")
        return
    import unittest.mock as mock
    with live(Provider()):
        path = _path("owner.json")
        path.write_text(json.dumps({"centroid": [1.0, 0.0], "samples": 5}), encoding="utf-8")
        calls = []
        real_replace = os.replace

        def fake_replace(src, dst):
            calls.append((str(src), str(dst)))
            return real_replace(src, dst)

        with mock.patch("os.replace", side_effect=fake_replace):
            profile = V.load_profile(path)
        check("a legacy plaintext print still loads", profile is not None)
        check("... and the one-way migration used a .tmp rename",
              len(calls) == 1 and calls[0][0].endswith(".tmp")
              and calls[0][1] == str(path), calls)
        check("... so the file is now the sealed envelope",
              json.loads(path.read_bytes()).get("sealed_v") == 1)


if __name__ == "__main__":
    print(f"voice module: {V.__file__}")
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    try:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
