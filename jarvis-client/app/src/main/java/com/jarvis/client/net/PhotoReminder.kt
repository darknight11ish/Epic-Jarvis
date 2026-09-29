package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

/**
 * "Photo to reminder" (the owner's choice, 2026-09-28; JARVIS-API.md section
 * 83; backend `jarvis_photo_remind.py`).
 *
 * A photo or screenshot SHARED to Jarvis (the share target, `ACTION_SEND`
 * `image/...` - the same way in as a picture for chat) is offered "Find a
 * date in it" under the attached picture on Home. The phone sends the
 * picture - already shrunk by [ChatPicture]/`PictureEncoder`, in memory
 * only - to the owner's PC, `POST /api/photo/scan`. The PC reads the words
 * with Windows' own text recognition and finds the date, time and title
 * with plain code - not the AI model. The phone reads no text itself: heavy
 * work is the PC's, like speech-to-text.
 *
 * PROPOSES, NEVER ACTS. The answer is shown in boxes the owner can change.
 * Nothing happens until a tap:
 *  - "Add a Jarvis reminder": ONE `POST /api/schedule/add {"kind":
 *    "reminder", "date", "time", "text"}` - a one-off reminder, no card,
 *    like any one-off reminder the owner sets; held on a stale link;
 *  - "Also on my phone": the phone's own calendar opens with the event
 *    filled in ([calendarOffer], [AlsoOnPhone]'s own hand-over), and the
 *    owner saves it THERE. Nothing is sent to the PC.
 *
 * OUTSIDE TEXT. The words came from a picture someone else made: shown as
 * plain text only, never sent to the AI model from here, never learned, and
 * dropped - with the picture - when the proposal is closed. Nothing here is
 * saved to disk.
 *
 * Pure Kotlin, no Android types: `PhotoReminderTest` runs it on a plain JVM.
 * The words are the PC's (`backend/test_photo_remind.py` checks both apps).
 */
object PhotoReminder {
    const val SCAN_PATH = "/api/photo/scan"

    const val TITLE = "Photo to reminder"
    const val FIND_LABEL = "Find a date in it"
    const val OUTSIDE_NOTE =
        "Read from a picture on your PC, by plain code - not by the AI model. These words count " +
            "as outside text: Jarvis never acts on them, and nothing is kept once you close this."
    const val NOTHING_FOUND =
        "No date or time found in the picture. You can still type one in and add the reminder yourself."
    const val NO_WORDS = "No words could be read in the picture."
    const val FOUND_ONE = "Found a date. Check it, change anything, then tap to add it."
    fun foundMany(n: Int): String = "Found $n dates. Check the first, or pick another, then tap to add it."
    const val NO_TIME = "No time found - 09:00 is filled in. Change it if you need to."
    const val PASSED = "That time has already passed - change the date or time."
    const val ADD_LABEL = "Add a Jarvis reminder"
    const val CLOSE_LABEL = "Close"
    const val READING = "Reading the words in the picture on your PC…"
    const val WORDS_READ = "Words read from the picture"
    const val WHAT_LABEL = "What"
    const val DATE_LABEL = "Date (2026-10-12)"
    const val TIME_LABEL = "Time (14:00)"
    const val MISSING =
        "Your PC's Jarvis cannot read dates in pictures yet - run apply-patches.ps1 on the PC."
    const val NOT_A_PICTURE = "That is not a picture Jarvis can read."
    const val BAD_DATE = "A date looks like 2026-10-12."
    const val BAD_TIME = "A time looks like 14:00."
    const val NO_TEXT = "A reminder needs some words: what should Jarvis remind you of?"

    /** At most this many proposals are shown, as the PC sends. */
    const val MAX_FOUND = 3

    private val DATE = Regex("\\d{4}-\\d{2}-\\d{2}")
    private val TIME = Regex("([01]?\\d|2[0-3]):([0-5]\\d)")

    /** One date the PC found. [time] is "09:00" when none was found ([timeFound] false). */
    data class Found(
        val title: String,
        val date: String,
        val time: String,
        val timeFound: Boolean,
        val passed: Boolean,
        val whenWords: String,
    )

