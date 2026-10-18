"""test_clipboard.py - Pillar 14 slice 14A, the opt-in RAM-only clipboard
time machine (jarvis_clipboard.py).

    python -B backend/test_clipboard.py

Runs anywhere: no network, no model, no owner's files. It drives the REAL
`ClipboardRing` and the REAL `jarvis_scrub`, and asserts on what they return;
it does not read the module's source text. The one exception is deliberate
and is about the scrubber's availability only: the "scrubber absent" and
"scrubber broken" branches replace the module's scrubber handle with a
stand-in for the length of that check (there is no other way to make the real
scrubber unavailable), and everything else runs against the real one.

What it proves:

  1. THE CONTRACT AND THE DEFAULT: `ClipboardRing()` is OFF and stores
     nothing; `max_items` 25 and `max_item_chars` 32768; `items` is newest
     first, each `{"text","app","title"}`; `offer` returns exactly
     `{"kept","reason"}` and a kept offer keeps the text verbatim with its
     foreground app and title.
  2. EVERY REFUSAL BRANCH, each storing nothing and leaving the ring exactly
     as it was: `not_text`, `disabled`, `empty` (empty, spaces, tabs,
     newlines, a non-breaking space), `too_large` (over the limit, and the
     limit itself still kept), `excluded_app` (every named password manager
     and credential dialog, in the app name and in the window title, plus an
     owner-configured excluded app, and a normal app still kept),
     `scrubber_unavailable` (absent, raising, missing half), `secret_detected`
     (labelled secret, secret in a URL, AWS key, GitHub token, OpenAI-style
     key - all through the REAL jarvis_scrub - and a card number that only
     passes the check digit), `secret_or_otp_detected` (a PEM block, a
     contextual 4-8 digit one-time code, a G-123456 authenticator code, and a
     single generated-password-shaped token). The contextual and
     password-shaped branches are driven with a scrubber that flags nothing,
     because otherwise the real scrubber answers first - both layers are
     proved, one at a time, and the tests say which is which.
  3. THE REAL SCRUBBER IS THE JUDGE: the module holds `jarvis_scrub` itself,
     not a private copy of its rules, and an offer really calls it.
  4. THE RING'S BOUNDS: duplicate copies are one entry moved to the top; a
     re-copied text refreshes its app and title; at most `max_items` entries
     are kept and the oldest falls off; the returned items are copies.
  5. THE INSTANT WIPE: `lock()` empties the ring AND stops capture;
     `clear()` empties it and leaves the switch as it was.
  6. THE THREE TRANSFORMS, exactly: CSV and TSV to a pipe table (including a
     quoted comma, a tab-separated table and a cell containing a pipe), with
     plain refusals under two rows, under two columns, for ragged rows and
     for text that is not a table; pretty JSON with two spaces and non-ASCII
     kept, and a plain refusal for invalid JSON; tracking parameters stripped
     from every http(s) URL with every other parameter kept in order and all
     non-URL text left exactly as it was.
  7. NO DISK, WATCHED FROM OUTSIDE THE MODULE: a fresh Python process in a
     fresh empty folder installs the operating system's own audit hook, warms
     up the scrubber's lazy imports, clears the log, and then drives the ring
     and all three transforms. Zero file-access events must be recorded, no
     file may appear in the folder, and the data must still come back. The
     test never looks at the module's text to decide this.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_clipboard.py", "jarvis_scrub.py")

import jarvis_clipboard as C  # noqa: E402
import jarvis_scrub  # noqa: E402

PASSED, SKIPPED, FAILED = [], [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-clipboard-suite-"))

OFFER_KEYS = {"kept", "reason"}
ITEM_KEYS = {"text", "app", "title"}
TRANSFORM_KEYS = {"ok", "kind", "text", "reason"}


# ---------------------------------------------------------------- harness --

def check(name, cond, detail=""):
    """One check. `cond` is always a real condition; never the constant True."""
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def enabled(**kwargs):
    """A ring with the owner's switch ON, for the checks about what it keeps."""
    return C.ClipboardRing(enabled=True, **kwargs)


def offer_shape(res):
    """True when `res` is exactly the documented offer answer."""
    return (isinstance(res, dict) and set(res) == OFFER_KEYS
            and isinstance(res["kept"], bool)
            and isinstance(res["reason"], str))


