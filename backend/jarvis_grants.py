"""jarvis_grants.py - the engine behind one plan card per job, and trusted mode.

STATUS: THE ENGINE ONLY. Nothing imports this module yet and no call site reads
it. The card, the chat sentences, the gate's one call and both apps' bar are a
later pull request; this one exists so the rules below can be proved on their
own, before anything can lean on them. The design it implements is
`docs/PLAN-CARD-AND-TRUSTED-MODE.md` (PR #1303), the owner's decisions of
2026-11-15 and 2026-11-16.

THE TWO MODES, IN ONE BREATH EACH
  1. One plan card per job. The owner answers ONE card that names every write a
     job will make - each action, repository, pull request or branch, file and,
     for a merge, the exact head commit - and `PlanGrant` is that answer as
     data. A write the card did not name, or one whose target has moved, does
     not run: it raises a new card. A divergence voids the rest of the plan.
  2. Trusted mode. One card opens a window of at most sixty minutes during
     which GitHub writes from a closed eleven-action allowlist run without a
     card each. It is capped per action, dies on restart, expires on its own,
     is voided the moment the event stream goes stale, and never covers email,
     files, credentials or spending.

THE NINE INVARIANTS, EACH ENFORCED IN CODE
  1. GitHub only, from `TRUSTED_ALLOWLIST` - exactly eleven action names. Any
     other action is a card, even inside an open window; email, files,
     credentials and spending included.
  2. The nine standing banned verbs are refused before any grant is looked at,
     and refused *as modifiers too*: `github_merge_pr` with `method="squash"`,
     `github_pr_review` with `event="APPROVE"`, a push with `force=True`. A
     grant can never make a banned request legal.
  3. A hard cap of `MAX_TRUSTED_ACTIONS` (20) USES PER ACTION PER SESSION, with
     a hard ceiling of 30: a caller asking for 99 gets 30, never 99. The
     twenty-first use of one action is refused. The number one window gets is
     resolved at open: the caller's own number, else the owner's
     `[grants].max_actions` setting, else 20 (see below).
  4. A trusted window lives at most sixty minutes from the moment it opened;
     at exactly sixty minutes it is closed.
  5. In memory only. Nothing here writes a file; a grant carries the id of the
     process that minted it, so a copy from an earlier process cannot run.
  6. A card that was already waiting is never swallowed. Given the ids of the
     cards already waiting, this engine answers "card" and leaves them to the
     owner; it never drains a queue.
  7. A stale event stream voids the window immediately. `void_stale()` is the
     call a caller makes when it notices; `consult(stream_fresh=False)` also
     voids, so a caller that forgets cannot coast.
  8. Targets are pinned. A trusted merge pinned to one head SHA refuses a
     different one; a plan grant matches the exact target it named.
  9. A grant can only ever narrow what would happen anyway. It can never lift a
     "never" and never runs an action whose request it cannot describe.

THE API, IN THE ORDER THE GATE USES IT
    GrantStore.open_trusted(chat_id, allowed_writes, targets, now, *,
                            seconds=3600, owner_approved=True,
                            max_actions=None) -> TrustedSession | None
    GrantStore.open_plan(job_id, allowed_writes, targets, now, *,
                         seconds) -> PlanGrant | None
        Open a window. Only the after-the-card path may call these, and a
        window whose `grant_made` audit line cannot be written is refused
        rather than allowed unlogged - the existing web-search grant's rule.
        `max_actions=None` means "resolve it": the caller's number, else the
        owner's setting, else 20.

    resolve_max_actions(requested=None) -> int
    setting_cap() -> int | None
        The cap one window will use, in that order, clamped at every level;
        and the one read of the owner's `[grants].max_actions` setting.

    consult(grant, tool, args, now, *, stream_fresh, tier="ask",
            pending_cards=(), lockdown=False) -> Decision
        Consult one action against one window, without spending anything.
        Pure: the same call twice gives the same answer.

    record_action(grant, action, *, carded=True) -> int
        Record that the consulted action really ran: spend one use, and write
        the gate's `granted` line only when `carded` is true (i.e. the tier
        would have raised a card; an "auto" action is not covered by a grant,
        it would have run anyway, and logging it as covered would overstate).

    close_window(grant, reason, *, state="closed") -> bool
        Close it now, with a reason a person can read. Idempotent: the second
        close changes nothing and writes no second line.

    status(grant, now) -> dict
        Read its status: live or not, why it closed, when it expires, how many
        uses each action has left.

    GrantStore.check(key, tool, args, now, *, stream_fresh, tier="ask",
                     pending_cards=(), lockdown=False) -> Decision
        THE ONE READING SITE the gate will call: look the window up by its key,
        consult, and on a run `record_action`. Kept here so the split above
        cannot be wired as "consult without record".

    void(grant, event) -> PlanGrant        # a divergence, plan grants only
    void_stale(session, now) -> TrustedSession
    GrantStore.revoke(chat_id) / end_chat(chat_id) / end_job(job_id) / restart()
        The four end conditions the existing web-search grant already has.

WHERE THE CAP'S DEFAULT LIVES, AND WHY IT IS NOT A CONSTANT
    `MAX_TRUSTED_ACTIONS` (20) is the default and the fallback. The number one
    window actually gets is `resolve_max_actions(caller's)`, in this order:
      1. the caller's own number for this session (a plan card or a chat
         sentence that says "20 this time"), clamped;
      2. otherwise the owner's `[grants].max_actions` setting, read through
         `jarvis_limits.LIMITS["trusted_actions"]` (1..30, default 20), so a
         change made once reaches every later window;
      3. otherwise 20.
    The number is resolved when a window OPENS and stored on the window, so
    changing the setting changes the next window and never one already open.
    This module only READS the setting: changing it is the existing
    `POST /api/limits/settings` gate action (a raise asks one card, exactly
    like every other limit), and no code here writes a setting. The chat and
    Jarvis Live sentences that name this setting - and the `NUMBER_SETTINGS`
    row that lets the spoken settings runner find it - arrive with the wiring
    PR; this PR registers the limit and reads it.

THE RECORD, IN THE DESIGN DOCUMENT'S OWN FIELD NAMES
    kind            "plan" | "trusted"
    job_id          the job (a plan) or the chat (a trusted window)
    allowed_writes  the exact action names the card named; closed
    targets         Target objects: repository, number, branch, file, head_sha
    void_if         for a plan, the divergences that have voided it
    issued_at       when the card was answered
    expires_at      when it dies by itself
    actions_taken   the total number of recorded uses
    max_actions     the per-action cap (trusted only; a plan's bound is its list)
    grant_id        the name the gate's three grant events already take

THREE OUTCOMES, AND WHY "card" IS NOT A SOFTER "refuse"
    run     this exact write is already approved; it may happen now.
    card    the write may be legitimate but this window does not authorise it -
            the owner must see it. A pending card, an unnamed file, a write
            outside GitHub and a moved plan target are all "card", because the
            card is still the owner's to answer and calling that "refused"
            would misstate what happened.
    refuse  it must not happen at all: a banned verb, a stale stream, a forged
            window, an exhausted cap, an unpinned trusted merge, a request
            nobody can describe.

WHY TWO CLASSES RATHER THAN ONE `kind` FIELD
    The fields that make each mode safe do not mean the same thing. A plan is
    narrow, job-bound, pinned to exact targets and voided by divergence. A
    trusted session is deliberately broad inside the repositories it names,
    capped per action, time-boxed to an hour, voided by a stale stream, and
    *not* voided by divergence at all: a merge inside the window still carries
    its own head_sha and passing-check requirement, and the window is not that
    pin. One class would make every branch of `consult()` begin "if kind ==
    ...", and a missed branch would silently apply the wrong rule. Two classes
    make the difference structural: each constructor enforces its own
    invariants, and `consult()` dispatches on type, so a third mode is a
    deliberate new class and a new branch rather than another string that can
    fall through. The `kind` attribute is kept on both anyway, validated
    against the class, because it is what an audit or storage layer switches
    on.

THE THREE LIMITS THIS ENGINE CANNOT SOLVE, STATED RATHER THAN HIDDEN
  1. A plan's occurrence identity. A plan is a set of (action, target) pairs.
     It says "a comment on #1295 is approved", not "exactly one comment"; a
     second comment on #1295 still matches. "Every write the job will make"
     needs a list of write intents consumed once each, or an explicit count.
     This module deliberately keeps the set semantics and does not pretend
     otherwise: the plan names what MAY be written, and only a plan-vs-write
     count in a later slice can say "once".
  2. A plan digest is audit evidence, not enforcement. A hash of the approved
     plan proves the executor ran that document, but the gate only sees the
     tool, the arguments and the window, so a hash cannot be checked without
     the plan itself. The executable pins therefore live in the grant (a
     Target's head_sha, number, branch and file), and a digest, if one is ever
     added, belongs beside the audit record.
  3. Authority and a pending card's identity. `owner_approved` is an assertion
     any code in the process can make; a Python object cannot prove who built
     it. The shape is only safe if one module mints windows, the gate receives
     a window by its store key (never as a model-supplied tool argument), and
     `open_trusted` is reached only after a card was answered. Likewise a
     pending card passed as a boolean cannot say which card or when it was
     raised, so this engine takes card IDS and names the one it saw. It is
     deliberately stricter than the letter of the rule: ANY pending card blocks
     the write, because a queue is exactly what a window may never drain.

THE AUDIT: ONE SOURCE OF TRUTH
    The gate owns the three grant events (`grant_made`, `granted`,
    `grant_ended`). This module has no copy of their names, strings or
    redaction; it calls the gate's own writers through one lazy import, exactly
    as `jarvis_agent._grant_audit` does. At import time this module needs
    nothing but the standard library, and it never opens a window when the
    writer it must log to is not there - "every action under a grant is logged"
    is part of what the owner approved.

WHAT THIS ENGINE DOES NOT MODEL
    Persistence, the real card queue, the real gate, the tool modules, the
    model's prompts, or how `stream_fresh` is measured. The clock is a
    parameter, so every rule is testable without sleeping. Nothing here reads
    GitHub: a trusted merge requires the request to carry its head SHA and to
    say the required checks passed, and the merge tool must re-check both
    before it runs. It also does not change its own cap setting: the existing
    limits route owns that gate action, and the engine only reads the resolved
    number when a window opens.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, Collection, Mapping

__all__ = [
    "BANNED_ACTIONS",
    "Decision",
    "Divergence",
    "GITHUB_READ_ACTIONS",
    "GITHUB_WRITE_ACTIONS",
    "GRANT_STORE_MAX",
    "Grant",
    "GrantClosed",
    "GrantStore",
    "MAX_TRUSTED_ACTIONS",
    "MAX_TRUSTED_ACTIONS_CEILING",
    "OUTCOMES",
    "PlanGrant",
    "SETTING_KEY",
    "TIERS",
    "TRUSTED_ALLOWLIST",
    "TRUSTED_MAX_LIFETIME",
    "Target",
    "TrustedGrant",
    "TrustedSession",
    "VOID_EVENTS",
    "ActionCapReached",
    "close_window",
    "consult",
    "current_process_id",
    "record_action",
    "resolve_max_actions",
    "setting_cap",
    "simulate_restart",
    "status",
    "void",
    "void_stale",
]

#: The three answers a consultation can give. See the docstring above.
OUTCOMES = frozenset({"run", "card", "refuse"})

#: The gate's own tiers. "auto" never needed a card; "ask" raises one; "never"
#: is a standing ban and a grant may not lift it.
TIERS = frozenset({"auto", "ask", "never"})

#: A trusted window's hard life. The design gives it an hour for the same
#: reason a GitHub App's installation token is minted for exactly one.
TRUSTED_MAX_LIFETIME = timedelta(minutes=60)

#: The existing store's own ceiling (`jarvis_agent._GRANTS_MAX`), kept so the
#: widening has the same bounded shape rather than growing without limit.
GRANT_STORE_MAX = 200

#: THE OWNER'S CAP, AND WHAT IT COUNTS. 20 USES PER ACTION PER SESSION, hard
#: ceiling 30, and a caller asking for more is clamped - never honoured. It is
#: a count of *uses*, not of action names: with an eleven-name allowlist a cap
#: of 20 names could never be reached, so the per-use reading is the only one
#: in which the number means anything. This constant is the DEFAULT and the
#: engine's fallback; the owner changes the default through the setting below,
#: and `resolve_max_actions()` decides what one window actually gets.
#: `TrustedSession.max_actions` is that per-action number; `actions_taken` is
#: the total across all actions.
MAX_TRUSTED_ACTIONS = 20
MAX_TRUSTED_ACTIONS_CEILING = 30

#: The setting the owner changes to move the default cap: `[grants].max_actions`
#: in the settings file, declared ONCE as `jarvis_limits.LIMITS["trusted_actions"]`
#: (1..30, default 20), with its words and its card in that table. The engine
#: only READS it, at the moment a window opens; changing it is the existing
#: limits route's gate action, never a write from here. The chat and Jarvis Live
#: sentences that name it arrive with the wiring PR.
SETTING_KEY = "trusted_actions"

#: The exact GitHub write surface trusted mode may cover, in the owner's own
#: shapes: comment, open_issue, rerun_workflow, create_repo, merge_pr,
#: fix_and_push, open_pr, issue_labels, edit_pr, pr_review (never an APPROVE),
#: issue_state. `github_workflow` and the fix flow's local `github_fix_write`
#: are deliberately outside it - see GITHUB_WRITE_ACTIONS below.
TRUSTED_ALLOWLIST = frozenset(
    {
        "github_comment",
        "github_open_issue",
        "github_rerun_workflow",
        "github_create_repo",
        "github_merge_pr",
        "github_fix_and_push",
        "github_open_pr",
        "github_issue_labels",
        "github_edit_pr",
        "github_pr_review",
        "github_issue_state",
    }
)

#: Every GitHub write a PLAN may name: the eleven above plus the two that are
#: real actions but outside the trusted window - `github_workflow` (cancel or
#: re-run failed jobs) and `github_fix_write` (the fix flow's local write, which
#: the design keeps carded while prepare and push are covered).
GITHUB_WRITE_ACTIONS = TRUSTED_ALLOWLIST | {"github_workflow", "github_fix_write"}

#: The six card-free reads share the gate's one read action; a read changes
#: nothing, so it needs no grant and is allowed on a stale stream's behalf only
#: by the gate, never here (a stale stream refuses everything, reads included).
GITHUB_READ_ACTIONS = frozenset({"github_inspect"})

_READ_TOOL_NAMES = frozenset(
    {
        "github_list",
        "github_read_file",
        "github_ci_status",
        "github_pr_scan",
        "github_pr_detail",
        "github_search",
    }
)

#: The four non-GitHub domains the owner named. Trusted mode NEVER covers them;
#: they are legitimate requests that need their own card. Named here so the
#: "GitHub only" answer is a sentence about them, not silence.
OTHER_TOOLS = frozenset(
    {"send_email", "write_file", "set_credential", "spend_money"}
)

#: The owner's standing bans, canonicalised to one word each so the sentence
#: reads the same whether the model asked for "squash", "squash_merge" or
#: "github_squash_merge". `approve`, `gist` and `protected_branch` are kept from
#: the repository's existing bans even though the shorter 2026-11-16 list does
#: not repeat them: they are still in force and a window must not reach them.
BANNED_ACTIONS: dict[str, str] = {
    "auto_merge": "auto_merge",
    "github_auto_merge": "auto_merge",
    "squash": "squash",
    "squash_merge": "squash",
    "github_squash_merge": "squash",
    "rebase": "rebase",
    "rebase_merge": "rebase",
    "github_rebase_merge": "rebase",
    "force_push": "force_push",
    "force-push": "force_push",
    "github_force_push": "force_push",
    "admin_bypass": "admin_bypass",
    "github_admin_bypass": "admin_bypass",
    "workflow_dispatch": "workflow_dispatch",
    "dispatch": "workflow_dispatch",
    "github_workflow_dispatch": "workflow_dispatch",
    "approve": "approve",
    "approve_pr": "approve",
    "github_approve_pr": "approve",
    "delete_branch": "delete_branch",
    "github_delete_branch": "delete_branch",
    "delete_release": "delete_release",
    "github_delete_release": "delete_release",
    "gist": "gist",
    "github_gist": "gist",
}

#: Pushing a branch is the one GitHub write that can land on a protected branch
#: by name. The live module refuses main/master/release/*/hotfix/* already; a
#: window that covered every push would make that refusal the only thing
#: standing, so the ban is enforced here too.
_PROTECTED_BRANCH_PREFIXES = ("release/", "hotfix/")
_PROTECTED_BRANCH_NAMES = frozenset({"main", "master"})
_PUSH_ACTIONS = frozenset({"github_fix_and_push", "github_open_pr"})

#: What may void a plan. A trusted window is not voided by divergence - it is
#: voided by the hour, the restart, the owner saying stop, or a stale stream.
VOID_EVENTS = ("head_moved", "check_red", "file_not_named", "second_pr")

_VOID_TEXT = {
    "head_moved": "the pull request's head moved after the plan was approved",
    "check_red": "a required check turned red",
    "file_not_named": "the job tried to write a file the plan did not name",
    "second_pr": "a second pull request became involved",
}

_BAN_TEXT = {
    "auto_merge": "Auto-merge is a standing ban; a merge is decided once, on a card.",
    "squash": "Squash-merging is a standing ban; every merge Jarvis makes is one merge commit.",
    "rebase": "Rebase-merging is a standing ban.",
    "force_push": "Force-pushing is a standing ban.",
    "admin_bypass": "An admin bypass is a standing ban; checks are not something a grant can step over.",
    "workflow_dispatch": "Dispatching a workflow is a standing ban; it is arbitrary remote execution.",
    "approve": "Approving a pull request is a standing ban; that is the owner's own sign-off.",
    "delete_branch": "Deleting a branch is a standing ban.",
    "delete_release": "Deleting a release is a standing ban.",
    "gist": "Gists are a standing ban; they are public by default and an exfiltration sink.",
    "merge_method": "Jarvis merges with one merge commit; this merge method is not one it offers.",
    "protected_branch": (
        "Pushing directly to main, master, release/* or hotfix/* is a standing ban."
    ),
}

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: What a PLAN must have pinned on the target it names before the write may
#: run. Exact matching is the safety property: a plan target that leaves out
#: the number, file, branch or head it changes is not exact, and a plan that
#: leaves out what it changes is a blank cheque.
_PLAN_REQUIRED: dict[str, tuple[str, ...]] = {
    "github_merge_pr": ("number", "head"),
    "github_fix_and_push": ("branch",),
    "github_fix_write": ("number", "file"),
    "github_comment": ("number",),
    "github_open_issue": (),
    "github_rerun_workflow": ("number",),
    "github_create_repo": (),
    "github_open_pr": ("branch",),
    "github_workflow": ("number",),
    "github_issue_labels": ("number",),
    "github_edit_pr": ("number",),
    "github_pr_review": ("number",),
    "github_issue_state": ("number",),
}

#: What the *request* must carry before the gate can describe it at all.
_REQUIRED_REQUEST: dict[str, tuple[str, ...]] = {
    "github_merge_pr": ("number",),
    # The prepare stage of the fix flow names the pull request; the push stage
    # names the branch. `_target_for` accepts either and refuses neither.
    "github_fix_and_push": (),
    "github_fix_write": ("number", "file"),
    "github_comment": ("number",),
    "github_open_issue": (),
    "github_rerun_workflow": ("number",),
    "github_create_repo": (),
    "github_open_pr": ("branch",),
    "github_workflow": ("number",),
    "github_issue_labels": ("number",),
    "github_edit_pr": ("number",),
    "github_pr_review": ("number",),
    "github_issue_state": ("number",),
}

_FIELD_QUESTION = {
    "repo": "which repository (owner/name) it would change",
    "number": "which pull request, issue or run it is for",
    "branch": "which branch it would push to",
    "file": "which file it would write",
}

_TOOL_ACTIONS: dict[str, str] = {name: "github_inspect" for name in _READ_TOOL_NAMES}
_TOOL_ACTIONS.update({name: name for name in GITHUB_WRITE_ACTIONS})
_TOOL_ACTIONS.update({name: name for name in OTHER_TOOLS})


class UnknownTool(ValueError):
    """The tool is not in the gate's catalogue, so nothing can be judged."""


