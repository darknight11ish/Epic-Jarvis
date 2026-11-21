package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * The plan store's read, the phone's ready list, and its two writes - PM4, the
 * phone half (2026-11-21; docs/PROJECTS-DESIGN.md's PM4 note,
 * docs/JARVIS-API.md section 88.10).
 *
 * The screen is the concise one the owner approved: a clean Projects list, the
 * **Next 3 ready tasks**, a tap to mark one Done, and a Quick Add box. It is
 * deliberately NOT a Kanban board - no columns, no dragging, no cards here.
 *
 * **Three things this file never does, and why they are the rule:**
 *  - It never decides "ready". The PC's own `ready_next()` decides, and the
 *    plan read sends its answer in the store's order. This file only caps the
 *    SCREEN at [READY_CAP] items - the same cap the PC's deterministic
 *    "what should I work on next" answer keeps (`jarvis_quick._MAX_NEXT_ITEMS`),
 *    so the screen and the voice answer can never disagree about how long the
 *    list is.
 *  - It never invents a date. [addBody] sends exactly the owner's typed words
 *    as `title`, and nothing else; a task with no date stays undated on the PC.
 *  - It never speaks for the PC's permissions. There is no card-raised answer
 *    here and no action that asks first: marking your own task done and writing
 *    your own task down are the owner's own taps on their own rows, exactly
 *    like ticking a to-do. The two write paths are the PC's existing doors -
 *    `set_work_item_status` (with its normal receipt/Undo) and
 *    `add_work_item`; no second route was invented for either.
 *
 * What it reads is `GET /api/projects/<id>/plan` (one project per read - the
 * phone opens a plan for each project it lists, so the id and the project's
 * name come from the list it already has). [readyTasks] then merges each
 * project's ready ids across the projects; the store's own three order keys
 * (priority, then due date, then written order) are in every item, so the merge
 * is the store's order rather than a second idea of it.
 *
 * **The Done tap asks once when a link is still live (the external review's
 * ruling 5.7, 2026-11-21).** The plan read carries each item's linked PR state,
 * and PM3's own projection of a linked durable job onto the item's `status`
 * (`TASK_STATE_TO_WORK`: running/queued is `in_progress`, waiting on the owner
 * is `waiting_approval`, a finished job is `in_review`). A PR the PC read as
 * still open, or a link the store's own projection still shows as running or
 * waiting, must not be silently marked done and must not be hard-blocked
 * either: the tap shows ONE confirmation naming what is still live, and its
 * "Mark done anyway" goes through the SAME one status path with the same
 * receipt/Undo. "Cancel" sends nothing and changes nothing. There is no second
 * route, no new card class and no invented state: a link whose state the PC has
 * not read yet (a PR number with no `linked_pr_state`, a job whose projection
 * has not run) never asks, a merged or closed PR never asks, and an item with
 * no links taps through exactly as it did before.
 *
 * Pure Kotlin, no Android types, so [com.jarvis.client.ProjectPlanTest] and
 * [com.jarvis.client.ProjectDoneWarningTest] run it on a plain JVM. The words
 * are the shared contract's `plan_words` (`contract/projects-cases.json`, made
 * by tools/gen_projects_cases.py), so the two cannot drift.
 */
object ProjectPlan {

    /** The phone's presentation cap. A RULE, not a layout choice: see the class doc. */
    const val READY_CAP = 3

    /** One project's plan read. The id and the name come from the list read. */
    data class Plan(
        val projectId: String,
        val projectName: String,
        val objective: String?,
        val successCriteria: String?,
        val status: String?,
        val targetDate: String?,
        val linkedRepo: String?,
        val linkedNotePath: String?,
        val slug: String?,
        val counts: Counts,
        val milestones: List<Milestone>,
        val items: List<Item>,
        /** Ready item ids, in the store's own `ready_next` order for this project. */
        val ready: List<String>,
        /** The newest events first, bounded by the PC. */
        val events: List<Event>,
    ) {
        fun item(id: String): Item? = items.firstOrNull { it.id == id }
    }

    data class Counts(
        val milestones: Int,
        val workItems: Int,
        val ready: Int,
        val blocked: Int,
        val edges: Int,
        val events: Int,
    )