def refused(res, reason):
    """True when `res` is the documented refusal with this exact reason."""
    return offer_shape(res) and res["kept"] is False and res["reason"] == reason


def transform_shape(res):
    """True when `res` is exactly the documented transform answer."""
    return (isinstance(res, dict) and set(res) == TRANSFORM_KEYS
            and isinstance(res["ok"], bool) and isinstance(res["kind"], str)
            and isinstance(res["text"], str) and isinstance(res["reason"], str))


def no_secret_texts(ring):
    """Every stored text, for the "refusal stored nothing new" checks."""
    return tuple(item["text"] for item in ring.items)


class _InertScrubber:
    """A scrubber that flags nothing, so the module's OWN guards are the judge.

    The real `jarvis_scrub` refuses a labelled secret before the module's PEM,
    one-time-code and password-shaped checks ever run, so those three branches
    cannot be reached while it is in place. This stand-in is used only to
    isolate those branches; the same inputs are also driven through the real
    scrubber, where they are refused one layer earlier.
    """

    def find_secret(self, text):
        return None

    def scrub_text(self, text, *, identifiers=True):
        return str(text)


class _BrokenScrubber:
    """A scrubber that raises when asked: the ring must fail closed."""

    def find_secret(self, text):
        raise RuntimeError("the scrubber broke")

    def scrub_text(self, text, *, identifiers=True):
        raise RuntimeError("the scrubber broke")


class _HalfScrubber:
    """A scrubber object missing the redacting half."""

    def find_secret(self, text):
        return None


@contextlib.contextmanager
def using_scrubber(stub):
    """Swap the module's scrubber handle for the length of one check."""
    real = C._scrub
    C._scrub = stub
    try:
        yield stub
    finally:
        C._scrub = real


class _RecordingScrubber:
    """The real scrubber, with a count of how often it was called."""

    def __init__(self, inner):
        self.inner = inner
        self.find_calls = 0
        self.scrub_calls = 0

    def find_secret(self, text):
        self.find_calls += 1
        return self.inner.find_secret(text)

    def scrub_text(self, text, *, identifiers=True):
        self.scrub_calls += 1
        return self.inner.scrub_text(text, identifiers=identifiers)


# ---------------------------------------------------------------- contract --

def t_the_contract_and_the_defaults():
    check("the module loaded the REAL jarvis_scrub, not a private copy of its rules",
          C._scrub is jarvis_scrub,
          f"the module's scrubber handle is {C._scrub!r}, not jarvis_scrub")
    check("DEFAULT_MAX_ITEMS is the documented 25",
          C.DEFAULT_MAX_ITEMS == 25, C.DEFAULT_MAX_ITEMS)
    check("DEFAULT_MAX_ITEM_CHARS is the documented 32768",
          C.DEFAULT_MAX_ITEM_CHARS == 32768, C.DEFAULT_MAX_ITEM_CHARS)
    check("TRANSFORMS is exactly the three documented kinds",
          tuple(C.TRANSFORMS) == ("markdown_table", "pretty_json",
                                  "strip_tracking_params"), C.TRANSFORMS)
    check("EXCLUDED_APPS names every documented password manager and credential dialog",
          set(C.EXCLUDED_APPS) == {
              "1password", "bitwarden", "keepass", "keepassxc", "dashlane",
              "lastpass", "proton pass", "windows security",
              "credential manager"}, C.EXCLUDED_APPS)
    check("TRACKING_PARAMS names every documented click identifier",
          set(C.TRACKING_PARAMS) == {
              "fbclid", "gclid", "msclkid", "mc_eid", "igshid", "_hsenc",
              "vero_id", "mkt_tok"}, C.TRACKING_PARAMS)
    check("an OFF ring's answer is exactly reason=disabled",
          refused(C.ClipboardRing().offer("hello"), "disabled"),
          C.ClipboardRing(enabled=True).offer("hello"))

    ring = C.ClipboardRing()
    check("a new ring is OFF", ring.enabled is False, ring.enabled)
    check("a new ring has no items", ring.items == () and len(ring) == 0, ring.items)
    check("a new ring's answer is exactly {kept, reason}, with kept a real bool",
          offer_shape(ring.offer("hello")), ring.offer("hello"))
    check("the OFF ring stored nothing", ring.items == (), ring.items)

    ring = enabled()
    res = ring.offer("the words that were copied", foreground_app="Code",
                     foreground_title="notes.py")
    check("an ON ring keeps a plain text and says so in the documented answer",
          refused(res, "") is False and offer_shape(res) and res["kept"] is True
          and res["reason"] == "", res)
    check("... and the item is exactly {text, app, title}, with the text verbatim",
          len(ring.items) == 1 and set(ring.items[0]) == ITEM_KEYS
          and ring.items[0]["text"] == "the words that were copied", ring.items)
    check("... and the foreground app and title ride along",
          ring.items[0]["app"] == "Code" and ring.items[0]["title"] == "notes.py",
          ring.items)


