package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Tutorials" and the FAQ: one catalogue for the phone and the PC, and where the
 * owner has read to.
 *
 * `GET /api/tutorials`, `POST /api/tutorials/progress`, `GET /api/faq` -
 * backend/jarvis_tutorials.py; docs/JARVIS-API.md section 114;
 * docs/TUTORIALS-DESIGN.md.
 *
 * The catalogue comes from the PC, never from this file: the same tutorials
 * have to be on both apps, and two hand-kept lists would drift. The progress is
 * the PC's too, so finishing "Memory" here marks it on the PC and the other way
 * round.
 *
 * NO CARD, EVER, and not held on a stale link: marking progress is the owner
 * recording their own reading and acts on nothing. A card per "Next" would be
 * absurd.
 *
 * The labels below are the desktop's (jarvis-desktop/src/tutorials.js `LABELS`)
 * word for word - jarvis-desktop/tests/tutorials.mjs checks, and
 * backend/test_tutorials.py checks the sections and states they both use.
 *
 * Kept apart from the screen so it is tested on the JVM.
 */
object Tutorials {

    const val PATH = "/api/tutorials"
    const val PROGRESS_PATH = "/api/tutorials/progress"
    const val FAQ_PATH = "/api/faq"

    // The labels, word for word the desktop's.
    const val HEADING = "Tutorials"
    const val INTRO_OFFER = "New here? Start with what Jarvis is"
    const val FAQ_HEADING = "Questions and answers"
    const val NEXT = "Next"
    const val BACK = "Back"
    const val SKIP = "Skip this one"
    const val QUIT = "Leave it here"
    const val AGAIN = "Show this one again"
    const val RESUME = "Continue at step"
    const val RESTART = "Start again"
    const val SEARCH = "Search the answers"
    const val STEP_OF = "Step"
    const val OF = "of"
    const val DONE = "Done"
    const val DUE = "Not read yet"
    const val IN_PROGRESS = "In progress"
    const val NOT_STARTED = "Not started"
    const val SKIPPED = "Skipped"
    const val NOTHING_FOUND = "Nothing matched that. Try a word from the question."

    const val UPDATE = "This PC's Jarvis does not have the tutorials yet. Update the backend " +
        "by running apply-patches.ps1, then try again."

    /** The sections, in the order the PC sends them. */
    val SECTIONS = listOf("pc" to "On this PC", "phone" to "On your phone")

    /** The states the route accepts; `notStarted` clears the record. */
    val STATES = listOf("in_progress", "done", "skipped", "not_started")

    /**
     * One step. `point` is the name of the REAL control this step sends the
     * owner to, in this app's own registry ([CONTROL_POINTS]) - empty when the
     * step has nothing to point at here.
     *
     * It is a registry name and never a widget or a coordinate, so the PC's
     * catalogue cannot name something this screen does not have, and a control
     * that moves is fixed in one place. A phone step is never sent a PC
     * control's name: the catalogue carries one target per app, and a step
     * meant only for the PC arrives with no phone target at all.
     *
     * A tutorial POINTS; it never presses. Nothing here may tap a control on
     * the owner's behalf - the app never approves anything by itself, and a
     * tutorial that can press a button can approve.
     */
    data class Step(
        val title: String,
        val body: String,
        val where: String,
        val point: String = "",
    ) {
        /** What this step points at here, or null when it points at nothing. */
        val target: String? get() = CONTROL_POINTS[point]

        /** True when the catalogue points this step at a control THIS app has. */
        val pointsHere: Boolean get() = target != null
    }

    data class Tutorial(
        val id: String,
        val section: String,
        val title: String,
        val why: String,
        val minutes: Int,
        val steps: List<Step>,
        val state: String,
        val step: Int,
        val stepsTotal: Int,
        val done: Boolean,
        val resumeAt: Int?,
        val due: Boolean,
    ) {
        /** Where opening this should put the owner: the recorded step, or the first. */
        val startIndex: Int
            get() = resumeAt?.takeIf { it > 0 && it < stepsTotal } ?: 0

        /** The one line a row shows about the owner's place in it. */
        val stateWords: String
            get() = when {
                done -> DONE
                state == "in_progress" && resumeAt != null -> "$RESUME ${resumeAt + 1}"
                state == "skipped" -> SKIPPED
                state == "in_progress" -> IN_PROGRESS
                else -> NOT_STARTED
            }

        /** A finished or skipped tutorial is offered again; a fresh one is not. */
        val showsAgain: Boolean
            get() = done || state == "skipped"

        val stepWords: String
            get() = "$STEP_OF ${(step + 1).coerceAtMost(stepsTotal.coerceAtLeast(1))} $OF $stepsTotal"

        /** The next step, or null when this is the last one. */
        fun nextIndex(at: Int): Int? = if (at + 1 < stepsTotal) at + 1 else null

        fun backIndex(at: Int): Int? = if (at > 0) at - 1 else null
    }

    data class Question(val q: String, val a: String, val where: String)

