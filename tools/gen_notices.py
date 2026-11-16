#!/usr/bin/env python3
"""Regenerate THIRD-PARTY-NOTICES.txt (the desktop installer's notices file).

    python3 tools/gen_notices.py            write it (Rust and Python halves)
    python3 tools/gen_notices.py --check    exit 1 if it is out of date
    python3 tools/gen_notices.py --diff     say which crates came and went
    python3 tools/gen_notices.py --python   write the Python section only
    python3 tools/gen_notices.py --check --python
                                            exit 1 if the Python section is out
                                            of date, naming each package that
                                            differs (no cargo needed)

What it does, in plain words:

1. Asks cargo which Rust libraries the WINDOWS build of the desktop app uses
   (`cargo metadata --filter-platform x86_64-pc-windows-msvc`, the same graph
   CI's `cargo deny` checks), following normal and build dependencies and
   leaving out test-only ones. Cargo must have downloaded them already (any
   `cargo check` does), because step 3 reads their licence files.
2. For each library, picks the licence Jarvis follows. A library offered
   under a choice ("MIT OR Apache-2.0") is used under the first of PREFER
   that it offers; one under several at once ("... AND ...") under all.
3. Reads each library's own licence files for its copyright lines, because
   MIT, BSD, ISC and Zlib ask for "the above copyright notice" to go with
   every copy. When a library's files name no copyright holder, its authors
   from Cargo.toml are named instead, and the line says so.
4. Writes the file: a plain header; the hand-written sections kept exactly
   as they are in the current file (everything from the first section
   marked "not generated" to SUMMARY BY LICENCE - fonts, models, code
   adapted into the backend); the Rust summary; the full list with versions
   and copyright lines; the Python packages from backend/requirements.lock
   with the licence each one declares; any Apache NOTICE files; and the full
   text of every licence used, once each.

The Rust half uses no network: cargo reads its own lockfile and the files it
already downloaded (`--offline`). The Python half asks PyPI's JSON API for
each pinned release's own metadata - name and version only, a generic
User-Agent, no account or key - because that is the only answer that is about
the LOCK rather than about whatever happens to be installed on this machine.
It needs no cargo, which is why `--check --python` can run in CI's
informational `audit` job, where the notices file is guarded today.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAURI = REPO / "jarvis-desktop" / "src-tauri"
OUT = REPO / "THIRD-PARTY-NOTICES.txt"
TARGET = "x86_64-pc-windows-msvc"

#: For a choice of licences, the one Jarvis follows: the first of these the
#: library offers.
PREFER = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "Zlib", "0BSD",
          "MIT-0", "Unlicense", "CC0-1.0", "BSL-1.0", "Unicode-3.0", "MPL-2.0"]

#: Licences whose text asks for the holder's copyright line with every copy.
NEEDS_COPYRIGHT = {"MIT", "BSD-3-Clause", "BSD-2-Clause", "ISC", "Zlib", "BSL-1.0"}

#: Where each licence's full text is read from: a library in the graph that
#: carries it as a file. The texts that have a copyright line of their own
#: (MIT, BSD, ISC) are written out below instead, as the standard template.
TEXT_FROM = {
    "Apache-2.0": [("tauri", "LICENSE_APACHE-2.0"), ("serde", "LICENSE-APACHE"),
                   ("anyhow", "LICENSE-APACHE")],
    "BSL-1.0": [("clipboard-win", "LICENSE"), ("ryu", "LICENSE-BOOST")],
    "Unicode-3.0": [("icu_collections", "LICENSE"), ("zerovec", "LICENSE")],
    "MPL-2.0": [("option-ext", "LICENSE.txt"), ("option-ext", "LICENSE"),
                ("cssparser", "LICENSE")],
}

TEMPLATES = {
    "MIT": """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.""",
    "BSD-3-Clause": """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.""",
    "BSD-2-Clause": """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.""",
    "ISC": """Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.""",
    "Zlib": """This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.
