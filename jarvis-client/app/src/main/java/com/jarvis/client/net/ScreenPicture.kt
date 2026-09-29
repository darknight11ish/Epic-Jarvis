package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Picture mode for "Look at this" and "Watch with me" (docs/JARVIS-API.md
 * section 96.1; the owner's decision, CLAUDE.md 2026-09-29): with ONE graphics
 * card, a small picture model on the PC's PROCESSOR may also look at the
 * picture of the screen - slowly. Off by default, ON is one approval card on
 * the PC, OFF is instant - the same shape as [WatchNotify] and
 * [PhoneNotifications], and, like them, decided on the PC and read by both
 * apps. This phone never looks at a screen picture itself for this: the PC's
 * picture reader does, after the PC has blacked out secrets in it.
 *
 * - `GET /api/screen/picture` - what [panel] reads (`enabled`, `waiting`,
 *   `line`, `measured_words`, `install_line`, ...). The PC writes the state
 *   line and the measured speed itself, so both apps say the same words and
 *   this phone never guesses a speed.
 * - `POST /api/screen/picture {"enabled": bool}` - ON is 202
 *   `{"waiting": true}` while one approval card (action [ACTION]) is up; OFF is
 *   200 at once and withdraws a waiting ON card.
 *
 * A route this old does not have (a PC without `screen-picture.patch`, or
 * without `jarvis_screen_picture.py`) answers 404 or 503, which
 * [com.jarvis.client.JarvisRuntime] reads as "not on this PC's Jarvis yet".
 *
 * THE FIXED WORDS are the PC's (`WORDS` in backend/jarvis_screen_picture.py):
 * tools/gen_screen_cases.py writes them into `contract/screen-cases.json` and
 * ScreenPictureTest holds this file to them, so the two apps cannot drift.
 */
object ScreenPicture {
    const val PATH = "/api/screen/picture"

    /** The approval action the PC raises the ON card under. */
    const val ACTION = "screen_picture_enable"

    const val TITLE = "Picture mode"
    const val DETAIL =
        "By default Jarvis reads only the words on your screen. Picture mode also lets a small " +
            "picture reader look at the picture itself, so it can tell what a chart, a button " +
            "or a photo shows. It runs on your PC's main chip (the CPU), not your graphics card, " +
            "so your chat model is not slowed down - but it is SLOW, and how slow depends on " +
            "your PC. Anything that looks like a key, a card number or a password is blacked out first, " +
            "and if that part is missing no picture is used. Nothing leaves this PC and nothing " +
            "is saved. Off by default. Turning it on asks first, because a model has to be " +
            "downloaded."
    const val SWITCH = "Turn on Picture mode (slow)"
    const val OFF_LINE = "Picture mode is off. Jarvis reads the words on your screen only."
    const val WAITING_LINE = "Waiting for your yes on the card. Nothing has changed yet."
    const val UNREAD = "Could not read this setting."
    const val MISSING =
        "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis " +
            "folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis."
    const val STEPS_TITLE = "To set it up, paste this one line into PowerShell on your PC:"
    const val STEPS_NOTE =
        "It downloads the picture model from Ollama (ollama.com). We have not checked how big " +
            "the download is, so expect a wait. Then it times one look on your PC and saves the " +
            "number. Jarvis never downloads the model by itself."
    const val COPY = "Copy the line"

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    /** A read that failed because this PC's Jarvis has no picture mode. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** Is the ON card still in the approval queue? */
    fun cardWaiting(actions: List<String?>): Boolean = actions.any { it == ACTION }

    /**
     * What a settings screen shows for one `GET /api/screen/picture` answer -
     * the reference is `panel()` in backend/jarvis_screen_picture.py. The switch
     * looks ON while its card waits, so it can be turned back off, but the line
     * says it is only waiting.
     */
    data class Panel(
        val available: Boolean,
        val enabled: Boolean,
        val waiting: Boolean,
        val checked: Boolean,
        val line: String,
        val measured: String,
        val installLine: String,
    )

    private fun JsonObject.text(key: String): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty()

    /** A real JSON true/false only - "true" as a string is not one. */
    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    fun panel(status: JsonObject?): Panel {
        val enabled = status?.flag("enabled")
            ?: return Panel(false, false, false, false, UNREAD, "", "")
        val waiting = status.flag("waiting") == true && !enabled
        val line = status.text("line").ifEmpty {
            when {
                waiting -> WAITING_LINE
                !enabled -> OFF_LINE
                else -> ""
            }
        }
        return Panel(
            available = true,
            enabled = enabled,
            waiting = waiting,
            checked = enabled || waiting,
            line = line,
            measured = status.text("measured_words"),
            installLine = status.text("install_line"),
        )
    }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said
            ?: if (on) "Picture mode is on."
            else "Picture mode is off. Jarvis reads the words on your screen only."
    }

    fun waitingLine(): String =
        "Waiting for your approval to turn on picture mode. ${Approvals.WHERE}"
}
