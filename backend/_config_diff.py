"""What differs between your jarvis-framework.toml and this repository's copy.

apply-patches.ps1 never overwrites the owner's settings file - it is theirs,
and some of what is in it (tiers, [tools].enabled, notes folders) are
decisions only the owner can make. But a file that silently lags behind the
repository is how a new setting ends up read as "missing, so off" with nobody
told. So instead of copying, the script runs this and prints the difference,
setting by setting, for the owner to decide on.

    python backend\\_config_diff.py <your file> <this repository's file>

Prints plain lines, and exits 0 whether or not anything differs (a difference
is information, not an error). Exits 2 if a file cannot be read or parsed -
and says which, since a settings file that does not parse is itself worth
knowing about: the backend reads the same file.

Standard library only (tomllib, Python 3.11+). On an older Python it falls
back to `tomli` if installed, and otherwise to comparing lines.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - depends on the Python
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None


def flatten(d: dict, prefix: str = "") -> dict:
    """{"a": {"b": 1}} -> {"[a] b": 1}. Tables become the bracket part."""
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
        else:
            out[f"[{prefix}] {k}" if prefix else k] = v
    return out


def _show(v) -> str:
    s = repr(v) if not isinstance(v, str) else f'"{v}"'
    return s if len(s) <= 100 else s[:97] + "..."


def diff(theirs: dict, ours: dict) -> list[str]:
    a, b = flatten(theirs), flatten(ours)
    lines: list[str] = []
    new = sorted(set(b) - set(a))
    gone = sorted(set(a) - set(b))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    if new:
        lines.append(f"In this repository's copy but NOT in yours ({len(new)}) - "
                     "the backend treats a missing setting as its default:")
        lines += [f"    {k} = {_show(b[k])}" for k in new]
    if changed:
        lines.append(f"Set differently ({len(changed)}) - yours is the one in use:")
        lines += [f"    {k}:  yours {_show(a[k])}   repository {_show(b[k])}" for k in changed]
    if gone:
        lines.append(f"In yours but not in this repository's copy ({len(gone)}) - "
                     "kept, nothing removes them:")
        lines += [f"    {k} = {_show(a[k])}" for k in gone]
    return lines


def _lines(p: Path) -> set:
    keep = set()
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        s = raw.split("#", 1)[0].strip()
        if s:
            keep.add(s)
    return keep


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    theirs_p, ours_p = Path(argv[1]), Path(argv[2])
    if _toml is None:
        a, b = _lines(theirs_p), _lines(ours_p)
        print("(Python older than 3.11 and no tomli: comparing lines, not settings.)")
        for s in sorted(b - a):
            print(f"    only in the repository's copy:  {s}")
        for s in sorted(a - b):
            print(f"    only in yours:                   {s}")
        return 0
    parsed = []
    for p in (theirs_p, ours_p):
        try:
            parsed.append(_toml.loads(p.read_text(encoding="utf-8-sig")))
        except Exception as exc:  # noqa: BLE001 - reported, in words
            print(f"Could not read {p} as TOML: {exc}")
            return 2
    out = diff(parsed[0], parsed[1])
    if not out:
        print("Same settings as this repository's copy (comments and layout aside).")
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
