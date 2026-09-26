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

    // Snooze and named lists (2026-09-25): the desktop's coming-up.js says the
    // same, and its tests/coming-up.mjs checks these words are in Schedule.kt.

    private val quickWins = obj(
        """{"jobs":[{"id":"s00000000c2","kind":"alarm","text":"","state":"active","snoozed":true,
              "when":"07:10 today"}],
            "todo":[{"id":"s00000000d1","kind":"todo","text":"milk","state":"active","list":"shopping"},
                    {"id":"s00000000d2","kind":"todo","text":"eggs","state":"active","list":"shopping"},
                    {"id":"s00000000d3","kind":"todo","text":"post the letter","state":"active","list":""}],
            "went_off":[{"id":"s00000000c1","kind":"alarm","text":"","state":"fired","went_off_at":"07:00",
                         "missed":"missed at 07:00","fired_at":1.0}],
            "lists":[{"name":"shopping","title":"Shopping list","open":2},{"name":"empty","open":0}]}""",
    )

    @Test
    fun whatWentOffAndTheNamedListsAreRead() {
        val v = Schedule.parse(quickWins)!!
        assertEquals(listOf("s00000000c1"), v.wentOff.map { it.id })
        assertEquals(listOf("Went off at 07:00 (late - the PC was off or asleep)"), Schedule.wentOffMeta(v.wentOff[0]))
        assertEquals("alarm, snoozed", Schedule.tagOf(v.jobs[0]))
        assertEquals(listOf("post the letter"), Schedule.todoItems(v).map { it.text })
        val lists = Schedule.namedLists(v)
        assertEquals(1, lists.size)
        assertEquals("Shopping list", lists[0].title)
        assertEquals(listOf("milk", "eggs"), lists[0].items.map { it.text })
        val old = Schedule.parse(list)!!
        assertTrue(old.wentOff.isEmpty() && old.lists.isEmpty())
    }

    @Test
    fun snoozeIsOneJobTenMinutesAndClearingNamesOneListAndItsCount() {
        assertEquals("""{"id":"s0000000001","do":"snooze","seconds":600}""", Schedule.actBody("s0000000001", "snooze"))
        assertNull(Schedule.actBody("all", "snooze"))
        assertEquals(listOf("snooze"), Schedule.WENT_OFF_ACTIONS)
        assertEquals("Snooze 10 minutes", Schedule.labelOf("snooze"))
        assertEquals("""{"do":"clear_list","list":"shopping","count":3}""", Schedule.clearListBody("shopping", 3))
        for (bad in listOf("", "*", "Shopping", "a b c d", "shop,ping")) {
            assertNull(bad, Schedule.clearListBody(bad, 1))
        }
        assertNull(Schedule.clearListBody("shopping", 0))
        assertEquals("""{"kind":"todo","text":"milk","list":"shopping"}""", Schedule.todoBody("milk", "shopping"))
        assertNull(Schedule.todoBody("milk", "Shopping"))
        assertEquals(
            "Clear the shopping list? This deletes all 3 items on it, and cannot be undone.",
            Schedule.clearListQuestion("Shopping list", 3),
        )
        assertEquals(
            "Clear the packing list? This deletes all 1 item on it, and cannot be undone.",
            Schedule.clearListQuestion("Packing list", 1),
        )
        assertEquals("Add to the shopping list", Schedule.addPlaceholder("Shopping list"))
        assertEquals("Add to the to-do list", Schedule.addPlaceholder("To-do list"))
    }

    @Test
    fun hiddenListsHideTheListNamesButKeepTheGrouping() {
        val v = Schedule.hide(Schedule.parse(quickWins)!!)
        val lists = Schedule.namedLists(v)
        assertEquals(Schedule.HIDDEN_LIST_TITLE, lists.single().title)
        assertEquals(2, lists.single().items.size)
        assertTrue(v.todo.none { it.list == "shopping" })
        assertTrue(v.lists.none { it.name == "shopping" || it.title.isNotEmpty() })
        assertTrue(v.wentOff.all { it.text.isEmpty() })
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

    private val tellme = obj(
        """{"id":"s00000000bb","kind":"tellme","text":"an email from Alex arrives","state":"active",
          "repeats":true,"repeat":"every 5 minutes","when":"12:05 today","urgent":true,
          "note":"Until Sunday 25 October at 12:00, or the first time it happens. Urgent: rings until you look.",
          "alert":"An email from Alex arrived.","alert_at":1790334600.0,
          "lock_screen":"Jarvis: something you asked to be told about happened."}""",
    )

    @Test
    fun aTellMeWhenRowSaysWhatIsWatchedHowOftenAndThatItIsUrgent() {
        val j = Schedule.job(tellme)!!
        assertEquals("When an email from Alex arrives", Schedule.titleOf(j))
        assertEquals("tell me when, urgent", Schedule.tagOf(j))
        assertEquals("tell me when", Schedule.tagOf(j.copy(urgent = false)))
        assertEquals(listOf("Looks every 5 minutes", j.note), Schedule.metaOf(j))
        assertEquals(listOf("Looks every 5 minutes", "Paused", j.note), Schedule.metaOf(j.copy(state = "paused")))
        assertEquals(listOf("pause", "delete"), Schedule.actionsOf(j))
        val hidden = Schedule.hide(Schedule.View(listOf(j), emptyList(), false)).jobs.single()
        assertEquals(Schedule.TELLME_TITLE, Schedule.titleOf(hidden))
        assertEquals("", hidden.alert)
        assertEquals(1790334600.0, j.alertAt!!, 0.0)
        // A repeating reminder's tag is unchanged.
        val v = Schedule.parse(list)!!
        assertEquals("reminder, repeats", Schedule.tagOf(v.jobs[2]))
    }

    @Test
    fun aMatchNotifiesTheAlertAndOnlyTheGenericWordsWhenLocked() {
        val j = Schedule.job(tellme)!!
        assertEquals("Tell me when" to "An email from Alex arrived.", Schedule.notification("tellme", j, false))
        val (_, locked) = Schedule.notification("tellme", j, true)
        assertEquals(Schedule.TELLME_LOCK_SCREEN, locked)
        assertFalse(locked.contains("Alex"))
        assertEquals(Schedule.TELLME_LOCK_SCREEN, Schedule.notification("tellme", null, false).second)
        assertEquals(Schedule.TELLME_LOCK_SCREEN, Schedule.lockScreen("tellme"))
        assertEquals(
            "s00000000bb" to true,
            Schedule.matchedFrom(obj("""{"id":"s00000000bb","kind":"tellme","state":"matched","urgent":true}""")),
        )
        assertNull(Schedule.matchedFrom(obj("""{"id":"s00000000bb","kind":"tellme","state":"fired"}""")))
        assertNull(Schedule.matchedFrom(obj("""{"id":"all","kind":"tellme","state":"matched"}""")))
        assertNull(Schedule.matchedFrom(obj("""{"id":"s00000000bb","kind":"timer","state":"matched"}""")))
    }

    @Test
    fun alarmsAndUrgentTellMeWhensRingUntilSeen() {
        assertTrue(Schedule.rings("alarm", urgent = false))
        assertTrue(Schedule.rings("tellme", urgent = true))
        assertFalse(Schedule.rings("tellme", urgent = false))
        assertFalse(Schedule.rings("timer", urgent = true))
        assertFalse(Schedule.rings("reminder", urgent = false))
    }

    @Test
    fun aJobChangedOnThePcTakesItsRingingNotificationAway() {
        // The PC's own shape (jarvis_schedule._changed): snoozed, deleted or
        // done there, by voice or in Coming up (bug audit 2026-09-26, #1).
        assertEquals("s0000000001" to "alarm",
            Schedule.changedFrom(obj("""{"id":"s0000000001","kind":"alarm","state":"changed"}""")))
        assertNull(Schedule.changedFrom(obj("""{"id":"s0000000001","kind":"alarm","state":"fired"}""")))
        assertNull(Schedule.changedFrom(obj("""{"id":"all","kind":"alarm","state":"changed"}""")))
        assertTrue(Schedule.cancelsOnChange("alarm"))
        assertTrue(Schedule.cancelsOnChange("timer"))
        assertTrue(Schedule.cancelsOnChange("reminder"))
        // A "tell me when" ends (a changed event) the moment it matched to
        // tell once: its notification must stay until it is seen.
        assertFalse(Schedule.cancelsOnChange("tellme"))
        assertTrue(Schedule.isFiredTag("s0000000001", "s0000000001"))
        assertFalse(Schedule.isFiredTag("s0000000001#match@170", "s0000000001"))
    }

    @Test
    fun aJobHeardMoreThanTenMinutesLateIsAQuietMissedNotice() {
        val went = 1_700_000_000.0
        assertFalse(Schedule.heardLate(went, went + 600))
        assertTrue(Schedule.heardLate(went, went + 601))
        assertFalse("unread: shown as before", Schedule.heardLate(null, went))
        assertFalse(Schedule.heardLate(went, went - 5))
        assertEquals("Missed at 07:00. Wake up", Schedule.missedWords("07:00", "Wake up"))
        assertEquals("Missed earlier. Jarvis: alarm.", Schedule.missedWords("", "Jarvis: alarm."))
        // The desktop's words, word for word.
        val rs = listOf(java.io.File("../../jarvis-desktop/src-tauri/src/brain/schedule.rs"),
            java.io.File("../jarvis-desktop/src-tauri/src/brain/schedule.rs"))
            .firstOrNull { it.isFile }?.readText()
        if (rs != null) {
            assertTrue(rs.contains("pub(crate) const LATE_RING_LIMIT_S: i64 = 10 * 60;"))
            assertTrue(rs.contains("\"Missed earlier.\""))
            assertTrue(rs.contains("format!(\"Missed at {at}.\")"))
        }
    }

    @Test
    fun anUnreadableJobIsToldApartByItsEvent() {
        // Bug audit #6: two failed reads used to both be "id@0", and the
        // second firing of a repeating job was dropped.
        assertEquals("s0000000001@1700000000", Schedule.shownKey("s0000000001", 1_700_000_000.5, "41", 9L))
        val monday = Schedule.shownKey("s0000000001", null, "41", 9L)
        val tuesday = Schedule.shownKey("s0000000001", null, "97", 10L)
        assertTrue(monday != tuesday)
        assertEquals("s0000000001@t10", Schedule.shownKey("s0000000001", null, null, 10L))
        assertEquals("s0000000001#match@ev3", Schedule.shownKey("s0000000001", 0.0, "3", 1L, "#match@"))
    }
}
