"""Jarvis's map of its own code, read from the file beside this one.

    import jarvis_self_code as SC
    SC.available()      # is the map installed with this build?
    SC.map_info()       # the commit, version, date and repository it came from
    SC.overview()       # the major parts of its own code, in words
    SC.lookup("memory") # what one part does, where it lives, what proves it
    SC.recent()         # what changed around the deploy that built the map
    SC.self_repo()      # which public repository this code is

WHAT IT READS, AND WHAT IT DOES NOT
===================================
One file: `jarvis-self-code.json`, beside this module. It is generated from the
repository tree at the commit the deploy was built from, by
`tools/gen_self_code_map.py`, and it travels with this module the same way
`quotes_corpus.json` travels with `jarvis_quotes.py` (the BESIDE list in
`tools/gen_base_from_backend.py`). The reader therefore never runs git, never
opens a socket, never writes anything, and never imports a module to look at
it. On this PC that one file sits in the live backend folder, so the deploy -
not a clone on some other drive - decides what it says.

WHAT IT HONESTLY KNOWS
======================
The map names the major parts of this program, the files each part owns, a
handful of modules to start reading for each, and the tests and documents that
go with them. It also carries the commit it was built from, that commit's date,
the repository's version and its newest twenty commit subjects.

It does NOT hold code bodies: it knows a module's path and the first sentence of
its docstring, not what is inside it. It does not run code, so it cannot say
what a function returns or why something is slow. And it knows nothing newer
than the deploy that installed it - a question about code merged after that
deploy is answered "not in the map I was built with", never guessed at.

If the JSON is absent, that is itself the answer: the map was not installed with
this build. Every function here says so in plain words and none of them raises,
because a missing file is a fact about the install and not a crash.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Optional

#: The file beside this module. A deploy carries it; see the module docstring.
MAP_NAME = "jarvis-self-code.json"

#: Said when the map is not there, once, in the same words everywhere.
NO_MAP = ("The self-code map was not installed with this build, so I cannot answer "
          "that about my own code. The map is one file beside the backend "
          f"({MAP_NAME}); a deploy that carries it is what makes this answer work.")

#: Every answer that names parts also says what the map is not, once. It is the
#: difference between "I know where that lives" and "I have read the code".
NOT_CODE = ("That is from a map of my own code: it names the parts and where they "
            "live, and it does not hold the code itself.")

#: Words a question wraps around the thing it is asking about. They carry no
#: meaning for the lookup, and leaving them in would score every part equally.
_STOP = frozenset("""
a an the and or of for to in on at by with from your my our its his her their
what which who whom whose when where why how does do did is are was were be been
being have has had can could would should will shall may might must
jarvis you your yours me i we us it this that these those
code codes codebase source sources module modules file files part parts
component components subsystem subsystems piece pieces thing things
tell show give about please exactly actually really
handle handles handled live lives located locate find sits sit
built build made make up
py json md txt yml yaml html css js toml patch
""".split())

#: How much of a purpose one overview line may carry. A chat answer is read on a
#: phone as often as on this PC; a 600-word list would be a wall, not an answer.
_OVERVIEW_PURPOSE = 120

#: How many of a part's files an answer names before it just counts the rest.
_FILES_SHOWN = 3

#: The least score a topic needs before it is a match rather than a near miss.
_CONFIDENT = 5

_CACHE: dict = {}
"""The loaded map, or the reason it could not be loaded - read once."""


def _load() -> tuple:
    """(the map, "") or (None, the plain reason). Never raises.

    Cached because this is called on a chat turn: the file is ~300 KB and
    parsing it per sentence would be a cost with no benefit, and the file does
    not change while the process is alive.
    """
    if "map" in _CACHE:
        return _CACHE["map"], _CACHE["why"]
    path = Path(__file__).resolve().parent / MAP_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        doc, why = None, NO_MAP
    except OSError as exc:
        doc, why = None, (f"The self-code map is in my folder but could not be read "
                          f"({type(exc).__name__}), so I cannot answer that about my "
                          f"own code.")
    except ValueError:
        doc, why = None, ("The self-code map in my folder is not readable as JSON, so I "
                          "cannot answer that about my own code. A deploy that rewrote "
                          "it badly is the cause.")
    else:
        if not isinstance(doc, dict) or not doc.get("subsystems"):
            doc, why = None, ("The self-code map in my folder is empty or not a map, so I "
                              "cannot answer that about my own code.")
        else:
            why = ""
    _CACHE["map"], _CACHE["why"] = doc, why
    return doc, why


def _rows() -> list:
    """The map's subsystem rows, or [] - and never anything but a list."""
    doc, _why = _load()
    if not doc:
        return []
    rows = doc.get("subsystems")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _said(text: str) -> str:
    """One answer line, flattened: a chat reply is one block of words."""
    return " ".join(str(text or "").split())


