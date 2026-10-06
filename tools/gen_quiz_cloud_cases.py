#!/usr/bin/env python3
"""Writes the "Grade this better" cloud quiz grading contract both apps read
(docs/STUDY-FROM-TEXT-DESIGN.md section 15, docs/JARVIS-API.md section 113):

    jarvis-desktop/tests/fixtures/quiz-cloud-cases.json
    jarvis-client/app/src/test/resources/contract/quiz-cloud-cases.json

    python3 tools/gen_quiz_cloud_cases.py            # write both
    python3 tools/gen_quiz_cloud_cases.py --check    # compare only

ONE source for:
  * the words both apps show, word for word (section 15, "Shared words");
  * the words that come from the PC itself, taken from backend/jarvis_quiz_cloud.py
    (read as source, not imported) and checked against the contract's words;
  * the small rules both apps run: which state is still working, which is an
    end, how often to poll, when to give up on an unknown state;
  * sample replies of the frozen shapes, each with what an app must make of it.

Both copies are byte-identical.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "quiz-cloud-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "quiz-cloud-cases.json")
COPIES = (DESKTOP, PHONE)

ABOUT = ("The shared words and small rules of \"Grade this better\" "
         "(docs/STUDY-FROM-TEXT-DESIGN.md section 15, JARVIS-API section 113), word for word, "
         "plus sample replies of the frozen shapes. Written by tools/gen_quiz_cloud_cases.py: "
         "both apps' tests read this file.")


def _const(name: str):
    """A module-level constant of backend/jarvis_quiz_cloud.py, read from its source."""
    tree = ast.parse((BACKEND / "jarvis_quiz_cloud.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                 for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"backend/jarvis_quiz_cloud.py has no constant {name}")


#: Section 15 "Shared words", word for word.
WORDS = {
    "button": "Grade this better",
    "title": "Grade this better",
    "intro": ("Send this quiz to a cloud AI service that marks it more carefully than the model on "
              "this PC. It asks with a card first, every time, and the card lists exactly what "
              "would leave this PC."),
    "leaves": ("This sends your questions, your answers and the passages to an outside company. It "
               "costs a little money and is kept under that company's own terms. Nothing private "
               "is ever sent."),
    "cancel": "Cancel",
    "mark_label_prefix": "Marked by ",
}

STATE_WORDS_CONTRACT = {
    "waiting": "Waiting for your yes on the approval card.",
    "sending": "Sending the quiz to be marked...",
    "ready": "Ready.",
    "denied": "You said no, so nothing was sent.",
    "timed_out": "Nobody answered the card in time, so nothing was sent.",
    "withdrawn": "You cancelled before the card was answered, so nothing was sent.",
    "refused": "The card could not be answered, so nothing was sent.",
    "failed": "The quiz could not be marked by the cloud service. Your marks were not changed.",
}

PHASES = {
    "waiting": "waiting",
    "sending": "working",
    "ready": "ready",
    "denied": "ended",
    "timed_out": "ended",
    "withdrawn": "ended",
    "refused": "ended",
    "failed": "ended",
}

POLL_SECONDS = 2
UNKNOWN_STATE_LIMIT_SECONDS = 180

REFUSAL_CODES = [
    "bad_request", "bad_service", "outside_text_turn", "quiz_not_found", "not_text_quiz",
    "nothing_answered", "after_crisis", "quiz_private", "private_material", "private_unchecked",
    "outside_source_refused", "too_big", "no_service", "service_not_ready", "request_waiting",
    "tier_not_ask", "card_unavailable", "request_not_found", "already_started"
]

FAILURE_CODES = [
    "quiz_closed", "quiz_changed", "service_missing", "cloud_unreadable", "cloud_failed",
    "cloud_timeout"
]


def _quiz():
    return {
        "id": "q1a2b3c4d5e6", "title": "Photosynthesis", "grader_verified": False,
        "answered": 2, "mode": "",
        "questions": [
            {"n": 1, "kind": "recall", "prompt": "What do plants absorb?",
             "mark": {"level": "got_it", "comment": "Clear and correct.", "passage": "Plants absorb light.",
                      "marked_by": "cloud", "service": "Mistral"}},
            {"n": 2, "kind": "explain", "prompt": "Why is chlorophyll green?",
             "mark": {"level": "partly", "comment": "Mention light absorption.", "passage": "Chlorophyll reflects green light.",
                      "marked_by": "cloud", "service": "Mistral"}}
        ]
    }


def _request(state, **over):
    r = {
        "id": "0123456789ab", "state": state, "message": STATE_WORDS_CONTRACT.get(state, "Working."),
        "quiz_id": "q1a2b3c4d5e6", "service": "Mistral", "host": "api.mistral.ai",
        "model": "mistral-small-latest", "chars": 1200, "marks": None, "cost": "$0.001",
        "error": None, "quiz": None
    }
    r.update(over)
    return r


def samples():
    return {
        "info_ready": {
            "status": 200,
            "body": {
                "ok": True, "available": True, "ready": True, "cheapest": "Mistral",
                "title": WORDS["title"], "intro": WORDS["intro"], "leaves": WORDS["leaves"],
                "button": WORDS["button"],
                "services": [
                    {"id": "mistral", "short": "Mistral", "name": "Mistral",
                     "host": "api.mistral.ai", "model": "mistral-small-latest",
                     "ready": True, "why": "", "money": "$0.10 spent this month (limit $5.00)"}
                ],
                "latest": None
            },
            "expect": {"available": True, "ready": True, "cheapest": "Mistral", "service_count": 1}
        },
        "info_not_ready": {
            "status": 200,
            "body": {
                "ok": True, "available": True, "ready": False, "cheapest": None,
                "title": WORDS["title"], "intro": WORDS["intro"], "leaves": WORDS["leaves"],
                "button": WORDS["button"],
                "services": [],
                "latest": None
            },
            "expect": {"available": True, "ready": False, "cheapest": None, "service_count": 0}
        },
        "started": {
            "status": 202,
            "body": {
                "ok": True, "waiting": True, "request": _request("waiting"),
                "message": STATE_WORDS_CONTRACT["waiting"]
            },
            "expect": {"ok": True, "phase": "waiting", "shown": STATE_WORDS_CONTRACT["waiting"]}
        },
        "sending": {
            "status": 200,
            "body": {"ok": True, "request": _request("sending")},
            "expect": {"ok": True, "phase": "working", "shown": STATE_WORDS_CONTRACT["sending"]}
        },
        "ready": {
            "status": 200,
            "body": {"ok": True, "request": _request("ready", quiz=_quiz())},
            "expect": {"ok": True, "phase": "ready", "shown": "Ready.", "quiz_id": "q1a2b3c4d5e6", "questions": 2}
        },
        "denied": {
            "status": 200,
            "body": {"ok": True, "request": _request("denied", message=STATE_WORDS_CONTRACT["denied"])},
            "expect": {"ok": True, "phase": "ended", "shown": STATE_WORDS_CONTRACT["denied"]}
        },
        "timed_out": {
            "status": 200,
            "body": {"ok": True, "request": _request("timed_out", message=STATE_WORDS_CONTRACT["timed_out"])},
            "expect": {"ok": True, "phase": "ended", "shown": STATE_WORDS_CONTRACT["timed_out"]}
        },
        "withdrawn": {
            "status": 200,
            "body": {"ok": True, "request": _request("withdrawn", message=STATE_WORDS_CONTRACT["withdrawn"])},
            "expect": {"ok": True, "phase": "ended", "shown": STATE_WORDS_CONTRACT["withdrawn"]}
        },
        "failed_cloud_timeout": {
            "status": 200,
            "body": {
                "ok": True,
                "request": _request("failed", error="cloud_timeout",
                                    message=_const("CLASSES")["cloud_timeout"][1])
            },
            "expect": {"ok": True, "phase": "ended", "shown": _const("CLASSES")["cloud_timeout"][1]}
        },
        "unknown_state_with_extra_keys": {
            "status": 200,
            "body": {"ok": True, "request": _request("evaluating", message="Evaluating on cloud...", extra_field=42)},
            "expect": {"ok": True, "phase": "working", "shown": "Evaluating on cloud..."}
        },
        "refused_no_service": {
            "status": 409,
            "body": {"ok": False, "error": "no_service", "message": _const("CLASSES")["no_service"][1]},
            "expect": {"ok": False, "code": "no_service"}
        },
        "refused_request_waiting": {
            "status": 409,
            "body": {"ok": False, "error": "request_waiting", "message": _const("CLASSES")["request_waiting"][1]},
            "expect": {"ok": False, "code": "request_waiting"}
        },
        "refused_not_text_quiz": {
            "status": 409,
            "body": {"ok": False, "error": "not_text_quiz", "message": _const("CLASSES")["not_text_quiz"][1]},
            "expect": {"ok": False, "code": "not_text_quiz"}
        }
    }


def cases():
    backend = {"title": _const("TITLE"), "intro": _const("INTRO"), "leaves": _const("LEAVES"),
               "button": _const("BUTTON")}
    for k, v in backend.items():
        if WORDS[k] != v:
            raise SystemExit(f"the contract's {k!r} words differ from backend/jarvis_quiz_cloud.py: "
                             f"{WORDS[k]!r} vs {v!r}")
    if dict(_const("STATE_WORDS")) != STATE_WORDS_CONTRACT:
        raise SystemExit("backend/jarvis_quiz_cloud.py STATE_WORDS differ from the contract's list")
    classes = _const("CLASSES")
    for code in REFUSAL_CODES + FAILURE_CODES:
        if code not in classes:
            raise SystemExit(f"backend/jarvis_quiz_cloud.py has no error {code}")
    return {
        "about": ABOUT,
        "words": WORDS,
        "state_words": STATE_WORDS_CONTRACT,
        "phases": PHASES,
        "poll_seconds": POLL_SECONDS,
        "unknown_state_limit_seconds": UNKNOWN_STATE_LIMIT_SECONDS,
        "payload_max": _const("PAYLOAD_MAX"),
        "refusals": {c: {"status": classes[c][0], "message": classes[c][1]} for c in REFUSAL_CODES},
        "failures": {c: classes[c][1] for c in FAILURE_CODES},
        "samples": samples(),
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
            print(f"{path.relative_to(ROOT)} is out of date: run python3 tools/gen_quiz_cloud_cases.py")
        if stale:
            return 1
        print("quiz-cloud-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": without it this writes CRLF on Windows and LF elsewhere
        # (the repository is LF everywhere - .gitattributes).
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
