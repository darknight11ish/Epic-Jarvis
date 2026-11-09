package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull

/**
 * The ONE learning-fault banner, with "Retry now" - the phone's side of
 * docs/JARVIS-API.md section 213 (added 2026-11-09, the memory-card research).
 *
 * When one of automatic learning's batch checks fails - a damaged
 * auto-learning.json, no local model, a cloud model name, a missing
 * jarvis_intake.py - the PC used to write the same reason onto every fact in
 * the pass, so one broken check looked like up to 200 review cards. The PC
 * now records ONE fault and leaves the cards it parked out of the pending
 * read; both apps draw the PC's own sentence with one button.
 *
 * THE PHONE ADDS NO WORD OF ITS OWN. The banner's `headline`, its `reason`,
 * and the `outcome` after a retry are the PC's own text; the only strings
 * here are the button's label and the plain sentences for a PC that cannot
 * be read. Nothing here approves, saves or decides: the retry asks the PC to
 * re-run its check, which is the same in-process check the learning pass
 * uses. No fact's words are ever in this payload - the PC keeps them out.
 *
 * The routes, behind the pairing token like every other memory route:
 * - `GET /api/memory/fault` - `{active, reason, headline, count, since, at,
 *   tries, last_try_at, last_result, recorded, why}`.
 * - `POST /api/memory/fault/retry` - `{ok, cleared, fault, outcome}`: the
 *   PC's own sentence. It answers 200 even when the check still fails; that
 *   is an answer, not an error.
 *
 * Pure Kotlin, no Android types, so `MemoryFaultTest` runs it on a plain JVM.
 */
object MemoryFault {
    const val PATH = "/api/memory/fault"
    const val RETRY_PATH = "/api/memory/fault/retry"

    /** The one button on the banner. The desktop uses the same two words
     *  (`jarvis-desktop/src/auto-learn.js` FAULT_RETRY_LABEL). */
    const val RETRY_LABEL = "Retry now"

    /** What the button does, for its own line - plain, and true. */
    const val RETRY_TITLE =
        "Re-runs the check that failed. It approves nothing and saves nothing - " +
            "your facts still wait where they were."

    /** Said when the retry route is not on this PC at all. */
    const val MISSING = "Your PC's Jarvis does not have the learning-fault check yet."

    /** Said for a 503 that carried no sentence of its own. */
    const val NOT_RUNNING = "Automatic learning is not running on your PC right now."

    /** Said when the PC's answer could not be read as a fault reply. */
    const val UNREADABLE = "Your PC answered, but not in a way this app can read."

    /**
     * One active fault, as the PC describes it. [headline] is the PC's own
     * sentence for the banner; if an older PC sends none, [reason] is shown
     * instead so the banner still explains itself.
     */
    data class Fault(
        val reason: String,
        val headline: String,
        val count: Int,
        val tries: Int,
        val lastResult: String,
    )

    /**
     * The retry's answer. [active] is the fault's state AFTER the retry:
     * `true` keeps the banner (and [fault] is its new reading), `false`
     * clears it and leaves only [outcome], and `null` means the PC could not
     * be asked, so the banner is left as it was. [outcome] is always the PC's
     * own sentence (or this app's plain failure line), never a guess.
     */
    data class Reply(val active: Boolean?, val fault: Fault?, val outcome: String)

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /** A real JSON boolean only - the string "true" is not one. */
    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.int(key: String): Int? =
        prim(key)?.takeIf { !it.isString }?.longOrNull
            ?.takeIf { it in 0..Int.MAX_VALUE.toLong() }?.toInt()

    /**
     * The active fault, or null. Only `active` exactly `true` is a fault: a
     * missing field is not one, and a PC that could not read its own record
     * says so in `why` rather than pretending.
     */
    fun read(body: JsonObject?): Fault? {
        if (body == null || body.flag("active") != true) return null
        val reason = body.str("reason") ?: ""
        val headline = body.str("headline") ?: ""
        if (reason.isEmpty() && headline.isEmpty()) return null
        return Fault(
            reason = reason,
            headline = headline.ifEmpty { reason },
            count = body.int("count") ?: 0,
            tries = body.int("tries") ?: 0,
            lastResult = body.str("last_result") ?: "",
        )
    }

    /** The retry's answer (`POST /api/memory/fault/retry`). */
    fun reply(body: JsonObject): Reply {
        val faultBody = body["fault"] as? JsonObject
        val fault = read(faultBody)
        // The PC says which way it is from both sides: an active fault object
        // keeps the banner, `cleared: true` removes it, and a fault object
        // that is not active is the same "cleared" said the other way. An
        // answer with neither leaves the banner as it was (active null).
        val active: Boolean? = when {
            fault != null -> true
            body.flag("cleared") == true -> false
            faultBody != null -> false
            else -> null
        }
        return Reply(
            active = active,
            fault = fault,
            outcome = body.str("outcome") ?: UNREADABLE,
        )
    }

    /**
     * Why the fault could not be read, in words for the routes this file
     * documents; null for the rest (the runtime's own words then). A 404 is a
     * PC without the route; a 503 is automatic learning not running (the PC's
     * own `error` first, when the call kept it).
     */
    fun readFailure(e: ApiError): String? = when (e) {
        ApiError.NotFound -> MISSING
        ApiError.NotAvailable -> NOT_RUNNING
        is ApiError.Server -> if (e.code == 503) AutoLearn.pcError(e.body) ?: NOT_RUNNING else null
        else -> null
    }

    /** Why a retry could not be sent: [readFailure], or null for the runtime's words. */
    fun retryFailure(e: ApiError): String? = readFailure(e)
}