class RequestError(ValueError):
    """The request is too incomplete to describe; nothing can be judged."""


class GrantClosed(ValueError):
    """The window is closed; it cannot be revived by recording a use."""


class ActionCapReached(ValueError):
    """This action has spent its per-session cap; a further use is refused."""


# ---------------------------------------------------------------------------
# The gate's three grant events - called, never copied
# ---------------------------------------------------------------------------


def _grant_audit(name: str, **fields: Any) -> bool:
    """Call one of `jarvis_gate`'s three grant-event writers; False if absent.

    THE ENGINE'S ONE DOOR INTO THE GATE'S AUDIT LOG, and the reason it is a
    lazy import rather than a local `audit_log()` call: the gate owns that log,
    its redaction and its event names (`jarvis_gate.grant_made` / `granted` /
    `grant_ended`). A backend whose gate predates them is a half-updated
    install, and then a window is REFUSED rather than allowed unlogged -
    "every action under a grant is logged" is part of what the owner approved.
    A failed write AFTER a window exists is swallowed, exactly as every other
    audit line in this project is (the owner's work must not fail because the
    disk is full).

    This is the same shape as `jarvis_agent._grant_audit`, on purpose: one
    source of truth for the three events, not two.
    """
    try:
        import jarvis_gate

        writer = getattr(jarvis_gate, name, None)
        if writer is None:
            return False
        writer(**fields)
        return True
    except Exception:  # noqa: BLE001 - a missing or broken gate means "no log"
        return False


