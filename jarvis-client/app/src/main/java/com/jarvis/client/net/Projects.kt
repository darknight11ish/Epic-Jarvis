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
import java.util.Locale
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * Projects - the owner's decision of 2026-09-28 ("Projects, like Claude's
 * Projects and more"), docs/PROJECTS-DESIGN.md build step 3, and
 * docs/JARVIS-API.md section 88 (`/api/projects` and its benchmarks).
 *
 * A project is one place for one thing the owner is working on: an app, or
 * "run a half marathon". It keeps "how Jarvis should work on this", a few
 * project notes, a Shareable switch (off by default), a work list (a named
 * list in Coming up) and benchmarks: numbers with dates, a chart, "better
 * or worse than last time", and a target.
 *
 * What asks first is the PC's to decide, never this app's: Shareable ON,
 * and taking off a private mark Jarvis made by itself ("5k time" read as
 * money), each raise ONE approval card. Everything else is the owner
 * writing down their own things - no card.
 *
 * On the phone, a coding project's folder and a benchmark's command are
 * shown but not changed: "Set on your PC" (the PC refuses them from any
 * other device, ARCHITECTURE section 8).
 *
 * The desktop says the same words (jarvis-desktop/src/projects.js); both
 * are checked against `contract/projects-cases.json`, made by
 * tools/gen_projects_cases.py from the real backend - its `words`, how a
 * number is written (`numbers`) and where a chart's top and bottom go
 * (`scales`).
 *
 * Pure Kotlin, no Android types, so `ProjectsTest` runs it on a plain JVM.
 */
object Projects {
    const val PATH = "/api/projects"

    /** The screens' own words, both apps, word for word (the contract's `words`). */
    val WORDS: Map<String, String> = mapOf(
        "title" to "Projects",
        "under" to "One place for each thing you are working on - an app, or a goal like a half marathon: how Jarvis should help, your notes, and numbers you track. Kept on your PC.",
        "new" to "New project",
        "name" to "Name",
        "kind_life" to "Life - numbers you track",
        "kind_coding" to "Coding - a folder on your PC",
        "create" to "Create",
        "coding_on_pc" to "A coding project's folder is chosen on your PC. Make coding projects there.",
        "set_on_pc" to "Set on your PC",
        "instructions" to "How Jarvis should work on this",
        "instructions_under" to "In your own words. Saved for later: Jarvis does not read this in chats yet.",
        "notes" to "Project notes",
        "notes_under" to "Short lines to keep in mind for this project, one per line.",
        "save" to "Save",
        "folder" to "Folder",
        "folder_none" to "No folder yet.",
        "folder_choose" to "Choose a folder…",
        "folder_clear" to "Clear",
        "folder_under" to "Only a folder on \"Folders Jarvis may look in\" (Settings), or one inside it.",
        "shareable" to "Shareable",
        "shareable_under" to "Off by default: nothing from this project is shared. Turning it on asks you with an approval card first; turning it off is instant.",
        "work_list" to "Work list",
        "work_list_none" to "No work list.",
        "work_list_under" to "A named list in Coming up. Add to it there, or say \"add ... to the {name}\".",
        "benchmarks" to "Benchmarks",
        "benchmarks_empty" to "No benchmarks yet. Add one to track a number over time.",
        "add_benchmark" to "Add a benchmark",
        "bench_name" to "What you measure",
        "bench_unit" to "Unit (optional)",
        "bench_better" to "Better is",
        "better_higher" to "Higher",
        "better_lower" to "Lower",
        "better_either" to "Don't say",
        "bench_target" to "Target (optional)",
        "add" to "Add",
        "log" to "Log",
        "log_value" to "A number",
        "private_label" to "private - not read aloud",
        "mark_private" to "Mark private",
        "remove_mark" to "Remove the private mark",
        "remove_mark_card" to "Jarvis marked this itself. Removing the mark asks you with an approval card first, because afterwards its numbers may be read aloud.",
        "remove_mark_yours" to "You marked this. Removing your mark is instant.",
        "waiting_card" to "Waiting for your yes on the approval card.",
        "chart_empty" to "No numbers yet - log the first one.",
        "chart_target" to "Target",
        "chart_summary" to "{count} numbers. Latest: {latest}.",
        "latest" to "Latest",
        "remove_number" to "Remove this number",
        "delete_project" to "Delete project",
        "delete_project_q" to "Delete the project \"{name}\"? Its benchmarks and every number logged go with it. This cannot be undone.",
        "delete_bench" to "Delete benchmark",
        "delete_bench_q" to "Delete the benchmark \"{name}\" and every number logged for it? This cannot be undone.",
        "delete_yes" to "Delete",
        "delete_no" to "Keep it",
        "command_on_pc" to "A benchmark's command is written and changed on your PC.",
        "missing" to "Your PC's Jarvis does not have Projects yet - run apply-patches.ps1 on the PC.",
        "stale" to "The connection to Jarvis is catching up, so nothing can be sent until it does.",
        "back" to "All projects",
        "open" to "Open",
        "life" to "Life",
        "coding" to "Coding",
    )

