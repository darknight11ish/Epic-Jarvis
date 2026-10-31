"""repair_live_backend_gaps.py - put back the base-file pieces this PC's
install never received, without touching anything else.

WHY THIS EXISTS (measured 2026-10-30 on the owner's PC)

`main` is green and the deploy through `tools/reconcile_live_backend.py` moved
the live backend onto today's SHIPPED modules and HUD deltas with 0 refusals.
Four pieces still could not arrive, because they are **base-file or
patch-carried** content that only `scripts/apply-patches.ps1` would carry - and
that patcher refuses 37 patches on this drifted install:

1. **jarvis_gate.py** - the two `_RISK` rows for the Android app builder
   (`app_build_android`, `app_install_android`). `jarvis-backend/jarvis_gate.py`
   (the published base) has them; the live file predates them. Without them
   `jarvis_gate.risk_for()` classifies the action as unknown, and a card for an
   unknown action is raised `approve_ok: false` - the owner cannot approve an
   app build at all (found in the field test: the card appeared but only Deny
   worked).
2. **jarvis_hud.py** - the `POST /api/history/pin` and
   `POST /api/history/archive` routes (added by later revisions of
   `chat-history.patch`). The live HUD's history route tuple ends at
   `/api/history/mark`, so both answer 404; the module `jarvis_chat_log.py`
   already has the handlers (it was synced by the deploy).
3. **jarvis_gate.py** - the card timer added by `show-card-timer.patch` (the
   owner's ruling of 2026-10-30: "if there is a card with a limited time of
   any kind, be sure to put the timer on it"). `pending()` never sends
   `expires_in` on this install, so no screen can draw a countdown and a
   routine card can still run out silently - the field test hit exactly that.
4. **jarvis_gate.py** - #1008's unclassified-action rule (Gemini's Q2 ruling
   of 2026-10-30, `unknown-risk-approvable.patch`): an action with no `_RISK`
   row is given the worst case, shown with one plain warning line, approved
   only through the human check, and forced to tier "ask"; the eight reads
   that ran unattended get their own rows, so the rule changes nothing the
   owner uses today. SIX disjoint hunks (the fifth and sixth are DEF-021's
   file-wins tier fix and its revised forced-ask block, 2026-10-31). The
   first one CANNOT be replayed on this PC by
   `tools/reconcile_live_backend.py`: the `gate` repair above put the
   app-builder rows immediately after the table's opening brace, so that
   hunk's two-line pre-image no longer exists here. The change is therefore
   carried as six exact pieces, applied as ONE write (one backup, one
   compile), so it cannot land half done.

All four repairs are exact, anchored, idempotent edits. Nothing is guessed: if
an anchor is missing or appears more than once the tool refuses; if a repair is
already present it says so and writes nothing; every write is backed up first
and the result must compile or it is rolled back.

THE CARD TIMER IS TWO HUNKS, NOT ONE (measured 2026-10-30). The patch it copies
both inserts the `expires_in` block AND changes `pending()`'s SELECT line so the
row it reads has a `waited_until` column. A repair that inserts only the block
can never run - the column is not in the dict, `d.pop("waited_until", ...)` is
always None - and its own probes would still call it applied. So a `Repair` may
carry `extra_edits`: further exact old/new pairs applied in the SAME write,
with the same one backup and one compile. A file with only one of the hunks is
REFUSED rather than re-applied, so this tool can never duplicate the block.

THE UNCLASSIFIED-ACTION RULE IS SIX PIECES, AND ITS FIRST ONE IS LIVE-SHAPED
(measured 2026-10-30, read-only dry run; extended 2026-10-31 for DEF-021).
`unknown-risk-approvable.patch` adds the eight rows at the TOP of `_RISK`,
changes the `_UNKNOWN_RISK` fallback, adds to `risk_for`'s docstring and
`notice_for`'s body, makes `_tiers()` let the owner's explicit
`[autonomy.tiers]` line win over `_SYNTH_TIERS` (with `_file_tier_names()`
for check()'s exemption), and forces an unclassified action to "ask" in
`check()`. Every hunk pre-image except the first appears exactly once in the
published gate; on the file measured 2026-10-30 (when the patch still had five
hunks) the first did not, because the `gate` repair above inserted the
app-builder rows immediately after that opening brace. So a `Repair` may also carry ordered `pieces` - several exact
old/new pairs, still one write, one backup, one compile - and this repair's
first piece is anchored on the brace alone so it applies to the live shape
AND to a fresh install. The sixth piece is DEF-021's `_tiers()` /
`_file_tier_names()` hunk; its pre-image is the owner's own `_tiers()` code,
which no patch writes, and the `check()` piece's post-image is DEF-021's
revised forced-ask block. A file that already carries the earlier five
pieces and not this one is the half state the tool REFUSES rather than
duplicating (the same rule the card timer's two hunks follow); changing a
live install in that shape is a separate deploy decision, not something
this repair may guess at.

This is a REPAIR for drifted installs, not a new mechanism to prefer: once the
patch stack can be applied again (`apply-patches.ps1` succeeds), the base files
carry every piece and this tool reports "already" and does nothing.

USAGE

    python -B tools/repair_live_backend_gaps.py --backend-path "<live>"           # check only
    python -B tools/repair_live_backend_gaps.py --backend-path "<live>" --apply   # write (after a clean check)
    ... --only gate           # one repair
    ... --only history
    ... --only timer
    ... --only unknown-risk

Exit codes: 0 = every requested repair is present (or was applied);
1 = something is missing in check mode; 2 = refused (anchor missing/ambiguous,
or the rewritten file did not compile).
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Piece:
    """One exact old -> new replacement inside a repair.

    `anchor` must appear EXACTLY once in the live file or the repair refuses.
    `replace_with` is what stands in its place: for an insertion it is the
    anchor followed by the new lines, so the anchor itself survives; for a
    rewrite it is the new text."""

    anchor: str
    replace_with: str


@dataclass(frozen=True)
class Repair:
    """One anchored edit (one insertion, plus any `extra_edits`/`pieces`) in one
    live base file."""

    name: str
    filename: str
    #: Every one of these strings must be in the file for the repair to count
    #: as already present.
    probes: tuple
    #: The exact text this repair replaces. It must appear exactly once, or
    #: the tool refuses.
    anchor: str = ""
    #: What the anchor becomes. For an insertion this is the anchor plus the
    #: new lines; for a changed line it is the new line.
    replace_with: str = ""
    why: str = ""
    #: Further exact (old, new) text pairs applied in the SAME write as the
    #: anchor above - one backup, one compile, one swap. The card timer needs
    #: this: its patch has two functional hunks (the block, and the SELECT line
    #: that gives the block a column to read) and either one alone is a no-op.
    #: Each pair's old text must appear exactly once; its new text is the
    #: positive proof that pair is already in.
    extra_edits: tuple = ()
    #: A repair that changes SEVERAL disjoint places in one file may carry them
    #: as ordered pieces instead of one anchor - still ONE write, ONE
    #: `.before-repair-*` backup and ONE compile-or-rollback, so it can never
    #: land half done. `anchor`/`replace_with` above are then unused. Each
    #: piece's old text must appear exactly once.
    pieces: tuple = ()

    def parts(self) -> tuple:
        """The (Piece, ...) this repair's single anchor applies, in order."""
        if self.pieces:
            return self.pieces
        if not self.anchor:
            return ()
        return (Piece(self.anchor, self.replace_with),)


