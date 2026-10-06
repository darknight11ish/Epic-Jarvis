#!/bin/sh
# Install the Android SDK packages the emulator jobs need, and do not let a
# half-finished DOWNLOAD look like a broken project.
#
#   sh scripts/install-android-emulator.sh
#
# WHY THIS EXISTS
#
# On 2026-10-04 the `face-shots` job died like this, on commit 6ace099c, before
# it compiled or ran a single line of this repository:
#
#   [===   ] 21% Downloading emulator-linux_x64-164
#   Warning: An error occurred while preparing SDK package Android Emulator:
#            Error reading Zip content from a SeekableByteChannel.
#   ##[error]Process completed with exit code 1.
#
# and the next thing the log said was a warning that the artifact step could
# find no screenshots - the only statement about the failure a reader was left
# with. The same commit PASSED on a re-run, so the download was corrupt, not
# the code: sdkmanager read a truncated or mangled zip off the network and
# gave up at 21% of the emulator package.
#
# A corrupt download is transient, so the fix is to ask again - after clearing
# whatever half-written file was left behind, because sdkmanager stages an
# unfinished download and resumes into the same bad bytes. Three attempts, not
# thirty: if the bytes are bad three times over, something real is wrong and
# the job should say so.
#
# The other half is what the log says when that happens. This script names the
# emulator in one line a person can read, instead of leaving a
# `No files were found with the provided path` warning to be misread as the
# cause.
#
# WHAT IT DELIBERATELY DOES NOT DO
#
# It never reports success unless `emulator/emulator` is really there and
# really runs. Every step after it is pointless without a working device, so a
# download that cannot be repaired must FAIL the job. A green run here means a
# working emulator, always.
#
# It also does not pin a package revision. Pinning the emulator to one build
# number is the obvious alternative, and it is a trap: when Google withdraws
# that revision, sdkmanager answers "Failed to find package" and the job is red
# for good until somebody edits it by hand - a worse failure than the flake it
# was meant to cure. Retrying keeps the job current and only spends time when
# the network is actually broken.
#
# WHAT IT CANNOT DO
#
# The download is GitHub's runner talking to Google. Nothing in this repository
# can prove a retry recovers a corrupt download on that network; only a real
# run that hits the flake can. What IS proved, in
# backend/test_ci_emulator_install.py, is the retry itself: that attempt one
# failing and attempt two succeeding ends in success, that every attempt
# failing ends in a named failure, and that an install reporting success while
# leaving no emulator binary is still caught.
set -u

ATTEMPTS=${EMU_ATTEMPTS:-3}
[ "$ATTEMPTS" -ge 1 ] 2>/dev/null || ATTEMPTS=3
SLEEP=${EMU_SLEEP:-10}
ATTEMPT_TIMEOUT=${EMU_ATTEMPT_TIMEOUT:-900}
EMULATOR_REL=${EMU_EMULATOR_REL:-emulator/emulator}
PARTIALS=${EMU_PARTIALS:-}
SDKM=${EMU_SDKMANAGER:-sdkmanager}
# How the installed binary is proved to run. Overridable so the test can drive
# the same verification path everywhere - on Windows a `sh`-scripted stub is
# not executable by name, only via `sh`, so the test sets this to that form
# rather than the test and the workflow taking different routes.
VERSION_CMD=${EMU_VERSION_CMD:-}

