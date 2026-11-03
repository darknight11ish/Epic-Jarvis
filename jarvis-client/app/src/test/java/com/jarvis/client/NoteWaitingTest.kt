package com.jarvis.client

import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.NoteCapture
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The chat line a note's approval card leaves behind (the owner's report,
 * 2026-11-02): "make a note: ..." with a card up answers the chat with the
 * literal "Waiting for your approval.", the note is filed when the card is
 * approved, and the chat went on claiming to wait for ever.
 *
 * Three halves, all pure Kotlin so they run on a plain JVM:
 *
 * 1. [NoteCapture.jobFromRoute] - the capture job id the PC now puts in
 *    `X-Jarvis-Route` (`note_job`), read strictly: only an id of the PC's own
 *    shape is ever used, and anything else is "nothing to follow".
 * 2. [NoteCapture.settledText] - the PC's own last sentence for that job, and
 *    null while it is still waiting, so a line that cannot be confirmed is
 *    never replaced by a guess.
 * 3. [ChatHistory.settle] - the ONE pair that said those words, matched on its
 *    question too, so two notes asked one after the other cannot swap their
 *    endings.
 *
 * The header shapes and job bodies below are the real ones: the docs'
 * `X-Jarvis-Route` fields (docs/JARVIS-API.md §11, §21) and
 * `jarvis_note_capture.capture_status`'s job record, measured against
 * `backend/jarvis_quick.py` (the last test pins that they still agree).
 */
class NoteWaitingTest {