GATE_ROWS = Repair(
    name="gate",
    filename="jarvis_gate.py",
    probes=('"app_build_android": ("no"', '"app_install_android": ("no"'),
    anchor="_RISK: dict[str, tuple[str, str, str]] = {\n",
    replace_with=(
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        "    # tools/repair_live_backend_gaps.py (2026-10-30): the Android app\n"
        "    # builder's two cards. The published base has these rows; this install\n"
        "    # predates them, so the gate treated both actions as unclassified and\n"
        "    # refused to let their cards be approved. Copied from\n"
        "    # jarvis-backend/jarvis_gate.py byte for byte.\n"
        '    "app_build_android": ("no", "outbound", "runs Gradle on this PC in one task\'s own copy, and a first build downloads the Gradle distribution and the Android Gradle plugin from services.gradle.org, dl.google.com and repo.maven.apache.org - nothing of yours is sent, but build scripts are other people\'s code running with your own Windows permissions, and what they do cannot be taken back from here"),\n'
        '    "app_install_android": ("no", "local", "installs the .apk this build made onto your phone over its cable, replacing the copy already there; nothing reaches anyone else, but Jarvis has no uninstall button, so it stays on the phone until you remove it yourself"),\n'
    ),
    why="the app builder's approval cards are unapprovable without these rows",
)

