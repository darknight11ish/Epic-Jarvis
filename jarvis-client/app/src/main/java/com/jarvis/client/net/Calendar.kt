package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalTime
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

/**
 * Jarvis's own calendar - events kept on the PC, read by both apps and by the
 * Android home-screen widget (the design brief of 2026-10-29,
 * `.dsh-scratch/JARVIS-CALENDAR-DESIGN-2026-10-29/REPORT.md`;
 * backend `jarvis_local_calendar.py`; docs/JARVIS-API.md section 163).
 *
 * THIS IS NOT THE PHONE'S CALENDAR. Nothing here reads or writes Android's own
 * `CalendarContract` provider, so the app asks for no calendar permission at
 * all: the events live in one SQLite file on the PC, beside `schedule.db`, and
 * this file only ever speaks to `/api/calendar`. That is the whole design - a
 * calendar Jarvis owns, not a window onto a Google account (the research in
 * Part 4 of the brief says every serious Android calendar is a
 * `CalendarContract` client and that is exactly what to avoid).
 *
 * IT IS ON BY DEFAULT, AND OFF HIDES RATHER THAN DELETES. `/api/calendar`
 * answers `"on": false` with no events while the PC's own switch is off; the
 * phone's Settings row and this screen's own switch both post
 * [SETTINGS_PATH]. Nothing is deleted either way, and a widget that vanishes
 * looks like a fault, so the widget keeps its place and says the calendar is
 * off (design decision D5).
 *
 * THE WALL CLOCK IS THE RECORD. `date`/`time` are the day and time the owner
 * typed, in the PC's own zone, and they are what every screen draws; this file
 * never turns them into an epoch to display them back. That is
 * `jarvis_schedule`'s own rule ("a daily 07:00 stays 07:00 across a clock
 * change") and it is why an event does not slide by an hour when the clocks
 * change.
 *
 * THE EVENT CARRIES ITS OWN WORDS. Unlike a `schedule` event - which carries an
 * id and a kind only, because a reminder's words are private - a calendar read
 * has to draw titles to be a calendar at all. So the privacy rules here are the
 * ones the reminder list already has: under App lock or "Hide memory lists and
 * chat history", the phone's own screens and the widget draw
 * [HIDDEN] instead of a title ([hidden], [widgetLines]' caller), and the
 * home screen - which is public - is the stricter of the two.
 *
 * Pure Kotlin, no Android types, so `CalendarTest` runs every branch on a plain
 * JVM. The zone and "today" are always passed in rather than read from the
 * clock inside, for the same reason: a test cannot lie about the date
 * otherwise.
 */
object Calendar {
    const val PATH = "/api/calendar"
    const val ADD_PATH = "/api/calendar/add"
    const val ACT_PATH = "/api/calendar/act"
    const val SETTINGS_PATH = "/api/calendar/settings"

    /** The event kind (an id-only doorbell, like every `schedule` event). */
    const val EVENT = "calendar"

    /** The section's own name, on both apps and in the widget's picker entry. */
    const val TITLE = "Jarvis Calendar"

    /**
     * What the calendar is, under its heading. Says "on your PC" rather than
     * "on the PC" - the phone reads this, and "the PC" is not where the owner
     * is standing.
     */
    const val UNDER =
        "Your own events, kept on your PC - beside the reminders, not in your phone's " +
            "calendar or a Google account. Both apps read the same list, and the home-screen " +
            "widget shows today."

    /** The PC's own switch is off: the screen still opens and says so. */
    const val OFF = "The Jarvis calendar is off."
    const val OFF_DETAIL = "Nothing is deleted. Turning it back on shows everything again."
    const val TURN_ON = "Turn it on"

    /** A PC without the route at all. */
    const val MISSING =
        "Your PC's Jarvis does not have its own calendar yet - run apply-patches.ps1 on the PC."

    /** Nothing on a day, and nothing in the month drawn. */
    const val EMPTY_DAY = "Nothing on this day."
    const val EMPTY_ADD = "Add an event"

    /** The widget's own three sentences, which are also the Brain row's. */
    const val NOTHING_TODAY = "Nothing today"

    /**
     * The home screen is public. Under App lock, or with "Hide memory lists and
     * chat history" on, the widget draws these instead of a title - the board
     * widget's own rule, in the same words: it is ONE sentence split into a
     * headline and a sub-line, exactly as the board widget splits its own
     * ("Hidden - open Jarvis to see it"). The two halves must not repeat each
     * other, so the headline is the single word and the sub-line carries the
     * instruction.
     */
    const val HIDDEN = "Hidden"
    const val HIDDEN_SUB = "open Jarvis to see it"

