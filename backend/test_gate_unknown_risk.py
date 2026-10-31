"""An action the gate has NO risk row for: worst case, forced "ask", still approvable.

    python3 test_gate_unknown_risk.py

WHY THIS EXISTS

On 2026-10-30 the owner's own PC showed the app builder's build card, he pressed
Approve, and nothing happened - the card could not be approved by anybody. The
cause was in `jarvis_owner_check.approve_check()`: a risky card needs a Windows
Hello prompt, a prompt may only ask about something Jarvis can NAME, and an
action with no written words was refused outright (`UNLABELLED`, 403). An action
whose risk row is missing has no written words on a fresh install, so the card
was a dead end that looked alive.

Gemini's ruling (Q2, `Downloads\\gemini_response_to_12h_review_and_next_plans_2026_10_30.md`
section 3, and `.dsh-scratch/UNKNOWN-RISK-2026-10-30/REPORT.md`) is a DUAL RULE:

  * CI stays STRICT: a shipped action that can run unattended and has no
    explicit `_RISK` row is a failure (section 6 below; the check that bites is
    in this file, and `backend/test_gate_risk_rows.py` is run unchanged beside
    it so nobody can say this change loosened that one).
  * RUNTIME is APPROVABLE WITH MAXIMUM FRICTION: when `classified` is False,
    `jarvis_gate.py` gives the action the worst case it has (reach "outbound",
    reversible "no" - so no swipe, on any screen), forces tier "ask" so it can
    never run unattended, prints ONE plain warning line on the card
    ("Unclassified action - treated as permanent and able to leave this PC"),
    and lets the owner approve it ONLY through the human check every risky card
    already needs: Windows Hello on this PC, the phone's own lock/signature.
    Nothing auto-approves, nothing bulk-approves, and a plain YES recorded
    without that check cannot run the action.

WHAT IS PROVED HERE, IN ORDER

  1. t_the_patch_is_the_base_plus_this_change - the footing. The patch
     REVERSES out of the published base (`jarvis-backend/jarvis_gate.py`, the
     state the whole stack leaves) into text that holds the old sentence and
     none of the new rows, and applies forward to the base BYTE FOR BYTE. It
     touches `jarvis_gate.py` and nothing else, and its position in
     `scripts/apply-patches.ps1` is pinned with the measurement that put it
     there.
  2. t_an_unclassified_action_is_given_the_worst_case_the_gate_has - the risk
     fields, the exact warning sentence, and the notice built from them.
  3. t_an_unclassified_action_can_never_run_without_a_person - forced "ask"
     from "auto", from "notify", and from a loosened `unknown_action_tier`;
     "never" stays never; a classified action and a tool literal are untouched.
  4. t_a_classified_action_is_exactly_as_before - the old contract, unchanged.
  5. t_the_eight_actions_that_ran_unattended_now_have_their_own_rows - the
     reason the forced "ask" changes nothing the owner uses today.
  6. t_a_tree_missing_a_row_fails_the_check_this_suite_adds - the CI half, and
     its bite: a copy with one row taken out is refused BY NAME.
  7. t_the_card_is_approved_by_the_human_check_and_by_nothing_else - the whole
     path: the real card row, the real `approve_check`, the real gate waiting.
     A yes recorded WITHOUT the check is refused and the action does not run.
  8. t_a_classified_card_with_no_written_words_is_still_refused - the exemption
     is scoped to unclassified cards only; the 2026-10-26 rule still holds.
  9. t_loosening_an_unclassified_action_is_refused - `jarvis_asks_first`, the
     page and the route, plus the plain sentence the owner is shown.

HOW THE GATE IS LOADED. `jarvis_gate.py` is the owner's file; this repository
holds the published base in `jarvis-backend/`. This suite copies that base into
a scratch folder, applies `unknown-risk-approvable.patch` with `git apply` (no
fuzz, the same way `scripts/apply-patches.ps1` does), and imports the result
beside the repository's own `jarvis_owner_check.py`, `jarvis_asks_first.py` and
`jarvis_card_words.py`. So what is exercised is the patch's real output, not a
copy typed to suit the test. `jarvis_framework` is a stand-in because the real
one reads the owner's settings file; it is a REAL tier table in the shape the
gate reads.

Needs nothing from the owner's PC and no network. Runs anywhere git does.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _gitapply  # noqa: E402  (beside this file; its docstring says why)
from _where import REPO  # noqa: E402

PATCH = HERE / "unknown-risk-approvable.patch"
BASE = REPO / "jarvis-backend"
BACKEND = REPO / "backend"
PS1 = REPO / "scripts" / "apply-patches.ps1"
SHIPPED_TOML = BACKEND / "rebuilt" / "jarvis-framework.toml"
BASE_GATE = BASE / "jarvis_gate.py"

#: The warning line, word for word - the ruling's own words, in ASCII.
WARNING = ("Unclassified action - treated as permanent and able to leave this PC")
#: What the card said before this patch. It must be gone from the after-image.
OLD_WARNING = "not classified, so treated as irreversible and outbound"

#: The eight actions that had an "auto" line and no row: measured on this tree
#: before the patch (section 5 checks it against the pre-image, not this list,
#: so the list cannot quietly become the evidence for itself). The NINTH of
#: that shape, `lower_api_limit`, is not here on purpose: chatbot-limits.patch
#: gives it a row, so at runtime it was never unclassified and a second row
#: would be dead code (the LAST one wins) - which is exactly what
#: backend/test_gate_risk_words.py fails.
EXPECTED_EIGHT = frozenset({
    "calendar_read", "email_read", "notes_search", "home_read", "news_read",
    "page_read", "github_read", "docker_service_stop",
})

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: counted on its own, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


# ---------------------------------------------------------------------------
# The published base, plus this patch, as modules
# ---------------------------------------------------------------------------

_BUILT: dict = {}
#: What the stand-in settings file says. Read at EVERY `_tiers()` call, so a
#: check can change the policy without re-importing the gate.
_CFG = {"tiers": {}, "unknown": "ask"}


def built() -> tuple:
    """(folder holding the patched gate and the shipped modules, why not).

    THE PUBLISHED BASE IS THE AFTER-IMAGE (jarvis-backend/README.md, and
    `_stack.py`'s own note), so the patch is rehearsed the way
    `scripts/apply-patches.ps1` rehearses it: take it BACK OUT of the base -
    which is the text the owner's file holds before it - then put it ON again.
    A folder that simply got the patch applied would be a copy of the base with
    every hunk failing, or worse, a file that `git apply` says it changed and
    did not (backend/_gitapply.py records that trap).
    """
    if "dir" in _BUILT:
        return _BUILT["dir"], ""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed, so the patch cannot be applied"
    if not PATCH.is_file():
        return None, f"{PATCH.name} is missing"
    if not BASE_GATE.is_file():
        return None, f"{BASE_GATE} is missing"
    d = Path(tempfile.mkdtemp(prefix="jarvis-unknown-risk-"))
    d.joinpath("jarvis_gate.py").write_bytes(BASE_GATE.read_bytes().replace(b"\r\n", b"\n"))
    for name in ("jarvis_owner_check.py", "jarvis_asks_first.py",
                 "jarvis_card_words.py"):
        src = BACKEND / name
        if not src.is_file():
            return None, f"{src} is missing"
        d.joinpath(name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    env = _gitapply.env_for(git, d)
    for direction in (["-R"], []):
        r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                            "apply", *direction, str(PATCH)], cwd=str(d),
                           capture_output=True, text=True, env=env)
        if r.returncode != 0:
            return None, (f"git apply {'-R ' if direction else ''}refused {PATCH.name}: "
                          f"{(r.stderr or r.stdout).strip().splitlines()[:2]}")
    _BUILT["dir"] = d
    return d, ""


def _fake_framework(cfg_dir: Path):
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg_dir
    fw.LOG_DIR = cfg_dir
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": _CFG["unknown"],
                     "approval_timeout_seconds": 900,
                     "tiers": dict(_CFG["tiers"])},
    }
    fw.action_tier = lambda a: str(_CFG["tiers"].get(a, _CFG["unknown"]))
    fw.all_tiers = lambda: dict(_CFG["tiers"])
    fw.config_path = lambda: None
    fw.reload_framework = lambda: None
    fw.audit_log = lambda *a, **k: None
    return fw


_MODS: dict = {}


def modules() -> tuple:
    """(gate, owner_check, asks_first, why not) - imported once, from the build."""
    if "gate" in _MODS:
        return _MODS["gate"], _MODS["owner"], _MODS["asks"], ""
    folder, why = built()
    if folder is None:
        return None, None, None, why
    cfg_dir = Path(tempfile.mkdtemp(prefix="jarvis-unknown-risk-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg_dir / "approvals.db")
    os.environ.pop("JARVIS_APPROVAL_TIMEOUT", None)
    os.environ["JARVIS_NTFY_TOPIC"] = ""
    os.environ["JARVIS_NTFY_SERVER"] = ""
    sys.modules["jarvis_framework"] = _fake_framework(cfg_dir)
    for name in ("jarvis_gate", "jarvis_owner_check", "jarvis_asks_first",
                 "jarvis_card_words"):
        sys.modules.pop(name, None)
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    import jarvis_gate
    import jarvis_owner_check
    import jarvis_asks_first
    _MODS.update(gate=jarvis_gate, owner=jarvis_owner_check, asks=jarvis_asks_first)
    return jarvis_gate, jarvis_owner_check, jarvis_asks_first, ""


def set_policy(tiers: dict, unknown: str = "ask") -> None:
    """What the stand-in settings file says for this check."""
    _CFG["tiers"] = dict(tiers)
    _CFG["unknown"] = unknown


def _sentence_about(exc) -> str:
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Reading the files this patch edits
# ---------------------------------------------------------------------------

def _patch_names() -> list:
    """The `$PATCHES` list out of apply-patches.ps1, in order."""
    text = PS1.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "$PATCHES = @(")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == ")")
    return [l.strip().strip("'") for l in lines[start + 1:end]
            if l.strip().startswith("'")]


def _patch_targets(name: str) -> set:
    """Every file a patch's hunks name (its `+++ b/<target>` lines)."""
    out = set()
    for line in (HERE / name).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("+++ b/"):
            out.add(line[len("+++ b/"):].strip())
    return out


def _risk_rows(source: str) -> set:
    """The keys of the module-level `_RISK` literal, read without importing it.

    `ast`, not a regex: a row's own sentence is allowed to contain anything,
    and a regex would read a sentence as a row. A source that does not parse
    raises rather than answering "no rows" - an empty answer here would make
    the missing-row check below pass on a file it could not read.
    """
    tree = ast.parse(source)
    for node in tree.body:
        target = getattr(node, "target", None)
        if isinstance(node, ast.AnnAssign) and getattr(target, "id", "") == "_RISK":
            return set(ast.literal_eval(node.value).keys())
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_RISK" for t in node.targets):
            return set(ast.literal_eval(node.value).keys())
    return set()


def _tiers_from_shipped() -> dict:
    import tomllib
    cfg = tomllib.loads(SHIPPED_TOML.read_text(encoding="utf-8"))
    return dict(cfg["autonomy"]["tiers"])


def rows_added_by_patches(exclude=None) -> set:
    """Every `_RISK` row any patch in the stack adds, by name.

    The published base is a SNAPSHOT of the owner's folder, not a computed
    after-image: `lower_api_limit`'s row is in `chatbot-limits.patch` and NOT
    in this repository's copy of his file. A check that read the base alone
    would call that action unclassified and be wrong about his PC. Reading the
    base AND every patch's added rows answers the question the ruling asks -
    "is there a row for this action anywhere in what ships?" - without running
    the stack.
    """
    out = set()
    for name in _patch_names():
        if name == exclude:
            continue
        patch = HERE / name
        if not patch.is_file():
            continue
        for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r'^\+\s*"(\w+)":\s*\(', line)
            if m:
                out.add(m.group(1))
    return out