    /** One of [WORDS]. */
    fun w(key: String): String = WORDS.getValue(key)

    /** `{name}` and friends filled in. */
    fun fill(template: String, vararg values: Pair<String, Any>): String {
        var out = template
        for ((k, v) in values) out = out.replace("{$k}", v.toString())
        return out
    }

    val MISSING: String get() = w("missing")

    // ------------------------------------------------------------ shapes ----

    data class Point(val id: String, val at: Double, val value: Double)

    data class Latest(val id: String, val value: Double, val at: Double?)

    data class Bench(
        val id: String,
        val name: String,
        val kind: String,
        val unit: String,
        val better: String?,
        val target: Double?,
        val sensitive: Boolean,
        /** Health or money, or marked by the owner: shown, never read aloud. */
        val keepOnScreen: Boolean,
        val keepOnScreenWords: String,
        val markedByYou: Boolean,
        /** "card" (Jarvis's own mark), "instant" (only the owner's), or "". */
        val unmark: String,
        val unmarkWaiting: Boolean,
        val unmarkLast: String,
        val results: Int,
        val latest: Latest?,
        val said: String,
        val targetReached: Boolean,
        val command: String,
        val notRunnableWhy: String,
        /** The chart's points, oldest first - only from a benchmark's own read. */
        val points: List<Point>?,
    )

    data class Folder(val path: String, val name: String, val listed: Boolean, val said: String)

    data class Project(
        val id: String,
        val name: String,
        val kind: String,
        val instructions: String,
        val notes: List<String>,
        val folder: Folder?,
        val shareable: Boolean,
        val shareableWaiting: Boolean,
        val shareableLast: String,
        val workListTitle: String?,
        val benchmarks: Int,
        val benchList: List<Bench>,
        val maxInstructions: Int,
        /** A Jarvis-built app's part (the list's short form or the full one), or null. */
        val app: AppInfo? = null,
    )

    data class ListView(
        val available: Boolean,
        val why: String,
        val projects: List<Project>,
        val empty: String,
        val max: Int,
    )

    // ------------------------------------------------------------ reading ---

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject.number(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() }

    private fun JsonObject.whole(key: String): Int? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    /** One benchmark, from the PC's `view`; null without an id. */
    fun parseBench(o: JsonObject?): Bench? {
        if (o == null) return null
        val id = o.text("id")?.takeIf { it.isNotBlank() } ?: return null
        val change = o.obj("change")
        val latest = o.obj("latest")?.let { l ->
            l.number("value")?.let { Latest(l.text("id").orEmpty(), it, l.number("at")) }
        }
        val points = (o["points"] as? JsonArray)?.mapNotNull { el ->
            val p = el as? JsonObject ?: return@mapNotNull null
            val v = p.number("value") ?: return@mapNotNull null
            val at = p.number("at") ?: return@mapNotNull null
            Point(p.text("id").orEmpty(), at, v)
        }
        val sensitive = o.flag("sensitive")
        val better = o.text("better")?.takeIf { it == "higher" || it == "lower" }
        return Bench(
            id = id,
            name = o.text("name").orEmpty(),
            kind = if (o.text("kind") == "command") "command" else "number",
            unit = o.text("unit").orEmpty(),
            better = better,
            target = o.number("target"),
            sensitive = sensitive,
            keepOnScreen = o.flag("keep_on_screen") || sensitive,
            keepOnScreenWords = o.text("keep_on_screen_words").orEmpty(),
            markedByYou = o.flag("marked_by_you"),
            unmark = o.text("unmark")?.takeIf { it == "card" || it == "instant" }.orEmpty(),
            unmarkWaiting = o.flag("unmark_waiting"),
            unmarkLast = o.obj("unmark_last")?.text("message").orEmpty(),
            results = o.whole("results") ?: 0,
            latest = latest,
            said = change?.text("said").orEmpty(),
            targetReached = change?.flag("target_reached") == true,
            command = o.text("command").orEmpty(),
            notRunnableWhy = o.text("not_runnable_why").orEmpty(),
            points = points,
        )
    }

