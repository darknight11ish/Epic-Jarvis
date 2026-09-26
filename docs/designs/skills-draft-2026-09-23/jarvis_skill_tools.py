"""jarvis_skill_tools.py - skills that RUN code, with typed inputs, through the gate.

NOT jarvis_skills.py, ON PURPOSE
The owner's machine already has a `jarvis_skills.py` (skill-notes.patch patches
its `refine()` and `cards()`; jarvis-framework.toml section 12 describes its
scanner, its trust levels and its gated install). There is no second copy of
it anywhere - docs/ARCHITECTURE.md section 9 - so a new file with that name
would overwrite the only one. This module sits BESIDE it and only does the
thing that one explicitly does not: "Bundled scripts are NEVER run by the
loader" (jarvis-framework.toml, [skills] comment). Today a skill that wants a
script run has to get the model to write a shell command, which reaches the
gate as `run_shell_on_host` with free text the model composed. This replaces
that one path with a narrower one:

    a skill folder may carry `jarvis-tool.toml`, which names ONE Python
    entrypoint, a closed list of typed parameters, and the effects the code
    says it has. The model fills in the parameters. Nothing else.

WHAT A SKILL CAN AND CANNOT DECIDE ABOUT ITSELF
It can name its parameters and their types, and it can DECLARE effects. It
cannot set its tier, its trust, or its action name, and a declaration can
only ever make things stricter:

    trust     comes from jarvis_skills.cards() (the index its gated install
              wrote), never from the skill's own files. Missing -> third_party.
    effects   declared UNION detected. Detection reads the code with `ast`
              (it does not run it) and works from an allowlist, so anything
              it does not recognise counts as "could do anything".
    action    a pure function of (trust, effects). Three names, each one a
              row in jarvis_gate's tier table that the owner controls.
    refusal   a pure function of the same inputs (see _refusal_for). A refused
              skill never reaches the approval queue, the same rule the
              existing scanner follows.

and at run time the gate verdict must say a person approved THIS call. Tier
`auto` or `notify` in jarvis-framework.toml does not run a skill - it is
refused here, the same pattern skill-notes.patch uses for refine(). There is
no floor lower than `ask`, because on Windows, with no sandbox (decision
record: "Sandbox: git worktrees, not Docker"), the declared effects of code
are a claim and nothing more.

THE FOUR STEPS (docs/ARCHITECTURE.md section 3)
    discover()   read folders, validate, scan. Runs nothing, opens no socket.
    plan()       validate the model's arguments strictly, hash every file,
                 decide action/refusal. Runs nothing, opens no socket.
    describe()   the card: the whole source, the exact input, every hash,
                 declared vs detected effects, and what saying no costs.
    run()        needs the gate's Verdict object itself - not a boolean -
                 and re-checks every file hash on a private copy before
                 running that copy.

WHAT THIS IS NOT
Not a sandbox. The child process gets a scrubbed environment (no tokens, no
keys - they live in env vars here: JARVIS_GITHUB_TOKEN, HUD_TOKEN, the IMAP
password), a private temp dir, stdin JSON, a timeout and an output cap. That is
hygiene. Code that decides to open a socket can. The card says so in words.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.10 and earlier
    _toml = None  # type: ignore


# --------------------------------------------------------------------------
#   Limits and vocabularies - every one of them a closed set
# --------------------------------------------------------------------------

TOOL_FILE = "jarvis-tool.toml"
SKILL_MD_MAX_BYTES = 64 * 1024        # matches [skills].max_skill_md_kb = 64
CODE_MAX_BYTES = 48 * 1024            # all .py together; it is all on the card
MAX_FILES = 40
MAX_PARAMS = 16
MAX_STRING = 4000
MAX_LIST = 50
OUTPUT_MAX_BYTES = 64 * 1024
TIMEOUT_DEFAULT, TIMEOUT_MAX = 20, 120

# agentskills.io/specification: 1-64 chars, a-z 0-9 and hyphen, no leading,
# trailing or double hyphen, must equal the folder name. ASCII only on
# purpose: the reference validator (skills-ref validator.py:54) accepts any
# Unicode letter, which lets a Cyrillic "а" name a different skill that
# reads identically on a card.
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PARAM_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

FRONTMATTER_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"})
TOOL_KEYS = frozenset({"entrypoint", "timeout_seconds", "effects", "params"})
PARAM_KEYS = frozenset({"type", "description", "required", "default", "enum",
                        "minimum", "maximum", "max_length", "max_items"})
PARAM_TYPES = frozenset({"string", "integer", "number", "boolean", "string_list"})

# What a skill may say about itself. `compute` is "none of the others".
EFFECTS = frozenset({"compute", "read_files", "write_files", "private_data",
                     "network", "run_programs"})
# The effects that mean "this code can reach past this machine or start other
# code". `dynamic` is internal only: the scan saw eval/exec/an unknown import
# and therefore knows nothing.
_UNBOUNDED = frozenset({"network", "run_programs", "dynamic"})

# Trust levels named in jarvis-framework.toml [skills]: self = Jarvis wrote
# it, local = the owner wrote it by hand, third_party = anything imported.
# Only `local` is treated as the owner's own code. `self` is model output that
# a person approved, which is not the same thing as a person having written it.
TRUSTS = frozenset({"local", "self", "third_party"})

ACTION_UNTRUSTED = "skill_run_untrusted"
ACTION_LOCAL = "skill_run_local"
ACTION_LOCAL_NETWORK = "skill_run_local_network"
ACTIONS = (ACTION_UNTRUSTED, ACTION_LOCAL, ACTION_LOCAL_NETWORK)

_TEXT_SUFFIXES = frozenset({".md", ".txt", ".py", ".toml", ".json", ".csv"})


# --------------------------------------------------------------------------
#   Static reading of the code - an allowlist, so the unknown is the worst
# --------------------------------------------------------------------------

# Imports that do nothing outside this process except what the rest of this
# scan looks for separately (open(), os.remove, ...). Anything NOT here and
# not a sibling file in the skill is "dynamic": we do not know what it does.
_CONTAINED_IMPORTS = frozenset({
    "__future__", "abc", "argparse", "base64", "binascii", "bisect", "calendar",
    "collections", "colorsys", "copy", "csv", "dataclasses", "datetime",
    "decimal", "difflib", "enum", "fnmatch", "fractions", "functools", "hashlib",
    "heapq", "html", "io", "itertools", "json", "math", "numbers", "operator",
    "os", "pathlib", "pprint", "random", "re", "statistics", "string",
    "struct", "sys", "textwrap", "time", "typing", "unicodedata", "uuid",
    "zoneinfo", "zlib",
})
_NETWORK_IMPORTS = frozenset({
    "socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
    "websocket", "websockets", "asyncio", "socketserver", "selectors",
})
_PROGRAM_IMPORTS = frozenset({
    "subprocess", "multiprocessing", "ctypes", "cffi", "pty", "winreg",
    "_winapi", "msvcrt", "signal", "concurrent", "threading",
})
_WRITE_IMPORTS = frozenset({"shutil", "tempfile", "sqlite3", "zipfile", "tarfile"})
_DYNAMIC_NAMES = frozenset({
    "eval", "exec", "compile", "__import__", "globals", "vars", "locals",
    "getattr", "setattr", "delattr", "__builtins__", "breakpoint",
})
_DYNAMIC_IMPORTS = frozenset({"importlib", "runpy", "pickle", "marshal",
                              "code", "codeop", "imp", "pkgutil", "builtins"})
_OS_PROGRAM_ATTRS = frozenset({
    "system", "popen", "startfile", "fork", "forkpty", "kill", "killpg",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
    "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
    "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
})
_WRITE_ATTRS = frozenset({
    "remove", "unlink", "rmdir", "removedirs", "rename", "renames", "replace",
    "makedirs", "mkdir", "chmod", "chown", "symlink", "link", "truncate",
    "write_text", "write_bytes", "touch", "utime", "mkfifo",
})
_READ_ATTRS = frozenset({"read_text", "read_bytes", "listdir", "scandir",
                         "walk", "iterdir", "glob", "rglob"})


def _root_module(name: str) -> str:
    return (name or "").split(".", 1)[0]


def detect_effects(sources: dict) -> tuple:
    """Read (never run) every .py file; return (effects, findings).

    `sources` is {relpath: text}. `findings` are "relpath:line  what" strings
    that go on the card verbatim, so the owner can check each one.

    This is a floor, not a proof. It cannot see what an unrecognised module
    does, so it says "dynamic" for those; and a determined author can hide a
    call from any static scan. It can only ever ADD effects.
    """
    siblings = {Path(p).stem for p in sources}
    effects: set = set()
    findings: list = []

    def hit(eff: str, rel: str, node, what: str) -> None:
        effects.add(eff)
        findings.append(f"{rel}:{getattr(node, 'lineno', 0)}  {what} -> {eff}")

    for rel, text in sorted(sources.items()):
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            effects.add("dynamic")
            findings.append(f"{rel}:{exc.lineno or 0}  does not parse -> dynamic")
            continue
        # Nodes that are the function of a call, so `open` used as a VALUE
        # (`o = open; o(p, "w")`) can be told apart from `open(...)`.
        called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for node in ast.walk(tree):
            mods: list = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:          # relative import: a sibling file
                    continue
                mods = [node.module or ""]
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    if a.name in _OS_PROGRAM_ATTRS:
                        hit("run_programs", rel, node, f"from {node.module} import {a.name}")
                    elif a.name in _WRITE_ATTRS:
                        hit("write_files", rel, node, f"from {node.module} import {a.name}")
                    elif full in ("logging.handlers", "logging.config"):
                        mods.append(full)
            for m in mods:
                root = _root_module(m)
                if m.startswith("logging.handlers"):
                    hit("network", rel, node, f"import {m}")
                elif m.startswith("logging.config"):
                    hit("dynamic", rel, node, f"import {m}")
                elif root in siblings or root in _CONTAINED_IMPORTS or root == "logging":
                    continue
                elif root in _NETWORK_IMPORTS:
                    hit("network", rel, node, f"import {m}")
                elif root in _PROGRAM_IMPORTS:
                    hit("run_programs", rel, node, f"import {m}")
                elif root in _WRITE_IMPORTS:
                    hit("write_files", rel, node, f"import {m}")
                elif root in _DYNAMIC_IMPORTS:
                    hit("dynamic", rel, node, f"import {m}")
                else:
                    hit("dynamic", rel, node, f"import {m} (not recognised)")

            if isinstance(node, ast.Name):
                if node.id in _DYNAMIC_NAMES:
                    hit("dynamic", rel, node, f"uses {node.id}")
                elif node.id == "open" and id(node) not in called:
                    hit("write_files", rel, node, "open used as a value")
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__") \
                        and node.attr not in ("__name__", "__file__", "__doc__"):
                    hit("dynamic", rel, node, f"touches .{node.attr}")
                elif node.attr == "modules" and _attr_base(node) == "sys":
                    hit("dynamic", rel, node, "sys.modules")
                elif node.attr == "handlers" and _attr_base(node) == "logging":
                    hit("network", rel, node, "logging.handlers")
                # Whatever the base is called: `import os as o; o.system(...)`
                # has base `o`. A false positive here only ever raises.
                elif node.attr in _OS_PROGRAM_ATTRS:
                    hit("run_programs", rel, node, f".{node.attr}(...)")
                elif node.attr in _WRITE_ATTRS:
                    hit("write_files", rel, node, f".{node.attr}(...)")
                elif node.attr in _READ_ATTRS:
                    hit("read_files", rel, node, f".{node.attr}(...)")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    mode = _open_mode(node)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
                    mode = _method_open_mode(node)
                else:
                    continue
                if mode is None or any(c in mode for c in "wax+"):
                    hit("write_files", rel, node, f"open(..., {mode!r})")
                else:
                    hit("read_files", rel, node, f"open(..., {mode!r})")
    return effects, findings


def _attr_base(node: ast.Attribute) -> str:
    v = node.value
    while isinstance(v, ast.Attribute):
        v = v.value
    return v.id if isinstance(v, ast.Name) else ""


def _open_mode(call: ast.Call) -> Optional[str]:
    """The literal mode of an open() call, "r" when absent, None when it is
    not a literal - an unknown mode is treated as a write."""
    node = call.args[1] if len(call.args) > 1 else None
    for kw in call.keywords:
        if kw.arg == "mode":
            node = kw.value
    if node is None:
        return "r"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


_MODE_RE = re.compile(r"^[rwxabt+]{1,4}$")


def _method_open_mode(call: ast.Call) -> Optional[str]:
    """`x.open(...)`: Path.open takes the mode FIRST, io.open/os.open take it
    second (os.open's is a flags int). So: a keyword mode if given; else any
    positional literal that looks like a mode; else "r" only for a bare
    `.open()`; anything else is unknown, which counts as a write."""
    for kw in call.keywords:
        if kw.arg in ("mode", "flags"):
            v = kw.value
            return v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else None
    for a in call.args[:2]:
        if isinstance(a, ast.Constant) and isinstance(a.value, str) and _MODE_RE.match(a.value):
            return a.value
    return "r" if len(call.args) <= 1 and all(
        isinstance(a, ast.Constant) for a in call.args) else None


# --------------------------------------------------------------------------
#   SKILL.md frontmatter - a strict subset of YAML, read by hand
# --------------------------------------------------------------------------

class SkillError(ValueError):
    """A skill folder that is not accepted. The message is for a person."""


_YAML_REFUSED = ("&", "*", "!", "|", ">", "[", "{", "? ")


def _scalar(raw: str, where: str) -> str:
    raw = raw.strip()
    if raw.startswith(_YAML_REFUSED):
        raise SkillError(f"{where}: uses a YAML feature Jarvis does not read "
                         f"(anchors, tags, block text, lists or maps inline). "
                         f"Write it as one plain line.")
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        inner = raw[1:-1]
        if raw[0] == '"':
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise SkillError(f"{where}: this quoted text is not valid")
        return inner.replace("''", "'")
    if " #" in raw:
        raw = raw.split(" #", 1)[0].rstrip()
    return raw


def parse_frontmatter(text: str) -> tuple:
    """(fields, body). Only `key: value` lines and one nested `metadata:` map.

    Why not a YAML library: a YAML parser accepts far more than the spec's
    frontmatter uses (anchors, tags, duplicate keys where the last silently
    wins), and every one of those is a way for two readers of the same file
    to disagree about what it says. The backend also has no YAML dependency
    today, and this is not a reason to add one.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise SkillError("SKILL.md must start with a --- line")
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            raise SkillError("SKILL.md frontmatter is never closed with ---")
    block, body = text[4:end], text[end + 5:]
    fields: dict = {}
    current_map: Optional[dict] = None
    for n, line in enumerate(block.split("\n"), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise SkillError(f"SKILL.md line {n}: tab indentation")
        indented = line.startswith(" ")
        key, sep, value = line.strip().partition(":")
        if not sep:
            raise SkillError(f"SKILL.md line {n}: expected 'key: value'")
        key = key.strip()
        if indented:
            if current_map is None:
                raise SkillError(f"SKILL.md line {n}: indented line outside metadata")
            if key in current_map:
                raise SkillError(f"SKILL.md line {n}: metadata.{key} appears twice")
            current_map[key] = _scalar(value, f"SKILL.md line {n}")
            continue
        current_map = None
        if key in fields:
            raise SkillError(f"SKILL.md line {n}: '{key}' appears twice")
        if key not in FRONTMATTER_FIELDS:
            raise SkillError(
                f"SKILL.md line {n}: '{key}' is not an agentskills.io field. "
                f"Jarvis reads only {sorted(FRONTMATTER_FIELDS)}; trust, tier and "
                f"permissions are never read from a skill's own files.")
        if key == "metadata":
            if value.strip():
                raise SkillError(f"SKILL.md line {n}: metadata must be a nested map")
            fields[key] = current_map = {}
            continue
        fields[key] = _scalar(value, f"SKILL.md line {n}")
    return fields, body


# --------------------------------------------------------------------------
#   The skill as discovered
# --------------------------------------------------------------------------

@dataclass
class Param:
    name: str
    type: str
    description: str = ""
    required: bool = False
    default: object = None
    enum: Optional[list] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    max_length: int = 500
    max_items: int = 20

    def schema(self) -> dict:
        s: dict = {"description": self.description} if self.description else {}
        if self.type == "string_list":
            item: dict = {"type": "string", "maxLength": self.max_length}
            if self.enum:
                item["enum"] = list(self.enum)
            s.update({"type": "array", "items": item, "maxItems": self.max_items})
            return s
        s["type"] = self.type
        if self.type == "string":
            s["maxLength"] = self.max_length
            if self.enum:
                s["enum"] = list(self.enum)
        if self.type in ("integer", "number"):
            if self.minimum is not None:
                s["minimum"] = self.minimum
            if self.maximum is not None:
                s["maximum"] = self.maximum
        return s


@dataclass
class Skill:
    name: str
    description: str
    folder: str
    entrypoint: str
    timeout_seconds: int
    params: list
    effects_declared: list
    effects_detected: list
    findings: list
    scan_warnings: list
    allowed_tools_ignored: str
    license: str
    trust: str
    action: str
    refused: str          # "" when runnable; otherwise why, in words
    # The bytes that were scanned, hashed from the SAME read. plan() refuses
    # if the folder no longer matches these, so what was scanned, what the
    # card shows and what runs are one set of bytes, not three reads.
    files: dict = field(default_factory=dict)      # relpath -> sha256
    sources: dict = field(default_factory=dict)    # relpath -> text, .py only

    def tool_name(self) -> str:
        return f"skill__{self.name}"

    def schema(self) -> dict:
        return {"type": "object",
                "properties": {p.name: p.schema() for p in self.params},
                "required": [p.name for p in self.params if p.required],
                "additionalProperties": False}

    def as_card(self) -> dict:
        """For a listing surface. Deliberately no source text: that belongs on
        the approval card, where it is read at the moment it matters."""
        return {"name": self.name, "description": self.description,
                "trust": self.trust, "action": self.action,
                "effects_declared": list(self.effects_declared),
                "effects_detected": list(self.effects_detected),
                "refused": self.refused or None,
                "scan_warnings": list(self.scan_warnings)}


def _is_link(p: Path) -> bool:
    """Symlink OR Windows junction/reparse point. `is_symlink()` alone misses
    junctions before Python 3.12, and a junction is how a folder on Windows
    points somewhere else without admin rights."""
    try:
        st = os.lstat(p)
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if attrs & reparse:
        return True
    is_junction = getattr(Path, "is_junction", None)
    return bool(is_junction and is_junction(p))


def _walk_files(folder: Path) -> list:
    """Every file in the skill, as relative posix paths. Refuses links of
    either kind anywhere, and anything that is not plain text."""
    if _is_link(folder):
        raise SkillError(f"{folder.name} is a link to somewhere else")
    out = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        for d in list(dirnames):
            if _is_link(Path(dirpath) / d):
                raise SkillError(f"{d} inside the skill is a link")
            if d == "__pycache__":
                raise SkillError("the skill ships compiled Python (__pycache__); "
                                 "only source is accepted, because only source "
                                 "is what the card shows")
        for f in filenames:
            p = Path(dirpath) / f
            rel = p.relative_to(folder).as_posix()
            if _is_link(p):
                raise SkillError(f"{rel} is a link")
            if p.suffix.lower() not in _TEXT_SUFFIXES:
                raise SkillError(
                    f"{rel}: only {sorted(_TEXT_SUFFIXES)} files are accepted in "
                    f"a skill that runs code. Anything else could be started by "
                    f"it and would not be on the card.")
            out.append(rel)
            if len(out) > MAX_FILES:
                raise SkillError(f"more than {MAX_FILES} files")
    return sorted(out)


def _read_text(p: Path, limit: int) -> str:
    return _read_text_and_hash(p, limit)[0]


def _read_text_and_hash(p: Path, limit: int) -> tuple:
    raw = p.read_bytes()
    if len(raw) > limit:
        raise SkillError(f"{p.name} is {len(raw)} bytes; the limit is {limit}")
    try:
        return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()
    except UnicodeDecodeError:
        raise SkillError(f"{p.name} is not UTF-8 text")


def _parse_param(name: str, raw: object) -> Param:
    if not _PARAM_RE.match(name):
        raise SkillError(f"parameter name {name!r}: lowercase letters, digits, "
                         f"underscores, starting with a letter, at most 32")
    if not isinstance(raw, dict):
        raise SkillError(f"params.{name} must be a table")
    extra = set(raw) - PARAM_KEYS
    if extra:
        raise SkillError(f"params.{name}: unknown keys {sorted(extra)}")
    t = raw.get("type")
    if t not in PARAM_TYPES:
        raise SkillError(f"params.{name}.type must be one of {sorted(PARAM_TYPES)}")
    p = Param(name=name, type=t,
              description=str(raw.get("description", ""))[:300],
              required=raw.get("required", False))
    if not isinstance(p.required, bool):
        raise SkillError(f"params.{name}.required must be true or false")
    if "max_length" in raw:
        ml = raw["max_length"]
        if type(ml) is not int or not 1 <= ml <= MAX_STRING:
            raise SkillError(f"params.{name}.max_length must be 1..{MAX_STRING}")
        p.max_length = ml
    if "max_items" in raw:
        mi = raw["max_items"]
        if type(mi) is not int or not 1 <= mi <= MAX_LIST:
            raise SkillError(f"params.{name}.max_items must be 1..{MAX_LIST}")
        p.max_items = mi
    if "enum" in raw:
        en = raw["enum"]
        if t not in ("string", "string_list") or not isinstance(en, list) or not en \
                or not all(isinstance(e, str) for e in en):
            raise SkillError(f"params.{name}.enum must be a list of strings "
                             f"on a string or string_list parameter")
        p.enum = list(en)
    for k in ("minimum", "maximum"):
        if k in raw:
            v = raw[k]
            if t not in ("integer", "number") or isinstance(v, bool) \
                    or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise SkillError(f"params.{name}.{k} must be a finite number "
                                 f"on an integer or number parameter")
            setattr(p, k, v)
    if "default" in raw:
        if p.required:
            raise SkillError(f"params.{name}: a required parameter has no default")
        err = _type_error(p, raw["default"])
        if err:
            raise SkillError(f"params.{name}.default: {err}")
        p.default = raw["default"]
    return p


def _load_tool_file(folder: Path) -> dict:
    if _toml is None:
        raise SkillError("no TOML reader (needs Python 3.11+)")
    try:
        data = _toml.loads(_read_text(folder / TOOL_FILE, 16 * 1024))
    except SkillError:
        raise
    except Exception as exc:
        raise SkillError(f"{TOOL_FILE} does not parse: {exc}")
    extra = set(data) - TOOL_KEYS
    if extra:
        raise SkillError(f"{TOOL_FILE}: unknown keys {sorted(extra)}. Trust, tier "
                         f"and approval are not a skill's to set.")
    return data


def _entrypoint(folder: Path, raw: object, files: list) -> str:
    if not isinstance(raw, str) or not raw.endswith(".py"):
        raise SkillError(f"{TOOL_FILE}: entrypoint must be a .py path inside the skill")
    rel = raw.replace("\\", "/")
    if rel.startswith("/") or ":" in rel or ".." in rel.split("/"):
        raise SkillError(f"{TOOL_FILE}: entrypoint {raw!r} leaves the skill folder")
    if rel not in files:
        raise SkillError(f"{TOOL_FILE}: entrypoint {raw!r} does not exist")
    return rel


def _refusal_for(trust: str, declared: set, detected: set, blocked: list) -> str:
    """The whole policy, in one place, as a pure function. The model is not
    an input. Neither is anything the skill says about its own trust."""
    if blocked:
        return ("the skill scanner refused it: " + "; ".join(blocked))
    everything = declared | detected
    if "private_data" in everything and everything & _UNBOUNDED:
        return ("it both reads private data and can reach the network or start "
                "other programs. Private data stays on this machine, so that "
                "pair is never offered, whoever wrote the skill.")
    if trust != "local":
        if everything & _UNBOUNDED:
            return (f"it is {trust.replace('_', ' ')} code and can "
                    f"{_plain(everything & _UNBOUNDED)}. Code from outside is only "
                    f"run when the scan can see everything it does. To run it "
                    f"anyway, read it and reinstall it as your own (trust: local).")
        undeclared = detected - declared - {"compute"}
        if undeclared:
            return (f"it says it does {_plain(declared)} but its code also does "
                    f"{_plain(undeclared)}. A skill from outside that understates "
                    f"what it does is not offered at all.")
    return ""


def _action_for(trust: str, effects: set) -> str:
    if trust != "local":
        return ACTION_UNTRUSTED
    return ACTION_LOCAL_NETWORK if effects & _UNBOUNDED else ACTION_LOCAL


_PLAIN = {"compute": "calculation only", "read_files": "read files",
          "write_files": "change or delete files",
          "private_data": "read private data (email, credentials, memory)",
          "network": "reach the internet", "run_programs": "start other programs",
          "dynamic": "things the scan cannot see (eval, exec, or an unrecognised "
                     "import)"}


def _plain(effs: Iterable) -> str:
    return ", ".join(_PLAIN.get(e, e) for e in sorted(effs)) or "nothing"


def _default_scanner():
    """The existing module's raw-bytes scanner - skill-notes.patch calls it as
    `scan_text(note, "note")` and reads `.severity == "block"` on each finding.
    Not re-implemented here: two scanners drift, and the one that exists is
    the one the owner has been told about."""
    try:
        import jarvis_skills
        return jarvis_skills.scan_text
    except Exception:
        return None


def _default_trust_of(name: str) -> str:
    """From the index the gated install wrote (`cards()` returns `trust`, per
    skill-notes.patch). Anything missing or unrecognised is third_party."""
    try:
        import jarvis_skills
        for c in jarvis_skills.cards():
            if c.get("name") == name:
                t = c.get("trust", "third_party")
                return t if t in TRUSTS else "third_party"
    except Exception:
        pass
    return "third_party"


def default_root() -> Path:
    """UNVERIFIED default: where the owner's jarvis_skills keeps skills has not
    been seen from here. ~/.openjarvis is where memory.db, the token and
    approvals.db live (backend/rebuilt/jarvis_framework.py), and OpenJarvis
    installs skills to <config>/skills (openjarvis skills/importer.py:69)."""
    env = os.environ.get("JARVIS_SKILLS_DIR", "").strip()
    return Path(env) if env else Path.home() / ".openjarvis" / "skills"


def load_skill(folder: Path, *, scanner=None, trust_of=None) -> Skill:
    """One folder -> one Skill, or SkillError. Reads files. Runs nothing."""
    folder = Path(folder)
    if scanner is None:
        scanner = _default_scanner()
    trust_of = trust_of or _default_trust_of
    files = _walk_files(folder)
    if "SKILL.md" not in files:
        raise SkillError("no SKILL.md")
    fm, _body = parse_frontmatter(_read_text(folder / "SKILL.md", SKILL_MD_MAX_BYTES))
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not (isinstance(name, str) and 1 <= len(name) <= 64 and _NAME_RE.match(name)):
        raise SkillError(f"name {name!r}: 1-64 of a-z, 0-9 and single hyphens")
    if name != folder.name:
        raise SkillError(f"name {name!r} must match its folder {folder.name!r}")
    if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
        raise SkillError("description must be 1-1024 characters")
    meta = fm.get("metadata", {})
    if not isinstance(meta, dict):
        raise SkillError("metadata must be a map")

    tool = _load_tool_file(folder)
    entry = _entrypoint(folder, tool.get("entrypoint"), files)
    timeout = tool.get("timeout_seconds", TIMEOUT_DEFAULT)
    if type(timeout) is not int or not 1 <= timeout <= TIMEOUT_MAX:
        raise SkillError(f"timeout_seconds must be a whole number 1..{TIMEOUT_MAX}")
    effects = tool.get("effects")
    if not isinstance(effects, list) or not effects \
            or not all(isinstance(e, str) for e in effects):
        raise SkillError('effects must be a non-empty list, e.g. ["compute"]')
    unknown = set(effects) - EFFECTS
    if unknown:
        raise SkillError(f"effects {sorted(unknown)} are not known; "
                         f"use {sorted(EFFECTS)}")
    params_raw = tool.get("params", {})
    if not isinstance(params_raw, dict) or len(params_raw) > MAX_PARAMS:
        raise SkillError(f"params must be a table of at most {MAX_PARAMS}")
    params = [_parse_param(k, v) for k, v in sorted(params_raw.items())]

    read = {rel: _read_text_and_hash(folder / rel, SKILL_MD_MAX_BYTES) for rel in files}
    texts = {rel: t for rel, (t, _h) in read.items()}
    hashes = {rel: h for rel, (_t, h) in read.items()}
    sources = {rel: t for rel, t in texts.items() if rel.endswith(".py")}
    if sum(len(t.encode("utf-8")) for t in sources.values()) > CODE_MAX_BYTES:
        raise SkillError(f"more than {CODE_MAX_BYTES} bytes of Python. All of it "
                         f"goes on the approval card; too long to read is too "
                         f"long to approve.")

    blocked, warned = [], []
    if scanner is None:
        blocked.append("the skill scanner (jarvis_skills.scan_text) is not "
                       "available here, and a skill that runs code is not "
                       "offered unscanned")
    else:
        for rel, t in texts.items():
            try:
                found = list(scanner(t, rel) or [])
            except Exception as exc:
                blocked.append(f"the scanner failed on {rel}: {type(exc).__name__}")
                continue
            for f in found:
                what = getattr(f, "reason", None) or getattr(f, "message", None) \
                    or getattr(f, "rule", None) or str(f)
                (blocked if getattr(f, "severity", "block") == "block"
                 else warned).append(f"{rel}: {what}")

    detected, findings = detect_effects(sources)
    declared = set(effects)
    trust = trust_of(name)
    trust = trust if trust in TRUSTS else "third_party"
    everything = declared | detected
    return Skill(
        name=name, description=desc, folder=str(folder), entrypoint=entry,
        timeout_seconds=timeout, params=params,
        effects_declared=sorted(declared), effects_detected=sorted(detected),
        findings=findings, scan_warnings=warned,
        allowed_tools_ignored=str(fm.get("allowed-tools", "")),
        license=str(fm.get("license", "")),
        trust=trust, action=_action_for(trust, everything),
        refused=_refusal_for(trust, declared, detected, blocked),
        files=hashes, sources=sources)


def discover(root: Optional[Path] = None, *, scanner=None, trust_of=None) -> tuple:
    """({name: Skill}, [(folder, reason)]). Only folders with a jarvis-tool.toml
    are this module's; an instruction-only skill belongs to jarvis_skills and
    is silently not ours. Rejections are returned, not logged and dropped: a
    skill that vanished for a reason nobody can see is the defect this
    codebase keeps producing."""
    root = Path(root) if root else default_root()
    found: dict = {}
    rejected: list = []
    if not root.is_dir():
        return found, rejected
    for child in sorted(root.iterdir()):
        if not (child / TOOL_FILE).exists() and not _is_link(child):
            continue
        try:
            s = load_skill(child, scanner=scanner, trust_of=trust_of)
        except (SkillError, OSError) as exc:
            rejected.append((child.name, str(exc)))
            continue
        found[s.name] = s
    return found, rejected


def cards(root: Optional[Path] = None, **kw) -> dict:
    """What a listing surface serves - including the refused and the rejected,
    each with its reason."""
    found, rejected = discover(root, **kw)
    return {"skills": [s.as_card() for s in found.values()],
            "rejected": [{"folder": f, "reason": r} for f, r in rejected]}


# --------------------------------------------------------------------------
#   Strict typing of the model's arguments - no coercion, ever
# --------------------------------------------------------------------------

def _type_error(p: Param, v: object) -> str:
    """"" if `v` is acceptable for `p`, otherwise a sentence the MODEL reads
    and can retry from. `"5"` is not an integer and `True` is not a number:
    Python's bool is an int, which is exactly the kind of looseness that turns
    `{"count": true}` into 1 without anyone deciding it."""
    if p.type == "boolean":
        return "" if type(v) is bool else f"expected true or false, got {_show(v)}"
    if p.type == "integer":
        if type(v) is not int:
            return f"expected a whole number, got {_show(v)}"
    elif p.type == "number":
        if type(v) not in (int, float) or not math.isfinite(v):
            return f"expected a finite number, got {_show(v)}"
    elif p.type == "string":
        if type(v) is not str:
            return f"expected text, got {_show(v)}"
        return _string_error(p, v)
    elif p.type == "string_list":
        if type(v) is not list:
            return f"expected a list of text, got {_show(v)}"
        if len(v) > p.max_items:
            return f"at most {p.max_items} items, got {len(v)}"
        for i, item in enumerate(v):
            if type(item) is not str:
                return f"item {i}: expected text, got {_show(item)}"
            err = _string_error(p, item)
            if err:
                return f"item {i}: {err}"
        return ""
    if p.minimum is not None and v < p.minimum:
        return f"must be at least {p.minimum}, got {v}"
    if p.maximum is not None and v > p.maximum:
        return f"must be at most {p.maximum}, got {v}"
    return ""


def _string_error(p: Param, v: str) -> str:
    if len(v) > p.max_length:
        return f"at most {p.max_length} characters, got {len(v)}"
    if "\x00" in v:
        return "contains a NUL character"
    if p.enum and v not in p.enum:
        return f"must be one of {p.enum}, got {v!r}"
    return ""


def _show(v: object) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str)
    return f"{type(v).__name__} {s[:60]}"


def validate_args(skill: Skill, args: object) -> tuple:
    """(clean, errors). `clean` has defaults filled in, so what is on the card
    is everything the code receives - not "whatever it defaults to"."""
    if not isinstance(args, dict):
        return {}, [f"arguments must be an object, got {type(args).__name__}"]
    known = {p.name: p for p in skill.params}
    errors = [f"{k}: not a parameter of {skill.name} (it takes "
              f"{sorted(known) or 'none'})" for k in sorted(set(args) - set(known))]
    clean: dict = {}
    for p in skill.params:
        if p.name not in args:
            if p.required:
                errors.append(f"{p.name}: required")
            elif p.default is not None:
                clean[p.name] = p.default
            continue
        err = _type_error(p, args[p.name])
        if err:
            errors.append(f"{p.name}: {err}")
        else:
            clean[p.name] = args[p.name]
    return (clean if not errors else {}), errors


# --------------------------------------------------------------------------
#   plan / describe - touch nothing
# --------------------------------------------------------------------------

@dataclass
class Plan:
    skill: str
    trust: str
    action: str
    folder: str
    entrypoint: str
    timeout_seconds: int
    input_json: str               # the exact text written to the child's stdin
    files: dict                   # relpath -> sha256, captured now
    sources: dict                 # relpath -> text, every .py, for the card
    effects_declared: list
    effects_detected: list
    findings: list
    scan_warnings: list
    allowed_tools_ignored: str
    license: str
    if_refused: str
    refused: str = ""
    errors: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("sources")          # on the card; not repeated in results
        return d


def _hash_tree(folder: Path) -> dict:
    return {rel: hashlib.sha256((folder / rel).read_bytes()).hexdigest()
            for rel in _walk_files(folder)}


def _taint_active() -> Optional[bool]:
    """jarvis_gate.taint_active() - evidenced by gate-push.patch:92 and
    test_gate_push.py:69. None when it cannot be asked, which callers treat
    as tainted."""
    try:
        import jarvis_gate
        return bool(jarvis_gate.taint_active())
    except Exception:
        return None


def plan(skill: Skill, args: object, *, taint=_taint_active) -> Plan:
    """Work out exactly what would run. Runs nothing, opens nothing.

    Note what is NOT a parameter here: tier, action, trust. The model supplies
    `args` and nothing else, and `args` cannot name a key the skill did not
    declare (additionalProperties is false, and enforced here, not trusted to
    the model's JSON-schema compliance)."""
    folder = Path(skill.folder)
    clean, errors = validate_args(skill, args)
    refused = skill.refused
    if not refused and errors:
        refused = "the arguments did not fit the skill's parameters"
    effects = set(skill.effects_declared) | set(skill.effects_detected)
    if not refused and effects & _UNBOUNDED:
        t = taint()
        if t is not False:
            refused = ("this conversation has read something private (or that "
                       "could not be checked), and this skill can reach past "
                       "this machine. It is not offered until that clears."
                       if t else
                       "whether this conversation has read something private "
                       "could not be checked, and this skill can reach past "
                       "this machine")
    try:
        now = _hash_tree(folder)
    except (OSError, SkillError) as exc:
        now = None
        refused = refused or f"the skill folder could not be read now: {exc}"
    if now is not None and now != skill.files and not refused:
        refused = ("its files changed since it was scanned. It has to be "
                   "discovered (and scanned) again before it can be offered.")
    return Plan(
        skill=skill.name, trust=skill.trust, action=skill.action,
        folder=str(folder), entrypoint=skill.entrypoint,
        timeout_seconds=skill.timeout_seconds,
        input_json=json.dumps(clean, ensure_ascii=False, sort_keys=True, indent=2),
        files=dict(skill.files), sources=dict(skill.sources),
        effects_declared=list(skill.effects_declared),
        effects_detected=list(skill.effects_detected),
        findings=list(skill.findings), scan_warnings=list(skill.scan_warnings),
        allowed_tools_ignored=skill.allowed_tools_ignored, license=skill.license,
        if_refused=(f"{skill.name} does not run. Jarvis answers without it, and "
                    f"nothing on this computer changes. You will be asked again "
                    f"only if Jarvis tries to use it again."),
        refused=refused, errors=errors)


_TRUST_WORDS = {"local": "you wrote it (trust: local)",
                "self": "Jarvis wrote it and you approved the install (trust: self)",
                "third_party": "it came from outside (trust: third party)"}


def describe(p: Plan) -> str:
    """The card. Every line of code, the exact input, every hash. Nothing
    summarised: summarising the thing on the card that authorises it defeats
    the card, and if it is too long to read that is information."""
    if p.refused:
        return (f"Jarvis will not run the skill {p.skill}: {p.refused}"
                + ("\n\n" + "\n".join(p.errors) if p.errors else ""))
    lines = [
        f"Jarvis wants to run the skill {p.skill} on this computer.",
        f"Who wrote it: {_TRUST_WORDS.get(p.trust, p.trust)}.",
        "",
        "It will receive exactly this input:",
        "",
        *("    " + l for l in p.input_json.splitlines()),
        "",
        f"It says it will: {_plain(p.effects_declared)}.",
        f"A read of its code found: {_plain(p.effects_detected) if p.effects_detected else 'calculation only'}.",
        *("    " + f for f in p.findings),
        "",
        "What this cannot promise: this is Python running with your account's "
        "permissions. It gets no passwords or tokens from Jarvis, a private "
        "scratch folder and a time limit, but Jarvis cannot stop it doing "
        "something its code does not show. The lists above are a claim and a "
        "scan, not a guarantee.",
    ]
    if p.scan_warnings:
        lines += ["", "The skill scanner warned:", *("    " + w for w in p.scan_warnings)]
    if p.allowed_tools_ignored:
        lines += ["", f"The skill asks for these tools to be pre-approved: "
                      f"{p.allowed_tools_ignored}. Jarvis never pre-approves "
                      f"anything, so that request is ignored."]
    lines += ["", f"Time limit: {p.timeout_seconds} seconds.", "",
              "Files, with their fingerprints (SHA-256). If any of these change "
              "before it runs, it will not run:"]
    lines += [f"    {h}  {rel}" for rel, h in sorted(p.files.items())]
    for rel, text in sorted(p.sources.items()):
        marker = "  (this is what runs)" if rel == p.entrypoint else ""
        lines += ["", f"----- {rel}{marker} -----", text.rstrip("\n"), "----- end -----"]
    lines += ["", f"If you say no: {p.if_refused}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   run - only with the gate's own verdict for this plan
# --------------------------------------------------------------------------

def _human_approved(v: object, p: Plan) -> str:
    """"" when `v` says a person approved this action; otherwise why not.

    `allowed` is not "a human decided" (docs/ARCHITECTURE.md section 3):
    jarvis_gate.check returns allowed=True for tier auto and notify with
    nobody asked. A skill is code from a folder; it runs only on `ask`,
    answered yes. `outcome` comes from gate-outcome.patch; a gate without it
    still has `tier`, and `ask` + allowed is only reachable by approval there.
    `unclassified_tool` is accepted as the action because that is what
    jarvis_gate.action_for_tool returns for a name its tables do not hold yet
    (jarvis_agent.py:375-380), and it too is tier ask by default.
    """
    if v is None:
        return ("no approval reached this run. (If this came through "
                "jarvis_agent, it needs the verdict hand-off in "
                "jarvis_agent-verdict.diff.)")
    if not getattr(v, "allowed", False):
        return f"not approved: {getattr(v, 'reason', 'refused')}"
    tier = getattr(v, "tier", None)
    if tier != "ask":
        return (f"{p.action} is tier {tier!r} in jarvis-framework.toml, which "
                f"means nobody was asked. A skill runs only when a person says "
                f"yes to it: set {p.action} to \"ask\", or to \"never\" to "
                f"refuse these outright.")
    outcome = getattr(v, "outcome", "approved")
    if outcome != "approved":
        return f"the gate's outcome was {outcome!r}, not a person's yes"
    if getattr(v, "action", None) not in (p.action, "unclassified_tool"):
        return (f"that approval was for {getattr(v, 'action', None)!r}, "
                f"not {p.action!r}")
    return ""


def _child_env(scratch: Path) -> dict:
    """An allowlist, not a denylist: a denylist of secret names is out of date
    the day someone adds JARVIS_SOMETHING_KEY. Windows needs SYSTEMROOT for
    Python to start its random source and sockets at all."""
    env = {}
    for k in ("SYSTEMROOT", "WINDIR"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    env["PATH"] = str(Path(sys.executable).parent)
    env["TEMP"] = env["TMP"] = env["TMPDIR"] = str(scratch)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _read_capped(path: Path) -> tuple:
    with open(path, "rb") as f:
        raw = f.read(OUTPUT_MAX_BYTES + 1)
    return raw[:OUTPUT_MAX_BYTES].decode("utf-8", "replace"), len(raw) > OUTPUT_MAX_BYTES


def _kill_tree(proc) -> None:
    if os.name == "nt":  # pragma: no cover - not exercised off Windows
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _spawn(argv: list, *, cwd: Path, env: dict, stdin: bytes, timeout: int,
           out: Path, err: Path) -> dict:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(out, "wb") as fo, open(err, "wb") as fe:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                                stdout=fo, stderr=fe, shell=False,
                                creationflags=flags)
        try:
            proc.communicate(stdin, timeout=timeout)
            return {"exit_code": proc.returncode, "timed_out": False}
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.wait(timeout=10)
            return {"exit_code": None, "timed_out": True}


def run(p: Plan, verdict: object, *, spawn: Optional[Callable[..., dict]] = None,
        taint=_taint_active) -> dict:
    """Run an approved plan. `verdict` is the gate's own answer to this plan's
    action - there is no `approved=True` to pass, because a boolean is what
    lets a caller that never asked anyone say it did.

    Runs a PRIVATE COPY of the folder, after checking the copy's hashes against
    the card: checking the original and then running it would leave a gap in
    which the file that runs is not the file that was read."""
    base = {"ok": False, "skill": p.skill, "untrusted_output": True,
            "ran": False}
    if p.refused:
        return {**base, "error": f"refused: {p.refused}", "details": p.errors}
    why = _human_approved(verdict, p)
    if why:
        return {**base, "error": f"refused: {why}"}
    effects = set(p.effects_declared) | set(p.effects_detected)
    if effects & _UNBOUNDED and taint() is not False:
        return {**base, "error": "refused: the conversation read something "
                                 "private after this was approved (or that "
                                 "cannot be checked now)"}
    work = Path(tempfile.mkdtemp(prefix=f"jarvis-skill-{p.skill}-"))
    try:
        copy = work / "skill"
        shutil.copytree(p.folder, copy, symlinks=True)
        try:
            now = _hash_tree(copy)
        except SkillError as exc:
            now = {"<unreadable>": str(exc)}
        if now != p.files:
            changed = sorted(set(now) ^ set(p.files)
                             | {k for k in now if now.get(k) != p.files.get(k)})
            return {**base, "error": "refused: the skill's files changed after "
                                     "the card was shown: " + ", ".join(changed)}
        scratch = work / "scratch"
        scratch.mkdir()
        # -E ignores PYTHON* variables, -s ignores the user's site-packages.
        # Not -I: isolated mode also drops the script's own folder from
        # sys.path, which breaks a skill importing its own sibling file -
        # and that folder is the private copy just verified above.
        argv = [sys.executable, "-E", "-s", "-X", "utf8", "-B",
                str(copy / Path(p.entrypoint))]
        res = (spawn or _spawn)(argv, cwd=copy, env=_child_env(scratch),
                                stdin=p.input_json.encode("utf-8"),
                                timeout=p.timeout_seconds,
                                out=work / "stdout", err=work / "stderr")
        stdout, cut = _read_capped(work / "stdout") if (work / "stdout").exists() else ("", False)
        stderr, _ = _read_capped(work / "stderr") if (work / "stderr").exists() else ("", False)
        try:
            output = json.loads(stdout) if stdout.strip() and not cut else stdout
        except json.JSONDecodeError:
            output = stdout
        ok = res.get("exit_code") == 0 and not res.get("timed_out")
        out = {**base, "ok": ok, "ran": True, "exit_code": res.get("exit_code"),
               "timed_out": bool(res.get("timed_out")), "output": output,
               "output_truncated": cut, "stderr_tail": stderr[-2000:]}
        if res.get("timed_out"):
            out["error"] = f"stopped after {p.timeout_seconds} seconds"
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------
#   Call sites
# --------------------------------------------------------------------------

def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check, failing CLOSED on any error - the same wrapper shape
    as jarvis_agent._gate_check (jarvis_agent.py:653-672)."""
    class _Refused:
        allowed, tier, outcome, action = False, "unknown", "refused", ""

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate is not usable here ({exc}); refusing")


def invoke(skill: Skill, args: object, *, gate_check=None, spawn=None,
           taint=_taint_active) -> dict:
    """plan -> describe -> ONE gate decision -> run. For callers outside the
    chat loop. Nothing is cached: the next call asks again."""
    p = plan(skill, args, taint=taint)
    if p.refused:
        return {"ok": False, "skill": skill.name, "ran": False,
                "error": f"refused: {p.refused}", "details": p.errors}
    card = describe(p)
    v = (gate_check or _gate_check)(p.action, {"text": card},
                                    f"skill {p.skill} {p.input_json[:1500]}")
    return run(p, v, spawn=spawn, taint=taint)


def agent_tools(root: Optional[Path] = None, *, scanner=None, trust_of=None,
                taint=_taint_active, spawn=None) -> dict:
    """{tool_name: jarvis_agent.Tool} for every skill that is not refused.

    Wiring (not done by this module, deliberately): the HUD merges these into
    jarvis_agent.TOOLS, and a tool is only OFFERED when its name is in
    [tools].enabled - the same opt-in browser_control uses
    (jarvis_agent.py:24-28). Execution needs jarvis_agent to hand the verdict
    through (jarvis_agent-verdict.diff); without that hand-off every call is
    refused here, which is the safe way for the wiring to be incomplete.
    """
    import jarvis_agent as AG
    found, _rejected = discover(root, scanner=scanner, trust_of=trust_of)
    tools = {}
    for s in found.values():
        if s.refused:
            continue

        def prepare(args, _s=s):
            p = plan(_s, args, taint=taint)
            if p.refused:
                # Raised, so jarvis_agent returns it to the model as "could
                # not accept those arguments" and NO card is raised: a refusal
                # never reaches the approval queue.
                raise ValueError(p.refused + ("; " + "; ".join(p.errors)
                                              if p.errors else ""))
            return p, describe(p)

        def execute(args, state, _s=s, **kw):
            return run(state, kw.get("verdict"), spawn=spawn, taint=taint)

        t = AG.Tool(s.tool_name(),
                    f"{s.description} (A local skill. Every use shows the owner "
                    f"its code and waits for a yes.)",
                    s.schema(), prepare, execute,
                    gate_lookup_name=lambda args, _a=s.action: _a)
        t.needs_verdict = True
        tools[t.name] = t
    return tools
