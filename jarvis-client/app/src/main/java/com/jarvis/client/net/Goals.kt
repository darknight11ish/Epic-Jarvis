package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/**
 * "Goals: a plan the owner edits, one card per acting step" (the owner's
 * "build it now", 2026-09-27; docs/JARVIS-API.md section 59; backend
 * `jarvis_goals.py`).
 *
 * The owner says "insulate the garage before winter" and writes - or asks
 * Jarvis in an ordinary chat message to suggest, then pastes in - a short
 * plan: a few named steps, each with a rough date ("by"). Typing the goal's
 * own words is enough to create a draft ([createBody]): the PC fills in a
 * one-step placeholder if no plan is given yet, and creating one raises no
 * card - a draft is content, not action, exactly like an email draft. The
 * owner edits the plan and taps Accept ([acceptBody]), which keeps it and
 * starts a weekly, model-free check-in through the PC's ONE scheduler - the
 * SAME approval card mechanism a repeating reminder already raises
 * ([Schedule]) - approving nothing that acts. A plan can only be edited
 * (steps added, removed or reworded) before it is accepted: once a goal is
 * active, its plan is fixed and only [stepBody] (done or not) and
 * [PATH]/stop apply. Ticking a step done and stopping a goal need no card
 * and are immediate, like a to-do item.
 *
 * NOTHING HERE EVER ACTS. When a step needs real action (search for
 * installers, draft an email), the owner asks Jarvis in ordinary chat, and
 * THAT goes through the exact same per-action approval card any chat turn
 * already uses - this module adds no new way to act, and no new gate logic.
 *
 * THE CHECK-IN'S OWN "WAITING" STATE, AND WHY IT ALSO SHOWS IN COMING UP.
 * `POST /api/goals/<id>/accept`'s own answer carries the freshly-raised
 * card's job view, `checkin` ([Accepted], read with the very same
 * [Schedule.job] parser "Coming up" uses) - `"state": "waiting"` until the
 * owner answers the card. No OTHER read of a goal carries it: the PC's own
 * store keeps the scheduler job's id internally but never hands it out
 * again (`backend/jarvis_goals.py`'s `_view()` has no `checkin_job` field),
 * so once this screen's own copy of that one answer is gone - the app
 * restarted, or the owner never saw it - there is no way to ask the Goals
 * routes whether that card is still waiting. The check-in's scheduler kind
 * ("goal_checkin") is left `owner_listed=True` (the backend's own default)
 * rather than hidden from "Coming up", and that is kept exactly as
 * shipped, on purpose: it is the ONLY place left where that state can still
 * be read, at any time, the same way a reminder's or the morning
 * briefing's own waiting card already shows there. Hiding it would trade a
 * real, working answer for a duplicate-looking row. [Schedule.actionsOf]
 * still gives that row NO buttons of its own: pausing or deleting a
 * check-in job directly from "Coming up" would leave the goal itself
 * `active` with no way to bring the check-in back (there is no route that
 * re-creates one for an existing goal) - `stop()` is the one control that
 * takes both down together, and it lives on the goal, not on the row.
 *
 * `GoalsSection` (ui/screens/GoalsPlate.kt) shows the "waiting" banner right
 * after Accept is tapped, from that one answer, and re-checks that ONE job
 * (`GET /api/schedule?id=`, [JarvisRuntime.scheduleJob]) whenever the
 * approval queue changes, so the banner clears itself once the card is
 * answered without needing a route of its own for it.
 *
 * Pure Kotlin, no Android types, so `GoalsTest` runs it on a plain JVM.
 */
object Goals {
    const val PATH = "/api/goals"

    /** The scheduler kind the weekly check-in registers as (`jarvis_goals.KIND`). */
    const val KIND = "goal_checkin"

    const val TITLE = "Goals"
    const val UNDER =
        "A plan you write and edit, kept on your PC. Accepting one sets up a weekly check-in straight " +
            "away, with no card - like a repeating reminder, it only ever reminds you and never " +
            "acts. Ticking a step done and Stop tracking need no card. When a step needs Jarvis " +
            "to actually do something, just ask in chat, as usual - that still asks first, every time."
    const val EMPTY = "No goals yet. Say what you want to get done below."

    const val NEW_HINT = "What do you want to get done? (\"insulate the garage before winter\")"
    const val START = "Start a goal"
    const val STARTING = "Starting…"

    const val STEP_HINT = "A step"
    const val BY_HINT = "Rough date (optional)"
    const val ADD_STEP = "Add step"
    const val REMOVE_STEP = "Remove"
    const val TOO_MANY_STEPS = "That is as many steps as a goal can have - drop one to add another."