# ---------------------------------------------------------------------------
# The cap, resolved: caller, then the owner's setting, then 20
# ---------------------------------------------------------------------------


def setting_cap() -> int | None:
    """What the owner's `[grants].max_actions` setting says now, or None.

    THE ONE READ of the setting. `jarvis_limits` owns the value, its 1..30
    range and the words both Settings screens show; this function asks that
    table, keeps no second copy and never writes. `None` means the table or
    the row is not on this PC - an older backend - and `resolve_max_actions()`
    then falls back to MAX_TRUSTED_ACTIONS, exactly as on a PC that never
    touched the setting.
    """
    try:
        import jarvis_limits

        row = jarvis_limits.find(SETTING_KEY)
        if row is None:
            return None
        return int(jarvis_limits.value_of(row))
    except Exception:  # noqa: BLE001 - an unreadable setting is "not set"
        return None


def resolve_max_actions(requested: int | None = None) -> int:
    """The cap one window gets: the caller's number, else the setting, else 20.

    The order, and every level is clamped to 1..MAX_TRUSTED_ACTIONS_CEILING:

      1. a number named FOR THIS SESSION (a plan card or a chat sentence that
         says "20 this time") wins;
      2. otherwise the owner's `[grants].max_actions` setting decides, so a
         change made once reaches every later window;
      3. otherwise MAX_TRUSTED_ACTIONS (20).

    Resolved when a window OPENS and stored on it, so changing the setting
    changes the next window and never one already open.
    """
    if requested is not None:
        if isinstance(requested, bool) or not isinstance(requested, int):
            raise ValueError("a cap must be a whole number")
        return max(1, min(requested, MAX_TRUSTED_ACTIONS_CEILING))
    value = setting_cap()
    if value is None:
        return MAX_TRUSTED_ACTIONS
    try:
        wanted = int(value)
    except (TypeError, ValueError):
        return MAX_TRUSTED_ACTIONS
    return max(1, min(wanted, MAX_TRUSTED_ACTIONS_CEILING))


# ---------------------------------------------------------------------------
# Time and process lifetime
# ---------------------------------------------------------------------------

_PROCESS_ID = uuid.uuid4().hex


def current_process_id() -> str:
    """The id of this process's lifetime. Every window is pinned to it."""
    return _PROCESS_ID