# The SDK root, from the environment first. android-actions/setup-android
# exports ANDROID_HOME and ANDROID_SDK_ROOT; if a future version stops doing
# that, sdkmanager's own location still gives the answer (it lives in
# <root>/cmdline-tools/<version>/bin/sdkmanager).
sdk_root() {
  if [ -n "${ANDROID_HOME:-}" ] && [ -d "$ANDROID_HOME" ]; then
    printf '%s\n' "$ANDROID_HOME"
    return 0
  fi
  if [ -n "${ANDROID_SDK_ROOT:-}" ] && [ -d "$ANDROID_SDK_ROOT" ]; then
    printf '%s\n' "$ANDROID_SDK_ROOT"
    return 0
  fi
  command -v "$SDKM" >/dev/null 2>&1 || return 1
  real=$(command -v "$SDKM")
  while [ -L "$real" ]; do
    target=$(readlink "$real") || break
    case $target in
      /*) real=$target ;;
      *) real=$(dirname "$real")/$target ;;
    esac
  done
  # <root>/cmdline-tools/<version>/bin/sdkmanager -> three levels up
  dirname "$(dirname "$(dirname "$real")")"
}

# Where sdkmanager stages a download it has not finished. Left in place, the
# next attempt resumes into the same partial file and fails identically.
clear_partials() {
  [ -n "$PARTIALS" ] || PARTIALS=$(sdk_root 2>/dev/null)/.downloadIntermediates
  if [ -d "$PARTIALS" ]; then
    echo "  clearing the half-written download left behind: $PARTIALS"
    rm -rf "$PARTIALS" 2>/dev/null || true
  fi
}

# One sdkmanager call, bounded so a stalled download cannot spend the whole
# job's 30-minute budget and leave the reason unstated.
#
# The probe matters: `timeout` is coreutils on the runner, but Windows has its
# own unrelated `timeout.exe`, and on a machine where that one answers first
# `timeout 900 sdkmanager ...` is "Invalid syntax" - the install never runs.
# Tested by what the command DOES, not by where it lives.
has_timeout() {
  command -v timeout >/dev/null 2>&1 || return 1
  timeout 5 true >/dev/null 2>&1 || return 1
  timeout 5 false >/dev/null 2>&1 && return 1
  return 0
}

run_one() {
  if has_timeout; then
    timeout "$ATTEMPT_TIMEOUT" "$SDKM" "$@"
  else
    "$SDKM" "$@"
  fi
}

install() {
  run_one --install "system-images;android-34;default;x86_64" \
                     "platforms;android-34" "platform-tools" "emulator"
}

# ---- the retry --------------------------------------------------------------
#
# The failing install sits in an `if` condition on purpose. GitHub runs a
# `run:` script as `sh -e`, which aborts on the first command that fails - the
# exact opposite of a retry. `if`, `while` and `until` conditions are exempt
# from that rule, which is why `rc=$?` is read in an `else` branch instead of
# being taken straight off the command line.
main() {
  # Accepting the licences is best-effort and never the reason to fail.
  yes 2>/dev/null | "$SDKM" --licenses >/dev/null 2>&1 || true

  attempt=1
  rc=1
  while [ "$attempt" -le "$ATTEMPTS" ]; do
    if [ "$ATTEMPTS" -gt 1 ]; then
      echo "sdkmanager: emulator and system image, attempt $attempt of $ATTEMPTS"
    fi
    if install; then
      rc=0
    else
      rc=$?
    fi
    if [ "$rc" -eq 0 ]; then
      break
    fi
    echo "  attempt $attempt failed (exit $rc)"
    if [ "$attempt" -lt "$ATTEMPTS" ]; then
      clear_partials
      echo "  asking Google again in ${SLEEP}s - a corrupt download is not a broken project"
      sleep "$SLEEP" 2>/dev/null || true
    fi
    attempt=$((attempt + 1))
  done

  # Report in the job's own vocabulary, then check the thing that actually
  # matters. `exit 1` here is a FAILED STEP, which is what a reader needs: it
  # stops the later steps and puts the reason above the missing-artifact
  # warning instead of leaving that warning to be read as the cause.
  if [ "$rc" -ne 0 ]; then
    echo "::error::The Android emulator could not be installed: sdkmanager failed $ATTEMPTS time(s) in a row (last exit $rc). Nothing was rendered and no screenshots exist. This is the SDK download, not this repository's code - re-run the job."
    exit 1
  fi

  root=$(sdk_root 2>/dev/null) || root=""
  if [ -z "$root" ]; then
    echo "::error::sdkmanager reported success but the Android SDK root could not be found, so the emulator cannot be trusted. Set ANDROID_HOME (android-actions/setup-android normally does)."
    exit 1
  fi

  emulator=$root/$EMULATOR_REL
  # Present, and not an empty file. The executable BIT is deliberately not
  # required: it does not survive every way this repository is checked out,
  # and the run below is the proof that matters.
  if [ ! -f "$emulator" ]; then
    echo "::error::The Android emulator could not be installed: sdkmanager reported success but $emulator is missing. Nothing was rendered and no screenshots exist."
    ls -l "$root/emulator" 2>&1 | head -20 || true
    exit 1
  fi

  # `-version` is the cheapest honest proof that the binary is not a truncated
  # stub. Its output is kept whatever it is, so a broken install is
  # diagnosable. Written as an if, not `&&`/`||`: as the last command of a
  # function, a trailing `||` would make the function's own status 0.
  if [ -z "$VERSION_CMD" ]; then
    if has_timeout; then
      VERSION_CMD="timeout 120 \"$emulator\" -version"
    else
      VERSION_CMD="\"$emulator\" -version"
    fi
  fi
  if ver=$(eval "$VERSION_CMD" 2>&1); then
    echo "Android emulator installed and answering:"
    printf '%s\n' "$ver" | head -5
  else
    echo "::error::The Android emulator could not be installed: $emulator exists but does not run. Nothing was rendered and no screenshots exist."
    printf '%s\n' "$ver" | head -20
    exit 1
  fi
}

# Sourced by the test, run by the workflow: only the second calls main.
case ${0##*/} in
  install-android-emulator.sh) main "$@" ;;
esac