    /**
     * What the PC counts across the catalogue it just sent
     * (`jarvis_tutorials.py` `read()`'s `counts`: `done`, `due`, `total`).
     *
     * `due` is "no record at all, or the steps changed since one was written",
     * so `total - due` is the number of lessons the owner has MET - including
     * the ones they skipped, because a skipped lesson was met and declined.
     * That distinction is the backend's and is not merged here.
     */
    data class Counts(val done: Int, val due: Int, val total: Int)

    data class Catalogue(
        val sections: List<String>,
        val tutorials: List<Tutorial>,
        val counts: Counts? = null,
    ) {
        /**
         * One section's list: its own tutorials plus the shared ones, which is
         * what "the same tutorials on both apps" means - one catalogue, two
         * sections.
         */
        fun forSection(section: String): List<Tutorial> =
            tutorials.filter { it.section == section || it.section == "both" }

        /**
         * The ONE number this screen shows, and it counts down: "You have met 9
         * of the 23 lessons here. 14 to go."
         *
         * The desktop draws the same sentence from the same counts
         * (`jarvis-desktop/src/tutorials.js` `metWords`), which is why the two
         * apps can never disagree about it. NOT a percentage, not a streak and
         * not a badge: the design refuses all three
         * (docs/EDUCATION-TAB-DESIGN.md section 5.4), and a percentage is the
         * number that rises fastest by skipping the shortest lessons.
         *
         * It says what he has MET, never what he can DO. The stronger `used`
         * state is designed and deliberately not built (section 5.3).
         *
         * Empty when the PC did not send `counts` (an older backend): a
         * made-up total would be worse than no total.
         */
        val metWords: String
            get() {
                val counts = counts ?: return ""
                if (counts.total <= 0) return ""
                val met = (counts.total - counts.due).coerceAtLeast(0)
                val toGo = counts.total - met
                val lessons = if (counts.total == 1) "lesson" else "lessons"
                return if (toGo <= 0) "You have met all ${counts.total} $lessons here."
                else "You have met $met of the ${counts.total} $lessons here. $toGo to go."
            }
    }

    sealed interface Read {
        data object NotAsked : Read
        data object Loading : Read
        data class Loaded(val catalogue: Catalogue) : Read

        /** 404 or 501: the PC's backend predates the tutorials. */
        data object OlderBackend : Read
        data class Failed(val reason: String) : Read
    }

    /**
     * The real controls on the PHONE that a tutorial may point at, by the name
     * the catalogue uses (`backend/jarvis_tutorials.py`'s per-step
     * `point.phone`).
     *
     * This list is the phone's alone and shares no entry with the desktop's
     * (`jarvis-desktop/src/tutorials.js`'s CONTROL_POINTS), which is the whole
     * point of the request: a phone tutorial talks about tapping, swiping and
     * notifications, a PC tutorial talks about hotkeys, windows and the HUD.
     * A step that names a PC control arrives with no phone target, so it is
     * never shown here as something to do.
     *
     * Each name says where the owner should look, in the phone's own words.
     * Nothing here is tapped for them.
     *
     * `asks-first` was MISSING until 2026-10-10, and it is the reason the check
     * in TutorialsTest now reads the real catalogue. The catalogue asks the
     * phone to point at it (`intro` step 2, "Your private things never leave
     * it"), this map had no entry, and `Step.pointsHere` was therefore false -
     * so that step silently lost its phone target. Nothing failed, because the
     * phone's own test asserted against a fixture this file cannot drift from
     * the catalogue into. The desktop's equivalent (jarvis-desktop/tests/
     * tutorials.mjs) read `backend/jarvis_tutorials.py` all along and would
     * have caught it on this side.
     */
    val CONTROL_POINTS = mapOf(
        "approval-card" to "The approval card on Home - tap it, or swipe it",
        "talk-button" to "The talk button at the bottom of Home",
        "pairing" to "Pairing, in Brain",
        "notifications" to "Your phone's own notification shade",
        "live-tile" to "The Live tile in Quick Settings",
        "phone-pc-only" to "Nothing to tap - this one is worth knowing",
        "asks-first" to "What asks first, in Settings",
    )

    /**
     * The actions a step may ask this app to NOTICE: the `used` half of the
     * design, which is **designed and NOT BUILT** (docs/TUTORIALS-DESIGN.md,
     * "`try` and the `used` state - DESIGN ONLY").
     *
     * A step may carry `try` beside `point`, in the same per-app shape as
     * [CONTROL_POINTS]:
     *
     *     "try": {"desktop": "switch-model", "phone": null}
     *
     * `null` means "this app never shows this as a thing to do" - the same rule
     * `point` uses, and the same failure it prevents: a step this app cannot
     * observe must not offer something that never lights up.
     *
     * **Nothing observes these yet.** No `used` record can be written and this
     * screen draws none - `Tutorials.kt` never reads this map. It is a registry
     * of NAMES, so the catalogue cannot name an action no app declares, and so
     * that building the mechanism is one file per app rather than a rewrite of
     * the curriculum. `TutorialsTest` holds the real catalogue to it.
     *
     * Only what THIS app can really see is listed. "add-live-tile" is here
     * because the phone owns the tile; the desktop's map has no such entry, so
     * the catalogue sends it `null` there.
     */
    val TRY_ACTIONS = mapOf(
        "ask-home-status" to "Home Assistant answered a status question",
        "open-memory" to "the Memory part of Brain was really opened",
        "open-work" to "the Work part of Brain was really opened",
        "ring-phone" to "a paired phone really rang",
        "add-live-tile" to "the Live tile was really placed in Quick Settings",
    )