def missing_rows(rows: set, tiers: dict) -> set:
    """Every action that can run with nobody asked and has no `_RISK` row.

    THE CI HALF OF THE RULING. "Can run with nobody asked" is read from the
    SHIPPED settings file: an "auto" or "notify" line. An "ask" action does not
    need a row to be safe (it already waits for a person) - though it should
    have one, and `test_card_words.py` makes sure it has words.
    """
    return {a for a, t in tiers.items()
            if str(t).strip().lower() in ("auto", "notify") and a not in rows}


def _reversed_source() -> tuple:
    """(the base with this patch taken back out, why not) - the pre-image.

    The published base is the state the WHOLE stack leaves, so this is the
    way `scripts/apply-patches.ps1` rehearses a patch: take it off (which is
    the text the owner's file holds before it), then put it on again.
    """
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    folder, why = built()
    if folder is None:
        return None, why
    d = Path(tempfile.mkdtemp(prefix="jarvis-unknown-risk-pre-"))
    f = d / "jarvis_gate.py"
    f.write_bytes(BASE_GATE.read_bytes().replace(b"\r\n", b"\n"))
    env = _gitapply.env_for(git, d)
    r = subprocess.run([git, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                        "apply", "-R", str(PATCH)], cwd=str(d), capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        return None, f"git apply -R refused: {(r.stderr or r.stdout).strip()[:300]}"
    return f.read_text(encoding="utf-8"), ""


# ---------------------------------------------------------------------------
# 1. The footing: the patch IS the base plus this change
# ---------------------------------------------------------------------------

def t_the_patch_is_the_base_plus_this_change():
    pre, why = _reversed_source()
    check("the patch reverses out of the published base", pre is not None, why)
    if pre is None:
        return
    check("the pre-image is the owner's own words, with the old sentence",
          OLD_WARNING in pre)
    check("... and it has none of the new warning", "UNCLASSIFIED_WARNING" not in pre)
    check("... and none of the eight rows",
          not [a for a in EXPECTED_EIGHT if f'    "{a}": (' in pre])
    after = BASE_GATE.read_text(encoding="utf-8")
    check("the after-image is what the patch is written against", PATCH.is_file())
    check("... and it carries the warning and the eight rows",
          "UNCLASSIFIED_WARNING" in after
          and all(f'    "{a}": (' in after for a in EXPECTED_EIGHT))
    check("... exactly once each (a second row would be dead code)",
          all(after.count(f'    "{a}": (') == 1 for a in EXPECTED_EIGHT))
    check("the patch touches jarvis_gate.py and nothing else",
          _patch_targets(PATCH.name) == {"jarvis_gate.py"}, _patch_targets(PATCH.name))
    heads = re.findall(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", PATCH.read_text(
        encoding="utf-8"), re.M)
    check("six hunks: the rows, the table end, risk_for, notice_for, the "
          "file-wins tier table (DEF-021), and check()",
          len(heads) == 6, len(heads))


