"""Does apply-patches.ps1 ship everything the backend needs from this repository?

    python3 test_shipped_modules.py

WHY THIS EXISTS. Every import of a module this repository ships is wrapped in
a `try`, so a module that never reaches the owner's PC produces no error
anywhere - the feature it carries is simply off. That has happened three
ways, each found by an audit and not by a test:

  - jarvis_agent.py was shipped, and the seven tool modules it imports
    (research, ui_control, android_control, calendar, email, notes, home)
    were not. Every tool answered "unavailable".
  - Nothing shipped backend/rebuilt/ at all, so fixes made to the ten
    rebuilt modules in this repository never reached the PC - while the
    script chose which patches to apply by assuming they were there.
  - backend/_where.py's SHIPPED list, which the suites use, fell seven
    modules behind the script's $SHIPPED.

So this reads the REAL producer and consumer - the script's own $SHIPPED
block, _where.SHIPPED, every shipped module's import statements (by parsing
them), every patch's added import lines, and the rebuilt jarvis_framework.py's
own settings-file search - and checks they agree. Nothing here is a
hand-copied list of what "should" be shipped: a module added to backend/
without being added to the script fails here.

Needs nothing from the owner's PC; runs anywhere, including CI.
"""
import ast
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

REPO = _where.REPO
PS1 = REPO / "scripts" / "apply-patches.ps1"
CHECK_PS1 = REPO / "scripts" / "check-backend.ps1"
REQS = HERE / "requirements.txt"
FAILED, PASSED = [], []

# Modules the shipped code imports that live ONLY on the owner's PC. They are
# not in this repository (checked below: an entry here that turns up as a file
# in backend/ is an error, because then it should be shipped instead).
OWNER_ONLY = {
    "jarvis_hud": "the server itself; patched, never shipped",
    "jarvis_gate": "the approval gate; patched (gate-push, no-auto-approve, ...), never shipped",
    "jarvis_extract": "the learning queue; patched (memory-safety, decide-once, ...), never shipped",
    "jarvis_models": "the model manager; patched (vram-estimate, gpu-offload), never shipped",
    "jarvis_skills": "the skill store; patched (skill-notes), never shipped",
    "jarvis_style": "probed by name in rebuilt jarvis_events.py's capability list, which "
                    "reports false when it is absent; not in this repository, and whether "
                    "the owner's PC has it is unverified",
}

# Third-party packages: import name -> pip name. Each must appear in
# requirements.txt, either as a requirement or in its "NOT installed" notes.
THIRD_PARTY = {
    "numpy": "numpy",
    "sherpa_onnx": "sherpa-onnx",
    "onnxruntime": "onnxruntime",
    "fastembed": "fastembed",
    "sqlite_vec": "sqlite-vec",
    "uiautomation": "uiautomation",
    "tomli": "tomli",
    "playwright": "playwright",
    "speechbrain": "speechbrain",
    "torch": "torch",
    "f5_tts": "f5-tts",
    "soundfile": "soundfile",
    "cryptography": "cryptography",
    "ddgs": "ddgs",
}

# Packages in requirements.txt that no shipped module imports BY NAME,
# because the standard library loads them itself. Each says who uses it.
INDIRECT = {
    "tzdata": "the standard library's zoneinfo reads it on Windows, which has no "
              "time-zone data of its own (jarvis_calendar.py's event times)",
    "markitdown": "imported only by the separate converter program jarvis_documents.py "
                  "starts (its _CHILD code), never by the backend itself - so a crafted "
                  "PDF is read in a process with no passwords in its environment",
}

# Files in backend/ that are NOT shipped, on purpose. Tools run from this
# repository, not from the backend folder.
NOT_SHIPPED = {
    "_where.py": "test plumbing",
    "_skeleton.py": "a template for new suites",
    "_stack.py": "test plumbing: the whole patch stack's stand-in for an owner's file",
    "_config_diff.py": "run by apply-patches.ps1 from this repository",
    "run_suites.py": "CI's test runner",
    "selftest.py": "run from this repository against the backend",
    "import_history.py": "run from this repository against the backend",
    "eval_memory.py": "the memory self-test, run from this repository on a scratch store",
    "eval_learner.py": "the memory self-test's learner half, run by eval_memory.py",
    "grade-peers.py": "a research tool, not part of the backend",
    "_ollama_wire.py": "test fixture: Ollama's real /v1 stream format, for the chat tests",
    "_voice_test.py": "test plumbing: a stand-in speaker model for the voice suites",
}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------ reading the script --

