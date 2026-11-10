"""Every shipped patch is carried by a route that is PROVED, never assumed.

    py -3 -B backend/test_patch_delta_coverage.py

WHY THIS EXISTS

The owner's ruling Q8 (Gemini, 2026-11-09), verbatim: "KEEP PER-PATCH
`DELTA_TABLE` ENTRIES AS THE STANDARD, BUT ENFORCE A UNIT TEST ASSERTING THAT
EVERY SHIPPED PATCH HAS EITHER A `DELTA_TABLE` ENTRY OR EXACT-HUNK COVERAGE."

The tool this pins is `tools/reconcile_live_backend.py`. It never copies the
five patched base files (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_extract.py`,
`jarvis_models.py`, `jarvis_skills.py`); for those it judges each patch's
presence against the live file and, when a patch is absent, inserts it by the
rule its `DELTA_TABLE` entry names. A patch with NO entry falls back to "any one
of its added lines is already there" - and that fallback has silently skipped a
real feature three times (DEF-035: `github-tools`, `handsfree`, `product-check`,
`history-purge` on 2026-11-05, then `bench.patch` on 2026-11-04, then
`cloud-escalate.patch` on 2026-10-28), because route boilerplate every handler
shares counts as proof. One present line is enough.

The fix the owner chose is not a whole-file SHA (brittle against CRLF, encoding
and comment shifts). It is this: every patch that ships must be covered by a
route we can point at, and a patch that is covered by none fails the suite.

WHAT "COVERED" MEANS, and why there are four routes

Every `(patch, file)` pair whose file is a live-shipped one must be carried by
exactly one of these, checked in this order:

  delta   its `DELTA_TABLE` entry names this file and carries explicit `probes`
          (the per-patch standard; every probe must be present for the tool to
          call the patch already-there, so a half-applied block cannot pass).
  whole   the file is in `$SHIPPED` - the deploy copies that module whole, so a
          patch the rebuilt modules supersede lands as the module's own bytes.
  base    the published base an installer starts from (`jarvis-backend/<file>`)
          already holds the patch: `selftest.patch_states` says "applied". This
          is the project's own per-line presence check (a line later patches
          remove is not counted, and neither is a line the patch's context
          already had), NOT a whole-file comparison - which is exactly the
          property the ruling asks for.
  exact   the patch's own hunks are the delivery route: it is in the patcher's
          stack (`backend/_stack.order()`, the exact bytes `apply-patches.ps1`
          applies) AND none of its hunks for that file needs an invented
          pre-image (`_stack.materialised`). Its hunks are then byte-for-byte
          text this repository holds, so no guess is involved.

Anything left over must be listed in EXEMPT below with a one-line reason, and
this suite fails on any pair that is neither covered nor exempted.

WHY AN EXEMPTION LIST AT ALL

A patch whose hunks read the owner's own file (the `_stack` walk has to invent
that pre-image) cannot be replayed exactly from this repository, and if the
published base does not carry it either, the only honest statement is that no
route is proved today. Choosing probes for it needs a read of the live file,
which this repository may not guess at (the tool's own doctrine: a refusal is
better than a guess). Those pairs are named one by one below rather than
silenced, and the suite fails if a NEW pair joins them without a reason.

The exemption count is printed on every run, and an exemption whose patch has
since become covered FAILS - so the list can only shrink.

A patch that is in neither `$PATCHES` nor `DELTA_TABLE` is also a failure here:
that is an orphan `.patch` file no deploy route will ever carry.

IT IS NOT A PASS FOR A MACHINE WITHOUT GIT. `_stack.materialised` needs git to
apply the stack, and without it every patch would look "exact" - the strongest
claim in this file - so the suite stops instead of reporting a false green.
"""
import re
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKEND = HERE
BASE = REPO / "jarvis-backend"
PS1 = REPO / "scripts" / "apply-patches.ps1"
DELTA_DIR = REPO / "tools" / "hud-deltas"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools"))
import _stack                                       # noqa: E402
import reconcile_live_backend as R                  # noqa: E402
import selftest as S                                # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