HISTORY_ROUTES = Repair(
    name="history",
    filename="jarvis_hud.py",
    probes=("/api/history/pin", "/api/history/archive"),
    anchor='                     "/api/history/fork", "/api/history/mark"):\n',
    replace_with=(
        '                     "/api/history/fork", "/api/history/mark", "/api/history/pin",\n'
        '                     "/api/history/archive"):\n'
    ),
    why="pinning and archiving a chat answer 404 without these routes",
)

CARD_TIMER = Repair(
    name="timer",
    filename="jarvis_gate.py",
    probes=('d["expires_in"] = _whole', '_waited = d.pop("waited_until", None)'),
    anchor="        # Why this is being asked about at all, when the table said otherwise.\n",
    replace_with=(
        "        # 2026-10-30 (the owner's ruling: \"if there is a card with a limited\n"
        "        # time of any kind, be sure to put the timer on it\"): the request\n"
        "        # that bounds this card is shown to the screens as `expires_in`, in\n"
        "        # whole seconds, only while that request is still waiting. The card\n"
        "        # itself still has no deadline, nothing is refused because a clock\n"
        "        # reached zero, and the 60-second grace is never counted down (no\n"
        "        # request can act in it). Never 0, never negative; the remainder is\n"
        "        # rounded UP so a fraction of a second reads \"1s left\". A ceremony\n"
        "        # card carries no `waited_until` and keeps no timer. `waited_until`\n"
        "        # itself is dropped: the screens are told how long is left, never the\n"
        "        # PC's own clock reading. Copied from backend/show-card-timer.patch.\n"
        "        _waited = d.pop(\"waited_until\", None)\n"
        "        if _waited is not None:\n"
        "            try:\n"
        "                _secs_left = float(_waited) - time.time()\n"
        "            except (TypeError, ValueError):\n"
        "                _secs_left = 0.0\n"
        "            _whole = int(_secs_left)\n"
        "            if _secs_left > _whole:\n"
        "                _whole += 1\n"
        "            if _whole >= 1:\n"
        '                d["expires_in"] = _whole\n'
        "        # Why this is being asked about at all, when the table said otherwise.\n"
    ),
    #: The second half of backend/show-card-timer.patch (its SELECT hunk):
    #: pending() must ask for the column the block above reads. The patch keeps
    #: the SQL valid by splitting the one added string into two literals - the
    #: new column on the first line, `" FROM approvals"` on the second - so this
    #: is exactly that two-line post-image, not a one-line edit (which would
    #: compile and then fail at run time: "raised,waited_until WHERE ..." has no
    #: FROM clause). Without the column `d.pop("waited_until", None)` is always
    #: None - no screen ever gets an `expires_in`, which is a silent no-op this
    #: tool's probes would call applied. Same one write, one backup, one compile.
    extra_edits=(
        ('            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n',
         '            "SELECT id,action,tier,detail,prompt,created,raised,waited_until"\n'
         '            " FROM approvals"\n'),
    ),
    why="a card with a limited life cannot show its timer without both the "
        "inserted block and the SELECT column it reads",
)

