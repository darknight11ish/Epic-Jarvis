package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import java.math.BigDecimal
import java.time.LocalDate
import java.time.ZoneId

/**
 * Automatic learning - the phone's side of docs/JARVIS-API.md section 19
 * ("Automatic learning", added 2026-09-24).
 *
 * The owner decided (CLAUDE.md, 2026-09-24) that Jarvis learns
 * automatically by default: facts about the owner and their projects, from
 * the owner's own words only, are saved without a per-fact yes, and every
 * one is listed in both apps with a one-tap Forget. Sensitive topics still
 * wait for a yes unless the owner turns on "Also remember sensitive topics
 * automatically", which is off by default.
 *
 * Two switches, the same shape as the learning switch ([MemoryCounts]) and
 * chat history's ([ChatLog]): turning either ON raises ONE approval card on
 * the PC (actions [Which.AUTO]'s and [Which.SENSITIVE]'s), and reads
 * "waiting" while that card is in the queue - including a card raised on
 * the desktop. Turning either OFF is immediate. The runtime holds ON (never
 * OFF) on a stale link, rule 4.
 *
 * The routes, all with the pairing token like every other:
 * - `GET /api/memory/learning` - `auto`, `auto_sensitive`, `auto_waiting`,
 *   `sensitive_waiting`, `auto_last`, `sensitive_last`.
 * - `POST /api/memory/learning/auto` and `/api/memory/learning/sensitive`,
 *   `{"enabled": bool}`: OFF 200 at once; ON 202 and one card; a tier other
 *   than `ask` 503.
 * - `GET /api/memory/auto?limit=30&before=<saved_at>` - the auto-saved facts
 *   still in use, newest first: `{"facts": [{"id", "text", "saved_at",
 *   "provenance", "device"}], "auto", "auto_sensitive"}`.
 * - `POST /api/memory/forget {"id"}` - ONE fact. Retired, not deleted; no undo.
 * - The `memory_saved` event: `{"ids": [...]}` only, never the text.
 *
 * THE PHONE STORES NONE OF IT. The list is read from the PC when Mind shows
 * it and dropped when Mind is left. No fact's text is ever put in a
 * notification.
 *
 * Pure Kotlin, no Android types, so `AutoLearnTest` runs it on a plain JVM.
 */
object AutoLearn {
    /** GET: the two switches, whether a card is waiting, how the last card ended. */
    const val SETTINGS_PATH = "/api/memory/learning"
    const val LIST_PATH = "/api/memory/auto"
    const val FORGET_PATH = "/api/memory/forget"

    /** The event the PC rings once per batch of facts saved without a card. */
    const val EVENT = "memory_saved"

    /** Facts per page. */
    const val PAGE = 30

    /** One of the two switches: its route, its card's action, and its words (spec section 5). */
    enum class Which(
        val path: String,
        val action: String,
        val title: String,
        val under: String,
        /** The `GET /api/memory/learning` keys: on/off, waiting, last. */
        val key: String,
        val waitingKey: String,
        val lastKey: String,
    ) {
        AUTO(
            path = "/api/memory/learning/auto",
            action = "learning_auto_enable",
            title = "Learn automatically",
            under = "Jarvis saves facts about you and your projects from what you type or say to it - " +
                "never from web pages, emails, documents or notes. You can forget any of them here.",
            key = "auto",
            waitingKey = "auto_waiting",
            lastKey = "auto_last",
        ),
        SENSITIVE(
            path = "/api/memory/learning/sensitive",
            action = "learning_sensitive_enable",
            title = "Also remember sensitive topics automatically",
            under = "Health, money, passwords and account details, and private details about other " +
                "people. When this is off, Jarvis asks you first.",
            key = "auto_sensitive",
            waitingKey = "sensitive_waiting",
            lastKey = "sensitive_last",
        ),
    }

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    // -------------------------------------------------------- reading ---

    /** How the last ON card ended (`{"outcome", "why", "at"}`), as the PC said it. */
    data class Last(val outcome: String, val why: String?)

