#!/usr/bin/env python3
"""Writes the "Quiz me on a YouTube video" contract both apps read
(docs/STUDY-FROM-TEXT-DESIGN.md section 14, docs/JARVIS-API.md section 112):

    jarvis-desktop/tests/fixtures/youtube-cases.json
    jarvis-client/app/src/test/resources/contract/youtube-cases.json

    python3 tools/gen_youtube_cases.py            # write both
    python3 tools/gen_youtube_cases.py --check    # compare only

ONE source for:
  * the words both apps show, word for word (section 14, "Shared words");
  * the words that come from the PC itself, taken from backend/jarvis_youtube.py
    (read as source, not imported) and checked against the contract's words, so
    the contract, the backend and both apps cannot quietly drift apart;
  * the small rules both apps run: which state is still working, which is an
    end, how often to poll, when to give up on a state nobody knows;
  * sample replies of the frozen shapes, each with what an app must make of it.

Both copies are byte-identical. Nothing here is new behaviour: it is the frozen
contract written down once.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "youtube-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "youtube-cases.json")
COPIES = (DESKTOP, PHONE)

ABOUT = ("The shared words and small rules of \"Quiz me on a YouTube video\" "
         "(docs/STUDY-FROM-TEXT-DESIGN.md section 14, JARVIS-API section 112), word for word, "
         "plus sample replies of the frozen shapes. Written by tools/gen_youtube_cases.py: "
         "both apps' tests read this file.")


def _const(name: str):
    """A module-level constant of backend/jarvis_youtube.py, read from its source
    (not imported: importing it pulls in the quiz, the gate and the network code)."""
    tree = ast.parse((BACKEND / "jarvis_youtube.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                 for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"backend/jarvis_youtube.py has no constant {name}")


#: Section 14 "Shared words", word for word. The four the PC also sends
#: (title, intro, terms, outside) are checked against the backend below.
WORDS = {
    "title": "Quiz me on a YouTube video",
    "intro": ("Paste a YouTube link and Jarvis reads the video's captions (the words shown as "
              "subtitles), then quizzes you on them. It asks with a card first, every time."),
    "terms": ("This breaks YouTube's terms and may be blocked. Only the caption text is fetched - "
              "never the video or its sound. The link tells YouTube which video you are studying."),
    "outside": ("The captions are treated as outside text: Jarvis never learns facts from them. "
                "Your answers are marked by the model on this PC."),
    "placeholder": "Paste a YouTube video link",
    "start": "Read the captions and write questions",
    "cancel": "Cancel",
    "label": "From YouTube captions",
    "missing": ("Your PC's Jarvis does not have YouTube quizzes yet - run apply-patches.ps1 "
                "on the PC."),
}

#: The state words the contract lists "for reference" (the PC sends them).
STATE_WORDS_CONTRACT = {
    "waiting": "Waiting for your yes on the approval card.",
    "fetching": "Reading the captions from YouTube...",
    "writing": "Writing the questions...",
    "ready": "Ready.",
    "denied": "You said no, so nothing was fetched.",
    "timed_out": "Nobody answered the card in time, so nothing was fetched.",
    "withdrawn": "You cancelled before the card was answered, so nothing was fetched.",
    "refused": "The card could not be answered, so nothing was fetched.",
    "failed": "Could not make a quiz from that video.",
}

#: How an app treats each state. "working" states keep polling; "ready" opens
#: the quiz; "ended" shows the PC's message and offers the link field again.
#: Any other state word is treated as still working (decode leniently).
PHASES = {
    "waiting": "waiting",   # working, and the only one Cancel is shown for
    "fetching": "working",
    "writing": "working",
    "ready": "ready",
    "denied": "ended",
    "timed_out": "ended",
    "withdrawn": "ended",
    "refused": "ended",
    "failed": "ended",
}

POLL_SECONDS = 2
UNKNOWN_STATE_LIMIT_SECONDS = 180

#: The error codes that come back before any card (a refusal body), each with its
#: status; the apps show the PC's own message for every one and never rewrite it.
REFUSAL_CODES = ["bad_link", "not_a_web_link", "link_has_login", "not_youtube", "playlist_link",
                 "no_video", "bad_count", "bad_language", "outside_text_turn", "request_waiting",
                 "too_many_quizzes", "card_unavailable", "tier_not_ask", "not_found",
                 "already_started"]

#: Codes a failed request can carry (status 200, state "failed").
FAILURE_CODES = ["no_captions", "no_captions_language", "video_unavailable", "age_restricted",
                 "youtube_refused", "youtube_failed", "fetch_timeout", "library_missing",
                 "too_little_text", "model_unavailable", "quiz_failed"]

LINK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _quiz():
    return {"id": "q1a2b3c4d5e6", "title": "Quiz on a YouTube video", "grader_verified": False,
            "answered": 0, "provenance": "outside", "source": "youtube",
            "questions": [{"n": 1, "kind": "recall", "prompt": "What is the video mainly about?"},
                          {"n": 2, "kind": "explain", "prompt": "Why does the speaker say so?"}]}


def _request(state, **over):
    r = {"id": "0123456789ab", "state": state, "message": STATE_WORDS_CONTRACT.get(state, "Working."),
         "link": LINK, "truncated": False, "minutes": None, "error": None, "quiz": None,
         "provenance": "outside", "source": "youtube"}
    r.update(over)
    return r


def samples():
    """Each sample: a reply body and what an app must make of it."""
    return {
        "started": {
            "status": 202,
            "body": {"ok": True, "waiting": True, "request": _request("waiting"),
                     "message": STATE_WORDS_CONTRACT["waiting"]},
            "expect": {"ok": True, "phase": "waiting", "shown": STATE_WORDS_CONTRACT["waiting"]},
        },
        "fetching": {
            "status": 200, "body": {"ok": True, "request": _request("fetching")},
            "expect": {"ok": True, "phase": "working", "shown": STATE_WORDS_CONTRACT["fetching"]},
        },
        "ready": {
            "status": 200, "body": {"ok": True, "request": _request(
                "ready", quiz=_quiz())},
            "expect": {"ok": True, "phase": "ready", "shown": "Ready.", "quiz_id": "q1a2b3c4d5e6",
                       "questions": 2, "source": "youtube", "truncated": False},
        },
        "ready_truncated": {
            "status": 200, "body": {"ok": True, "request": _request(
                "ready", quiz=_quiz(), truncated=True, minutes=42,
                message="Ready. The video is long, so the quiz covers only the first part "
                        "(about 42 minutes).")},
            "expect": {"ok": True, "phase": "ready", "questions": 2, "truncated": True,
                       "shown": "Ready. The video is long, so the quiz covers only the first "
                                "part (about 42 minutes)."},
        },
        "ready_without_quiz": {
            "status": 200, "body": {"ok": True, "request": _request("ready", quiz=None)},
            "expect": {"ok": False, "phase": "ended", "unreadable": True},
        },
        "denied": {
            "status": 200, "body": {"ok": True, "request": _request(
                "denied", message=STATE_WORDS_CONTRACT["denied"])},
            "expect": {"ok": True, "phase": "ended", "shown": STATE_WORDS_CONTRACT["denied"]},
        },
        "failed_no_captions": {
            "status": 200, "body": {"ok": True, "request": _request(
                "failed", error="no_captions", message=_const("CLASSES")["no_captions"][1])},
            "expect": {"ok": True, "phase": "ended", "shown": _const("CLASSES")["no_captions"][1]},
        },
        "unknown_state_with_extra_keys": {
            "status": 200, "body": {"ok": True, "request": _request(
                "thinking_hard", message="Still on it.", future_key=[1, 2])},
            "expect": {"ok": True, "phase": "working", "shown": "Still on it."},
        },
        "refused_not_youtube": {
            "status": 400, "body": {"ok": False, "error": "not_youtube",
                                    "message": _const("CLASSES")["not_youtube"][1]},
            "expect": {"ok": False, "shown": _const("CLASSES")["not_youtube"][1],
                       "code": "not_youtube"},
        },
        "refused_request_waiting": {
            "status": 409, "body": {"ok": False, "error": "request_waiting",
                                    "message": _const("CLASSES")["request_waiting"][1]},
            "expect": {"ok": False, "shown": _const("CLASSES")["request_waiting"][1],
                       "code": "request_waiting"},
        },
        "too_many_quizzes_keeps_pcs_words": {
            "status": 409, "body": {"ok": False, "error": "too_many_quizzes",
                                    "message": _const("CLASSES")["too_many_quizzes"][1]},
            "expect": {"ok": False, "shown": _const("CLASSES")["too_many_quizzes"][1],
                       "code": "too_many_quizzes"},
        },
        "info": {
            "status": 200,
            "body": {"ok": True, "available": True, "title": WORDS["title"], "intro": WORDS["intro"],
                     "terms": WORDS["terms"], "outside": WORDS["outside"],
                     "limits": {"link": 300, "text": 20000, "count_min": 1, "count_max": 10},
                     "latest": _request("waiting")},
            "expect": {"available": True, "latest_phase": "waiting", "link_max": 300},
        },
        "info_no_latest": {
            "status": 200,
            "body": {"ok": True, "available": True, "limits": {"link": 300}, "latest": None},
            "expect": {"available": True, "latest_phase": None, "link_max": 300},
        },
    }


def cases():
    backend = {"title": _const("TITLE"), "intro": _const("INTRO"), "terms": _const("TERMS"),
               "outside": _const("OUTSIDE_LINE")}
    for k, v in backend.items():
        if WORDS[k] != v:
            raise SystemExit(f"the contract's {k!r} words differ from backend/jarvis_youtube.py: "
                             f"{WORDS[k]!r} vs {v!r}")
    if dict(_const("STATE_WORDS")) != STATE_WORDS_CONTRACT:
        raise SystemExit("backend/jarvis_youtube.py STATE_WORDS differ from the contract's list")
    classes = _const("CLASSES")
    for code in REFUSAL_CODES + FAILURE_CODES:
        if code not in classes:
            raise SystemExit(f"backend/jarvis_youtube.py has no error {code}")
    return {
        "about": ABOUT,
        "words": WORDS,
        "state_words": STATE_WORDS_CONTRACT,
        "phases": PHASES,
        "poll_seconds": POLL_SECONDS,
        "unknown_state_limit_seconds": UNKNOWN_STATE_LIMIT_SECONDS,
        "link_max": _const("LINK_MAX"),
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
            print(f"{path.relative_to(ROOT)} is out of date: run python3 tools/gen_youtube_cases.py")
        if stale:
            return 1
        print("youtube-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
