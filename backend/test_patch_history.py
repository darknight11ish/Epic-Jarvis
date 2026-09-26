"""backend/patch-history holds every earlier version of every patch, and each
one is a text git can really take off.

WHY

scripts/apply-patches.ps1 finds out whether a patch is on by taking it off
(`git apply --reverse`), and only the exact text that went on comes off. When
a patch is edited after the owner applied it, the new text cannot take the
old one off, so the script used to stop with "will not apply" and the owner
was stuck. Now it tries every earlier text in backend/patch-history, newest
first. That only helps if the folder is complete, so:

  1. up to date: regenerating it from `git log` gives exactly what is
     committed. Fails the moment someone edits a patch and does not run
     `python3 tools/build_patch_history.py`. Needs the full git history: in
     CI (the CI variable is set) a shallow clone is a FAILURE, because
     skipping there would switch the check off unnoticed; anywhere else,
     including the owner's PC with a downloaded copy, it is skipped.
  2. the index and the folder agree, newest first per patch, nothing equal
     to the current text, nothing twice, every entry names a real patch.
  3. every earlier text is a well-formed patch that `git apply --reverse`
     takes off a file carrying it - checked against a stand-in built from
     its own after-image, so it needs no file from the owner's PC.
  4. the rule the script follows, modelled in Python and run with real
     `git apply` on a small made-up backend: an old text of one patch is on,
     it is recognised, taken off, and the current stack goes on - and a text
     that was never published is refused with nothing changed. The script
     itself is run the same way, in Windows PowerShell 5.1, by CI's
     powershell-5 job; this is the same rule where no PowerShell exists.

    python3 test_patch_history.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HIST = HERE / "patch-history"
INDEX = HIST / "index.tsv"
sys.path.insert(0, str(ROOT / "tools"))
import build_patch_history as bph  # noqa: E402

GIT = shutil.which("git")
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def read_index() -> list:
    rows = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line.split("\t"))
    return rows


# --- 1 ----------------------------------------------------------------------

def texts(hist: Path, rows: list) -> set:
    return {(r[0], lf((hist / r[1]).read_bytes())) for r in rows if (hist / r[1]).is_file()}


def t_history_is_up_to_date():
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "patch-history"
            bph.build(fresh)
            fresh_rows = [l.split("\t") for l in (fresh / "index.tsv").read_text(encoding="utf-8").splitlines()
                          if l and not l.startswith("#")]
            want = texts(fresh, fresh_rows)
            diff = bph.differences(fresh, HIST)
    except bph.NoHistory as e:
        if os.environ.get("CI"):
            check("the full git history is available in CI", False,
                  f"{e}. The CI job must check out with fetch-depth: 0.")
        else:
            print(f"skip  up-to-date check: {e}")
        return
    # By TEXT, which is what the script needs: every earlier version in
    # `git log` is here, and nothing is here that is not in it. Commit ids in
    # the names are not compared - a squash or rebase merge would change
    # them without changing a single text.
    have = texts(HIST, read_index())
    missing = sorted(k for k, _ in want - have)
    extra = sorted(k for k, _ in have - want)
    fix = "\n        Fix: python3 tools/build_patch_history.py, then commit backend/patch-history."
    check("every earlier version of every patch in `git log` is in backend/patch-history",
          not missing, f"missing a version of: {', '.join(missing)}{fix}")
    check("backend/patch-history holds no version `git log` does not have (or that is current)",
          not extra, f"not in git log, or now current: {', '.join(extra)}{fix}")
    if diff and not missing and not extra:
        print("note  same texts, but the names or index differ from a fresh build (a rebase or"
              " squash merge does that); regenerating would tidy it:"
              " python3 tools/build_patch_history.py")


# --- 2 ----------------------------------------------------------------------

def t_index_and_folder_agree():
    rows = read_index()
    check("index.tsv has rows of five tab-separated columns",
          rows and all(len(r) == 5 for r in rows), f"{[r for r in rows if len(r) != 5][:3]}")
    current = {k: lf(p.read_bytes()) for k, p in bph.current_patches()}
    listed = {r[1] for r in rows}
    on_disk = {p.relative_to(HIST).as_posix() for p in HIST.rglob("*.patch")}
    check("every file in patch-history is in index.tsv", on_disk <= listed, f"{sorted(on_disk - listed)}")
    check("every file in index.tsv exists", listed <= on_disk, f"{sorted(listed - on_disk)}")
    check("every index row names a patch the script can apply",
          all(r[0] in current for r in rows), f"{sorted({r[0] for r in rows} - set(current))}")
    misplaced = [r[1] for r in rows
                 if not (r[1].startswith(r[0][:-len(".patch")] + "/")
                         and r[2].startswith(Path(r[1]).stem))]
    check("every file sits in its patch's folder, named after its commit", not misplaced, f"{misplaced}")
    by_patch = {}
    for r in rows:
        by_patch.setdefault(r[0], []).append(r)
    # Newest first: the script tries them in this order, and stops at the
    # first that comes off.
    check("each patch's versions are listed newest first",
          all([x[3] for x in v] == sorted((x[3] for x in v), reverse=True) for v in by_patch.values()),
          f"{[k for k, v in by_patch.items() if [x[3] for x in v] != sorted((x[3] for x in v), reverse=True)]}")
    same_as_now = [r[1] for r in rows if r[0] in current and lf((HIST / r[1]).read_bytes()) == current[r[0]]]
    check("no earlier version is the current text", not same_as_now, f"{same_as_now}")
    dup = []
    for k, v in by_patch.items():
        texts = [lf((HIST / r[1]).read_bytes()) for r in v if (HIST / r[1]).exists()]
        if len(set(texts)) != len(texts):
            dup.append(k)
    check("no text is kept twice for one patch", not dup, f"{dup}")
    crlf = [r[1] for r in rows if b"\r\n" in (HIST / r[1]).read_bytes()]
    check("every earlier version is stored with LF endings", not crlf, f"{crlf}")


# --- 3 ----------------------------------------------------------------------

def targets(text: str) -> dict:
    """{file: (created, [hunk])}; hunk = [after_start, after_lines,
    no_newline_at_end, prefixes] - prefixes is each body line's first
    character, to count the hunk's trailing context."""
    out, cur, hunk, created, prev = {}, None, None, False, ""
    old_left = new_left = 0
    for l in text.split("\n"):
        if old_left > 0 or new_left > 0:
            # Inside a hunk, by its line counts - so a removed line that
            # starts "-- " is not a file header, and an EMPTY line is an empty
            # context line (git accepts that; an editor that strips trailing
            # spaces writes it).
            kind = l[:1] if l[:1] in ("+", "-") else " "
            hunk[3].append(kind)
            if kind != "-":
                hunk[1].append(l[1:])
                new_left -= 1
            if kind != "+":
                old_left -= 1
            prev = kind
            continue
        if l.startswith("\\") and hunk is not None:
            if prev in (" ", "+"):
                hunk[2] = True
            continue
        if l.startswith("--- "):
            created = l.split()[1] == "/dev/null"
            continue
        if l.startswith("+++ "):
            cur = l[4:].split("\t")[0].strip()[2:]
            out[cur] = (created, [])
            hunk = None
            continue
        if cur is not None and l.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", l)
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_left = int(m.group(3)) if m.group(3) is not None else 1
            hunk = [int(m.group(2)), [], False, []]
            out[cur][1].append(hunk)
            prev = ""
    return out


