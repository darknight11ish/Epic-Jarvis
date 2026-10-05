#!/usr/bin/env python3
"""Every media source the desktop hands an `<audio>` element must be a scheme
the policies it is served under let through.

    python3 tools/check_media_csp.py [-v]

This is the check for a whole class of bug that no compiler, test or log line
anywhere in this tree can see: an `<audio>` element is given a `data:` URI, no
`media-src` in force lists `data:`, and the browser refuses the load without an
exception - `play()` rejects with a `NotSupportedError`, `onerror` fires or
nothing at all happens, and the feature is simply silent. It is not a crash and
it is not a failing test.

That is exactly what the tree said on 2026-10-05, and what this script was
written for: `tauri.conf.json` carried

    media-src 'self' blob:

while every clip this app plays - the spoken answer (`speak_reply`), the
"One moment." sound, the focus-session line, a voice's "Hear it" sample - is
built in Rust as `data:audio/wav;base64,...`. Every one of them was refused,
so Jarvis spoke nothing at all and nothing anywhere said why. The `img-src`
directive had listed `data:` all along, which is why the faces and the QR code
worked while the voice did not.

What it reads - all from THIS checkout:

  jarvis-desktop/src-tauri/tauri.conf.json   app.security.csp, served as a
                                             response HEADER on every page
  jarvis-desktop/src/**/*.js, *.html         every media element, the source it
                                             is handed, and a page's own
                                             `<meta http-equiv=
                                             "Content-Security-Policy">`

TWO POLICIES, NOT ONE. `jarvis_hud.html` carries a `<meta>` CSP of its own and
says so itself ("Tauri serves the app's `app.security.csp` as a response HEADER
on every .html asset, and BOTH policies are enforced"). A media source in that
page therefore has to satisfy both, and adding `data:` to the app CSP alone
would not make a clip play there - so each site is tested against every policy
in force for the page it is written in, and the refusal names the one that
refused it.

A source this script cannot read is a FAILURE, not a pass: an argument that is
neither a `data:` literal nor a name it can follow has to be listed below with a
one-line reason. A check that quietly skipped those would have missed this bug
too, since the URI arrives from Rust rather than as a literal in the page -
which is why the run-time cases are listed here, each naming the Rust line that
builds the URI, and why that line is verified rather than taken on trust.

What it cannot decide, said out loud rather than guessed:

  * Media played through the Web Audio API (`AudioContext.createBuffer`,
    `decodeAudioData`) never touches `media-src` - that is a different code
    path. The "I heard you" sound is one of those (main.js `playHeardSound`),
    so it is not counted here.
  * `fetch()` of a `data:` URI is `connect-src`, not `media-src`.
  * An element built by `document.createElement("audio")` and given a source
    somewhere else would not be seen. Nothing in this tree does that (0 found),
    and the count is printed so that a new one is visible.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "jarvis-desktop" / "src"
SRC_TAURI = REPO / "jarvis-desktop" / "src-tauri"
CONF = SRC_TAURI / "tauri.conf.json"

# ---------------------------------------------------------------------------
#   Sources whose value this script cannot read, each with its reason
# ---------------------------------------------------------------------------
# Key: (page, the function it is written in, the argument as written).
# Value: (one-line reason, the Rust file that builds the URI, a string that
#         file must contain).
#
# Every one of these is a `data:audio/wav;base64,...` the PC alone builds, and
# the page only ever sees the finished string - so there is no literal here for
# this script to read. A new one has to be added deliberately, and the Rust
# half is CHECKED, not trusted: if the named file stops carrying a `data:` URI,
# that is reported as a stale entry rather than passing quietly.
RUNTIME_SOURCES = {
    ("main.js", "playClip", "dataUri"): (
        "every caller passes what `speak_reply` answered",
        "src/voice.rs", "data:audio/wav;base64"),
    ("main.js", "playFocusCallout", "uri"): (
        "guarded two lines above by `uri.startsWith(\"data:audio/wav;base64,\")`",
        "src/brain/focus.rs", "data:audio/wav;base64"),
    ("main.js", "maybeSayOneMoment", "momentClip.uri"): (
        "the `moment` clip saved by `voiceFlow.moment`",
        "src/voice_flow.rs", "data:audio/wav;base64"),
    ("main.js", "liveSlowFirstAnswer", "momentClip.uri"): (
        "the same saved `moment` clip, played by Live's slower first answer",
        "src/voice_flow.rs", "data:audio/wav;base64"),
    ("main.js", "sayAside", "uri"): (
        "`speak_reply` again, for one fixed line said on its own",
        "src/voice.rs", "data:audio/wav;base64"),
    ("voice-panel.js", "playFromPc", "reply.audio"): (
        "the voice-sample reply, checked by the page for its `data:audio/` prefix",
        "src/voice_training.rs", "data:audio/wav;base64"),
}

# The lifecycle types `EventSource`/`media` know about, so that "no scheme at
# all" (`'self'`) is not the only thing a source list may say.
SCHEME_SOURCES = ("data", "blob", "filesystem", "mediastream")


# ---------------------------------------------------------------------------
#   Reading the pages
# ---------------------------------------------------------------------------

def without_comments(src: str) -> str:
    """Blank out comments, keeping every byte offset - so a reported line
    number still points at the real line (the same trick as check-tokens.py).

    `voice-flow.js` has a doc comment saying `heardSoundUri()` is "a
    `data:audio/wav` URI, for `new Audio()`", and without this it reads as a
    call site. Only comments are blanked: the argument of a real call is a
    string literal this check has to be able to READ, so strings stay.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            quote = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for j in range(i, end):
                if out[j] != "\n":
                    out[j] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def balanced(src: str, open_at: int) -> tuple[str, int]:
    """The text inside the brackets starting at `open_at`, and where they end.

    A media source can be a call, an object member or a template literal, so an
    argument is taken by balanced brackets rather than by the first comma.
    """
    depth, i, start = 0, open_at, open_at + 1
    while i < len(src):
        c = src[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return src[start:i].strip(), i
        i += 1
    return src[start:].strip(), len(src)


def first_argument(src: str, call_end: int) -> str:
    """The first top-level argument of the call whose `(` is just before
    `call_end`."""
    depth, i, start = 1, call_end, call_end
    while i < len(src):
        c = src[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return src[start:i].strip()
        elif c == "," and depth == 1:
            return src[start:i].strip()
        i += 1
    return src[start:].strip()


def enclosing_function(src: str, at: int) -> str | None:
    """The name of the function `at` sits inside, or None.

    Used only to key RUNTIME_SOURCES: `uri` is a local in three different
    functions in main.js with three different producers, so the function is
    part of the identity.

    The body's `{` is found by skipping the parameter list first, because a
    destructured parameter carries a `{` of its own -
    `async function playFromPc({ command, args, ... })` would otherwise be read
    as ending at the parameter object.
    """
    best: tuple[str, int] | None = None
    for m in re.finditer(r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", src, re.M):
        _params, paren_end = balanced(src, m.end() - 1)
        brace = src.find("{", paren_end)
        if brace < 0 or brace > at:
            continue
        _body, end = balanced(src, brace)
        if brace <= at <= end and (best is None or brace > best[1]):
            best = (m.group(1), brace)
    return best[0] if best else None


def data_producers() -> dict[str, str]:
    """{function name: the file it is in} for every function in src/ whose body
    RETURNS a `data:` URI it built itself.

    `heardSoundUri()` (voice-flow.js) is the shape this is for: a page-side
    producer, so a call to it is a `data:` source with a literal in the tree to
    prove it.
    """
    out: dict[str, str] = {}
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in (".js", ".html"):
            continue
        text = without_comments(path.read_text(encoding="utf-8", errors="replace"))
        for m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\(", text):
            brace = text.find("{", m.end())
            if brace < 0:
                continue
            body, _end = balanced(text, brace)
            if re.search(r"return\s+[`\"']data:(?:audio|video)/", body):
                out[m.group(1)] = path.name
    return out


# ---------------------------------------------------------------------------
#   Reading the policies
# ---------------------------------------------------------------------------

def directives(csp: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in csp.split(";"):
        bits = part.split()
        if bits:
            out[bits[0].lower()] = bits[1:]
    return out


def media_rule(rules: dict[str, list[str]]) -> tuple[str, list[str]]:
    """The directive that decides a media load, and its source list.

    `media-src` absent means the fallback chain decides, and its first link is
    `default-src`. Which one is in force is printed, because adding `data:` to
    a `media-src` line that is not there would change nothing.
    """
    if "media-src" in rules:
        return "media-src", rules["media-src"]
    return "default-src (no media-src)", rules.get("default-src", [])


def permits(sources: list[str], scheme: str) -> bool:
    return any(s.rstrip(":").lower() == scheme for s in sources if s.lower().endswith(":")
               and s[:-1].lower() in SCHEME_SOURCES)


def meta_csp(raw: str) -> str | None:
    """A page's own `<meta http-equiv="Content-Security-Policy">`, or None.
    `jarvis_hud.html` has one; nothing else does.

    The content attribute is taken by its own quote character, not by "anything
    that is not a quote": a CSP is full of `'self'` and `'unsafe-inline'`, so
    `[^"']*` stops at the first source and reports an empty policy - which is
    how this read `jarvis_hud.html`'s `media-src 'self' blob:` as nothing at
    all the first time it ran.
    """
    m = re.search(r"<meta[^>]*http-equiv\s*=\s*[\"']Content-Security-Policy[\"'][^>]*>",
                  raw, re.I)
    if not m:
        return None
    content = re.search(r"""content\s*=\s*(?:"([^"]*)"|'([^']*)')""", m.group(0), re.I)
    if not content:
        return None
    return content.group(1) if content.group(1) is not None else content.group(2)


def classify(arg: str, page: str, owner: str | None, producers: dict[str, str]):
    """(scheme, note) for a media source argument, or None when it cannot be
    read. `data:` is decided from the text where the text is there, and from
    RUNTIME_SOURCES where it is not."""
    text = arg.strip()
    literal = re.match(r"^[`\"'](data|blob):", text)
    if literal:
        mime = re.match(r"^[`\"']data:([\w.+-]+/[\w.+-]+)", text)
        note = f"a literal in the page{f' ({mime.group(1)})' if mime else ''}"
        return literal.group(1), note
    call = re.match(r"^([A-Za-z_$][\w$]*)\s*\(", text)
    if call and call.group(1) in producers:
        return "data", f"built by {call.group(1)}() in {producers[call.group(1)]}"
    entry = RUNTIME_SOURCES.get((page, owner, text))
    if entry:
        return "data", entry[0]
    return None


def main() -> int:
    verbose = "-v" in sys.argv

    if not CONF.exists():
        print(f"::error::no {CONF.relative_to(REPO).as_posix()} - this check cannot "
              f"read the CSP")
        return 1
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    csp = (conf.get("app", {}).get("security", {}) or {}).get("csp")
    if not csp:
        print("::error::tauri.conf.json carries no app.security.csp - every window "
              "is served with no policy, so there is nothing to test against")
        return 1
    conf_name = CONF.relative_to(REPO).as_posix() if CONF.is_relative_to(REPO) \
        else CONF.as_posix()

    producers = data_producers()
    files = [p for p in sorted(SRC.rglob("*")) if p.suffix in (".js", ".html")]
    # A .js file never carries a <meta>, but it is loaded by a page that may -
    # and the sites in it run in that page. The pages that load each module are
    # not followed here (check_invoke_grants.py does that); instead every
    # <meta> CSP in src/ is collected by the page that carries it, and a module
    # with no page of its own is judged against the app CSP alone. Said out
    # loud rather than guessed at: `jarvis_hud.html` is the only page with one,
    # and the only page whose own script plays media is the Jarvis bar.
    meta_policies: dict[str, tuple[str, str]] = {}
    for path in files:
        if path.suffix != ".html":
            continue
        found = meta_csp(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            meta_policies[path.name] = (f"{path.name}'s own <meta> CSP", found)

    sites: list[tuple[str, int, str, str | None, str | None]] = []
    unresolved: list[tuple[str, int, str, str | None]] = []
    html_sites = 0

    for path in files:
        text = without_comments(path.read_text(encoding="utf-8", errors="replace"))
        raw = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"new\s+Audio\s*\(", text):
            arg = first_argument(text, m.end())
            line = text[:m.start()].count("\n") + 1
            owner = enclosing_function(text, m.start())
            place = f"in {owner}()" if owner else "at the top level"
            kind = classify(arg, path.name, owner, producers)
            if kind is None:
                unresolved.append((path.name, line, arg, owner))
            else:
                scheme, note = kind
                sites.append((path.name, line, f"new Audio({arg})", scheme,
                              f"{place} - {note}"))
        # A tag in a page is a media element too. None today; the count is
        # printed so that a new one is not invisible.
        for m in re.finditer(r"<(audio|video)\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", raw):
            html_sites += 1
            line = raw[:m.start()].count("\n") + 1
            scheme = m.group(2).split(":", 1)[0] if ":" in m.group(2)[:12] else None
            sites.append((path.name, line, m.group(0)[:70], scheme, f"{m.group(1)} tag"))
        for m in re.finditer(r"createElement\(\s*[\"'](audio|video)[\"']", raw):
            line = raw[:m.start()].count("\n") + 1
            unresolved.append((path.name, line,
                               f'createElement("{m.group(1)}") - the source is set '
                               f'elsewhere', None))

    problems = False
    if unresolved:
        problems = True
        print("::error::a media source this check cannot read - add it to "
              "RUNTIME_SOURCES in this script with a one-line reason naming the "
              "file that builds the URI, or make the source a literal:")
        for name, line, arg, owner in unresolved:
            print(f"  {name}:{line}  {arg}   (in {owner}())" if owner
                  else f"  {name}:{line}  {arg}")

    # The run-time entries are checked against the Rust they name: an entry
    # whose reason has stopped being true is worse than no entry, because it
    # makes the next reader trust a stale claim.
    for (_page, _owner, arg), (reason, rust, needle) in sorted(RUNTIME_SOURCES.items()):
        path = SRC_TAURI / rust
        if not path.exists() or needle not in path.read_text(encoding="utf-8", errors="replace"):
            problems = True
            print(f"::error::RUNTIME_SOURCES[{arg}] says its URI is built in "
                  f"{rust}, and that file no longer holds `{needle}` - the entry is "
                  f"stale and has to be worked out again")

    # Every policy in force for the page a site is written in.
    def policies_for(page: str):
        yield f"app CSP ({conf_name})", directives(csp)
        if page in meta_policies:
            name, body = meta_policies[page]
            yield name, directives(body)

    refused: list[tuple[str, int, str, str, str, str, str]] = []
    # Every policy in force anywhere, by name, so the fix lines below can print
    # the source list of the policy that actually refused something.
    named_policies: dict[str, dict[str, list[str]]] = {}
    for page in {page for page, *_rest in sites}:
        for name, rules in policies_for(page):
            named_policies.setdefault(name, rules)
    for page, line, what, scheme, note in sites:
        if not scheme:
            continue
        for name, rules in policies_for(page):
            where, allowed = media_rule(rules)
            if not permits(allowed, scheme):
                refused.append((page, line, what, scheme, name, where, note))
                break

    if refused:
        problems = True
        refused_schemes = ", ".join(f"'{s}'" for s in sorted({s[3] + ":" for s in refused}))
        print(f"::error::media-src does not allow {refused_schemes} - the browser "
              f"refuses these loads, so they play nothing at all and nothing says why:")
        for page, line, what, scheme, _name, where, note in refused:
            print(f"  {scheme + ':':<7} {page}:{line}  {what}   ({note})")
            print(f"          refused by {_name}'s {where}")
        # One fix line per policy that refused something, because there are two
        # policies in force on the HUD page and they are edited in two places.
        for name, where in dict.fromkeys((_name, where) for _p, _l, _w, _s, _n, _wh, _no
                                         in refused):
            _directive, allowed = media_rule(named_policies.get(name, {}))
            print(f"  {where} today, {name}: {' '.join(allowed)}")
            if name.startswith("app CSP"):
                print(f"  Fix: add `data:` to {where} in {conf_name}'s csp.")
            else:
                print(f"  Fix: add `data:` to {where} in that page's own <meta> "
                      f"http-equiv=\"Content-Security-Policy\" - the app CSP alone "
                      f"does not lift it.")

    if problems:
        return 1

    schemes = sorted({s[3] for s in sites if s[3]})
    print(f"{len(sites)} media source(s) across {len(files)} page file(s); "
          f"media-src permits every scheme they use"
          + (f" ({', '.join(s + ':' for s in schemes)})." if schemes else "."))
    print(f"{len(RUNTIME_SOURCES)} of them are built at run time, each listed in this "
          f"script with the Rust line that builds it, and each of those lines was "
          f"checked.")
    if html_sites == 0:
        print("0 sources come from an <audio>/<video> tag and 0 from "
              "createElement(\"audio\") - every one is `new Audio(...)`, which is why "
              "the scan above is the whole list.")
    if meta_policies:
        for page, (name, body) in sorted(meta_policies.items()):
            where, allowed = media_rule(directives(body))
            print(f"NOTE: {page} carries its own <meta> CSP, and BOTH policies are "
                  f"enforced on it - its {where} is: {' '.join(allowed)}. A data: "
                  f"source added to that page would still be refused there, whatever "
                  f"the app CSP says.")
    if verbose:
        for page, line, what, scheme, note in sorted(sites):
            print(f"  {page}:{line}  [{scheme or 'no scheme'}]  {what}   ({note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