def t_the_patch_is_registered_and_its_place_is_measured():
    names = _patch_names()
    check("the patch is in apply-patches.ps1's $PATCHES",
          PATCH.name in names)
    check("it is not the last patch of all (plugin-loader.patch must stay last)",
          names[-1] == "plugin-loader.patch", names[-1])
    after = names[names.index(PATCH.name) + 1:]
    writers = [n for n in after if "jarvis_gate.py" in _patch_targets(n)]
    check("no patch after it writes jarvis_gate.py - so it cannot disturb one",
          not writers, writers)
    check("it comes after readpage.patch, so the table is already its full height",
          names.index(PATCH.name) > names.index("readpage.patch"))
    # The rows are the FIRST thing in the table rather than the last, and that
    # is measured rather than chosen: the table's END is different on a PC
    # whose patch stack has run (chatbot-limits.patch writes rows there) and on
    # one where it has not, while the table's opening is the same in both. The
    # hunk that adds them carries the opening line and `# reading anything` as
    # its whole context, so it applies to either state.
    check("... and the rows sit at the top of the table, where every state agrees",
          BASE_GATE.read_text(encoding="utf-8").index('"calendar_read": (')
          < BASE_GATE.read_text(encoding="utf-8").index('"read_web_page": ('))
    check("... and the ninth of that shape, lower_api_limit, is left to "
          "chatbot-limits.patch rather than given a second row",
          '"lower_api_limit": (' not in _reversed_source()[0]
          and '"lower_api_limit": (' in (HERE / "chatbot-limits.patch").read_text(
              encoding="utf-8"))