def stand_in(created: bool, hunks: list) -> str:
    """A file carrying these hunks' after-image at about their line numbers.

    git anchors a hunk that starts at line 1 to the top of the file, and one
    with no trailing context to the end, so no filler goes there."""
    if created:
        lines = [x for h in hunks for x in h[1]]
        return "\n".join(lines) + ("" if hunks and hunks[-1][2] else "\n")
    body = []
    ordered = sorted(hunks, key=lambda h: h[0])
    for start, lines, _, _ in ordered:
        if start > 1:
            while len(body) < start - 3:
                body.append(f"# filler {len(body)}")
            body.append("# filler gap")
        body.extend(lines)
    last = ordered[-1] if ordered else None
    at_end = last is not None and (last[2] or (last[3] and last[3][-1] != " "))
    if not at_end:
        body += ["# filler end"] * 5
    return "\n".join(body) + ("" if last is not None and last[2] else "\n")


def git(args, cwd):
    return subprocess.run([GIT] + args, cwd=cwd, capture_output=True, text=True)


def t_every_earlier_version_comes_off():
    if not GIT:
        print("skip  git is not installed, so no patch can be taken off here")
        return
    bad = []
    rows = read_index()
    for r in rows:
        patch = HIST / r[1]
        text = lf(patch.read_bytes()).decode("utf-8")
        d = Path(tempfile.mkdtemp(prefix="jarvis-hist-"))
        try:
            for name, (created, hunks) in targets(text).items():
                dest = d / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(stand_in(created, hunks))
            p = d / "_old.patch"
            p.write_bytes(lf(patch.read_bytes()))
            res = git(["apply", "--check", "--reverse", str(p)], d)
            if res.returncode != 0:
                bad.append(f"{r[1]}: {(res.stderr or res.stdout).strip().splitlines()[:2]}")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    check(f"all {len(rows)} earlier versions come off a file that carries them", not bad, "\n        ".join(bad))