    /** What the PC read. Held on screen only. [text]: the words, outside text. */
    data class Scan(val found: List<Found>, val text: String, val said: String) {
        /** Never the words: a data class's toString would print them. */
        override fun toString(): String = "PhotoReminder.Scan(${found.size} found, ${text.length} chars)"
    }

    sealed interface Outcome {
        data class Ok(val scan: Scan) : Outcome
        data class Failed(val why: String) : Outcome
    }

    /** The scan's body: a `data:image/...;base64,` picture only, never a web address. */
    fun scanBody(dataUri: String): String? {
        val uri = dataUri.trim()
        val head = uri.take(48).lowercase()
        if (!head.startsWith("data:image/") || ";base64," !in head) return null
        if (uri.length > ChatPicture.BACKEND_MAX_BODY - 1024) return null
        return buildJsonObject { put("image", uri) }.toString()
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull

    /** The PC's answer (`code`, `body`), made safe to show. */
    fun parse(code: Int, body: JsonObject?): Outcome {
        if (code == 404 || code == 501) return Outcome.Failed(MISSING)
        if (code !in 200..299 || body == null) {
            return Outcome.Failed(body?.text("error") ?: "Your PC could not read the picture ($code).")
        }
        if (body.flag("ok") == false) return Outcome.Failed(body.text("error") ?: "Your PC could not read the picture.")
        val found = (body["found"] as? JsonArray).orEmpty().mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val date = o.text("date")?.takeIf { DATE.matches(it) } ?: return@mapNotNull null
            Found(
                title = o.text("title").orEmpty().take(200),
                date = date,
                time = o.text("time")?.takeIf { TIME.matches(it) } ?: "09:00",
                timeFound = o.flag("time_found") == true,
                passed = o.flag("passed") == true,
                whenWords = o.text("when").orEmpty(),
            )
        }.take(MAX_FOUND)
        val text = body.text("text").orEmpty()
        val said = when {
            text.isBlank() -> NO_WORDS
            found.isEmpty() -> NOTHING_FOUND
            found.size == 1 -> FOUND_ONE
            else -> foundMany(found.size)
        }
        return Outcome.Ok(Scan(found, text, said))
    }

    /** The line under one proposal: no time found, or already gone - or null. */
    fun hint(f: Found?): String? {
        if (f == null) return null
        return listOfNotNull(NO_TIME.takeIf { !f.timeFound }, PASSED.takeIf { f.passed })
            .joinToString(" ").ifEmpty { null }
    }

    /** What is wrong with the owner's boxes, or null when they can be sent. */
    fun problem(what: String, date: String, time: String): String? = when {
        !validDate(date.trim()) -> BAD_DATE
        !TIME.matches(time.trim()) -> BAD_TIME
        what.isBlank() -> NO_TEXT
        else -> null
    }

    private fun validDate(d: String): Boolean =
        DATE.matches(d) && runCatching { LocalDate.parse(d) }.isSuccess

    private fun hhmm(time: String): String {
        val m = TIME.matchEntire(time.trim()) ?: return time.trim()
        return m.groupValues[1].padStart(2, '0') + ":" + m.groupValues[2]
    }

    /** The tap's ONE reminder - never a repeat - or null when the boxes are not right. */
    fun reminderBody(what: String, date: String, time: String): String? {
        if (problem(what, date, time) != null) return null
        return buildJsonObject {
            put("kind", "reminder")
            put("date", date.trim())
            put("time", hhmm(time))
            put("text", what.trim())
        }.toString()
    }

    /**
     * "Also on my phone": the event for the phone's own calendar, at the
     * boxes' date and time in the phone's [zone], as long as a reminder
     * there ([AlsoOnPhone.EVENT_MINUTES]). Null when the boxes are not right.
     */
    fun calendarOffer(what: String, date: String, time: String, zone: ZoneId = ZoneId.systemDefault()): AlsoOnPhone.Offer? {
        if (problem(what, date, time) != null) return null
        val begin = runCatching {
            LocalDate.parse(date.trim()).atTime(LocalTime.parse(hhmm(time))).atZone(zone).toInstant().toEpochMilli()
        }.getOrNull() ?: return null
        return AlsoOnPhone.Offer.ToCalendar(
            AlsoOnPhone.Event(what.trim(), begin, begin + AlsoOnPhone.EVENT_MINUTES * 60_000L, null),
        )
    }
}
