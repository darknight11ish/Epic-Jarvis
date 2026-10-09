package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "Limits and how often Jarvis does things" (the PC's `backend/jarvis_limits.py`,
 * 2026-10-08; docs/JARVIS-API.md section 121). SEVEN limits the owner can change
 * live in ONE table on the PC and are read and written through two routes:
 *
 *   GET  [PATH]       -> every row this app may change, with what the PC says now
 *   POST [WRITE_PATH] -> ONE row, `{"key": ..., "value": ...}`
 *
 * WHICH ROWS THE PHONE OFFERS. The PC's own table gives each limit an `app`
 * ("both", "desktop" or "phone") and a `pc_only` flag, and `jarvis_limits.view
 * (app="phone")` is the view that leaves out both the desktop's own rows and
 * everything only the PC may change. This app never keeps its own copy of that
 * list - it cannot drift from the table if it does not exist. Two things happen
 * instead:
 *
 *  * the PC serves this app the PHONE's view (`view(app="phone")`), which is
 *    what decides the `app` half of the rule; and
 *  * every row that does arrive is filtered again here by `pc_only`, so a
 *    PC-only row can never be drawn as a control on a phone even if a PC sends
 *    one ([offered]).
 *
 * A row whose `kind` this app has no control for (the table's "float") is not
 * offered either: a number with no step and no chip would be a control that
 * cannot be worked. Only "int" and "bool" reach the screen.
 *
 * ONE TAP IS ONE CHANGE, and the PC decides what it means. Some changes take
 * effect at once; others are a loosening, and the PC then puts ONE approval card
 * to the owner and writes nothing until it is answered there - so a 200 can mean
 * "a card is waiting", never "it is done". WHICH DIRECTION ASKS IS THE ROW'S OWN:
 * on most rows turning a number up is the loosening, and on the voice check's
 * bar turning it DOWN is (a lower bar means more clips count as the owner's
 * voice). No line here may claim one direction always applies at once; the row's
 * own `note`, written by the PC, says which way that row goes. This app shows
 * the PC's own sentence ([Answer]) and invents none of its own; it re-reads the
 * row afterwards, whatever the answer.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Limits {

    /** `GET /api/limits` - read. The PC answers with the phone's own view. */
    const val PATH = "/api/limits"

    /** `POST /api/limits/settings` - ONE limit at a time. */
    const val WRITE_PATH = "/api/limits/settings"

    const val TITLE = "Limits and how often Jarvis does things"
    const val DETAIL =
        "How much Jarvis does at once, how long you can undo, and how long it waits before it " +
            "reads something of yours. These are the PC's own settings, in the PC's own words."
    /**
     * Said ONCE, above the rows: the screen must not look as if every tap went
     * straight through.
     *
     * IT MAY NOT SAY WHICH DIRECTION ASKS (corrected 2026-10-09). This used to
     * end "Turning something down applies at once", as a blanket line about
     * every row under it - and that is not true of every row. On the voice
     * check's bar, LOWERING it is the loosening (a lower bar means more clips
     * count as the owner's voice), so going down is the direction that raises
     * ONE card on the PC, and the row's own note says exactly that. A general
     * sentence ending that way therefore contradicted the row immediately below
     * it. Which direction asks is the row's own business - the PC decides it
     * per row, and sends it in the row's `note` - so the line above the rows
     * says only what is true of all of them.
     */
    const val LOOSEN_NOTE =
        "Changing something here may take effect at once or ask you on the PC first, and " +
            "nothing changes until you answer there. The line under each one says which."
    /** The row's own mark, when turning this one up is what asks. */
    const val ASKS_ON_PC = "Turning this up asks you on the PC."

    const val READING = "Reading…"
    const val DONE = "Done."
    /** Nothing to offer: either an older PC, or every row is one this phone may not change. */
    const val EMPTY = "There is nothing here your phone may change."
    const val MISSING =
        "Your PC's Jarvis does not have these settings yet - run apply-patches.ps1 on the PC."

    // ------------------------------------------------------------- rows ----

    /**
     * One limit, exactly as `GET /api/limits` gives it. `value` stays a raw
     * [JsonElement] so what is posted back is the number (or true/false) the PC
     * sent, never a re-typed one.
     */
    data class Row(
        val key: String,
        val title: String,
        /** "int" or "bool" - the two this app has a control for. */
        val kind: String,
        val value: JsonElement,
        /** The value in the PC's own words ("keep undo for a day", "24 hours"). */
        val words: String,
        /** The allowed values, when the PC gives a fixed set; empty otherwise. */
        val choices: List<Long>,
        val low: Long,
        val high: Long,
        val unit: String,
        val note: String,
        /** Turning this one UP asks the owner on the PC first. */
        val loosenUp: Boolean,
        /** Only the PC may change this one. It is never offered here. */
        val pcOnly: Boolean,
        /** Who owns this row: "both", "desktop" or "phone". */
        val app: String,
    ) {
        val on: Boolean get() = (value as? JsonPrimitive)?.booleanOrNull ?: false
        val number: Long get() = (value as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toLong() ?: 0L

        /** The next value down, or null at the bottom of the PC's own range. */
        val down: Long? get() = if (kind == "int" && choices.isEmpty() && number > low) number - 1 else null

        /** The next value up, or null at the top of the PC's own range. */
        val up: Long? get() = if (kind == "int" && choices.isEmpty() && number < high) number + 1 else null
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.number(key: String): Long? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toLong()

    /** One row, or null for anything that is not a row this app can draw. */
    private fun row(o: JsonObject): Row? {
        val key = o.text("key") ?: return null
        val kind = o.text("kind") ?: return null
        // A kind with no control here (the table's "float") is not a row this
        // app can offer: it would be a number with no step and no chip.
        if (kind != "int" && kind != "bool") return null
        val value = o["value"] ?: return null
        val choices = (o["choices"] as? JsonArray)
            ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toLong() }
            .orEmpty()
        return Row(
            key = key,
            title = o.text("title") ?: key,
            kind = kind,
            value = value,
            words = o.text("words") ?: "",
            choices = choices,
            low = o.number("low") ?: 0L,
            high = o.number("high") ?: 0L,
            unit = o.text("unit").orEmpty(),
            note = o.text("note").orEmpty(),
            loosenUp = o.flag("loosen_up") == true,
            pcOnly = o.flag("pc_only") == true,
            app = o.text("app") ?: "both",
        )
    }

    /**
     * EVERY row the PC sent, in the PC's own order - PC-only ones included, so
     * the filter below is a real decision that can be tested rather than a
     * `mapNotNull` that quietly drops things.
     */
    fun read(body: JsonObject): List<Row> =
        (body["limits"] as? JsonArray)
            ?.mapNotNull { it as? JsonObject }
            ?.mapNotNull { row(it) }
            .orEmpty()

    /**
     * The rows this app may draw: what the PC sent, minus anything marked
     * `pc_only` and minus anything the table marks for the DESKTOP only.
     *
     * Both halves are held here because the route serves every row - one route
     * for both apps, since the PC's own card must see the PC-only limits and
     * this app must not, and the route cannot tell the two callers apart
     * without being told which it is. Filtering on the row's own `app` is what
     * keeps the two sides from drifting: a row says who owns it.
     */
    fun offered(body: JsonObject): List<Row> =
        read(body).filter { !it.pcOnly && it.app != "desktop" }

    /** An answer that means "this PC has no such route yet" (an older PC). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 404))

    /** ONE change: the row's key and the value. Never anything else. */
    fun body(key: String, value: JsonElement): String =
        JsonObject(mapOf("key" to JsonPrimitive(key), "value" to value)).toString()

    /** ONE change by number, for the step pair and the chips. */
    fun body(key: String, value: Long): String = body(key, JsonPrimitive(value))

    /** ONE change on a bool row. */
    fun body(key: String, value: Boolean): String = body(key, JsonPrimitive(value))

    // --------------------------------------------------------- answers ----

    /**
     * What ONE change answered: the PC's own sentence, word for word, and
     * whether anything was actually written.
     *
     * A refusal (400, 403, 409, 503) comes back as the PC's own `error`
     * sentence, and it is the answer the owner sees - this app never rewords it.
     * `changed` is false both for a refusal and for a `loosening` answer, which
     * means "a card is waiting on the PC": the row is re-read either way, so the
     * screen can never show a value the PC did not confirm.
     */
    data class Answer(val sentence: String, val changed: Boolean)

    fun answer(result: ApiResult<JsonObject>): Answer = when (result) {
        is ApiResult.Ok ->
            // The `error` first: `classifyPost` keeps a refusal's body, and that
            // sentence is the answer. `said` is the PC's for a change that went
            // through (or for a card that is now waiting).
            Answer(
                sentence = result.value.text("error") ?: result.value.text("said") ?: DONE,
                changed = result.value.flag("ok") != false,
            )
        is ApiResult.Failed ->
            Answer(
                sentence = if (missing(result.error)) MISSING
                else PlainErrors.forApiError(result.error).text,
                changed = false,
            )
    }

    /** A POST's status and body, read the way [WebSearch.classifyPost] reads them. */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> = when {
        // The PC's own sentence IS the answer - a refusal ("That has to be
        // between 1 and 1000."), a card's card-denied line, or a `said`. Shown
        // as it arrived; 400/403/409/503 all carry one.
        body?.text("error") != null || body?.text("said") != null -> ApiResult.Ok(body)
        code in 200..299 && body != null -> ApiResult.Ok(body)
        code == 401 || code == 403 -> ApiResult.Failed(ApiError.BadToken)
        code == 404 -> ApiResult.Failed(ApiError.NotFound)
        code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
        else -> ApiResult.Failed(ApiError.Server(code, ""))
    }

    // ------------------------------------------------- TalkBack words ----

    /**
     * What the screen reader says for a row's own value. The app's switches
     * carry their words deliberately (MannerSection's humour switch, the decks
     * stepper), so a control is never just "switch" or a bare symbol.
     */
    fun rowWords(r: Row): String {
        val base = if (r.words.isNotBlank()) r.words else r.title
        return "${r.title}: $base" + if (r.loosenUp) ". $ASKS_ON_PC" else ""
    }

    /** The words for the two step buttons of an int row with no fixed choices. */
    fun downWords(r: Row): String = "Turn ${r.title} down"

    fun upWords(r: Row): String =
        "Turn ${r.title} up" + if (r.loosenUp) ". $ASKS_ON_PC" else ""

    /** The words for one chip of an int row with a fixed set of choices. */
    fun choiceWords(r: Row, choice: Long): String {
        val unit = if (r.unit.isBlank()) "" else " ${r.unit}"
        val chosen = if (choice == r.number) ", in use" else ""
        return "${r.title}: $choice$unit$chosen" + if (r.loosenUp) ". $ASKS_ON_PC" else ""
    }

    /** A range line, so the owner can see how far a number may go. */
    fun rangeLine(r: Row): String {
        if (r.kind != "int" || r.choices.isNotEmpty()) return ""
        val unit = if (r.unit.isBlank()) "" else " ${r.unit}"
        return "Between ${r.low}$unit and ${r.high}$unit."
    }
}