# --- 4 ----------------------------------------------------------------------
#
# The rule of apply-patches.ps1 steps (a) to (c) and 2, in Python, run with
# real `git apply`. A model: if the script's rule changes, change this too.

def older_versions(key, history):
    return history.get(key, [])


def upgrade(backend: Path, stack: list, history: dict):
    """(status, taken_off). status: 'already', 'applied', 'refused'."""
    def run(args, where):
        return git(args, where).returncode == 0

    def copy():
        d = Path(tempfile.mkdtemp(prefix="jarvis-model-"))
        for f in backend.iterdir():
            if f.suffix == ".py":
                shutil.copy2(f, d / f.name)
        return d

    rh = copy()
    try:
        if all(run(["apply", "--reverse", str(p)], rh) for _, p in reversed(stack)):
            return "already", []
    finally:
        shutil.rmtree(rh, ignore_errors=True)
    rh = copy()
    try:
        if all([run(["apply", str(p)], rh) for _, p in stack]):
            for _, p in stack:
                assert run(["apply", str(p)], backend)
            return "applied", []
    finally:
        shutil.rmtree(rh, ignore_errors=True)
    rh = copy()
    try:
        found = []
        for key, p in reversed(stack):
            if run(["apply", "--check", "--reverse", str(p)], rh):
                if run(["apply", "--reverse", str(p)], rh):
                    found.append((key, p))
                continue
            for o in older_versions(key, history):
                if run(["apply", "--check", "--reverse", str(o)], rh):
                    if run(["apply", "--reverse", str(o)], rh):
                        found.append((key, o))
                    break
        if not found or not all([run(["apply", str(p)], rh) for _, p in stack]):
            return "refused", []
    finally:
        shutil.rmtree(rh, ignore_errors=True)
    for _, p in found:
        assert run(["apply", "--reverse", str(p)], backend)
    for _, p in stack:
        assert run(["apply", str(p)], backend)
    return "applied", found


def diff_of(before: str, after: str, work: Path, out: Path):
    """A git-format patch turning jarvis_hud.py from `before` into `after`."""
    g = work / "g"
    if g.exists():
        shutil.rmtree(g)
    g.mkdir()
    git(["init", "-q"], g)
    git(["config", "core.autocrlf", "false"], g)
    (g / "jarvis_hud.py").write_text(before, encoding="utf-8", newline="\n")
    git(["add", "jarvis_hud.py"], g)
    (g / "jarvis_hud.py").write_text(after, encoding="utf-8", newline="\n")
    r = git(["diff", f"--output={out}"], g)
    assert r.returncode == 0 and out.stat().st_size > 0, r.stderr


