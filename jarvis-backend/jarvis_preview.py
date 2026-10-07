"""
jarvis_preview.py - what it would do, rendered before you say yes.

The gate (jarvis_gate.py) answers "may this proceed". It cannot answer "what
IS this", and a person cannot answer the first question without the second.
Until now the approval card showed the raw tool arguments, which is how you
end up approving `rm -rf "$TMP/../.."` because it looked like a path.

Four rules, one module, and the first one is the reason for the other three:

  1. THE AUTHORITATIVE PANE IS COMPUTED, NOT WRITTEN.  Every fact on it comes
     out of code in this file. Nothing here calls a model, and nothing here
     generates prose about the action. The content being judged is exactly the
     content an attacker controls, so a summary written from it is a sentence
     the attacker gets to influence - and the sentence directly above the
     Approve button is the whole prize. A model gloss may still be useful, so
     Preview.gloss exists for a caller to fill in and render BELOW a fold,
     clearly labelled as written rather than measured. This module never
     fills it.

  2. THE PANE DECLARES ITS OWN COVERAGE.  Coverage is a required field on
     every Preview, not an optional extra, because a pane that looks confident
     about a command it only half parsed is worse than no pane at all: it
     manufactures the false confidence this feature exists to remove. Anything
     undecidable - $(...), backticks, a pipe into an interpreter, an
     -EncodedCommand payload, a fetched script, a variable standing where a
     path should be - goes into an unknown bucket, is counted against
     coverage, and takes the whole command to the top tier. "resolved 3 of 5
     tokens" is the honest headline; "looks fine" is not.

  3. THE NUMBER, NOT THE ADJECTIVE.  "Destructive" is an opinion. "412 files,
     2.1 GB" is a fact, and it is the fact that changes a decision. Every
     renderer produces one, and the phone card is built around it.

  4. THREE LINES FOR A PHONE.  A wall of unified diff on a six-inch screen
     gets swipe-approved unread, which is strictly worse than showing nothing,
     because afterwards the person believes they checked. card() returns
     exactly three short strings - verb and target, label and number, reach -
     and puts everything else behind `details`.

Everything is stdlib. Nothing here reaches the network. git is driven through
subprocess with an explicit argument list and never shell=True, because this
module's whole job is to be the thing that does not quietly run a string.
"""
from __future__ import annotations

import base64
import binascii
import difflib
import hashlib
import os
import json
import re
import sqlite3
import stat
import subprocess
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:                                    # pragma: no cover
    fw = None


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("preview", {}).get(key, default)
    except Exception:
        return default


def _audit(event: str, detail: dict) -> None:
    try:
        fw.audit_log(event, detail)
    except Exception:
        pass


# The tier ladder, same words and same order as the gate's. Duplicated rather
# than imported so that previewing an action never drags the approvals
# database, the taint latch and the polling loop into a process that only
# wanted to draw a card.
_RANK = {"auto": 0, "notify": 1, "ask": 2, "never": 3}
_TIER_CEILING = "never"


def _worst(*tiers: str) -> str:
    return max([t for t in tiers if t in _RANK] or ["ask"],
               key=lambda t: _RANK[t])


# Not everything unreadable is unreadable in the same way, and the first
# version of this module treated it as if it were: every undecidable command
# went to "never", which in this project means "only a config edit unblocks
# it". That reads as rigour and behaves as breakage - `ls $(pwd)` is an
# ordinary thing to type, and a rule that refuses it teaches the owner to
# widen the setting, which is how a safety rule ends up switched off.
#
# So the category splits in two, on the same line the skill scanner already
# draws:
#
#   FETCH AND EXECUTE - a pipe into an interpreter, `$(curl ...)`, a script
#   fetched and run in place, -EncodedCommand. There is no legitimate version
#   of these shapes, so there is nothing for a human to weigh and no reason to
#   offer them a button. NEVER.
#
#   MERELY UNREAD - a variable standing where a path should be, a plain
#   command substitution, three grammars disagreeing. A person can read this
#   and decide; what they must not be given is a pane that hides how little of
#   it we parsed. ASK, with the unresolved tokens stated on the card.
#
# The false-confidence failure this module exists to prevent is a pane that
# looks complete when it is not. Declared coverage is the fix for that, not
# refusing every command with a dollar sign in it.
_NO_HONEST_VERSION = (
    "pipe into an interpreter",
    "encoded command payload",
    "a fetched script is run in place",
)

# A command substitution is ordinary - `$(pwd)`, `$(git rev-parse HEAD)`. A
# command substitution that reaches the network inside it is not: whatever
# comes back becomes the arguments of the outer command, which is the same
# "someone else chooses what runs" shape as a pipe into a shell, and arguably
# worse, because `rm -rf $(curl ...)` lets a server choose what gets deleted.
_SUBST_NET = re.compile(
    r"\b(?:curl|wget|iwr|invoke-webrequest|nc|ncat|scp|ftp|"
    r"invoke-restmethod|irm)\b", re.I)


def _unknown_tier(unknown: Optional[list] = None) -> str:
    """What an undecidable command is classified as.

    `unknown` is the list of findings. Without it this returns the ceiling,
    because a caller that cannot say what it failed to read gets the strict
    answer.
    """
    ceiling = str(_cfg("unknown_tier", _TIER_CEILING) or _TIER_CEILING).strip().lower()
    ceiling = ceiling if ceiling in _RANK else _TIER_CEILING
    if unknown is None:
        return ceiling
    for u in unknown:
        if u.get("severity") != SEV_UNDECIDABLE:
            continue
        why = str(u.get("why", ""))
        if any(shape in why for shape in _NO_HONEST_VERSION):
            return ceiling
        if "substitution" in why and _SUBST_NET.search(str(u.get("token", ""))):
            return ceiling
    t = str(_cfg("unread_tier", "ask") or "ask").strip().lower()
    if t not in _RANK:
        t = "ask"
    # A setting cannot lower this below "ask": an unread command must always
    # reach a person, whatever the file says.
    return t if _RANK[t] >= _RANK["ask"] else "ask"


# --------------------------------------------------------------------------
#   The shape everything comes back in
# --------------------------------------------------------------------------

@dataclass
class Coverage:
    """How much of the thing the pane actually resolved.

    `total` is whole units of the input - shell tokens, files in a write set,
    recipients - and `resolved` is how many of them this module can state a
    fact about. They are deliberately not percentages in the data: a pane that
    rounds 4 of 5 to "80%" reads as a grade, and 4 of 5 reads as a list with
    something missing from it, which is what it is.
    """
    resolved: int
    total: int
    unit: str = "tokens"
    unknown: list = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.resolved >= self.total

    @property
    def percent(self) -> float:
        return 100.0 if self.total == 0 and self.resolved == 0 else (
            round(100.0 * self.resolved / self.total, 1) if self.total else 0.0)

    @property
    def text(self) -> str:
        return f"resolved {self.resolved} of {self.total} {self.unit}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(complete=self.complete, percent=self.percent, text=self.text)
        return d


@dataclass
class Preview:
    """One shape for every action, including the ones with no renderer.

    `coverage` has no default on purpose. A renderer that forgets it fails at
    construction rather than shipping a card that silently claims to have read
    everything.
    """
    action: str
    kind: str                     # shell | diff | email | git | none
    supported: bool
    coverage: Coverage
    verb: str                     # line 1 of the card
    target: str
    label: str                    # line 2: the rule-table classification
    number: str                   # line 2: the fact that makes it real
    reach: str                    # line 3: repo / machine / leaves
    tier_hint: str
    facts: dict = field(default_factory=dict)
    unknown: list = field(default_factory=list)
    # Written by a model, by someone else, later, and rendered below a fold.
    # This module never sets it - see rule 1 in the module docstring.
    gloss: Optional[str] = None
    error: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["coverage"] = self.coverage.as_dict()
        return d


REACH_REPO = "this repo"
REACH_MACHINE = "this machine"
REACH_OUT = "leaves the machine"


# --------------------------------------------------------------------------
#   Small formatting helpers
# --------------------------------------------------------------------------

def _bytes(n: int) -> str:
    """Human bytes, one decimal place, ASCII only."""
    n = max(0, int(n))
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def _elide(s: str, budget: int) -> str:
    """Shorten from the MIDDLE, because both ends of a path carry meaning.

    Cutting the tail off /home/me/projects/client-work/invoices leaves
    "/home/me/projects/clie..." which is the part you already knew. The
    basename is the part you were checking.
    """
    s = " ".join(str(s).split())
    if len(s) <= budget:
        return s
    if budget <= 4:
        return s[:max(0, budget)]
    head = (budget - 3) // 2
    tail = budget - 3 - head
    return s[:head] + "..." + (s[-tail:] if tail else "")


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


