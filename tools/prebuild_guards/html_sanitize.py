"""Turn a chapter's HTML into XHTML that cannot run or read anything.

WHY THIS FILE EXISTS

P-Pub-1 turns Markdown chapters into XHTML for an EPUB 3 book and for the KDP
print previewer, which is a WebView2 window on this PC. A chapter is not always
written by the owner: it can be pasted from a web page, a scraped article or a
third-party document. Raw HTML in it can carry ``<script>``, an ``onerror=``
attribute, an ``<iframe>`` or an ``<img src="file:///C:/Users/...">``. In a
previewer those can run code or pull a local file into the page; in an exported
EPUB they ship the hostile markup to every reader.

WHAT THIS MODULE DOES

``sanitize_xhtml(xhtml, assets_dir=...)`` parses the chapter with the standard
library's ``html.parser`` (so quoted attributes, unquoted attributes and
entities are handled by the parser, not by a fragile regular expression) and
rebuilds the markup from a known-safe set:

* ``<script>``, ``<style>``, ``<iframe>``, ``<object>``, ``<embed>``,
  ``<form>``, ``<link>``, ``<base>``, ``<meta>``, ``<template>`` and
  ``<noscript>`` are dropped, together with their contents;
* every ``on*`` event attribute is dropped, as is every attribute not on the
  small allow-list (so ``style``, ``srcset`` and ``formaction`` cannot slip a
  load or a second URL through);
* every tag not on the allow-list is dropped but its text is kept (a harmless
  unknown wrapper does not lose the owner's words);
* a link (``<a href>``) may be an ``http:``, ``https:`` or ``mailto:`` address,
  a ``#`` anchor, or a relative path with no ``..``; anything else - notably
  ``javascript:`` and ``file:`` - loses the attribute;
* an ``<img src>`` must be a RELATIVE path inside ``assets_dir``. Absolute
  paths, drive letters, UNC paths, backslashes, ``..`` segments,
  percent-encoded traversals (``..%2f``) and every scheme (``file:``,
  ``http:``, ``data:``) are refused by raising :class:`GuardRefusal` for the
  whole chapter. A picture reference is meaningful, so it is not silently
  dropped: the owner is told which picture is outside the book's folder and
  can move it or fix the path.

The result is checked with ``xml.etree.ElementTree`` before it is returned, so
a chapter with mismatched tags is refused instead of producing an invalid
EPUB.

WHAT THIS DOES NOT DO

* It does not escape or rewrite text; it re-emits it as escaped text.
* It does not cap the chapter's size; P-Pub must bound the chapter it hands in
  (the same way it bounds any other book input) before calling this.
* It does not add a stylesheet. P-Pub should add its own ``<link>`` AFTER this
  guard; a chapter's own ``<style>``/``<link>`` is deliberately thrown away.
* It is not a general HTML/CSS sanitiser for a browser. It is a closed-world
  allow-list for book chapters, and it should stay that way.
"""

from __future__ import annotations

import html as _html
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

#: Tags a chapter may keep. This is the closed world: anything else loses its
#: tag (its text survives). ``html``/``head``/``body``/``title`` are kept so a
#: complete XHTML document survives the guard; ``script``, ``style``, ``link``
#: and ``meta`` are deliberately absent.
ALLOWED_TAGS = frozenset({
    "a", "abbr", "address", "article", "aside", "b", "blockquote", "body", "br",
    "caption", "cite", "code", "col", "colgroup", "dd", "del", "dfn", "div",
    "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
    "h5", "h6", "head", "header", "hr", "html", "i", "img", "ins", "kbd", "li",
    "mark", "nav", "ol", "p", "pre", "q", "s", "samp", "section", "small",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
    "thead", "time", "title", "tr", "u", "ul", "var",
})

#: Tags dropped together with everything inside them. ``embed`` is void, so it
#: has no contents; it is here for the name and is treated as void below.
DROP_WITH_CONTENT = frozenset({
    "applet", "base", "embed", "form", "frame", "frameset", "iframe", "link",
    "meta", "noscript", "object", "script", "style", "template",
})

#: Elements HTML defines as void: they have no closing tag and no contents.
VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "frame", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

#: Attributes a chapter may keep. ``src`` is only honoured on ``<img>``,
#: ``href`` only on ``<a>``, and both are checked separately below. Every
#: ``on*`` attribute is refused whatever this set says.
ALLOWED_ATTRS = frozenset({
    "alt", "class", "colspan", "datetime", "dir", "epub:type", "height", "href",
    "id", "lang", "role", "rowspan", "scope", "src", "title", "width",
    "xml:lang", "xmlns", "xmlns:epub",
})

_DRIVE = re.compile(r"^[A-Za-z]:")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class GuardRefusal(Exception):
    """A plain-English reason this chapter will not be built.

    ``str(exc)`` names the picture or markup at fault and says that nothing was
    built. It is raised before any XHTML is returned.
    """


def _refuse(why: str) -> None:
    raise GuardRefusal(why)


def _hidden(value: str) -> bool:
    """True for control, format or surrogate characters a person cannot see."""
    for ch in value:
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf", "Cs") or ch in ("\u2028", "\u2029"):
            return True
    return False


def _unquote_all(value: str) -> str:
    """Decode percent escapes up to three times, to catch double encoding."""
    out = value
    for _ in range(3):
        nxt = unquote(out, errors="replace")
        if nxt == out:
            break
        out = nxt
    return out