def t_the_upgrade_rule_on_a_made_up_backend():
    if not GIT:
        print("skip  git is not installed")
        return
    w = Path(tempfile.mkdtemp(prefix="jarvis-upgrade-"))
    try:
        base = [f"line {i}" for i in range(1, 41)]

        def text(changes):
            lines = list(base)
            for i, v in changes.items():
                lines[i] = v
            return "\n".join(lines) + "\n"
        one = {4: "line 5 - one"}
        two_old = {**one, 19: "line 20 - two, as first published"}
        two_new = {**one, 19: "line 20 - two, as it is now", 24: "line 25 - two, added later"}
        never = {**one, 19: "line 20 - two, hand-edited, never published"}
        three = {**two_new, 34: "line 35 - three, added to the list since"}
        P = {n: w / f"{n}.patch" for n in ("one", "two_old", "two_decoy", "two", "three")}
        diff_of(text({}), text(one), w, P["one"])
        diff_of(text(one), text(two_old), w, P["two_old"])
        diff_of(text(one), text({**one, 19: "line 20 - some other old text"}), w, P["two_decoy"])
        diff_of(text(one), text(two_new), w, P["two"])
        diff_of(text(two_new), text(three), w, P["three"])
        stack = [("one.patch", P["one"]), ("two.patch", P["two"]), ("three.patch", P["three"])]
        # Newest first: the decoy is tried and does not come off; the next does.
        history = {"two.patch": [P["two_decoy"], P["two_old"]]}

        def backend(state):
            b = w / f"be-{len(list(w.glob('be-*')))}"
            b.mkdir()
            (b / "jarvis_hud.py").write_text(text(state), encoding="utf-8", newline="\n")
            return b

        b = backend(two_old)
        status, off = upgrade(b, stack, history)
        check("an older text of a patch is recognised and replaced", status == "applied", status)
        check("...by taking off the text that is really there, and the current one-patch",
              [(k, p.name) for k, p in off] == [("two.patch", "two_old.patch"), ("one.patch", "one.patch")],
              f"{[(k, p.name) for k, p in off]}")
        check("...and the result is the current stack, exactly",
              (b / "jarvis_hud.py").read_text(encoding="utf-8") == text(three))
        check("a second run finds everything on", upgrade(b, stack, history)[0] == "already")

        b = backend(never)
        before = (b / "jarvis_hud.py").read_bytes()
        status, _ = upgrade(b, stack, history)
        check("a text that was never published is refused", status == "refused", status)
        check("...and nothing is changed", (b / "jarvis_hud.py").read_bytes() == before)

        b = backend(two_old)
        status, _ = upgrade(b, stack, {})
        check("without the history the same backend is refused (what used to happen)",
              status == "refused", status)

        b = backend({})
        check("a backend with nothing on takes the whole stack",
              upgrade(b, stack, history)[0] == "applied"
              and (b / "jarvis_hud.py").read_text(encoding="utf-8") == text(three))
    finally:
        shutil.rmtree(w, ignore_errors=True)


def t_the_script_reads_the_history():
    ps1 = (ROOT / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 reads backend/patch-history/index.tsv",
          "'patch-history'" in ps1 and "'index.tsv'" in ps1)
    check("apply-patches.ps1 tries older versions when taking patches off",
          ps1.count("Get-OlderVersions -Name") >= 2)
    check("apply-patches.ps1 takes off the text the rehearsal found, not the current one",
          "Invoke-Patch -File $u.File -Reverse" in ps1)
    check("apply-patches.ps1 is ASCII (Windows PowerShell 5.1 reads it as ANSI)",
          all(ord(c) < 128 for c in ps1))


if __name__ == "__main__":
    for fn in (t_history_is_up_to_date,
               t_index_and_folder_agree,
               t_every_earlier_version_comes_off,
               t_the_upgrade_rule_on_a_made_up_backend,
               t_the_script_reads_the_history):
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