    private fun str(obj: JsonObject, key: String): String =        (obj[key] as? JsonPrimitive)?.contentOrNull.orEmpty()

    /** The phone's own target for a step: `point.phone`, empty when None. */
    private fun point(obj: JsonObject): String {
        val points = obj["point"] as? JsonObject ?: return ""
        return str(points, "phone")
    }

    private fun step(obj: JsonObject): Step =
        Step(title = str(obj, "title"), body = str(obj, "body"),
             where = str(obj, "where"), point = point(obj))

    /** A tutorial, or null when it is not the shape `read()` makes. */
    fun parseTutorial(obj: JsonObject): Tutorial? {
        val id = str(obj, "id")
        if (id.isEmpty()) return null
        val steps = (obj["steps"] as? JsonArray)
            ?.mapNotNull { (it as? JsonObject)?.let(::step) }.orEmpty()
        return Tutorial(
            id = id,
            section = str(obj, "section"),
            title = str(obj, "title"),
            why = str(obj, "why"),
            minutes = (obj["minutes"] as? JsonPrimitive)?.intOrNull ?: 0,
            steps = steps,
            state = str(obj, "state").ifEmpty { "not_started" },
            step = (obj["step"] as? JsonPrimitive)?.intOrNull ?: 0,
            stepsTotal = (obj["steps_total"] as? JsonPrimitive)?.intOrNull ?: steps.size,
            done = (obj["done"] as? JsonPrimitive)?.booleanOrNull ?: false,
            resumeAt = (obj["resume_at"] as? JsonPrimitive)?.intOrNull,
            due = (obj["due"] as? JsonPrimitive)?.booleanOrNull ?: true,
        )
    }

    /** The PC's catalogue, or null when it is not that shape. */
    fun parse(obj: JsonObject): Catalogue? {
        val list = obj["tutorials"] as? JsonArray ?: return null
        val tutorials = list.mapNotNull { (it as? JsonObject)?.let(::parseTutorial) }
        if (tutorials.isEmpty()) return null
        val sections = (obj["sections"] as? JsonArray)
            ?.mapNotNull { (it as? JsonObject)?.let { s -> str(s, "id").ifEmpty { null } } }
            .orEmpty()
        return Catalogue(sections.ifEmpty { SECTIONS.map { it.first } }, tutorials, counts(obj))
    }

    /** The PC's own totals, or null when it did not send them (an older one). */
    private fun counts(obj: JsonObject): Counts? {
        val block = obj["counts"] as? JsonObject ?: return null
        fun number(key: String): Int? = (block[key] as? JsonPrimitive)?.intOrNull
        val done = number("done") ?: return null
        val due = number("due") ?: return null
        val total = number("total") ?: return null
        return Counts(done = done, due = due, total = total)
    }

    /** One question and its answer, or null when it is not that shape. */
    fun parseQuestion(obj: JsonObject): Question? {
        val q = str(obj, "q")
        if (q.isEmpty()) return null
        return Question(q = q, a = str(obj, "a"), where = str(obj, "where"))
    }

    /** The whole FAQ, in the PC's own order. */
    fun parseFaq(obj: JsonObject): List<Question>? {
        val list = obj["questions"] as? JsonArray ?: return null
        return list.mapNotNull { (it as? JsonObject)?.let(::parseQuestion) }
    }

    /**
     * The FAQ filtered by what the owner typed. In the question AND the answer,
     * because half the time the owner remembers a word from the answer.
     */
    fun search(questions: List<Question>, typed: String): List<Question> {
        val needle = typed.trim().lowercase()
        if (needle.isEmpty()) return questions
        return questions.filter {
            "${it.q} ${it.a} ${it.where}".lowercase().contains(needle)
        }
    }

    /** What a step writes back to the PC. */
    fun progressBody(id: String, at: Int, state: String = "in_progress"): JsonObject =
        JsonObject(
            mapOf(
                "id" to JsonPrimitive(id),
                "state" to JsonPrimitive(state),
                "step" to JsonPrimitive(at),
            )
        )

    /**
     * The PC's answer as the screen's own state. A 404 or a 501 is not a
     * failure to shout about: it is an older backend, and the screen says so in
     * words (UPDATE) instead of showing a status number.
     */
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
            // The plain words both apps use (PlainErrors): what happened, then
            // what to do - never the raw error or a status number.
            else -> Read.Failed(PlainErrors.forApiError(e).text)
        }
    }

    /** The line under the panel, or null when the catalogue says it all. */
    fun readLine(read: Read): String? = when (read) {
        Read.NotAsked -> null
        Read.Loading -> "Asking your PC…"
        is Read.Loaded -> null
        Read.OlderBackend -> UPDATE
        is Read.Failed -> read.reason
    }
}
