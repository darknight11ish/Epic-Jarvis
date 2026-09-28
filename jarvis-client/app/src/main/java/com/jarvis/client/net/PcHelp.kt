package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * "PC help": five plain answers about the PC - why it is slow, how full its
 * drives are, what is using its graphics card, how hot the card is, and when
 * it last restarted.
 *
 * `GET /api/pc/help` - backend/jarvis_pc_help.py, routed by
 * jarvis_brain_reads.py; docs/JARVIS-API.md section 84.
 *
 * READ-ONLY: it changes nothing on the PC, so there is no card and it is
 * not held on a stale link. The phone asks only when the owner taps "Check
 * now" (one reading takes the PC a couple of seconds), never on a timer.
 * Every sentence is the PC's own; the three labels below are the desktop's
 * (pc-help.js `PC_HELP`) word for word - backend/test_pc_help.py checks.
 * The answer can name programs on the PC: it is shown, never stored or
 * logged here.
 *
 * Kept apart from the screen so it is tested on the JVM against
 * `contract/pc-help-cases.json`, the REAL answers tools/gen_pc_help_cases.py
 * writes for both apps (PcHelpContractTest).
 */
object PcHelp {

    const val PATH = "/api/pc/help"

    // The labels, word for word the desktop's.
    const val HEADING = "PC help"
    const val CHECK = "Check now"
    const val CHECKING = "Checking your PC…"

    const val UPDATE = "This PC's Jarvis does not have PC help yet. Update the backend by " +
        "running apply-patches.ps1, then try again."

    /** The phone's own line before the first check. */
    const val INTRO = "Why is your PC slow, how full are its drives, what is using the " +
        "graphics card, how hot it is, and when it last restarted. Jarvis only reads; it " +
        "changes nothing. You can also just ask Jarvis, like \"why is my PC slow?\"."

    data class Section(val id: String, val title: String, val words: String)

    data class Answer(val sections: List<Section>, val notes: List<String>)

    sealed interface Read {
        data object NotAsked : Read
        data object Checking : Read
        data class Loaded(val answer: Answer) : Read
        /** 404 or 503: the PC's backend predates PC help. */
        data object OlderBackend : Read
        data class Failed(val reason: String) : Read
    }

    /** The PC's answer, or null when it is not the shape `read()` makes. */
    fun parse(obj: JsonObject): Answer? {
        val sections = obj["sections"] as? JsonArray ?: return null
        val list = sections.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val title = o.str("title") ?: return@mapNotNull null
            val words = o.str("words") ?: return@mapNotNull null
            Section(id = o.str("id").orEmpty(), title = title, words = words)
        }
        val notes = listOfNotNull(obj.str("private"), obj.str("changes")).filter { it.isNotBlank() }
        return Answer(list, notes)
    }

    fun readOf(result: ApiResult<JsonObject>): Read = when (result) {
        is ApiResult.Ok -> {
            val obj = result.value
            if ((obj["available"] as? JsonPrimitive)?.booleanOrNull == false) {
                Read.OlderBackend
            } else {
                parse(obj)?.let { Read.Loaded(it) }
                    ?: Read.Failed("Your PC answered, but not in a shape this screen can read.")
            }
        }
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> Read.OlderBackend
            else -> Read.Failed(failureLine(e))
        }
    }

    /** The line under the button, or null when the answers say it all. */
    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> null
        Read.Checking -> CHECKING
        is Read.Loaded -> null
        Read.OlderBackend -> UPDATE
        is Read.Failed -> read.reason
    }

    private fun failureLine(e: ApiError): String = when (e) {
        // The plain words both apps use (PlainErrors): what happened, then
        // what to do - never the raw error or a status number.
        is ApiError.Unreachable, ApiError.BadToken, is ApiError.Server, is ApiError.Malformed ->
            PlainErrors.forApiError(e).text
        ApiError.NotFound, ApiError.NotAvailable -> UPDATE
        ApiError.AlreadyHandled -> "Already handled elsewhere."
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