def _utc(value: datetime, name: str) -> datetime:
    """Require a timezone-aware datetime and normalise it to UTC."""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime, not {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be timezone-aware, not a naive datetime")
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


# ---------------------------------------------------------------------------
# Target: the exact thing a write would touch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """The one thing a write names, exactly.

    `number` is the pull request (or issue or run) number the design calls the
    pull request number. `head` is the full 40-hex commit a merge is pinned to:
    "the head moved" cannot be detected without a pin. A target may leave
    fields out; a *plan* then matches only requests that leave them out too
    (exactness), while a *trusted* window treats an omitted field as "any
    inside the repository it names".
    """

    repo: str
    number: int | None = None
    branch: str | None = None
    file: str | None = None
    head: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repo, str) or not _REPO_RE.fullmatch(self.repo.strip()):
            raise ValueError(
                f"a repository target must be owner/name, not {self.repo!r}"
            )
        object.__setattr__(self, "repo", self.repo.strip())
        if self.number is not None:
            if isinstance(self.number, bool) or not isinstance(self.number, int):
                raise ValueError("a target number must be a whole number")
            if self.number <= 0:
                raise ValueError("a target number must be positive")
        for name in ("branch", "file"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"a target {name} must be a non-empty string")
            if value is not None:
                object.__setattr__(self, name, value.strip())
        if self.head is not None:
            if not isinstance(self.head, str) or not _SHA_RE.fullmatch(self.head):
                raise ValueError(
                    "a target head must be the full 40-character lowercase SHA, "
                    f"not {self.head!r}, so the plan can pin it"
                )

    def key(self) -> tuple[Any, ...]:
        """The exact-match key. Repo is case-insensitive, as GitHub is."""
        return (
            self.repo.casefold(),
            self.number,
            self.branch,
            self.file,
            self.head,
        )

    def covers(self, request: "Target") -> bool:
        """True when this (trusted) target is a superset of the request's scope.

        Only the fields this target names are constrained; a repo-only target
        covers any pull request in that repo, while a target naming #1295
        covers #1295 only. A plan grant never uses this - it uses key().
        """
        if self.repo.casefold() != request.repo.casefold():
            return False
        for name in ("number", "branch", "file", "head"):
            mine = getattr(self, name)
            if mine is not None and mine != getattr(request, name):
                return False
        return True

    def describe(self) -> str:
        parts = [self.repo]
        if self.number is not None:
            parts.append(f"#{self.number}")
        if self.branch is not None:
            parts.append(f"branch {self.branch}")
        if self.file is not None:
            parts.append(f"file {self.file}")
        if self.head is not None:
            parts.append(f"head {self.head[:12]}...")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Divergence: what voids a plan grant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Divergence:
    """One event that makes the rest of an approved plan a new card."""

    event: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.event not in VOID_EVENTS:
            raise ValueError(
                f"unknown divergence event {self.event!r}; expected one of "
                f"{', '.join(VOID_EVENTS)}"
            )
        if not isinstance(self.detail, str):
            raise ValueError("a divergence detail must be a string")

    def describe(self) -> str:
        text = _VOID_TEXT[self.event]
        return f"{text} ({self.detail})" if self.detail else text


# ---------------------------------------------------------------------------
# Decision: what the engine tells the caller
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """One answer about one action. `reason` is for the owner.

    `why_it_matters` is the rule behind the answer, so a card (or a log line)
    can say why without re-deriving it. `grant_id` is the window that answered
    - None when a card or a ban answered - so every audit line can point back
    at the one card that allowed it.
    """

    outcome: str
    reason: str
    why_it_matters: str
    action: str = ""
    target: str = ""
    grant_kind: str | None = None
    grant_id: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}")
        for name in ("reason", "why_it_matters"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"a decision needs a non-empty {name}")
        if self.grant_kind is not None and self.grant_kind not in {"plan", "trusted"}:
            raise ValueError("grant_kind must be 'plan', 'trusted' or None")

    @property
    def is_run(self) -> bool:
        return self.outcome == "run"

    def __str__(self) -> str:
        return f"{self.outcome.upper()}: {self.reason}"


# ---------------------------------------------------------------------------
# Grants: one envelope, two kinds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Grant:
    """Shared envelope: who, what, where, how long, in which process.

    Not usable on its own; KIND is set by each subclass and validated here so
    the label can never disagree with the class. `process_id` is keyword-only
    and internal: it is stamped at construction and compared at decision time,
    which is how "a restart wipes every grant" is enforced even for an object
    that was written to disk and read back.

    `max_actions` is keyword-only too, so it can never be mistaken for the
    subclass's next positional field. It is None for a plan (its bound is the
    list it names) and the clamped per-action cap for a trusted session.
    """

    kind: str
    job_id: str | None
    allowed_writes: frozenset[str]
    targets: tuple[Target, ...]
    issued_at: datetime
    expires_at: datetime
    max_actions: int | None = field(default=None, kw_only=True)
    process_id: str | None = field(
        default=None, kw_only=True, repr=False, compare=False
    )
    grant_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        kw_only=True,
        repr=False,
        compare=False,
    )
    _uses: dict[str, int] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _closed_reason: str | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _closed_state: str = field(default="", init=False, repr=False, compare=False)

    KIND: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if not self.KIND:
            raise TypeError(
                "Grant is the shared envelope; construct TrustedSession or PlanGrant"
            )
        if self.kind != self.KIND:
            raise ValueError(
                f"a {type(self).__name__} must have kind {self.KIND!r}, not {self.kind!r}"
            )
        if self.job_id is not None and (
            not isinstance(self.job_id, str) or not self.job_id.strip()
        ):
            raise ValueError("job_id must be a non-empty string when given")
        if isinstance(self.allowed_writes, str):
            raise ValueError(
                "allowed_writes must be a collection of action names, not a string"
            )
        writes = frozenset(self.allowed_writes)
        if not writes:
            raise ValueError("a grant must name at least one action")
        for action in writes:
            if not isinstance(action, str) or not action.strip():
                raise ValueError("every action must be a non-empty string")
        object.__setattr__(self, "allowed_writes", writes)
        if isinstance(self.targets, (str, bytes)):
            raise ValueError("targets must be a collection of Target objects")
        targets = tuple(self.targets)
        if not targets:
            raise ValueError("a grant must name at least one target")
        for target in targets:
            if not isinstance(target, Target):
                raise ValueError("every target must be a Target")
        object.__setattr__(self, "targets", targets)
        issued = _utc(self.issued_at, "issued_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise ValueError("expires_at must be later than issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if self.process_id is None:
            object.__setattr__(self, "process_id", current_process_id())
        elif not isinstance(self.process_id, str) or not self.process_id.strip():
            raise ValueError("process_id must be a non-empty string when given")
        if not isinstance(self.grant_id, str) or not self.grant_id.strip():
            raise ValueError("grant_id must be a non-empty string")
        if self.max_actions is not None and (
            isinstance(self.max_actions, bool)
            or not isinstance(self.max_actions, int)
        ):
            raise ValueError("max_actions must be a whole number or None")

    @property
    def lifetime(self) -> timedelta:
        return self.expires_at - self.issued_at

    @property
    def is_closed(self) -> bool:
        """True once this window has been ended, for any of its reasons."""
        return self._closed_reason is not None

    @property
    def closed_reason(self) -> str | None:
        """Why it closed, in words a person can read; None while it is open."""
        return self._closed_reason

    @property
    def actions_taken(self) -> int:
        """Every use recorded against this window, across all actions."""
        return sum(self._uses.values())

    def used(self, action: str) -> int:
        return self._uses.get(action, 0)

    def describe(self) -> str:
        writes = ", ".join(sorted(self.allowed_writes))
        where = "; ".join(target.describe() for target in self.targets)
        line = (
            f"{self.kind} grant {self.grant_id} for {self.job_id or 'a chat'}: "
            f"writes {writes}; targets {where}; "
            f"open {_stamp(self.issued_at)} to {_stamp(self.expires_at)}"
        )
        if self.is_closed:
            line += f"; closed: {self._closed_reason}"
        return line

    def _record_use(self, action: str) -> int:
        self._uses[action] = self.used(action) + 1
        return self._uses[action]

    def _close(self, reason: str, state: str) -> bool:
        """Set the closed state once and write the gate's `grant_ended` line."""
        if self.is_closed:
            return False
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a close needs a reason the owner could read")
        if not isinstance(state, str) or not state.strip():
            raise ValueError("a close needs a state word for the audit line")
        object.__setattr__(self, "_closed_reason", reason.strip())
        object.__setattr__(self, "_closed_state", state.strip())
        _grant_audit("grant_ended", grant_id=self.grant_id, state=state.strip())
        return True


@dataclass(frozen=True)
class TrustedSession(Grant):
    """Chat-opened trust: allowlisted GitHub writes, <= 60 minutes, capped.

    `owner_approved` is deliberately not required to be True by the
    constructor. The engine is the place that must refuse a False one, because
    a forged window has to be a constructible object for that refusal to be
    testable - and because a constructor cannot prove who called it.
    """

    KIND: ClassVar[str] = "trusted"
    owner_approved: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.owner_approved, bool):
            raise ValueError("owner_approved must be True or False")
        if self.lifetime > TRUSTED_MAX_LIFETIME:
            raise ValueError(
                "a trusted session lasts at most 60 minutes; "
                f"this one asks for {self.lifetime}"
            )
        # The cap is RESOLVED once, here: a number named for this session, else
        # the owner's setting, else 20 - clamped at every level. Storing the
        # answer is what makes a later setting change reach only new windows.
        object.__setattr__(
            self, "max_actions", resolve_max_actions(self.max_actions)
        )
        if "*" in self.allowed_writes:
            if len(self.allowed_writes) != 1:
                raise ValueError(
                    "the '*' action cannot be combined with named actions"
                )
            # Expand once, at open, to the allowlist that exists now. A write
            # tool added later is therefore not covered by an old window - the
            # window does not grow silently.
            object.__setattr__(
                self, "allowed_writes", frozenset(TRUSTED_ALLOWLIST)
            )
        unknown = self.allowed_writes - TRUSTED_ALLOWLIST
        if unknown:
            raise ValueError(
                "trusted mode covers the eleven allowlisted GitHub writes only; "
                f"it cannot name {', '.join(sorted(unknown))}"
            )

    def remaining(self, action: str) -> int:
        return max(0, int(self.max_actions or 0) - self.used(action))

    def describe(self) -> str:
        return (
            f"{super().describe()}, cap {self.max_actions} use(s) per action"
        )


#: The design document's original name for the same object; the 2026-11-16
#: ruling calls it a session. Both names are exported so a caller can use
#: either without a second class.
TrustedGrant = TrustedSession