    /**
     * What a title reads while App lock or "Hide memory lists and chat history"
     * is on, on the phone's own screens. The same word the schedule uses for a
     * hidden job's words ([Schedule.HIDDEN_TEXT]), because it is the same rule.
     */
    const val HIDDEN_TITLE = "(hidden)"

    /** A link that is down or catching up: never a guess. */
    const val STALE = "Not up to date"
    const val STALE_SUB = "Tap to open Jarvis and reconnect"

    /** The widget while the feature is off (design decision D5). */
    const val OFF_WIDGET = "Jarvis Calendar is off"
    const val OFF_WIDGET_SUB = "tap to turn it on"

    /** The buttons on the screen. */
    const val ADD = "Add"
    const val SAVE = "Save"
    const val DELETE = "Delete"
    const val EDIT = "Edit"
    const val TODAY = "Today"
    const val OPEN = "Open the calendar"
    const val REMOVE_YES = "Yes, delete it"
    const val REMOVE_NO = "Keep it"

    /** Field labels on the add/edit sheet, and its own two tick boxes. */
    const val FIELD_TITLE = "What is it?"
    const val FIELD_DATE = "Date (YYYY-MM-DD)"
    const val FIELD_TIME = "Time (HH:MM)"
    const val FIELD_END_DATE = "Last day (YYYY-MM-DD)"
    const val FIELD_END_TIME = "Ends (HH:MM)"
    const val FIELD_PLACE = "Where (optional)"
    const val FIELD_NOTES = "Notes (optional)"
    const val FIELD_REMIND = "Remind me (minutes before)"

    /**
     * What the remind box really does in this slice, said under it.
     *
     * The owner's decision D3 (2026-10-29) was "store the field, ring nothing in
     * v1". A box labelled "Remind me" that never rings would be the one thing
     * this screen must not do - claim something happened that did not - so the
     * field says what it is for. The PC keeps the number, and a later slice is
     * what makes it ring.
     */
    const val REMIND_NOTE = "Saved with the event. Nothing rings yet."

    const val ALL_DAY = "All day"
    const val REPEATS = "Repeats"

    /**
     * The recurrence choices, in the order the sheet offers them.
     *
     * These are the PC's own four, and no more: `jarvis_local_calendar`'s
     * `RECURRENCES` is `("none", "daily", "weekly", "monthly")` and it refuses
     * anything else with a 400, so a fifth word here would be a choice the PC
     * rejects - a control that looks like it worked and did not. "Yearly" was
     * in the first draft of this list and was removed for exactly that reason.
     */
    val REPEAT_CHOICES: List<Pair<String, String>> = listOf(
        "none" to "Does not repeat",
        "daily" to "Every day",
        "weekly" to "Every week",
        "monthly" to "Every month",
    )

    /** The PC's caps, and the reader's own 300-character title rule. */
    const val MAX_TITLE = 300
    const val MAX_PLACE = 300
    const val MAX_NOTES = 2000
    const val MAX_DAYS = 90

    /**
     * The PC's own cap on `remind_minutes` (four weeks, `MAX_REMIND_MINUTES` in
     * `jarvis_local_calendar`), so the sheet can say "that is more than four
     * weeks" instead of letting the PC refuse it after the tap.
     */
    const val MAX_REMIND = 40_320

    /**
     * `?days=` for the screen's own read: as much as the PC will send in one
     * answer.
     *
     * The route's window always starts TODAY (the PC's today) and runs forward,
     * so a month grid can only draw days it has actually been told about. 90 is
     * the PC's own cap (`MAX_DAYS`), and taking all of it means the owner can
     * page three months ahead and still see their events - a 42-day read looked
     * right for one month and went blank the moment he pressed "next month",
     * which reads as "nothing booked" when nothing was ever asked for. Days
     * before today are not in the window at all, and the screens say so instead
     * of drawing an empty day (see [knows]).
     */
    const val SCREEN_DAYS = MAX_DAYS

    // ------------------------------------------------------------- shapes ----

