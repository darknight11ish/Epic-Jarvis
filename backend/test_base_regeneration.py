"""Does `tools/gen_base_from_backend.py` follow the base's own re-take rule?

    py -3 test_base_regeneration.py

WHY THIS EXISTS

`jarvis-backend/` is the only complete copy of the program in this repository,
and for its first three days nothing could re-take it: `jarvis-backend/README.md`
described the rule in prose ("The exact rule, so it can be re-taken") and the
copy was taken by hand. `docs/UPDATER-REDESIGN.md` section 5's build step 3 asks
for the missing half - one script that re-takes the folder, and a check that
fails when it differs - and follow-up 8 of that README asks for the same thing.

A script whose only test is "it ran" would be worse than the prose it replaced:
the prose at least says what the rule IS. So every check here builds a folder
whose answer is known in advance - a source folder holding one file the rule
copies, one it must refuse, and one it must edit - and reads the tool's own
report of what it planned. The last check runs the tool against THIS
repository's `jarvis-backend/` and requires the files the rule takes from the
repository itself to agree: `backend/rebuilt/jarvis-framework.toml`,
`backend/requirements.lock`, `backend/quiz_grader_cases.json` and
`jarvis-desktop/src-tauri/Cargo.lock` are the inputs, and
`backend/test_base_matches_repo.py` is the authority on the rest.

WHAT IT DOES NOT PROVE, PLAINLY

Nothing here can prove the committed base is what the OWNER'S folder produces -
that folder is not in this repository and not in CI. `--check` is the command
that answers that question on a machine which has it, and its answer is a
report, not a green tick. What is proved here is the rule: which files are
copied, which are refused, and the one documented edit.

Needs nothing from the owner's PC; runs anywhere, including CI.
"""
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))

import gen_base_from_backend as G  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-800:])


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


def t_the_tool_is_ascii_only():
    """The one script every platform runs, and a name a shell must not mangle.

    `scripts/apply-patches.ps1` is byte-scanned for the same reason (Windows
    PowerShell 5.1 reads a script by the system code page), and this file is
    run by `python tools/...` on the same machines.
    """
    raw = (REPO / "tools" / "gen_base_from_backend.py").read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 0x7F]
    check("tools/gen_base_from_backend.py is pure ASCII", not bad,
          f"{len(bad)} non-ASCII byte(s), first at {bad[:1]}")


