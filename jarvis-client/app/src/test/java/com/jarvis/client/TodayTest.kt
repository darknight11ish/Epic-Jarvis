package com.jarvis.client

import com.jarvis.client.net.Briefing
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Schedule
import com.jarvis.client.net.Today
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

/**
 * Today cards on the phone (docs/JARVIS-API.md section 82; net/Today.kt) -
 * the desktop's today.js, word for word: which cards show today and which
 * later, the briefing's parts (only a briefing made today, never news or
 * "What did I miss?"), the words hidden with the private lists, and the one
 * body a new card sends.
 */
class TodayTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private val list = obj(
        """{"available":true,"jobs":[
          {"id":"s0000000d02","kind":"today","text":"Bins out","state":"active","repeats":true,
           "today":"later","shows_at":"18:00"},
          {"id":"s0000000d01","kind":"today","text":"Gym bag","state":"active","repeats":true,
           "today":"showing","shows_at":"07:00"},
          {"id":"s0000000d03","kind":"today","text":"Water the plants","state":"active",
           "today":"","shows_at":"08:00"},
          {"id":"s0000000001","kind":"reminder","text":"call Mum","state":"active"}],
          "todo":[]}""",
    )

    @Test
    fun onlyTodaysCardsAreOnThePageAndLaterOnesAreApart() {
        val (showing, later) = Today.todayCards(Today.cardsOf(Schedule.parse(list)))
        assertEquals(listOf("Gym bag"), showing.map { it.text })
        assertEquals(listOf("Bins out"), later.map { it.text })
        assertEquals("From 07:00", Today.cardMeta(showing.single()))
        assertEquals("today card", Schedule.tag("today"))
    }

    @Test
    fun theWordsAreHiddenWithThePrivateListsButTheTimesStay() {
        val hidden = Schedule.hide(Schedule.parse(list)!!)
        val (showing, _) = Today.todayCards(Today.cardsOf(hidden))
        assertEquals("(hidden) today card", Today.cardTitle(showing.single()))
        assertEquals("From 07:00", Today.cardMeta(showing.single()))
        assertEquals(Schedule.TODAY_CARD_TITLE, Schedule.titleOf(hidden.jobs.first { it.kind == "today" }))
    }

    private val zone = ZoneId.of("UTC")
    private val now = 1_790_000_000_000L

    private fun brief(made: Double, source: String = "schedule") = Briefing.parse(obj(
        """{"available":true,"building":false,"setups":[],"sources":{},"briefing":{
          "id":"b0123456789","source":"$source","heading":"h","made":$made,"missed":"",
          "sections":[
            {"key":"weather","title":"Weather","state":"ok","summary":"Now 12 °C.","items":[]},
            {"key":"calendar","title":"Calendar","state":"ok","summary":"2 events today.","items":["09:30 Dentist"]},
            {"key":"todo","title":"To-do list","state":"ok","summary":"1 open item.","items":["milk"]},
            {"key":"email","title":"Email","state":"ok","summary":"3 unread emails.","items":["From Alex"]},
            {"key":"news","title":"News feeds","state":"ok","summary":"2 headlines.","items":["x"]}],
          "not_included":[]}}""",
    ))

    @Test
    fun theBriefingsPartsOnlyFromOneMadeTodayAndNeverNews() {
        val parts = Today.briefingCards(brief(now / 1000.0 - 60), now, zone)!!
        assertEquals(listOf("weather", "calendar", "email"), parts.map { it.key })
        assertNull(Today.briefingCards(brief(now / 1000.0 - 3 * 86400), now, zone))
        assertNull(Today.briefingCards(brief(now / 1000.0 - 60, "missed"), now, zone))
        val hidden = Today.briefingCards(Briefing.hide(brief(now / 1000.0 - 60)!!), now, zone)!!
        assertTrue(hidden.all { it.items.isEmpty() })
        assertFalse(Today.madeToday(null, now, zone))
    }

    @Test
    fun aNewCardIsOneBodyInBothAppsWords() {
        assertEquals(
            "{\"kind\":\"today\",\"text\":\"Gym bag\",\"repeat\":{\"every\":\"week\",\"at\":\"07:05\",\"days\":[0,2]}}",
            Today.addBody("  Gym   bag ", "7:05", setOf(2, 0, 9)).first,
        )
        assertEquals(
            "{\"kind\":\"today\",\"text\":\"Bins\",\"repeat\":{\"every\":\"day\",\"at\":\"18:00\"}}",
            Today.addBody("Bins", "18:00", (0..6).toSet()).first,
        )
        assertTrue(Today.addBody("Pills", "08:00", setOf(0, 1, 2, 3, 4)).first!!.contains("\"weekday\""))
        assertTrue(Today.addBody("a \"quote\"", "08:00", setOf(0)).first!!.contains("a \\\"quote\\\""))
        assertEquals(Today.NO_WORDS, Today.addBody("  ", "07:00", setOf(0)).second)
        assertEquals(Today.TOO_LONG, Today.addBody("x".repeat(Today.MAX_TEXT + 1), "07:00", setOf(0)).second)
        assertEquals(Today.BAD_TIME, Today.addBody("Gym", "7pm", setOf(0)).second)
        assertEquals(Today.NO_DAYS, Today.addBody("Gym", "07:00", emptySet()).second)
    }
}
