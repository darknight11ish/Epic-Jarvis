package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/**
 * "Always keep in mind" - the owner's decision of 2026-09-24, and
 * docs/JARVIS-API.md section 6 (`GET` / `POST /api/memory/profile`).
 *
 * A short list of facts the owner pins. Jarvis reads them with every
 * question, word for word: a search alone only finds facts that share words
 * or meaning with the question, so "the owner is vegetarian" was missing
 * from "what should I cook tonight?". The PC keeps fact ids only; the words
 * are the facts' own, never summarised or rewritten, and a pinned fact that
 * is forgotten, corrected or erased leaves the list by itself. The whole
 * list may use [DEFAULT_LIMIT] characters.
 *
 * Pinning is the owner's own tap on a fact they can see - no approval card,
 * no "are you sure?" - and it is held on a stale link, like Forget
 * ([com.jarvis.client.JarvisRuntime.pinFact]). The phone pins from Mind ->
 * "Saved automatically" (the only list of current facts it shows) and
 * unpins from its own section ([com.jarvis.client.ui.screens.AlwaysKeepInMindSection]).
 * The desktop says the same words (jarvis-desktop/src/memory-profile.js).
 *
 * The POST's answers, as `backend/rebuilt/jarvis_memory.py` `handle_profile`
 * sends them:
 * - 200 `{"ok": true, "id", "pinned", "changed", "chars", "limit", "note"}`.
 * - 409 `{"ok": false, "reason": "too_long" | "fact_too_long" |
 *   "not_current", "error": <the sentence to show>}` - refused, in words.
 * - 404 `{"ok": false, "reason": "no_such_fact"}` - the fact is gone. A 404
 *   WITHOUT that reason, or a 501, is a PC that cannot pin at all.
 * - 503 - the memory is not running. 400 - a bad request.
 *
 * Pure Kotlin, no Android types, so `MemoryProfileTest` runs it on a plain JVM.
 */
object MemoryProfile {
    const val PATH = "/api/memory/profile"

    fun body(id: Long, pinned: Boolean): String = "{\"id\":$id,\"pinned\":$pinned}"

    /** The section's title and its one line - both apps, word for word. */
    const val TITLE = "Always keep in mind"
    const val UNDER = "Jarvis reads these with every question, word for word. Keep it short."

    /** The buttons on a fact. */
    const val PIN = "Pin"
    const val UNPIN = "Unpin"
    const val PINNING = "Pinning…"
    const val UNPINNING = "Unpinning…"

    /** Said after a pin or an unpin went through. The desktop says the same. */
    const val PINNED = "Pinned. Jarvis reads it with every question."
    const val UNPINNED = "Unpinned. The fact itself stays."

    /** The list with nothing on it. */
    const val EMPTY = "Nothing pinned yet. Use Pin on a fact to have Jarvis read it with every question."

    /** A PC without the list: a 404 or a 501 on the read. */
    const val MISSING = "Your PC's Jarvis does not have the \"Always keep in mind\" list yet."

    /** A pin the PC could not do at all (no route, or an older store). */
    const val TOO_OLD =
        "Not changed. Your PC's Jarvis cannot keep facts in mind yet - run apply-patches.ps1 on the PC to update it."

    /** A 404 that said "no such fact". */
    const val ALREADY_GONE = "Jarvis had no such fact any more."

    const val NOT_RUNNING = "Not changed. Jarvis's memory is not running on your PC right now."

    /** The PC's limit when it does not say (jarvis_memory.PROFILE_LIMIT). */
    const val DEFAULT_LIMIT = 1200

    /** 1200 -> "1,200". By hand, so every phone language says the same as the desktop. */
    fun grouped(n: Int): String {
        val digits = maxOf(0, n).toString()
        val out = StringBuilder()
        digits.forEachIndexed { i, c ->
            if (i > 0 && (digits.length - i) % 3 == 0) out.append(',')
            out.append(c)
        }
        return out.toString()
    }

    /** "N of 1,200 characters used" - both apps' words. */
    fun usedLine(chars: Int, limit: Int): String = grouped(chars) + " of " + grouped(limit) + " characters used"

    data class Fact(val id: Long, val text: String, val added: Double?)

    data class Profile(val facts: List<Fact>, val chars: Int, val limit: Int) {
        val ids: Set<Long> get() = facts.mapTo(HashSet()) { it.id }
    }

    /**
     * `GET /api/memory/profile`, read - or null when it is not the list (no
     * `facts` array). A fact without a whole-number id, or without text, is
     * dropped, never guessed.
     */
    fun parse(body: JsonObject): Profile? {
        val raw = body["facts"] as? JsonArray ?: return null
        val facts = raw.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.number("id")?.longOrNull ?: return@mapNotNull null
            val text = o.text("text") ?: return@mapNotNull null
            Fact(id, text, o.number("added")?.doubleOrNull?.takeIf { it.isFinite() })
        }
        val chars = body.number("chars")?.longOrNull?.toInt() ?: facts.sumOf { it.text.length }
        val limit = body.number("limit")?.longOrNull?.toInt() ?: DEFAULT_LIMIT
        return Profile(facts, chars, limit)
    }

    /** A read that failed because this PC has no such list: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** What the PC answered a pin, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /**
     * Whether the list changed as asked (so it is read again), and the
     * sentence to show. A refusal is the PC's own sentence ("That would make
     * the list too long - unpin something first").
     */
    fun said(reply: Reply, pinned: Boolean): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")?.let { DesktopWrite.asSentence(it) }
        // A refusal's own words exactly as the desktop shows them (its
        // backend_refusal raises the first letter and adds nothing).
        val refusal = b?.text("error")?.replaceFirstChar { it.uppercase() }
        return when {
            reply.code in 200..299 -> if (b?.flag("ok") == false) {
                false to ("Not changed. " + (error ?: "Your PC said no, without a reason."))
            } else {
                true to (if (pinned) PINNED else UNPINNED)
            }
            reply.code == 404 && b?.text("reason") == "no_such_fact" -> true to ALREADY_GONE
            reply.code == 404 || reply.code == 501 -> false to TOO_OLD
            reply.code == 409 -> false to (refusal ?: "Not changed. Your PC said no, without a reason.")
            reply.code == 503 -> false to NOT_RUNNING
            reply.code == 400 -> false to ("Not changed. " + (error ?: "Your PC did not understand the request."))
            else -> false to ("Not changed. Your PC answered ${reply.code}." + (error?.let { " $it" } ?: ""))
        }
    }

    private fun JsonObject.number(key: String): JsonPrimitive? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