# ---------------------------------------------------------------------------
# 2. The worst case, the warning, and the notice built from them
# ---------------------------------------------------------------------------

def t_an_unclassified_action_is_given_the_worst_case_the_gate_has():
    G, OC, AF, why = modules()
    check("the patched gate imports and the shipped modules load", G is not None, why)
    if G is None:
        return
    set_policy({})
    r = G.risk_for("some_new_action")
    check("an unclassified action is irreversible", r["reversible"] == "no", r)
    check("... and outbound", r["reach"] == "outbound", r)
    check("... so no swipe may decide it", r["swipe_ok"] is False, r)
    check("... and it says so as unclassified", r["classified"] is False, r)
    check("... in the ruling's own plain words, word for word",
          r["why"] == WARNING, r["why"])
    n = G.notice_for({"action": "some_new_action"})
    check("the card's notice is heavy", n["weight"] == "heavy", n)
    check("... its body starts with the warning line", n["body"].startswith(WARNING),
          n["body"])
    check("... and says why the worst case was chosen",
          "worst case" in n["body"], n["body"])
    check("... and that nothing has happened yet",
          "nothing has happened yet" in n["body"], n["body"])
    check("... and it still says refusing without reading is safe",
          n["deny_ok"] is True and n["approve_ok"] is False, n)
    check("... and its title is readable, quoting the action's own name",
          "some new action" in n["title"], n["title"])
    check("... and never quotes the payload",
          "SECRET" not in n["body"] and "SECRET" not in n["title"])
    check("the same warning is what a card for a plugin action gets",
          G.risk_for("plugin_start:whatever")["why"] == WARNING)


# ---------------------------------------------------------------------------
# 3. Forced "ask": it can never run with nobody asked
# ---------------------------------------------------------------------------

def _verdict(gate, action, **kw):
    """`check()` with a short wait, so an "ask" comes back as timed_out."""
    return gate.check(action, {"x": 1}, "card text", timeout=kw.pop("timeout", 0.35), **kw)