def t_the_rule_is_the_readme_s_rule():
    """The three exclusions, the files beside the code and the one derived file,
    as the README writes them.

    Read out of the tool rather than restated: a rule that only exists in this
    test would drift from the tool the moment either changed.
    """
    names = [pat.pattern for pat, _why in G.NEVER_COPIED]
    check("the three refusals are the README's own (test_*.py, patch_openjarvis.py, spike_sandbox.py)",
          names == [r"^test_.*\.py$", r"^patch_openjarvis\.py$", r"^spike_sandbox\.py$"],
          str(names))
    beside = [n for n, _w, _y in G.BESIDE] + [n for n, _w, _y in G.BESIDE_BINARY]
    check("the files beside the code are the README's own list",
          beside == ["jarvis_hud.html", "jarvis-framework.toml", "requirements.lock",
                     "quiz_grader_cases.json", "rust-crates.lock", "jarvis-visual-spec.json",
                     # the browser's own files (2026-10-23, PWA Slice 3a):
                     # jarvis_hud.py's STATIC_ASSETS whitelist reads each beside
                     # itself; the page's real copies live in jarvis-desktop/src/
                     "theme.css", "fonts.css",
                     "lane-warning.js", "hud-actions.js", "hud-safety.js",
                     "hud-edit.js", "hud-presets.js", "private-speech.js",
                     "face-voice.js", "face-moments.js", "face-tuning.js",
                     "animal-shared.js", "hud-layout.js", "hud-layout-store.js",
                     # ... and PWA Slice 2's browser bridge, which the page
                     # loads with a <script src> (delivered with the static
                     # files, 2026-10-23)
                     "hud-web-bridge.js",
                     # ... PWA Slice 3b's manifest and service worker
                     "manifest.webmanifest", "sw.js",
                     # ... and the seven woff2 faces and the three icons, which are BYTES
                     "chakra-petch-400.woff2", "chakra-petch-500.woff2",
                     "chakra-petch-600.woff2", "chakra-petch-700.woff2",
                     "ibm-plex-mono-400.woff2", "ibm-plex-mono-500.woff2",
                     "ibm-plex-sans-400.woff2",
                     "jarvis-180.png", "jarvis-192.png", "jarvis-512.png"],
          str(beside))
    srcs = {n: w for n, w, _y in G.BESIDE}
    check("... and the settings file comes from backend/rebuilt/, never from the source folder",
          "backend/rebuilt/jarvis-framework.toml" in srcs["jarvis-framework.toml"]
          and "{source}" not in srcs["jarvis-framework.toml"],
          srcs["jarvis-framework.toml"])
    check("... and jarvis-visual-spec.json is the one that DOES come from the source folder",
          srcs["jarvis-visual-spec.json"].startswith("{source}"),
          srcs["jarvis-visual-spec.json"])
    binary = [n for n, _w, _y in G.BESIDE_BINARY]
    check("... and the seven woff2 faces and three PWA icons are the BYTE half of the rule (copied, never decoded)",
          binary == ["chakra-petch-400.woff2", "chakra-petch-500.woff2",
                     "chakra-petch-600.woff2", "chakra-petch-700.woff2",
                     "ibm-plex-mono-400.woff2", "ibm-plex-mono-500.woff2",
                     "ibm-plex-sans-400.woff2",
                     "jarvis-180.png", "jarvis-192.png", "jarvis-512.png"]
          and all(w.startswith("{repo}/backend/static/")
                  for _n, w, _y in G.BESIDE_BINARY)
          and not ({n for n, _w, _y in G.BESIDE} & set(binary)),
          str(binary))
    derived = [n for n, _w, _y in G.DERIVED_FROM_REPO]
    check("_where.py is the one file DERIVED rather than copied, and from this repository",
          derived == ["_where.py"] and G.DERIVED_FROM_REPO[0][1] == "{repo}/backend/_where.py",
          str(G.DERIVED_FROM_REPO))
    check("... and it is not also listed as a file the copy leaves alone",
          "_where.py" not in [n for n, _y in G.NOT_PART_OF_THE_COPY],
          str([n for n, _y in G.NOT_PART_OF_THE_COPY]))
    check("... and the base's own trailer is ASCII, like the tool that writes it",
          bool(G.BASE_WHERE_TRAILER.strip())
          and all(b <= 0x7F for b in G.BASE_WHERE_TRAILER.encode("utf-8")),
          "a PowerShell 5.1 script reads this tool by the system code page")


def t_a_duplicate_dict_key_keeps_its_last_line():
    """The one deliberate edit, on an answer known in advance.

    CPython keeps the last of two identical keys in one dict literal and says
    nothing; `jarvis-backend/README.md` says the base has the dead earlier
    lines removed, and `tools/check_literal_keys.py` is what found them. Both
    halves matter: the earlier line goes, the LATER one stays, and nothing
    else in the file moves.
    """
    text = ('RISK = {\n'
            '    "a": ("yes", "local"),\n'
            '    "dead": ("yes", "local"),\n'
            '    "b": ("no", "outbound"),\n'
            '    "dead": ("yes", "outbound"),\n'
            '}\n')
    out, dropped = G.dropped_duplicate_keys(text)
    check("a key written twice in one dict literal keeps its LAST line",
          '"dead": ("yes", "outbound"),' in out and '"dead": ("yes", "local"),' not in out,
          out)
    check("... and the drop is named, with the line it was on",
          dropped == [(3, "dead")], str(dropped))
    check("... and nothing else was edited: the same text with that one line taken out",
          out == text.replace('    "dead": ("yes", "local"),\n', ""), out)
    check("... and the result still compiles", _compiles(out), out)


