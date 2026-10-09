package com.jarvis.client.net

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * The prompt coach (docs/PROMPT-COACH-DESIGN.md; backend
 * `jarvis_prompt_coach.py`, `prompt-coach.patch`). The owner asked for it on
 * 2026-10-08: a "Coach this" button beside the box where they type, which asks
 * the model on their own PC what is missing from the question they are about
 * to send - a score, up to four gaps, and a rewritten version they may send
 * instead of theirs.
 *
 * This object is the SWITCH's half, which is all this phone does with it: the
 * settings card on Mind, OFF by default. The button itself, the critique and
 * "Send mine" / "Send the suggestion" are later work - nothing here builds
 * them, and nothing here reads a prompt.
 *
 * What the phone does: turn it on or off, ONE change. Neither direction raises
 * an approval card (the PC's decision of 2026-10-08, and its own detail line
 * says so), because the coach reads only words the chat is about to send to
 * the same local model, takes no action and opens no way out of the PC.
 *
 * The copies of the PC's words below are byte-identical to
 * `backend/jarvis_prompt_coach.py`'s `LABEL`, `DETAIL`, `HEADING`, `BUTTON`,
 * `SEND_MINE` and `SEND_SUGGESTION` (the same shape as [WebSearch]'s copies of
 * `jarvis_search.py`'s words): the PC sends them with every read, and they are
 * used only when an answer lacks them. `MISSING` is byte-identical to the
 * desktop's own copy of that sentence, and the two status lines are the
 * desktop's own wording.
 *
 * Pure Kotlin, no Android types, so a plain JVM test can run it against the
 * PC's real answers - the same rule [WebSearch] follows.
 */
object PromptCoach {
    /** The switch's own state (`GET`), and the one setting (`POST`). */
    const val PATH = "/api/prompt/coach"
    const val SETTING_PATH = "/api/prompt/coach/setting"

    // The PC's words (backend/jarvis_prompt_coach.py), for when an answer
    // lacks them.
    const val LABEL = "Prompt coach"
    const val HEADING = "Prompt coach"
    const val DETAIL =
        "Off (the default): nothing is read and there is no Coach this button. " +
            "On: a Coach this button appears beside the box where you type. Pressing it " +
            "asks the model on your own PC what is missing from your question - a score, " +
            "up to four gaps, and a rewritten version you can send instead of yours. It " +
            "never sends anything by itself, it never changes your words unless you pick " +
            "the rewritten one, and it is only ever advice: a low score does not stop you " +
            "sending what you wrote. The model on this PC is small, so its advice is " +
            "sometimes wrong and it misses things a bigger model would catch. Turning " +
            "this on or off happens at once - no approval card, because nothing here " +
            "leaves the PC and nothing is acted on."
    const val BUTTON = "Coach this"
    const val SEND_MINE = "Send mine"
    const val SEND_SUGGESTION = "Send the suggestion"

    /**
     * The line under the switch after a change, in the same words the
     * desktop's own page words for itself (`prompt-coach-settings.js`:
     * `` `${label} is on.` `` / `` `is off.` ``), built from [LABEL] - which is
     * the PC's own label, byte for byte. The PC's answer to this route carries
     * `on` and `why`, not a sentence of its own to show here ([said]).
     */
    const val ON_LINE = "$LABEL is on."
    const val OFF_LINE = "$LABEL is off."

    /** What the phone says when the switch was changed and the PC sent no sentence. */
    const val WAITING_CARD = "Waiting for your approval card."

    /**
     * A PC without `jarvis_prompt_coach.py`. Byte-identical to the desktop's
     * own copy (`prompt_coach.rs`'s `PROMPT_COACH_MISSING`,
     * `prompt-coach-settings.js`'s `MISSING`), which says the phone says the
     * same words.
     */
    const val MISSING =
        "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC."

    /**
     * The PC's answer to `GET /api/prompt/coach`, in its own words. The three
     * button labels are carried but unused by this screen: they belong to the
     * "Coach this" bar, which is later work. They are read here so the words
     * that bar will need cannot drift from the PC's.
     */
    data class View(
        /** The switch, as the PC has it. */
        val on: Boolean,
        /** The PC's own sentence when its setting file could not be read; "" otherwise. */
        val why: String,
        val label: String,
        val detail: String,
        val heading: String,
        val button: String,
        val sendMine: String,
        val sendSuggestion: String,
    )

    /** `GET /api/prompt/coach`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        // No `on` means this is not the prompt coach's own answer at all:
        // "off" is a real, sent false, never a missing field.
        val on = body.flag("on") ?: return null
        return View(
            on = on,
            why = body.text("why") ?: "",
            label = body.text("label") ?: LABEL,
            detail = body.text("detail") ?: DETAIL,
            heading = body.text("heading") ?: HEADING,
            button = body.text("button") ?: BUTTON,
            sendMine = body.text("send_mine") ?: SEND_MINE,
            sendSuggestion = body.text("send_suggestion") ?: SEND_SUGGESTION,
        )
    }

    /** A read that failed because this PC has no prompt coach. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /**
     * ONE change: the prompt coach switch. Either direction is at once and
     * raises no card on the PC. `{"enabled": true|false}` is the only body
     * this object can make.
     */
    fun enabledBody(on: Boolean): String = JsonObject(mapOf("enabled" to JsonPrimitive(on))).toString()

    /**
     * What to tell the owner after the switch was pressed, from the PC's
     * answer. The PC's sentence is null for this route (its answer carries
     * `on` and `why`, not a `message`), so the line is the switch's own; the
     * PC's `why` is not lost - the screen reads the setting again straight
     * after the change and shows it.
     */
    fun said(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        // Neither direction of THIS switch raises a card, so this branch is
        // not reached by the prompt coach itself. It is kept because the
        // runtime treats any card that appeared in the queue while the
        // request was out as waiting (DesktopWrite.withNewCard), and that
        // sentence is better than claiming the change is done.
        is DesktopWrite.Outcome.Waiting -> WAITING_CARD
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said ?: if (on) ON_LINE else OFF_LINE
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