@dataclass(frozen=True)
class PlanGrant(Grant):
    """One approved plan: exact (action, target) pairs, until void or expiry.

    A plan may not contain "*": the owner approved named writes, never a queue.
    `void_if` is usually empty at construction; `void()` appends to it in
    place, because every holder of the plan must see a divergence at once and a
    returned copy would let a caller forget to rebind.
    """

    KIND: ClassVar[str] = "plan"
    void_if: tuple[Divergence, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.job_id:
            raise ValueError("a plan grant belongs to a job; job_id is required")
        if "*" in self.allowed_writes:
            raise ValueError(
                "a plan grant names actions; '*' is exactly the queue the design forbids"
            )
        events = () if self.void_if is None else tuple(self.void_if)
        for event in events:
            if not isinstance(event, Divergence):
                raise ValueError("void_if must contain Divergence events")
        object.__setattr__(self, "void_if", events)


def void(grant: PlanGrant, event: Divergence | str) -> PlanGrant:
    """Mark the rest of a plan as needing a new card. Returns the same grant.

    This is the one deliberate mutation in the plan shape. A void is a safety
    event: every holder must see it immediately, and a function that returned a
    *copy* would let a caller forget to rebind and keep running on a live
    grant. A trusted session is not voided by divergence - it covers whatever
    is current and the tools carry their own pins - so passing one is a
    TypeError, not a silent no-op.
    """
    if not isinstance(grant, PlanGrant):
        raise TypeError(
            "void() is for plan grants only; a trusted session is not voided by "
            "divergence (it expires, goes stale, or dies on restart)"
        )
    divergence = event if isinstance(event, Divergence) else Divergence(event)
    if divergence in grant.void_if:
        return grant
    object.__setattr__(grant, "void_if", grant.void_if + (divergence,))
    if not grant.is_closed:
        grant._close(divergence.describe(), "voided")
    return grant


def void_stale(session: TrustedSession, now: datetime | None = None) -> TrustedSession:
    """Kill a trust window the moment the event stream is seen to be stale.

    THE CALL THE CALLER MAKES when it notices staleness - the platform watcher
    should call it directly, without waiting for the next tool call, because
    "voids immediately" must be true when no action is being attempted. The
    same window can never be used again even after the stream recovers; the
    owner opens a new one. `consult(stream_fresh=False)` calls this too, so a
    caller that forgets cannot coast.
    """
    if not isinstance(session, TrustedSession):
        raise TypeError("void_stale() is for trusted sessions only")
    when = _utc(now, "now") if now is not None else datetime.now(timezone.utc)
    session._close(f"the event stream went stale at {_stamp(when)}", "stale")
    return session


# ---------------------------------------------------------------------------
# The store: the widening of jarvis_agent's _GRANTS
# ---------------------------------------------------------------------------
#
# jarvis_agent.py keeps the existing grant in `_GRANTS` (conversation_id -> a
# small dict), with `_GRANTS_LOCK`, `_GRANTS_MAX`, `web_search_grant()` reading
# it (and dropping an expired one with `grant_ended(state="expired")`),
# `_remember_web_search_grant()` writing it after the card, and
# `_forget_web_search_grant()` for the instant stop. This is the same store
# widened: the key is still the chat (or job), the value is a typed grant with
# a scope list and a cap, and the four end conditions are still the same.


class GrantStore:
    """In-memory only: there is no file, setting or secret to survive a restart."""

    def __init__(self, max_entries: int = GRANT_STORE_MAX) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise ValueError("max_entries must be a whole number")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._grants: dict[str, Grant] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    # -- opening, the after-the-card paths --------------------------------

    def open_trusted(
        self,
        chat_id: str,
        allowed_writes: Collection[str],
        targets: Collection[Target],
        now: datetime,
        *,
        seconds: float = 3600,
        owner_approved: bool = True,
        max_actions: int | None = None,
    ) -> TrustedSession | None:
        """Write a session for this chat after the owner's card; None if refused.

        Mirrors `_run_web_search_grant`: the thing that creates a window is the
        post-card path, not the model's ask, and a window that cannot be
        written into the grant log is refused rather than allowed unlogged. A
        second window for the same chat is refused too, exactly like the
        existing "already on, so there is nothing to ask" answer.

        `max_actions=None` means "resolve it": a number the caller names wins,
        else the owner's `[grants].max_actions` setting, else 20. The answer is
        stored on the window, so changing the setting afterwards moves only
        windows opened later.
        """
        if not isinstance(chat_id, str) or not chat_id.strip():
            return None
        if not owner_approved:
            return None
        key = f"chat:{chat_id}"
        # Drop a dead window first, so its expiry cannot masquerade as "already
        # on". Only a LIVE window refuses a second one, which is the design's
        # "it is already on, until 21:58" answer.
        self.get(key, now)
        with self._lock:
            if key in self._grants:
                return None
        opened = _utc(now, "now")
        try:
            session = TrustedSession(
                "trusted",
                chat_id,
                allowed_writes,
                targets,
                opened,
                opened + timedelta(seconds=seconds),
                True,
                max_actions=max_actions,
            )
        except (TypeError, ValueError):
            return None
        if not _grant_audit(
            "grant_made", grant_id=session.grant_id, seconds=float(seconds)
        ):
            return None
        with self._lock:
            self._grants[key] = session
            self._trim()
        return session

    def open_plan(
        self,
        job_id: str,
        allowed_writes: Collection[str],
        targets: Collection[Target],
        now: datetime,
        *,
        seconds: float,
    ) -> PlanGrant | None:
        """Write a plan grant for this job after its one card; None if refused.

        Unlike the trusted session there is no default life: a plan's expiry is
        part of what its card promises, so the caller has to name it. (The
        existing web-search grant's 8-hour cap is that feature's promise, not a
        sensible default for an arbitrary job.)
        """
        if not isinstance(job_id, str) or not job_id.strip():
            return None
        key = f"job:{job_id}"
        # Drop a dead plan first (the same "already on" rule as a session).
        self.get(key, now)
        with self._lock:
            if key in self._grants:
                return None
        opened = _utc(now, "now")
        try:
            plan = PlanGrant(
                "plan",
                job_id,
                allowed_writes,
                targets,
                opened,
                opened + timedelta(seconds=seconds),
            )
        except (TypeError, ValueError):
            return None
        if not _grant_audit(
            "grant_made", grant_id=plan.grant_id, seconds=float(seconds)
        ):
            return None
        with self._lock:
            self._grants[key] = plan
            self._trim()
        return plan

    # -- reading, the one place a grant is consulted ----------------------

    def get(self, key: str, now: datetime) -> Grant | None:
        """The live grant for this key, or None.

        An expired or closed one is dropped here, not by a timer. An expired
        one writes `grant_ended(state="expired")` exactly once - the same shape
        as `web_search_grant()` in jarvis_agent.py. A closed one has already
        written its own end line, so it is dropped silently. A grant from an
        earlier process cannot be returned even if someone put it back in the
        dict.
        """
        moment = _utc(now, "now")
        with self._lock:
            grant = self._grants.get(key)
        if grant is None:
            return None
        if grant.process_id != current_process_id():
            self._drop(key, "restarted")
            return None
        if grant.is_closed:
            self._drop(key, None)
            return None
        if moment >= grant.expires_at:
            self._drop(key, "expired")
            return None
        return grant

    def check(
        self,
        key: str,
        tool: str,
        args: Mapping[str, Any] | None,
        now: datetime,
        *,
        stream_fresh: bool,
        tier: str = "ask",
        pending_cards: Collection[str] = (),
        lockdown: bool = False,
    ) -> Decision:
        """Look the window up, consult, and record a run - the one call site.

        This is the place a grant is actually read, which is the invariant the
        existing module enforces with its single `_web_search_call` site. A run
        that used a grant spends one use of that action and writes
        `gate.granted`; a run that used no grant (a read, or an action at
        "auto") does neither, because the log would otherwise overstate what
        the grant covered.
        """
        grant = self.get(key, now)
        decision = consult(
            grant,
            tool,
            args,
            now,
            stream_fresh=stream_fresh,
            tier=tier,
            pending_cards=pending_cards,
            lockdown=lockdown,
        )
        if decision.is_run and decision.grant_kind is not None and grant is not None:
            record_action(grant, decision.action, carded=(tier == "ask"))
        return decision

    # -- the four end conditions ------------------------------------------

    def revoke(self, chat_id: str) -> bool:
        """The owner says stop: instant, idempotent, logged once."""
        return self._drop(
            f"chat:{chat_id}",
            "revoked",
            reason="the owner said 'trusted mode off'",
        ) is not None

    def end_chat(self, chat_id: str) -> bool:
        """This chat ended: its trusted window goes with it, logged once."""
        return self._drop(
            f"chat:{chat_id}", "chat_ended", reason="the chat ended"
        ) is not None

    def end_job(self, job_id: str) -> bool:
        """The plan's job finished (or was abandoned): its plan goes with it."""
        return self._drop(
            f"job:{job_id}", "job_ended", reason="the job ended"
        ) is not None

    def restart(self) -> None:
        """The process ended: every grant is gone and each end is logged.

        The live store cannot log its own death (the process writing the log is
        the one that died), so this is a widening: the audit can now say
        "restarted" for each grant. Nothing survives.
        """
        with self._lock:
            grants = list(self._grants.values())
            self._grants.clear()
        for grant in grants:
            grant._close("Jarvis restarted", "restarted")

    def clear(self) -> None:
        """Silent clear for tests; the production paths always log."""
        with self._lock:
            self._grants.clear()

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._grants)

    def __len__(self) -> int:
        with self._lock:
            return len(self._grants)

    # -- status ------------------------------------------------------------

    def status(self, key: str, now: datetime) -> dict:
        """What this store can say about one key; never a guess."""
        grant = self.get(key, now)
        if grant is None:
            return {
                "live": False,
                "reason": "no window is open for this key",
                "grant_id": None,
                "kind": None,
            }
        return status(grant, now)

    # -- internals ---------------------------------------------------------

    def _drop(self, key: str, state: str | None, reason: str = "") -> Grant | None:
        with self._lock:
            grant = self._grants.pop(key, None)
        if grant is not None and state is not None:
            grant._close(reason or state, state)
        return grant

    def _trim(self) -> None:
        while len(self._grants) > self._max_entries:
            self._grants.pop(next(iter(self._grants)))


def simulate_restart() -> str:
    """Test seam: pretend the process restarted, invalidating every existing grant.

    The real store is process-local and a new process starts empty; this is how
    the same thing is proved in one process. It writes no `grant_ended` line:
    a dying process cannot write its own log, and pretending otherwise would
    invent an event. The old objects still fail on the process id, which is the
    property under test.
    """
    global _PROCESS_ID
    _PROCESS_ID = uuid.uuid4().hex
    return _PROCESS_ID


# ---------------------------------------------------------------------------
# Reading a request
# ---------------------------------------------------------------------------