def t_not_text_and_empty_and_whitespace_are_refused():
    ring = enabled()
    for value, label in ((None, "None"), (42, "a number"), (b"bytes", "bytes")):
        res = ring.offer(value)
        check(f"{label} is refused as not_text", refused(res, "not_text"), res)
    check("... and none of the three stored anything", ring.items == (), ring.items)
    for value, label in (("", "en empty text"), ("   ", "three spaces"),
                         ("\t\n ", "tabs and newlines"), ("\u00a0", "a non-breaking space")):
        res = ring.offer(value)
        check(f"{label} is refused as empty", refused(res, "empty"), res)
    check("... and no whitespace-only text was stored", ring.items == (), ring.items)


def t_too_large_is_refused_whole():
    ring = enabled(max_item_chars=5)
    keep = ring.offer("12345")
    res = ring.offer("123456")
    check("a text over max_item_chars is refused as too_large",
          refused(res, "too_large"), res)
    check("... and the text exactly at max_item_chars is still kept",
          offer_shape(keep) and keep["kept"] is True, keep)
    check("... and the refused one stored nothing, leaving only the kept one",
          no_secret_texts(ring) == ("12345",), ring.items)
    default_ring = enabled()
    over = "x" * (C.DEFAULT_MAX_ITEM_CHARS + 1)
    check("the DEFAULT limit also refuses one character over 32768",
          refused(default_ring.offer(over), "too_large"), default_ring.items)
    check("the over-limit refusal stored nothing", default_ring.items == (),
          len(default_ring.items))


def t_every_named_password_manager_is_refused():
    ring = enabled()
    for name in C.EXCLUDED_APPS:
        res = ring.offer("a copied password", foreground_app=name.upper())
        check(f"the window app {name!r} is refused as excluded_app",
              refused(res, "excluded_app"), res)
    res = ring.offer("a copied password", foreground_title="Sign in - Bitwarden")
    check("a password manager IN A WINDOW TITLE is refused as excluded_app",
          refused(res, "excluded_app"), res)
    res = ring.offer("a copied password", foreground_app="KeePassXC")
    check("KeePassXC (the second KeePass) is refused as excluded_app",
          refused(res, "excluded_app"), res)
    res = ring.offer("a copied password", foreground_title="Windows Security")
    check("a Windows security credential dialog is refused as excluded_app",
          refused(res, "excluded_app"), res)
    check("... and none of the excluded-app offers stored anything",
          ring.items == (), ring.items)

    private = enabled(excluded_apps=("Obsidian", "my vault"))
    check("an owner-configured excluded app is refused as excluded_app",
          refused(private.offer("a note", foreground_app="Obsidian"),
                 "excluded_app"), private.items)
    check("... and an owner-configured excluded app is matched in a title too",
          refused(private.offer("a note", foreground_title="My Vault notes"),
                 "excluded_app"), private.items)
    normal = private.offer("a line of code", foreground_app="Code",
                           foreground_title="notes.py")
    check("a normal word processor / editor is NOT refused",
          offer_shape(normal) and normal["kept"] is True, normal)


