"""jarvis_energy.py - what one answer cost the graphics card, in joules.

    python3 backend/test_energy.py

No pytest, no graphics card, no nvidia-smi: readings are handed in through a
fake `run`, so this runs the same on a machine with an NVIDIA card, a machine
with none, and in CI. Nothing here touches the owner's real config folder or
his real energy.jsonl - the log is always a file in a fresh folder under
`dshwork/`, made and removed by this suite.

WHY NOT tempfile.mkdtemp() ALONE (2026-10-06): a confined run can have `%TEMP%`
redirected into the workspace and still be refused write there - `mkdir` says
yes, `open(..., "a")` then raises PermissionError, the log quietly holds
nothing, and eight checks fail for a reason that has nothing to do with this
module. A folder beside the code always works, so that is tried first and the
system temp folder is only the fallback. `E.record()` swallowing that refusal
(returning `{}`, raising nothing) is correct behaviour and is checked below;
it is the test that must not depend on a writable %TEMP%.

What it proves: off by default writes nothing; with the switch on and a
reading handed in, the arithmetic is exactly right (joules, joules per token,
tokens per joule, tokens per second); an unreadable reading is `{}` rather
than an exception; a missing nvidia-smi makes `available()` False and
`status()["why"]` a plain sentence; the file is capped at 500 rows; and two
controls on the source, because this module must never be able to send
anything anywhere.
"""
import atexit
import contextlib
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
# jarvis_energy.py is OURS - it ships in this repository, so this folder comes
# first. The framework stub next to it (jarvis_framework.py) is deliberately
# NOT importable here: nothing in this suite may pull in the gate.
sys.path.insert(0, str(HERE))
import jarvis_energy as E  # noqa: E402

FAILED, PASSED = [], []
TMPS = []
#: A folder beside the code, which a confined run can always write to. Its
#: parent (dshwork) is the folder the suites are run from in this repository.
UNDER_TEST = HERE.parent / "dshwork" / "tmp-energy"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _can_write(where: Path) -> bool:
    try:
        where.mkdir(parents=True, exist_ok=True)
        probe = where / ".write-probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def tmpdir() -> Path:
    """A fresh folder this suite may write to: beside the code first, the
    system temp folder only if even that is refused.

    `tempfile.mkdtemp(dir=...)` is NOT used under the code folder, though it
    would be the obvious way: it makes the directory mode 0o700, and a
    confined run then refuses `open(..., "w")` inside it (Errno 13) while
    happily writing into a folder made with a plain `mkdir` (0o777, less the
    umask). That is what made the first run of this suite report eight
    failures that had nothing to do with jarvis_energy.py.
    """
    make = getattr(tempfile, "_get_candidate_names")()
    for _ in range(64):
        d = UNDER_TEST / f"case-{next(make)}"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            break
        if _can_write(d):
            TMPS.append(d)
            return d
    fallback = Path(tempfile.mkdtemp(prefix="jarvis-energy-"))
    TMPS.append(fallback)
    return fallback


@atexit.register
def _tidy():
    for d in TMPS:
        shutil.rmtree(d, ignore_errors=True)


def tmplog() -> E.EnergyLog:
    return E.EnergyLog(tmpdir() / "energy.jsonl")


def a_reading(*, power=100.0, mem=2048.0, util=50.0, at=1_790_000_000):
    """Exactly what sample() hands back - built here rather than read from a
    card, so the arithmetic below can be checked against whole numbers."""
    return {"power_w": power, "mem_mb": mem, "util_pct": util, "at": at}


class Switched:
    """Turns the feature on (or off) for one block, and puts the environment
    back the way it was - even if the block raises."""

    def __init__(self, on=True):
        self.on = on

    def __enter__(self):
        self.keep = os.environ.get(E.ENV_SWITCH)
        if self.on:
            os.environ[E.ENV_SWITCH] = "1"
        else:
            os.environ.pop(E.ENV_SWITCH, None)
        return self

    def __exit__(self, *a):
        if self.keep is None:
            os.environ.pop(E.ENV_SWITCH, None)
        else:
            os.environ[E.ENV_SWITCH] = self.keep
        return False


class NoTool:
    """Makes `shutil.which` say nvidia-smi is not on this PC, whatever the
    machine running the suite actually has."""

    def __enter__(self):
        self.real = E.shutil.which
        E.shutil.which = lambda name, *a, **k: None
        return self

    def __exit__(self, *a):
        E.shutil.which = self.real
        return False


