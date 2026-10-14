"""The cloud lane writes down what it spends, so the monthly limit can advance.

    python3 test_cloud_spend.py

WHY THIS EXISTS. `docs/audit-2026-10-07/E-open-pull-requests.md`, finding E3:
the cloud-lane transport "never records what it spends, so the monthly limit it
advertises can never advance". `jarvis_chatbot_api.cloud_lane()` refuses a lane
once this month's money limit is reached, and that limit is shown in both apps -
but `jarvis_hud.py`'s own cloud send is a SECOND transport, and it never called
`record_spend`. The total it checked could only ever begin at zero.

WHERE THE RECORD IS TAKEN, AND WHY NOT IN THE HUD. Every line the answer streams
through in `jarvis_hud.py` sits inside a hunk of the patch stack, so a line added
there makes those patches unappliable - measured: the 143-patch rehearsal failed
on 29 patches. `jarvis_speed.Meter.finish()` is the hook that module already
documents as existing so that file can be measured without being edited, and it
has just measured the answer. So `jarvis_speed` hands the measurement to
`jarvis_chatbot_api.note_answer_spend()`, which is where the money already lives.

WHAT IS CHECKED. That one real `Meter` run writes the spend down; that the
service's own token count is recorded as exact and a counted one as an estimate;
that a local turn and a lane this PC cannot pay for write NOTHING; that a money
file which cannot be read never breaks an answered turn; and - the point of E3 -
that recording moves the month's total and the cap then refuses the lane.

The money file is a temporary file. The owner's is never read or written here.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "jarvis-backend"))

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_speed as SPEED  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


CLOUD_STATE = {"lane": "cloud-lane", "pid": "openai_api", "model": "gpt-5-mini",
               "host": "api.openai.com", "key": "never-read-here",
               "url": "https://api.openai.com/v1/chat/completions", "cap": 0, "problem": ""}


class Log:
    """Stands in for SpeedLog so nothing is written to the owner's folder."""

    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(row)