    data class Milestone(
        val id: String,
        val title: String,
        val status: String,
        val dueDate: String?,
        val position: Int,
        val workItems: Int,
        val done: Int,
    )

    /**
     * One stored work item, as the PC sent it. [dueDate] is null exactly when
     * the store holds no date - the phone never fills one in. [priority] is
     * null when the owner set none (the store sorts those last).
     */
    data class Item(
        val id: String,
        val project: String,
        val projectName: String,
        val milestone: String?,
        val title: String,
        val detail: String,
        val status: String,
        val priority: Int?,
        val dueDate: String?,
        val created: Double,
        val changed: Double,
        val blockedByIds: List<String>,
        val ready: Boolean,
        val executor: String,
        val linkedTaskId: String?,
        val linkedPrNumber: Int?,
        val linkedPrState: String,
        val linkedCiStatus: String,
    )

    data class Event(val id: String, val at: Double, val kind: String, val subject: String)

    /** One ready task, ready to draw or say: the item, its project, and its id. */
    data class Task(val id: String, val projectId: String, val projectName: String, val item: Item) {
        val title: String get() = item.title
        val priority: Int? get() = item.priority
        val dueDate: String? get() = item.dueDate
        val created: Double get() = item.created
    }

    // ------------------------------------------------------------ words -----

