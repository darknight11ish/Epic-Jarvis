#!/usr/bin/env python3
"""test_ci_emulator_install.py - the emulator download flake, and the retry
that answers it.

    python3 backend/test_ci_emulator_install.py

THE INCIDENT. On 2026-10-04 the `face-shots` job in
.github/workflows/jarvis-client.yml died on commit 6ace099c, before it
compiled or ran one line of this repository:

    [===   ] 21% Downloading emulator-linux_x64-164
    Warning: An error occurred while preparing SDK package Android Emulator:
             Error reading Zip content from a SeekableByteChannel.
    ##[error]Process completed with exit code 1.

The same commit PASSED on a re-run. The download was corrupt, not the code.
The only other thing the log said was that the artifact step found no
screenshots - a statement about the SYMPTOM, which is exactly how a flake
gets read as a broken project.

WHAT THIS SUITE CHECKS. Two different kinds of thing, and it is worth keeping
them apart:

  1. That the fix is really wired into the workflow - the face-shots job's
     install step runs scripts/install-android-emulator.sh, and that file is
     there. This is the half nothing else can see: a retry script nothing
     calls fixes nothing. The workflow is parsed with yaml.safe_load, so a
     broken edit fails here rather than on GitHub.

     The same half covers the 2026-10-06 incident that followed this one: the
     emulator downloaded and then could not RUN, because libpulse.so.0 was
     absent from the runner. The fix for that is an apt step, and what makes
     it a fix rather than decoration is its ORDER - before the step that runs
     `emulator -version` and before the step that starts the emulator - so
     that is what is checked, along with the assertion that caught it still
     being in the helper.

  2. That the retry behaviour itself is right - run for real, against stub
     installers, through the project's own check() harness:
       * attempt 1 fails, attempt 2 succeeds             -> exit 0, both tried
       * every attempt fails                              -> exit 1, and the
                                                             emulator is NAMED
       * sdkmanager says success but left no binary       -> exit 1
       * sdkmanager says success, binary exists, will
         not run                                          -> exit 1

     The last three are the point of "do not make the job tolerate a
     genuinely broken emulator". A retry that swallowed a real failure would
     be worse than the flake.

WHAT IT CANNOT CHECK. The download is GitHub's runner talking to Google.
Nothing here can prove that a second sdkmanager call recovers a corrupt
download on that network, and nothing here can prove the runner's own
`emulator` package unpacks. Only a real run that hits the flake can settle
that. This suite proves the retry LOGIC; it does not prove the recovery.

A POSIX shell is needed to run the script at all (the workflow runs on
Ubuntu, where /bin/sh is always there). Where there is none - a Windows
checkout with no Git for Windows - the run checks are SKIPPED by name, and
the wiring checks still run: a skip is a check that could not run here, and
says so, rather than passing quietly.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WORKFLOW = REPO / ".github" / "workflows" / "jarvis-client.yml"
HELPER = REPO / "scripts" / "install-android-emulator.sh"
EMU_VERSION_LINE = "Android emulator version 36.1.9.0 (build_id 12345678) (CL 12345)"

PASSED, FAILED, SKIPPED = [], [], []

try:
    import yaml  # noqa: E402
except ImportError:  # pragma: no cover - CI has PyYAML; a bare checkout may not
    yaml = None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name)
    if not cond and detail:
        print("        " + str(detail)[-700:])


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


# ---------------------------------------------------------------------------
# A POSIX shell. `sh` first (the script is POSIX and the workflow runs it with
# sh), then a Git-for-Windows shell by its real path, then whatever `bash` is:
# on a Windows box `bash` on PATH is often C:\WINDOWS\system32\bash.exe, the
# WSL launcher, which may have no distribution behind it at all.
# ---------------------------------------------------------------------------
def find_shell() -> str | None:
    for name in ("sh", "dash"):
        found = shutil.which(name)
        if found and _shell_works(found):
            return found
    for cand in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "sh.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "usr" / "bin" / "sh.exe",
    ):
        if cand.is_file() and _shell_works(str(cand)):
            return str(cand)
    for name in ("bash", "busybox"):
        found = shutil.which(name)
        if found and _shell_works(found):
            return found
    return None


def _shell_works(cmd: str) -> bool:
    try:
        r = subprocess.run([cmd, "-c", "echo ready"], capture_output=True,
                           text=True, timeout=120)
    except OSError:
        return False
    return r.returncode == 0 and "ready" in r.stdout


SHELL = find_shell()
SHELL_WHY = "no POSIX shell on this machine (the workflow runs on Ubuntu, which has one)"


def posix(p: Path) -> str:
    """A path the chosen shell can open.

    A Git-for-Windows shell needs C:\\a\\b as /c/a/b, and the GitHub runner - a
    plain Linux shell - needs the path untouched. cygpath is asked first where
    it exists, because it is the tool that knows; /c/... is the documented Git
    Bash mount form if it does not. Nothing here runs on Linux, so the paths
    the workflow uses are never rewritten.
    """
    s = str(p)
    if os.name != "nt" or not SHELL:
        return s
    if SHELL.startswith("/mnt/"):
        return "/mnt/" + s[0].lower() + s[2:].replace("\\", "/")
    cyg = shutil.which("cygpath")
    if cyg:
        r = subprocess.run([cyg, "-u", s], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    if len(s) > 1 and s[1] == ":":
        return "/" + s[0].lower() + s[2:].replace("\\", "/")
    return s.replace("\\", "/")


def run_helper(tmp: Path, sdk_root: Path, attempts: int, stub_install: str,
               emulator_body: str | None = None,
               emulator_present: bool = True) -> subprocess.CompletedProcess:
    """Run the REAL script, with only the things it cannot have here stubbed.

    `stub_install` is the body of a shell script standing in for the
    sdkmanager COMMAND (the real sdkmanager is not on this machine and could
    not be downloaded by a test), so what is under test is the retry loop
    around it. EMU_PARTIALS points the staging cleanup at a real folder the
    script can delete, so that half runs too rather than being skipped over.
    """
    partials = tmp / "download-intermediates"
    partials.mkdir(exist_ok=True)
    (partials / "half-written-download.zip").write_text("truncated", encoding="utf-8")

    stub = tmp / "sdkmanager-stub.sh"
    stub.write_text(stub_install.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    # The stub stands in for the sdkmanager COMMAND, and the script calls that
    # by name - `timeout "$ATTEMPT_TIMEOUT" "$SDKM" "$@"`. The real sdkmanager
    # is an executable file, so the stand-in has to be one too. Python writes
    # 0644, which is harmless on Windows (there is no exec bit, and Git's shell
    # reads the shebang regardless) and is EACCES on the Ubuntu runner:
    #   timeout: failed to run command '.../sdkmanager-stub.sh': Permission denied
    # exit 126, on every attempt - which is exactly what the Linux `backend`
    # job reported on 2026-10-06. The emulator stub below needs no chmod: the
    # script is told to run that one through `sh` (EMU_VERSION_CMD).
    os.chmod(stub, 0o755)

    # The "emulator" the install left behind, and how the script should ask it
    # its version. Always through `sh`: a shell script is not executable BY
    # NAME on Windows, and the point is the script's verification step, not
    # the platform's exec rules.
    emulator = sdk_root / "emulator" / "emulator"
    if emulator_present:
        emulator.parent.mkdir(parents=True, exist_ok=True)
        emulator.write_text(
            (emulator_body or f"#!/bin/sh\necho '{EMU_VERSION_LINE}'\n").replace("\r\n", "\n"),
            encoding="utf-8", newline="\n")

    env = {k: v for k, v in os.environ.items() if not k.startswith("EMU_")}
    env.update({
        "ANDROID_HOME": posix(sdk_root),
        "EMU_ATTEMPTS": str(attempts),
        "EMU_SLEEP": "0",
        "EMU_PARTIALS": posix(partials),
        "EMU_EMULATOR_REL": "emulator/emulator",
        # The stub is the sdkmanager the script calls.
        "EMU_SDKMANAGER": posix(stub),
        # How the script proves the binary runs. Same verification either way.
        "EMU_VERSION_CMD": f"sh {posix(emulator)} -version",
    })
    if os.name == "nt" and SHELL:
        # A Git-for-Windows shell started from PowerShell does not have the
        # Unix tools of its own installation on PATH, so `cat` and `head` are
        # missing inside the script. On the runner (Linux) PATH already has
        # them, and nothing here touches it.
        unix_bin = Path(SHELL).resolve().parent
        env["PATH"] = str(unix_bin) + os.pathsep + str(unix_bin.parent / "bin") \
            + os.pathsep + env.get("PATH", "")
    return subprocess.run([SHELL, posix(HELPER)], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))


def _sdk_root(tmp: Path) -> Path:
    root = tmp / "android-sdk"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# 1. The wiring: is the fix actually in the workflow, and is it valid YAML?
# ---------------------------------------------------------------------------
def t_workflow_is_one_yaml_document_with_the_jobs_intact():
    if yaml is None:
        skip("the workflow parses as YAML", "PyYAML is not installed here")
        return
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    check("the workflow parses with yaml.safe_load", isinstance(wf, dict))
    jobs = wf.get("jobs", {})
    check("face-shots is still a job of its own", "face-shots" in jobs,
          detail=f"jobs: {sorted(jobs)}")
    shots = jobs.get("face-shots", {})
    check("face-shots still needs the build job", shots.get("needs") == "build")
    check("face-shots is still non-gating (continue-on-error)",
          shots.get("continue-on-error") is True)
    check("face-shots still has its own 30-minute budget",
          shots.get("timeout-minutes") == 30, detail=shots.get("timeout-minutes"))
    check("face-shots still runs on ubuntu-latest", shots.get("runs-on") == "ubuntu-latest")
    # The steps are intact and in order - the change is one step's body, not a
    # reshaped job.
    names = [s.get("name") for s in shots.get("steps", [])]
    for wanted in ("Let the runner use KVM", "Compile the app and the test",
                   "Photograph every face", "Upload the face photographs"):
        check(f"the step {wanted!r} is still there", wanted in names, detail=names)


def t_the_install_step_runs_the_retry_helper():
    if yaml is None:
        skip("the install step runs the retry helper", "PyYAML is not installed here")
        return
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = wf["jobs"]["face-shots"]["steps"]
    # The step used to be called "Install the system image"; it is now
    # "Install the system image and the emulator", because that is what it
    # does. Matched by prefix so the rename itself is not what this checks -
    # what it checks is that the install step exists and runs the helper.
    step = next((s for s in steps
                 if str(s.get("name", "")).startswith("Install the system image")), None)
    check("the face-shots job still has an install-the-system-image step",
          step is not None, detail=[s.get("name") for s in steps])
    if step is None:
        return
    body = step.get("run", "")
    check("that step runs scripts/install-android-emulator.sh",
          "scripts/install-android-emulator.sh" in body, detail=body)
    check("the step is still run with sh (the script is POSIX)",
          "sh scripts/install-android-emulator.sh" in body, detail=body)
    check("the step no longer calls sdkmanager inline - one retry path, not two",
          "sdkmanager --install" not in body, detail=body)
    check("the helper is a real file in this checkout", HELPER.is_file(),
          detail=str(HELPER))
    # A CRLF-saved shell script is the classic way this file passes review and
    # dies on the runner ("sh: not found" on the shebang line).
    if HELPER.is_file():
        raw = HELPER.read_bytes()
        check("the helper is saved with LF line endings only",
              b"\r\n" not in raw, detail="the file contains CRLF")
        check("the helper starts with a #!/bin/sh shebang",
              raw.startswith(b"#!/bin/sh\n"), detail=raw[:40])


def t_the_library_the_emulator_needs_is_installed_before_it_is_used():
    """The 2026-10-06 failure, and the half of its fix that lives in YAML.

    PR #61's face-shots job downloaded the emulator fine and then could not RUN
    it:

        qemu-system-x86_64: error while loading shared libraries:
        libpulse.so.0: cannot open shared object file: No such file or directory

    so the retry below cannot answer it - a download that already succeeded
    gives the same binary. The library has to be installed on the runner.

    This is the wiring half, in the same spirit as the install-step check above:
    an apt line in a workflow proves nothing unless it is before the step that
    RUNS the binary, and the install step runs `emulator -version` itself
    (that is the assertion that caught the incident). So the check that matters
    is order.
    """
    if yaml is None:
        skip("the emulator's missing library is installed before it is used",
             "PyYAML is not installed here")
        return
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = wf["jobs"]["face-shots"]["steps"]
    names = [str(s.get("name", "")) for s in steps]

    def index_of(pred):
        return next((i for i, s in enumerate(steps) if pred(s)), None)

    apt = index_of(lambda s: "libpulse0" in str(s.get("run", "")))
    check("a step installs libpulse0 (the library that was missing)", apt is not None,
          detail=names)
    if apt is None:
        return
    body = str(steps[apt].get("run", ""))
    check("that step is a real apt install, not a comment about one",
          "apt-get install" in body and "libpulse0" in body, detail=body)

    # Order is the whole point. The install step verifies the binary by RUNNING
    # it, and the photograph step starts it for real; a library installed after
    # either one is a library installed too late.
    install = index_of(lambda s: str(s.get("name", "")).startswith("Install the system image"))
    shots = index_of(lambda s: s.get("name") == "Photograph every face")
    check("the install-the-system-image step is still in the job", install is not None,
          detail=names)
    check("the photographs step is still in the job", shots is not None, detail=names)
    if install is None or shots is None:
        return
    check("libpulse0 is installed BEFORE the step that runs `emulator -version`",
          apt < install, detail=f"apt at {apt}, install step at {install}")
    check("libpulse0 is installed BEFORE the emulator is started for photographs",
          apt < shots, detail=f"apt at {apt}, photographs at {shots}")

    # And the assertion that caught the incident is still the thing that runs
    # the binary, still in the helper, still refusing to call it installed.
    helper = HELPER.read_text(encoding="utf-8") if HELPER.is_file() else ""
    check("the helper still proves the emulator runs before claiming success",
          "-version" in helper and "exists but does not run" in helper,
          detail="the retry must not be weakened into a presence check")


def t_the_job_still_says_why_when_there_are_no_screenshots():
    if yaml is None:
        skip("the missing-artifact warning is explained", "PyYAML is not installed here")
        return
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    shots = wf["jobs"]["face-shots"]
    body = "\n".join(s.get("run", "") for s in shots["steps"])
    # The honest-failure wording has to live in the workflow too: the helper
    # knows about the emulator, the workflow knows about the screenshots.
    check("the workflow itself names the emulator as the reason a screenshot-less run failed",
          "could not be installed" in body,
          detail="no step says the emulator could not be installed")
    check("the workflow still insists the emulator booted before the tests run",
          "the emulator never finished booting" in body)
    up = next((s for s in shots["steps"] if s.get("name") == "Upload the face photographs"), {})
    check("the upload step is still best-effort (its absence is not the failure)",
          up.get("with", {}).get("if-no-files-found") == "warn", detail=up.get("with"))


# ---------------------------------------------------------------------------
# 2. The retry, run for real.
# ---------------------------------------------------------------------------
def t_a_corrupt_first_download_is_survived_by_the_second_attempt():
    if not SHELL:
        skip("attempt 1 fails, attempt 2 succeeds -> exit 0", SHELL_WHY)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        root = _sdk_root(tmp)
        counter = tmp / "attempts.txt"
        # First install call: the incident, "21% Downloading emulator..." and a
        # corrupt zip. Second call: succeeds. Exactly what the real re-run did.
        # The sdkmanager stub is also called once for --licenses before any of
        # this, so the counter reads 3 (1 licences + 2 installs).
        stub = f"""#!/bin/sh
