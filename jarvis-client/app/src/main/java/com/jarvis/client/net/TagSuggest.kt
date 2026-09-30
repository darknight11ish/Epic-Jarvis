package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/**
 * "Suggest tags overnight" in History -> Tags - the phone's side of
 * docs/JARVIS-API.md section 104 and section A of "Slice contract (frozen)" in
 * docs/OVERNIGHT-TAGS-DESIGN.md (the owner, 2026-09-30).
 *
 * While the owner sleeps, the model ON THE PC may look at a few untagged chats
 * and SUGGEST a tag. Each suggestion is an approval card. NOTHING is filed
 * without a tap on Approve. The phone only:
 * - reads `GET /api/history/tags/suggest` (when the Tags editor opens, and
 *   after a change; no push),
 * - sends `POST /api/history/tags/suggest` with exactly `{"enabled": bool}`, and
 * - shows the suggestion cards the ordinary approvals flow already brings
 *   (action [CARD_ACTION]); [cardText] picks which of the card's two texts.
 *
 * Turning it ON raises a card on the PC (`202 pending`); the switch stays OFF
 * on screen until a later GET says `enabled`. Turning it OFF is instant. THE
 * PHONE STORES NOTHING about it. Held on a stale link (rule 4) by the runtime.
 *
 * Pure Kotlin, no Android types, so `TagSuggestTest` runs it on a plain JVM
 * against contract/history-cases.json (`words.tag_suggest*`,
 * `tag_suggest_state_cases`, `tag_suggest_card_cases`).
 */
object TagSuggest {
    const val PATH = "/api/history/tags/suggest"

    /** The gate action of one suggestion card (tier ask). */
    const val CARD_ACTION = "chat_tag_suggest"

    /** The gate action of the switch's card. */
    const val SWITCH_ACTION = "chat_tags_suggest_on"

    // ------------------------------------------------------------ words ---
    // Word for word with the desktop (fixture `words.tag_suggest*`).

    const val LABEL = "Suggest tags overnight"
    const val OFF = "Off"
    const val ON = "On. Looks at up to 5 chats a night."
    const val PAUSED = "Paused after three 'no' answers. Turn it on again to carry on."
    const val PENDING =
        "Waiting for your approval. It turns on only if you approve the card, on your PC or phone."
    const val WAITING_ONE = "1 suggestion is waiting for your Approve."
    const val WAITING_OTHER = "{n} suggestions are waiting for your Approve."
    const val CARD_TITLE = "Suggested tag for a chat"
    const val CARD_BODY =
        "Jarvis thinks this chat belongs under \"{tag}\". Approve to file it there. Nothing else changes. " +
            "Deny and Jarvis will not suggest a tag for this chat again."
    const val CHAT_HIDDEN = "A chat from {when}"
    const val ERROR_FALLBACK = "Your PC did not change that setting."

    val ERRORS = mapOf(
        "bad_request" to "That request was not understood.",
        "no_local_model" to
            "Jarvis needs a model on this PC to do this, and none answered. It does not use a cloud model for this.",
        "no_tags" to "Make a tag first.",
    )

    /** Phone wording (not in the shared list): an older PC has no such route. */
    const val OLD_PC =
        "This PC's Jarvis cannot suggest tags yet. Update it by running apply-patches.ps1 on the PC."

    /** Shown while a change is being sent. */
    const val ASKING = "Asking your PC…"

    // ---------------------------------------------------------- reading ---

    /** `GET /api/history/tags/suggest`. */
    data class State(val enabled: Boolean, val paused: Boolean, val waiting: Int, val lastDay: String)

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    /**
     * The state from a GET answer, or null when the body is not one (`ok:
     * false`, or no boolean `enabled`). `paused` and `enabled` are never both
     * true (the PC guarantees it); if a buggy answer said both, PAUSED wins
     * and the switch reads off, the safer way.
     */
    fun state(body: JsonObject): State? {
        if (body.flag("ok") == false) return null
        val enabled = body.flag("enabled") ?: return null
        val paused = body.flag("paused") == true
        return State(
            enabled = enabled && !paused,
            paused = paused,
            waiting = (body.whole("waiting") ?: 0L).coerceIn(0L, 1_000_000L).toInt(),
            lastDay = body.str("last_day").orEmpty(),
        )
    }

    /** The one state line: paused, else on, else off. */
    fun stateLine(s: State): String = if (s.paused) PAUSED else if (s.enabled) ON else OFF

    /** The line under it, or null when nothing waits. */
    fun waitingLine(waiting: Int): String? = when {
        waiting <= 0 -> null
        waiting == 1 -> WAITING_ONE
        else -> WAITING_OTHER.replace("{n}", waiting.toString())
    }

    // --------------------------------------------------------- requests ---

    /** The body: exactly `enabled`, nothing else. */
    fun body(on: Boolean): String = buildJsonObject { put("enabled", on) }.toString()

    // ---------------------------------------------------------- answers ---

    /**
     * What a change came to. [ok] false: [said] is the one plain sentence.
     * [pending]: a card is on the PC, so the switch stays off and [said] is
     * [PENDING]. Otherwise [enabled] is what the PC now says.
     */
    data class Write(
        val ok: Boolean,
        val said: String? = null,
        val pending: Boolean = false,
        val enabled: Boolean? = null,
    )

    /** The PC's non-empty message, else the code's sentence, else [ERROR_FALLBACK]. */
    fun errorSentence(code: String?, message: String? = null): String {
        message?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        if (code != null) ERRORS[code]?.let { return it }
        return ERROR_FALLBACK
    }

    /**
     * A POST's answer. `202` with `pending: true` means a card is up; the
     * switch does NOT flip on the phone's say-so. `200` with `enabled` is the
     * PC's own word. Anything else is a refusal with a sentence.
     */
    fun write(code: Int, body: JsonObject?): Write {
        if (body != null && body.flag("ok") == true) {
            if (body.flag("pending") == true) return Write(ok = true, said = PENDING, pending = true)
            return Write(ok = true, enabled = body.flag("enabled"))
        }
        return Write(ok = false, said = errorSentence(body?.str("error"), body?.str("message")))
    }

    // ------------------------------------------------------- the card ---

    /**
     * Which text of a suggestion card to show. Under "Hide memory lists and
     * chat history" it is the PC's `text_hidden` (the `Chat:` line reads `A
     * chat from ...`); if the PC sent none, NOTHING is shown (fail closed: the
     * card's title still says what it is). Otherwise the whole `text`.
     */
    fun cardText(text: String?, textHidden: String?, hide: Boolean): String =
        if (hide) textHidden.orEmpty() else (text ?: textHidden).orEmpty()

    /**
     * The card the PC writes, rebuilt from its parts - used by the tests to
     * hold this app's shared words to the fixture (`tag_suggest_card_cases`).
     * The app itself shows the PC's text, it does not build one.
     */
    fun cardWords(title: String, whenText: String, tag: String, hidden: Boolean): String {
        val chat = if (hidden) CHAT_HIDDEN.replace("{when}", whenText) else "\"$title\" (last updated $whenText)"
        return CARD_TITLE + "\n\n" + CARD_BODY.replace("{tag}", tag) + "\n\nChat: $chat\nTag: $tag"
    }
}
