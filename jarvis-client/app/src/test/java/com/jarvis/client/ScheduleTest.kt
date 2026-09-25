package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Schedule
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Coming up" on the phone (docs/JARVIS-API.md section 21; net/Schedule.kt):
 * reading the PC's list, the rows' lines and buttons - the desktop's
 * coming-up.js, word for word - ONE job per change and never "all", the
 * notification's words (only the kind while a lock is on), and the "Done"
 * line under an answer made without the model.
 */
class ScheduleTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private val list = obj(
        """{"available":true,"jobs":[
          {"id":"s0000000001","kind":"timer","text":"pasta","state":"active","left":600,"duration":600},
          {"id":"s0000000002","kind":"alarm","text":"","state":"active","when":"07:00 tomorrow"},
          {"id":"s0000000003","kind":"reminder","text":"take my pills","state":"active","repeats":true,
           "repeat":"every weekday (Monday to Friday) at 07:00","when":"07:00 on Monday"},
          {"id":"s0000000004","kind":"reminder","text":"stretch","state":"waiting","repeats":true,
           "repeat":"every 2 hours"},
          {"id":"all","kind":"timer"}, {"kind":"timer"}],
          "todo":[{"id":"s0000000005","kind":"todo","text":"buy milk","state":"active"}]}""",
    )

    @Test
    fun theListIsReadAndARowWithoutARealIdIsDropped() {
        val v = Schedule.parse(list)!!
        assertEquals(4, v.jobs.size)
        assertEquals(listOf("s0000000001", "s0000000002", "s0000000003", "s0000000004"), v.jobs.map { it.id })
        assertEquals("buy milk", v.todo.single().text)
        assertNull(Schedule.parse(obj("""{"ok":true}""")))
        assertNull(Schedule.parse(obj("""{"jobs":[]}""")))
    }

    @Test
    fun eachRowSaysWhatTheDesktopSays() {
        val v = Schedule.parse(list)!!
        assertEquals("pasta timer", Schedule.titleOf(v.jobs[0]))
        assertEquals(listOf("9:58 left"), Schedule.metaOf(v.jobs[0], 2000))
        assertEquals("Alarm", Schedule.titleOf(v.jobs[1]))
        assertEquals(listOf("07:00 tomorrow"), Schedule.metaOf(v.jobs[1]))
        assertEquals(
            listOf("every weekday (Monday to Friday) at 07:00", "next: 07:00 on Monday"),
            Schedule.metaOf(v.jobs[2]),
        )
        assertEquals(listOf("every 2 hours", Schedule.WAITING), Schedule.metaOf(v.jobs[3]))
        assertEquals(listOf("pause", "delete"), Schedule.actionsOf(v.jobs[0]))
        assertEquals(listOf("delete"), Schedule.actionsOf(v.jobs[3]))
        assertEquals(listOf("done", "delete"), Schedule.actionsOf(v.todo[0]))
        assertEquals("9:58", Schedule.countdown(598.0))
        assertEquals("1:02:03", Schedule.countdown(3723.0))
        assertEquals("0:00", Schedule.countdown(-4.0))
        assertEquals("1 hour 30 minutes", Schedule.lengthWords(5400.0))
        assertTrue(Schedule.anyTicking(v))
    }

    @Test
    fun oneJobPerChangeAndNeverAll() {
        assertEquals("""{"id":"s0000000001","do":"delete"}""", Schedule.actBody("s0000000001", "delete"))
        for (bad in listOf("all", "*", "", "s000000000", "S0000000001", "s0000000001,s0000000002")) {
            assertNull(bad, Schedule.actBody(bad, "delete"))
        }
        for (bad in listOf("delete_all", "clear", "approve", "")) {
            assertNull(bad, Schedule.actBody("s0000000001", bad))
        }
        assertEquals("""{"kind":"todo","text":"buy \"oat\" milk"}""", Schedule.todoBody("  buy  \"oat\"   milk "))
        assertNull(Schedule.todoBody("   "))
        assertNull(Schedule.todoBody("x".repeat(Schedule.MAX_TEXT + 1)))
    }

    @Test
    fun theReplyIsReadInThePcsWords() {
        assertEquals(true to "Paused.", Schedule.said(Schedule.Reply(200, obj("""{"ok":true,"said":"Paused."}"""))))
        assertEquals(true to Schedule.ALREADY_GONE,
            Schedule.said(Schedule.Reply(404, obj("""{"ok":false,"reason":"no_such_job"}"""))))
        assertEquals(false to Schedule.TOO_OLD, Schedule.said(Schedule.Reply(404, null)))
        assertEquals(false to "Only a to-do item can be marked done.",
            Schedule.said(Schedule.Reply(409, obj("""{"ok":false,"error":"Only a to-do item can be marked done."}"""))))
        assertEquals(true to "Added to your to-do list.",
            Schedule.said(Schedule.Reply(200, obj("""{"ok":true,"job":{"id":"s0000000009"}}"""))))
    }

    @Test
    fun aNotificationShowsTheWordsOnlyWhenNothingIsLocked() {
        val job = Schedule.parseOne(obj(
            """{"job":{"id":"s0000000003","kind":"reminder","text":"call Mum","state":"fired",
               "lock_screen":"Jarvis: a reminder is due.","missed":"missed at 07:00","fired_at":1.0}}""",
        ))
        assertEquals("Reminder" to "call Mum (missed at 07:00 - the PC was off or asleep.)",
            Schedule.notification("reminder", job, private = false))
        val locked = Schedule.notification("reminder", job, private = true)
        assertEquals("Reminder" to "Jarvis: a reminder is due.", locked)
        assertFalse(locked.second.contains("Mum"))
        assertEquals("Timer done" to "Jarvis: your timer is done.", Schedule.notification("timer", null, false))
        assertEquals(
            "s0000000001" to "timer",
            Schedule.firedFrom(obj("""{"id":"s0000000001","kind":"timer","state":"fired","late":false}""")),
        )
        assertNull(Schedule.firedFrom(obj("""{"id":"s0000000001","kind":"timer","state":"changed"}""")))
        assertNull(Schedule.firedFrom(obj("""{"id":"all","kind":"timer","state":"fired"}""")))
    }

    @Test
    fun hiddenListsKeepTheTimesButNotTheWords() {
        val v = Schedule.hide(Schedule.parse(list)!!)
        assertEquals("(hidden) timer", Schedule.titleOf(v.jobs[0]))
        assertEquals("(hidden)", Schedule.titleOf(v.jobs[2]))
        assertEquals(listOf("07:00 tomorrow"), Schedule.metaOf(v.jobs[1]))
        assertTrue(v.todo.all { it.text.isEmpty() })
    }

    @Test
    fun anAnswerMadeWithoutTheModelSaysDone() {
        assertTrue(Schedule.quickFromRouteHeader("""{"where":"local","quick":"timer_set"}"""))
        assertFalse(Schedule.quickFromRouteHeader("""{"where":"local","lane":"qwen3:8b"}"""))
        assertFalse(Schedule.quickFromRouteHeader(null))
        assertFalse(Schedule.quickFromRouteHeader("not json"))
        assertEquals("Done - answered on this PC without the AI model.", Schedule.DONE_LINE)
    }

    // The standby schedule (backend jarvis_standby_schedule.py, 2026-09-25):
    // the desktop's coming-up.js says the same, and its tests/coming-up.mjs
    // checks these words are in Schedule.kt.

    @Test
    fun theStandbyScheduleIsItsOwnRowWithHowItLastWent() {
        val v = Schedule.parse(
            obj(
                """{"jobs":[{"id":"s00000000aa","kind":"standby","text":"","state":"active",
                  "repeats":true,"repeat":"every day from 01:00 to 07:00",
                  "when":"awake at 07:00 today, if the schedule put it on standby","note":"Went on standby at 01:00.",
                  "notify":false}],"todo":[]}""",
            ),
        )!!
        val job = v.jobs.single()
        assertEquals(Schedule.STANDBY_TITLE, Schedule.titleOf(job))
        assertEquals(Schedule.STANDBY_TITLE, Schedule.titleOf(Schedule.hide(v).jobs.single()))
        assertEquals(
            listOf(
                "every day from 01:00 to 07:00",
                "next: awake at 07:00 today, if the schedule put it on standby",
                "Went on standby at 01:00.",
            ),
            Schedule.metaOf(job),
        )
        assertEquals(listOf("pause", "delete"), Schedule.actionsOf(job))
        assertEquals("s00000000aa", Schedule.standbyOf(v)?.id)
        assertNull(Schedule.standbyOf(Schedule.parse(list)))
    }

    @Test
    fun aStandbyScheduleIsTwoTimesAndNothingElse() {
        assertEquals("01:00" to "07:00", Schedule.standbyTimes("1:00", "07:00"))
        assertEquals("23:30" to "06:05", Schedule.standbyTimes(" 23:30 ", "06:05"))
        for ((a, b) in listOf("01:00" to "01:00", "24:00" to "07:00", "01:60" to "07:00",
            "1" to "07:00", "" to "", "01:00" to "7:0", "-1:00" to "07:00")) {
            assertNull("$a $b", Schedule.standbyTimes(a, b))
            assertNull("$a $b", Schedule.standbyBody(a, b))
        }
        val body = obj(Schedule.standbyBody("1:00", "07:00")!!)
        assertEquals(
            obj("""{"kind":"standby","repeat":{"every":"day","at":"01:00","until":"07:00"}}"""),
            body,
        )
    }

    @Test
    fun aKindThatNotifiesNobodyShowsNoNotification() {
        assertNull(
            Schedule.firedFrom(obj("""{"id":"s00000000aa","kind":"standby","state":"fired","notify":false}""")),
        )
        assertEquals(
            "s0000000001" to "timer",
            Schedule.firedFrom(obj("""{"id":"s0000000001","kind":"timer","state":"fired","late":false}""")),
        )
    }
}