UNKNOWN_RISK = Repair(
    name="unknown-risk",
    filename="jarvis_gate.py",
    probes=(
        # One line from each of the six hunks; ALL must be present, so a half
        # applied file is never mistaken for a repaired one. Each is an ADDED
        # line, so none can be present before the repair.
        '"calendar_read": ("yes", "local"',
        'UNCLASSIFIED_WARNING = ("Unclassified action - treated as permanent '
        'and able "',
        '`classified` is False when the table above has no row for `action`.',
        'nobody has written down what it does, so it is given the ',
        'out = dict(_SYNTH_TIERS)',
        'gate.unclassified_forced_ask',
    ),
    why="an action with no risk row must be approvable, and forced to ask",
    pieces=(
        Piece(
            # The eight rows, FIRST in the table as the patch puts them. Anchored on
            # the opening brace alone, because on this PC the hunk's own two-line
            # pre-image is gone: the #997 `gate` repair inserted the app builder's
            # rows immediately after that brace. The rows are copied from the
            # patch's own post-image, not typed.
            anchor='_RISK: dict[str, tuple[str, str, str]] = {\n',
            replace_with=(
                '_RISK: dict[str, tuple[str, str, str]] = {\n'
                "    # unknown-risk-approvable.patch (Gemini's Q2 ruling, 2026-10-30). These\n"
                '    # EIGHT had an "auto" line in [autonomy.tiers] and NO row here: they were\n'
                '    # the only actions that run with nobody asked while the gate itself calls\n'
                '    # them unclassified. The ruling forces every unclassified action to "ask",\n'
                '    # and these rows are what stops that rule from turning every calendar\n'
                '    # read, mail read, notes search and status check into an approval card.\n'
                '    # Each is the sentence its own tier line already implies - a read, and\n'
                '    # nothing changes - so nothing any screen shows changes today: an "auto"\n'
                '    # action raises no card. What is left of the forced "ask" is aimed at the\n'
                '    # actions nobody has written down at all.\n'
                '    #\n'
                '    # The ninth one of that shape is `lower_api_limit`, and it is NOT here on\n'
                '    # purpose: chatbot-limits.patch already gives it a row, and a second row\n'
                '    # would be dead code - the LAST one wins - which\n'
                '    # backend/test_gate_risk_words.py fails. They sit FIRST in the table, with\n'
                "    # the other reads, and that is also the placement that works: the table's\n"
                '    # END is different on a PC whose patch stack has run and on one where it\n'
                '    # has not (chatbot-limits.patch writes rows there), while these lines are\n'
                '    # the same in both.\n'
                '    "calendar_read": ("yes", "local", "reads your calendar on this PC; changes nothing in it"),\n'
                '    "email_read": ("yes", "local", "reads your mail on this PC through your own account; sends nothing and changes nothing"),\n'
                '    "notes_search": ("yes", "local", "searches your notes on this PC; changes nothing in them"),\n'
                '    "home_read": ("yes", "local", "asks the home devices you set up on your own network for their state; switches nothing"),\n'
                '    "news_read": ("yes", "outbound", "fetches the news feeds you chose; a public read that changes nothing"),\n'
                '    "page_read": ("yes", "outbound", "reads the one page you already named; that site sees this PC\'s address, and nothing changes"),\n'
                '    "github_read": ("yes", "outbound", "reads public GitHub data; sends nothing of yours and changes nothing"),\n'
                '    "docker_service_stop": ("yes", "local", "stops a service you started on this PC; starting it again is its own card"),\n'
                ''
            ),
        ),
        Piece(
            # `UNCLASSIFIED_WARNING` and the worst-case fallback it becomes.
            anchor=(
                '\n'
                '_UNKNOWN_RISK = ("no", "outbound",\n'
                '                 "not classified, so treated as irreversible and outbound")\n'
                '\n'
                '\n'
                'def risk_for(action: str) -> dict:'
            ),
            replace_with=(
                '\n'
                "#: What the card says when the gate has NO row for the action. Gemini's ruling\n"
                '#: of 2026-10-30 asks for it in plain words, and these are they: the action is\n'
                '#: given the worst case this gate has - it cannot be undone, and it can leave\n'
                '#: this PC - and the owner may still say yes, with the human check every risky\n'
                '#: card already needs. ONE sentence, used by `risk_for` and `notice_for`, so\n'
                "#: the card's warning line and its body cannot drift apart.\n"
                'UNCLASSIFIED_WARNING = ("Unclassified action - treated as permanent and able "\n'
                '                        "to leave this PC")\n'
                '\n'
                '_UNKNOWN_RISK = ("no", "outbound", UNCLASSIFIED_WARNING)\n'
                '\n'
                '\n'
                'def risk_for(action: str) -> dict:'
            ),
        ),
        Piece(
            # `risk_for`'s docstring: what `classified: false` now means.
            anchor=(
                '    decisions. The rest is there so a UI can EXPLAIN the decision rather than\n'
                '    just enforce it - a card that says "no undo: there is no unsend" teaches\n'
                '    the rule, and a card that silently refuses a swipe does not.\n'
                '    """\n'
                '    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)\n'
                '    return {'
            ),
            replace_with=(
                '    decisions. The rest is there so a UI can EXPLAIN the decision rather than\n'
                '    just enforce it - a card that says "no undo: there is no unsend" teaches\n'
                '    the rule, and a card that silently refuses a swipe does not.\n'
                '\n'
                '    `classified` is False when the table above has no row for `action`. Since\n'
                "    Gemini's ruling of 2026-10-30 that is not a refusal: the action is given\n"
                '    the worst case the table has (reversible "no", reach "outbound", so no\n'
                '    swipe), its `why` is UNCLASSIFIED_WARNING - the plain warning line every\n'
                '    card shows - and the owner may still approve it, through the same human\n'
                "    check (Windows Hello on this PC, the phone's own lock) every risky card\n"
                '    needs. `check()` is the other half: it forces such an action to tier\n'
                '    "ask", so it can never run unattended.\n'
                '    """\n'
                '    rev, reach, why = _RISK.get(action or "", _UNKNOWN_RISK)\n'
                '    return {'
            ),
        ),
        Piece(
            # `notice_for`: the body says WHY the worst case was chosen.
            anchor=(
                '    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised\n'
                '\n'
                '    bits = [r["why"]]\n'
                '    if raised:\n'
                '        # Said, never quoted. That something tried to rush you is the fact that\n'
                '        # changes your decision; its actual words are not needed to convey it,'
            ),
            replace_with=(
                '    heavy = (r["reversible"] == "no") or (r["reach"] != "local") or raised\n'
                '\n'
                '    bits = [r["why"]]\n'
                '    if not r["classified"]:\n'
                '        # The warning line above is the headline; this says WHY the worst case\n'
                "        # was chosen, in the plainest words there are. Both are this file's own\n"
                '        # strings, so the notice is still safe by construction on a lock screen\n'
                '        # (see the docstring above): nothing here reads the payload.\n'
                '        bits.append("nobody has written down what it does, so it is given the "\n'
                '                    "worst case")\n'
                '    if raised:\n'
                '        # Said, never quoted. That something tried to rush you is the fact that\n'
                '        # changes your decision; its actual words are not needed to convey it,'
            ),
        ),
        Piece(
            # DEF-021 (2026-10-31): `_tiers()` lets the owner's explicit
            # `[autonomy.tiers]` line win over `_SYNTH_TIERS`, and the new
            # `_file_tier_names()` beside it is what check()'s forced-ask
            # exemption reads. Its anchor is the owner's OLD function alone; the
            # patch's context around it is dropped, so the same piece applies to
            # the published pre-image, the live gate and the test's synthetic
            # gate. This is the patch's SIXTH hunk (the hunk before the revised
            # check() block below).
            anchor=(
                'def _tiers(framework: Optional[dict] = None) -> dict:\n'
                '    """The tier table, validated. An unrecognised tier string - "Never" with a\n'
                '    capital, "aks", anything not in _VALID_TIERS - is treated as "never",\n'
                '    because a typo in a security policy should lock, not unlock."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        raw = f.get("autonomy", {}).get("tiers", {}) or {}\n'
                '    except Exception:\n'
                '        return {}\n'
                '    out = {}\n'
                '    for k, v in raw.items():\n'
                '        v = str(v).strip().lower()\n'
                '        out[k] = v if v in _VALID_TIERS else "never"\n'
                '    out.update(_SYNTH_TIERS)\n'
                '    return out'
            ),
            replace_with=(
                'def _tiers(framework: Optional[dict] = None) -> dict:\n'
                '    """The tier table, validated, with the owner\'s explicit line winning.\n'
                '\n'
                '    An unrecognised tier string - "Never" with a capital, "aks", anything not\n'
                '    in _VALID_TIERS - is treated as "never", because a typo in a security\n'
                '    policy should lock, not unlock.\n'
                '\n'
                '    THE FILE WINS OVER THE TOOL TABLE (DEF-021, 2026-10-31). `_SYNTH_TIERS`\n'
                "    holds the gate's own per-tool defaults for names that are not actions of\n"
                '    [autonomy.tiers] ("calculator" -> auto, "memory_store" -> notify). It used\n'
                '    to be applied AFTER the file, so an owner who wrote a line for one of\n'
                "    those names had it silently overwritten - and `check()`'s forced-ask\n"
                "    exemption then skipped exactly those names. The owner's file is the\n"
                '    policy: its validated line is laid over the synthesised table, so what the\n'
                '    What-asks-first page already showed is what the gate now does. A name with\n'
                '    no file line still takes its synthesised tier unchanged."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        raw = f.get("autonomy", {}).get("tiers", {}) or {}\n'
                '    except Exception:\n'
                '        return {}\n'
                '    out = dict(_SYNTH_TIERS)\n'
                '    for k, v in raw.items():\n'
                '        v = str(v).strip().lower()\n'
                '        out[k] = v if v in _VALID_TIERS else "never"\n'
                '    return out\n'
                '\n'
                '\n'
                'def _file_tier_names(framework: Optional[dict] = None) -> set:\n'
                '    """The actions with an EXPLICIT line in the file\'s [autonomy.tiers].\n'
                '\n'
                "    Used by `check()`'s forced-ask rule (DEF-021): the tool-table exemption\n"
                '    applies only when the owner has NOT written a line for that name. A name\n'
                "    the file names is the owner's own action and takes the ordinary rule, so\n"
                '    an unclassified one is still forced to "ask"; a name the file does not\n'
                "    name keeps the gate's per-tool default. Never raises; an unreadable file\n"
                '    answers an empty set, which is the stricter direction for every other rule\n'
                '    (the empty tier table itself refuses in `check()`)."""\n'
                '    try:\n'
                '        f = framework if framework is not None else fw.load_framework()\n'
                '        return set((f.get("autonomy", {}) or {}).get("tiers", {}) or {})\n'
                '    except Exception:\n'
                '        return set()'
            ),
        ),
        Piece(
            # `check()`: an action with no row is forced to ask; never untouched.
            # DEF-021 (2026-10-31) revised this block: the tool-table exemption
            # now needs the owner's file to have NO line for the name too. The
            # anchor and the replacement are the patch's own sixth hunk.
            anchor=(
                '            # is no reading of "no policy" under which a tool call is safe.\n'
                '            raise RuntimeError("autonomy tier table is empty")\n'
                '        tier = tiers.get(action, UNKNOWN_TIER)\n'
                '    except Exception as exc:\n'
                '        # Cannot read the policy -> cannot claim the action is permitted.\n'
                '        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})'
            ),
            replace_with=(
                '            # is no reading of "no policy" under which a tool call is safe.\n'
                '            raise RuntimeError("autonomy tier table is empty")\n'
                '        tier = tiers.get(action, UNKNOWN_TIER)\n'
                "        # AN ACTION WITH NO RISK ROW MAY NOT RUN WITH NOBODY ASKED (Gemini's\n"
                '        # ruling Q2, 2026-10-30). risk_for() already gives such an action the\n'
                '        # worst case it has - permanent and outbound - and this is the other\n'
                '        # half: whatever [autonomy.tiers] says, an action the risk table does\n'
                '        # not know is forced to "ask". "never" is stricter than ask and is left\n'
                '        # exactly as it is. A risk table that cannot be read forces it too.\n'
                '        #\n'
                '        # A TOOL-TABLE NAME IS EXEMPT ONLY WHEN THE FILE DOES NOT NAME IT.\n'
                '        # `_SYNTH_TIERS` holds the TOOLS whose tier `action_for_tool()` sets\n'
                '        # directly from `_TOOL_ACTIONS` ("calculator" -> auto, "memory_store"\n'
                '        # -> notify, "git_commit" -> ask). Those are the gate\'s own per-tool\n'
                '        # decisions, not actions the risk table classifies - forcing them to\n'
                '        # ask would card every calculation and every saved memory, which is\n'
                '        # not what this rule is for. But an owner who writes an explicit\n'
                '        # [autonomy.tiers] line for one of those names has made it their own\n'
                '        # action (DEF-021, 2026-10-31): the file wins over the tool table in\n'
                '        # `_tiers()`, and this rule must agree with that rather than silently\n'
                '        # skipping the name. So the exemption needs BOTH - the name is in the\n'
                '        # tool table AND the file has no line for it. Everything else is\n'
                '        # covered, including an action with no tier line at all (whose\n'
                '        # fallback used to be loosened by `[autonomy] unknown_action_tier` in\n'
                "        # the owner's file).\n"
                '        #\n'
                '        # Nothing that runs unattended today changes: every action the shipped\n'
                '        # config sets to "auto" or "notify" has its own row (the nine that did\n'
                '        # not are added by this patch), so this closes the hole for the NEXT\n'
                '        # action somebody adds without one.\n'
                '        try:\n'
                '            _explicit = _file_tier_names(framework)\n'
                '        except Exception:\n'
                '            _explicit = set()\n'
                '        try:\n'
                '            _forced = (tier != "never"\n'
                '                       and not (isinstance(action, str)\n'
                '                                and action in _SYNTH_TIERS\n'
                '                                and action not in _explicit)\n'
                '                       and not risk_for(action)["classified"])\n'
                '        except Exception:\n'
                '            _forced = tier != "never"\n'
                '        if _forced:\n'
                '            if tier != "ask":\n'
                '                _audit("gate.unclassified_forced_ask", {"action": action, "was": tier})\n'
                '            tier = "ask"\n'
                '    except Exception as exc:\n'
                '        # Cannot read the policy -> cannot claim the action is permitted.\n'
                '        _audit("gate.policy_unreadable", {"action": action, "error": str(exc)})'
            ),
        ),
    ),
)


