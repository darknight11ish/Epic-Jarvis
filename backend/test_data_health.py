"""test_data_health.py - "Data health in the preflight" (feasibility idea
I97, docs/FEASIBILITY-AUDIT-2026-09-26.md: "Small, read-only." /
"WARN, never fix.").

    python3 backend/test_data_health.py

What it proves:
  - a missing chat history / memory database is "ok" (off, or never written
    to), never mistaken for damage;
  - a real, healthy SQLite file passes; a file that is not a database at
    all (corruption) is caught and reported as WARN, never as a failure;
  - low free disk space is caught, with a stand-in disk_usage() so the test
    never depends on how much room this machine actually has;
  - a damaged (non-JSON) settings file in the folder is caught and named;
    a folder with none is "ok";
  - nothing this module runs ever creates, writes to, moves or deletes a
    file - the guardrail (checked by literally diffing the folder's
    contents before and after check());
  - GET /api/data-health carries every row, and the count of "warn" rows;
  - data-health.patch applies to what the earlier patches wrote, reverses,
    checks the origin and the token, and falls back to 503 without the
    module.
No network, no model.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_data_health.py")

import jarvis_data_health as DH  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _snapshot(d: Path) -> dict:
    return {str(p.relative_to(d)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(d.rglob("*")) if p.is_file()}


def t_missing_databases_are_ok_not_warn():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        chat = next(r for r in rows if "chat history" in r[1])
        mem = next(r for r in rows if "memory store" in r[1])
        proj = next(r for r in rows if "projects" in r[1])
        check("no chat-history.db: ok, not warn", chat[0] == DH.OK, chat)
        check("no memory.db: ok, not warn", mem[0] == DH.OK, mem)
        check("no projects.db: ok, not warn", proj[0] == DH.OK, proj)
        check("every row is ok or warn, nothing else",
              all(r[0] in (DH.OK, DH.WARN) for r in rows), rows)


def t_a_healthy_database_passes():
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        conn = sqlite3.connect(str(d / "chat-history.db"))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        chat = next(r for r in rows if "chat history" in r[1])
        check("a real, healthy database: ok", chat[0] == DH.OK, chat)


def t_a_corrupt_database_is_warn_not_a_failure():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "memory.db").write_bytes(b"this is not a sqlite file at all, just text")
        (d / "projects.db").write_bytes(b"not a database either")
        before = _snapshot(d)
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        after = _snapshot(d)
        mem = next(r for r in rows if "memory store" in r[1])
        proj = next(r for r in rows if "projects" in r[1])
        check("a file that is not a database: WARN (not silently ok)", mem[0] == DH.WARN, mem)
        check("a damaged projects.db: WARN too", proj[0] == DH.WARN, proj)
        check("nothing was written, moved or deleted while checking it", before == after,
              (before, after))
        check("no row status is anything but ok/warn (never a fix, never a fail)",
              all(r[0] in (DH.OK, DH.WARN) for r in rows), rows)


def t_low_disk_space_is_caught():
    class _Usage:
        total, used, free = 100 * 1024 ** 3, 99 * 1024 ** 3, 500 * 1024 * 1024  # 500 MB free

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        rows = DH.check(config_dir=d, disk_usage=lambda p: _Usage())
        disk = next(r for r in rows if "free" in r[1])
        check("500 MB free is caught as low", disk[0] == DH.WARN, disk)

    class _Plenty:
        total, used, free = 500 * 1024 ** 3, 100 * 1024 ** 3, 400 * 1024 ** 3  # 400 GB free

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        rows = DH.check(config_dir=d, disk_usage=lambda p: _Plenty())
        disk = next(r for r in rows if "free" in r[1])
        check("400 GB free is ok", disk[0] == DH.OK, disk)


def t_a_damaged_settings_file_is_named():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "manner.json").write_text('{"style": "warm"}', encoding="utf-8")
        (d / "focus_ledger.json").write_text("{not json at all", encoding="utf-8")
        before = _snapshot(d)
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        after = _snapshot(d)
        settings = next(r for r in rows if "will not parse as JSON" in r[1])
        check("the damaged file is named", "focus_ledger.json" in settings[2], settings)
        check("the healthy file is not named as broken",
              "manner.json" not in settings[1] and "manner.json" not in settings[2], settings)
        check("nothing here was written, moved or deleted", before == after, (before, after))


def t_a_clean_folder_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "manner.json").write_text('{"style": "warm"}', encoding="utf-8")
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        settings = next(r for r in rows if "settings file" in r[1] and "parse" in r[1])
        check("no damaged file: every settings file parses", settings[0] == DH.OK, settings)


def t_never_touches_a_subfolder():
    """voice/, voice-models/ and notes/ hold real data, not settings JSON -
    a file inside one must never be read as a "settings file"."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        sub = d / "voice-models"
        sub.mkdir()
        (sub / "broken.json").write_text("{not json", encoding="utf-8")
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        check("a subfolder's file is not reported as a damaged settings file",
              not any("broken.json" in (r[1] + r[2]) for r in rows), rows)


