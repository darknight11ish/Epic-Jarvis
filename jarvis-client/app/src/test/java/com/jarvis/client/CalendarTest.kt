package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Calendar
import com.jarvis.client.net.Calendar.Reply
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.DayOfWeek
import java.time.LocalDate

/**
 * Jarvis's own calendar on the phone (JARVIS-API section 163; net/Calendar.kt,
 * ui/screens/CalendarPlate.kt): reading the PC's answer, the month grid, which
 * event belongs to which day, the words an event is drawn with - all-day,
 * timed, a span, a repeat - and the bodies the screen posts.
 *
 * Every test passes its own "today" in rather than reading the clock, because
 * a test that reads the clock passes in October and fails in November: the
 * month-grid cases would otherwise depend on the day the suite happened to run.
 * The one place the device's own zone is used is [Calendar.todayNow], and it is
 * checked against the same instant rather than against "now".
 */
class CalendarTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private fun event(
        id: String = "c0000000001",
        title: String = "Dentist",
        date: String = "2026-11-03",
        time: String? = "14:30",
        extra: String = "",
    ) = Calendar.parseEvent(
        obj(
            """{"id":"$id","title":"$title","date":"$date","time":${
                if (time == null) "null" else "\"$time\""
            },"all_day":${time == null},"place":"","notes":"","recurrence":"","tz":"Europe/London"$extra}""",
        ),
    )!!

    private val answer = obj(
        """{"available":true,"on":true,"days":7,
           "window":{"start":"2026-11-01","end":"2026-11-08"},
           "events":[
             {"id":"c0000000001","title":"Dentist","date":"2026-11-03","time":"14:30","all_day":false,
              "place":"Bridge Street","notes":"bring the form","remind_minutes":30,"recurrence":"","tz":"Europe/London"},
             {"id":"c0000000002","title":"Holiday","date":"2026-11-01","end_date":"2026-11-04","all_day":true,
              "place":"","notes":"","recurrence":"","tz":"Europe/London"},
             {"id":"c0000000003","title":"Standup","date":"2026-11-03","time":"09:00","all_day":false,
              "place":"","notes":"","recurrence":"weekly","tz":"Europe/London"},
             {"id":"c0000000004","title":"No id"},
             {"id":"c0000000005","title":"Bad day","date":"2026-02-30","time":"10:00","all_day":false}],
           "sources":{"local":{"state":"on","count":3}}}""",
    )

    // ------------------------------------------------------------- parse ----

    @Test
    fun theAnswerIsReadAndAnEventWithoutAnIdOrARealDayIsDropped() {
        val v = Calendar.parse(answer)!!
        assertEquals(3, v.events.size)
        assertEquals(listOf("c0000000001", "c0000000002", "c0000000003"), v.events.map { it.id })
        assertEquals(LocalDate.of(2026, 11, 1), v.startDay)
        assertEquals(LocalDate.of(2026, 11, 8), v.endDay)
        assertTrue(v.on)
        assertTrue(v.available)
        // Nothing that is not an answer at all.
        assertNull(Calendar.parse(obj("""{"ok":true}""")))
        assertNull(Calendar.parse(obj("""{"weather":"rain"}""")))
    }

    @Test
    fun switchedOffIsARealAnswerWithNoEventsInIt() {
        // The PC answers 200 with `"on": false` and no events, on purpose: the
        // screens then need no special case for a 404, and "off" is not an
        // error (design decision D4).
        val v = Calendar.parse(obj("""{"available":true,"on":false,"days":7,"events":[]}"""))!!
        assertFalse(v.on)
        assertEquals(emptyList<Calendar.Event>(), v.events)
    }

    @Test
    fun aPcWithoutTheRouteIsDistinctFromAnEmptyCalendar() {
        assertTrue(Calendar.missing(ApiError.NotFound))
        assertTrue(Calendar.missing(ApiError.Server(501, "")))
        assertFalse(Calendar.missing(ApiError.Unreachable("refused", "refused")))
        assertFalse(Calendar.missing(ApiError.BadToken))
    }

    // ------------------------------------------------------- the month ----

    @Test
    fun theGridIsWholeWeeksAndStartsOnTheFirstWeekday() {
        val november = Calendar.Month(2026, 11)
        // 1 November 2026 is a Sunday, so a Monday-first grid pads six times.
        val cells = Calendar.cells(november)
        assertEquals(0, cells.size % 7)
        assertEquals(Calendar.Cell.Blank, cells[0])
        assertEquals(Calendar.Cell.Day(LocalDate.of(2026, 11, 1)), cells[6])
        assertEquals(Calendar.Cell.Day(LocalDate.of(2026, 11, 30)), cells[6 + 29])
        // A month that starts on the first weekday gets no leading blanks, and
        // one that needs six rows still gets whole weeks.
        val june = Calendar.cells(Calendar.Month(2026, 6))
        assertEquals(Calendar.Cell.Day(LocalDate.of(2026, 6, 1)), june[0])
        assertEquals(0, june.size % 7)
        assertEquals(30, june.count { it is Calendar.Cell.Day })
        val august = Calendar.cells(Calendar.Month(2026, 8))
        assertEquals(31, august.count { it is Calendar.Cell.Day })
        assertEquals(0, august.size % 7)
    }

    @Test
    fun theGridCanStartOnSundayAndSaysSoWithItsLetters() {
        val sunday = Calendar.cells(Calendar.Month(2026, 11), DayOfWeek.SUNDAY)
        // 1 November 2026 IS a Sunday: no padding at all in a Sunday-first grid.
        assertEquals(Calendar.Cell.Day(LocalDate.of(2026, 11, 1)), sunday[0])
        val monday = Calendar.weekdayLetters()
        val sundayLetters = Calendar.weekdayLetters(DayOfWeek.SUNDAY)
        assertEquals(7, monday.size)
        assertEquals(7, sundayLetters.size)
        assertEquals("M", monday.first())
        assertEquals("S", sundayLetters.first())
        // Rotating the start rotates the letters, it does not invent any.
        assertEquals(monday.toSet(), sundayLetters.toSet())
    }

    @Test
    fun theMonthWalksAcrossAYearAndNeverSaysMonthZero() {
        val january = Calendar.Month(2026, 1)
        assertEquals(Calendar.Month(2025, 12), january.previous())
        assertEquals(Calendar.Month(2026, 2), january.next())
        assertEquals(Calendar.Month(2026, 11), Calendar.monthOf(LocalDate.of(2026, 11, 3)))
        assertEquals("November 2026", Calendar.Month(2026, 11).words)
        assertEquals(LocalDate.of(2026, 2, 28), Calendar.Month(2026, 2).last)
        assertEquals(LocalDate.of(2028, 2, 29), Calendar.Month(2028, 2).last)
    }

    // -------------------------------------------------- which day it is on ----

    @Test
    fun aSpanIsOnEveryDayItCoversAndAnEventIsOnItsOwn() {
        val v = Calendar.parse(answer)!!
        val third = LocalDate.of(2026, 11, 3)
        // The holiday covers the 1st to the 4th; the standup and the dentist are
        // on the 3rd only.
        assertTrue(Calendar.hasEvents(v, third))
        assertEquals(
            listOf("Holiday", "Standup", "Dentist"),
            Calendar.eventsOn(v, third).map { it.title },
        )
        // All-day first, then timed earliest to latest: the order a day reads.
        assertEquals(listOf("Holiday"), Calendar.eventsOn(v, LocalDate.of(2026, 11, 2)).map { it.title })
        assertEquals(listOf("Holiday"), Calendar.eventsOn(v, LocalDate.of(2026, 11, 4)).map { it.title })
        // The last day of the span is included and the day after it is not.
        assertEquals(emptyList<Calendar.Event>(), Calendar.eventsOn(v, LocalDate.of(2026, 11, 5)))
        assertEquals(emptyList<Calendar.Event>(), Calendar.eventsOn(v, LocalDate.of(2026, 11, 6)))
    }

    @Test
    fun aDottedDayListCoversEveryCoveredDayOnce() {
        val v = Calendar.parse(answer)!!
        val days = Calendar.daysWithEvents(v)
        // A set, because that is what the dots are: the ORDER follows the PC's
        // own rows and nothing reads it.
        assertEquals(
            setOf(
                LocalDate.of(2026, 11, 1), LocalDate.of(2026, 11, 2), LocalDate.of(2026, 11, 3),
                LocalDate.of(2026, 11, 4),
            ),
            days.toSet(),
        )
        // One day, one entry: a four-day event does not dot the 3rd twice.
        assertEquals(4, days.size)
    }

    @Test
    fun twoEventsAtThesameTimeAreInATitleOrderRatherThanThePcsRowOrder() {
        val v = Calendar.parse(
            obj(
                """{"on":true,"events":[
                   {"id":"c0000000001","title":"Zebra","date":"2026-11-03","time":"09:00","all_day":false},
                   {"id":"c0000000002","title":"Apple","date":"2026-11-03","time":"09:00","all_day":false}]}""",
            ),
        )!!
        assertEquals(listOf("Apple", "Zebra"), Calendar.eventsOn(v, LocalDate.of(2026, 11, 3)).map { it.title })
    }

    // ------------------------------------------------------------ window ----

    @Test
    fun theSettingsCountIsTheStoresAndNotJustTheWindows() {
        // `sources.local.count` is how many events the WHOLE store holds, while
        // `events` is only the ones in the window (jarvis_local_calendar's
        // list_events). The Settings line says "N events saved", so it must read
        // the store's number: a window's size would say "2 events saved" to an
        // owner with 37.
        val v = Calendar.parse(
            obj(
                """{"on":true,"days":7,"window":{"start":"2026-11-01","end":"2026-11-08"},
                   "events":[{"id":"c0000000001","title":"Dentist","date":"2026-11-03","time":"14:30","all_day":false}],
                   "sources":{"local":{"state":"on","count":37}}}""",
            ),
        )!!
        assertEquals(37, v.saved)
        // With no count anywhere, the window's own size is the honest answer and
        // the caller words it as such.
        assertEquals(
            1,
            Calendar.parse(
                obj("""{"on":true,"events":[{"id":"c0000000001","title":"x","date":"2026-11-03"}]}"""),
            )!!.saved,
        )
    }

    @Test
    fun aStoreThatCouldNotBeReadSaysWhyAndIsNeverAnEmptyCalendar() {
        val bad = Calendar.parse(
            obj(
                """{"available":false,"on":false,"events":[],
                   "why":"The calendar's store could not be read (OperationalError). Nothing was changed."}""",
            ),
        )!!
        assertFalse(bad.available)
        assertTrue(bad.why.contains("could not be read"))
        // A PC that says nothing about `why` is still `available: false`, and the
        // screens fall back to their own sentence rather than to "no events".
        assertFalse(Calendar.parse(obj("""{"available":false,"on":false,"events":[]}"""))!!.available)
    }

    @Test
    fun aDayThePcNeverSentIsNotAnEmptyDay() {
        // The read is `?days=N` from the PC's own today forward, so a day before
        // today - or past the end of what it sent - is a day this app knows
        // nothing about. Drawing it as empty would invent a fact.
        val v = Calendar.parse(answer)!!
        assertTrue(Calendar.knows(v, LocalDate.of(2026, 11, 1)))
        assertTrue(Calendar.knows(v, LocalDate.of(2026, 11, 7)))
        // The PC's `end` is exclusive: it sends today + days and stops there.
        assertFalse(Calendar.knows(v, LocalDate.of(2026, 11, 8)))
        assertFalse(Calendar.knows(v, LocalDate.of(2026, 10, 31)))
        assertEquals(
            "Not read: your PC sent 1 November to 8 November, and nothing outside that is known.",
            Calendar.unreadDay(v),
        )
        // A month with no overlap at all says so once, at the top; November
        // overlaps the window, so it is an ordinary month.
        assertTrue(Calendar.monthUnread(v, Calendar.Month(2026, 9)))
        assertFalse(Calendar.monthUnread(v, Calendar.Month(2026, 11)))
        // A view with no window at all behaves exactly as it did before the
        // window existed, rather than refusing to draw anything.
        val bare = Calendar.parse(obj("""{"on":true,"events":[]}"""))!!
        assertTrue(Calendar.knows(bare, LocalDate.of(1999, 1, 1)))
        assertFalse(Calendar.monthUnread(bare, Calendar.Month(2026, 11)))
        assertEquals("", Calendar.windowWords(bare))
    }

    // ------------------------------------------------------------ words ----

    @Test
    fun anAllDayEventSaysAllDayAndASpanSaysHowLongItIs() {
        assertEquals("All day", Calendar.timeWords(event(time = null)))
        assertEquals("All day, 4 days", Calendar.timeWords(event(time = null, extra = ",\"end_date\":\"2026-11-06\"")))
        assertEquals("14:30", Calendar.timeWords(event()))
        assertEquals(
            "14:30 - 15:15",
            Calendar.timeWords(event(extra = ",\"end_time\":\"15:15\"")),
        )
        // A span that ends before it starts ended the next day: said, not drawn
        // as a mistake.
        assertEquals(
            "23:00 - 01:00 (next day)",
            Calendar.timeWords(event(time = "23:00", extra = ",\"end_time\":\"01:00\"")),
        )
    }

    @Test
    fun aRepeatIsSaidInWordsAndNeverAsAProtocolName() {
        assertEquals("", Calendar.recurrenceWords(event()))
        assertEquals("Every day", Calendar.recurrenceWords(event(extra = ",\"recurrence\":\"daily\"")))
        assertEquals("Every week", Calendar.recurrenceWords(event(extra = ",\"recurrence\":\"weekly\"")))
        assertEquals("Every month", Calendar.recurrenceWords(event(extra = ",\"recurrence\":\"monthly\"")))
        assertEquals("Every year", Calendar.recurrenceWords(event(extra = ",\"recurrence\":\"yearly\"")))
        assertEquals("", Calendar.recurrenceLabel("none"))
        // An unknown value is shown, not swallowed: a screen that hides the
        // word would claim the event does not repeat.
        assertEquals("Repeats: every second tuesday", Calendar.recurrenceLabel("every second tuesday"))
    }

    @Test
    fun aDayIsNamedTheWayAPersonNamesIt() {
        val today = LocalDate.of(2026, 11, 3)
        assertEquals("Today", Calendar.dayWords(today, today))
        assertEquals("Tomorrow", Calendar.dayWords(today.plusDays(1), today))
        assertEquals("Yesterday", Calendar.dayWords(today.minusDays(1), today))
        assertEquals("Thursday 5 November", Calendar.dayWords(today.plusDays(2), today))
        assertEquals("Today, 3 November", Calendar.datedWords(today, today))
        assertEquals("Tomorrow, 4 November", Calendar.datedWords(today.plusDays(1), today))
        assertEquals("Tue 10 Nov", Calendar.datedWords(today.plusDays(7), today))
    }

    @Test
    fun aDaysAccessibilityLineSaysWhatIsOnItAndNotATitle() {
        val day = LocalDate.of(2026, 11, 3)
        val today = LocalDate.of(2026, 11, 3)
        assertEquals("Tuesday 3 November, today", Calendar.dayA11y(day, 0, today))
        assertEquals("Tuesday 3 November, today, 1 event", Calendar.dayA11y(day, 1, today))
        assertEquals("Tuesday 3 November, today, 3 events", Calendar.dayA11y(day, 3, today))
        // Never the owner's own words - a cell has no title to read.
        assertFalse(Calendar.dayA11y(day, 2, today).contains("Dentist"))
    }

    @Test
    fun anEventsMetaLineIsItsTimeThenItsPlaceThenItsRepeat() {
        val e = event(extra = ",\"place\":\"Bridge Street\",\"recurrence\":\"weekly\"")
        assertEquals(listOf("14:30", "Bridge Street", "Every week"), Calendar.metaOf(e))
        assertEquals(listOf("All day"), Calendar.metaOf(event(time = null)))
    }

    // ------------------------------------------------------------- bodies ----

    @Test
    fun aNewEventSendsTheFieldsItWasGivenAndAllDaySendsNoTime() {
        // `end_date` is sent even when it is the same day: leaving it out means
        // "keep the span it had" to the PC, so an event shortened to one day
        // would stay as long as it was.
        assertEquals(
            """{"title":"Dentist","date":"2026-11-03","all_day":false,"time":"14:30","end_date":"2026-11-03"}""",
            Calendar.addBody("Dentist", "2026-11-03", "14:30"),
        )
        // All day: no time at all, because a PC that stored "00:00" would draw
        // it as a timed midnight event.
        assertEquals(
            """{"title":"Holiday","date":"2026-11-03","all_day":true,"end_date":"2026-11-03"}""",
            Calendar.addBody("Holiday", "2026-11-03", allDay = true),
        )
        val full = Calendar.addBody(
            title = "  Dentist  ",
            date = "2026-11-03",
            time = "9:05",
            endDate = "2026-11-04",
            endTime = "10:00",
            place = "Bridge Street",
            notes = "bring the form",
            remindMinutes = 30,
            recurrence = "weekly",
        )!!
        assertTrue(full.contains("\"title\":\"Dentist\""))
        assertTrue(full.contains("\"time\":\"09:05\""))
        assertTrue(full.contains("\"end_date\":\"2026-11-04\""))
        assertTrue(full.contains("\"end_time\":\"10:00\""))
        assertTrue(full.contains("\"place\":\"Bridge Street\""))
        assertTrue(full.contains("\"remind_minutes\":30"))
        assertTrue(full.contains("\"recurrence\":\"weekly\""))
        // "none" is never sent: a PC that does not know the word must not be
        // given a reason to refuse.
        assertFalse(full.contains("none"))
    }

    @Test
    fun anEventThatCannotBeOneIsRefusedBeforeItIsSent() {
        // No title, an impossible day, a time that is not one, the last day
        // before the first, an end before the start.
        assertNull(Calendar.addBody("", "2026-11-03", "14:30"))
        assertNull(Calendar.addBody("Dentist", "2026-02-30", "14:30"))
        assertNull(Calendar.addBody("Dentist", "2026-11-03", "25:00"))
        assertNull(Calendar.addBody("Dentist", "2026-11-03", allDay = false))
        assertNull(Calendar.addBody("Dentist", "2026-11-03", "14:30", endDate = "2026-11-02"))
        assertNull(Calendar.addBody("Dentist", "2026-11-03", "14:30", endTime = "14:00"))
        // A span ending the NEXT day may end earlier on the clock than it
        // starts - that is an overnight event, not a mistake.
        assertNotNull(
            Calendar.addBody("Night shift", "2026-11-03", "23:00", endDate = "2026-11-04", endTime = "01:00"),
        )
    }

    @Test
    fun everyWrongBoxIsNamedInPlainWords() {
        assertEquals("Give the event a name first.", Calendar.problem("", "2026-11-03", "14:30", false, null, null))
        assertEquals(
            "The date should look like 2026-11-03.",
            Calendar.problem("Dentist", "3 November", "14:30", false, null, null),
        )
        assertEquals(
            "Add a time, or tick All day.",
            Calendar.problem("Dentist", "2026-11-03", "  ", false, null, null),
        )
        assertEquals(
            "The time should look like 14:30.",
            Calendar.problem("Dentist", "2026-11-03", "2:5", false, null, null),
        )
        assertEquals(
            "The last day is before the first one.",
            Calendar.problem("Dentist", "2026-11-03", "14:30", false, "2026-11-01", null),
        )
        assertNull(Calendar.problem("Dentist", "2026-11-03", "14:30", false, null, null))
        // An all-day event needs no time, and says nothing about one.
        assertNull(Calendar.problem("Holiday", "2026-11-03", null, true, null, null))
        // The remind box is checked here rather than being left for the PC to
        // refuse: four weeks is the PC's own cap (MAX_REMIND_MINUTES).
        assertEquals(
            "A reminder can be at most four weeks (40320 minutes) before.",
            Calendar.problem("Dentist", "2026-11-03", "14:30", false, null, null, remind = 40_321),
        )
        assertNull(Calendar.problem("Dentist", "2026-11-03", "14:30", false, null, null, remind = 40_320))
    }

    @Test
    fun theRepeatChoicesAreTheFourThePcAccepts() {
        // jarvis_local_calendar's RECURRENCES is ("none", "daily", "weekly",
        // "monthly") and anything else is a 400. A fifth word here would be a
        // choice that looks like it worked and did not - "yearly" was in the
        // first draft of this list and was removed for exactly that reason.
        assertEquals(
            listOf("none", "daily", "weekly", "monthly"),
            Calendar.REPEAT_CHOICES.map { it.first },
        )
        assertEquals(4, Calendar.REPEAT_CHOICES.size)
    }

    @Test
    fun oneChangeToOneEventCarriesItsIdAndItsFields() {
        val body = Calendar.updateBody(
            "c0000000001",
            """{"title":"Dentist","date":"2026-11-03","all_day":false,"time":"15:00"}""",
        )!!
        assertEquals(
            """{"id":"c0000000001","do":"update","title":"Dentist","date":"2026-11-03","all_day":false,"time":"15:00"}""",
            body,
        )
        assertEquals("""{"id":"c0000000001","do":"delete"}""", Calendar.deleteBody("c0000000001"))
        // Never a bulk form, and never an id that is not one.
        assertNull(Calendar.deleteBody("all"))
        assertNull(Calendar.deleteBody(""))
        assertNull(Calendar.updateBody("all", """{"title":"x"}"""))
        assertEquals("""{"on":true}""", Calendar.settingsBody(true))
        assertEquals("""{"on":false}""", Calendar.settingsBody(false))
    }

    @Test
    fun anIdIsALowercaseHexIdLikeThePcsOwn() {
        assertTrue(Calendar.validId("c0000000001"))
        assertTrue(Calendar.validId("cabcdef1234"))
        assertFalse(Calendar.validId("s0000000001"))
        assertFalse(Calendar.validId("c000000000A"))
        assertFalse(Calendar.validId("c00000000011"))
        assertFalse(Calendar.validId("all"))
    }

    // -------------------------------------------------------------- reply ----

    @Test
    fun whatThePcAnsweredIsSaidInItsOwnWords() {
        assertEquals(
            true to "Dentist, Tuesday 3 November at 14:30.",
            Calendar.said(Reply(200, obj("""{"ok":true,"said":"Dentist, Tuesday 3 November at 14:30."}"""))),
        )
        assertEquals(
            true to "Saved.",
            Calendar.said(Reply(200, obj("""{"ok":true,"event":{"id":"c0000000001"}}"""))),
        )
        assertEquals(
            true to "The Jarvis calendar is off. Nothing was deleted.",
            Calendar.said(Reply(200, obj("""{"ok":true,"on":false}"""))),
        )
        // Already gone is a success: the owner wanted it gone and it is.
        assertEquals(
            true to "That event was already gone.",
            Calendar.said(Reply(404, obj("""{"ok":false,"reason":"no_such_event"}"""))),
        )
        // A PC without the route is not.
        assertEquals(false to Calendar.MISSING, Calendar.said(Reply(404, obj("""{"ok":false}"""))))
        // A full store says so in words, and never claims the newest event went in.
        assertTrue(
            Calendar.said(Reply(409, obj("""{"ok":false,"error":"Your calendar is full."}"""))).second
                .contains("Your calendar is full."),
        )
        assertEquals(
            false to "The end time is before the start.",
            Calendar.said(Reply(400, obj("""{"ok":false,"error":"The end time is before the start."}"""))),
        )
        // The PC's 5xx answers carry an exception NAME in `error` and the
        // readable sentence in `message`. "OperationalError" would be true and
        // useless, so the message is what is shown.
        assertEquals(
            false to "the event could not be saved",
            Calendar.said(
                Reply(
                    503,
                    obj("""{"ok":false,"error":"OperationalError","message":"the event could not be saved"}"""),
                ),
            ),
        )
        // The switch being off is a 409 with the PC's own sentence: it is an
        // answer, not a failure to read, so the error is shown as it is.
        assertEquals(
            false to "The Jarvis calendar is off. Turn it on in Settings first - nothing was changed.",
            Calendar.said(
                Reply(
                    409,
                    obj(
                        """{"ok":false,"reason":"off","error":"The Jarvis calendar is off. """ +
                            """Turn it on in Settings first - nothing was changed."}""",
                    ),
                ),
            ),
        )
    }

    // -------------------------------------------------------------- times ----

    @Test
    fun aTimeIsTidiedToTheOneShapeThePcStores() {
        assertEquals("09:05", Calendar.tidyTime("9:05"))
        assertEquals("14:30", Calendar.tidyTime(" 14:30 "))
        assertEquals("00:00", Calendar.tidyTime("0:00"))
        assertEquals("24:00", Calendar.tidyTime("24:00"))
        assertNull(Calendar.tidyTime("24:30"))
        assertNull(Calendar.tidyTime("25:00"))
        assertNull(Calendar.tidyTime(""))
        assertTrue(Calendar.validTime("14:30"))
        assertFalse(Calendar.validTime("9:05"))
    }

    @Test
    fun todayComesFromTheDeviceZoneRatherThanUtc() {
        // 2026-11-03 23:30 in Los Angeles is 2026-11-04 in UTC: the day a phone
        // shows must be the phone's, not the server's.
        val instant = java.time.Instant.parse("2026-11-04T07:30:00Z").toEpochMilli()
        assertEquals(
            LocalDate.of(2026, 11, 3),
            Calendar.todayNow(instant, java.time.ZoneId.of("America/Los_Angeles")),
        )
        assertEquals(
            LocalDate.of(2026, 11, 4),
            Calendar.todayNow(instant, java.time.ZoneId.of("UTC")),
        )
    }
}
