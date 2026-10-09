package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * The prompt coach (docs/PROMPT-COACH-DESIGN.md; backend
 * `jarvis_prompt_coach.py`, `prompt-coach.patch`). The owner asked for it on
 * 2026-10-08: a "Coach this" button beside the box where they type, which asks
 * the model on their own PC what is missing from the question they are about
 * to send - a score, up to four gaps, and a rewritten version they may send
 * instead of theirs.
 *
 * This object is BOTH halves: the settings switch on Mind ([View], [parse],
 * [enabledBody], [said]) and the button's own half ([coachBody], [Critique],
 * [parseCritique], [classify]).
 *
 * What the phone does with the switch: turn it on or off, ONE change. Neither
 * direction raises an approval card (the PC's decision of 2026-10-08, and its
 * own detail line says so), because the coach reads only words the chat is
 * about to send to the same local model, takes no action and opens no way out
 * of the PC.
 *
 * WHAT THE BUTTON DOES, and the part that must not drift: it SENDS nothing.
 * `POST /api/prompt/coach` returns a critique, and the owner then presses
 * either "Send mine" (their own words, unchanged) or "Send the suggestion"
 * (the rewrite, put in the box and sent). There is no improve-and-send. The
 * score is never a gate - a 1 out of 10 is still sendable - and a refusal is
 * the PC's own sentence, never a generic failure.
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
    /** The switch's own state (`GET`), and the critique and the one setting (`POST`). */
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

    // ---- The critique's own words -------------------------------------------
    //
    // The PC sends the critique as data (`jarvis_prompt_coach.SCHEMA`): a
    // score, a boolean, a list of {what, why, fix}, a list of questions and one
    // rewritten prompt. It sends NO sentences to label them, so the three
    // labels below are this app's own, kept here rather than inline so a test
    // can read them - the same reason [WebSearch] keeps its labels in its
    // object.

    /** "Score: 7 out of 10". */
    fun scoreLine(score: Int): String = "Score: $score out of 10"

    /** What each gap is: what is missing, why it matters, the smallest fix. */
    const val ISSUE_WHAT = "What's missing"
    const val ISSUE_WHY = "Why it matters"
    const val ISSUE_FIX = "The smallest fix"

    /** The heading over the questions the coach would have to ask. */
    const val MISSING_TITLE = "What it would need to ask you"

    /** The heading over the rewrite - shown in full, and never applied by itself. */
    const val SUGGESTION_TITLE = "A rewrite you could send"

    /**
     * While the model reads the question. The design says plainly that nobody
     * has measured how long a critique takes on the owner's PC, so this line
     * is the only promise made about speed: that something is happening.
     */
    const val READING = "Reading your question…"

    /** The one way out of the advice panel without sending anything. */
    const val DISMISS = "Dismiss"

    /**
     * Said under the two buttons when they cannot be pressed - the link went
     * down, an answer is streaming, or shared text arrived while the panel was
     * open. The panel stays: the advice is still worth reading.
     */
    const val NOT_NOW =
        "Not connected just now, so nothing can be sent. Your words are still in the box."

    /**
     * The PC answered a 200 that was not a critique. That is a fault in the
     * answer rather than a refusal, so it is not dressed up as one - but it is
     * still a sentence, because an empty panel would look like a coach with
     * nothing to say.
     */
    const val MALFORMED =
        "The prompt coach's answer was not something this app could read, so there is " +
            "nothing to show. Nothing was sent."

    /**
     * The line for a critique with nothing to say. The PC's own module says
     * this is a valid, expected answer ("INVENTING A COMPLAINT IS A FAILURE"),
     * and `clear` is the model's own word for it - but it is only believed
     * when there are no gaps, because a model that says "clear" while listing
     * four gaps is contradicting itself (`jarvis_prompt_coach.parse`).
     */
    const val CLEAR_LINE = "Nothing missing that it could see. Send it."

    /**
     * The fewest words worth a model call, matching the PC's own
     * `jarvis_prompt_coach.MIN_WORDS`. The PC refuses anything shorter with
     * its own sentence; the phone does not send it at all, so a two-word
     * question never costs the owner a model call.
     */
    const val MIN_WORDS = 3

    /**
     * How many earlier turns may ride with the question. The owner's answer of
     * 2026-10-08: the last few turns, so "it" and "that" have an antecedent,
     * and no more. Matches the PC's own `MAX_TURNS`, which trims again on its
     * side.
     */
    const val MAX_TURNS = 6

    /** Who said one earlier turn. The PC reads `who` as free text and only prints it. */
    const val OWNER = "owner"
    const val JARVIS = "jarvis"

    /** One earlier turn as the coach sees it. */
    data class Turn(val who: String, val text: String)

    /**
     * The PC's answer to `GET /api/prompt/coach`, in its own words. The three
     * button labels are carried but unused by the settings screen: they belong
     * to the "Coach this" bar, which reads them from here ([button],
     * [sendMine], [sendSuggestion]) so the words that bar shows cannot drift
     * from the PC's.
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
        /**
         * The route answered at all. False only when `GET /api/prompt/coach`
         * failed in a way that means this PC has no prompt coach
         * ([missing]), which is the one case the chat bar says [MISSING]
         * instead of hiding the button - a PC that has the route with the
         * switch off is simply off, and shows nothing.
         */
        val routeKnown: Boolean = true,
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

    /**
     * What the chat bar knows about the coach: the PC's own words, or that
     * this PC has no route at all. `null` (nothing read yet) is not this type
     * - the caller keeps "not asked" and "off" apart, because "off" means no
     * button and "not asked" means no button either, but only one of them has
     * a sentence the owner may need to see.
     */
    fun absentView(): View = View(
        on = false,
        why = "",
        label = LABEL,
        detail = DETAIL,
        heading = HEADING,
        button = BUTTON,
        sendMine = SEND_MINE,
        sendSuggestion = SEND_SUGGESTION,
        routeKnown = false,
    )

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

    // ---- The button's half --------------------------------------------------

    /**
     * The last few turns of the conversation, oldest first, as the coach sees
     * them: the owner's own question then Jarvis's answer, for each finished
     * exchange. Capped at [MAX_TURNS] - the NEWEST ones, because a pronoun in
     * the question on screen points at what was just said, not at the start of
     * the chat. Nothing else of an exchange rides along: not the provenance
     * tag, not the picture, not the shared text, and nothing Jarvis read from
     * a tool. Blank turns are dropped rather than sent as empty lines.
     *
     * A chat that has read outside text is not special-cased here: the words
     * are the owner's own conversation, which the chat is about to send to the
     * same local model anyway, and the critique is kept nowhere (the design's
     * rule 2). What must never happen is the coach SENDING anything, and it
     * cannot - it returns text.
     */
    fun history(thread: List<ChatHistory.Exchange>): List<Turn> {
        val out = ArrayList<Turn>(MAX_TURNS * 2)
        for (exchange in thread) {
            val question = exchange.question.trim()
            if (question.isNotEmpty()) out.add(Turn(OWNER, question))
            val answer = exchange.answer.trim()
            if (answer.isNotEmpty()) out.add(Turn(JARVIS, answer))
        }
        // Keep the newest, in order. `out` is oldest-first, so the tail is what
        // was said last.
        return if (out.size <= MAX_TURNS) out else out.subList(out.size - MAX_TURNS, out.size).toList()
    }

    /**
     * `POST /api/prompt/coach`'s body: the words in the box, and the last few
     * turns beside them (`jarvis_prompt_coach.handle_post` reads `text` and
     * `history`, each turn `{"who", "text"}`).
     *
     * Built with the JSON writer rather than by hand, so a quote, a newline or
     * a backslash in what the owner typed cannot break out of its field and
     * change the request - the same rule [ChatHistory.messages] follows.
     */
    fun coachBody(text: String, history: List<Turn>): String = JsonObject(
        mapOf(
            "text" to JsonPrimitive(text),
            "history" to JsonArray(
                history.map { t ->
                    JsonObject(mapOf("who" to JsonPrimitive(t.who), "text" to JsonPrimitive(t.text)))
                },
            ),
        ),
    ).toString()

    /** One gap: what is missing, why it matters, and the smallest fix. */
    data class Issue(val what: String, val why: String, val fix: String)

    /**
     * The critique, exactly as the PC's `jarvis_prompt_coach.parse` hands it
     * over: the lists are already trimmed and the score is already clamped to
     * 1..10 on the PC, and this type adds nothing to them.
     */
    data class Critique(
        val score: Int,
        /**
         * The model's own answer to "is this already fine?", believed only
         * when there are no gaps - the PC does that join, so this is already
         * the corrected value.
         */
        val clear: Boolean,
        val issues: List<Issue>,
        /** The questions the coach would have to ask to do the job well. */
        val missing: List<String>,
        /** The same request, rewritten. Shown in full, never applied. */
        val suggestion: String,
    )

    /**
     * The PC's answer to `POST /api/prompt/coach`, read.
     *
     * Null when this is not that answer at all - no `coach` object, a score
     * that is not a whole number, or an `issues` entry with no `what` (its one
     * required field, and the one the screen cannot draw a gap without). Null
     * is deliberate and is the discipline the rest of this file follows: the
     * alternative is a half-filled panel that looks built, which is the exact
     * failure docs/JARVIS-API.md's `probe` note was written about.
     *
     * A field that is merely ABSENT is not that failure, because the PC's own
     * parser guarantees each one: it sends `why` and `fix` as "" rather than
     * dropping them, `missing` as a list, and `suggestion` as a string. So a
     * missing `why` reads as no `why` said, and a missing `missing` as no
     * questions - the PC already went to the trouble of meaning that.
     */
    fun parseCritique(body: JsonObject): Critique? {
        val coach = body["coach"] as? JsonObject ?: return null
        val score = coach.number("score")?.intOrNull ?: return null
        // The PC clamps to 1..10; clamp again rather than show "Score: 40"
        // against a PC that ever stops doing so.
        val clamped = score.coerceIn(1, 10)
        val rawIssues = coach["issues"] as? JsonArray ?: return null
        val issues = ArrayList<Issue>(rawIssues.size)
        for (el in rawIssues) {
            val o = el as? JsonObject ?: return null
            val what = o.text("what") ?: return null
            issues.add(Issue(what = what, why = o.text("why") ?: "", fix = o.text("fix") ?: ""))
        }
        val missing = (coach["missing"] as? JsonArray).orEmpty().mapNotNull { el ->
            val s = (el as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()
            s?.takeIf { it.isNotEmpty() }
        }
        return Critique(
            score = clamped,
            // Not "clear unless there are issues": the PC already made that
            // join, and second-guessing it here would hide a genuine
            // contradiction from the owner instead of showing it.
            clear = coach.flag("clear") == true,
            issues = issues,
            missing = missing,
            suggestion = coach.text("suggestion") ?: "",
        )
    }

    /** What the PC answered a `POST /api/prompt/coach`, kept whole ([classify]). */
    data class Reply(val code: Int, val body: JsonObject?)

    /** What one press of "Coach this" came to. */
    sealed interface Read {
        data class Shown(val critique: Critique) : Read

        /**
         * The PC refused, in its own sentence - too short to coach, the switch
         * off on the PC, no model found, the model silent, the address not
         * this PC. Never re-worded here: `jarvis_prompt_coach.Refused` exists
         * so the owner gets the real reason.
         */
        data class Refused(val said: String) : Read

        /** The PC answered, and the answer was not a critique. */
        data object Malformed : Read

        /** This PC has no prompt coach at all. */
        data object Missing : Read

        /** Something else went wrong on the way; [JarvisRuntime] words it. */
        data class Failed(val why: String) : Read
    }

    /**
     * What one `POST /api/prompt/coach` came to, from its status and body.
     *
     * `jarvis_prompt_coach.handle_post` refuses with a 409 and its own
     * sentence in `error`; a PC without the module answers 503; a 200 carries
     * `{"ok": true, "coach": {...}}`. So a 200 that is not a critique really
     * is a malformed answer, and anything else that carries a sentence is a
     * refusal rather than a transport failure - "the desktop answered 409"
     * would be the wrong thing to show beside a button the owner just
     * pressed.
     *
     * A 404 is the one exception: `PromptCoach.missing` reads a 404 as "this
     * PC has no route", so it must not be flattened into a refusal sentence
     * here.
     */
    fun classify(code: Int, body: JsonObject?): Read = when {
        code == 200 -> {
            val critique = if (body == null) null else parseCritique(body)
            if (critique != null) Read.Shown(critique) else Read.Malformed
        }
        code == 404 -> Read.Missing
        else -> {
            val said = if (body == null) null else body.text("error")
            if (said != null) Read.Refused(said) else Read.Failed("The desktop answered $code.")
        }
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull

    private fun JsonObject.number(key: String): JsonPrimitive? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }
}