def t_the_real_scrubber_is_the_judge():
    check("the module's scrubber handle really is the jarvis_scrub module",
          C._scrub is jarvis_scrub, C._scrub)
    recorder = _RecordingScrubber(jarvis_scrub)
    ring = enabled()
    with using_scrubber(recorder):
        plain = ring.offer("plain words in a sentence")
        labelled = ring.offer("password = hunter2")
    check("an offer goes through the scrubber's finding check",
          recorder.find_calls >= 2, recorder.find_calls)
    check("... and its redacting check runs too (the plain text reaches it; "
          "a label the finding check names is refused before it)",
          recorder.scrub_calls >= 1, recorder.scrub_calls)
    check("a plain sentence passes the real scrubber and is kept",
          offer_shape(plain) and plain["kept"] is True, plain)
    check("a labelled secret is refused by the REAL scrubber as secret_detected",
          refused(labelled, "secret_detected"), labelled)
    check("... and the real-scrubber refusal stored nothing",
          no_secret_texts(ring) == ("plain words in a sentence",), ring.items)

    fixtures = (
        ("a labelled secret", "password = hunter2"),
        ("a secret in a URL",
         "https://example.com/?token=abcdef1234567890"),
        ("an AWS access key", "AKIAIOSFODNN7EXAMPLE"),
        ("a GitHub token", "ghp_16C7e42F292c6912E7710c838347Ae178B4a12"),
        ("an OpenAI-style key",
         "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH"),
    )
    ring = enabled()
    for label, text in fixtures:
        res = ring.offer(text)
        check(f"the real scrubber refuses {label} as secret_detected",
              refused(res, "secret_detected"), res)
    check("... and none of the real-scrubber refusals stored anything",
          ring.items == (), ring.items)

    ring = enabled()
    for label, text in (("a spaced Mastercard test number",
                         "Card number 5500 0000 0000 0004"),
                        ("a dashed Mastercard test number",
                         "Card number 5500-0000-0000-0004"),
                        ("a bare Visa test number", "4111 1111 1111 1111"),
                        ("a 13-digit test number", "4222222222222")):
        res = ring.offer(text)
        check(f"{label} is refused as secret_detected by the card check digit",
              refused(res, "secret_detected"), res)
    near_card = ring.offer("Order 4111 1111 1111 1112 was placed")
    check("... and a 16-digit number that FAILS the card check digit is kept",
          offer_shape(near_card) and near_card["kept"] is True, near_card)
    mixed = ring.offer("Ref 2026-10-17 192216 done")
    check("a mixed-separator number that passes the check digit is not mistaken "
          "for a card", offer_shape(mixed) and mixed["kept"] is True, mixed)
    email = ring.offer("write to john@example.com about it")
    check("an e-mail address is not a credential and is kept",
          offer_shape(email) and email["kept"] is True, email)


def t_a_missing_or_broken_scrubber_fails_closed():
    ring = enabled()
    with using_scrubber(None):
        res = ring.offer("nothing secret here")
    check("an absent scrubber refuses as scrubber_unavailable",
          refused(res, "scrubber_unavailable"), res)
    check("... and the absent-scrubber refusal stored nothing", ring.items == (),
          ring.items)
    with using_scrubber(_BrokenScrubber()):
        res = ring.offer("nothing secret here")
    check("a scrubber that RAISES refuses as scrubber_unavailable (fail closed)",
          refused(res, "scrubber_unavailable"), res)
    with using_scrubber(_HalfScrubber()):
        res = ring.offer("nothing secret here")
    check("a scrubber missing half its API refuses as scrubber_unavailable",
          refused(res, "scrubber_unavailable"), res)
    check("... and none of the broken-scrubber refusals stored anything",
          ring.items == (), ring.items)
    after = ring.offer("nothing secret here")
    check("with the real scrubber back, the same text is kept",
          offer_shape(after) and after["kept"] is True, after)
    ring.clear()


def t_a_private_key_block_is_refused():
    ring = enabled()
    block = ("-----BEGIN RSA PRIVATE KEY-----\n"
             "MIIEowIBAAKCAQEA1234567890abcdef\n"
             "-----END RSA PRIVATE KEY-----\n")
    with using_scrubber(_InertScrubber()):
        res = ring.offer(block)
    check("with a scrubber that flags nothing, a PEM block is refused by the ring's own guard",
          refused(res, "secret_or_otp_detected"), res)
    lower = ring.offer("-----begin openSSH private key-----")
    check("... and a lower-case PEM header is refused too",
          refused(lower, "secret_or_otp_detected"), lower)
    real = ring.offer(block)
    check("the REAL scrubber refuses the same PEM block one layer earlier",
          refused(real, "secret_detected"), real)
    check("... and none of the PEM offers stored anything", ring.items == (),
          ring.items)


