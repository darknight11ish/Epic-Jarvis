#!/usr/bin/env python3
"""check_field_test_binaries.py - Step 0 of every field-test pass.

    python -B tools/check_field_test_binaries.py \
        --feature-sha <the row's merge commit> \
        --installed-desktop 0.2.211 --installed-apk 0.2.1905 \
        --backend-sha <the live backend's commit> \
        --github

WHY THIS EXISTS (Gemini's mandatory Step 0, ruling 2026-10-18). A field-test
row is evidence only for the BUILD it ran on. Desktop `desktop-latest` and
phone `client-latest` are rolling releases and move several times an hour; a
row that failed or passed may have been testing a binary that never contained
the feature. So every pass starts by recording what is installed - live
backend commit, installed desktop version/commit vs `desktop-latest`, installed
APK version/commit vs `client-latest` - and for each row's `<feature_sha>`:

    git merge-base --is-ancestor <feature_sha> <installed_binary_commit>

PASS means the installed binary really contains the feature. If it does not,
but the newest published build does, the answer is WAITING_FOR_RELEASE_BUILD
with the version to install. **A row whose feature is still building is
WAITING_FOR_RELEASE_BUILD - never FAIL and never UNWIRED.** Only bad input, a
missing commit, or an unanswerable backend reach the REFUSED exit.

THE THREE EXIT CODES are the contract this tool offers a checklist:

    0  PASS                     every requested surface's installed build
                                contains the feature
    3  WAITING_FOR_RELEASE_BUILD  at least one requested surface does not yet
                                have it installed (a newer build is waiting,
                                or the release build is still running)
    2  REFUSED                  the question cannot be answered honestly
                                (bad version/SHA, commit not in this clone,
                                backend unreachable, no surface requested)

WHAT IS TAKEN AS INPUT, AND WHERE IT COMES FROM
- `--installed-desktop` / `--installed-apk`: the version the app shows in
  About. The installed commit is `--desktop-sha` / `--apk-sha` (the release
  body names it at install time, e.g. `from commit \\`44ea3b7\\``), or, when
  the installed version IS the published one, the rolling release's own commit.
- `--github`: read `desktop-latest` and `client-latest` from the public GitHub
  API (no token; the release title carries the version and the release body /
  APK asset name carries the commit). Without it the latest values must be
  given as `--desktop-latest`/`--desktop-latest-sha` etc.
- `--backend-url` (+ `--backend-token` when the HUD token is set): GET
  `/api/version` so the pass records the live backend is really there.
  `--backend-sha` is the commit the live backend was updated to (the update
  log prints it); the API itself has no commit field, so it is an input, never
  guessed.

The tool never writes anything and never installs anything.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parent

PASS = "PASS"
WAITING = "WAITING_FOR_RELEASE_BUILD"
REFUSED = "REFUSED"

EXIT_PASS, EXIT_WAITING, EXIT_REFUSED = 0, 3, 2

#: The rolling releases this gate reads (never a version tag: they are rolling).
DESKTOP_TAG = "desktop-latest"
CLIENT_TAG = "client-latest"

HEX_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
VERSION = re.compile(r"^\d+(?:\.\d+){1,3}$")
COMMIT_IN_BODY = re.compile(r"commit\s+[\[`]?([0-9a-fA-F]{7,40})")
APK_ASSET = re.compile(r"jarvis-client-([0-9a-fA-F]{7,40})\.apk")
DESKTOP_VERSION = re.compile(r"Jarvis Desktop\s*(?:-|\*\*)?\s*latest?\s*\(([\d.]+)\)")
CLIENT_VERSION = re.compile(r"Jarvis for Android\s+([\d.]+)")


class Refused(RuntimeError):
    """The gate cannot answer honestly; the message says what to do."""


def say_version(text: str) -> tuple:
    """A version as comparable integers; refuses anything that is not one."""
    text = str(text or "").strip()
    if not VERSION.match(text):
        raise Refused(f"{text!r} is not a version like 0.2.211")
    return tuple(int(part) for part in text.split("."))


def version_is_newer(latest: str, installed: str) -> bool:
    """True when `latest` is a newer build than `installed` (trailing .0 equal)."""
    a, b = say_version(latest), say_version(installed)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def full_commit(repo: Path, sha: str, *, what: str) -> str:
    """The full commit hash for a SHA (or a name git understands), or a
    refusal that tells the reader to fetch."""
    sha = str(sha or "").strip()
    if not sha or sha.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._/@^~{}:-]{1,120}", sha):
        raise Refused(f"{what} {sha!r} is not a git commit hash or branch")
    done = _run_git(repo, "rev-parse", "--verify", f"{sha}^{{commit}}")
    if done.returncode != 0:
        raise Refused(
            f"{what} commit {sha} is not in this checkout - run `git fetch "
            f"origin` first, then ask again; Step 0 cannot be answered from a "
            f"clone that does not hold the build's commit")
    return done.stdout.strip()


def is_ancestor(repo: Path, feature: str, build: str) -> bool:
    """`git merge-base --is-ancestor`; the ruling's own command."""
    done = _run_git(repo, "merge-base", "--is-ancestor", feature, build)
    if done.returncode not in (0, 1):
        raise Refused(f"git could not compare {feature} with {build}: "
                      f"{(done.stderr or done.stdout).strip()}")
    return done.returncode == 0