# --------------------------------------------------------------------------
#   Paths: what the command names, and whether we were told it is fine
# --------------------------------------------------------------------------

def _allowlist() -> list[str]:
    """Prefixes the owner has declared safe to touch without ceremony.

    Empty by default, and empty means "nothing is declared safe" rather than
    "everything is". An allowlist that starts permissive is a setting nobody
    ever tightens.
    """
    raw = _cfg("path_allowlist", [])
    out = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        try:
            out.append(os.path.abspath(os.path.expanduser(str(item))))
        except Exception:
            continue
    return out


def _inside_allowlist(path: str, allow: Optional[list[str]] = None) -> bool:
    """True only if the resolved path sits under a declared prefix.

    Compared component-wise, not with startswith: "/home/me/docs" must not
    make "/home/me/docs-old" allowed. Anything that cannot be resolved - a
    variable, a substitution - is not inside anything.
    """
    allow = _allowlist() if allow is None else allow
    if not allow or not path:
        return False
    try:
        p = os.path.abspath(os.path.expanduser(path))
    except Exception:
        return False
    for root in allow:
        if p == root or p.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def _count_tree(path: str) -> dict:
    """Files and bytes under a path, bounded.

    Symlinks are never followed. Two reasons, and the second is the one that
    matters: a loop would hang the card, and `rm -rf somelink` removes the
    link, not the tree behind it - so following it would report a number for
    files that are not going to be deleted, which is worse than reporting
    nothing.
    """
    limit = int(_cfg("max_walk_entries", 20000) or 20000)
    try:
        st = os.lstat(path)
    except OSError:
        return {"exists": False, "files": 0, "bytes": 0, "truncated": False,
                "is_dir": False}
    if stat.S_ISLNK(st.st_mode):
        return {"exists": True, "files": 1, "bytes": st.st_size,
                "truncated": False, "is_dir": False, "symlink": True}
    if not stat.S_ISDIR(st.st_mode):
        return {"exists": True, "files": 1, "bytes": st.st_size,
                "truncated": False, "is_dir": False}
    files = total = 0
    truncated = False
    stack = [path]
    while stack and not truncated:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if files >= limit:
                        truncated = True
                        break
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            files += 1
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return {"exists": True, "files": files, "bytes": total,
            "truncated": truncated, "is_dir": True}


# --------------------------------------------------------------------------
#   Shell: three grammars, one tokeniser per grammar
# --------------------------------------------------------------------------
# Windows makes this three problems, not one. `'C:\My Docs'` is one argument
# in PowerShell and three characters plus two literal apostrophes in cmd.
# `$(date)` is a substitution in sh and in PowerShell and a literal string in
# cmd. A backtick is a substitution in sh and an ESCAPE in PowerShell. There
# is no grammar that is a safe superset, so the pane names which one it
# assumed, and when the caller declines to say, it parses all three and only
# reports a resolved answer if they agree.

GRAMMARS = ("posix", "powershell", "cmd")

# Undecidable, in increasing order of how much it should worry you.
SEV_OK = ""
SEV_UNRESOLVED = "unresolved"     # counted against coverage
SEV_UNDECIDABLE = "undecidable"   # counted, and takes the whole command to the top


@dataclass
class Token:
    text: str                     # after quoting has been handled
    raw: str                      # as written
    quoted: bool = False
    kind: str = "word"            # word | op
    severity: str = SEV_OK
    why: str = ""
    note: str = ""                # e.g. a decoded -EncodedCommand payload

    def as_dict(self) -> dict:
        return asdict(self)


_OPS = (">>", "2>&1", "2>", "&&", "||", ">", "<", "|", ";", "&")


def _read_quoted(s: str, i: int, closer: str) -> tuple[str, int, bool]:
    """Consume up to the closing quote. Returns (body, next index, closed)."""
    out = []
    i += 1
    while i < len(s):
        if s[i] == closer:
            return "".join(out), i + 1, True
        out.append(s[i])
        i += 1
    return "".join(out), i, False


_SUBST_POSIX = re.compile(r"\$\(|`")
_SUBST_PS = re.compile(r"\$\(|@\(")
_VAR_POSIX = re.compile(r"\$\{?\w+\}?|\$[@*#?!$-]")
_VAR_PS = re.compile(r"\$(?:\{[^}]*\}|\w+(?::\w+)?)")
_VAR_CMD = re.compile(r"%[^%\s]+%|![^!\s]+!")


def tokenise(command: str, grammar: str) -> list[Token]:
    """Split a command line into tokens under one declared grammar.

    Deliberately hand-written rather than shlex: shlex.split answers "what are
    the arguments" and silently discards the thing this pane most needs to
    report, which is that it could not tell. `rm -rf $(cat list)` comes back
    from shlex as three tidy arguments with no indication that the third one
    is a program that has not run yet.
    """
    grammar = grammar if grammar in GRAMMARS else "posix"
    toks: list[Token] = []
    buf: list[str] = []
    raw: list[str] = []
    quoted = False
    sev, why = SEV_OK, ""

    def flush():
        nonlocal buf, raw, quoted, sev, why
        if buf or raw:
            toks.append(Token("".join(buf), "".join(raw), quoted, "word", sev, why))
        buf, raw, quoted, sev, why = [], [], False, SEV_OK, ""

    def mark(severity: str, reason: str):
        nonlocal sev, why
        if _sev_rank(severity) > _sev_rank(sev):
            sev, why = severity, reason

    i, n = 0, len(command or "")
    while i < n:
        ch = command[i]

        if ch in " \t\n":
            flush()
            i += 1
            continue

        # Operators, outside any quoting.
        op = next((o for o in _OPS if command.startswith(o, i)), None)
        if op and not (grammar == "cmd" and op in ("<",)):
            flush()
            toks.append(Token(op, op, False, "op"))
            i += len(op)
            continue

        if ch == "'" and grammar in ("posix", "powershell"):
            # Single quotes are literal in both, and are NOT quotes in cmd -
            # a cmd line with 'single quotes' has apostrophes in the argument.
            body, i, closed = _read_quoted(command, i, "'")
            buf.append(body)
            raw.append("'" + body + ("'" if closed else ""))
            quoted = True
            if not closed:
                mark(SEV_UNDECIDABLE, "unterminated single quote")
            continue

        if ch == '"':
            body, j, closed = _read_quoted(command, i, '"')
            buf.append(body)
            raw.append('"' + body + ('"' if closed else ""))
            quoted = True
            if not closed:
                mark(SEV_UNDECIDABLE, "unterminated double quote")
            # Expansion still happens inside double quotes in sh and
            # PowerShell, which is why a quoted argument is not automatically
            # a resolved one.
            if grammar == "posix" and _SUBST_POSIX.search(body):
                mark(SEV_UNDECIDABLE, "command substitution inside quotes")
            elif grammar == "powershell" and _SUBST_PS.search(body):
                mark(SEV_UNDECIDABLE, "subexpression inside quotes")
            elif grammar == "posix" and _VAR_POSIX.search(body):
                mark(SEV_UNRESOLVED, "variable inside quotes")
            elif grammar == "powershell" and _VAR_PS.search(body):
                mark(SEV_UNRESOLVED, "variable inside quotes")
            elif grammar == "cmd" and _VAR_CMD.search(body):
                mark(SEV_UNRESOLVED, "variable inside quotes")
            i = j
            continue

        if grammar == "powershell" and ch == "`":
            # PowerShell's backtick is the escape character, not a
            # substitution. Treating it as one - the reflex from sh - would
            # put half of every legitimate PowerShell line in the unknown
            # bucket and train the owner to ignore the bucket.
            if i + 1 < n:
                buf.append(command[i + 1])
                raw.append(command[i:i + 2])
                i += 2
            else:
                i += 1
            continue

        if grammar in ("posix", "cmd") and ch == "`":
            body, j, closed = _read_quoted(command, i, "`")
            buf.append(body)
            raw.append("`" + body + ("`" if closed else ""))
            mark(SEV_UNDECIDABLE, "backtick command substitution")
            i = j
            continue

        if grammar == "posix" and ch == "\\" and i + 1 < n:
            buf.append(command[i + 1])
            raw.append(command[i:i + 2])
            i += 2
            continue

        if grammar == "cmd" and ch == "^" and i + 1 < n:
            buf.append(command[i + 1])
            raw.append(command[i:i + 2])
            i += 2
            continue

        if ch == "$" and grammar in ("posix", "powershell"):
            if command.startswith("$(", i):
                depth, j = 0, i + 1
                while j < n:
                    if command[j] == "(":
                        depth += 1
                    elif command[j] == ")":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                chunk = command[i:j]
                buf.append(chunk)
                raw.append(chunk)
                mark(SEV_UNDECIDABLE, "command substitution")
                i = j
                continue
            pat = _VAR_POSIX if grammar == "posix" else _VAR_PS
            m = pat.match(command, i)
            if m:
                buf.append(m.group(0))
                raw.append(m.group(0))
                mark(SEV_UNRESOLVED, "unresolved variable")
                i = m.end()
                continue

        if grammar == "cmd":
            m = _VAR_CMD.match(command, i)
            if m:
                buf.append(m.group(0))
                raw.append(m.group(0))
                mark(SEV_UNRESOLVED, "unresolved variable")
                i = m.end()
                continue

        buf.append(ch)
        raw.append(ch)
        i += 1

    flush()
    return toks