def t_a_contextual_one_time_code_is_refused():
    ring = enabled()
    cases = (
        "Your verification code is 482910",
        "OTP: 123456",
        "482910 is your verification code",
        "PIN 1234",
        "Use 2FA code 9988",
        "Security code 1234567",
        "Sign-in code 5566",
        "G-123456",
        "g-654321",
    )
    with using_scrubber(_InertScrubber()):
        for text in cases:
            res = ring.offer(text)
            check(f"a one-time code is refused: {text!r}",
                  refused(res, "secret_or_otp_detected"), res)
    check("... and none of the one-time codes stored anything", ring.items == (),
          ring.items)

    with using_scrubber(_InertScrubber()):
        for text in ("The login page loaded fine",
                     "The order number is 123456",
                     "A ten digit number 1234567890 is not a code",
                     "The code word is open sesame"):
            res = ring.offer(text)
            check(f"wording without a 4-8 digit code is kept: {text!r}",
                  offer_shape(res) and res["kept"] is True, res)
    check("... and the not-a-code texts are the only things kept",
          len(ring.items) == 4, no_secret_texts(ring))

    ring = enabled()
    real = ring.offer("Your verification code is 482910")
    check("the REAL scrubber path still refuses the verification code",
          refused(real, "secret_or_otp_detected"), real)
    far = "The verification email arrived. " + ("filler words. " * 20) + "482910"
    res = ring.offer(far)
    check("a code 200+ characters from the keyword is not guessed to be an OTP",
          offer_shape(res) and res["kept"] is True, res)


def t_a_password_shaped_token_is_refused():
    ring = enabled()
    with using_scrubber(_InertScrubber()):
        for text, label in (
                ("Xk9#mP2$vL8@qZ4", "a 16-character token mixing all four classes"),
                ("myPassword123", "a 13-character token mixing three classes"),
                ("Abcdef1234!@", "a 12-character token (the lower boundary)"),
                ("Z" * 120 + "a1!x", "a 124-character token (near the upper boundary)")):
            res = ring.offer(text)
            check(f"{label} is refused as secret_or_otp_detected",
                  refused(res, "secret_or_otp_detected"), res)
        for text, label in (
                ("Abcde123!@#", "an 11-character token (under the boundary)"),
                ("correcthorsebatterystaple", "a long single-case word"),
                ("abcdefghijk1", "a lower-case word with one digit"),
                ("Z" * 125 + "a1!x", "a 129-character token (over the boundary)")):
            res = ring.offer(text)
            check(f"{label} is kept", offer_shape(res) and res["kept"] is True, res)
    check("... and exactly the four password-shaped tokens were left out",
          len(ring.items) == 4, no_secret_texts(ring))

    ring = enabled()
    link = ring.offer("https://example.com/id/1234567890")
    check("a lone URL is a link, not a password, and is kept",
          offer_shape(link) and link["kept"] is True, link)
    check("... and the lone URL is the one thing stored", len(ring.items) == 1,
          ring.items)


# -------------------------------------------------------------------- ring --

def t_duplicate_copies_are_one_entry_moved_to_the_top():
    ring = enabled(max_items=5)
    ring.offer("alpha")
    ring.offer("alpha")
    check("two consecutive identical copies are one entry",
          no_secret_texts(ring) == ("alpha",), no_secret_texts(ring))
    ring.offer("beta")
    ring.offer("alpha")
    check("a re-copied text moves its earlier entry to the top instead of growing the ring",
          no_secret_texts(ring) == ("alpha", "beta"), no_secret_texts(ring))
    ring = enabled()
    ring.offer("same", foreground_app="Code", foreground_title="a.py")
    ring.offer("same", foreground_app="Notepad", foreground_title="b.txt")
    check("re-copying the same text refreshes its app and title",
          ring.items[0]["app"] == "Notepad"
          and ring.items[0]["title"] == "b.txt", ring.items)
    check("the ring never holds two copies of one text",
          len({item["text"] for item in ring.items}) == len(ring.items), ring.items)