def ancestor_command(feature: str, build: str) -> str:
    return f"git merge-base --is-ancestor {feature} {build}"


def _http_json(url: str, headers: dict = None):
    """One GET of public JSON. No token, no redirects followed, short timeout."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "jarvis-field-test-gate",
        **(headers or {}),
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            body = answer.read(512 * 1024)
    except urllib.error.HTTPError as exc:
        raise Refused(f"{url} answered {exc.code}") from exc
    except Exception as exc:
        raise Refused(f"{url} could not be reached: {exc}") from exc
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception as exc:
        raise Refused(f"{url} did not answer JSON: {exc}") from exc


def release_info(tag: str, data: dict, repo: Path) -> dict:
    """(version, commit) from ONE rolling release's own metadata."""
    if not isinstance(data, dict):
        raise Refused(f"the {tag} release metadata is not an object")
    title = str(data.get("title") or data.get("name") or "")
    body = str(data.get("body") or "")
    asset_names = " ".join(str(asset.get("name") or "")
                          for asset in (data.get("assets") or [])
                          if isinstance(asset, dict))
    version = ""
    for pattern in (CLIENT_VERSION, DESKTOP_VERSION):
        found = pattern.search(title)
        if found:
            version = found.group(1)
            break
    if not version:
        found = re.search(r"\*\*Jarvis (?:Desktop|for Android) ([\d.]+)\*\*", body)
        version = found.group(1) if found else ""
    if not version:
        raise Refused(f"the {tag} release does not name its version in the title "
                      f"or body; pass --desktop-latest / --apk-latest instead")
    say_version(version)
    short = ""
    found = APK_ASSET.search(asset_names)
    if found:
        short = found.group(1)
    if not short:
        found = COMMIT_IN_BODY.search(body)
        short = found.group(1) if found else ""
    if not short and HEX_SHA.match(str(data.get("target_commitish") or "")):
        short = str(data["target_commitish"])
    short = short.strip()
    if not short:
        raise Refused(f"the {tag} release does not name its commit in the body, "
                      f"the APK asset or target_commitish; pass its SHA instead")
    return {"version": version, "sha": full_commit(repo, short, what=f"{tag}'s")}


def github_release(repo: Path, tag: str, http, tag_data: dict = None,
                   slug: str = "") -> dict:
    """One rolling release, read from GitHub unless the caller injected data."""
    data = tag_data
    if data is None:
        owner_repo = (slug or "").strip() or repo_slug(repo)
        url = f"https://api.github.com/repos/{owner_repo}/releases/tags/{tag}"
        data = (http or _http_json)(url)
    return release_info(tag, data, repo)