def t_two_dict_literals_with_the_same_key_are_left_alone():
    """The rule is about ONE literal. Two literals are two entries, not a
    duplicate, and a tool that dropped one would silently delete a tier."""
    text = ('A = {\n    "x": 1,\n}\n'
            'B = {\n    "x": 2,\n    "x": 3,\n}\n')
    out, dropped = G.dropped_duplicate_keys(text)
    check("the same key in two different dict literals is not a duplicate",
          'A = {\n    "x": 1,\n}' in out, out)
    check("... and only the second literal's earlier line is dropped",
          dropped == [(5, "x")], str(dropped))


def t_a_plan_copies_what_the_rule_says_and_refuses_what_it_says():
    """One source folder, one answer, read from the tool's own plan."""
    with tempfile.TemporaryDirectory(prefix="jarvis-base-gen-") as td:
        src = Path(td) / "source"
        write(src / "jarvis_hud.py", "print('hi')\n")
        write(src / "jarvis_widgets.py", "print('widgets')\n")
        write(src / "test_speech.py", "print('not copied')\n")
        write(src / "patch_openjarvis.py", "print('not copied')\n")
        write(src / "spike_sandbox.py", "print('not copied')\n")
        write(src / "jarvis-visual-spec.json", '{"v": 1}\n')
        write(src / "jarvis-framework.toml", "[the owner's live settings]\n")
        want, problems = G.planned(src, REPO)
        check("the two .py files the rule takes are planned",
              "jarvis_hud.py" in want and "jarvis_widgets.py" in want, str(sorted(want)))
        check("the three .py files the rule refuses are not",
              not any(n in want for n in ("test_speech.py", "patch_openjarvis.py",
                                          "spike_sandbox.py")),
              str(sorted(want)))
        check("the owner's live settings file is NOT what the base's toml comes from",
              want.get("jarvis-framework.toml") == G.read_text(REPO / "backend" / "rebuilt" / "jarvis-framework.toml"),
              str(want.get("jarvis-framework.toml"))[:120])
        check("... and every beside-file (text and bytes) is planned",
              all(n in want for n, _w, _y in G.BESIDE + G.BESIDE_BINARY),
              str([n for n, _w, _y in G.BESIDE + G.BESIDE_BINARY if n not in want]))
        check("... and the woff2 faces are planned as BYTES, never decoded as text",
              isinstance(want.get("chakra-petch-400.woff2"), bytes)
              and want.get("chakra-petch-400.woff2")
              == (REPO / "backend" / "static" / "chakra-petch-400.woff2").read_bytes(),
              type(want.get("chakra-petch-400.woff2")))
        check("... and the owner's own visual spec IS copied in",
              want.get("jarvis-visual-spec.json") == '{"v": 1}\n',
              str(want.get("jarvis-visual-spec.json")))
        check("... and the base's _where.py is planned too, DERIVED from this repository "
              "rather than taken from the source folder",
              want.get("_where.py") == G.base_where_text(REPO),
              str(want.get("_where.py"))[-200:])
        check("... and the source folder's own _where.py, if it had one, is not what is used",
              want.get("_where.py", "").endswith(G.BASE_WHERE_TRAILER)
              and want.get("_where.py", "") != "",
              str(want.get("_where.py"))[-200:])
        check("a folder with no jarvis_hud.py in it is refused, not half-copied",
              G.planned(Path(td) / "empty", REPO)[1], "no problem reported")


def t_a_folder_that_is_not_a_backend_is_refused():
    """`--source` is the owner's backend folder, and a mistyped path must not
    produce a base. The tool's own exit code is what a script checks."""
    with tempfile.TemporaryDirectory(prefix="jarvis-base-gen-") as td:
        empty = Path(td) / "not-a-backend"
        empty.mkdir()
        run = subprocess.run([sys.executable, str(REPO / "tools" / "gen_base_from_backend.py"),
                              "--source", str(empty), "--check"],
                             capture_output=True, text=True)
        check("--check on a folder with no jarvis_hud.py exits 1",
              run.returncode == 1, f"exit {run.returncode}\n{run.stdout[-400:]}")
        check("... and says why, by naming the file it looked for",
              "jarvis_hud.py" in run.stdout, run.stdout[-400:])