    /**
     * One event, exactly as `/api/calendar` answers it.
     *
     * [allDay] is the PC's own flag. It is read as well as [time] because the
     * two can disagree on a PC that writes `"time": "00:00"` for an all-day
     * event: the flag is the truth, and [timeWords] follows it.
     */
    data class Event(
        val id: String,
        val title: String,
        val date: String,
        val time: String?,
        val endDate: String?,
        val endTime: String?,
        val allDay: Boolean,
        val place: String,
        val notes: String,
        val remindMinutes: Int?,
        val recurrence: String,
        val tz: String,
    ) {
        /** The day this event is drawn on, as the PC spelled it - null if it is not a date. */
        val day: LocalDate? get() = runCatching { LocalDate.parse(date) }.getOrNull()

        /** True when the event covers [day] - its first day through its last. */
        fun covers(day: LocalDate): Boolean {
            val from = runCatching { LocalDate.parse(date) }.getOrNull() ?: return false
            val to = runCatching { LocalDate.parse(endDate ?: date) }.getOrNull() ?: from
            return !day.isBefore(from) && !day.isAfter(to)
        }

        /** A single day's event: no end date, or one that is the same day. */
        val oneDay: Boolean get() = (endDate ?: date) == date
    }

    /**
     * A whole `/api/calendar` answer.
     *
     * [available] false is a PC whose route answered but could not read its
     * store (the PC sends 503 with `"available": false`). [on] false is the
     * feature switched off - honest, and not an error: the screen says so in
     * words and offers the switch, and the widget keeps its place.
     */
    data class View(
        val available: Boolean,
        val on: Boolean,
        val days: Int,
        val start: String,
        val end: String,
        val events: List<Event>,
        /** How many events the store holds in total, for the Settings line. Never a title. */
        val saved: Int,
        /**
         * The PC's own sentence when it could not read its store (or when its
         * settings file is damaged). Empty when it said nothing - and a screen
         * that drew "you have no events" over one of these would be inventing a
         * fact, because the PC said the opposite.
         */
        val why: String = "",
    ) {
        val startDay: LocalDate? get() = runCatching { LocalDate.parse(start) }.getOrNull()
        val endDay: LocalDate? get() = runCatching { LocalDate.parse(end) }.getOrNull()

        /** Nothing at all in the window that was read. */
        val nothing: Boolean get() = events.isEmpty()
    }

    /** What the PC answered a write, kept whole (like [Schedule.Reply]). */
    data class Reply(val code: Int, val body: JsonObject?)

    // -------------------------------------------------------------- parse ----

    /**
     * The answer, or null when it is not one.
     *
     * A null answer and an empty calendar are different things, and every
     * caller treats them differently: "could not read this" is never drawn as
     * "nothing on your calendar".
     */
    fun parse(body: JsonObject): View? {
        val window = body["window"] as? JsonObject
        val start = window?.text("start") ?: body.text("start")
        val end = window?.text("end") ?: body.text("end")
        val on = body.flag("on") ?: true
        val available = body.flag("available") ?: true
        // Neither flag present is not an answer this app can draw honestly.
        if (start == null && end == null && body["events"] == null) return null
        val events = (body["events"] as? JsonArray)
            ?.mapNotNull { (it as? JsonObject)?.let(::parseEvent) }
            ?: emptyList()
        // The count is the STORE's, not the window's, and the PC puts it where
        // the contract says: `sources.local.count` is how many events the whole
        // store holds, while `events` is only the ones in the window. A
        // top-level `count`/`saved` is read too, so a PC that moves it does not
        // silently make the Settings line wrong. The last fallback is the
        // window's own size - known to be true, and said as such by the caller.
        val sources = body["sources"] as? JsonObject
        val local = sources?.get("local") as? JsonObject
        val saved = body.num("count")?.toInt()
            ?: body.num("saved")?.toInt()
            ?: local?.num("count")?.toInt()
            ?: events.size
        return View(
            available = available,
            on = on,
            days = body.num("days")?.toInt() ?: 0,
            start = start ?: "",
            end = end ?: "",
            events = if (on) events else emptyList(),
            saved = saved,
            why = body.text("why") ?: "",
        )
    }

    /** One event, or null when it has no id or no day to be drawn on. */
    fun parseEvent(o: JsonObject): Event? {
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val date = o.text("date")?.takeIf { validDate(it) } ?: return null
        return Event(
            id = id,
            title = o.text("title") ?: "",
            date = date,
            time = o.text("time"),
            endDate = o.text("end_date"),
            endTime = o.text("end_time"),
            allDay = o.flag("all_day") ?: (o.text("time") == null),
            place = o.text("place") ?: "",
            notes = o.text("notes") ?: "",
            remindMinutes = o.num("remind_minutes")?.toInt(),
            recurrence = o.text("recurrence") ?: "",
            tz = o.text("tz") ?: "",
        )
    }

