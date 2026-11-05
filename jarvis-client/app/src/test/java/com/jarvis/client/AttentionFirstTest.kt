package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JobAttention
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.Jobs
import com.jarvis.client.net.parseListBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Attention-first sorting on the phone (2026-11-04, pattern 4 of the
 * owner-forwarded `gemini_rulings_1253_and_superagent_spec_2026_11_04.md`).
 *
 * What is held here, in the order the owner meets it:
 *
 *  * the predicate's truth table, letter for letter from the spec - an
 *    approval, a blocked/`needs_input` question, or a failure the owner has not
 *    put aside; and NOTHING else;
 *  * the PC's own `waits_for_person` boolean, when the payload carries one,
 *    winning over the local derivation - and its ABSENCE falling back, which is
 *    what makes an older backend look right rather than broken;
 *  * a stable split, so rows never jump between two reads of the same answer;
 *  * the ONE-line quiet summary, including "last finished" only when a row
 *    really carries a finish time;
 *  * the wiring: the Work pane draws the sections in that order, an empty
 *    "Needs you" is not created at all (zero pixels), the quiet list is folded
 *    away until a tap, and no polling or approval was added.
 */
class AttentionFirstTest {

    // ------------------------------------------------------------ fixtures ----

    private fun job(
        id: String = "j",
        state: String = "",
        waits: Boolean? = null,
        dismissed: Boolean = false,
        finished: Double? = null,
    ) = JobRecord(
        id = id,
        state = state,
        waitsForPerson = waits,
        dismissedByOwner = dismissed,
        finished = finished,
    )

    private fun feed(body: String): Jobs.Feed =
        (parseListBody(body, Jobs.Feed.serializer(), emptyList()) as ApiResult.Ok).value

    // ------------------------------------------------------ the truth table ----

    @Test
    fun `the three waiting states always wait for a person`() {
        for (state in listOf("waiting_approval", "blocked", "needs_input")) {
            assertTrue(state, JobAttention.waitsForPerson(job(state = state)))
        }
    }

    @Test
    fun `a failure waits unless the owner has put it aside`() {
        assertTrue(JobAttention.waitsForPerson(job(state = "failed")))
        assertTrue(JobAttention.waitsForPerson(job(state = "failed", dismissed = false)))
        assertFalse(JobAttention.waitsForPerson(job(state = "failed", dismissed = true)))
    }

    @Test
    fun `everything else is quiet`() {
        for (state in listOf("queued", "running", "done", "cancelled", "paused", "", "something-new")) {
            assertFalse(state, JobAttention.waitsForPerson(job(state = state)))
        }
    }

    @Test
    fun `the server's own boolean wins when the payload carries it`() {
        // The PC knows things this file cannot see. A running job it says is
        // waiting on a person must not be overridden, and a parked row it says
        // is handled must be trusted.
        assertTrue(JobAttention.waitsForPerson(job(state = "running", waits = true)))
        assertFalse(JobAttention.waitsForPerson(job(state = "waiting_approval", waits = false)))
        assertFalse(JobAttention.waitsForPerson(job(state = "failed", waits = false)))
        // Null is "no field", not "no": the derivation still runs.
        assertTrue(JobAttention.waitsForPerson(job(state = "waiting_approval", waits = null)))
    }