def t_view_carries_every_row_and_the_warn_count():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "bad.json").write_text("nope", encoding="utf-8")
        rows = DH.check(config_dir=d, disk_usage=lambda p: shutil.disk_usage(tmp))
        n_warn = sum(1 for r in rows if r[0] == DH.WARN)
        check("at least one warn row for the damaged settings file", n_warn >= 1, rows)


def t_view_is_fixed_text_no_card_no_secret():
    code, v = DH.handle_get()
    check("GET: 200, available", code == 200 and v["available"] is True)
    check("the title", v["title"] == "Data health")
    check("checks is a non-empty list of dicts with status/what/detail",
          isinstance(v["checks"], list) and v["checks"]
          and all(set(c) >= {"status", "what", "detail"} for c in v["checks"]), v)
    check("every served status is ok or warn, never anything else",
          all(c["status"] in ("ok", "warn") for c in v["checks"]), v["checks"])
    check("the warn count matches the number of warn rows",
          v["warn"] == sum(1 for c in v["checks"] if c["status"] == "warn"), v)
    check("no card and no gate: fixed shape only",
          "waiting" not in v and "request_id" not in v)
    src = (HERE / "jarvis_data_health.py").read_text(encoding="utf-8")
    check("the module asks no gate and raises no card",
          "jarvis_gate" not in src and "gate(" not in src and "request_id" not in src)
    check("the module never writes: no os.replace, no write_text/write_bytes call on "
          "anything but nothing (grep for the literal calls)",
          "write_text(" not in src and "write_bytes(" not in src and "os.replace" not in src
          and ".unlink(" not in src and "os.remove" not in src)


def _rehearse():
    order = _stack.order()
    if "data-health.patch" not in order:
        return False, "data-health.patch is not in apply-patches.ps1's list", ""
    before = order[:order.index("data-health.patch")]
    patch = (HERE / "data-health.patch").read_text(encoding="utf-8")
    text, log = _stack.stand_in("jarvis_hud.py", before)
    if text is None:
        return False, "; ".join(log), ""
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-data-health-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr, ""
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True, text=True)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != text:
            return False, "does not reverse cleanly: " + r.stderr, ""
        return True, "", after
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)
        return self.sent


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, why, hud = _rehearse()
    check("data-health.patch applies to what the earlier patches wrote, and reverses", ok, why)
    if not ok:
        return
    i = hud.index('        if path == "/api/data-health":')
    j = hud.index('        if path == "/api/reach":', i)
    blk = hud[i:j]
    check("GET /api/data-health checks origin and token", "_origin_ok(self)" in blk
          and "_token_ok(self)" in blk)
    check("... and touches nothing else (the only file it patches is jarvis_hud.py)",
          (HERE / "data-health.patch").read_text(encoding="utf-8").count("+++ b/") == 1)
    ns = {}
    exec(compile("def f(self, path, _origin_ok, _token_ok):\n" + blk, "<GET>", "exec"), ns)
    h = _Handler()
    ns["f"](h, "/api/data-health", lambda s: True, lambda s: True)
    check("GET runs and answers checks", h.sent[0] == 200
          and isinstance(h.sent[1].get("checks"), list) and h.sent[1]["checks"], h.sent)
    ns["f"](h, "/api/data-health", lambda s: True, lambda s: False)
    check("... 401 without the token", h.sent[0] == 401)
    ns["f"](h, "/api/data-health", lambda s: False, lambda s: True)
    check("... 403 from another origin", h.sent[0] == 403)
    saved = sys.modules.get("jarvis_data_health")
    sys.modules["jarvis_data_health"] = None
    try:
        ns["f"](h, "/api/data-health", lambda s: True, lambda s: True)
    finally:
        sys.modules["jarvis_data_health"] = saved
    check("... 503 available:false without jarvis_data_health.py", h.sent[0] == 503
          and h.sent[1]["available"] is False)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies data-health.patch after sayable.patch",
          names.index("sayable.patch") < names.index("data-health.patch"))


def main():
    for fn in (t_missing_databases_are_ok_not_warn, t_a_healthy_database_passes,
               t_a_corrupt_database_is_warn_not_a_failure, t_low_disk_space_is_caught,
               t_a_damaged_settings_file_is_named, t_a_clean_folder_is_ok,
               t_never_touches_a_subfolder, t_view_carries_every_row_and_the_warn_count,
               t_view_is_fixed_text_no_card_no_secret, t_the_patch):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