def t_the_ring_keeps_at_most_max_items():
    ring = enabled(max_items=3)
    for text in ("one", "two", "three", "four"):
        ring.offer(text)
    check("the ring stops at max_items entries", len(ring) == 3, len(ring))
    check("the newest copy is first", no_secret_texts(ring)[0] == "four",
          no_secret_texts(ring))
    check("the OLDEST entry falls off when the ring is full",
          "one" not in no_secret_texts(ring), no_secret_texts(ring))


def t_lock_wipes_the_ring_and_stops_capture():
    ring = enabled()
    ring.offer("first")
    ring.offer("second")
    ring.lock()
    check("lock() empties the ring at once", ring.items == () and len(ring) == 0,
          ring.items)
    check("lock() also turns capture OFF, so nothing is captured until the owner says so",
          ring.enabled is False, ring.enabled)
    res = ring.offer("after the lock")
    check("an offer after a lock is refused as disabled",
          refused(res, "disabled"), res)
    check("... and the locked ring is still empty", ring.items == (), ring.items)


def t_clear_wipes_the_ring_and_leaves_the_switch():
    ring = enabled()
    ring.offer("first")
    ring.offer("second")
    ring.clear()
    check("clear() empties the ring at once", ring.items == () and len(ring) == 0,
          ring.items)
    check("clear() leaves capture ON, unlike lock()", ring.enabled is True,
          ring.enabled)
    res = ring.offer("after the clear")
    check("... and a fresh offer after clear() is kept again",
          offer_shape(res) and res["kept"] is True, res)


def t_items_are_a_copy_of_the_ring():
    ring = enabled()
    ring.offer("kept words")
    snapshot = ring.items
    try:
        snapshot[0]["text"] = "edited by the caller"
    except TypeError:
        pass
    check("the items a caller gets are copies: editing one cannot edit the ring",
          ring.items[0]["text"] == "kept words", ring.items)


# -------------------------------------------------------------- transforms --

def t_markdown_table_transform():
    csv_text = 'name,points\n"Ada, Lovelace",9\nGrace,10\n'
    expected = ("| name | points |\n| --- | --- |\n"
                "| Ada, Lovelace | 9 |\n| Grace | 10 |\n")
    res = C.transform(csv_text, "markdown_table")
    check("CSV becomes a pipe table with a | --- | separator row",
          transform_shape(res) and res["ok"] is True
          and res["text"] == expected, res)
    tsv_text = "a\tb\n1\t2\n"
    res = C.transform(tsv_text, "markdown_table")
    check("TSV becomes the same shape of table",
          transform_shape(res) and res["ok"] is True
          and res["text"] == "| a | b |\n| --- | --- |\n| 1 | 2 |\n", res)
    piped = '"a|b",2\n1,2\n'
    res = C.transform(piped, "markdown_table")
    check("a pipe inside a cell is escaped, so it cannot end the cell",
          transform_shape(res) and res["ok"] is True
          and res["text"] == "| a\\|b | 2 |\n| --- | --- |\n| 1 | 2 |\n", res)
    res = C.transform("a\nb\n", "markdown_table")
    check("a one-column table is refused as needing 2 columns",
          transform_shape(res) and res["ok"] is False
          and res["reason"] == "a table needs at least 2 columns", res)
    res = C.transform("a,b\n", "markdown_table")
    check("a one-row table is refused as needing 2 rows",
          transform_shape(res) and res["ok"] is False
          and res["reason"] == "a table needs at least 2 rows", res)
    res = C.transform("a,b\n1,2,3\n", "markdown_table")
    check("rows of different widths are refused, never silently padded",
          transform_shape(res) and res["ok"] is False
          and res["reason"] == "every row needs the same number of columns", res)
    res = C.transform("", "markdown_table")
    check("an empty text has no table to format and is refused",
          transform_shape(res) and res["ok"] is False, res)