    @Test
    fun `the wire carries the optional fields, and a body without them still works`() {
        // The JSON is a REAL number in jarvis_jobs' own database (SQLite REAL),
        // so `finished` must not be read as an integer.
        val with = feed(
            """{"available": true, "ticking": true, "status": {"handlers": ["h"]},
                "jobs": [{"id": "a", "state": "running", "waits_for_person": true,
                          "dismissed_by_owner": false, "finished": 1700000000.5},
                         {"id": "b", "state": "failed", "dismissed_by_owner": true,
                          "finished": 1700000001.25}]}""",
        )
        assertEquals(true, with.jobs[0].waitsForPerson)
        assertEquals(1700000000.5, with.jobs[0].finished!!, 0.0)
        assertEquals(true, with.jobs[1].dismissedByOwner)
        assertEquals(1700000001.25, with.jobs[1].finished!!, 0.0)
        assertTrue(JobAttention.waitsForPerson(with.jobs[0]))
        assertFalse(JobAttention.waitsForPerson(with.jobs[1]))

        // An older PC: no attention fields at all. The derivation decides.
        val old = feed(
            """{"available": true, "ticking": true, "status": {"handlers": ["h"]},
                "jobs": [{"id": "a", "state": "waiting_approval"},
                         {"id": "b", "state": "running"}]}""",
        )
        assertNull(old.jobs[0].waitsForPerson)
        assertTrue(JobAttention.waitsForPerson(old.jobs[0]))
        assertFalse(JobAttention.waitsForPerson(old.jobs[1]))
    }

    // ----------------------------------------------------------- the split ----

    @Test
    fun `the split keeps the payload's own order on BOTH sides`() {
        val jobs = listOf(
            job(id = "a", state = "running"),
            job(id = "b", state = "waiting_approval"),
            job(id = "c", state = "done"),
            job(id = "d", state = "failed"),
            job(id = "e", state = "queued"),
            job(id = "f", state = "blocked"),
        )
        val split = JobAttention.partition(jobs)
        assertEquals(listOf("b", "d", "f"), split.needs.map { it.id })
        assertEquals(listOf("a", "c", "e"), split.quiet.map { it.id })
        // Same answer twice: a re-read of the same list must not reorder rows.
        assertEquals(split, JobAttention.partition(jobs))
    }

    @Test
    fun `an empty list is two empty sections`() {
        val split = JobAttention.partition(emptyList())
        assertTrue(split.needs.isEmpty())
        assertTrue(split.quiet.isEmpty())
    }

    // -------------------------------------------------- the quiet summary ----

    @Test
    fun `no quiet jobs means no bar at all`() {
        assertEquals("", JobAttention.quietLine(emptyList(), 1000))
    }

