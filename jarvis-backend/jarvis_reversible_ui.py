"""jarvis_reversible_ui.py - the ONE allow-list behind the manual-click rule.

THE OWNER'S ASK (2026-11-09), in their own words: *"if i manually choose
anything in the jarvis app or deskstop program, and its something that i can
easily click and change back right away, it shouldnt need a card"*.

GEMINI'S RULING Q2 (2026-11-09): implement that as an EXPLICIT BACKEND
ALLOW-LIST gated by a trusted UI-origin signal - "never a blanket route-level
bypass on all endpoints", and never a header or body field a model can set.
This module is that allow-list. It is data plus two small helpers; it decides
nothing else.

WHAT "REVERSIBLE" MEANS HERE, and it means ALL of this or the action is not on
the list:

  * ONE CLICK BACK. The owner can put it back from the same screen, straight
    away, without waiting for a model to answer.
  * ALREADY HERE. It uses something already installed on this PC. Nothing is
    downloaded or installed.
  * NO LOSS. Nothing is deleted, moved out of a backup, or forgotten.
  * NO SPEND. It costs no money and calls no paid service.
  * NO PRIVACY OR SECURITY DOWNGRADE. It turns no protection off and widens no
    boundary. A change that gives Jarvis MORE reach is the opposite of
    reversible-by-click, even when the click is easy.

THE TRUSTED-UI SIGNAL IS THE ROUTE, NOT A FIELD. `install()` wraps ONE path
(`/api/models/switch`) on the HUD's own Handler, after the server's origin
check and pairing-token check have passed - the same shape
`jarvis_presets.install()` already uses for `POST /api/work/apply`. The model
never posts to these routes: a chat tool call reaches the modules in-process.
So a request that arrives here came from a paired app's own control. No
request body, header or query parameter is read for "no card": the uncarded
road is chosen by the path before the body is even parsed. Every other route
is forwarded untouched to the handler that already owned it.

REVERSIBLE_UI_CHOICES - what may be uncarded, and the ONE model/chat path that
still asks for each (the evidence the fence has two sides):

  * `apply_preset` - one local preset is one model switch on a lane the owner
    already has. Clicking another preset (or the receipt's Undo) puts it back.
    The app road is `POST /api/work/apply` -> `jarvis_presets.install()` ->
    `_apply_body(..., owner_ui=True)` (`jarvis_presets.py:2055`). The model
    path is `jarvis_presets.apply_from_body` -> `_apply_body(...,
    owner_ui=False)` (`jarvis_presets.py:1978`) -> `jarvis_models.switch_to`
    (`jarvis_presets.py:1901`) -> the `switch_model` card
    (`jarvis-backend/jarvis_models.py:1174`); its callers are
    `jarvis_model_knowledge.apply_preset` and
    `jarvis_settings_registry.set_focus_preset`.

  * `switch_model` - choosing a model the PC already has. The previous model
    is one line above it in the same list, so the way back is a click. The app
    road is `POST /api/models/switch` -> this module's `install()` ->
    `jarvis_presets.switch_model_for_the_owner` (the same body a preset click
    uses: one model record and one tripwire, no card). The model path is
    `jarvis_quick.py:20846` -> `jarvis_model_knowledge.switch_model`
    (`jarvis_model_knowledge.py:313`) -> `jarvis_models.switch_to(ref,
    why="chat")` -> the `switch_model` card
    (`jarvis-backend/jarvis_models.py:1174`, tier "ask" in
    `backend/rebuilt/jarvis-framework.toml`).

WHAT IS DELIBERATELY NOT ON THE LIST, even when the button is easy to press:
deleting or erasing a memory, `forget_range`, deleting or uninstalling a skill
or a model, reverting files; installing or editing a skill, plugin or model
(`download_model`), applying self-code patches, running system updates;
turning Lockdown off, changing App Lock / Windows Hello, revealing a
private/hidden list, storing or changing a credential, raising a spend or
safety cap; creating a GitHub repo, sending email or messages, importing an
external archive (a Notion export, a chat-history archive). Each of these is
one click to do and NOT one click to undo, or it widens a boundary. They stay
carded on BOTH roads: the allow-list refuses them by name, and this module
intercepts no route that could reach them.

THE EVERYDAY SETTINGS, AUDITED 2026-11-09 (this is the honest part - most of
these needed no change at all):

  ALREADY CARDLESS on both roads, so listing them in the allow-list would
  claim a fence that does not exist:
    * read_aloud - `backend/jarvis_read_aloud.py:181` `set_enabled()` writes
      and publishes; there is no `jarvis_gate` call anywhere in that file.
    * voice (the built-in voice picker) - `backend/jarvis_voices.py:678`
      `set_speaker()` says "at once, no card either way". (The voice CHECK,
      better-voice and enrolment cards at `:3482`, `:3614` and `:3780` are
      different actions and stay carded.)
    * theme / face - `backend/jarvis_settings_registry.py:3490` `set_face()`
      is cosmetic and cardless.
    * to-do carry-over - `backend/jarvis_settings_registry.py:3646` calls
      `jarvis_schedule.set_todo_mode_here`; that module raises no
      `jarvis_gate` card (its own note at `backend/jarvis_schedule.py:404`),
      and the setting never moves or deletes an item.
    * the six PC notification switches - `backend/jarvis_settings_registry.py`
      `_set_notify()` (around `:1206`) rides `jarvis_limits.change` with
      `loosening="none"` on all six (`backend/jarvis_limits.py:406-414`):
      they only change when this PC speaks up.

  ALREADY CARDLESS IN THE SAFE DIRECTION ONLY, and deliberately left that way:
  turning such a switch OFF takes an ability away and is instant; turning it
  ON gives Jarvis more reach and still raises its card, because that is a
  privacy/security WIDENING and the owner's rule does not cover it:
    * `wifi_auto_reconnect` - OFF at `backend/jarvis_wifi.py:1448-1460` (no
      gate); ON raises ONE `change_own_config` at `:1464`.
    * `background_learning` / `learn_sensitive` / `learn_paraphrase` - OFF at
      `backend/jarvis_auto_learn.py:571-596`; ON spawns `_decide`, whose gate
      is at `:526`.
    * `phone_notifications` - OFF at `backend/jarvis_phone_notifications.py`
      `request()` (the `if not enabled:` branch); ON goes through `_decide`
      (gate at `:272`).
    * `watch_notify` - OFF at `backend/jarvis_watch_notify.py` `request()`
      (the `if not enabled:` branch); ON through `_decide` (gate at `:231`).
    * skills ON/OFF - OFF at `backend/jarvis_skill_menu.py:935-959` moves the
      folder out and raises nothing; ON at `:961-1009` runs the scanner and
      `jarvis_skills.install()`'s `modify_own_code` card, because it offers
      executable skill text to the model again.

  NOT WIRED, and why, rather than a guess:
    * the morning briefing's hour - no shipped module in this repository sets
      it (the setter lives in the live `jarvis_hud.py`, which this repository
      patches but never ships). Wiring it would need a new patch for a
      time-of-day preference; it is recorded here as a candidate, not claimed.
    * `briefing_senders` - its ON card is
      `backend/jarvis_briefing.py:1960`; it is left exactly as it is rather
      than audited further, because showing who mail is from in the briefing
      is a privacy widening, not an everyday toggle.

HONEST LIMITS (do not claim more than this module does):

  * It cannot make a route cardless that the HUD owns and this repository
    never ships. It wraps the ONE route both apps already use for a model
    switch.
  * `jarvis_models.switch_to` is NOT changed here. That module is patched,
    never shipped (`test_shipped_modules.py` says so), and the base copy is a
    published snapshot - adding a keyword to it would either be an
    undeliverable base edit or a new patch. The uncarded switch therefore
    reuses `jarvis_presets`' proven helper instead of adding a parameter every
    existing caller could pass by mistake. Every model/chat path still reaches
    the unchanged `switch_to` and still asks.
  * A toggle whose module is not shipped here is listed, not wired. A wrong
    claim would be worse than an unfinished one.

Standard library only. No global mutable state, no environment switch, and no
request input decides whether a card is raised.
"""

