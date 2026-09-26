package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Briefing
import com.jarvis.client.net.DesktopWrite
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
        for (bad in listOf("24:00", "07:60", "", "07:00:00", "7:0", "2400")) assertNull(bad, Briefing.setupBody("day", bad))
        // A number pad has no colon.
        for ((typed, at) in listOf("7" to "07:00", "730" to "07:30", "0730" to "07:30", "2330" to "23:30")) {
            assertEquals(typed, """{"kind":"briefing","repeat":{"every":"day","at":"$at"}}""",
                Briefing.setupBody("day", typed))
        }
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

    // "Show who new emails are from" (the owner's decision of 2026-09-25):
    // on by default, OFF at once, ON through ONE approval card on the PC.

    @Test
    fun theSendersAreLinesSoHidingTakesThemOutAndTheCountStays() {
        val v = Briefing.parse(
            obj(
                """{"available":true,"briefing":{"id":"b0123456789","heading":"h","sections":[
                  {"key":"email","title":"Email","state":"ok","summary":"3 unread emails.",
                   "items":["From Alex, Your Bank and GitHub"]}]},"setups":[],
                  "senders":{"on":true,"waiting":false,"last":null,"why":""}}""",
            ),
        )!!
        assertEquals(listOf("From Alex, Your Bank and GitHub"), v.briefing!!.sections[0].items)
        val hidden = Briefing.hide(v).briefing!!
        assertTrue(hidden.sections[0].items.isEmpty())
        assertEquals("3 unread emails.", hidden.sections[0].summary)
        assertFalse(hidden.toString().contains("Alex"))
        assertTrue(v.senders!!.on)
    }

    @Test
    fun theSendersSwitchHoldsOnOnAStaleLinkAndNeverOff() {
        val on = Briefing.Senders(on = true, waiting = false, last = "", lastOutcome = "", why = "")
        val off = on.copy(on = false)
        assertTrue(Briefing.sendersView(on, live = false).canChange)
        assertFalse(Briefing.sendersView(off, live = false).canChange)
        assertTrue(Briefing.sendersView(off, live = true).canChange)
        val waiting = Briefing.sendersView(off.copy(waiting = true), live = false)
        assertTrue(waiting.checked)
        assertTrue(waiting.canChange)
        assertEquals(listOf(Briefing.SENDERS_WAITING), waiting.lines)
        val denied = Briefing.sendersView(
            off.copy(last = "The card was turned down, so the briefing shows the number only.", lastOutcome = "denied"),
            live = true,
        )
        assertEquals(listOf("The card was turned down, so the briefing shows the number only."), denied.lines)
        val approved = Briefing.sendersView(on.copy(last = "You approved the card.", lastOutcome = "enabled"), live = true)
        assertTrue(approved.lines.isEmpty())
        val older = Briefing.sendersView(null, live = true)
        assertFalse(older.show)
        assertEquals(listOf(Briefing.SENDERS_MISSING), older.lines)
        assertNull(Briefing.parse(obj("""{"available":true,"briefing":null}"""))!!.senders)
        assertNull(Briefing.parse(obj("""{"available":true,"briefing":null,"senders":{"on":"yes"}}"""))!!.senders)
        val damaged = Briefing.parse(
            obj("""{"available":true,"briefing":null,"senders":{"on":false,"waiting":false,"why":"the file is damaged"}}"""),
        )!!.senders
        assertEquals(listOf("The file is damaged."), Briefing.sendersView(damaged, live = true).lines)
    }

    @Test
    fun theSendersBodyAndWhatIsSaidAfter() {
        assertEquals("""{"enabled":true}""", Briefing.sendersBody(true))
        assertEquals("""{"enabled":false}""", Briefing.sendersBody(false))
        assertEquals(
            "Waiting for your approval.",
            Briefing.sendersSaid(true, DesktopWrite.Outcome.Waiting("Waiting for your approval.")),
        )
        assertEquals(Briefing.SENDERS_WAITING, Briefing.sendersSaid(true, DesktopWrite.Outcome.Waiting(null)))
        assertEquals("Not changed. No.", Briefing.sendersSaid(true, DesktopWrite.Outcome.Refused("No.")))
        assertEquals(
            "Done - the briefing shows the number only.",
            Briefing.sendersSaid(false, DesktopWrite.Outcome.Done(null)),
        )
        assertEquals("/api/briefing/senders", Briefing.SENDERS_PATH)
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

    // "What did I miss?" (2026-09-25): the desktop's briefing.js says the
    // same; its tests/briefing.mjs checks these words are in Briefing.kt.
    @Test
    fun whatDidIMissIsReadOnlyFromAPcThatKnowsIt() {
        val missed = JarvisJson.parseToJsonElement(
            """{"ok":true,"briefing":{"id":"b00000000m1","source":"missed",
               "heading":"What you missed since 14:05 today, when you last talked to Jarvis.",
               "sections":[{"key":"went_off","title":"Went off","state":"ok","summary":"1 reminder went off.",
                            "items":["15:00 call the bank"]}],"not_included":[]}}""",
        ) as kotlinx.serialization.json.JsonObject
        val v = Briefing.readMissed(missed)!!
        org.junit.Assert.assertEquals("missed", v.briefing!!.source)
        org.junit.Assert.assertEquals(emptyList<String>(), Briefing.hide(v).briefing!!.sections.single().items)
        val older = JarvisJson.parseToJsonElement(
            """{"ok":true,"briefing":{"id":"b00000000b1","source":"now","heading":"Your briefing","sections":[]}}""",
        ) as kotlinx.serialization.json.JsonObject
        org.junit.Assert.assertNull(Briefing.readMissed(older))
        org.junit.Assert.assertEquals("{\"missed\":true}", Briefing.MISSED_BODY)
        org.junit.Assert.assertEquals("What did I miss?", Briefing.MISSED_LABEL)
    }
}
