package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * Focus sessions (the owner's decision of 2026-09-25; docs/JARVIS-API.md
 * section 31; backend `jarvis_focus.py`, `focus.patch`).
 *
 * A timer plus Quiet. On the PC, Jarvis watches which app or site is in front
 * and names a drift out loud - on the PC only. This phone starts and stops a
 * session and shows the countdown, the counts and the report card. It never
 * sees what was in front: the PC sends only booleans and counts, and the
 * spoken line is refused to anything but the PC itself (ARCHITECTURE section
 * 8, "One-sided on purpose").
 *
 * Start, Resume and +10 minutes are held on a stale link (rule 4: they make
 * Jarvis watch, or watch longer); Pause and Stop are let through - they only
 * make it do less.
 *
 * Pure Kotlin, no Android types, so `FocusTest` runs it on a plain JVM
 * against `contract/focus-cases.json` - the PC's real answers.
 */
object Focus {
    const val PATH = "/api/focus"
    const val START_PATH = "/api/focus/start"
    const val ACT_PATH = "/api/focus/act"

    const val TITLE = "Focus session"
    const val DETAIL =
        "A timer plus Quiet. On the PC, Jarvis watches which app or site is in front " +
            "and says so when you drift - out loud, on the PC only. It keeps counts, never " +
            "what it saw, and nothing leaves the PC. Off unless you start it."
    const val PHONE_NOTE =
        "Watching what is in front happens on the PC only; this phone shows the " +
            "countdown and the counts."
    const val MISSING =
        "Your PC's Jarvis does not have focus sessions yet - run apply-patches.ps1 on the PC."

    const val DEFAULT_MINUTES = 25
    const val MIN_MINUTES = 1
    const val MAX_MINUTES = 240
    const val EXTEND_MINUTES = 10

    const val MINUTES_LABEL = "Minutes"
    const val ON_LABEL = "On what (optional)"

    /** The "On:" line while "Hide memory lists and chat history" hides what it is on. */
    const val INTENT_HIDDEN = "On: hidden until you confirm it is you."
    const val START = "Start"
    const val PAUSE = "Pause"
    const val RESUME = "Resume"
    const val EXTEND = "+10 minutes"
    const val STOP = "Stop"
    const val BAD_MINUTES = "A focus session is 1 to 240 minutes long."
    const val LAST_TITLE = "Last session"

    /** What the phone may ask for. "lock" is the desktop's alone: it is about the PC's screen. */
    val PHONE_ACTIONS = setOf("pause", "resume", "stop", "extend")

    /** Held on a stale link: they make Jarvis watch, or watch for longer. */
    val HELD_WHEN_STALE = setOf("resume", "extend")

    data class Report(
        val title: String,
        val lines: List<String>,
        val clean: Boolean,
        val streak: Int,
        val completed: Boolean,
    )

    data class View(
        val on: Boolean,
        val paused: Boolean,
        val state: String,
        val minutes: Int,
        val leftS: Long,
        val intent: String,
        val deferred: Boolean,
        val onTarget: Boolean?,
        val drifting: Boolean,
        val excused: Boolean,
        val drifts: Int,
        val line: String,
        val note: String,
        val report: Report?,
        val streak: Int,
    )

    /** `GET /api/focus`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val on = body.flag("on") ?: return null
        val rep = (body["report"] as? JsonObject)?.let { r ->
            Report(
                title = r.text("title") ?: "",
                lines = (r["lines"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                    ?: emptyList(),
                clean = r.flag("clean") == true,
                streak = r.num("streak")?.toInt() ?: 0,
                completed = r.flag("completed") == true,
            )
        }
        return View(
            on = on,
            paused = body.flag("paused") == true,
            state = body.text("state") ?: if (on) "locked" else "off",
            minutes = body.num("minutes")?.toInt() ?: 0,
            leftS = body.num("left_s")?.toLong()?.coerceAtLeast(0) ?: 0,
            intent = body.text("intent") ?: "",
            deferred = body.flag("deferred") == true,
            onTarget = body.flag("on_target"),
            drifting = body.flag("drifting") == true,
            excused = body.flag("excused") == true,
            drifts = body.num("drifts")?.toInt() ?: 0,
            line = body.text("line") ?: "",
            note = body.text("note") ?: "",
            report = rep,
            streak = body.num("streak")?.toInt() ?: 0,
        )
    }

    /** A read that failed because this PC has no focus sessions. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** Seconds left now, counted down from what the PC said [sinceMs] ago. */
    fun leftNow(v: View, sinceMs: Long): Long =
        if (!v.on || v.paused) v.leftS else (v.leftS - sinceMs / 1000).coerceAtLeast(0)

    /** "24:05", or "1:02:05" past an hour. */
    fun clock(seconds: Long): String {
        val s = seconds.coerceAtLeast(0)
        val h = s / 3600
        val m = (s % 3600) / 60
        val sec = s % 60
        return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
    }

    /** The minutes typed, or null when they are not 1 to 240. */
    fun minutesOf(text: String): Int? =
        text.trim().toIntOrNull()?.takeIf { it in MIN_MINUTES..MAX_MINUTES }

    /** `POST /api/focus/start`'s body, or null for minutes out of range. */
    fun startBody(minutes: Int, on: String): String? {
        if (minutes !in MIN_MINUTES..MAX_MINUTES) return null
        val words = on.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ").take(60)
        return "{\"minutes\":$minutes,\"on\":" + JarvisJson.encodeToString(
            kotlinx.serialization.serializer<String>(), words) + "}"
    }

    /** `POST /api/focus/act`'s body for one of [PHONE_ACTIONS], or null. */
    fun actBody(action: String): String? = when (action) {
        "extend" -> "{\"do\":\"extend\",\"minutes\":$EXTEND_MINUTES}"
        in PHONE_ACTIONS -> "{\"do\":\"$action\"}"
        else -> null
    }

    /** The buttons for a view, in order. */
    fun actionsOf(v: View): List<String> = when {
        !v.on -> emptyList()
        v.paused -> listOf("resume", "extend", "stop")
        else -> listOf("pause", "extend", "stop")
    }

    fun labelOf(action: String): String = when (action) {
        "pause" -> PAUSE
        "resume" -> RESUME
        "extend" -> EXTEND
        "stop" -> STOP
        else -> action
    }

    /** What the PC answered a start or an act, kept whole. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** Whether it changed, and the PC's sentence to show. */
    fun said(reply: Reply): Pair<Boolean, String> {
        val b = reply.body
        return when {
            reply.code in 200..299 && b?.flag("ok") != false ->
                true to (b?.text("said") ?: "Done.")
            reply.code == 404 || reply.code == 501 -> false to MISSING
            else -> false to (b?.text("error") ?: "Not changed (HTTP ${reply.code}).")
        }
    }

    /** Whether a `focus` event should make the plate read again (every one does). */
    fun isFocusEvent(kind: String): Boolean = kind == "focus"

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