def t_check_fails_on_a_base_that_disagrees():
    """The half of step 3 that "fails when it differs": both directions.

    A base that has been edited here, and a base missing a file the source
    produces, are the two ways `jarvis-backend/` can stop being what the live
    folder produces. `--check` must exit 1 on both and name the file.
    """
    with tempfile.TemporaryDirectory(prefix="jarvis-base-gen-") as td:
        src = Path(td) / "source"
        base = Path(td) / "base"
        write(src / "jarvis_hud.py", "print('live')\n")
        write(src / "jarvis-visual-spec.json", '{"v": 1}\n')
        write(src / "jarvis-framework.toml", "[the owner's live settings]\n")
        # The base has one file the source does not, and its copy of another
        # has been edited here.
        write(base / "jarvis_hud.py", "print('a base someone edited by hand')\n")
        write(base / "jarvis_gone.py", "print('no longer in the program')\n")
        # Every beside-file that has a source, so the only differences `--check`
        # finds are the two put there on purpose. The woff2 faces are bytes and
        # are written byte for byte, the same way the tool reads them.
        for name, where, _why in G.BESIDE:
            src_path = Path(where.format(repo=REPO.as_posix(), source=src.as_posix()))
            if src_path.is_file():
                write(base / name, G.read_text(src_path))
        for name, where, _why in G.BESIDE_BINARY:
            src_path = Path(where.format(repo=REPO.as_posix(), source=src.as_posix()))
            if src_path.is_file():
                (base / name).write_bytes(src_path.read_bytes())
        run = subprocess.run([sys.executable, str(REPO / "tools" / "gen_base_from_backend.py"),
                              "--source", str(src), "--base", str(base), "--check"],
                             capture_output=True, text=True)
        check("--check exits 1 for a base that disagrees", run.returncode == 1,
              f"exit {run.returncode}\n{run.stdout[-500:]}")
        check("... and names the file that was edited here", "jarvis_hud.py" in run.stdout,
              run.stdout[-500:])
        check("... and names the file the base has and the source does not",
              "jarvis_gone.py" in run.stdout, run.stdout[-500:])
        check("... and writes nothing in --check mode",
              (base / "jarvis_hud.py").read_text(encoding="utf-8") == "print('a base someone edited by hand')\n",
              repr((base / "jarvis_hud.py").read_text(encoding="utf-8")))


def t_the_fast_twin_check_covers_every_beside_file_this_repository_owns():
    """The beside-file half of the two-file rule, against the fast local check.

    `tools/check_stale_twins.py` compares `twin_pairs()`, and `twin_pairs()` is
    the modules plus `BESIDE_TWINS`. Until 2026-10-13 the tool compared the
    modules only, and PR #390 added `rapidocr` to `backend/requirements.lock`
    while leaving `jarvis-backend/requirements.lock` alone: the tool reported
    191 of 191 modules matching, and CI's `backend` and `audit` jobs went red on
    `these differ (or are absent): requirements.lock` - a line printed by the
    test above. So the two lists are held together here.

    Nothing is restated: the beside names come from `G.BESIDE`, the re-take
    rule's own table, and the coverage comes from the rule's own `twin_pairs()`.
    A file added to that table and not covered fails this, which is the point.
    """
    import test_base_matches_repo as M          # noqa: PLC0415

    covered = {leaf for leaf, _ours in M.twin_pairs()}
    repo_owned = {n for n, where, _why in G.BESIDE + G.BESIDE_BINARY
                  if "{source}" not in where}
    check("every beside-file the re-take rule takes from THIS repository is in "
          "the fast twin check's list",
          repo_owned <= covered,
          "the fast check does not compare: " + ", ".join(sorted(repo_owned - covered)))
    check("... and so are the seven woff2 faces, the rule's BYTE half",
          all(n in covered for n, _w, _y in G.BESIDE_BINARY),
          str([n for n, _w, _y in G.BESIDE_BINARY if n not in covered]))
    check("... and requirements.lock, the file that went stale in PR #390 while "
          "the module half was green, is one of them",
          "requirements.lock" in covered, str(sorted(covered))[:300])
    check("... and the beside-file that comes from the owner's live folder is not, "
          "because there is no copy of it here to compare against",
          "jarvis-visual-spec.json" not in covered and "jarvis-visual-spec.json" not in repo_owned,
          str(sorted(covered))[:300])
    check("... and _where.py is not either: the base's copy is DERIVED - this "
          "repository's copy plus BASE_WHERE_TRAILER - so it is compared by the "
          "check above and never with the same-text rule",
          "_where.py" not in covered,
          str(sorted(covered))[:300])