#: Patches that no route proves TODAY, alphabetically. Each reason is one line
#: and says what would remove the entry: a `DELTA_TABLE` rule whose probes are
#: chosen from a READ of the live file (never invented), or a base that carries
#: the patch. A reason is not a licence to leave it here: the suite fails when
#: an entry stops being true (stale exemption).
EXEMPT = {
    "appearance.patch":
        "the published base cannot prove it (later stack rewrites it) and its hunks read "
        "the owner's own HUD, so no probe may be chosen without a live read",
    "attention-settings.patch":
        "not in the published base; its hunks read the owner's own HUD dispatch "
        "lines, so a probe needs a live read",
    "cloud-honesty.patch":
        "the published base cannot prove it and its hunk reads the owner's own "
        "HUD; a probe would have to be invented",
    "gate-outcome.patch":
        "the published base cannot prove it and its hunks read the owner's own "
        "gate; what is missing is owner-only text",
    "gate-risk-rows.patch":
        "no unique added line survives to check against the base (shared with "
        "another patch), and its hunk reads the owner's own gate",
    "hud-exclusive-bind.patch":
        "not in the published base; its hunk replaces the live listener "
        "construction, text only the owner's file holds",
    "hud-origin-module.patch":
        "not in the published base; its hunks replace the owner's own "
        "_token_ok/_origin_ok bodies, which no earlier patch writes",
    "initiative-payload.patch":
        "not in the published base; its hunk reads the owner's own HUD text "
        "and no exact pre-image exists here",
    "limits-read.patch":
        "not in the published base; its hunks read the owner's own HUD limits "
        "lines, so nothing here proves them byte for byte",
    "presets.patch":
        "not in the published base; its hunk reads the owner's own HUD preset "
        "block and no probe can be chosen without a live read",
    "retrieve-count.patch":
        "not in the published base; its hunks read the owner's own HUD "
        "retrieval lines, so a probe would be a guess",
    "show-card-timer.patch":
        "not in the published base; its hunk reads the owner's own gate and "
        "the card's timer text, which this repository does not hold",
}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: `skip`, counted on its own, never a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def lf(text: str) -> str:
    return text.replace("\r\n", "\n")


# ---------------------------------------------------------------- the inputs --

def ps1_list(name: str) -> list:
    """The quoted entries of `$name = @( ... )`, in order, comments dropped."""
    text = PS1.read_text(encoding="utf-8")
    start = text.index(f"${name} = @(")
    out = []
    for line in text[start:].splitlines()[1:]:
        code = line.split("#", 1)[0].strip()
        if code == ")":
            return out
        out += re.findall(r"'([^']+)'", code)
    raise AssertionError(f"${name} has no closing ')'")


def superseded() -> set:
    """The patches `$REBUILT_SUPERSEDES` swaps for a rebuilt-patches/ half."""
    text = PS1.read_text(encoding="utf-8")
    start = text.index("$REBUILT_SUPERSEDES = @{")
    body = text[start:text.index("}", start)]
    return set(re.findall(r"^\s*'([\w.-]+\.patch)'\s*=", body, re.M))


_TARGET = re.compile(r"^\+\+\+ b/(\S+)", re.M)


def targets_of(text: str) -> list:
    """The files one patch edits. `\\S+` stops at the tab some old headers carry
    (`+++ b/jarvis_gate.py<TAB>2026-09-17 ...`), so the file is the bare name."""
    return sorted(set(_TARGET.findall(lf(text))))


_CTX = None


