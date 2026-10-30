package com.jarvis.client

import com.jarvis.client.net.Calendar
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.widget.WidgetStates
import com.jarvis.client.widget.WidgetStates.Cal
import com.jarvis.client.widget.WidgetStates.Read
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/**
 * The calendar widget's decisions (2026-10-29; widget/CalendarWidget.kt,
 * widget/WidgetStates.kt): what it draws, and the three rules that come before
 * anything pretty.
 *
 *  1. **It always says something.** Every draw ends in a state with words -
 *     there is no "loading" state anywhere (the owner's 2026-10-27 bug: every
 *     widget sat on Glance's spinner for ever).
 *  2. **The home screen is public.** Under App lock or "Hide memory lists and
 *     chat history" it draws one sentence and NO title.
 *  3. **Off is not empty.** A widget that vanished, or drew a blank square,
 *     would read as a fault - so it stays and says the calendar is off (design
 *     decision D5).
 *
 * Nothing here touches Android: `WidgetStates` is pure Kotlin on purpose, and
 * the widget itself does no deciding of its own.
 */
class CalendarWidgetTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private fun view(events: String = "") = Calendar.parse(
        obj("""{"available":true,"on":true,"days":7,"events":[$events]}"""),
    )!!

    private val today = LocalDate.of(2026, 11, 3)

    private val three = view(
        """{"id":"c0000000001","title":"Standup","date":"2026-11-03","time":"09:00","all_day":false},
           {"id":"c0000000002","title":"Dentist","date":"2026-11-03","time":"14:30","all_day":false},
           {"id":"c0000000003","title":"Holiday","date":"2026-11-03","all_day":true},
           {"id":"c0000000004","title":"Tomorrow","date":"2026-11-04","time":"10:00","all_day":false}""",
    )

    // ------------------------------------------------------------- states ----

    @Test
    fun aWidgetThatCouldNotStartSaysSoRatherThanSpin() {
        assertEquals(
            Cal.NOT_STARTED,
            WidgetStates.calendar(ready = false, paired = true, off = false, hidden = false, live = true, read = Read.CONTENT),
        )
        val words = WidgetStates.calendarWords(Cal.NOT_STARTED)
        assertTrue(words.first.isNotBlank())
        assertTrue(words.second.isNotBlank())
    }

    @Test
    fun anUnpairedPhoneIsToldToPairAndNotToldItsCalendarIsEmpty() {
        assertEquals(
            Cal.NOT_PAIRED,
            WidgetStates.calendar(ready = true, paired = false, off = false, hidden = false, live = false, read = Read.CONTENT),
        )
        assertTrue(WidgetStates.calendarWords(Cal.NOT_PAIRED).first.contains("pairing"))
    }

    @Test
    fun switchedOffKeepsItsPlaceAndSaysSo() {
        // Decision D5: the widget STAYS. A vanishing widget reads as a fault.
        assertEquals(
            Cal.OFF,
            WidgetStates.calendar(ready = true, paired = true, off = true, hidden = false, live = true, read = Read.CONTENT),
        )
        val words = WidgetStates.calendarWords(Cal.OFF)
        assertEquals(Calendar.OFF_WIDGET, words.first)
        assertEquals(Calendar.OFF_WIDGET_SUB, words.second)
        assertTrue(words.first.contains("off"))
    }

    @Test
    fun aLinkThatIsDownSaysItHasNotCheckedRatherThanDrawingYesterdaysList() {
        assertEquals(
            Cal.STALE,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = false, live = false, read = Read.CONTENT),
        )
        assertEquals(Calendar.STALE, WidgetStates.calendarWords(Cal.STALE).first)
        // A read that ran out of its budget is its own sentence, not "not up to
        // date": the two are different faults and only one is the owner's.
        assertEquals(
            Cal.TIMED_OUT,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = false, live = true, read = Read.TIMED_OUT),
        )
        assertTrue(WidgetStates.calendarWords(Cal.TIMED_OUT).first.contains("Could not reach"))
        assertEquals(
            Cal.FAILED,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = false, live = true, read = Read.FAILED),
        )
        assertTrue(WidgetStates.calendarWords(Cal.FAILED).first.isNotBlank())
    }

    @Test
    fun appLockDrawsOneSentenceAndNoTitleAtAll() {
        assertEquals(
            Cal.HIDDEN,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = true, live = true, read = Read.CONTENT),
        )
        val words = WidgetStates.calendarWords(Cal.HIDDEN)
        assertEquals(Calendar.HIDDEN, words.first)
        assertTrue(words.first.contains("Hidden"))
        // The home screen is public: not one of the owner's own words.
        assertFalse(words.first.contains("Dentist"))
        assertFalse(words.second.contains("Dentist"))
        // Hidden wins over a stale link AND over a failed read: a locked phone
        // says the same one sentence whatever else is wrong.
        assertEquals(
            Cal.HIDDEN,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = true, live = false, read = Read.CONTENT),
        )
        // ...but "off" still wins over "hidden", because that one needs a tap to
        // Settings and is the more useful sentence.
        assertEquals(
            Cal.OFF,
            WidgetStates.calendar(ready = true, paired = true, off = true, hidden = true, live = true, read = Read.CONTENT),
        )
    }

    @Test
    fun aLiveReadWithRealEventsIsContent() {
        assertEquals(
            Cal.CONTENT,
            WidgetStates.calendar(ready = true, paired = true, off = false, hidden = false, live = true, read = Read.CONTENT),
        )
        assertEquals("" to "", WidgetStates.calendarWords(Cal.CONTENT))
    }

    // -------------------------------------------------------------- lines ----

    @Test
    fun theWidgetDrawsTodaysNextThreeEventsAndNeverMore() {
        val lines = Calendar.widgetLines(three, today, hidden = false)
        assertEquals(3, lines.size)
        // All-day first, then timed earliest to latest - the same order the
        // screen's day list uses.
        assertEquals("All day  Holiday", lines[0])
        assertEquals("09:00  Standup", lines[1])
        assertEquals("14:30  Dentist", lines[2])
        // Tomorrow's event is not in the list: the widget is about the day.
        assertFalse(lines.any { it.contains("Tomorrow") })
    }

    @Test
    fun anEmptyDaySaysNothingTodayAndIsNeverBlank() {
        val empty = Calendar.widgetLines(view(), today, hidden = false)
        assertEquals(listOf(Calendar.NOTHING_TODAY), empty)
        assertEquals("Nothing today", empty.single())
        // A day with only tomorrow's event is empty too.
        val tomorrowOnly = view(
            """{"id":"c0000000001","title":"Tomorrow","date":"2026-11-04","time":"10:00","all_day":false}""",
        )
        assertEquals(listOf(Calendar.NOTHING_TODAY), Calendar.widgetLines(tomorrowOnly, today, hidden = false))
    }

    @Test
    fun theWidgetsLinesHoldNoTitleWhileThePhoneIsLocked() {
        val lines = Calendar.widgetLines(three, today, hidden = true)
        assertEquals(3, lines.size)
        lines.forEach {
            assertTrue(it.contains(Calendar.HIDDEN))
            assertFalse(it.contains("Standup"))
            assertFalse(it.contains("Dentist"))
            assertFalse(it.contains("Holiday"))
        }
        // The time still shows: the shape of a day is not the private part.
        assertTrue(lines[1].startsWith("09:00"))
    }

    @Test
    fun theBrainRowsOneLineSaysWhatIsOnNowAndHowManyMore() {
        assertEquals(
            "All day  Holiday (+2 more today)",
            Calendar.todayLine(three, today, hidden = false),
        )
        assertEquals("Nothing today", Calendar.todayLine(view(), today, hidden = false))
        // A title is never spoken while the lists are hidden.
        assertFalse(Calendar.todayLine(three, today, hidden = true).contains("Holiday"))
        assertTrue(Calendar.todayLine(three, today, hidden = true).contains(Calendar.HIDDEN))
    }

    // ----------------------------------------------------------- the read ----

    @Test
    fun aReadThatCouldNotRunIsNeverDrawnAsAnEmptyDay() {
        // Every terminal state has words, and none of them says "Nothing today":
        // the two would be indistinguishable to the owner, and only one is true.
        val every = Cal.entries.filter { it != Cal.CONTENT }
        every.forEach { state ->
            val words = WidgetStates.calendarWords(state)
            assertTrue("$state has no headline", words.first.isNotBlank())
            assertTrue("$state has no sub-line", words.second.isNotBlank())
            assertFalse("$state claims nothing is on", words.first == Calendar.NOTHING_TODAY)
        }
        // And the one state whose words are taken from the feature's own module
        // is asserted against that module, so the two cannot drift.
        assertEquals(Calendar.OFF_WIDGET to Calendar.OFF_WIDGET_SUB, WidgetStates.calendarWords(Cal.OFF))
        assertEquals(Calendar.HIDDEN to Calendar.HIDDEN_SUB, WidgetStates.calendarWords(Cal.HIDDEN))
        assertEquals(Calendar.STALE to Calendar.STALE_SUB, WidgetStates.calendarWords(Cal.STALE))
        assertNotNull(WidgetStates.calendarWords(Cal.CONTENT))
    }
}