from __future__ import annotations

import json
from typing import Mapping

#: The one route this module intercepts. It is the owner's own model picker on
#: the desktop (`jarvis-desktop` Brain -> Model) and the phone (`jarvis-client`
#: Brain -> Models), and the same route `jarvis_presets.SWITCH_ROUTE` names.
SWITCH_ROUTE = "/api/models/switch"

#: Action -> why it is reversible AND the one model/chat path that still asks.
#: Ordered as the owner meets them: a preset is a model choice, a model is one
#: line in the same list. Adding a key here is the WHOLE permission: nothing
#: else in this program turns a card off for a name in this mapping.
REVERSIBLE_UI_CHOICES: Mapping[str, Mapping[str, str]] = {
    "apply_preset": {
        "reason": ("One local preset is one model switch on a lane this PC "
                   "already has. The preset rail and the receipt's Undo are "
                   "both one click, and nothing is downloaded, deleted or "
                   "spent."),
        "ui_road": ("POST /api/work/apply -> jarvis_presets.install() -> "
                    "_apply_body(..., owner_ui=True) (jarvis_presets.py:2055)"),
        "model_path_asks": (
            "jarvis_presets.apply_from_body -> _apply_body(..., "
            "owner_ui=False) (jarvis_presets.py:1978) -> "
            "jarvis_models.switch_to (jarvis_presets.py:1901) -> the "
            "switch_model card (jarvis-backend/jarvis_models.py:1174); "
            "callers jarvis_model_knowledge.apply_preset and "
            "jarvis_settings_registry.set_focus_preset"),
    },
    "switch_model": {
        "reason": ("A model already on this PC, picked in either app's own "
                   "model list. The previous model is one line above it, so "
                   "the way back is a click; nothing is downloaded, deleted "
                   "or spent."),
        "ui_road": ("POST /api/models/switch -> jarvis_reversible_ui.install() "
                    "-> jarvis_presets.switch_model_for_the_owner "
                    "(one model record and one tripwire, no card)"),
        "model_path_asks": (
            "jarvis_quick.py:20846 -> jarvis_model_knowledge.switch_model "
            "(jarvis_model_knowledge.py:313) -> jarvis_models.switch_to(ref, "
            "why=\"chat\") -> the switch_model card "
            "(jarvis-backend/jarvis_models.py:1174; tier \"ask\" in "
            "backend/rebuilt/jarvis-framework.toml)"),
    },
}