def _relative_problem(value: str) -> str:
    """'' when ``value`` is a plain relative path with no way above the folder."""
    raw = value.strip()
    if not raw:
        return "has no path"
    if _hidden(raw):
        return "contains a hidden character"
    if raw.startswith(("/", "\\")) or "\\" in raw:
        return "is an absolute path or a Windows path, not a path inside the book"
    if _DRIVE.match(raw):
        return "starts with a drive letter, so it points at another disk"
    decoded = _unquote_all(raw)
    if decoded.startswith(("/", "\\")) or "\\" in decoded:
        return "is an absolute path or a Windows path once its escaping is decoded"
    if _DRIVE.match(decoded):
        return "starts with a drive letter once its escaping is decoded"
    if any(part == ".." for part in decoded.replace("\\", "/").split("/")):
        return "points at the folder above the book's pictures folder"
    return ""


class _Sanitizer(HTMLParser):
    """Rebuild the allowed parts of one chapter; refuse unsafe picture paths."""

    def __init__(self, assets_dir):
        super().__init__(convert_charrefs=True)
        self.assets = Path(assets_dir).expanduser().resolve()
        self.out: list[str] = []
        self.skip = 0

    # -- tags ---------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, self_closing=True)

    def _start(self, tag, attrs, *, self_closing: bool) -> None:
        tag = tag.lower()
        if self.skip:
            if not self_closing and tag not in VOID_TAGS:
                self.skip += 1
            return
        if tag in DROP_WITH_CONTENT:
            if not self_closing and tag not in VOID_TAGS:
                self.skip = 1
            return
        if tag not in ALLOWED_TAGS:
            return                     # drop the wrapper, keep its text
        clean = self._clean_attrs(tag, attrs)
        pieces = [f"<{tag}"]
        for name, value in clean:
            pieces.append(f' {name}="{_html.escape(value, quote=True)}"')
        pieces.append(" />" if self_closing or tag in VOID_TAGS else ">")
        self.out.append("".join(pieces))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag not in VOID_TAGS:
                self.skip -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    # -- text and everything else ------------------------------------------

    def handle_data(self, data):
        if not self.skip:
            self.out.append(_html.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass

    # -- attributes ---------------------------------------------------------

    def _clean_attrs(self, tag: str, attrs) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for name, value in attrs:
            lname = (name or "").lower()
            if not lname or _hidden(lname):
                continue
            squashed = re.sub(r"[^a-z]", "", lname)
            if lname.startswith("on") or squashed.startswith("on"):
                continue               # onerror, onclick, on-load, ...
            if lname not in ALLOWED_ATTRS:
                continue
            if value is None:
                value = lname          # XHTML needs a value for every attribute
            if _hidden(value):
                continue
            if lname == "src":
                if tag != "img":
                    continue
                problem = self._image_problem(value)
                if problem:
                    _refuse(f"Jarvis will not build this chapter: the picture "
                            f"{value[:200]!r} {problem}. A picture path can make "
                            f"the previewer read a file elsewhere on the PC, so "
                            f"nothing was built. Move the picture into the book's "
                            f"pictures folder and use a path relative to it.")
                out.append(("src", value.strip()))
                continue
            if lname == "href":
                if tag != "a":
                    continue
                safe = self._safe_link(value)
                if safe is None:
                    continue
                out.append(("href", safe))
                continue
            out.append((lname, value))
        return out

    def _image_problem(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return "has no path"
        low = raw.lower()
        if low.startswith("file:"):
            return "points at a file on this PC, which a book chapter may not do"
        if _SCHEME.match(raw) or low.startswith("//"):
            return "is not a relative path inside the book's pictures folder"
        problem = _relative_problem(raw)
        if problem:
            return problem
        decoded = _unquote_all(raw)
        try:
            candidate = (self.assets / decoded.replace("/", os.sep)).resolve()
        except (OSError, ValueError):
            return "cannot be turned into a place on this PC"
        if not candidate.is_relative_to(self.assets):
            return ("really lives outside the book's pictures folder once any "
                    "shortcut is followed")
        return ""

    @staticmethod
    def _safe_link(value: str) -> str | None:
        raw = (value or "").strip()
        if not raw or _hidden(raw):
            return None
        low = raw.lower()
        if low.startswith("#"):
            return raw
        if _SCHEME.match(raw):
            if re.match(r"^(https?|mailto):", low):
                return raw
            return None                # javascript:, data:, file:, ...
        if _relative_problem(raw):
            return None
        return raw


def sanitize_xhtml(xhtml: str, *, assets_dir) -> str:
    """Return a safe XHTML chapter, or raise :class:`GuardRefusal`.

    ``assets_dir`` is the book's own pictures folder. Every ``<img src>`` must
    resolve inside it. The returned string is well-formed XML (it has been
    parsed again before it is returned); the caller can wrap it in its own
    document and stylesheet.
    """
    if not isinstance(xhtml, str):
        _refuse("Jarvis will not build this chapter: the chapter's markup is "
                "not text. Nothing was built.")
    try:
        assets = Path(assets_dir).expanduser().resolve()
    except (OSError, ValueError):
        _refuse("Jarvis will not build this chapter: the folder that holds its "
                "pictures cannot be found. Nothing was built.")
    parser = _Sanitizer(assets)
    try:
        parser.feed(xhtml)
        parser.close()
    except GuardRefusal:
        raise
    except Exception:
        _refuse("Jarvis will not build this chapter: its markup could not be "
                "read. Nothing was built.")
    cleaned = "".join(parser.out)
    try:
        ET.fromstring("<jarvis-chapter>" + cleaned + "</jarvis-chapter>")
    except ET.ParseError:
        _refuse("Jarvis will not build this chapter: some markup in it is not "
                "closed properly, so the book would be damaged. Nothing was built.")
    return cleaned


__all__ = [
    "ALLOWED_ATTRS",
    "ALLOWED_TAGS",
    "DROP_WITH_CONTENT",
    "GuardRefusal",
    "VOID_TAGS",
    "sanitize_xhtml",
]