    const val ACCEPT = "Accept"
    const val ACCEPTING = "Setting it up…"
    const val ACCEPT_DETAIL =
        "Sets up a weekly check-in on your PC, with no card, like a repeating reminder. It only " +
            "ever reminds you - it never acts."
    /** Only an older PC, from before check-ins stopped asking (2026-09-28), still says "waiting". */
    const val WAITING = "Waiting for your yes on the approval card."
    const val ALSO_IN_COMING_UP = "It also shows under Coming up, in case you leave this screen first."

    const val STOP = "Stop tracking"
    const val STOPPING = "Stopping…"

    const val DRAFT_TAG = "Draft"
    const val STOPPED_TAG = "Stopped"
    const val DONE_TAG = "Done"
    const val ALL_STEPS_DONE = "Every step is marked done."

    const val MISSING = "Your PC's Jarvis does not have Goals yet - run apply-patches.ps1 on the PC."
    const val TOO_OLD = "Not changed. Your PC's Jarvis does not have Goals yet - run apply-patches.ps1 on the PC."
    const val ALREADY_GONE = "That goal is not there any more."
    const val NOT_AVAILABLE = "Not changed. Jarvis's scheduler is not available on your PC right now."

    /** Stands in for words the private lists hide. */
    const val HIDDEN_TEXT = "(hidden)"

    /**
     * The PC's own numbers (`backend/jarvis_goals.py` MAX_TEXT / MAX_STEPS /
     * MAX_GOALS / MAX_BY) - also sent back in `GET /api/goals`'s own
     * `limits`, read by [parse], which is preferred over these once a read
     * has come back.
     */
    const val MAX_TEXT = 300
    const val MAX_STEPS = 7
    const val MAX_GOALS = 20
    const val MAX_BY = 40

    data class Step(val step: String, val by: String, val done: Boolean)

    data class Goal(
        val id: String,
        val text: String,
        val plan: List<Step>,
        val status: String,
        val created: Double?,
        val changed: Double?,
    )

    data class Limits(val text: Int, val steps: Int, val goals: Int, val by: Int)

    data class View(val goals: List<Goal>, val limits: Limits?)

    /** `POST /api/goals/<id>/accept`'s own answer: the goal, kept, and its freshly-raised check-in job. */
    data class Accepted(val goal: Goal, val checkin: Schedule.Job?)

    private val ID = Regex("g[0-9a-f]{10}")

    /** A goal id as the PC makes them. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    private fun step(o: JsonObject): Step? {
        val text = o.text("step") ?: return null
        return Step(text, o.text("by") ?: "", o.flag("done") == true)
    }

    private fun goal(o: JsonObject): Goal? {
        val id = o.text("id")?.takeIf { validId(it) } ?: return null
        val text = o.text("text") ?: return null
        val plan = (o["plan"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(::step) } ?: return null
        val status = o.text("status") ?: return null
        return Goal(id, text, plan, status, o.num("created"), o.num("changed"))
    }

    /**
     * `GET /api/goals`, read - or null when it is not the list (no `goals`
     * array). A goal without a valid id, its own words, or a plan is
     * dropped, never guessed.
     */
    fun parse(body: JsonObject): View? {
        val raw = body["goals"] as? JsonArray ?: return null
        val goals = raw.mapNotNull { (it as? JsonObject)?.let(::goal) }
        val limits = (body["limits"] as? JsonObject)?.let { l ->
            val text = l.num("text")?.toInt()
            val steps = l.num("steps")?.toInt()
            val goalsMax = l.num("goals")?.toInt()
            val by = l.num("by")?.toInt()
            if (text != null && steps != null && goalsMax != null && by != null) {
                Limits(text, steps, goalsMax, by)
            } else {
                null
            }
        }
        return View(goals, limits)
    }

    /** `GET /api/goals/<id>`, or any write's answer - the `goal` in it, or null. */
    fun parseOne(body: JsonObject): Goal? = (body["goal"] as? JsonObject)?.let(::goal)

    /**
     * `POST /api/goals/<id>/accept`'s own answer: the goal, plus its
     * freshly-raised check-in job read the same way [Schedule.job] reads any
     * other row of "Coming up" - or null.
     */
    fun parseAccepted(body: JsonObject): Accepted? {
        val g = body["goal"] as? JsonObject ?: return null
        val goalView = goal(g) ?: return null
        val checkin = (g["checkin"] as? JsonObject)?.let(Schedule::job)
        return Accepted(goalView, checkin)
    }

    /** A read that failed because this PC has no Goals: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    private fun planJson(plan: List<Step>): JsonArray = buildJsonArray {
        plan.forEach { s ->
            add(
                buildJsonObject {
                    put("step", s.step.trim())
                    put("by", s.by.trim())
                    put("done", s.done)
                },
            )
        }
    }

    /** The body of a new draft: the owner's own words, and their own plan once they have typed one. */
    fun createBody(text: String, plan: List<Step>? = null): String = buildJsonObject {
        put("text", text.trim())
        if (plan != null) put("plan", planJson(plan))
    }.toString()