def t_pretty_json_transform():
    raw = '{"b": 1, "t": "h\u00e9llo", "a": [1, 2]}'
    expected = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    res = C.transform(raw, "pretty_json")
    check("JSON comes back indented by two spaces, with non-ASCII kept",
          transform_shape(res) and res["ok"] is True
          and res["text"] == expected and "\u00e9" in res["text"], res)
    check("... and the pretty form is exactly json.dumps(indent=2) of the value",
          res.get("text") == ('{\n  "b": 1,\n  "t": "h\u00e9llo",\n'
                              '  "a": [\n    1,\n    2\n  ]\n}'), res.get("text"))
    res = C.transform('{"a": 1,,}', "pretty_json")
    check("invalid JSON is refused in plain words",
          transform_shape(res) and res["ok"] is False
          and res["reason"] == "that is not valid JSON", res)
    res = C.transform("[1, 2]", "pretty_json")
    check("a JSON array pretty-prints too",
          transform_shape(res) and res["ok"] is True
          and res["text"] == "[\n  1,\n  2\n]", res)


def t_strip_tracking_params_transform():
    every = ("utm_source", "utm_medium", "utm_campaign", "utm_term",
             "utm_content", "fbclid", "gclid", "msclkid", "mc_eid", "igshid",
             "_hsenc", "vero_id", "mkt_tok")
    url = "https://example.com/p?" + "&".join(f"{name}=x" for name in every)
    res = C.transform(url, "strip_tracking_params")
    check("every documented tracking parameter is stripped",
          transform_shape(res) and res["ok"] is True
          and res["text"] == "https://example.com/p", res.get("text"))
    res = C.transform(
        "https://example.com/page?utm_source=x&fbclid=abc&id=42&page=2",
        "strip_tracking_params")
    check("?... non-tracking parameters are kept in their order",
          res["ok"] is True
          and res["text"] == "https://example.com/page?id=42&page=2", res.get("text"))
    res = C.transform("https://example.com/p?utm_campaign=a#frag",
                      "strip_tracking_params")
    check("a fragment survives the strip", res["ok"] is True
          and res["text"] == "https://example.com/p#frag", res.get("text"))
    res = C.transform("no link here, id=42&utm_source=x stays",
                      "strip_tracking_params")
    check("text that is not a URL is returned exactly as it was",
          res["ok"] is True
          and res["text"] == "no link here, id=42&utm_source=x stays",
          res.get("text"))
    res = C.transform("https://example.com/plain", "strip_tracking_params")
    check("a URL with no query is unchanged",
          res["ok"] is True and res["text"] == "https://example.com/plain",
          res.get("text"))
    res = C.transform(
        "https://a.test/?utm_source=1 and https://b.test/?id=2&utm_source=3",
        "strip_tracking_params")
    check("EVERY http(s) link in the text is cleaned, not only the first",
          res["ok"] is True
          and res["text"] == "https://a.test/ and https://b.test/?id=2",
          res.get("text"))
    res = C.transform("https://x.test/?id=1&id=2&utm_source=z",
                      "strip_tracking_params")
    check("a repeated non-tracking parameter is kept, in order",
          res["ok"] is True and res["text"] == "https://x.test/?id=1&id=2",
          res.get("text"))

    unknown = C.transform("x", "shouty")
    check("an unknown kind is refused in plain words, not guessed at",
          transform_shape(unknown) and unknown["ok"] is False
          and unknown["reason"] == "that is not a transform I know", unknown)
    not_text = C.transform(42, "pretty_json")
    check("a non-text argument is refused as not text",
          transform_shape(not_text) and not_text["ok"] is False
          and not_text["reason"] == "that is not text", not_text)


# ----------------------------------------------------- no disk, from outside --