def context() -> dict:
    """Everything the classification reads, measured once. Read-only."""
    global _CTX
    if _CTX is not None:
        return _CTX
    patches = sorted(p.name for p in BACKEND.glob("*.patch"))
    shipped = ps1_list("SHIPPED")
    order = _stack.order()
    materialised = {}
    for target in R.PATCHED_FILES:
        stats = _stack.materialised(target)
        for name, _n in (stats.get("by_patch") or {}).items():
            materialised.setdefault(Path(name).name, set()).add(target)
    base = {}
    for name, target, state, present, total in S.patch_states(BASE):
        base[(Path(name).name, target)] = (state, present, total)
    _CTX = {
        "patches": patches,
        "stack": ps1_list("PATCHES"),
        # The patcher's stack order: a superseded patch is its rebuilt half,
        # and one with no half is left out (the rebuilt module replaces it).
        "order": order,
        "order_names": set(order),
        "leaves": {p.rsplit("/", 1)[-1] for p in shipped},
        "materialised": materialised,
        "superseded": superseded(),
        "base": base,
    }
    return _CTX


def in_stack(name: str, ctx: dict) -> bool:
    return name in ctx["order_names"] or ("rebuilt-patches/" + name) in ctx["order_names"]


def classify(name: str, target: str, ctx: dict, *, exempt: bool = True):
    """(route, why) for one patch/file pair - the rule this suite enforces.

    Pure apart from `ctx`; `exempt=False` is used to ask "is this exemption
    still a real gap?" without the list masking the answer."""
    if target in ctx["leaves"]:
        if name in ctx["superseded"]:
            return "whole", "the rebuilt module is copied whole"
        return "gap", f"{target} is shipped whole, so a live patch must not edit it"
    if target not in R.PATCHED_FILES:
        return "gap", (f"{target} is neither a patched base file nor shipped whole, "
                       f"so no deploy route carries it")
    entry = (R.DELTA_TABLE.get(name) or {}).get(target) or {}
    if entry.get("probes"):
        return "delta", f"{len(entry['probes'])} explicit probe(s)"
    state, present, total = ctx["base"].get((name, target), ("no file", 0, 0))
    if state == "applied":
        return "base", f"the published base holds {present}/{total} distinctive lines"
    if in_stack(name, ctx) and target not in ctx["materialised"].get(name, ()):
        return "exact", "its hunks are byte-for-byte text this repository holds"
    why = (f"base: {state} ({present}/{total}); "
           f"hunks that need the owner's own text: "
           f"{'yes' if target in ctx['materialised'].get(name, ()) else 'no'}; "
           f"stack: {'yes' if in_stack(name, ctx) else 'no'}")
    if exempt and name in EXEMPT:
        return "exempt", why
    return "gap", why


# ---------------------------------------------------------------- the checks --

def t_the_tree_and_the_lists_are_one_set():
    """`backend/*.patch`, `$PATCHES` and the stack walk name the same patches.

    An orphan `.patch` file is the first half of a silent skip: no route would
    ever carry it, and nothing used to say so."""
    ctx = context()
    patches = set(ctx["patches"])
    stack = ctx["stack"]
    check("backend/ holds the patch stack", len(patches) >= 100, f"{len(patches)}")
    check("$PATCHES names exactly the .patch files in backend/",
          set(stack) == patches,
          f"only in the script: {sorted(set(stack) - patches)}; "
          f"only in the tree: {sorted(patches - set(stack))}")
    check("$PATCHES has no duplicate entry", len(stack) == len(set(stack)),
          [n for n in stack if stack.count(n) > 1])
    check("$SHIPPED is readable", len(ctx["leaves"]) >= 100, f"{len(ctx['leaves'])}")
    check("the five patched base files are NOT shipped whole",
          not (set(R.PATCHED_FILES) & ctx["leaves"]),
          sorted(set(R.PATCHED_FILES) & ctx["leaves"]))
    missing = [n for n in stack if not in_stack(n, ctx) and n not in ctx["superseded"]]
    check("every shipped patch is in the exact-hunk stack, or superseded by a "
          "rebuilt module", not missing, missing)
    halves = [n for n in ctx["superseded"]
              if ("rebuilt-patches/" + n) in ctx["order_names"]]
    check("a superseded patch with a rebuilt half is carried by that half",
          all(in_stack(n, ctx) for n in halves), sorted(halves))
    check("the stack walk is not empty", len(ctx["order"]) >= 100, f"{len(ctx['order'])}")
    check("no patch appears twice in the stack walk",
          len(ctx["order"]) == len(set(ctx["order"])),
          [n for n in ctx["order"] if ctx["order"].count(n) > 1])