def t_the_repository_s_own_inputs_are_the_ones_in_the_base():
    """The files the rule takes from THIS repository, against the committed base.

    These have no live source at all: they are the repository's copies.
    `backend/test_base_matches_repo.py` covers the modules that ship whole; this
    covers the `BESIDE` inputs it does not (§1's list: `requirements.lock`,
    `quiz_grader_cases.json`, `rust-crates.lock`, and the settings template it
    checks by a different route), and `_where.py`, which is the one file the
    base derives rather than copies.
    """
    base = REPO / "jarvis-backend"
    pairs = [(n, Path(w.format(repo=REPO.as_posix(), source=REPO.as_posix())))
             for n, w, _y in G.BESIDE if "{repo}" in w]
    differ = [n for n, ours in pairs
              if not (base / n).is_file() or G.read_text(base / n) != G.read_text(ours)]
    binary = [(n, Path(w.format(repo=REPO.as_posix(), source=REPO.as_posix())))
              for n, w, _y in G.BESIDE_BINARY]
    differ += [n for n, ours in binary
               if not (base / n).is_file() or (base / n).read_bytes() != ours.read_bytes()]
    check("the base's copy of each file the rule takes from this repository is this repository's copy",
          not differ, "these differ (or are absent): " + ", ".join(sorted(differ)))

    #: `_where.py` is the exception, and it is a DERIVED file rather than a
    #: copied or an untouched one: `backend/_where.py` plus the base's own
    #: trailer, which says in words what this copy is. Kept by hand until
    #: 2026-10-10, by which time the base's copy was 77 lines of SHIPPED entries
    #: behind and nothing noticed; `tools/gen_base_from_backend.py` writes it
    #: now (`base_where_text()`), so re-taking the base refreshes it too.
    theirs = base / "_where.py"
    ours = REPO / "backend" / "_where.py"
    got = G.read_text(theirs) if theirs.is_file() else ""
    note = G.BASE_WHERE_TRAILER
    check("jarvis-backend/_where.py is this repository's copy plus the base's own trailer",
          bool(got) and got == G.read_text(ours) + note,
          "not `backend/_where.py` + BASE_WHERE_TRAILER - re-take it with "
          "`py -3 tools/gen_base_from_backend.py --source <the backend folder>`")
    check("... and that trailer is the whole difference (so the two are not identical)",
          bool(note.strip()) and got != G.read_text(ours),
          "the base's _where.py is byte-identical to backend/_where.py, which cannot be right: "
          "the trailer is what says which copy a reader is holding")
    check("... and the trailer says what it is, in words, not only in a filename",
          "jarvis-backend" in note and "not" in note and "base" in note,
          repr(note[-300:]))


def _compiles(text: str) -> bool:
    try:
        compile(text, "<test>", "exec")
        return True
    except SyntaxError:
        return False


if __name__ == "__main__":
    for fn in (t_the_tool_is_ascii_only,
               t_the_rule_is_the_readme_s_rule,
               t_a_duplicate_dict_key_keeps_its_last_line,
               t_two_dict_literals_with_the_same_key_are_left_alone,
               t_a_plan_copies_what_the_rule_says_and_refuses_what_it_says,
               t_a_folder_that_is_not_a_backend_is_refused,
               t_check_fails_on_a_base_that_disagrees,
               t_the_fast_twin_check_covers_every_beside_file_this_repository_owns,
               t_the_repository_s_own_inputs_are_the_ones_in_the_base):
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