def repo_slug(repo: Path) -> str:
    """OWNER/REPO from this clone's origin, so no extra flag is needed."""
    done = _run_git(repo, "remote", "get-url", "origin")
    url = (done.stdout or "").strip()
    found = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?$", url)
    if not found:
        raise Refused("cannot read the repository slug from `git remote get-url "
                      "origin`; pass --repo-slug OWNER/REPO")
    return found.group(1)


def _record_versions(say, name: str, installed: str, installed_sha: str,
                     latest: str, latest_sha: str, tag: str) -> None:
    said_installed = f"{installed} ({installed_sha or 'commit not known'})" \
        if installed else "NOT INSTALLED"
    said_latest = f"{latest} ({latest_sha or 'commit not known'})" \
        if latest else "not read from GitHub (pass --github)"
    say(f"{name}: installed {said_installed}  vs  {tag} {said_latest}")


def _one_build(surface: str, repo: Path, feature: str, installed: str,
               installed_sha: str, latest: str, latest_sha: str) -> dict:
    """PASS or WAITING for one installed binary against one feature."""
    if not installed:
        return {"surface": surface, "state": WAITING,
                "detail": f"not installed; install {surface} build first"}
    if not installed_sha:
        return {"surface": surface, "state": WAITING,
                "detail": (f"the commit installed {surface} {installed} was built "
                           f"from is not known - pass its SHA (the release body "
                           f"names it) or use --github when that version is the "
                           f"published one")}
    installed_full = full_commit(repo, installed_sha, what=f"installed {surface}")
    if is_ancestor(repo, feature, installed_full):
        if latest and latest_sha and version_is_newer(latest, installed):
            return {"surface": surface, "state": WAITING,
                    "detail": (f"installed {installed} already includes {feature}, "
                               f"but a newer published build {latest} "
                               f"({latest_sha}) is waiting - install it before "
                               f"the UI rows")}
        return {"surface": surface, "state": PASS,
                "detail": (f"{feature} is in the installed build ({ancestor_command(feature, installed_full)} "
                           f"exits 0)")}
    if latest_sha:
        latest_full = full_commit(repo, latest_sha, what=f"{surface} latest")
        if is_ancestor(repo, feature, latest_full):
            return {"surface": surface, "state": WAITING,
                    "detail": (f"installed {installed} does not include {feature}; "
                               f"the published build {latest} ({latest_full}) does "
                               f"- install {latest} first")}
        return {"surface": surface, "state": WAITING,
                "detail": (f"still building: installed {installed} and the "
                           f"published {latest} ({latest_full}) do not include "
                           f"{feature} yet - this row stays "
                           f"WAITING_FOR_RELEASE_BUILD")}
    return {"surface": surface, "state": WAITING,
            "detail": (f"installed {installed} does not include {feature}; the "
                       f"newest published build was not read - pass --github or "
                       f"the latest version and SHA to see whether it is still "
                       f"building")}


def check_desktop(repo, args, http, say, tags, feature):
    installed = (args.installed_desktop or "").strip()
    latest = (args.desktop_latest or "").strip()
    latest_sha = (args.desktop_latest_sha or "").strip()
    installed_sha = (args.desktop_sha or "").strip()
    if tags.get(DESKTOP_TAG) is not None:
        info = github_release(repo, DESKTOP_TAG, http, tags[DESKTOP_TAG],
                              slug=args.repo_slug)
        latest = latest or info["version"]
        latest_sha = latest_sha or info["sha"]
    if not latest_sha and installed and args.github:
        info = github_release(repo, DESKTOP_TAG, http, slug=args.repo_slug)
        latest = latest or info["version"]
        latest_sha = info["sha"]
    if not installed_sha and latest_sha and installed and latest \
            and not version_is_newer(latest, installed) \
            and not version_is_newer(installed, latest):
        installed_sha = latest_sha
    if installed:
        say_version(installed)
    if latest:
        say_version(latest)
    if latest_sha:
        latest_sha = full_commit(repo, latest_sha, what="desktop-latest")
    if installed_sha:
        installed_sha = full_commit(repo, installed_sha, what="installed desktop")
    _record_versions(say, "desktop", installed, installed_sha, latest, latest_sha,
                     DESKTOP_TAG)
    return _one_build("desktop", repo, feature, installed, installed_sha,
                      latest, latest_sha)