n=0
[ -f "{posix(counter)}" ] && n=$(cat "{posix(counter)}")
n=$((n + 1))
printf '%s' "$n" > "{posix(counter)}"
if [ "$n" -eq 1 ]; then
  echo "done"
  exit 0
fi
if [ "$n" -eq 2 ]; then
  echo "[===   ] 21% Downloading emulator-linux_x64-164"
  echo "Warning: An error occurred while preparing SDK package Android Emulator:" >&2
  echo "         Error reading Zip content from a SeekableByteChannel." >&2
  exit 1
fi
echo "done"
exit 0
"""
        r = run_helper(tmp, root, attempts=3, stub_install=stub)
        out = (r.stdout or "") + (r.stderr or "")
        check("a corrupt first download is retried, and the second attempt's success is the run's success",
              r.returncode == 0, detail=f"exit {r.returncode}\n{out}")
        check("the run says it retried (attempt 1 of 3, then 2 of 3)",
              "attempt 1 of 3" in out and "attempt 2 of 3" in out, detail=out)
        check("the retry really re-ran the install (two installs, plus the licences call)",
              counter.is_file() and counter.read_text().strip() == "3",
              detail=counter.read_text() if counter.is_file() else "no counter")
        check("the half-written download was cleared before asking again",
              not (tmp / "download-intermediates").exists(), detail=out)
        check("the run still verified the emulator before claiming success",
              "Android emulator installed and answering" in out, detail=out)


def t_every_attempt_failing_names_the_emulator_and_still_fails():
    if not SHELL:
        skip("every attempt fails -> exit 1, naming the emulator", SHELL_WHY)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        root = _sdk_root(tmp)
        counter = tmp / "attempts.txt"
        stub = f"""#!/bin/sh