    @Test
    fun `the summary names the section, the count and only real facts`() {
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 1 background job — 1 still running",
            JobAttention.quietLine(listOf(job(state = "running")), 1000),
        )
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 2 background jobs — 1 still running, 1 finished",
            JobAttention.quietLine(listOf(job(state = "running"), job(state = "done")), 1000),
        )
        // A queued job is work in flight; it must not be called finished.
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 1 background job — 1 still running",
            JobAttention.quietLine(listOf(job(state = "queued")), 1000),
        )
    }

    @Test
    fun `the last finish is shown, and nothing is invented when it is absent`() {
        val now = 10_000L
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 3 background jobs — 1 still running, 2 finished" +
                " · last finished 2m ago",
            JobAttention.quietLine(
                listOf(
                    job(state = "done", finished = now - 600.0),
                    job(state = "done", finished = now - 120.0),
                    job(state = "running"),
                ),
                now,
            ),
        )
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 1 background job — 1 still running",
            JobAttention.quietLine(listOf(job(state = "running")), now),
        )
    }

    @Test
    fun `a dismissed failure is still counted, in plain words`() {
        assertEquals(
            "${JobAttention.QUIET_HEAD} · 1 background job — 1 failed · last finished 1m ago",
            JobAttention.quietLine(
                listOf(job(state = "failed", dismissed = true, finished = 940.0)),
                1000,
            ),
        )
    }

    @Test
    fun `ages are whole words and never negative`() {
        assertEquals("", JobAttention.agoWords(0, 1000))
        assertEquals("", JobAttention.agoWords(-5, 1000))
        assertEquals("just now", JobAttention.agoWords(995, 1000))
        assertEquals("just now", JobAttention.agoWords(980, 1000))
        assertEquals("1m ago", JobAttention.agoWords(1_000_000L - 60, 1_000_000L))
        assertEquals("1h ago", JobAttention.agoWords(1_000_000L - 3600, 1_000_000L))
        assertEquals("1d ago", JobAttention.agoWords(1_000_000L - 86400, 1_000_000L))
        // A phone clock behind the PC reads "just now", never "-3m ago".
        assertEquals("just now", JobAttention.agoWords(2000, 1000))
    }

    // ----------------------------------------------------------- the words ----

    @Test
    fun `both apps use the same two headings, word for word`() {
        // The desktop's module is the other half of the same UI rule. Reading
        // it here is what stops the two drifting apart silently - the same
        // trick the job list's "shared cases" test uses.
        val desktop = SourceFile.read("jarvis-desktop/src/attention.js")
        assertTrue(desktop, desktop.contains("export const NEEDS_YOU = \"${JobAttention.NEEDS_HEAD}\""))
        assertTrue(desktop, desktop.contains("export const QUIET_HEALTHY = \"${JobAttention.QUIET_HEAD}\""))
        assertTrue(desktop, desktop.contains("export const SHOW = \"${JobAttention.SHOW}\""))
        assertTrue(desktop, desktop.contains("export const HIDE = \"${JobAttention.HIDE}\""))
    }

    // ---------------------------------------------------------- the wiring ----

    @Test
    fun `the Work pane draws Needs-you first, then the ONE quiet bar`() {
        val plate = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/JobsPlate.kt",
        )
        val splitAt = plate.indexOf("JobAttention.partition(rows)")
        assertTrue("the pane does not split with the shared predicate", splitAt >= 0)
        val needsAt = plate.indexOf("if (split.needs.isNotEmpty())")
        val barAt = plate.indexOf("QuietBar(")
        val quietRowsAt = plate.indexOf("JobRows(split.quiet")
        assertTrue("the Needs-you section must be conditional", needsAt > splitAt)
        assertTrue("a job that needs you comes before the quiet ones", barAt > needsAt)
        assertTrue("the quiet rows are only drawn once the bar is open", quietRowsAt > barAt)
        // The heading lives INSIDE the conditional, so an empty section draws
        // nothing at all - no heading, no empty box, no gap.
        assertTrue(
            "Kicker(NEEDS_HEAD) must be inside the needs branch",
            plate.indexOf("Kicker(JobAttention.NEEDS_HEAD)") > needsAt,
        )
        assertTrue(
            "the quiet list is folded until the owner taps",
            plate.contains("if (quietOpen) {"),
        )
        // ONE line, enforced rather than assumed.
        assertTrue(plate.contains("maxLines = 1"))
        assertTrue(plate.contains("TextOverflow.Ellipsis"))
        // And the fold says its state to TalkBack as well as in words.
        assertTrue(plate.contains("stateDescription = if (open)"))
    }

    @Test
    fun `folding the quiet list only changes a local flag - no timer, no request`() {
        val plate = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/JobsPlate.kt",
        )
        val start = plate.indexOf("private fun QuietBar(")
        assertTrue("QuietBar is missing", start >= 0)
        val body = plate.substring(start, plate.indexOf("\n}\n", start))
        for (banned in listOf("JarvisRuntime", "jobsRead", "setInterval", "delay(", "Timer")) {
            assertFalse("the quiet bar does $banned", body.contains(banned))
        }
        // The one state write is the owner's tap, and nothing sets it open by
        // itself.
        assertTrue(body.contains("onToggle"))
        assertFalse(plate.contains("quietOpen = true"))
    }

    @Test
    fun `the permission model is untouched - still exactly one yes and one no`() {
        val plate = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/JobsPlate.kt",
        )
        // The existing count from BackgroundJobsTest, re-asserted here because
        // this slice edits the same screen: splitting a list must not duplicate
        // the only decision the pane is allowed to offer.
        assertEquals(1, Regex("""\bAffirm\(""").findAll(plate).count())
        assertEquals(1, Regex("""\bRefuse\(""").findAll(plate).count())
        assertFalse(plate.contains("/api/approve"))
        assertFalse(plate.contains("/api/deny"))
    }
}