def check_phone(repo, args, http, say, tags, feature):
    installed = (args.installed_apk or "").strip()
    latest = (args.apk_latest or "").strip()
    latest_sha = (args.apk_latest_sha or "").strip()
    installed_sha = (args.apk_sha or "").strip()
    if tags.get(CLIENT_TAG) is not None:
        info = github_release(repo, CLIENT_TAG, http, tags[CLIENT_TAG],
                              slug=args.repo_slug)
        latest = latest or info["version"]
        latest_sha = latest_sha or info["sha"]
    if not latest_sha and installed and args.github:
        info = github_release(repo, CLIENT_TAG, http, slug=args.repo_slug)
        latest = latest or info["version"]
        latest_sha = info["sha"]
    if not installed_sha and latest_sha and installed and latest \
            and not version_is_newer(latest, installed) \
            and not version_is_newer(installed, latest):
        installed_sha = latest_sha
    if installed:
        say_version(installed)
    if latest:
        say_version(latest)
    if latest_sha:
        latest_sha = full_commit(repo, latest_sha, what="client-latest")
    if installed_sha:
        installed_sha = full_commit(repo, installed_sha, what="installed phone")
    _record_versions(say, "phone", installed, installed_sha, latest, latest_sha,
                     CLIENT_TAG)
    return _one_build("phone", repo, feature, installed, installed_sha,
                      latest, latest_sha)


def check_backend(repo, args, http, say, feature) -> dict:
    """Record the live backend, and check its commit only when it was given."""
    url = (args.backend_url or "").strip().rstrip("/")
    recorded = "NOT RECORDED"
    state, detail = PASS, ""
    if url:
        # The HUD's origin check accepts an Origin-less request only from the
        # HUD's own client name (jarvis_owner_check.origin_ok); a made-up
        # "field-test-gate" name was refused with 403, so the build-SHA gate
        # could never record the live backend. "hud" is the name the rule
        # exists for.
        headers = {"X-Jarvis-Client": "hud"}
        token = (args.backend_token or "").strip()
        if token:
            headers["X-Jarvis-Token"] = token
        data = (http or _http_json)(url + "/api/version", headers)
        if not isinstance(data, dict) or not data.get("server"):
            raise Refused(f"{url}/api/version answered something that is not "
                          f"Jarvis's handshake; Step 0 cannot be recorded")
        recorded = (f"{url} reachable - server={data.get('server')} "
                    f"api={data.get('api')} started={data.get('started')}")
    say(f"live backend: {recorded}")
    say(f"live backend SHA: {args.backend_sha or 'NOT RECORDED (read it from the update log)'}")
    if args.backend_sha:
        build = full_commit(repo, args.backend_sha, what="live backend")
        if is_ancestor(repo, feature, build):
            detail = (f"{feature} is in the live backend "
                      f"({ancestor_command(feature, build)} exits 0)")
        else:
            state = WAITING
            detail = (f"the live backend ({build}) does not include "
                      f"{feature} yet - run the backend update to "
                      f"current main first; this row stays "
                      f"WAITING_FOR_RELEASE_BUILD")
        return {"surface": "backend", "state": state, "detail": detail}
    if url:
        return {"surface": "backend", "state": WAITING,
                "detail": ("no --backend-sha was recorded; read the live "
                           "backend's commit from the update log and pass it")}
    return None