def _sev_rank(s: str) -> int:
    return {SEV_OK: 0, SEV_UNRESOLVED: 1, SEV_UNDECIDABLE: 2}.get(s, 0)


# Programs that turn their standard input into more program. A pipe into one
# of these means the command on the left decides what the command on the
# right does, and nothing on this pane can tell you what that will be.
_INTERPRETERS = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "ash", "busybox",
    "python", "python2", "python3", "perl", "ruby", "node", "nodejs", "php",
    "lua", "rscript", "osascript", "wscript", "cscript", "deno", "bun",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe",
    "iex", "invoke-expression", "eval", "source", "xargs", "env",
})

# Programs whose whole purpose is to move bytes between this machine and
# another one. Presence is a FACT on the pane, not a verdict.
_NETWORK_PROGS = frozenset({
    "curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod", "irm",
    "start-bitstransfer", "bitsadmin", "scp", "sftp", "ftp", "tftp", "rsync",
    "nc", "ncat", "netcat", "telnet", "ssh", "rclone", "aria2c", "httpie",
    "http", "certutil", "nslookup", "dig",
})

_URL = re.compile(r"\b(?:https?|ftps?|sftp|scp|ssh)://[^\s'\"<>|]+", re.I)
_ENCODED_FLAG = re.compile(r"^-(?:e|ec|enc|encoded|encodedcommand)$", re.I)


def _basename(prog: str) -> str:
    p = (prog or "").replace("\\", "/").rsplit("/", 1)[-1]
    return p.lower()


# --------------------------------------------------------------------------
#   The rule table: a BOUNDED list of destructive verbs
# --------------------------------------------------------------------------
# Bounded on purpose, and its boundary is published rather than hidden. A
# command that matches nothing here is reported as "not in the rule table",
# never as "safe" - the table is a list of things we can name, not a list of
# everything that can hurt you. The pane says which of those two it is.

@dataclass(frozen=True)
class Rule:
    code: str
    verb: str            # line 1 of the phone card
    label: str           # line 2
    progs: tuple         # empty means "match against the whole command"
    needs: Optional[str] = None    # regex over the segment's arguments
    tier: str = "ask"
    reach: str = REACH_MACHINE
    counts_paths: bool = True
    prefix: bool = False           # match progs as a prefix (mkfs.ext4)


_RULES: tuple[Rule, ...] = (
    Rule("rm_recursive", "Delete", "recursive delete", ("rm",),
         r"(?:^|\s)-[a-zA-Z]*r[a-zA-Z]*(?:\s|$)", "ask"),
    Rule("rm", "Delete", "delete", ("rm", "unlink"), None, "ask"),
    Rule("remove_item_recursive", "Delete", "recursive delete",
         ("remove-item", "ri", "rmdir", "rd"), r"-recurse\b", "ask"),
    Rule("remove_item", "Delete", "delete",
         ("remove-item", "ri", "remove-itemproperty", "clear-content"), None, "ask"),
    Rule("del_recursive", "Delete", "recursive delete",
         ("del", "erase", "rd", "rmdir"), r"(?:^|\s)/s\b", "ask"),
    Rule("del", "Delete", "delete", ("del", "erase", "rd", "rmdir"), None, "ask"),
    Rule("shred", "Overwrite", "unrecoverable overwrite",
         ("shred", "srm", "sdelete", "wipe"), None, "ask"),
    Rule("cipher_wipe", "Overwrite", "unrecoverable overwrite", ("cipher",),
         r"(?:^|\s)/w\b", "ask"),
    Rule("truncate", "Truncate", "truncate to zero", ("truncate",), None, "ask"),
    Rule("reg_delete", "Delete", "registry delete", ("reg", "reg.exe"),
         r"(?:^|\s)delete\b", "ask", REACH_MACHINE, False),
    Rule("takeown", "Take ownership", "ownership change",
         ("takeown", "icacls", "chown"), None, "ask", REACH_MACHINE, False),
    Rule("format", "Format", "format a volume",
         ("format", "format-volume", "clear-disk", "diskpart", "newfs"),
         None, "never", REACH_MACHINE, False),
    Rule("mkfs", "Format", "make a filesystem", ("mkfs", "mke2fs"),
         None, "never", REACH_MACHINE, False, True),
    Rule("dd", "Write raw blocks", "raw block write", ("dd",),
         None, "never", REACH_MACHINE, False),
    # A force-push rewrites history on a machine that is not this one, and it
    # is the one git verb nobody else can undo for you.
    Rule("git_force_push", "Force-push", "rewrites remote history", ("git",),
         r"\bpush\b[\s\S]*(?:--force\b|--force-with-lease\b|(?<![\w-])-f(?![\w-]))",
         "ask", REACH_OUT, False),
    Rule("git_hard_reset", "Discard", "discards local commits", ("git",),
         r"\breset\b[\s\S]*--hard\b", "ask", REACH_REPO, False),
    Rule("git_clean", "Delete", "deletes untracked files", ("git",),
         r"\bclean\b[\s\S]*-[a-zA-Z]*f", "ask", REACH_REPO, False),
    # SQL arrives as an argument to a dozen different clients, so this rule
    # matches the statement wherever it appears. Reach is "leaves the machine"
    # because a connection string in another argument decides whether the
    # database is local, and guessing outward is the safe way to be wrong.
    Rule("sql_drop", "Drop", "drops a table or database", (),
         r"\bdrop\s+(?:table|database|schema)\b", "ask", REACH_OUT, False),
    Rule("sql_truncate", "Truncate", "empties a table", (),
         r"\btruncate\s+table\b", "ask", REACH_OUT, False),
    Rule("shutdown", "Shut down", "stops this machine",
         ("shutdown", "poweroff", "halt", "reboot", "init",
          "stop-computer", "restart-computer"),
         None, "ask", REACH_MACHINE, False),
    Rule("kill", "Terminate", "kills processes",
         ("killall", "pkill", "taskkill", "stop-process"),
         None, "ask", REACH_MACHINE, False),
)


def _rule_for(prog: str, argtext: str, whole: str) -> Optional[Rule]:
    """First matching rule, in table order. Table order is strict-first."""
    b = _basename(prog)
    for r in _RULES:
        if not r.progs:
            if r.needs and re.search(r.needs, whole, re.I):
                return r
            continue
        hit = any(b.startswith(p) for p in r.progs) if r.prefix else (b in r.progs)
        if not hit:
            continue
        if r.needs and not re.search(r.needs, argtext, re.I):
            continue
        return r
    return None


# --------------------------------------------------------------------------
#   Reading a tokenised command
# --------------------------------------------------------------------------

def _is_flag(text: str, grammar: str) -> bool:
    if not text:
        return False
    if grammar == "cmd":
        # cmd switches are /s /q /f - short. A token like /home/me/x is a
        # POSIX path that someone pasted into a cmd line, not a switch.
        return bool(re.match(r"^/[A-Za-z?]{1,3}(?::.*)?$", text))
    return text.startswith("-") and text != "-"


