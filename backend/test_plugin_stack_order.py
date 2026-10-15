"""test_plugin_stack_order.py - the loader's order, checked across EVERY folder.

    python3 backend/test_plugin_stack_order.py

WHY THIS EXISTS, AND WHAT IT COST TO LEARN. On 2026-10-14 and 15, four defects
were found in the drop-in folders' `stack_order` numbers, and every one of them
came from the same hole: `plugins/ready/` is ordered by a number each folder
writes for itself, and NOTHING checked those numbers against each other.

  * `skill-hub` and `voiceprint` BOTH carried `stack_order: 142`. The loader
    sorts by `(stack_order, name)`, so the pair loaded in an order decided by
    the letter of the folder name, which nobody chose. FIXED 2026-10-15:
    `skill-hub` kept 142 and `voiceprint` moved to 146, the first number free
    after it (143 `receipts`, 144 `auto-router` and 145 `vault` were all taken;
    145 is claimed on the pushed `fix/vault-fail-closed`).
  * `voiceprint/README.md` said 144 while its own `plugin.json` said 142.
    FIXED in the same change: the README now states the manifest's number.
  * `backend/test_receipts.py` judged the receipts folder's position against
    `registry.json`'s catalogued folders only, so every folder that replaces no
    patch was invisible to it - the check passed by not looking.
  * a branch re-ordered three SHIPPED lists by hand and nothing could say
    whether the new order was right.

WHAT IT ASSERTS. One thing, five ways: the loader's order is DEFINED for every
folder, by a number that is unique, that agrees with the catalogue the patch
stack is described by, and that a README does not contradict.

  1. every folder under `plugins/ready/` carries an integer `stack_order`;
  2. no two folders share one - with NO exceptions;
  3. the loader's own sequence never steps DOWN in `stack_order`, so the NUMBER
     decides the order and the name tie-breaker decides nothing; and no folder
     falls through to the sentinel default;
  4. every folder that replaces a patch states the same number `registry.json`
     gives that patch - and the two sets are the same set, so (4) cannot be
     blind to a folder the catalogue does not know about;
  5. a README that states a loader position states the manifest's number - with
     no exceptions.

THE RECORD, WHICH IS NOW EMPTY, AND WHY THAT IS SAFE. This suite used to carry
the two known defects as RECORDS - `tools/check_unmanaged_files.py`'s pattern,
where a defect that is KNOWN is printed loudly and fails the moment it changes,
rather than blocking a merge. Both have now been fixed, so both records were
DELETED rather than left behind to fail on a fixed state. The two rot checks at
the bottom are what made deleting them safe; with nothing recorded they report
themselves as SKIPPED, never as a pass, because `not stale` over an empty list
is a condition that cannot fail - and a check that cannot fail is worse than no
check. A NEW collision is a failure the moment it appears; record one here ONLY
if it is ever shipped on purpose.

WHAT IT CANNOT SEE. Only four of the 28 folders' READMEs state a position at
all, so (5) covers those four. The others say nothing, which is not a pass and
not a failure - it is printed as a coverage line so the number is never assumed.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _where import BACKEND, REPO  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []

READY = REPO / "plugins" / "ready"
REGISTRY = REPO / "plugins" / "registry.json"

#: A floor on how many folders must be present, so a moved or renamed
#: `plugins/ready/` fails LOUDLY instead of passing over an empty glob. 28
#: folders on 2026-10-15; the floor is deliberately below that and above zero.
MIN_FOLDERS = 20

#: KNOWN, RECORDED COLLISIONS - EMPTY, AND THAT IS THE POINT.
#: (the shared number, the folders that share it, why it is recorded)
#:
#: The one entry this ever held was `skill-hub` and `voiceprint` both claiming
#: 142. That was DECIDED on 2026-10-15 - `skill-hub` kept 142 and `voiceprint`
#: moved to 146, the first number free after it (143 `receipts`, 144
#: `auto-router` and 145 `vault` were all taken; 145 on the pushed
#: `fix/vault-fail-closed`) - so the record was DELETED rather than left behind
#: to fail on a fixed state. The rot check below is what makes deleting it safe.
#: A new collision is a failure the moment it appears; if one is ever shipped on
#: purpose, record it here with its reason and it will be printed on every run
#: instead of failing.
KNOWN_COLLISIONS: list = []

#: KNOWN, RECORDED DOCUMENT/MANIFEST MISMATCHES - same rules as above. EMPTY:
#: `voiceprint/README.md` said 144 while its manifest said 142, and the README
#: was brought to the manifest's number (146) with the same decision.
#: folder -> (the manifest's number, the number its README states, why recorded)
KNOWN_README_MISMATCHES: dict = {}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print("skip  " + why)


# --------------------------------------------------------------------------
#   Reading the folders
# --------------------------------------------------------------------------

def _folders() -> list:
    """[{folder, path, manifest, error}] for every folder under plugins/ready."""
    if not READY.is_dir():
        return []
    out = []
    for child in sorted(READY.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        entry = {"folder": child.name, "path": child, "manifest": None,
                 "error": ""}
        path = child / "plugin.json"
        if not path.is_file():
            entry["error"] = "no plugin.json"
        else:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                entry["error"] = f"plugin.json will not parse ({type(exc).__name__})"
            else:
                if not isinstance(data, dict):
                    entry["error"] = "plugin.json is not an object"
                else:
                    entry["manifest"] = data
        out.append(entry)
    return out


def _is_whole_number(value) -> bool:
    """An int, and NOT a bool. `True` is an int in Python, and a folder that
    said `"stack_order": true` would sort as 1 without anything complaining."""
    return isinstance(value, int) and not isinstance(value, bool)


def _loader_module():
    """The REAL loader, or None. Imported, never re-implemented."""
    try:
        import jarvis_plugins
        return jarvis_plugins
    except Exception:  # noqa: BLE001
        return None


#: Why `_loader_entries()` returned None, so a failure can say what really
#: happened instead of only that nothing was read.
_LOADER_ERROR: list = []


def _loader_entries():
    """The loader's OWN `discover()` over plugins/ready/, or None.

    Deliberately the real function rather than a copy of its sort. A replica can
    drift from the loader and then pass while the loader does something else;
    `discover()` returns the folders in the order the loader will load them
    (`jarvis_plugins.py:138` sorts by `(stack_order, name)`), so every ordering
    claim below is about what the loader really does.
    """
    _LOADER_ERROR.clear()
    module = _loader_module()
    if module is None:
        _LOADER_ERROR.append("jarvis_plugins could not be imported")
        return None
    try:
        return module.discover(READY)
    except Exception as exc:  # noqa: BLE001
        _LOADER_ERROR.append(f"{type(exc).__name__}: {exc}")
        return None


def _catalogue() -> dict:
    """{folder name: registry entry} for the plug-in bucket, or {} if unreadable."""
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    return {e["name"]: e for e in data.get("entries", [])
            if isinstance(e, dict) and e.get("bucket") == "plug-in" and e.get("name")}


# ==========================================================================
#   1. there is something to check, and it is shaped the way we think
# ==========================================================================

def t_the_ready_folder_is_there_and_holds_folders():
    check("plugins/ready/ exists - a missing folder is a failure, never a pass",
          READY.is_dir(), f"looked in {READY}")
    folders = _folders()
    check(f"it holds at least {MIN_FOLDERS} drop-in folders, so an empty or moved "
          f"glob cannot pass by having nothing to look at",
          len(folders) >= MIN_FOLDERS, f"found {len(folders)}")


def t_every_folder_has_a_readable_manifest():
    bad = [f"{e['folder']}: {e['error']}" for e in _folders() if e["error"]]
    check("every folder's plugin.json is there, parses, and is an object",
          not bad, "\n".join(bad))


def t_every_folder_states_a_whole_number():
    bad = []
    for e in _folders():
        if e["error"]:
            continue
        value = e["manifest"].get("stack_order")
        if not _is_whole_number(value):
            bad.append(f"{e['folder']}: stack_order is {value!r}")
    check("every folder declares its own whole-number stack_order",
          not bad, "\n".join(bad))


# ==========================================================================
#   2. no two folders share a number - except the recorded collision
# ==========================================================================

def _groups() -> dict:
    """{number: [folder, ...]} for every folder that states a number."""
    out: dict = {}
    for e in _folders():
        if e["error"]:
            continue
        value = e["manifest"].get("stack_order")
        if _is_whole_number(value):
            out.setdefault(value, []).append(e["folder"])
    return out


def t_no_two_folders_share_a_number():
    """THE CHECK THIS SUITE WAS BUILT FOR."""
    actual = {n: tuple(sorted(fs)) for n, fs in _groups().items() if len(fs) > 1}
    recorded = {n: tuple(sorted(fs)) for n, fs, _why in KNOWN_COLLISIONS}
    new = {n: fs for n, fs in actual.items() if recorded.get(n) != fs}
    # The name says which rule is in force RIGHT NOW, so an empty record cannot
    # read as "a collision would be tolerated".
    allowed = (f"the recorded collision(s) {sorted(recorded)} are allowed"
               if recorded else "none is recorded, so none is allowed")
    check(f"no two folders under plugins/ready/ share a stack_order ({allowed})",
          not new,
          "NEW collision(s), not recorded anywhere - the loader would order these "
          "by folder name, which nobody chose:\n"
          + "\n".join(f"      {n} -> {list(fs)}" for n, fs in sorted(new.items())))


def t_the_recorded_collision_is_still_real():
    """So the record cannot rot into a list of things that are no longer true.
    A recorded collision that has been FIXED is a failure here on purpose: the
    record is then stale and must be dropped, rather than left to read as an
    open defect for ever.

    With no records this is SKIPPED, not passed: `not stale` over an empty list
    is a condition that cannot fail, and a check that cannot fail is worse than
    none. The skip names why there is nothing to check."""
    if not KNOWN_COLLISIONS:
        skip("no recorded collision - skill-hub and voiceprint were separated on "
             "2026-10-15 (142 and 146), so there is no record left to rot")
        return
    actual = _groups()
    stale = []
    for number, folders, _why in KNOWN_COLLISIONS:
        holders = tuple(sorted(actual.get(number, [])))
        if holders != tuple(sorted(folders)):
            stale.append(f"recorded {number} -> {list(folders)}, but the folders "
                         f"holding {number} now are {list(holders)}")
    check("every recorded collision still describes what is on disk "
          "(a fixed one must be dropped from the record, not left behind)",
          not stale, "\n".join(stale))


# ==========================================================================
#   3. the loader's sequence is total, and the NUMBER alone decides it
# ==========================================================================

def t_the_loader_itself_would_load_every_folder():
    """A check about the LOADER, not about a replica of it. A folder the loader
    cannot read, or one it is switched off, is a feature that is silently OFF -
    the exact failure mode `test_shipped_modules.py` exists for one level up."""
    check("the loader module is importable", _loader_module() is not None,
          f"tried to import jarvis_plugins from {BACKEND}")
    entries = _loader_entries()
    if entries is None:
        check("the loader's own discover() ran over plugins/ready/", False,
              f"jarvis_plugins.discover({READY}) did not return a list: "
              + "; ".join(_LOADER_ERROR)
              + ". NOTE: a folder whose plugin.json says `\"stack_order\": null` "
                "stops the loader HERE - `e.get(\"stack_order\", 10_000)` uses the "
                "default only when the key is ABSENT, so None reaches sorted() and "
                "raises. That would stop the whole backend starting.")
        return
    check("the loader's own discover() ran over plugins/ready/", True)
    rejected = [f"{e.get('name')}: {e.get('error')}"
                for e in entries if e.get("error")]
    check("the loader REJECTS none of the folders (an error entry is a feature "
          "that silently never loads)",
          not rejected, "\n".join(rejected))
    off = sorted(str(e.get("name")) for e in entries if e.get("disabled"))
    check("no folder is switched off by a `disabled` marker or `enabled: false`",
          not off, f"switched off: {off}")


def t_the_loader_order_is_decided_by_the_number_alone():
    entries = _loader_entries()
    if entries is None:
        check("the loader's sequence can be read, so its order can be checked", False,
              "discover() did not run, so nothing can be said about the order: "
              + "; ".join(_LOADER_ERROR))
        return
    live = [e for e in entries if not e.get("error") and not e.get("disabled")]
    check("the loader's sequence was read for the folders it would load",
          bool(live), f"{len(live)} folder(s) the loader would load")
    # A folder whose key is PRESENT but not a number falls THROUGH the loader's
    # default: `.get(k, d)` only uses `d` when the key is absent.
    fell_back = [str(e.get("name")) for e in live
                 if not _is_whole_number(e.get("stack_order"))]
    check("no folder the loader would load falls back to the sentinel default, "
          "so the order never depends on a number nobody wrote",
          not fell_back, f"no usable stack_order: {fell_back}")
    numbers = [e.get("stack_order") for e in live]
    names = [str(e.get("name")) for e in live]
    # NOT "no adjacent equal": that is satisfied by any order that happens not
    # to repeat a neighbour, and a loader sorting by NAME ALONE passes it. The
    # claim has to be that the sequence never steps back down, which is what
    # "the number decides the order" actually means. (Found by the bite-proof:
    # the name-only mutation passed the weaker reading.)
    down = [(names[i], numbers[i], names[i + 1], numbers[i + 1])
            for i in range(len(numbers) - 1) if numbers[i] > numbers[i + 1]]
    check("the loader's OWN sequence never steps DOWN in stack_order, so the "
          "NUMBER orders the folders rather than the folder name",
          not down,
          "the loader loads these out of order:\n"
          + "\n".join(f"      {a} ({x}) before {b} ({y})" for a, x, b, y in down))
    ties = [(numbers[i], names[i], names[i + 1])
            for i in range(len(numbers) - 1) if numbers[i] == numbers[i + 1]]
    # The recorded collision IS a tie by definition, so it is allowed here too -
    # otherwise the known defect would make this suite red, which is the one
    # thing the record exists to prevent. Any OTHER tie fails.
    recorded_ties = {(n, frozenset(fs)) for n, fs, _why in KNOWN_COLLISIONS}
    new_ties = [t for t in ties if (t[0], frozenset(t[1:])) not in recorded_ties]
    check("no folder's position is decided by its name - no ties beyond any "
          "recorded collision",
          not new_ties,
          "these pairs tie, so their order is decided by the folder name:\n"
          + "\n".join(f"      {n}: {a} before {b}" for n, a, b in new_ties))


# ==========================================================================
#   4. the catalogue the patch stack is described by agrees
# ==========================================================================

def t_every_catalogued_folder_states_its_patch_order():
    catalogue = _catalogue()
    check("plugins/registry.json was read and has the plug-in bucket",
          bool(catalogue), f"{REGISTRY} gave {len(catalogue)} plug-in entries")
    bad = []
    for name, entry in sorted(catalogue.items()):
        folder = READY / name
        manifest = folder / "plugin.json"
        if not manifest.is_file():
            bad.append(f"{name}: catalogued, but plugins/ready/{name}/plugin.json is not there")
            continue
        value = json.loads(manifest.read_text(encoding="utf-8")).get("stack_order")
        if value != entry.get("order"):
            bad.append(f"{name}: registry.json order={entry.get('order')!r}, "
                       f"plugin.json stack_order={value!r} ({entry.get('patch')})")
    check("every catalogued folder's stack_order equals its patch order in registry.json",
          not bad, "\n".join(bad))


def t_the_catalogue_and_the_folders_are_the_same_set():
    """The half that stops the check above being BLIND. `test_receipts.py` once
    compared the receipts folder against the catalogued folders only, so a
    folder that replaces no patch was outside what it could see - it passed by
    not looking. This asserts the two sets are the same, so a folder that names
    a patch cannot escape (4) by being absent from the catalogue."""
    catalogue = _catalogue()
    names_a_patch, no_patch = set(), set()
    for e in _folders():
        if e["error"]:
            continue
        (names_a_patch if e["manifest"].get("replaces_patch") else no_patch).add(e["folder"])
    check("every folder that names a patch is in registry.json's plug-in bucket",
          not (names_a_patch - set(catalogue)),
          f"names a patch but is not catalogued: {sorted(names_a_patch - set(catalogue))}")
    check("every catalogued plug-in is a folder that names a patch",
          not (set(catalogue) - names_a_patch),
          f"catalogued but names no patch: {sorted(set(catalogue) - names_a_patch)}")
    check("the folders that replace NO patch are outside the catalogue, as they must be",
          not (no_patch & set(catalogue)),
          f"both at once: {sorted(no_patch & set(catalogue))}")


# ==========================================================================
#   5. a README must not contradict its own manifest
# ==========================================================================

_POSITION = re.compile(r"Position in the loader'?s order:\s*\*{0,2}\s*(\d+)")


def _readme_positions() -> dict:
    """{folder: the number its README states}, for the READMEs that state one."""
    out = {}
    for e in _folders():
        readme = e["path"] / "README.md"
        if not readme.is_file():
            continue
        found = _POSITION.search(readme.read_text(encoding="utf-8", errors="replace"))
        if found:
            out[e["folder"]] = int(found.group(1))
    return out


def t_a_readme_that_states_a_position_states_the_manifest_s():
    stated = _readme_positions()
    actual = {e["folder"]: e["manifest"].get("stack_order")
              for e in _folders() if not e["error"]}
    bad = []
    for folder, number in sorted(stated.items()):
        if actual.get(folder) == number:
            continue
        known = KNOWN_README_MISMATCHES.get(folder)
        if known and (known[0], known[1]) == (actual.get(folder), number):
            continue                       # recorded; checked for rot below
        bad.append(f"{folder}: README says {number}, plugin.json says {actual.get(folder)!r}")
    check("every README that states a loader position states the manifest's number",
          not bad, "\n".join(bad))


def t_the_recorded_readme_mismatch_is_still_real():
    """The same rot check for the README/manifest record. SKIPPED while there
    are no records, for the same reason: `not stale` over an empty dict is a
    condition that cannot fail."""
    if not KNOWN_README_MISMATCHES:
        skip("no recorded README mismatch - voiceprint/README.md was brought to "
             "its manifest's number on 2026-10-15, so there is no record to rot")
        return
    stated = _readme_positions()
    actual = {e["folder"]: e["manifest"].get("stack_order")
              for e in _folders() if not e["error"]}
    stale = []
    for folder, (manifest_number, readme_number, _why) in KNOWN_README_MISMATCHES.items():
        if actual.get(folder) == readme_number:
            stale.append(f"{folder}: README now says {readme_number}, which IS the "
                         f"manifest's number - the record is stale, drop it")
        elif stated.get(folder) != readme_number or actual.get(folder) != manifest_number:
            stale.append(f"{folder}: recorded {manifest_number}/{readme_number}, but "
                         f"manifest={actual.get(folder)!r} README={stated.get(folder)!r}")
    check("every recorded README mismatch still describes what is on disk "
          "(a fixed one must be dropped from the record)",
          not stale, "\n".join(stale))


# ==========================================================================
#   main - and the recorded defects, printed on EVERY run
# ==========================================================================

def _print_records():
    print()
    if not KNOWN_COLLISIONS and not KNOWN_README_MISMATCHES:
        print("RECORDED DEFECTS: none. Every collision and every README/manifest "
              "mismatch is a FAILURE now.")
        print("The two that were recorded here - the 142 pair and voiceprint's "
              "README - were fixed on 2026-10-15 and their records deleted.")
    else:
        print("RECORDED DEFECTS - KNOWN, PRINTED EVERY RUN, AWAITING A DECISION.")
        print("This suite is green with them and fails the moment one changes.")
        for number, folders, why in KNOWN_COLLISIONS:
            print(f"  * stack_order {number} is held by BOTH {list(folders)}")
            for line in _wrap(why):
                print(f"      {line}")
        for folder, (man, rd, why) in KNOWN_README_MISMATCHES.items():
            print(f"  * {folder}/README.md says {rd}, its plugin.json says {man}")
            for line in _wrap(why):
                print(f"      {line}")
    stated = _readme_positions()
    print(f"  coverage: {len(stated)} of {len(_folders())} folders' READMEs state a "
          f"loader position ({', '.join(sorted(stated)) or 'none'}); the rest state "
          f"none, which is neither a pass nor a failure.")


def _wrap(text, width=88):
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def main() -> int:
    funcs = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("t_") and callable(fn)]
    for name, fn in funcs:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(f"{name} raised", False,
                  f"{type(exc).__name__}: {exc}\n" + traceback.format_exc())
    _print_records()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "\n        ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