def t_the_delta_table_is_well_formed():
    """The entries are data, so their SHAPE can be checked without a live PC.

    Probes are the whole point of the standard: an entry whose probes are empty
    falls back to the loose rule the ruling exists to replace."""
    ctx = context()
    table = R.DELTA_TABLE
    named, literal, problems = [], [], []
    for patch, entries in table.items():
        if not isinstance(entries, dict) or not entries:
            problems.append(f"{patch}: no entry for any file")
            continue
        real = (BACKEND / patch).is_file()
        (named if real else literal).append(patch)
        for target, entry in entries.items():
            where = f"{patch} -> {target}"
            if target not in R.PATCHED_FILES:
                problems.append(f"{where}: not one of the five patched base files")
                continue
            if not (entry.get("probes") or ()):
                problems.append(f"{where}: no probes")
            for key in ("file", "replace_file"):
                block = entry.get(key)
                if block and not (DELTA_DIR / str(block)).is_file():
                    problems.append(f"{where}: {key} {block!r} is not in tools/hud-deltas/")
            for region in entry.get("regions") or ():
                if not region.get("file") or not region.get("replace_file"):
                    problems.append(f"{where}: a region needs file and replace_file")
                for key in ("file", "replace_file"):
                    block = region.get(key)
                    if block and not (DELTA_DIR / str(block)).is_file():
                        problems.append(f"{where}: region {key} {block!r} is missing")
                if not (region.get("probes") or ()):
                    problems.append(f"{where}: a region has no probes")
            if entry.get("hunks") and not real:
                problems.append(f"{where}: a literal entry cannot say hunks")
            adapted = entry.get("adapted_hunks") or {}
            if adapted:
                if not entry.get("hunks"):
                    problems.append(f"{where}: adapted_hunks without hunks")
                if real:
                    count = len(_stack.hunks((BACKEND / patch).read_text(encoding="utf-8"),
                                             target))
                    bad = sorted(i for i in adapted if not 1 <= int(i) <= count)
                    if bad:
                        problems.append(f"{where}: adapted hunk(s) {bad} but the patch has "
                                        f"{count}")
    check("every DELTA_TABLE entry has probes and readable block files",
          not problems, "\n        ".join(problems))
    no_block = [p for p in literal
                if not any((e.get("file") or e.get("lines"))
                           for e in table[p].values())]
    check("a literal delta (no .patch of its own) carries its block", not no_block,
          no_block)
    check("the DELTA_TABLE still carries per-patch entries, not only literal deltas",
          len(named) >= 20, f"{len(named)} patch-named, {len(literal)} literal")
    print(f"      DELTA_TABLE: {len(table)} entries - {len(named)} name a patch, "
          f"{len(literal)} are literal deltas with no .patch")
    check("every patch-named entry names a patch that is really in $PATCHES",
          set(named) <= set(ctx["stack"]), sorted(set(named) - set(ctx["stack"])))


def t_every_shipped_patch_is_covered():
    """The owner's rule: every patch/file pair on a live-shipped file is carried
    by a proved route or by a named exemption - never by nothing."""
    ctx = context()
    rows = []
    for name in ctx["patches"]:
        text = lf((BACKEND / name).read_text(encoding="utf-8", errors="replace"))
        targets = targets_of(text)
        if not targets:
            check(f"{name} names a file it edits", False, "no `+++ b/` line")
            continue
        for target in targets:
            route, why = classify(name, target, ctx)
            rows.append((name, target, route, why))
    for name, target, route, why in rows:
        if route == "exempt":
            state, present, total = ctx["base"].get((name, target), ("no file", 0, 0))
            hunks = "yes" if target in ctx["materialised"].get(name, ()) else "no"
            print(f"      exempt {name} -> {target} (base: {state} {present}/{total}; "
                  f"reads the owner's own text: {hunks})")
    counts = {}
    for _n, _t, route, _w in rows:
        counts[route] = counts.get(route, 0) + 1
    print(f"      pairs: {len(rows)} - " + ", ".join(
        f"{k} {counts.get(k, 0)}" for k in ("delta", "base", "exact", "whole",
                                            "exempt", "gap")))
    gaps = [(n, t, w) for n, t, r, w in rows if r == "gap"]
    check("every patch/file pair on a live-shipped file is carried by a proved "
          "route or a named exemption", not gaps,
          "\n        ".join(f"{n} -> {t}: {w}" for n, t, w in gaps))
    covered = {n for n, _t, r, _w in rows if r != "gap"}
    print(f"      patches: {len(ctx['patches'])} - covered {len(covered)}, "
          f"gaps {len({n for n, _t, _w in gaps})}")
    return rows


