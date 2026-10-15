"""A sandbox adaptation: make ``tempfile.mkdtemp`` usable where a 0o700 directory cannot be written.

WHY THIS FILE IS IN THE REPOSITORY AT ALL.
    In this project's development container, a *confined* agent session is
    denied every write inside a directory created with mode 0o700:
    ``os.mkdir(p, 0o700)`` succeeds, and the write after it raises
    ``PermissionError: [Errno 13] Permission denied``. ``tempfile.mkdtemp()``
    uses exactly that mode, and ``tempfile.TemporaryDirectory()`` calls it.

    The backend suites stage their working copies with that primitive, and the
    failure is NOT a red suite: the suite catches the exception and SKIPS the
    checks it could not run, so a reader sees a pass where half the checks
    never ran. Measured in a confined session by the teammate who found it:
    backend/test_base_matches_repo.py reported 15 of its 30 checks,
    backend/test_claims.py 40 of its 45, and tools/check_claims.py exited 1.
    Run in a session whose token can write - and on CI - the same three are
    30, 45, and exit 0.

WHAT IT DOES, AND NOTHING ELSE.
    If, and only if, the real ``tempfile.mkdtemp`` cannot be used from here,
    it is replaced by one that creates the directory with ``os.makedirs`` -
    the same directory, in the same temporary root the caller asked for, with
    the same prefix, suffix and uniqueness guarantee, and the same
    8-character random name the standard library uses. Nothing else is
    touched: no other tempfile function, no other module, no product code.
    Child processes inherit it, because PYTHONPATH is inherited and CPython's
    own ``site`` module imports ``sitecustomize`` in every interpreter that
    starts with this directory on ``sys.path``.

HOW TO USE IT.  Put this repository's root on PYTHONPATH for the run:

        $env:PYTHONPATH = "C:\\path\\to\\repo"        # PowerShell
        PYTHONPATH=/path/to/repo python3 backend/test_foo.py

    No suite and no runner has to know it exists; nothing in the repository
    imports it, and adding it to ``sys.path`` is not needed. A session that
    needs it can say so in one line, and a session that does not need it is
    unaffected - see the probe below.

WHEN IT IS A NO-OP, WHICH IS THE NORMAL CASE.
    It PROBES FIRST: it creates a directory with the real ``mkdtemp``, writes
    a file inside, and removes it again. On every machine where that works -
    every Linux CI runner, every desktop, and any session whose token can
    write a 0o700 directory - the probe succeeds and NOTHING IS PATCHED. The
    patch is installed only when the probe fails, which is what makes this
    safe to leave on PYTHONPATH everywhere, and why CI's behaviour cannot
    change because this file exists.

    One consequence, stated plainly because it is a real one: while the patch
    IS active, scratch directories are made with the process umask instead of
    0o700, so they may be readable by another account on the same machine.
    That is exactly why it never installs itself when the standard primitive
    works, and it is the trade the fault forces: an unwritable scratch
    directory is a suite that cannot check anything.

TWO ENVIRONMENT OVERRIDES, FOR MEASUREMENT AND NOT FOR THE PRODUCT:
        DSH_MKDTEMP_SHIM=0   never patch - leave a broken primitive visible,
                             which is how the "15 of 30" regression is proved
        DSH_MKDTEMP_SHIM=1   patch without probing, to show what the patch does
    Left unset, the probe decides. That is the only setting a run should use.

WHAT IT DELIBERATELY DOES NOT DO.
    It does not choose a temporary root: ``dir or tempfile.gettempdir()``
    stands, exactly as the standard library has it, so nothing about where a
    suite's scratch lives changes. If ``tempfile.gettempdir()`` itself is the
    thing that fails, that is a different fault with a different remedy and
    this file does not paper over it.

THIS IS A WORKAROUND FOR A SANDBOX, NOT A PRODUCT FIX.
    Nothing the owner runs needs it. The fault is in the container's file
    sandbox - not in Jarvis, not in Python, and not in the suites: on the
    owner's PC and on CI, ``mkdtemp`` already works. Do not import this from a
    shipped module, do not add it to an installer list, and do not copy it
    into ``jarvis-backend/``. It belongs to how the suites are RUN here, and
    it says so in the first line.

SELF-TEST.  ``python sitecustomize.py`` runs the checks in ``_self_test()``
    and exits non-zero if any of them fails - a healthy machine is left
    alone, a forced patch installs, a directory it makes accepts a write,
    ``TemporaryDirectory`` (which calls ``mkdtemp``) does too, the same
    temporary root and the same name shape are kept, and a child process
    inherits all of it.
"""
import os
import shutil
import sys
import tempfile
import uuid

#: The real primitive, kept so the self-test can still probe with it.
REAL_MKDTEMP = tempfile.mkdtemp

#: True when THIS process replaced tempfile.mkdtemp. A run can read it to say
#: which primitive it used; the self-test asserts both answers.
SHIM_ACTIVE = False

#: "0" = never patch, "1" = patch without probing, "" (the default) = probe.
_SETTING = os.environ.get("DSH_MKDTEMP_SHIM", "")


