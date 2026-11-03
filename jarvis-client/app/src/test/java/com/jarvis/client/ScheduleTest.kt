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
        assertEquals(listOf("add_time", "pause", "delete"), Schedule.actionsOf(v.jobs[0]))
        assertEquals(listOf("delete"), Schedule.actionsOf(v.jobs[3]))
        assertEquals(listOf("done", "delete"), Schedule.actionsOf(v.todo[0]))
        assertEquals("9:58", Schedule.countdown(598.0))
        assertEquals("1:02:03", Schedule.countdown(3723.0))
        assertEquals("0:00", Schedule.countdown(-4.0))
        assertEquals("1 hour 30 minutes", Schedule.lengthWords(5400.0))
        assertTrue(Schedule.anyTicking(v))
    }

    @Test
    fun onlyATimerOffersTheHudsFiveMoreMinutes() {
        // Q2/F5 (2026-10-22): the PC's own matrix is the authority -
        // jarvis_schedule.act() accepts add_time for a timer only. This is the
        // phone half of the cross-surface rule; when Session A lands
        // contract/schedule-cases.json this check can read its timer row instead
        // of these fixtures (contract/ is not this branch's to edit).
        val v = Schedule.parse(list)!!
        assertEquals(listOf("add_time", "pause", "delete"), Schedule.actionsOf(v.jobs[0]))
        for (row in v.jobs.drop(1) + v.todo) {
            assertFalse("${row.kind}/${row.state} must not offer add_time",
                "add_time" in Schedule.actionsOf(row))
        }
        val paused = Schedule.parse(obj(
            """{"available":true,"jobs":[{"id":"s0000000006","kind":"timer",
            "text":"tea","state":"paused","left":120,"duration":600}],"todo":[]}""",
        ))!!
        assertEquals(listOf("add_time", "resume", "delete"), Schedule.actionsOf(paused.jobs[0]))
        assertEquals("+5 minutes", Schedule.labelOf("add_time"))
        assertEquals("""{"id":"s0000000006","do":"add_time","seconds":300}""",
            Schedule.actBody("s0000000006", "add_time"))
    }

    @Test
    fun oneJobPerChangeAndNeverAll() {
        assertEquals("""{"id":"s0000000001","do":"delete"}""", Schedule.actBody("s0000000001", "delete"))
        assertEquals("""{"id":"s0000000001","do":"add_time","seconds":300}""",
            Schedule.actBody("s0000000001", "add_time"))
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
        // The PC's words stay the shared contract (the desktop's own tests
        // read this file for them)...
        assertEquals("Done - answered on this PC without the AI model.", Schedule.DONE_LINE)
        // ...and the phone shows "your PC": it is not a PC itself.
        assertEquals("Done - answered on your PC without the AI model.", Schedule.DONE_LINE_HERE)
    }

    // "Open <a settings section>" by voice or chat (jarvis_settings_
    // registry.py, docs/JARVIS-API.md section 58.1) - additive to the same
    // X-Jarvis-Route the answer above already reads.

    @Test
    fun openSettingsIsReadOffTheSameHeader() {
        assertEquals(
            "web-search",
            Schedule.openSettingsFromRoute("""{"quick":"settings_open","open_settings":"web-search"}"""),
        )
        assertNull(Schedule.openSettingsFromRoute("""{"where":"local","quick":"timer_set"}"""))
        assertNull(Schedule.openSettingsFromRoute(null))
        assertNull(Schedule.openSettingsFromRoute("not json"))
        assertNull(Schedule.openSettingsFromRoute("""{"open_settings":""}"""))
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
        // A fired entry can be CLEARED as well as snoozed (DEF-008, the
        // owner's decision of 2026-10-13): the second button is the same
        // "delete" every other row offers, worded "Delete" - never a second
        // word for one action, and never "clear", which means a whole list.
        assertEquals(listOf("snooze", "delete"), Schedule.WENT_OFF_ACTIONS)
        assertEquals("Snooze 10 minutes", Schedule.labelOf("snooze"))
        assertEquals("Delete", Schedule.labelOf("delete"))
        assertEquals("""{"id":"s00000000c1","do":"delete"}""", Schedule.actBody("s00000000c1", "delete"))
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
    fun aReminderForNextTimeIsDeleteOnlyAndItsSubjectHidesWithTheWords() {
        val j = Schedule.job(
            obj(
                """{"id":"s00000000cc","kind":"nexttime","text":"ask about the bill",
                  "about":"the dentist","state":"active","when":"until Sunday 27 December",
                  "note":"Waits for you to talk about it.","fires":0,"max_fires":3}""",
            ),
        )!!
        assertEquals("ask about the bill", Schedule.titleOf(j))
        assertEquals("next time", Schedule.tagOf(j))
        assertEquals(
            listOf(Schedule.nextTimeAbout("the dentist"), "until Sunday 27 December", "Waits for you to talk about it."),
            Schedule.metaOf(j),
        )
        assertEquals("When you talk about “the dentist”", Schedule.nextTimeAbout("the dentist"))
        assertEquals(listOf("delete"), Schedule.actionsOf(j))
        val hidden = Schedule.hide(Schedule.View(listOf(j), emptyList(), false)).jobs.single()
        assertEquals(Schedule.NEXT_TIME_TITLE, Schedule.titleOf(hidden))
        assertEquals("", hidden.about)
        assertFalse(Schedule.metaOf(hidden).joinToString(" ").contains("dentist"))
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
    fun aWatchThatCannotLookSaysSoOnceAndOnlyTheGenericWordsWhenLocked() {
        val broken = obj(
            """{"id":"s00000000cc","kind":"tellme","text":"CI fails on o/r","state":"active",
              "broken":"Your \"tell me when\" (CI fails on o/r) cannot look right now. GitHub did not answer.",
              "broken_at":1790000000}""",
        )
        val j = Schedule.job(broken)!!
        assertEquals(1_790_000_000.0, j.brokenAt!!, 0.0)
        val (title, text) = Schedule.brokenNotification(j, false)
        assertEquals("Tell me when", title)
        assertTrue(text.startsWith("Your \"tell me when\" (CI fails on o/r)"))
        val (_, locked) = Schedule.brokenNotification(j, true)
        assertEquals(Schedule.TELLME_BROKEN_LOCK_SCREEN, locked)
        assertFalse(locked.contains("o/r"))
        assertEquals(Schedule.TELLME_BROKEN_LOCK_SCREEN, Schedule.brokenNotification(null, false).second)
        assertEquals("s00000000cc", Schedule.brokenFrom(obj("""{"id":"s00000000cc","kind":"tellme","state":"broken"}""")))
        assertNull(Schedule.brokenFrom(obj("""{"id":"s00000000cc","kind":"tellme","state":"matched"}""")))
        assertNull(Schedule.brokenFrom(obj("""{"id":"all","kind":"tellme","state":"broken"}""")))
        assertNull(Schedule.brokenFrom(obj("""{"id":"s00000000cc","kind":"timer","state":"broken"}""")))
        // A broken notice is not a match: it never rings.
        assertNull(Schedule.matchedFrom(obj("""{"id":"s00000000cc","kind":"tellme","state":"broken"}""")))
        // Hidden lists blank it like the alert.
        val hidden = Schedule.hide(Schedule.View(jobs = listOf(j), todo = emptyList(), hidden = false))
        assertEquals("", hidden.jobs.single().broken)
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
        // ageSeconds directly from PC
        assertFalse(Schedule.heardLate(went, went + 600, ageSeconds = 600.0))
        assertTrue(Schedule.heardLate(went, went, ageSeconds = 601.0))
        assertFalse(Schedule.heardLate(null, went, ageSeconds = 100.0))
        assertTrue(Schedule.heardLate(null, went, ageSeconds = 601.0))
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
    fun ageSecondsIsParsedFromJobJson() {
        val j = Schedule.job(obj("""{"id":"s0000000001","kind":"alarm","text":"wake up","state":"fired","age_s":45.0}"""))!!
        assertEquals(45.0, j.ageSeconds!!, 0.0)
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

    @Test
    fun theReviewDecksDailyJobIsNamedPlainlyAndOffersNoButtons() {
        // Decks owns the job (made with the first deck, removed with the last):
        // Pause or Delete here would only fight it.
        val job = Schedule.job(obj(
            """{"id":"s00000000c1","kind":"review","state":"active","text":"","repeats":true,"repeat":"every day at 04:00","note":"3 cards ready"}""",
        ))!!
        assertEquals(emptyList<String>(), Schedule.actionsOf(job))
        assertEquals("card review, repeats", Schedule.tagOf(job))
        assertEquals("card review", Schedule.tag("review"))
        assertEquals("Card review", Schedule.titleOf(job))
    }

    // ---------------- a "went off" notification whose job is gone ----
    // The owner's report of 2026-10-11: the jobs were deleted on the PC while
    // the phone still showed both notifications, and nothing cancelled them,
    // because the PC's `changed` event is the only cancellation this app had -
    // and a job that no longer exists sends none.

    @Test
    fun theJobIdComesOutOfANotificationKey() {
        // A timer's or alarm's key IS the job id.
        assertEquals("s0000000001", Schedule.jobIdFromTag("s0000000001"))
        // A "tell me when" MATCH's key is `id#match@…`.
        assertEquals("s0000000002", Schedule.jobIdFromTag("s0000000002#match@ev3"))
        assertEquals("s0000000002", Schedule.jobIdFromTag("s0000000002#match@1700000000"))
        // An ordinary key is left alone, and a separator with no id before it
        // is not treated as one.
        assertEquals("s0000000003#broken@8", Schedule.jobIdFromTag("s0000000003#broken@8"))
        assertEquals("#match@9", Schedule.jobIdFromTag("#match@9"))
    }

    @Test
    fun aWentOffJobThePcStillListsIsKeptAndOneItNoLongerListsIsNot() {
        // The two tags that were still ringing on the owner's phone, and a
        // third that is still a real job.
        val posted = listOf(
            "s7623a9a982" to "s7623a9a982",
            "sf50b6d4930" to "sf50b6d4930",
            "s0000000009" to "s0000000009",
        )
        val alive = setOf("s0000000009")
        assertEquals(
            listOf("s7623a9a982" to "s7623a9a982", "sf50b6d4930" to "sf50b6d4930"),
            Schedule.stopsWhenJobGone(posted, alive),
        )
        // Nothing is touched when every job is still there.
        assertEquals(
            emptyList<Pair<String, String>>(),
            Schedule.stopsWhenJobGone(posted, setOf("s7623a9a982", "sf50b6d4930", "s0000000009")),
        )
        // The MOTOR of the pairing: the job id is what is asked about, and a
        // match's composed tag still resolves to its own job.
        assertEquals(
            listOf("s0000000002#match@ev3" to "s0000000002"),
            Schedule.stopsWhenJobGone(listOf("s0000000002#match@ev3" to "s0000000002"), emptySet()),
        )
    }

    @Test
    fun theKnownIdsAreTheJobsTheTodoItemsAndTheOnesThatWentOff() {
        val body = obj(
            """{"available":true,
                "jobs":[{"id":"s0000000001","kind":"timer","text":"pasta","state":"active"}],
                "todo":[{"id":"s0000000005","kind":"todo","text":"buy milk","state":"active"}],
                "went_off":[{"id":"s0000000007","kind":"alarm","text":"","state":"fired"}]}""",
        )
        val view = Schedule.parse(body)!!
        assertEquals(
            setOf("s0000000001", "s0000000005", "s0000000007"),
            Schedule.knownIds(view),
        )
        // A list with nothing in it knows nothing - and the caller only asks
        // after a read that SUCCEEDED, so this is "the PC says it has no
        // jobs", never "the PC could not be asked".
        assertEquals(emptySet<String>(), Schedule.knownIds(Schedule.parse(obj("""{"available":true,"jobs":[],"todo":[]}"""))!!))
    }

    // ----------------------------------------------------------------------
    // The to-do list's own day (2026-11-02; JARVIS-API section 179; the
    // owner's choice of both ways, full daily rollover as the default).
    // ----------------------------------------------------------------------

    private val carryList = obj(
        """{"available":true,"jobs":[],"todo":[
          {"id":"s0000000011","kind":"todo","text":"call the dentist","state":"active",
           "list":"","created_date":"2026-10-30","carry":"from Friday (3d ago)"},
          {"id":"s0000000012","kind":"todo","text":"renew the prescription","state":"active",
           "list":"","created_date":"2026-11-01","carry":"from yesterday"},
          {"id":"s0000000013","kind":"todo","text":"buy milk","state":"active",
           "list":"","created_date":"2026-11-02"}],
          "todo_mode":"day",
          "todo_modes":[{"value":"rollover","label":"Daily rollover","detail":"everything open"},
                        {"value":"day","label":"Day by day","detail":"each day its own"}],
          "todo_days":[{"date":"2026-11-02","label":"Today","count":1,"items":["s0000000013"]},
                       {"date":"2026-11-01","label":"Yesterday","count":1,"items":["s0000000012"]},
                       {"date":"2026-10-30","label":"Friday (3d ago)","count":1,
                        "items":["s0000000011"]}]}""",
    )

    @Test
    fun theDayAnItemWasWrittenAndItsAgeAreReadFromThePc() {
        val v = Schedule.parse(carryList)!!
        val old = v.todo.first { it.id == "s0000000011" }
        assertEquals("2026-10-30", old.createdDate)
        assertEquals("from Friday (3d ago)", old.carry)
        // The words are the PC's: a 3-day-old item must never say "from
        // yesterday", and the phone never works an age out for itself.
        assertTrue(Schedule.carryOf(old) != "from yesterday")
        assertEquals("from yesterday", Schedule.carryOf(v.todo.first { it.id == "s0000000012" }))
        assertEquals("", Schedule.carryOf(v.todo.first { it.id == "s0000000013" }))
        // The tag is one more line under a rollover row, and only for a to-do.
        assertEquals(listOf("from Friday (3d ago)"),
            Schedule.metaOf(old, 0L, Schedule.carryOf(old)))
        assertEquals(emptyList<String>(),
            Schedule.metaOf(v.todo.first { it.id == "s0000000013" }, 0L,
                Schedule.carryOf(v.todo.first { it.id == "s0000000013" })))
        assertEquals(emptyList<String>(),
            Schedule.metaOf(old.copy(kind = "alarm"), 0L, Schedule.carryOf(old)))
    }

    @Test
    fun dayByDayIsTheSameRowsGroupedAndRolloverIsUnchanged() {
        val v = Schedule.parse(carryList)!!
        assertEquals(Schedule.MODE_DAY, v.todoMode)
        val days = Schedule.todoDays(v)
        assertEquals(listOf("Today", "Yesterday", "Friday (3d ago)"), days.map { it.label })
        assertEquals(listOf("buy milk"), days[0].items.map { it.text })
        assertEquals(listOf("call the dentist"), days[2].items.map { it.text })
        // The SAME items, in the same order, are still on the flat list - so
        // switching back to rollover is the identical list.
        assertEquals(listOf("s0000000011", "s0000000012", "s0000000013"), v.todo.map { it.id })
        assertEquals(listOf("s0000000011", "s0000000012", "s0000000013"),
            Schedule.todoItems(v).map { it.id })
        // And the two modes are the PC's own.
        assertEquals(listOf("rollover", "day"), Schedule.todoModes(v).map { it.value })
        assertEquals("Daily rollover", Schedule.todoModes(v)[0].label)
    }

    @Test
    fun aPcFromBeforeTheFeatureReadsAsRolloverAndLosesNothing() {
        val old = Schedule.parse(obj(
            """{"available":true,"jobs":[],"todo":[
               {"id":"s0000000011","kind":"todo","text":"call the dentist","state":"active"}]}""",
        ))!!
        assertEquals(Schedule.MODE_ROLLOVER, old.todoMode)
        assertEquals(emptyList<Schedule.Mode>(), old.todoModes)
        // The list is still shown - as ONE day - rather than as an empty screen.
        val days = Schedule.todoDays(old)
        assertEquals(1, days.size)
        assertEquals(listOf("call the dentist"), days[0].items.map { it.text })
        // ...and the switch still offers both, in plain words.
        assertEquals(listOf("rollover", "day"), Schedule.todoModes(old).map { it.value })
    }

    @Test
    fun theModeFinallyCanBeChangedAndOnlyWithARealMode() {
        assertEquals("""{"do":"todo_mode","mode":"day"}""", Schedule.todoModeBody(Schedule.MODE_DAY))
        assertEquals("""{"do":"todo_mode","mode":"rollover"}""",
            Schedule.todoModeBody(Schedule.MODE_ROLLOVER))
        // Not a mode, not a request - and never a second field (nothing else
        // is sent: this changes how the list is drawn, not the list).
        assertNull(Schedule.todoModeBody("both"))
        assertNull(Schedule.todoModeBody(""))
        assertNull(Schedule.todoModeBody("Day"))
    }

    @Test
    fun theWordsAreGoneWhileThePrivateListsAreHidden() {
        val hidden = Schedule.hide(Schedule.parse(carryList)!!)
        assertEquals("", Schedule.carryOf(hidden.todo.first()))
        assertEquals(emptyList<String>(),
            Schedule.metaOf(hidden.todo.first(), 0L, Schedule.carryOf(hidden.todo.first())))
        // The mode itself is not the owner's words about anything: it is still
        // read, so the switch keeps showing which of the two is on.
        assertEquals(Schedule.MODE_DAY, hidden.todoMode)
    }

    // ---- a reminder that ASKS (2026-11-02) --------------------------------
    //
    // The owner's request: *"a notification on my Android phone saying 'Did you
    // take your medication?' with a Yes or No button"*. What is proved here is
    // the phone's half only - the PC's own rules (the lengths, the three-button
    // ceiling, the destinations) are proved in backend/test_schedule_ask.py, and
    // this side never re-checks them: it draws what the PC handed out, and drops
    // a shape it could not draw honestly.

    private val asked = obj(
        """{"available":true,"asks":true,"jobs":[],
           "todo":[{"id":"s0000000010","kind":"reminder","text":"medication",
             "state":"fired","fired_at":1800000000,"went_off_at":"10:00",
             "asks":true,
             "action":{"kind":"ask","question":"Did you take your medication?",
               "buttons":[{"label":"Taken","does":"record"},
                          {"label":"Skipped","does":"record"},
                          {"label":"Later","does":"snooze","minutes":30}],
               "record":{"history":true,"obsidian_daily":true,"goal":"g-1"}},
             "answers":[{"at":1800000000,"clock":"10:00","button":"Taken",
                         "does":"record","wrote":["its own history"]}]}]}""",
    )

    @Test
    fun aQuestionIsReadWithItsButtonsAndItsAnswers() {
        val job = Schedule.parse(asked)!!.todo.single()
        assertTrue(job.asks)
        val ask = job.ask!!
        assertEquals("Did you take your medication?", ask.question)
        assertEquals(listOf("Taken", "Skipped", "Later"), ask.buttons.map { it.label })
        assertEquals(listOf("record", "record", "snooze"), ask.buttons.map { it.does })
        assertEquals(30, ask.buttons.last().minutes)
        // Only the snooze button carries a time; the others have none at all.
        assertEquals(0, ask.buttons.first().minutes)
        assertTrue(ask.record.history)
        assertTrue(ask.record.obsidianDaily)
        assertEquals("g-1", ask.record.goal)
        assertEquals("", ask.record.habit)
        val answer = job.answers.single()
        assertEquals("10:00", answer.clock)
        assertEquals("Taken", answer.button)
        assertEquals(listOf("its own history"), answer.wrote)
    }

    @Test
    fun theNotificationSaysTheQuestionInTheOwnersWords() {
        val job = Schedule.parse(asked)!!.todo.single()
        assertEquals(
            Schedule.title("reminder") to "Did you take your medication?",
            Schedule.notification("reminder", job, private = false),
        )
        // While App lock or "Hide memory lists" is on, the generic line only -
        // the question is the owner's own words about his own health.
        assertEquals(
            Schedule.title("reminder") to Schedule.ASK_ON_LOCK_SCREEN,
            Schedule.notification("reminder", job, private = true),
        )
        // A reminder with no question is untouched.
        val plain = Schedule.parse(list)!!.jobs.first { it.id == "s0000000003" }
        assertEquals("take my pills", Schedule.notification("reminder", plain, false).second)
    }

    @Test
    fun aQuestionThisPhoneCannotDrawIsDroppedWhole() {
        fun askOf(body: String) = Schedule.parse(
            obj("""{"available":true,"jobs":[],"todo":[{"id":"s0000000011","kind":"reminder",
                     "text":"x","state":"fired","fired_at":1,"action":$body}]}"""),
        )!!.todo.single().ask
        assertNull("no question", askOf("""{"kind":"ask","buttons":[{"label":"Yes","does":"done"}]}"""))
        assertNull("no buttons", askOf("""{"kind":"ask","question":"q?","buttons":[]}"""))
        assertNull("a verb this build has no answer for",
            askOf("""{"kind":"ask","question":"q?","buttons":[{"label":"Go","does":"shell"}]}"""))
        assertNull("a snooze with no minutes",
            askOf("""{"kind":"ask","question":"q?","buttons":[{"label":"Later","does":"snooze"}]}"""))
        assertNull("another kind entirely",
            askOf("""{"kind":"open-webpage","url":"https://example.com"}"""))
        // A fourth button is not drawn: three is Android's own ceiling.
        val four = askOf("""{"kind":"ask","question":"q?","buttons":[
            {"label":"a","does":"done"},{"label":"b","does":"done"},
            {"label":"c","does":"done"},{"label":"d","does":"done"}]}""")!!
        assertEquals(3, four.buttons.size)
    }

    @Test
    fun oneAnswerIsOneJobAndTheButtonsIndex() {
        assertEquals("""{"id":"s0000000010","do":"answer","button":0}""",
            Schedule.answerBody("s0000000010", 0))
        assertEquals("""{"id":"s0000000010","do":"answer","button":2}""",
            Schedule.answerBody("s0000000010", 2))
        // Never a label, never a target, never a fourth button, never a made-up id.
        assertNull(Schedule.answerBody("s0000000010", 3))
        assertNull(Schedule.answerBody("s0000000010", -1))
        assertNull(Schedule.answerBody("all", 0))
        assertNull(Schedule.answerBody("", 0))
    }
}