    /** One project, from the PC's `full` (or the list's `summary`); null without an id. */
    fun parseProject(o: JsonObject?): Project? {
        if (o == null) return null
        val id = o.text("id")?.takeIf { it.isNotBlank() } ?: return null
        val folder = o.obj("folder")?.let { f ->
            val path = f.text("path").orEmpty()
            Folder(
                path = path,
                name = f.text("name")?.takeIf { it.isNotBlank() } ?: path,
                listed = (f["listed"] as? JsonPrimitive)?.booleanOrNull != false,
                said = f.text("said").orEmpty(),
            )
        }
        val wl = o.obj("work_list")
        val notes = (o["notes"] as? JsonArray)?.mapNotNull {
            (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.contentOrNull
        }.orEmpty()
        val benches = (o["benchmark_list"] as? JsonArray)?.mapNotNull { parseBench(it as? JsonObject) }.orEmpty()
        return Project(
            id = id,
            name = o.text("name").orEmpty(),
            kind = if (o.text("kind") == "coding") "coding" else "life",
            instructions = o.text("instructions").orEmpty(),
            notes = notes,
            folder = folder,
            shareable = o.flag("shareable"),
            shareableWaiting = o.flag("shareable_waiting"),
            shareableLast = o.obj("shareable_last")?.text("message").orEmpty(),
            workListTitle = wl?.let { it.text("title")?.takeIf { t -> t.isNotBlank() } ?: it.text("name") },
            benchmarks = o.whole("benchmarks") ?: benches.size,
            benchList = benches,
            maxInstructions = o.obj("max")?.whole("instructions") ?: 1500,
            app = parseApp(o.obj("app")),
        )
    }

    /** `GET /api/projects`, read - or null when it is not the list at all. */
    fun parseList(body: JsonObject): ListView? {
        val raw = body["projects"] as? JsonArray ?: return null
        return ListView(
            available = true,
            why = "",
            projects = raw.mapNotNull { parseProject(it as? JsonObject) },
            empty = body.text("empty").orEmpty(),
            max = body.whole("max") ?: 30,
        )
    }

    /**
     * A read the PC answered without Projects at all: a 404 that is not
     * jarvis_projects' own "no such project" (which carries `ok: false`), or
     * a 501.
     */
    fun isMissing(reply: Reply): Boolean {
        val pcOwn = (reply.body?.get("ok") as? JsonPrimitive)?.booleanOrNull == false
        return (reply.code == 404 && !pcOwn) || reply.code == 501
    }

    /** A read that failed because this PC has no Projects: a 404 or a 501. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || (error is ApiError.Server && error.code == 501)

    // ------------------------------------------------------------ numbers ---

    /**
     * A number the way the PC writes it (jarvis_projects._num_words): a whole
     * number without a point, otherwise at most four places with the
     * trailing zeros taken off.
     */
    fun numberWords(v: Double): String {
        if (!v.isFinite()) return ""
        if (v == floor(v) && abs(v) < 1e15) return v.toLong().toString()
        return String.format(Locale.ROOT, "%.4f", v).trimEnd('0').trimEnd('.')
    }

    /** With its unit, as the PC says it: "5 km", "$200", "12.5%". */
    fun withUnit(v: Double, unit: String): String {
        val n = numberWords(v)
        return when {
            unit.isEmpty() -> n
            unit == "$" || unit == "£" || unit == "€" -> "$unit$n"
            unit == "%" -> "$n%"
            else -> "$n $unit"
        }
    }

    /**
     * Where the chart's bottom and top are (lo < hi): every value and the
     * target fit, with a tenth of the range spare each way; one value (or all
     * the same) gets one unit of room each way, or a tenth of its size when
     * that is bigger. The same as tools/gen_projects_cases.py's `chart_scale`.
     */
    fun chartScale(values: List<Double>, target: Double?): Pair<Double, Double> {
        val pool = values.filter { it.isFinite() }.toMutableList()
        if (target != null && target.isFinite()) pool.add(target)
        if (pool.isEmpty()) return 0.0 to 1.0
        val lo = pool.min()
        val hi = pool.max()
        if (hi - lo < 1e-9) {
            val room = max(1.0, abs(lo) * 0.1)
            return (lo - room) to (hi + room)
        }
        val pad = (hi - lo) * 0.1
        return (lo - pad) to (hi + pad)
    }

    /** A point's place in a box of [width] by [height], y growing downward. */
    data class Placed(val x: Float, val y: Float)

    /**
     * The chart's drawing as numbers: each point placed by its date (the
     * first on the left, the newest on the right, one alone in the middle),
     * and the target line's y, or null. The desktop's `chartGeometry`.
     */
    fun chartGeometry(
        points: List<Point>,
        target: Double?,
        width: Float,
        height: Float,
        inset: Float = 8f,
    ): Pair<List<Placed>, Float?> {
        val (lo, hi) = chartScale(points.map { it.value }, target)
        val w = width - inset * 2
        val h = height - inset * 2
        fun y(v: Double): Float = (inset + h - ((v - lo) / (hi - lo)) * h).toFloat()
        val first = points.firstOrNull()?.at ?: 0.0
        val last = points.lastOrNull()?.at ?: 0.0
        val span = last - first
        val placed = points.map { p ->
            val x = if (span > 0) inset + ((p.at - first) / span).toFloat() * w else inset + w / 2
            Placed(min(max(x, 0f), width), y(p.value))
        }
        val t = target?.takeIf { it.isFinite() }?.let { y(it) }
        return placed to t
    }

    /** "3 numbers. Latest: 12 km." - the chart's words for TalkBack. */
    fun chartSummary(b: Bench): String {
        val count = if (b.results > 0) b.results else b.points?.size ?: 0
        val latest = b.latest ?: return w("chart_empty")
        if (count == 0) return w("chart_empty")
        return fill(w("chart_summary"), "count" to count, "latest" to withUnit(latest.value, b.unit))
    }

    /** What the private-mark button does, or null: never while a card waits. */
    data class Offer(val kind: String, val label: String, val why: String)

    fun unmarkOffer(b: Bench): Offer? {
        if (!b.keepOnScreen || b.unmark.isEmpty() || b.unmarkWaiting) return null
        return Offer(
            kind = b.unmark,
            label = w("remove_mark"),
            why = if (b.unmark == "card") w("remove_mark_card") else w("remove_mark_yours"),
        )
    }

    /** A logged value from the box: a number, or null. "72,5" is 72.5. */
    fun valueFrom(raw: String): Double? =
        raw.trim().replace(',', '.').takeIf { it.isNotEmpty() }?.toDoubleOrNull()?.takeIf { it.isFinite() }

    /** The notes box: one note per line, blanks dropped. */
    fun notesFrom(text: String): List<String> = text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }

