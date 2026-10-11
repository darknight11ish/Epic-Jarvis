"""test_arbiter.py - the interruption budget, the digest, and the banked face.

Most of these are about things NOT happening. A budget is only a budget if it
refuses, so the tests that matter are the ones asserting that a second spoken
interruption does not happen, that a finished job cannot make a sound, that a
producer cannot buy its way past the limit by claiming urgency, and that there
is no code path anywhere in this module that approves anything.

The last one is tested structurally rather than by behaviour: a bulk-approve
control is the kind of thing that gets added later by someone solving a real
annoyance, so the test asserts the module has no such function at all.
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import jarvis_arbiter as AB


def cfg(**overrides):
    return mock.patch.object(AB, "_cfg",
                             side_effect=lambda k, d: overrides.get(k, d))


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old_db, self._old_cfgdir = AB.DB_PATH, AB._CFG_DIR
        AB.DB_PATH = self.dir / "arbiter.db"
        AB._CFG_DIR = self.dir
        AB._inited = False
        AB._last_published.clear()
        os.environ["JARVIS_PRESENCE_FILE"] = str(self.dir / "presence.json")

    def tearDown(self):
        AB.DB_PATH, AB._CFG_DIR = self._old_db, self._old_cfgdir
        AB._inited = False
        os.environ.pop("JARVIS_PRESENCE_FILE", None)
        self.tmp.cleanup()

    def speak(self, source="test", **kw):
        return AB.deliver(source, kw.pop("title", "something happened"), **kw)

    def present(self, locked=False, idle=0):
        Path(os.environ["JARVIS_PRESENCE_FILE"]).write_text(
            json.dumps({"locked": locked, "idle_seconds": idle}), "utf-8")


# ==========================================================================
#   1. The budget refuses
# ==========================================================================

class Budget(Sandbox):

    def test_the_first_few_get_through_and_the_next_does_not(self):
        with cfg(spoken_per_day=3):
            spoken = [self.speak(title=f"finding {i}").channel for i in range(5)]
        self.assertEqual(spoken, [AB.SPEAK, AB.SPEAK, AB.SPEAK,
                                  AB.DIGEST, AB.DIGEST])

    def test_what_did_not_fit_is_in_the_digest_not_lost(self):
        with cfg(spoken_per_day=1):
            for i in range(4):
                self.speak(title=f"finding {i}")
            self.assertEqual(AB.digest()["count"], 3)

    def test_priority_does_not_buy_a_bigger_budget(self):
        """A producer that could be heard more by claiming urgency would always
        claim urgency, and a scale everybody tops out on is not a scale."""
        with cfg(spoken_per_day=1):
            self.assertEqual(self.speak(priority="critical").channel, AB.SPEAK)
            self.assertEqual(self.speak(priority="critical").channel, AB.DIGEST)

    def test_two_producers_at_once_cannot_both_spend_the_last_token(self):
        import threading
        with cfg(spoken_per_day=1):
            out = []
            def go():
                out.append(AB.deliver("racer", "x").channel)
            ts = [threading.Thread(target=go) for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(out.count(AB.SPEAK), 1, out)

    def test_the_budget_resets_the_next_day(self):
        day2 = time.time() + 86400 * 1.5
        with cfg(spoken_per_day=1):
            self.assertEqual(self.speak().channel, AB.SPEAK)
            self.assertEqual(self.speak().channel, AB.DIGEST)
            self.assertEqual(AB.deliver("t", "tomorrow", now=day2).channel, AB.SPEAK)

    def test_muting_lasts_until_tomorrow_and_no_longer(self):
        """Not "mute forever": a mute with no end is how a feature gets
        switched off once and never reconsidered."""
        with cfg(spoken_per_day=5):
            AB.mute_until_tomorrow()
            self.assertEqual(self.speak().channel, AB.DIGEST)
            self.assertTrue(AB.budget()["muted"])
            tomorrow = time.time() + 86400 * 1.2
            self.assertFalse(AB.budget(tomorrow)["muted"])
            self.assertEqual(AB.deliver("t", "x", now=tomorrow).channel, AB.SPEAK)

    def test_unmute_works_the_same_day(self):
        with cfg(spoken_per_day=2):
            AB.mute_until_tomorrow()
            AB.unmute()
            self.assertEqual(self.speak().channel, AB.SPEAK)

    def test_a_zero_budget_means_nothing_is_ever_spoken(self):
        with cfg(spoken_per_day=0):
            self.assertEqual(self.speak().channel, AB.DIGEST)
            self.assertEqual(AB.budget()["remaining"], 0)


# ==========================================================================
#   2. When the budget is zero regardless
# ==========================================================================

class Blocked(Sandbox):

    def test_quiet_and_standby_spend_nothing(self):
        for mode in ("quiet", "standby"):
            with self.subTest(mode=mode):
                AB._inited = False
                with cfg(spoken_per_day=5), \
                     mock.patch.dict(sys.modules, {"jarvis_power": mock.Mock(
                         current=lambda: mode)}):
                    d = self.speak()
                self.assertEqual(d.channel, AB.DIGEST)
                self.assertIn(mode, d.reason)

    def test_a_locked_session_spends_nothing(self):
        """This is the webcam replacement. The operating system already knows
        whether the owner is there; a camera would add a second-person record
        and an always-open handle and buy nothing."""
        self.present(locked=True)
        with cfg(spoken_per_day=5):
            self.assertEqual(self.speak().channel, AB.DIGEST)
            self.assertIn("locked", AB.budget()["blocked_by"])

    def test_a_long_idle_counts_as_away(self):
        self.present(idle=3600)
        with cfg(spoken_per_day=5, away_after_idle_minutes=15):
            self.assertEqual(self.speak().channel, AB.DIGEST)

    def test_a_short_idle_does_not(self):
        self.present(idle=60)
        with cfg(spoken_per_day=5, away_after_idle_minutes=15):
            self.assertEqual(self.speak().channel, AB.SPEAK)

    def test_an_unknown_presence_does_not_silence_jarvis(self):
        """No presence file at all. Failing to "never speak" would look like a
        broken assistant, and an unknown answer is not a reason to be one."""
        with cfg(spoken_per_day=5):
            self.assertEqual(self.speak().channel, AB.SPEAK)

    def test_a_corrupt_presence_file_is_not_a_lock(self):
        Path(os.environ["JARVIS_PRESENCE_FILE"]).write_text("{ not json", "utf-8")
        with cfg(spoken_per_day=5):
            self.assertEqual(self.speak().channel, AB.SPEAK)


# ==========================================================================
#   3. Foreground is not an interruption
# ==========================================================================

class Foreground(Sandbox):

    def test_something_you_asked_for_never_waits_on_a_budget(self):
        with cfg(spoken_per_day=0):
            d = AB.deliver("gate", "approve this?", solicited=True)
        self.assertEqual(d.channel, AB.SPEAK)
        self.assertTrue(d.spoken)

    def test_it_is_not_counted(self):
        with cfg(spoken_per_day=1):
            AB.deliver("gate", "approve this?", solicited=True)
            self.assertEqual(AB.budget()["spent"], 0)
            self.assertEqual(self.speak().channel, AB.SPEAK)

    def test_it_is_never_queued(self):
        with cfg(spoken_per_day=0):
            AB.deliver("gate", "approve this?", solicited=True)
        self.assertEqual(AB.pending_count(), 0)

    def test_it_works_while_muted(self):
        with cfg(spoken_per_day=5):
            AB.mute_until_tomorrow()
            self.assertEqual(
                AB.deliver("gate", "you asked", solicited=True).channel, AB.SPEAK)


# ==========================================================================
#   4. Things that stop being true
# ==========================================================================

class Perishable(Sandbox):

    def test_an_undeferrable_item_is_dropped_rather_than_shown_tomorrow(self):
        """A stale "your build is failing" from yesterday is worse than
        nothing: acting on it wastes a real minute."""
        with cfg(spoken_per_day=0):
            d = self.speak(title="build failing", can_defer=False)
        self.assertEqual(d.channel, AB.DROPPED)
        self.assertEqual(AB.pending_count(), 0)

    def test_can_defer_false_does_not_buy_a_token(self):
        with cfg(spoken_per_day=1):
            self.assertEqual(self.speak(can_defer=False).channel, AB.SPEAK)
            self.assertEqual(self.speak(can_defer=False).channel, AB.DROPPED)

    def test_an_expired_item_never_reaches_the_digest(self):
        now = time.time()
        with cfg(spoken_per_day=0):
            self.speak(title="ephemeral", expires=now + 10, now=now)
        self.assertEqual(AB.digest(now=now)["count"], 1)
        self.assertEqual(AB.digest(now=now + 60)["count"], 0)

    def test_notify_costs_nothing_and_is_not_queued(self):
        with cfg(spoken_per_day=0):
            d = self.speak(want=AB.NOTIFY)
        self.assertEqual(d.channel, AB.NOTIFY)
        self.assertEqual(AB.pending_count(), 0)


# ==========================================================================
#   5. The digest
# ==========================================================================

class Digest(Sandbox):

    def fill(self):
        with cfg(spoken_per_day=0):
            self.speak(source="heartbeat", title="disk is at 91%", kind="finding")
            self.speak(source="long-fuse", title="repo watch finished", kind="job")
            self.speak(source="gate", title="send email to finance", kind="approval",
                       body="the whole command and recipient list")
            self.speak(source="steward", title="a newer model is out", kind="steward")

    def test_it_is_ranked_by_consequence_not_by_how_loudly_it_asks(self):
        self.fill()
        self.assertEqual([i["kind"] for i in AB.digest()["items"]],
                         ["approval", "job", "steward", "finding"])

    def test_urgent_wording_does_not_move_an_item_up(self):
        """Ranking by urgency would implement the attacker's half of the
        approval-fatigue trick for them."""
        with cfg(spoken_per_day=0):
            self.speak(source="page", kind="finding",
                       title="URGENT: act now, before it expires")
            self.speak(source="gate", kind="approval", title="ordinary approval")
        self.assertEqual(AB.digest()["items"][0]["kind"], "approval")

    def test_an_approval_carries_no_detail_and_opens_its_own_card(self):
        self.fill()
        item = [i for i in AB.digest()["items"] if i["kind"] == "approval"][0]
        self.assertTrue(item["opens_card"])
        self.assertEqual(item["body"], "")

    def test_there_is_no_way_to_approve_anything_from_this_module(self):
        """Structural. A bulk-approve control is the kind of thing somebody
        adds later to fix a real annoyance, so the absence is asserted rather
        than assumed."""
        names = [n for n in dir(AB) if not n.startswith("_")]
        for banned in ("approve", "approve_all", "decide", "accept",
                       "approve_safe", "resolve"):
            self.assertNotIn(banned, names)
        self.assertNotIn("approve", AB.digest()["note"].split("There is no ")[0])

    def test_the_digest_says_out_loud_that_there_is_no_approve_all(self):
        self.assertIn("no approve-all", AB.digest()["note"])

    def test_it_is_due_once_a_day_at_the_chosen_hour(self):
        self.fill()
        day = time.mktime(time.localtime())
        lt = time.localtime(day)
        morning = day - lt.tm_hour * 3600 + 9 * 3600
        evening = morning + 9 * 3600
        with cfg(digest_hour=18):
            self.assertFalse(AB.digest_due(morning))
            self.assertTrue(AB.digest_due(evening))

    def test_an_empty_digest_is_never_due(self):
        """A brief that arrives empty teaches the owner it is not worth
        opening, and then the one that matters is not opened either."""
        with cfg(digest_hour=0):
            self.assertFalse(AB.digest_due())

    def test_it_is_not_due_twice_in_one_day(self):
        self.fill()
        with cfg(digest_hour=0):
            self.assertTrue(AB.digest_due())
            AB.mark_digest_delivered()
            self.assertFalse(AB.digest_due())

    def test_generating_it_does_not_mark_it_seen(self):
        """The phone was off, the tray never opened. A digest that was built
        and never displayed has to come back."""
        self.fill()
        with cfg(digest_hour=0):
            AB.digest()
            self.assertTrue(AB.digest_due())

    def test_marking_some_items_leaves_the_rest(self):
        self.fill()
        first = AB.digest()["items"][0]["id"]
        AB.mark_digest_delivered([first])
        self.assertEqual(AB.digest()["count"], 3)


# ==========================================================================
#   6. The banked reactor state
# ==========================================================================

class Banked(Sandbox):

    def test_nothing_waiting_is_not_banked(self):
        with cfg(spoken_per_day=0):
            self.assertFalse(AB.banked())

    def test_spent_budget_with_things_waiting_is_banked(self):
        with cfg(spoken_per_day=0):
            self.speak()
            self.assertTrue(AB.banked())

    def test_banked_replaces_only_a_resting_face(self):
        """The budget governs what Jarvis STARTS. Interrupting a sentence it
        is already in the middle of, to somebody who asked for it, would be a
        different bug wearing the same name."""
        with cfg(spoken_per_day=0):
            self.speak()
            self.assertEqual(AB.face_state("idle"), "banked")
            for busy in ("speaking", "thinking", "listening", "working"):
                self.assertEqual(AB.face_state(busy), busy)

    def test_the_rim_ring_counts_what_is_waiting(self):
        with cfg(spoken_per_day=0):
            for i in range(4):
                self.speak(title=f"x{i}")
        self.assertEqual(AB.pending_count(), 4)

    def test_a_job_finishing_while_banked_cannot_make_a_sound(self):
        """The rule the whole feature rests on. The code path that finishes a
        job is not the code path that checks the budget, and letting a
        completion speak anyway is exactly how an interruption budget becomes
        decorative."""
        fake = mock.Mock()
        fake.collect.return_value = [{"id": "j1", "label": "repo watch",
                                      "state": "done", "result_summary": "3 commits"}]
        with cfg(spoken_per_day=0), \
             mock.patch.dict(sys.modules, {"jarvis_jobs": fake}):
            out = AB.tick()
            self.assertEqual(out["jobs"], 1)
            self.assertEqual(AB.pending_count(), 1)
            self.assertEqual(AB.face_state("idle"), "banked")
            self.assertEqual([i["kind"] for i in AB.digest()["items"]], ["job"])

    def test_a_failed_job_is_ranked_above_a_finding_but_still_silent(self):
        fake = mock.Mock()
        fake.collect.return_value = [{"id": "j2", "label": "sync",
                                      "state": "failed", "error": "no route to host"}]
        with cfg(spoken_per_day=0), \
             mock.patch.dict(sys.modules, {"jarvis_jobs": fake}):
            self.speak(source="heartbeat", kind="finding", title="disk is fine")
            AB.tick()
        self.assertEqual([i["kind"] for i in AB.digest()["items"]],
                         ["job", "finding"])


# ==========================================================================
#   7. Talking to the clients
# ==========================================================================

class Publishing(Sandbox):

    def test_the_state_is_published_when_it_changes(self):
        bus = mock.Mock()
        with cfg(spoken_per_day=1), \
             mock.patch.dict(sys.modules, {"jarvis_events": mock.Mock(BUS=bus)}):
            self.speak()
        kinds = [c.args[0] for c in bus.publish.call_args_list]
        self.assertIn("attention", kinds)

    def test_it_is_not_published_again_when_nothing_changed(self):
        bus = mock.Mock()
        with cfg(spoken_per_day=0), \
             mock.patch.dict(sys.modules, {"jarvis_events": mock.Mock(BUS=bus)}):
            AB.tick()
            n = bus.publish.call_count
            AB.tick()
        self.assertEqual(bus.publish.call_count, n)

    def test_the_arbiter_works_with_no_event_bus_at_all(self):
        with cfg(spoken_per_day=1), \
             mock.patch.dict(sys.modules, {"jarvis_events": None}):
            self.assertEqual(self.speak().channel, AB.SPEAK)

    def test_status_answers_without_a_bus_or_a_power_module(self):
        s = AB.status()
        self.assertIn("budget", s)
        self.assertIn("pending", s)


# ==========================================================================
#   8. Keeping the table from growing for ever
# ==========================================================================

class Housekeeping(Sandbox):

    def test_delivered_rows_are_dropped_after_the_keep_window(self):
        old = time.time() - 40 * 86400
        with cfg(spoken_per_day=5, keep_delivered_days=14):
            self.speak(now=old)
            AB.expire()
        with closing_conn(AB) as c:
            n = c.execute("SELECT COUNT(*) n FROM intents").fetchone()["n"]
        self.assertEqual(n, 0)

    def test_a_queued_row_is_never_dropped_by_the_keep_window(self):
        """Old and still waiting is exactly the case a digest exists for."""
        old = time.time() - 40 * 86400
        with cfg(spoken_per_day=0, keep_delivered_days=14):
            self.speak(now=old)
            AB.expire()
        self.assertEqual(AB.pending_count(), 1)


def closing_conn(mod):
    import contextlib
    return contextlib.closing(mod._connect())


if __name__ == "__main__":
    unittest.main(verbosity=2)