    /** The body of `.../accept`: the owner's edited plan, or none to keep the draft exactly as it stood. */
    fun acceptBody(plan: List<Step>? = null): String = buildJsonObject {
        if (plan != null) put("plan", planJson(plan))
    }.toString()

    /** The body of `.../step`: one step, marked done or not. */
    fun stepBody(index: Int, done: Boolean): String = buildJsonObject {
        put("index", index)
        put("done", done)
    }.toString()

    /** `.../stop` takes no body; a plain empty object, like every other bodyless POST here. */
    const val STOP_BODY = "{}"

    /** Whether a goal's own words, or one step's, fit - the PC's own MAX_TEXT. */
    fun validText(text: String, limit: Int = MAX_TEXT): Boolean =
        text.trim().isNotEmpty() && text.trim().length <= limit

    /** Whether a rough date/label fits - the PC's own MAX_BY; empty is always fine. */
    fun validBy(by: String, limit: Int = MAX_BY): Boolean = by.trim().length <= limit

    /** Whether a plan is one the PC would accept: 1-[MAX_STEPS] steps, each with real, short words. */
    fun validPlan(plan: List<Step>, maxSteps: Int = MAX_STEPS): Boolean =
        plan.isNotEmpty() && plan.size <= maxSteps && plan.all { validText(it.step) && validBy(it.by) }

    /** What the PC answered a write, kept whole: the status and the JSON body, if any. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** The PC's own sentence, capitalised, or a plain fallback - the shape [MemoryShared.said] uses too. */
    private fun refusalSaid(reply: Reply, gone: String = ALREADY_GONE): String {
        val error = reply.body?.text("error")
        return when {
            reply.code == 404 && error == "no such goal" -> gone
            reply.code == 404 || reply.code == 501 -> TOO_OLD
            reply.code == 503 -> NOT_AVAILABLE
            reply.code == 409 || reply.code == 400 ->
                "Not changed. " + (error?.replaceFirstChar { it.uppercase() } ?: "Your PC said no, without a reason.")
            else -> "Not changed. Your PC answered ${reply.code}." + (error?.let { " $it" } ?: "")
        }
    }

    /** Creating a draft: whether it worked, the new goal if so, and the sentence to show. */
    fun createdSaid(reply: Reply): Triple<Boolean, Goal?, String> {
        if (reply.code in 200..299 && reply.body?.flag("ok") != false) {
            val g = reply.body?.let(::parseOne)
            return if (g != null) Triple(true, g, "Started as a draft - edit the plan below, then Accept.")
            else Triple(false, null, "Not started. Your PC sent something this phone could not read.")
        }
        return Triple(false, null, refusalSaid(reply, gone = "Not started. " + ALREADY_GONE))
    }

    /** Accepting: whether it worked, the accepted goal with its check-in if so, and the sentence. */
    fun acceptedSaid(reply: Reply): Triple<Boolean, Accepted?, String> {
        if (reply.code in 200..299 && reply.body?.flag("ok") != false) {
            val a = reply.body?.let(::parseAccepted)
            return if (a != null) {
                Triple(true, a, if (a.checkin?.state == "waiting") "Accepted. $WAITING" else "Accepted.")
            } else {
                Triple(false, null, "Not accepted. Your PC sent something this phone could not read.")
            }
        }
        return Triple(false, null, refusalSaid(reply))
    }

    /** Ticking a step, or stopping: whether it worked, the updated goal if so, and the sentence. */
    fun changedSaid(reply: Reply, doneWord: String = "Done."): Triple<Boolean, Goal?, String> {
        if (reply.code in 200..299 && reply.body?.flag("ok") != false) {
            val g = reply.body?.let(::parseOne)
            return if (g != null) Triple(true, g, doneWord)
            else Triple(false, null, "Not changed. Your PC sent something this phone could not read.")
        }
        return Triple(false, null, refusalSaid(reply))
    }

    /** The tag under a goal's own words: its status, in plain words. */
    fun statusTag(status: String): String = when (status) {
        "draft" -> DRAFT_TAG
        "stopped" -> STOPPED_TAG
        "done" -> DONE_TAG
        else -> ""
    }

    /** The list with every goal's own words replaced, for while the lists are hidden. */
    fun hide(v: View): View = v.copy(
        goals = v.goals.map { g -> g.copy(text = HIDDEN_TEXT, plan = g.plan.map { it.copy(step = "", by = "") }) },
    )

    /** The open goals (draft, active) first, newest first, as the PC already sends them; then the rest. */
    fun ordered(v: View?): List<Goal> {
        if (v == null) return emptyList()
        val (open, closed) = v.goals.partition { it.status == "draft" || it.status == "active" }
        return open + closed
    }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