n=0
[ -f "{posix(counter)}" ] && n=$(cat "{posix(counter)}")
n=$((n + 1))
printf '%s' "$n" > "{posix(counter)}"
echo "Warning: An error occurred while preparing SDK package Android Emulator:" >&2
echo "         Error reading Zip content from a SeekableByteChannel." >&2
exit 1
"""
        r = run_helper(tmp, root, attempts=3, stub_install=stub)
        out = (r.stdout or "") + (r.stderr or "")
        check("a genuinely broken install still FAILS the step (exit 1)",
              r.returncode == 1, detail=f"exit {r.returncode}\n{out}")
        check("all three install attempts were made before giving up (plus the licences call)",
              counter.is_file() and counter.read_text().strip() == "4",
              detail=counter.read_text() if counter.is_file() else "no counter")
        check("the failure names the emulator, in the job's ::error:: vocabulary",
              "::error::" in out and "The Android emulator could not be installed" in out,
              detail=out)
        check("the failure says the code is not to blame, and what to do",
              "not this repository's code" in out and "re-run the job" in out, detail=out)
        check("the failure is not dressed up as a warning",
              "::warning::The Android emulator could not be installed" not in out, detail=out)


def t_a_successful_install_with_no_emulator_binary_is_caught():
    if not SHELL:
        skip("success with no emulator binary -> exit 1", SHELL_WHY)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        root = _sdk_root(tmp)
        # sdkmanager exits 0 into an emulator folder that is simply not there -
        # the shape of a download that "succeeded" into nothing.
        r = run_helper(tmp, root, attempts=3,
                       stub_install="#!/bin/sh\necho done\nexit 0\n",
                       emulator_present=False)
        out = (r.stdout or "") + (r.stderr or "")
        check("an install that reports success but leaves no emulator binary still FAILS",
              r.returncode == 1, detail=f"exit {r.returncode}\n{out}")
        check("and says which file was missing",
              "emulator/emulator" in out and "could not be installed" in out, detail=out)


def t_an_emulator_that_will_not_run_is_caught():
    if not SHELL:
        skip("an emulator that will not run -> exit 1", SHELL_WHY)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        root = _sdk_root(tmp)
        # Present, but exits 127 when asked its version - a truncated stub, or
        # a binary built for another machine.
        r = run_helper(
            tmp, root, attempts=3,
            stub_install="#!/bin/sh\necho done\nexit 0\n",
            emulator_body="#!/bin/sh\necho 'cannot execute: required file not found' >&2\nexit 127\n",
        )
        out = (r.stdout or "") + (r.stderr or "")
        check("an emulator binary that exists but will not run still FAILS",
              r.returncode == 1, detail=f"exit {r.returncode}\n{out}")
        check("and the run does not claim the emulator is installed and answering",
              "installed and answering" not in out, detail=out)


def t_the_success_path_prints_the_version_it_verified():
    if not SHELL:
        skip("the success path prints the version", SHELL_WHY)
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        root = _sdk_root(tmp)
        stub = "#!/bin/sh\necho done\nexit 0\n"
        r = run_helper(tmp, root, attempts=3, stub_install=stub)
        out = (r.stdout or "") + (r.stderr or "")
        check("a working install exits 0 and prints what it verified",
              r.returncode == 0 and EMU_VERSION_LINE in out,
              detail=f"exit {r.returncode}\n{out}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                import traceback
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print("skipped: " + ", ".join(SKIPPED))
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