    /** A store id: "c" and ten lowercase hex characters, like schedule's own ids. */
    fun validId(id: String): Boolean = ID.matches(id)

    private val ID = Regex("c[0-9a-f]{10}")

    /** "2026-11-03" and nothing else - never 2026-02-30. */
    fun validDate(s: String): Boolean {
        if (!DATE_SHAPE.matches(s)) return false
        return runCatching { LocalDate.parse(s) }.isSuccess
    }

    /** "14:30", "9:05" or "24:00" - tidied to "HH:MM" by [tidyTime], or null. */
    fun tidyTime(s: String): String? {
        val m = TIME.matchEntire(s.trim()) ?: return null
        val h = m.groupValues[1].toInt()
        val min = m.groupValues[2].toInt()
        if (h == 24 && min != 0) return null
        return String.format(Locale.ROOT, "%02d:%02d", h, min)
    }

    /** "14:30" and nothing else, which is what the PC stores. */
    fun validTime(s: String): Boolean = TIME.matches(s) && tidyTime(s) == s

    private val DATE_SHAPE = Regex("\\d{4}-\\d{2}-\\d{2}")
    private val TIME = Regex("([01]?\\d|2[0-3]|24):([0-5]\\d)")

    // ---------------------------------------------------------- the month ----

    /**
     * One cell of the month grid: a day, or a blank that keeps the weekdays
     * under the right letters.
     */
    sealed class Cell {
        /** A padding square before the 1st or after the last day. */
        object Blank : Cell()

        data class Day(val date: LocalDate) : Cell()
    }

    /** A month, and the 42 cells a 6-row grid needs for it. */
    data class Month(val year: Int, val month: Int) {
        val first: LocalDate get() = LocalDate.of(year, month, 1)
        val last: LocalDate get() = YearMonth.of(year, month).atEndOfMonth()

        /** January 2026 -> December 2025. Never a month 0. */
        fun previous(): Month {
            val d = first.minusMonths(1)
            return Month(d.year, d.monthValue)
        }

        fun next(): Month {
            val d = first.plusMonths(1)
            return Month(d.year, d.monthValue)
        }

        /** "November 2026" - the heading. */
        val words: String get() = first.format(MONTH_WORDS)
    }

    private val MONTH_WORDS = DateTimeFormatter.ofPattern("LLLL yyyy", Locale.UK)

    /** The month a day falls in. */
    fun monthOf(day: LocalDate): Month = Month(day.year, day.monthValue)

    /**
     * The grid's cells: whole weeks, so a month needs between 28 and 42.
     *
     * [firstDay] is the week's first day - the phone's own choice is offered
     * as Monday, because the PC writes dates in the ISO order the rest of this
     * app shows, and a grid that starts on Sunday next to "2026-11-03" reads
     * as a different calendar.
     */
    fun cells(month: Month, firstDay: DayOfWeek = DayOfWeek.MONDAY): List<Cell> {
        val lead = (month.first.dayOfWeek.value - firstDay.value + 7) % 7
        val total = lead + month.last.dayOfMonth
        val weeks = (total + 6) / 7
        val out = ArrayList<Cell>(weeks * 7)
        repeat(lead) { out += Cell.Blank }
        for (d in 1..month.last.dayOfMonth) out += Cell.Day(LocalDate.of(month.year, month.month, d))
        while (out.size < weeks * 7) out += Cell.Blank
        return out
    }

    /** The seven weekday letters, in [firstDay]'s order: "M T W T F S S". */
    fun weekdayLetters(firstDay: DayOfWeek = DayOfWeek.MONDAY): List<String> =
        (0..6).map { DayOfWeek.of(((firstDay.value - 1 + it) % 7) + 1) }.map(::initial)

    private fun initial(d: DayOfWeek): String =
        d.getDisplayName(TextStyle.NARROW, Locale.UK).uppercase(Locale.UK)

    // --------------------------------------------------------- the events ----

    /** Every day in [view] that has at least one event on it. */
    fun daysWithEvents(view: View): Set<LocalDate> {
        val out = LinkedHashSet<LocalDate>()
        for (e in view.events) {
            val from = runCatching { LocalDate.parse(e.date) }.getOrNull() ?: continue
            val to = runCatching { LocalDate.parse(e.endDate ?: e.date) }.getOrNull() ?: from
            if (to.isBefore(from)) {
                out += from
                continue
            }
            var d = from
            // A bounded walk: a mistyped end date must not walk for a year in a
            // draw. 400 days is the PC's own cap territory and far past v1.
            var guard = 0
            while (!d.isAfter(to) && guard++ < 400) {
                out += d
                d = d.plusDays(1)
            }
        }
        return out
    }