def _count(value) -> int:
    """A number from the map, or 0. A hand-edited map must not raise here."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _paths(value) -> list:
    """A list of repo-relative paths from the map, whatever it actually holds."""
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v) for v in value if str(v or "").strip()]


def _cut(text: str, limit: int) -> str:
    """`text` cut at a word boundary with an ellipsis, or unchanged."""
    text = _said(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."


def available() -> bool:
    """Is the map installed beside this build? False is an answer, not an error."""
    return bool(_load()[0])


def map_info() -> dict:
    """The four facts a caller may want without reading any prose.

    Always returns the same keys, with empty strings when the map is absent, so
    a caller never has to guess at a KeyError. `why` says what happened.
    """
    doc, why = _load()
    if not doc:
        return {"available": False, "ref": "", "version": "", "built_at": "",
                "repo": "", "public": False, "subsystems": 0, "files": 0,
                "why": why}
    coverage = doc.get("coverage") or {}
    return {
        "available": True,
        "ref": str(doc.get("ref") or ""),
        "version": str(doc.get("version") or ""),
        "built_at": str(doc.get("built_at") or ""),
        "repo": str(doc.get("repo") or ""),
        "public": bool(doc.get("public")),
        "subsystems": len(_rows()),
        "files": _count(coverage.get("covered")),
        "why": "",
    }


def _stamp() -> str:
    """'version 0.2.0, commit 6bff915, built 2026-11-07' - the map's own words."""
    info = map_info()
    bits = []
    if info["version"]:
        bits.append("version " + info["version"])
    if info["ref"]:
        bits.append("commit " + info["ref"][:9])
    if info["built_at"]:
        bits.append("built " + info["built_at"][:10])
    return ", ".join(bits)


def overview() -> str:
    """The major parts of its own code, one line each, then what sits around them.

    The runtime parts get a line each, because that is the question. The
    repository furniture - tests, docs, deploy, the base and the videos - gets
    one line together, because a caller asking "what are your major parts" wants
    the code, and 27 equal lines reads as a dump rather than an answer.
    """
    doc, why = _load()
    if not doc:
        return why
    rows = _rows()
    runtime = [r for r in rows if str(r.get("group") or "") != "repo"]
    repo = [r for r in rows if str(r.get("group") or "") == "repo"]
    lines = [("My own code is " + (map_info()["repo"] or "this repository")
              + " - " + (_stamp() or "no build stamp") + ". It has "
              + f"{len(runtime)} parts that run and {len(repo)} that hold the "
              "repository together.")]
    for i, row in enumerate(runtime, 1):
        purpose = _cut(row.get("purpose"), _OVERVIEW_PURPOSE)
        keys = [str(k.get("path") or "") for k in row.get("key_modules") or ()
                if isinstance(k, dict) and k.get("path")]
        where = f" (start at {keys[0]})" if keys else ""
        lines.append(f"{i}. {row.get('title')} - {purpose}{where}")
    if repo:
        bits = [f"{row.get('title')} ({_count(row.get('file_count')):,} files)"
                for row in repo]
        lines.append("Around that code: " + "; ".join(bits) + ".")
    lines.append(NOT_CODE + " It knows nothing newer than the deploy that built it.")
    return "\n".join(lines)