2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.""",
}

LICENCE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|COPYRIGHT|UNLICENSE)", re.I)
COPYRIGHT_LINE = re.compile(r"^\s*(copyright\b|\(c\)\s+\d{4}|©)", re.I)
PLACEHOLDER = re.compile(r"\[yyyy\]|\[name of copyright owner\]|<year>|<copyright|"
                         r"\{yyyy\}|\{name of copyright owner\}|YEAR|OWNER|"
                         r"copyright notice|copyright holder|copyright statement|"
                         r"copyright license|copyright and license",
                         re.I)


def metadata() -> dict:
    # `encoding="utf-8", errors="replace"` is not decoration. Without it Python
    # decodes cargo's output with the console's own code page - cp1252 on the
    # owner's Windows machine - and a crate whose metadata carries one byte
    # that page has no character for kills subprocess's reader thread. The
    # thread then leaves `.stdout` as None and `json.loads(out)` dies with
    # "the JSON object must be str, bytes or bytearray, not NoneType", which
    # says nothing about the real cause. It is the same fault
    # backend/run_suites.py records fixing on 2026-10-03 (test_mail_mask.py),
    # and CI never sees it because the Ubuntu runner is already UTF-8.
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--offline", "--locked",
         "--filter-platform", TARGET],
        cwd=TAURI, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace").stdout
    return json.loads(out)


def shipped(meta: dict) -> list:
    """Every package the Windows build compiles: normal and build
    dependencies from the app down, not test-only ones."""
    by_id = {p["id"]: p for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    root = meta["resolve"]["root"]
    seen, todo = set(), [root]
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        for dep in nodes[i]["deps"]:
            if any(k.get("kind") != "dev" for k in dep["dep_kinds"]):
                todo.append(dep["pkg"])
    seen.discard(root)
    return sorted((by_id[i] for i in seen), key=lambda p: (p["name"], _vkey(p["version"])))


def _vkey(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.+-]", v))


def _tokens(expr: str) -> list:
    return re.findall(r"\(|\)|[A-Za-z0-9.+-]+", expr.replace("/", " OR "))


def _parse(tokens: list) -> list:
    """SPDX expression -> list of alternatives, each a set of licences that
    all apply ("A OR (B AND C)" -> [{A}, {B, C}]). WITH exceptions are kept
    on the licence name."""
    def expr(i):
        alts, i = term(i)
        while i < len(tokens) and tokens[i].upper() == "OR":
            more, i = term(i + 1)
            alts = alts + more
        return alts, i

    def term(i):
        alts, i = atom(i)
        while i < len(tokens) and tokens[i].upper() == "AND":
            more, i = atom(i + 1)
            alts = [a | b for a in alts for b in more]
        return alts, i

    def atom(i):
        if tokens[i] == "(":
            alts, i = expr(i + 1)
            return alts, i + 1
        name = tokens[i]
        i += 1
        if i < len(tokens) and tokens[i].upper() == "WITH":
            name = f"{name} WITH {tokens[i + 1]}"
            i += 2
        return [frozenset([name])], i

    alts, _ = expr(0)
    return alts


def chosen(expr: str) -> frozenset:
    """The licences Jarvis follows for one package."""
    alts = _parse(_tokens(expr))

    def rank(alt):
        return (len(alt), sorted(PREFER.index(x.split(" WITH ")[0])
                                 if x.split(" WITH ")[0] in PREFER else 99 for x in alt))
    return min(alts, key=rank)


def _licence_files(pkg: dict) -> list:
    base = Path(pkg["manifest_path"]).parent
    files = [f for f in sorted(base.iterdir()) if f.is_file() and LICENCE_FILE.match(f.name)]
    if pkg.get("license_file"):
        f = base / pkg["license_file"]
        if f.is_file() and f not in files:
            files.append(f)
    return files


def copyright_lines(pkg: dict) -> list:
    lines = []
    for f in _licence_files(pkg):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if (COPYRIGHT_LINE.match(line) and not PLACEHOLDER.search(line)
                    and 12 <= len(line) <= 200 and line not in lines):
                lines.append(line)
    return lines[:6]


def notice_files(pkg: dict) -> list:
    base = Path(pkg["manifest_path"]).parent
    return [f for f in sorted(base.iterdir()) if f.is_file() and re.match(r"^NOTICE", f.name, re.I)]


def licence_text(name: str, by_name: dict) -> str:
    if name in TEMPLATES:
        return TEMPLATES[name]
    for crate, fname in TEXT_FROM.get(name, []):
        for pkg in by_name.get(crate, []):
            f = Path(pkg["manifest_path"]).parent / fname
            if f.is_file():
                return f.read_text(encoding="utf-8", errors="replace").strip("\n")
    return ""


# ---------------------------------------------------------------------------
# THE PYTHON HALF
#
# `--python` keeps section 3, the Python packages backend/requirements.lock
# pins. It asks nothing of cargo, so the Python half can be checked on a
# machine with no Rust - and CI's informational `audit` job runs it.
#
# WHERE EACH LICENCE COMES FROM, AND WHY. The package's own published metadata
# for exactly the pinned version, through PyPI's JSON API - the same source,
# with the same generic User-Agent and the same three retries, that
# tools/check_python_advisories.py already reads for advisories. That is the
# only source that can answer for the LOCK rather than for a machine:
#
#   * tools/requirements-dev.txt lists `pip-licenses` (MIT), and this file
#     invokes it as a SECOND READER, printing any package the two describe
#     differently (see cross_check below). It is deliberately not the source
#     of the rows. pip-licenses reads the packages INSTALLED in the
#     environment it runs in, and installed packages drift from the lock - on
#     the owner's PC on 2026-11-16, five of the lock's 78 pins were installed
#     at another version (certifi, filelock, magika, numpy, soupsieve), so its
#     answer would describe the wrong release for those five. In CI nothing is
#     installed at all, and there would be no rows to compare against. A
#     notice that changes with the machine reading it cannot guard a committed
#     file.
#   * Nothing is guessed from a package's name, its dependencies or its
#     reputation. A package whose metadata states no licence reads `unknown`;
#     one whose statement is too vague to put here as fact keeps its own words
#     and is listed at the end. Both are what stops "probably MIT" becoming
#     "MIT" - the whole point of the audit finding this answers
#     (docs/DEEP-AUDITS-2026-10-05.md, section "Three structural problems",
#     problem 3: no generated notice covers anything but Rust crates).
# ---------------------------------------------------------------------------

LOCK = REPO / "backend" / "requirements.lock"
DEV_REQS = REPO / "tools" / "requirements-dev.txt"
PYPI = "https://pypi.org/pypi/{name}/{version}/json"
PYPI_USER_AGENT = "jarvis-third-party-notices/1 (+https://pypi.org)"
PY_HEADING = "3. PYTHON PACKAGES THE BACKEND INSTALLS (generated)"
PY_NEXT_HEADING = "\n4. APACHE-2.0 NOTICE FILES"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")
#: The shape of a licence EXPRESSION: names joined by AND / OR / WITH.
SPDX_EXPR = re.compile(r"[A-Za-z0-9.+-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+-]+)*")

#: A declaration -> the licence name, where the package's own words leave no
#: room to doubt. Deliberately ABSENT: "BSD" and "BSD License" (nothing says
#: 2-clause or 3-clause), "Apache Software License" (nothing says which
#: version), "Dual License", "Apache licensed, as found in the LICENSE file",
#: and any statement naming more than one licence. Those are printed in the
#: package's own words and listed at the end for a person - never guessed.
PY_NAMES = {
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license (mit)": "MIT",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "2-clause bsd license": "BSD-2-Clause",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "psf-2.0": "PSF-2.0",
    "psfl": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "mit-0": "MIT-0",
    "mit-cmu": "MIT-CMU",
    "isc": "ISC",
    "isc license (iscl)": "ISC",
    "zlib": "Zlib",
    "bsl-1.0": "BSL-1.0",
    "boost software license 1.0 (bsl-1.0)": "BSL-1.0",
    "0bsd": "0BSD",
    "unlicense": "Unlicense",
    "the unlicense (unlicense)": "Unlicense",
    "cc0-1.0": "CC0-1.0",
}

#: Declarations pip-licenses prints for a package whose own metadata is
#: coarser than the row above, with the licence each one can stand for. Used
#: only by the second-opinion check, never to write a row.
PIP_COARSE = {
    "bsd license": ("BSD-2-Clause", "BSD-3-Clause"),
    "apache software license": ("Apache-2.0",),
    "mit license": ("MIT",),
    "mozilla public license 2.0 (mpl 2.0)": ("MPL-2.0",),
    "python software foundation license": ("PSF-2.0",),
    "osi approved": (),          # a classifier that names no licence at all
}

#: The start of the Rust section, used to stop `--diff` reading Python rows as
#: crates that were removed.
RUST_HEADING = "2. RUST LIBRARIES IN THE DESKTOP PROGRAM"


def lock_pins(text: str) -> list:
    """(name, version) for every pin in the lock, in file order, once each.

    A name may appear twice with different versions and an environment marker
    (numpy is 2.4.6 below Python 3.12 and 2.5.3 at or above it; magika is
    0.6.2 on Windows and 0.6.3 elsewhere), so the pair is the key, not the
    name.
    """
    out, seen = [], set()
    for line in text.splitlines():
        m = PIN.match(line)
        if not m:
            continue
        key = (m.group(1).lower(), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        out.append((m.group(1), m.group(2)))
    return out


def dev_tools() -> list:
    """Names tools/requirements-dev.txt asks for that the lock does not pin.

    These are the tools used to build or check the notices - pip-licenses is
    one - and they are not Jarvis dependencies: they must never reach the
    lock, and they are not listed as packages Jarvis installs.
    """
    if not DEV_REQS.is_file():
        return []
    pinned = {name.lower() for name, _ in lock_pins(LOCK.read_text(encoding="utf-8"))}
    names = set()
    for line in DEV_REQS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if m and m.group(1).lower() not in pinned:
            names.add(m.group(1))
    return sorted(names)


def _first_line(text: str) -> str:
    """The first non-empty line of a field, whitespace squashed.

    Some projects put the entire licence text in the metadata's `license`
    field (fsrs, pandas). Its first line still names the licence, in the
    project's own words, which is evidence - where the field as a whole is
    60 KB of terms and conditions it is not a name.
    """
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line:
            return line
    return ""


def _looks_like_a_name(text: str) -> bool:
    """Is this a licence NAME, rather than a paragraph or a copyright line?"""
    return (bool(text) and len(text) <= 80 and not text.lower().startswith("copyright"))


def declaration(name: str, version: str, fetch=None) -> dict:
    """What PyPI says the pinned release itself declares about its licence."""
    url = PYPI.format(name=urllib.parse.quote(name), version=urllib.parse.quote(version))
    if fetch is None:
        def fetch(u):
            req = urllib.request.Request(u, headers={"User-Agent": PYPI_USER_AGENT,
                                                     "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
    last = None
    for attempt in range(3):
        try:
            data = fetch(url)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SystemExit(f"{name}=={version} is pinned in "
                                 f"{LOCK.relative_to(REPO)} but PyPI has no such release") from None
            last = exc
        except Exception as exc:      # a network hiccup: try twice more
            last = exc
        time.sleep(2 * (attempt + 1))
    else:
        raise SystemExit(f"PyPI did not answer for {name}=={version} "
                         f"({type(last).__name__}). The Python rows are read from it, "
                         "so nothing was written and nothing was changed.")
    info = data.get("info") or {}
    return {"license": info.get("license") or "",
            "expression": info.get("license_expression") or "",
            "classifiers": [c for c in (info.get("classifiers") or []) if isinstance(c, str)]}


def py_licence(decl: dict) -> tuple:
    """(name, the words it came from, might this be stated as fact?).

    The order matters: a PEP 639 licence expression is the project's machine-
    readable answer, then its `license` field, then the OSI classifier. Every
    value that is not mapped in PY_NAMES is returned in the project's own
    words with `False`, which is what puts it in the list at the end.
    """
    expr = " ".join(decl["expression"].split())
    if expr and SPDX_EXPR.fullmatch(expr):
        return expr, expr, True
    words = _first_line(decl["license"])
    if _looks_like_a_name(words):
        fixed = PY_NAMES.get(words.lower())
        if fixed:
            return fixed, words, True
        # "MPL-2.0 AND MIT" is a licence expression, not prose: a project
        # naming two licences that way means both. A SINGLE word is not
        # treated this way, or "BSD" would pass as if it named a licence.
        if re.search(r"\s(?:AND|OR|WITH)\s", words.upper()) and SPDX_EXPR.fullmatch(words):
            return words, words, True
        return words, words, False
    for c in decl["classifiers"]:
        if c.startswith("License ::"):
            short = c.rsplit(" :: ", 1)[-1].strip()
            if not short:
                continue
            fixed = PY_NAMES.get(short.lower())
            return (fixed, short, True) if fixed else (short, short, False)
    return "unknown", "", False


def python_rows(fetch=None) -> list:
    """One row per pinned release, sorted the way the file prints them."""
    rows = []
    for name, version in lock_pins(LOCK.read_text(encoding="utf-8")):
        label, declared, certain = py_licence(declaration(name, version, fetch))
        rows.append({"name": name, "version": version, "label": label,
                     "declared": declared, "certain": certain})
    return sorted(rows, key=lambda r: (r["name"].lower(), _vkey(r["version"])))


def _para(text: str, indent: str = "") -> str:
    """One wrapped paragraph, so no line in the file runs on forever."""
    return textwrap.fill(" ".join(text.split()), width=78,
                         initial_indent=indent, subsequent_indent=indent) + "\n"


def build_python_section(rows=None, fetch=None) -> str:
    """Section 3, exactly as it is written to the file."""
    rows = python_rows(fetch) if rows is None else rows
    by_licence, confirm = defaultdict(set), []
    for r in rows:
        by_licence[r["label"]].add(r["name"])
        if not r["certain"]:
            confirm.append(r)

    title = PY_HEADING
    out = [f"{title}\n", "=" * (len(title) + 1), "\n\n"]
    out.append(_para(
        f"{len(rows)} pinned releases, from backend/requirements.lock (every one "
        "pinned exactly, with the sha256 of each file PyPI publishes for it). A "
        "licence here is the one the package's own published metadata declares for "
        "exactly that version, read from PyPI's JSON API - the same source "
        "tools/check_python_advisories.py reads. Nothing is inferred from a package's "
        "name, its dependencies or what other projects say about it. Pip installs "
        "these on the PC; none is shipped inside either app.\n"))
    out.append("\nSUMMARY BY LICENCE\n------------------\n")
    for label in sorted(by_licence):
        names = sorted(by_licence[label], key=str.lower)
        out.append(f"{label} ({len(names)}): {', '.join(names)}\n")
    out.append("\nFULL LIST\n---------\n")
    for r in rows:
        extra = ""
        if r["declared"] and r["declared"].lower() != r["label"].lower():
            extra = f' (declared: "{r["declared"]}")'
        out.append(f'{r["name"]} {r["version"]} - {r["label"]}{extra}\n')

    out.append("\nLICENCES A PERSON MUST CONFIRM\n" + "-" * 30 + "\n\n")
    if not confirm:
        out.append(_para("None: every package's metadata names its licence without "
                         "ambiguity."))
    for r in confirm:
        url = f"https://pypi.org/project/{r['name']}/{r['version']}/"
        if r["label"] == "unknown":
            out.append(_para(f'{r["name"]} {r["version"]} - UNKNOWN', indent="  "))
            out.append(_para("Its published metadata states no licence at all: no "
                             "licence expression, no licence field and no OSI "
                             "classifier. This has to be found out before the package "
                             "can be relied on.", indent="    "))
        else:
            out.append(_para(f'{r["name"]} {r["version"]} - "{r["declared"]}"',
                             indent="  "))
            out.append(_para("Too vague to state as a fact here: it does not name a "
                             "single licence this file can write down. A person has to "
                             "read the package's own licence file and record what it "
                             "says.", indent="    "))
        out.append(f"    {url}\n")

    atoms = set()
    for r in rows:
        if r["certain"]:
            atoms.update(re.split(r"\s+(?:AND|OR|WITH)\s+", r["label"]))
    no_text = sorted(atoms - set(TEMPLATES) - set(TEXT_FROM))
    out.append("\nLICENCE TEXTS\n-------------\n\n")
    out.append(_para(
        "Section 5 carries the full text of MIT, BSD-3-Clause, BSD-2-Clause, ISC, "
        "Zlib, Apache-2.0, MPL-2.0 and BSL-1.0, once each; those cover every package "
        "above under them."))
    if no_text:
        out.append(_para("No text is reproduced in this file for: " + ", ".join(no_text)
                         + ". Each of those is the package's own licence file, which "
                         "pip installs beside the package."))
    tools = dev_tools()
    if tools:
        out.append("\n")
        out.append(_para(
            "The tools used to build and cross-check this section are named in "
            "tools/requirements-dev.txt (" + ", ".join(tools) + "). They are "
            "development-time readers, not Jarvis dependencies: they are not in "
            "backend/requirements.lock and are not listed above."))
    return "".join(out)


def python_section(text: str) -> str:
    """The Python section of a notices file, or "" when it has none yet."""
    start = text.find(PY_HEADING)
    if start < 0:
        return ""
    end = text.find(PY_NEXT_HEADING, start)
    return text[start:end] if end > 0 else text[start:]


def replace_python_section(text: str, fresh: str) -> str:
    """`text` with its Python section swapped for `fresh`, nothing else moved."""
    start = text.find(PY_HEADING)
    if start < 0:
        raise SystemExit("THIRD-PARTY-NOTICES.txt has no Python section yet: run "
                         "python3 tools/gen_notices.py once (it needs cargo) to add it, "
                         "and --python keeps it up to date from then on")
    end = text.find(PY_NEXT_HEADING, start)
    if end < 0:
        raise SystemExit("the Python section is not followed by the Apache NOTICE "
                         "section, so there is no safe place to stop replacing")
    return text[:start] + fresh.rstrip("\n") + "\n" + text[end:]


def python_rows_in(text: str) -> dict:
    """{(name, version): licence text} as a notices file's FULL LIST says it.

    Only the FULL LIST is read: the rows in the confirm list carry the
    package's own vague words instead of a licence name, and reading those
    would report a difference on every package a person still has to check.
    """
    block = python_section(text)
    start = block.find("\nFULL LIST\n")
    if start < 0:
        return {}
    end = block.find("\nLICENCES A PERSON MUST CONFIRM", start)
    if end > 0:
        block = block[start:end]
    rows = {}
    for m in re.finditer(r"^([A-Za-z0-9][A-Za-z0-9._-]*) ([^ \n]+) - (.+)$", block, re.M):
        rows[(m.group(1), m.group(2))] = m.group(3)
    return rows


def python_differences(current: str, fresh: str) -> list:
    """One line per package the written file and a fresh reading disagree on."""
    old, new = python_rows_in(current), python_rows_in(fresh)
    out = []
    for key in sorted(set(old) | set(new), key=lambda k: (k[0].lower(), _vkey(k[1]))):
        where = " ".join(key)
        if key not in old:
            out.append(f'not in the file yet: {where} ({new[key]})')
        elif key not in new:
            out.append(f"no longer in the lock: {where}")
        elif old[key] != new[key]:
            out.append(f'{where}: the file says "{old[key]}", the release says "{new[key]}"')
    if not out and python_section(current) != fresh:
        out.append("the section text differs outside the rows (read the two by eye)")
    return out


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pip_licences() -> dict:
    """{canonical name: (version, licence words)} from pip-licenses, or {}.

    pip-licenses is a development tool (tools/requirements-dev.txt). It reads
    what is INSTALLED, so this is only ever a second opinion - see the long
    note at the top of this block.
    """
    for cmd in ([sys.executable, "-m", "piplicenses"], ["pip-licenses"]):
        try:
            done = subprocess.run(cmd + ["--format=json"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0 and done.stdout.lstrip().startswith("["):
            try:
                data = json.loads(done.stdout)
            except ValueError:
                continue
            return {_canonical(d.get("Name", "")): (d.get("Version"), d.get("License") or "")
                    for d in data if d.get("Name")}
    return {}


def cross_check(rows: list) -> list:
    """Where pip-licenses describes a package differently from section 3.

    A second reader that disagrees is worth a person's attention, so every
    disagreement is printed. It deliberately does NOT change the exit code:
    pip-licenses reads the installed environment, which is not what the file
    records, and a check that is red on one machine and green on another
    cannot guard a committed file.
    """
    seen = pip_licences()
    if not seen:
        return []
    notes = []
    for r in rows:
        got = seen.get(_canonical(r["name"]))
        if not got or got[0] != r["version"]:
            continue
        said = " ".join((got[1] or "").split())
        label = r["label"]
        if not said or said.upper() == "UNKNOWN":
            if label != "unknown":
                notes.append(f'{r["name"]} {r["version"]}: pip-licenses says nothing, '
                             f'section 3 says "{label}"')
            continue
        low = said.lower()
        if low == label.lower() or PY_NAMES.get(low, "").lower() == label.lower():
            continue
        if label in PIP_COARSE.get(low, ()):
            continue
        notes.append(f'{r["name"]} {r["version"]}: pip-licenses says "{said}", '
                     f'section 3 says "{label}"')
    return notes


HEADER = """Third-party notices - Jarvis
============================