#: Name -> why it always asks. This is documentation the tests read, not a
#: mechanism: these names are simply absent from REVERSIBLE_UI_CHOICES, and no
#: route this module installs can reach them.
EXCLUDED_UI_ACTIONS: Mapping[str, str] = {
    "delete_memory": "deleting a fact cannot be undone by a click - there is "
                     "nothing left to click back",
    "forget_range": "it deletes facts and chats from a time range; the second "
                    "yes is the owner's (jarvis_forget_range.py)",
    "delete_skill": "removes installed skill code; not one click back",
    "delete_model": "removes gigabytes from disk; not one click back",
    "download_model": "installs a model (jarvis-backend/jarvis_models.py:1092, "
                      "download_model) - a download, not a choice",
    "install_skill": "installs executable skill text "
                     "(jarvis_skills.py's modify_own_code card)",
    "edit_skill": "edits executable skill text (modify_own_code)",
    "install_plugin": "installs program code (modify_own_code)",
    "apply_self_code": "changes Jarvis's own code (modify_own_code)",
    "run_update": "installs a new build of the program",
    "revert_files": "replaces files from a backup; the old state is gone",
    "lockdown_off": "turning Lockdown OFF widens what Jarvis may do without "
                    "asking - a security downgrade, never a toggle",
    "app_lock": "App Lock / Windows Hello settings are the lock itself",
    "credentials": "storing or changing a credential is a boundary change",
    "reveal_private_memory": "shows a list that was deliberately hidden",
    "raise_spend_limit": "raises how much money Jarvis may spend",
    "raise_safety_cap": "raises a cap that exists to stop harm",
    "github_create_repo": "creates a repository in the outside world",
    "send_email": "an email cannot be unsent",
    "send_message": "a message cannot be unsent",
    "import_notion_export": "imports an external archive into memory",
    "import_history": "imports an external archive into memory",
    "purge_history": "deletes conversation history",
}