REPAIRS = {r.name: r for r in (GATE_ROWS, HISTORY_ROUTES, CARD_TIMER,
                              UNKNOWN_RISK)}


class Refused(Exception):
    pass


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")


def _anchor_problem(repair: Repair, text: str) -> str:
    """'' when every anchor is there exactly once, else the refusal text.

    A repair can name several places: `pieces` (a multi-region change - the
    unclassified-action rule's six hunks) and `extra_edits` (further exact
    old/new pairs applied in the same write - the card timer's SELECT line). ALL
    of them are checked BEFORE anything is written, so drift in any one region
    refuses the whole repair instead of applying the parts it could find."""
    parts = repair.parts()
    if not parts:
        return (f"{repair.filename}: the repair {repair.name!r} has no anchor; "
                "refusing to guess")
    checks = []
    for index, piece in enumerate(parts, 1):
        where = f" ({index} of {len(parts)} pieces)" if len(parts) > 1 else ""
        checks.append((piece.anchor, f"the anchor for {repair.name!r}{where}"))
    for index, (old, _new) in enumerate(repair.extra_edits, 1):
        checks.append((old, f"the extra edit {index} of {repair.name!r}"))
    for anchor, label in checks:
        if not anchor:
            return f"{repair.filename}: {label} is empty; refusing to guess"
        count = text.count(anchor)
        if count == 1:
            continue
        if count == 0:
            return (f"{repair.filename}: {label} is not there any more. Nothing was "
                    "written; this install has drifted further and needs a real look.")
        return (f"{repair.filename}: {label} appears {count} times; refusing to guess "
                "which one.")
    return ""