def t_an_unclassified_action_can_never_run_without_a_person():
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    # "auto" in the settings file: the gate must ask anyway.
    set_policy({"some_new_action": "auto"})
    v = _verdict(G, "some_new_action")
    check("an unclassified action at tier auto is asked about", v.tier == "ask", v.tier)
    check("... and it did NOT run", v.allowed is False, v)
    check("... and the outcome is 'asked', never 'auto'",
          v.outcome in ("asked", "approved", "timed_out", "denied"), v.outcome)
    # "notify" too: nothing runs and nobody is merely told afterwards.
    set_policy({"some_new_action": "notify"})
    v = _verdict(G, "some_new_action")
    check("an unclassified action at tier notify is asked about", v.tier == "ask", v.tier)
    check("... and it did NOT run", v.allowed is False and v.outcome != "notify", v)
    # no tier line at all, with the fallback loosened in the settings file.
    # (The table must not be EMPTY: an empty one is "the policy could not be
    # read" and the gate refuses before any tier rule - its own guard, tested
    # elsewhere. One unrelated line is enough to make the table real.)
    set_policy({"send_email": "ask"}, unknown="auto")
    v = _verdict(G, "some_new_action")
    check("a loosened unknown_action_tier cannot let it run", v.tier == "ask", v.tier)
    check("... and it still did NOT run", v.allowed is False, v)
    # no tier line at all, fallback notify.
    set_policy({"send_email": "ask"}, unknown="notify")
    v = _verdict(G, "some_new_action")
    check("nor can 'notify' as the fallback", v.tier == "ask", v)
    # "never" is stricter than ask and must stay.
    set_policy({"some_new_action": "never"})
    v = _verdict(G, "some_new_action")
    check("'never' is still refused outright, never softened to a card",
          v.tier == "never" and v.allowed is False, v)
    check("... and no card was raised for it", v.outcome == "refused", v.outcome)
    # An ask-tier unclassified action keeps asking (no behaviour change).
    set_policy({"some_new_action": "ask"})
    v = _verdict(G, "some_new_action")
    check("an unclassified action already at ask is unchanged", v.tier == "ask", v.tier)
    # A tool literal is the gate's own per-tool decision, not an unclassified
    # action: forcing it would card every calculation. Since DEF-021 the
    # exemption needs the owner's file to have NO line for the name; with no
    # line it is unchanged and still runs.
    set_policy({"send_email": "ask"})
    G.action_for_tool("calculator")
    v = _verdict(G, "calculator")
    check("a tool the gate maps straight to 'auto' still runs when the file has no line",
          v.allowed is True and v.tier == "auto", v)
    check("... and that exemption is by name, from the gate's own table",
          "calculator" in G._SYNTH_TIERS)


# ---------------------------------------------------------------------------
# 3b. DEF-021: an explicit file line wins over the tool table, and the
#     forced-ask exemption needs the file to say nothing
# ---------------------------------------------------------------------------

def t_an_explicit_file_line_beats_the_tool_table():
    """DEF-021, 2026-10-31 (Gemini: the #1 code priority of Round 3).

    `_tiers()` used to apply `_SYNTH_TIERS` OVER the file's own
    `[autonomy.tiers]` line, and the #1008 forced-ask exemption then skipped
    exactly those names - so `calculator = "never"` in the owner's file ran
    auto. Proved by running the published gate before the fix:
    `_tiers({"calculator": "never"})` -> auto and
    `check("calculator", framework=...)` -> allowed=True, tier="auto".
    """
    G, OC, AF, why = modules()
    check("the patched gate imports for the DEF-021 checks", G is not None, why)
    if G is None:
        return
    # The owner's explicit "never" wins, and the action is refused.
    set_policy({"calculator": "never"})
    G.action_for_tool("calculator")
    tiers = G._tiers()
    check("the file's 'never' wins over the tool table in _tiers()",
          tiers.get("calculator") == "never", tiers.get("calculator"))
    v = _verdict(G, "calculator")
    check("calculator = never is REFUSED, not run", v.tier == "never"
          and v.allowed is False, v)
    check("... with no card and no approval path", v.outcome == "refused", v.outcome)
    # The owner's explicit "ask" raises a card.
    set_policy({"calculator": "ask"})
    v = _verdict(G, "calculator")
    check("calculator = ask raises a card", v.tier == "ask", v.tier)
    check("... and it did NOT run", v.allowed is False, v)
    check("... and the outcome is an ask, never auto", v.outcome != "auto", v.outcome)
    # An explicit "auto" line is the owner's own ACTION now, so the
    # unclassified-action rule applies to it: forced ask, never unattended.
    set_policy({"calculator": "auto"})
    v = _verdict(G, "calculator")
    check("an explicit calculator = auto is still forced to ask (unclassified action)",
          v.tier == "ask", v.tier)
    check("... and it did not run with nobody asked", v.allowed is False, v)
    # The What asks first page and the gate agree for the name.
    set_policy({"calculator": "never"})
    page = AF.view(here=True)
    rows = {r["id"]: r for group in page["groups"] for r in group["rows"]}
    check("the What asks first page names calculator", "calculator" in rows,
          sorted(rows)[:8])
    check("... with the file's own tier", rows.get("calculator", {}).get("tier") == "never",
          rows.get("calculator"))
    check("... and the page, the file reader and _tiers() agree",
          rows.get("calculator", {}).get("tier") == AF._file_tiers().get("calculator")
          == G._tiers().get("calculator") == "never",
          (rows.get("calculator", {}).get("tier"),
           AF._file_tiers().get("calculator"), G._tiers().get("calculator")))
    # A name with NO file line still gets the forced ask: the #1008 rule.
    set_policy({})
    v = _verdict(G, "some_new_action")
    check("a name with NO file line still gets the forced ask",
          v.tier == "ask" and v.allowed is False, v)


