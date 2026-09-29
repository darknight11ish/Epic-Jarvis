#!/usr/bin/env python3
"""Writes backend/jarvis_secret_rules.py from gitleaks's own rule file.

    python3 tools/gen_secret_rules.py --from path/to/gitleaks.toml   # write it
    python3 tools/gen_secret_rules.py --url                          # download, write
    python3 tools/gen_secret_rules.py --from FILE --check            # compare only

WHAT THIS IS FOR. "Screen safety" (the owner's "all three", 2026-09-29)
blacks out anything that looks like a key, token or password in a picture of
the screen before a model or a text reader's output is used
(backend/jarvis_secrets.py). The patterns for it are gitleaks's
(https://github.com/gitleaks/gitleaks, config/gitleaks.toml, MIT, copyright
(c) 2019 Zachary Rice - credited in THIRD-PARTY-NOTICES.txt). The gitleaks
PROGRAM is not used, only its rule data, which this script turns into plain
Python data so the backend needs nothing new installed.

WHAT IT CHANGES, and only this (each change is counted in the file's header
and checked by backend/test_secret_rules.py):
  * gitleaks is written in Go, whose regular expressions allow a flag in the
    middle of a pattern - `X(?i)Y` means "from here on, ignore case, up to
    the end of the group". Python refuses that. It becomes `X(?i:Y)`, the same
    meaning, closed where the group closes.
  * Go's `\\z` (the very end of the text) is Python's `\\Z`.
  * Go's `[[:alnum:]]` is not understood by Python - worse, Python does not
    refuse it, it silently reads it as a different set of characters. It
    becomes `a-zA-Z0-9`. (One rule; this is the one a plain "does it compile"
    check would have passed.)
  * The one rule with no pattern at all (`pkcs12-file`: it matches a file
    NAME, and a screen has none) is dropped.
Everything else is kept as gitleaks wrote it: the pattern, the entropy bar,
the secret group, the keyword pre-filter and the rule's own allowlists.
Allowlists that need a file path are dropped (a screen has no path).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

try:
    import tomllib
except ImportError:            # Python 3.10
    import tomli as tomllib    # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "jarvis_secret_rules.py"
URL = "https://raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml"

_POSIX = {
    "alnum": "a-zA-Z0-9", "alpha": "a-zA-Z", "digit": "0-9", "xdigit": "0-9A-Fa-f",
    "upper": "A-Z", "lower": "a-z", "word": "0-9A-Za-z_", "space": " \\t\\n\\r\\f\\v",
    "blank": " \\t",
}


def _group_end(rx: str, start: int) -> int:
    """Index of the ')' that closes the group the text at `start` is in (or
    len(rx) at the top level). Skips escapes and [character classes]."""
    depth, i, n = 0, start, len(rx)
    while i < n:
        c = rx[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            i += 1
            if i < n and rx[i] == "^":
                i += 1
            if i < n and rx[i] == "]":
                i += 1
            while i < n and rx[i] != "]":
                if rx[i] == "\\":
                    i += 1
                elif rx[i] == "[" and rx[i:i + 2] == "[:":
                    j = rx.find(":]", i)
                    i = j + 1 if j > 0 else i
                i += 1
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return n


def _skip_class(rx: str, i: int) -> int:
    """`i` is at a '[': the index just after the matching ']'."""
    n = len(rx)
    i += 1
    if i < n and rx[i] == "^":
        i += 1
    if i < n and rx[i] == "]":
        i += 1
    while i < n and rx[i] != "]":
        if rx[i] == "\\":
            i += 1
        i += 1
    return i + 1


def _find_flag(rx: str, start: int) -> int:
    """Index of the next `(?i)` at or after `start` that is a real group
    opener (not escaped, not inside a [class]), or -1."""
    i, n = start, len(rx)
    while i < n:
        c = rx[i]
        if c == "\\":
            i += 2
        elif c == "[":
            i = _skip_class(rx, i)
        elif rx.startswith("(?i)", i):
            return i
        else:
            i += 1
    return -1


def _scope_flags(rx: str, top: bool) -> tuple:
    """(pattern, how many inline flags were made into groups)."""
    out, i, count = [], 0, 0
    while i < len(rx):
        j = _find_flag(rx, i)
        if j < 0:
            out.append(rx[i:])
            break
        if j == 0:
            if top:
                out.append("(?i)")           # a leading flag is fine in Python
            i = j + 4                        # (inside a scope already: a no-op)
            continue
        end = _group_end(rx, j + 4)
        inner, m = _scope_flags(rx[j + 4:end], False)
        out.append(rx[i:j] + "(?i:" + inner + ")")
        count += 1 + m
        i = end
    return "".join(out), count


def to_python(rx: str) -> tuple:
    """(python pattern, [what changed]). See the module docstring."""
    changed = []

    def posix(m):
        name = m.group(1)
        if name not in _POSIX:
            raise ValueError("unknown POSIX class " + name)
        changed.append("posix")
        return _POSIX[name]

    rx = re.sub(r"\[:([a-z]+):\]", posix, rx)
    if "\\z" in rx:
        rx = re.sub(r"(?<!\\)((?:\\\\)*)\\z", r"\1\\Z", rx)
        changed.append("z")
    rx, n = _scope_flags(rx, True)
    if n:
        changed.append("inline_i")
    return rx, changed


def _clean_allow(a: dict):
    if a.get("paths"):
        return None                      # a screen has no file path
    regexes = []
    for r in a.get("regexes") or []:
        p, _c = to_python(r)
        regexes.append(p)
    stops = [str(s).lower() for s in a.get("stopwords") or []]
    if not regexes and not stops:
        return None
    return {"target": a.get("regexTarget") or "secret", "regexes": regexes, "stopwords": stops}


def build(doc: dict) -> tuple:
    rules, counts = [], {"inline_i": 0, "z": 0, "posix": 0, "dropped": []}
    for r in doc["rules"]:
        rx = r.get("regex")
        if not rx:
            counts["dropped"].append(r["id"])
            continue
        p, changed = to_python(rx)
        for c in set(changed):
            counts[c] += 1
        rules.append({
            "id": r["id"], "regex": p,
            "entropy": float(r.get("entropy") or 0.0),
            "group": int(r.get("secretGroup") or 0),
            "keywords": [str(k).lower() for k in r.get("keywords") or []],
            "allow": [x for x in (_clean_allow(a) for a in r.get("allowlists") or []) if x],
        })
    g = doc.get("allowlist") or {}
    glob = {"regexes": [to_python(x)[0] for x in g.get("regexes") or []],
            "stopwords": [str(s).lower() for s in g.get("stopwords") or []]}
    return rules, glob, counts


def render(rules: list, glob: dict, counts: dict, sha: str, minv: str) -> str:
    lines = [
        '"""jarvis_secret_rules.py - GENERATED by tools/gen_secret_rules.py. Do not edit by hand.',
        "",
        "The rule data behind \"screen safety\" (backend/jarvis_secrets.py): what a key,",
        "token or password looks like. It is gitleaks's rule file, config/gitleaks.toml",
        "(https://github.com/gitleaks/gitleaks), turned into plain Python data. The",
        "gitleaks program itself is not used.",
        "",
        "gitleaks is MIT-licensed, copyright (c) 2019 Zachary Rice; the notice is in",
        "THIRD-PARTY-NOTICES.txt, as MIT asks.",
        "",
        f"Source: gitleaks master, config/gitleaks.toml, minVersion {minv}, sha256 {sha}",
        f"({len(rules)} rules with a pattern; fetched 2026-09-29).",
        f"Changed on the way in (tools/gen_secret_rules.py says why): {counts['inline_i']} inline (?i)",
        f"flags made into groups, {counts['z']} \\z -> \\Z, {counts['posix']} POSIX class(es) spelled out,",
        f"dropped: {', '.join(counts['dropped']) or 'none'} (it has no pattern - it matches a file name).",
        '"""',
        "# fmt: off",
        "",
        "#: Each rule: id, regex (Python `re`, used with re.ASCII like Go's), entropy",
        "#: (0 = no bar), group (which capture group is the secret; 0 = the first one",
        "#: there is, else the whole match), keywords (lowercase; the rule is only",
        "#: tried when one is in the text) and allow (that rule's own allowlists:",
        "#: target \"secret\"/\"match\"/\"line\", regexes, stopwords).",
        "RULES = (",
    ]
    for r in rules:
        lines.append("    " + repr(r) + ",")
    lines.append(")")
    lines.append("")
    lines.append("#: gitleaks's global allowlist (regexes and stopwords). Used ONLY with the broad")
    lines.append("#: generic-api-key rule, never with the specific token formats (see")
    lines.append("#: jarvis_secrets.py: a real token containing the word \"false\" must still be hidden).")
    lines.append("GLOBAL_ALLOW = " + repr(glob))
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", help="a local gitleaks.toml")
    ap.add_argument("--url", action="store_true", help="download gitleaks master's config")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.url:
        raw = urllib.request.urlopen(URL, timeout=60).read()
    elif a.src:
        raw = Path(a.src).read_bytes()
    else:
        ap.error("give --from FILE or --url")
    doc = tomllib.loads(raw.decode("utf-8"))
    rules, glob, counts = build(doc)
    text = render(rules, glob, counts, hashlib.sha256(raw).hexdigest(), doc.get("minVersion", "?"))
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("up to date" if ok else "OUT OF DATE")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(rules)} rules; {counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
