package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * "Erase the words" - the owner's decision of 2026-09-24 (CLAUDE.md), and
 * docs/JARVIS-API.md section 6 (`POST /api/memory/erase`).
 *
 * Forget hides a fact and keeps its words as history. "Erase the words" is
 * the second action beside it: the fact's words are wiped from the PC for
 * good - its text, its search entry, every copy in the memory file - and
 * only its dates stay, so the history shows that something was erased there.
 * It asks first, like Forget, and is held on a stale link, like Forget. There
 * is no approval card (Forget has none either) and no undo at all.
 *
 * The phone offers it wherever it offers Forget: Mind -> "Saved
 * automatically" ([com.jarvis.client.ui.screens.SavedAutomaticallySection]).
 * An erased fact is no longer current, so it leaves that list. Mind's
 * "what did Jarvis know on this date?" plate shows one as [erasedLine] -
 * never its words, and never the marker the PC keeps in their place.
 *
 * The route's answers, as `backend/rebuilt/jarvis_memory.py` `handle_erase`
 * sends them:
 * - 200 `{"ok": true, "id", "erased_at", "already_erased", ...}` - erased.
 *   The reply never carries the words.
 * - 404 `{"ok": false, "reason": "no_such_fact"}` - there is no such fact,
 *   so there are no words left either. A 404 WITHOUT that reason is a PC
 *   that has no such route at all - an older one - and nothing was erased.
 *   The difference matters: treating it as "gone" would take the fact off
 *   the list while its words are still on the PC.
 * - 501 - the PC's jarvis_memory.py is too old to erase.
 * - 503 - the memory is not running.
 * - 400 - a bad request, the PC's `error` in words.
 *
 * Pure Kotlin, no Android types, so `MemoryEraseTest` runs it on a plain JVM.
 */
object MemoryErase {
    const val PATH = "/api/memory/erase"

    fun body(id: Long): String = "{\"id\":$id}"

    /** The button, next to Forget. */
    const val LABEL = "Erase the words"
    const val BUSY = "Erasing…"
    const val YES = "Yes, erase the words"

    /** Asked first. Both apps' words, word for word (the desktop's `ERASE_CONFIRM`). */
    const val CONFIRM =
        "Erase the words of this fact from your PC for good? Jarvis keeps only the date it " +
            "was saved, so its history shows something was erased here. This cannot be undone."

    /** Said after it went through. The desktop says the same. */
    const val ERASED = "Erased."

    /** A 404 that said "no such fact": nothing left to erase. */
    const val ALREADY_GONE = "Jarvis had no such fact any more."

    /** A PC without the route (404 without the reason, or 501). */
    const val TOO_OLD =
        "Not erased. Your PC's Jarvis cannot erase words yet - run apply-patches.ps1 on the PC to update it."

    const val NOT_RUNNING = "Not erased. Jarvis's memory is not running on your PC right now."

    /** What the PC answered, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /**
     * Whether the words are gone now (so the row leaves the list), and the
     * sentence to show.
     */
    fun said(reply: Reply): Pair<Boolean, String> {
        val b = reply.body
        val error = b?.text("error")?.let { DesktopWrite.asSentence(it) }
        return when {
            reply.code in 200..299 -> if (b?.flag("ok") == false) {
                false to ("Not erased. " + (error ?: "Your PC said no, without a reason."))
            } else {
                true to ERASED
            }
            reply.code == 404 && b?.text("reason") == "no_such_fact" -> true to ALREADY_GONE
            reply.code == 404 || reply.code == 501 -> false to TOO_OLD
            reply.code == 503 -> false to NOT_RUNNING
            reply.code == 400 -> false to ("Not erased. " + (error ?: "Your PC did not understand the request."))
            else -> false to ("Not erased. Your PC answered ${reply.code}." + (error?.let { " $it" } ?: ""))
        }
    }

    /**
     * An erased fact's `erased_at` (unix seconds; a column of every fact row
     * the PC sends), or null for a fact that still has its words. Only a real,
     * positive number counts - a string or `true` is not a date.
     */
    fun erasedAt(fact: JsonObject): Double? {
        val p = fact["erased_at"] as? JsonPrimitive ?: return null
        if (p is JsonNull || p.isString) return null
        return p.doubleOrNull?.takeIf { it.isFinite() && it > 0 }
    }

    private val DAY = DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.ENGLISH)

    /** What an erased fact shows instead of its words: "Erased on 24 September 2026". */
    fun erasedLine(seconds: Double, zone: ZoneId): String =
        "Erased on " + DAY.format(Instant.ofEpochSecond(seconds.toLong()).atZone(zone))

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
