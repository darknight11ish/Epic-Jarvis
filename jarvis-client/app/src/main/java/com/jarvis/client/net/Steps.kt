package com.jarvis.client.net

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * What Jarvis is doing while it answers - the `step` event
 * (`backend/jarvis_agent.py`, `_step_event`), shown on Mind the way the
 * desktop's Brain → Live shows it (`jarvis-desktop/src/brain.js`, `stepText`).
 *
 * The event is an allowlist: `{"phase", "tool"?, "ok"?, "round"?}`, with a
 * tool NAME from the backend's own table (or "unknown") - never a tool's
 * arguments or result, never the model's text or reasoning. So these lines
 * can only ever say which tool, never what it saw. Sent only while tools are
 * switched on (`[tools] enabled`).
 */
object Steps {

    /** Lines kept. The desktop keeps 300 in a window that can stay open all day. */
    const val KEEP = 100

    /** One line: when it arrived on this phone, and what it said. */
    data class Line(val time: String, val text: String)

    /** The desktop's `stepText`, word for word. */
    fun text(data: JsonElement?): String {
        val o = data as? JsonObject ?: JsonObject(emptyMap())
        val named = (o["tool"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            ?.takeIf { it.isNotEmpty() }
        val tool = named ?: "a tool"
        val shown = if (tool == "unknown") "a tool Jarvis does not have" else tool
        val phase = (o["phase"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        return when (phase) {
            "model" -> {
                val round = (o["round"] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull
                if (round != null && round > 1) "asking the model again (round $round)" else "asking the model"
            }
            "tool_started" -> "using $shown"
            "tool_finished" ->
                if ((o["ok"] as? JsonPrimitive)?.booleanOrNull == false) "$shown failed" else "$shown done"
            "tool_refused" ->
                if (tool == "unknown") "the model asked for a tool Jarvis does not have" else "$shown not allowed"
            "answer" -> "writing the answer"
            else -> "working"
        }
    }

    private val CLOCK = DateTimeFormatter.ofPattern("HH:mm:ss")

    /** "14:03:09" - the desktop's time column, in this phone's time zone. */
    fun clock(epochMs: Long, zone: ZoneId = ZoneId.systemDefault()): String =
        CLOCK.format(Instant.ofEpochMilli(epochMs).atZone(zone))

    /** [lines] with [line] added last, keeping the newest [keep]. */
    fun append(lines: List<Line>, line: Line, keep: Int = KEEP): List<Line> =
        (lines + line).takeLast(keep)

    /** Said under the lines - the desktop's own note, for a phone. */
    const val NOTE =
        "What Jarvis is doing, newest last: asking the model, each tool it uses and whether it " +
            "worked, then writing the answer. Tools show here only when they are switched on " +
            "([tools] enabled in the config on your PC). The model's own step-by-step thinking " +
            "is not shown: it can quote your email or files, and it would reach this phone."
}