#: Settings that already need NO card on either road. Listed so a reader does
#: not go looking for a fence here: there is nothing to un-card. Evidence is
#: the line that decides it, read 2026-11-09.
ALREADY_CARDLESS_UI: Mapping[str, Mapping[str, str]] = {
    "read_aloud": {
        "evidence": "backend/jarvis_read_aloud.py:181 set_enabled(); the file "
                    "contains no jarvis_gate call (POST route at :297)",
        "note": "one write and one event, from either app or by voice",
    },
    "voice": {
        "evidence": "backend/jarvis_voices.py:678 set_speaker() - \"at once, "
                    "no card either way\"",
        "note": "the built-in voice picker; voice CHECK/enrolment stay carded",
    },
    "theme_face": {
        "evidence": "backend/jarvis_settings_registry.py:3490 set_face() - "
                    "cosmetic, no card",
        "note": "one file write and one appearance event",
    },
    "todo_carryover": {
        "evidence": "backend/jarvis_settings_registry.py:3646 -> "
                    "jarvis_schedule.set_todo_mode_here; no jarvis_gate call "
                    "in that module (its note at jarvis_schedule.py:404)",
        "note": "never moves, copies or re-dates an item",
    },
    "pc_notifications": {
        "evidence": "backend/jarvis_settings_registry.py:1206 _set_notify() -> "
                    "jarvis_limits.change; loosening=\"none\" on all six at "
                    "backend/jarvis_limits.py:406-414",
        "note": "alarm/reminder/briefing/handoff/setup/quiet-hours switches",
    },
}

#: Settings that are instantaneous when turned OFF (taking an ability away)
#: and still raise ONE card when turned ON (giving Jarvis more reach). They
#: are NOT on the allow-list, because the ON direction is exactly the kind of
#: widening the owner's rule does not cover.
SAFE_DIRECTION_ONLY_UI: Mapping[str, Mapping[str, str]] = {
    "wifi_auto_reconnect": {
        "off": "backend/jarvis_wifi.py:1448-1460 - writes, no gate",
        "on": "backend/jarvis_wifi.py:1464 - ONE change_own_config card",
    },
    "background_learning": {
        "off": "backend/jarvis_auto_learn.py:571-596 - applies, no gate",
        "on": "backend/jarvis_auto_learn.py:618 -> _decide, gate at :526",
    },
    "learn_sensitive": {
        "off": "backend/jarvis_auto_learn.py:571-596 - applies, no gate",
        "on": "backend/jarvis_auto_learn.py:618 -> _decide, gate at :526",
    },
    "learn_paraphrase": {
        "off": "backend/jarvis_auto_learn.py:571-596 - applies, no gate",
        "on": "backend/jarvis_auto_learn.py:618 -> _decide, gate at :526",
    },
    "phone_notifications": {
        "off": "backend/jarvis_phone_notifications.py request(), the "
               "\"if not enabled\" branch",
        "on": "through _decide, gate at backend/jarvis_phone_notifications.py:272",
    },
    "watch_notify": {
        "off": "backend/jarvis_watch_notify.py request(), the \"if not "
               "enabled\" branch",
        "on": "through _decide, gate at backend/jarvis_watch_notify.py:231",
    },
    "skills_on_off": {
        "off": "backend/jarvis_skill_menu.py:935-959 - moves the folder out, "
               "raises nothing",
        "on": "backend/jarvis_skill_menu.py:961-1009 -> "
              "jarvis_skills.install()'s modify_own_code card",
    },
    "briefing_senders": {
        "off": "not audited further by this lane",
        "on": "backend/jarvis_briefing.py:1960 - the senders card",
    },
}

