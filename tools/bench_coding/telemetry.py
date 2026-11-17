"""The telemetry the benchmark is allowed to claim, from files that exist.

FOUR SOURCES, and each one is read as it is rather than as the spec describes
it - because two of the spec's four assumptions are wrong on this PC (checked
2026-11-16, and repeated here so a later reader does not "correct" it back):

1. SPEED - `~/.openjarvis/speed.jsonl` exists and its first line is the
   schema. The real field names are `at`, `prompt_tokens`, `cached_tokens`,
   `tokens`, `tokens_per_s`, `total_ms`, `first_word_ms`, `model`,
   `prompt_rounds`, `tools`, `kind`, `streamed`, `token_source`,
   `on_gpu_percent`, `words`, `words_per_s` and `v`. There is **no**
   `completion_tokens` field; `tokens` is the completion count. `at` is a
   Unix timestamp in seconds, which is what lets this module attribute a row
   to the turn that produced it.

2. CLOUD MONEY - the spec says `~/.openjarvis/chatbot/api-money.json` /
   `daily-budget.json`. `daily-budget.json` **does not exist**: there is no
   daily cap yet. `api-money.json` does exist, so cloud spend is measured as
   the delta of its `months.<month>.<service>.dollars` figures. It is a
   month-to-date record written by the chatbot driver; the router's own cloud
   path may or may not write it, and the report says which was seen rather
   than assuming.

3. ROUTE - the spec says `X-Jarvis-Route` is a header carrying `local` vs
   `jarvis-escalate`. The header DOES exist, but its body is JSON and it
   carries no such two-word value: `lane` is the name of the lane/model that
   answered, and `where` is `local` or not. `client.py` keeps the header
   verbatim; this module only computes the parts a table needs.

4. GIT CLEANLINESS - `git status --short` and `git diff --stat` inside the
   disposable repository, always. Nothing is read from the product's tree.

A row that cannot be attributed to a turn is kept and flagged, never dropped
silently: the live PC is shared, and another session's answer between two
benchmark turns is a fact about the measurement, not noise to hide.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

#: The real schema of `speed.jsonl`'s first line, recorded here so the report
#: can quote it and a reader can diff it against the file on the PC.
SPEED_FIELDS = (
    "at", "cached_tokens", "first_word_ms", "kind", "model",
    "on_gpu_percent", "prompt_rounds", "prompt_tokens", "streamed",
    "token_source", "tokens", "tokens_per_s", "tools", "total_ms", "v",
    "words", "words_per_s",
)


def home() -> Path:
    return Path(os.path.expanduser("~"))


def speed_path() -> Path:
    return home() / ".openjarvis" / "speed.jsonl"


def money_path() -> Path:
    return home() / ".openjarvis" / "chatbot" / "api-money.json"


def daily_budget_path() -> Path:
    return home() / ".openjarvis" / "daily-budget.json"


def _read_json(path: Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def speed_rows(path: Path | None = None) -> list[dict]:
    """Every well-formed row, in file order. A broken line is skipped."""
    target = Path(path) if path else speed_path()
    rows: list[dict] = []
    try:
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def speed_count(path: Path | None = None) -> int:
    return len(speed_rows(path))


def speed_schema(path: Path | None = None) -> dict:
    """What the file's own first line says the schema is."""
    target = Path(path) if path else speed_path()
    rows = speed_rows(target)
    first = rows[0] if rows else {}
    return {
        "path": str(target),
        "exists": target.is_file(),
        "fields": sorted(first),
        "documented_fields": list(SPEED_FIELDS),
        "missing_from_first_row": sorted(set(SPEED_FIELDS) - set(first)),
    }


def speed_delta(before: int, after: int, path: Path | None = None) -> list[dict]:
    """The rows appended between two counts, with the fields the spec names."""
    rows = speed_rows(path)
    fresh = rows[max(0, before): max(0, after)] if after >= before else []
    kept = []
    for row in fresh:
        kept.append({
            "at": row.get("at"),
            "model": row.get("model"),
            "kind": row.get("kind"),
            "prompt_tokens": row.get("prompt_tokens"),
            "cached_tokens": row.get("cached_tokens"),
            "tokens": row.get("tokens"),
            "tokens_per_s": row.get("tokens_per_s"),
            "total_ms": row.get("total_ms"),
            "first_word_ms": row.get("first_word_ms"),
            "prompt_rounds": row.get("prompt_rounds"),
            "tools": row.get("tools"),
            "streamed": row.get("streamed"),
            "words": row.get("words"),
            "words_per_s": row.get("words_per_s"),
            "on_gpu_percent": row.get("on_gpu_percent"),
        })
    return kept


