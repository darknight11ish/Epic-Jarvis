package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * How long "Solve it here" stays on offer (backend/jarvis_handoff_mode.py; the
 * owner's OWN decision of 2026-10-08, his words: "make this a setting for both
 * options with 1 as the default"; docs/CAPTCHA-HANDOFF-DESIGN.md section 5;
 * docs/JARVIS-API.md section 87.8). The hand-off itself is [Handoff].
 *
 * The captcha hand-off shows a live picture of ONE of the owner's browser
 * windows on this phone, over their private network. This chooses how long it
 * keeps offering it when nobody answers:
 *
 *  * "Stop early" ([STOP_EARLY]) - THE DEFAULT: about a minute with nobody
 *    looking, then the hand-off ends AND the PC says plainly which window
 *    Jarvis is stuck on, so the owner solves it there;
 *  * "Keep offering it" ([KEEP_OFFERING]): the full 15-minute ceiling, so the
 *    owner can pick their phone up late. A window of theirs stays on offer
 *    fifteen times longer - MORE exposure - so choosing it is ONE approval card
 *    on the PC with Windows Hello ([ACTION]), and the PC refuses it from any
 *    other device. Going back to "Stop early" is instant, from either app.
 *
 * THIS PHONE SHOWS AND SETS: one word, in the PC's own words. It never pictures
 * anything itself, never taps or types, and holds no picture of its own.
 *
 * A PC whose backend is older than this setting answers 404 or 503, which
 * [com.jarvis.client.JarvisRuntime] reads as "not on this PC's Jarvis yet".
 *
 * Pure Kotlin (no Android), so HandoffModeTest runs it against the PC's real
 * answers (contract/handoff-cases.json, tools/gen_handoff_cases.py): the words
 * are the PC's own (`WORDS` in jarvis_handoff_mode.py) and the two values and
 * the default are read from the same file, so neither app can drift.
 */
object HandoffMode {
    /** The setting's one route. NOT under the hand-off's own routes: see [Handoff]. */
    const val PATH = "/api/chatbot/handoff_mode"

    /** The approval action the PC raises the "Keep offering it" card under. */
    const val ACTION = "handoff_keep_offering"

    const val STOP_EARLY = "stop_early"
    const val KEEP_OFFERING = "keep_offering"
    /** The two choices, in the PC's order. */
    val MODES: List<String> = listOf(STOP_EARLY, KEEP_OFFERING)
    /** The default, and the one that is already the stricter choice. */
    const val DEFAULT = STOP_EARLY

    const val TITLE = "When the phone does not answer"
    const val DETAIL =
        "When Jarvis is stuck on a captcha or a sign-in page, your phone can show a live picture " +
            "of that one window. This chooses how long Jarvis keeps offering it."
    const val STOP_EARLY_LABEL = "Stop early"
    const val STOP_EARLY_DETAIL =
        "After about a minute with nobody looking, the hand-off ends and the PC says which window " +
            "Jarvis is stuck on, so you can solve it there."
    const val KEEP_OFFERING_LABEL = "Keep offering it"
    const val KEEP_OFFERING_DETAIL =
        "The live picture stays on offer for the full 15 minutes, so you can pick your phone up " +
            "late. That is more time for that window to be seen, so turning this on asks for your " +
            "approval."
    const val OPENS_WINDOWS_HELLO =
        "Turning \"Keep offering it\" on asks for your approval on the PC."
    const val WAITING_LINE =
        "Waiting for your approval. The hand-off keeps stopping early until you approve the card."
    const val OFF_NOW = "Done. The hand-off stops early again when nobody is looking."
    const val DAMAGED =
        "the hand-off settings file is damaged, so the hand-off stops early when nobody is " +
            "looking. Choose \"Keep offering it\" again to rewrite it"
    /** A read that never reached the PC. */
    const val UNREAD = "Could not read this setting."
    /** One tap is in flight. */
    const val ASKING = "Asking your PC…"
    /** The longer choice waits for a fresh link; the quick cut-off never does. */
    const val WAITING_LINK = "Waiting for the connection to your PC."
    /** The PC has no such setting yet (an older backend). */
    const val MISSING =
        "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis folder, " +
            "run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis."

    /** Every sentence this setting shows, under the PC's own keys (`mode_words`). */
    val WORDS: Map<String, String> = linkedMapOf(
        "title" to TITLE,
        "detail" to DETAIL,
        "stop_early" to STOP_EARLY_LABEL,
        "stop_early_detail" to STOP_EARLY_DETAIL,
        "keep_offering" to KEEP_OFFERING_LABEL,
        "keep_offering_detail" to KEEP_OFFERING_DETAIL,
        "opens_windows_hello" to OPENS_WINDOWS_HELLO,
        "waiting" to WAITING_LINE,
        "off_now" to OFF_NOW,
        "damaged" to DAMAGED,
    )

    /** What each choice is called. */
    val LABELS: Map<String, String> = mapOf(
        STOP_EARLY to STOP_EARLY_LABEL,
        KEEP_OFFERING to KEEP_OFFERING_LABEL,
    )

    /** The one line that says what each choice does. */
    val HELP: Map<String, String> = mapOf(
        STOP_EARLY to STOP_EARLY_DETAIL,
        KEEP_OFFERING to KEEP_OFFERING_DETAIL,
    )

    private fun JsonObject?.text(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()

    /** A real JSON true only - the string "true" is not one. */
    private fun JsonObject?.flag(key: String): Boolean? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject?.number(key: String): Double? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

    /**
     * `GET /api/chatbot/handoff_mode`, as the settings row reads it - the
     * reference is `view()` in backend/jarvis_handoff_mode.py. [available] is
     * false for anything not in the PC's exact shape: never a guess.
     */
    data class View(
        val available: Boolean,
        val mode: String,
        val waiting: Boolean,
        val idleSeconds: Double,
        val ceilingSeconds: Double,
        val why: String,
        val lastWords: String,
    ) {
        val patient: Boolean get() = mode == KEEP_OFFERING

        /** What the row shows under the two choices, in the PC's own words. */
        val line: String
            get() = when {
                !available -> UNREAD
                waiting -> WAITING_LINE
                why.isNotEmpty() -> why
                patient -> KEEP_OFFERING_DETAIL
                else -> STOP_EARLY_DETAIL
            }
    }

    fun view(status: JsonObject?): View {
        val read = status.text("mode")
        if (read !in MODES) {
            return View(false, DEFAULT, false, 0.0, 0.0, "", "")
        }
        return View(
            available = true,
            mode = read,
            waiting = status.flag("waiting") == true,
            idleSeconds = status.number("idle_s") ?: 0.0,
            ceilingSeconds = status.number("ceiling_s") ?: 0.0,
            why = status.text("why").orEmpty(),
            lastWords = (status?.get("last") as? JsonObject).text("message").orEmpty(),
        )
    }

    /** The body for one choice, or null when it is not one of the two. */
    fun body(mode: String): String? =
        if (mode in MODES) "{\"mode\":\"$mode\"}" else null
}
