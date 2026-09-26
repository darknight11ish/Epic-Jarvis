"""test_paste_guard.py - a pasted password, PIN or one-time code is masked
before it reaches the stored chat-history database; ordinary sentences,
including everyday talk about "the code" in a developer's own chat, are not.

    python3 backend/test_paste_guard.py

Feasibility idea I115 (docs/FEASIBILITY-AUDIT-2026-09-26.md: "Keeps pasted
passwords out of stored history." / "Reuse jarvis_sensitive/jarvis_mail_mask
patterns."). What it proves:
  - jarvis_paste_guard.guard() masks every secret in HIDE (a label then a
    value, a value then a label, any separator shape, a bare one-time code
    near a named code word) with the one fixed marker, and leaves every
    sentence in KEEP exactly as it was - including the false-positive this
    module's own first draft had ("I changed my password today" masking
    "today") and ordinary talk about source code, which never counts as a
    label at all;
  - it never raises, and on an internal error returns the text UNCHANGED,
    on purpose the opposite choice from jarvis_mail_mask.py's WITHHELD (see
    the module docstring for why);
  - jarvis_chat_log.py calls it on a user message's words before writing
    them to the encrypted database, but writes the LIVE-TURN REGISTRY's
    hash from the ORIGINAL words first - so a message with a password in
    it is still recognised as "this PC saw it arrive live" by
    jarvis_auto_learn.py, which hashes the words the model actually saw,
    never the masked ones (test_chat_log.py's own t_live_turn_hash tests
    the registry generally; this file's own t_chat_log_masks_before_write
    is the one that would catch a masked hash breaking that lookup).
No network, no model.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_paste_guard.py", "jarvis_chat_log.py")

import jarvis_paste_guard as G  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: (text, the piece that must be gone). Every value here is invented for
#: this test, never shaped like a real credential in use anywhere.
HIDE = [
    ("My wifi password is Sunshine123!", "Sunshine123"),
    ("pw: correcthorsebattery", "correcthorsebattery"),
    ("PIN = 4821", "4821"),
    ("passcode - Tr0ub4dor&3", "Tr0ub4dor&3"),
    ("Sunshine123 is my password", "Sunshine123"),
    ("4821 is the PIN", "4821"),
    ("OTP 738291", "738291"),
    ("Your verification code is 482913.", "482913"),
    ("the SECURITY CODE: 118822", "118822"),
    ("my Wi-Fi code is 88112233", "88112233"),
    ("sign-in code = 91827364", "91827364"),
    ("here is my recovery code: ABCDE12345", "ABCDE12345"),
    ("Username: alex\nPassword: correcthorsebattery", "correcthorsebattery"),
    ("the door code is 4821, remember it", "4821"),
    ("my alarm code is 4471", "4471"),
    ("2FA code: 918273", "918273"),
    ("passphrase=river-lantern-forty", "river-lantern-forty"),
]

#: Sentences that must come back byte-for-byte identical - including the
#: exact bug an earlier draft of this module had (a separator that could
#: match zero characters let it treat the next ordinary word as the value).
KEEP = [
    "I changed my password today",
    "two-factor is on for everything",
    "password is fine now",
    "my password is wrong",
    "your password is the same as your PIN",
    "no secrets here, just a normal message",
    "order number is 482913",
    "there is no password",
    "no PIN required",
    "no PIN is required",
    "here's the code: 482913",           # bare "code" is never a label - see below
    "Use code 7731 to sign in",
    "this code is buggy",
    "let's refactor the code",
    "the code needs tests",
    "check the code below",
    "no label here but 482913 alone",
    "I prefer passkeys over passwords",
    "I keep the API key in an env var",
    "",
]


def t_hide():
    for text, secret in HIDE:
        out, changed = G.guard(text)
        check(f"masked: {text!r}", changed and secret not in out and G.MASK in out,
              (text, out))


def t_keep():
    for text in KEEP:
        out, changed = G.guard(text)
        check(f"unchanged: {text!r}", out == text and changed is False, (text, out))


def t_bare_code_is_never_a_label_alone():
    """The module's own documented gap: "code" with no kind named is never
    masked, however close a number sits to it - a developer's own chat says
    "the code" constantly, and none of those mentions are secrets."""
    for text in ("the code has 482913 lines", "review the code, then merge 482913",
                 "issue 482913: the code throws an exception"):
        out, changed = G.guard(text)
        check(f"bare 'code' never masks a nearby number: {text!r}", out == text and not changed,
              (text, out))


def t_marker_is_never_masked_twice():
    """A marker this same call already wrote must never be treated as a new
    secret by a later pass in the same call - the same "a marker is never
    matched again" rule jarvis_mail_mask.py and jarvis_scrub.py document."""
    out, changed = G.guard("my PIN is 4821")
    check("first pass produces exactly one marker", out.count(G.MASK) == 1, out)
    out2, changed2 = G.guard(out)
    check("running guard() again on already-masked text changes nothing",
          out2 == out and changed2 is False, (out, out2))


def t_never_raises():
    for bad in (None, 123, [], {}, object()):
        try:
            out, changed = G.guard(bad)
        except Exception:
            check(f"never raises on {bad!r}", False, traceback.format_exc())
            continue
        check(f"never raises on {bad!r}", isinstance(out, str) and changed is False, out)


def t_chat_log_masks_before_write():
    """jarvis_chat_log.py calls jarvis_paste_guard.guard() on the words it
    writes to the encrypted database, but the LIVE-TURN REGISTRY (read by
    jarvis_auto_learn.py) keeps the hash of the ORIGINAL, unmasked words -
    otherwise a message with a password in it could never be recognised as
    "this PC saw it arrive live" by the exact hash lookup live_turn() does."""
    import test_chat_log as T

    w = T.World()
    try:
        secret = "my wifi password is Sunshine123!"
        out = w.log.record_turn(T.req(secret, cid="conv-pasteguard", prov="pasted"),
                                 turn=T.local("Got it."))
        check("recorded, answer kept", out.get("recorded") and out["answer_kept"], out)
        conv = w.log.get("conv-pasteguard")
        stored = conv["turns"][0]["text"]
        check("the stored row is masked", "Sunshine123" not in stored, stored)
        check("the stored row carries the fixed marker", G.MASK in stored, stored)
        raw = w.raw()
        check("Sunshine123 is nowhere on disk, masked or not", b"Sunshine123" not in raw)
        # The live-turn registry's hash is of the ORIGINAL words - the same
        # words jarvis_agent.py already showed the model this turn - not the
        # masked ones, or jarvis_auto_learn.py's live_turn() lookup would miss.
        live = w.log.live_turn("conv-pasteguard", secret)
        check("the live-turn registry matches on the ORIGINAL words", live is not None, live)
        missed = w.log.live_turn("conv-pasteguard", stored)
        check("... and does NOT match on the masked words", missed is None, missed)
    finally:
        w.done()


def main():
    for fn in (t_hide, t_keep, t_bare_code_is_never_a_label_alone,
               t_marker_is_never_masked_twice, t_never_raises,
               t_chat_log_masks_before_write):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
