package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * "Fork from here" in History - the phone's side of docs/JARVIS-API.md
 * section 110 and the "Fork contract (frozen)" at the end of
 * docs/CHAT-TAGS-DESIGN.md.
 *
 * On a message in an opened chat, the owner can start a NEW chat that holds
 * everything up to and including that message. The PC does the copying; the
 * phone only sends `POST /api/history/fork` with exactly `{"id", "upto"}`
 * (`upto` is the turn's `idx`) and opens the chat the PC names in its answer.
 *
 * THE PHONE STORES NOTHING about a fork. It does not build the new title
 * (the PC writes "Fork of ..."), does not check the chat's kind beyond the
 * PC's own `forkable`, and shows no card: it is the owner's own kept words
 * and nothing leaves the PC. Held on a stale link (rule 4) by the runtime.
 *
 * Pure Kotlin, no Android types, so `ForkTest` runs it on a plain JVM against
 * the shared fixture (contract/history-cases.json, `words.fork*`).
 */
object ChatFork {
    const val FORK_PATH = "/api/history/fork"

    // ------------------------------------------------------------ words ---
    // Word for word with the desktop (fixture `words.fork*`).

    /** The button. */
    const val BUTTON = "Fork from here"

    /** Its help text (a hover title on the desktop; kept for the fixture check). */
    const val TITLE = "Start a new chat that begins with everything up to this message."

    /** The button's screen-reader name after the owner's own message. */
    const val LABEL_USER = "Fork from here, after your message"

    /** The button's screen-reader name after one of Jarvis's kept answers. */
    const val LABEL_ASSISTANT = "Fork from here, after Jarvis's answer"

    /** Shown on the button while the request runs. */
    const val BUSY = "Forking…"

    /** A chat that cannot be forked, when the PC gave no reason of its own. */
    const val NO = "This chat cannot be forked."

    /** When the PC's answer has neither a sentence nor a code this app knows. */
    const val ERROR_FALLBACK = "Your PC did not fork that chat."

    /** Under "Hide memory lists and chat history": nothing is forked from a hidden list. */
    const val HIDDEN = "Show your chats first, then choose the message."

    /** The sentence for each error code the PC names, when it sends no `message`. */
    val ERRORS = mapOf(
        "bad_request" to "Choose a message in this chat to fork from.",
        "bad_upto" to "That message is not in this chat, so it was not forked.",
        "not_found" to "That chat is not kept any more, so it was not forked.",
    )

    /** The `Fork of ` the PC puts before the original title (for the fixture check only; never built here). */
    const val PREFIX = "Fork of "

    /** The longest title the PC makes, prefix included (fixture `fork_title_max`). */
    const val TITLE_MAX = 80

    /** The screen-reader name for a message by [role] ("assistant" or anything else = the owner's own). */
    fun label(role: String): String = if (role == "assistant") LABEL_ASSISTANT else LABEL_USER

    /** `Forked into "{title}".`, with the title exactly as the PC sent it. */
    fun done(title: String): String = "Forked into \"$title\"."

    /**
     * Whether a message gets the button: the chat is forkable, the message is
     * one the owner sent or one of Jarvis's kept answers, and the PC numbered it.
     */
    fun offered(forkable: Boolean, role: String, idx: Int?): Boolean =
        forkable && (role == "user" || role == "assistant") && idx != null && idx >= 0

    // --------------------------------------------------------- requests ---

    /** The body: exactly `id` and `upto`, nothing else. */
    fun body(chatId: String, upto: Int): String = buildJsonObject {
        put("id", chatId)
        put("upto", upto)
    }.toString()

    // ---------------------------------------------------------- answers ---

    /**
     * What a fork came to. On success [id] is the new chat's id and [said] the
     * `Forked into ...` line; on a refusal [said] is the one plain sentence.
     */
    data class Result(
        val ok: Boolean,
        val said: String,
        val id: String? = null,
        val title: String? = null,
        val turns: Int? = null,
        val tagId: Int? = null,
    )

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    /**
     * The one sentence a refused fork shows, the same rule as the desktop's
     * and the fixture's `fork_error_cases`: the PC's own [message] wins; else
     * the sentence for the [code] (`not_forkable` = [NO]); else [ERROR_FALLBACK].
     */
    fun errorSentence(code: String?, message: String? = null): String {
        message?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        if (code == "not_forkable") return NO
        if (code != null) ERRORS[code]?.let { return it }
        return ERROR_FALLBACK
    }

    /**
     * The PC's answer as a [Result]. A [body] that is not readable JSON is not
     * a fork the phone can open, so it is the fallback sentence. A `200` whose `id` is missing or not a chat id is refused the same way:
     * there is nothing to open.
     */
    fun result(body: JsonObject?): Result {
        if (body != null && body.flag("ok") == true) {
            val id = body.str("id")
            if (id != null && ChatHistory.validConversationId(id)) {
                val title = body.str("title") ?: ""
                return Result(
                    ok = true,
                    said = done(title),
                    id = id,
                    title = title,
                    turns = body.whole("turns")?.toInt(),
                    tagId = body.whole("tag_id")?.toInt(),
                )
            }
            return Result(ok = false, said = ERROR_FALLBACK)
        }
        return Result(ok = false, said = errorSentence(body?.str("error"), body?.str("message")))
    }
}
