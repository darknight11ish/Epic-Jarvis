#!/usr/bin/env python3
"""test_vendored_three.py - the HUD's three.js is the real r128 build, in every copy.

    python3 backend/test_vendored_three.py

WHY THIS SUITE EXISTS (2026-10-27, the approved "exact Gemini cosmos" port)

The owner approved porting the Gemini page's three.js Galaxy picture into the
HUD, and the HUD must work completely offline: it never loads a CDN, and its
server answers only files named in `jarvis_hud.py`'s closed `STATIC_ASSETS`
whitelist. So three.js r128 is VENDORED here first, as its own change with no
page edit - the port that draws with it comes later, and it must find the
library already beside `jarvis_hud.py` on the owner's PC.

A vendored library is only safe if it is provably the real one. A truncated
download, a placeholder, or a copy run through a line-ending rewrite all look
like a file that exists; none of them is three.js. This suite therefore pins
the bytes and the content, and checks every copy the deploy machinery reads.

WHAT THIS SUITE PINS

  1. **The official r128 minified build, byte for byte.** 603,445 bytes and
     the SHA-256 recorded below, fetched on 2026-10-27 from
     `https://unpkg.com/three@0.128.0/build/three.min.js`. The two other
     official mirrors served the identical bytes that day:
     `https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js` and
     `https://raw.githubusercontent.com/mrdoob/three.js/r128/build/three.min.js`.
     The test never touches the network - the hash IS the provenance record.
  2. **It is the real library, not a stub.** The file's own `@license` banner
     names Three.js Authors and MIT, its revision constant is `"128"`, it
     exports `REVISION`, and the classes a renderer needs are all present.
  3. **Every copy is byte-identical.** `backend/static/three.min.js` (this
     repository's source of truth), `jarvis-desktop/src/three.min.js` (where
     the page's real copies live) and `jarvis-backend/three.min.js` (the
     published base) are the same bytes, and each hashes to the pinned value.
  4. **The asset plumbing already knows about it.** Both `$SHIPPED` lists (the
     patcher and `_where.SHIPPED`) and the base's re-take rule (`BESIDE` in
     `tools/gen_base_from_backend.py`) name it, so a deploy puts it beside
     `jarvis_hud.py` and the published base carries it. A vendored file those
     lists do not name is a 404 on the owner's PC however correct it is here.
  5. **A whitelist key and a page that loads the file arrive TOGETHER, or
     neither does.** This change is the vendoring only: the page loads no
     three.js yet, so `/three.min.js` is deliberately NOT a `STATIC_ASSETS`
     key - `backend/test_hud_static.py` fails any key nothing loads, and an
     entry nothing loads is dead surface. The port PR adds the page's
     `<script>` and the key in the same change; this check allows either
     state but refuses the two mismatches (a key nothing loads, or a page
     asking for a file the whitelist does not serve).

Runs anywhere: standard library only, reads this repository only.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

REPO = HERE.parent
STATIC = REPO / "backend" / "static" / "three.min.js"
DESKTOP = REPO / "jarvis-desktop" / "src" / "three.min.js"
BASE = REPO / "jarvis-backend" / "three.min.js"
HUD = REPO / "jarvis-backend" / "jarvis_hud.py"
PAGE = REPO / "backend" / "jarvis_hud.html"
FACE_PAGE = REPO / "backend" / "static" / "faces.html"
PS1 = REPO / "scripts" / "apply-patches.ps1"
GEN = REPO / "tools" / "gen_base_from_backend.py"

#: Provenance, recorded once. The URL is what was fetched on 2026-10-27; the
#: test never fetches anything, because the hash is the thing that has to stay
#: true. `https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`
#: and `https://raw.githubusercontent.com/mrdoob/three.js/r128/build/three.min.js`
#: returned the same size and hash on the same day (all three measured).
PROVENANCE_URL = "https://unpkg.com/three@0.128.0/build/three.min.js"
SIZE = 603_445
SHA256 = "9274bbcec8d96168626c732b5d31c775aa8cfb7eaa0599bec0c175908a2c1ce2"
REVISION = "128"

#: What a real three.js build exports. A stub that only says "three.js r128"
#: would pass a banner check and fail here.
EXPORTS = ("t.WebGLRenderer=", "t.Scene=", "t.PerspectiveCamera=",
           "t.BufferGeometry=", "t.Mesh=", "t.REVISION=e")

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps1_shipped() -> list:
    """The patcher's `$SHIPPED` entries, read the way the other suites read it."""
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$SHIPPED = @(")
    block = text[start:text.index("\n)", start)]
    return re.findall(r"^\s*'([^']+)'", block, re.M)


def beside_table() -> dict:
    """The base's re-take rule: leaf name -> where this repository keeps it."""
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import gen_base_from_backend as gen        # noqa: PLC0415
    finally:
        sys.path.remove(str(REPO / "tools"))
    return {name: where for name, where, _why in gen.BESIDE + gen.BESIDE_BINARY}


def static_assets() -> dict:
    """`jarvis_hud.py`'s whitelist literal, from the published base."""
    tree = ast.parse(HUD.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "STATIC_ASSETS"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("jarvis-backend/jarvis_hud.py has no STATIC_ASSETS = {...}")


def t_the_file_is_the_official_r128_build():
    """The pinned bytes, and the content that proves they are three.js r128."""
    check("the vendored library exists in backend/static/", STATIC.is_file(), str(STATIC))
    if not STATIC.is_file():
        return
    raw = STATIC.read_bytes()
    check(f"it is {SIZE:,} bytes, the size of the official r128 build",
          len(raw) == SIZE, f"{len(raw):,} bytes")
    check("its SHA-256 is the official r128 build's",
          hashlib.sha256(raw).hexdigest() == SHA256, sha256(STATIC))
    text = raw.decode("utf-8", "replace")
    banner = text[:300]
    check("its own banner carries the MIT licence notice and the Three.js copyright",
          "@license" in banner
          and "Copyright 2010-2021 Three.js Authors" in banner
          and "SPDX-License-Identifier: MIT" in banner,
          repr(banner[:200]))
    check('its revision constant is "128" (the minified `const e="128"` it exports as REVISION)',
          f'const e="{REVISION}"' in text and "t.REVISION=e" in text,
          "the revision tokens are not in the file")
    missing = [name for name in EXPORTS if name not in text]
    check("... and it is the real library, not a stub: a renderer, a scene, a "
          "camera, geometry, a mesh and the UMD export tail are all present",
          not missing, "missing: " + ", ".join(missing))
    check("... and it really is a whole build, not a fragment (over 500 KB of code)",
          len(raw) > 500_000, f"{len(raw):,} bytes")


def t_every_copy_is_the_same_bytes():
    """The three places a deploy or the base reads from all hold the same file."""
    copies = (("backend/static/three.min.js", STATIC),
              ("jarvis-desktop/src/three.min.js", DESKTOP),
              ("jarvis-backend/three.min.js", BASE))
    reference = STATIC.read_bytes() if STATIC.is_file() else b""
    for name, path in copies:
        check(f"{name} exists", path.is_file(), str(path))
        if not path.is_file():
            continue
        data = path.read_bytes()
        check(f"... is byte-identical to the official build ({len(data):,} bytes, "
              "the pinned SHA-256)",
              data == reference and hashlib.sha256(data).hexdigest() == SHA256,
              f"{len(data):,} bytes, sha256 {sha256(path)}")


def t_the_asset_plumbing_carries_it():
    """A vendored file nothing ships is a 404 on the owner's PC."""
    where = set(_where.SHIPPED)
    check("backend/_where.py's SHIPPED list names static/three.min.js",
          "static/three.min.js" in where,
          "not in _where.SHIPPED: the tests' own ship list would skip it")
    shipped = ps1_shipped()
    check("scripts/apply-patches.ps1's $SHIPPED list names static/three.min.js",
          "static/three.min.js" in shipped,
          "not in apply-patches.ps1 $SHIPPED: the patcher would never copy it")
    beside = beside_table()
    check("the published base's re-take rule (BESIDE) carries it from backend/static/",
          beside.get("three.min.js") == "{repo}/backend/static/three.min.js",
          str(beside.get("three.min.js")))
    check("... and the base really holds it (the copy checked above)",
          BASE.is_file(), str(BASE))


def t_the_whitelist_key_and_the_page_load_arrive_together():
    """Neither a dead key nor a page asking for a file the server will not serve.

    Today it is the vendoring only: no page loads three.js and there is no
    `/three.min.js` key. The port PR adds both in one change; either state
    passes, and the two mismatches fail with the reason.
    """
    assets = static_assets()
    key = "/three.min.js" in assets
    entry = assets.get("/three.min.js")
    served_name = entry[0] if isinstance(entry, tuple) and entry else ""
    pages = []
    for page in (PAGE, FACE_PAGE):
        if page.is_file() and "three.min.js" in page.read_text(
                encoding="utf-8", errors="replace"):
            pages.append(page.relative_to(REPO).as_posix())
    check("no page loads three.js yet, or the whitelist serves it (a page "
          "loading it against no key would 404)",
          bool(pages) == key,
          f"whitelist key: {key}; page(s) loading it: {pages or 'none'}")
    if key:
        check("if the whitelist serves it, it serves THIS file with the .js type",
              served_name == "three.min.js"
              and entry == ("three.min.js", "text/javascript; charset=utf-8"),
              str(entry))
        check("... and every page that loads it is a file this repository has",
              all((REPO / p).is_file() for p in pages), str(pages))
    else:
        check("this change is the vendoring only: no HUD page references "
              "three.js yet, so the port PR is what adds the page edit and the key",
              not pages, str(pages))


def main() -> int:
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
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
