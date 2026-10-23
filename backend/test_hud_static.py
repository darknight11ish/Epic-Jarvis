"""test_hud_static.py - the browser's own files are served, and only these.

    python3 backend/test_hud_static.py

WHY THIS SUITE EXISTS (PWA Slice 3a, the owner's ruling Q6 of 2026-10-23)

The page at "/" was the only file `jarvis_hud.py` could answer. A browser
opened it and then asked for `theme.css`, `fonts/fonts.css`, the woff2 faces
and a dozen `.js` modules - every one a 404 - so the HUD arrived half-dressed
and its shell modules never mounted. The fix is a CLOSED-WORLD whitelist
(`STATIC_ASSETS`) plus one handler that reads each named file from beside the
server: a URL is a key or it is a 404, never a directory walk.

WHAT THIS SUITE PROVES, against the real published base HUD and the real page:

  1. **The whitelist covers EXACTLY what `backend/jarvis_hud.html` loads.**
     Every `<link href>`, every `import("...")` / `from "..."`, every `url()`
     in the CSS it loads, and every local import of a module it loads is a
     whitelist key; and every non-planned key is reachable from the page. A
     page file that is not whitelisted fails here - the point of "closed
     world" - and a whitelist entry nothing loads fails too.
  2. **The PWA files that are not written yet are listed ahead of time**
     (`manifest.webmanifest`, `sw.js`, the home-screen icons). Their request is
     an honest 404 until the file lands beside the server: no crash, no guessed
     file, and no stub file is created here. (The browser bridge was planned
     this way in Slice 3a and is a served file now - PWA Slice 2 put it beside
     the server - so the same deployment-honesty rule below checks it like any
     other file the page loads.)
  3. **Exact MIME types, and no way around the dict.** The real
     `_serve_static` is lifted out of the base HUD with `ast` and run
     in-process against a temporary folder: a whitelisted file answers 200
     with its exact Content-Type and `nosniff`; an unknown path, `..`, an
     encoded traversal, an absolute URL, a trailing slash or a case variant is
     NOT handled at all.
  4. **The gate is the page's own.** No token -> 401; a cross-origin `Origin`
     that fails `_origin_ok` -> 403; a token with no Origin (exactly the shape
     a browser's `<link>` and `<script>` requests make) -> 200.
  5. **The route is really wired.** `Handler.do_GET` has the branch that calls
     `_serve_static`, and it sits before the page route - proved structurally
     by `ast`, not by matching source text.
  6. **Deployment honesty.** Every file the whitelist serves today exists in
     `backend/static/`, is byte-identical to the page's own copy in
     `jarvis-desktop/src/`, is listed in BOTH SHIPPED lists (the patcher and
     the live deploy copy it) and in the re-take rule's `BESIDE` table (the
     published base carries it). Without this the route would work in the
     repository and 404 on the owner's PC.

No network, no model, no owner PC: the HUD is read as source and the handler
is run in-process against a temporary folder.
"""
from __future__ import annotations

import ast
import posixpath
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402
from _where import REPO  # noqa: E402

HUD = REPO / "jarvis-backend" / "jarvis_hud.py"
PAGE = REPO / "backend" / "jarvis_hud.html"
STATIC = REPO / "backend" / "static"
DESKTOP = REPO / "jarvis-desktop" / "src"
PS1 = REPO / "scripts" / "apply-patches.ps1"

#: The exact Content-Type each extension must get (the ruling names exact MIME
#: types; "text/plain for everything" is what a careful test catches).
CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
}

#: Files the PWA slices after this one will write. Whitelisted now so the day
#: they appear beside the server they are served; a request today is a 404.
PLANNED = {
    "/manifest.webmanifest": ".webmanifest",
    "/sw.js": ".js",
    "/icons/jarvis-180.png": ".png",
    "/icons/jarvis-192.png": ".png",
    "/icons/jarvis-512.png": ".png",
}

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def hud_tree() -> ast.Module:
    return ast.parse(HUD.read_text(encoding="utf-8", errors="replace"))


def static_assets(tree: ast.Module = None) -> dict:
    """The whitelist, read from the base HUD's own source (literal only)."""
    tree = tree or hud_tree()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "STATIC_ASSETS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("jarvis-backend/jarvis_hud.py has no module-level STATIC_ASSETS = {...}")


class Request:
    """The duck-typed request `_serve_static` reads and answers."""

    def __init__(self, *, origin=None, token_ok=True, origin_ok=True):
        self.headers = {"Origin": origin} if origin else {}
        self.token_ok = token_ok
        self.origin_ok_result = origin_ok
        self.sent = []

    def _send(self, code, body, ctype="application/json; charset=utf-8",
              extra_headers=None):
        self.sent.append((code, body, ctype, list(extra_headers or [])))
        return code


