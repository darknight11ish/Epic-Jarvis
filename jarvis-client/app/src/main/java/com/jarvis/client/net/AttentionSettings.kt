package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The interruption budget's two numbers: how many times a day Jarvis may speak
 * up unasked ([KEY_COUNT]) and the hour the morning brief arrives
 * ([KEY_HOUR]).
 *
 * The PC's own Brain has had both since 2026-10-08 (`jarvis-desktop/src/brain.html`
 * "Speak up" / "Brief at", through the Rust command `set_attention_limits` ->
 * `jarvis_arbiter.change`). The phone could only READ them ([Attention.limit]
 * and [Attention.digestHour] inside the Attention card), which left them the one
 * gap in an otherwise complete settings surface. This object is the phone's half
 * of that write path - the same shape [Limits] uses for the PC's limit table,
 * because it is the same kind of thing: ONE number at a time, `said` for a
 * change and `error` for a refusal, both the PC's own words.
 *
 * WHAT THIS APP DECIDES: nothing. The NUMBER decides the direction, on the PC,
 * against the budget already in force - so nothing here sends a direction, and
 * a caller cannot make a raise look like a lowering (the hole fixed in the money
 * limits on 2026-10-07, bug audit finding E2, is written out of this route on
 * purpose). Turning the count DOWN, and moving the hour at all, apply at once.
 * RAISING the count is a loosening: the BACKEND puts ONE approval card to the
 * owner on the PC and writes nothing until it is answered there. A 200 can
 * therefore mean "a card is waiting", never "it is done" - which is why the
 * plate re-reads [Attention] whatever the answer was, and why no sentence is
 * invented here.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object AttentionSettings {

    /** `POST /api/attention/settings` - ONE number at a time (`jarvis_arbiter.change`). */
    const val PATH = "/api/attention/settings"

    /** The owner's words for the two controls, exactly as the PC's Brain has them. */
    const val COUNT_LABEL = "Speak up"
    const val HOUR_LABEL = "Brief at"

    /** The route's own two keys. */
    const val KEY_COUNT = "spoken_per_day"
    const val KEY_HOUR = "digest_hour"

    /**
     * The ranges the PC itself enforces (`jarvis_arbiter.SPOKEN_PER_DAY_MIN/MAX`
     * = 0..24, `DIGEST_HOUR_MIN/MAX` = 0..23). Held here so a control can never
     * offer, and this app can never send, a number the PC would refuse - the
     * ceiling is the PC's, not a taste of this app's.
     */
    const val COUNT_LOW = 0
    const val COUNT_HIGH = 24
    const val HOUR_LOW = 0
    const val HOUR_HIGH = 23

    /**
     * Said ONCE above the two controls, like [Limits.LOOSEN_NOTE]: the screen
     * must not look as if every tap went straight through.
     */
    const val LOOSEN_NOTE =
        "Turning the count down applies at once. Turning it up asks you on the PC first, and " +
            "nothing changes until you answer there."

    /** The hour control's own mark: moving the brief never asks. */
    const val HOUR_NOTE = "Moving the brief's hour applies at once - it never asks."

    const val DONE = "Done."
    const val MISSING =
        "Your PC's Jarvis does not have these settings yet - run apply-patches.ps1 on the PC."

    // ------------------------------------------------------------ bodies ----

    /**
     * ONE change: the key and the number, nothing else. Never a direction, never
     * both numbers in one call (`change` answers 400 for that, and a card asking
     * about both at once is a card nobody could answer well).
     */
    fun body(key: String, value: Int): String =
        JsonObject(mapOf(key to JsonPrimitive(value))).toString()

    /** How many times a day, as the route's own key. */
    fun countBody(value: Int): String = body(KEY_COUNT, value)

    /** The hour the brief arrives, as the route's own key. */
    fun hourBody(value: Int): String = body(KEY_HOUR, value)

    // -------------------------------------------------------- validation ----

    /** True when the PC would accept this many interruptions a day. */
    fun countInRange(n: Int): Boolean = n >= COUNT_LOW && n <= COUNT_HIGH

    /** True when the day really has this hour. */
    fun hourInRange(h: Int): Boolean = h >= HOUR_LOW && h <= HOUR_HIGH

    /**
     * The count a control may actually SEND: null when the PC would refuse it,
     * so an out-of-range number is never posted as-is. The plate keeps its step
     * buttons inside [COUNT_LOW]..[COUNT_HIGH], so this is the second lock on
     * the same door rather than the only one.
     */
    fun countToSend(n: Int): Int? = n.takeIf { countInRange(it) }

    /** The hour a control may actually send, or null. */
    fun hourToSend(h: Int): Int? = h.takeIf { hourInRange(it) }

    // ----------------------------------------------------------- answers ----

    /**
     * What ONE change answered: the PC's own sentence, word for word, and
     * whether the PC says it wrote something.
     *
     * `said` comes first here (unlike [Limits.answer]): this route answers a
     * raise that is still waiting on the PC with `ok` and a `said` that says so,
     * so a caller must never read `ok` as "the count is now this". The plate
     * re-reads [Attention] instead of trusting either flag; `changed` is only
     * ever used to decide whether the sentence is also worth the shared notice.
     */
    data class Answer(val sentence: String, val changed: Boolean)

    fun answer(result: ApiResult<JsonObject>): Answer = when (result) {
        is ApiResult.Ok ->
            Answer(
                sentence = result.value.text("said") ?: result.value.text("error") ?: DONE,
                changed = result.value.flag("ok") != false,
            )
        is ApiResult.Failed ->
            Answer(
                sentence = if (missing(result.error)) MISSING
                else PlainErrors.forApiError(result.error).text,
                changed = false,
            )
    }

    /** An answer that means "this PC has no such route yet" (a PC not yet patched). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 404))

    /** A POST's status and body, read the way [Limits.classifyPost] reads them. */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> = when {
        // A refusal (400 "That has to be a whole number between 0 and 24.", 409
        // "You said no, ...", 503) carries the PC's own sentence, and so does a
        // `said` - shown as it arrived, never reworded here.
        body?.text("error") != null || body?.text("said") != null -> ApiResult.Ok(body)
        code in 200..299 && body != null -> ApiResult.Ok(body)
        code == 401 || code == 403 -> ApiResult.Failed(ApiError.BadToken)
        code == 404 -> ApiResult.Failed(ApiError.NotFound)
        code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
        else -> ApiResult.Failed(ApiError.Server(code, ""))
    }

    // ------------------------------------------------- TalkBack words ----

    /**
     * The count as the owner reads it: "6 times a day", "once a day", "not at
     * all" - the PC's own picker words (`brain.js` `fillBudgetPickers`), so the
     * two apps say the same thing.
     */
    fun countWords(n: Int): String = when (n) {
        0 -> "not at all"
        1 -> "once a day"
        else -> "$n times a day"
    }

    /**
     * The hour as a clock: "8 pm (20:00)", "midnight (00:00)", "noon (12:00)" -
     * the PC's own picker words (`brain.js` `budgetHourWords`), so an hour reads
     * the same on both screens. The 24-hour half is kept because it is the only
     * unmistakeable one: "12 am" and "12 pm" are a coin toss to a tired reader.
     */
    fun hourWords(h: Int): String {
        val clock = "%02d:00".format(h)
        if (h == 0) return "midnight ($clock)"
        if (h == 12) return "noon ($clock)"
        return "${h % 12} ${if (h < 12) "am" else "pm"} ($clock)"
    }

    /** The count control's own value for TalkBack, with its range. */
    fun countValueWords(n: Int): String = "${countWords(n)}. Between $COUNT_LOW and $COUNT_HIGH a day."

    /** What the screen reader says on the hour's own value. */
    fun hourValueWords(h: Int): String = "${hourWords(h)}. Between 0 and 23."

    /** The words for the count's two step buttons, so a step is never just a "-". */
    fun countDownWords(n: Int): String = "$COUNT_LABEL: turn it down to ${countWords(n - 1)}"
    fun countUpWords(n: Int): String =
        "$COUNT_LABEL: turn it up to ${countWords(n + 1)}. Turning it up asks you on the PC first."

    /** The words for the hour's two step buttons. */
    fun hourDownWords(h: Int): String = "$HOUR_LABEL: move it back to ${hourWords(h - 1)}"
    fun hourUpWords(h: Int): String = "$HOUR_LABEL: move it on to ${hourWords(h + 1)}"

    // ---------------------------------------------------------- readers ----

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
}