#: Settings this lane could not wire, said plainly.
NOT_WIRED_UI: Mapping[str, str] = {
    "briefing_hour": ("no shipped module in this repository sets the briefing "
                      "hour; the setter lives in the live jarvis_hud.py, which "
                      "this repository patches but never ships. Wiring it "
                      "would need a new patch for a time-of-day preference, so "
                      "it is recorded here rather than claimed."),
}


def is_reversible_ui_choice(action) -> bool:
    """True only for a name in REVERSIBLE_UI_CHOICES.

    Deliberately strict: a non-string, an empty string, a header-shaped name or
    an unknown action is NOT a reversible choice. A typo here must fail closed
    (the caller keeps its card), never open.
    """
    return isinstance(action, str) and action in REVERSIBLE_UI_CHOICES


def reason_for(action) -> str:
    """The plain-words reason, or "" when the action is not on the list."""
    row = REVERSIBLE_UI_CHOICES.get(action) if isinstance(action, str) else None
    return str((row or {}).get("reason") or "")


def is_excluded(action) -> bool:
    """True for a name the ruling says must always ask. Documentation only."""
    return isinstance(action, str) and action in EXCLUDED_UI_ACTIONS


def _switch_for_the_owner(ref: str, why: str) -> dict:
    """The one uncarded model switch, from `jarvis_presets` (imported lazily).

    Kept out of this module's import graph so importing the allow-list never
    imports the model steward or the graphics-card code. A missing module is an
    honest refusal, never a silent success.
    """
    try:
        import jarvis_presets as P
    except Exception as exc:
        return {"ok": False, "ref": str(ref),
                "reason": (f"the model steward is not available "
                           f"({type(exc).__name__})")}
    fn = getattr(P, "switch_model_for_the_owner", None)
    if not callable(fn):
        return {"ok": False, "ref": str(ref),
                "reason": "this PC's preset module has no owner model switch"}
    out = fn(ref, why=why)
    return out if isinstance(out, dict) else {"ok": False, "ref": str(ref),
                                               "reason": "the model switch answered nothing"}


def install(Handler, *, origin_ok, token_ok, read_body) -> str:
    """Wrap POST /api/models/switch on the HUD's Handler. Returns a status line.

    The wrapper copies the HUD's own branch exactly - origin check, token
    check, JSON object body, then the switch - and forwards EVERY other path to
    the handler that already owned it. It reads only `ref` and `why` from the
    body. No field, header or query parameter is consulted for "no card": the
    path decides, and the path is only reachable from a paired app because the
    origin and token checks passed above.
    """
    original = getattr(Handler, "do_POST", None)

    def do_POST(self):
        path = str(getattr(self, "path", "") or "").split("?", 1)[0]
        if path != SWITCH_ROUTE:
            if original is None:
                return self._send(404, {"error": "not found"})
            return original(self)
        if not origin_ok(self):
            return self._send(403, {"error": "cross-origin request refused"})
        if not token_ok(self):
            return self._send(401, {"error": "bad or missing X-Jarvis-Token"})
        try:
            body = json.loads(read_body(self) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"error": str(exc)})
        if not isinstance(body, dict):
            return self._send(400, {"error": "body must be an object"})
        # ONLY these two keys are read. `owner_ui`, `ui_direct`, `no_card` and
        # every other invented field are not looked at - the path already said
        # this was the owner's own control.
        ref = str(body.get("ref") or "")
        if not ref:
            return self._send(400, {"error": "need a model ref"})
        why = str(body.get("why") or "desktop")
        try:
            out = _switch_for_the_owner(ref, why)
        except Exception as exc:                 # the HUD's own branch answers 500 too
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._send(200 if out.get("ok") else 409, out)

    Handler.do_POST = do_POST
    return f"reversible  ready ({len(REVERSIBLE_UI_CHOICES)} choice(s))"
