package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Look at this" and "Watch with me": the words and the few rules each app
 * decides for itself (the owner's decision of 2026-09-28,
 * docs/SCREEN-DESIGN.md; docs/JARVIS-API.md sections 62 and 96; the session
 * is the PC's - backend/jarvis_screen.py).
 *
 * The PC's status says only fixed words and numbers: on/off, the minutes
 * left, a pause or end reason from a FIXED list ("a password box"), whether a
 * look is held - never a program, a site, a title or a word from a screen.
 * This file holds the phone to the same table the desktop's look-rules.js is
 * held to (`contract/screen-cases.json`, written by
 * tools/gen_screen_cases.py from the backend): the sign's words, the line
 * after a look, and the mark a question carries.
 *
 * No Android in this file, so the JVM tests can hold every rule
 * ([com.jarvis.client.ScreenRulesTest]).
 */
object ScreenRules {
    const val TITLE = "Jarvis is watching"
    const val PAUSED_TITLE = "Jarvis is watching - paused"
    const val ENDED_TITLE = "Watching ended"
    const val STOP = "Stop watching"
    const val MORE = "20 more minutes"
    const val DROP = "Forget this look"
    const val DOT = " · "

    /** How long a sign keeps saying why a session ended. */
    const val ENDED_SHOW_S = 15

    /** The mark a question carries so the PC adds the held look's words. */
    const val MARK = "look"

    /** The PC's route for its own Watch with me (JARVIS-API section 62), and its event. */
    const val PATH = "/api/screen"
    const val EVENT = "screen_watch"

    /** The body of the one thing this phone ever sends there: end the PC's watching. */
    const val STOP_BODY = """{"do":"stop"}"""

    /** The message field a Watch-with-me picture is marked with, and its value. */
    const val SCREEN_FIELD = "screen"
    const val SCREEN_PHONE = "phone"

    val SEEN: Map<String, String> = mapOf(
        "hint" to "Press the Look at this key, then ask - Jarvis reads the words on the window in " +
            "front, once, and keeps nothing.",
        "held" to "Jarvis is holding what it read for your follow-up questions. It is thrown away " +
            "when it is two minutes old or the Jarvis bar closes.",
        "held_short" to "Answered using what Jarvis read from your screen (words only).",
        "watching_note" to "Ask about your screen and Jarvis looks when you start. A picture is " +
            "never saved.",
        "link" to "Reconnecting to Jarvis. Stop still works.",
        "left_under_a_minute" to "under a minute left",
        "title" to TITLE,
        "paused_title" to PAUSED_TITLE,
        "ended_title" to ENDED_TITLE,
        "stop" to STOP,
        "more" to MORE,
        "drop" to DROP,
    )

    data class Sign(
        val show: Boolean,
        val on: Boolean,
        val title: String,
        val detail: String,
        val stop: String,
        val more: String,
        val tone: String,
    )

    private fun JsonObject.str(key: String): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim().orEmpty()

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.booleanOrNull == true

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

    /** "24 min left", "under a minute left", or "" when it is not a time. */
    fun minutesLeft(leftS: Double?): String {
        if (leftS == null || leftS < 0) return ""
        if (leftS < 60) return SEEN.getValue("left_under_a_minute")
        val whole = leftS.toLong()
        return "${(whole + 59) / 60} min left"
    }

    private val NONE = Sign(false, false, "", "", "", "", "off")

    /**
     * What the sign says, from the PC's status: the phone's notification and
     * Home line. [endedAgo]: seconds since a session ended - shown for
     * [ENDED_SHOW_S].
     */
    fun sign(status: JsonObject?, stale: Boolean = false, endedAgo: Int? = null): Sign {
        val s = status ?: return NONE
        if (s.flag("on")) {
            val paused = s.str("state") == "paused"
            val left = minutesLeft(s.num("left_s"))
            val bits = mutableListOf<String>()
            if (paused) {
                bits += "Paused: " + s.str("pause_words").ifEmpty { "something private is in front" }
            }
            val ending = s.flag("ending_soon")
            if (ending && !paused) bits += "Ending soon - " + left.ifEmpty { "almost done" }
            else if (left.isNotEmpty()) bits += left
            if (stale) bits += SEEN.getValue("link")
            return Sign(
                show = true,
                on = true,
                title = if (paused) PAUSED_TITLE else TITLE,
                detail = bits.joinToString(DOT),
                stop = STOP,
                more = if (ending) MORE else "",
                tone = if (paused) "paused" else "watching",
            )
        }
        if (s.str("state") == "ended") {
            val ago = endedAgo ?: 0
            if (ago >= ENDED_SHOW_S) return NONE
            val words = s.str("ended_words")
            return Sign(
                show = true,
                on = false,
                title = ENDED_TITLE,
                detail = if (words.isNotEmpty()) "Ended: $words" else "",
                stop = "",
                more = "",
                tone = "ended",
            )
        }
        return NONE
    }

    data class Line(val text: String, val tone: String)

    /**
     * What is said after ONE look, from the note or the refusal the PC sent
     * (`{ok, note, said}`). Never a word from the screen: a `part` in a wrong
     * answer is never read.
     */
    fun lookLine(payload: JsonObject?): Line {
        val p = payload
        if (p != null && p.flag("ok")) {
            return Line(p.str("note").ifEmpty { "Looked at your screen." }, "ok")
        }
        return Line(
            p?.str("said").orEmpty().ifEmpty {
                "Jarvis could not look at your screen just now. Try again. If it keeps " +
                    "happening, check Settings, Look at this and Watch with me."
            },
            "warn",
        )
    }

    /** The mark a question carries, or "": only while a look is held. */
    fun screenMark(status: JsonObject?): String =
        if (status?.flag("look_held") == true) MARK else ""
}
