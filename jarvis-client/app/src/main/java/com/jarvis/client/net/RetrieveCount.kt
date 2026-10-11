package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "3 recalled · 2 near" under an answer - the count-only half of the
 * desktop's retrieval trace (the owner's decision of 2026-10-08, "Just the
 * number"; docs/RETRIEVE-PORT-BRIEF.md, option B; docs/JARVIS-API.md section
 * 119; `retrieve-count.patch`).
 *
 * The desktop's HUD draws `/api/retrieve` as a strip under the question
 * reading "7 recalled · 6 near", and a panel whose rows are **the matched
 * words themselves** - a saved fact, a document, every Logseq page read off
 * disk, up to 150 characters each. That is exactly why the desktop blanks
 * the whole trace while "Windows Hello for memory lists and chat history" is
 * on. The owner chose the middle option for the phone: the number, never a
 * word of it.
 *
 * **How that is guaranteed, and not merely intended.** The words are not
 * sent at all: the phone asks with `count=1`, and the PC's answer is
 * `{"available": true, "count_only": true, "recalled": 3, "near": 2}` -
 * built by `_retrieve_counts()` in `jarvis_hud.py`, which never calls
 * `pack()`, the one place that puts matched text in a reply. There is no
 * second route and no second shape.
 *
 * On a PC that has not been patched the same question would be answered with
 * the words, so the phone never asks it: [CAPABILITY] must be true in
 * `/api/version`'s `capabilities` first ([TemporaryChat.CAPABILITY] is the
 * same pattern for the same reason). [parse] refuses anything that is not an
 * explicit count-only reply, so even a reply that somehow carried words
 * yields nothing at all rather than a count beside them.
 *
 * [Count] holds two whole numbers and no text field, so a count this app
 * draws cannot contain a fact, a document or a note - by construction, not
 * by care. The desktop already says these two words (`.trace-bar`'s
 * `N recalled · M near`, `jarvis_hud.html`), so this is the same sentence
 * with the words taken out, not a new surface.
 *
 * Shown only while the memory lists are NOT hidden: the PC itself answers
 * `{"available": false, "hidden": true}` for this route under "Windows Hello
 * for memory lists and chat history" (`lock/rules.rs` `redact_hud_read`), so
 * the phone asks for nothing and shows nothing in that state either - the
 * same rule, not a second one.
 *
 * Pure Kotlin, no Android types, so `RetrieveCountTest` runs it on a plain
 * JVM.
 */
object RetrieveCount {
    const val PATH = "/api/retrieve"

    /**
     * The capability `/api/version` reports once the PC answers `count=1`
     * (`jarvis_events._capability_probe`, asked of the running server:
     * `_hud_has("_retrieve_counts")`).
     */
    const val CAPABILITY = "retrieve_count"

    /** The query flag that asks for counts instead of the words. */
    const val COUNT_FLAG = "count=1"

    /** A PC without the count-only read (a 404 or a 501). Nothing is asked
     *  of it, so this is only ever the answer to a race: the PC was updated
     *  or restarted between the handshake and the question. */
    const val MISSING =
        "Your PC's Jarvis cannot count what it reached for yet - run apply-patches.ps1 on the PC " +
            "to update it."

    /**
     * The count-only reply, turned into two whole numbers.
     *
     * Two numbers are all this class can hold: there is no field for a
     * fact's words, an id or a kind, so nothing a PC sends can put one on
     * the screen through here.
     */
    data class Count(val recalled: Int, val near: Int) {
        /** False when the search reached for nothing - there is no line to
         *  show, and showing "0 recalled · 0 near" would be noise. */
        val any: Boolean get() = recalled > 0 || near > 0
    }

    /** What one read came to. */
    sealed interface Read {
        data class Shown(val count: Count) : Read
        /** A PC that does not answer the count-only read. */
        data object Missing : Read
        data class Failed(val why: String) : Read
    }

    /**
     * `GET /api/retrieve?q=...&count=1` for this answer's own question, or
     * null when there is no question to ask about (the same "nothing to
     * show" an empty conversation already is).
     *
     * The question is the owner's own words and is already on this screen
     * ([ChatSession.question]); it is percent-encoded so a `&` or a `#` in
     * it cannot smuggle a second query parameter past the PC.
     */
    fun path(question: String?): String? {
        val q = question?.trim().orEmpty()
        if (q.isEmpty()) return null
        val encoded = runCatching { java.net.URLEncoder.encode(q, "UTF-8") }.getOrNull()
        if (encoded.isNullOrEmpty()) return null
        return "$PATH?q=$encoded&$COUNT_FLAG"
    }

    /**
     * The count-only reply, read - or null when this is not one.
     *
     * Null is the safe answer, and it is returned for every reply that is
     * not exactly the count-only shape:
     *
     *  * no `count_only: true` (an older PC, or any other route's body);
     *  * a `hits` key of any kind - the desktop's own full trace, which
     *    carries the words ([parse] never looks at them);
     *  * `recalled` or `near` missing, quoted, fractional, negative or
     *    beyond a whole number.
     */
    fun parse(body: JsonObject): Count? {
        if (body.flag("count_only") != true) return null
        if (body.containsKey("hits")) return null
        val recalled = body.wholeNumber("recalled") ?: return null
        val near = body.wholeNumber("near") ?: return null
        return Count(recalled, near)
    }

    /**
     * The line under an answer: "3 recalled · 2 near", the same two words
     * and the same middle dot the desktop's own trace bar uses. Null when
     * there is nothing to say.
     */
    fun line(count: Count): String? {
        if (!count.any) return null
        return "${count.recalled} recalled · ${count.near} near"
    }

    /** A read that failed because this PC has no such route: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** A whole JSON number that is not a string, not null, and not negative. */
    private fun JsonObject.wholeNumber(key: String): Int? =
        (this[key] as? JsonPrimitive)
            ?.takeIf { it !is JsonNull && !it.isString }
            ?.intOrNull
            ?.takeIf { it >= 0 }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)
            ?.takeIf { it !is JsonNull && !it.isString }
            ?.booleanOrNull
}