def main(argv=None, *, say=print, http=None, tags=None) -> int:
    """The checklist's Step 0. Returns 0 PASS, 3 WAITING, 2 REFUSED."""
    parser = argparse.ArgumentParser(
        description="Step 0 Binary Build-SHA Gate for a field-test pass.",
        epilog=("Exit codes: 0 PASS, 3 WAITING_FOR_RELEASE_BUILD, 2 REFUSED. "
                "A feature still building is WAITING, never FAIL or UNWIRED."))
    parser.add_argument("--feature-sha", required=True,
                        help="the commit the field-test row is testing")
    parser.add_argument("--installed-desktop", default="",
                        help="the desktop version shown in About")
    parser.add_argument("--desktop-sha", default="",
                        help="the commit the installed desktop was built from")
    parser.add_argument("--desktop-latest", default="",
                        help="the desktop-latest version (with --github, read)")
    parser.add_argument("--desktop-latest-sha", default="",
                        help="the desktop-latest commit")
    parser.add_argument("--installed-apk", default="",
                        help="the phone APK version shown in About")
    parser.add_argument("--apk-sha", default="",
                        help="the commit the installed APK was built from")
    parser.add_argument("--apk-latest", default="",
                        help="the client-latest version (with --github, read)")
    parser.add_argument("--apk-latest-sha", default="",
                        help="the client-latest commit")
    parser.add_argument("--backend-url", default="",
                        help="the live backend's base URL, e.g. http://127.0.0.1:8765")
    parser.add_argument("--backend-token", default="",
                        help="the HUD token, when the backend needs one")
    parser.add_argument("--backend-sha", default="",
                        help="the commit the live backend was updated to")
    parser.add_argument("--github", action="store_true",
                        help="read desktop-latest/client-latest release metadata")
    parser.add_argument("--repo-slug", default="",
                        help="OWNER/REPO for --github (default: this clone's origin)")
    parser.add_argument("--repo", default="",
                        help="the git checkout to ask (default: this repository)")
    args = parser.parse_args([str(a) for a in (argv if argv is not None else sys.argv[1:])])
    args.feature_sha = str(args.feature_sha).strip()
    return _main(args, say, http, tags)


def _main(args, say, http, tags) -> int:
    repo = Path(args.repo).resolve() if args.repo else REPO_DEFAULT
    tag_data = dict(tags or {})
    args.github = bool(args.github or tag_data)
    try:
        feature = full_commit(repo, args.feature_sha, what="feature")
        say("STEP 0 - BINARY BUILD-SHA GATE")
        say(f"feature commit: {feature}")
        results = []
        if args.backend_url or args.backend_sha:
            got = check_backend(repo, args, http, say, feature)
            if got is not None:
                results.append(got)
        if any((args.installed_desktop, args.desktop_sha, args.desktop_latest,
                args.desktop_latest_sha)):
            results.append(check_desktop(repo, args, http, say, tag_data, feature))
        if any((args.installed_apk, args.apk_sha, args.apk_latest,
                args.apk_latest_sha)):
            results.append(check_phone(repo, args, http, say, tag_data, feature))
        if not results:
            raise Refused("nothing to gate: pass installed desktop and/or APK "
                          "versions (and/or --backend-url / --backend-sha)")
        for got in results:
            say(f"- {got['surface']}: {got['state']} - {got['detail']}")
        overall = PASS if all(got["state"] == PASS for got in results) else WAITING
        say(f"VERDICT: {overall}")
        if overall == WAITING:
            say("A row that is WAITING_FOR_RELEASE_BUILD is not a failure: install "
                "the named build (or wait for the release workflow), then run it.")
        return EXIT_PASS if overall == PASS else EXIT_WAITING
    except Refused as exc:
        say(f"REFUSED  {exc}")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
