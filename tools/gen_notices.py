#!/usr/bin/env python3
"""Regenerate THIRD-PARTY-NOTICES.txt (the desktop installer's notices file).

    python3 tools/gen_notices.py            write it
    python3 tools/gen_notices.py --check    exit 1 if it is out of date
    python3 tools/gen_notices.py --diff     say which crates came and went

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
   adapted into the backend); the summary; the full list with versions and
   copyright lines; any Apache NOTICE files; and the full text of every
   licence used, once each.

No network is used: cargo reads its own lockfile and the files it already
downloaded (`--offline`).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
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
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--offline", "--locked",
         "--filter-platform", TARGET],
        cwd=TAURI, capture_output=True, text=True, check=True).stdout
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
  3. Apache-2.0 NOTICE files those libraries carry.
  4. The full text of every licence used, once each.

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
  * The desktop's JavaScript has no third-party libraries; its only
    third-party files are the fonts below.

"""


def build(meta: dict, current: str) -> str:
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
    out.append("\n3. APACHE-2.0 NOTICE FILES\n" + "=" * 26 + "\n\n")
    if not notices:
        out.append("None of the libraries followed under Apache-2.0 carries a NOTICE file.\n")
    for p, f in notices:
        text = f.read_text(encoding="utf-8", errors="replace").strip("\n")
        out.append(f"--- {p['name']} {p['version']}: {f.name} ---\n{text}\n\n")
    out.append("\n4. LICENCE TEXTS\n" + "=" * 16 + "\n\n"
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


def main(argv: list) -> int:
    current = OUT.read_text(encoding="utf-8")
    meta = metadata()
    if "--diff" in argv:
        old = set(re.findall(r"^([A-Za-z0-9_-]+):? ([0-9][^ ,]*)", current, re.M))
        new = {(p["name"], p["version"]) for p in shipped(meta)}
        print("added:", sorted(new - old))
        print("removed:", sorted(old - new))
        return 0
    text = build(meta, current)
    if "--check" in argv:
        if text != current:
            print("THIRD-PARTY-NOTICES.txt is out of date: run python3 tools/gen_notices.py")
            return 1
        print("THIRD-PARTY-NOTICES.txt is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT.relative_to(REPO)} ({len(text) // 1024} KB).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
