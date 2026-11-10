- **2026-11-10 — GitHub parity behind one card per action: merge-commit-only
  merge and isolated fix-and-push:** Asked to choose the shape of GitHub in
  Jarvis, the owner picked **"Everything at once"** on a clickable card (Gemini
  ruling Q1, 10:40 PT): a read-only PR cockpit, a card-gated merge, and a
  card-gated fix-and-push. This reverses the 2026-11-03 "Read + actions" and
  2026-11-09 one-create boundary **only behind one approval card per mutating
  action** - there is no standing grant, no bulk path and nothing auto-approved:
  each merge and each PR-branch push raises its own one-shot card, and a
  loosened tier line still cannot run one with nobody asked because both tools
  are in `jarvis_agent.NEEDS_A_PERSON`. The merge is **merge-commit only** and
  carries a **TOCTOU pin**: the card names the pull request's exact 40-hex head
  commit, and immediately before the one `PUT` Jarvis re-reads the pull request
  and refuses - sending nothing - if the commit moved, the pull request is a
  draft or not mergeable, a check is still running, or a required check did not
  conclude success; the request body is exactly `{"merge_method": "merge",
  "sha": <pinned sha>}` and no code path can make it anything else.
  Fix-and-push is **isolated-worktree only**: it copies the pull request into
  its own folder under `%LOCALAPPDATA%\Jarvis\github-fix` (never the live
  checkout), and the push stage re-reads the live pull request and refuses any
  folder outside that root, a protected branch (`main`, `master`, `release/*`,
  `hotfix/*`), a branch that is not the pull request's own, a dirty tree, a fork,
  any force/delete/mirror flag, and any changed file on the **pre-push
  credential denylist** (the same names, key stems and extensions
  `jarvis_project_read` refuses). The token is never in a git URL, never on a
  command line and never written to disk - the push carries it in git's own
  environment config. **Everything ships off by default**: both new actions are
  `"ask"` in both shipped `[autonomy.tiers]` files, each tool has its own switch
  under Settings, What asks first (off until turned on), and the absolute bans
  that remain are unchanged and total: **force-push, squash-merge, rebase-merge,
  admin bypass, auto-merge, bypassing required checks, pushing directly to
  main/master/release/*, and deleting or closing repositories or branches** -
  `jarvis_github.NEVER_WORDS` is now exactly the sentence that says so. The
  record of the build is `docs/JARVIS-API.md` §190.9 and §190.10,
  `backend/jarvis_github.py`, `backend/github-tools.patch` and
  `backend/test_github_tools.py`.
