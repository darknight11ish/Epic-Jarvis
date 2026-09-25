package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * The morning briefing (the owner's decisions of 2026-09-25;
 * docs/JARVIS-API.md section 22; backend `jarvis_briefing.py`).
 *
 * A short list of the day, put together on the PC WITHOUT the AI model:
 * today's calendar (only when it is set up for Jarvis), today's alarms,
 * reminders and timers, the to-do list, how many approval cards wait, and -
 * only when email is set up - how many unread emails and who the newest are
 * from (the owner's decision of 2026-09-25), or the number only when the
 * owner turns "Show who new emails are from" off ([SENDERS_LABEL]: OFF at
 * once, ON through ONE approval card on the PC, held on a stale link). The
 * senders are LINES of the email section, so [hide] takes them out too.
 * Weather and news are not available: no provider has been chosen.
 *
 * It is a kind of job on the PC's one scheduler, so it also shows in Coming
 * up. A briefing that repeats is set up with the scheduler's own route
 * (`POST /api/schedule/add` with kind "briefing") and waits for ONE approval
 * card that lists the next three times; stopping one is `POST
 * /api/schedule/act` with "delete", one at a time. Both are held on a stale
 * link. "Brief me now" (`POST /api/briefing/now`) only READS, so like every
 * read it is not held.
 *
 * THE NOTIFICATION says only [LOCK_SCREEN] - on the lock screen AND inside
 * it, whatever the privacy settings - and comes when the PC says the
 * briefing is READY (the `schedule` event, state "ready"), not when its time
 * comes ("fired"), so it is never ahead of the briefing. Tapping it opens
 * Mind, where the briefing is. "Hide memory lists and chat history" hides
 * its lines ([hide]); the counts stay.
 *
 * The desktop says the same words (jarvis-desktop/src/briefing.js); its
 * tests/briefing.mjs checks this file for them.
 *
 * Pure Kotlin, no Android types, so `BriefingTest` runs it on a plain JVM.
 */
object Briefing {
    const val PATH = "/api/briefing"
    const val NOW_PATH = "/api/briefing/now"
    const val SENDERS_PATH = "/api/briefing/senders"
    const val KIND = "briefing"

    const val TITLE = "Morning briefing"
    const val DETAIL =
        "A short list of your day, put together on your PC without the AI model. It only reads: " +
            "it changes nothing and approves nothing."
    const val EMPTY = "No briefing yet. Say \"brief me now\", or set one up to arrive each morning."
    const val NOW_LABEL = "Brief me now"
    const val NOW_BUSY = "Putting it together…"
    const val BUILDING = "Putting your briefing together…"
    const val MISSING =
        "Your PC's Jarvis does not have the morning briefing yet - run apply-patches.ps1 on the PC."
    const val KEPT = "Kept on your PC until Jarvis restarts. Nothing of it is written to disk."

    /**
     * "What did I miss?" (jarvis_briefing.build_missed, 2026-09-25) - the
     * desktop's briefing.js, word for word. A read, like "Brief me now".
     */
    const val MISSED_LABEL = "What did I miss?"
    const val MISSED_BUSY = "Looking…"
    const val MISSED_DETAIL =
        "Since you last talked to Jarvis, on either app: what went off, approval cards waiting, " +
            "unread email and what is next. Put together on your PC without the AI model."
    const val MISSED_MISSING =
        "Your PC's Jarvis does not have \"What did I miss?\" yet - run apply-patches.ps1 on the PC."
    const val MISSED_BODY = "{\"missed\":true}"

    /** All a notification ever says (jarvis_briefing.LOCK_SCREEN). */
    const val LOCK_SCREEN = "Jarvis: your morning briefing is ready."

    /** The line weather and news get (jarvis_briefing.OUTSIDE_LINE). */
    const val OUTSIDE_LINE =
        "Weather and news: not available. No provider has been chosen, so Jarvis fetches nothing " +
            "from the internet for this."

    /** Setting it up - the desktop's Settings, Morning briefing. */
    const val SETUP_TITLE = "When it arrives"
    const val SETUP_DETAIL =
        "Choose when your briefing arrives. It repeats, so Jarvis asks you once with an approval " +
            "card that lists the next three times; nothing is set up until you say yes. Stopping it is " +
            "immediate. You can also say \"brief me every weekday at 7\", or \"brief me now\" at any time."
    const val SETUP_NONE = "No briefing is set up."
    const val SET_LABEL = "Set up"
    const val STOP_LABEL = "Stop"
    const val ASKED =
        "Asked. Your PC shows an approval card that lists the next three times - nothing is set up until you approve it."
    const val READS_TITLE = "What it includes"
    const val SPOKEN =
        "It is read aloud only when you ask (\"read my briefing\"), and then only under your " +
            "private-answers setting, like a calendar answer."

    /** "Show who new emails are from" - the desktop's Settings, Morning briefing. */
    const val SENDERS_LABEL = "Show who new emails are from"
    const val SENDERS_DETAIL =
        "The briefing lists who your newest unread emails are from (up to 5), next to how many " +
            "there are. Off: the number only. Turning it on shows you an approval card first; turning " +
            "it off happens at once."
    const val SENDERS_WAITING = "Waiting for your yes on the approval card, on your PC or phone."
    const val SENDERS_MISSING =
        "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC."

    /** The repeats a briefing can be set up with - the scheduler's own rules. */
    val EVERY = listOf(
        "weekday" to "Weekdays (Monday to Friday)",
        "day" to "Every day",
        "week" to "Chosen days",
    )
    val DAY_NAMES = listOf("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    data class Section(
        val key: String,
        val title: String,
        val state: String,
        val summary: String,
        val items: List<String>,
    )

    data class Brief(
        val id: String,
        val heading: String,
        /** "schedule", "now", "chat" - or "missed" for "What did I miss?". */
        val source: String = "",
        val made: Double?,
        val missed: String,
        val sections: List<Section>,
        val notIncluded: List<String>,
        val hidden: Boolean,
    )

    data class Setup(
        val id: String,
        val state: String,
        val repeats: Boolean,
        val repeat: String,
        val whenWords: String,
    )

    /** The PC's `senders`: the setting, whether an ON card waits, how the last one ended. */
    data class Senders(
        val on: Boolean,
        val waiting: Boolean,
        val last: String,
        val lastOutcome: String,
        val why: String,
    )

    data class View(
        val briefing: Brief?,
        val building: Boolean,
        val setups: List<Setup>,
        val sources: List<String>,
        /** Null from a PC without the setting: the switch is not offered. */
        val senders: Senders? = null,
    )

    private fun section(o: JsonObject) = Section(
        key = o.text("key") ?: "",
        title = o.text("title") ?: "",
        state = o.text("state") ?: "",
        summary = o.text("summary") ?: "",
        items = (o["items"] as? JsonArray)?.mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull
        } ?: emptyList(),
    )

    /** `GET /api/briefing` or `POST /api/briefing/now`, read - or null when it is not one. */
    fun parse(body: JsonObject): View? {
        if (!body.containsKey("briefing")) return null
        val b = body["briefing"] as? JsonObject
        val setups = (body["setups"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.text("id")?.takeIf { Schedule.validId(it) } ?: return@mapNotNull null
            Setup(
                id = id,
                state = o.text("state") ?: "",
                repeats = o.flag("repeats") == true,
                repeat = o.text("repeat") ?: "",
                whenWords = o.text("when") ?: "",
            )
        } ?: emptyList()
        val sources = (body["sources"] as? JsonObject)?.let { s ->
            listOf("calendar", "email", "weather").mapNotNull { k -> (s[k] as? JsonObject)?.text("said") }
        } ?: emptyList()
        return View(
            briefing = b?.let {
                Brief(
                    id = it.text("id") ?: "",
                    heading = it.text("heading") ?: "",
                    source = it.text("source") ?: "",
                    made = it.num("made"),
                    missed = it.text("missed") ?: "",
                    sections = (it["sections"] as? JsonArray)?.mapNotNull { s -> (s as? JsonObject)?.let(::section) }
                        ?: emptyList(),
                    notIncluded = (it["not_included"] as? JsonArray)?.mapNotNull { n ->
                        (n as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull
                    } ?: emptyList(),
                    hidden = it.flag("hidden") == true,
                )
            },
            building = body.flag("building") == true,
            setups = setups,
            sources = sources,
            senders = (body["senders"] as? JsonObject)?.let(::senders),
        )
    }

    private fun senders(o: JsonObject): Senders? {
        val on = o.flag("on") ?: return null
        val last = o["last"] as? JsonObject
        return Senders(
            on = on,
            waiting = o.flag("waiting") == true,
            last = last?.text("message") ?: "",
            lastOutcome = last?.text("outcome") ?: "",
            why = o.text("why") ?: "",
        )
    }

    /** What the switch shows - the desktop's `sendersView`, the same rule. */
    data class SendersView(val show: Boolean, val checked: Boolean, val canChange: Boolean, val lines: List<String>)

    /**
     * Checked while on or while an ON card waits (so it can be turned OFF,
     * which takes the request back). OFF is never held; ON is held on a
     * stale link (rule 4).
     */
    fun sendersView(s: Senders?, live: Boolean): SendersView {
        if (s == null) return SendersView(show = false, checked = false, canChange = false, lines = listOf(SENDERS_MISSING))
        val lines = mutableListOf<String>()
        if (s.waiting) {
            lines += SENDERS_WAITING
        } else if (s.last.isNotEmpty() && s.lastOutcome != "enabled") {
            lines += s.last
        }
        if (s.why.isNotEmpty()) lines += s.why.replaceFirstChar { it.uppercase() } + "."
        val checked = s.on || s.waiting
        return SendersView(show = true, checked = checked, canChange = checked || live, lines = lines)
    }

    /** The body of `POST /api/briefing/senders`. */
    fun sendersBody(on: Boolean): String = "{\"enabled\":$on}"

    /** The sentence to show after a change, from the PC's own answer. */
    fun sendersSaid(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Done -> outcome.said ?: if (on) "Done." else "Done - the briefing shows the number only."
        is DesktopWrite.Outcome.Waiting -> outcome.said ?: SENDERS_WAITING
        is DesktopWrite.Outcome.Refused -> "Not changed. " + outcome.why
    }

    /**
     * The answer to "What did I miss?", or null when the PC answered with an
     * ordinary briefing - a PC from before it ignores the question, and then
     * [MISSED_MISSING] is said instead.
     */
    fun readMissed(body: JsonObject): View? {
        val v = parse(body) ?: return null
        return if (v.briefing?.source == "missed") v else null
    }

    /** A read that failed because this PC has no briefing: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** The lines taken out, for while "Hide memory lists and chat history" is on. The counts stay. */
    fun hide(v: View): View = v.copy(
        briefing = v.briefing?.let { b ->
            b.copy(sections = b.sections.map { it.copy(items = emptyList()) }, hidden = true)
        },
    )

    /** "(Due at 07:00 - the PC was off or asleep, so it is late.)" or "". */
    fun lateLine(b: Brief): String =
        if (b.missed.isEmpty()) "" else
            "(Due ${b.missed.replace("missed at ", "at ")} - the PC was off or asleep, so it is late.)"

    /** One setup in words - Coming up's words for the job. */
    fun setupLine(s: Setup): String {
        var words = if (s.repeats) s.repeat.ifEmpty { "a repeating briefing" } else s.whenWords.ifEmpty { "once" }
        if (s.state == "waiting") words += " - waiting for your yes on the approval card"
        else if (s.state == "paused") words += " - paused"
        return words
    }

    /** "7:00", "07:00", "7", "0730" or "730" - a phone's number pad has no colon. */
    private val CLOCK = Regex("([01]?\\d|2[0-3])(?::?([0-5]\\d))?")

    /**
     * The body that sets up ONE briefing that repeats - the scheduler's own
     * rule - or null when it is not one: every day, every weekday, or every
     * week on chosen days (0 = Monday). Never "every N hours", never a list.
     */
    fun setupBody(every: String, at: String, days: Collection<Int> = emptyList()): String? {
        if (EVERY.none { it.first == every }) return null
        val m = CLOCK.matchEntire(at.trim()) ?: return null
        val hhmm = m.groupValues[1].padStart(2, '0') + ":" + m.groupValues[2].ifEmpty { "00" }
        if (every == "week") {
            if (days.any { it !in 0..6 }) return null
            val d = days.toSortedSet()
            if (d.isEmpty()) return null
            return "{\"kind\":\"briefing\",\"repeat\":{\"every\":\"week\",\"at\":\"$hhmm\",\"days\":[" +
                d.joinToString(",") + "]}}"
        }
        return "{\"kind\":\"briefing\",\"repeat\":{\"every\":\"$every\",\"at\":\"$hhmm\"}}"
    }

    /** From a `schedule` event: the job id when a briefing is READY, else null. */
    fun readyFrom(data: JsonObject?): String? {
        if (data == null || data.text("state") != "ready" || data.text("kind") != KIND) return null
        return data.text("id")?.takeIf { Schedule.validId(it) }
    }

    /** Whether a `schedule` event is about a briefing (its time came, it is ready, or it changed). */
    fun isAbout(data: JsonObject?): Boolean = data?.text("kind") == KIND

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