    /** The settings. A field the PC did not send is null (or false for the waiting flags). */
    data class Status(
        val auto: Boolean?,
        val autoSensitive: Boolean?,
        val autoWaiting: Boolean = false,
        val sensitiveWaiting: Boolean = false,
        val autoLast: Last? = null,
        val sensitiveLast: Last? = null,
    ) {
        fun on(which: Which): Boolean? = when (which) {
            Which.AUTO -> auto
            Which.SENSITIVE -> autoSensitive
        }

        fun waiting(which: Which): Boolean = when (which) {
            Which.AUTO -> autoWaiting
            Which.SENSITIVE -> sensitiveWaiting
        }

        fun last(which: Which): Last? = when (which) {
            Which.AUTO -> autoLast
            Which.SENSITIVE -> sensitiveLast
        }
    }

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /** A real JSON boolean only - the string "true" is not one. */
    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.last(key: String): Last? {
        val o = this[key] as? JsonObject ?: return null
        val outcome = o.str("outcome") ?: return null
        return Last(outcome, o.str("why"))
    }

    /** `GET /api/memory/learning`. */
    fun status(body: JsonObject): Status = Status(
        auto = body.flag(Which.AUTO.key),
        autoSensitive = body.flag(Which.SENSITIVE.key),
        autoWaiting = body.flag(Which.AUTO.waitingKey) == true,
        sensitiveWaiting = body.flag(Which.SENSITIVE.waitingKey) == true,
        autoLast = body.last(Which.AUTO.lastKey),
        sensitiveLast = body.last(Which.SENSITIVE.lastKey),
    )

    /**
     * The two switches off the list's answer (`GET /api/memory/auto` carries
     * `auto` and `auto_sensitive` too) - used only when the settings read
     * failed, so the switches still show which way they are.
     */
    fun statusFromList(body: JsonObject): Status =
        Status(auto = body.flag(Which.AUTO.key), autoSensitive = body.flag(Which.SENSITIVE.key))

    // --------------------------------------------------------- switch ---

    /** What a switch shows. */
    enum class Switch { ON, OFF, WAITING, UNKNOWN }

    /** Is [which]'s ON card in the approval queue - raised here or on the desktop? */
    fun cardWaiting(actions: List<String?>, which: Which): Boolean = actions.any { it == which.action }

    /**
     * ON only when the PC says it is on. Waiting while the ON card is in the
     * queue or the PC says one is waiting - never "on" before a real approval.
     */
    fun switchState(status: Status?, which: Which, cardInQueue: Boolean): Switch = when {
        status?.on(which) == true -> Switch.ON
        cardInQueue || status?.waiting(which) == true -> Switch.WAITING
        status?.on(which) == false -> Switch.OFF
        else -> Switch.UNKNOWN
    }

    fun waitingLine(which: Which): String = when (which) {
        Which.AUTO -> "Waiting for your approval to turn on learning automatically. ${Approvals.WHERE}"
        Which.SENSITIVE -> "Waiting for your approval to remember sensitive topics automatically. " +
            Approvals.WHERE
    }

    /**
     * The line under a switch. [learningOn] is the background learning switch
     * (the one above these two): "Learn automatically" means nothing while it
     * is off, and the line says so. [autoOn] is "Learn automatically", which
     * the sensitive switch depends on in the same way.
     */
    fun stateLine(which: Which, switch: Switch, learningOn: Boolean?, autoOn: Boolean?): String {
        val base = when (switch) {
            Switch.WAITING -> return waitingLine(which)
            Switch.UNKNOWN -> return when (which) {
                Which.AUTO -> "Couldn't tell whether Jarvis learns automatically."
                Which.SENSITIVE -> "Couldn't tell whether sensitive topics are remembered automatically."
            }
            Switch.ON -> when (which) {
                Which.AUTO -> "On. Facts from your own words are saved without asking, and listed " +
                    "under Saved automatically."
                Which.SENSITIVE -> "On. Sensitive facts from your own words are saved without asking too."
            }
            Switch.OFF -> when (which) {
                Which.AUTO -> "Off. Every fact Jarvis learns waits for your yes, as a card."
                Which.SENSITIVE -> "Off. Sensitive facts wait for your yes, as a card."
            } + " Turning it on asks you first, with an approval card."
        }
        val caveat = when {
            learningOn == false -> " Learning is off, so nothing is saved automatically until it is on."
            which == Which.SENSITIVE && autoOn == false ->
                " Learn automatically is off, so this changes nothing until it is on."
            else -> ""
        }
        return if (switch == Switch.ON) base + caveat else base
    }

