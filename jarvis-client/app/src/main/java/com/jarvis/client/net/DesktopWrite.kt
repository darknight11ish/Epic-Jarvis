package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The answer to a change the phone asked the PC for, on routes whose answer
 * shape is not written down in this repository: `/api/watch/add`,
 * `/api/watch/remove`, `/api/watch/seen` and `/api/skills/decide`. Their
 * handler is in the owner's `jarvis_hud.py` (not here), which "returns what
 * the module said - including its refusals" (`backend/appearance.patch`,
 * `_desktop_action`'s own doc).
 *
 * So nothing here assumes a field. It reads the few words every other route
 * of that server uses, and nothing else:
 *
 * - a card is up when the answer says so - `waiting: true`, `asking: true`
 *   or `state: "waiting"`, as the power, task and note routes do - or is a
 *   202. The runtime ALSO counts a card that appeared in the queue during
 *   the request as waiting ([withNewCard]), which does not depend on any
 *   field at all.
 * - `ok: false`, or a failure status carrying `error` / `reason` /
 *   `message`, is a refusal in the PC's own words.
 * - anything else in the 200s is done, with `message` or `note` if sent.
 */
object DesktopWrite {

    sealed interface Outcome {
        /** Done. [said] is the PC's own sentence, when it sent one. */
        data class Done(val said: String?) : Outcome

        /** An approval card is up, and nothing has changed yet. */
        data class Waiting(val said: String?) : Outcome

        /** The PC said no, and why. */
        data class Refused(val why: String) : Outcome
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()
            ?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull

    /** The PC's reason, as a sentence, from the fields its routes use for one. */
    private fun reason(body: JsonObject?): String? =
        (body?.str("error") ?: body?.str("reason") ?: body?.str("message"))?.let(::asSentence)

    /** The server's lower-case fragments, shown as a sentence. */
    fun asSentence(s: String): String =
        s.replaceFirstChar { it.uppercase() }.let { if (it.last() in ".!?") it else "$it." }

    fun classify(code: Int, body: JsonObject?): ApiResult<Outcome> {
        if (code == 401 || code == 403) return ApiResult.Failed(ApiError.BadToken)
        val waiting = body != null && (
            body.flag("waiting") == true || body.flag("asking") == true || body.str("state") == "waiting"
            )
        if (code in 200..299) {
            if (body?.flag("ok") == false) {
                return ApiResult.Ok(Outcome.Refused(reason(body) ?: "Your PC said no, without a reason."))
            }
            if (waiting || code == 202) return ApiResult.Ok(Outcome.Waiting(body?.str("message")))
            return ApiResult.Ok(Outcome.Done(body?.str("message") ?: body?.str("note")))
        }
        reason(body)?.let { return ApiResult.Ok(Outcome.Refused(it)) }
        return ApiResult.Failed(
            when (code) {
                404 -> ApiError.NotFound
                409 -> ApiError.AlreadyHandled
                503 -> ApiError.NotAvailable
                else -> ApiError.Server(code, "")
            },
        )
    }

    /**
     * A card that appeared in the queue while the request was out means the
     * PC is asking first, whatever its answer's fields said.
     */
    fun withNewCard(outcome: Outcome, newCard: Boolean): Outcome =
        if (newCard && outcome is Outcome.Done) Outcome.Waiting(outcome.said) else outcome
}
