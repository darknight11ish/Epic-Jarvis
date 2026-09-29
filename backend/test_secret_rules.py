"""test_secret_rules.py - the gitleaks rule data behind screen safety
(jarvis_secret_rules.py, made by tools/gen_secret_rules.py).

    python3 backend/test_secret_rules.py

What it proves:
  - the generator's three fixes are right: a flag in the middle of a Go
    pattern becomes a group with the same meaning, Go's \\z becomes \\Z, and a
    POSIX class is spelled out (the one a plain "does it compile" check
    would have let through - it compiles, and means something else);
  - every rule in the generated file compiles in Python and none was lost:
    221 rules, gitleaks's `pkcs12-file` (no pattern) the only one dropped;
  - rules that the fixes changed still find their own kind of token, and
    a real-shaped token is found through jarvis_secrets while the same rule
    is not fooled by ordinary words;
  - the data file's header says what it was made from and what changed, and
    the notices file credits gitleaks and Presidio (MIT asks for that).
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_secret_rules.py", "jarvis_secrets.py")

import gen_secret_rules as G  # noqa: E402
import jarvis_secret_rules as R  # noqa: E402
import jarvis_secrets as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_generator():
    p, ch = G.to_python(r"\b(p8e-(?i)[a-z0-9]{32})(?:[\x60'\"\s;]|\\[nr]|$)")
    check("a flag in the middle becomes a group closed where the group closes",
          "(?i:[a-z0-9]{32})" in p and ch == ["inline_i"], p)
    rx = re.compile(p, re.ASCII)
    check("... and it still means 'ignore case from there on'",
          rx.search("p8e-" + "AbCdEfGh" * 4) is not None and rx.search("P8E-" + "a" * 32) is None)
    p, ch = G.to_python(r"\b(sha256~[\w-]{43})(?:[^\w-]|\z)")
    check("Go's \\z becomes \\Z", r"\Z" in p and r"\z" not in p and ch == ["z"], p)
    check("... and an escaped backslash before a z is left alone",
          G.to_python(r"a\\z")[0] == r"a\\z")
    p, ch = G.to_python(r"\b(pat[[:alnum:]]{14}\.[a-f0-9]{64})\b")
    check("a POSIX class is spelled out",
          "[[:alnum:]]" not in p and "a-zA-Z0-9" in p and ch == ["posix"], p)
    good = "pat" + "AbC123xyzQ4567"[:14] + "." + "0123456789abcdef" * 4
    check("... and the repaired pattern finds a real-shaped Airtable token",
          re.compile(p, re.ASCII).search(good) is not None)
    wrong = re.compile(r"\b(pat[[:alnum:]]{14}\.[a-f0-9]{64})\b")      # Python's own reading
    check("... which Python's silent reading of the original does NOT",
          wrong.search(good) is None)
    p, ch = G.to_python(r"(?i)\bkey\b")
    check("a leading flag is left as it is", p == r"(?i)\bkey\b" and ch == [], p)
    p, _ = G.to_python(r"\bx(?i)[a-z]+(?-i:B)[a-z]")
    check("a switched-off flag inside a switched-on one stays", "(?-i:B)" in p)
    re.compile(p)
    p, ch = G.to_python(r"[(?i)]x")
    check("a bracket that only LOOKS like a flag is not touched", p == r"[(?i)]x" and ch == [], p)


def t_data():
    ids = [r["id"] for r in R.RULES]
    check("221 rules, none lost but the one with no pattern", len(ids) == 221 and "pkcs12-file" not in ids)
    check("no rule id twice", len(set(ids)) == len(ids))
    bad = []
    for r in R.RULES:
        try:
            re.compile(r["regex"], re.ASCII)
            for a in r["allow"]:
                for x in a["regexes"]:
                    re.compile(x, re.ASCII)
        except Exception as exc:
            bad.append((r["id"], str(exc)[:60]))
    check("every rule and every allowlist pattern compiles in Python", not bad, str(bad[:3]))
    for x in R.GLOBAL_ALLOW["regexes"]:
        re.compile(x, re.ASCII)
    check("the broad rule has its own allowlists and stopwords",
          any(r["id"] == "generic-api-key" and any(a["stopwords"] for a in r["allow"])
              for r in R.RULES))
    check("a rule that needed a file path is not in the data",
          all(a["target"] in ("secret", "match", "line") for r in R.RULES for a in r["allow"]))
    head = (HERE / "jarvis_secret_rules.py").read_text(encoding="utf-8")[:1800]
    check("the header says where it came from, what changed and the licence",
          "gitleaks" in head and "MIT" in head and "sha256" in head and "Zachary Rice" in head
          and "dropped: pkcs12-file" in head, head[:200])
    notices = (ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    check("the notices file credits gitleaks and Presidio, with the copyright lines",
          "gitleaks" in notices and "Zachary Rice" in notices and "Presidio" in notices
          and "Presidio Contributors" in notices)


SAMPLES = {
    # id -> a token in the shape the rule wants (made up; none is a real key)
    "github-pat": "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5",
    "aws-access-token": "AKIA" + "Z7Q3N5XK2VJ4W6MB",
    "slack-bot-token": "xoxb-" + "1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx",
    "stripe-access-token": "sk_live_" + "51H8xYz2Ab3Cd4Ef5Gh6Ij7Kl",
    "private-key": "-----BEGIN RSA PRIVATE KEY-----\n" + "MIIEowIBAAKCAQEA" + "x7Q2" * 20
                   + "\n-----END RSA PRIVATE KEY-----",
    "airtable-personnal-access-token": "pat" + "AbCdEfGh123456" + "." + "0123456789abcdef" * 4,
    "sendgrid-api-token": "SG." + "AbCdEfGhIjKlMnOpQrStUv" + "." + "0123456789AbCdEfGhIjKlMnOpQrStUv0123456789A"[:43],
    "linear-api-key": "lin_api_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5kL7m",
    "doppler-api-token": "dp.pt." + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5kL7mNpQ"[:43],
    "postman-api-token": "PMAK-" + "0123456789abcdef01234567" + "-" + "0123456789abcdef0123456789abcdef01",
    "openshift-user-token": "sha256~" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1eF3hJ5kL7mNpQ"[:43],
}


def t_samples():
    found_by = {}
    for sid, tok in SAMPLES.items():
        spans = S._gitleaks_spans("here: " + tok + " done\n", time_left())
        found_by[sid] = {x[2] for x in spans}
    for sid, tok in SAMPLES.items():
        check(f"a made-up {sid} token is found", bool(found_by[sid]), str(found_by[sid]))
    for sid in ("sendgrid-api-token", "linear-api-key", "doppler-api-token", "postman-api-token",
                "openshift-user-token"):
        check(f"{sid} (a flag/\\z fix) is found by its own rule", sid in found_by[sid],
              str(found_by[sid]))
    check("a token whose vendor's name is not on the screen is found by its shape",
          "airtable-personnal-access-token" in found_by["airtable-personnal-access-token"])
    check("ordinary sentences find nothing",
          not S._gitleaks_spans("The keyboard shortcut for the apiary report is on page 12, "
                                "and the tokens were counted by the author.\n",
                                time_left()))


def time_left():
    import time
    return time.monotonic() + 30


def main():
    for fn in (t_generator, t_data, t_samples):
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