Jarvis itself is MIT-licensed, copyright (c) 2026 darknight11ish (see
LICENSE). It is built with parts made by other people, and those parts keep
their own licences. This file names every one of them, with the notices and
licence texts their licences ask to travel with each copy.

What is in this file, in order:

  1. Parts named by hand (fonts, voice and wake-word models, the memory
     model, code or ideas adapted from other projects). The phone app has
     its own list: jarvis-client/app/src/main/assets/licenses/NOTICES.txt,
     shown in the app under FAQ -> About -> Third-party notices.
  2. The Rust libraries inside the desktop program, generated by
     tools/gen_notices.py from the Windows build (`npm run notices` in
     jarvis-desktop runs it): a summary by licence, then every library with
     its version, the licence Jarvis follows it under, and its copyright
     lines.
  3. The Python packages backend/requirements.lock pins, generated the same
     way from each package's own published metadata: a summary by licence,
     then every package with the version pinned and the licence it declares.
     A package that declares no licence, or too vague a one, is listed again
     at the end of that section for a person to resolve.
  4. Apache-2.0 NOTICE files those Rust libraries carry.
  5. The full text of every licence used, once each.

Worth knowing:

  * NON-COMMERCIAL: the "hey Jarvis" wake-word models (openWakeWord, CC
    BY-NC-SA 4.0) and a few optional voice models are for non-commercial use
    only. That is why Jarvis is a free, non-commercial build (rule 5).
  * MPL-2.0 (file-level copyleft): a few Rust libraries in section 2 are
    under it. They are used unmodified; their source is on crates.io, at the
    address given beside each.
  * No GPL, LGPL, AGPL, SSPL or CDDL part is inside either app. SearXNG
    (AGPL-3.0) and Ollama are separate programs the owner runs; nothing of
    them is distributed with Jarvis.
  * The WebView2 Runtime is Microsoft's and is not redistributed: the
    installer uses Microsoft's own bootstrapper.
  * The desktop's JavaScript has ONE third-party library: three.js r128,
    vendored so the HUD can draw its 3D picture with no CDN and no network
    (see "THE HUD'S 3D LIBRARY" in section 1). Its only other third-party
    files are the fonts below. A few small pieces of code or word lists
    copied from other projects are named in section 1.