def attribute_turn(rows: list[dict], started: float, ended: float,
                   route_lane: str = "") -> dict:
    """Pick the row(s) that belong to one chat turn.

    A row belongs when its `at` is inside the turn's own wall-clock window
    (with a two-second grace before the request, because the writer stamps the
    row when the turn ENDS). The turn's lane, when the route header named one,
    is used to PREFER a matching model; it never silently discards the others.
    `chosen` is the single best row, `all` is every row in the window, and
    `ambiguous` is true when more than one row could be the turn's.
    """
    inside = []
    for row in rows:
        stamp = row.get("at")
        if not isinstance(stamp, (int, float)):
            continue
        if started - 2 <= float(stamp) <= ended + 5:
            inside.append(row)
    matching = [row for row in inside if route_lane and row.get("model") == route_lane]
    pool = matching or inside
    chosen = pool[-1] if pool else {}
    out = {
        "matched": bool(pool),
        "chosen": chosen,
        "all": inside,
        "ambiguous": len(inside) > 1,
        "window": [round(started, 3), round(ended, 3)],
        "route_lane": route_lane or "",
        "same_model_rows": len(matching),
    }
    if not out["matched"]:
        out["why"] = ("no speed.jsonl row landed in this turn's window"
                      if rows else "speed.jsonl is absent or empty")
    return out


def money_total(path: Path | None = None) -> dict:
    """Every service's month-to-date dollars, added up, plus the breakdown."""
    target = Path(path) if path else money_path()
    data = _read_json(target)
    months = data.get("months") if isinstance(data.get("months"), dict) else {}
    per_service: dict[str, float] = {}
    requests: dict[str, int] = {}
    for month in sorted(months):
        services = months[month] if isinstance(months[month], dict) else {}
        for service, row in services.items():
            if not isinstance(row, dict):
                continue
            try:
                dollars = float(row.get("dollars") or 0.0)
            except (TypeError, ValueError):
                dollars = 0.0
            per_service[service] = round(per_service.get(service, 0.0) + dollars, 9)
            try:
                count = int(row.get("requests") or 0)
            except (TypeError, ValueError):
                count = 0
            requests[service] = requests.get(service, 0) + count
    return {
        "path": str(target),
        "exists": target.is_file(),
        "total_dollars": round(sum(per_service.values()), 9),
        "per_service": per_service,
        "requests": requests,
        "months": sorted(months),
        "daily_budget_file": {
            "path": str(daily_budget_path()),
            "exists": daily_budget_path().is_file(),
            "note": ("not present on this PC (2026-11-16): there is no daily cap "
                     "yet, so spend is the api-money.json delta"),
        },
    }


def money_delta(before: dict, after: dict) -> dict:
    """The difference between two `money_total()` readings."""
    delta = round(float(after.get("total_dollars") or 0.0)
                  - float(before.get("total_dollars") or 0.0), 9)
    services: dict[str, float] = {}
    for name in sorted(set(before.get("per_service") or {})
                       | set(after.get("per_service") or {})):
        services[name] = round(
            float((after.get("per_service") or {}).get(name) or 0.0)
            - float((before.get("per_service") or {}).get(name) or 0.0), 9)
    return {"dollars": delta, "per_service": services}


def git(repo: Path, *args: str, timeout: int = 60) -> dict:
    """One `git` inside the disposable repo; a sentence instead of a stack."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "exit": -1, "out": "", "err": f"{type(exc).__name__}: {exc}"}
    return {"ok": done.returncode == 0, "exit": done.returncode,
            "out": done.stdout or "", "err": done.stderr or ""}


def git_snapshot(repo: Path) -> dict:
    """`git status --short` and `git diff --stat`, always, plus the paths."""
    status = git(repo, "status", "--short")
    stat = git(repo, "diff", "--stat")
    paths: list[str] = []
    for line in (status.get("out") or "").splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip().strip('"'))
    return {
        "status_short": status.get("out", ""),
        "status_exit": status.get("exit"),
        "diff_stat": stat.get("out", ""),
        "diff_stat_exit": stat.get("exit"),
        "changed_paths": paths,
        "clean": (status.get("out", "").strip() == ""),
    }


def environment() -> dict:
    """The machine facts a repeat of this run has to match."""
    import platform  # noqa: PLC0415

    facts = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "speed_schema": speed_schema(),
        "money": {key: value for key, value in money_total().items()
                  if key != "path"},
    }
    facts["money"]["path"] = money_total().get("path")
    return facts