def ps1_list(name: str) -> list:
    """The quoted entries of `$name = @( ... )` in apply-patches.ps1, in order.
    Comments (from #) are dropped first, so a name in a comment is not an entry."""
    text = PS1.read_text(encoding="utf-8")
    start = text.index(f"${name} = @(")
    out = []
    for line in text[start:].splitlines()[1:]:
        code = line.split("#", 1)[0].strip()
        if code == ")":
            return out
        out += re.findall(r"'([^']+)'", code)
    raise AssertionError(f"${name} has no closing ')'")


def ps1_superseded() -> set:
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$REBUILT_SUPERSEDES = @{")
    body = text[start:text.index("}", start)]
    return set(re.findall(r"^\s*'([^']+\.patch)'\s*=", body, re.M))


def ps1_scalar(name: str) -> str:
    m = re.search(rf"^\${name}\s*=\s*'([^']+)'", PS1.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


SHIPPED = ps1_list("SHIPPED")
LEAVES = {p.rsplit("/", 1)[-1] for p in SHIPPED}
SHIPPED_MODS = {leaf[:-3] for leaf in LEAVES}


# ------------------------------------------------------ reading the imports --

_DYNAMIC = re.compile(r"""(?:__import__|import_module|\bhas)\(\s*["'](jarvis_\w+)["']""")


def imports_of_source(src: str) -> set:
    """Top-level names imported anywhere in this source - including inside
    functions and try blocks, which is where every guarded import lives -
    plus modules named as a string to __import__/import_module/has()."""
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    names |= set(_DYNAMIC.findall(src))
    return names


def imports_of_patch(path: Path) -> set:
    """Names imported by the lines a patch ADDS. Each added line that is an
    import statement is parsed on its own (dedented), so the answer comes
    from Python's parser, not from a guess at the syntax."""
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        code = line[1:].strip()
        if re.match(r"(import|from)\s", code):
            try:
                names |= imports_of_source(code.rstrip("\\").rstrip(",").rstrip("("))
            except SyntaxError:
                m = re.match(r"(?:from|import)\s+([\w.]+)", code)
                if m:
                    names.add(m.group(1).split(".")[0])
        names |= set(_DYNAMIC.findall(code))
    return names


def patch_targets(path: Path) -> set:
    return {m.split("\t")[0].strip()
            for m in re.findall(r"^\+\+\+ b/(.+)$", path.read_text(encoding="utf-8"), re.M)}


def requirement_names() -> set:
    """pip names in requirements.txt: requirement lines, and names in its notes."""
    names = set()
    for raw in REQS.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            m = re.match(r"#\s+([A-Za-z][\w.-]*)\s{2,}", s)
            if m:
                names.add(m.group(1).lower())
            continue
        names.add(re.split(r"[\s;<>=!~\[]", s, maxsplit=1)[0].lower())
    return names


# ------------------------------------------------------------------- tests --

def t_the_two_lists_are_one_list():
    check("$SHIPPED in apply-patches.ps1 is not empty", len(SHIPPED) > 10, f"{SHIPPED}")
    check("_where.SHIPPED is exactly $SHIPPED, in the same order",
          list(_where.SHIPPED) == SHIPPED,
          f"only in the script: {sorted(set(SHIPPED) - set(_where.SHIPPED))}; "
          f"only in _where.py: {sorted(set(_where.SHIPPED) - set(SHIPPED))}")
    check("no entry is listed twice", len(SHIPPED) == len(set(SHIPPED)))
    check("no two entries land on the same file name in the backend folder",
          len(LEAVES) == len(SHIPPED))
    check("$SHIPPED is defined once", PS1.read_text(encoding="utf-8").count("$SHIPPED = @(") == 1)


def t_every_entry_exists():
    for p in SHIPPED:
        check(f"{p} exists in backend/", (HERE / p).is_file())


def t_every_module_here_is_shipped():
    # Every jarvis_*.py written for the backend - here or in rebuilt/ - must
    # reach it. A new module that is not in $SHIPPED is the exact failure
    # this suite exists for.
    here = sorted(p.name for p in HERE.glob("*.py")
                  if not p.name.startswith("test_") and p.name not in NOT_SHIPPED)
    rebuilt = sorted(f"rebuilt/{p.name}" for p in (HERE / "rebuilt").glob("*.py"))
    for n in here:
        check(f"backend/{n} is shipped", n in SHIPPED,
              "add it to $SHIPPED in scripts/apply-patches.ps1 and to _where.SHIPPED, "
              "or to NOT_SHIPPED here with the reason")
    for n in rebuilt:
        check(f"backend/{n} is shipped", n in SHIPPED)
    for n in NOT_SHIPPED:
        check(f"NOT_SHIPPED entry {n} still exists (else drop it)", (HERE / n).is_file())


def t_every_import_is_accounted_for():
    std = set(sys.stdlib_module_names)
    sources = {p: imports_of_source((HERE / p).read_text(encoding="utf-8")) for p in SHIPPED}
    patches = sorted(HERE.glob("*.patch")) + sorted((HERE / "rebuilt-patches").glob("*.patch"))
    for pp in patches:
        sources[str(pp.relative_to(HERE))] = imports_of_patch(pp)
    reqs = requirement_names()
    unknown = []
    for who, names in sorted(sources.items()):
        for n in sorted(names):
            if n in std or n in SHIPPED_MODS or n in OWNER_ONLY:
                continue
            if n in THIRD_PARTY:
                if THIRD_PARTY[n].lower() not in reqs:
                    unknown.append(f"{n} (imported by {who}) is a package missing from requirements.txt")
                continue
            unknown.append(f"{n} (imported by {who})")
    check("every module a shipped file or a patch imports is shipped, the owner's, "
          "the standard library, or in requirements.txt", not unknown, "; ".join(unknown))
    # The specific regression: jarvis_agent.py's tools.
    agent = sources["jarvis_agent.py"]
    tools = sorted(n for n in agent if n.startswith("jarvis_") and n not in OWNER_ONLY)
    check("every jarvis_* module jarvis_agent.py imports is shipped",
          all(t in SHIPPED_MODS for t in tools),
          f"not shipped: {[t for t in tools if t not in SHIPPED_MODS]}")
    check("the check can see jarvis_agent.py's guarded tool imports at all",
          {"jarvis_research", "jarvis_home", "jarvis_calendar"} <= set(tools), f"{tools}")


def t_the_exemptions_are_real():
    for n, why in OWNER_ONLY.items():
        check(f"{n} is owner-only, so it must not be a file in this repository",
              not (HERE / f"{n}.py").is_file() and not (HERE / "rebuilt" / f"{n}.py").is_file(),
              f"backend has {n}.py - ship it instead of exempting it ({why})")
    for pip in sorted(set(THIRD_PARTY.values())):
        check(f"{pip} is named in requirements.txt", pip.lower() in requirement_names())
    # And the other way: nothing in requirements.txt that nothing imports.
    used = set()
    for p in SHIPPED:
        used |= imports_of_source((HERE / p).read_text(encoding="utf-8"))
    by_pip = {v.lower(): k for k, v in THIRD_PARTY.items()}
    for pip in sorted(requirement_names()):
        if pip in INDIRECT:
            check(f"requirements.txt's {pip} is used indirectly, and says by whom",
                  bool(INDIRECT[pip]))
            continue
        check(f"requirements.txt's {pip} is imported by a shipped module",
              by_pip.get(pip) in used, f"no shipped module imports {by_pip.get(pip, pip)}")


def t_no_patch_edits_a_shipped_file():
    # The script copies shipped files whole, every run. A patch that edited
    # one would be undone by the next copy - and the order of copying and
    # patching would start to matter. On the list the script actually
    # applies (split halves for the six superseded patches), none does.
    superseded = ps1_superseded()
    check("six patches are superseded by the rebuilt modules", len(superseded) == 6, f"{superseded}")
    for name in ps1_list("PATCHES"):
        path = HERE / name
        if name in superseded:
            path = HERE / "rebuilt-patches" / name
            if not path.is_file():
                continue
        hit = patch_targets(path) & LEAVES
        check(f"{path.relative_to(HERE)} edits no shipped file", not hit, f"{sorted(hit)}")


def t_the_settings_file_search_matches_the_backend():
    # The script decides "you have a settings file" by looking where
    # rebuilt/jarvis_framework.py looks. Read that module's own source, so a
    # change to its search order fails here instead of the script quietly
    # installing a second copy the backend never reads.
    src = (HERE / "rebuilt" / "jarvis_framework.py").read_text(encoding="utf-8")
    cand = src[src.index("candidates = ["):]
    cand = cand[:cand.index("]") + 1]
    order = ["_explicit()", "CONFIG_DIR / CONFIG_NAME", "here / CONFIG_NAME",
             "here.parent / CONFIG_NAME"]
    pos = [cand.find(o) for o in order]
    check("jarvis_framework.config_path() still searches: override, config dir, "
          "beside the module, one folder up", all(p >= 0 for p in pos) and pos == sorted(pos), cand)
    check("the override is JARVIS_FRAMEWORK_TOML", 'os.environ.get("JARVIS_FRAMEWORK_TOML")' in src)
    check("the config dir is OPENJARVIS_CONFIG_DIR, then JARVIS_CONFIG_DIR, then ~/.openjarvis",
          'os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")' in src
          and '".openjarvis"' in src)
    ps = PS1.read_text(encoding="utf-8")
    step = ps[ps.index("# --- 4. the settings file"):ps.index("# --- 5. Python packages")]
    want = ["$env:JARVIS_FRAMEWORK_TOML", "(Join-Path $cfgDir $CONFIG_NAME)",
            "(Join-Path $BackendPath $CONFIG_NAME)",
            "(Join-Path (Split-Path -Parent $BackendPath) $CONFIG_NAME)"]
    at = [step.find(w) for w in want]
    check("the script looks in the same four places, in the same order",
          all(a >= 0 for a in at) and at == sorted(at), f"{list(zip(want, at))}")
    envs = [step.find("$env:OPENJARVIS_CONFIG_DIR"), step.find("$env:JARVIS_CONFIG_DIR"),
            step.find("'.openjarvis'")]
    check("and works out the config dir the same way", all(e >= 0 for e in envs) and envs == sorted(envs))
    check("the settings file it installs is rebuilt/jarvis-framework.toml, and it exists",
          ps1_scalar("CONFIG_SRC") == "rebuilt/jarvis-framework.toml"
          and (HERE / "rebuilt" / "jarvis-framework.toml").is_file())
    check("it never copies over an existing settings file",
          step.count("Copy-Item") == 1 and "elseif (-not $cfgInUse)" in step)


def t_the_settings_diff_reports_what_differs():
    ours = HERE / "rebuilt" / "jarvis-framework.toml"
    text = ours.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as d:
        same = Path(d) / "same.toml"
        same.write_text(text.replace("\n", "\r\n"), encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "_config_diff.py"), str(same), str(ours)],
                           capture_output=True, text=True)
        check("an identical file (even with CRLF endings) reports no difference",
              r.returncode == 0 and "Same settings" in r.stdout, r.stdout + r.stderr)
        mine = Path(d) / "mine.toml"
        changed = text.replace('owner = "Mario"', 'owner = "Someone"', 1)
        changed = changed.replace("[meta]\n", "[meta]\nmy_own = 1\n", 1)
        changed = changed.replace("commercial = false", "", 1)
        mine.write_text(changed, encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "_config_diff.py"), str(mine), str(ours)],
                           capture_output=True, text=True)
        out = r.stdout
        check("a changed setting is named, with both values",
              '[meta] owner:  yours "Someone"   repository "Mario"' in out, out)
        check("a setting the owner lacks is named", "[meta] commercial = False" in out, out)
        check("a setting only the owner has is named, and said to be kept",
              "[meta] my_own = 1" in out and "kept" in out, out)
        bad = Path(d) / "bad.toml"
        bad.write_text("[meta\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "_config_diff.py"), str(bad), str(ours)],
                           capture_output=True, text=True)
        check("a settings file that does not parse is reported as such",
              r.returncode == 2 and "Could not read" in r.stdout, r.stdout)


def t_check_backend_knows_what_will_be_copied_in():
    # check-backend.ps1 used to report the shipped modules as MISSING and say
    # "do not run apply-patches.ps1 yet" - about files apply-patches.ps1 is
    # what copies in.
    s = CHECK_PS1.read_text(encoding="utf-8")
    check("check-backend.ps1 reads this repository's shipped modules",
          "rebuilt" in s and "_where.py" in s, "it should read SHIPPED from backend/_where.py")


if __name__ == "__main__":
    for fn in (t_the_two_lists_are_one_list, t_every_entry_exists, t_every_module_here_is_shipped,
               t_every_import_is_accounted_for, t_the_exemptions_are_real,
               t_no_patch_edits_a_shipped_file, t_the_settings_file_search_matches_the_backend,
               t_the_settings_diff_reports_what_differs, t_check_backend_knows_what_will_be_copied_in):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