    private fun job(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    /** The header the PC really sends for a note left waiting (measured). */
    private val waitingHeader =
        """{"inject_memory":false,"injected_facts":0,"injected_ids":[],"injected_sensitive":0,""" +
            """"lane":"no AI model","note_job":"note_79b501a21f3dd6e7","quick":"note_make_waiting",""" +
            """"where":"local"}"""

    // ------------------------------------------------- the job id, read strictly

    @Test
    fun theJobsIdIsReadFromTheAnswersOwnRoute() {
        assertEquals("note_79b501a21f3dd6e7", NoteCapture.jobFromRoute(waitingHeader))
    }
    @Test
    fun anAnswerWithNoJobNamesNothingToFollow() {
        for (header in listOf(
            null,
            "",
            "   ",
            "not json",
            "{}",
            // A quick answer that is not a note at all - a timer, a reminder.
            """{"quick":"timer_set","where":"local"}""",
            // A note filed at once: there is no card, so nothing to follow.
            """{"quick":"note_made","where":"local"}""",
            """{"note_job":null}""",
            """{"note_job":""}""",
            // A number, an object or a list where the id should be is not an id.
            """{"note_job":12}""",
            """{"note_job":{}}""",
            """{"note_job":["note_0123456789abcdef"]}""",
            """{"note_job":true}""",
        )) {
            assertNull("$header named a job", NoteCapture.jobFromRoute(header))
        }
    }

    @Test
    fun anIdThePcDidNotMakeIsNeverUsed() {
        // This one goes into a query string: anything that is not the PC's own
        // shape (jarvis_note_capture: "note_" + 16 lowercase hex) is refused.
        for (id in listOf(
            "javascript:alert(1)",
            "note_",
            "note_xyz",
            "note_0123456789ABCDEF",       // upper case: not what token_hex makes
            "note_0123456789abcdef/../x",
            "0123456789abcdef",
            "note_0123456789abcdef0$",     // a character hex never has
        )) {
            assertNull("$id was accepted", NoteCapture.jobFromRoute("""{"note_job":"$id"}"""))
        }
        // A short id that is still the PC's shape (8 hex) is accepted: the
        // length is a sanity bound, not a guess at today's token size. The
        // surrounding space is the wire's, not part of the id.
        assertEquals(
            "note_01234567",
            NoteCapture.jobFromRoute("""{"note_job":" note_01234567 "}"""),
        )
    }

    @Test
    fun theRoutesOtherKeysDoNotConfuseIt() {
        val header = """{"injected_ids":["mem:3"],"open_settings":"notes",""" +
            """"note_job":"note_0123456789abcdef","quick":"note_make_waiting"}"""
        assertEquals("note_0123456789abcdef", NoteCapture.jobFromRoute(header))
    }

    // ------------------------------------------------- the ending, in the PC's words

    @Test
    fun aFiledJobSettlesWithTheFileItNames() {
        val said = NoteCapture.settledText(
            job("""{"id":"note_1","state":"filed","target":"obsidian","outcome":"approved",
                    "message":"Filed in Obsidian, 2026-11-02.md.","where":"2026-11-02.md"}"""),
        )
        assertEquals("Filed in Obsidian, 2026-11-02.md.", said)
    }

    @Test
    fun aDeniedOrTimedOutCardSaysNothingWasWritten() {
        assertEquals(
            "You said no, so nothing was written.",
            NoteCapture.settledText(
                job("""{"state":"not_filed","target":"obsidian","outcome":"denied",
                        "message":"You said no, so nothing was written."}"""),
            ),
        )
        assertEquals(
            "Nobody answered the approval card in time, so nothing was written.",
            NoteCapture.settledText(
                job("""{"state":"not_filed","target":"obsidian","outcome":"timed_out",
                        "message":"Nobody answered the approval card in time, so nothing was written."}"""),
            ),
        )
    }

    @Test
    fun aFailedWriteIsSettledWithItsOwnReason() {
        assertEquals(
            "Not filed: the vault is not there.",
            NoteCapture.settledText(
                job("""{"state":"failed","target":"obsidian","message":"Not filed: the vault is not there."}"""),
            ),
        )
    }

    @Test
    fun aJobStillWaitingReplacesNothing() {
        // The whole point: while the card is up, the line must stay as it is.
        assertNull(
            NoteCapture.settledText(
                job("""{"state":"waiting","target":"obsidian","message":"Waiting for your approval."}"""),
            ),
        )
    }

    @Test
    fun aJobWithNoTargetStillUsesItsOwnMessage() {
        // The PC always names the target; a job that does not must still show
        // the PC's sentence rather than a made-up one.
        assertEquals(
            "Filed in Obsidian, 2026-11-02.md.",
            NoteCapture.settledText(job("""{"state":"filed","message":"Filed in Obsidian, 2026-11-02.md."}""")),
        )
    }

    @Test
    fun anAnswerThatNeverSaysWhetherItFiledIsSettledHonestly() {
        val said = NoteCapture.settledText(job("""{"state":"weird","target":"obsidian"}"""))
        assertNotNull("an unknown state is never left claiming to wait", said)
        assertTrue(said!!.contains("did not say whether the note was filed"))
    }

    @Test
    fun givingUpSaysItCouldNotFindOutRatherThanStillWaiting() {
        // A chat line that ran out of time may have been cut off from the PC
        // the whole time: "Still waiting for your approval" is the plate's
        // sentence for a card it SAW waiting, and would be a claim here.
        assertFalse(NoteCapture.UNCONFIRMED.contains("Still waiting"))
        assertTrue(NoteCapture.UNCONFIRMED.startsWith("Could not find out how the note ended."))
        assertTrue(NoteCapture.GAVE_UP.startsWith("Still waiting for your approval."))
        // Losing track says what went wrong, never what happened to the note.
        val lost = NoteCapture.lostTrack("the link went down")
        assertTrue(lost.startsWith("Lost track of the note (the link went down)."))
        assertFalse(lost.contains("Filing"))
        assertFalse(lost.contains("Filed in"))
    }

    // ------------------------------------------------- the one line that changes

    private fun ex(q: String, a: String) = ChatHistory.Exchange(q, a)

    private val waiting = "Waiting for your approval."
    private val filed = "Filed in Obsidian, 2026-11-02.md."

    @Test
    fun onlyThePairThatSaidThoseWordsIsChanged() {
        val thread = listOf(
            ex("hello", "Hi."),
            ex("make a note: buy milk", waiting),
            ex("what's the weather", "Sunny."),
        )
        val out = ChatHistory.settle(thread, "make a note: buy milk", waiting, filed)
        assertEquals(listOf("Hi.", "Sunny."), out.filterIndexed { i, _ -> i != 1 }.map { it.answer })
        assertEquals(filed, out[1].answer)
        assertEquals("make a note: buy milk", out[1].question)
        assertEquals(3, out.size)
    }

    @Test
    fun twoNotesInARowEachSettleTheirOwnLine() {
        // Both waiting answers read exactly the same words: matching the answer
        // alone would let the second note's ending land on the first line.
        val thread = listOf(
            ex("make a note: buy milk", waiting),
            ex("make a note: call Sam", waiting),
        )
        val afterSecond = ChatHistory.settle(thread, "make a note: call Sam", waiting, "Denied.")
        assertEquals(listOf(waiting, "Denied."), afterSecond.map { it.answer })
        val afterFirst = ChatHistory.settle(
            afterSecond, "make a note: buy milk", waiting, "Filed in Obsidian, 2026-11-01.md.",
        )
        assertEquals(
            listOf("Filed in Obsidian, 2026-11-01.md.", "Denied."),
            afterFirst.map { it.answer },
        )
    }

    @Test
    fun aLineThatIsNoLongerThereIsLeftAlone() {
        // A new conversation cleared the chat, or a newer answer replaced it.
        val thread = listOf(ex("make a note: buy milk", "Something else entirely."))
        assertSame(thread, ChatHistory.settle(thread, "make a note: buy milk", waiting, filed))
        // The right words on a DIFFERENT question are not this line.
        assertSame(thread, ChatHistory.settle(thread, "something else", waiting, filed))
        assertTrue(ChatHistory.settle(emptyList(), "q", waiting, filed).isEmpty())
    }

    @Test
    fun settlingTwiceChangesNothingMore() {
        val thread = listOf(ex("make a note: buy milk", waiting))
        val once = ChatHistory.settle(thread, "make a note: buy milk", waiting, filed)
        assertEquals(filed, once[0].answer)
        // The follow of a second reader, or the same job read twice: the old
        // words are gone, so nothing matches and nothing redraws.
        assertSame(once, ChatHistory.settle(once, "make a note: buy milk", waiting, "Denied."))
    }

    @Test
    fun blankOrIdenticalWordsAreNotARewrite() {
        val thread = listOf(ex("make a note: buy milk", waiting))
        assertSame(thread, ChatHistory.settle(thread, "make a note: buy milk", "", filed))
        assertSame(thread, ChatHistory.settle(thread, "make a note: buy milk", waiting, ""))
        assertSame(thread, ChatHistory.settle(thread, "make a note: buy milk", waiting, waiting))
        assertSame(thread, ChatHistory.settle(thread, "", waiting, filed))
    }

    // ------------------------------------------------- the two sides still agree

    /** Walks up from the test's working directory (jarvis-client/) to the repo. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun thePcStillPutsTheJobIdOnTheAnswerAndThePhoneStillReadsThatKey() {
        // The phone's key is [NoteCapture.JOB_ROUTE_KEY]'s, and the PC's half
        // is two lines in the fast path: the id kept from the capture job and
        // the key it is published under. If either is renamed, the chat goes
        // back to claiming to wait for ever - silently - so it is pinned here
        // as well as in backend/test_note_and_vault_asking.py.
        val pc = repoFile("backend/jarvis_quick.py").readText()
        assertTrue(
            "the PC no longer publishes the note job id on the answer's route",
            pc.contains("""out["${NoteCapture.JOB_ROUTE_KEY}"] = res.note_job"""),
        )
        assertTrue(
            "the waiting answer no longer keeps the capture job's id",
            pc.contains("""note_job=str(body.get("id") or "").strip() or None"""),
        )
        // The id the PC names is the one this file reads, and `capture` is
        // what makes it: the job record's own "id" field.
        val capture = repoFile("backend/jarvis_note_capture.py").readText()
        assertTrue(
            "the capture job no longer carries the id the phone asks about",
            capture.contains("\"id\": job_id"),
        )
        assertEquals("note_job", NoteCapture.JOB_ROUTE_KEY)
    }
}