    // ------------------------------------------------------------ apps ------
    // docs/APPS-IN-PROJECTS-DESIGN.md sections 5 and 7.1: a coding project
    // may be a Jarvis-built app. The phone reads it, merges and discards; it
    // never creates an app, starts a task or pastes a change in (the PC only).

    /** The screens' words for apps (design 5 and 7.1). Kept apart from [WORDS] until the shared fixture carries them. */
    val APP_WORDS: Map<String, String> = mapOf(
        "app" to "App",
        "app_type_web" to "Web app",
        "app_type_android" to "Android app",
        "app_where" to "Files: kept on this PC in Jarvis's apps folder. This app's files are only on this PC.",
        "app_latest" to "Latest version",
        "app_versions" to "{n} saved versions",
        "app_no_version" to "No saved version yet.",
        "app_tasks" to "Open tasks",
        "app_no_tasks" to "No open tasks.",
        "app_start_on_pc" to "Starting a task, and pasting a change into one, is done on your PC.",
        "app_create_on_pc" to "An app Jarvis builds is made on your PC: New project, then \"An app Jarvis builds\".",
        "app_older" to "Made before another change - may not fit.",
        "app_waiting" to "Waiting for your card.",
        "app_open" to "Open",
        "task_back" to "All tasks",
        "task_files" to "Files in this change",
        "task_from_jarvis" to "Jarvis wrote this change.",
        "task_from_paste" to "You pasted this change in on your PC.",
        "task_from_empty" to "Nothing in this task yet.",
        "task_read" to "Read the whole change. Merge opens on the last page.",
        "task_page" to "Page {n} of {total}",
        "task_prev" to "Previous page",
        "task_next" to "Next page",
        "task_none" to "This task has no changes to show.",
        "task_too_big" to "This change is too big to show on one card. Ask Jarvis to split it into smaller steps.",
        "merge" to "Merge",
        "merge_hint" to "Approve the card that appears - it needs your fingerprint or PIN.",
        "merge_locked" to "Merge opens once you have reached the last page.",
        "merge_card_up" to "A card for this app is already waiting - answer it first.",
        "discard" to "Discard",
        "discard_q" to "Throw away the task \"{title}\"? Nothing reaches your app. This cannot be undone.",
        "discard_yes" to "Discard",
        "discard_no" to "Keep it",
    )

