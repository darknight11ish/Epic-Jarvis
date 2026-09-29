package com.jarvis.client

import com.jarvis.client.net.AlsoOnPhone
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PhotoReminder
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

/**
 * "Photo to reminder" (JARVIS-API.md section 83; net/PhotoReminder.kt): the
 * PC's proposal read safely, a picture sent only as a data: address, the
 * tap's ONE one-off reminder in the owner's words (never a repeat, and no
 * words from a picture can add a key), and "Also on my phone" as a calendar
 * event at the boxes' time.
 */
class PhotoReminderTest {
    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json) as JsonObject

    private val flyer = obj(
        """{"ok":true,"outside":true,"text":"Summer fair, Sat 12 Oct, 2pm","said":"x",
        "found":[{"title":"Summer fair","date":"2026-10-12","time":"14:00","time_found":true,
        "passed":false,"when":"Monday 12 October at 14:00"}]}""",
    )

    @Test
    fun aFlyerIsReadIntoOneProposal() {
        val out = PhotoReminder.parse(200, flyer) as PhotoReminder.Outcome.Ok
        assertEquals(1, out.scan.found.size)
        val f = out.scan.found[0]
        assertEquals("Summer fair", f.title)
        assertEquals("2026-10-12", f.date)
        assertEquals("14:00", f.time)
        assertEquals(PhotoReminder.FOUND_ONE, out.scan.said)
        assertNull(PhotoReminder.hint(f))
        // The words never show up in a log line.
        assertTrue("Summer" !in out.scan.toString())
    }

    @Test
    fun nothingFoundAndNoWordsAreSaidPlainly() {
        val none = PhotoReminder.parse(200, obj("""{"ok":true,"text":"Seven dwarves","found":[]}"""))
        assertEquals(PhotoReminder.NOTHING_FOUND, (none as PhotoReminder.Outcome.Ok).scan.said)
        val empty = PhotoReminder.parse(200, obj("""{"ok":true,"text":"","found":[]}"""))
        assertEquals(PhotoReminder.NO_WORDS, (empty as PhotoReminder.Outcome.Ok).scan.said)
    }

    @Test
    fun theProposalIsCappedAndABadDateDropped() {
        val many = obj(
            """{"ok":true,"text":"x","found":[""" +
                (1..5).joinToString(",") { """{"title":"E$it","date":"2026-10-0$it","time":"10:00"}""" } +
                """,{"title":"bad","date":"12/10","time":"10:00"}]}""",
        )
        val out = PhotoReminder.parse(200, many) as PhotoReminder.Outcome.Ok
        assertEquals(PhotoReminder.MAX_FOUND, out.scan.found.size)
        assertEquals(PhotoReminder.foundMany(3), out.scan.said)
    }

    @Test
    fun noTimeAndAPassedTimeAreSaid() {
        val f = PhotoReminder.Found("x", "2026-10-12", "09:00", timeFound = false, passed = true, whenWords = "")
        assertEquals(PhotoReminder.NO_TIME + " " + PhotoReminder.PASSED, PhotoReminder.hint(f))
    }

    @Test
    fun aPcWithoutTheRouteOrAFailedReadSaysSo() {
        assertEquals(PhotoReminder.MISSING, (PhotoReminder.parse(404, null) as PhotoReminder.Outcome.Failed).why)
        val failed = PhotoReminder.parse(503, obj("""{"ok":false,"error":"Windows could not read the words in the picture."}"""))
        assertEquals("Windows could not read the words in the picture.", (failed as PhotoReminder.Outcome.Failed).why)
    }

    @Test
    fun onlyAPictureAsADataAddressIsSent() {
        assertNotNull(PhotoReminder.scanBody("data:image/jpeg;base64,AAAA"))
        assertNull(PhotoReminder.scanBody("https://example.com/flyer.jpg"))
        assertNull(PhotoReminder.scanBody("content://media/external/images/1"))
        assertNull(PhotoReminder.scanBody("data:text/html;base64,PGgxPg=="))
    }

    @Test
    fun theTapSendsOneOneOffReminderInTheOwnersWords() {
        val body = obj(PhotoReminder.reminderBody("Summer fair", "2026-10-12", "9:05")!!)
        assertEquals(setOf("kind", "date", "time", "text"), body.keys)
        assertEquals("reminder", (body["kind"] as JsonPrimitive).content)
        assertEquals("09:05", (body["time"] as JsonPrimitive).content)
        // Words from a picture cannot add a key: they are one escaped string.
        val sneaky = obj(PhotoReminder.reminderBody("a\",\"repeat\":{\"every\":\"day\"},\"x\":\"", "2026-10-12", "14:00")!!)
        assertEquals(setOf("kind", "date", "time", "text"), sneaky.keys)
    }

    @Test
    fun badBoxesAreSaidAndNothingIsSent() {
        assertEquals(PhotoReminder.BAD_DATE, PhotoReminder.problem("x", "12/10/2026", "14:00"))
        assertEquals(PhotoReminder.BAD_DATE, PhotoReminder.problem("x", "2026-02-31", "14:00"))
        assertEquals(PhotoReminder.BAD_TIME, PhotoReminder.problem("x", "2026-10-12", "2pm"))
        assertEquals(PhotoReminder.NO_TEXT, PhotoReminder.problem("  ", "2026-10-12", "14:00"))
        assertNull(PhotoReminder.reminderBody("  ", "2026-10-12", "14:00"))
    }

    @Test
    fun alsoOnMyPhoneIsACalendarEventAtTheBoxesTime() {
        val offer = PhotoReminder.calendarOffer("Summer fair", "2026-10-12", "14:00", ZoneId.of("UTC"))
            as AlsoOnPhone.Offer.ToCalendar
        // 2026-10-12 14:00 UTC.
        assertEquals(1_791_813_600_000L, offer.event.beginMs)
        assertEquals(AlsoOnPhone.EVENT_MINUTES * 60_000L, offer.event.endMs - offer.event.beginMs)
        assertEquals("Summer fair", offer.event.title)
        assertNull(offer.event.rrule)
        assertNull(PhotoReminder.calendarOffer("x", "bad", "14:00"))
    }
}