_PATHISH_EXT = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _looks_like_path(text: str, grammar: str) -> bool:
    if not text or _is_flag(text, grammar):
        return False
    if text.startswith(("/", "./", "../", "~/", "~\\", ".\\", "..\\", "\\\\")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return True
    if "\\" in text or "/" in text:
        return True
    if text in (".", "..", "~"):
        return True
    if _PATHISH_EXT.search(text):
        return True
    try:
        return os.path.exists(text)
    except (OSError, ValueError):
        return False


def _has_unresolved(text: str, grammar: str) -> bool:
    if grammar == "cmd":
        return bool(_VAR_CMD.search(text))
    if grammar == "powershell":
        return bool(_VAR_PS.search(text) or _SUBST_PS.search(text))
    return bool(_VAR_POSIX.search(text) or _SUBST_POSIX.search(text))


@dataclass
class Segment:
    program: str
    args: list
    tokens: list


def _segments(tokens: list) -> list:
    """Split on the operators that start a new command."""
    breaks = {"|", ";", "&&", "||", "&"}
    out, cur = [], []
    for t in tokens:
        if t.kind == "op" and t.text in breaks:
            out.append(cur)
            cur = []
        elif t.kind == "op":
            continue                     # a redirect belongs to the segment
        else:
            cur.append(t)
    out.append(cur)
    segs = []
    for words in out:
        if not words:
            segs.append(Segment("", [], []))
            continue
        segs.append(Segment(words[0].text, [w.text for w in words[1:]], words))
    return segs


def _analyse(command: str, grammar: str) -> dict:
    """One grammar's reading of one command line. No judgement, just facts."""
    toks = tokenise(command, grammar)
    words = [t for t in toks if t.kind == "word"]
    ops = [t.text for t in toks if t.kind == "op"]
    segs = _segments(toks)
    allow = _allowlist()

    unknown: list[dict] = []

    def add_unknown(severity: str, why: str, what: str, note: str = ""):
        unknown.append({"severity": severity, "why": why,
                        "token": what[:200], "note": note[:400]})

    # 1. Whatever the tokeniser could not settle.
    for t in words:
        if t.severity:
            add_unknown(t.severity, t.why, t.raw, t.note)

    # 2. A pipe whose right-hand side is an interpreter. The left-hand side
    #    then chooses the program, and no amount of reading this line tells
    #    you what it chose.
    for idx, t in enumerate(toks):
        if t.kind == "op" and t.text == "|":
            nxt = next((x for x in toks[idx + 1:] if x.kind == "word"), None)
            if nxt and _basename(nxt.text) in _INTERPRETERS:
                add_unknown(SEV_UNDECIDABLE, "pipe into an interpreter",
                            f"| {nxt.text}")

    # 3. powershell -EncodedCommand. The payload is decoded and shown, because
    #    a person should see it - but the classification stays at the top
    #    tier. Decoding is easy; claiming to have ANALYSED the result would be
    #    the false confidence this module exists to prevent, since what comes
    #    out is another command in another grammar, possibly with another
    #    -EncodedCommand inside it.
    for seg in segs:
        if _basename(seg.program) not in ("powershell", "powershell.exe",
                                          "pwsh", "pwsh.exe"):
            continue
        for j, a in enumerate(seg.args):
            if _ENCODED_FLAG.match(a) and j + 1 < len(seg.args):
                add_unknown(SEV_UNDECIDABLE, "encoded command payload",
                            f"{a} {seg.args[j + 1][:60]}",
                            _decode_b64_utf16(seg.args[j + 1]))

    # 4. A script fetched now and run now.
    net_progs = sorted({_basename(s.program) for s in segs
                        if _basename(s.program) in _NETWORK_PROGS})
    urls = _URL.findall(command or "")
    if net_progs and any(t.kind == "op" and t.text == "|" for t in toks):
        add_unknown(SEV_UNDECIDABLE, "a fetched script is run in place",
                    " ".join(net_progs))

    # 5. Paths, and whether a variable is standing where one should be.
    paths: list[dict] = []
    for seg in segs:
        rule = _rule_for(seg.program, " ".join(seg.args), command or "")
        if _has_unresolved(seg.program, grammar):
            add_unknown(SEV_UNDECIDABLE, "the program name is not resolved",
                        seg.program)
        for a in seg.args:
            if _is_flag(a, grammar):
                continue
            unresolved = _has_unresolved(a, grammar)
            pathish = _looks_like_path(a, grammar)
            if unresolved and (pathish or (rule and rule.counts_paths)):
                add_unknown(SEV_UNDECIDABLE,
                            "a variable stands where a path should be", a)
                paths.append({"text": a, "resolved": False, "exists": False,
                              "allowlisted": False, "files": 0, "bytes": 0})
                continue
            if not pathish:
                continue
            info = _count_tree(os.path.expanduser(a))
            paths.append({"text": a,
                          "resolved": True,
                          "abs": os.path.abspath(os.path.expanduser(a)),
                          "exists": info["exists"],
                          "is_dir": info.get("is_dir", False),
                          "allowlisted": _inside_allowlist(a, allow),
                          "files": info["files"], "bytes": info["bytes"],
                          "truncated": info["truncated"]})

    matched = []
    for seg in segs:
        r = _rule_for(seg.program, " ".join(seg.args), command or "")
        if r and r.code not in [m["code"] for m in matched]:
            matched.append({"code": r.code, "label": r.label, "verb": r.verb,
                            "tier": r.tier, "reach": r.reach,
                            "program": seg.program, "counts_paths": r.counts_paths})

    return {
        "grammar": grammar,
        "tokens": [t.as_dict() for t in toks],
        "words": [t.text for t in words],
        "program": segs[0].program if segs else "",
        "argv": [t.text for t in words[1:]] if words else [],
        "programs": [s.program for s in segs if s.program],
        "segments": [{"program": s.program, "args": s.args} for s in segs
                     if s.program],
        "operators": ops,
        "redirects": [o for o in ops if o in (">", ">>", "<", "2>", "2>&1")],
        "pipes": ops.count("|"),
        "network": {"programs": net_progs, "urls": urls[:10]},
        "paths": paths,
        "rules": matched,
        "unknown": unknown,
        "word_count": len(words),
    }


def _decode_b64_utf16(payload: str) -> str:
    """Show the owner what an -EncodedCommand actually spells.

    Best effort and clearly labelled: a failure returns an empty string rather
    than a guess, and a success does not upgrade the classification.
    """
    try:
        raw = base64.b64decode(payload + "=" * (-len(payload) % 4), validate=True)
    except (binascii.Error, ValueError):
        return ""
    for enc in ("utf-16-le", "utf-8"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if text.isprintable() or "\n" in text:
            return "decoded: " + " ".join(text.split())[:300]
    return ""


# --------------------------------------------------------------------------
#   Shell preview
# --------------------------------------------------------------------------

def shell_preview(command: str, grammar: str = "") -> Preview:
    """The fact pane for a shell command, with declared coverage.

    `grammar` must be one of posix / powershell / cmd. Passing nothing is
    allowed and is handled honestly rather than guessed: the line is parsed
    under all three, and if the three readings agree on the argument list and
    the classification then the ambiguity did not matter and nothing is
    reported. If they disagree, that disagreement IS the finding - one of
    those readings is what the machine will do and this pane cannot say which.
    """
    command = command if isinstance(command, str) else str(command or "")
    declared = grammar in GRAMMARS
    if declared:
        a = _analyse(command, grammar)
        disagreement = None
    else:
        readings = {g: _analyse(command, g) for g in GRAMMARS}
        signatures = {g: (tuple(r["words"]), tuple(sorted(
            m["code"] for m in r["rules"]))) for g, r in readings.items()}
        agree = len(set(signatures.values())) == 1
        # Take the reading with the most unknowns so an undeclared grammar can
        # only ever make the pane more cautious, never less.
        a = max(readings.values(), key=lambda r: (len(r["unknown"]),
                                                  len(r["paths"])))
        disagreement = None if agree else {
            g: list(r["words"]) for g, r in readings.items()}
        if not agree:
            a = dict(a)
            a["unknown"] = a["unknown"] + [{
                "severity": SEV_UNDECIDABLE,
                "why": "no grammar was declared and the three disagree",
                "token": command[:200],
                "note": "; ".join(f"{g}: {len(w)} args" for g, w in
                                  ((g, r["words"]) for g, r in readings.items()))}]

    unknown = a["unknown"]
    undecidable = [u for u in unknown if u["severity"] == SEV_UNDECIDABLE]
    unresolved_words = len({u["token"] for u in unknown})
    total = max(a["word_count"], 1 if command.strip() else 0)
    coverage = Coverage(resolved=max(0, total - min(unresolved_words, total)),
                        total=total, unit="tokens", unknown=unknown)

    # Classification. Order matters: an undecidable command is not rescued by
    # also matching a mild rule, and a rule match is not softened by the rest
    # of the line looking ordinary.
    rules = a["rules"]
    if undecidable:
        tier = _unknown_tier(undecidable)
        label = "not fully parsed"
        verb = "Run"
    elif rules:
        tier = _worst(*[r["tier"] for r in rules])
        label = ", ".join(dict.fromkeys(r["label"] for r in rules))
        verb = rules[0]["verb"]
    else:
        # The bounded table said nothing. That is a statement about the table.
        tier = "ask"
        label = "not in the rule table"
        verb = "Run"

    if a["network"]["programs"] or a["network"]["urls"]:
        tier = _worst(tier, "ask")
        reach = REACH_OUT
    elif rules:
        reach = _reach_worst([r["reach"] for r in rules])
    else:
        reach = REACH_MACHINE

    # The number. For a deletion it is what would stop existing; otherwise it
    # is how much of the line we could actually place.
    counted = [p for p in a["paths"] if p.get("resolved") and p.get("exists")]
    files = sum(p["files"] for p in counted)
    size = sum(p["bytes"] for p in counted)
    destructive_paths = rules and any(r["counts_paths"] for r in rules) and a["paths"]
    if destructive_paths and counted:
        number = f"{_plural(files, 'file')}, {_bytes(size)}"
        if any(p.get("truncated") for p in counted):
            number = "at least " + number
    elif destructive_paths and not undecidable:
        # The rule fired and the path resolved, and there is nothing there.
        # Worth saying out loud: it is also what a typo'd path looks like.
        number = "nothing at that path"
    elif undecidable:
        number = f"{len(undecidable)} undecidable, {coverage.text}"
    else:
        number = coverage.text

    target = ""
    if a["paths"]:
        target = a["paths"][0]["text"]
    elif a["program"]:
        target = a["program"]

    facts = {
        "command": command,
        "grammar": a["grammar"],
        "grammar_declared": declared,
        "grammar_disagreement": disagreement,
        "program": a["program"],
        "argv": a["argv"],
        "segments": a["segments"],
        "operators": a["operators"],
        "redirects": a["redirects"],
        "pipes": a["pipes"],
        "network": a["network"],
        "paths": a["paths"],
        "outside_allowlist": [p["text"] for p in a["paths"]
                              if not p.get("allowlisted")],
        "rules": rules,
        "files": files,
        "bytes": size,
    }
    return Preview(action="run_shell_on_host", kind="shell", supported=True,
                   coverage=coverage, verb=verb, target=target, label=label,
                   number=number, reach=reach, tier_hint=tier, facts=facts,
                   unknown=unknown)


def _reach_worst(reaches: list) -> str:
    order = {REACH_REPO: 0, REACH_MACHINE: 1, REACH_OUT: 2}
    return max(reaches or [REACH_MACHINE], key=lambda r: order.get(r, 1))


# --------------------------------------------------------------------------
#   File writes: a diff against what is actually on disk
# --------------------------------------------------------------------------
# Against DISK, not against whatever the caller believes the previous content
# was. The two differ exactly when something else has changed the file since,
# which is the case where a diff matters most and the case a cached "before"
# would render as no change at all.

_BINARY_SNIFF = 8192


def _read_disk(path: Path) -> tuple[Optional[bytes], bool]:
    try:
        return path.read_bytes(), True
    except FileNotFoundError:
        return None, False
    except OSError:
        return None, True


def _is_binary(data: Optional[bytes]) -> bool:
    if not data:
        return False
    head = data[:_BINARY_SNIFF]
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def diff_preview(path, new_content=None, *, delete: bool = False) -> Preview:
    """One file: a unified diff against disk, or an honest non-diff.

    Four renderings, because three of them are not diffs and pretending
    otherwise is how a preview lies:
      - the file does not exist  -> a creation, every line added
      - delete=True              -> a deletion, every line removed
      - either side is binary    -> sizes and hashes, and NO text
      - otherwise                -> a unified diff
    """
    p = Path(os.path.expanduser(str(path)))
    old, existed = _read_disk(p)
    if isinstance(new_content, str):
        new = new_content.encode("utf-8")
    elif isinstance(new_content, (bytes, bytearray)):
        new = bytes(new_content)
    elif new_content is None:
        new = b""
    else:
        new = str(new_content).encode("utf-8")

    if delete:
        mode, new = "delete", b""
    elif not existed:
        mode = "create"
    else:
        mode = "modify"

    old_bytes = old or b""
    binary = _is_binary(old_bytes) or _is_binary(new)
    added = removed = 0
    diff = ""
    truncated = False

    if binary:
        # A binary file rendered as text is a screen of replacement characters
        # that a person will scroll past. Hashes and sizes are less
        # satisfying and are actually true.
        note = "binary file; not rendered as text"
    elif mode == "delete":
        lines = old_bytes.decode("utf-8", "replace").splitlines()
        removed = len(lines)
        note = f"deletes the file ({_plural(removed, 'line')})"
    elif mode == "create":
        lines = new.decode("utf-8", "replace").splitlines()
        added = len(lines)
        note = f"new file ({_plural(added, 'line')})"
    else:
        note = ""

    if not binary:
        old_lines = old_bytes.decode("utf-8", "replace").splitlines()
        new_lines = new.decode("utf-8", "replace").splitlines()
        ctx = int(_cfg("diff_context_lines", 3) or 3)
        raw = "\n".join(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{p} (on disk)" if existed else f"{p} (does not exist)",
            tofile=f"{p} (after)" if mode != "delete" else f"{p} (deleted)",
            lineterm="", n=ctx))
        cap = int(_cfg("max_diff_kb", 200) or 200) * 1024
        truncated = len(raw) > cap
        diff = raw[:cap]
        if mode == "modify":
            for line in raw.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1

    facts = {
        "path": str(p),
        "mode": mode,
        "existed": existed,
        "binary": binary,
        "note": note,
        "old_bytes": len(old_bytes),
        "new_bytes": len(new),
        "old_sha256": _sha(old_bytes) if existed else None,
        "new_sha256": _sha(new) if mode != "delete" else None,
        "lines_added": added,
        "lines_removed": removed,
        "diff": "" if binary else diff,
        "diff_truncated": truncated,
        "in_repo": _repo_root(p) is not None,
        "allowlisted": _inside_allowlist(str(p)),
    }
    verb = {"create": "Create", "delete": "Delete", "modify": "Write"}[mode]
    if binary:
        number = f"{_bytes(len(old_bytes))} -> {_bytes(len(new))}"
        label = "binary file, not shown as text"
    else:
        number = f"+{added} / -{removed} lines, {_bytes(len(new))}"
        label = {"create": "new file", "delete": "deletes the file",
                 "modify": "edits an existing file"}[mode]
    # One file, and the pane resolved it, unless disk refused to answer.
    readable = existed is False or old is not None
    coverage = Coverage(resolved=1 if readable else 0, total=1, unit="files",
                        unknown=[] if readable else [{
                            "severity": SEV_UNDECIDABLE,
                            "why": "the file on disk could not be read, so "
                                   "there is nothing to diff against",
                            "token": str(p), "note": ""}])
    tier = "ask" if readable else _unknown_tier()
    return Preview(action="file_write", kind="diff", supported=True,
                   coverage=coverage, verb=verb, target=str(p), label=label,
                   number=number,
                   reach=REACH_REPO if facts["in_repo"] else REACH_MACHINE,
                   tier_hint=tier, facts=facts, unknown=coverage.unknown)


def diff_set_preview(edits) -> Preview:
    """Several files at once, summarised the way a phone can show it.

    The summary line is files touched, lines added and removed, bytes - one
    number per question a person actually asks before approving a batch.
    """
    edits = list(edits or [])
    parts = []
    for e in edits:
        if isinstance(e, (str, Path)):
            parts.append(diff_preview(e, None))
        else:
            parts.append(diff_preview(e.get("path"), e.get("content"),
                                      delete=bool(e.get("delete"))))
    if len(parts) == 1:
        return parts[0]
    added = sum(p.facts["lines_added"] for p in parts)
    removed = sum(p.facts["lines_removed"] for p in parts)
    size = sum(p.facts["new_bytes"] for p in parts)
    resolved = sum(1 for p in parts if p.coverage.complete)
    unknown = [u for p in parts for u in p.unknown]
    facts = {"files": [p.facts for p in parts],
             "lines_added": added, "lines_removed": removed,
             "new_bytes": size,
             "binary": [p.facts["path"] for p in parts if p.facts["binary"]]}
    return Preview(
        action="file_write", kind="diff", supported=True,
        coverage=Coverage(resolved, len(parts), "files", unknown),
        verb="Write", target=f"{_plural(len(parts), 'file')}",
        label="; ".join(dict.fromkeys(p.label for p in parts)),
        number=f"{_plural(len(parts), 'file')}, +{added} / -{removed} lines, "
               f"{_bytes(size)}",
        reach=_reach_worst([p.reach for p in parts]),
        tier_hint=_worst(*[p.tier_hint for p in parts]),
        facts=facts, unknown=unknown)


def _repo_root(path: Path) -> Optional[Path]:
    """Walk up looking for a .git. Deliberately a filesystem check and not a
    git call: this runs on every diff card, and a subprocess per card is a
    cost that shows up as a slow HUD."""
    try:
        p = path if path.is_dir() else path.parent
        p = p.resolve()
    except OSError:
        return None
    for cand in [p] + list(p.parents):
        if (cand / ".git").exists():
            return cand
    return None


# --------------------------------------------------------------------------
#   Email: what the recipient sees, and how many of them there are
# --------------------------------------------------------------------------

_ADDR = re.compile(r"[^\s,;<>]+@[^\s,;<>]+")
_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def _addresses(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value]
    else:
        items = re.split(r"[,;]", str(value))
    out = []
    for item in items:
        item = item.strip()
        if item:
            out.append(item)
    return out


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = _TAG.sub("", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def email_preview(message: dict) -> Preview:
    """The message as the recipient would see it, plus the counts that decide.

    To, Cc and Bcc are counted SEPARATELY and never summed into one
    "recipients" number. A Bcc of two hundred is the single fact that should
    stop a person, and it is exactly the one that a combined count hides:
    "203 recipients" on a card looks like a mailing list working correctly.
    """
    message = message or {}
    to = _addresses(message.get("to"))
    cc = _addresses(message.get("cc"))
    bcc = _addresses(message.get("bcc"))
    subject = str(message.get("subject") or "")
    body = message.get("body")
    html = message.get("html") or message.get("body_html")
    rendered_from_html = False
    if not body and html:
        body = _html_to_text(str(html))
        rendered_from_html = True
    body = str(body or "")

    links = []
    for href, label in _HREF.findall(str(html or "")):
        visible = _html_to_text(label)
        # A link whose visible text is itself a URL that is not the target is
        # the oldest trick there is, and it is decidable with a string
        # comparison, so it belongs on the deterministic pane.
        mismatch = bool(_URL.match(visible.strip())) and \
            visible.strip().rstrip("/") != href.strip().rstrip("/")
        links.append({"href": href, "text": visible[:120], "mismatch": mismatch})

    invisible = 0
    try:
        import jarvis_content_risk as cr
        n = cr.normalise(body)
        invisible = n.stripped
        body_visible = n.text
    except Exception:
        body_visible = body

    show = int(_cfg("recipients_shown", 5) or 5)
    external = [a for a in to + cc + bcc if _ADDR.search(a)]
    domains = sorted({a.rsplit("@", 1)[-1].strip("<>").lower()
                      for a in external if "@" in a})

    facts = {
        "from": str(message.get("from") or ""),
        "to": to[:show], "to_count": len(to),
        "cc": cc[:show], "cc_count": len(cc),
        "bcc": bcc[:show], "bcc_count": len(bcc),
        "more_to": max(0, len(to) - show),
        "more_cc": max(0, len(cc) - show),
        "more_bcc": max(0, len(bcc) - show),
        "subject": subject,
        "body": body_visible,
        "body_chars": len(body_visible),
        "rendered_from_html": rendered_from_html,
        "invisible_characters": invisible,
        "links": links[:20],
        "link_mismatches": sum(1 for l in links if l["mismatch"]),
        "attachments": [{"name": str(a.get("name", "?")),
                         "bytes": int(a.get("bytes", 0) or 0)}
                        for a in (message.get("attachments") or [])
                        if isinstance(a, dict)],
        "domains": domains,
    }
    malformed = [a for a in to + cc + bcc if not _ADDR.search(a)]
    unknown = [{"severity": SEV_UNRESOLVED,
                "why": "this does not parse as an address",
                "token": a, "note": ""} for a in malformed]
    total = len(to) + len(cc) + len(bcc)
    coverage = Coverage(resolved=total - len(malformed), total=total,
                        unit="recipients", unknown=unknown)
    number = f"{len(to)} To, {len(cc)} Cc, {len(bcc)} Bcc"
    label = "sends mail"
    if len(bcc) > len(to) + len(cc) and bcc:
        label = "mostly Bcc"
    first = (to + cc + bcc + ["nobody"])[0]
    return Preview(action="send_email", kind="email", supported=True,
                   coverage=coverage, verb="Send",
                   target=first if total == 1 else f"{total} recipients",
                   label=label, number=number, reach=REACH_OUT,
                   tier_hint="ask", facts=facts, unknown=unknown)


# --------------------------------------------------------------------------
#   The send-hold, which is the only honest "undo send"
# --------------------------------------------------------------------------
# SMTP has no unsend. Once the message is handed to a server it is gone, and
# every product that offers "recall" either never sent it yet or is asking a
# second server politely. So the undo has to happen BEFORE the handover: the
# message sits here for a few seconds, cancel_hold() throws it away, and only
# what survives the window is ever given to a transport.
#
# The queue is in memory on purpose. A hold that survives this process would
# have to be re-sent by whatever starts next, and "the machine rebooted so
# your mail went out anyway" is the opposite of what the feature promises. In
# memory, a crash means the message is never sent, which is the safe way for
# this to fail.

# The hold queue is the ONLY honest undo for a sent message. SMTP has no
# unsend; what a mail client calls "undo send" is a client-side delay exactly
# like this one. So a message is parked here for a few seconds and the send
# happens when nobody cancelled it.
#
# It lives in SQLite rather than in a dict, for one reason: the process that
# would send the message is not the process the owner is holding. A hold
# created inside OpenJarvis has to be cancellable from the HUD, and therefore
# from the phone - "stop that email" is the whole feature, and an in-memory
# queue makes it reachable only from the process that happens to own it.
#
# A hold that outlives a restart is CANCELLED, never released. The alternative
# reading - "the window passed while we were down, so send it" - means a crash
# or a reboot sends mail the owner was in the middle of stopping. If in doubt,
# the message does not go.
_HOLD_DB = Path(os.environ.get(
    "JARVIS_HOLD_DB", str(Path(os.path.expanduser("~/.openjarvis")) / "holds.db")))
try:
    _HOLD_DB = Path(os.environ.get("JARVIS_HOLD_DB", str(Path(fw.CONFIG_DIR) / "holds.db")))
except Exception:
    pass
_HOLD_LOCK = threading.RLock()
_HOLD_BOOT = uuid.uuid4().hex[:12]      # this process's run; see _hold_conn()
_hold_inited = False


def _hold_conn():
    global _hold_inited
    _HOLD_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_HOLD_DB), timeout=10)
    c.row_factory = sqlite3.Row
    if not _hold_inited:
        with _HOLD_LOCK:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""CREATE TABLE IF NOT EXISTS holds (
                             handle  TEXT PRIMARY KEY,
                             message TEXT NOT NULL,
                             created REAL NOT NULL,
                             due_at  REAL NOT NULL,
                             seconds REAL NOT NULL,
                             boot    TEXT NOT NULL,
                             state   TEXT NOT NULL DEFAULT 'held')""")
            # Anything held by a run that is no longer this one was in flight
            # when something stopped. Cancel it. The owner can send it again
            # deliberately; what must not happen is mail leaving the machine
            # because a process died during the window they were using to stop
            # it.
            c.execute("UPDATE holds SET state='cancelled_by_restart' "
                      "WHERE state='held' AND boot <> ?", (_HOLD_BOOT,))
            c.commit()
            _hold_inited = True
    return c


def hold(message: dict, seconds: Optional[float] = None) -> str:
    """Park a message for `seconds`. Returns a handle for cancel_hold()."""
    if seconds is None:
        seconds = float(_cfg("default_hold_seconds", 30) or 30)
    seconds = max(0.0, float(seconds))
    handle = "hold-" + uuid.uuid4().hex[:12]
    now = time.time()
    with closing(_hold_conn()) as c:
        c.execute("INSERT INTO holds (handle,message,created,due_at,seconds,boot,state)"
                  " VALUES (?,?,?,?,?,?, 'held')",
                  (handle, json.dumps(message, default=str), now,
                   now + seconds, seconds, _HOLD_BOOT))
        c.commit()
    _audit("preview.held", {"handle": handle, "seconds": seconds,
                            "to_count": len(_addresses((message or {}).get("to"))),
                            "bcc_count": len(_addresses((message or {}).get("bcc")))})
    return handle


def cancel_hold(handle: str) -> bool:
    """True if the message was still here and is now gone.

    False means it was already released by due() - the caller has it and this
    module cannot reach into an SMTP session. Saying True there would be the
    lie the whole feature exists to avoid.
    """
    with closing(_hold_conn()) as c:
        cur = c.execute("UPDATE holds SET state='cancelled' "
                        "WHERE handle=? AND state='held'", (str(handle),))
        c.commit()
        gone = cur.rowcount > 0
    if gone:
        _audit("preview.hold_cancelled", {"handle": handle})
    return gone


def due(now: Optional[float] = None) -> list:
    """Holds whose window has passed, removed from the queue as they are
    returned. A hold handed out twice is a message sent twice, so this takes
    rather than peeks; use holds() to look without taking.

    The take is a single UPDATE guarded on state, so two processes ticking at
    the same moment cannot both be handed the same message.
    """
    now = time.time() if now is None else now
    ready = []
    with closing(_hold_conn()) as c:
        rows = c.execute("SELECT * FROM holds WHERE state='held' AND due_at<=?"
                         " ORDER BY due_at", (now,)).fetchall()
        for r in rows:
            cur = c.execute("UPDATE holds SET state='released' "
                            "WHERE handle=? AND state='held'", (r["handle"],))
            if cur.rowcount:
                ready.append(_hold_row(r))
        c.commit()
    for h in ready:
        _audit("preview.hold_released", {"handle": h["handle"]})
    return ready


def _hold_row(r) -> dict:
    try:
        msg = json.loads(r["message"])
    except Exception:
        msg = {}
    return {"handle": r["handle"], "message": msg, "created": r["created"],
            "due_at": r["due_at"], "seconds": r["seconds"]}


def holds() -> list:
    """Everything still waiting, oldest first. Read-only."""
    with closing(_hold_conn()) as c:
        rows = c.execute("SELECT * FROM holds WHERE state='held'"
                         " ORDER BY due_at").fetchall()
    return [_hold_row(r) for r in rows]


def sweep_holds(older_than_hours: float = 24.0) -> int:
    """Drop decided rows once they can tell nobody anything useful. Held rows
    are never swept: a hold with no window left is cancelled, not forgotten."""
    cutoff = time.time() - max(0.0, older_than_hours) * 3600.0
    with closing(_hold_conn()) as c:
        cur = c.execute("DELETE FROM holds WHERE state<>'held' AND created<?",
                        (cutoff,))
        c.commit()
        return cur.rowcount


# --------------------------------------------------------------------------
#   Commit before acting
# --------------------------------------------------------------------------
# "You can always undo it" is a claim, and a claim is not a backup. If the
# path is in a git repository there is a cheap way to make it true, so this
# makes it true and reports the sha; if it cannot, it says so plainly instead
# of letting the caller keep the comfortable assumption.

_SECRET_NAMES = (
    re.compile(r"(?:^|/)\.env(?:\.[\w.-]+)?$", re.I),
    re.compile(r"(?:^|/)id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?$", re.I),
    re.compile(r"(?:^|/)\.ssh/", re.I),
    re.compile(r"(?:^|/)\.aws/credentials$", re.I),
    re.compile(r"(?:^|/)\.?netrc$", re.I),
    re.compile(r"(?:^|/)\.npmrc$|(?:^|/)\.pypirc$", re.I),
    re.compile(r"\.(?:pem|pfx|p12|jks|keystore|key|kdbx|ppk)$", re.I),
    re.compile(r"(?:^|/)(?:secrets?|credentials?)\.(?:ya?ml|json|toml|ini)$", re.I),
    re.compile(r"(?:^|/)service[-_]account.*\.json$", re.I),
)

_SECRET_CONTENT = (
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("assigned secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*"
        r"[\"']?[A-Za-z0-9/+_\-]{16,}[\"']?")),
)


def scan_for_secrets(paths, root: Optional[Path] = None) -> list:
    """Credential-shaped files and credential-shaped strings.

    Name and content both, because they miss different things: a file called
    .env is a secret whatever is in it, and a file called config.py is a
    secret when there is an AKIA in it.
    """
    cap = int(_cfg("secret_scan_kb", 64) or 64) * 1024
    hits = []
    for rel in paths:
        rel = str(rel)
        norm = rel.replace("\\", "/")
        for pat in _SECRET_NAMES:
            if pat.search(norm):
                hits.append({"path": rel, "why": "the name is credential-shaped",
                             "match": pat.pattern[:60]})
                break
        else:
            full = Path(root or ".") / rel
            try:
                if full.is_symlink() or not full.is_file():
                    continue
                if full.stat().st_size > cap * 8:
                    continue
                data = full.read_bytes()[:cap]
            except OSError:
                continue
            if _is_binary(data):
                continue
            text = data.decode("utf-8", "replace")
            for why, pat in _SECRET_CONTENT:
                if pat.search(text):
                    hits.append({"path": rel, "why": why, "match": ""})
                    break
    return hits


def _git(args: list, cwd, timeout: float = 20.0):
    """Run git with an explicit argv. Never shell=True - this module exists to
    stop a string being handed to a shell, so handing one to a shell here
    would be funny in the wrong way."""
    return subprocess.run(["git"] + list(args), cwd=str(cwd), timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, check=False)


def git_available() -> bool:
    try:
        return _git(["--version"], cwd=".").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def commit_before(path, why: str = "") -> dict:
    """Make "you can revert this" a fact before the action runs.

    Returns a dict with `ok`, a `status` word, a human `message`, and
    `restore_point` when there is one. Two refusals, both of which came out of
    review and both of which are about not doing someone a favour they did not
    ask for:

      - a DIRTY tree is refused. Sweeping unrelated work-in-progress into a
        commit to make room for our own change is not a safety feature, it is
        a second uninvited edit, and the person now has to unpick a commit
        they never made.
      - a commit that would STAGE A SECRET is refused. The obvious
        implementation is `git add -A`, and in a repo with an untracked .env
        and a remote, the obvious implementation is an exfiltration waiting
        for the next push. Refusing is right even though it blocks the
        snapshot: a missing snapshot is recoverable, a published key is not.

    A clean tree needs no snapshot of working state - HEAD already is one -
    so it gets a named empty marker commit instead, which is the difference
    between "there is a sha somewhere before this" and a sha you can read off
    the card.
    """
    p = Path(os.path.expanduser(str(path)))
    detail = {"path": str(p), "why": (why or "")[:120]}
    try:
        if not git_available():
            return {"ok": False, "status": "git_not_available",
                    "message": "git is not on PATH, so no commit was made and "
                               "nothing here can promise this is revertible",
                    "restore_point": None, **detail}
    except Exception as exc:
        return {"ok": False, "status": "git_not_available",
                "message": f"git could not be run ({exc})",
                "restore_point": None, **detail}

    root = _repo_root(p)
    if root is None:
        return {"ok": False, "status": "not_a_repo",
                "message": f"{p} is not inside a git repository, so there is "
                           f"no commit to fall back to",
                "restore_point": None, **detail}
    detail["repo"] = str(root)

    st = _git(["status", "--porcelain", "--untracked-files=all"], cwd=root)
    if st.returncode != 0:
        return {"ok": False, "status": "git_failed",
                "message": f"git status failed: {st.stderr.strip()[:200]}",
                "restore_point": None, **detail}

    changed = []
    for line in st.stdout.splitlines():
        if len(line) > 3:
            name = line[3:].strip().strip('"')
            # Renames arrive as "old -> new"; the new name is the staged one.
            if " -> " in name:
                name = name.split(" -> ", 1)[1]
            changed.append(name)

    # The secret check runs FIRST and is reported first even though a dirty
    # tree would refuse anyway. The two refusals mean different things to the
    # person reading them: one is "commit your work", the other is "there is a
    # credential in this directory and something was about to commit it".
    secrets = scan_for_secrets(changed, root)
    if secrets:
        _audit("preview.commit_refused", {"why": "secret", "repo": str(root),
                                          "n": len(secrets)})
        names = ", ".join(sorted({s["path"] for s in secrets})[:5])
        return {"ok": False, "status": "would_stage_secret",
                "message": f"refusing to commit: {names} looks like a "
                           f"credential, and this repository may have a remote",
                "secrets": secrets, "restore_point": None,
                "dirty": changed, **detail}

    if changed:
        _audit("preview.commit_refused", {"why": "dirty", "repo": str(root),
                                          "n": len(changed)})
        return {"ok": False, "status": "dirty_tree",
                "message": f"refusing to commit: {_plural(len(changed), 'file')} "
                           f"already changed here, and committing someone "
                           f"else's work-in-progress is not a safety feature",
                "dirty": changed[:50], "restore_point": None, **detail}

    head = _git(["rev-parse", "HEAD"], cwd=root)
    if head.returncode != 0:
        return {"ok": False, "status": "no_commits",
                "message": "this repository has no commits yet, so there is "
                           "nothing to revert to",
                "restore_point": None, **detail}
    head_sha = head.stdout.strip()

    if not bool(_cfg("marker_commits", True)):
        return {"ok": True, "status": "head_is_the_restore_point",
                "message": "the tree is clean, so HEAD is already the point "
                           "to come back to",
                "restore_point": head_sha, **detail}

    msg = f"jarvis: snapshot before {why or 'an approved action'}"
    made = _git(["commit", "--allow-empty", "-m", msg[:200]], cwd=root)
    if made.returncode != 0:
        # Usually an unset user.email. The restore point still exists; only
        # the label failed, and saying "ok, here is HEAD" is true while
        # "failed" would push the caller into doing nothing at all.
        return {"ok": True, "status": "head_only",
                "message": f"could not write a marker commit "
                           f"({made.stderr.strip()[:120]}), but the tree is "
                           f"clean so HEAD is the point to come back to",
                "restore_point": head_sha, **detail}
    new = _git(["rev-parse", "HEAD"], cwd=root)
    sha = new.stdout.strip() if new.returncode == 0 else head_sha
    _audit("preview.committed", {"repo": str(root), "sha": sha[:12]})
    return {"ok": True, "status": "committed",
            "message": f"marker commit {sha[:12]} written; "
                       f"git reset --hard {sha[:12]} undoes what follows",
            "restore_point": sha, "previous": head_sha, **detail}


def git_preview(path, why: str = "") -> Preview:
    """A dry pane for commit_before: what the snapshot would find."""
    p = Path(os.path.expanduser(str(path)))
    root = _repo_root(p)
    if root is None:
        return Preview("git_commit", "git", True,
                       Coverage(0, 1, "repositories", [{
                           "severity": SEV_UNRESOLVED,
                           "why": "not inside a git repository",
                           "token": str(p), "note": ""}]),
                       "Commit", str(p), "no repository here",
                       "nothing to revert to", REACH_MACHINE, "ask",
                       {"path": str(p), "repo": None})
    out = commit_before(p, why)
    return Preview("git_commit", "git", True,
                   Coverage(1, 1, "repositories", []),
                   "Commit", str(root), out["status"].replace("_", " "),
                   (out.get("restore_point") or "no restore point")[:12],
                   REACH_REPO, "auto" if out["ok"] else "ask", out)


# --------------------------------------------------------------------------
#   The single entry point
# --------------------------------------------------------------------------

_RENDERERS = {
    "run_shell_on_host": "shell", "shell": "shell", "shell_exec": "shell",
    "docker_shell_exec": "shell", "code_interpreter": "shell", "repl": "shell",
    "file_write": "diff", "write_file": "diff", "apply_patch": "diff",
    "delete_file": "diff", "edit_file": "diff",
    "send_email": "email", "email": "email", "draft_email": "email",
    "channel_send": "email",
    "git_commit": "git", "commit_before": "git",
}


def preview(action: str, detail: Optional[dict] = None) -> Preview:
    """Dispatch to a renderer and always come back with the same shape.

    Including for an action with no renderer. Returning an empty preview there
    would render as a card with nothing alarming on it, which reads as "we
    checked and it is fine" - so an unsupported action says so, reports zero
    coverage, and carries the top tier.
    """
    action = str(action or "")
    detail = detail or {}
    kind = _RENDERERS.get(action)
    if kind is None:
        return _no_renderer(action, "no renderer for this action")
    try:
        if kind == "shell":
            cmd = detail.get("command") or detail.get("cmd") or detail.get("args")
            if isinstance(cmd, (list, tuple)):
                # Already an argv: there is no quoting left to get wrong, so
                # it is rendered under POSIX rules purely to reuse the rule
                # table, and joined without re-quoting.
                cmd = " ".join(str(c) for c in cmd)
            p = shell_preview(str(cmd or ""),
                              str(detail.get("grammar") or
                                  _cfg("default_grammar", "")))
            p.action = action
            return p
        if kind == "diff":
            if detail.get("files"):
                p = diff_set_preview(detail["files"])
            else:
                p = diff_preview(detail.get("path", ""),
                                 detail.get("content"),
                                 delete=bool(detail.get("delete")) or
                                 action == "delete_file")
            p.action = action
            return p
        if kind == "email":
            p = email_preview(detail)
            p.action = action
            if action == "draft_email":
                p.reach = REACH_MACHINE      # a draft is not a sent message
                p.tier_hint = "auto"
            return p
        if kind == "git":
            p = git_preview(detail.get("path", "."), str(detail.get("why", "")))
            p.action = action
            return p
    except Exception as exc:
        _audit("preview.failed", {"action": action, "error": str(exc)[:200]})
        return _no_renderer(action, f"the preview itself failed ({exc})")
    return _no_renderer(action, "no renderer for this action")


def _no_renderer(action: str, why: str) -> Preview:
    return Preview(
        action=action, kind="none", supported=False,
        coverage=Coverage(0, 1, "actions", [{"severity": SEV_UNDECIDABLE,
                                             "why": why, "token": action,
                                             "note": ""}]),
        verb="Run", target=action or "an unnamed action",
        label="nothing here was checked", number="resolved 0 of 1 actions",
        reach=REACH_OUT, tier_hint=_unknown_tier(),
        facts={"why": why},
        unknown=[{"severity": SEV_UNDECIDABLE, "why": why,
                  "token": action, "note": ""}],
        error=why)


# --------------------------------------------------------------------------
#   Three lines for a phone
# --------------------------------------------------------------------------

def card(p) -> dict:
    """Exactly three short lines, plus everything else behind `details`.

    Three because the screen is six inches and the person is walking. Line 1
    is what and to what, line 2 is the classification and the number that
    makes it real, line 3 is how far it reaches. Anything that does not fit
    one of those three is not on the card; it is in `details`, which the
    desktop pane renders in full.
    """
    if isinstance(p, dict):
        data = p
        coverage = p.get("coverage") or {}
        verb, target = p.get("verb", ""), p.get("target", "")
        label, number = p.get("label", ""), p.get("number", "")
        reach, tier = p.get("reach", REACH_OUT), p.get("tier_hint", "ask")
        complete = bool(coverage.get("complete"))
        cov_text = coverage.get("text", "")
    else:
        data = p.as_dict()
        verb, target = p.verb, p.target
        label, number = p.label, p.number
        reach, tier = p.reach, p.tier_hint
        complete = p.coverage.complete
        cov_text = p.coverage.text

    budget = int(_cfg("card_line_chars", 72) or 72)
    line1 = _elide(f"{verb} {target}".strip(), budget)
    two = f"{label}: {number}" if label and number else (label or number)
    # An incomplete pane says so ON the card, not in an expandable. The whole
    # point of declaring coverage is that the person holding the phone sees
    # it before the thumb moves.
    if not complete:
        two = f"{cov_text} - {label}" if label else cov_text
    line2 = _elide(two, budget)
    line3 = _elide(f"Reach: {reach}", budget)
    return {"lines": [line1, line2, line3],
            "line1": line1, "line2": line2, "line3": line3,
            "tier_hint": tier, "coverage": cov_text, "complete": complete,
            "budget": budget, "details": data}


# --------------------------------------------------------------------------
#   python jarvis_preview.py "rm -rf /tmp/x"
# --------------------------------------------------------------------------

if __name__ == "__main__":                              # pragma: no cover
    import argparse
    import json as _json
    import sys

    ap = argparse.ArgumentParser(
        description="Show what an action would do, without doing it.")
    ap.add_argument("command", nargs="?", help="a shell command to preview")
    ap.add_argument("--grammar", default="", choices=["", *GRAMMARS],
                    help="posix, powershell or cmd; empty parses all three "
                         "and reports it only if they disagree")
    ap.add_argument("--diff", help="preview a write to this path, "
                                   "with the new content read from stdin")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.diff:
        pv = diff_preview(a.diff, sys.stdin.read())
    elif a.command:
        pv = shell_preview(a.command, a.grammar)
    else:
        ap.error("give a command or --diff PATH")
    c = card(pv)
    if a.json:
        print(_json.dumps(pv.as_dict(), indent=1, default=str))
    else:
        for line in c["lines"]:
            print("  " + line)
        print(f"\n  tier hint: {c['tier_hint']}   {c['coverage']}")
        for u in pv.unknown:
            print(f"    unknown [{u['severity']}] {u['why']}: {u['token']}")
            if u.get("note"):
                print(f"      {u['note']}")