#: The child process's whole program. It installs the operating system's own
#: audit hook BEFORE importing the module, warms up the scrubber's lazy
#: imports, forgets everything the warm-up did, and only then drives the ring
#: and the transforms. The module is never asked what it does; the operating
#: system is asked what happened.
AUDIT_CHILD = r'''
import os
import sys

seen = []


def _watch(event, args):
    if event == "open":
        seen.append(args)


sys.addaudithook(_watch)

backend, rebuilt = sys.argv[1], sys.argv[2]
sys.path.insert(0, backend)
sys.path.append(rebuilt)

import jarvis_clipboard as C

# The scrubber imports its router and reads its known values lazily on the
# first call. Warm that up BEFORE the log is cleared, so a lazy import is not
# mistaken for the module touching a file during the work.
if C._scrub is not None:
    try:
        C._scrub.find_secret("warm up")
        C._scrub.scrub_text("warm up", identifiers=False)
    except Exception:
        pass
seen.clear()

before = sorted(os.listdir("."))

ring = C.ClipboardRing(enabled=True)
kept = ring.offer("the words that were copied", foreground_app="Code",
                  foreground_title="notes.py")
refused_otp = ring.offer("Your verification code is 482910")
refused_secret = ring.offer("password = hunter2")
table = C.transform('name,points\n"Ada, Lovelace",9\nGrace,10\n', "markdown_table")
pretty = C.transform('{"b": 1, "a": [1, 2]}', "pretty_json")
strip = C.transform("see https://example.com/p?utm_source=x&id=42 now",
                    "strip_tracking_params")
ring.clear()
ring.offer("after a clear")
ring.lock()
after = sorted(os.listdir("."))

problems = []
if kept.get("kept") is not True:
    problems.append("a plain offer was not kept: %r" % (kept,))
if refused_otp.get("reason") != "secret_or_otp_detected":
    problems.append("the one-time code was not refused: %r" % (refused_otp,))
if refused_secret.get("reason") != "secret_detected":
    problems.append("the labelled secret was not refused: %r" % (refused_secret,))
if table.get("text") != "| name | points |\n| --- | --- |\n| Ada, Lovelace | 9 |\n| Grace | 10 |\n":
    problems.append("the markdown table was wrong: %r" % (table.get("text"),))
if pretty.get("text") != '{\n  "b": 1,\n  "a": [\n    1,\n    2\n  ]\n}':
    problems.append("the pretty JSON was wrong: %r" % (pretty.get("text"),))
if strip.get("text") != "see https://example.com/p?id=42 now":
    problems.append("the stripped URL was wrong: %r" % (strip.get("text"),))
if ring.items != () or ring.enabled is not False:
    problems.append("the ring did not end wiped and off: %r" % (ring.items,))

print("file_access_events", len(seen))
print("files_before", len(before))
print("files_after", len(after))
print("new_files", after)
print("clean", not problems)
for problem in problems:
    print("problem", problem)
if seen:
    print("first_events", repr(seen[:3]))
sys.exit(0 if not problems and not seen and after == before else 1)
'''


def _tree(root: Path) -> list:
    """Every path under `root`, as text, for the "no file appeared" check."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def t_nothing_is_written_or_opened_on_disk():
    work = TMP / "disk-watch"
    config = work / "config"
    config.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["OPENJARVIS_CONFIG_DIR"] = str(config)
    env["JARVIS_CONFIG_DIR"] = str(config)
    env["PYTHONIOENCODING"] = "utf-8"
    before = _tree(work)
    run = subprocess.run(
        [sys.executable, "-B", "-c", AUDIT_CHILD,
         str(HERE), str(HERE / "rebuilt")],
        cwd=str(work), env=env, capture_output=True, text=True, timeout=120)
    after = _tree(work)
    out = (run.stdout or "").strip().splitlines()
    numbers = {}
    for line in out:
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].endswith(("events", "before", "after")):
            numbers[parts[0]] = parts[1].strip()
    check("the watched child process ran the module and exited cleanly",
          run.returncode == 0, f"exit {run.returncode}\n{run.stdout[-800:]}\n"
                               f"{run.stderr[-800:]}")
    access = numbers.get("file_access_events")
    check("driving the module opened NO file at all (the operating system's audit hook saw zero)",
          access is not None and access.isdigit() and int(access) == 0,
          f"file_access_events={access}\n{run.stdout[-800:]}")
    check("no file appeared in the fresh folder the module was driven in",
          after == before, f"before={before}\nafter={after}")
    check("the child's own counts of files before and after agree",
          numbers.get("files_before") is not None
          and numbers.get("files_before") == numbers.get("files_after"),
          numbers)
    check("the driven data still came back correct (no disk was needed for it)",
          "clean True" in (run.stdout or "") and "problem" not in run.stdout,
          run.stdout[-800:])


# ------------------------------------------------------------------- runner --

if __name__ == "__main__":
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
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
