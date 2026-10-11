package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

/**
 * What a captcha does about the browser window it is blocking
 * (backend/jarvis_handoff_front.py; the owner's OWN decision of 2026-10-09, his
 * words: "1 by default with the option for 2 in the settings of Jarvis"). The
 * hand-off itself is [Handoff]; how long it stays on offer is [HandoffMode].
 *
 * When a captcha or a sign-in page blocks the browser window Jarvis is driving,
 * one of two things may happen to that window on the PC:
 *
 *  * "Leave it where it is" ([LEAVE_IN_PLACE]) - THE DEFAULT, and the narrower
 *    one: the window is not touched at all - it keeps its size, its place and
 *    whatever is in front of it - and the PC says plainly which window Jarvis is
 *    stuck on, so the owner solves it there when they are ready;
 *  * "Bring it to the front" ([BRING_TO_FRONT]): that one window is raised and
 *    activated the moment Jarvis is stuck, so it is in front and ready to type
 *    into. It takes the owner's screen and their keyboard away from whatever
 *    they were doing - MORE than Jarvis was doing before - so choosing it is ONE
 *    approval card on the PC with Windows Hello ([ACTION]), and the PC refuses
 *    it from any other device. Going back is instant, from either app.
 *
 * THIS PHONE SHOWS AND SETS: one word, in the PC's own words. It never raises a
 * window itself, never pictures anything, and holds nothing of its own.
 *
 * A PC whose backend is older than this setting answers 404 or 503, which
 * [com.jarvis.client.JarvisRuntime] reads as "not on this PC's Jarvis yet".
 *
 * Pure Kotlin (no Android), so HandoffFrontTest runs it against the PC's real
 * answers (contract/handoff-cases.json, tools/gen_handoff_cases.py): the words
 * are the PC's own (`WORDS` in jarvis_handoff_front.py) and the two values and
 * the default are read from the same file, so neither app can drift.
 */
object HandoffFront {
    /** The setting's one route. NOT under the hand-off's own routes: see [Handoff]. */
    const val PATH = "/api/chatbot/handoff_front"

    /** The approval action the PC raises the "Bring it to the front" card under. */
    const val ACTION = "handoff_bring_to_front"

    const val LEAVE_IN_PLACE = "leave_in_place"
    const val BRING_TO_FRONT = "bring_to_front"
    /** The two choices, in the PC's order. */
    val MODES: List<String> = listOf(LEAVE_IN_PLACE, BRING_TO_FRONT)
    /** The default, and the one that touches no window at all. */
    const val DEFAULT = LEAVE_IN_PLACE

    const val TITLE = "When a captcha stops Jarvis"
    const val DETAIL =
        "When Jarvis is stuck on a captcha or a sign-in page, it can leave that browser window " +
            "exactly where it is - or bring it to the front so you can type into it. Either way " +
            "the PC says which window is stuck."
    const val LEAVE_IN_PLACE_LABEL = "Leave it where it is"
    const val LEAVE_IN_PLACE_DETAIL =
        "The window is not touched: it keeps its size, its place and whatever is in front of it. " +
            "The PC says which window Jarvis is stuck on, and you solve it there when you are ready."
    const val BRING_TO_FRONT_LABEL = "Bring it to the front"
    const val BRING_TO_FRONT_DETAIL =
        "That one window is raised and activated the moment Jarvis is stuck, so it is in front " +
            "and ready to type into. It takes your screen and your keyboard away from whatever " +
            "you were doing, so turning this on asks for your approval."
    const val OPENS_WINDOWS_HELLO =
        "Turning \"Bring it to the front\" on asks for your approval on the PC."
    const val WAITING_LINE =
        "Waiting for your approval. The window stays where it is until you approve the card."
    const val OFF_NOW = "Done. The window stays where it is again."
    const val DAMAGED =
        "the captcha window setting is damaged, so the window stays where it is. Choose " +
            "\"Bring it to the front\" again to rewrite it"
    /** A read that never reached the PC. */
    const val UNREAD = "Could not read this setting."
    /** One tap is in flight. */
    const val ASKING = "Asking your PC…"
    /** Raising the window waits for a fresh link; leaving it alone never does. */
    const val WAITING_LINK = "Waiting for the connection to your PC."
    /** The PC has no such setting yet (an older backend). */
    const val MISSING =
        "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis folder, " +
            "run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis."

    /** Every sentence this setting shows, under the PC's own keys (`front_words`). */
    val WORDS: Map<String, String> = linkedMapOf(
        "title" to TITLE,
        "detail" to DETAIL,
        "leave_in_place" to LEAVE_IN_PLACE_LABEL,
        "leave_in_place_detail" to LEAVE_IN_PLACE_DETAIL,
        "bring_to_front" to BRING_TO_FRONT_LABEL,
        "bring_to_front_detail" to BRING_TO_FRONT_DETAIL,
        "opens_windows_hello" to OPENS_WINDOWS_HELLO,
        "waiting" to WAITING_LINE,
        "off_now" to OFF_NOW,
        "damaged" to DAMAGED,
    )

    /** What each choice is called. */
    val LABELS: Map<String, String> = mapOf(
        LEAVE_IN_PLACE to LEAVE_IN_PLACE_LABEL,
        BRING_TO_FRONT to BRING_TO_FRONT_LABEL,
    )

    /** The one line that says what each choice does. */
    val HELP: Map<String, String> = mapOf(
        LEAVE_IN_PLACE to LEAVE_IN_PLACE_DETAIL,
        BRING_TO_FRONT to BRING_TO_FRONT_DETAIL,
    )

    private fun JsonObject?.text(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()

    /** A real JSON true only - the string "true" is not one. */
    private fun JsonObject?.flag(key: String): Boolean? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    /**
     * `GET /api/chatbot/handoff_front`, as the settings row reads it - the
     * reference is `view()` in backend/jarvis_handoff_front.py. [available] is
     * false for anything not in the PC's exact shape: never a guess.
     */
    data class View(
        val available: Boolean,
        val mode: String,
        val waiting: Boolean,
        val why: String,
        val lastWords: String,
    ) {
        val raises: Boolean get() = mode == BRING_TO_FRONT

        /** What the row shows under the two choices, in the PC's own words. */
        val line: String
            get() = when {
                !available -> UNREAD
                waiting -> WAITING_LINE
                why.isNotEmpty() -> why
                raises -> BRING_TO_FRONT_DETAIL
                else -> LEAVE_IN_PLACE_DETAIL
            }
    }

    fun view(status: JsonObject?): View {
        // `read` is `String?`: a missing `mode` field, a damaged file or a word
        // that is not one of the two is not a mode, so it reads as the
        // fail-closed default rather than being forced to a non-null String.
        val read = status.text("mode")
        if (read == null || read !in MODES) {
            return View(false, DEFAULT, false, "", "")
        }
        return View(
            available = true,
            mode = read,
            waiting = status.flag("waiting") == true,
            why = status.text("why").orEmpty(),
            lastWords = (status?.get("last") as? JsonObject).text("message").orEmpty(),
        )
    }

    /** The body for one choice, or null when it is not one of the two. */
    fun body(mode: String): String? =
        if (mode in MODES) "{\"mode\":\"$mode\"}" else null
}