    /** The phone's own words (the contract's `plan_words`), word for word. */
    val WORDS: Map<String, String> = mapOf(
        "ready_title" to "Next 3 ready tasks",
        "ready_under" to "Up to 3 you can start now, across your projects.",
        "ready_empty" to "Nothing is ready to work on right now.",
        "ready_more" to "And {n} more ready on your PC.",
        "ready_missing" to "Your PC's Jarvis does not have the project plan read yet - " +
            "run apply-patches.ps1 on the PC.",
        "ready_unreadable" to "Couldn't read what's ready: {why}",
        "done" to "Done",
        "done_said" to "Marked done.",
        "done_row" to "Mark {title} in {project} done",
        // The one-tap warning before a Done tap when the plan read still shows a
        // live link (ruling 5.7): the words for one PR, one job, both, and the
        // two buttons. "Mark done anyway" IS the confirmation - one tap, then the
        // existing status path; "Cancel" sends nothing.
        "done_warning_pr" to "Linked PR #{n} is still open",
        "done_warning_job" to "The linked job is still running",
        "done_warning_job_waiting" to "The linked job is still waiting on you",
        "done_warning_both" to "Linked PR #{n} is still open, and the linked job is still running",
        "done_warning_both_waiting" to
            "Linked PR #{n} is still open, and the linked job is still waiting on you",
        "done_warning_ask" to "{why} - mark done anyway?",
        "done_anyway" to "Mark done anyway",
        "done_cancel" to "Cancel",
        "quick_title" to "Quick add a task",
        "quick_placeholder" to "The task, in your words",
        "quick_under" to "It is saved exactly as you type it, with no date added.",
        "quick_to" to "Add to: {name}",
        "quick_add" to "Add",
        "quick_said" to "Added.",
        "quick_blank" to "Type the task first.",
        "speech_ready" to "Ready now: {items}.",
        "speech_item" to "{title} in {project}",
        "speech_none" to "Nothing is ready to work on right now.",
        "speech_more" to " And {n} more.",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    /** `{title}` and friends filled in. */
    fun fill(template: String, vararg values: Pair<String, Any>): String {
        var out = template
        for ((k, v) in values) out = out.replace("{$k}", v.toString())
        return out
    }

    // ------------------------------------------------------------ reading ---

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject.whole(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject.number(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() }

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    private fun JsonObject.array(key: String): JsonArray? = this[key] as? JsonArray

    private fun date(o: JsonObject, key: String): String? =
        o.text(key)?.takeIf { it.isNotBlank() }

    /**
     * The PC's sentence for a failed plan read: its own `error` when it sent
     * one, else the status. Never a made-up cause.
     */
    fun readError(reply: Projects.Reply): String =
        reply.body?.text("error")?.trim()?.takeIf { it.isNotEmpty() }
            ?: "Your PC could not answer that read. Nothing was changed."

    /**
     * One plan read, or null when the body is not a plan answer at all (a PC
     * without the route answers 404/501, handled by [Projects.isMissing] where
     * the read is made). Missing keys read with honest defaults and never make
     * an item up: a list needs an id, and a body without `counts` is not a plan.
     */
    fun parse(projectId: String, projectName: String, body: JsonObject?): Plan? {
        if (body == null) return null
        if ((body["ok"] as? JsonPrimitive)?.booleanOrNull == false) return null
        val countsRaw = body.obj("counts") ?: return null
        val counts = Counts(
            milestones = countsRaw.whole("milestones") ?: 0,
            workItems = countsRaw.whole("work_items") ?: 0,
            ready = countsRaw.whole("ready") ?: 0,
            blocked = countsRaw.whole("blocked") ?: 0,
            edges = countsRaw.whole("edges") ?: 0,
            events = countsRaw.whole("events") ?: 0,
        )
        val milestones = body.array("milestones").orEmpty().mapNotNull { el ->
            val m = el as? JsonObject ?: return@mapNotNull null
            val id = m.text("id")?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val mc = m.obj("counts")
            Milestone(
                id = id,
                title = m.text("title").orEmpty(),
                status = m.text("status").orEmpty(),
                dueDate = date(m, "due_date"),
                position = m.whole("position") ?: 0,
                workItems = mc?.whole("work_items") ?: 0,
                done = mc?.whole("done") ?: 0,
            )
        }
        val items = body.array("work_items").orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.text("id")?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val blocked = o.array("blocked_by").orEmpty().mapNotNull { b ->
                (b as? JsonObject)?.text("id")?.takeIf { it.isNotBlank() }
            }
            Item(
                id = id,
                project = o.text("project") ?: projectId,
                projectName = o.text("project_name")?.takeIf { it.isNotBlank() } ?: projectName,
                milestone = o.text("milestone")?.takeIf { it.isNotBlank() },
                title = o.text("title").orEmpty(),
                detail = o.text("detail").orEmpty(),
                status = o.text("status").orEmpty(),
                priority = o.whole("priority"),
                dueDate = date(o, "due_date"),
                created = o.number("created") ?: 0.0,
                changed = o.number("changed") ?: 0.0,
                blockedByIds = blocked,
                ready = o.flag("ready"),
                executor = o.text("executor")?.takeIf { it.isNotBlank() } ?: "owner",
                linkedTaskId = o.text("linked_task_id")?.takeIf { it.isNotBlank() },
                linkedPrNumber = o.whole("linked_pr_number"),
                linkedPrState = o.text("linked_pr_state").orEmpty(),
                linkedCiStatus = o.text("linked_ci_status").orEmpty(),
            )
        }
        val ready = body.array("ready").orEmpty().mapNotNull { el ->
            (el as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }
        }
        val events = body.array("events").orEmpty().mapNotNull { el ->
            val e = el as? JsonObject ?: return@mapNotNull null
            val id = e.text("id")?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            Event(
                id = id,
                at = e.number("at") ?: 0.0,
                kind = e.text("kind").orEmpty(),
                subject = e.text("subject").orEmpty(),
            )
        }
        return Plan(
            projectId = projectId,
            projectName = projectName,
            objective = body.text("objective")?.takeIf { it.isNotBlank() },
            successCriteria = body.text("success_criteria")?.takeIf { it.isNotBlank() },
            status = body.text("status")?.takeIf { it.isNotBlank() },
            targetDate = date(body, "target_date"),
            linkedRepo = body.text("linked_repo")?.takeIf { it.isNotBlank() },
            linkedNotePath = body.text("linked_note_path")?.takeIf { it.isNotBlank() },
            slug = body.text("slug")?.takeIf { it.isNotBlank() },
            counts = counts,
            milestones = milestones,
            items = items,
            ready = ready,
            events = events,
        )
    }

    // ------------------------------------------------------------ the order --

    /**
     * The store's own ready order: priority (lower first, none last), then due
     * date (earlier first, none last), then when it was written, then its id -
     * exactly `jarvis_projects._READY_ORDER`. Each plan's `ready` list is
     * already in this order for its own project; merging projects needs the
     * keys, which every item carries.
     */
    private fun compareStoreOrder(a: Task, b: Task): Int {
        val pa = a.priority
        val pb = b.priority
        if (pa != pb) {
            if (pa == null) return 1
            if (pb == null) return -1
            return pa.compareTo(pb)
        }
        val da = a.dueDate
        val db = b.dueDate
        if (da != db) {
            if (da == null) return 1
            if (db == null) return -1
            return da.compareTo(db)
        }
        if (a.created != b.created) return a.created.compareTo(b.created)
        return a.id.compareTo(b.id)
    }

    /**
     * The ready tasks across [plans], in the store's order, capped at [cap]
     * ([READY_CAP] on the screen). Only ids the PC listed as ready are used, so
     * a blocked item can never be shown as ready even if another read is old.
     */
    fun readyTasks(plans: Collection<Plan>, cap: Int = READY_CAP): List<Task> {
        val limit = cap.coerceAtLeast(0)
        if (limit == 0) return emptyList()
        val byId = HashMap<String, Plan>()
        val seen = LinkedHashSet<String>()
        for (plan in plans) {
            for (i in plan.items) byId[i.id] = plan
            for (id in plan.ready) seen.add(id)
        }
        val all = seen.mapNotNull { id ->
            val plan = byId[id] ?: return@mapNotNull null
            val item = plan.item(id) ?: return@mapNotNull null
            if (!item.ready) return@mapNotNull null
            Task(id, plan.projectId, plan.projectName, item)
        }.sortedWith(Comparator { a, b -> compareStoreOrder(a, b) })
        return all.take(limit)
    }

    /** The TRUE number of ready tasks on the PC (each read's own total), so "and N more" is honest. */
    fun totalReady(plans: Collection<Plan>): Int = plans.sumOf { it.counts.ready }

    /**
     * What the phone says when this readout is spoken (TalkBack here, and the
     * same words the voice answer uses): at most [READY_CAP] items, never the
     * whole list, and it says how many more there are on the PC. Nothing ready
     * is its own honest sentence.
     */
    fun spoken(tasks: List<Task>, total: Int = tasks.size): String {
        val shown = tasks.take(READY_CAP)
        if (shown.isEmpty()) return w("speech_none")
        val items = shown.joinToString(", ") {
            fill(w("speech_item"), "title" to it.title, "project" to it.projectName)
        }
        val base = fill(w("speech_ready"), "items" to items)
        val more = (total - shown.size).coerceAtLeast(0)
        return if (more > 0) base + fill(w("speech_more"), "n" to more) else base
    }

    // ------------------------------------------------------------ routes ----

    /** `GET /api/projects/<id>/plan`, or null for an id that is not one. */
    fun planPath(pid: String): String? =
        if (Projects.isId(pid)) "/api/projects/$pid/plan" else null

    /** `POST /api/projects/<id>/work_items` - one task, the owner's own words. */
    fun addPath(pid: String): String? =
        if (Projects.isId(pid)) "/api/projects/$pid/work_items" else null

    /** `POST /api/projects/<id>/work_items/<wid>/status` - ONE status change. */
    fun statusPath(pid: String, wid: String): String? =
        if (Projects.isId(pid) && Projects.isId(wid)) "/api/projects/$pid/work_items/$wid/status" else null

    /** The one status change this screen makes: done, through the existing path. */
    fun statusBody(): String = "{\"status\":\"done\"}"

    /**
     * Quick Add's body: the owner's typed words as `title` and NOTHING else -
     * no date, no status, no priority. Null for blank words: nothing is sent.
     */
    fun addBody(words: String): String? {
        val title = words.trim()
        if (title.isEmpty()) return null
        return buildJsonObject { put("title", title) }.toString()
    }

    /** One request: a projects route and the JSON body to POST. */
    data class Request(val path: String, val body: String)

    /** The tap on Done: ONE POST through the store's existing status path. */
    fun doneRequest(pid: String, wid: String): Request? =
        statusPath(pid, wid)?.let { Request(it, statusBody()) }

    // ------------------------------- the Done warning (ruling 5.7, 2026-11-21) --

    /**
     * The one confirmation a Done tap must show first, in the phone's own
     * words: [message] is the warning (the PR number and/or the linked job,
     * then the question), and [confirm] and [cancel] are its two buttons.
     */
    data class DoneWarning(val message: String, val confirm: String, val cancel: String)

    /**
     * What one tap on Done does. [Send] is the tap that goes through at once -
     * the state an unlinked or settled item is in. [Ask] is the same ONE
     * request held back until the owner taps "Mark done anyway": until then
     * nothing has been sent, and [Ask.request] is exactly what the confirm
     * sends (there is no second request builder and no second route).
     */
    sealed class DoneStep {
        data class Send(val request: Request) : DoneStep()
        data class Ask(val warning: DoneWarning, val request: Request) : DoneStep()
    }

    /**
     * The linked PR the plan read still shows open, or null.
     *
     * The read's `linked_pr_state` is the PC's own projection (`PR_STATES` in
     * the store: open, merged, closed). A blank state means the PC has not read
     * that PR yet, so there is no state to warn about; merged and closed are
     * settled. Anything else the PC sends is treated as still open - the
     * ruling's own "not merged/closed" - because warning is the safe direction.
     */
    private fun openLinkedPr(item: Item): Int? {
        val number = item.linkedPrNumber ?: return null
        val state = item.linkedPrState.trim().lowercase()
        if (state.isEmpty() || state == "merged" || state == "closed") return null
        return number
    }

    /**
     * The linked durable job the store's own projection still shows running or
     * waiting, as the word that names it - null when no link is live.
     *
     * The plan read carries a JOB's state only as the status PM3 projects onto
     * the work item (`jarvis_projects.TASK_STATE_TO_WORK`): a queued or running
     * job is `in_progress`, a job waiting on the owner is `waiting_approval`,
     * and a finished job is `in_review`. That projection is the whole reading:
     * no job state is guessed from an id, and a status the projection does not
     * name (backlog, ready, in_review, done, cancelled) never warns.
     */
    private fun liveLinkedJob(item: Item): String? {
        if (item.linkedTaskId == null) return null
        return when (item.status) {
            "in_progress" -> "running"
            "waiting_approval" -> "waiting"
            else -> null
        }
    }

    /**
     * The ONE warning a Done tap must show first, or null when it can go
     * straight through (nothing linked is live, or the link's state was never
     * read - a missing link state never blocks and never warns).
     *
     * The message names the PR by number and/or names the linked job, then asks
     * the one question: "... - mark done anyway?". The warning is not a card and
     * writes nothing: only the owner's tap on its confirm button sends anything.
     */
    fun doneWarning(item: Item): DoneWarning? {
        val pr = openLinkedPr(item)
        val job = liveLinkedJob(item)
        if (pr == null && job == null) return null
        val why = when {
            pr != null && job == "waiting" -> fill(w("done_warning_both_waiting"), "n" to pr)
            pr != null && job == "running" -> fill(w("done_warning_both"), "n" to pr)
            pr != null -> fill(w("done_warning_pr"), "n" to pr)
            job == "waiting" -> w("done_warning_job_waiting")
            else -> w("done_warning_job")
        }
        return DoneWarning(
            message = fill(w("done_warning_ask"), "why" to why),
            confirm = w("done_anyway"),
            cancel = w("done_cancel"),
        )
    }

    /**
     * One tap on Done: either the ONE status request now ([DoneStep.Send]), or
     * the same request held behind one confirmation ([DoneStep.Ask]). Null when
     * there is no valid id to send to - nothing is invented.
     *
     * The tap is the whole check: it reads only the plan read this screen
     * already has, and it sends nothing, blocks nothing and invents no state.
     */
    fun doneStep(pid: String, item: Item): DoneStep? {
        val request = doneRequest(pid, item.id) ?: return null
        val warning = doneWarning(item) ?: return DoneStep.Send(request)
        return DoneStep.Ask(warning, request)
    }

    /** Quick Add: ONE POST of the typed words. Null for blank words. */
    fun addRequest(pid: String, words: String): Request? =
        addPath(pid)?.let { path -> addBody(words)?.let { Request(path, it) } }
}
