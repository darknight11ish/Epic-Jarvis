"""The pairing cases both apps' tests read are current, and right.

    python3 test_pairing_cases.py

QR-code pairing (docs/PAIRING-DESIGN.md) is built three times - here, in
the desktop and on the phone - and must agree exactly on the QR text, the
typed code, the name rule, the sums and the words. tools/gen_pairing_cases.py
makes one table from backend/jarvis_devices.py's own code:

    jarvis-desktop/tests/fixtures/pairing-cases.json
    jarvis-client/app/src/test/resources/contract/pairing-cases.json

WHAT THIS PINS
  1. Both copies are exactly what the generator makes today.
  2. The sums are the design's own test vectors (section 6.2), so a change
     to the backend's sums that the apps did not make fails here.
  3. The word list in jarvis_devices.py is contract/pair-words.txt, word for
     word, and it is the EFF short word list 2's shape: 1,296 words, each
     first three letters unique.

Runs anywhere: standard library only, no owner's files, nothing opened.
"""
import hashlib
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_both_copies_are_current():
    import gen_pairing_cases as G
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8").replace("\r\n", "\n") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_pairing_cases.py)",
              have == doc)


def t_the_design_vectors():
    import gen_pairing_cases as G
    qr, code = G.build()["vectors"]
    want_qr = {"secret": "AAECAwQFBgcICQoLDA0ODw",
               "phone_nonce": "EBESExQVFhcYGRobHB0eHw",
               "pc_nonce": "ICEiIyQlJicoKSorLC0uLw",
               "proof": "H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c",
               "pc_proof": "HkPzmveXlM4XdYo_7TECbY7y3HF1Q4mIXmSxVXxDM80",
               "word_numbers": [330, 679, 1036, 970],
               "collect": "xqsJqE1r6hkgKSjlXeofy2K_C65PQiTjkZgEtpuTCEg"}
    want_code = {"k_hex": "e898e958c53b4f306488422d76cbdd30ba929057ac21bc70fb8ffbaeadff5c2e",
                 "proof": "5cbB9b5oknDpoMN3xu_fPdO5q_GvgR5BwN19a2eXxQ4",
                 "pc_proof": "WM3nmfZziLG4yNxam4xdbLkbCmz34-67h9-Vig0ZdUo",
                 "word_numbers": [1164, 578, 141, 383],
                 "collect": "vGv4Z06RSHN36fZ3dWXisIq7S6ALIBm_EsRAgf7xeqE"}
    for k, v in want_qr.items():
        check(f"method qr: {k} is the design's", qr.get(k) == v, qr.get(k))
    for k, v in want_code.items():
        check(f"method code: {k} is the design's", code.get(k) == v, code.get(k))


def t_the_word_list():
    import jarvis_devices as D
    import gen_pairing_cases as G
    words = G.WORDS_FILE.read_text(encoding="utf-8").split()
    check("jarvis_devices.WORDS is contract/pair-words.txt, word for word",
          tuple(words) == D.WORDS)
    check("1,296 words, each first three letters unique",
          len(words) == 1296 and len({w[:3] for w in words}) == 1296)
    check("the file is one word per line, LF, ending in a newline",
          G.WORDS_FILE.read_bytes() == ("\n".join(words) + "\n").encode("utf-8"))
    table = G.build()["words"]
    check("the cases file carries the list's SHA-256",
          table["sha256"] == hashlib.sha256(G.WORDS_FILE.read_bytes()).hexdigest())


def t_the_tables_say_what_the_design_says():
    import gen_pairing_cases as G
    b = G.build()
    qr = {c["text"]: c for c in b["qr"]}
    check("the design's own QR example parses",
          qr[G.QR[0]]["ok"] is True and qr[G.QR[0]]["parsed"]["port"] == 4719)
    check("a newer version says so, anything else is invalid",
          [c["reason"] for c in b["qr"] if not c["ok"]].count("newer") == 2)
    codes = {c["input"]: c["normalised"] for c in b["codes"]}
    check("the typed code: case, spaces, dashes, O/I/L", codes["k7qm 4txd"] == "K7QM4TXD"
          and codes["O0IL-1234"] == "00111234" and codes["K7QM-4TXU"] is None)
    names = {c["name"]: c["ok"] for c in b["names"]}
    check("names: letters of any script yes; line breaks, RTL override, quotes no",
          names["Émilie's phone"] and names["小米 14"] and not names["Pixel\n9"]
          and not names["Pixel 9‮"] and not names["Pixel \"9\""])
    check("a 40-character name is allowed, 41 is not",
          names["1234567890" * 4] and not names["1234567890" * 4 + "1"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