def _words(text: str) -> list:
    """The meaningful lowercase words of a phrase, in the order said."""
    raw = re.findall(r"[a-z0-9_]+", str(text or "").lower().replace("-", " "))
    return [w for w in raw if len(w) > 1 and w not in _STOP]


def _name_words(text: str) -> set:
    """The words of a title or a file name, including the `jarvis_` stem's own."""
    flat = str(text or "").lower().replace("_", " ").replace("-", " ")
    return {w for w in re.findall(r"[a-z0-9]+", flat) if len(w) > 1}


def _hit(token: str, words: set) -> bool:
    """Does `token` name one of `words`? Exact, or the same word's other ending.

    "document" has to find "documents" and "model" has to find "models", or a
    person's singular never matches a title written in the plural. Short words
    are matched exactly only: "gate" must not be found by "gates" alone, and a
    two-letter fragment must never match anything.
    """
    if token in words:
        return True
    if len(token) < 5:
        return False
    # Only the WORD may be the longer one ("document" finds "documents"). The
    # reverse - a long compound token matching a shorter word inside it - would
    # make "jarvis_quick" match every title that says "Jarvis".
    return any(len(w) >= 5 and len(w) <= len(token) + 3 and w.startswith(token)
               for w in words)


def _score(topic: str, row: dict) -> int:
    """How well one subsystem answers `topic`. Deterministic and explainable.

    The weights are the design: a word in the TITLE or the id is what a person
    means; a word in a key module's name is a strong hint; a word in the purpose
    or a doc's name is a hint. Matching a whole file name beats all of them.
    """
    tokens = _words(topic)
    if not tokens:
        return 0
    phrase = " ".join(tokens)
    title_words = _name_words(row.get("title"))
    flat_title = " ".join(re.findall(r"[a-z0-9]+", str(row.get("title") or "").lower()))
    purpose_words = _name_words(row.get("purpose"))
    id_words = _name_words(row.get("id"))
    keys = [str(k.get("path") or "") for k in row.get("key_modules") or ()
            if isinstance(k, dict)]
    key_stems = [_name_words(Path(k).name) for k in keys]
    doc_stems = [_name_words(Path(str(d)).name) for d in row.get("docs") or ()]
    # The published base is a COPY of files owned elsewhere, so naming a module
    # must not resolve to the copy: only its own title and purpose can match.
    copies = str(row.get("id") or "") == "base"
    names = set() if copies else {Path(str(p)).name.lower()
                                  for p in row.get("files") or ()}
    stems = set() if copies else {Path(str(p)).stem.lower()
                                  for p in row.get("files") or ()}
    score = 0
    if len(tokens) > 1 and phrase in flat_title:
        score += 8
    for token in tokens:
        if _hit(token, title_words):
            score += 6
        if _hit(token, id_words):
            score += 5
        if any(_hit(token, stem) for stem in key_stems):
            score += 3
        if _hit(token, purpose_words):
            score += 2
        if any(_hit(token, stem) for stem in doc_stems):
            score += 2
        if token in names or token in stems:
            score += 6
    return score


def resolve(topic: str) -> Optional[dict]:
    """The one subsystem a topic names, or None.

    This is the deterministic match `lookup` answers from, exposed because the
    chat matcher has to know whether a topic is in the map before it takes a
    "what does X do" sentence away from the model - a map that answered every
    question with "not in the map" would be worse than no map.
    """
    rows = _rows()
    if not rows:
        return None
    scored = sorted(((_score(topic, row), str(row.get("id") or ""), row)
                     for row in rows), key=lambda t: (-t[0], t[1]))
    best, _bid, row = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if best >= _CONFIDENT and best >= second + 2:
        return row
    return None


