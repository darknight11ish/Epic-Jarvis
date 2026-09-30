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

    // Steps that wait on other steps, and follow a number (docs/JARVIS-API.md
    // section 101; docs/GOALS-PROGRESS-DESIGN.md "Slice contract (frozen)").
    const val DO_FIRST = "Do these first"
    const val FOLLOWS = "Follows a number"
    const val FOLLOWS_LABEL = "Follows"
    const val UNDO = "Undo"
    /** Shown when a tick is taken back while the private lists are hidden (no step words then). */
    const val TICKED_GENERIC = "Ticked a step."

    /** The PC's own limit on what one step can wait on (`limits.needs`). */
    const val MAX_NEEDS = 3

    /** The step ids the PC hands out (`goal_limits.step_ids`). */
    val STEP_IDS: List<String> = (1..9).map { "s$it" }

    /**
     * The lock sentences, word for word (`jarvis_goals.WORDS`, the contract's
     * `goal_words`). The PC fills the `{...}` in and sends the finished
     * sentence (`lock_words`, `reached_words`, `error`), so this app shows
     * those as sent and needs only [w]("locked") and [w]("measure_gone").
     * Some keys (`follows_*`, `needs_*`, `reached_tag`, `ticked`, `unticked`) are
     * the screens' own sentences: the PC never sends them, and
     * tools/gen_projects_cases.py adds them to `goal_words` so both apps say
     * them word for word.
     */
    val WORDS: Map<String, String> = mapOf(
        "after" to "after: {steps}",
        "after_open_again" to "after: {steps} (open again)",
        "circle" to "These steps wait on each other in a circle: {steps}.",
        "follows_empty" to "No number with a target yet. Set a target on a benchmark in Projects first.",
        "follows_none" to "No number",
        "follows_under" to
            "The step shows \"reached\" when that number reaches its target. You still tick it yourself.",
        "locked" to "locked",
        "locked_refusal" to "Do \"{step}\" first, or tick it if it is already done.",
        "measure_gone" to "The number this step follows is gone - tick it by hand.",
        "needs_cleaned" to "Removed \"{step}\" - the steps that waited on it no longer do.",
        "needs_limit" to "At most {max} steps can come first.",
        "needs_none" to "Nothing - this step can start now",
        "needs_under" to "This step stays locked until the ones you pick are done. Pick up to 3.",
        "no_such_benchmark" to "\"{step}\" follows a number that does not exist any more.",
        "no_target" to "\"{step}\" follows \"{name}\", which has no target yet - set one first.",
        "reached" to "The number reached its target: {latest} (target {target}).",
        "reached_tag" to "number reached",
        "reached_tick" to "{step}: the number reached its target - tick it when you are ready.",
        "self_wait" to "\"{step}\" cannot wait on itself.",
        "ticked" to "Ticked \"{step}\".",
        "too_many_needs" to "\"{step}\" can wait on at most 3 other steps.",
        "unknown_wait" to "\"{step}\" waits on a step that is not in this plan.",
        "unticked" to "Unticked \"{step}\".",
        "waiting_on" to "Waiting on \"{step}\".",
    )

    /** One of [WORDS], with its `{step}` and `{max}` filled in when given. */
    fun w(key: String, step: String? = null, max: Int? = null): String {
        var out = WORDS.getValue(key)
        if (step != null) out = out.replace("{step}", step)
        if (max != null) out = out.replace("{max}", max.toString())
        return out
    }

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

    /** The benchmark a step follows (`measure`): both ids, 32 hex digits each. */
    data class Measure(val project: String, val bench: String)

    /**
     * One step. The first three fields are the owner's own words and tick;
     * the rest are what the PC stores ([id], [doneAt], [needs], [measure])
     * and what it computes and sends ([state] and below - never worked out
     * here, and never sent back). Every extra field has a default, so an
     * older PC's plain `{step, by, done}` still reads.
     */
    data class Step(
        val step: String,
        val by: String,
        val done: Boolean,
        val id: String = "",
        val doneAt: Double? = null,
        val needs: List<String> = emptyList(),
        val measure: Measure? = null,
        /** "open", "locked", "met_by_number" or "done"; "" from an older PC. */
        val state: String = "",
        val waitingOn: List<String> = emptyList(),
        val lockWords: String = "",
        val reached: Boolean = false,
        val reachedWords: String = "",
        val measureName: String = "",
        val measureGone: Boolean = false,
        val measureSensitive: Boolean = false,
    ) {
        /** Waiting for another step, as the PC says. */
        val locked: Boolean get() = state == "locked"

        /** Met, as the PC says: ticked, or its number reached the target. */
        val met: Boolean get() = state == "done" || state == "met_by_number"
    }

    /** A benchmark a step could follow: it has a target and a better-direction. */
    data class MeasureOption(val measure: Measure, val label: String)

    data class Goal(
        val id: String,
        val text: String,
        val plan: List<Step>,
        val status: String,
        val created: Double?,
        val changed: Double?,
    )

    data class Limits(val text: Int, val steps: Int, val goals: Int, val by: Int, val needs: Int = MAX_NEEDS)

    data class View(val goals: List<Goal>, val limits: Limits?)

    /** `POST /api/goals/<id>/accept`'s own answer: the goal, kept, and its freshly-raised check-in job. */
    data class Accepted(val goal: Goal, val checkin: Schedule.Job?)

    private val ID = Regex("g[0-9a-f]{10}")

    /** A goal id as the PC makes them. */
    fun validId(id: String?): Boolean = id != null && ID.matches(id)

    private val STEP_ID = Regex("s[0-9]")
    private val HEX32 = Regex("[0-9a-f]{32}")

    private fun ids(a: Any?): List<String> =
        (a as? JsonArray)?.mapNotNull { el ->
            (el as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { STEP_ID.matches(it) }
        }.orEmpty()

    private fun measure(o: JsonObject?): Measure? {
        if (o == null) return null
        val project = o.raw("project") ?: return null
        val bench = o.raw("bench") ?: return null
        return if (HEX32.matches(project) && HEX32.matches(bench)) Measure(project, bench) else null
    }

    private fun step(o: JsonObject): Step? {
        val text = o.text("step") ?: return null
        return Step(
            step = text,
            by = o.text("by") ?: "",
            done = o.flag("done") == true,
            id = o.raw("id")?.takeIf { STEP_ID.matches(it) } ?: "",
            doneAt = o.num("done_at"),
            needs = ids(o["needs"]),
            measure = measure(o["measure"] as? JsonObject),
            state = o.raw("state") ?: "",
            waitingOn = ids(o["waiting_on"]),
            lockWords = o.raw("lock_words") ?: "",
            reached = o.flag("reached") == true,
            reachedWords = o.raw("reached_words") ?: "",
            measureName = o.raw("measure_name") ?: "",
            measureGone = o.flag("measure_gone") == true,
            measureSensitive = o.flag("measure_sensitive") == true,
        )
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
            val needs = l.num("needs")?.toInt() ?: MAX_NEEDS
            if (text != null && steps != null && goalsMax != null && by != null) {
                Limits(text, steps, goalsMax, by, needs)
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
                    // ONLY the stored fields. done_at and everything the PC
                    // computes (state, lock_words ...) are never sent back;
                    // a new step has no id yet.
                    if (s.id.isNotEmpty()) put("id", s.id)
                    put("step", s.step.trim())
                    put("by", s.by.trim())
                    put("done", s.done)
                    put("needs", buildJsonArray { s.needs.forEach { add(JsonPrimitive(it)) } })
                    put(
                        "measure",
                        s.measure?.let { m ->
                            buildJsonObject {
                                put("project", m.project)
                                put("bench", m.bench)
                            }
                        } ?: JsonNull,
                    )
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

    /**
     * The body of `.../step`: one step, marked done or not. By the step's id
     * when the PC gave it one (it stays put when steps move), else by
     * position - an older PC's plan has no ids.
     */
    fun stepBody(stepId: String, index: Int, done: Boolean): String = buildJsonObject {
        if (stepId.isNotEmpty()) put("id", stepId) else put("index", index)
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
            // A tick on a step that is still waiting (a stale screen): the
            // PC's sentence, as sent - 'Do "Get quotes" first, or tick it ...'.
            reply.code == 409 && reply.body?.flag("locked") == true && error != null -> error
            reply.code == 404 && error == "no such goal" -> gone
            reply.code == 404 || reply.code == 501 -> TOO_OLD
            reply.code == 503 -> NOT_AVAILABLE
            // The PC's own sentence, as sent - no prefix, no rewording (same as the desktop).
            reply.code == 409 || reply.code == 400 -> error ?: "Not changed. Your PC said no, without a reason."
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
        goals = v.goals.map { g ->
            g.copy(
                text = HIDDEN_TEXT,
                plan = g.plan.map { s ->
                    // lock_words repeat other steps' own words, and a followed number's
                    // name and value are the owner's own: all three go for EVERY step,
                    // exactly as the desktop does (goals.rs redact_goals), not only
                    // for a health or money number. The state stays: it is not a word,
                    // and it still drives the UI blind.
                    s.copy(step = "", by = "", lockWords = "", reachedWords = "", measureName = "")
                },
            )
        },
    )

    // ------------------------------------------------- the draft editor ----

    /** A step's own words for lists in the editor: its text, or "Step N" while still empty. */
    fun label(plan: List<Step>, index: Int): String =
        plan.getOrNull(index)?.step?.trim()?.takeIf { it.isNotEmpty() }?.let { if (it.length > 40) it.take(40) + "…" else it }
            ?: "Step ${index + 1}"

    /** A new, empty step with a free id from the PC's own s1..s9. */
    fun newStep(plan: List<Step>): Step {
        val taken = plan.map { it.id }.toSet()
        return Step("", "", false, id = STEP_IDS.firstOrNull { it !in taken } ?: "")
    }

    /**
     * The plan without step [index], and that step's id taken out of every
     * other step's `needs` - the PC does not clean that for the app. Second
     * value: whether any other step was changed by that (so the screen can say so).
     */
    fun removeStep(plan: List<Step>, index: Int): Pair<List<Step>, Boolean> {
        val gone = plan.getOrNull(index) ?: return plan to false
        var touched = false
        val rest = plan.filterIndexed { i, _ -> i != index }.map { s ->
            if (gone.id.isNotEmpty() && gone.id in s.needs) {
                touched = true
                s.copy(needs = s.needs.filter { it != gone.id })
            } else {
                s
            }
        }
        return rest to touched
    }

    /**
     * Picks or drops [otherId] in step [index]'s "Do these first". A fourth
     * is not added (the picker stops at [maxNeeds]; the PC would refuse it
     * with its own sentence); a step never waits on itself.
     */
    fun toggleNeed(plan: List<Step>, index: Int, otherId: String, maxNeeds: Int = MAX_NEEDS): List<Step> {
        val s = plan.getOrNull(index) ?: return plan
        if (otherId.isEmpty() || otherId == s.id) return plan
        val next = when {
            otherId in s.needs -> s.needs.filter { it != otherId }
            s.needs.size >= maxNeeds -> return plan
            else -> s.needs + otherId
        }
        return plan.mapIndexed { i, it -> if (i == index) it.copy(needs = next) else it }
    }

    /** Sets (or, with null, clears) the number step [index] follows. */
    fun setMeasure(plan: List<Step>, index: Int, measure: Measure?): List<Step> =
        plan.mapIndexed { i, it -> if (i == index) it.copy(measure = measure) else it }

    /**
     * The benchmarks a step could follow, from the projects as read: a
     * number (not a command) with a target and a better-direction. The
     * label is "project: benchmark".
     */
    fun measureOptions(projects: List<Projects.Project>): List<MeasureOption> =
        projects.flatMap { p ->
            p.benchList
                .filter { it.kind == "number" && it.target != null && it.better != null }
                .map { b -> MeasureOption(Measure(p.id, b.id), "${p.name}: ${b.name}") }
        }.filter { HEX32.matches(it.measure.project) && HEX32.matches(it.measure.bench) }

    // ------------------------------------------------------- the rows ----

    /**
     * What a screen reader hears for a row: "<step>, locked, after: <steps>",
     * then the reached line and what it follows. [shownStep] is the step's
     * words, or the hidden stand-in.
     */
    fun spoken(s: Step, shownStep: String): String = buildList {
        add(shownStep)
        if (s.locked) {
            add(w("locked"))
            if (s.lockWords.isNotEmpty()) add(s.lockWords)
        } else if (s.lockWords.isNotEmpty()) {
            add(s.lockWords)
        }
        if (s.reached && s.reachedWords.isNotEmpty()) add(s.reachedWords)
        if (s.measureGone) add(w("measure_gone"))
    }.joinToString(", ")

    /** Whether the tick control is usable: never for a locked step (the PC would answer 409). */
    fun canTick(s: Step): Boolean = !s.locked || s.done

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

    /** A string exactly as sent (no trimming), or null when it is absent or not a string. */
    private fun JsonObject.raw(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
