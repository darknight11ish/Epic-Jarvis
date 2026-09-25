package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Briefing
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Schedule
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The morning briefing on the phone (docs/JARVIS-API.md section 22;
 * net/Briefing.kt): reading the PC's answer, hiding its lines (the counts
 * stay), the scheduler's rule for setting one up - never "every N hours",
 * never a list - the notification only when the briefing is READY, and a
 * briefing job's title in Coming up.
 */
class BriefingTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private val answer = obj(
        """{"available":true,"building":false,
          "briefing":{"id":"b0123456789","heading":"Your briefing for Friday 25 September, made at 07:00.",
            "made":1790000000,"missed":"missed at 07:00","private":true,
            "sections":[{"key":"calendar","title":"Calendar","state":"ok","summary":"1 event today.",
                         "items":["09:30 Dentist"]},
                        {"key":"todo","title":"To-do list","state":"ok","summary":"2 open items.",
                         "items":["buy milk","post the letter"]}],
            "not_included":["Not included: your calendar is not set up for Jarvis on this PC."]},
          "setups":[{"id":"s00000000b1","kind":"briefing","state":"waiting","repeats":true,
                     "repeat":"every weekday (Monday to Friday) at 07:00"},
                    {"id":"all","kind":"briefing"}],
          "sources":{"calendar":{"state":"on","said":"Included: your calendar."},
                     "weather":{"state":"not_available","said":"x"}}}""",
    )

    @Test
    fun theAnswerIsReadAndARowWithoutARealIdIsDropped() {
        val v = Briefing.parse(answer)!!
        val b = v.briefing!!
        assertEquals(2, b.sections.size)
        assertEquals(listOf("09:30 Dentist"), b.sections[0].items)
        assertEquals(listOf("s00000000b1"), v.setups.map { it.id })
        assertEquals(listOf("Included: your calendar.", "x"), v.sources)
        assertNull(Briefing.parse(obj("""{"ok":true}""")))
        val none = Briefing.parse(obj("""{"available":true,"briefing":null,"setups":[]}"""))!!
        assertNull(none.briefing)
    }

    @Test
    fun hidingTakesEveryLineOutAndKeepsTheCounts() {
        val hidden = Briefing.hide(Briefing.parse(answer)!!)
        val b = hidden.briefing!!
        assertTrue(b.hidden)
        assertTrue(b.sections.all { it.items.isEmpty() })
        assertEquals("1 event today.", b.sections[0].summary)
        assertFalse(b.toString().contains("Dentist"))
    }

    @Test
    fun aLateBriefingAndASetupSayWhatTheyAre() {
        val v = Briefing.parse(answer)!!
        assertEquals("(Due at 07:00 - the PC was off or asleep, so it is late.)", Briefing.lateLine(v.briefing!!))
        assertEquals(
            "every weekday (Monday to Friday) at 07:00 - waiting for your yes on the approval card",
            Briefing.setupLine(v.setups[0]),
        )
    }

    @Test
    fun aSetupIsOneOfTheSchedulersRulesAndNothingElse() {
        assertEquals(
            """{"kind":"briefing","repeat":{"every":"weekday","at":"07:00"}}""",
            Briefing.setupBody("weekday", "7:00"),
        )
        assertEquals(
            """{"kind":"briefing","repeat":{"every":"week","at":"08:30","days":[0,4]}}""",
            Briefing.setupBody("week", "08:30", listOf(4, 0, 4)),
        )
        assertNull(Briefing.setupBody("week", "08:30", emptyList()))
        assertNull(Briefing.setupBody("week", "08:30", listOf(7)))
        for (bad in listOf("hours", "all", "", "month")) assertNull(bad, Briefing.setupBody(bad, "07:00"))
        for (bad in listOf("24:00", "7", "07:60", "", "07:00:00")) assertNull(bad, Briefing.setupBody("day", bad))
    }

    @Test
    fun theNotificationComesWhenTheBriefingIsReadyNotWhenItsTimeComes() {
        assertEquals("s00000000b1", Briefing.readyFrom(obj("""{"id":"s00000000b1","kind":"briefing","state":"ready"}""")))
        assertNull(Briefing.readyFrom(obj("""{"id":"s00000000b1","kind":"briefing","state":"fired"}""")))
        assertNull(Briefing.readyFrom(obj("""{"id":"s00000000b1","kind":"reminder","state":"ready"}""")))
        assertNull(Briefing.readyFrom(obj("""{"id":"all","kind":"briefing","state":"ready"}""")))
        assertTrue(Briefing.isAbout(obj("""{"id":"s00000000b1","kind":"briefing","state":"fired"}""")))
        assertFalse(Briefing.isAbout(obj("""{"id":"s00000000b1","kind":"timer","state":"fired"}""")))
        assertEquals("Jarvis: your morning briefing is ready.", Briefing.LOCK_SCREEN)
        assertTrue(Briefing.missing(ApiError.NotFound))
    }

    @Test
    fun inComingUpABriefingJobIsCalledMorningBriefing() {
        val job = Schedule.parse(
            obj("""{"jobs":[{"id":"s00000000b1","kind":"briefing","text":"","state":"active","repeats":true,
                 "repeat":"every day at 07:00","when":"07:00 tomorrow"}],"todo":[]}"""),
        )!!.jobs.single()
        assertEquals("Morning briefing", Schedule.titleOf(job))
        assertEquals("Morning briefing", Schedule.title("briefing"))
        assertEquals("Jarvis: your morning briefing is ready.", Schedule.lockScreen("briefing"))
        assertEquals("briefing", Schedule.tag("briefing"))
    }
}
