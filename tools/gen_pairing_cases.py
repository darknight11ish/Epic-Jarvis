#!/usr/bin/env python3
"""Writes the pairing cases both apps' tests read, and checks them.

    python3 tools/gen_pairing_cases.py            # write both copies
    python3 tools/gen_pairing_cases.py --check    # compare only

QR-code pairing with a key per device (docs/PAIRING-DESIGN.md, the owner's
"build it now" of 2026-09-28) is built three times - the backend
(backend/jarvis_devices.py), the desktop (Rust and the settings page) and
the phone (Kotlin). Every rule the three must agree on exactly is made HERE,
by running the backend's own code - nothing is judged by hand - and written
into

    jarvis-desktop/tests/fixtures/pairing-cases.json
    jarvis-client/app/src/test/resources/contract/pairing-cases.json

(byte-identical). backend/test_pairing_cases.py fails when either copy is
stale, and checks the sums against the design's own test vectors (6.2).

What is in it:
  vectors    the sums (proof, pc_proof, word numbers, collect) for method
             "qr" and method "code", from the design's fixed inputs
  qr         QR texts, valid and not, and what the strict parser makes of
             each (design 8.4)
  codes      typed codes and what they normalise to, or null (8.5)
  names      device names and whether the name rule allows each (section 4;
             length is counted in Unicode code points, not UTF-16 units)
  addresses  what the desktop may put in the QR code (6.1) - the phone's own
             rule: the shared own-networks rule AND a .ts.net or .nord name
  keys       the device key's shape and texts holding one, for the
             scrubbers (8.6): each app's scrubber must remove `secret`
  words      the word list's size and SHA-256 (contract/pair-words.txt is
             the one list; both apps copy it)
  sentences  every sentence the apps show for pairing and devices
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_devices as D  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "pairing-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "pairing-cases.json")
COPIES = (DESKTOP, PHONE)
WORDS_FILE = ROOT / "contract" / "pair-words.txt"

#: The design's fixed inputs (docs/PAIRING-DESIGN.md 6.2).
SECRET = bytes(range(0x00, 0x10))
PAIR_ID = "00112233445566ff"
PHONE_NONCE = D._b64u(bytes(range(0x10, 0x20)))
PC_NONCE = D._b64u(bytes(range(0x20, 0x30)))
NAME = "Pixel 9"
CODE = "K7QM4TXD"

GOOD_SECRET = D._b64u(SECRET)
QR = [
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/my-pc.nord/1/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/a.b.ts.net/65535/{PAIR_ID}/{GOOD_SECRET}/0000000000",
    # newer
    f"jarvis-pair:2/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:10/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    # not the shape
    "",
    "jarvis-pair:1",
    f"JARVIS-PAIR:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f" jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600 ",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600/",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}",
    f"jarvis-pair:x/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:01/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/Jarvis-PC.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net./4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/192.168.1.20/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/100.101.2.3/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.local/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/evil.com/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/desktop.ts.net.evil.com/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/evil@x.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/04719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/0/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/65536/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/+4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566FF/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566f/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}A/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET[:-1]}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}=/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/AAECAwQFBgcICQoLDA0OD+/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/179000060",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/17900006000",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/179000060x",
    f"jarvis-pair:1//4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600?x=1",
    f"jarvis-pair:1/jarvis pc.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
    f"https://jarvis-pc.tail1234.ts.net/4719/{PAIR_ID}/{GOOD_SECRET}/1790000600",
]

CODES = ["K7QM-4TXD", "K7QM4TXD", "k7qm-4txd", "k7qm 4txd", " K7QM-4TXD ", "K7QM--4TXD",
         "O0IL-1234", "oOiI-lL00", "ABCD-EFGH", "0000-0000", "ZZZZ-ZZZZ",
         "K7QM-4TX", "K7QM-4TXDD", "K7QM-4TXU", "K7QM_4TXD", "K7QM.4TXD", "", "--------",
         "K7QM-4TXÐ", "Ｋ7QM-4TXD"]

NAMES = ["Pixel 9", "P", "Galaxy S24 Ultra", "Pixel-9_(work).2", "Owner's phone",
         "Émilie's phone", "小米 14", "١٢٣", "1234567890" * 4,
         " ", "", "1234567890" * 4 + "1", "Pixel\n9", "Pixel\t9", "Pixel 9‮",
         "Pixel \"9\"", "Pixel: 9", "Pixel/9", "Pixel 9!", "Pixel​9", "Pixel 9 \U0001f4f1",
         "é", "\U00020000 phone"]

ADDRESSES = ["jarvis-pc.tail1234.ts.net", "JARVIS-PC.TAIL1234.TS.NET",
             "jarvis-pc.tail1234.ts.net.", "my-pc.nord", "a.b.ts.net",
             "192.168.1.20", "100.101.2.3", "jarvis-pc.local", "jarvis-pc", "localhost",
             "127.0.0.1", "evil.com", "abc123.ngrok-free.app", "ts.net", "evilts.net",
             "desktop.ts.net.evil.com", "http://jarvis-pc.tail1234.ts.net",
             "jarvis-pc.tail1234.ts.net:4719", "me@jarvis-pc.tail1234.ts.net",
             "jarvis pc.ts.net", "", "a..ts.net", ".ts.net", "-a.ts.net"]

KEY_SECRET = "Ab_-0123456789abcdefghijklmnopqrstuvwxyzABC"


def _vector(method: str) -> dict:
    k = SECRET if method == "qr" else D.code_key(CODE)
    ref = PAIR_ID if method == "qr" else "-"
    t = D.transcript(method, ref, PHONE_NONCE, NAME)
    out = {"method": method, "pair_id": PAIR_ID, "phone_nonce": PHONE_NONCE,
           "pc_nonce": PC_NONCE, "name": NAME}
    if method == "qr":
        out["secret"] = GOOD_SECRET
    else:
        out["code"] = CODE
        out["k_hex"] = k.hex()
    out.update(proof=D.claim_proof(k, t), pc_proof=D.pc_proof(k, t, PC_NONCE),
               word_numbers=D.word_numbers(k, t, PC_NONCE),
               collect=D.collect_proof(k, PAIR_ID, PHONE_NONCE))
    return out


def _qr(text: str) -> dict:
    try:
        got = D.parse_qr(text)
    except D.QrError as exc:
        return {"text": text, "ok": False, "reason": exc.reason}
    return {"text": text, "ok": True,
            "parsed": {"host": got["host"], "port": got["port"], "pair_id": got["pair_id"],
                       "secret": D._b64u(got["secret"]), "expires": got["expires"]}}


def build() -> dict:
    key = f"jdk1.d3f9a1c2e.{KEY_SECRET}"
    words = WORDS_FILE.read_bytes()
    return {
        "_comment": ("Generated by tools/gen_pairing_cases.py from backend/jarvis_devices.py "
                     "(docs/PAIRING-DESIGN.md). Do not edit by hand."),
        "session_seconds": D.SESSION_SECONDS,
        "tries": D.TRIES,
        "code_alphabet": D.CODE_ALPHABET,
        "name_max": D.NAME_MAX,
        "phone_suffixes": list(D.PHONE_SUFFIXES),
        "vectors": [_vector("qr"), _vector("code")],
        "qr": [_qr(t) for t in QR],
        "codes": [{"input": c, "normalised": D.normalise_code(c),
                   "shown": (D.show_code(D.normalise_code(c)) if D.normalise_code(c) else None)}
                  for c in CODES],
        "names": [{"name": n, "ok": D.name_ok(n), "code_points": len(n)} for n in NAMES],
        "addresses": [{"address": a, "host": D.phone_host(a),
                       "error": None if D.phone_host(a) else D.address_problem(a)}
                      for a in ADDRESSES],
        "keys": {
            "pattern": D.KEY_PATTERN,
            "prefix": D.KEY_PREFIX,
            "cases": [
                {"text": key, "secret": KEY_SECRET},
                {"text": f"X-Jarvis-Token: {key}", "secret": KEY_SECRET},
                {"text": f"token={key}&x=1", "secret": KEY_SECRET},
                {"text": f"{{\"token\": \"{key}\"}}", "secret": KEY_SECRET},
                {"text": f"saved {key}.", "secret": KEY_SECRET},
            ],
            "not_keys": [f"jdk1.d3f9a1c2e.{KEY_SECRET[:-1]}", f"jdk1.d3f9a1c2.{KEY_SECRET}",
                         f"jdk2.d3f9a1c2e.{KEY_SECRET}", f"jdk1.D3F9A1C2E.{KEY_SECRET}"],
        },
        "words": {"file": "contract/pair-words.txt", "count": len(D.WORDS),
                  "sha256": hashlib.sha256(words).hexdigest(),
                  "first": D.WORDS[0], "last": D.WORDS[-1], "separator": " · "},
        "sentences": {
            "pc_only": D.PC_ONLY,
            "card_title": D.CARD_TITLE,
            "phone": dict(D.PHONE_WORDS),
            "key": dict(D.KEY_WORDS),
            "session": dict(D.SESSION_WORDS),
            "devices": dict(D.DEVICES_WORDS),
            "address_off_network": D.ADDRESS_OFF_NETWORK,
            "address_not_a_name": D.ADDRESS_NOT_A_NAME,
        },
    }


def document() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv) -> int:
    doc = document()
    if "--check" in argv:
        bad = [p for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_pairing_cases.py")
        if not bad:
            print("pairing-cases.json: both copies up to date")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