def t_the_public_surface_is_the_one_asked_for():
    for name in ("enabled", "available", "sample", "record", "status",
                 "EnergyLog", "default_path"):
        check(f"jarvis_energy.{name} exists", callable(getattr(E, name, None)),
              repr(getattr(E, name, None)))
    check("the file is energy.jsonl, next to speed.jsonl",
          E.FILE_NAME == "energy.jsonl")
    check("the cap is 500 rows", E.MAX_ROWS == 500)
    check("the query asks for power, memory and utilisation",
          E.QUERY == "power.draw,memory.used,utilization.gpu")


def t_off_by_default_writes_nothing():
    keep = os.environ.get(E.ENV_SWITCH)
    os.environ.pop(E.ENV_SWITCH, None)
    try:
        log = tmplog()
        calls = []

        def fake_run(argv):
            calls.append(argv)
            return "150.00, 2048, 45\n"
        row = E.record(500, 2.0, samples=[a_reading()], log=log, run=fake_run)
        check("with the switch off, record() returns {} and says nothing",
              row == {}, repr(row))
        check("... and writes no file at all", not log.path.exists(),
              str(log.path))
        check("... and does not go near the card either", calls == [], repr(calls))
        check("enabled() is False by default", E.enabled() is False)
    finally:
        if keep is None:
            os.environ.pop(E.ENV_SWITCH, None)
        else:
            os.environ[E.ENV_SWITCH] = keep


def t_the_reading_is_read_from_the_cards_own_csv():
    seen = []

    def fake_run(argv):
        seen.append(argv)
        return "123.45, 4096, 87\n"
    row = E.sample(run=fake_run)
    check("a reading comes back with the three numbers and a time",
          row.get("power_w") == 123.45 and row.get("mem_mb") == 4096.0
          and row.get("util_pct") == 87.0 and isinstance(row.get("at"), int), row)
    check("nvidia-smi is asked exactly the documented question, once",
          len(seen) == 1 and seen[0][0] == "nvidia-smi"
          and f"--query-gpu={E.QUERY}" in seen[0]
          and "--format=csv,noheader,nounits" in seen[0], seen)
    check("no card is named, so nvidia-smi's first card is the one read",
          "-i" not in seen[0], seen)
    second = E.sample(1, run=fake_run)
    check("a card number is passed through when one is asked for",
          "-i" in seen[-1] and "1" in seen[-1] and second.get("power_w") == 123.45,
          seen[-1])


@contextlib.contextmanager
def _a_card():
    """`available()` is a property of the HOST, not of the arithmetic.

    `t_the_arithmetic_is_exactly_right` hands its readings in through a fake
    `run`, so it must not also depend on nvidia-smi being on this machine's
    PATH: on CI's ubuntu-latest runner there is no NVIDIA driver, so
    `available()` is False and `record()` returns `{}` at its own guard
    before any arithmetic runs - every check in that function then fails for
    a reason that has nothing to do with what it is proving (2026-10-06; the
    two functions below already stub it this way, for this exact reason).

    NOT a loosened check: every assertion in the function is unchanged, and
    the "there is no nvidia-smi at all" contract keeps its own checks in
    `t_a_missing_nvidia_smi_is_a_plain_sentence`.
    """
    real = E.available
    E.available = lambda: True
    try:
        yield
    finally:
        E.available = real


