package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Sending email (the owner's decision of 2026-09-25, after the Muse audit;
 * docs/JARVIS-API.md section 24; backend `jarvis_email_send.py`,
 * `email-send.patch`).
 *
 * Jarvis may send an email from the owner's own account, ONE approval card
 * per email, the card showing the recipients, the subject and every word.
 * On the phone that card is an ordinary approval card: [PendingRows] puts
 * the whole text in its summary, shown in full and scrollable, and the
 * notification and the home-screen widget show only the PC's `notice` -
 * "Jarvis wants to send email" - never a recipient or a word of it.
 *
 * What this adds is the Settings line, on Mind: whether sending is set up,
 * from which address and through which server, in the PC's own words
 * (`GET /api/email/sending`, `said`), the same line the desktop's Settings
 * shows. Never the password: the PC sends only whether one is set, and the
 * phone has no way to send one (it is set on the PC).
 *
 * Pure Kotlin, no Android types, so `EmailSendingTest` runs it on a plain
 * JVM against `contract/email-sending-cases.json` - the PC's real answers.
 */
object EmailSending {
    const val PATH = "/api/email/sending"

    /** The gate action every email is asked under (jarvis_email_send.ACTION). */
    const val ACTION = "send_email"

    // The desktop's words (email-sending.js).
    const val TITLE = "Sending email"
    const val NOTE =
        "Jarvis can send an email from your own account, but only after you have read all of it " +
            "on an approval card and said yes - one card per email, and there is no \"always allow\". " +
            "It uses the same account as reading email, set up on the PC."
    const val MISSING = "Your PC's Jarvis cannot send email yet - run apply-patches.ps1 on the PC."

    data class View(val ready: Boolean, val said: String, val state: String)

    /** `GET /api/email/sending`. Null when the answer carries no line. */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val said = body.text("said") ?: return null
        return View(ready = body.flag("ready") == true, said = said, state = body.text("state") ?: "")
    }

    /** A PC without the route: an older backend, or the module missing (503). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 503))

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
