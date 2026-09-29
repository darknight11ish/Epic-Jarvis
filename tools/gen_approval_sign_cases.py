#!/usr/bin/env python3
"""Writes the signed-approval cases the phone's and the desktop's tests read.

    python3 tools/gen_approval_sign_cases.py            # write both copies
    python3 tools/gen_approval_sign_cases.py --check    # compare only

Phase 2 of pairing (docs/PAIRING-DESIGN.md section 11, docs/JARVIS-API.md
section 91): the phone signs each risky approval with a key in its Keystore,
and the PC checks the signature. The phone (Kotlin), the desktop (which only
reads the device list) and the backend (backend/jarvis_devices.py) must
agree exactly on:

  * the "words hash" - SHA-256 of  id 0x1F action 0x1F title 0x1F text  -
    the phone works it out from what it SHOWED, the PC from the card it
    holds now, and they must match byte for byte;
  * the message the phone signs;
  * the error words.

Every value here is made by running the backend's own code - nothing is
judged by hand - and written into

    jarvis-desktop/tests/fixtures/approval-sign-cases.json
    jarvis-client/app/src/test/resources/contract/approval-sign-cases.json

(byte-identical). backend/test_approval_sign.py fails when either copy is
stale, and checks the two vectors the design was frozen with.

What is in it:
  words_hash    rows (as /api/pending sends them), the id / action / title /
                text the rule takes from each, and the resulting hash
  message       the bytes the phone signs, for one card and one nonce
  signature     a FIXED test key (public key, SPKI base64url), the message it
                signed and the DER signature - so a phone can prove its own
                ECDSA-SHA256 check agrees with the PC's; plus a signature that
                must NOT verify (the same signature, another message)
  titles        the title each of these actions shows (jarvis_card_words)
  sentences     every sentence the PC answers with, by `owner_check` / reason

The test key's private half is NOT here, and is not needed: the signature
was made once (RFC 6979 is not used by Android's Keystore, so a phone's own
signatures differ - that is fine, only verification must agree) and pasted
below. If `cryptography` is installed the generator re-checks the constants
with the backend's own verifier.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_card_words as CW  # noqa: E402
import jarvis_devices as D  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "approval-sign-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "approval-sign-cases.json")
COPIES = (DESKTOP, PHONE)

#: The nonce every vector uses: 16 bytes 00 01 .. 0f, base64url (22 characters).
NONCE = D._b64u(bytes(range(16)))

#: A fixed P-256 test key (never a real one) and a signature it made over
#: MESSAGE_ROW below. Made once with the `cryptography` package.
TEST_PUBLIC_KEY = ("MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEUVw9brnjlrkE0_7Kf1T9zQzB6Ze_N13KUVrQpsO0A19F"
                   "Nr46UPMY-_mlR1kCoiFQK-8NV-CMU7LMClbxfZ-TVA")
TEST_SIGNATURE = ("MEUCIQC4FawpbUKShvfow6CvavQWXUsv-SdxFANFzuHEXc2NbwIgajQhyOXtN3YEAEVKwwmo5CPcyROQ"
                  "73GQNMNcDSmT6GI")

#: The rows the words hash is worked out from. Each is shaped as the wire
#: sends it: `notice.title` (built by the PC) or none, `detail` an object
#: with `text`, plain text, or something else.
ROWS = [
    ("the design's first vector: a notice title and detail.text",
     {"id": "a1", "action": "send_email",
      "notice": {"title": "Jarvis wants to send an email"},
      "detail": {"text": "To: sam@example.com\nSubject: Lunch\n\nSee you at noon.",
                 "to": ["sam@example.com"]}}),
    ("the design's second vector: no detail at all",
     {"id": "b2", "action": "lockdown_off",
      "notice": {"title": "Jarvis wants to turn Lockdown off"}}),
    ("detail is plain text: the text is the detail itself",
     {"id": "c3", "action": "send_email",
      "notice": {"title": "Jarvis wants to send an email"},
      "detail": "Plain words"}),
    ("no notice: the title is the generic line built from the action name",
     {"id": "d4", "action": "pair_device", "detail": {"text": "x"}}),
    ("a blank notice title falls back the same way (the generic line)",
     {"id": "e5", "action": "register_approval_key", "notice": {"title": "  "}}),
    ("a notice title is used exactly as sent, spaces and all",
     {"id": "i9", "action": "send_email", "notice": {"title": " Padded title "},
      "detail": {"text": "x"}}),
    ("a numeric id is its text",
     {"id": 12, "action": "run_shell_on_host", "notice": {"title": "Jarvis wants to run a command"},
      "detail": {"command": "dir"}}),
    ("detail is an object with no text: the text is empty",
     {"id": "f6", "action": "send_email", "notice": {"title": "T"}, "detail": {"to": "a@b.c"}}),
    ("detail.text is not text: empty",
     {"id": "g7", "action": "send_email", "notice": {"title": "T"}, "detail": {"text": 5}}),
    ("non-ASCII words are hashed as UTF-8",
     {"id": "h8", "action": "send_email", "notice": {"title": "Jarvis wants to send an email"},
      "detail": {"text": "Café — 你好 🙂"}}),
]

#: The card the message and signature vectors are for (the first vector).
MESSAGE_ROW = ROWS[0][1]
TITLE_ACTIONS = ["send_email", "register_approval_key", "pair_device", "unretire_shared_key",
                 "lockdown_off", "run_shell_on_host", ""]


def _words_case(name: str, row: dict) -> dict:
    return {"name": name, "row": row, "id": str(row.get("id")).strip(),
            "action": str(row.get("action") or ""), "title": D.card_title(row),
            "text": D.detail_text(row), "words_sha256": D.words_sha256(row)}


def build() -> dict:
    words = D.words_sha256(MESSAGE_ROW)
    message = D.sign_message("a1", "send_email", NONCE, words)
    wrong = D.sign_message("a2", "send_email", NONCE, words)
    if D._crypto() is not None:
        assert D.signature_ok(TEST_PUBLIC_KEY, message, TEST_SIGNATURE) is True, "stale constant"
        assert D.signature_ok(TEST_PUBLIC_KEY, wrong, TEST_SIGNATURE) is False
        assert D.parse_public_key(TEST_PUBLIC_KEY)[1] is None
    return {
        "_comment": ("Generated by tools/gen_approval_sign_cases.py from "
                     "backend/jarvis_devices.py (docs/PAIRING-DESIGN.md section 11, "
                     "docs/JARVIS-API.md section 91). Do not edit by hand."),
        "rule": {
            "words_hash": ("lowercase hex SHA-256 (UTF-8) of id, action, title and text joined "
                           "by the byte 0x1F; title is the notice's title, or - when there is "
                           "none - the generic line the apps show, 'Jarvis wants your OK for \"<the "
                           "action's name as words>\"' (never a known action's fixed phrase); "
                           "text is detail.text "
                           "when detail is an object with text, the detail itself when it is "
                           "plain text, else the empty string"),
            "separator": "0x1f",
            "message": ("the bytes of \"jarvis-approve-v1\", 0x00, id, 0x00, action, 0x00, "
                        "nonce, 0x00, words_sha256 (as ASCII hex)"),
            "magic": D.SIGN_MAGIC.decode("ascii"),
            "signature": "ECDSA over P-256 with SHA-256, DER encoded, base64url without padding",
            "public_key": "SubjectPublicKeyInfo DER of an EC P-256 key, base64url without padding",
            "nonce_bytes": 16, "nonce_chars": len(NONCE), "nonce_seconds": D.NONCE_SECONDS,
            "nonces_per_device": D.NONCES_PER_DEVICE,
        },
        "words_hash": [_words_case(n, r) for n, r in ROWS],
        "message": {"id": "a1", "action": "send_email", "nonce": NONCE, "words_sha256": words,
                    "hex": message.hex()},
        "signature": {
            "public_key": TEST_PUBLIC_KEY,
            "message_hex": message.hex(),
            "sig": TEST_SIGNATURE,
            "verifies": True,
            "other_message_hex": wrong.hex(),
            "other_message_verifies": False,
        },
        "titles": [{"action": a, "title": CW.title_for(a)} for a in TITLE_ACTIONS],
        "sentences": dict(D.SIGN_WORDS),
        "owner_check": ["no_signature", "bad_signature", "no_approval_key"],
    }


def document() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv) -> int:
    doc = document()
    if "--check" in argv:
        bad = [p for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_approval_sign_cases.py")
        if not bad:
            print("approval-sign-cases.json: both copies up to date")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
