package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The headless browser (Obscura) setting (docs/JARVIS-API.md section 97; the
 * owner's decision, 2026-09-29): Jarvis may choose a browser with no window,
 * instead of the visible one, for plain web reading. Off by default, ON is one
 * approval card on the PC, OFF is instant - the same shape as [ScreenPicture],
 * and, like it, decided on the PC and read by both apps.
 *
 * THIS PHONE ONLY SHOWS AND SETS. It never runs a browser, never sees a web
 * page and has no proxy or address field: the program (Obscura) runs on the PC,
 * and every page it opens, click and box it fills is still its own plan card,
 * exactly as for the visible browser.
 *
 * - `GET /api/browser/engine` - what [panel] reads (`obscura`, `waiting`,
 *   `mode`, `line`, `status_line`, `install_line`, ...). The PC writes the
 *   lines itself, so both apps say the same words.
 * - `POST /api/browser/engine {"obscura": bool}` - ON is 202 `{"waiting": true}`
 *   while one approval card (action [ACTION]) is up; OFF is 200 at once and
 *   withdraws a waiting ON card.
 * - `POST /api/browser/engine {"mode": "auto"|"visible"|"headless"}` - which
 *   browser Jarvis uses by default; at once, no card.
 *
 * A route this old does not have (a PC without `browser-engine.patch`, or
 * without `jarvis_browser_engine.py`) answers 404 or 503, which
 * [com.jarvis.client.JarvisRuntime] reads as "not on this PC's Jarvis yet".
 *
 * THE FIXED WORDS are the PC's (`WORDS` in backend/jarvis_browser_engine.py):
 * tools/gen_browser_cases.py writes them into `contract/browser-engine-cases.json`
 * and BrowserEngineTest holds this file to them, so the two apps cannot drift.
 */
object BrowserEngine {
    const val PATH = "/api/browser/engine"

    /** The approval action the PC raises the ON card under. */
    const val ACTION = "obscura_enable"

    /** The three modes, in the PC's order. */
    val MODES: List<String> = listOf("auto", "visible", "headless")
    const val DEFAULT_MODE = "auto"

    const val TITLE = "Headless browser (Obscura)"
    const val DETAIL =
        "Jarvis normally works a web page in a browser window you can see. This adds a second " +
            "way: Obscura, a small browser with no window, for plain reading and quick lookups. " +
            "Jarvis chooses per task - the visible window when you might need to sign in or take " +
            "over, the headless browser for simple reading. Every page it opens and every step it " +
            "takes is still listed on an approval card first. What it reads is outside text: it " +
            "never becomes a fact Jarvis remembers. It cannot reach your own network (this PC, " +
            "your home network, Tailscale), uses no proxy, keeps no cookies and saves no files. " +
            "Off by default. Turning it on asks first, because it is a new program on your PC " +
            "that reaches the web."
    const val SWITCH = "Let Jarvis use the headless browser (Obscura)"
    const val MODE_TITLE = "Which browser Jarvis uses"
    const val STEALTH =
        "Stealth is always on for the headless browser. It makes the browser look like an " +
            "ordinary Chrome. It does not solve captchas, and sites can still block or ban it. " +
            "Signing in to a real account with it could get that account closed under a site's terms, " +
            "so Jarvis never types a password with it and never solves a captcha: when it sees a " +
            "captcha or a sign-in page it stops and hands the job to the visible browser. A sign-in " +
            "that starts with only a username or email box may not be recognised."
    const val OFF_LINE = "Off. Jarvis uses the visible browser window only."
    const val WAITING_LINE = "Waiting for your yes on the card. Nothing has changed yet."
    const val UNREAD = "Could not read this setting."
    const val MISSING =
        "This PC's Jarvis does not have the headless browser yet. Run " +
            "scripts\\apply-patches.ps1 on the PC to add it."
    const val STEPS_TITLE = "To install it, paste this one line into PowerShell on your PC:"
    const val STEPS_NOTE =
        "It downloads one named release of Obscura's Windows program from its GitHub releases " +
            "(github.com/h4ckf0r0day/obscura, Apache-2.0), unpacks it into Jarvis's own folder and " +
            "prints its checksums for you to compare with the release page. It does not run the " +
            "program. The line then prints a second command that checks it: version, stealth on, and " +
            "that it refuses to visit your own network. Jarvis never downloads it by itself."
    const val COPY = "Copy the line"

    /** What each mode is called, and the one line that says what it does. */
    val MODE_LABELS: Map<String, String> = mapOf(
        "auto" to "Automatic (recommended)",
        "visible" to "Always the visible browser",
        "headless" to "The headless browser when it can run",
    )
    val MODE_HELP: Map<String, String> = mapOf(
        "auto" to "Jarvis picks per task: the visible window whenever you might need to sign in " +
            "or take over, the headless browser for plain reading.",
        "visible" to "Jarvis always opens the browser window you can see and take over.",
        "headless" to "Jarvis uses the headless browser whenever it can run, except when the task looks like a " +
            "sign-in, a payment or a captcha. If it cannot run, Jarvis says so and uses the visible " +
            "browser.",
    )

    fun enabledBody(on: Boolean): String = "{\"obscura\":$on}"

    /** The body for one mode, or null when it is not one of the three. */
    fun modeBody(mode: String): String? =
        if (mode in MODES) "{\"mode\":\"$mode\"}" else null

    /** A read that failed because this PC's Jarvis has no headless browser. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** Is the ON card still in the approval queue? */
    fun cardWaiting(actions: List<String?>): Boolean = actions.any { it == ACTION }

    /**
     * What a settings screen shows for one `GET /api/browser/engine` answer -
     * the reference is `panel()` in backend/jarvis_browser_engine.py. The switch
     * looks ON while its card waits, so it can be turned back off, but the line
     * says it is only waiting.
     */
    data class Panel(
        val available: Boolean,
        val obscura: Boolean,
        val waiting: Boolean,
        val checked: Boolean,
        val mode: String,
        val line: String,
        val status: String,
        val installLine: String,
    )

    private fun JsonObject.text(key: String): String =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim().orEmpty()

    /** A real JSON true/false only - "true" as a string is not one. */
    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    fun panel(status: JsonObject?): Panel {
        val on = status?.flag("obscura")
            ?: return Panel(false, false, false, false, DEFAULT_MODE, UNREAD, "", "")
        val waiting = status.flag("waiting") == true && !on
        val line = status.text("line").ifEmpty {
            when {
                waiting -> WAITING_LINE
                !on -> OFF_LINE
                else -> ""
            }
        }
        val mode = status.text("mode").let { if (it in MODES) it else DEFAULT_MODE }
        return Panel(
            available = true,
            obscura = on,
            waiting = waiting,
            checked = on || waiting,
            mode = mode,
            line = line,
            status = status.text("status_line"),
            installLine = status.text("install_line"),
        )
    }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said
            ?: if (on) "The headless browser is on."
            else "The headless browser is off. Jarvis uses the visible browser only."
    }

    /** What to say after a mode was picked. */
    fun saidMode(outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said ?: "Saved."
    }

    /** The PC's own words ([WAITING_LINE]) and where to approve it - never a line the phone made up. */
    fun waitingLine(): String = "$WAITING_LINE ${Approvals.WHERE}"
}
