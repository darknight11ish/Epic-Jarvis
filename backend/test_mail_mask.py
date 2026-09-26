"""test_mail_mask.py - one-time codes and sign-in links are hidden in the
email text Jarvis reads; ordinary numbers and links are not.

    python3 backend/test_mail_mask.py

The Muse audit's idea 2 (docs/COMPETITORS-MUSE-2026-09-25.md). What it
proves:
  - jarvis_mail_mask.hide() hides every code and link in HIDE (codes near a
    code word, codes under a subject that says "code", reset / magic /
    verify / sign-in links, and links with a long random piece), and leaves
    every text in KEEP exactly as it was (prices, years, order and invoice
    numbers, phone numbers, dates, times, ordinary links);
  - the everyday and planted texts test_injection_cases.py already uses
    are not changed (the precision side, on text nobody wrote for this);
  - it never raises, and on an internal error it WITHHOLDS the text rather
    than passing it through;
  - jarvis_email.py uses it on every path email text leaves by: run()'s
    subject, preview and sender, the preview cut at 400 characters without
    half a marker, and senders() (the morning briefing's names);
  - without the module, email text is withheld, not shown unmasked.
No network, no model.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_mail_mask.py", "jarvis_email.py")

import jarvis_mail_mask as M  # noqa: E402
import jarvis_email as E  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: (text, subject, the piece that must be gone). Hex and random pieces are
#: built by concatenation so nothing here is shaped like a real secret.
_HEX = "9f8e7d6c" + "5b4a3928" + "1706f5e4" + "d3c2b1a0"
_RAND = "aZ3kLm9Q" + "p2Xy7RtB" + "8vN4wE1c"
_B64 = "QmFzZTY0" + "VG9rZW4x" + "MjM0NQab"
HIDE = [
    ("Your verification code is 482913.", "", "482913"),
    ("482913 is your Instagram code. Don't share it.", "", "482913"),
    ("G-482913 is your Google verification code.", "", "G-482913"),
    ("Use code 7731 to sign in to your account.", "", "7731"),
    ("Your one-time passcode: 55190023", "", "55190023"),
    ("Enter 123-456 to verify your email address.", "", "123-456"),
    ("Your login code is 123 456", "", "123 456"),
    ("OTP for your transaction is 849201. Valid for 10 minutes.", "", "849201"),
    ("Your 2FA code: 90817", "", "90817"),
    ("Security code: 3345. If you didn't request this, ignore this email.", "", "3345"),
    ("Here is your code X7K9P2 - it expires soon.", "", "X7K9P2"),
    ("Your code is AB12CD", "", "AB12CD"),
    ("Hi Sam, 558812 Thanks, the team", "Your verification code", "558812"),
    ("Your PIN is 4821", "", "4821"),
    ("Your code is 2024", "", "2024"),
    ("Enter this code to log in: 663 104", "", "663 104"),
    ("Your Microsoft account security code is 7291", "", "7291"),
    ("To finish signing in, type 30417 in the app.", "", "30417"),
    ("Reset your password: https://accounts.example.com/reset?token=abc123", "", "reset?token"),
    ("Click https://example.com/magic-link/" + _HEX + " to log in.", "", _HEX),
    ("Confirm your email: https://app.example.org/verify-email?u=42&k=" + _B64, "", "verify-email"),
    ("Sign in here: https://example.com/auth/callback?code=4f2a", "", "auth/callback"),
    ("Open www.shop.example/login/redirect?next=/cart", "", "login/redirect"),
    ("Your file: https://files.example.net/s/" + _RAND, "", _RAND),
    ("Unsubscribe: https://news.example.com/unsubscribe?id=77", "", "unsubscribe"),
    ("Accept the invite https://team.example.com/invitation/abc", "", "invitation"),
    ("Continue at https://login.example.com/?next=home", "", "login.example.com"),
]

KEEP = [
    "The total is $1299 and it ships Tuesday.",
    "Order number 12345678 has shipped.",
    "Your order #40912 is on its way. Log in to track it.",
    "Meeting moved to 2024-10-05 at 14:30.",
    "Call me on 555-123-4567 after 6.",
    "Call +1 555 123 4567 to reach support.",
    "We have 2500 members this year.",
    "Happy new year 2025!",
    "The invoice 88213 is attached; please pay by Friday.",
    "Flight BA2490 departs at 09:15.",
    "It costs 1500 dollars.",
    "Your score went up 1200 points.",
    "Sales grew 3400% since 2019.",
    "Watch this: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "Read it at https://news.example.com/2024/10/05/city-council-votes-on-new-budget",
    "See https://shop.example.com/products/walking-boots-size-10",
    "Lunch on Friday? I found a place near 1200 Market Street.",
    "The code review is at 3pm in room 4012.",
    "Your account ending 4821 was charged £12.50.",
    "Please sign in to the wiki and update page 1234.",
    "We raised 25000 euros for the school.",
    "Version 4.2.1 is out; download it from https://example.com/downloads",
    "Reference 889123 for your booking at the hotel.",
    "The 2019 report is attached, with the 2020 numbers.",
    "Dinner for 4 at 7:30, table 12.",
    "Postcode SW1A 1AA, house 1600.",
]


def t_hides_codes_and_links():
    for text, subject, gone in HIDE:
        out = M.hide(text, subject=subject)
        check(f"hidden: {text[:60]!r}", gone not in out and "hidden]" in out, out)
    check(f"at least 20 hide cases ({len(HIDE)})", len(HIDE) >= 20)


def t_keeps_ordinary_text():
    for text in KEEP:
        out = M.hide(text)
        check(f"kept: {text[:60]!r}", out == text, out)
    check(f"at least 20 keep cases ({len(KEEP)})", len(KEEP) >= 20)


def t_the_words_are_plain():
    out = M.hide("Your code is 482913 and https://x.example/reset?t=1")
    check("the markers are plain words", M.CODE_MARK in out and M.LINK_MARK in out, out)
    check("a random-piece link says so", M.TOKEN_LINK_MARK in M.hide(
        "https://files.example.net/s/" + _RAND))
    check("a full stop after a link stays a full stop",
          M.hide("Reset: https://x.example/reset?t=1.") == "Reset: " + M.LINK_MARK + ".")


def t_everyday_texts_from_the_injection_suite_are_unchanged():
    # AgentDojo's ordinary environment text (emails, files, reviews,
    # messages) that test_injection_cases.py uses to check for false alarms:
    # text nobody wrote for this module. Three of the 180 really are a code
    # or a reset link (a Facebook security code, two password-reset links),
    # and those three - and only those - are changed.
    texts = json.loads((HERE / "agentdojo_injections.json").read_text(encoding="utf-8"))["benign"]
    changed = [t for t in texts if M.hide(t) != t[:M.MAX_CHARS]]
    real = [t for t in changed if "security code is" in t or "password-reset/token" in t]
    check(f"{len(texts)} everyday texts: only the 3 real codes and reset links change",
          len(texts) >= 150 and len(changed) == 3 and len(real) == 3,
          repr([t[:80] for t in changed]))
    kept = [t for t in texts if t not in changed]
    check("... and every other one is exactly as it was",
          all(M.hide(t) == t[:M.MAX_CHARS] for t in kept))


def t_never_raises_and_withholds_on_error():
    for bad in (None, 12345, b"bytes", object(), "x" * 100000):
        try:
            M.hide(bad)
            ok = True
        except Exception:
            ok = False
        check(f"never raises on {type(bad).__name__}", ok)
    saved = M._hide_links
    M._hide_links = lambda t: 1 / 0
    try:
        out = M.hide("Your code is 482913")
    finally:
        M._hide_links = saved
    check("an internal error withholds the text", out == M.WITHHELD, out)


def t_cap_never_leaves_half_a_marker():
    text = "x" * 390 + " " + M.CODE_MARK + " more"
    out = M.cap(text, 400)
    check("cut at 400 without half a marker", len(out) <= 400 and "[a one" not in out, out[-20:])
    check("a short text is untouched", M.cap("hello", 400) == "hello")


def _raw(subject="Hello", body="Hi", sender="Alex <alex@example.com>"):
    return (f"From: {sender}\r\nSubject: {subject}\r\nDate: Fri, 25 Sep 2026 07:00:00 +0000\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n").encode("utf-8")


def t_every_email_path_uses_it():
    import os
    os.environ["JARVIS_IMAP_HOST"] = "mail.example.com"
    try:
        p = E.plan(5)
        msgs = [_raw("Your verification code", "Hi, 558812 is below. Thanks"),
                _raw("Code 482913 for you", "Reset here https://x.example/reset?token=abc"),
                _raw("Hello", "word " * 78 + "code 482913 " + "tail " * 40)]
        out = E.run(p, fetch_messages=lambda _p: msgs, approved=True)
        m = out["messages"]
        check("run(): the preview under a code subject hides the code",
              "558812" not in m[0]["preview"] and M.CODE_MARK in m[0]["preview"], m[0])
        check("run(): the subject hides its code", "482913" not in m[1]["subject"], m[1])
        check("run(): a reset link in the preview is hidden",
              "reset?token" not in m[1]["preview"] and M.LINK_MARK in m[1]["preview"], m[1])
        check("run(): the preview is still at most 400 characters, with no half marker",
              all(len(x["preview"]) <= E._MAX_PREVIEW_CHARS for x in m)
              and not m[2]["preview"].rstrip().endswith(("[a", "[a one-time")), m[2]["preview"][-30:])
        check("run(): a code just inside the 400 is hidden", "482913" not in m[2]["preview"])
        heads = [b"From: 482913 is your code <no-reply@example.com>\r\n"]
        s = E.senders(p, fetch=lambda _p, n: (1, heads), approved=True)
        check("senders(): the briefing's names are hidden too",
              s["ok"] and "482913" not in json.dumps(s), s)
        check("sender_name() hides", "482913" not in E.sender_name(heads[0]))
        plain = E.run(p, fetch_messages=lambda _p: [_raw("Lunch", "Lunch on Friday at 12:30?")],
                      approved=True)["messages"][0]
        check("an ordinary email is unchanged", plain["preview"] == "Lunch on Friday at 12:30?"
              and plain["subject"] == "Lunch", plain)
        # Without the module: withheld, never shown unmasked.
        saved = sys.modules.get("jarvis_mail_mask")
        sys.modules["jarvis_mail_mask"] = None      # import now fails
        try:
            gone = E.run(p, fetch_messages=lambda _p: [_raw("Code 482913", "code 482913")],
                         approved=True)["messages"][0]
        finally:
            sys.modules["jarvis_mail_mask"] = saved
        check("without jarvis_mail_mask.py the text is withheld, not shown",
              "482913" not in json.dumps(gone), gone)
    finally:
        os.environ.pop("JARVIS_IMAP_HOST", None)


if __name__ == "__main__":
    for fn in (t_hides_codes_and_links, t_keeps_ordinary_text, t_the_words_are_plain,
               t_everyday_texts_from_the_injection_suite_are_unchanged,
               t_never_raises_and_withholds_on_error, t_cap_never_leaves_half_a_marker,
               t_every_email_path_uses_it):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
