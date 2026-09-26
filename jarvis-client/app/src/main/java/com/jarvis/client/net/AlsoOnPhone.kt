package com.jarvis.client.net

import java.time.Instant
import java.time.ZoneId

/**
 * "Also on my phone" (the owner's decision of 2026-09-26, the cutting-edge
 * "Quick wins"; the feasibility audit's I93): an alarm handed to this phone's
 * own Clock app, or a reminder handed to its calendar as an event - by the
 * owner's TAP only, never on its own.
 *
 * WHY. The PC is Jarvis's only clock: a timer, alarm or reminder goes off on
 * the PC, and the phone hears of it only while it is connected (JARVIS-API
 * section 21.1). A copy in the phone's own Clock app rings even when the PC
 * is off or out of reach.
 *
 * THE TAP IS THE APPROVAL. There is no approval card: nothing is done on the
 * PC, and nothing is sent to it. The button opens the phone's own Clock app
 * (`AlarmClock.ACTION_SET_ALARM`) or calendar (`Intent.ACTION_INSERT` on
 * `CalendarContract.Events`) with the time and the owner's words filled in,
 * and the owner saves it THERE - the Clock app is asked to show its own
 * screen (`EXTRA_SKIP_UI` false). The two things the feasibility audit said
 * the button must warn about are one line, [NOTE]: keep both and BOTH ring;
 * and the phone's calendar may copy the event to the owner's Google account.
 * Jarvis's own late-alarm rule (a job heard of more than 10 minutes late
 * shows a silent "Missed at" notice) stays on Jarvis's own alarms.
 *
 * WHAT IS OFFERED ([offer]):
 *  - an ALARM that is active, with its words shown (not while the private
 *    lists are hidden): one that repeats every day, on weekdays or on chosen
 *    days is copied with those days; a one-off only when it is due within the
 *    next 24 hours, because the Clock app sets an alarm by time of day only -
 *    further ahead, [LATER] says so. One every few hours is not offered.
 *  - a REMINDER that is active and shown: an event at its next time, fifteen
 *    minutes long, repeating the same way when it repeats.
 *  - nothing else (timers, to-do items, briefings, "tell me when").
 *
 * The desktop has no such button, on purpose: docs/ARCHITECTURE.md section
 * 8, "On the phone, kept off the desktop".
 *
 * Pure Kotlin, no Android types, so `AlsoOnPhoneTest` runs it on a plain JVM;
 * `ui/screens/ComingUpPlate.kt` turns an offer into the Intent.
 */
object AlsoOnPhone {
    const val LABEL = "Also on my phone"

    /** The one line under Coming up, shown while any row offers the button. */
    const val NOTE =
        "\"Also on my phone\" copies an alarm to this phone's Clock app, or a reminder to its " +
            "calendar, so it rings even when your PC is off. You save it there. Keep both and both " +
            "will ring; the phone's calendar may copy the event to your Google account."

    /** A one-off alarm more than a day away. */
    const val LATER =
        "\"Also on my phone\" is offered from the day before: the phone's Clock app sets an alarm " +
            "by time of day only."

    const val NO_CLOCK = "This phone has no clock app that takes alarms from other apps."
    const val NO_CALENDAR = "This phone has no calendar app that takes events from other apps."

    /** How long an event made from a reminder is. */
    const val EVENT_MINUTES = 15

    /** What the Clock app gets. [days] are java.util.Calendar's (SUNDAY = 1 ... SATURDAY = 7). */
    data class Alarm(val hour: Int, val minute: Int, val message: String, val days: List<Int>)

    /** What the calendar gets. [rrule] is iCalendar's, or null for one event. */
    data class Event(val title: String, val beginMs: Long, val endMs: Long, val rrule: String?)

    sealed interface Offer {
        data class ToClock(val alarm: Alarm) : Offer
        data class ToCalendar(val event: Event) : Offer
        /** Not offered, and why - in words the row shows. */
        data class Later(val why: String) : Offer
    }

    /** The PC's weekday numbers (0 = Monday) as java.util.Calendar's. */
    private val CALENDAR_DAY = listOf(2, 3, 4, 5, 6, 7, 1)
    private val BYDAY = listOf("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    private val HHMM = Regex("([01]?\\d|2[0-3]):([0-5]\\d)")

    /** The PC's weekdays (0 = Monday) the rule repeats on, or null when it is not by day. */
    private fun pcDays(job: Schedule.Job): List<Int>? = when (job.ruleEvery) {
        "day" -> (0..6).toList()
        "weekday" -> (0..4).toList()
        "week" -> job.ruleDays.filter { it in 0..6 }.distinct().sorted().takeIf { it.isNotEmpty() }
        else -> null
    }

    /**
     * What "Also on my phone" would hand over for [job], or null when it is
     * not offered at all. [nowMs] is the phone's clock; [zone] the phone's time
     * zone, for a one-off's time of day.
     */
    fun offer(job: Schedule.Job, nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): Offer? {
        if (job.state != "active" || job.hidden) return null
        val due = job.due ?: return null
        val dueMs = (due * 1000).toLong()
        return when (job.kind) {
            "alarm" -> alarmOffer(job, dueMs, nowMs, zone)
            "reminder" -> reminderOffer(job, dueMs)
            else -> null
        }
    }

    private fun alarmOffer(job: Schedule.Job, dueMs: Long, nowMs: Long, zone: ZoneId): Offer? {
        val words = job.text.trim()
        if (job.repeats) {
            val days = pcDays(job) ?: return null
            val at = HHMM.matchEntire(job.ruleAt.trim()) ?: return null
            return Offer.ToClock(
                Alarm(at.groupValues[1].toInt(), at.groupValues[2].toInt(), words,
                    days.map { CALENDAR_DAY[it] }.sorted()),
            )
        }
        if (dueMs <= nowMs) return null
        if (dueMs - nowMs > 24L * 3600 * 1000) return Offer.Later(LATER)
        val t = Instant.ofEpochMilli(dueMs).atZone(zone)
        return Offer.ToClock(Alarm(t.hour, t.minute, words, emptyList()))
    }

    private fun reminderOffer(job: Schedule.Job, dueMs: Long): Offer? {
        val rrule = if (job.repeats) {
            val days = pcDays(job) ?: return null
            if (days.size == 7) "FREQ=DAILY" else "FREQ=WEEKLY;BYDAY=" + days.joinToString(",") { BYDAY[it] }
        } else {
            null
        }
        val title = job.text.trim().ifEmpty { "Reminder" }
        return Offer.ToCalendar(Event(title, dueMs, dueMs + EVENT_MINUTES * 60_000L, rrule))
    }

    /** Whether any row of [jobs] offers the button - then [NOTE] is shown once. */
    fun anyOffered(jobs: List<Schedule.Job>, nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): Boolean =
        jobs.any { offer(it, nowMs, zone) is Offer.ToClock || offer(it, nowMs, zone) is Offer.ToCalendar }
}
