package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Inbox tidy by voice" - the owner's decision of 2026-09-28, and
 * docs/JARVIS-API.md section 92 (`/api/email/tidy`).
 *
 * The owner says "archive the newsletters from last week" (or "mark all from
 * Sam as read", "move the promos to Trash"). Jarvis finds the emails on the
 * PC and raises ONE approval card that lists every email it will touch; the
 * card is decided by a tap - never by voice. Approved, the PC does it and
 * keeps a record for 10 minutes, and a small strip under the chat offers
 * Undo. There is no permanent delete: "delete" only ever means Trash.
 *
 * On the phone the card is an ordinary approval card ([PendingRows] puts
 * the whole list in its summary, shown in full and scrollable; the
 * notification and the home-screen widget show only the PC's `notice`, never
 * a sender or a subject). What this adds is the Undo strip: it reads
 * `GET /api/email/tidy` (a status of counts and the PC's own words - never a
 * sender or a subject) and sends `POST /api/email/tidy/undo` on the owner's
 * tap.
 *
 * What asks first is the PC's to decide, never this app's; Undo needs no
 * card (it only puts back what the owner had ten minutes ago). It is held on
 * a stale link (rule 4) - it acts on a mailbox - and it waits for the unlock
 * while the lists are hidden.
 *
 * The desktop says the same words (jarvis-desktop/src/inbox-tidy.js); both
 * are checked against `contract/inbox-tidy-cases.json`, made by
 * tools/gen_inbox_tidy_cases.py from the real backend.
 *
 * Pure Kotlin, no Android types, so `InboxTidyTest` runs it on a plain JVM.
 */
object InboxTidy {
    const val PATH = "/api/email/tidy"
    const val UNDO_PATH = "/api/email/tidy/undo"

    /** How often the phone re-reads the status while it is connected. */
    const val POLL_MS = 20_000L

    /** The strip's own words, both apps, word for word (the contract's `words`). */
    val WORDS: Map<String, String> = mapOf(
        "hidden" to "Your inbox was tidied. You can undo it for a few minutes.",
        "locked" to "Unlock Jarvis to undo this.",
        "missing" to "Your PC's Jarvis cannot tidy your inbox yet - run apply-patches.ps1 on the PC.",
        "stale" to "The connection to Jarvis is catching up, so nothing can be sent until it does.",
        "title" to "Inbox tidy",
        "undo" to "Undo",
        "undo_left" to "{minutes} min left to undo",
        "undone" to "Put back. Everything is as it was before.",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    val MISSING: String get() = w("missing")

    // ------------------------------------------------------------ shapes ----

    /** The newest tidy still open to Undo. Counts and words of the PC's own. */
    data class Undo(
        val count: Int,
        val action: String,
        val said: String,
        val minutesLeft: Int,
        val secondsLeft: Int,
        val more: Int,
    )

    data class Status(val available: Boolean, val undo: Undo?)

    /** The status and body of a reply, whole: a 404 the PC sent itself and a 404 from a PC without the routes read differently. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** What Undo did, in words for the owner. [done]: the emails were put back. */
    data class Outcome(val done: Boolean, val message: String)

    /** What the strip under the chat shows. */
    data class Strip(val text: String, val left: String, val canUndo: Boolean, val note: String)

    // ----------------------------------------------------------- reading ----

    /** `GET /api/email/tidy`. A body that is not what the PC sends reads as "nothing to undo". */
    fun parseStatus(body: JsonObject?): Status {
        if (body == null) return Status(available = false, undo = null)
        val available = body.flag("available") != false
        val u = body["undo"] as? JsonObject
        val undo = if (u == null) {
            null
        } else {
            val said = u.text("said")
            val minutes = u.int("minutes_left")
            if (said == null || minutes == null) {
                null
            } else {
                Undo(
                    count = u.int("count") ?: 0,
                    action = u.text("action").orEmpty(),
                    said = said,
                    minutesLeft = minutes,
                    secondsLeft = u.int("seconds_left") ?: 0,
                    more = u.int("more") ?: 0,
                )
            }
        }
        return Status(available, undo)
    }

    /** A status and when this phone read it (`SystemClock.elapsedRealtime()`). */
    data class Held(val status: Status, val atMs: Long)

    /**
     * The status as it is [ageMs] after it was read: the seconds left run
     * down here, so a strip does not keep offering an Undo whose ten minutes
     * are up while the link is down. An Undo with no time left is gone.
     */
    fun aged(status: Status, ageMs: Long): Status {
        val u = status.undo ?: return status
        val left = u.secondsLeft - (ageMs.coerceAtLeast(0L) / 1000L).toInt()
        if (left <= 0) return status.copy(undo = null)
        return status.copy(undo = u.copy(secondsLeft = left, minutesLeft = maxOf(1, (left + 59) / 60)))
    }

    /** `{minutes}` filled in. */
    fun leftWords(minutes: Int): String = w("undo_left").replace("{minutes}", minutes.toString())

    /**
     * What the strip under the chat says for [status], or null when there is
     * nothing to undo. The rule both apps follow (the contract's `strip`
     * rows):
     *  - [locked] (the lists are hidden): it says only that the inbox was
     *    tidied - no count, no action - and Undo waits for the unlock;
     *  - [stale]: Undo is held (rule 4) and the strip says why;
     *  - more than one tidy open: the newest is shown and the others counted.
     */
    fun strip(status: Status, locked: Boolean, stale: Boolean): Strip? {
        val u = status.undo ?: return null
        val text = if (locked) {
            w("hidden")
        } else if (u.more > 0) {
            u.said + " (${u.more} earlier " + (if (u.more == 1) "tidy" else "tidies") + " can be undone after)"
        } else {
            u.said
        }
        val note = if (locked) w("locked") else if (stale) w("stale") else ""
        return Strip(text, leftWords(u.minutesLeft), canUndo = !locked && !stale, note = note)
    }

    /** A PC without the routes: an older backend, or the module missing. */
    fun missing(reply: Reply): Boolean = reply.code == 404 || reply.code == 501 || reply.code == 503

    /**
     * `POST /api/email/tidy/undo`, read. 200 says how many came back
     * (`message`, the PC's own words); 409 says there was nothing to undo;
     * 503 says the mail server could not be reached and it can be tried
     * again; anything else falls back to a plain sentence.
     */
    fun undoOutcome(reply: Reply): Outcome {
        val body = reply.body
        if (reply.code == 200 && body?.flag("ok") == true) {
            return Outcome(true, body.text("message") ?: w("undone"))
        }
        val why = body?.text("error")
        // The PC's own sentence (nothing to undo, could not reach the mail
        // server, ...) always says `ok: false`; a route that is not there does not.
        if (body?.flag("ok") == false && why != null) return Outcome(false, why)
        if (missing(reply)) return Outcome(false, MISSING)
        return Outcome(false, "Nothing was undone. Try again in a moment.")
    }

    // ----------------------------------------------------------- helpers ----

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.int(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.intOrNull

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
