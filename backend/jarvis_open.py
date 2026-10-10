"""jarvis_open.py - "open Notion", "open settings", "open Jarvis settings":
opening a program or a Windows panel from the owner's own words.

NEW MODULE, shipped whole (no patch of its own). jarvis_quick.py (already
SHIPPED) is the only importer: its grammar has the sentence, and this file
answers WHICH thing was named and how sure it is.

THE OWNER'S REQUEST (2026-10-10, his own words)
    "can it control parts of my pc like if i ask open notion, or open
    settings, or open jarvis settings. it should be able to do all of that."

THE PRECEDENT THIS IS BUILT ON, WORD FOR WORD
CLAUDE.md, 2026-09-27: "Music/video control on the PC: no card, only from
the owner's own words." jarvis_media.py (already SHIPPED) is that feature,
and this file is the same shape for the same reason:

  * NO CARD. Opening a program the owner already has is not a change to
    anything Jarvis holds - no memory, no file, no setting, no account -
    and it is the owner's own sentence, not something Jarvis decided. A
    card here would be asking the owner to confirm what he just said.
  * NO MODEL TOOL, and no route of its own. Nothing in jarvis_agent.py's
    tool loop mentions this file, so the AI model cannot open anything on
    its own initiative and outside text (a web page, an email, a note) has
    nothing to steer. `/api/chat` reaches this only through the fast path
    below, which sees the owner's typed or spoken words and nothing else.
  * It never imports jarvis_gate, so there is no action name to give a
    tier to and nothing here can be made to ask.

WHAT "OPEN SETTINGS" MEANS, AND WHY (the disambiguation, said plainly)
There are two Settings on this PC and one phrase for both. The owner settled
which one the bare phrase means on 2026-10-10, answering question 1 of
docs/BARS-AND-SETTINGS-AUDIT-2026-10-10.md ("Flip it"): Jarvis is his own app,
so "open settings" in it means ITS settings, and Windows' own screen is named
in so many words.
  * "open settings", "open my settings" -> JARVIS's own Settings window, at
    the TOP (no section). This is the owner's decision, not an accident of
    wording, and the answer says so.
  * "open Jarvis settings" and the other explicit Jarvis words, or one of the
    registry's own section names ("open web search", "open voice settings"),
    -> the same window. Those section names are matched FIRST, by
    jarvis_quick.py's own `_settings_open`, so every phrase that already
    worked still lands where it did.
  * "open Windows settings" (or "open the windows settings app") ->
    WINDOWS Settings (`ms-settings:`). After the flip this is the only words
    that reach Windows' own screen, so it is matched EXPLICITLY, by
    `_WINDOWS_SAID` below, and never left to the app index - a Start-menu
    shortcut that happened to be called that must not steal it.
  * Every word that is BOTH a Windows panel and a Jarvis section (security,
    sound, camera, backup, ...) still opens the WINDOWS page by name and
    says, in the same answer, how to ask for the one inside Jarvis ("open
    Jarvis settings, sound"). That note was kept truthful through the flip:
    it used to send the owner to "open Jarvis settings" for the bare word,
    which is now the very thing he said.
  * Words that name neither -> Jarvis does NOT guess. They are treated as an
    app name, and the PC resolves that honestly or says it is not there.

WHAT IS NEVER DONE
No guessing. A name that matches nothing known is not "the nearest app":
the owner is told plainly that it was not found, and nothing is opened.
A name that matches two different panels is a question, not a coin toss.
Nothing is opened from inside this file at all - it resolves a name and
returns it; the app that heard the owner's words is what runs the program.

WHY THE APP ITSELF DOES THE OPENING
Both apps reach this the same way they reach every fast-path answer
(jarvis_quick.py). The phone cannot open a program on the PC, so it says so
in one plain sentence (`ON_PC` below is that sentence's shape). The desktop
gets `open_app` on X-Jarvis-Route and runs it in Rust, through the Windows
shell - the same way it already opens a link in the owner's browser
(commands.rs `open_with_shell`), and with no new Tauri command and no new
permission for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# --------------------------------------------------------------------------
#   What was named
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Opened:
    """One resolved thing to open.

    kind:
      "app"      - a program. `target` is its name (see `built`) or one of
                   `BUILT_IN`'s own values.
      "panel"    - a Windows panel. `target` is its `ms-settings:` address.
      "jarvis"   - Jarvis's own Settings window. `target` is a settings.html
                   section id, or "" for the top of the window.
      "other"    - a Windows shell target that is not an app or a panel:
                   File Explorer, the Control Panel. `target` is the command.
    built:
      True when `target` is already a program the shell can start by itself
      (a name from `BUILT_IN`, an explorer/control command), so the desktop
      does not have to look it up. False for an app named in the owner's own
      words, which the desktop resolves against this PC's own Start menu.
    note:
      One extra plain sentence to say after the answer, or "". Used by the
      phrase with two real readings ("open settings" and the panel words that
      are also Jarvis sections), to say which one was opened and how to ask
      for the other. Never an error and never a card: it is one answer either
      way, said plainly.
    """

    kind: str
    target: str
    built: bool
    said: str
    note: str = ""


#: Said after the bare "open settings" now that it means Jarvis's own window
#: (the owner's decision of 2026-10-10): which one it opened, and the one
#: phrase that reaches Windows' instead. Both readings stay one sentence away,
#: so nothing is guessed and nothing is hidden.
_JARVIS_NOTE = ('That is Jarvis\'s own settings window. Say "open Windows '
                'settings" for Windows\' own.')

#: The words that mean WINDOWS Settings since the flip - matched as the whole
#: phrase, before anything else, so the app index can never take them. Written
#: exactly as `_clean` leaves them (lower case, no leading article, trailing
#: "app"/"screen"/"window"/"settings" kind-noun peeled).
_WINDOWS_SAID = frozenset({"windows settings", "windows' settings"})


# --------------------------------------------------------------------------
#   Windows panels - a fixed list, so a panel is named or it is not
# --------------------------------------------------------------------------

#: Plain words -> the `ms-settings:` address Windows itself uses. Every one
#: of these is a fixed page in Windows Settings; the list is short on purpose
#: and a page not on it falls through to the app index (so "open sound"
#: reaches the sound panel, while "open sound recorder" reaches the app).
PANELS = {
    "windows settings": "ms-settings:",
    "settings": "ms-settings:",
    "display": "ms-settings:display",
    "screen": "ms-settings:display",
    "sound": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "volume": "ms-settings:sound",
    "microphone": "ms-settings:privacy-microphone",
    "mic": "ms-settings:privacy-microphone",
    "bluetooth": "ms-settings:bluetooth",
    "devices": "ms-settings:bluetooth",
    "printers": "ms-settings:printers",
    "printer": "ms-settings:printers",
    "network": "ms-settings:network",
    "wifi": "ms-settings:network-wifi",
    "wi-fi": "ms-settings:network-wifi",
    "ethernet": "ms-settings:network-ethernet",
    "vpn": "ms-settings:network-vpn",
    "airplane mode": "ms-settings:network-airplanemode",
    "mobile hotspot": "ms-settings:network-mobilehotspot",
    "battery": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep",
    "sleep": "ms-settings:powersleep",
    "storage": "ms-settings:storagesense",
    "apps": "ms-settings:appsfeatures",
    "installed apps": "ms-settings:appsfeatures",
    "default apps": "ms-settings:defaultapps",
    "startup apps": "ms-settings:startupapps",
    "windows update": "ms-settings:windowsupdate",
    "update": "ms-settings:windowsupdate",
    "updates": "ms-settings:windowsupdate",
    "security": "ms-settings:windowsdefender",
    "windows security": "ms-settings:windowsdefender",
    "privacy": "ms-settings:privacy",
    "location": "ms-settings:privacy-location",
    "camera": "ms-settings:privacy-webcam",
    "notifications": "ms-settings:notifications",
    "focus assist": "ms-settings:quiethours",
    "do not disturb": "ms-settings:quiethours",
    "date and time": "ms-settings:dateandtime",
    "time": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage",
    "region": "ms-settings:regionlanguage",
    "keyboard": "ms-settings:keyboard",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "accessibility": "ms-settings:easeofaccess",
    "ease of access": "ms-settings:easeofaccess",
    "accounts": "ms-settings:yourinfo",
    "my account": "ms-settings:yourinfo",
    "sign-in options": "ms-settings:signinoptions",
    "windows hello": "ms-settings:signinoptions",
    "backup": "ms-settings:backup",
    "recovery": "ms-settings:recovery",
    "about this pc": "ms-settings:about",
    "about my pc": "ms-settings:about",
    "system info": "ms-settings:about",
    "taskbar": "ms-settings:taskbar",
    "personalisation": "ms-settings:personalization",
    "personalization": "ms-settings:personalization",
    "themes": "ms-settings:themes",
    "background": "ms-settings:personalization-background",
    "clipboard": "ms-settings:clipboard",
    "multitasking": "ms-settings:multitasking",
}

#: The words that mean JARVIS's own Settings rather than Windows'. Since the
#: owner's decision of 2026-10-10, the bare "open settings" means Jarvis's too,
#: and `resolve` treats it as the default - it is not listed here because it is
#: matched before `PANELS` can claim it, not because it is less than the rest.
#: A section of Jarvis Settings named by its own name ("open voice settings")
#: is matched BEFORE this file is ever asked - jarvis_quick.py's
#: `_settings_open` runs first and hands it to jarvis_settings_registry.py.
JARVIS_SETTINGS = (
    "jarvis settings",
    "jarvis's settings",
    "my jarvis settings",
    "the jarvis settings",
    "jarvis setup",
    "jarvis's setup",
    "jarvis preferences",
    "jarvis's preferences",
    "settings for jarvis",
)

#: A shell target that is neither an app nor a panel: File Explorer and the
#: old Control Panel. Fixed commands, never a path from anywhere.
SHELL_TARGETS = {
    "file explorer": ("explorer.exe", True),
    "explorer": ("explorer.exe", True),
    "my files": ("explorer.exe", True),
    "my folders": ("explorer.exe", True),
    "my documents": ("explorer.exe", True),
    "my downloads": ("explorer.exe", True),
    "control panel": ("control.exe", True),
    "the control panel": ("control.exe", True),
    "task manager": ("taskmgr.exe", True),
    "recycle bin": ("shell:RecycleBinFolder", True),
    "trash": ("shell:RecycleBinFolder", True),
    "the recycle bin": ("shell:RecycleBinFolder", True),
}

#: Windows' own accessories, by the plain name the owner would say. The
#: value is the program the shell starts by itself; `built=True` for these,
#: so the desktop opens them without looking anything up. Deliberately only
#: the programs that ship with Windows: everything else is resolved against
#: THIS PC's own Start menu, so a name is never opened to the wrong thing.
BUILT_IN = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "the calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "microsoft paint": "mspaint.exe",
    "snipping tool": "ms-screenclip:",
    "screenshot tool": "ms-screenclip:",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "registry editor": "regedit.exe",
    "character map": "charmap.exe",
    "on-screen keyboard": "osk.exe",
    "magnifier": "magnify.exe",
    "sticky notes": "ms-stickynotes:",
    "clock": "ms-clock:",
    "weather": "msnweather:",
    "photos": "ms-photos:",
    "camera": "microsoft.windows.camera:",
    "media player": "mswindowsmusic:",
    "groove music": "mswindowsmusic:",
    "movies and tv": "mswindowsvideo:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
}

#: Words whose Windows panel and Jarvis Settings section share a NAME, so the
#: answer has to say which one it opened and how to ask for the other. Only
#: ever consulted for a word that is a panel: the panel is opened, and the
#: note names the other reading rather than hiding it. The bare word
#: "settings" is deliberately absent: after the owner's flip it is Jarvis's
#: own window and is matched before `PANELS` is consulted at all.
_AMBIGUOUS_SECTIONS = ("security", "notifications", "storage",
                       "accounts", "display", "language", "keyboard", "mouse",
                       "printer", "devices", "camera", "location", "backup",
                       "updates", "sound", "network", "privacy", "apps")


# --------------------------------------------------------------------------
#   The sentence
# --------------------------------------------------------------------------

_LEAD = re.compile(
    r"^(?:please\s+)?(?:jarvis[\s,]+)?(?:can\s+you\s+|could\s+you\s+|would\s+you\s+)?"
    r"(?:open|launch|start|run|fire\s+up|bring\s+up|pull\s+up)\s+(?:the\s+|my\s+|a\s+|an\s+)?(.+?)$"
)

#: "open an app called figma", "open the program named notion": the owner
#: naming the KIND before the name. Taken off so "figma" is looked up and not
#: "app called figma".
_CALLED = re.compile(r"^(?:app|application|program|tool)\s+"
                     r"(?:called|named|by\s+the\s+name)\s+(.+)$")

_TAIL = re.compile(
    r"(?:\s*,\s*)?(?:\s+(?:please|thanks|thank\s+you|for\s+me|now|"
    r"up|jarvis|real\s+quick|quickly))+$"
)

#: "the settings app/screen/window/page" and "the x program/app" are the
#: same request as "x"; the noun is the owner telling us what kind of thing
#: it is, never part of its name. Peels ONE trailing noun, in
#: `resolve` - after the whole phrase has been tried, so "display settings"
#: stays Display settings instead of becoming an app called "display".
#: `[^]*` is spelled out rather than `.` because the leading `\s+` is what
#: has to consume the space: `re.match` is used (not `re.sub`), so a name
#: that does NOT end in one of these words leaves the name alone instead of
#: being emptied by a zero-width match.
_KIND_NOUNS = re.compile(r"\s+(?:app|application|program|window|page|screen|panel|settings)$")


def _without_kind_noun(name: str) -> str:
    """`name` with one trailing kind-noun taken off, or `name` unchanged.

    `re.sub` cannot be used here: `_KIND_NOUNS` matches the empty string, so
    on a name that ends in none of those words it took the name apart -
    "display settings app" was left as "display settings app" and handed to
    the app index as a program name (caught by this file's own suite). A
    match that really consumed a noun is the only one that counts.
    """
    found = _KIND_NOUNS.search(name)
    if found is None:
        return name
    return name[:found.start()].strip()

#: `JARVIS_SETTINGS` in the case `parse` hands over (the sentence is lowered
#: before it is split, so this is what the lookup has to compare against).
_JARVIS_LOWER = frozenset(w.lower() for w in JARVIS_SETTINGS)


def _clean(what: str) -> str:
    """The name on its own: no lead-in, no politeness, no leading article."""
    got = (what or "").strip().strip("?.!,").strip()
    for _ in range(3):
        cut = _TAIL.sub("", got).strip()
        if cut == got:
            break
        got = cut
    if got.startswith("the "):
        got = got[4:].strip()
    return got


def parse(text: str) -> Optional[tuple]:
    """`(name, is_jarvis)` for an "open ..." sentence, or None.

    `is_jarvis` is True only when the owner said Jarvis's own Settings in so
    many words. `name` is the thing on its own, lower case, with the lead-in
    and the politeness taken off - NOT with a trailing "settings" removed,
    because for several of these that word is part of the name ("Windows
    settings", "display settings") and stripping it here would turn them
    into apps called "windows" and "display". `resolve` peels the trailing
    kind-noun off itself, after it has tried the whole phrase.
    """
    if not text:
        return None
    s = " ".join(str(text).lower().split())
    if not s or len(s) > 200 or "\n" in s:
        return None
    m = _LEAD.fullmatch(s)
    if not m:
        return None
    said = _clean(m.group(1))
    if not said:
        return None
    called = _CALLED.fullmatch(said)
    what = (called.group(1) if called else said).strip()
    if not what:
        return None
    if what in _JARVIS_LOWER:
        return (what, True)
    return (what, False)


# --------------------------------------------------------------------------
#   What to do with it
# --------------------------------------------------------------------------

def _applied(what: str) -> Opened:
    """An app by name - the desktop resolves it against this PC's Start menu.

    `built=False`: this file will not claim a program exists on a machine it
    cannot see. Windows' own accessories are named exactly (`BUILT_IN`), and
    anything else is looked up by the app that is really running on the PC.
    """
    return Opened("app", what, False, what)


def resolve(name: str, is_jarvis: bool = False) -> object:
    """What to open for `name`, or a `Choice` when Jarvis must not guess.

    Never returns None for a name that got past `parse`: "I do not know what
    that is" is a real answer, and it is `Opened("app", name, False, name)`
    with the desktop saying it could not find it - not a guess at the
    nearest thing.

    The whole phrase is tried FIRST ("open windows settings" is Windows
    Settings, not an app called "windows"), and only then is a trailing
    kind-noun taken off ("open the calculator app" is the calculator).
    """
    if is_jarvis:
        return Opened("jarvis", "", True, name)

    key = " ".join(name.split())

    # Jarvis's own Settings said any other way ("jarvis preferences"), and the
    # bare "open settings" itself - the owner's decision of 2026-10-10: in
    # Jarvis's own app that phrase means Jarvis's own window, at the top.
    if key == "settings" or key in _JARVIS_LOWER:
        return Opened("jarvis", "", True, key, _JARVIS_NOTE)

    # WINDOWS' own Settings, named in so many words - the only words that
    # reach it now. Matched explicitly and before `PANELS`, so a Start-menu
    # shortcut called "Windows Settings" cannot take the phrase away.
    if key in _WINDOWS_SAID:
        return Opened("panel", "ms-settings:", True, key)

    # The rest of the Windows panels, by their plain names - the whole phrase
    # first. A word that is BOTH a panel and a Jarvis section ("sound",
    # "security") opens the panel and says, in the same answer, how to ask for
    # the one inside Jarvis (`_other_reading`).
    panel = PANELS.get(key)
    if panel is not None:
        note = _other_reading(key) if key in _AMBIGUOUS_SECTIONS else ""
        return Opened("panel", panel, True, key, note)

    # A shell target that is not an app or a panel.
    target = SHELL_TARGETS.get(key)
    if target is not None:
        return Opened("other", target[0], True, key)

    # Windows' own accessories.
    program = BUILT_IN.get(key)
    if program is not None:
        return Opened("app", program, True, key)

    # "open the settings app" / "the display settings screen": take one
    # trailing kind-noun off and try all of the above again, in the same
    # order, so the bare "open settings" keeps meaning Jarvis's window here
    # too. Repeated at most twice, because a name can carry two of these
    # nouns ("the display settings app" is the Display page, not a program
    # called "display settings") - and a word that really is a panel's whole
    # name is found by the direct lookup above, before any of this runs.
    bare = ""
    for _ in range(2):
        peeled = _without_kind_noun(key)
        if not peeled or peeled == key:
            break
        bare = peeled
        if bare == "settings" or bare in _JARVIS_LOWER:
            return Opened("jarvis", "", True, bare, _JARVIS_NOTE)
        if bare in _WINDOWS_SAID:
            return Opened("panel", "ms-settings:", True, bare)
        panel = PANELS.get(bare)
        if panel is not None:
            note = _other_reading(bare) if bare in _AMBIGUOUS_SECTIONS else ""
            return Opened("panel", panel, True, bare, note)
        target = SHELL_TARGETS.get(bare)
        if target is not None:
            return Opened("other", target[0], True, bare)
        program = BUILT_IN.get(bare)
        if program is not None:
            return Opened("app", program, True, bare)
        key = bare

    # Anything else is an app by name, resolved on the PC itself - unless the
    # words name one of Jarvis's own Settings sections ("open web search",
    # "open the morning briefing"), which is navigation and not a program.
    # jarvis_quick.py's own `_settings_open` has already had its turn by the
    # time this is reached; this only catches the section names it did not
    # take (a trailing "settings" defeats its `find_section`, which compares
    # whole phrases).
    for candidate in (key, bare):
        section = _section_for(candidate)
        if section is not None:
            return Opened("jarvis", section, True, _section_name(section))

    return _applied(key)


def _section_for(words: str) -> Optional[str]:
    """The id of the Jarvis Settings section these words name, or None.

    Read from the one list of sections the apps already share
    (jarvis_settings_registry.SECTIONS), never from a second copy here - the
    same reason that module exists. A backend without it (an older install)
    simply has no section to name, and the words are treated as an app.
    """
    if not words:
        return None
    try:
        import jarvis_settings_registry as R
    except Exception:
        return None
    try:
        section = R.find_section(words)
    except Exception:
        return None
    return section.id if section is not None else None


def _other_reading(key: str) -> str:
    """The sentence that names the OTHER reading of an ambiguous word.

    "open sound" opens WINDOWS' sound page; this says so and says how to get
    the one inside Jarvis - which is the section jump "open Jarvis settings,
    sound", not the bare "open settings" that used to be meant here before
    the owner's flip of 2026-10-10. "open security" and every other word with
    two places says the same thing about its own two. No question mark and no
    button: the request was answered, not refused - the note is so the owner
    learns the other door rather than having to guess at it.
    """
    return (f'That is Windows\' own {key} page. Say "open Jarvis settings, {key}" '
            f'for the one inside Jarvis.')


def words(opened: Opened) -> str:
    """The one plain sentence for what is about to be opened.

    Says "on this PC" on purpose: the same answer goes to the phone, which
    cannot open a program on the PC, and its own line says so separately
    (`ON_PC`). A sentence that claimed "Opening Notion." on a phone that
    opened nothing would be a claim Jarvis cannot support.
    """
    if opened.kind == "jarvis":
        # `said` carries the section's own name when a section was named
        # ("Opening Web search in Jarvis settings on this PC."), and "" for
        # the whole window - the same shape jarvis_quick._run_settings_open
        # already uses, so a cut-off spoken answer still says where it went.
        # The bare word "settings" is the whole window, not a section, so it
        # is not repeated back at the owner ("Opening settings in Jarvis
        # settings" would say the same thing twice).
        if opened.said and opened.said != "settings" and not opened.said.startswith("jarvis"):
            return f"Opening {opened.said} in Jarvis settings on this PC."
        return "Opening Jarvis settings on this PC."
    if opened.kind == "panel":
        return f"Opening {_panel_name(opened)} on this PC."
    return f"Opening {opened.said} on this PC."


def _section_name(section_id: str) -> str:
    """What the owner calls a Jarvis Settings section, from the one list both
    apps share (jarvis_settings_registry.SECTIONS). The raw id is only ever
    the last resort, for an install whose registry does not know it."""
    try:
        import jarvis_settings_registry as R
        section = R.section_by_id(section_id)
        if section is not None and section.names:
            return section.names[0]
    except Exception:
        pass
    return section_id.replace("-", " ")


#: Jarvis's own name for a panel, so the answer reads as the screen the owner
#: asked for and not as its address.
_PANEL_NAMES = {
    "ms-settings:": "Windows Settings",
    "ms-settings:display": "Display settings",
    "ms-settings:sound": "Sound settings",
    "ms-settings:bluetooth": "Bluetooth and devices",
    "ms-settings:network": "Network settings",
    "ms-settings:network-wifi": "Wi-Fi settings",
    "ms-settings:windowsupdate": "Windows Update",
    "ms-settings:windowsdefender": "Windows Security",
    "ms-settings:appsfeatures": "Installed apps",
    "ms-settings:powersleep": "Power and sleep",
    "ms-settings:about": "About this PC",
    "ms-settings:yourinfo": "Your account",
    "ms-settings:signinoptions": "Sign-in options",
    "ms-settings:easeofaccess": "Accessibility",
    "ms-settings:notifications": "Notifications",
    "ms-settings:privacy": "Privacy",
    "ms-settings:privacy-webcam": "Camera privacy settings",
    "ms-settings:privacy-microphone": "Microphone privacy settings",
    "ms-settings:privacy-location": "Location privacy settings",
    "ms-settings:storagesense": "Storage settings",
    "ms-settings:backup": "Windows Backup",
    "ms-settings:recovery": "Recovery",
    "ms-settings:printers": "Printers and scanners",
    "ms-settings:network-ethernet": "Ethernet settings",
    "ms-settings:network-vpn": "VPN settings",
    "ms-settings:dateandtime": "Date and time",
    "ms-settings:regionlanguage": "Language and region",
    "ms-settings:keyboard": "Typing settings",
    "ms-settings:mousetouchpad": "Mouse settings",
    "ms-settings:defaultapps": "Default apps",
    "ms-settings:startupapps": "Startup apps",
    "ms-settings:taskbar": "Taskbar settings",
    "ms-settings:personalization": "Personalisation",
    "ms-settings:themes": "Themes",
    "ms-settings:batterysaver": "Battery settings",
    "ms-settings:clipboard": "Clipboard settings",
    "ms-settings:multitasking": "Multitasking",
    "ms-settings:quiethours": "Focus assist",
}


def _panel_name(opened: Opened) -> str:
    return _PANEL_NAMES.get(opened.target, "that settings page")


#: Said by an app that cannot open a program on the PC - the phone. One
#: sentence, its own shape, exactly like OpenPlace.ON_PC's for a setting that
#: lives only on the PC.
ON_PC = ("Opening programs and Windows panels happens on your PC, not on this "
         "phone. Ask Jarvis on your PC.")