    /** One of [APP_WORDS]. */
    fun aw(key: String): String = APP_WORDS.getValue(key)

    /** merge.last.outcome -> its fixed sentence (design 7.1, word for word). */
    val MERGE_OUTCOMES: Map<String, String> = mapOf(
        "merged" to "Added to your app.",
        "denied" to "Not added - you said no. The change is kept aside.",
        "timed_out" to "Not added - the card timed out. The change is kept aside.",
        "stale" to "Not added - the app or the change moved after the card was shown. Look at the new card.",
        "unsaved" to "Not added - the app's own folder has changes that are not saved in git.",
        "conflict" to "Not added - the change did not fit the app's newer version. Nothing was changed; discard it and ask again.",
        "withdrawn" to "Not added - the change was thrown away before you answered.",
        "refused" to "Not added.",
        "failed" to "Not added - something went wrong. Nothing was changed.",
    )

    data class AppMain(val head: String, val subject: String, val at: Double?, val versions: Int)

    data class MergeLast(val task: String, val outcome: String, val message: String, val at: Double?)

    data class TaskSummary(
        val task: String,
        val title: String,
        val started: Double?,
        /** "jarvis" | "pasted" | "empty" (anything else reads as empty). */
        val source: String,
        val files: Int,
        val added: Int,
        val removed: Int,
        val olderMain: Boolean,
        val waiting: Boolean,
    )

    data class FileChange(val path: String, val added: String, val removed: String)

    data class TaskDetail(
        val summary: TaskSummary,
        val list: List<FileChange>,
        val diff: String,
        val tooBig: Boolean,
        /** The sentence the PC gives for "no card can be raised", or "". */
        val refused: String,
    )

    /**
     * The app part of a project. The list gives a short form (`tasks` a
     * count, `merge_waiting` a flag); the full read gives everything.
     */
    data class AppInfo(
        val name: String,
        /** "web" | "android" | "" */
        val type: String,
        val title: String,
        val gitOk: Boolean,
        val said: String,
        val main: AppMain?,
        val tasks: List<TaskSummary>,
        val openTasks: Int,
        /** The task id a merge card waits for, or null. */
        val waitingTask: String?,
        val mergeWaiting: Boolean,
        val last: MergeLast?,
    )

    fun parseTask(o: JsonObject?): TaskSummary? {
        if (o == null) return null
        val id = o.text("task")?.takeIf { it.isNotBlank() } ?: return null
        return TaskSummary(
            task = id,
            title = o.text("title").orEmpty(),
            started = o.number("started"),
            source = o.text("source")?.takeIf { it == "jarvis" || it == "pasted" } ?: "empty",
            files = o.whole("files") ?: 0,
            added = o.whole("added") ?: 0,
            removed = o.whole("removed") ?: 0,
            olderMain = o.flag("older_main"),
            waiting = o.flag("waiting"),
        )
    }

