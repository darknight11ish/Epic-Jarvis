"""test_hud_fieldtest_answers.py - the four wrong answers the HUD field test of
2026-10-29 caught, held to this PC's real state.

    python3 backend/test_hud_fieldtest_answers.py

WHY THIS EXISTS. On 2026-10-29 the owner asked the HUD four things and got four
answers that were wrong about this PC:

  1. "can you connect my calendar and email" got the private-iCal card with the
     email half silently dropped, and "what about connecting to a gmail account
     or google calendar?" matched no fast path at all, so the 8B model answered
     that connecting Google Calendar "requires a refresh token ... tokens are
     managed in your browser's signed-in account; I cannot retrieve them from
     here ... generate an OAuth token, then share the resulting code with me".
     Every word of that is wrong - there IS a two-way Google setup
     (`jarvis_google_calendar.py`, the steps in docs/GOOGLE-CALENDAR-SETUP.md,
     the sign-in returning to a loopback listener on this PC) - and the last
     clause invites a SECRET INTO A CHAT. So the sentences that name a Google
     calendar/account or email are answered by `accounts_connect`, from fixed
     copy, and this suite holds that copy to the real paths and to the doc.
  2. "what's on my calendar" while nothing is connected said "Settings,
     Accounts, pick the private link or Google sign-in" - and there is no Google
     sign-in row in Settings at all. The read/write way is the command setup.
  3. "change your voice to Ashby" got a raw dump of every built-in voice id.
     Ashby and Clara are the two voices MADE FOR JARVIS, and the Voices screen
     already says why they are not listed and the one line that makes them.
  4. "what voice are you using" reached the model, which guessed.
  5. "how do I pair my phone" reached the model, which invented a procedure.
     Both apps have the real one: Settings, Devices on this PC ("Pair a phone"),
     and Settings, Devices on the phone ("Pair with your PC").

WHAT IT PROVES:

  * every sentence above is answered without the model, by the intent named;
  * every path the Google/email answer names is REAL - the three CLI commands
    are in docs/GOOGLE-CALENDAR-SETUP.md, that doc is `SETUP_DOC`'s own value,
    the loopback address is in the doc, and the two Settings places it names
    exist in the registry and on the page;
  * it never asks for a secret: no "share the ... code/token with me" wording,
    no "refresh token", no browser-session claim;
  * the Ashby answer is the picker's own `BLENDS_TO_MAKE` note through
    `settings_choice_bad` (the contract main already pins), and a blend this PC
    really OFFERS still goes through the same setter as before;
  * the voice answer is read from `jarvis_voices.speaker_view()`, not typed;
  * the pairing answer names both screens' own button words, checked against
    the two source files;
  * all four answers change nothing (read-only intents, no card, no menu, no
    facts) and only navigate Settings where that is what the answer says;
  * `jarvis-desktop/src/settings.html` no longer says the HUD always stays dark.

No network, no model, no calendar read, no Credential Manager. The suite names
its own OPENJARVIS_CONFIG_DIR / HOME, so it never reads the owner's real one.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-hud-fieldtest-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
(_TMP / "home").mkdir(parents=True, exist_ok=True)

#: A PC that already has a calendar configured must still run this suite: the
#: "not connected" copy is the default, and each other branch is exercised with
#: a stub below.
for _var in ("JARVIS_CALENDAR_ICS_SECRET_URL", "JARVIS_CALDAV_URL",
             "JARVIS_CALDAV_USER", "JARVIS_CALDAV_PASSWORD"):
    os.environ.pop(_var, None)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_calendar.py", "jarvis_google_calendar.py",
                "jarvis_kokoro.py", "jarvis_voices.py", "jarvis_settings_registry.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_google_calendar as G  # noqa: E402
import jarvis_kokoro as K  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_voices as JV  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class _Sched:
    """The fast path asks the scheduler two things: note that a command was
    understood, and (for anything not read-only) forget what "cancel that"
    would take back. Both are spies here - nothing is written."""

    def __init__(self):
        self.commands = []
        self.forgotten = []

    def mark_command(self, text):
        self.commands.append(text)

    def note_set(self, *a, **k):
        pass

    def forget_set(self, conversation):
        self.forgotten.append(conversation)


#: THE OWNER'S OWN SENTENCES (the HUD field test, 2026-10-29), plus the close
#: phrasings the same request arrives in.
GOOGLE_SAID = (
    "can you connect my calendar and email",
    "can you connect my calendar and my email",
    "what about connecting to a gmail account or google calendar?",
    "what about connecting a gmail account or google calendar",
    "connect my google calendar",
    "connect my email",
    "connect my gmail",
    "what about gmail?",
    "hook up my google calendar",
    "set up my gmail account",
    "how do I connect my google calendar",
)

#: What the answer MUST name, one entry per real path (2026-10-29): the Google
#: two-way setup and its doc, the private iCal card, GitHub's card, and email
#: as not built with its IMAP details in Settings, Accounts.
WANTED_PATHS = (
    "py -3 jarvis_google_calendar.py",
    "docs/GOOGLE-CALENDAR-SETUP.md",
    "loopback",
    "private iCal link",
    "connect my calendar",
    "GitHub",
    "connect GitHub",
    "not built yet",
    "IMAP",
    "Settings, Accounts",
)

#: The model's wrong answer and the shape of every invitation to paste a secret.
#: A chat is never where a token, an auth code or a password goes.
BAD_PHRASES = (
    "refresh token", "signed-in account", "browser's signed-in", "OAuth token",
    "share the", "share your", "share it with me", "send me", "give me the code",
    "paste it here", "type the code", "code with me", "token with me",
    "I cannot retrieve", "cannot retrieve them",
)


def _answer(text, sched=None, conversation=None):
    return Q.answer(text, sched=sched or _Sched(), conversation=conversation)


# ══════════════════════════════════════════════════════════════════════════
#   1. Google Calendar and email: the four real paths, and no secret in chat
# ══════════════════════════════════════════════════════════════════════════

def t_google_and_email_are_answered_with_the_real_paths():
    for said in GOOGLE_SAID:
        got = Q.match(said)
        check(f"{said!r} is the fast path's own answer",
              got is not None and got.name == "accounts_connect", got)
        r = _answer(said)
        check(f"... answered here, not by the model ({said!r})", r is not None, r)
        if r is None:
            continue
        check(f"... with the route naming this answer ({said!r})",
              r.intent == "accounts_connect", r.intent)
        for want in WANTED_PATHS:
            check(f"... it says {want!r}", want in r.reply, r.reply)
        for bad in BAD_PHRASES:
            check(f"... it never says {bad!r}", bad not in r.reply, r.reply)
        check("... it is the four numbered paths, not a page",
              len(r.reply) <= 1400, f"{len(r.reply)} characters")


def t_the_commands_and_the_doc_are_the_real_ones():
    """Every command in the answer is in the doc, the doc is the module's own
    SETUP_DOC, and the doc really is the loopback setup - not a promise."""
    reply = _answer("connect my google calendar").reply
    doc_path = REPO / str(getattr(G, "SETUP_DOC", ""))
    check("the answer names the module's own SETUP_DOC",
          doc_path.is_file() and str(G.SETUP_DOC) in reply, (G.SETUP_DOC, doc_path))
    check("the fallback path in jarvis_quick is the same file",
          Q.GOOGLE_SETUP_DOC_FALLBACK == str(G.SETUP_DOC), Q.GOOGLE_SETUP_DOC_FALLBACK)
    doc = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    # Each command, and the fragment of it the doc itself prints (the doc says
    # "<paste the client ID here>", so only the command's own words are fixed).
    for cmd, in_doc in ((Q.GOOGLE_SETUP_COMMANDS[0], "jarvis_google_calendar.py client"),
                        (Q.GOOGLE_SETUP_COMMANDS[1], "jarvis_google_calendar.py mode google"),
                        (Q.GOOGLE_SETUP_COMMANDS[2], "jarvis_google_calendar.py connect")):
        check(f"the doc really has {cmd!r}", in_doc in doc, in_doc)
        check(f"... and the answer really says {cmd!r}", cmd in reply, reply)
    check("the doc is the loopback sign-in, so no code is pasted anywhere",
          "127.0.0.1" in doc and "loopback" in doc)
    check("the doc never asks for a token or code in a chat",
          "share the" not in doc.lower() and "code with me" not in doc.lower())
    check("the answer's Settings jump is a section that exists",
          R.section_by_id("account-secrets") is not None and
          _answer("connect my email").open_settings == "account-secrets",
          _answer("connect my email").open_settings)


def t_the_lead_says_what_is_really_chosen():
    """The first sentence is read from `jarvis_google_calendar.mode()` - an
    owner who is already connected is told so, and one who is not is not told
    he is."""
    real = G.mode
    try:
        for chosen, want in (("google", "read/write way"),
                             ("ical", "read-only"),
                             ("off", "not connected")):
            G.mode = lambda c=chosen: c
            r = _answer("connect my google calendar")
            check(f"mode {chosen!r}: the answer says {want!r}",
                  r is not None and want in r.reply.split("\n")[0], r and r.reply)
    finally:
        G.mode = real


# ══════════════════════════════════════════════════════════════════════════
#   2. "Not connected yet" names only places that exist
# ══════════════════════════════════════════════════════════════════════════

def t_the_not_connected_answer_names_no_missing_settings_row():
    said = G.answer("what's on my calendar")
    check("a disconnected calendar says so", "not connected yet" in said.lower(), said)
    check("... it names Settings, Accounts", "Settings, Accounts" in said, said)
    check("... it says the private link is read-only", "read-only" in said, said)
    # The step main already had, and the PR dropped on 2026-10-29: pasting the
    # link is not enough - the read-only way has to be CHOSEN with this command.
    # Restored 2026-10-30; without it the owner follows the sentence and still
    # gets "not connected".
    check("... it gives the command that chooses the read-only way",
          "py -3 jarvis_google_calendar.py mode ical" in said, said)
    check("... and says the command runs in the backend folder",
          "in the backend folder" in said, said)
    check("... and it names the real read/write setup doc", G.SETUP_DOC in said, said)
    check("... it no longer names a 'Google sign-in' Settings row",
          "pick the private link or Google sign-in" not in said
          and "Accounts, pick" not in said, said)
    # The twin must say the same thing: the base is what an installer starts
    # from, so a fix in one half only is a fix that ships to nobody.
    for rel in ("backend/jarvis_google_calendar.py", "jarvis-backend/jarvis_google_calendar.py"):
        path = REPO / rel
        if not path.is_file():
            skip(f"{rel} is not in this tree")
            continue
        text = path.read_text(encoding="utf-8")
        check(f"{rel} drops the missing Settings row",
              "pick the private link or Google sign-in" not in text, rel)
        check(f"{rel} names the real setup doc instead",
              "the one-time Google" in text and "sign-in commands in" in text, rel)
        check(f"{rel} keeps the command that chooses the read-only way",
              "then run " in text
              and "mode ical` in the backend folder. For the " in text, rel)


# ══════════════════════════════════════════════════════════════════════════
#   3. "change your voice to Ashby" - not a raw list of voice ids
#      (the settings grammar's answer, not a second intent of its own)
# ══════════════════════════════════════════════════════════════════════════

def t_an_unoffered_ashby_says_how_to_make_it():
    """B3's contract, and it is the settings grammar's one.

    "change your voice to Ashby" is a value `voice_speaker` does not have, so
    the answer is main's `settings_choice_bad` + the picker's own
    `jarvis_kokoro.BLENDS_TO_MAKE` sentence. This is the ONE contract the HUD
    suite and `backend/test_settings_registry.py` both pin. The PR first added a
    second intent here (`voice_blend_help`) and it was removed on 2026-10-30:
    two answers for one sentence cannot both pass the required backend job, and
    the settings answer is the one the rest of the PC already uses.

    What it must NOT do is the field test's defect: dump every voice id.
    """
    real_view = JV.speaker_view

    def unmade_view():
        view = dict(real_view() or {})
        view["choices"] = [{"id": "af_bella", "label": "American (female) - Bella"}]
        view["note"] = K.BLENDS_TO_MAKE
        view["make_line"] = K.MAKE_LINE
        return view

    JV.speaker_view = unmade_view
    try:
        for said in ("change your voice to Ashby", "use the Ashby voice",
                     "switch to the Ashby voice", "set your voice to Ashby",
                     "change his voice to Ashby", "change your voice to Clara"):
            got = Q.match(said)
            check(f"{said!r} is the settings answer, not a list of ids",
                  got is not None and got.name == "settings_choice_bad"
                  and got.f.get("key") == "voice_speaker", got)
            r = _answer(said)
            check(f"... and it is answered, not the model ({said!r})", r is not None, r)
            if r is None:
                continue
            check(f"... it is the picker's own sentence, word for word ({said!r})",
                  r.reply == K.BLENDS_TO_MAKE, r.reply)
            for want in ("Ashby", "Clara", "not made yet", "Make Ashby and Clara",
                         "README.md"):
                check(f"... it says {want!r} ({said!r})", want in r.reply, r.reply)
            check(f"... and it is NOT the raw voice-id dump ({said!r})",
                  "Say one of:" not in r.reply and "af bella" not in r.reply, r.reply)
        # The names come from jarvis_kokoro.MIX, never typed again: every blend
        # the pack defines reaches this answer by its own `name`. A blend added
        # to MIX is covered here without this test naming it.
        for pid in K.MIX_IDS:
            name = str((K.MIX.get(pid) or {}).get("name") or "").strip()
            if not name:
                continue
            other = Q.match(f"change your voice to {name}")
            check(f"the pack's own name {name!r} reaches the same answer",
                  other is not None and other.name == "settings_choice_bad"
                  and other.f.get("key") == "voice_speaker", other)
            if other is not None:
                check(f"... with the picker's sentence for {name!r}",
                      Q._run_settings_choice_bad(other.f).reply == K.BLENDS_TO_MAKE,
                      Q._run_settings_choice_bad(other.f).reply)
    finally:
        JV.speaker_view = real_view


def t_a_made_ashby_still_changes_the_voice():
    """No regression: when the pack really offers Ashby, the sentence reaches
    the same setter it always did (cardless), and nothing here intercepts it."""
    ashby = next(k for k, row in K.MIX.items() if row.get("name") == "Ashby")
    clara = next(k for k, row in K.MIX.items() if row.get("name") == "Clara")
    real_view = JV.speaker_view

    def made_view():
        view = dict(real_view() or {})
        view["choices"] = [{"id": "af_bella", "label": "American (female) - Bella"},
                           {"id": ashby, "label": K.MIX[ashby]["label"]},
                           {"id": clara, "label": K.MIX[clara]["label"]}]
        return view

    JV.speaker_view = made_view
    try:
        for said, want in (("change your voice to Ashby", ashby),
                           ("use the Clara voice", clara)):
            got = Q.match(said)
            check(f"a made blend still reaches the setter ({said!r})",
                  got is not None
                  and got.name in ("settings_choice", "control_set")
                  and got.f.get("key") == "voice_speaker"
                  and got.f.get("value") == want, got)
            check(f"... and never the not-made-yet refusal ({said!r})",
                  got is None or got.name != "settings_choice_bad", got)
        bad = Q.match("change your voice to Nobody")
        check("an unknown voice still gets the real choices",
              bad is not None and bad.name == "settings_choice_bad", bad)
    finally:
        JV.speaker_view = real_view


# ══════════════════════════════════════════════════════════════════════════
#   4. "what voice are you using" - read from the PC, never guessed
# ══════════════════════════════════════════════════════════════════════════

def t_which_voice_speaks_is_read_from_the_pc():
    view = JV.speaker_view() or {}
    choice = str(view.get("choice") or "")
    name = choice if choice and choice != "custom" else JV.speaker_name()
    label = K.label_of(name) if name else ""
    for said in ("what voice are you using", "which voice are you using",
                 "what voice is that", "what's your voice",
                 "tell me what voice you're using"):
        got = Q.match(said)
        check(f"{said!r} is answered here, not by the model",
              got is not None and got.name == "voice_ask", got)
        r = _answer(said)
        check(f"... and the answer is not None ({said!r})", r is not None, r)
        if r is None:
            continue
        if label:
            check(f"... it names the voice the PC really uses ({said!r})",
                  label in r.reply, (label, r.reply))
        check(f"... it names where it is chosen ({said!r})",
              "Settings, Jarvis's voice" in r.reply, r.reply)
    # The near misses keep their own answer: a writing question is not this.
    for said in ("what voice should I use in my email", "what is a voice",
                 "change your voice louder"):
        got = Q.match(said)
        check(f"{said!r} is not the voice-status answer",
              got is None or got.name != "voice_ask", got)


# ══════════════════════════════════════════════════════════════════════════
#   5. "how do I pair my phone" - both screens, in their own words
# ══════════════════════════════════════════════════════════════════════════

def t_pairing_a_phone_names_both_screens():
    desktop = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    phone = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
             / "client" / "net" / "Devices.kt").read_text(encoding="utf-8")
    check("the PC's button really is called 'Pair a phone'",
          ">Pair a phone<" in desktop, "jarvis-desktop/src/settings.html")
    check("the phone's button really is called 'Pair with your PC'",
          'PAIR_BUTTON = "Pair with your PC"' in phone, "Devices.kt")
    for said in ("how do I pair my phone", "how do I pair my phone with Jarvis",
                 "how can I pair a phone", "how do I pair a new phone",
                 "how do I connect my phone to jarvis", "pair my phone",
                 "connect my phone"):
        got = Q.match(said)
        check(f"{said!r} is answered here, not by the model",
              got is not None and got.name == "pair_phone", got)
        r = _answer(said)
        check(f"... and it is answered ({said!r})", r is not None, r)
        if r is None:
            continue
        for want in ("Settings, Devices", "Pair a phone", "Pair with your PC",
                     "Tailscale", "NordVPN Meshnet"):
            check(f"... it says {want!r}", want in r.reply, r.reply)
        check("... it does not claim the phone is already paired",
              "already paired" not in r.reply.lower(), r.reply)
    # The phone's state question is not the how-to. Since 2026-10-31 (the
    # post-deploy audit) it has its own deterministic, read-only answer from
    # the paired-device store (`honest_state`, shape "phone_state"); it must
    # stay out of the pairing words. "ring my phone" keeps its own intent.
    got = Q.match("is my phone paired?")
    check("'is my phone paired?' is the phone-state answer now",
          got is not None and got.name == "honest_state", got)
    got = Q.match("ring my phone")
    check("'ring my phone' is not the pairing how-to",
          got is None or got.name != "pair_phone", got)


# ══════════════════════════════════════════════════════════════════════════
#   6. The Settings page no longer says the HUD stays dark
# ══════════════════════════════════════════════════════════════════════════

def t_the_settings_page_no_longer_says_the_hud_stays_dark():
    path = REPO / "jarvis-desktop" / "src" / "settings.html"
    if not path.is_file():
        skip("jarvis-desktop/src/settings.html is not in this tree")
        return
    text = path.read_text(encoding="utf-8")
    check("the stale 'The HUD always stays dark' line is gone",
          "HUD always" not in text and "always\n          stays dark" not in text,
          "settings.html")
    check("... and the Appearance note says the HUD follows the theme",
          "the HUD included" in text, "settings.html")
    # The HUD really did gain the app's colours: the claim above is checked
    # against the HUD's own words rather than trusted.
    hud = REPO / "jarvis-desktop" / "src" / "jarvis_hud.html"
    if hud.is_file():
        check("... which the HUD's own stylesheet agrees with",
              "follows Daylight and High Contrast" in hud.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════
#   7. All of it changes nothing
# ══════════════════════════════════════════════════════════════════════════

def t_they_change_nothing():
    for name in ("accounts_connect", "voice_ask", "pair_phone"):
        check(f"{name} is a read-only intent", name in Q.READ_ONLY_INTENTS, name)
    for said in ("connect my email", "change your voice to Ashby",
                 "what voice are you using", "how do I pair my phone"):
        sched = _Sched()
        r = _answer(said, sched=sched, conversation="c-fieldtest")
        check(f"{said!r} runs", r is not None, r)
        if r is None:
            continue
        check("... it creates nothing 'cancel that' could take back",
              not r.made, r.made)
        check("... it reads no stored facts", not r.facts, r.facts)
        check("... and it never clears the 'cancel that' record",
              sched.forgotten == [], sched.forgotten)
        check("... it is a private answer to a public question",
              r.private is False, r.private)
    # Exactly two of the four answers navigate Settings, and both say why in
    # the words.
    check("the email/Google answer opens the Accounts card",
          _answer("connect my email").open_settings == "account-secrets",
          _answer("connect my email").open_settings)
    check("the pairing answer opens the Devices card",
          _answer("how do I pair my phone").open_settings == "devices",
          _answer("how do I pair my phone").open_settings)
    check("the voice answers open nothing",
          _answer("what voice are you using").open_settings is None
          and _answer("change your voice to Ashby").open_settings is None)


def main():
    for fn in (t_google_and_email_are_answered_with_the_real_paths,
               t_the_commands_and_the_doc_are_the_real_ones,
               t_the_lead_says_what_is_really_chosen,
               t_the_not_connected_answer_names_no_missing_settings_row,
               t_an_unoffered_ashby_says_how_to_make_it,
               t_a_made_ashby_still_changes_the_voice,
               t_which_voice_speaks_is_read_from_the_pc,
               t_pairing_a_phone_names_both_screens,
               t_the_settings_page_no_longer_says_the_hud_stays_dark,
               t_they_change_nothing):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
