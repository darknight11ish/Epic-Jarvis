#!/usr/bin/env python3
"""Compare what the desktop can do against what the phone can do, and fail
when the answer has changed without anyone deciding about it.

    python3 tools/check_parity.py

The two apps are both clients of the same Python backend, so the set of
`/api/...` routes each one calls is a fair, machine-readable proxy for its
feature surface. That is the whole idea here: parity as a check rather than a
promise. A document saying "the phone is up to date" is worth nothing a week
later; this fails the build. CI runs it on every push (.github/workflows/ci.yml).

What it reads - all from THIS checkout:

  desktop  jarvis-desktop/src-tauri/src/**/*.rs   the Rust side
           jarvis-desktop/src/**/*.{js,mjs,html}   the windows, which call
                                                   routes themselves too
  phone    jarvis-client/app/src/main/java/**/*.kt

Comments are stripped before routes are collected, so a route a file only
TALKS about (a KDoc line, a "// /api/graph is desktop-only" note) does not
count as a call.

A route with an id in it is kept whole. `/api/pending/{encoded}/amend` (Rust),
`/api/pending/$encodedId/amend` (Kotlin) and `/api/pending/${id}/amend`
(JavaScript) all become `/api/pending/{id}/amend` - not `/api/pending`, which
is a different route that both apps also call.

An allow-list is not a call. The Brain window's read allow-list
(jarvis-desktop/src-tauri/src/brain/routes.rs, READ_ROUTES) names every
route that window MAY read, by a section name. An entry counts as a call only
when a desktop window that calls `brain_read` asks for that section name.
Entries no window asks for are printed on their own, and are not counted.
The rest of that file (its tests list write routes) is not read at all.

It used to read the desktop from a separate branch (claude/jarvis-desktop-
tauri-vey6bc, last touched 19 Sep) and only its Rust, so it checked a desktop
that no longer existed, missed every route the JavaScript calls, and still
called the model routes out of scope after the owner allowed them on the
phone (18 and 20 Sep).

Failures - each one means a decision is missing or has gone stale:

  1. The desktop calls a route that is not classified below.
  2. A route classified `ported` is not called by the phone.
  3. A route classified `deliberate` (kept OFF the phone) IS called by the
     phone. Either a rule was broken or the decision changed; say which.
  4. A classified route the desktop no longer calls.

  5. The phone calls a route the desktop does not, and PHONE_ONLY below does
     not classify it. Parity runs both ways.
  6. A route in PHONE_ONLY that the phone no longer calls, or that the
     desktop now calls too (move it to CLASSIFICATION).

A route marked `todo` that the phone has started calling is a warning, not
a failure: it means "reclassify as ported", which is good news.

A route marked `planned` is built on the backend and neither app calls it
yet (the backend is written first, then each app builds against it). It is
exempt from rule 4. The moment the desktop calls it, a warning says to
reclassify it (`ported` once the phone calls it too, else `todo`).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP_DIRS = [
    ("jarvis-desktop/src-tauri/src", (".rs",)),
    ("jarvis-desktop/src", (".js", ".mjs", ".html")),
]
PHONE_DIRS = [("jarvis-client/app/src/main/java", (".kt",))]

# One path segment: a literal word, or a placeholder for an id - Rust's
# `{encoded}` / `{}`, JavaScript's `${...}`, Kotlin's `$encodedId` / `${...}`.
# The first segment after /api/ must be literal: `/api/{endpoint}` names no
# route this tool can classify (commands.rs builds /api/approve and /api/deny
# that way; both are also written out in full elsewhere).
_LIT = r"[A-Za-z0-9_-]+"
_PH = r"(?:\$\{[^}\n]*\}|\{[^}/\"\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*)"
ROUTE = re.compile(rf"/api/{_LIT}(?:/(?:{_LIT}|{_PH}))*/?")
_IS_PH = re.compile(rf"^{_PH}$")

# Allow-lists: files whose routes are a list of what a window MAY read, not
# calls. {file: (the constant holding the list, the command that reads it)}.
ALLOWLISTS = {
    "jarvis-desktop/src-tauri/src/brain/routes.rs": ("READ_ROUTES", "brain_read"),
}

# Every route the desktop calls, and what the phone does about it.
#
# "ported"       - the phone calls it too; checked
# "deliberate"   - a decision was made NOT to port it; the reason is the
#                  point, and the phone calling it is a failure
# "todo"         - portable and wanted, nobody has done it yet
# "not-backend"  - not a Jarvis route at all: the desktop calls Ollama's own
#                  API on loopback under the same /api/ prefix
# "planned"      - on the backend, for both apps, and neither calls it yet
CLASSIFICATION = {
    "/api/appearance": ("ported", ""),
    "/api/big-model": ("ported", "The big model (slow) with colibri: what was found and its three switches, each ON an approval card (backend/big-model.patch, 2026-09-24). Desktop: Settings, Big model (slow) (get_big_model / set_big_model, settings window only). Phone: Mind, Big model (slow) (BigModelPlate.kt)."),
    "/api/deep": ("ported", "Deep questions and their answers, newest first (backend/big-model.patch). Desktop: the Brain's Memory tab, Deep questions (get_deep). Phone: Mind, Deep questions. Both read it again on the `deep` event."),
    "/api/deep/ask": ("ported", "Queue one deep question for the big model; no card per question, the switch was approved (backend/big-model.patch). Desktop: the Brain's \"Ask slowly\" (ask_deep). Phone: Mind's \"Ask slowly\". Both hold it on a stale link."),
    "/api/approve": ("ported", ""),
    "/api/attention": ("ported", ""),
    "/api/attention/mute": ("ported", ""),
    "/api/attention/unmute": ("ported", ""),
    "/api/chat": ("ported", ""),
    "/api/compute": ("ported", "Brain screen, read-only."),
    # /api/config is NOT here: it is only in the Brain's read allow-list
    # (brain/routes.rs, section "config") and no window asks for it, so the
    # desktop does not call it. If the phone ever calls it, rule 5 fails -
    # and it should stay off: deep config editing on the phone is out of
    # scope (CLAUDE.md).
    "/api/content-risk": ("ported", "Brain screen, read-only."),
    "/api/deny": ("ported", ""),
    "/api/digest": ("ported", ""),
    "/api/digest/seen": ("ported", ""),
    "/api/events": ("ported", ""),
    "/api/feedback/mark": ("ported", ""),
    "/api/graph": ("deliberate", "The memory graph is explicitly out of scope on the phone (CLAUDE.md)."),
    # Chat history kept on the PC (backend/chat-history.patch, 2026-09-24):
    # built on the backend first; both apps are to build against
    # docs/JARVIS-API.md section 18.
    "/api/history": ("planned", "Chat history: the conversations this PC has kept, newest first, with the switch's state and why nothing is being kept when it is not (docs/JARVIS-API.md section 18). Desktop: the Brain window's History section. Phone: a History screen next to Mind's other sections."),
    "/api/history/conversation": ("planned", "One kept conversation, read-only, with where each of your messages came from."),
    "/api/history/delete": ("planned", "Delete one conversation, after a confirm step. There is no delete-all."),
    "/api/history/settings": ("planned", "\"Keep chat history on this PC\": OFF is immediate; ON raises one approval card (history_enable) and both apps say \"Waiting for your approval\" while it waits. Also how long to keep conversations."),
    "/api/holds/cancel": ("ported", ""),
    "/api/initiative": ("ported", "Brain screen, read-only."),
    "/api/jobs": ("ported", ""),
    "/api/jobs/cancel": ("ported", ""),
    "/api/ledger": ("ported", "Brain screen, read-only."),
    "/api/memory/decide": ("ported", "The review queue: one card, one decision."),
    "/api/memory/edit": ("deliberate", "Rewording stored facts is deep memory editing; it stays on the desktop's Memory tab."),
    "/api/memory/export": ("deliberate", "A copy of everything Jarvis knows does not belong on a phone that can be lost."),
    "/api/memory/facts": ("ported", ""),
    "/api/memory/forget": ("deliberate", "Deep memory editing; it stays on the desktop's Memory tab."),
    "/api/memory/keep_both": ("ported", ""),
    "/api/memory/learning": ("ported", "The learning on/off switch on Mind (MemoryCountsSection). Turning learning ON raises an approval card on the PC (learning-asks.patch, 2026-09-24): the phone says \"waiting\" while a learning_enable card is in the queue, and holds ON on a stale link; OFF is immediate."),
    "/api/memory/pending": ("ported", "The review queue."),
    "/api/memory/sleep_time": ("ported", ""),
    "/api/memory/status": ("ported", "Memory counts and whether search-by-meaning is on, read-only, in the desktop Memory pane's words. Phone: Mind, What Jarvis remembers (MemoryCountsPlate.kt, net/MemoryCounts.kt)."),
    "/api/models": ("ported", "Allowed by the owner 2026-09-18: the installed list, not a catalogue."),
    "/api/models/install": ("ported", "Allowed by the owner 2026-09-20: a typed name, raising an approval card."),
    "/api/models/rollback": ("ported", ""),
    "/api/models/switch": ("ported", "Allowed by the owner 2026-09-18, raising an approval card."),
    "/api/notes/capture": ("ported", ""),
    "/api/pending": ("ported", ""),
    "/api/pending/{id}/amend": ("ported", "A note on one waiting approval card; approves nothing (backend/task-control.patch). Desktop: amend_approval (commands.rs). Phone: JarvisApi.amend."),
    "/api/power": ("ported", ""),
    "/api/second-card": ("ported", "The second graphics card's switches (backend/second-card.patch, 2026-09-24). Desktop: Settings, Second graphics card (vision.rs reads it for pictures). Phone: Mind screen's Second graphics card plate, and chat's photo button. What was found plus one switch at a time; each ON is an approval card."),
    "/api/retrieve": ("todo", "The HUD's retrieval trace (which facts an answer reached for). Not in JARVIS-API.md yet; decide what it should show before porting."),
    "/api/show": ("not-backend", "Ollama's /api/show on loopback: does the model take pictures (vision.rs)."),
    "/api/shutdown": ("deliberate", "Shutting the backend down from a phone is a foot-gun: the phone would then have nothing to reach and no way to undo it."),
    "/api/skills": ("ported", "Brain screen, read-only."),
    "/api/skills/decide": ("ported", "Removing a skill, after an are-you-sure, as on the desktop (Brain, Faculties, Skills). Phone: Mind, Skills (SkillsPlate.kt, net/Skills.kt). Never held on a stale link; a card the PC raises is shown as waiting. Removal only - no app can install a skill."),
    "/api/status": ("ported", ""),
    "/api/tags": ("not-backend", "Ollama's /api/tags on loopback: the installed model list (commands.rs). Not a Jarvis route."),
    "/api/task/note": ("ported", ""),
    "/api/task/pause": ("ported", ""),
    "/api/task/resume": ("ported", ""),
    "/api/task/stop": ("ported", ""),
    "/api/undo": ("ported", ""),
    "/api/undo/revert": ("ported", ""),
    "/api/version": ("ported", "The handshake. Both apps also list its capabilities by name: desktop Settings, \"What this backend supports\" (its own card, after About) (get_backend_capabilities); phone, \"This backend\"."),
    "/api/visual-spec": ("deliberate", "The phone bundles its own copy of the spec and checks it in a unit test (SpecDriftTest); JARVIS-API.md: the phone never fetches it."),
    "/api/voice/say": ("ported", ""),
    "/api/voice/status": ("ported", "What the PC's voice can do. Desktop: \"hey Jarvis\" listening reads it (voice.rs), and Settings, Voice shows it, with training, how strict, private answers and the guided test drawn from it (get_voice_status, voice-panel.js). Phone: Platform checks, Your voice and the wake-word card."),
    "/api/voice/enroll": ("ported", "\"Train my voice\" (backend/voice-enroll.patch) and, since 2026-09-24, its other modes (docs/JARVIS-API.md section 16): training in rounds, strictness, private answers, the guided test. Desktop: Settings, Voice, for this PC's microphone (mic=desktop; voice_training.rs send_voice_training, set_voice_setting, measure_voice, cancel_voice_training). Phone: Train my voice (JarvisApi.enrollVoice and the calibrate / threshold modes)."),
    "/api/voice/turn": ("deliberate", "Smart Turn, 'finished or only paused?'. The phone runs the same model "
                        "itself (assets/turn/, voice/SmartTurn.kt), so its audio never leaves it to ask; "
                        "the desktop asks its own PC over loopback."),
    "/api/voice/utterance": ("ported", ""),
    # Custom voices (backend/voices.patch, 2026-09-24): built on the backend
    # first (docs/JARVIS-API.md section 15). Both apps call all five since
    # 2026-09-24: desktop Settings, Jarvis's voice (voice_training.rs,
    # voice-panel.js); phone Platform checks -> Jarvis's voice
    # (ui/screens/VoicesScreen.kt, net/CustomVoices.kt).
    "/api/voice/voices": ("ported", "Custom voices: the list, which one Jarvis speaks in and why the built-in voice is used instead, the better voice's state, and say() timings (docs/JARVIS-API.md section 15). Desktop: Settings, Jarvis's voice (get_custom_voices). Phone: Platform checks, Jarvis's voice (VoicesScreen.kt), re-read on the `voices` event."),
    "/api/voice/voices/create": ("ported", "Add a custom voice: a recording and its exact words. One approval card (custom_voice); a voice that sounds like the owner's is refused. Desktop: create_custom_voice (the sentence shown, or a WAV file and typed words). Phone: record a sentence it shows (the words are that sentence - no speech-to-text) or pick a WAV and type its words; held on a stale link."),
    "/api/voice/voices/active": ("ported", "Speak in a custom voice (one approval card) or back in the built-in one (immediate). Desktop: set_active_voice. Phone: the custom voice is held on a stale link, the built-in one always goes."),
    "/api/voice/voices/delete": ("ported", "Delete a custom voice. Immediate; the built-in voice comes back if it was the one in use. Desktop: delete_custom_voice, after an are-you-sure. Phone: asks first on the phone, never held."),
    "/api/voice/voices/better": ("ported", "The better voice (F5-TTS on the second graphics card): ON is one approval card (better_voice_enable), OFF is immediate. Desktop: set_better_voice, offered only with a capable second card. Phone: offered only when a capable second card is there; ON held on a stale link, OFF always goes."),
    # The voice flow (backend/voice-flow.patch, 2026-09-24): built on the
    # backend, for both apps. Its other two parts are on routes both apps
    # already call - `?source=barge_in` / `&waited_ms=` on /api/voice/utterance
    # and the `flow` block of /api/voice/status - so only this one is new.
    "/api/voice/moment": ("planned", "The \"One moment.\" clip, a WAV in the voice Jarvis speaks in now (made once per voice, kept in memory). An app plays it when no sound has started about a second after the owner finished, never over the reply (docs/JARVIS-API.md section 17)."),
    "/api/voice/wake": ("ported", "The wake-word switch; turning it on raises an approval card, turning it off is immediate. Both apps can do both: desktop Settings, Voice (set_wake_word; ON also from the Jarvis bar's listen button), phone Platform checks."),
    "/api/watch": ("ported", "Watches - the GitHub topics Jarvis keeps an eye on. Desktop: Brain, Watch tab. Phone: Mind, Watches (WatchPlate.kt, net/Watch.kt)."),
    "/api/watch/add": ("ported", "Watch a topic. The phone holds it on a stale link (it turns something on) and shows a card if the PC raises one."),
    "/api/watch/remove": ("ported", "Forget a topic, after a warning. Never held on a stale link."),
    "/api/watch/report": ("ported", "What is new - a peek that marks nothing read."),
    "/api/watch/seen": ("ported", "Mark these read - a POST on purpose, so opening a link cannot clear the list."),
    "/api/wiki": ("ported", "The wiki builder's documents and their state (backend/wiki.patch, 2026-09-24). Both apps list them; neither browses files or reads pages - the vault reaches the phone through Syncthing."),
    "/api/wiki/ingest": ("ported", "\"Add to wiki\" for one document, then its job. Raises one approval card (wiki_update); nothing is written before it is answered."),
}
STATUSES = {"ported", "deliberate", "todo", "not-backend", "planned"}

# Every route the PHONE calls that the desktop does not - parity the other way.
#
# "phone-only"    - kept off the desktop on purpose; the reason is the point
# "desktop-todo"  - the desktop should have it too, and nobody has built it
PHONE_ONLY = {
}
PHONE_STATUSES = {"phone-only", "desktop-todo"}

_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_HTML = re.compile(r"<!--.*?-->", re.S)
# `//` at the start of a line, or after whitespace - never the `//` inside
# "http://", which has a colon before it.
_LINE = re.compile(r"(^|\s)//.*$", re.M)


def strip_comments(text: str, ext: str) -> str:
    if ext == ".html":
        text = _HTML.sub("", text)
    return _LINE.sub(r"\1", _BLOCK.sub("", text))


def normalise(route: str) -> str:
    """`/api/pending/$encodedId/amend` -> `/api/pending/{id}/amend`."""
    segs = route.rstrip("/").split("/")
    return "/".join("{id}" if _IS_PH.match(seg) else seg for seg in segs)


def routes_in(text):
    return {normalise(m) for m in ROUTE.findall(text)}


_ENTRY = re.compile(r'\(\s*"([A-Za-z0-9_]+)"\s*,\s*"(/api/[^"?]+)')


def allowlist_entries(text: str, const: str):
    """(section, route) pairs from `const NAME: ... = &[ ... ];`."""
    m = re.search(rf"\b{const}\b[^=]*=\s*&\[(.*?)\];", text, re.S)
    if not m:
        return None
    return [(sec, normalise(route)) for sec, route in _ENTRY.findall(m.group(1))]


def scan(dirs, allow=None):
    """{route: {files}} for every call. With `allow` (a dict), allow-list
    files are not scanned for calls; their entries go into allow[file] as
    (section, route) pairs instead."""
    found = {}
    for rel, exts in dirs:
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            print(f"::error::{rel} is not in this checkout; has it moved?")
            sys.exit(2)
        for dirpath, _, names in os.walk(base):
            if "node_modules" in dirpath:
                continue
            for n in names:
                ext = os.path.splitext(n)[1]
                if ext not in exts:
                    continue
                path = os.path.join(dirpath, n)
                rel_path = os.path.relpath(path, ROOT).replace(os.sep, "/")
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = strip_comments(fh.read(), ext)
                if allow is not None and rel_path in ALLOWLISTS:
                    const = ALLOWLISTS[rel_path][0]
                    entries = allowlist_entries(text, const)
                    if entries is None:
                        print(f"::error::{rel_path} has no {const} list any more; "
                              "update ALLOWLISTS in tools/check_parity.py.")
                        sys.exit(2)
                    allow[rel_path] = entries
                    continue
                for r in routes_in(text):
                    found.setdefault(r, set()).add(rel_path)
    return found


def sections_asked(command):
    """Every quoted word in a desktop window file that calls `command`."""
    words = set()
    for rel, _ in DESKTOP_DIRS:
        for dirpath, _, names in os.walk(os.path.join(ROOT, rel)):
            if "node_modules" in dirpath:
                continue
            for n in names:
                ext = os.path.splitext(n)[1]
                if ext not in (".js", ".mjs", ".html"):
                    continue
                with open(os.path.join(dirpath, n), encoding="utf-8", errors="replace") as fh:
                    text = strip_comments(fh.read(), ext)
                if command in text:
                    words |= set(re.findall(r"[\"']([A-Za-z0-9_]+)[\"']", text))
    return words


def apply_allowlists(found, allow):
    """Count the allow-list entries a window asks for as calls. Returns the
    (file, section, route) entries no window asks for."""
    unused = []
    for rel, entries in sorted(allow.items()):
        asked = sections_asked(ALLOWLISTS[rel][1])
        for sec, route in entries:
            if sec in asked:
                found.setdefault(route, set()).add(rel)
            else:
                unused.append((rel, sec, route))
    return unused


def main():
    allow = {}
    desk_at = scan(DESKTOP_DIRS, allow)
    unused_allow = apply_allowlists(desk_at, allow)
    phone_at = scan(PHONE_DIRS)
    desk, phone = set(desk_at), set(phone_at)
    problems, warnings = [], []

    for r, (s, _) in CLASSIFICATION.items():
        if s not in STATUSES:
            problems.append(f"{r} has an unknown status {s!r}.")
    for r, (s, _) in PHONE_ONLY.items():
        if s not in PHONE_STATUSES:
            problems.append(f"{r} has an unknown phone-only status {s!r}.")
        if r in CLASSIFICATION:
            problems.append(f"{r} is in both CLASSIFICATION and PHONE_ONLY; keep one.")

    for r in sorted(desk - set(CLASSIFICATION)):
        problems.append(
            f"{r} is called by the desktop ({', '.join(sorted(desk_at[r]))}) and is not "
            "classified in tools/check_parity.py. Someone added a feature; decide whether "
            "the phone should have it.")

    by = lambda st: {r for r, (s, _) in CLASSIFICATION.items() if s == st}  # noqa: E731
    for r in sorted(by("ported") - phone):
        problems.append(
            f"{r} is classified 'ported' but the phone does not call it. "
            "The classification has drifted from the code.")
    for r in sorted(by("deliberate") & phone):
        problems.append(
            f"{r} is classified 'deliberate' (kept off the phone: {CLASSIFICATION[r][1]}) "
            f"but the phone calls it ({', '.join(sorted(phone_at[r]))}).")
    for r in sorted(by("todo") & phone):
        warnings.append(f"{r} is 'todo' but the phone now calls it - reclassify it as 'ported'.")
    for r in sorted(by("planned") & desk):
        warnings.append(f"{r} is 'planned' but the desktop now calls it - reclassify it as "
                        f"'ported' (if the phone calls it too) or 'todo'.")
    for r in sorted(by("planned") & phone - desk):
        warnings.append(f"{r} is 'planned' and the phone calls it; the desktop does not yet.")
    for r in sorted(set(CLASSIFICATION) - desk - by("planned")):
        problems.append(
            f"{r} is classified here but the desktop no longer calls it. "
            "Remove it, or find out where it went.")

    for r in sorted(phone - desk - set(PHONE_ONLY) - set(CLASSIFICATION)):
        problems.append(
            f"{r} is called by the phone ({', '.join(sorted(phone_at[r]))}) and not by the "
            "desktop, and PHONE_ONLY in tools/check_parity.py does not classify it. Decide "
            "whether the desktop should have it.")
    for r in sorted(set(PHONE_ONLY) - phone):
        problems.append(
            f"{r} is in PHONE_ONLY but the phone no longer calls it. "
            "Remove it, or find out where it went.")
    for r in sorted(set(PHONE_ONLY) & desk):
        problems.append(
            f"{r} is in PHONE_ONLY but the desktop calls it now "
            f"({', '.join(sorted(desk_at[r]))}). Move it to CLASSIFICATION.")

    todo, no = sorted(by("todo")), sorted(by("deliberate"))
    print(f"desktop: {len(desk)} routes   phone: {len(phone)}   "
          f"ported: {len(by('ported'))}   not porting: {len(no)}   still to port: {len(todo)}   "
          f"not the backend's: {len(by('not-backend'))}   "
          f"planned (backend first): {len(by('planned'))}")
    if todo:
        print("\nStill to port:")
        for r in todo:
            print(f"  {r:<26} {CLASSIFICATION[r][1]}")
    ahead = sorted(phone - desk)
    if ahead:
        print("\nOn the phone and not the desktop (parity runs both ways):")
        for r in ahead:
            st, why = PHONE_ONLY.get(r, ("UNCLASSIFIED", ""))
            print(f"  {r:<26} {st}: {why}" if why else f"  {r:<26} {st}")
    if unused_allow:
        print("\nIn an allow-list, asked for by no window (not counted as calls):")
        for rel, sec, route in unused_allow:
            print(f"  {route:<26} section {sec!r} in {rel}")
    for w in warnings:
        print(f"::warning::{w}")
    if problems:
        print("\n" + "=" * 60)
        for p in problems:
            print(f"::error::{p}")
        return 1
    print("\nNo undecided drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