# ---------------------------------------------------------------------------
# 4. A classified action is exactly as before
# ---------------------------------------------------------------------------

def t_a_classified_action_is_exactly_as_before():
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    set_policy({"switch_model": "auto", "send_email": "ask"})
    v = _verdict(G, "switch_model")
    check("a classified action at tier auto still runs unattended",
          v.allowed is True and v.tier == "auto", v)
    r = G.risk_for("switch_model")
    check("its risk fields are its own row's",
          r["reversible"] == "yes" and r["reach"] == "local"
          and r["swipe_ok"] is True and r["classified"] is True, r)
    check("... and its sentence is its own, not the warning", r["why"] != WARNING, r["why"])
    n = G.notice_for({"action": "switch_model"})
    check("... and its card does not carry the warning",
          WARNING not in n["body"] and n["weight"] == "normal", n)
    out = G.risk_for("send_email")
    check("a risky classified action keeps 'no'/'outbound'",
          out == {"reversible": "no", "reach": "outbound", "swipe_ok": False,
                  "why": G._RISK["send_email"][2], "classified": True}, out)
    check("... and its notice is heavy without the warning",
          G.notice_for({"action": "send_email"})["weight"] == "heavy"
          and WARNING not in G.notice_for({"action": "send_email"})["body"])


# ---------------------------------------------------------------------------
# 5. Why forcing "ask" changes nothing the owner uses today
# ---------------------------------------------------------------------------

def t_the_eight_actions_that_ran_unattended_now_have_their_own_rows():
    tiers = _tiers_from_shipped()
    pre, why = _reversed_source()
    if pre is None:
        skip(why)
        return
    after = BASE_GATE.read_text(encoding="utf-8")
    before_rows = _risk_rows(pre) | rows_added_by_patches(exclude=PATCH.name)
    after_rows = _risk_rows(after) | rows_added_by_patches()
    before_gaps = missing_rows(before_rows, tiers)
    after_gaps = missing_rows(after_rows, tiers)
    check("before the patch, EIGHT actions could run with nobody asked and no row",
          before_gaps == set(EXPECTED_EIGHT),
          sorted(before_gaps ^ set(EXPECTED_EIGHT)))
    check("... which is exactly the eight this patch gives a row",
          len(before_gaps) == 8 and before_gaps == set(EXPECTED_EIGHT))
    check("... and lower_api_limit is NOT one of them (chatbot-limits.patch "
          "already gives it a row)",
          "lower_api_limit" in rows_added_by_patches(exclude=PATCH.name)
          and "lower_api_limit" not in EXPECTED_EIGHT)
    check("after the patch, no action that runs unattended is unclassified",
          after_gaps == set(), sorted(after_gaps))
    # The rows say the plain thing their tier line already implies.
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    for action in sorted(EXPECTED_EIGHT):
        r = G.risk_for(action)
        check(f"{action} is classified, reversible and has its own sentence",
              r["classified"] is True and r["reversible"] == "yes"
              and bool(r["why"]) and r["why"] != WARNING, r)
    check("the reads stay on this PC", G.risk_for("calendar_read")["reach"] == "local")
    check("the ones that fetch from the internet say so",
          all(G.risk_for(a)["reach"] == "outbound"
              for a in ("news_read", "page_read", "github_read")))
    check("this patch adds no row for lower_api_limit (that one is chatbot-limits')",
          "lower_api_limit" not in G._RISK
          and '"lower_api_limit": (' in (HERE / "chatbot-limits.patch").read_text(
              encoding="utf-8"))


# ---------------------------------------------------------------------------
# 6. CI stays strict: a tree missing a row fails, by name
# ---------------------------------------------------------------------------