def _checks_passed(args: Mapping[str, Any]) -> bool:
    return (
        _truthy(args.get("checks_passed"))
        or _truthy(args.get("required_checks_passed"))
        or _truthy(args.get("checks_ok"))
    )


def _action_for(tool: str, args: Mapping[str, Any]) -> str:
    """Map a tool name (and its stage) to the gate action it really is.

    Exactly the live `gate_lookup_name` (`jarvis_agent.py:5913-5916`): only the
    write stage of `github_fix_and_push` is its own action; prepare, push and a
    missing stage stay under `github_fix_and_push`.
    """
    if not isinstance(tool, str) or not tool.strip():
        raise UnknownTool("the tool name is empty")
    tool = tool.strip()
    if tool == "github_fix_and_push":
        if _text(args.get("stage")).lower() == "write":
            return "github_fix_write"
        return "github_fix_and_push"
    if tool in BANNED_ACTIONS:
        return BANNED_ACTIONS[tool]
    if tool in _TOOL_ACTIONS:
        return _TOOL_ACTIONS[tool]
    raise UnknownTool(f"{tool!r} is not in the gate's tool catalogue")


def _banned_reason(action: str, args: Mapping[str, Any]) -> str | None:
    """Return the canonical ban, if this request asks for one. None otherwise.

    This inspects the *modifier* arguments as well as the action name, because
    the dangerous requests are mostly allowed tools asked to do a banned thing:
    `github_merge_pr` with `method="squash"`, `github_pr_review` with
    `event="APPROVE"`, a push with `force=True`. A window can name the allowed
    tool; it cannot make the banned modifier legal. This runs before any grant
    is consulted, so a grant can never beat a ban.
    """
    if action in BANNED_ACTIONS:
        return BANNED_ACTIONS[action]
    method = _text(args.get("method")) or _text(args.get("merge_method"))
    if method:
        lowered = method.lower()
        if lowered in {"squash", "rebase"}:
            return lowered
        if action == "github_merge_pr" and lowered != "merge":
            return "merge_method"
    if _truthy(args.get("squash")):
        return "squash"
    if _truthy(args.get("rebase")):
        return "rebase"
    if (
        _truthy(args.get("force"))
        or _truthy(args.get("force_push"))
        or _truthy(args.get("force-push"))
    ):
        return "force_push"
    if (
        _truthy(args.get("admin"))
        or _truthy(args.get("admin_bypass"))
        or _truthy(args.get("bypass"))
        or _truthy(args.get("bypass_required_checks"))
    ):
        return "admin_bypass"
    if _truthy(args.get("auto_merge")) or _truthy(args.get("auto_merge_enabled")):
        return "auto_merge"
    if _truthy(args.get("dispatch")) or _text(args.get("mode")).lower() == "dispatch":
        return "workflow_dispatch"
    if action == "github_pr_review" and _text(args.get("event")).upper() == "APPROVE":
        return "approve"
    if _truthy(args.get("approve")):
        return "approve"
    if _truthy(args.get("delete_branch")):
        return "delete_branch"
    if _truthy(args.get("delete_release")):
        return "delete_release"
    if _truthy(args.get("gist")):
        return "gist"
    branch = _text(args.get("branch")) or _text(args.get("head_branch"))
    if action in _PUSH_ACTIONS and branch and _is_protected_branch(branch):
        return "protected_branch"
    return None


def _is_protected_branch(branch: str) -> bool:
    lowered = branch.strip().lower()
    return lowered in _PROTECTED_BRANCH_NAMES or lowered.startswith(
        _PROTECTED_BRANCH_PREFIXES
    )


def _number_from(args: Mapping[str, Any]) -> int | None:
    for key in ("pr", "number", "issue", "run", "pull_request"):
        value = args.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise RequestError(f"{key}={value!r} is not a whole number") from None
        if number <= 0:
            raise RequestError(f"{key}={value!r} is not a positive number")
        return number
    return None


def _head_from(args: Mapping[str, Any]) -> str | None:
    for key in ("head_sha", "head", "sha", "commit"):
        value = args.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            raise RequestError(
                f"{key}={value!r} is not the full 40-character lowercase head SHA; "
                "the gate cannot pin an unpinned write"
            )
        return value
    return None


def _target_for(action: str, args: Mapping[str, Any]) -> Target | None:
    if action in OTHER_TOOLS or action in GITHUB_READ_ACTIONS:
        return None
    repo = _text(args.get("repo")) or _text(args.get("repository"))
    if not repo:
        raise RequestError(
            "the request does not say which repository (owner/name) it would change"
        )
    try:
        target = Target(
            repo=repo,
            number=_number_from(args),
            branch=(
                (_text(args.get("branch")) or _text(args.get("head_branch")) or None)
                if action in _PUSH_ACTIONS
                else None
            ),
            file=_text(args.get("file")) or _text(args.get("path")) or None,
            head=_head_from(args),
        )
    except ValueError as exc:
        raise RequestError(str(exc)) from None
    for name in _REQUIRED_REQUEST.get(action, ()):
        if getattr(target, name) is None:
            raise RequestError(
                f"the request does not say {_FIELD_QUESTION.get(name, name)}"
            )
    if action == "github_fix_and_push" and (
        target.branch is None and target.number is None
    ):
        # Prepare names the pull request; push names the branch. One of the
        # two is what makes the target describable at all.
        raise RequestError(
            "the request does not say which pull request or branch it would change"
        )
    return target


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


def _grant_kind(grant: Any) -> str | None:
    """The kind of a real grant, or None for anything else the gate was handed.

    An object that is not one of the two grant kinds is not a grant; it is an
    unknown permission object and the decision must be able to say so without
    crashing on it (the caller passes whatever it holds).
    """
    return grant.kind if isinstance(grant, Grant) else None


def _grant_id(grant: Any) -> str | None:
    return grant.grant_id if isinstance(grant, Grant) else None


def _run(
    action: str, target: Target | None, grant: Any, reason: str, why: str
) -> Decision:
    return Decision(
        "run",
        reason,
        why,
        action=action,
        target=target.describe() if target else "",
        grant_kind=_grant_kind(grant),
        grant_id=_grant_id(grant),
    )


def _card(
    action: str, target: Target | None, grant: Any, reason: str, why: str
) -> Decision:
    return Decision(
        "card",
        reason,
        why,
        action=action,
        target=target.describe() if target else "",
        grant_kind=_grant_kind(grant),
        grant_id=_grant_id(grant),
    )


def _refuse(
    action: str, target: Target | None, grant: Any, reason: str, why: str
) -> Decision:
    return Decision(
        "refuse",
        reason,
        why,
        action=action,
        target=target.describe() if target else "",
        grant_kind=_grant_kind(grant),
        grant_id=_grant_id(grant),
    )


def _join(names: list[str]) -> str:
    if not names:
        return "(none)"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _summarise(names: Collection[str]) -> str:
    ordered = sorted(names)
    if len(ordered) <= 3:
        return _join(ordered)
    return f"{len(ordered)} actions ({_join(ordered[:3])}, ...)"


def _plan_mismatch_reason(grant: PlanGrant, target: Target) -> str:
    """Say which exact part of the target the plan does not name."""
    repos = sorted({t.repo for t in grant.targets})
    same_repo = [
        t for t in grant.targets if t.repo.casefold() == target.repo.casefold()
    ]
    if not same_repo:
        return (
            f"The plan is for {_join(repos)}, not {target.repo}. "
            "A plan grant does not reach another repository."
        )
    for named in same_repo:
        if named.number is not None and named.number != target.number:
            return (
                f"The plan named #{named.number}, not #{target.number}. "
                "A grant for one pull request does not cover its neighbour."
            )
        if named.head is not None and named.head != target.head:
            wanted = named.head[:12] + "..."
            asked = target.head[:12] + "..." if target.head else "no pinned head"
            return (
                f"The plan pinned head {wanted}, but this write is for {asked}. "
                "The pull request moved after the owner approved the plan."
            )
        if named.file is not None and named.file != target.file:
            return f"The plan named the file {named.file}, not {target.file}."
        if named.branch is not None and named.branch != target.branch:
            return f"The plan named the branch {named.branch}, not {target.branch}."
    return f"The write to {target.describe()} is not one the plan named."


def _trusted_scope_reason(grant: TrustedSession, target: Target) -> str:
    repos = sorted({t.repo for t in grant.targets})
    same_repo = [
        t for t in grant.targets if t.repo.casefold() == target.repo.casefold()
    ]
    if not same_repo:
        return (
            f"The trust window covers {_join(repos)}, not {target.repo}. "
            "The repository is the outer edge of the window."
        )
    for named in same_repo:
        if named.number is not None and named.number != target.number:
            return (
                f"The trust window is narrowed to #{named.number}, not #{target.number}."
            )
        if named.head is not None and named.head != target.head:
            return "The trust window is pinned to a different head commit."
        if named.file is not None and named.file != target.file:
            return f"The trust window is narrowed to the file {named.file}."
        if named.branch is not None and named.branch != target.branch:
            return f"The trust window is narrowed to the branch {named.branch}."
    return f"This write to {target.describe()} is outside the trust window's own scope."