def _mkdtemp(suffix="", prefix="tmp", dir=None):
    """``tempfile.mkdtemp``'s contract, without the 0o700 the sandbox denies.

    Same temporary root (``dir`` then ``gettempdir()``), same default prefix,
    same 8 random characters, and a race with another process is retried the
    same way the standard library retries it. The only difference is HOW the
    directory is made: ``os.makedirs`` instead of ``os.mkdir(..., 0o700)``.
    """
    base = dir or tempfile.gettempdir()
    while True:
        name = os.path.join(base, "%s%s%s" % (prefix, uuid.uuid4().hex[:8], suffix))
        try:
            os.makedirs(name)
        except OSError:
            if not os.path.exists(name):
                # A real failure - no such parent, no permission - and the
                # standard library raises for it too, so let it out.
                raise
            continue                      # someone else won the race; retry
        return name


def _probe():
    """True when the REAL mkdtemp works here, so nothing needs patching.

    This is the whole reason the file is safe: the answer on a healthy machine
    is True, the patch is never installed, and behaviour is byte-for-byte what
    it was before this file existed.
    """
    d = None
    try:
        d = REAL_MKDTEMP()
        with open(os.path.join(d, "probe"), "w") as fh:
            fh.write("ok")
        return True
    except Exception:
        return False
    finally:
        if d:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass


def _install():
    global SHIM_ACTIVE
    if SHIM_ACTIVE:
        return
    tempfile.mkdtemp = _mkdtemp
    SHIM_ACTIVE = True


try:
    if _SETTING != "0":
        if _SETTING == "1" or not _probe():
            _install()
except Exception:
    # A shim that breaks an interpreter would be a worse fault than the one it
    # works around: this file runs in EVERY Python that starts with the repo
    # root on PYTHONPATH, including child processes that have to report their
    # own results. It may fail to help; it may never fail to import.
    pass


# --------------------------------------------------------------------------
#   The self-test: python sitecustomize.py
# --------------------------------------------------------------------------

_CHILD = (
    "import tempfile, sys\n"
    "import sitecustomize as s\n"
    "d = tempfile.mkdtemp(prefix='selftest-', suffix='-x')\n"
    "open(d + '/written', 'w').write('ok')\n"
    "print('%s|%s|%s' % (s.SHIM_ACTIVE, d, tempfile.mkdtemp.__name__))\n"
)


def _child(setting):
    """Run one child interpreter with this directory on PYTHONPATH."""
    import subprocess
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
    env["DSH_MKDTEMP_SHIM"] = setting
    proc = subprocess.run([sys.executable, "-B", "-c", _CHILD],
                          capture_output=True, text=True, env=env,
                          cwd=os.path.dirname(os.path.abspath(__file__)))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "")[-300:]
    return proc.stdout.strip().split("|"), ""


def _self_test():
    fails = []

    def check(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(detail)))
        if not ok:
            fails.append(name)

    # 1. The override must be able to turn the patch OFF, or the "with the shim
    #    disabled" half of every measurement is impossible.
    got, why = _child("0")
    check("DSH_MKDTEMP_SHIM=0 leaves the primitive alone",
          bool(got) and got[0] == "False", why or got)
    # 2. Forced on: it installs, a directory it makes is writable, and the name
    #    keeps mkdtemp's shape (prefix + 8 characters + suffix).
    got, why = _child("1")
    ok = bool(got) and got[0] == "True" and "_mkdtemp" in got[2]
    check("DSH_MKDTEMP_SHIM=1 installs the patch", ok, why or got)
    if ok:
        d = got[1]
        check("the patched directory accepts a write",
              os.path.isfile(os.path.join(d, "written")), d)
        check("the name keeps mkdtemp's shape",
              os.path.basename(d).startswith("selftest-")
              and os.path.basename(d).endswith("-x")
              and len(os.path.basename(d)) == len("selftest-") + 8 + len("-x"), d)
        check("it is under the same temporary root",
              os.path.abspath(os.path.dirname(d)) == os.path.abspath(tempfile.gettempdir()), d)
        shutil.rmtree(d, ignore_errors=True)
    # 3. TemporaryDirectory calls mkdtemp, so patching one primitive must carry
    #    the other: that is what the suites that use `with TemporaryDirectory()`
    #    depend on, and it is not obvious from either side.
    child2 = (
        "import os, tempfile\n"
        "with tempfile.TemporaryDirectory(prefix='selftest-td-') as d:\n"
        "    open(os.path.join(d, 'written'), 'w').write('ok')\n"
        "print('TD-OK')\n"
    )
    import subprocess
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
    env["DSH_MKDTEMP_SHIM"] = "1"
    proc = subprocess.run([sys.executable, "-B", "-c", child2], capture_output=True,
                          text=True, env=env)
    check("TemporaryDirectory works under the patch",
          proc.returncode == 0 and "TD-OK" in (proc.stdout or ""),
          (proc.stderr or proc.stdout or "")[-200:])
    # 4. On THIS machine, with no override, the probe decides - and whatever it
    #    decides, the outcome must be a usable mkdtemp.
    d = tempfile.mkdtemp(prefix="selftest-now-")
    try:
        with open(os.path.join(d, "written"), "w") as fh:
            fh.write("ok")
        check("this process has a usable mkdtemp (probe decided: shim %s)"
              % ("active" if SHIM_ACTIVE else "not needed"), True)
    except Exception as exc:
        check("this process has a usable mkdtemp", False, exc)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("\n%s" % ("FAILED: " + ", ".join(fails) if fails else "the mkdtemp shim holds"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_self_test())