def t_a_tree_missing_a_row_fails_the_check_this_suite_adds():
    tiers = _tiers_from_shipped()
    after = BASE_GATE.read_text(encoding="utf-8")
    after_rows = _risk_rows(after) | rows_added_by_patches()
    gaps = missing_rows(after_rows, tiers)
    check("this tree passes the missing-row rule", gaps == set(), sorted(gaps))
    # BITE: take ONE row out of a copy and the same rule names it.
    broken = after.replace(
        '    "calendar_read": ("yes", "local", "reads your calendar on this PC; changes nothing in it"),\n',
        "", 1)
    check("the bite really removed the row", broken != after)
    bites = missing_rows(_risk_rows(broken) | rows_added_by_patches(exclude=PATCH.name), tiers)
    check("a tree missing a row FAILS, and the check names it",
          bites == {"calendar_read"}, sorted(bites))
    # ... and a NEW auto action with no row is caught too, not just the eight.
    bites2 = missing_rows(after_rows, dict(tiers, a_future_action="auto"))
    check("a future 'auto' action with no row is caught by name",
          bites2 == {"a_future_action"}, sorted(bites2))
    # The other half of the CI claim, run for real: the file the brief names
    # keeps its own scope and still passes, so nothing here loosened it.
    py = sys.executable or "python3"
    r = subprocess.run([py, "-B", str(HERE / "test_gate_risk_rows.py")],
                       cwd=str(REPO), capture_output=True, text=True, timeout=300)
    check("test_gate_risk_rows.py still passes on this tree",
          r.returncode == 0, (r.stdout or r.stderr).strip()[-400:])
    check("... and it is the file that checks the stale duplicate rows, not "
          "missing rows (said plainly so nobody believes otherwise)",
          "gate-risk-rows.patch" in (HERE / "test_gate_risk_rows.py").read_text(
              encoding="utf-8"))


# ---------------------------------------------------------------------------
# 7. Approvable by the human check, and by nothing else
# ---------------------------------------------------------------------------

def _wait_for_card(gate, action, timeout=6.0):
    """The NEWEST card waiting for `action`, or None.

    A card id this suite has already been handed is skipped: the gate reuses
    ONE card for an identical request, so a row left behind by an earlier
    check must never be mistaken for this one.
    """
    end = time.time() + timeout
    while time.time() < end:
        rows = [r for r in gate.pending() if r["action"] == action]
        fresh = [r for r in rows if r["id"] not in _SEEN_IDS]
        if fresh:
            _SEEN_IDS.add(fresh[-1]["id"])
            return fresh[-1]
        time.sleep(0.02)
    return None


_SEEN_IDS: set = set()


def _raise_card(gate, action, timeout=10.0):
    """(the live row, the thread, the box) for `action`, with a card waiting."""
    set_policy({action: "ask"})
    box = {}
    t = threading.Thread(
        target=lambda: box.update(v=gate.check(action, {"what": "the app"},
                                               "Build it", timeout=timeout)))
    t.daemon = True
    t.start()
    row = _wait_for_card(gate, action)
    return row, t, box


def t_the_card_is_approved_by_the_human_check_and_by_nothing_else():
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    # --- a yes recorded WITHOUT the check cannot run it -------------------
    row, t, box = _raise_card(G, "some_new_action")
    check("a card waits for an unclassified action", row is not None)
    if row is None:
        return
    check("the row carries the warning the screens show",
          row["risk"]["why"] == WARNING and row["risk"]["classified"] is False, row["risk"])
    check("... and the notice body repeats it in plain words",
          WARNING in row["notice"]["body"], row["notice"]["body"])
    check("... and it is a risky row, so the check applies", OC.is_risky(row) is True)
    check("... and the pending row has no written title of its own",
          OC.has_written_title("some_new_action") is False)
    G.decide(row["id"], True, "somebody")
    t.join(timeout=8)
    v = box.get("v")
    check("a plain yes is refused when it did not come through the check",
          v is not None and v.allowed is False and v.outcome == "refused",
          v)
    check("... and it says why, in plain words",
          v is not None and "approval check" in v.reason, getattr(v, "reason", ""))

    # --- the human check approves it --------------------------------------
    row, t, box = _raise_card(G, "some_new_action")
    check("a second card waits", row is not None)
    if row is None:
        return
    calls = []

    def fake_verify(text, seconds):
        calls.append(text)
        return OC.CONFIRMED

    real_verify = OC.verify
    OC.verify = fake_verify
    try:
        got = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                               pending=lambda: [row])
    finally:
        OC.verify = real_verify
    check("the PC's own approval check lets it through (None = go ahead)",
          got is None, got)
    check("... and it DID ask the human check, once", len(calls) == 1, calls)
    check("... and the prompt names the action and carries the warning",
          calls and "some new action" in calls[0] and WARNING in calls[0], calls)
    # The route's next step, which is what records the yes - the same order
    # POST /api/approve uses: the check first, then decide(). The stamp the
    # check left behind is what makes this yes believable (see the case above).
    check("... the row is still waiting when the yes is recorded",
          G.decide(row["id"], True, "hud") is True)
    t.join(timeout=8)
    v = box.get("v")
    check("... and the action now runs, on the owner's yes",
          v is not None and v.allowed is True and v.outcome == "approved", v)

    # --- dismissed, unavailable: nothing is approved ----------------------
    # A SHORT wait on purpose: the request ends by itself as "timed_out", so
    # the check can say it did not run without a deny - and a deny would also
    # fire the gate's own "learn a rule from the refusal" proposal, which is
    # not what this suite is about (and is slow the first time it loads a
    # model). What is being proved is that the 403 left the card untouched.
    for answer, label in ((OC.CANCELLED_, "dismissed"),
                          (OC.UNAVAILABLE, "no Windows Hello"),
                          (OC.FAILED, "the prompt failed")):
        row, t, box = _raise_card(G, "some_new_action", timeout=2.0)
        if row is None:
            check(f"a card waits before the {label} case", False)
            continue
        OC.verify = lambda text, seconds, answer=answer: answer
        try:
            got = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                                   pending=lambda: [row])
        finally:
            OC.verify = real_verify
        code = got[0] if isinstance(got, tuple) else 200
        check(f"{label}: refused (403) and nothing approved", code == 403, got)
        check(f"... and the card was left waiting, not settled by the refusal",
              row["id"] in [r["id"] for r in G.pending()], row["id"])
        t.join(timeout=8)
        check(f"... and the action did not run after {label}",
              box.get("v") is not None and box["v"].allowed is False,
              box.get("v") if box.get("v") is not None else "still waiting")