def _trusted_decision(
    grant: TrustedSession,
    action: str,
    target: Target,
    args: Mapping[str, Any],
    now: datetime,
) -> Decision:
    if not grant.owner_approved:
        return _refuse(
            action,
            target,
            grant,
            "This trusted session says the owner did not open it, so it is not a grant.",
            "Trust has to come from the owner. A boolean that any code in the "
            "process can set is only useful if a false one is treated as an "
            "attack, not as a formality.",
        )
    if grant.is_closed:
        return _card(
            action,
            target,
            grant,
            f"This trust window is closed ({grant.closed_reason}); it cannot be "
            "used again by waiting.",
            "A window that ended is not made open again by the world becoming "
            "safe. The owner opens a new one.",
        )
    if grant.process_id != current_process_id():
        return _card(
            action,
            target,
            grant,
            "Jarvis restarted since this trust window opened, and every grant "
            "dies with the process that opened it.",
            "Trust was given to one running Jarvis that the owner was watching. "
            "After a restart nobody is watching, and a saved session would be "
            "authority nobody renewed.",
        )
    if now < grant.issued_at:
        return _card(
            action,
            target,
            grant,
            f"This trust window does not open until {_stamp(grant.issued_at)}.",
            "A grant that is not open yet cannot cover a write now; a clock "
            "that disagrees with the grant is a reason to ask, not to assume.",
        )
    if now >= grant.expires_at:
        return _card(
            action,
            target,
            grant,
            f"The trust window closed at {_stamp(grant.expires_at)}; a trusted "
            "session lasts at most 60 minutes.",
            "Trust is meant to be short. Once the window closes, the next write "
            "is the owner's decision again, not an inheritance from the last one.",
        )
    if action not in GITHUB_WRITE_ACTIONS:
        return _refuse(
            action,
            target,
            grant,
            "This action is not on the GitHub write surface, so trusted mode "
            "cannot judge it and fails closed.",
            "Trusted mode is scoped to one surface. An action outside the "
            "catalogue is not 'probably fine'; it is unknown.",
        )
    if action not in TRUSTED_ALLOWLIST:
        return _card(
            action,
            target,
            grant,
            "Trusted mode covers only the eleven allowlisted GitHub writes; "
            f"{action} is not one of them, so it needs its own card.",
            "The allowlist is the owner's exact ruling. A write outside it is "
            "carded even though it is a GitHub write, because trust named a "
            "smaller surface than 'GitHub'.",
        )
    if action not in grant.allowed_writes:
        return _card(
            action,
            target,
            grant,
            f"The trust window covers {_summarise(grant.allowed_writes)}; "
            f"{action} is not one of them.",
            "The action list is the edge of the trust window. A stricter window "
            "than the owner needed is a card, never a reason to widen it.",
        )
    same_repo = [
        named
        for named in grant.targets
        if named.repo.casefold() == target.repo.casefold()
    ]
    if not same_repo:
        return _card(
            action,
            target,
            grant,
            _trusted_scope_reason(grant, target),
            "Trust is scoped by repository, and by pull request, branch or file "
            "when the owner narrowed it. A write outside that scope is a "
            "different decision, even though the tool is the same.",
        )
    if action == "github_merge_pr":
        if target.head is None:
            return _refuse(
                action,
                target,
                grant,
                "A trusted merge must name the head_sha it would merge; without "
                "the pin the gate cannot prove it is the commit the checks passed on.",
                "The merge is the one GitHub write that cannot be undone. Trusted "
                "mode may skip the card, but it may not skip the pin.",
            )
        if not _checks_passed(args):
            return _refuse(
                action,
                target,
                grant,
                "A trusted merge is only allowed with passing required checks; "
                "this request does not say the checks passed.",
                "A merge on a red pull request is exactly what the ban on "
                "bypassing checks is for. Trust covers speed, not a skipped check.",
            )
        pins = {
            named.head
            for named in same_repo
            if named.head is not None and named.number in (None, target.number)
        }
        if pins and target.head not in pins:
            pinned = sorted(pins)[0]
            return _refuse(
                action,
                target,
                grant,
                f"The pinned head_sha {target.head[:12]}... does not match the "
                f"head {pinned[:12]}... this session was opened for.",
                "A pinned merge is approval of one commit. A different head is a "
                "different change, and a trust window is not a licence to merge it.",
            )
    if not any(named.covers(target) for named in same_repo):
        return _card(
            action,
            target,
            grant,
            _trusted_scope_reason(grant, target),
            "Trust is scoped by repository, and by pull request, branch or file "
            "when the owner narrowed it. A write outside that scope is a "
            "different decision, even though the tool is the same.",
        )
    if grant.remaining(action) <= 0:
        return _refuse(
            action,
            target,
            grant,
            f"The per-action cap for this trust window allows at most "
            f"{grant.max_actions} uses of {action}, and all "
            f"{grant.max_actions} are used up. A further write is refused "
            "rather than counted as covered.",
            "The per-action cap is the owner's hard ceiling on how much trust "
            "one window can spend. When it is gone, the window is spent; it is "
            "not a reason to open another one silently.",
        )
    return _run(
        action,
        target,
        grant,
        "This is a GitHub write inside the repository, the hour and the "
        "per-action cap the owner opened, and the event stream is fresh.",
        "Trusted mode exists so a job does not card every single GitHub write "
        "inside a short, owner-opened window. This write is inside that window.",
    )


def _plan_decision(
    grant: PlanGrant, action: str, target: Target, args: Mapping[str, Any], now: datetime
) -> Decision:
    if grant.is_closed:
        divergence = grant.void_if[-1] if grant.void_if else None
        detail = divergence.describe() if divergence else grant.closed_reason
        return _card(
            action,
            target,
            grant,
            f"The plan is closed: {detail}. What the owner approved is no "
            "longer the state of the world.",
            "A plan is approval of a specific run. When the run diverges, the "
            "honest move is a new card, not the old yes stretched over it.",
        )
    if grant.process_id != current_process_id():
        return _card(
            action,
            target,
            grant,
            "Jarvis restarted since this plan was approved, and every grant dies "
            "with the process that approved it.",
            "A plan is approval of one run by one Jarvis. A restarted process "
            "cannot prove it is still that run.",
        )
    if now < grant.issued_at:
        return _card(
            action,
            target,
            grant,
            f"This plan does not open until {_stamp(grant.issued_at)}.",
            "The gate does not accept a plan before the moment it was approved.",
        )
    if now >= grant.expires_at:
        return _card(
            action,
            target,
            grant,
            f"This plan's grant expired at {_stamp(grant.expires_at)}; the job's "
            "remaining writes each need a card.",
            "A plan is for a job, not forever. Once it expires, the rest of the "
            "job is again the owner's decision.",
        )
    if action not in grant.allowed_writes:
        return _card(
            action,
            target,
            grant,
            f"The plan named {_summarise(grant.allowed_writes)}; this write is "
            f"{action}. A write that was never named is a write the owner never saw.",
            "The one card is only safe because every write was on it. An action "
            "the plan did not name is exactly the silent expansion the design forbids.",
        )
    matched = next(
        (named for named in grant.targets if named.key() == target.key()), None
    )
    if matched is None:
        return _card(
            action,
            target,
            grant,
            _plan_mismatch_reason(grant, target),
            "Exact targets are the whole safety property of a plan grant. A "
            "write to a different pull request, repository, branch, file or "
            "head is not the write the owner approved, however similar it looks.",
        )
    missing = [
        name
        for name in _PLAN_REQUIRED.get(action, ())
        if getattr(matched, name) is None
    ]
    if missing:
        return _card(
            action,
            target,
            grant,
            f"The plan named this {action} without "
            f"{_join([_FIELD_QUESTION.get(name, name) for name in missing])}, so "
            "the gate cannot prove it is the write the owner approved.",
            "A plan that leaves out the thing it changes is a blank cheque. "
            "Exact matching needs the number, file, branch or head on the plan.",
        )
    if action == "github_merge_pr" and not _checks_passed(args):
        return _card(
            action,
            target,
            grant,
            "The required checks are not passing on this merge, and a card drawn "
            "when they were green does not approve a red one.",
            "A plan is a promise about the world as it was. A merge past a red "
            "check is the failure the plan card exists to prevent.",
        )
    return _run(
        action,
        target,
        grant,
        "This write is one the plan named, on the exact target it named, inside "
        "the grant's life, with a fresh stream.",
        "This is the one card the owner approved for the whole job. Running "
        "exactly what it named - and nothing else - is the point of the shape.",
    )