def check_one(live: Path, repair: Repair) -> str:
    """'already' or 'missing'. Raises Refused when the file/anchor is unusable.

    A repair with several hunks (`extra_edits` for the card timer, `pieces` for
    the unclassified-action rule) is ONE change in one file, so a file holding
    only SOME of them is neither 'already' nor safe to insert again - re-running
    the insertion would put a second copy of a block in the live file. That half
    state is REFUSED; the card timer's two hunks (2026-10-30) are why.
    """
    p = live / repair.filename
    if not p.is_file():
        raise Refused(f"{repair.filename} is not in {live} - is this the live backend folder?")
    text = read(p)
    inserted = all(probe in text for probe in repair.probes)
    extras = [replacement in text for _old, replacement in repair.extra_edits]
    if inserted and all(extras):
        return "already"
    if inserted or any(extras):
        raise Refused(
            f"{repair.filename}: the {repair.name!r} repair is only PARTLY present "
            f"({'the inserted block' if inserted else 'a changed line'} is in, the "
            "rest is not). Refusing rather than writing it again and duplicating "
            "code; look at the file by hand.")
    problem = _anchor_problem(repair, text)
    if problem:
        raise Refused(problem)
    return "missing"


def apply_one(live: Path, repair: Repair, *, stamp: str) -> str:
    """Apply the repair's hunks in one write, compiling before the swap sticks."""
    p = live / repair.filename
    state = check_one(live, repair)
    if state == "already":
        return "already"
    text = read(p)
    new = text
    for piece in repair.parts():
        new = new.replace(piece.anchor, piece.replace_with, 1)
    for old, replacement in repair.extra_edits:
        new = new.replace(old, replacement, 1)
    backup = p.with_name(p.name + f".before-repair-{stamp}")
    # ONE backup per file per run, holding the file as it was BEFORE this run's
    # first write. This matters now that two repairs write the same file
    # (`timer` and `unknown-risk` both write jarvis_gate.py): if the second one
    # copied the file over this backup, the bytes from before the run would be
    # lost and only an intermediate state kept.
    if not backup.exists():
        shutil.copy2(p, backup)
    fd, tmpname = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(live))
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        py_compile.compile(tmpname, doraise=True)
        shutil.move(tmpname, str(p))
    except Exception as exc:
        # Put the original back and remove the temporary, so the live folder is
        # never left in a half-written state.
        try:
            shutil.copy2(backup, p)
        finally:
            Path(tmpname).unlink(missing_ok=True)
        raise Refused(f"{repair.filename}: the repaired file did not compile "
                      f"({type(exc).__name__}); the original was restored") from exc
    return "applied"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend-path", required=True,
                    help="the folder holding the live jarvis_hud.py")
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs (without it this is a check)")
    ap.add_argument("--only", default="", choices=["", *REPAIRS.keys()],
                    help="repair only this one")
    ns = ap.parse_args(argv)
    live = Path(ns.backend_path).expanduser()
    chosen = [REPAIRS[ns.only]] if ns.only else list(REPAIRS.values())
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outcomes = []
    try:
        for repair in chosen:
            state = check_one(live, repair)
            if state == "already":
                print(f"ok       {repair.name}: already present")
                outcomes.append("already")
                continue
            if not ns.apply:
                print(f"MISSING  {repair.name}: {repair.why}")
                outcomes.append("missing")
                continue
            applied = apply_one(live, repair, stamp=stamp)
            print(f"{'applied ' if applied == 'applied' else 'ok      '} {repair.name}: "
                  f"{repair.filename} ({'written, backup kept' if applied == 'applied' else 'already present'})")
            outcomes.append(applied)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    if "missing" in outcomes:
        print("\nNothing was changed. Re-run with --apply after reviewing the above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