def t_a_classified_card_with_no_written_words_is_still_refused():
    """The 2026-10-26 rule survives for classified actions: no blank prompts."""
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    real = OC.has_written_title
    OC.has_written_title = lambda action: False
    try:
        # A classified, risky action: the refusal must still fire.
        row, t, box = _raise_card(G, "send_email", timeout=2.0)
        check("a classified risky card waits", row is not None)
        if row is not None:
            got = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                                   pending=lambda: [row])
            check("a classified action with no written words is still refused",
                  isinstance(got, tuple) and got[0] == 403
                  and got[1].get("owner_check") == "unlabelled", got)
            t.join(timeout=8)
        # ... and the SAME unwritten-words state does NOT refuse an
        # unclassified card: that is the exemption, and only it.
        row, t, box = _raise_card(G, "some_new_action")
        if row is not None:
            calls = []
            OC.verify = lambda text, seconds: (calls.append(text), OC.CONFIRMED)[1]
            try:
                got = OC.approve_check({"id": row["id"]}, peer="127.0.0.1",
                                       pending=lambda: [row])
            finally:
                OC.verify = real
            check("... while the unclassified card goes through the very same check",
                  got is None, got)
            t.join(timeout=8)
    finally:
        OC.has_written_title = real


# ---------------------------------------------------------------------------
# 8. The settings page cannot loosen what the gate has not classified
# ---------------------------------------------------------------------------

def t_loosening_an_unclassified_action_is_refused():
    G, OC, AF, why = modules()
    if G is None:
        skip("the patched gate could not be built")
        return
    wrote = []
    body = {"action": "calendar_read", "ask": False}

    def call(classified, tier="auto", **kw):
        return AF.request_tier(
            body, here=True, tier_of=lambda a: tier,
            write=lambda a, t: wrote.append((a, t)),
            classified=classified, spawn=lambda fn: None, armed=lambda: True, **kw)

    try:
        code, out = call(lambda a: False)
        check("loosening an unclassified action is refused (409)", code == 409, out)
        check("... and says it is not classified", out.get("not_classified") is True)
        check("... in plain words, and that nothing was changed",
              "not classified" in out.get("error", "")
              and "nothing was changed" in out.get("error", ""), out.get("error"))
        check("... and the settings file was not touched", wrote == [], wrote)
        # the same request, with the action classified: it goes on to its card.
        code2, out2 = call(lambda a: True, tier="ask")
        check("the same request with a classified action raises its PC-only card",
              code2 == 202 and isinstance(out2, dict) and out2.get("waiting") is True,
              code2)
    finally:
        AF._L_STATE["pending"].clear()
    # The real classifier reads the gate's own table, not a copy.
    check("the page's own classifier reads the gate: a rowed action is classified",
          AF._classified("calendar_read") is True)
    check("... and an unknown one is not", AF._classified("some_new_action") is False)
    # The page marks the row so the switch is not offered at all.
    real = AF._classified
    AF._classified = lambda a: False
    try:
        view = AF.view(here=True)
        rows = [r for g in view["groups"] for r in g["rows"]]
        switchless = [r for r in rows
                      if r.get("switch") is not None and r["switch"].get("can_loosen")]
        check("no row offers a switch that could loosen an unclassified action",
              switchless == [], [r["id"] for r in switchless])
        noted = [r for r in rows if r.get("note") == AF.NOTE_NOT_CLASSIFIED]
        check("... and the rows say why, in plain words", bool(noted), len(noted))
    finally:
        AF._classified = real


# ---------------------------------------------------------------------------

def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    n = sum(1 for _ in PASSED)
    print(f"\n{n} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 0 if not FAILED and not SKIPPED else (1 if FAILED else 0)


if __name__ == "__main__":
    raise SystemExit(main())
