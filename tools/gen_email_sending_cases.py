#!/usr/bin/env python3
"""Writes the email-sending contract file for both apps, and checks it.

    python3 tools/gen_email_sending_cases.py            # write both copies
    python3 tools/gen_email_sending_cases.py --check    # compare only

What GET /api/email/sending really answers (backend/jarvis_email_send.py,
email-send.patch), in named situations, and one example approval card
(describe()), made by the real code - nothing is written by hand:

    jarvis-desktop/tests/fixtures/email-sending-cases.json
    jarvis-client/app/src/test/resources/contract/email-sending-cases.json

(byte-identical). Both apps build against it: the desktop's Rust and
JavaScript tests, and the phone's EmailSendingTest.

The account is a fake in this process's environment only; its password is
built by concatenation and must not appear in the output (checked).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
os.environ["OPENJARVIS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="jarvis-es-cases-")
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_email_send as SEND  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "email-sending-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "email-sending-cases.json")
COPIES = (DESKTOP, PHONE)

# A fake password, built by concatenation; it never appears in the output.
_FAKE = "pw" + "-cases-" + "0123456789"
_NAMES = (SEND.USER_ENV, SEND.PASSWORD_ENV, SEND.IMAP_HOST_ENV, SEND.SMTP_HOST_ENV,
          SEND.SMTP_PORT_ENV, SEND.SMTP_TLS_ENV)


def _env(**kw):
    for n in _NAMES:
        os.environ.pop(n, None)
    for k, v in kw.items():
        os.environ[k] = v


def cases() -> dict:
    ask = lambda a: "ask"
    on = lambda: {SEND.TOOL}
    off = lambda: set()
    gmail = {SEND.USER_ENV: "owner@example.com", SEND.PASSWORD_ENV: _FAKE,
             SEND.IMAP_HOST_ENV: "imap.gmail.com"}
    out = {}
    _env()
    out["not_set_up"] = SEND.view(tools_enabled=off, tier_of=ask)
    _env(**gmail)
    out["tool_off"] = SEND.view(tools_enabled=off, tier_of=ask)
    out["ready"] = SEND.view(tools_enabled=on, tier_of=ask)
    out["refused_auto"] = SEND.view(tools_enabled=on, tier_of=lambda a: "auto")
    out["switched_off"] = SEND.view(tools_enabled=on, tier_of=lambda a: "never")
    _env(**gmail, **{SEND.SMTP_HOST_ENV: "smtp.office365.com", SEND.SMTP_PORT_ENV: "587"})
    out["starttls"] = SEND.view(tools_enabled=on, tier_of=ask)
    p = SEND.plan(["alex@example.com"], ["sam@example.org"], "Dinner on Friday",
                  "Hi Alex,\n\nFriday at 7 works for me. [the menu](https://example.com/menu)"
                  "\n\n**See you there.**\n\nMario")
    card = SEND.describe(p)
    _env()
    return {"cases": out,
            # A backend without jarvis_email_send.py (the route's 503).
            "missing": {"status": 503, "body": {"available": False,
                                                "error": "ModuleNotFoundError"}},
            # One card, as the approval queue carries it (`detail.text`),
            # with markdown-looking text in the email: both apps must show
            # it word for word, never as formatting.
            "example_card": card,
            "example_body": p.body,
            "limits": {"recipients": SEND.MAX_RECIPIENTS, "subject_chars": SEND.MAX_SUBJECT_CHARS,
                       "body_chars": SEND.MAX_BODY_CHARS}}


def render() -> str:
    text = json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert _FAKE not in text, "the password reached the contract file"
    return text


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_email_sending_cases.py")
        if stale:
            return 1
        print("email-sending-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