    /**
     * One day's events, in the order a day reads: the all-day band first, then
     * the timed ones from earliest to latest, and a title as the tie-break so
     * the order never depends on the PC's own row order.
     */
    fun eventsOn(view: View, day: LocalDate): List<Event> =
        view.events.filter { it.covers(day) }.sortedWith(
            compareBy<Event>({ if (it.allDay) 0 else 1 }, { it.time ?: "" }, { it.title.lowercase(Locale.UK) }),
        )

    /** The events today, for the widget and the Brain row. Never more than [max]. */
    fun today(view: View, today: LocalDate, max: Int = 3): List<Event> =
        eventsOn(view, today).take(max)

    /** Whether anything at all is on [day]. */
    fun hasEvents(view: View, day: LocalDate): Boolean = view.events.any { it.covers(day) }

    /**
     * Whether the PC actually told us about [day] - it only ever sends a window
     * that STARTS TODAY and runs forward (`?days=N`, 1-90), so a day before
     * today, or past the end of what was sent, is a day this app knows nothing
     * about.
     *
     * The difference matters: "no dot on the 3rd" over an unread day and over a
     * genuinely empty day look identical, and only one of them is true. The
     * screens ask this before saying "Nothing on this day" ([EMPTY_DAY]), and
     * draw an unread day's number in the quiet colour.
     *
     * A view with no window in it (a PC that did not say) answers `true`: the
     * app then behaves exactly as it did before the window existed, rather than
     * refusing to draw anything.
     */
    fun knows(view: View, day: LocalDate): Boolean {
        val from = view.startDay ?: return true
        // The PC's `end` is exclusive - it sends `today + days` and stops there.
        val to = view.endDay ?: return !day.isBefore(from)
        return !day.isBefore(from) && day.isBefore(to)
    }

    /**
     * The days the PC did send, in words: "3 Nov to 3 Feb". What an unread day
     * is told, instead of a claim about that day. Empty when the answer carried
     * no window at all.
     */
    fun windowWords(view: View): String {
        val from = view.startDay
        val to = view.endDay
        return when {
            from != null && to != null -> "${from.format(DAY_MONTH)} to ${to.format(DAY_MONTH)}"
            from != null -> "from ${from.format(DAY_MONTH)}"
            else -> ""
        }
    }

    /** The one sentence a day the PC did not send is given. */
    fun unreadDay(view: View): String {
        val w = windowWords(view)
        return if (w.isEmpty()) {
            "Your PC did not say which days it read, so this day is not known."
        } else {
            "Not read: your PC sent $w, and nothing outside that is known."
        }
    }

    /**
     * Whether the whole of [month] falls outside the window the PC sent, so the
     * grid can say why a month is blank instead of letting it look empty.
     *
     * The PC's window starts at ITS today and runs `days` forward, so paging
     * back into last month is paging into days it never sent. A grid that drew
     * those as ordinary empty days would say "you have nothing on" about a
     * month nobody asked about.
     */
    fun monthUnread(view: View, month: Month): Boolean {
        val from = view.startDay ?: return false
        val to = view.endDay ?: return false
        // No overlap at all: the month ends before the window opens, or starts
        // at or after the day after its last one.
        return month.last.isBefore(from) || !month.first.isBefore(to)
    }

    // -------------------------------------------------------------- words ----

    /**
     * When an event is, in one line: "All day", "09:30", "09:30 - 10:15", or
     * "All day, 3 days" for a span. The dash is the app's own hyphen, because
     * an em dash is the Anti-Slop filter's business and a time range is not
     * prose.
     */
    fun timeWords(e: Event, today: LocalDate? = null): String {
        if (e.allDay) {
            val from = runCatching { LocalDate.parse(e.date) }.getOrNull()
            val to = runCatching { LocalDate.parse(e.endDate ?: e.date) }.getOrNull()
            if (from != null && to != null && to.isAfter(from)) {
                val days = java.time.temporal.ChronoUnit.DAYS.between(from, to) + 1
                return "All day, $days days"
            }
            return "All day"
        }
        val start = e.time ?: return "All day"
        val end = e.endTime
        if (end == null || end == start) return start
        // A span that ends before it starts ended the next day: say so rather
        // than draw "23:00 - 01:00" and look like a mistake.
        if (end < start) return "$start - $end (next day)"
        return "$start - $end"
    }

