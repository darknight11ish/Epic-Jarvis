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
 * automatically", which is off by default - and passwords, PINs, account
 * and ID numbers wait for a yes even with that on (decided the same day,
 * after the safety research; the PC enforces it, the phone only says so).
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
 *   `sensitive_waiting`, `auto_last`, `sensitive_last`, and `why`: the PC's
 *   own sentence when its settings file is damaged (both switches then read
 *   off, fail closed), "" otherwise.
 * - `POST /api/memory/learning/auto` and `/api/memory/learning/sensitive`,
 *   `{"enabled": bool}`: OFF 200 at once, and it withdraws an ON card still
 *   waiting (approving that card then changes nothing); ON 202 and one card;
 *   a tier other than `ask` 503.
 * - `GET /api/memory/auto?limit=30&before=<saved_at>` - the auto-saved facts
 *   still in use, newest first: `{"facts": [{"id", "text", "saved_at",
 *   "provenance", "device"}], "auto", "auto_sensitive"}`.
 * - `POST /api/memory/forget {"id"}` - ONE fact. Retired, not deleted; no undo.
 * - The `memory_saved` event: `{"ids": [...]}` only, never the text.
 *
 * A 503 from the switches' or the list's routes is automatic learning (or
 * the memory under it) not running on the PC: the PC's own `error` is shown
 * when it sent one, else [NOT_RUNNING] ([readFailure], [switchFailure]).
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
            under = "Health, money, and private details about other people. When this is off, " +
                "Jarvis asks you first. Passwords, PINs, account and ID numbers, birthdays, " +
                "phone numbers and email addresses always wait for your yes.",
            key = "auto_sensitive",
            waitingKey = "sensitive_waiting",
            lastKey = "sensitive_last",
        ),
    }

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    // -------------------------------------------------------- reading ---

    /**
     * How the last ON card ended (`{"outcome", "why", "message", "at"}`), as
     * the PC said it. [message] is the PC's plain sentence for the owner;
     * [why] is the technical reason, kept out of the main line.
     */
    data class Last(val outcome: String, val why: String?, val message: String? = null)

    /** The settings. A field the PC did not send is null (or false for the waiting flags). */
    data class Status(
        val auto: Boolean?,
        val autoSensitive: Boolean?,
        val autoWaiting: Boolean = false,
        val sensitiveWaiting: Boolean = false,
        val autoLast: Last? = null,
        val sensitiveLast: Last? = null,
        /**
         * The PC's `why`: its own sentence when the settings file is damaged
         * or unreadable (both switches then read off). Null when all is well
         * or the PC did not say.
         */
        val why: String? = null,
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
        return Last(outcome, o.str("why"), o.str("message"))
    }

    /** `GET /api/memory/learning`. */
    fun status(body: JsonObject): Status = Status(
        auto = body.flag(Which.AUTO.key),
        autoSensitive = body.flag(Which.SENSITIVE.key),
        autoWaiting = body.flag(Which.AUTO.waitingKey) == true,
        sensitiveWaiting = body.flag(Which.SENSITIVE.waitingKey) == true,
        autoLast = body.last(Which.AUTO.lastKey),
        sensitiveLast = body.last(Which.SENSITIVE.lastKey),
        why = body.str("why"),
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
     * The same, from the queue's (id, action) pairs, leaving out the cards
     * [withdrawn] by turning the switch OFF while they waited. Such a card
     * stays in the queue until it is answered or runs out (the PC cannot take
     * a card back), but approving it changes nothing, so it is not "waiting".
     */
    fun cardWaiting(cards: List<Pair<String, String?>>, which: Which, withdrawn: Set<String>): Boolean =
        cards.any { (id, action) -> action == which.action && id !in withdrawn }

    /** The ids of [which]'s ON cards in the queue - the ones an OFF withdraws. */
    fun cardIds(cards: List<Pair<String, String?>>, which: Which): Set<String> =
        cards.filter { it.second == which.action }.mapTo(HashSet()) { it.first }

    /**
     * ON only when the PC says it is on. Waiting while the ON card is in the
     * queue or the PC says one is waiting - never "on" before a real approval.
     * A waiting switch can still be turned OFF, which withdraws the card; only
     * a second ON is refused ([mayPress]).
     */
    fun switchState(status: Status?, which: Which, cardInQueue: Boolean): Switch = when {
        status?.on(which) == true -> Switch.ON
        cardInQueue || status?.waiting(which) == true -> Switch.WAITING
        status?.on(which) == false -> Switch.OFF
        else -> Switch.UNKNOWN
    }

    /**
     * Whether pressing a switch that shows [switch], asking for [want], may be
     * sent. OFF always may - it only narrows, and while a card waits it
     * withdraws it. ON only from OFF: never a second ON while one waits, and
     * never before the PC has said which way it is. Holding ON on a stale
     * link is the runtime's ([com.jarvis.client.JarvisRuntime.setAutoLearn]).
     */
    fun mayPress(switch: Switch, want: Boolean): Boolean = when (switch) {
        Switch.ON, Switch.WAITING -> !want
        Switch.OFF -> want
        Switch.UNKNOWN -> false
    }

    /** Said under a waiting switch: turning it off is how to take the request back. */
    const val WITHDRAW_HINT = "Turning it off takes the request back."

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
            Switch.WAITING -> return waitingLine(which) + " " + WITHDRAW_HINT
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
        // The background-learning note goes under "Learn automatically" only:
        // said once, like the desktop's, not again under the sensitive switch.
        val caveat = when {
            which == Which.AUTO && learningOn == false -> " $LEARNING_OFF_NOTE"
            which == Which.SENSITIVE && autoOn == false -> " $SENSITIVE_NEEDS_AUTO"
            else -> ""
        }
        return if (switch == Switch.ON) base + caveat else base
    }

    /**
     * The desktop's sentence (auto-learn.js `LEARNING_OFF_NOTE`), one wording
     * for both apps: "Learn automatically" means nothing while background
     * learning is off.
     */
    const val LEARNING_OFF_NOTE =
        "Background learning is off, so nothing is saved automatically. Start background learning above to use this."

    const val SENSITIVE_NEEDS_AUTO = "\"Learn automatically\" is off, so this changes nothing until it is on."

    /** A refused card, when the PC sent no plain sentence of its own. */
    const val REFUSED_LINE = "Your PC's settings do not let this be approved, so it stayed off."

    /** An approved card whose change could not be saved, when the PC sent no sentence. */
    const val FAILED_LINE = "It was approved, but your PC could not save the change, so it stayed off."

    const val WITHDRAWN_LINE = "You turned it off while the card waited, so approving it changed nothing."

    /**
     * One line about how the last ON card ended, when it did not turn the
     * switch on and the switch is still off. Null otherwise - an approved
     * card needs no line, the switch says it. A refused or failed card says
     * the PC's plain `message`; its technical `why` is [lastDetail]'s.
     */
    fun lastLine(last: Last?, switch: Switch): String? {
        if (last == null || switch != Switch.OFF) return null
        return when (last.outcome) {
            "denied" -> "The last request to turn it on was denied."
            "timed_out" -> "The last request to turn it on expired without an answer."
            "refused" -> last.message?.let { DesktopWrite.asSentence(it) } ?: REFUSED_LINE
            "failed" -> last.message?.let { DesktopWrite.asSentence(it) } ?: FAILED_LINE
            "withdrawn" -> WITHDRAWN_LINE
            else -> null
        }
    }

    /**
     * The technical reason under [lastLine], small, for a refused or failed
     * card whose PC said one - or null. Never the main line.
     */
    fun lastDetail(last: Last?, switch: Switch): String? {
        if (last == null || switch != Switch.OFF) return null
        if (last.outcome != "refused" && last.outcome != "failed") return null
        return last.why?.let { "Details from your PC: " + DesktopWrite.asSentence(it) }
    }

    /**
     * The PC's `why` about its settings file (damaged or unreadable), shown
     * under "Learn automatically" as the PC wrote it - or null when it said
     * nothing.
     */
    fun whyLine(status: Status?): String? = status?.why?.let { DesktopWrite.asSentence(it) }

    /**
     * Said when a switch's POST failed, for the failures the routes document;
     * null for the rest (the runtime's own words then). A 503 that carried
     * the PC's `error` never gets here: that is already a refusal in its own
     * words (`DesktopWrite.classify`).
     */
    fun switchFailure(e: ApiError): String? = when (e) {
        ApiError.NotAvailable -> "Not changed. $NOT_RUNNING"
        is ApiError.Server -> if (e.code == 503) "Not changed. " + (pcError(e.body) ?: NOT_RUNNING) else null
        else -> null
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
        /** Memory idea 3: how often the owner has said it again since (0 = never). */
        val saidAgain: Int = 0,
        /**
         * Memory idea 4 (the memory review's I10): "YYYY-MM-DD" when the
         * owner's own words gave the day it became true ("moved to Leeds in
         * 2021"), else null. Shown as "true from 1 January 2021".
         */
        val trueFrom: String? = null,
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
                saidAgain = (o["said_again"] as? JsonObject)?.prim("count")
                    ?.takeIf { !it.isString }?.longOrNull
                    ?.takeIf { it in 1..Int.MAX_VALUE.toLong() }?.toInt() ?: 0,
                // As sent, not trimmed: the desktop reads it the same way.
                trueFrom = (o["true_from"] as? JsonPrimitive)?.takeIf { it.isString }?.content,
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

    /**
     * The small line under a fact: when it was saved, in which app it was
     * said, how often said again, and "true from 1 January 2021" when the
     * owner's words gave that day - the desktop's `factMeta` (auto-learn.js).
     */
    fun rowLine(fact: Fact, zone: ZoneId, today: LocalDate): String = listOfNotNull(
        ChatLog.whenLine(fact.savedAt?.toLong(), zone, today),
        fromWhere(fact.device),
        saidAgainWords(fact.saidAgain),
        MemoryWords.trueFromLine(fact.trueFrom),
    ).joinToString(" · ")

    /** "said again once" / "said again 3 times" - the desktop's words (auto-learn.js). */
    fun saidAgainWords(n: Int): String? = when {
        n <= 0 -> null
        n == 1 -> "said again once"
        else -> "said again $n times"
    }

    /** Which app the owner's words were said in, in History's words; nothing for one the PC did not name. */
    fun fromWhere(device: String?): String? = when (device) {
        "phone", "desktop", "hud" -> "from the " + ChatLog.deviceWord(device)
        else -> null
    }

    const val TITLE = "Saved automatically"
    const val VOICE_MARK = "said aloud"
    const val EMPTY = "Nothing has been saved automatically yet."

    /** Said, after [EMPTY], while "Learn automatically" is off. */
    const val EMPTY_WHILE_OFF = "\"Learn automatically\" is off."

    /** The empty list's words. [auto] is "Learn automatically", as the list's own answer said it. */
    fun emptyLine(auto: Boolean?): String = if (auto == false) "$EMPTY $EMPTY_WHILE_OFF" else EMPTY

    /** One line under the list's title: History's Delete is not a Forget. */
    const val HISTORY_NOTE =
        "Deleting a conversation from History does not forget facts learned from it - use Forget here."

    /**
     * The list read again - on Refresh or a `memory_saved` event - with the
     * older pages "Load older" already brought in kept under it: the
     * desktop's `refreshRows` (auto-learn.js), by `saved_at`. [page] is the
     * new first page. Facts in [shown] older than its oldest are kept; the
     * rest are what the page says, so one forgotten elsewhere drops out. A
     * first page that was not full means there is nothing older, so nothing
     * older is kept. Returns the rows, and whether there may be more;
     * [moreBefore] is what the last "Load older" said about that.
     */
    fun refreshed(shown: List<Fact>?, page: Page, moreBefore: Boolean): Pair<List<Fact>, Boolean> {
        val fresh = page.facts
        if (!page.mayHaveOlder) return fresh to false
        val edge = olderThan(fresh) ?: return fresh to true
        val ids = fresh.mapTo(HashSet()) { it.id }
        val older = shown.orEmpty().filter { f ->
            f.id !in ids && f.savedAt?.let { it < edge } == true
        }
        return (fresh + older) to (if (older.isNotEmpty()) moreBefore else true)
    }

    // --------------------------------------------------------- forget ---

    fun forgetBody(id: Long): String = "{\"id\":$id}"

    /**
     * Asked before a Forget is sent - the owner kept this question
     * (2026-09-24), because forgetting cannot be undone. One wording for
     * both apps.
     */
    const val FORGET_CONFIRM =
        "Jarvis keeps a record that it once knew this, but will not use it again. " +
            "This cannot be undone."

    const val FORGOTTEN = "Forgotten. Jarvis will not use it again."

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

    /** Said for a 503 from the automatic-learning routes when the PC sent no `error`. */
    const val NOT_RUNNING = "Automatic learning is not running on your PC right now."

    /**
     * The PC's `error` out of a 503's body (`{"error": "..."}`), as a
     * sentence, or null when there is none. [body] is the raw text the route
     * sent, which `JarvisApi.probeKeeping503` keeps for these routes.
     */
    fun pcError(body: String?): String? {
        if (body.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(body) as? JsonObject }.getOrNull() ?: return null
        return o.str("error")?.let { DesktopWrite.asSentence(it) }
    }

    /**
     * Why the switches or the list could not be read, when the route says
     * something specific: no such route, or a 503 - in the PC's own words
     * when it sent them, else [NOT_RUNNING]. Null for the rest (the
     * runtime's own words then).
     */
    fun readFailure(e: ApiError): String? = when (e) {
        ApiError.NotFound -> "Your PC's Jarvis does not have automatic learning yet."
        ApiError.NotAvailable -> NOT_RUNNING
        is ApiError.Server -> if (e.code == 503) pcError(e.body) ?: NOT_RUNNING else null
        else -> null
    }

    /** Why the list could not be read: [readFailure]. */
    fun listFailure(e: ApiError): String? = readFailure(e)

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