def t_the_arithmetic_is_exactly_right():
    with _a_card(), Switched(True):
        log = tmplog()
        seen = []

        def fake_run(argv):
            seen.append(argv)
            return "120.00, 8000, 99\n"
        # 120 W for the whole 2.0 s of a 600-token answer.
        row = E.record(600, 2.0, samples=[a_reading(power=120.0)], log=log,
                       run=fake_run)
        check("the row comes back", isinstance(row, dict) and row.get("power_w") == 120.0,
              row)
        check("joules are mean watts x seconds", row.get("joules") == 240.0, row)
        check("joules per token is joules / tokens",
              row.get("joules_per_token") == 0.4, row)
        check("tokens per joule is tokens / joules",
              row.get("tokens_per_joule") == 2.5, row)
        check("tokens per second is tokens / seconds",
              row.get("tokens_per_second") == 300.0, row)
        check("the token count is on the row", row.get("tokens") == 600, row)
        check("the reading's power is used, so the card is not asked again",
              seen == [], repr(seen))

        rows = log.tail()
        check("exactly one row is on file, and it is the one returned",
              len(rows) == 1 and rows[0] == row, rows)

        # The mean of several readings, taken while the answer was written.
        log2 = tmplog()
        row2 = E.record(100, 3.0, samples=[a_reading(power=100.0),
                                           a_reading(power=200.0)], log=log2)
        check("with several readings, the mean watts are used",
              row2.get("power_w") == 150.0 and row2.get("joules") == 450.0
              and row2.get("joules_per_token") == 4.5, row2)

        # No samples: one reading is taken now, through the injected run.
        log3 = tmplog()
        calls = []

        def one_run(argv):
            calls.append(argv)
            return "60.00, 1024, 10\n"
        row3 = E.record(2000, 5.0, log=log3, run=one_run)
        check("with no samples, the card is read once at the end",
              len(calls) == 1 and row3.get("power_w") == 60.0, row3)
        check("... and the figures are worked out from that reading",
              row3.get("joules") == 300.0 and row3.get("joules_per_token") == 0.15
              and row3.get("tokens_per_second") == 400.0, row3)

        # A real card reading, replaying nvidia-smi's own CSV for one card.
        log4 = tmplog()
        row4 = E.record(50, 1.0, log=log4, run=lambda argv: "89.65, 1200, 91\n")
        check("a whole real CSV line works end to end",
              row4.get("joules") == 89.65 and row4.get("joules_per_token") == 1.793,
              row4)

        # Figures that cannot be worked out are left out, never guessed at.
        log5 = tmplog()
        odd = E.record(None, None, samples=[a_reading(power=100.0)], log=log5)
        check("with no tokens and no seconds, only the power is recorded",
              odd.get("power_w") == 100.0 and "joules" not in odd
              and "joules_per_token" not in odd, odd)
        log6 = tmplog()
        zeros = E.record(0, 0, samples=[a_reading(power=100.0)], log=log6)
        check("zero tokens and zero seconds are not divided by",
              "joules" not in zeros and "tokens_per_second" not in zeros
              and "joules_per_token" not in zeros, zeros)


def t_an_unreadable_reading_is_empty_not_an_exception():
    with Switched(True):
        for label, out in (
                ("a card that reports [N/A]", "[N/A], [N/A], [N/A]\n"),
                ("an empty answer", ""),
                ("nvidia-smi's own complaint", "NVIDIA-SMI has failed because it "
                                               "couldn't communicate with the driver\n"),
                ("junk", "hello, world\n"),
                ("a number that is not a number", "inf, nan, -5\n")):
            check(f"an unreadable reading ({label}) is {{}}, not an exception",
                  E.sample(run=lambda argv, out=out: out) == {},
                  repr(out))

        def boom(argv):
            raise OSError("nvidia-smi vanished between the check and the call")
        check("a run callable that raises is still {{}}", E.sample(run=boom) == {})
        check("and so is one that returns nothing at all",
              E.sample(run=lambda argv: None) == {})

        log = tmplog()
        check("a failed reading writes no row, and does not raise",
              E.record(500, 2.0, log=log,
                       run=lambda argv: "NVIDIA-SMI has failed\n") == {}
              and not log.path.exists())
        check("a clock that is a string is dropped, not written",
              E.sample(run=lambda argv: "1,2,3\n") != {}
              and E._clean_sample({"power_w": 1.0, "at": "yesterday"}) == {})

        # A file this suite may not write to (its parent is a file, not a
        # folder): still no exception, still an empty answer. The same shape a
        # confined run's refused %TEMP% takes.
        d = tmpdir()
        (d / "afile").write_text("x", encoding="utf-8")
        unwritable = E.EnergyLog(d / "afile" / "energy.jsonl")
        check("an unwritable energy.jsonl returns False instead of raising",
              unwritable.append({"v": 1, "at": 1, "power_w": 2.0}) is False)
        check("and reading it gives nothing instead of raising",
              unwritable.tail() == [])
        real_available = E.available
        E.available = lambda: True          # the card is fine; only the file is not
        try:
            check("record() onto an unwritable file still returns, writing nothing",
                  E.record(10, 1.0, samples=[a_reading()], log=unwritable) == {})
        finally:
            E.available = real_available


