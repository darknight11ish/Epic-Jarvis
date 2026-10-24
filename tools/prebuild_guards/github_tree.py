"""Stop a GitHub "create tree" request from wiping the repository by accident.

WHY THIS FILE EXISTS

GitHub's Git Data API builds a new commit in pieces. First you post a tree
(``POST /repos/{owner}/{repo}/git/trees``), then a commit, then you move the
branch. The tree request has an optional field, ``base_tree``, naming the tree
the new one starts from. When it is left out, GitHub does not add to the
current repository: it creates a brand-new root tree holding only the files in
the request. The next commit then deletes every other file in the repository.
A missing or misspelled ``base_tree`` is not a small API mistake; it is data
loss on the owner's repository, so this module refuses one before any request
is built.

WHAT THIS MODULE IS

Pure functions and data. There is no network code here and no token. P-GH-1
will call ``build_tree_payload`` before it raises the ``github_push`` approval
card, and ``compare_trees`` to fill in the card's exact counts. The card must
show the counts before the owner is asked, because "Added 1" and "Deleted 214"
are very different requests even when both come from a helpful-sounding plan.

WHAT A PAYLOAD LOOKS LIKE

    {
      "tree": [
        {"path": "README.md", "mode": "100644", "type": "blob",
         "content": "new text"},
        {"path": "src/app.py", "mode": "100644", "type": "blob",
         "sha": "the blob's existing sha"},
      ],
      "base_tree": "the current commit's tree sha",
    }

``build_tree_payload(entries, base_tree=...)`` validates every entry, requires
a non-empty ``base_tree`` when an existing branch is being updated, and returns
that dictionary (or raises :class:`GuardRefusal`).

``compare_trees(proposed, current, deletion_requested=(...))`` compares the
proposed paths with the current tree's paths and returns added / modified /
deleted / unchanged counts and names. It refuses by default when anything would
be deleted, unless each deleted path was named in ``deletion_requested`` - the
owner's explicit "yes, delete this file" is the only thing that permits it.

WHAT THIS DOES NOT DO

* It does not call GitHub, read a token or raise a card.
* It cannot prove that a path GitHub returns is harmless; it compares names.
* It does not decide that the owner approved a deletion. It only checks that
  the deletion was explicitly requested; the card and the gate still decide.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

#: The modes a Git tree entry may carry. ``040000`` is a folder, ``160000`` a
#: submodule, ``120000`` a link entry; the two file modes differ only in the
#: execute bit.
ALLOWED_MODES = frozenset({"100644", "100755", "120000", "040000", "160000"})

#: The three entry types the Git Data API accepts.
ALLOWED_TYPES = frozenset({"blob", "tree", "commit"})

#: The modes each entry type may carry. A tree is ``040000``, a submodule
#: ``160000``; a blob is a file or a link entry.
_MODES_BY_TYPE = {
    "blob": frozenset({"100644", "100755", "120000"}),
    "tree": frozenset({"040000"}),
    "commit": frozenset({"160000"}),
}

_DRIVE = re.compile(r"^[A-Za-z]:")


class GuardRefusal(Exception):
    """A plain-English reason this GitHub change is refused.

    ``str(exc)`` names what would go wrong and says that nothing was sent.
    """


def _refuse(why: str) -> None:
    raise GuardRefusal(why)


def _path_problem(path) -> str:
    """'' when ``path`` stays inside the repository, else a short reason."""
    if not isinstance(path, str) or not path:
        return "one file has no name"
    if "\x00" in path:
        return "one file name contains a hidden zero byte"
    if "\\" in path:
        return (f"one file is named {path!r}, and a backslash in a GitHub path "
                f"can point outside the repository")
    if path.startswith("/"):
        return f"one file is named {path!r}, which starts at the top of the repository"
    if _DRIVE.match(path):
        return f"one file is named {path!r}, which starts with a drive letter"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return f"one file is named {path!r}, which points outside the repository"
    return ""


def _clean_entry(entry, position: int) -> dict:
    """Validate one tree entry and return a copy with known fields only."""
    where = f"file {position + 1} in the change"
    if not isinstance(entry, dict):
        _refuse(f"Jarvis will not send this change to GitHub: {where} is not a "
                f"file description. Nothing was sent.")
    unknown = set(entry) - {"path", "mode", "type", "content", "sha"}
    if unknown:
        names = ", ".join(sorted(str(k) for k in unknown))
        _refuse(f"Jarvis will not send this change to GitHub: {where} uses a "
                f"field GitHub does not know ({names}). Nothing was sent.")
    path = entry.get("path")
    why = _path_problem(path)
    if why:
        _refuse(f"Jarvis will not send this change to GitHub: {why}. "
                f"Nothing was sent.")
    kind = entry.get("type") or "blob"
    if kind not in ALLOWED_TYPES:
        _refuse(f"Jarvis will not send this change to GitHub: {where} says it is "
                f"a {kind!r}, which is not a kind of file GitHub accepts. "
                f"Nothing was sent.")
    mode = entry.get("mode")
    if mode is None:
        mode = {"blob": "100644", "tree": "040000", "commit": "160000"}[kind]
    if mode not in ALLOWED_MODES or mode not in _MODES_BY_TYPE[kind]:
        _refuse(f"Jarvis will not send this change to GitHub: {where} is a "
                f"{kind} with the file mode {mode!r}, which GitHub would refuse. "
                f"Nothing was sent.")
    has_content = "content" in entry
    has_sha = "sha" in entry
    if kind == "blob":
        if has_content == has_sha:
            _refuse(f"Jarvis will not send this change to GitHub: {where} must "
                    f"carry either the file's text or its existing fingerprint "
                    f"(sha), and not both or neither. Nothing was sent.")
        if has_content and not isinstance(entry.get("content"), str):
            _refuse(f"Jarvis will not send this change to GitHub: {where} carries "
                    f"text that is not text. Nothing was sent.")
    else:
        if not has_sha or has_content:
            _refuse(f"Jarvis will not send this change to GitHub: {where} is a "
                    f"{kind} and must carry only its existing fingerprint (sha). "
                    f"Nothing was sent.")
    if has_sha and not (isinstance(entry.get("sha"), str) and entry["sha"].strip()):
        _refuse(f"Jarvis will not send this change to GitHub: {where} has an "
                f"empty fingerprint (sha), so GitHub would not know which file "
                f"it means. Nothing was sent.")
    out = {"path": path, "mode": mode, "type": kind}
    if has_content:
        out["content"] = entry["content"]
    else:
        out["sha"] = entry["sha"].strip()
    return out


def validate_tree_payload(payload, *,
                          updating_existing_branch: bool = True) -> dict:
    """Check a ``POST /git/trees`` payload and return its clean form.

    Refuses an unknown or misspelled top-level field (``baseTree`` in
    particular, because a misspelling is the same as leaving ``base_tree`` out),
    a tree that is not a list, an entry that GitHub would reject, and - when
    ``updating_existing_branch`` is true - a missing or blank ``base_tree``.
    """
    if not isinstance(payload, dict):
        _refuse("Jarvis will not send this change to GitHub: the request is not "
                "a file list. Nothing was sent.")
    unknown = set(payload) - {"tree", "base_tree"}
    if unknown:
        if "baseTree" in payload or "basetree" in {str(k).lower() for k in unknown}:
            _refuse("Jarvis will not send this change to GitHub: the request "
                    "spells the starting tree 'baseTree' (or another spelling "
                    "GitHub does not know). A misspelled base_tree is the same as "
                    "leaving it out, which would replace the whole repository with "
                    "only this change. Nothing was sent.")
        names = ", ".join(sorted(str(k) for k in unknown))
        _refuse(f"Jarvis will not send this change to GitHub: the request uses "
                f"fields GitHub does not know ({names}). Nothing was sent.")
    tree = payload.get("tree")
    if not isinstance(tree, list):
        _refuse("Jarvis will not send this change to GitHub: the request has no "
                "list of files. Nothing was sent.")
    entries = [_clean_entry(entry, i) for i, entry in enumerate(tree)]
    seen = set()
    for entry in entries:
        if entry["path"] in seen:
            _refuse(f"Jarvis will not send this change to GitHub: two parts of "
                    f"the change use the same file name {entry['path']!r}. "
                    f"Nothing was sent.")
        seen.add(entry["path"])
    base = payload.get("base_tree")
    if base is not None:
        if not isinstance(base, str):
            _refuse("Jarvis will not send this change to GitHub: the starting "
                    "tree is not a name. Nothing was sent.")
        if not base.strip():
            _refuse("Jarvis will not send this change to GitHub: the request "
                    "names an empty starting tree. Without a real one, GitHub "
                    "would replace the whole repository. Nothing was sent.")
    if updating_existing_branch and not (isinstance(base, str) and base.strip()):
        _refuse("Jarvis will not send this change to GitHub: the request does "
                "not say which version of the repository it starts from. Without "
                "that, GitHub would make a new repository holding only the files "
                "in this change, and every other file would be deleted. Nothing "
                "was sent.")
    out = {"tree": entries}
    if isinstance(base, str) and base.strip():
        out["base_tree"] = base.strip()
    return out


def build_tree_payload(entries, *, base_tree=None,
                       updating_existing_branch: bool = True) -> dict:
    """Build the exact dictionary for ``POST /git/trees``, or refuse.

    ``entries`` is the list described in the module docstring. When
    ``updating_existing_branch`` is true (the default, and the safe default),
    ``base_tree`` must be a non-empty string. Pass
    ``updating_existing_branch=False`` only for the first commit to a brand-new,
    empty repository.
    """
    try:
        entries_list = list(entries)
    except TypeError:
        _refuse("Jarvis will not send this change to GitHub: the change is not "
                "a list of files. Nothing was sent.")
    payload = {"tree": entries_list}
    if base_tree is not None:
        payload["base_tree"] = base_tree
    return validate_tree_payload(
        payload, updating_existing_branch=updating_existing_branch)


def _current_map(current) -> dict:
    """Normalise the current tree into ``{path: sha or None}``."""
    if isinstance(current, Mapping):
        items = current.items()
    elif isinstance(current, Iterable) and not isinstance(current, (str, bytes)):
        items = ((path, None) for path in current)
    else:
        _refuse("Jarvis cannot compare this change with the repository: the "
                "current file list is not a list. Nothing was sent.")
    out = {}
    for path, sha in items:
        why = _path_problem(path)
        if why:
            _refuse(f"Jarvis cannot compare this change with the repository: "
                    f"{why}. Nothing was sent.")
        if sha is not None and not isinstance(sha, str):
            _refuse(f"Jarvis cannot compare this change with the repository: "
                    f"the sha for {path!r} is not a name. Nothing was sent.")
        out[str(path)] = (sha.strip() if isinstance(sha, str) and sha.strip() else None)
    return out


def _requested_paths(deletion_requested) -> set:
    if isinstance(deletion_requested, str):
        return {deletion_requested} if deletion_requested else set()
    try:
        return {str(p) for p in deletion_requested}
    except TypeError:
        _refuse("Jarvis cannot tell which files you asked to delete, so nothing "
                "was sent.")


def compare_trees(proposed, current, *, deletion_requested=()) -> dict:
    """Compare a proposed tree with the current one, refusing unasked deletes.

    ``current`` is a mapping of ``{path: blob sha}`` (or just an iterable of
    paths, when the shas are not known). ``proposed`` is a list of tree entries
    in the same shape ``build_tree_payload`` accepts.

    Returns ``{"added", "modified", "deleted", "unchanged", "added_paths",
    "modified_paths", "deleted_paths", "requested_not_deleted"}``.

    A path in both trees counts as MODIFIED unless both sides carry the same
    non-empty sha, in which case it is UNCHANGED. A proposed entry that carries
    ``content`` has no sha to compare, so it counts as modified - the card must
    never understate a change. This compares content, not the file mode: a
    mode-only change (100644 to 100755) needs a current tree that carries modes,
    which this function does not take; the caller that reads the tree can
    compare modes itself and add them to the card.

    Raises :class:`GuardRefusal` when any path would be deleted and that path is
    not named in ``deletion_requested``. The refusal lists the files, because a
    request that deletes 214 files should say so before it is approved.
    """
    if isinstance(proposed, dict):
        proposed = proposed.get("tree")
    if not isinstance(proposed, list):
        _refuse("Jarvis cannot compare this change with the repository: the "
                "proposed file list is not a list. Nothing was sent.")
    entries = [_clean_entry(entry, i) for i, entry in enumerate(proposed)]
    proposed_map = {}
    for entry in entries:
        if entry["path"] in proposed_map:
            _refuse(f"Jarvis cannot compare this change with the repository: "
                    f"two parts use the same file name {entry['path']!r}. "
                    f"Nothing was sent.")
        proposed_map[entry["path"]] = entry.get("sha") if entry["type"] == "blob" else None
    current_map = _current_map(current)
    added = sorted(set(proposed_map) - set(current_map))
    deleted = sorted(set(current_map) - set(proposed_map))
    common = set(proposed_map) & set(current_map)
    modified = []
    unchanged = []
    for path in sorted(common):
        now = current_map.get(path)
        want = proposed_map.get(path)
        if now and want and now == want:
            unchanged.append(path)
        else:
            modified.append(path)
    requested = _requested_paths(deletion_requested)
    unasked = [path for path in deleted if path not in requested]
    if unasked:
        shown = ", ".join(repr(path) for path in unasked[:8])
        more = "" if len(unasked) <= 8 else f", and {len(unasked) - 8} more"
        _refuse(f"Jarvis will not send this change to GitHub: it would delete "
                f"{len(unasked)} file(s) that are in the repository now "
                f"({shown}{more}). Nothing was sent. If you really asked for "
                f"those files to be deleted, name them in the request.")
    return {
        "added": len(added),
        "modified": len(modified),
        "deleted": len(deleted),
        "unchanged": len(unchanged),
        "added_paths": added,
        "modified_paths": modified,
        "deleted_paths": deleted,
        "requested_not_deleted": sorted(requested - set(deleted)),
    }


def counts_line(report: dict) -> str:
    """The exact line the approval card shows, e.g. ``Added: 2 · Modified: 1 · Deleted: 0``."""
    return (f"Added: {report['added']} · Modified: {report['modified']} · "
            f"Deleted: {report['deleted']}")


__all__ = [
    "ALLOWED_MODES",
    "ALLOWED_TYPES",
    "GuardRefusal",
    "build_tree_payload",
    "compare_trees",
    "counts_line",
    "validate_tree_payload",
]
