package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * How much of an approval card is shown at first - the owner's request of
 * 2026-10-09: "for approval cards, there should be a more simple summary, with
 * an explain more button that expands the approval card total word length and
 * explains the details more. and approval card preferences such as this should
 * be changeable in the settings".
 *
 * THE SETTING IS THE PC'S, NOT THIS PHONE'S. It lives in card-prefs.json in the
 * Jarvis settings folder, beside appearance.json and animal.json, and is read
 * over `GET /api/card-prefs` (backend/jarvis_card_summary.py, `card-prefs.patch`).
 * The desktop reads the same route, so the phone and the PC cannot disagree
 * about how a card is drawn, and nothing here keeps a second copy. Cosmetic, so
 * it is at once with no approval card, either way.
 *
 * THE SHORT SUMMARY IS THE PC'S TOO. `notice.summary` on each row is built by
 * the PC from `backend/jarvis_card_words.py`'s own table (one written short
 * phrase per action), and `notice.full` is the card's whole existing text -
 * exactly what "Explain more" opens. This file only decides WHICH of the two is
 * drawn first, and the words of the control, which the PC also sends.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object CardSummary {
    const val PATH = "/api/card-prefs"

    /** Start folded, with the control. The default, and the first choice. */
    const val START_SHORT = "start_short"

    /** Draw every card open, with its whole text - how cards were before. */
    const val ALWAYS_FULL = "always_full"

    const val DEFAULT = START_SHORT

    /** The two choices, in the PC's own order. */
    val MODES = listOf(START_SHORT, ALWAYS_FULL)

    const val TITLE = "Approval cards"

    /** The control's own words. The PC sends the same two at the route. */
    const val MORE_LABEL = "Explain more"
    const val LESS_LABEL = "Show less"

    const val MISSING =
        "Your PC's Jarvis cannot keep this card setting yet - run apply-patches.ps1 on the PC."

    /** This phone's own words for the two choices, used only when the PC sends none. */
    val LABELS = mapOf(
        START_SHORT to "Start short (default)",
        ALWAYS_FULL to "Always show everything",
    )

    /** One line per choice, on the PC's own terms. */
    val HELP = mapOf(
        START_SHORT to
            "A card shows one line saying what Jarvis wants to do, and an \"Explain more\" button " +
            "opens the whole card: exactly what changes, why it matters, and what happens if you " +
            "say no. Nothing is hidden from you - it is one tap away.",
        ALWAYS_FULL to
            "Every card is drawn open, with its whole text, as cards were before. No \"Explain " +
            "more\" button is needed because there is nothing folded away.",
    )

    /**
     * `GET /api/card-prefs`, read - or null when this PC has no such route (an
     * older backend), which draws cards exactly as they were before.
     */
    data class View(
        val mode: String,
        val title: String = TITLE,
        val choices: List<Choice>,
        val moreLabel: String = MORE_LABEL,
        val lessLabel: String = LESS_LABEL,
        /** The PC says a real choice is saved, rather than the default in use. */
        val stored: Boolean = false,
    ) {
        val folded: Boolean get() = mode != ALWAYS_FULL
    }

    data class Choice(val id: String, val label: String, val detail: String, val default: Boolean)

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }
            ?.contentOrNull?.toBooleanStrictOrNull()

    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val mode = body.text("mode")?.takeIf { it in MODES } ?: DEFAULT
        val given = (body["choices"] as? kotlinx.serialization.json.JsonArray)
            ?.mapNotNull { it as? JsonObject }
            ?.associateBy { it.text("id") }
        val choices = MODES.map { id ->
            val g = given?.get(id)
            Choice(
                id = id,
                label = g?.text("label") ?: LABELS.getValue(id),
                detail = g?.text("detail") ?: HELP.getValue(id),
                default = g?.flag("default") ?: (id == DEFAULT),
            )
        }
        return View(
            mode = mode,
            title = body.text("title") ?: TITLE,
            choices = choices,
            moreLabel = body.text("more_label") ?: MORE_LABEL,
            lessLabel = body.text("less_label") ?: LESS_LABEL,
            stored = body.flag("stored") ?: false,
        )
    }

    /** A read that failed because this PC has no card settings. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The one change this phone may send. Null for anything but the two choices. */
    fun modeBody(mode: String): String? =
        if (mode in MODES) JsonObject(mapOf("mode" to JsonPrimitive(mode))).toString() else null

    /** What to say after a change: the PC's own sentence, or the plain words of a failure. */
    fun said(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: "Done."
        is ApiResult.Failed -> if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    /**
     * What ONE card draws, worked out here so the rule is in one place and a
     * plain JVM test can hold it.
     *
     * `summary` is the short line, or null when the card has none to show
     * (either it is already drawn above the card, or there is nothing but the
     * detail). `body` is the whole text - the card's own `notice.full` and its
     * `detail` together - or "" when nothing is unfolded. `control` is whether
     * an "Explain more"/"Show less" control is drawn at all: never under
     * "always show everything" (nothing is folded away), and never when opening
     * the card would show nothing more than the summary already does.
     *
     * @param mode the PC's setting ([View.mode]); anything else is the default
     * @param summary the row's own short words (`notice.summary`), or null
     * @param full the row's whole card text (`notice.full`), or null
     * @param detail the row's own `detail` - a command, a diff, a plan's text
     * @param expanded whether THIS card is open right now
     */
    data class Shown(
        val summary: String?,
        val body: String,
        val expanded: Boolean,
        val control: Boolean,
        val label: String,
    )

    fun shown(
        mode: String,
        summary: String?,
        full: String?,
        detail: String? = null,
        expanded: Boolean = false,
        moreLabel: String = MORE_LABEL,
        lessLabel: String = LESS_LABEL,
    ): Shown {
        val open = mode == ALWAYS_FULL || expanded
        val short = summary?.trim()?.takeIf { it.isNotEmpty() }
        // The whole card: the PC's own `full` text, and then the row's own
        // detail - both of which "Explain more" reveals, exactly as the card
        // draws them today.
        val whole = listOfNotNull(
            full?.trim()?.takeIf { it.isNotEmpty() },
            detail?.trim()?.takeIf { it.isNotEmpty() },
        ).joinToString("\n\n")
        // Folded: the short line replaces the whole text. There is one thing
        // worth reading at a glance, and the card's own `detail` is not it -
        // that is what the control is for.
        val body = when {
            open -> whole
            short != null -> ""
            else -> whole
        }
        val control = mode != ALWAYS_FULL && whole.isNotEmpty() && body != whole
        return Shown(
            // A folded card with nothing to unfold already shows the whole
            // text, so the short line on top of it would say it twice.
            summary = if (short != null && (open || body.isEmpty())) short else null,
            body = body,
            expanded = open,
            control = control,
            label = if (open) lessLabel else moreLabel,
        )
    }
}
