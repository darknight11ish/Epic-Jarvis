"""test_egress_gate_checker.py - the egress census reads code, not prose.

    python3 -B backend/test_egress_gate_checker.py

WHY THIS SUITE EXISTS

`tools/check_egress_gate.py` keeps the promise that every file naming an
outbound host either asks `jarvis_egress_gate.check_egress` or is on its
allow-list with a written reason. Until 2026-11-18 it searched the raw file
text, so a docstring counted as a mention. A new module's docstring showed
`api.deepseek.com` as an example, the checker failed the required suite
`backend/test_chatbot_api.py` ("every outbound host mention is accounted for")
and the lane's fix was to DELETE the example. An external review ruled that
out: a gate that teaches an author to remove documentation is teaching the
wrong lesson.

What replaced it is an AST walk. This suite proves every side of it on fixture
trees it writes in a temporary folder - so the fixture itself is the evidence,
never a claim about the repository - and then runs the same checker once on
THIS CHECKOUT so a green tree is reported rather than assumed. Every check
names the tree it read:

    tree: <a temporary fixture folder under TMP>

and for the last test:

    tree: this checkout (<repo root>)

WHAT IS PROVED HERE, and why each check can fail:

  * a module docstring and a function docstring naming a host do NOT fail the
    walk, and the run says how many documentation-only mentions it ignored;
  * a `#` comment naming a host does NOT fail it - comments never reach the AST
    at all, so nothing has to strip them;
  * a bare string expression statement (documentation kept inside a function,
    which is not a docstring `ast.get_docstring` returns) does NOT fail it;
  * a real string literal naming one of the census hosts STILL fails, with the
    file, line and host printed - the gate is not weakened;
  * a host built in an f-string still fails;
  * a host split over two adjacent literals, and a host built by `+`, still
    fails - and the fixture's own source text does NOT contain the joined host,
    which is the proof the old raw-text scan could not have seen either: the
    AST walk is stricter here, not looser;
  * a module-level constant holding a URL still fails;
  * an unlisted new host in a real call (`requests.get("https://evil.example")`)
    still fails once the census names it - HOSTS is a closed census, as it was
    before this change, so the test adds the host the 2026-11-16 audit would
    have added and edits nothing else;
  * a file whose real code asks `check_egress` is NOT a violation, and a file
    that merely SAYS check_egress in a docstring or a comment is NOT wiring -
    the old text check counted prose as a call, and `backend/test_web_search.py`
    was green that way;
  * a listed file passes with its reason; a listed file that now names a host
    only in prose is reported as a STALE entry (this is why the 2026-11-18 change
    removed thirteen entries); a listed file that is gone is reported;
  * a listed `backend/` file still covers its byte-identical `jarvis-backend/`
    copy, measured by bytes;
  * THIS CHECKOUT is green under the same walk, and the run's own census line
    (files wired, files allow-listed, an allow-list path count) is read back and
    checked for internal agreement, with the numbers printed.

Standard library only. No file outside this checkout is written except the
per-run temporary folder under the system temp directory.
"""
from __future__ import annotations

import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import check_egress_gate as G  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-egress-gate-"))

#: Fixture sources held as constants so the check about what the raw text says
#: compares against the text it wrote, never against a file read back.
CONCAT_SOURCE = (
    "BASE = \"https://api.\" + \"deepseek.com/v1\"\n"
    "\n"
    "\n"
    "def url(path):\n"
    "    return BASE + path\n")
ADJACENT_SOURCE = (
    'BASE = ("https://api."\n'
    '        "github.com")\n'
    "\n"
    "\n"
    "def url(path):\n"
    "    return BASE + path\n")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _tree(files: dict[str, str]) -> Path:
    """A fresh fixture tree with `files` written under it; returns its root."""
    root = Path(tempfile.mkdtemp(prefix="tree-", dir=str(TMP)))
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _run(root: Path, allowed: dict[str, str] | None = None,
         argv: list[str] | None = None) -> tuple[int, str]:
    """Run the checker over `root` with a standing-in allow-list; echo where.

    The fixture trees pass their OWN allow-list (usually empty) rather than the
    repository's, so a repo entry can never account for a fixture file.
    """
    said: list[str] = []
    code = G.main(argv=list(argv or []), repo=root,
                  allowed={} if allowed is None else dict(allowed),
                  say=said.append)
    return code, "\n".join(said)


def _prose(files: dict[str, str], allowed: dict[str, str] | None = None,
           argv: list[str] | None = None) -> tuple[int, str, Path]:
    root = _tree(files)
    code, out = _run(root, allowed=allowed, argv=argv)
    return code, out, root


def t_a_docstring_naming_a_host_does_not_fail_the_walk():
    code, out, root = _prose({"backend/new_module.py": (
        '"""new_module.py - an example module.\n'
        "\n"
        "The provider it would use is https://api.deepseek.com/v1/chat, and\n"
        "this sentence is documentation, not a request.\n"
        '"""\n'
        "\n"
        "\n"
        "def example():\n"
        '    """Call https://api.openai.com/v1/models when the switch is on."""\n'
        "    return 1\n")})
    check("a module AND function docstring naming a host do not fail"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... and the run says it ignored exactly those two mentions",
          "ignored 2 that are documentation only" in out, out)