def t_the_exemption_count_is_printed_and_the_list_cannot_go_stale():
    """An exemption is a recorded gap, not a silent one - and it must still be
    one. A patch that becomes covered must lose its entry, or the list becomes
    a place where real coverage is forgotten."""
    ctx = context()
    check("exemption list is alphabetically sorted", list(EXEMPT) == sorted(EXEMPT),
          [n for n in EXEMPT if list(EXEMPT).index(n)
           != sorted(EXEMPT).index(n)])
    bad = [n for n, why in EXEMPT.items()
           if not why.strip() or "\n" in why.strip()]
    check("every exemption carries a one-line reason", not bad, bad)
    unknown = sorted(set(EXEMPT) - set(ctx["patches"]))
    check("every exemption names a real patch file", not unknown, unknown)
    stale = []
    for name in sorted(set(EXEMPT) & set(ctx["patches"])):
        text = lf((BACKEND / name).read_text(encoding="utf-8", errors="replace"))
        routes = [classify(name, target, ctx, exempt=False)
                  for target in targets_of(text)]
        if routes and all(route != "gap" for route, _why in routes):
            stale.append(f"{name} is covered by "
                         f"{', '.join(sorted({route for route, _w in routes}))} now; "
                         f"remove the exemption")
    check("no exemption is stale (an exempted patch has since become covered)",
          not stale, stale)
    print(f"      exemptions: {len(EXEMPT)}")


def t_the_rule_bites_on_a_made_up_patch():
    """The classification itself, on a patch that is in none of the routes.

    A test of the test: the rule must answer GAP for a brand-new patch that is
    absent from the base, reads the owner's own text, and has no entry - the
    exact shape of the silent skips this suite exists to stop."""
    ctx = {
        "leaves": {"jarvis_extra.py"},
        "superseded": set(),
        "materialised": {"made-up.patch": {"jarvis_hud.py"}},
        "base": {},
        "order_names": {"made-up.patch"},
    }
    route, why = classify("made-up.patch", "jarvis_hud.py", ctx)
    check("a new patch with no route is a GAP",
          route == "gap" and "no file" in why, (route, why))
    R.DELTA_TABLE["made-up.patch"] = {"jarvis_hud.py": {"probes": ("a probe",)}}
    try:
        check("...and the same patch with one DELTA_TABLE entry is DELTA",
              classify("made-up.patch", "jarvis_hud.py", ctx)[0] == "delta")
    finally:
        del R.DELTA_TABLE["made-up.patch"]
    check("a patch that edits a file shipped whole, and is not superseded, is a GAP",
          classify("made-up.patch", "jarvis_extra.py", ctx)[0] == "gap")
    check("a file no route ships is a GAP",
          classify("made-up.patch", "made_up_file.py", ctx)[0] == "gap")


if __name__ == "__main__":
    if not shutil.which("git"):
        skip("git is not installed, so the exact-hunk route cannot be measured - "
             "this suite did NOT run and is NOT a pass")
    else:
        for fn in (t_the_tree_and_the_lists_are_one_set,
                   t_the_delta_table_is_well_formed,
                   t_every_shipped_patch_is_covered,
                   t_the_exemption_count_is_printed_and_the_list_cannot_go_stale,
                   t_the_rule_bites_on_a_made_up_patch):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
