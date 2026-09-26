package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * "Stop everything" - the phone's button for the PC's `POST /api/stop_all`
 * (`backend/jarvis_stop_all.py`, the owner's decision of 2026-09-25). The
 * desktop's hotkey (Alt+Shift+X) calls the same route and shows the same
 * words in a notification.
 *
 * One press stops the phone's own speech at once - before the PC is even
 * asked, so a dead link never keeps Jarvis talking - then asks the PC to
 * stop a running task before its next step, make the answer being written
 * use no more tools, and stop everything registered with it. It approves
 * nothing and starts nothing, needs no approval card, and is **never held
 * on a stale link**: stopping only ever makes Jarvis do less (rule 4 blocks
 * acting, and this is the opposite).
 *
 * Kept apart from [com.jarvis.client.JarvisRuntime] so what the button
 * claims can be unit tested without a running app.
 */
object StopEverything {
    /** The button's words - the desktop's hotkey is called this too. */
    const val LABEL = "Stop everything"

    /** The line under the button. */
    const val HINT = "Stops Jarvis talking and anything it is doing on the PC or this phone. " +
        "Asks nothing first; approves nothing."

    /** Always true by the time the PC answers: the phone stopped its own speech first. */
    const val SPEECH = "Stopped speaking."

    /** The PC sent no words of its own. The desktop's `STOP_PC_SILENT`. */
    const val PC_SILENT = "Jarvis stopped what it was doing."

    /** The PC could not be asked; the plain reason follows. The desktop's `STOP_NOT_REACHED`. */
    const val NOT_REACHED = "Nothing else could be stopped."

    /**
     * The PC could not be reached: the plain words every other failure uses
     * (PlainErrors - "Your PC isn't answering. ..."), after [SPEECH] and
     * [NOT_REACHED], with their one button (Try again, or Check the
     * connection settings). Null for any other failure.
     */
    fun problem(error: ApiError?): PlainErrors.Shown? {
        if (error !is ApiError.Unreachable) return null
        val plain = PlainErrors.forApiError(error)
        return plain.copy(says = "$SPEECH $NOT_REACHED ${plain.says}".trim())
    }

    /**
     * What the phone says after a press: [SPEECH], then the PC's own
     * sentence (`message`) - or why the PC could not be asked.
     */
    fun describe(reply: JsonObject?, error: ApiError?): String {
        if (error != null) {
            return when (error) {
                ApiError.NotFound ->
                    "$SPEECH This PC's Jarvis cannot stop anything else yet - run " +
                        "apply-patches.ps1 on the PC (stop-all.patch). The Stop button on " +
                        "a running task still works."
                ApiError.BadToken ->
                    "$SPEECH The PC refused this phone's token, so nothing else was stopped. " +
                        "Pair the phone again from the desktop's Settings."
                is ApiError.Unreachable -> problem(error)?.text ?: "$SPEECH $NOT_REACHED"
                else -> "$SPEECH The PC could not be asked to stop anything else."
            }
        }
        val said = (reply?.get("message") as? JsonPrimitive)
            ?.takeIf { it.isString }?.content?.trim()?.takeIf { it.isNotEmpty() }
        return "$SPEECH ${said ?: PC_SILENT}"
    }
}