def lifted_serve_static(folder: Path):
    """The REAL `_serve_static`, lifted out of the base HUD with `ast`.

    Its globals are the whitelist literal from the same file, a throwaway
    `HERE` (the folder files are read from) and two switchable token/origin
    decisions, so the test drives the production function itself rather than a
    paraphrase of it."""
    tree = hud_tree()
    assets = static_assets(tree)
    node = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "_serve_static"), None)
    if node is None:
        raise AssertionError("jarvis-backend/jarvis_hud.py has no module-level "
                             "_serve_static(handler, path)")
    ns = {
        "STATIC_ASSETS": assets,
        "HERE": folder,
        "_token_ok": lambda handler: handler.token_ok,
        "_origin_ok": lambda handler: handler.origin_ok_result,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<_serve_static>", "exec"), ns)
    return ns["_serve_static"], assets


def _clean_ref(ref: str) -> str:
    """One page reference -> an absolute site path, or "" for not-our-file."""
    ref = str(ref or "").strip()
    if not ref or ref.startswith(("#", "data:", "http:", "https:", "mailto:",
                                  "javascript:", "//")):
        return ""
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref:
        return ""
    if ref.startswith("./"):
        ref = ref[1:]
    if not ref.startswith("/"):
        ref = "/" + ref
    return ref


def _is_asset_path(ref: str) -> bool:
    return bool(re.search(r"\.(js|css|woff2|png|webmanifest)$", ref))


def page_refs() -> set:
    """Every local file `backend/jarvis_hud.html` asks for, as site paths."""
    text = PAGE.read_text(encoding="utf-8", errors="replace")
    found = set()
    for pattern in (r'(?:href|src)\s*=\s*"([^"]+)"',
                    r'import\s*\(\s*"([^"]+)"\s*\)',
                    r'\bfrom\s*"([^"]+)"'):
        found.update(m.group(1) for m in re.finditer(pattern, text))
    out = {_clean_ref(r) for r in found}
    return {r for r in out if r and _is_asset_path(r)}


def css_refs(url: str, filename: str) -> set:
    """The files one served stylesheet asks for, as site paths."""
    source = STATIC / filename
    if not source.is_file():
        return set()
    text = source.read_text(encoding="utf-8", errors="replace")
    base = posixpath.dirname(url)
    out = set()
    for m in re.finditer(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', text):
        ref = m.group(1).strip()
        if ref.startswith(("data:", "http:", "https:", "#")):
            continue
        resolved = ref if ref.startswith("/") else posixpath.join(base, ref)
        resolved = posixpath.normpath(resolved)
        if resolved.startswith("/") and _is_asset_path(resolved):
            out.add(resolved)
    return out


def js_imports(filename: str) -> set:
    """The local modules one served module imports, as site paths."""
    source = STATIC / filename
    if not source.is_file():
        return set()
    text = source.read_text(encoding="utf-8", errors="replace")
    out = set()
    for pattern in (r'(?:import|export)\s+[^;]*?\bfrom\s+"(\./[^"]+)"',
                    r'import\s*\(\s*"(\./[^"]+)"\s*\)'):
        for m in re.finditer(pattern, text):
            ref = _clean_ref(m.group(1))
            if ref:
                out.add(ref)
    return out


def expected_asset_refs(assets: dict) -> set:
    """Everything the page loads, transitively, as site paths.

    Start at the page's own references, then follow each served stylesheet's
    `url()` values and each served module's local imports until nothing new
    appears. That set is what a browser pulls in; the whitelist must equal it
    (plus the planned entries, which nothing loads yet)."""
    wanted = page_refs()
    seen = set()
    while True:
        new = set()
        for url in sorted(wanted - seen):
            seen.add(url)
            entry = assets.get(url)
            if entry is None:
                continue
            filename = entry[0]
            if filename.endswith(".css"):
                new |= css_refs(url, filename)
            elif filename.endswith(".js"):
                new |= js_imports(filename)
        if new <= wanted:
            break
        wanted |= new
    return wanted


def ps1_shipped() -> list:
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$SHIPPED = @(")
    block = text[start:text.index("\n)", start)]
    return re.findall(r"^\s*'([^']+)'", block, re.M)


def t_the_whitelist_covers_everything_the_page_loads():
    """The closed world, both ways: every page file is a key, and every key is
    a file the page (or a stylesheet/module it loads) asks for."""
    assets = static_assets()
    wanted = expected_asset_refs(assets)
    missing = sorted(wanted - set(assets))
    check("every file the page loads (stylesheets, fonts, modules and their "
          "own local imports) is in the whitelist",
          not missing, "not whitelisted: " + ", ".join(missing))
    today = set(assets) - set(PLANNED)
    extra = sorted(today - wanted)
    check("... and every non-planned whitelist entry is a file the page really loads",
          not extra, "whitelisted but nothing loads it: " + ", ".join(extra))
    check("the page's asset references were actually read (not an empty set)",
          len(wanted) >= 20, f"{len(wanted)} reference(s): {sorted(wanted)[:6]}")
    check("every planned PWA entry is whitelisted ahead of its slice",
          set(PLANNED) <= set(assets), str(sorted(set(PLANNED) - set(assets))))
    check("... and the entries still planned are the manifest, the service "
          "worker and the home-screen icons",
          set(PLANNED) == {"/manifest.webmanifest", "/sw.js",
                           "/icons/jarvis-180.png", "/icons/jarvis-192.png",
                           "/icons/jarvis-512.png"},
          str(sorted(PLANNED)))
    check("... and the browser bridge is no longer planned: the page loads it "
          "and this server serves it (PWA Slice 2's delivery fix)",
          "/hud-web-bridge.js" not in PLANNED
          and "/hud-web-bridge.js" in assets
          and (STATIC / "hud-web-bridge.js").is_file())


def t_every_content_type_is_exact_and_every_file_is_flat():
    """Exact MIME types, and the value is a bare filename - the request never
    becomes part of a path, so nothing can walk out of the server's folder."""
    assets = static_assets()
    wrong = [(url, entry) for url, entry in assets.items()
             if not isinstance(entry, tuple) or len(entry) != 2
             or CONTENT_TYPES.get(posixpath.splitext(entry[0])[1]) != entry[1]]
    check("every entry is URL -> (filename, exact Content-Type)", not wrong,
          str(wrong[:5]))
    flat = [url for url, (filename, _ctype) in assets.items()
            if filename != posixpath.basename(filename) or filename in ("", ".", "..")
            or "/" in filename or "\\" in filename]
    check("every served filename is a bare name beside the server (no folder, "
          "no '..' - a request can never become a path)", not flat, str(flat))
    bad_keys = [url for url in assets
                if not url.startswith("/") or ".." in url or "*" in url
                or "%" in url or "?" in url or url != posixpath.normpath(url)
                or url.endswith("/")]
    check("every key is an exact site path (no wildcard, prefix, traversal or "
          "query shape)", not bad_keys, str(bad_keys))
    names = [entry[0] for entry in assets.values()]
    check("no two URLs serve the same file (the map is the whole surface)",
          len(names) == len(set(names)), str(sorted(names))[:300])


def t_the_real_handler_serves_files_and_refuses_everything_else():
    """Run the lifted production `_serve_static` against a temporary folder."""
    folder = Path(tempfile.mkdtemp(prefix="jarvis-static-"))
    try:
        serve, assets = lifted_serve_static(folder)
        (folder / "theme.css").write_bytes(b"body { color: red; }\n")

        got = Request()
        handled = serve(got, "/theme.css")
        check("a whitelisted file answers 200 with its bytes, its exact type and "
              "nosniff",
              handled is True and got.sent and got.sent[-1][0] == 200
              and got.sent[-1][1] == b"body { color: red; }\n"
              and got.sent[-1][2] == CONTENT_TYPES[".css"]
              and ("X-Content-Type-Options", "nosniff") in got.sent[-1][3],
              got.sent[-1][:3])

        for path in ("/jarvis_hud.py", "/theme.css/../jarvis_hud.py",
                     "/%2e%2e/jarvis_hud.py", "/theme.css%00", "//theme.css",
                     "/theme.css/", "/THEME.CSS", "/theme.css?x=1",
                     "http://100.64.0.9:4719/theme.css", "/api/status",
                     "", "/"):
            req = Request()
            check(f"not a whitelist key, so not handled: {path!r}",
                  serve(req, path) is False and req.sent == [], req.sent)

        missing = Request()
        missing_handled = serve(missing, "/manifest.webmanifest")
        check("a whitelisted file that is not beside the server yet is an honest "
              "404 (the planned PWA slice, not a crash, not a guessed file)",
              missing_handled is True and missing.sent
              and missing.sent[-1][0] == 404, missing.sent)

        refused = Request(token_ok=False)
        refused_handled = serve(refused, "/theme.css")
        check("no token: 401, the same gate as the page it belongs to",
              refused_handled is True and refused.sent
              and refused.sent[-1][0] == 401, refused.sent)

        cross = Request(origin="https://evil.example", origin_ok=False)
        cross_handled = serve(cross, "/theme.css")
        check("a cross-origin Origin that fails the real check: 403",
              cross_handled is True and cross.sent
              and cross.sent[-1][0] == 403, cross.sent)

        same = Request(origin="http://100.64.9.9:4719", origin_ok=True)
        same_handled = serve(same, "/theme.css")
        check("an Origin the server serves, with a token: 200",
              same_handled is True and same.sent and same.sent[-1][0] == 200,
              same.sent)
        check("every answer that serves bytes carries X-Content-Type-Options: nosniff",
              all(("X-Content-Type-Options", "nosniff")
                  in req.sent[-1][3] for req in (got, same)),
              [req.sent[-1][3] for req in (got, same)])
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def t_the_get_route_calls_it_before_the_page():
    """Structural wiring, by `ast`: without this branch the function above is
    dead code and the browser still gets 404s."""
    tree = hud_tree()
    handler = next((n for n in tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "Handler"), None)
    check("jarvis_hud.py has its one Handler class", handler is not None)
    if handler is None:
        return
    do_get = next((n for n in handler.body
                   if isinstance(n, ast.FunctionDef) and n.name == "do_GET"), None)
    check("... with a do_GET", do_get is not None)
    if do_get is None:
        return
    branches = [n for n in do_get.body if isinstance(n, ast.If)]
    static_branch = None
    page_at = None
    for index, node in enumerate(branches):
        test = ast.unparse(node.test)
        if "STATIC_ASSETS" in test and "path" in test:
            static_branch = node
        if page_at is None and "index.html" in test:
            page_at = index
    check("do_GET has a `if path in STATIC_ASSETS` branch",
          static_branch is not None,
          [ast.unparse(n.test) for n in branches])
    if static_branch is None:
        return
    calls = [ast.unparse(n.func) for n in ast.walk(static_branch)
             if isinstance(n, ast.Call)]
    check("... and that branch calls _serve_static(self, path)",
          "_serve_static" in calls, calls)
    static_at = branches.index(static_branch)
    check("... and it comes before the page route (the page's file requests are "
          "answered by it, not by the 404 tail)",
          page_at is not None and static_at < page_at,
          (static_at, page_at))
    check("the helper and the table are both module-level (where the delta puts them)",
          isinstance(static_assets(), dict)
          and any(isinstance(n, ast.FunctionDef) and n.name == "_serve_static"
                  for n in tree.body))


def t_the_files_reach_the_owner_pc():
    """Deployment honesty: a whitelist entry that only exists in this checkout
    is a 404 on the owner's PC. Every file served today is in backend/static/,
    byte-identical to the page's own copy, shipped by BOTH lists and carried
    by the base's re-take rule."""
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import gen_base_from_backend as gen        # noqa: PLC0415
    finally:
        sys.path.remove(str(REPO / "tools"))
    assets = static_assets()
    shipped = set(ps1_shipped())
    where = set(_where.SHIPPED)
    beside = {name: where for name, where, _why in gen.BESIDE + gen.BESIDE_BINARY}

    missing_src, drifted, not_shipped, not_beside = [], [], [], []
    for url, (filename, _ctype) in sorted(assets.items()):
        if url in PLANNED:
            continue
        ours = STATIC / filename
        if not ours.is_file():
            missing_src.append(filename)
            continue
        source = (DESKTOP / "fonts" / filename) if url.startswith("/fonts/") \
            else (DESKTOP / filename)
        if not source.is_file() or ours.read_bytes() != source.read_bytes():
            drifted.append(filename)
        if f"static/{filename}" not in shipped or f"static/{filename}" not in where:
            not_shipped.append(filename)
        if beside.get(filename) != f"{{repo}}/backend/static/{filename}":
            not_beside.append(filename)

    check("every file served today has a copy in backend/static/",
          not missing_src, "missing: " + ", ".join(missing_src))
    check("... which is byte-identical to the page's own copy in jarvis-desktop/src/ "
          "(the whitelist never serves a stale file)",
          not drifted, "drifted: " + ", ".join(drifted))
    check("... and every one is in BOTH SHIPPED lists (the patcher and the live "
          "deploy copy it beside jarvis_hud.py)",
          not not_shipped, "not shipped: " + ", ".join(not_shipped))
    check("... and in the re-take rule's BESIDE table (the published base carries it)",
          not not_beside, "not beside: " + ", ".join(not_beside))
    check("the planned PWA files are NOT stubbed into backend/static/ (a missing "
          "file must really be missing until its slice lands)",
          not [f for url, (f, _c) in assets.items()
               if url in PLANNED and (STATIC / f).exists()])


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