def t_a_comment_naming_a_host_does_not_fail_the_walk():
    code, out, root = _prose({"backend/commented.py": (
        "# The provider this module once used was api.deepseek.com.\n"
        "answer = 2 + 2\n")})
    check("a # comment naming a host does not fail"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... and the run counts it as documentation the walk ignored",
          "ignored 1 that are documentation only" in out, out)


def t_a_bare_documentation_string_does_not_fail_the_walk():
    code, out, root = _prose({"backend/section_string.py": (
        '"""section_string.py - see the sections below."""\n'
        "\n"
        "\n"
        "def described():\n"
        '    """A real docstring."""\n'
        '    "The host this used to reach was api.mistral.ai"  # documentation\n'
        "    return 3\n")})
    check("a bare string statement inside a function is documentation too"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... and it is counted as ignored, not silently dropped",
          "ignored 1 that are documentation only" in out, out)


def t_a_real_string_literal_naming_a_host_still_fails():
    code, out, root = _prose({"backend/sender.py": (
        "import urllib.request\n"
        "\n"
        "\n"
        "def send(prompt):\n"
        '    url = "https://api.deepseek.com/v1/chat/completions"\n'
        "    return urllib.request.urlopen(url, data=prompt.encode())\n")})
    check("a real string literal naming a census host still FAILS"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the file, line and host printed",
          "backend/sender.py:5: api.deepseek.com" in out, out)
    check("... and the run reports one unaccounted mention",
          "1 unaccounted host mention(s)" in out, out)


def t_a_host_built_into_an_fstring_still_fails():
    code, out, root = _prose({"backend/fstring.py": (
        "def url(model):\n"
        '    return f"https://api.openai.com/v1/models/{model}"\n')})
    check("a host built into an f-string still FAILS"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the host printed", "backend/fstring.py:2: api.openai.com" in out,
          out)


def t_a_host_built_by_concatenation_still_fails():
    code, out, root = _prose({"backend/concat.py": CONCAT_SOURCE})
    check("a host built by + across two literals still FAILS"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the host printed", "backend/concat.py:1: api.deepseek.com" in out,
          out)
    check("... and the old raw-text scan could not have seen it: the fixture's"
          " own source does not carry the joined host",
          "api.deepseek.com" not in CONCAT_SOURCE, CONCAT_SOURCE)


def t_a_host_split_over_adjacent_literals_still_fails():
    code, out, root = _prose({"backend/adjacent.py": ADJACENT_SOURCE})
    check("a host split over two ADJACENT literals still FAILS"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the host printed", "backend/adjacent.py:1: api.github.com" in out,
          out)
    check("... and that joined host is not in the fixture's source text either",
          "api.github.com" not in ADJACENT_SOURCE, ADJACENT_SOURCE)


def t_a_module_level_constant_holding_a_url_still_fails():
    code, out, root = _prose({"backend/constant.py": (
        'ISSUES_URL = "https://api.github.com/repos/owner/repo/issues"\n'
        "\n"
        "\n"
        "def issue(number):\n"
        "    return ISSUES_URL + \"/\" + str(number)\n")})
    check("a module-level constant holding a URL still FAILS"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the file and line", "backend/constant.py:1: api.github.com" in out,
          out)


def t_an_unlisted_new_host_in_a_real_call_still_fails():
    """The review's own case: `requests.get("https://evil.example")`.

    HOSTS is a closed census - a host is a mention only once the census names it,
    exactly as before this change - so the test adds the host the 2026-11-16
    audit would have added and edits nothing else. The point proved is the one
    the review asked for: a REAL CALL with a URL argument fails; a docstring in
    the same fixture does not.
    """
    saved = G.HOSTS
    try:
        G.HOSTS = saved + ("evil.example",)
        code, out, root = _prose({"backend/caller.py": (
            '"""caller.py - documentation: https://evil.example is not reachable."""\n'
            "\n"
            "import requests\n"
            "\n"
            "\n"
            "def send():\n"
            '    return requests.get("https://evil.example/collect")\n')})
    finally:
        G.HOSTS = saved
    check("requests.get(\"https://evil.example\") FAILS once the census names it"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... quoting the real call's line, not the docstring's",
          "backend/caller.py:7: evil.example" in out
          and "backend/caller.py:1: evil.example" not in out, out)


def t_a_file_that_asks_the_gate_in_code_is_not_a_violation():
    code, out, root = _prose({"backend/wired.py": (
        "from jarvis_egress_gate import check_egress\n"
        "\n"
        'URL = "https://api.github.com/users/me"\n'
        "\n"
        "\n"
        "def read():\n"
        '    return check_egress("wired", URL, None, "read")\n')})
    check("a file whose code asks check_egress is not a violation"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... and it is reported as wired, not as allow-listed",
          "1 name check_egress in code, 0 are on the allow-list" in out, out)