    /**
     * One line about how the last ON card ended, when it did not turn the
     * switch on and the switch is still off. Null otherwise - an approved
     * card needs no line, the switch says it.
     */
    fun lastLine(last: Last?, switch: Switch): String? {
        if (last == null || switch != Switch.OFF) return null
        return when (last.outcome) {
            "denied" -> "The last request to turn it on was denied."
            "timed_out" -> "The last request to turn it on expired without an answer."
            "refused", "failed" -> "The last request to turn it on did not go through" +
                (last.why?.let { ": ${it.trimEnd('.')}." } ?: ".")
            else -> null
        }
    }

    /** What to say after a switch was pressed, from the PC's answer. */
    fun said(which: Which, on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine(which)
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said?.let { DesktopWrite.asSentence(it) } ?: when (which) {
            Which.AUTO -> if (on) "Jarvis learns automatically." else
                "Jarvis no longer learns automatically. New facts wait for your yes."
            Which.SENSITIVE -> if (on) "Sensitive topics are remembered automatically." else
                "Sensitive topics wait for your yes again."
        }
    }

    // ----------------------------------------------------------- list ---

    /** One fact saved without a card. */
    data class Fact(
        val id: Long,
        val text: String,
        /** Unix seconds, possibly with a fraction. */
        val savedAt: Double?,
        val provenance: String?,
        val device: String?,
    ) {
        /** Said aloud to Jarvis (a verified voice turn), not typed. */
        val aloud: Boolean get() = provenance == Provenance.VOICE
    }

    /** One page: its facts, whether there may be older ones, and the two switches. */
    data class Page(val facts: List<Fact>, val mayHaveOlder: Boolean, val status: Status)

    /**
     * One page, newest first. [before] is the `saved_at` of the oldest fact
     * already shown. Written out in full - never `1.7E9`, which the PC's
     * number parsing would not be asked to understand.
     */
    fun listPath(before: Double? = null, limit: Int = PAGE): String =
        "$LIST_PATH?limit=${limit.coerceIn(1, 100)}" +
            (before?.takeIf { it.isFinite() }?.let { "&before=" + plain(it) } ?: "")

    private fun plain(d: Double): String = BigDecimal.valueOf(d).stripTrailingZeros().toPlainString()

