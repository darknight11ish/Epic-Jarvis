package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The words on an approval card, and what Jarvis says aloud about a card -
 * the same on this phone as in the desktop's Jarvis bar, widget and HUD.
 *
 * The creativity audit (2026-09-25, docs/creativity-2026-09-25/experience.md
 * finding 1) found the card speaking three dialects - this phone said
 * "Jarvis wants to learning enable", the desktop showed `switch_model`, and
 * Approve and Deny swapped places between screens. Now the PC writes every
 * title (backend/jarvis_card_words.py, served as each row's `notice.title`)
 * and every screen shows the same layout:
 *
 *     Needs your OK                     <- [KICKER]
 *     Jarvis wants to search the web    <- the title
 *     ...the rest of the card...
 *     [Deny]  [Approve]                 <- Deny left, Approve right ([BUTTONS])
 *
 * Deny on the left and Approve on the right matches this card's own swipe
 * (right approves, left denies) and Android's own dialogs, which put the
 * confirming button on the right. docs/ARCHITECTURE.md §3 has the reasons.
 *
 * CardWordsContractTest holds every word here to
 * `contract/card-words-cases.json`, which tools/gen_card_words_cases.py makes
 * from the backend - the desktop's tests/card-words.mjs reads the same file.
 */
object CardWords {
    /** The small label above every card's title. */
    const val KICKER = "Needs your OK"

    /** The two buttons, left to right, on every screen. */
    val BUTTONS = listOf("Deny", "Approve")

    /** The title of a row that names no action at all. */
    const val NO_ACTION = "Jarvis is asking for your approval"

    /**
     * What an EXPIRED card says - the FACT, and the one sentence both apps
     * draw: `backend/jarvis_card_words.py`'s `TIMED_OUT`, which the desktop
     * renders from `card-words.js`'s `CARD_TIMED_OUT`. The owner's ruling of
     * 2026-10-28, that "the cards on android should match the cards on
     * desktop", is what put this in one place: the phone said "Timed out — ask
     * the desktop to raise this again." and the PC said "Timed out: Jarvis
     * stopped waiting and refused it by itself." for the same event.
     *
     * An expired card is not decidable on either screen: the gate refuses it by
     * itself at the deadline, so it draws no buttons (DEF-010, 2026-10-11) and
     * this sentence is what explains the empty place they left.
     */
    const val TIMED_OUT = "Timed out: Jarvis stopped waiting and refused it by itself."

    /**
     * The phone's own second sentence on the same card - [TIMED_OUT] plus this
     * is the whole line. The PC does not show it: there the owner is already in
     * front of the window that raises cards, so "ask the desktop" would be
     * advice about the machine he is sitting at. Both strings come from the
     * PC's `jarvis_card_words` (`TIMED_OUT_NEXT`) and are held to it by
     * `CardWordsContractTest` against `contract/card-words-cases.json`.
     */
    const val TIMED_OUT_NEXT = "Ask the desktop to raise this again."

    /** "Open the card" - the line on every screen but Home while a card waits. */
    const val OPEN_CARD = "Open the card"

    /**
     * What Jarvis says during a SPOKEN question that waits on a card, and
     * afterwards - keyed by the chat stream's `: jarvis-status` word
     * (backend/jarvis_agent.py: "approval", then the gate's outcome). Fixed
     * sentences: nothing from the card. There is no approving by voice: the
     * voice check cannot tell a recording from the owner, so these only say
     * where the card is.
     */
    val VOICE: Map<String, String> = mapOf(
        "waiting" to "I need your OK for that. There's a card on your screen.",
        "approved" to "Approved. Carrying on.",
        "denied" to "OK, I won't do that.",
        "timed_out" to "That card timed out, so nothing was done.",
    )

    /** What the "Open the card" line shows: which card, and how many more. */
    data class Waiting(val id: String, val title: String, val more: String)

    /**
     * The "Open the card" line for [items], or null when nothing waits. The
     * NEWEST card is named - the last one read, most likely the one the
     * owner's last tap raised - and "and N more waiting" says the rest are
     * there too. The desktop's `cardLinkView` (card-link.js) says the same.
     */
    fun waiting(items: List<PendingItem>): Waiting? {
        val newest = items.lastOrNull() ?: return null
        val more = items.size - 1
        return Waiting(newest.id, newest.title, if (more > 0) "and $more more waiting" else "")
    }

    private val NOT_A_WORD = Regex("[^A-Za-z0-9 ]+")

    /**
     * A title for a row with no `notice` (a backend older than
     * approval-notice.patch): the action's name, quoted as a name - the PC's
     * own fallback for an action it has no phrase for, letter for letter.
     * Never from `prompt` or `detail`: a title also ends up on a lock screen.
     */
    fun fallbackTitle(action: String?): String {
        val words = (action ?: "")
            .replace('_', ' ')
            .replace(NOT_A_WORD, " ")
            .split(' ')
            .filter { it.isNotEmpty() }
            .joinToString(" ")
            .take(60)
            .trim()
        return if (words.isEmpty()) NO_ACTION else "Jarvis wants your OK for \"$words\""
    }

    /**
     * The short summary for a row whose PC sent none - a backend older than the
     * "Explain more" work (2026-10-09, backend/jarvis_card_words.py
     * `summary_for`): the card's own FIRST WHOLE SENTENCE, never cut mid-word,
     * falling back to [fallbackTitle] so it can never be blank.
     *
     * This is the phone's copy of the PC's own fallback rule, letter for letter:
     * the PC sends `notice.summary` on every row from a backend that has this
     * feature, so this only runs against an older one - and then it must still
     * be a readable line rather than the raw action id.
     */
    fun summaryFallback(full: String?, title: String = NO_ACTION): String {
        val flat = (full ?: "").replace(Regex("\\s+"), " ").trim()
        val stop = flat.indexOfFirst { it == '.' || it == '!' || it == '?' }
        val line = if (stop >= 0) flat.take(stop + 1).trim() else flat
        if (line.isEmpty()) return title
        return if (line.endsWith(".") || line.endsWith("!") || line.endsWith("?")) line else "$line."
    }
}

/**
 * A card's whole text as WORDS - never as machine JSON.
 *
 * The phone field test of 2026-10-29 (`REPORT.md` B7) caught a card drawing
 * `{ "from": "qwen3.5:9b", "to": "hf.co/…", "why": "preset" }` as its body,
 * on a PC whose approval cards are set to "Start short (default)". The PC had
 * sent no short summary and no whole card text for that row, so
 * [CardSummary.shown] had nothing to fold and fell back to the row's `detail` -
 * which `normalisePendingRow` stores as pretty-printed JSON.
 *
 * Two rules follow, and both are held by the plain-JVM `CardBodyWordsTest`:
 *
 *  - PROSE IS UNTOUCHED. A command, a plan, a diff or a sentence is what the
 *    PC sent, word for word - that text IS the thing being agreed to.
 *  - JSON IS NEVER DRAWN. A JSON object or list is said in plain words, and
 *    machine text that cannot be read is left out instead of dumped. The body
 *    of an approval card is for a person to answer, not a payload to display.
 *
 * The wording is deliberately plain ("From a to b (preset)", or one
 * "Label: value" line per field), and it never invents a translation for a
 * value the PC sent: the exact model name, path or command stays visible,
 * because that is what the owner is agreeing to.
 *
 * Pure Kotlin, no Android types, so a plain JVM test holds every rule.
 */
object CardBodyWords {

    /**
     * The keys that read as one sentence when they are the WHOLE object:
     * `{"from":"a","to":"b","why":"preset"}` -> "From a to b (preset)".
     */
    private val SENTENCE_KEYS = setOf("from", "to", "why", "reason")

    /** Keys whose value is the reason a card was raised, so it goes in brackets. */
    private val REASON_KEYS = setOf("why", "reason")

    /**
     * [text] as a person reads it: ordinary text exactly as sent, JSON said in
     * plain words, and machine text that cannot be read left out ("").
     */
    fun words(text: String?): String {
        val trimmed = text?.trim().orEmpty()
        if (trimmed.isEmpty()) return ""
        if (!looksMachine(trimmed)) return trimmed
        val element = runCatching { JarvisJson.parseToJsonElement(trimmed) }.getOrNull()
        return when (element) {
            is JsonObject -> objectWords(element)
            is JsonArray -> listWords(element)
            // JSON-shaped, but not a document this helper can say in words:
            // leave it out rather than print it raw.
            else -> ""
        }
    }

    /** True when [text] is a JSON object or list rather than words a person wrote. */
    fun isMachine(text: String?): Boolean {
        val trimmed = text?.trim().orEmpty()
        if (!looksMachine(trimmed)) return false
        return when (runCatching { JarvisJson.parseToJsonElement(trimmed) }.getOrNull()) {
            is JsonObject, is JsonArray -> true
            else -> false
        }
    }

    /**
     * The SHAPE of JSON, whether or not it actually parses - so a truncated
     * payload is recognised as machine text and hidden, not drawn as prose.
     */
    private fun looksMachine(trimmed: String): Boolean =
        trimmed.length >= 2 &&
            (
                (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
                    (trimmed.startsWith("[") && trimmed.endsWith("]"))
                )

    /** One JSON object, as one sentence for the common from/to/why shape, else one line per field. */
    private fun objectWords(obj: JsonObject): String {
        val fields = obj.entries.mapNotNull { (key, value) ->
            val field = fieldKey(key).takeIf { it.isNotEmpty() } ?: return@mapNotNull null
            valueWords(value)?.let { field to it }
        }
        if (fields.isEmpty()) return ""
        val oneSentence = fields.all { it.first in SENTENCE_KEYS } &&
            fields.any { it.first == "from" || it.first == "to" }
        if (oneSentence) {
            return fields.joinToString(" ") { (key, value) ->
                if (key in REASON_KEYS) "($value)" else "$key $value"
            }.replaceFirstChar { it.uppercaseChar() }
        }
        return fields.joinToString("\n") { (key, value) -> "${label(key)}: $value" }
    }

    /** One JSON value inside a field, as words; null when there is nothing sayable. */
    private fun valueWords(value: JsonElement): String? = when (value) {
        is JsonNull -> null
        is JsonPrimitive -> value.content.trim().takeIf { it.isNotEmpty() }
        is JsonObject -> innerWords(value)
        is JsonArray -> scalarList(value) ?: listWords(value).takeIf { it.isNotEmpty() }
    }

    /** An object inside a field: "First name: Priya; Age: 3" - never braces. */
    private fun innerWords(obj: JsonObject): String? {
        val parts = obj.entries.mapNotNull { (key, value) ->
            val primitive = value as? JsonPrimitive ?: return@mapNotNull null
            if (primitive is JsonNull) return@mapNotNull null
            val words = primitive.content.trim().takeIf { it.isNotEmpty() } ?: return@mapNotNull null
            val field = fieldKey(key).takeIf { it.isNotEmpty() } ?: return@mapNotNull null
            "${label(field)}: $words"
        }
        return parts.takeIf { it.isNotEmpty() }?.joinToString("; ")
    }

    /** A list of plain values: "a, b" - null unless every item is a readable value. */
    private fun scalarList(list: JsonArray): String? {
        if (list.isEmpty()) return null
        val parts = list.map { element ->
            val primitive = element as? JsonPrimitive ?: return null
            if (primitive is JsonNull) return null
            primitive.content.trim().takeIf { it.isNotEmpty() } ?: return null
        }
        return parts.joinToString(", ")
    }

    /** A JSON list as words: a plain value a line, an object said in words. */
    private fun listWords(list: JsonArray): String =
        list.mapNotNull { element ->
            when (element) {
                is JsonNull -> null
                is JsonPrimitive -> element.content.trim().takeIf { it.isNotEmpty() }
                is JsonObject -> objectWords(element).takeIf { it.isNotBlank() }
                is JsonArray -> listWords(element).takeIf { it.isNotBlank() }
            }
        }.joinToString("\n")

    /** A field name as a person reads it: `first_name` -> "First name". */
    private fun label(key: String): String =
        key.split(' ', '_', '-')
            .filter { it.isNotEmpty() }
            .joinToString(" ")
            .replaceFirstChar { it.uppercaseChar() }

    /** A field name compared the way JSON keys are usually written. */
    private fun fieldKey(key: String): String = key.trim().lowercase()
}