def t_prose_naming_check_egress_is_not_wiring():
    code, out, root = _prose({"backend/pretender.py": (
        '"""pretender.py - this module asks jarvis_egress_gate.check_egress."""\n'
        "\n"
        'URL = "https://api.github.com/users/me"\n'
        "\n"
        "\n"
        "def read():\n"
        "    # check_egress is called by the caller, honestly\n"
        "    return URL\n")})
    check("check_egress in a docstring and a comment is NOT wiring"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... the host in real code is the unaccounted mention",
          "backend/pretender.py:3: api.github.com" in out, out)


def t_a_listed_file_passes_with_its_written_reason():
    code, out, root = _prose(
        {"backend/known.py": 'URL = "https://api.github.com/users/me"\n'},
        allowed={"backend/known.py": "a fixture row; opens no socket"})
    check("a listed file passes on its written reason"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... and the allow-list is what accounted for it",
          "1 are on the allow-list with a reason" in out, out)


def t_an_allow_list_entry_whose_host_is_only_prose_is_stale():
    code, out, root = _prose(
        {"backend/prose_only.py": (
            '"""prose_only.py - the export was tested against claude.ai."""\n'
            "answer = 1\n")},
        allowed={"backend/prose_only.py": "the host is in a comment; opens no socket"})
    check("an entry whose host now lives only in prose is reported STALE"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... with the reason it is no longer true",
          "backend/prose_only.py is on the allow-list but no longer names a cloud"
          " host in code" in out, out)


def t_an_allow_list_entry_for_a_missing_file_is_reported():
    code, out, root = _prose({"backend/present.py": "answer = 1\n"},
                             allowed={"backend/gone.py": "a reason that outlived its file"})
    check("an entry for a file that is not in the tree is reported"
          " (tree: a temporary fixture folder)", code == 1, (code, out))
    check("... naming the missing path",
          "backend/gone.py is on the allow-list but is not in this checkout" in out,
          out)


def t_a_listed_file_still_covers_its_byte_identical_base_copy():
    module = ('URL = "https://api.github.com/users/me"\n'
              "\n"
              "\n"
              "def read():\n"
              "    return URL\n")
    code, out, root = _prose(
        {"backend/twinned.py": module, "jarvis-backend/twinned.py": module},
        allowed={"backend/twinned.py": "a fixture row; opens no socket"})
    check("a listed backend file still covers its byte-identical base copy"
          " (tree: a temporary fixture folder)", code == 0, (code, out))
    check("... so both copies are counted as allow-listed",
          "2 are on the allow-list with a reason" in out, out)


def t_this_checkout_is_green_and_the_census_is_read_back():
    """The same walk, on the REAL tree, and the line it prints is parsed.

    Nothing here writes to the repository: the checker only reads. The counts
    are this run's own report, checked for internal agreement rather than
    pinned to a number that would need editing every time a file lands.
    """
    said: list[str] = []
    code = G.main(argv=[], repo=G.REPO, allowed=None, say=said.append)
    out = "\n".join(said)
    check(f"this checkout ({G.REPO}) is GREEN under the AST walk", code == 0,
          out[-3000:])
    match = re.search(
        r"(\d+) file\(s\) name one of the (\d+) outbound hosts in real code: "
        r"(\d+) name check_egress in code, (\d+) are on the allow-list with a reason",
        out)
    check("... and it reports its census line", match is not None, out[-3000:])
    if match is None:
        return
    files, hosts, wired, listed = (int(n) for n in match.groups())
    allow_paths = re.search(r"The allow-list is (\d+) exact path", out)
    ignored = re.search(r"ignored (\d+) that are documentation only", out)
    mentions = re.search(r"counted (\d+) host mention\(s\) in real code", out)
    check("... the file count is wired + allow-listed",
          files == wired + listed, (files, wired, listed))
    check("... every allow-list path is a real entry with a written reason",
          allow_paths is not None and int(allow_paths.group(1)) == len(G.ALLOWED)
          and all(reason.strip() for reason in G.ALLOWED.values()),
          (allow_paths.group(1) if allow_paths else None, len(G.ALLOWED)))
    check("... it says how much documentation it ignored, and how many mentions"
          " it did count", ignored is not None and mentions is not None,
          (ignored.group(0) if ignored else None,
           mentions.group(0) if mentions else None))
    print(f"\n    tree: this checkout ({G.REPO})")
    print(f"    accounted: {files} file(s) over {hosts} census hosts - "
          f"{wired} wired + {listed} allow-listed ({len(G.ALLOWED)} paths); "
          f"{mentions.group(1) if mentions else '?'} code mention(s), "
          f"{ignored.group(1) if ignored else '?'} documentation mention(s) ignored")


def main() -> int:
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("t_") and callable(value)]
    for test in tests:
        print(f"--- {test.__name__} ---")
        try:
            test()
        except Exception:                              # noqa: BLE001
            FAILED.append(test.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