    fun parseTaskDetail(o: JsonObject?): TaskDetail? {
        if (o == null) return null
        val summary = parseTask(o) ?: return null
        val list = (o["list"] as? JsonArray)?.mapNotNull { el ->
            val f = el as? JsonObject ?: return@mapNotNull null
            val path = f.text("path")?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            FileChange(path, f.text("added").orEmpty(), f.text("removed").orEmpty())
        }.orEmpty()
        return TaskDetail(
            summary = summary,
            list = list,
            diff = o.text("diff").orEmpty(),
            tooBig = o.flag("too_big"),
            refused = o.text("refused").orEmpty(),
        )
    }

    /** `app` from a project's summary or full view; null when it is not an app project. */
    fun parseApp(o: JsonObject?): AppInfo? {
        if (o == null) return null
        val name = o.text("name")?.takeIf { it.isNotBlank() } ?: return null
        val rawTasks = o["tasks"]
        val tasks = (rawTasks as? JsonArray)?.mapNotNull { parseTask(it as? JsonObject) }.orEmpty()
        val count = (rawTasks as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull ?: tasks.size
        val main = o.obj("main")?.let { m ->
            AppMain(
                head = m.text("head").orEmpty(),
                subject = m.text("subject").orEmpty(),
                at = m.number("at"),
                versions = m.whole("versions") ?: 0,
            )
        }
        val merge = o.obj("merge")
        val waitingTask = merge?.text("waiting")?.takeIf { it.isNotBlank() }
        val last = merge?.obj("last")?.let { l ->
            MergeLast(
                task = l.text("task").orEmpty(),
                outcome = l.text("outcome").orEmpty(),
                message = l.text("message").orEmpty(),
                at = l.number("at"),
            )
        }
        return AppInfo(
            name = name,
            type = o.text("type")?.takeIf { it == "web" || it == "android" }.orEmpty(),
            title = o.text("title").orEmpty(),
            gitOk = (o["git_ok"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull != false,
            said = o.text("said").orEmpty(),
            main = main,
            tasks = tasks,
            openTasks = count,
            waitingTask = waitingTask,
            mergeWaiting = waitingTask != null || o.flag("merge_waiting"),
            last = last,
        )
    }

    /** The task inside `GET .../app/tasks/<task>` (`{"ok", "task": detail}`). */
    fun taskOf(reply: Reply): TaskDetail? = parseTaskDetail(reply.body?.obj("task"))

    /** The sentence for a finished merge: the fixed one, or the PC's own for "refused" and unknowns. */
    fun mergeSentence(last: MergeLast): String = when (last.outcome) {
        "refused" -> last.message.ifBlank { MERGE_OUTCOMES.getValue("refused") }
        else -> MERGE_OUTCOMES[last.outcome] ?: last.message
    }

    fun typeWords(app: AppInfo): String = when (app.type) {
        "web" -> aw("app_type_web")
        "android" -> aw("app_type_android")
        else -> aw("app")
    }

    fun sourceWords(source: String): String = when (source) {
        "jarvis" -> aw("task_from_jarvis")
        "pasted" -> aw("task_from_paste")
        else -> aw("task_from_empty")
    }

    /** "3 files, +41 -2" */
    fun changeCounts(t: TaskSummary): String =
        "${t.files} ${if (t.files == 1) "file" else "files"}, +${t.added} -${t.removed}"

    // -- the whole change, in pages --------------------------------------------

    /** How a diff line is drawn: added, removed, a hunk header, file header lines, or plain. */
    enum class DiffKind { ADDED, REMOVED, HUNK, META, CONTEXT }

    /** [continued] is true for the second and later pieces of one very long line. */
    data class DiffLine(val text: String, val kind: DiffKind, val continued: Boolean)

    const val DIFF_LINES_PER_PAGE = 120
    const val DIFF_PIECE = 300

    private fun kindOf(line: String): DiffKind = when {
        line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff --git") ||
            line.startsWith("index ") -> DiffKind.META
        line.startsWith("@@") -> DiffKind.HUNK
        line.startsWith("+") -> DiffKind.ADDED
        line.startsWith("-") -> DiffKind.REMOVED
        else -> DiffKind.CONTEXT
    }

    /**
     * The whole diff as lines, none dropped: a line longer than [DIFF_PIECE]
     * becomes several pieces, so nothing is ever a giant single `Text`.
     */
    fun diffLines(diff: String): List<DiffLine> {
        if (diff.isEmpty()) return emptyList()
        val out = ArrayList<DiffLine>()
        for (line in diff.split('\n')) {
            val kind = kindOf(line)
            if (line.length <= DIFF_PIECE) {
                out.add(DiffLine(line, kind, false))
            } else {
                line.chunked(DIFF_PIECE).forEachIndexed { i, piece -> out.add(DiffLine(piece, kind, i > 0)) }
            }
        }
        return out
    }

    fun diffPages(diff: String, perPage: Int = DIFF_LINES_PER_PAGE): List<List<DiffLine>> =
        diffLines(diff).chunked(perPage.coerceAtLeast(1))

    /** The pages put back together - equals the diff they were made from. */
    fun diffText(pages: List<List<DiffLine>>): String {
        val sb = StringBuilder()
        var first = true
        for (l in pages.flatten()) {
            if (!l.continued && !first) sb.append('\n')
            sb.append(l.text)
            first = false
        }
        return sb.toString()
    }

    /** Merge may be tapped only after the last page has been shown. */
    fun readToEnd(pageCount: Int, furthestShown: Int): Boolean = pageCount > 0 && furthestShown >= pageCount - 1

    /**
     * Why Merge cannot be tapped now (a plain sentence), or null when it can.
     * The card itself is raised by the PC and decided in the approval queue;
     * this only decides whether the button on this page is usable.
     */
    fun mergeBlock(
        detail: TaskDetail,
        pageCount: Int,
        furthestShown: Int,
        cardWaitingForApp: Boolean,
        canAct: Boolean,
    ): String? = when {
        !canAct -> w("stale")
        detail.refused.isNotBlank() -> detail.refused
        detail.tooBig -> aw("task_too_big")
        pageCount == 0 -> aw("task_none")
        cardWaitingForApp || detail.summary.waiting -> aw("merge_card_up")
        !readToEnd(pageCount, furthestShown) -> aw("merge_locked")
        else -> null
    }

    // ------------------------------------------------------------ routes ----

    private val ID = Regex("[0-9a-f]{32}")

    /** Only a real id (32 lower-case hex digits) ever reaches a URL. */
    fun isId(s: String): Boolean = ID.matches(s)

    fun projectPath(id: String): String? = if (isId(id)) "/api/projects/$id" else null

    private val TASK_ID = Regex("[0-9a-f]{12}")

    /** Only a real task id (12 lower-case hex digits) ever reaches a URL. */
    fun isTaskId(s: String): Boolean = TASK_ID.matches(s)

    /** `GET` one open task of an app project. */
    fun taskPath(pid: String, task: String): String? =
        if (isId(pid) && isTaskId(task)) "/api/projects/$pid/app/tasks/$task" else null

    fun benchPath(pid: String, bid: String, points: Int = 365): String? =
        if (isId(pid) && isId(bid)) "/api/projects/$pid/benchmarks/$bid?points=${points.coerceIn(1, 1000)}" else null

    /**
     * The POST path for one change, named by the same actions the desktop's
     * `projects_write` takes (brain/projects.rs ACTIONS) - or null for an
     * unknown action or a bad id. The phone never sends a folder or a
     * command: those are the PC's ([PC_ONLY]).
     */
    fun writePath(
        action: String,
        pid: String? = null,
        bid: String? = null,
        rid: String? = null,
        task: String? = null,
    ): String? {
        val p = pid?.takeIf { isId(it) }
        val t = task?.takeIf { isTaskId(it) }
        val b = bid?.takeIf { isId(it) }
        val r = rid?.takeIf { isId(it) }
        return when (action) {
            "create" -> PATH
            "update" -> p?.let { "/api/projects/$it" }
            "delete" -> p?.let { "/api/projects/$it/delete" }
            "shareable" -> p?.let { "/api/projects/$it/shareable" }
            "bench_add" -> p?.let { "/api/projects/$it/benchmarks" }
            "bench_update" -> if (p != null && b != null) "/api/projects/$p/benchmarks/$b" else null
            "bench_delete" -> if (p != null && b != null) "/api/projects/$p/benchmarks/$b/delete" else null
            "log" -> if (p != null && b != null) "/api/projects/$p/benchmarks/$b/log" else null
            "result_delete" -> if (p != null && b != null && r != null) {
                "/api/projects/$p/benchmarks/$b/results/$r/delete"
            } else {
                null
            }
            "unmark" -> if (p != null && b != null) "/api/projects/$p/benchmarks/$b/unmark" else null
            // An app's task: merge (one card) and discard. Starting a task and
            // pasting a change in are the PC's ([PC_ONLY]) - no path here.
            "app_task_merge" -> if (p != null && t != null) "/api/projects/$p/app/tasks/$t/merge" else null
            "app_task_discard" -> if (p != null && t != null) "/api/projects/$p/app/tasks/$t/discard" else null
            else -> null
        }
    }

    /** What the phone leaves to the PC (the PC refuses them from here too). */
    val PC_ONLY: Set<String> = setOf("folder", "command", "app_create", "app_task_start", "app_task_files")

    /**
     * Whether a change waits for a live link: all do, except Shareable OFF.
     * That includes an app task's Merge and Discard (rule 4).
     */
    fun heldOnStale(action: String, on: Boolean? = null): Boolean = !(action == "shareable" && on == false)

    // ------------------------------------------------------------ bodies ----

    fun createBody(name: String): String = buildJsonObject {
        put("name", name.trim())
        put("kind", "life")
    }.toString()

    fun textBody(instructions: String, notes: String): String = buildJsonObject {
        put("instructions", instructions)
        put("notes", JsonArray(notesFrom(notes).map { JsonPrimitive(it) }))
    }.toString()

    fun shareableBody(on: Boolean): String = "{\"on\":$on}"

    fun logBody(value: Double): String = buildJsonObject { put("value", value) }.toString()

    fun markBody(): String = "{\"sensitive\":true}"

    /**
     * "Add a benchmark" - a number the owner logs (the phone never adds a
     * command: [PC_ONLY]). The JSON, or an error sentence to show.
     */
    fun benchBody(name: String, unit: String, better: String?, target: String): Pair<String?, String?> {
        val n = name.trim()
        if (n.isEmpty()) return null to "Give the benchmark a name."
        val t = target.trim()
        val tv = if (t.isEmpty()) null else valueFrom(t) ?: return null to "The target is a number, like 21.1."
        return buildJsonObject {
            put("name", n)
            put("kind", "number")
            if (unit.trim().isNotEmpty()) put("unit", unit.trim())
            if (better == "higher" || better == "lower") put("better", better)
            if (tv != null) put("target", tv)
        }.toString() to null
    }

    // ------------------------------------------------------------ answers ---

    /** What the PC answered a change, kept whole: the status and the JSON body. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** How a change went: [changed] reads again; [waiting] a card is up. */
    data class Outcome(val changed: Boolean, val waiting: Boolean, val said: String)

    /**
     * Reads one change's answer. A 202 (`waiting: true`) is a card the PC
     * raised; its own message says so. A refusal is the PC's own sentence
     * (403 "the PC only", 400 a limit, 409 a name used twice). A 404 without
     * `ok: false` is a PC without Projects. [quiet] keeps a private number out
     * of the sentence, which TalkBack reads out.
     */
    fun said(reply: Reply, done: String, quiet: Boolean = false): Outcome {
        val b = reply.body
        val error = b?.text("error")?.let { DesktopWrite.asSentence(it) }
        val pcOwn = (b?.get("ok") as? JsonPrimitive)?.booleanOrNull == false
        return when {
            reply.code in 200..299 -> when {
                pcOwn -> Outcome(false, false, "Not changed. " + (error ?: "Your PC said no, without a reason."))
                reply.code == 202 || b?.flag("waiting") == true ->
                    Outcome(true, true, b?.text("message") ?: w("waiting_card"))
                quiet -> Outcome(true, false, done)
                else -> Outcome(true, false, b?.text("message") ?: done)
            }
            reply.code == 404 && !pcOwn -> Outcome(false, false, MISSING)
            reply.code == 501 -> Outcome(false, false, MISSING)
            else -> Outcome(false, false, error ?: "Not changed. Your PC said no (HTTP ${reply.code}).")
        }
    }

    /** The benchmark's view inside a change's answer, for "better or worse" after a log. */
    fun benchOf(reply: Reply): Bench? = parseBench(reply.body?.obj("benchmark"))

    /** The project inside a change's answer (create, update). */
    fun projectOf(reply: Reply): Project? = parseProject(reply.body?.obj("project"))
}