def consult(
    grant: Grant | None,
    tool: str,
    args: Mapping[str, Any] | None,
    now: datetime,
    *,
    stream_fresh: bool,
    tier: str = "ask",
    pending_cards: Collection[str] = (),
    lockdown: bool = False,
) -> Decision:
    """Consult one action against one window, before it runs.

    Pure: it spends nothing and closes nothing except the one case that must be
    immediate - a trusted window shown a stale stream is voided here, even if
    this particular call is banned or unreadable, because the window itself is
    now unsafe.

    The order is the guarantee order: a standing ban (including a banned
    modifier) refuses first; a stale stream refuses everything and voids a
    trusted window; a "never" tier may not be lifted by any grant; reads run
    with no grant; a request nobody can describe is refused; a pending card and
    lockdown outrank every grant; no window means a card; then the window's own
    rules. `record_action` is what spends a use, and `GrantStore.check` is the
    one call site that pairs the two.
    """
    moment = _utc(now, "now")
    if not isinstance(stream_fresh, bool):
        raise TypeError("stream_fresh must be a bool, not a truthy value")
    if not isinstance(tier, str) or tier not in TIERS:
        raise ValueError(f"tier must be one of {sorted(TIERS)}, not {tier!r}")
    if not isinstance(lockdown, bool):
        raise TypeError("lockdown must be a bool, not a truthy value")
    if isinstance(pending_cards, (str, bytes)) or not isinstance(
        pending_cards, Collection
    ):
        raise TypeError("pending_cards must be a collection of card ids")
    cards = tuple(pending_cards)
    for card in cards:
        if not isinstance(card, str) or not card.strip():
            raise ValueError("every pending card id must be a non-empty string")
    if not isinstance(tool, str) or not tool.strip():
        return _refuse(
            "",
            None,
            grant,
            "The gate was called without a tool name, so there is nothing to judge.",
            "A gate that guesses what it was asked is worse than one that says no.",
        )
    if args is None:
        args = {}
    if not isinstance(args, Mapping):
        return _refuse(
            tool,
            None,
            grant,
            "The tool arguments are not a mapping, so the gate cannot read the "
            "target of this write.",
            "A write the gate cannot describe is a write nobody can approve.",
        )
    # A stale stream voids the window the moment it is seen, even if this
    # particular call is banned or unreadable: the window itself is now unsafe.
    if not stream_fresh and isinstance(grant, TrustedSession):
        void_stale(grant, moment)
    try:
        action = _action_for(tool, args)
    except UnknownTool as exc:
        return _refuse(
            tool,
            None,
            grant,
            f"{exc}. The gate refuses rather than guess what it would do.",
            "An unknown tool cannot be matched against a grant, and a gate that "
            "treats unknown as harmless is not a gate.",
        )
    ban = _banned_reason(action, args)
    if ban:
        return _refuse(
            action,
            None,
            grant,
            f"{_BAN_TEXT[ban]} This request asked for {ban.replace('_', ' ')}, so "
            "it is refused - a grant cannot lift a ban.",
            "A ban is not an approval that was skipped; it is something Jarvis "
            "does not offer at all. Letting a grant name it would turn the grant "
            "into a new permission.",
        )
    if not stream_fresh:
        return _refuse(
            action,
            None,
            grant,
            "The event stream is stale, so Jarvis cannot see what is happening "
            "on GitHub right now. Nothing runs - not even a write a grant would "
            "otherwise cover - until the stream is fresh again."
            + (
                " This trust window is now voided."
                if isinstance(grant, TrustedSession)
                else ""
            ),
            "A card or a grant is only as good as the picture behind it. Acting "
            "on a stale picture is how a job writes over something it never saw.",
        )
    if tier == "never":
        return _refuse(
            action,
            None,
            grant,
            "This action is set to 'never' on this PC, and no grant, card or "
            "window can lift a 'never'.",
            "The tier table is the owner's standing rule. A grant is a yes to "
            "something the table would have asked about, never a way round a no.",
        )
    if action in GITHUB_READ_ACTIONS:
        return _run(
            action,
            None,
            None,
            "This is a read: it changes nothing, so it needs no grant.",
            "Reads are the one thing that cannot use a grant to change state; "
            "carding them would make Jarvis slower without making it safer.",
        )
    try:
        target = _target_for(action, args)
    except RequestError as exc:
        return _refuse(
            action,
            None,
            grant,
            f"The gate cannot tell what this write would change: {exc}. It "
            "refuses rather than guess.",
            "An approval of something nobody can describe is not an approval. "
            "Refusing is the only honest answer to an incomplete target.",
        )
    if tier == "auto":
        return _run(
            action,
            target,
            None,
            "This action runs without a card at tier 'auto'; the grant did not "
            "allow it and is not spent by it.",
            "A grant can only narrow what would happen anyway. An action nobody "
            "was going to be asked about is not the grant's to cover, and "
            "logging it as covered would overstate the window.",
        )
    if cards:
        return _card(
            action,
            target,
            grant,
            f"An approval card was already waiting when this window opened "
            f"({cards[0]}). A grant never answers a pending card and never "
            "drains a queue; it stays with the owner.",
            "A pending card is the owner's decision in progress. A grant that "
            "answered it would silently replace a person's unfinished decision "
            "with an earlier yes, which is the opposite of what a grant is for. "
            "This check is deliberately stricter than the letter of the rule: "
            "ANY pending card blocks the write.",
        )
    if lockdown:
        return _card(
            action,
            target,
            grant,
            "Lockdown is on ('ask me about everything'), so no standing grant may "
            "stand in for the card. This write asks you.",
            "The one switch whose whole purpose is to ask about everything "
            "outranks any standing yes. The existing web-search grant already "
            "obeys this; a widened grant must not lose the rule.",
        )
    if target is None:
        if isinstance(grant, TrustedSession):
            return _card(
                action,
                None,
                grant,
                "Trusted mode covers GitHub writes only. Email, files, "
                "credentials and spending stay carded.",
                "The owner trusted Jarvis with one surface for one hour. "
                "Widening that to the rest of the PC is not what 'go trusted' "
                "meant, and those four are the things the design keeps carded.",
            )
        if isinstance(grant, PlanGrant):
            return _card(
                action,
                None,
                grant,
                "This plan names GitHub writes, and this request is not one of "
                "them, so it is not covered.",
                "A plan grant can only cover what its target grammar can name. "
                "Something else is a new card, whatever the plan says.",
            )
        return _card(
            action,
            None,
            grant,
            "No grant covers this write. It needs its own card, showing exactly "
            "what will change.",
            "This is the default: without a grant there is no standing approval "
            "to lean on, and the owner should see the write.",
        )
    if grant is None:
        return _card(
            action,
            target,
            None,
            "No grant covers this write. It needs its own card, showing exactly "
            "what will change.",
            "This is the default: without a grant there is no standing approval "
            "to lean on, and the owner should see the write.",
        )
    if isinstance(grant, TrustedSession):
        return _trusted_decision(grant, action, target, args, moment)
    if isinstance(grant, PlanGrant):
        return _plan_decision(grant, action, target, args, moment)
    return _refuse(
        action,
        target,
        grant,
        "The gate does not recognise this object as a grant, so it fails closed.",
        "Only the two grant kinds have rules. Anything else is an unknown "
        "permission object, and unknown permissions do not run writes.",
    )


def record_action(grant: Grant, action: str, *, carded: bool = True) -> int:
    """Record that a consulted action really ran; return its new use count.

    `carded` is "the gate would have raised a card for this action". It is True
    for every action a window may cover, and False for an action at tier
    "auto": the gate's `granted` event means "a grant replaced a card", and
    writing it for an action nobody was going to be asked about would overstate
    what the window did. The use is spent either way, because the action
    happened.
    """
    if not isinstance(grant, Grant):
        raise TypeError("record_action() needs a grant")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("record_action() needs the action that ran")
    if grant.is_closed:
        raise GrantClosed(
            f"this {grant.kind} grant is closed ({grant.closed_reason}); "
            "nothing more can be recorded against it"
        )
    if isinstance(grant, TrustedSession) and grant.remaining(action) <= 0:
        raise ActionCapReached(
            f"{action} has used all {grant.max_actions} uses this window allows"
        )
    used = grant._record_use(action)
    if carded:
        _grant_audit("granted", action=action, grant_id=grant.grant_id)
    return used


def close_window(
    grant: Grant, reason: str, *, state: str = "closed"
) -> bool:
    """Close this window now, with a reason a person can read; True if it closed.

    Idempotent: a second close changes nothing and writes no second
    `grant_ended` line. A closed window cannot be reopened - the object is
    never live again, and the next write it is consulted about is a card.
    """
    if not isinstance(grant, Grant):
        raise TypeError("close_window() needs a grant")
    return grant._close(reason, state)


def status(grant: Grant, now: datetime) -> dict:
    """Read one window's status: live or not, why it ended, what is left."""
    if not isinstance(grant, Grant):
        raise TypeError("status() needs a grant")
    moment = _utc(now, "now")
    if grant.is_closed:
        state = "closed"
    elif grant.process_id != current_process_id():
        state = "not this process"
    elif moment >= grant.expires_at:
        state = "expired"
    else:
        state = "open"
    left = int((grant.expires_at - moment).total_seconds())
    row = {
        "grant_id": grant.grant_id,
        "kind": grant.kind,
        "job_id": grant.job_id,
        "live": state == "open",
        "state": state,
        "reason": grant.closed_reason or "",
        "issued_at": _stamp(grant.issued_at),
        "expires_at": _stamp(grant.expires_at),
        "expires_in_seconds": max(0, left),
        "actions_taken": grant.actions_taken,
        "max_actions": grant.max_actions,
    }
    if isinstance(grant, TrustedSession):
        row["remaining"] = {
            action: grant.remaining(action)
            for action in sorted(grant.allowed_writes)
        }
    return row
