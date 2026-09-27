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
 * "Between us" - the owner's decision of 2026-09-27, and
 * docs/JARVIS-API.md section 44 (`GET` / `POST /api/memory/shared`).
 *
 * A shared joke or nickname is an ordinary fact - "Remember: we call the
 * printer 'the beast'" is saved exactly as any other "Remember: ..." is -
 * with a label the owner's own tap adds: `meta.kind = "shared"`. Jarvis
 * may use it in an answer when relevant, in Warm manner only (never
 * Plain) - never set automatically, and never by the model.
 *
 * Tagging is the owner's own tap on a fact they can see - no approval
 * card, no "are you sure?" - and it is held on a stale link, like Pin
 * ([com.jarvis.client.JarvisRuntime.setShared]). The phone tags from Brain
 * -> "Saved automatically" and untags from its own section
 * ([com.jarvis.client.ui.screens.BetweenUsSection]). The desktop says the
 * same words (jarvis-desktop/src/memory-shared.js).
 *
 * The POST's answers, as `backend/rebuilt/jarvis_memory.py` `handle_shared`
 * sends them:
 * - 200 `{"ok": true, "id", "shared", "changed"}`.
 * - 409 `{"ok": false, "reason": "not_current", "error": <the sentence to
 *   show>}` - refused, in words.
 * - 404 `{"ok": false, "reason": "no_such_fact"}` - the fact is gone. A
 *   404 WITHOUT that reason, or a 501, is a PC that cannot tag at all.
 * - 503 - the memory is not running. 400 - a bad request.
 *
 * Pure Kotlin, no Android types, so `MemorySharedTest` runs it on a plain JVM.
 */
object MemoryShared {
    const val PATH = "/api/memory/shared"

    fun body(id: Long, shared: Boolean): String = "{\"id\":$id,\"shared\":$shared}"

    /** The section's title and its one line - both apps, word for word. */
    const val TITLE = "Between us"
    const val UNDER = "Shared jokes and nicknames. Jarvis may bring one up when it fits - never in Plain manner."

    /** The toggle on a fact. */
    const val SHARE = "Between us"
    const val UNSHARE = "Not between us"
    const val SHARING = "Tagging…"
    const val UNSHARING = "Untagging…"

    /** Said after a tag or an untag went through. The desktop says the same. */
    const val SHARED = "Tagged. It is now in \"Between us\"."
    const val UNSHARED = "Untagged. The fact itself stays."

    /** The list with nothing on it. */
    const val EMPTY = "Nothing tagged yet. Use \"Between us\" on a fact to add a shared joke or nickname here."

    /** A PC without the list: a 404 or a 501 on the read. */
    const val MISSING = "Your PC's Jarvis does not have the \"Between us\" list yet."

    /** A tag/untag the PC could not do at all (no route, or an older store). */
    const val TOO_OLD =
        "Not changed. Your PC's Jarvis cannot tag \"Between us\" facts yet - run apply-patches.ps1 on the PC to update it."

    /** A 404 that said "no such fact". */
    const val ALREADY_GONE = "Jarvis had no such fact any more."

    const val NOT_RUNNING = "Not changed. Jarvis's memory is not running on your PC right now."

    data class Fact(val id: Long, val text: String, val created: Double?)

    data class Shared(val facts: List<Fact>) {
        val ids: Set<Long> get() = facts.mapTo(HashSet()) { it.id }
    }

    /**
     * `GET /api/memory/shared`, read - or null when it is not the list (no
     * `facts` array). A fact without a whole-number id, or without text, is
     * dropped, never guessed.
     */
    fun parse(body: JsonObject): Shared? {
        val raw = body["facts"] as? JsonArray ?: return null
        val facts = raw.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.number("id")?.longOrNull ?: return@mapNotNull null
            val text = o.text("text") ?: return@mapNotNull null
            Fact(id, text, o.number("created")?.doubleOrNull?.takeIf { it.isFinite() })
        }
        return Shared(facts)
    }

    /** A read that failed because this PC has no such list: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    /** What the PC answered a tag or untag, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /**
     * Whether the list changed as asked (so it is read again), and the
     * sentence to show. A refusal is the PC's own sentence ("That fact is
     * no longer in use, so it cannot be a shared joke").
     */
    fun said(reply: Reply, shared: Boolean): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")?.let { DesktopWrite.asSentence(it) }
        val refusal = b?.text("error")?.replaceFirstChar { it.uppercase() }
        return when {
            reply.code in 200..299 -> if (b?.flag("ok") == false) {
                false to ("Not changed. " + (error ?: "Your PC said no, without a reason."))
            } else {
                true to (if (shared) SHARED else UNSHARED)
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
