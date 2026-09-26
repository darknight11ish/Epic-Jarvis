package com.jarvis.client

import com.jarvis.client.net.AlsoOnPhone
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Schedule
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.ZoneId

/**
 * "Also on my phone" (the owner's decision of 2026-09-26; net/AlsoOnPhone.kt):
 * what an alarm or reminder in Coming up hands to the phone's own Clock app or
 * calendar - built from the PC's own job, only for what the Clock app can
 * really do, never for a hidden row, and nothing for anything else.
 */
class AlsoOnPhoneTest {
    private val utc = ZoneId.of("UTC")

    /** 2026-09-26 09:00 UTC, in ms. */
    private val now = 1_790_413_200_000L

    private fun job(json: String): Schedule.Job =
        Schedule.job(JarvisJson.parseToJsonElement(json) as JsonObject)!!

    @Test
    fun aOneOffAlarmWithinADayGoesToTheClockAtItsTime() {
        // Due 2026-09-26 18:30 UTC.
        val a = job("""{"id":"s0000000001","kind":"alarm","text":"gym","state":"active",
            "due":1790447400,"repeats":false}""")
        val offer = AlsoOnPhone.offer(a, now, utc) as AlsoOnPhone.Offer.ToClock
        assertEquals(AlsoOnPhone.Alarm(18, 30, "gym", emptyList()), offer.alarm)
    }

    @Test
    fun aOneOffAlarmMoreThanADayAheadIsNotHandedOverAndSaysWhy() {
        val a = job("""{"id":"s0000000002","kind":"alarm","text":"","state":"active",
            "due":1790600000,"repeats":false}""")
        assertEquals(AlsoOnPhone.Offer.Later(AlsoOnPhone.LATER), AlsoOnPhone.offer(a, now, utc))
    }

    @Test
    fun aRepeatingAlarmKeepsItsDaysInTheClocksNumbers() {
        val weekdays = job("""{"id":"s0000000003","kind":"alarm","text":"wake up","state":"active",
            "due":1790488800,"repeats":true,"rule":{"every":"weekday","at":"07:00"}}""")
        val w = (AlsoOnPhone.offer(weekdays, now, utc) as AlsoOnPhone.Offer.ToClock).alarm
        // java.util.Calendar: MONDAY = 2 ... FRIDAY = 6.
        assertEquals(AlsoOnPhone.Alarm(7, 0, "wake up", listOf(2, 3, 4, 5, 6)), w)
        val chosen = job("""{"id":"s0000000004","kind":"alarm","text":"","state":"active",
            "due":1790488800,"repeats":true,"rule":{"every":"week","at":"9:05","days":[6,0]}}""")
        // Sunday = 1, Monday = 2.
        assertEquals(listOf(1, 2), (AlsoOnPhone.offer(chosen, now, utc) as AlsoOnPhone.Offer.ToClock).alarm.days)
        val hours = job("""{"id":"s0000000005","kind":"alarm","text":"","state":"active",
            "due":1790488800,"repeats":true,"rule":{"every":"hours","hours":2,"start":1}}""")
        assertNull("the Clock app has no every-N-hours", AlsoOnPhone.offer(hours, now, utc))
    }

    @Test
    fun aReminderGoesToTheCalendarAsAnEventRepeatingTheSameWay() {
        val r = job("""{"id":"s0000000006","kind":"reminder","text":"call Mum","state":"active",
            "due":1790447400,"repeats":false}""")
        val e = (AlsoOnPhone.offer(r, now, utc) as AlsoOnPhone.Offer.ToCalendar).event
        assertEquals(AlsoOnPhone.Event("call Mum", 1_790_447_400_000L, 1_790_448_300_000L, null), e)
        val weekly = job("""{"id":"s0000000007","kind":"reminder","text":"bins","state":"active",
            "due":1790447400,"repeats":true,"rule":{"every":"week","at":"18:30","days":[0,3]}}""")
        assertEquals("FREQ=WEEKLY;BYDAY=MO,TH",
            (AlsoOnPhone.offer(weekly, now, utc) as AlsoOnPhone.Offer.ToCalendar).event.rrule)
        val daily = job("""{"id":"s0000000008","kind":"reminder","text":"","state":"active",
            "due":1790447400,"repeats":true,"rule":{"every":"day","at":"18:30"}}""")
        val d = (AlsoOnPhone.offer(daily, now, utc) as AlsoOnPhone.Offer.ToCalendar).event
        assertEquals("FREQ=DAILY", d.rrule)
        assertEquals("Reminder", d.title)
    }

    @Test
    fun nothingIsOfferedForAHiddenPausedOrOtherRow() {
        val a = """{"id":"s0000000009","kind":"alarm","text":"gym","state":"active",
            "due":1790447400,"repeats":false}"""
        val hidden = Schedule.hide(Schedule.View(listOf(job(a)), emptyList(), false)).jobs[0]
        assertNull("words hidden: nothing handed over", AlsoOnPhone.offer(hidden, now, utc))
        assertNull(AlsoOnPhone.offer(job(a.replace("\"active\"", "\"paused\"")), now, utc))
        assertNull("a past one", AlsoOnPhone.offer(job(a), 1_790_500_000_000L, utc))
        for (kind in listOf("timer", "todo", "briefing", "tellme", "standby")) {
            assertNull(kind, AlsoOnPhone.offer(job(a.replace("\"alarm\"", "\"$kind\"")), now, utc))
        }
        assertTrue(AlsoOnPhone.anyOffered(listOf(job(a)), now, utc))
        assertFalse(AlsoOnPhone.anyOffered(listOf(hidden), now, utc))
    }

    @Test
    fun theWordsWarnAboutTwoAlarmsAndGoogleAndTheClockPermissionIsDeclared() {
        assertTrue(AlsoOnPhone.NOTE.contains("both will ring"))
        assertTrue(AlsoOnPhone.NOTE.contains("Google account"))
        val manifest = listOf(File("src/main/AndroidManifest.xml"), File("app/src/main/AndroidManifest.xml"))
            .first { it.isFile }.readText()
        assertTrue(manifest.contains("com.android.alarm.permission.SET_ALARM"))
        assertFalse("no exact-alarm permission", manifest.contains("SCHEDULE_EXACT_ALARM"))
    }
}