"""


def build(meta: dict, current: str, py_rows=None) -> str:
    pkgs = shipped(meta)
    by_name = defaultdict(list)
    for p in meta["packages"]:
        by_name[p["name"]].append(p)

    # The hand-written sections: kept exactly as they are.
    if "(not generated" not in current:
        raise SystemExit("THIRD-PARTY-NOTICES.txt has no hand-written section to keep")
    # Back up to the start of the heading line of the first hand-written section.
    first = current.rfind("\n", 0, current.find("(not generated")) + 1
    end = current.find("\n2. RUST LIBRARIES IN THE DESKTOP PROGRAM")
    if end < 0:
        end = current.find("\nSUMMARY BY LICENCE")
    kept = current[first:end + 1] if end > 0 else current[first:]

    rows, by_licence, used, notices = [], defaultdict(list), set(), []
    for p in pkgs:
        expr = p.get("license") or ""
        if not expr:
            lic = frozenset(["SEE LICENSE FILE"])
        else:
            lic = chosen(expr)
        for x in lic:
            used.add(x.split(" WITH ")[0])
        label = " AND ".join(sorted(lic))
        by_licence[label].append(p["name"])
        lines = copyright_lines(p)
        if not lines and any(x.split(" WITH ")[0] in NEEDS_COPYRIGHT for x in lic):
            authors = ", ".join(a.split(" <")[0] for a in (p.get("authors") or [])) or \
                f"the {p['name']} developers"
            lines = [f"Copyright (c) {authors} (from Cargo.toml; its licence files "
                     "name no holder)"]
        src = f"https://crates.io/crates/{p['name']}/{p['version']}"
        rows.append((p, expr or "(licence file)", label, lines, src))
        if "Apache-2.0" in label:
            for f in notice_files(p):
                notices.append((p, f))

    out = [HEADER, "1. PARTS NAMED BY HAND\n", "=" * 22, "\n\n", kept.rstrip("\n"), "\n\n"]
    out += ["2. RUST LIBRARIES IN THE DESKTOP PROGRAM (generated)\n", "=" * 52, "\n\n",
            f"{len(pkgs)} libraries, from `cargo metadata --filter-platform {TARGET}` of\n"
            "jarvis-desktop/src-tauri (normal and build dependencies, not test-only ones).\n"
            "\"Offered\" is the library's own licence expression; \"followed\" is the\n"
            "licence Jarvis uses it under (the first of MIT, Apache-2.0, BSD, ... that a\n"
            "choice offers; every licence of an AND).\n\n",
            "SUMMARY BY LICENCE\n------------------\n"]
    for label in sorted(by_licence):
        names = by_licence[label]
        out.append(f"{label} ({len(names)}): {', '.join(names)}\n")
    out.append("\nFULL LIST\n---------\n")
    for p, expr, label, lines, src in rows:
        out.append(f"{p['name']} {p['version']} - followed: {label} (offered: {expr})\n")
        if label.startswith("MPL") or "MPL-2.0" in label:
            out.append(f"  Source: {src}\n")
        for line in lines:
            out.append(f"  {line}\n")
    out.append("\n" + build_python_section(py_rows))
    out.append("\n4. APACHE-2.0 NOTICE FILES\n" + "=" * 26 + "\n\n")
    if not notices:
        out.append("None of the libraries followed under Apache-2.0 carries a NOTICE file.\n")
    for p, f in notices:
        text = f.read_text(encoding="utf-8", errors="replace").strip("\n")
        out.append(f"--- {p['name']} {p['version']}: {f.name} ---\n{text}\n\n")
    out.append("\n5. LICENCE TEXTS\n" + "=" * 16 + "\n\n"
               "Each licence used in section 2, in full, once. For MIT, BSD, ISC, Zlib and\n"
               "BSL-1.0, the copyright lines are the ones listed beside each library in\n"
               "section 2; the permission text below goes with each of them.\n\n")
    missing = []
    for name in sorted(used):
        text = licence_text(name, by_name)
        if not text and name not in ("SEE LICENSE FILE",):
            if name in ("0BSD", "MIT-0", "Unlicense", "CC0-1.0"):
                continue
            missing.append(name)
            continue
        if not text:
            continue
        out.append(f"--- {name} ---\n\n{text}\n\n")
    if missing:
        raise SystemExit(f"no licence text found for: {', '.join(missing)}")
    return "".join(out).rstrip("\n") + "\n"


def rust_section(text: str) -> str:
    """The Rust section of a notices file, so `--diff` reads crates only."""
    start = text.find(RUST_HEADING)
    if start < 0:
        return ""
    end = text.find(PY_HEADING, start)
    return text[start:end] if end > 0 else text[start:]


def main(argv: list) -> int:
    current = OUT.read_text(encoding="utf-8")

    # --python: section 3 only, no cargo needed. This is the mode CI's audit
    # job runs, and the one to run after a package is added or bumped.
    if "--python" in argv:
        rows = python_rows()
        fresh = build_python_section(rows)
        notes = cross_check(rows)
        if not python_section(current):
            print("THIRD-PARTY-NOTICES.txt has no Python section yet: run "
                  "python3 tools/gen_notices.py once (it needs cargo) to add it; "
                  "--python keeps it up to date from then on.")
            return 1
        if "--check" in argv:
            if replace_python_section(current, fresh) != current:
                print("The Python section of THIRD-PARTY-NOTICES.txt is out of date: "
                      "run python3 tools/gen_notices.py --python")
                for line in python_differences(current, fresh):
                    print(f"  {line}")
                return 1
            print(f"The Python section of THIRD-PARTY-NOTICES.txt is up to date "
                  f"({len(rows)} packages).")
        else:
            OUT.write_text(replace_python_section(current, fresh),
                           encoding="utf-8", newline="\n")
            print(f"Wrote the Python section of {OUT.relative_to(REPO)} "
                  f"({len(rows)} packages).")
        for note in notes:
            print(f"NOTE pip-licenses disagrees: {note}")
        return 0

    meta = metadata()
    if "--diff" in argv:
        old = set(re.findall(r"^([A-Za-z0-9_-]+):? ([0-9][^ ,]*)",
                             rust_section(current), re.M))
        new = {(p["name"], p["version"]) for p in shipped(meta)}
        print("added:", sorted(new - old))
        print("removed:", sorted(old - new))
        return 0
    rows = python_rows()
    text = build(meta, current, rows)
    if "--check" in argv:
        if text != current:
            print("THIRD-PARTY-NOTICES.txt is out of date: run python3 tools/gen_notices.py")
            for line in python_differences(current, build_python_section(rows)):
                print(f"  {line}")
            return 1
        print(f"THIRD-PARTY-NOTICES.txt is up to date ({len(rows)} Python packages).")
        for note in cross_check(rows):
            print(f"NOTE pip-licenses disagrees: {note}")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT.relative_to(REPO)} ({len(text) // 1024} KB, "
          f"{len(rows)} Python packages).")
    for note in cross_check(rows):
        print(f"NOTE pip-licenses disagrees: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