    /**
     * `GET /api/memory/auto`. A fact with no whole-number id cannot be
     * forgotten, and one with no text says nothing, so both are left out.
     * [asked] is the `limit` that was sent: a full page means there may be more.
     */
    fun page(body: JsonObject, asked: Int = PAGE): Page {
        val raw = body["facts"] as? JsonArray
        val facts = raw.orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val idPrim = o.prim("id")?.takeIf { !it.isString } ?: return@mapNotNull null
            val id = idPrim.longOrNull ?: return@mapNotNull null
            val text = o.str("text") ?: return@mapNotNull null
            Fact(
                id = id,
                text = text,
                savedAt = o.prim("saved_at")?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() },
                provenance = o.str("provenance"),
                device = o.str("device"),
            )
        }
        return Page(facts, mayHaveOlder = (raw?.size ?: 0) >= asked, status = statusFromList(body))
    }

    /** [more] after [shown], without a fact twice: two can share one `saved_at` second. */
    fun append(shown: List<Fact>, more: List<Fact>): List<Fact> {
        val seen = shown.mapTo(HashSet()) { it.id }
        return shown + more.filter { seen.add(it.id) }
    }

    /** What "Load older" asks for: facts saved before the oldest one shown. */
    fun olderThan(shown: List<Fact>): Double? = shown.mapNotNull { it.savedAt }.minOrNull()

    /** The small line under a fact: when it was saved, and in which app it was said. */
    fun rowLine(fact: Fact, zone: ZoneId, today: LocalDate): String = listOfNotNull(
        ChatLog.whenLine(fact.savedAt?.toLong(), zone, today),
        fromWhere(fact.device),
    ).joinToString(" · ")

    /** Which app the owner's words were said in, in History's words; nothing for one the PC did not name. */
    fun fromWhere(device: String?): String? = when (device) {
        "phone", "desktop", "hud" -> "from the " + ChatLog.deviceWord(device)
        else -> null
    }

    const val TITLE = "Saved automatically"
    const val VOICE_MARK = "said aloud"
    const val EMPTY = "Nothing has been saved automatically yet."

    // --------------------------------------------------------- forget ---

    fun forgetBody(id: Long): String = "{\"id\":$id}"

    /** Asked before a Forget is sent - the desktop's Forget words. */
    const val FORGET_CONFIRM =
        "Stop recalling this? It stays in the history but Jarvis will not use it again. " +
            "This cannot be undone."

    const val FORGOTTEN = "Forgotten. It stays in the history and will not be recalled."

    /** Said when the PC answers 404: there is no such fact, so it is not recalled either way. */
    const val ALREADY_GONE = "Jarvis had no such fact any more."

    /**
     * After a 2xx from `/api/memory/forget`: whether it is forgotten, and what
     * to say. `ok: false` is the PC saying no.
     */
    fun forgetSaid(body: JsonObject): Pair<Boolean, String> =
        if (body.flag("ok") == false) {
            false to ("Not forgotten. " +
                ((body.str("error") ?: body.str("reason"))?.let { DesktopWrite.asSentence(it) }
                    ?: "Your PC said no, without a reason."))
        } else {
            true to FORGOTTEN
        }

    /**
     * Why a Forget failed, in words, for the answers the route documents;
     * null for the rest (the runtime's own words then). A 409 is the store
     * saying it could not retire it - usually because it already had been.
     */
    fun forgetFailure(e: ApiError): String? = when (e) {
        is ApiError.Server -> if (e.code == 409) {
            "Not forgotten. Your PC could not retire it - it may have been forgotten already."
        } else {
            null
        }
        ApiError.AlreadyHandled ->
            "Not forgotten. Your PC could not retire it - it may have been forgotten already."
        ApiError.NotAvailable -> "Not forgotten. Jarvis's memory is not running on your PC right now."
        else -> null
    }

    /** Why the list could not be read, when the route says something specific. */
    fun listFailure(e: ApiError): String? = when (e) {
        ApiError.NotFound -> "Your PC's Jarvis does not have automatic learning yet."
        ApiError.NotAvailable -> "Jarvis's memory is not running on your PC right now."
        else -> null
    }

    // ---------------------------------------------------------- event ---

    /**
     * The fact ids a `memory_saved` event names. The bus sends `{"ids": [..]}`
     * flat (`BUS.publish`); `{"value": {"ids": [..]}}` (`BUS.note`) is read
     * too. Only whole numbers count; anything else is dropped, never guessed.
     */
    fun savedIds(data: JsonElement?): List<Long> {
        val obj = data as? JsonObject ?: return emptyList()
        val arr = (obj["ids"] as? JsonArray) ?: ((obj["value"] as? JsonObject)?.get("ids") as? JsonArray)
        return arr.orEmpty().mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> !p.isString }?.longOrNull }
            .distinct()
    }

    /** How many ids the runtime keeps to not count one fact twice (a replayed event). */
    const val SEEN_CAP = 500

    /**
     * The ids in [ids] not already in [seen], and [seen] with them added
     * (oldest dropped past [SEEN_CAP]).
     */
    fun fresh(seen: List<Long>, ids: List<Long>): Pair<List<Long>, List<Long>> {
        val known = seen.toHashSet()
        val new = ids.filter { known.add(it) }
        return new to (seen + new).takeLast(SEEN_CAP)
    }

    /** The quiet line on Mind. Never the fact's text - only how many. Null for none. */
    fun rememberedLine(count: Int): String? = when {
        count <= 0 -> null
        count == 1 -> "Jarvis remembered 1 thing"
        else -> "Jarvis remembered $count things"
    }
}