    /** "Every week", "Every day", ... or "" when it does not repeat. */
    fun recurrenceWords(e: Event): String = recurrenceLabel(e.recurrence)

    fun recurrenceLabel(wire: String): String {
        val w = wire.trim().lowercase(Locale.UK)
        return when (w) {
            "", "none", "off", "no", "once" -> ""
            "daily", "day", "every day" -> "Every day"
            "weekly", "week", "every week", "every monday" -> "Every week"
            "monthly", "month", "every month" -> "Every month"
            "yearly", "annual", "year", "every year" -> "Every year"
            "weekdays", "every weekday" -> "Every weekday"
            else -> "Repeats: $wire"
        }
    }

    /** The row under a title on a day list: time, place, repeat - each if it has one. */
    fun metaOf(e: Event): List<String> = listOfNotNull(
        timeWords(e),
        e.place.trim().takeIf { it.isNotEmpty() },
        recurrenceWords(e).takeIf { it.isNotEmpty() },
    )

    private val SHORT = DateTimeFormatter.ofPattern("EEE d MMM", Locale.UK)
    private val LONG = DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.UK)
    private val DAY_MONTH = DateTimeFormatter.ofPattern("d MMMM", Locale.UK)
    private val WEEKDAY = DateTimeFormatter.ofPattern("EEEE", Locale.UK)

    private fun isToday(d: LocalDate, today: LocalDate): Boolean = d == today
    private fun isTomorrow(d: LocalDate, today: LocalDate): Boolean = d == today.plusDays(1)
    private fun isYesterday(d: LocalDate, today: LocalDate): Boolean = d == today.minusDays(1)

    /**
     * A day for a heading: "Today", "Tomorrow", "Yesterday" - the words a
     * person uses - and "Monday 3 November" for everything else. [today] is
     * passed in, never read from the clock here, so a test can move it.
     */
    fun dayWords(d: LocalDate, today: LocalDate): String = when {
        isToday(d, today) -> "Today"
        isTomorrow(d, today) -> "Tomorrow"
        isYesterday(d, today) -> "Yesterday"
        else -> d.format(LONG)
    }

    /** The same day, always dated: "Today, 3 November" - what a widget's line says. */
    fun datedWords(d: LocalDate, today: LocalDate): String = when {
        isToday(d, today) -> "Today, " + d.format(DAY_MONTH)
        isTomorrow(d, today) -> "Tomorrow, " + d.format(DAY_MONTH)
        isYesterday(d, today) -> "Yesterday, " + d.format(DAY_MONTH)
        else -> d.format(SHORT)
    }

    /** A month grid's day number, and its accessibility description. */
    fun dayA11y(d: LocalDate, count: Int, today: LocalDate): String {
        val head = d.format(LONG)
        val day = when {
            isToday(d, today) -> "$head, today"
            isTomorrow(d, today) -> "$head, tomorrow"
            else -> head
        }
        return when (count) {
            0 -> day
            1 -> "$day, 1 event"
            else -> "$day, $count events"
        }
    }

    // ------------------------------------------------------------- widget ----

    /**
     * The lines the home-screen widget draws under its date: today's next
     * [max] events, or the single line [NOTHING_TODAY] when there are none.
     *
     * Never empty, and never a title while [hidden] - the home screen is
     * public, so a locked phone says [HIDDEN] instead of the owner's words.
     * That is decided here rather than in the widget so it is JVM-testable:
     * `CalendarWidgetTest` is the only place this rule is proved.
     */
    fun widgetLines(view: View, today: LocalDate, hidden: Boolean, max: Int = 3): List<String> {
        val events = today(view, today, max)
        if (events.isEmpty()) return listOf(NOTHING_TODAY)
        return events.map { e ->
            val when_ = if (e.allDay) "All day" else (e.time ?: "All day")
            if (hidden) "$when_  $HIDDEN" else "$when_  ${e.title.ifBlank { "(no title)" }}"
        }
    }

    /**
     * The Brain row's one line: what is on today, in the same words the widget
     * uses, or [NOTHING_TODAY]. [hidden] replaces every title, exactly as on the
     * widget.
     */
    fun todayLine(view: View, today: LocalDate, hidden: Boolean): String {
        val events = today(view, today, 1)
        if (events.isEmpty()) return NOTHING_TODAY
        val e = events.first()
        val rest = eventsOn(view, today).size - 1
        val head = if (e.allDay) "All day" else (e.time ?: "All day")
        val title = if (hidden) HIDDEN else e.title.ifBlank { "(no title)" }
        return if (rest > 0) "$head  $title (+$rest more today)" else "$head  $title"
    }

    // -------------------------------------------------------------- bodies ----

    /**
     * The body of one new event, or null when it cannot be one.
     *
     * The rules are the sheet's own, and they are checked here rather than
     * only on the PC so the owner is told which field is wrong instead of
     * reading a server sentence. [allDay] wins over [time]: an all-day event
     * sends no time at all, because a PC that stored "00:00" would draw it as a
     * timed midnight event.
     */
    fun addBody(
        title: String,
        date: String,
        time: String? = null,
        allDay: Boolean = false,
        endDate: String? = null,
        endTime: String? = null,
        place: String = "",
        notes: String = "",
        remindMinutes: Int? = null,
        recurrence: String = "none",
    ): String? {
        val t = tidyTitle(title) ?: return null
        if (!validDate(date)) return null
        val start: String? = if (allDay) null else (tidyTime(time ?: "") ?: return null)
        val last = endDate?.trim()?.takeIf { it.isNotEmpty() }?.let { d -> d.takeIf(::validDate) ?: return null } ?: date
        if (last < date) return null
        val end = if (allDay) null else endTime?.trim()?.takeIf { it.isNotEmpty() }?.let { tt ->
            tidyTime(tt) ?: return null
        }
        if (start != null && end != null && last == date && end <= start) return null
        val body = buildString {
            append("{\"title\":").append(quoted(t))
            append(",\"date\":").append(quoted(date))
            append(",\"all_day\":").append(allDay)
            if (start != null) append(",\"time\":").append(quoted(start))
            // `end_date` is ALWAYS sent, even when it is the same day. Leaving
            // it out means "keep whatever was there" to the PC (`_fields`:
            // "a multi-day span keeps its length"), so an owner who shortens a
            // five-day event to one day would watch it stay five days long. The
            // same field is what lengthens it, and sending the first day back is
            // how it is shortened.
            append(",\"end_date\":").append(quoted(last))
            if (end != null) append(",\"end_time\":").append(quoted(end))
            quotedOrOmit(place.trim(), MAX_PLACE)?.let { append(",\"place\":").append(it) }
            quotedOrOmit(notes.trim(), MAX_NOTES)?.let { append(",\"notes\":").append(it) }
            if (remindMinutes != null && remindMinutes >= 0) {
                append(",\"remind_minutes\":").append(remindMinutes.coerceAtMost(MAX_REMIND))
            }
            if (recurrence.isNotEmpty() && recurrence != "none") {
                append(",\"recurrence\":").append(quoted(recurrence))
            }
            append("}")
        }
        return body
    }

    /** The body of one change to one event: its id, "update", and the same fields. */
    fun updateBody(id: String, addBody: String?): String? {
        if (!validId(id)) return null
        val inner = addBody?.trim()?.removePrefix("{")?.removeSuffix("}") ?: return null
        return "{\"id\":\"$id\",\"do\":\"update\",$inner}"
    }

    /** The body of one delete: its id, and "delete". Never "all", never a range. */
    fun deleteBody(id: String): String? =
        if (validId(id)) "{\"id\":\"$id\",\"do\":\"delete\"}" else null

    /** The body of the PC's own ON/OFF switch. No card either way - a preference. */
    fun settingsBody(on: Boolean): String = "{\"on\":$on}"

    /**
     * One sentence about what is wrong with a would-be event, or null when it
     * is fine. The sheet calls this before [addBody] so the owner is told
     * which box, in plain words, instead of a server's own refusal.
     */
    fun problem(
        title: String,
        date: String,
        time: String?,
        allDay: Boolean,
        endDate: String?,
        endTime: String?,
        /** The "remind me" box, already turned into a number. */
        remind: Int? = null,
    ): String? {
        val t = title.trim()
        if (t.isEmpty()) return "Give the event a name first."
        if (t.length > MAX_TITLE) return "That name is longer than $MAX_TITLE characters."
        if (!validDate(date)) return "The date should look like 2026-11-03."
        if (!allDay) {
            if ((time ?: "").isBlank()) return "Add a time, or tick All day."
            if (tidyTime(time ?: "") == null) return "The time should look like 14:30."
        }
        val last = endDate?.trim()?.takeIf { it.isNotEmpty() }
        if (last != null) {
            if (!validDate(last)) return "The last day should look like 2026-11-05."
            if (last < date) return "The last day is before the first one."
        }
        val end = endTime?.trim()?.takeIf { it.isNotEmpty() }
        if (!allDay && end != null) {
            val e = tidyTime(end) ?: return "The end time should look like 15:15."
            if ((last ?: date) == date && e <= (tidyTime(time ?: "") ?: "")) return "The end time is before the start."
        }
        // The PC's own cap is four weeks (`MAX_REMIND_MINUTES`); saying so here
        // means the owner is told before the write, not after it.
        if (remind != null && remind > MAX_REMIND) {
            return "A reminder can be at most four weeks ($MAX_REMIND minutes) before."
        }
        return null
    }

    /** The title as the PC keeps it: trimmed, one line, at most [MAX_TITLE]. */
    fun tidyTitle(title: String): String? {
        val t = title.trim().replace(Regex("\\s+"), " ")
        if (t.isEmpty() || t.length > MAX_TITLE) return null
        return t
    }

    // -------------------------------------------------------------- reply ----

    /**
     * What the PC answered a write: whether it changed, and the sentence to
     * show.
     *
     * A 404 that says `no_such_event` is NOT the same as a 404 from a PC
     * without the route - the first means "it is already gone", which is a
     * success as far as the owner is concerned, and the same split
     * `Schedule.said` makes for a job.
     */
    fun said(reply: Reply): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")
        // The PC's 5xx answers carry an exception NAME in `error` and the
        // sentence a person can read in `message` ("the event could not be
        // saved"). Showing "OperationalError" to the owner would be technically
        // true and useless.
        val message = b?.text("message")
        return when {
            reply.code in 200..299 -> if (b?.flag("ok") == false) {
                false to (error ?: "Not saved.")
            } else {
                true to (b?.text("said") ?: defaultSaid(b))
            }
            reply.code == 404 && b?.text("reason") == "no_such_event" -> true to "That event was already gone."
            reply.code == 404 || reply.code == 501 -> false to MISSING
            reply.code == 409 -> false to (
                error ?: "Your calendar is full. Delete something first - nothing was dropped."
                )
            reply.code in 500..599 -> false to (
                message ?: error ?: "Not saved. Your PC answered ${reply.code}."
                )
            else -> false to (error ?: "Not saved. Your PC answered ${reply.code}.")
        }
    }

    private fun defaultSaid(b: JsonObject?): String = when {
        b?.get("event") is JsonObject -> "Saved."
        b != null && (b.flag("on") != null) -> if (b.flag("on") == true) {
            "The Jarvis calendar is on."
        } else {
            "The Jarvis calendar is off. Nothing was deleted."
        }
        else -> "Done."
    }

    /** A PC without the route at all: the screen says so instead of "empty". */
    fun missing(e: ApiError): Boolean =
        e == ApiError.NotFound || (e is ApiError.Server && e.code == 501)

    // ------------------------------------------------------------ helpers ----

    /**
     * The zone the phone believes the PC writes in, for "today".
     *
     * The PC owns the clock (it is the one that fires reminders), and every
     * date it stores is in its own zone. This is the phone's own zone as the
     * best available stand-in: the two are the same device pair on the same
     * private network, and every screen draws the dates the PC stored rather
     * than converting them, so the only thing this decides is which day the
     * word "Today" points at.
     */
    val deviceZone: ZoneId get() = ZoneId.systemDefault()

    /** Today, in [deviceZone] unless a caller says otherwise - tests always do. */
    fun todayNow(nowMs: Long = System.currentTimeMillis(), zone: ZoneId = deviceZone): LocalDate =
        java.time.Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDate()

    /** A stored "14:30" as a time, or null. */
    fun timeOf(e: Event): LocalTime? = e.time?.let { runCatching { LocalTime.parse(it) }.getOrNull() }

    private fun quoted(s: String): String = JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), s)

    private fun quotedOrOmit(value: String, cap: Int): String? {
        if (value.isEmpty()) return null
        return quoted(value.take(cap))
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && it.isString }?.contentOrNull?.trim()
            ?.takeIf { it.isNotEmpty() }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.let {
            it.doubleOrNull ?: it.intOrNull?.toDouble()
        }?.takeIf { it.isFinite() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
