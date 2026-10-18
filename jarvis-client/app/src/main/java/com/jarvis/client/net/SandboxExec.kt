package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The data and maths sandbox's own switch (LM-1C, 2026-10-18;
 * docs/JARVIS-API.md section 142): whether the AI model is OFFERED the small
 * read-only Python tool at all. Off by default; ON is ONE normal approval card
 * on the PC (`change_own_config`), OFF is instant - the same shape as
 * [BrowserEngine] and [ScreenPicture], and decided on the PC like them.
 *
 * THIS PHONE ONLY SHOWS AND ASKS. It never runs a script and never sees a file
 * or a piece of data: the sandbox runs on the PC, and every one of its own
 * refusals (no network, no file writes, only the files the owner listed, time
 * and output caps) is unchanged by this switch.
 *
 * - `GET /api/sandbox` - what [panel] reads: `enabled`, `waiting`, `line`
 *   (the PC's own state sentence, including what the last card did), `status`
 *   and `why`. The PC writes the line itself, so both apps say the same words.
 * - `POST /api/sandbox {"enabled": bool}` - ON is 202 `{"waiting": true}`
 *   while one approval card waits; OFF is 200 at once and withdraws a waiting
 *   ON card.
 *
 * A PC whose route is missing (its Jarvis predates the drop-in folder) answers
 * 404 or 501, which [missing] names so the plate can disable the switch with
 * one sentence instead of pretending it is off.
 */
object SandboxExec {
    const val PATH = "/api/sandbox"

    /** The approval action the PC raises the ON card under. */
    const val ACTION = "change_own_config"

    const val TITLE = "Data and maths sandbox"
    const val SWITCH = "Let Jarvis run small Python scripts for sums and averages"
    const val DETAIL =
        "Off by default. The AI model may run a small Python script for sums, averages and " +
            "percentages, in its own sandbox: no network, no file writes, only files you have " +
            "already listed for Jarvis, a hard time limit and an output limit. It refuses " +
            "dangerous code before it starts anything. Turning it on asks first, with one " +
            "approval card on the PC; turning it off is instant."
    const val OFF_LINE = "Off. The AI model is not offered the data and maths sandbox."
    const val WAITING_LINE =
        "Waiting for your approval. The AI model is offered the data sandbox only if you " +
            "approve the card."
    const val UNREAD = "Could not read this switch."
    const val MISSING =
        "This PC's Jarvis does not have the data sandbox switch yet. In PowerShell on the PC, " +
            "in the Jarvis folder, run: .\\scripts\\add-plugin.ps1 -Name sandbox . Then restart " +
            "Jarvis."
    const val WAITING_LINK = "Waiting for the connection to your PC."
    const val COULD_NOT_TURN_ON = "Could not turn it on: "

    fun enabledBody(on: Boolean): String = "{\"enabled\":$on}"

    /** A read that failed because this PC's Jarvis has no sandbox route. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /**
     * What the plate shows for one `GET /api/sandbox` answer - the reference is
     * `view()` in backend/jarvis_sandbox_exec.py. The switch looks ON while a
     * card waits, so it can be taken back, but the line says it is only
     * waiting. A real JSON boolean is required for the switch itself: an answer
     * without one is [available] = false, never "off".
     */
    data class Panel(
        val available: Boolean,
        val enabled: Boolean,
        val waiting: Boolean,
        val checked: Boolean,
        val line: String,
        val status: String,
        val why: String,
    )

    private fun JsonObject.text(key: String): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty()

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    fun panel(status: JsonObject?): Panel {
        val on = status?.flag("enabled")
            ?: return Panel(false, false, false, false, UNREAD, "", "")
        val waiting = status.flag("waiting") == true && !on
        val line = status.text("line").ifEmpty {
            when {
                waiting -> WAITING_LINE
                !on -> OFF_LINE
                else -> ""
            }
        }
        return Panel(
            available = true,
            enabled = on,
            waiting = waiting,
            checked = on || waiting,
            line = line,
            status = status.text("status"),
            why = status.text("why"),
        )
    }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused ->
            if (on) COULD_NOT_TURN_ON + outcome.why else "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said
            ?: if (on) "The data sandbox is on." else OFF_LINE
    }

    /** The PC's own words and where to approve it - never a line the phone made up. */
    fun waitingLine(): String = "$WAITING_LINE ${Approvals.WHERE}"
}
