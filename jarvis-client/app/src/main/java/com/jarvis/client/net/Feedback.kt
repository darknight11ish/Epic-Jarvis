package com.jarvis.client.net

/*
 * Right/Wrong v2 - the phone's half (Wave 10, the owner's choice of
 * 2026-11-07: "Mark + why + save my correction").
 *
 * THE WIRE CONTRACT IS THE LEAD'S, AND IT IS FIXED. `POST /api/feedback/mark`
 * keeps the old body exactly - {"turn_id": "<32 hex>", "mark": "right" |
 * "wrong" | "none"} - and a wrong mark carried from the new sheet ALSO sends:
 *
 *   {"turn_id": "<32 hex>", "mark": "wrong",
 *    "reason": "wrong_fact" | "outdated" | "misunderstood" | "too_long" |
 *              "too_sensitive" | "",
 *    "correction": "<the owner's own words, one line, at most 500 characters>"}
 *
 * The response keeps `ok` and adds `said` (string - the PC's own receipt
 * sentence, shown to the owner) and `card_raised` (bool - the PC has queued
 * ONE card about it, which the owner still answers on the PC). Older fields
 * are unchanged and an older PC's response simply has no `said`; nothing here
 * invents a claim in that case.
 *
 * WHAT THIS FILE IS: the pure rules only, kept out of Compose and OkHttp so
 * the JVM unit tests can reach them - the same rule `net/Learning.kt` keeps
 * for the old mark. `Feedback.markBody` (Learning.kt) is the ONE body builder;
 * everything here calls it rather than keeping a second copy of the JSON.
 */

/**
 * The five reasons the owner chose, in the order the sheet draws them.
 *
 * [wire] is exactly what the PC accepts (the Lead's contract); [label] is the
 * chip's plain words, the owner's own list. Nothing else may be sent - an
 * edit here without the PC's list is a 400, so both halves are named
 * together.
 */
enum class FeedbackReason(val wire: String, val label: String) {
    WRONG_FACT("wrong_fact", "wrong fact"),
    OUTDATED("outdated", "outdated"),
    MISUNDERSTOOD("misunderstood", "misunderstood"),
    TOO_LONG("too_long", "too long"),
    TOO_SENSITIVE("too_sensitive", "too sensitive"),
}

/**
 * What the PC said back about one mark.
 *
 * [said] is shown to the owner as the receipt, word for word (empty on an
 * older PC, which sends none). [cardRaised] means the PC queued ONE card
 * about this mark - the phone never answers or approves it: the card is
 * answered on the PC, as every card is.
 */
data class MarkReceipt(
    val said: String = "",
    val cardRaised: Boolean = false,
)

/**
 * The Wrong sheet's pure rules: the five chips, the one-line correction and
 * the request it sends.
 *
 * CANCEL CAN NEVER SEND. [Tap.CANCEL] goes through the same [request] as
 * every other control and comes back [Request.Nothing] by construction - the
 * sheet dismisses on it, and there is no second path a dismiss could take.
 * That is what "sends nothing until Submit" means here, and the unit tests
 * prove it on the function the screen calls.
 */
object WrongFeedback {
    /** The correction is ONE line of the owner's own words, at most this many characters. */
    const val MAX_CORRECTION = 500

    // ---- the sheet's plain words (read by the UI and pinned by its tests) ----
    const val TITLE = "What was wrong?"
    const val SUBTITLE = "Pick a reason if one fits. You can also type what I should " +
        "have said - your own words, kept on your PC. Nothing is sent until you tap Send."
    const val WHY = "Why was it wrong?"
    const val CORRECTION_LABEL = "What should I have said?"
    const val CORRECTION_HINT = "Optional, one line, up to 500 characters."
    const val JUST_WRONG = "Just mark it wrong"
    const val SUBMIT = "Send"
    const val CANCEL = "Cancel"
    const val CLOSE = "Close"
    const val OFFLINE = "Not connected, so a mark cannot be sent right now."
    /** Shown only when the PC sent no `said` of its own (an older PC). */
    const val SAID_FALLBACK = "The mark reached your PC."
    /** The same, when the PC also said a card is waiting. */
    const val CARD_FALLBACK =
        "The mark reached your PC. One approval card is waiting for you there - " +
            "answer it on the PC."

    /** The correction as it is STORED and SENT: one line, never over the cap. */
    fun cap(text: String): String =
        text.replace("\r\n", " ").replace('\r', ' ').replace('\n', ' ').take(MAX_CORRECTION)

    /** How many characters the box has left (never negative). */
    fun remaining(correction: String): Int = MAX_CORRECTION - cap(correction).length

    /** The counter under the box, in plain words. */
    fun remainingLabel(correction: String): String = "${remaining(correction)} characters left"

    /**
     * A chip tap: pick the reason, or clear it by tapping the chosen one again.
     * One reason at a time - the owner's list is five single choices, and the
     * PC's `reason` is one value.
     */
    fun toggle(current: FeedbackReason?, tapped: FeedbackReason): FeedbackReason? =
        if (current == tapped) null else tapped

    /** What the sheet is holding before Submit. */
    data class Draft(
        val reason: FeedbackReason? = null,
        val correction: String = "",
    ) {
        /** True when nothing extra was chosen: the request is the OLD body. */
        val plain: Boolean get() = reason == null && cap(correction).trim().isEmpty()
    }

    /** A control the owner can tap on the sheet. */
    enum class Tap { CANCEL, JUST_WRONG, SUBMIT }

    /** What a tap asks for. Only [Send] ever reaches the network. */
    sealed interface Request {
        /** Nothing is sent (a dismiss, a dead link, or an id the PC would refuse). */
        data object Nothing : Request

        /** The exact JSON posted to `POST /api/feedback/mark`. */
        data class Send(val body: String) : Request
    }

    /**
     * What ONE tap does, given the sheet's draft and whether a mark may be
     * sent at all. [Tap.CANCEL] is first and returns [Request.Nothing]: the
     * sheet's dismiss control goes through this same function, so no
     * dismiss-shaped path can produce a body.
     *
     * "Just mark it wrong" sends today's body unchanged; Submit sends the
     * same body when no reason and no correction were given, and the v2 body
     * with both fields otherwise (the Lead's contract keeps the old body
     * valid, and an owner who picked nothing did not ask for anything new).
     */
    fun request(
        tap: Tap,
        turnId: String,
        draft: Draft,
        canSend: Boolean,
    ): Request {
        if (tap == Tap.CANCEL) return Request.Nothing
        if (!canSend) return Request.Nothing
        val body = if (tap == Tap.JUST_WRONG) {
            Feedback.markBody(turnId, AnswerMark.WRONG)
        } else {
            Feedback.markBody(
                turnId,
                AnswerMark.WRONG,
                draft.reason,
                cap(draft.correction),
            )
        }
        return body?.let { Request.Send(it) } ?: Request.Nothing
    }

    /**
     * The receipt the sheet shows after a successful send: the PC's own
     * `said` sentence, word for word, or - only when an older PC sent none -
     * one honest fixed line. Null before anything was sent.
     */
    fun receiptWords(receipt: MarkReceipt?): String? {
        if (receipt == null) return null
        val said = receipt.said.trim()
        if (said.isNotEmpty()) return said
        return if (receipt.cardRaised) CARD_FALLBACK else SAID_FALLBACK
    }
}
