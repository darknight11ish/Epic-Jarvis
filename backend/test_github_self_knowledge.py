#!/usr/bin/env python3
"""test_github_self_knowledge.py - Jarvis knows its own GitHub, and never invents
what it can do there.

    python3 backend/test_github_self_knowledge.py

WHY THIS EXISTS. The tool-capability audit of 2026-11-07
(`.dsh-scratch/TOOL-CAPABILITY-AUDIT-2026-11-07/`, live 0.2.437) drove eight
recorded GitHub questions through the real chat and measured the answers against
the built surface. The result was one true answer out of eight, and every fault
had the same cause: the only deterministic GitHub paths were "connect" and "is
it connected", so everything else fell to the local model, which guessed:

  * "what can you do with my GitHub?" named only the two 2026-09-30 research
    features - the built 2026-11-03 read+actions surface had no catalogue row;
  * "can you merge a pull request?" INVENTED a merge approval card ("I can
    propose the merge to you now") while `jarvis_github.NEVER` names merge and
    no merge action, card or endpoint exists;
  * "what do you need before you can read my repos?" said nothing was needed
    and asked to be pointed at a folder (a GitHub repo is not a folder);
  * "what is your GitHub repository?" denied having a public repository (it is
    `darknight11ish/Epic-Jarvis`);
  * "how do I disconnect it?" asked what "it" was, while the careful true
    sentence already sat in `/api/accounts` (`jarvis_accounts.state_words`).

WHAT THIS SUITE PROVES, all read-only and with no network:

  1. the catalogue has ONE `connected-github` row naming the real surface (the
     six tools, `github_search`, the scheduled `watch_github` job, the three
     carded actions and the never-list), and every generated copy is current;
  2. "what can you do with my GitHub?" is answered from that row, not from the
     model and not only from the two research rows;
  3. `/api/accounts`'s GitHub row is the real six-ability surface, no longer
     "Read-only: private repositories and CI status";
  4. `jarvis_accounts.sentence()` / `state_words()` are REACHABLE from chat -
     the accounts list, one account's abilities, and its removal sentence;
  5. all eight recorded questions route deterministically (no model), and no
     answer invents a merge card or a tool that does not exist;
  6. the connected / not-connected state comes from `jarvis_github.connected()`,
     never from a guess;
  7. no merge/push/commit/close/delete surface exists anywhere: not a tool, not
     a planner, not a gate row, not a case;
  8. the four earlier fixes this branch also carries: the six tools' enable
     hints name the real control, the connect card's summary is current, the
     update grammar takes "YOUR latest release", and the feature guide no longer
     says "no switch" beside a `where` that says "switch it on".

Nothing here opens a socket, raises a card, types a secret or calls a model.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-github-self-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ.pop("JARVIS_BACKEND", None)
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))

import jarvis_agent as AG               # noqa: E402
import jarvis_asks_first as ASK         # noqa: E402
import jarvis_connect_account as CA     # noqa: E402
import jarvis_feature_guide as FG       # noqa: E402
import jarvis_github as GH              # noqa: E402
import jarvis_quick as Q                # noqa: E402
import jarvis_tool_profiles as TP       # noqa: E402
import jarvis_accounts as ACC           # noqa: E402
import jarvis_feature_catalogue as CAT  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _reply(question):
    intent = Q.match(question)
    if intent is None:
        return None, None, ""
    return intent, intent.name, str(Q.run(intent, None, 0.0).reply)


def _feature_row():
    rows = json.loads((REPO / "features" / "features.json").read_text(encoding="utf-8"))
    return next((row for row in rows if row.get("id") == "connected-github"), None)


def _github_family():
    return next((f for f in ACC.FAMILIES if f.id == "github"), None)


# --------------------------------------------------------------------------
#   1. the catalogue row, and every copy generated from it
# --------------------------------------------------------------------------
SIX_TOOLS = ("github_list", "github_read_file", "github_ci_status",
             "github_comment", "github_open_issue", "github_rerun_workflow")
#: 2026-11-09: the owner's "create a repository called Fitness Band" added ONE
#: carded create to the surface, so the real surface was seven tools.
SEVEN_TOOLS = SIX_TOOLS + ("github_create_repo",)
#: 2026-11-10 (the owner's "Everything at once"): the read-only PR cockpit, the
#: carded merge-commit merge and the carded fix-and-push. Ten tools, six carded
#: actions (three reads and the cockpit share github_inspect).
TEN_TOOLS = SEVEN_TOOLS + ("github_pr_scan", "github_merge_pr",
                           "github_fix_and_push")


def t_the_catalogue_has_the_connected_github_row():
    row = _feature_row()
    check("features.json has ONE connected-github row", row is not None)
    if row is None:
        return
    blob = " ".join(str(row.get(k) or "") for k in
                    ("title", "what", "where", "asks", "limit")).lower()
    check("it names the ten real tools",
          all(tool in blob for tool in TEN_TOOLS), blob)
    check("it names github_search and the scheduled watch_github job",
          "github_search" in blob and "watch_github" in blob, blob)
    check("it names the six carded actions",
          all(w in blob for w in ("comment", "open an issue", "re-run a workflow",
                                  "create one new, empty repository",
                                  "merge one pull request", "push a fix")), blob)
    check("it says a merge is merge-commit only and pinned to one commit",
          "merge commit" in blob and "pinned to" in blob, blob)
    check("it names the absolute bans that remain",
          all(w in blob for w in ("never squash", "never force-push",
                                  "never deletes")), blob)
    check("it says not-connected is a state that offers the connect card",
          "not connected" in blob and "connect my github" in blob, blob)
    check("its gate rows are the seven real card actions",
          set(row.get("gate") or []) == {"github_inspect", "github_comment",
                                         "github_open_issue",
                                         "github_rerun_workflow",
                                         "github_create_repo", "github_merge_pr",
                                         "github_fix_and_push"},
          row.get("gate"))
    check("the generated catalogue carries the row",
          any(r.get("id") == "connected-github" for r in CAT.FEATURES),
          [r.get("id") for r in CAT.FEATURES][-3:])
    src = (REPO / "features" / "features.json").read_bytes()
    import hashlib
    check("the generated catalogue records this features.json's own sha256",
          CAT.SOURCE_SHA256 == hashlib.sha256(src).hexdigest(), CAT.SOURCE_SHA256)
    copies = (REPO / "jarvis-desktop" / "src" / "features.json",
              REPO / "jarvis-client" / "app" / "src" / "main" / "assets"
              / "features.json")
    check("both apps' copies are byte-identical to the source",
          all(c.is_file() and c.read_bytes() == src for c in copies))


# --------------------------------------------------------------------------
#   2. the deterministic capability answer
# --------------------------------------------------------------------------
def t_the_capability_answer_names_the_connected_surface():
    intent, name, reply = _reply("what can you do with my GitHub?")
    check("'what can you do with my GitHub?' stays the catalogue answer",
          name == "feature_capabilities", name)
    check("... and names the connected-GitHub row",
          "Read and act on your own GitHub" in reply, reply[:300])
    check("... and the three carded actions",
          "open an issue" in reply.lower() and "re-run a workflow" in reply.lower(),
          reply[:400])
    check("... and the bans that remain (never squash, never force-push)",
          "never squash" in reply.lower()
          and "never force-push" in reply.lower(), reply[-500:])
    check("... and the token requirement",
          "personal access token" in reply.lower(), reply[-400:])


# --------------------------------------------------------------------------
#   3. /api/accounts's GitHub row is the real surface
# --------------------------------------------------------------------------
def t_the_accounts_row_is_the_real_surface():
    family = _github_family()
    check("jarvis_accounts still has a GitHub family", family is not None)
    if family is None:
        return
    check("its abilities are the nine real actions",
          set(family.abilities) == {"github_inspect", "github_comment",
                                    "github_open_issue", "github_rerun_workflow",
                                    "github_create_repo", "github_merge_pr",
                                    "github_fix_and_push", "github_read",
                                    "research_authenticated"},
          family.abilities)
    row = ACC.state_of("github")
    check("the row no longer says 'Read-only: private repositories and CI status'",
          "read-only: private repositories and ci status" not in str(row).lower(),
          row.get("limit"))
    check("its limit names read AND act, each on its own card",
          "read and act" in str(row.get("limit") or "").lower()
          and "own card" in str(row.get("limit") or "").lower(), row.get("limit"))
    check("its limit says merge commit only, pinned to the card's commit",
          "merge commit" in str(row.get("limit") or "").lower()
          and "pinned to" in str(row.get("limit") or "").lower(),
          row.get("limit"))
    check("... and still names the bans that remain",
          "never force-push" in str(row.get("limit") or "").lower()
          and "delete/close" in str(row.get("limit") or "").lower(),
          row.get("limit"))
    check("its can sentence names reading repositories and commenting",
          "repositories" in str(row.get("can") or "").lower()
          and "comment" in str(row.get("can") or "").lower(), row.get("can"))
    view = ACC.accounts_view(probe=False)
    fam = next((f for f in view["families"] if f.get("id") == "github"), None)
    check("/api/accounts shows the same nine abilities", fam is not None
          and len(fam.get("abilities") or []) == 9,
          (fam or {}).get("abilities"))


# --------------------------------------------------------------------------
#   4. the accounts answers are REACHABLE (they had no door before)
# --------------------------------------------------------------------------
def t_the_accounts_answers_are_reachable():
    intent, name, reply = _reply("what accounts do I have?")
    check("'what accounts do I have?' is the accounts list", name == "accounts_answer",
          name)
    check("... and it names every family from jarvis_accounts.sentence()",
          "GitHub" in reply and "Email" in reply, reply[:200])
    intent, name, reply = _reply("what abilities does my GitHub connection have?")
    check("'what abilities does my GitHub connection have?' is the account answer",
          name == "accounts_answer" and intent is not None
          and intent.f.get("account") == "github",
          (name, intent.f if intent else None))
    check("... and it names the carded GitHub actions",
          "github comment" in reply.lower() and "Asks you first, every time" in reply,
          reply[:300])
    intent, name, reply = _reply("how do I disconnect my GitHub?")
    check("'how do I disconnect my GitHub?' is the account answer",
          name == "accounts_answer" and intent is not None
          and intent.f.get("shape") == "disconnect",
          (name, intent.f if intent else None))
    row = ACC.state_of("github")
    check("... and the answer IS the row's own removal sentence",
          str(row.get("remove") or "")[:40] in reply, reply[:400])
    check("... and never asks what 'it' is",
          "you haven't told me what" not in reply.lower(), reply[:200])
    check("all three new intents are read-only",
          {"github_self", "accounts_answer"} <= set(Q.READ_ONLY_INTENTS))


# --------------------------------------------------------------------------
#   5. the eight recorded questions route deterministically
# --------------------------------------------------------------------------
def t_the_eight_recorded_questions_route_deterministically():
    cases = (
        ("what can you do with my GitHub?", "feature_capabilities"),
        ("can you merge a pull request?", "github_self"),
        ("can you comment on an issue?", "github_self"),
        ("what do you need before you can read my repos?", "github_self"),
        ("is my GitHub connected?", "connect_account"),
        ("what can't you do on GitHub?", "github_self"),
        ("how do I connect my GitHub?", "connect_account"),
        ("how do I disconnect it?", None),
        ("how do I disconnect my GitHub?", "accounts_answer"),
        ("what is your GitHub repository?", "github_self"),
        ("where does your code live?", "github_self"),
        ("what GitHub tools do you have?", "github_self"),
        ("do you have a feature that reads my GitHub?", "github_self"),
        ("did you merge that PR?", "github_self"),
        ("what's your CI status?", "github_self"),
        ("what asks before GitHub acts?", "github_self"),
    )
    for question, expected in cases:
        intent = Q.match(question)
        got = intent.name if intent is not None else None
        if expected is None:
            # "it" with no noun is genuinely ambiguous: the model keeps it, and
            # the honest fix is the named question above, not a guess.
            check(f"{question!r} is not claimed by a guess", got != "accounts_answer",
                  got)
            continue
        check(f"{question!r} -> {expected}", got == expected, got)

    # The answers themselves: every recorded question, in full.
    wanted = {
        "what is your GitHub repository?": ("darknight11ish/Epic-Jarvis",),
        "can you merge a pull request?": ("one approval card", "merge commit",
                                          "refused", "never squash"),
        "did you merge that PR?": ("one approval card", "merge commit",
                                   "never squash"),
        "what can't you do on GitHub?": ("force-push", "squash-merge", "delete",
                                         "main"),
        "what do you need before you can read my repos?":
            ("personal access token", "let the ai use this"),
        "what GitHub tools do you have?": TEN_TOOLS + ("github_search",
                                                       "watch_github"),
        "can you comment on an issue?": ("approval card",),
        "what's your CI status?": ("GitHub Actions", "darknight11ish/Epic-Jarvis"),
        "what asks before GitHub acts?": ("ask you first every time",),
        "do you have a feature that reads my GitHub?": TEN_TOOLS,
    }
    for question, needles in wanted.items():
        intent, name, reply = _reply(question)
        low = reply.lower()
        check(f"{question!r} answers with the real facts",
              all(n.lower() in low for n in needles), reply[:400])


# --------------------------------------------------------------------------
#   6. connected state is READ, not guessed
# --------------------------------------------------------------------------
class _FakeGitHub:
    def __init__(self, connected):
        self._connected = connected

    def connected(self):
        return self._connected

    def never_words(self):
        return GH.NEVER_WORDS


def t_the_connected_state_is_read_not_guessed():
    keep = Q._github_module
    try:
        for connected, needle in ((False, "not connected yet"),
                                  (True, "is connected")):
            Q._github_module = lambda c=connected: _FakeGitHub(c)
            intent = Q.match("what can't you do on GitHub?")
            reply = Q.run(intent, None, 0.0).reply
            check(f"connected={connected}: the answer says so", needle in reply,
                  reply[-300:])
        # The unreadable module is said, never guessed.
        Q._github_module = lambda: None
        intent = Q.match("what can't you do on GitHub?")
        reply = Q.run(intent, None, 0.0).reply
        check("an absent module is said, never guessed",
              "no GitHub module" in reply or "force-push" in reply, reply[:300])
    finally:
        Q._github_module = keep


# --------------------------------------------------------------------------
#   7. the merge/push surface that exists is carded, and the bans still hold
# --------------------------------------------------------------------------
def t_no_merge_push_commit_close_surface_exists():
    # 2026-11-10 (the owner's "Everything at once"): merge and PR-branch push
    # exist now, each behind its OWN card. The old pins here said no merge tool,
    # planner or tier line existed at all; those sentences are now false, and a
    # suite that kept them would be pinning a lie. What is pinned instead is the
    # boundary that DID survive: the absolute bans, and the card in front of
    # every merge and push.
    check("jarvis_github.NEVER names the absolute bans that remain",
          {"force_push", "squash_merge", "rebase_merge", "admin_bypass",
           "auto_merge", "bypass_required_checks", "push_to_main",
           "delete_repository", "close_repository", "delete_branch",
           "close_branch"} <= set(GH.NEVER), sorted(GH.NEVER))
    check("jarvis_github has no planner for any banned verb",
          not [n for n in dir(GH) if n.startswith("plan_")
               and re.search(r"squash|rebase|admin|force|delete|close|commit", n)],
          [n for n in dir(GH) if n.startswith("plan_")])
    check("jarvis_agent.TOOLS has no squash/rebase/admin/force/delete/close tool",
          not [n for n in AG.TOOLS
               if re.search(r"squash|rebase|admin|force|delete|close|commit", n)],
          sorted(AG.TOOLS))
    check("the ten GitHub tools are the only github_* tools registered for the "
          "owner's own GitHub (github_search is the separate research tool)",
          sorted(n for n in AG.TOOLS if n.startswith("github_")) ==
          sorted(list(TEN_TOOLS) + ["github_search"]),
          sorted(n for n in AG.TOOLS if n.startswith("github_")))
    check("every merge/push tool is carded and can never be auto-approved",
          all(t in AG.NEEDS_A_PERSON and t in AG.GITHUB_ACTION_TOOLS
              for t in ("github_merge_pr", "github_fix_and_push")),
          sorted(AG.NEEDS_A_PERSON))
    # The "What asks first" page may list the new carded actions; what it must
    # never list is a banned one. `app_merge_change` is the desktop app's own
    # update approval, not a GitHub action, so only github_* rows are read.
    rows = [r for g in ASK.view(here=False)["groups"] for r in g["rows"]]
    check("no asks-first GitHub row names a banned action",
          not [r for r in rows
               if str(r.get("id") or "").startswith("github_")
               and re.search(r"squash|rebase|admin|force|delete|close|commit",
                             str(r.get("id") or ""))],
          [r.get("id") for r in rows if "github_" in str(r.get("id"))])
    intent, name, reply = _reply("can you merge a pull request?")
    check("the merge answer is the fixed module answer, not the model",
          name == "github_self" and "merge" in reply.lower(), (name, reply[:120]))
    check("... and it names the ONE card every merge needs",
          "one approval card" in reply.lower(), reply[:300])
    check("... and says merge commit only",
          "merge commit" in reply.lower(), reply[:300])
    check("... and never says there is no merge card any more",
          "no merge card" not in reply.lower()
          and "approving a card cannot create one" not in reply.lower(), reply)
    check("... and it names what a merge is refused for",
          "refused" in reply.lower() and "required check" in reply.lower(),
          reply[:400])
    # The shipped tiers carry every carded action at "ask", and no banned one.
    toml = (REPO / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(
        encoding="utf-8")
    block = toml.split("[autonomy.tiers]", 1)[1]
    for action in ("github_inspect", "github_comment", "github_open_issue",
                   "github_rerun_workflow", "github_create_repo",
                   "github_merge_pr", "github_fix_and_push"):
        check(f'shipped tier says {action} = "ask"',
              re.search(rf'(?m)^{action}\s*=\s*"ask"', block) is not None)
    check("the shipped tiers name no banned action",
          re.search(r'(?m)^\s*github_\w*(?:squash|rebase|admin|force|delete|'
                    r'close)\w*\s*=', block) is None)


# --------------------------------------------------------------------------
#   8. the four smaller fixes this branch carries
# --------------------------------------------------------------------------
def t_the_ten_tool_hints_name_the_real_control():
    check("one shared hint constant exists", bool(TP.GITHUB_TOOL_ENABLE_HINT))
    for tool in TEN_TOOLS:
        hint = str(TP.PROFILES[tool]["enable_hint"])
        check(f"{tool}: the hint names 'Let the AI use this'",
              "Let the AI use this" in hint, hint)
        check(f"{tool}: the hint names no nonexistent 'Settings -> Tools' control",
              "Settings -> Tools" not in hint, hint)
        check(f"{tool}: the hint uses the shared constant",
              hint == TP.GITHUB_TOOL_ENABLE_HINT, hint)


def t_the_connect_card_summary_is_current():
    summary = CA.SERVICES["github"].summary
    low = summary.lower()
    check("the connect card names the reads the token is for",
          "read your repositories" in low and "pull requests" in low, summary)
    check("... and the three carded actions", "comment" in low
          and "open an issue" in low and "re-run a workflow" in low, summary)
    check("... and says each one is its own card", "own card" in low, summary)


def t_your_latest_release_is_the_same_question():
    for question in ("what's the latest release", "what's your latest release",
                     "what is your latest release",
                     "what is jarvis's latest release"):
        intent = Q.match(question)
        check(f"{question!r} -> update_ask",
              intent is not None and intent.name == "update_ask",
              intent.name if intent else None)


def t_the_guide_no_longer_says_no_switch_beside_switch_it_on():
    for feature_id in ("github-research", "connected-github", "computer-control"):
        words = FG.explain(feature_id)["words"]
        low = words.lower()
        check(f"{feature_id}: the answer says where its switch is",
              'under "let the ai use this"' in low
              or "under \"let the ai use this\"" in low, words[:300])
        check(f"{feature_id}: it no longer says 'names no on/off switch'",
              "names no on/off switch" not in low, words)
        check(f"{feature_id}: it no longer says 'has no switch of its own'",
              "has no switch of its own" not in low, words)
        check(f"{feature_id}: the Status line stays the contract's own label "
              f"(display rewords are phone-only + app-lock)",
              FG.status_label(FG.row_by_id(feature_id)) ==
              FG.label_for(FG.row_by_id(feature_id)), words[:200])
    state = FG.state("github research")
    check("'is github research on?' reads a real state",
          state.get("state") is False, state.get("words"))
    check("... and says it plainly", "off right now" in state["words"].lower(),
          state.get("words"))


def t_the_web_research_row_is_no_longer_a_diagnostic():
    import tomllib
    data = tomllib.loads((REPO / "backend" / "rebuilt" /
                          "jarvis-framework.toml").read_text(encoding="utf-8"))
    check("web_research ships as \"ask\" (what the tool loop really does)",
          data["autonomy"]["tiers"].get("web_research") == "ask",
          data["autonomy"]["tiers"].get("web_research"))
    row = ASK._row("web_research", here=True)
    check("the 'Search GitHub' row says it asks, not the developer diagnostic",
          row.get("says") == ASK.SAYS["ask"] and row.get("says") != ASK.SAYS_REFUSED,
          row.get("says"))


# --------------------------------------------------------------------------

def main() -> int:
    try:
        t_the_catalogue_has_the_connected_github_row()
        t_the_capability_answer_names_the_connected_surface()
        t_the_accounts_row_is_the_real_surface()
        t_the_accounts_answers_are_reachable()
        t_the_eight_recorded_questions_route_deterministically()
        t_the_connected_state_is_read_not_guessed()
        t_no_merge_push_commit_close_surface_exists()
        t_the_ten_tool_hints_name_the_real_control()
        t_the_connect_card_summary_is_current()
        t_your_latest_release_is_the_same_question()
        t_the_guide_no_longer_says_no_switch_beside_switch_it_on()
        t_the_web_research_row_is_no_longer_a_diagnostic()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
