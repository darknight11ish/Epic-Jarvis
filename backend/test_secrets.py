"""test_secrets.py - finding secrets in the words read from a screenshot
(jarvis_secrets.py), and working out the black boxes.

    python3 backend/test_secrets.py

What it proves (screen safety, the owner's "all three", 2026-09-29):
  - things that ARE secrets are found: a token, a private key (also one cut
    off before its end), a card number, an IBAN, a crypto wallet, an email
    address, an IP address, a value written next to "Password:" or "PIN:";
  - things that only LOOK like them are left alone: a 16-digit number that
    fails the card check digit, an IBAN or wallet with a wrong check, dots or
    stars after "Password:", "Password: required", ordinary sentences full of
    the words "key", "token", "access" and "author";
  - a secret that runs over several lines is hidden on EVERY line it touches
    (a wrapped token, a card number with its groups on two lines, a key);
  - every word that overlaps a secret, even by a letter, is hidden whole;
  - the boxes: one solid box per run of words per line, the words' own
    positions grown a little, never fewer than the words;
  - fail closed: a screen with too much text, rule data that will not load,
    a check that takes too long, and a hidden word with no position all end
    in "not checked" / "no picture", never in "carry on";
  - the text handed on says "[hidden]", not the secret; text with nothing to
    hide comes back exactly as it was.
Every "secret" here is made up.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_secrets.py", "jarvis_secret_rules.py")

import jarvis_secrets as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


CHAR_W, LINE_H, GAP = 8.0, 16.0, 8.0


def screen(*lines, top=100.0):
    """Lines of text as the reader gives them: each word with a position.
    Words are CHAR_W wide per character, a GAP apart; lines LINE_H + 4 apart."""
    out = []
    for i, text in enumerate(lines):
        x, words = 20.0, []
        for w in text.split():
            words.append({"text": w, "left": x, "top": top + i * (LINE_H + 4),
                          "width": len(w) * CHAR_W, "height": LINE_H})
            x += len(w) * CHAR_W + GAP
        out.append({"text": text, "words": words})
    return out


def hidden(*lines):
    return S.redact(screen(*lines))


TOKEN = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5"          # 40 characters, made up


def t_found():
    r = hidden("my token is " + TOKEN + " thanks")
    check("a token is hidden and the words around it are not",
          r.text == "my token is [hidden] thanks" and r.hidden == 1, r.text)
    check("... and the text never holds the secret", TOKEN not in r.text)
    r = hidden("api_key = 'kJ8dLq2Zx9Vw3RtY7uBnM4pAs6DfGh1C'")
    check("a value after 'api_key =' is hidden (the broad rule)", "[hidden]" in r.text
          and "kJ8dLq2Zx9Vw3RtY7uBnM4pAs6DfGh1C" not in r.text, r.text)
    r = hidden("-----BEGIN RSA PRIVATE KEY-----", "MIIEowIBAAKCAQEA" + "x7Q2" * 20, "abcdefghijk",
               "-----END RSA PRIVATE KEY-----", "and then more")
    check("a private key is hidden on every line, and the next line is not",
          r.text.split("\n")[:4] == ["[hidden]"] * 4 and r.text.endswith("and then more"), r.text)
    r = hidden("-----BEGIN PRIVATE KEY-----", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSj")
    check("a private key with no end line (cut off by the screen) is hidden to the end",
          r.text == "[hidden]\n[hidden]", r.text)
    r = hidden("Card 4111 1111 1111 1111 exp 12/29")
    check("a card number that passes the check digit is hidden",
          r.text == "Card [hidden] exp 12/29" and "card" in r.kinds, r.text)
    r = hidden("Card 4111 1111 1111 1112 exp 12/29")
    check("... one that FAILS the check digit is left alone", r.hidden == 0 and "1112" in r.text)
    r = hidden("Amex 378282246310005 and MC 5500 0055 5555 5559")
    check("Amex and Mastercard test numbers are hidden too", r.text == "Amex [hidden] and MC [hidden]",
          r.text)
    r = hidden("IBAN GB82 WEST 1234 5698 7654 32 sent")
    check("an IBAN is hidden", r.text == "IBAN [hidden] sent", r.text)
    r = hidden("IBAN GB82 WEST 1234 5698 7654 33 sent")
    check("... one with a wrong check number is left alone", r.hidden == 0)
    r = hidden("wallet 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2 ok")
    check("a Bitcoin address is hidden", r.text == "wallet [hidden] ok", r.text)
    r = hidden("wallet 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3 ok")
    check("... one that fails its own check is left alone", r.hidden == 0, r.text)
    r = hidden("pay bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq now")
    check("a bech32 address is hidden", r.text == "pay [hidden] now", r.text)
    r = hidden("write to bob.smith@example.com or ping 192.168.1.20 today")
    check("an email address and an IP address are hidden",
          r.text == "write to [hidden] or ping [hidden] today", r.text)
    ok = True
    for line, want in (("Password: hunter2", "Password: [hidden]"), ("PIN = 4821", "PIN = [hidden]"),
                       ("Passcode:letmein", "[hidden]")):
        r = hidden(line)
        ok = ok and r.text == want
    check("a value written after Password, PIN or Passcode is hidden, even a short one", ok, r.text)


def t_left_alone():
    quiet = [
        "The keyboard shortcut for the apiary report is on page 12.",
        "Access denied. Author: John Smith. Key features include a token counter.",
        "Total: 12,345.67 USD on 2026-09-29 at 14:05, ref 20260929",
        "Windows 10.0.19045.3693 build 19045 version 22H2",
        "Password: ******", "Password: ••••••••", "Password: required", "PIN: optional",
        "Sign in with your password or a passkey.",
        "Call 555 0100 or visit https://example.com/docs/getting-started?lang=en",
        "C:\\Users\\me\\Documents\\report-final-v2.docx modified yesterday",
        "1234 5678 9012 3456 is not a card (fails the check digit)",
    ]
    for line in quiet:
        r = hidden(line)
        check("left alone: " + line[:50], r.hidden == 0 and r.text == line, r.text)


def t_lines():
    half = TOKEN[:20], TOKEN[20:]
    r = hidden("token: " + half[0], half[1] + " and more words")
    check("a token the screen wrapped is hidden on BOTH lines",
          r.text.split("\n")[0].endswith("[hidden]") and r.text.split("\n")[1].startswith("[hidden]"),
          r.text)
    check("... with nothing of it left in the text", half[0] not in r.text and half[1] not in r.text)
    r = hidden("Card 4111 1111", "1111 1111 expires soon")
    check("a card number with its groups on two lines is hidden on both",
          r.text == "Card [hidden]\n[hidden] expires soon", r.text)
    check("... and each line has its own box", len(r.boxes) == 2)
    r = hidden("the quick brown fox", "jumps over the lazy dog")
    check("two ordinary lines joined end to end find nothing", r.hidden == 0)
    r = hidden("ghp_aB3dE5gH7jK9", "mN1pQ3sT5vW7", "yZ9bC1eF3hJ5", "then a new line")
    check("a token over THREE lines is hidden on all three, and the fourth line is not",
          r.text == "[hidden]\n[hidden]\n[hidden]\nthen a new line", r.text)
    r = hidden("Sent from: bob@example.com", "Subject: lunch")
    check("a match that ends a line may also hide the first word of the next (the price of "
          "hiding a wrapped secret on every line - safe, and said in the docs)",
          r.text.split("\n")[0] == "Sent from: [hidden]", r.text)


def t_words():
    r = hidden("start key=" + "kJ8dLq2Zx9Vw3RtY7uBnM4pAs6DfGh1C" + " end")
    check("a secret inside a longer word hides the WHOLE word, not half of it",
          r.text == "start [hidden] end", r.text)
    r = hidden("one two", TOKEN, "three")
    check("a secret alone on a line hides that line, and only that line",
          r.text == "one two\n[hidden]\nthree", r.text)
    r = hidden("Password: hunter2 and Password: swordfish")
    check("two secrets on one line are two runs", r.text.count("[hidden]") == 2, r.text)
    r = hidden("a " + TOKEN + " " + TOKEN + " b")
    check("neighbouring secret words are one run, so one box", r.text == "a [hidden] b"
          and r.hidden == 1 and len(r.boxes) == 1, r.text)


def t_boxes():
    lines = screen("go " + TOKEN + " now", top=100)
    r = S.redact(lines)
    w = lines[0]["words"][1]
    l, t, rr, b = r.boxes[0]
    pad = S.PAD_PX + 0.1 * LINE_H
    check("a box is the word's own rectangle grown by the padding",
          abs(l - (w["left"] - pad)) < 1e-6 and abs(t - (w["top"] - pad)) < 1e-6
          and abs(rr - (w["left"] + w["width"] + pad)) < 1e-6
          and abs(b - (w["top"] + w["height"] + pad)) < 1e-6, str(r.boxes))
    check("a box never covers less than the words", l < w["left"] and t < w["top"]
          and rr > w["left"] + w["width"] and b > w["top"] + w["height"])
    lines = screen("Password: hunter2 x")
    r = S.redact(lines)
    ws = lines[0]["words"]
    check("a run of several words is ONE box across the gap between them",
          len(r.boxes) == 1, str(r.boxes))
    lines = screen("Card 4111 1111 1111 1111 exp")
    r = S.redact(lines)
    ws = lines[0]["words"]
    check("... from the first hidden word to the last",
          r.boxes[0][0] < ws[1]["left"] and r.boxes[0][2] > ws[4]["left"] + ws[4]["width"], str(r.boxes))
    plain = S.redact([{"text": "Password: hunter2",
                       "words": [{"text": "Password:"}, {"text": "hunter2"}]}])
    check("a hidden word the reader gave NO position for cannot be boxed: flagged, not skipped",
          plain.boxless is True and plain.hidden == 1 and plain.boxes == [])
    plain = S.redact("Password: hunter2")
    check("plain text (no positions at all) is hidden in the words but has no boxes",
          plain.text == "Password: [hidden]" and plain.boxless is True)
    clean = S.redact(screen("nothing to see here"))
    check("nothing hidden: no boxes, not boxless", clean.hidden == 0 and clean.boxes == []
          and clean.boxless is False)


def t_input_shapes():
    check("a string is split into lines and words",
          [[w.text for w in ln] for ln in S.to_lines("a b\n\nc")] == [["a", "b"], ["c"]])
    check("a list of strings works", len(S.to_lines(["a b", "c"])) == 2)
    check("a line with words and one without both work",
          len(S.to_lines([{"text": "x y", "words": []}, {"text": "z", "words": [
              {"text": "z", "left": 1, "top": 2, "width": 3, "height": 4}]}])) == 2)
    check("a bad number in a position makes that word position-less, not a crash",
          S.to_lines([{"text": "z", "words": [{"text": "z", "left": "x", "top": 1, "width": 1,
                                               "height": 1}]}])[0][0].box is None)
    check("nothing at all is nothing", S.redact(None).text == "" and S.redact([]).hidden == 0)


def t_text():
    text = "line one\nToken " + TOKEN + "\nline three"
    out, n = S.redact_text(text)
    check("redact_text hides the run and keeps the lines", out == "line one\nToken [hidden]\nline three"
          and n == 1, out)
    same = "  spaced   out\n\ntext  "
    check("text with nothing to hide comes back EXACTLY as it was", S.redact_text(same) == (same, 0))
    check("an empty text is fine", S.redact_text("") == ("", 0) and S.redact_text(None) == ("", 0))


def t_fail_closed():
    big = "word " * (S.MAX_SCAN_CHARS // 5 + 10)
    try:
        S.redact(big)
        ok = False
    except S.Unchecked:
        ok = True
    check("a screen with too much text to check is refused, not skipped", ok)
    saved = dict(S._COMPILED)
    S._COMPILED.clear()
    import jarvis_secret_rules as R
    good = R.RULES
    R.RULES = ({"id": "x", "regex": "(", "entropy": 0.0, "group": 0, "keywords": [], "allow": []},)
    try:
        S.redact("hello there")
        ok = False
    except S.Unchecked:
        ok = True
    finally:
        R.RULES = good
        S._COMPILED.clear()
        S._COMPILED.update(saved)
    check("rule data that will not compile ends in 'not checked', never in fewer rules", ok)
    old = S.BUDGET_S
    S.BUDGET_S = -1.0
    try:
        S.redact("hello there")
        ok = False
    except S.Unchecked:
        ok = True
    finally:
        S.BUDGET_S = old
    check("a check past its time limit is 'not checked'", ok)
    real = S.redact

    def slow(lines, **kw):
        time.sleep(1.5)
        return real(lines)
    S.redact = slow
    try:
        S.check("hello", timeout=0.1)
        ok = False
    except S.Unchecked:
        ok = True
    finally:
        S.redact = real
    check("a check that never comes back is given up on (its thread is left behind)", ok)

    def boom(lines, **kw):
        raise ValueError("odd")
    S.redact = boom
    try:
        S.check("hello")
        ok = False
    except S.Unchecked:
        ok = True
    finally:
        S.redact = real
    check("any other failure in the check is 'not checked' too", ok)
    check("the plain sentence says what happened", "not using it" in S.NOT_CHECKED)


def t_many():
    spans = [(i * 10, i * 10 + 8, 0, i) for i in range(1000)]
    check("overlapping words are found by bisection, and exactly the right ones",
          S._overlapping(spans, 25, 47) == [(0, 2), (0, 3), (0, 4)]
          and S._overlapping(spans, 8, 10) == [] and S._overlapping(spans, 0, 1) == [(0, 0)]
          and S._overlapping(spans, 9995, 12000) == [(0, 999)])
    lines = screen(*[" ".join(f"user{i}@example.com" for i in range(6)) for _ in range(300)])
    t0 = time.time()
    r = S.check(lines)
    check("a screen of 1,800 email addresses is checked in a few seconds, all hidden",
          r.hidden >= 300 and "@" not in r.text and time.time() - t0 < 20, f"{time.time() - t0:.1f}s")


def t_hygiene():
    src = (HERE / "jarvis_secrets.py").read_text(encoding="utf-8")
    check("no network, no file and no subprocess in the checker",
          not any(x in src for x in ("socket", "urllib", "requests", "subprocess", "open(",
                                      "write_text", "tempfile")))
    check("the Presidio PACKAGE and spaCy are not used, only its patterns",
          not any(x in src for x in ("import presidio", "from presidio", "import spacy",
                                      "from spacy")))


def main():
    for fn in (t_found, t_left_alone, t_lines, t_words, t_boxes, t_input_shapes, t_text,
               t_fail_closed, t_many, t_hygiene):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            print("FAIL " + fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
