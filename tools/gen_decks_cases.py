#!/usr/bin/env python3
"""Writes the review-decks and Spanish-practice contract both apps read
(docs/QUIZ-DECKS-DESIGN.md "Slice contract (frozen)", JARVIS-API section 102):

    jarvis-desktop/tests/fixtures/decks-cases.json
    jarvis-client/app/src/test/resources/contract/decks-cases.json

    python3 tools/gen_decks_cases.py            # write both
    python3 tools/gen_decks_cases.py --check    # compare only

ONE source for:
  * the words both apps show, word for word (the desktop's decks.js and quiz.js,
    the phone's Decks.kt and Quiz.kt are held to them by decks.mjs, quiz.mjs,
    DecksTest.kt and QuizTest.kt);
  * the words that come from the PC itself, taken from the backend modules, not
    typed again: the "Answer key written by the model" label, the Spanish crisis
    notice, the four ratings;
  * worked examples of the small rules (how a day, a card count and the "next
    cards ready" line are said; which deck rows may start a review; whether the
    "why per-deck counts can add up to more" note shows) that both apps run;
  * sample replies of the frozen shapes (C2 and C4).

This file replaced the hand-written tests/fixtures/decks-words.json (2026-09-30,
the decks audit): the phone's tests used to assert the same words by hand, so
the two apps could drift without a test noticing. Every key of that file is
kept here.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def _const(module: str, name: str):
    """A module-level constant of a backend file, read from its source (not
    imported: importing jarvis_decks pulls in the scheduler and `cryptography`,
    which not every machine that checks this file has)."""
    tree = ast.parse((BACKEND / module).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                 for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{module} has no constant {name}")



DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "decks-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "decks-cases.json")
COPIES = (DESKTOP, PHONE)

ABOUT = ("The shared words of Review decks and Spanish practice (docs/QUIZ-DECKS-DESIGN.md, "
         "Slice contract C5), word for word, plus worked examples of the small rules and the "
         "frozen reply shapes of C2 and C4. Written by tools/gen_decks_cases.py: both apps' "
         "tests (src/decks.js, src/quiz.js, Decks.kt, Quiz.kt) read this file.")

#: The one sentence the apps say when the local model did not answer (the
#: backend's own class says the same thing with "in a way Jarvis could use").
MODEL_UNAVAILABLE = "The model on this PC did not answer. Nothing was changed - try again in a moment."

#: Shown under the deck list when the decks' own "ready" counts add up to more than
#: the total: the day's new cards are shared by every deck (JARVIS-API 102.3), and
#: each deck's row counts what it alone would offer.
PER_DECK_NOTE = ("New cards a day is shared by every deck, so the decks can show more cards "
                 "ready than the total above.")

WORDS = {'section_title': 'My study decks',
 'mode_text': 'Text',
 'mode_spanish': 'Spanish practice',
 'level_heading': 'Level (roughly)',
 'level_label_b1': 'Level B1 (roughly)',
 'exercise_translate': 'Translate',
 'exercise_blank': 'Fill the blank',
 'exercise_complete': 'Finish the sentence',
 'exercise_mixed': 'Mixed',
 'topic_label': 'Topic (optional)',
 'topic_counter': '0 / 60',
 'spanish_placeholder': 'Paste Spanish text (optional)',
 'start_button': 'Write questions',
 'kind_translate': 'Translate',
 'kind_blank': 'Fill the blank',
 'kind_complete': 'Finish the sentence',
 'answer_line_example': 'Answer: está',
 'passage_from_text': 'From the text',
 'passage_example': 'Example sentence',
 'keep_button': 'Keep these questions',
 'keep_finish': 'Keep and finish',
 'keep_cancel': 'Cancel',
 'keep_back_placeholder': 'Type the answer in your own words',
 'kept_many': 'Kept 3 questions',
 'kept_one': 'Kept 1 question',
 'new_deck': 'New deck',
 'deck_name': 'Deck name',
 'choose_deck': 'Choose a deck',
 'keep_hidden': 'Turn off Hide memory lists to keep questions',
 'cards_ready': 'Cards ready',
 'nothing_ready': 'Nothing ready today',
 'new_per_day': 'New cards a day',
 'review': 'Review',
 'pause': 'Pause',
 'resume': 'Resume',
 'delete_deck': 'Delete this deck',
 'delete_card': 'Delete this card',
 'edit': 'Edit',
 'save': 'Save',
 'cards_link': 'Cards',
 'cards_many': '8 cards',
 'cards_one': '1 card',
 'ready_row': '3 ready',
 'delete_confirm': 'Are you sure? Deleting is immediate. Copies in older backups stay until '
                   'they age out.',
 'delete': 'Delete',
 'empty_state': 'Keep questions from a quiz to make your first deck.',
 'review_hidden': 'Turn off Hide memory lists to review',
 'show_answer': 'Show answer',
 'typed_placeholder': 'Type your answer (only for you - it is not sent or marked)',
 'rating_again': "Didn't remember",
 'rating_hard': 'Remembered, with effort',
 'rating_good': 'Remembered',
 'rating_easy': 'Easy',
 'enough': "That's enough for now",
 'more': 'Do 10 more',
 'stop': 'Stop',
 'back_answer': 'Answer',
 'key_label_model': 'Answer key written by the model',
 'guess_label': "Jarvis's guess"}

WORDS.update({
    # the intros, changed 2026-09-30: Keep now saves, so "Nothing is saved" is no longer true
    "quiz_intro": ("Paste some text and Jarvis writes a few questions about it. Your answers are "
                   "marked by the model on this PC. Nothing is saved unless you choose Keep, "
                   "nothing is learned, and nothing leaves this PC."),
    "spanish_intro": ("Type your answers in Spanish. Paste some Spanish text of your own and the "
                      "questions come from it, or leave the box empty and Jarvis writes the "
                      "sentences. Nothing is saved unless you choose Keep, nothing is learned, "
                      "and nothing leaves this PC."),
    "model_unavailable": MODEL_UNAVAILABLE,
    "accent_row_label": "Spanish letters",
    "review_all": "Review all decks",
    "per_deck_note": PER_DECK_NOTE,
})

# Words the PC itself sends: taken from the backend, never typed a second time.
PC_WORDS = {
    "key_label_model": _const("jarvis_decks.py", "KEY_LABEL"),
    "spanish_notice": _const("jarvis_quiz.py", "SPANISH_NOTICE"),
}

WORDS["key_label_model"] = PC_WORDS["key_label_model"]   # one source: the backend's own label

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_day(day):
    if not (isinstance(day, str) and len(day) == 10 and day[4] == "-" and day[7] == "-"):
        return "" if day is None else str(day)
    y, m, d = day.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def next_ready_line(day):
    return f"Next cards ready on {format_day(day)}" if day else ""


def cards_label(n):
    return "1 card" if n == 1 else f"{n} cards"


def kept_line(n):
    return f"Kept {n} {'question' if n == 1 else 'questions'}"


def can_review(deck, available=True, hidden=False):
    """Review is offered for a deck that is ready and not paused (never while the
    private lists are hidden or the store cannot be opened)."""
    return bool(available and not hidden and not deck["paused"] and deck["ready"] > 0)


def can_review_all(ready, available=True, hidden=False):
    return bool(available and not hidden and ready > 0)


def per_deck_note_shown(decks, total):
    return sum(d["ready"] for d in decks) > total


def examples():
    days = ["2026-10-03", "2027-01-31", "2026-12-25", None, "", "soon"]
    decks = [
        {"name": "ready", "cards": 8, "ready": 3, "paused": False},
        {"name": "none ready", "cards": 8, "ready": 0, "paused": False},
        {"name": "paused with cards ready", "cards": 8, "ready": 3, "paused": True},
        {"name": "empty", "cards": 0, "ready": 0, "paused": False},
    ]
    return {
        "format_day": [[d, format_day(d)] for d in days],
        "next_ready_line": [[d, next_ready_line(d)] for d in days],
        "cards_label": [[n, cards_label(n)] for n in (0, 1, 2, 8, 1000)],
        "kept_line": [[n, kept_line(n)] for n in (1, 2, 3, 20)],
        # [deck, available, hidden, may start a review]
        "can_review": [[d, a, h, can_review(d, a, h)]
                       for d in decks for a, h in ((True, False), (True, True), (False, False))],
        # [total ready, available, hidden, may start "Review all decks"]
        "can_review_all": [[r, a, h, can_review_all(r, a, h)]
                           for r in (0, 1, 7) for a, h in ((True, False), (True, True), (False, False))],
        # [each deck's ready, the total, whether the note shows]
        "per_deck_note": [[r, t, per_deck_note_shown([{"ready": x} for x in r], t)]
                          for r, t in (([3, 2], 5), ([3, 3], 5), ([3, 3], 3), ([], 0), ([5], 5), ([0, 0], 0))],
    }


SAMPLES = {'decks': {'ok': True,
           'available': True,
           'why': '',
           'decks': [{'id': 'd1a2b3c4d5e6',
                      'name': 'Plants',
                      'cards': 8,
                      'ready': 3,
                      'paused': False,
                      'kind': 'study'},
                     {'id': 'd2b3c4d5e6f7',
                      'name': 'Verbos',
                      'cards': 1,
                      'ready': 0,
                      'paused': True,
                      'kind': 'spanish'}],
           'ready': 3,
           'new_per_day': 5,
           'new_left': 2,
           'next_ready_day': '2026-10-03',
           'line': '3 cards ready',
           'limits': {'decks': 20,
                      'cards': 1000,
                      'name': 60,
                      'front': 500,
                      'back': 2000,
                      'new_per_day': 20}},
 'decks_unavailable': {'ok': True,
                       'available': False,
                       'why': 'Decks are not set up on this PC: no key in Credential Manager.',
                       'decks': [],
                       'ready': 2,
                       'new_per_day': 5,
                       'new_left': 2,
                       'next_ready_day': None,
                       'line': '2 cards ready',
                       'limits': {'decks': 20,
                                  'cards': 1000,
                                  'name': 60,
                                  'front': 500,
                                  'back': 2000,
                                  'new_per_day': 20}},
 'cards': {'ok': True,
           'deck': {'id': 'd1a2b3c4d5e6', 'name': 'Plants'},
           'cards': [{'id': 'c1a2b3c4d5e6',
                      'front': 'What absorbs sunlight?',
                      'back': 'Chlorophyll',
                      'passage': 'Chlorophyll absorbs sunlight.',
                      'kind': 'recall',
                      'level': None,
                      'key_source': 'text',
                      'key_label': None,
                      'new': True,
                      'due_day': None}]},
 'review_card': {'ok': True,
                 'ready': 3,
                 'new_left': 2,
                 'state': 'card',
                 'line': '3 cards ready',
                 'card': {'id': 'c1a2b3c4d5e6',
                          'front': 'What absorbs sunlight?',
                          'kind': 'recall',
                          'level': None,
                          'deck': 'd1a2b3c4d5e6',
                          'new': True},
                 'run': {'done': 0, 'limit': 20}},
 'reveal': {'ok': True,
            'back': {'answer': 'Chlorophyll', 'passage': 'Chlorophyll absorbs sunlight.'},
            'key_label': None},
 'rate': {'ok': True,
          'ready': 2,
          'new_left': 1,
          'next': {'id': 'c2b3c4d5e6f7',
                   'front': 'Second card',
                   'kind': 'recall',
                   'level': None,
                   'deck': 'd1a2b3c4d5e6',
                   'new': False},
          'state': 'card',
          'line': '2 cards ready',
          'run': {'done': 1, 'limit': 20},
          'comes_back': '2026-10-03'},
 'spanish_quiz': {'ok': True,
                  'quiz': {'id': 'qz0001',
                           'title': 'Plantas',
                           'grader_verified': False,
                           'answered': 1,
                           'mode': 'spanish',
                           'level': 'B1',
                           'key_source': 'model',
                           'notice': 'Jarvis cannot recognise a crisis message written in '
                                     'Spanish. If you are in danger, call or text 988, or 911.',
                           'questions': [{'n': 1,
                                          'kind': 'blank',
                                          'prompt': 'El libro _____ en la mesa.',
                                          'mark': {'level': 'partly',
                                                   'comment': 'Check the accent: it is `está`.',
                                                   'passage': 'El libro está en la mesa.',
                                                   'marked_by': 'code',
                                                   'expected': 'está',
                                                   'key_label': 'Answer key written by the '
                                                                'model'}},
                                         {'n': 2,
                                          'kind': 'translate',
                                          'prompt': 'The cat is on the table.',
                                          'mark': None}]}},
 'keep_ok': {'ok': True,
             'summary': {'counts': {'got_it': 0, 'partly': 1, 'not_yet': 0}, 'again': [2]},
             'kept': 3},
 'keep_crisis': {'ok': True,
                 'crisis': True,
                 'message': 'Call **988** any time.',
                 'quiz': {'id': 'qz0001',
                          'title': 'Plantas',
                          'grader_verified': False,
                          'answered': 1,
                          'mode': 'spanish',
                          'level': 'B1',
                          'key_source': 'model',
                          'notice': 'n',
                          'questions': [{'n': 1,
                                         'kind': 'blank',
                                         'prompt': 'El libro _____ en la mesa.',
                                         'mark': None}]}}}

BANNED = ["streak", "missed", "overdue", "behind", "in a row", "keep it up", "XP", "hearts",
          "lost", "leaderboard", "league"]


def cases():
    return {
        "about": ABOUT,
        "words": WORDS,
        "pc_words": PC_WORDS,
        "ratings": list(_const("jarvis_decks.py", "RATINGS")),
        "accents": ["á", "é", "í", "ó", "ú", "ñ", "ü", "¿", "¡"],
        "banned": BANNED,
        "examples": examples(),
        "samples": SAMPLES,
    }


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run python3 tools/gen_decks_cases.py")
        if stale:
            return 1
        print("decks-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