def t_a_missing_nvidia_smi_is_a_plain_sentence():
    with NoTool():
        check("with no nvidia-smi on PATH, available() is False",
              E.available() is False)
        with Switched(True):
            st = E.status(log=tmplog())
        check("status() says the card's power draw cannot be read",
              isinstance(st.get("why"), str) and st["why"] != ""
              and "power draw" in st["why"] and "cannot be read" in st["why"],
              st)
        check("... and it is one sentence, not a stack of them",
              st["why"].count(".") <= 1, st["why"])
        check("... and it does not blame a switch the owner never touched",
              "enabled = true" not in st["why"], st["why"])
        check("status() reports available False and nothing kept",
              st.get("available") is False and st.get("n") == 0
              and st.get("last") is None and st.get("mean_joules_per_token") is None,
              st)
        log = tmplog()
        check("record() writes nothing at all without nvidia-smi",
              E.record(100, 1.0, samples=[a_reading()], log=log) == {}
              and not log.path.exists(), str(log.path))

    # And with the tool there but the switch off, the sentence names the switch.
    if E.available():
        with Switched(False):
            st = E.status(log=tmplog())
        check("with nvidia-smi but the switch off, the sentence names the switch",
              st.get("available") is True and st.get("enabled") is False
              and "[energy] enabled = true" in st["why"], st)
        with Switched(True):
            st = E.status(log=tmplog())
        check("with both, the sentence says it is measuring",
              st.get("enabled") is True and st.get("available") is True
              and "measured" in st["why"], st)
    else:
        print("note: nvidia-smi is not on this PC, so the two "
              "'switch off'/'measuring' sentences were not checked")


def t_the_file_is_capped_at_five_hundred_rows():
    with Switched(True):
        log = tmplog()
        real = E.available
        E.available = lambda: True              # a card, for the arithmetic only
        try:
            for i in range(505):
                row = E.record(10 + i, 1.0, samples=[a_reading(power=100.0)], log=log)
                assert row, f"row {i} was not written"
        finally:
            E.available = real
        rows = log.tail()
        check("505 answers leave 500 rows on file", len(rows) == 500, len(rows))
        check("the oldest five are the ones dropped",
              [r["tokens"] for r in rows[:2]] == [15, 16]
              and rows[0]["tokens"] != 10, rows[:2])
        check("the newest row is still the one just written",
              rows[-1]["tokens"] == 514, rows[-1])
        raw = log.path.read_text(encoding="utf-8")
        check("and the file on disk really is 500 lines",
              len([ln for ln in raw.splitlines() if ln.strip()]) == 500)


def t_status_adds_up_what_is_on_file():
    with Switched(True):
        log = tmplog()
        real = E.available
        E.available = lambda: True
        try:
            E.record(100, 1.0, samples=[a_reading(power=100.0)], log=log)
            E.record(200, 1.0, samples=[a_reading(power=300.0)], log=log)
        finally:
            E.available = real
        st = E.status(log=log)
        # 100 J / 100 tokens = 1.0, 300 J / 200 tokens = 1.5; mean 1.25.
        check("the mean joules per token is the mean of the rows on file",
              st.get("mean_joules_per_token") == 1.25, st)
        check("n is how many rows are on file", st.get("n") == 2, st)
        check("last is the most recent row",
              st.get("last") and st["last"].get("tokens") == 200, st)
    st_empty = E.status(log=tmplog())
    check("an empty file is not an error: nothing kept, nothing claimed",
          st_empty.get("n") == 0 and st_empty.get("last") is None
          and st_empty.get("mean_joules_per_token") is None, st_empty)


def t_nothing_can_leave_the_pc():
    src = (HERE / "jarvis_energy.py").read_text(encoding="utf-8")
    for banned in ("urllib", "requests", "socket", "http.client", "ftplib",
                   "smtplib", "telnetlib"):
        check(f"CONTROL: jarvis_energy.py does not import {banned}",
              banned not in src, f"{banned} appears in the source")
    check("CONTROL: jarvis_energy.py does not import the gate (jarvis_gate)",
          "jarvis_gate" not in src)
    check("the only program it runs is nvidia-smi",
          '["nvidia-smi"' in src or "['nvidia-smi'" in src)


if __name__ == "__main__":
    for fn in (t_the_public_surface_is_the_one_asked_for,
               t_off_by_default_writes_nothing,
               t_the_reading_is_read_from_the_cards_own_csv,
               t_the_arithmetic_is_exactly_right,
               t_an_unreadable_reading_is_empty_not_an_exception,
               t_a_missing_nvidia_smi_is_a_plain_sentence,
               t_the_file_is_capped_at_five_hundred_rows,
               t_status_adds_up_what_is_on_file,
               t_nothing_can_leave_the_pc):
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
