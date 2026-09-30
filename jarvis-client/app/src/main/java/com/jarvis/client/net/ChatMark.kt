package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * "New section here" in History - the phone's side of docs/JARVIS-API.md
 * section 106 and section B of "Slice contract (frozen)" in
 * docs/OVERNIGHT-TAGS-DESIGN.md (the owner, 2026-09-30).
 *
 * In an opened chat of 10 or more messages, each message the owner sent gets a
 * "New section here" button that draws a divider ABOVE it. The owner's answer
 * is that it is only a divider: nothing here is ever sent to a model, and it
 * changes nothing about what "Continue this chat" carries on.
 *
 * THE PHONE STORES NOTHING about a marker. The PC keeps the list (sealed);
 * the phone sends exactly `{"id", "idx", "on"}` and draws what the PC's
 * conversation read says (`marks`, `markable`, `mark_why`). No card. Held on a
 * stale link (rule 4) by the runtime.
 *
 * Pure Kotlin, no Android types, so `ChatMarkTest` runs it on a plain JVM
 * against contract/history-cases.json (`words.mark*`, `mark_error_cases`).
 */
object ChatMark {
    const val MARK_PATH = "/api/history/mark"

    /** At most this many section breaks in one chat (fixture `mark_max`). */
    const val MAX = 20

    /** The button is offered from this many messages (fixture `mark_min_turns`). */
    const val MIN_TURNS = 10

    // ------------------------------------------------------------ words ---
    // Word for word with the desktop (fixture `words.mark*`).

    const val BUTTON = "New section here"
    const val BUTTON_LABEL = "New section here, before your message"
    const val DIVIDER = "New section"
    const val REMOVE = "Remove section break"
    const val DONE = "Section break added."
    const val REMOVED = "Section break removed."
    const val LIMIT = "You can have at most 20 section breaks in one chat."
    const val NO = "This chat cannot have section breaks."
    const val ERROR_FALLBACK = "Your PC did not save that section break."

    /** Shown on a button while its request runs (phone wording, like Fork's). */
    const val BUSY = "Saving…"

    /** Nothing is changed while the private lists are hidden. */
    const val HIDDEN = "Show your chats first, then choose the message."

    /** The sentence for each error code the PC names, when it sends no `message`. */
    val ERRORS = mapOf(
        "bad_request" to "Choose one of your messages in this chat.",
        "not_found" to "That chat is not kept any more, so no section break was saved.",
        "too_many_marks" to LIMIT,
    )

    /** The remove button's screen-reader name. */
    const val REMOVE_LABEL = REMOVE

    // ------------------------------------------------------- the reading ---

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    /**
     * The turn numbers of a `marks` array: whole numbers 0 or more, each once.
     * Anything else in it (a string, a fraction, a negative) is ignored, never
     * a crash; a missing or odd `marks` is none.
     */
    fun marksOf(arr: Any?): Set<Int> {
        val out = LinkedHashSet<Int>()
        (arr as? JsonArray).orEmpty().forEach { el ->
            val p = el as? JsonPrimitive ?: return@forEach
            if (p.isString) return@forEach
            val n = p.longOrNull ?: return@forEach
            if (n in 0..Int.MAX_VALUE.toLong()) out += n.toInt()
        }
        return out
    }

    /**
     * Whether a message gets the "New section here" button: the chat is
     * markable, it is one of the OWNER'S messages, the PC numbered it, and it
     * has no divider yet (a divider has its own Remove).
     */
    fun offered(markable: Boolean, role: String, idx: Int?, marks: Set<Int>): Boolean =
        markable && role == "user" && idx != null && idx >= 0 && idx !in marks

    /** Whether a divider is drawn above the turn numbered [idx]. */
    fun dividerAbove(idx: Int?, marks: Set<Int>): Boolean = idx != null && idx in marks

    /** Whether a 21st break would be refused - so the button can say so before asking. */
    fun full(marks: Set<Int>): Boolean = marks.size >= MAX

    // --------------------------------------------------------- requests ---

    /** The body: exactly `id`, `idx` and `on`, nothing else. */
    fun body(chatId: String, idx: Int, on: Boolean): String = buildJsonObject {
        put("id", chatId)
        put("idx", idx)
        put("on", on)
    }.toString()

    // ---------------------------------------------------------- answers ---

    /**
     * What a request came to. On success [marks] is the chat's whole list as
     * the PC now holds it and [said] the polite announcement; on a refusal
     * [said] is the one plain sentence and [marks] is null.
     */
    data class Result(val ok: Boolean, val said: String, val marks: Set<Int>? = null)

    /**
     * The one sentence a refused request shows (fixture `mark_error_cases`):
     * the PC's own non-empty [message] wins; else, for `not_markable`, the PC's
     * [markWhy] then [NO]; else the sentence for the [code]; else [ERROR_FALLBACK].
     */
    fun errorSentence(code: String?, message: String? = null, markWhy: String? = null): String {
        message?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        if (code == "not_markable") return markWhy?.trim()?.takeIf { it.isNotEmpty() } ?: NO
        if (code != null) ERRORS[code]?.let { return it }
        return ERROR_FALLBACK
    }

    /**
     * The PC's answer as a [Result]. [wanted] is what was asked (`on`), used
     * only for the announcement when the answer does not repeat it. A body
     * that is not readable JSON is the fallback sentence.
     */
    fun result(body: JsonObject?, wanted: Boolean): Result {
        if (body != null && body.flag("ok") == true) {
            val on = body.flag("on") ?: wanted
            return Result(ok = true, said = if (on) DONE else REMOVED, marks = marksOf(body["marks"]))
        }
        return Result(
            ok = false,
            said = errorSentence(body?.str("error"), body?.str("message"), body?.str("mark_why")),
        )
    }
}
