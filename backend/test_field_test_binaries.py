"""test_field_test_binaries.py - Step 0 of a field-test pass, checked offline.

    python3 backend/test_field_test_binaries.py

No pytest, no network, no real app. A throwaway git repository holds the
commit shapes a release produces, a fake HTTP function stands in for the
GitHub API and the live backend, and `tools/check_field_test_binaries.py` is
called through its own `main()` exactly as the checklist calls it.

WHAT THIS PROVES, and why each check can fail:

1. A feature commit that IS an ancestor of the installed build prints PASS,
   exit 0, and names the real `git merge-base --is-ancestor` command.
2. An installed build that lacks the feature, while the published build has
   it, is WAITING_FOR_RELEASE_BUILD with the version to install - exit 3.
3. A feature still building (neither installed nor the newest published build
   contains it) is WAITING_FOR_RELEASE_BUILD - **never FAIL and never
   UNWIRED**, which is Gemini's own wording for this gate.
4. A newer published build is a WAITING answer even when the installed build
   already has the feature: the checklist says install the newest build first.
5. Both requested surfaces must pass; one waiting makes the whole row wait.
6. An unknown commit, a missing surface, or a backend answering nonsense is
   REFUSED (exit 2) with words that say what to do - it is never guessed.
7. A version is compared as numbers (`0.2.10 > 0.2.9`), and a trailing `.0` is
   the same build; a non-version is refused.
8. The rolling release metadata (desktop title/body, the APK asset's commit)
   is read into the same version/commit pair - through an injected fake HTTP,
   so this suite never touches the network.
9. The live backend's `/api/version` is recorded with the HUD token when one
   is needed, and a backend that answers something else is refused.

Nothing here writes to the owner's folders, reads a real release or starts an
app. Standard library only.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import check_field_test_binaries as G  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-field-test-gate-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr or done.stdout}")
    return done.stdout.strip()


def _commit(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


def _make_repo(root: Path) -> dict:
    """base -> feature -> installed -> newer, and a `stale` sibling of base.

    `feature` is the row's commit; `installed` contains it; `stale` is a later
    published build on a branch that never merged the feature; `newer` is a
    later build that DOES contain it.
    """
    repo = root / "app-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "field-test@example.invalid")
    _git(repo, "config", "user.name", "field test")
    base = _commit(repo, "base.txt", "base\n")
    feature = _commit(repo, "feature.txt", "the feature\n")
    installed = _commit(repo, "installed.txt", "build that has it\n")
    newer = _commit(repo, "newer.txt", "next build\n")
    _git(repo, "checkout", "-q", "-b", "stale", base)
    stale = _commit(repo, "stale.txt", "an unrelated build\n")
    _git(repo, "checkout", "-q", "main")
    return {"repo": repo, "base": base, "feature": feature,
            "installed": installed, "newer": newer, "stale": stale}


CHAIN = _make_repo(TMP)


def _run(argv, http=None, tags=None):
    said = []
    code = G.main(["--repo", str(CHAIN["repo"]), *argv],
                  say=said.append, http=http, tags=tags)
    return code, "\n".join(said)


def _desktop(installed_sha, installed_version, latest_sha="", latest_version=""):
    argv = ["--feature-sha", CHAIN["feature"],
            "--installed-desktop", installed_version,
            "--desktop-sha", installed_sha]
    if latest_sha or latest_version:
        argv += ["--desktop-latest", latest_version,
                 "--desktop-latest-sha", latest_sha or installed_sha]
    return argv


def t_an_installed_build_that_has_the_feature_passes():
    code, out = _run(_desktop(CHAIN["installed"], "0.2.211",
                              CHAIN["installed"], "0.2.211"))
    check("the installed build contains the feature: PASS, exit 0",
          code == 0 and "VERDICT: PASS" in out, (code, out))
    check("... and the real ancestor command is printed",
          f"git merge-base --is-ancestor {CHAIN['feature']} {CHAIN['installed']}"
          in out, out)
    check("... and Step 0 records the full feature commit",
          f"feature commit: {CHAIN['feature']}" in out, out)
    check("... and both surfaces' versions are recorded",
          "desktop: installed 0.2.211" in out and "desktop-latest 0.2.211" in out, out)


def t_a_published_build_that_has_it_is_waited_for_not_failed():
    # Installed is the base (no feature); the published build DOES have it.
    code, out = _run(_desktop(CHAIN["base"], "0.2.210",
                              CHAIN["installed"], "0.2.211"))
    check("the installed build lacks it but a published build has it: WAITING",
          code == 3 and "VERDICT: WAITING_FOR_RELEASE_BUILD" in out, (code, out))
    check("... and the words say which build to install",
          "install 0.2.211 first" in out, out)
    check("... and a waiting row is NEVER called FAIL or UNWIRED",
          "FAIL" not in out and "UNWIRED" not in out, out)


def t_a_feature_still_building_is_waiting_never_fail():
    # Neither the installed build nor the newest published one has it.
    code, out = _run(_desktop(CHAIN["base"], "0.2.210",
                              CHAIN["stale"], "0.2.211"))
    check("a feature still building is WAITING_FOR_RELEASE_BUILD, exit 3",
          code == 3 and "VERDICT: WAITING_FOR_RELEASE_BUILD" in out, (code, out))
    check("... and it says so in the ruling's own words",
          "still building" in out, out)
    check("... never FAIL and never UNWIRED", "FAIL" not in out
          and "UNWIRED" not in out, out)


def t_a_newer_build_is_installed_before_the_ui_rows_even_when_it_passes():
    # The installed build has the feature, but a newer published build exists.
    code, out = _run(_desktop(CHAIN["installed"], "0.2.211",
                              CHAIN["newer"], "0.2.212"))
    check("a newer published build makes the row WAITING (install it first)",
          code == 3 and "newer published build 0.2.212" in out, (code, out))
    check("... and it says the installed copy already includes the feature",
          "already includes" in out, out)


def t_every_requested_surface_must_pass():
    argparse = _desktop(CHAIN["installed"], "0.2.211",
                        CHAIN["installed"], "0.2.211")
    code, out = _run(argparse + [
        "--installed-apk", "0.2.1905", "--apk-sha", CHAIN["base"],
        "--apk-latest", "0.2.1906", "--apk-latest-sha", CHAIN["installed"]])
    check("desktop PASS + phone WAITING means the whole row WAITS, exit 3",
          code == 3 and "- desktop: PASS" in out
          and "- phone: WAITING_FOR_RELEASE_BUILD" in out, (code, out))


def t_an_unknown_commit_is_refused_not_waited_for():
    code, out = _run(["--feature-sha", "deadbeef",
                      "--installed-desktop", "0.2.211",
                      "--desktop-sha", CHAIN["installed"]])
    check("a feature commit this clone does not hold is REFUSED, exit 2",
          code == 2 and "REFUSED" in out, (code, out))
    check("... and the words say to fetch before trusting the gate",
          "git fetch origin" in out, out)


def t_nothing_to_gate_is_refused():
    code, out = _run(["--feature-sha", CHAIN["feature"]])
    check("no desktop/APK/backend surface is REFUSED, exit 2",
          code == 2 and "nothing to gate" in out, (code, out))


def t_an_installed_commit_that_was_not_recorded_waits_rather_than_guessing():
    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--installed-desktop", "0.2.211"])
    check("an installed build whose commit is not known is WAITING, exit 3",
          code == 3 and "commit" in out and "not known" in out, (code, out))
    check("... and it asks for the SHA rather than assuming one",
          "--desktop-sha" in out or "pass its SHA" in out, out)


def t_versions_compare_as_numbers_and_trailing_zero_is_the_same_build():
    check("0.2.10 is newer than 0.2.9", G.version_is_newer("0.2.10", "0.2.9"))
    check("0.2.211.0 is the same build as 0.2.211",
          not G.version_is_newer("0.2.211.0", "0.2.211")
          and not G.version_is_newer("0.2.211", "0.2.211.0"))
    check("0.3.0 is newer than 0.2.999", G.version_is_newer("0.3.0", "0.2.999"))
    try:
        G.say_version("two point one")
        bad = "accepted"
    except G.Refused:
        bad = "refused"
    check("a non-version is refused rather than compared", bad == "refused", bad)


def _desktop_release(version: str, commit: str) -> dict:
    return {"title": f"Jarvis Desktop - latest ({version})",
            "body": f"Jarvis Desktop **{version}**, from commit `{commit[:7]}` "
                    f"on `main`.",
            "assets": [{"name": f"jarvis-desktop_{version}_x64-setup.exe"}],
            "target_commitish": commit}


def _client_release(version: str, commit: str) -> dict:
    return {"title": f"Jarvis for Android {version} (main @ {commit[:7]})",
            "body": f"**Jarvis for Android {version}** - from `main`, commit "
                    f"`{commit[:7]}`.",
            "assets": [{"name": f"jarvis-client-{commit[:7]}.apk"}],
            "target_commitish": commit}


def t_the_rolling_release_metadata_is_read_without_network():
    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--installed-desktop", "0.2.211",
                      "--desktop-sha", CHAIN["installed"]],
                     tags={G.DESKTOP_TAG: _desktop_release("0.2.211",
                                                         CHAIN["installed"])})
    check("desktop-latest's own title/body give the version and commit: PASS",
          code == 0 and "desktop-latest 0.2.211" in out, (code, out))
    info = G.release_info(G.DESKTOP_TAG, _desktop_release("0.2.212", CHAIN["newer"]),
                          CHAIN["repo"])
    check("the desktop release parses to its version and full commit",
          info == {"version": "0.2.212", "sha": CHAIN["newer"]}, info)
    info = G.release_info(G.CLIENT_TAG, _client_release("0.2.1905", CHAIN["installed"]),
                          CHAIN["repo"])
    check("the APK asset name gives the phone release's commit",
          info == {"version": "0.2.1905", "sha": CHAIN["installed"]}, info)


def t_the_github_read_uses_the_injected_http_and_a_failure_is_refused():
    calls = []

    def fake_http(url, headers=None):
        calls.append(url)
        if "client-latest" in url:
            return _client_release("0.2.1906", CHAIN["newer"])
        return _desktop_release("0.2.212", CHAIN["newer"])

    code, out = _run(["--feature-sha", CHAIN["feature"], "--github",
                      "--repo-slug", "owner/repo",
                      "--installed-desktop", "0.2.211",
                      "--desktop-sha", CHAIN["base"]], http=fake_http)
    check("--github reads the rolling releases through the injected HTTP",
          code == 3 and any("desktop-latest" in url for url in calls), (code, calls, out))
    check("... and a newer release the row does not have is WAITING",
          "install 0.2.212 first" in out, out)

    def broken_http(url, headers=None):
        raise G.Refused("network down")

    code, out = _run(["--feature-sha", CHAIN["feature"], "--github",
                      "--repo-slug", "owner/repo",
                      "--installed-desktop", "0.2.211",
                      "--desktop-sha", CHAIN["installed"]], http=broken_http)
    check("a GitHub read that fails is REFUSED, never guessed",
          code == 2 and "network down" in out, (code, out))


def t_the_live_backend_is_recorded_with_its_token_and_never_faked():
    seen = {}

    def fake_http(url, headers=None):
        seen["url"], seen["headers"] = url, dict(headers or {})
        return {"server": "jarvis-hud", "api": 7, "started": 1234}

    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--installed-desktop", "0.2.211",
                      "--desktop-sha", CHAIN["installed"],
                      "--backend-url", "http://127.0.0.1:8765",
                      "--backend-token", "T",
                      "--backend-sha", CHAIN["installed"]], http=fake_http)
    check("the live backend's /api/version is recorded with the HUD token",
          code == 0
          and seen.get("url") == "http://127.0.0.1:8765/api/version"
          and seen.get("headers", {}).get("X-Jarvis-Token") == "T", (code, seen, out))
    check("... and it names itself as the HUD, which is the only Origin-less "
          "client jarvis_owner_check.origin_ok accepts",
          seen.get("headers", {}).get("X-Jarvis-Client") == "hud", (code, seen, out))
    check("... and the Step 0 line names the server it really reached",
          "live backend: http://127.0.0.1:8765 reachable - server=jarvis-hud"
          in out, out)

    def nonsense_http(url, headers=None):
        return {"hello": "there"}

    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--backend-url", "http://127.0.0.1:8765",
                      "--backend-sha", CHAIN["installed"]], http=nonsense_http)
    check("a backend answering something that is not Jarvis is REFUSED",
          code == 2 and "not Jarvis's handshake" in out, (code, out))


def t_a_live_backend_without_the_feature_waits_for_the_update():
    def handshake(url, headers=None):
        return {"server": "jarvis-hud", "api": 7, "started": 1}

    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--backend-url", "http://127.0.0.1:8765",
                      "--backend-sha", CHAIN["base"]], http=handshake)
    check("a live backend older than the feature is WAITING, never FAIL",
          code == 3 and "run the backend update" in out
          and "FAIL" not in out and "UNWIRED" not in out, (code, out))


def t_bad_inputs_are_refused_in_plain_words():
    code, out = _run(["--feature-sha", CHAIN["feature"],
                      "--installed-desktop", "not-a-version",
                      "--desktop-sha", CHAIN["installed"]])
    check("a version that is not a version is REFUSED",
          code == 2 and "not a version" in out, (code, out))


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        try:
            t()
        except Exception:                              # noqa: BLE001
            FAILED.append(t.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for name in FAILED:
            print(f"  {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