def main() -> int:
    api_src = (REPO / "backend" / "jarvis_chatbot_api.py").read_text(encoding="utf-8")
    speed_src = (REPO / "backend" / "jarvis_speed.py").read_text(encoding="utf-8")

    # ---- 1. the hook is wired -------------------------------------------
    check("the money module can record one answer",
          "def note_answer_spend(" in api_src)
    check("the Meter hands its measurement over when the answer finishes",
          "note_answer_spend(row)" in speed_src and "jarvis_chatbot_api" in speed_src,
          "jarvis_speed no longer records the cloud lane's spend - E3 is back")

    if not hasattr(API, "note_answer_spend"):
        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        print("failed: " + ", ".join(FAILED))
        return 1

    seen = []
    real_last, real_record = API.last_lane_state, API.record_spend

    def spy(pid, model, pt, ct, **kw):
        seen.append((pid, model, pt, ct, kw))
        return 0.0

    try:
        # ---- 2. a real Meter run records the turn -------------------------
        API.last_lane_state = lambda: dict(CLOUD_STATE)
        API.record_spend = spy
        meter = SPEED.start("cloud-lane")
        meter.feed(b'data: {"choices":[{"delta":{"content":"Hello there"}}]}\n\n')
        meter.feed(b'data: {"choices":[{"delta":{"content":" friend"}}]}\n\n')
        meter.feed(b'data: {"usage":{"prompt_tokens":120,"completion_tokens":40}}\n\n')
        meter.feed(b"data: [DONE]\n\n")
        meter.finish("cloud-lane", background=False, log=Log(), gpu=lambda _m: None)
        check("a real Meter run writes one record for the answer", len(seen) == 1, seen)
        check("... against the service and the model the lane resolved",
              bool(seen) and seen[0][0] == "openai_api" and seen[0][1] == "gpt-5-mini", seen)
        check("... with the service's own token counts when it sent them",
              bool(seen) and seen[0][2] == 120 and seen[0][3] == 40, seen)
        check("... recorded as exact, because the service reported them",
              bool(seen) and seen[0][4].get("guessed") is False, seen)

        # ---- 3. a counted answer is recorded as an estimate ----------------
        seen.clear()
        meter2 = SPEED.start("cloud-lane")
        meter2.feed(b'data: {"choices":[{"delta":{"content":"one two three"}}]}\n\n')
        meter2.feed(b"data: [DONE]\n\n")
        meter2.finish("cloud-lane", background=False, log=Log(), gpu=lambda _m: None)
        check("an answer with no service-reported usage is still written down",
              len(seen) == 1, seen)
        check("... and is marked an estimate, not a figure the service gave",
              bool(seen) and seen[0][4].get("guessed") is True, seen)

        # ---- 4. a local turn writes nothing -------------------------------
        seen.clear()
        API.last_lane_state = lambda: dict(API.NO_LANE_STATE)
        meter3 = SPEED.start("local")
        meter3.feed(b'data: {"choices":[{"delta":{"content":"local words"}}]}\n\n')
        meter3.finish("local", background=False, log=Log(), gpu=lambda _m: None)
        check("a local turn writes nothing down", not seen, seen)

        # ---- 5. a lane this PC cannot pay for writes nothing --------------
        seen.clear()
        API.last_lane_state = lambda: {"pid": "openai_api", "model": "gpt-5-mini",
                                       "url": "", "key": ""}
        API.note_answer_spend({"tokens": 10, "prompt_tokens": 10, "token_source": "usage"})
        check("a lane with no address (unpayable here) writes nothing down", not seen, seen)

        # ---- 6. a money file that cannot be written breaks nothing --------
        def explode(*a, **k):
            raise OSError("the money file cannot be read")

        API.record_spend = explode
        API.last_lane_state = lambda: dict(CLOUD_STATE)
        raised = False
        try:
            API.note_answer_spend({"tokens": 5, "prompt_tokens": 5, "token_source": "usage"})
        except Exception:
            raised = True
        check("a record that cannot be written does not raise", not raised)
    finally:
        API.last_lane_state, API.record_spend = real_last, real_record

    # ---- 7. THE POINT: the total moves, and the cap then refuses ----------
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-cloud-spend-"))
    real_path = API.money_path
    pid, model = "openai_api", "gpt-5-mini"
    try:
        API.money_path = lambda: tmp / "chatbot" / API.MONEY_FILE
        API.last_lane_state = lambda: dict(CLOUD_STATE)
        # Money here is kept in whole cents, so $0.01 is the smallest real
        # budget; one answer of this size costs about $0.0017 at this model's
        # published price, so several of them pass a one-cent limit.
        limit = 0.01
        made = API.set_limit(pid, limit)
        check("the limit is set on a temporary money file, not the owner's",
              bool(made.get("ok")), made)
        check("with a limit set and nothing spent, the month's total starts at zero",
              API.spent_of(pid) == 0.0, API.spent_of(pid))
        why, _cap = API.money_check(pid, model, next_chars=10, next_messages=1)
        check("... so a lane inside its limit can be paid for", why == "", why)

        row = {"tokens": 400, "prompt_tokens": 4000, "token_source": "deltas"}
        API.note_answer_spend(row)
        spent = API.spent_of(pid)
        check("one recorded cloud answer moves the month's total off zero", spent > 0,
              f"spent={spent!r} - a zero here means the record was never written, "
              "or the model has no price in this build")

        for _ in range(40):
            if API.spent_of(pid) > limit:
                break
            API.note_answer_spend(row)
        spent = API.spent_of(pid)
        why2, _cap2 = API.money_check(pid, model, next_chars=10, next_messages=1)
        check("... and once the month passes the limit the lane is refused, so the cap can be kept",
              spent > limit and why2 != "", (spent, limit, why2))
    finally:
        API.money_path = real_path
        API.last_lane_state = real_last

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