def _nearest(topic: str) -> list:
    """The two parts whose TITLES are closest to `topic`, for an honest miss."""
    titles = [str(r.get("title") or "") for r in _rows() if r.get("title")]
    if not titles:
        return []
    said = " ".join(_words(topic)) or str(topic or "").strip()
    close = difflib.get_close_matches(said, titles, n=2, cutoff=0.0)
    return close or titles[:2]


def lookup(topic: str) -> str:
    """What one part of its own code does, where it lives, and what proves it.

    A confident match answers with the part's own purpose, its first files, its
    first key module, its tests and its docs. Anything else says so and names
    the two nearest parts - never a guess, and never a model.
    """
    if not available():
        return NO_MAP
    asked = _said(topic).strip(" .?!:;\"'")
    if not asked:
        return ("Tell me what to look for - a part of my code, a module name, or a "
                "word like memory or voice - and I will say what it does and where "
                "it lives.")
    row = resolve(asked)
    if row is None:
        near = _nearest(asked)
        names = ", ".join(f'"{t}"' for t in near)
        return (f'"{asked}" is not in the map I was built with. '
                + (f"The two nearest parts I do know are {names}. " if names else "")
                + "I will not guess about code I was not built with.")
    files = _paths(row.get("files"))
    shown = files[:_FILES_SHOWN]
    rest = len(files) - len(shown)
    keys = _paths([k.get("path") for k in row.get("key_modules") or ()
                   if isinstance(k, dict)])
    tests = _paths(row.get("tests"))
    docs = _paths(row.get("docs"))
    lines = [f"{row.get('title')} - that is one part of my own code, and it does "
             f"this: {_said(row.get('purpose'))}"]
    if shown:
        lines.append("Where it lives: " + ", ".join(shown)
                     + (f" (and {rest:,} more file" + ("" if rest == 1 else "s")
                        + " in the same part)" if rest > 0 else "") + ".")
    if keys:
        lines.append("Start reading: " + ", ".join(keys) + ".")
    if tests:
        lines.append("Proved by: " + ", ".join(tests) + ".")
    if docs:
        lines.append("Described in: " + ", ".join(docs) + ".")
    lines.append(NOT_CODE)
    return "\n".join(lines)


def recent() -> str:
    """What changed around the deploy that built the map, and how old it is.

    The words say "as of the deploy that built this map" on purpose: this is a
    snapshot of the twenty commits at that commit, so silence about a newer merge
    is honest rather than an omission.
    """
    doc, why = _load()
    if not doc:
        return why
    commits = [c for c in doc.get("recent_commits") or () if isinstance(c, dict)]
    head = ("As of the deploy that built this map (" + (_stamp() or "no build stamp")
            + "), the newest the map knows about on the main branch are:")
    if not commits:
        return (head.rstrip(":") + ". This build's map carries no commit list, so I "
                "will not describe changes I cannot see.")
    lines = [head]
    for row in commits:
        date = str(row.get("date") or "")
        subject = _cut(row.get("subject"), 110)
        lines.append(f"- {date}  {subject}" if date else f"- {subject}")
    lines.append("Everything above is at that commit - anything merged after it is "
                 "not in this map, and I will not pretend it is.")
    return "\n".join(lines)


def self_repo() -> str:
    """Which public repository this code is - the fact the live build got wrong."""
    doc, why = _load()
    if not doc:
        return why
    repo = str(doc.get("repo") or "")
    public = bool(doc.get("public"))
    if not repo:
        return ("I cannot name my own repository: this build's map does not carry one, "
                "and I will not invent an address.")
    url = "https://github.com/" + repo
    lines = [("My own code is the " + repo + " repository"
              + (", public on GitHub at " + url if public else "")
              + ".")]
    lines.append("The map I answer from was built from " + (_stamp() or "a commit it "
                 "does not name") + ".")
    lines.append("Everything I run is in that repository - the backend, the desktop "
                 "shell, the Android app, the deploy stack and the documents - which is "
                 "why a question about my own code has an answer at all.")
    lines.append(NOT_CODE)
    return "\n".join(lines)
