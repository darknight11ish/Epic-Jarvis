package com.jarvis.client.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Projects
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Projects" on Brain ([Projects], the owner's decision of 2026-09-28;
 * docs/PROJECTS-DESIGN.md build step 3) - the desktop's Brain -> Projects,
 * in the same words (both apps are checked against the contract file).
 *
 * The list, then one project at a time: how Jarvis should work on it and
 * its notes, the Shareable switch (ON asks with an approval card on the PC;
 * OFF is instant, and works on a stale link), its work list, and its
 * benchmarks - the latest number, "better or worse than last time", a chart
 * of dated points with the target as a dashed line, Log, the private mark
 * and Delete. Deleting asks "are you sure?" right there first.
 *
 * A number marked private (health or money, or by the owner) shows "private
 * - not read aloud", and the line after logging one says only "Logged." -
 * TalkBack reads that line out, so the number stays off it.
 *
 * What the phone leaves to the PC, said as "Set on your PC": a coding
 * project (its folder is chosen from the PC's own folders) and a
 * benchmark's command (its words decide what would run on the PC). The PC
 * refuses both from here too (ARCHITECTURE section 8).
 *
 * "Hide memory lists and chat history" (Settings) replaces it with
 * [HiddenSection] until Show is confirmed, like Brain's other private lists.
 */
@Composable
internal fun ProjectsSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(Projects.w("title"), busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.projectsTick.collectAsState()
    val pending by JarvisRuntime.pending.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var list by remember { mutableStateOf<Projects.ListView?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }
    var project by remember { mutableStateOf<Projects.Project?>(null) }
    var charts by remember { mutableStateOf<Map<String, Projects.Bench>>(emptyMap()) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var newName by remember { mutableStateOf("") }

    // A card this screen caused is answered elsewhere; read again when the
    // queue changes while one waits.
    val waiting = project?.let { p ->
        p.shareableWaiting || p.benchList.any { it.unmarkWaiting } || p.app?.mergeWaiting == true
    } == true
    val queueKey = if (waiting) pending.size else -1

    LaunchedEffect(reads, tick, openId, queueKey) {
        when (val r = JarvisRuntime.projectsRead(Projects.PATH)) {
            is ApiResult.Ok -> {
                val reply = r.value
                val parsed = if (reply.code in 200..299) reply.body?.let { Projects.parseList(it) } else null
                when {
                    parsed != null -> {
                        list = parsed
                        missing = false
                        readError = null
                    }
                    Projects.isMissing(reply) -> {
                        missing = true
                        readError = null
                    }
                    else -> readError = Projects.said(reply, "").said
                }
            }
            is ApiResult.Failed -> if (Projects.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
        val id = openId ?: run {
            project = null
            charts = emptyMap()
            return@LaunchedEffect
        }
        val path = Projects.projectPath(id) ?: return@LaunchedEffect
        val r = JarvisRuntime.projectsRead(path)
        val p = (r as? ApiResult.Ok)?.value?.takeIf { it.code in 200..299 }?.let { Projects.projectOf(it) }
        if (p == null) {
            if (r is ApiResult.Ok && r.value.code == 404) openId = null
            return@LaunchedEffect
        }
        project = p
        val got = mutableMapOf<String, Projects.Bench>()
        for (b in p.benchList) {
            val bp = Projects.benchPath(p.id, b.id) ?: continue
            val br = JarvisRuntime.projectsRead(bp)
            val bench = (br as? ApiResult.Ok)?.value?.takeIf { it.code in 200..299 }?.let { Projects.benchOf(it) }
            if (bench != null) got[b.id] = bench
        }
        charts = got
    }

    /** ONE change; the sentence goes on the status line. */
    fun change(
        action: String,
        path: String?,
        json: String,
        done: String,
        quiet: Boolean = false,
        on: Boolean? = null,
        after: (Projects.Outcome) -> Unit = {},
    ) {
        busy = true
        said = null
        scope.launch {
            try {
                val out = JarvisRuntime.projectsWrite(action, path, json, done, quiet, on)
                said = out.said
                after(out)
            } finally {
                busy = false
            }
        }
    }

    Section(Projects.w("title"), trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val shownList = list
            val open = project
            val err = readError
            when {
                missing -> Text(Projects.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                open != null && openId == open.id -> ProjectView(
                    p = open,
                    charts = charts,
                    canAct = canAct,
                    busy = busy,
                    onBack = {
                        openId = null
                        project = null
                        said = null
                    },
                    change = ::change,
                    onDeleted = {
                        openId = null
                        project = null
                    },
                )
                shownList == null -> Text(
                    if (err != null) "Couldn't read Projects: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(Projects.w("under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (err != null) {
                        Gap(4)
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (shownList.projects.isEmpty()) {
                        Gap(8)
                        Text(shownList.empty.ifBlank { "No projects yet." },
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    shownList.projects.forEach { p ->
                        Gap(8)
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(p.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                                val kind = if (p.kind == "coding") Projects.w("coding") else Projects.w("life")
                                val n = p.benchmarks
                                val a = p.app
                                val appNote = buildString {
                                    if (a != null) {
                                        append(" · ").append(Projects.aw("app"))
                                        if (a.openTasks > 0) {
                                            append(" · ").append(a.openTasks)
                                                .append(if (a.openTasks == 1) " open task" else " open tasks")
                                        }
                                        if (a.mergeWaiting) append(" · ").append(Projects.aw("app_waiting"))
                                    }
                                }
                                Text("$kind · $n ${if (n == 1) "benchmark" else "benchmarks"}$appNote",
                                    style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                            }
                            Quiet(Projects.w("open"), modifier = Modifier.semantics {
                                contentDescription = "${Projects.w("open")} ${p.name}"
                            }, onClick = {
                                said = null
                                openId = p.id
                            })
                        }
                    }
                    // New project: a life project on the phone.
                    Gap(12)
                    TextInput(
                        value = newName,
                        onValueChange = { newName = it.take(60) },
                        label = Projects.w("new"),
                        placeholder = Projects.w("name"),
                        supportingText = Projects.w("coding_on_pc") + " " + Projects.aw("app_create_on_pc"),
                    )
                    Gap(6)
                    Primary(
                        Projects.w("create"),
                        enabled = canAct && !busy && newName.isNotBlank() &&
                            shownList.projects.size < shownList.max,
                        busy = busy,
                        onClick = {
                            change("create", Projects.writePath("create"), Projects.createBody(newName),
                                done = "Created.", after = { out ->
                                    if (out.changed) {
                                        newName = ""
                                        JarvisRuntime.projectsLast.value
                                            ?.let { Projects.projectOf(it) }?.let { openId = it.id }
                                    }
                                })
                        },
                    )
                    if (!canAct) {
                        Gap(4)
                        Text(Projects.w("stale"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}

/** ONE change through [JarvisRuntime.projectsWrite]; also used by AppSection.kt and TaskDiffScreen.kt. */
internal typealias Change = (
    action: String,
    path: String?,
    json: String,
    done: String,
    quiet: Boolean,
    on: Boolean?,
    after: (Projects.Outcome) -> Unit,
) -> Unit

@Composable
private fun ProjectView(
    p: Projects.Project,
    charts: Map<String, Projects.Bench>,
    canAct: Boolean,
    busy: Boolean,
    onBack: () -> Unit,
    change: Change,
    onDeleted: () -> Unit,
) {
    val chrome = LocalChrome.current
    var instructions by remember(p.id, p.instructions) { mutableStateOf(p.instructions) }
    var notes by remember(p.id, p.notes) { mutableStateOf(p.notes.joinToString("\n")) }
    var confirmDelete by remember(p.id) { mutableStateOf(false) }

    Quiet("← ${Projects.w("back")}", onClick = onBack)
    Text(p.name, style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
    Text(if (p.kind == "coding") Projects.w("kind_coding") else Projects.w("kind_life"),
        style = MaterialTheme.typography.labelSmall, color = chrome.textLo)

    Gap(10)
    TextInput(
        value = instructions,
        onValueChange = { instructions = it.take(p.maxInstructions) },
        label = Projects.w("instructions"),
        supportingText = Projects.w("instructions_under"),
        singleLine = false,
    )
    Gap(8)
    TextInput(
        value = notes,
        onValueChange = { notes = it },
        label = Projects.w("notes"),
        supportingText = Projects.w("notes_under"),
        singleLine = false,
        maxLines = 10,
    )
    Quiet(Projects.w("save"), enabled = canAct && !busy, onClick = {
        change("update", Projects.writePath("update", p.id), Projects.textBody(instructions, notes),
            "Saved.", false, null) {}
    })

    val app = p.app
    if (app != null) {
        // A Jarvis-built app: its files are Jarvis's own folder, not a folder
        // the owner chose (AppSection.kt).
        AppSection(p, app, canAct, busy, change)
    } else if (p.kind == "coding") {
        Gap(10)
        Label(Projects.w("folder"))
        Text(p.folder?.path ?: Projects.w("folder_none"), style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid)
        p.folder?.takeIf { !it.listed }?.let {
            Text(it.said, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
        Text(Projects.w("set_on_pc"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }

    // Shareable: ON asks with a card on the PC; OFF is instant (never held).
    Gap(10)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(Projects.w("shareable"), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
            modifier = Modifier.weight(1f))
        Toggle(
            checked = p.shareable,
            onCheckedChange = { on ->
                change("shareable", Projects.writePath("shareable", p.id), Projects.shareableBody(on),
                    "Done.", false, on) {}
            },
            enabled = !busy && !p.shareableWaiting && (canAct || p.shareable),
            modifier = Modifier.semantics { contentDescription = Projects.w("shareable") },
        )
    }
    Text(Projects.w("shareable_under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (p.shareableWaiting) {
        Text(Projects.w("waiting_card"), style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    } else if (p.shareableLast.isNotEmpty()) {
        Text(p.shareableLast, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
    }

    Gap(10)
    Label(Projects.w("work_list"))
    Text(p.workListTitle ?: Projects.w("work_list_none"), style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid)
    p.workListTitle?.let {
        Text(Projects.fill(Projects.w("work_list_under"), "name" to it.lowercase()),
            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }

    Gap(10)
    Label(Projects.w("benchmarks"))
    if (p.benchList.isEmpty()) {
        Text(Projects.w("benchmarks_empty"), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    p.benchList.forEach { b0 ->
        Gap(10)
        BenchView(p, charts[b0.id] ?: b0, canAct, busy, change)
    }

    Gap(10)
    AddBench(p, canAct, busy, change)

    Gap(12)
    Quiet(Projects.w("delete_project"), color = chrome.badInk, enabled = canAct && !busy,
        onClick = { confirmDelete = true })
    if (confirmDelete) {
        Text(Projects.fill(Projects.w("delete_project_q"), "name" to p.name),
            style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(Projects.w("delete_yes"), color = chrome.badInk, enabled = canAct && !busy, onClick = {
                confirmDelete = false
                change("delete", Projects.writePath("delete", p.id), "{}", "Deleted.", false, null) { out ->
                    if (out.changed) onDeleted()
                }
            })
            Quiet(Projects.w("delete_no"), onClick = { confirmDelete = false })
        }
    }
}

@Composable
private fun Label(text: String) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = LocalChrome.current.textLo)
}

@Composable
private fun BenchView(
    p: Projects.Project,
    b: Projects.Bench,
    canAct: Boolean,
    busy: Boolean,
    change: Change,
) {
    val chrome = LocalChrome.current
    var value by remember(b.id) { mutableStateOf("") }
    var confirmDelete by remember(b.id) { mutableStateOf(false) }
    var showNumbers by remember(b.id) { mutableStateOf(false) }

    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(b.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            if (b.keepOnScreen) Pill(Projects.w("private_label"), color = chrome.warnInk)
        }
        if (b.kind == "command") {
            Text(b.command, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Text(b.notRunnableWhy, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Text(Projects.w("set_on_pc"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        b.latest?.let { l ->
            val line = buildString {
                append(Projects.w("latest")).append(": ").append(Projects.withUnit(l.value, b.unit))
                if (b.said.isNotEmpty()) append(" · ").append(b.said)
                if (b.targetReached) append(" · Target reached.")
            }
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Gap(4)
        Chart(b)
        // The finish-time range, exactly as the PC worded it (never rebuilt). The chart's own
        // spoken text already carries it, so this line is for the eyes only.
        val pace = b.forecast
        if (pace != null && (b.points.orEmpty().isNotEmpty() || b.latest != null)) {
            // A forecast with no words is still drawn; only its words line is left out.
            if (pace.words.isNotBlank()) {
                Text(pace.words, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    modifier = Modifier.clearAndSetSemantics { })
            }
            if (pace.basis.isNotEmpty() && (pace.state == "range" || pace.state == "open_ended")) {
                Text(pace.basis, style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                    modifier = Modifier.clearAndSetSemantics { })
            }
        }
        b.target?.let {
            Text("${Projects.w("chart_target")}: ${Projects.withUnit(it, b.unit)} (dashed line)",
                style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }

        val points = b.points.orEmpty()
        if (points.isNotEmpty()) {
            Quiet(if (showNumbers) "Hide numbers" else "Numbers (${points.size})",
                onClick = { showNumbers = !showNumbers })
            if (showNumbers) {
                points.asReversed().take(30).forEach { pt ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("${shortDate(pt.at)}  ${Projects.withUnit(pt.value, b.unit)}",
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                            modifier = Modifier.weight(1f))
                        Quiet(Projects.w("remove_number"), enabled = canAct && !busy, onClick = {
                            change("result_delete", Projects.writePath("result_delete", p.id, b.id, pt.id), "{}",
                                "Removed.", true, null) {}
                        })
                    }
                }
            }
        }

        if (b.kind == "number") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextInput(
                    value = value,
                    onValueChange = { value = it.take(20) },
                    modifier = Modifier.weight(1f).semantics {
                        contentDescription = "${Projects.w("log_value")} for ${b.name}"
                    },
                    placeholder = if (b.unit.isNotEmpty()) "${Projects.w("log_value")} (${b.unit})" else Projects.w("log_value"),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                val v = Projects.valueFrom(value)
                Quiet(Projects.w("log"), enabled = canAct && !busy && v != null, onClick = {
                    if (v != null) {
                        change("log", Projects.writePath("log", p.id, b.id), Projects.logBody(v), "Logged.",
                            b.keepOnScreen, null) { out -> if (out.changed) value = "" }
                    }
                })
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            val offer = Projects.unmarkOffer(b)
            if (offer != null) {
                Quiet(offer.label, enabled = canAct && !busy, onClick = {
                    change("unmark", Projects.writePath("unmark", p.id, b.id), "{}", "Done.", false, null) {}
                })
            } else if (!b.keepOnScreen) {
                Quiet(Projects.w("mark_private"), enabled = canAct && !busy, onClick = {
                    change("bench_update", Projects.writePath("bench_update", p.id, b.id), Projects.markBody(),
                        "Marked private.", false, null) {}
                })
            }
            Quiet(Projects.w("delete_bench"), color = chrome.badInk, enabled = canAct && !busy,
                onClick = { confirmDelete = true })
        }
        Projects.unmarkOffer(b)?.let {
            Text(it.why, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (b.unmarkWaiting) {
            Text(Projects.w("waiting_card"), style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        } else if (b.unmarkLast.isNotEmpty()) {
            Text(b.unmarkLast, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        if (confirmDelete) {
            Text(Projects.fill(Projects.w("delete_bench_q"), "name" to b.name),
                style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet(Projects.w("delete_yes"), color = chrome.badInk, enabled = canAct && !busy, onClick = {
                    confirmDelete = false
                    change("bench_delete", Projects.writePath("bench_delete", p.id, b.id), "{}", "Deleted.",
                        false, null) {}
                })
                Quiet(Projects.w("delete_no"), onClick = { confirmDelete = false })
            }
        }
    }
}

/** Dated points joined by a line, the target as a dashed line. Its words are [Projects.chartSummary]. */
@Composable
private fun Chart(b: Projects.Bench) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val points = b.points ?: b.latest?.let { l -> listOfNotNull(l.at?.let { Projects.Point(l.id, it, l.value) }) }.orEmpty()
    if (points.isEmpty()) {
        Text(Projects.w("chart_empty"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        return
    }
    val words = "${b.name}: ${Projects.chartSummary(b)}"
    val ground = chrome.surface2
    val edge = chrome.hairlineStrong
    val targetInk = chrome.warnMark
    val mark = chrome.textHi
    val forecast = b.forecast?.takeIf { it.drawable }
    Canvas(
        Modifier
            .fillMaxWidth()
            .height(96.dp)
            .semantics { contentDescription = words },
    ) {
        drawRect(ground)
        val fore = Projects.forecastGeometry(points, forecast, b.target, size.width, size.height, 8.dp.toPx())
        val (placed, target) = if (fore != null) {
            fore.points to fore.target
        } else {
            Projects.chartGeometry(points, b.target, size.width, size.height, 8.dp.toPx())
        }
        drawLine(edge, Offset(0f, size.height - 1f), Offset(size.width, size.height - 1f), 1.dp.toPx())
        // Same order and look as the desktop chart (FORECAST DRAWING RULE, docs/GOALS-PROGRESS-DESIGN.md):
        // axis, the target, then the guess UNDER the numbers - a soft accent triangle with a dashed
        // accent edge, a dashed accent trend line, the bracket on the target level and an open
        // chevron (its tip at the clip point) where the drawing stops short - then the numbers.
        target?.let {
            drawLine(
                targetInk, Offset(0f, it), Offset(size.width, it), 1.5.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())),
            )
        }
        if (fore != null) {
            val band = Path().apply {
                moveTo(fore.bandFrom.x, fore.bandFrom.y)
                lineTo(fore.bandFast.x, fore.bandFast.y)
                lineTo(fore.bandSlow.x, fore.bandSlow.y)
                close()
            }
            drawPath(band, accent.copy(alpha = 0.20f))
            drawPath(
                band, accent.copy(alpha = 0.7f),
                style = Stroke(
                    width = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 3.dp.toPx())),
                ),
            )
            drawLine(
                accent, Offset(fore.lineFrom.x, fore.lineFrom.y), Offset(fore.lineTo.x, fore.lineTo.y), 1.5.dp.toPx(),
                cap = StrokeCap.Round,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 3.dp.toPx())),
            )
            val from = fore.bracketFrom
            val to = fore.bracketTo
            val level = fore.target
            if (from != null && to != null && level != null) {
                val tick = 4.dp.toPx()
                val stroke = 1.5.dp.toPx()
                drawLine(mark, Offset(from, level), Offset(to, level), stroke, cap = StrokeCap.Round)
                drawLine(mark, Offset(from, level - tick), Offset(from, level + tick), stroke, cap = StrokeCap.Round)
                drawLine(mark, Offset(to, level - tick), Offset(to, level + tick), stroke, cap = StrokeCap.Round)
            }
            // The chevrons are only drawn once, where two ends land on the same spot.
            val ends = buildList {
                if (fore.arrowFast) add(fore.bandFast)
                if (fore.arrowSlow) add(fore.bandSlow)
                if (fore.arrowLine) add(fore.lineTo)
            }
            val shown = mutableListOf<Projects.Placed>()
            for (e in ends) {
                if (shown.none { kotlin.math.abs(it.x - e.x) < 0.5f && kotlin.math.abs(it.y - e.y) < 0.5f }) {
                    shown += e
                    drawChevron(mark, e)
                }
            }
        }
        for (i in 1 until placed.size) {
            drawLine(accent, Offset(placed[i - 1].x, placed[i - 1].y), Offset(placed[i].x, placed[i].y), 2.dp.toPx())
        }
        for (pt in placed) drawCircle(accent, radius = 3.dp.toPx(), center = Offset(pt.x, pt.y))
    }
}

/** An open chevron pointing right with its tip at [at] (the clip point): "this goes on past the edge". */
private fun DrawScope.drawChevron(color: androidx.compose.ui.graphics.Color, at: Projects.Placed) {
    val len = 5.dp.toPx()
    val half = 4.dp.toPx()
    val stroke = 1.5.dp.toPx()
    drawLine(color, Offset(at.x - len, at.y - half), Offset(at.x, at.y), stroke, cap = StrokeCap.Round)
    drawLine(color, Offset(at.x, at.y), Offset(at.x - len, at.y + half), stroke, cap = StrokeCap.Round)
}

@Composable
private fun AddBench(p: Projects.Project, canAct: Boolean, busy: Boolean, change: Change) {
    val chrome = LocalChrome.current
    var open by remember(p.id) { mutableStateOf(false) }
    var name by remember(p.id) { mutableStateOf("") }
    var unit by remember(p.id) { mutableStateOf("") }
    var better by remember(p.id) { mutableStateOf<String?>(null) }
    var target by remember(p.id) { mutableStateOf("") }
    var problem by remember(p.id) { mutableStateOf<String?>(null) }

    Quiet(Projects.w("add_benchmark"), onClick = { open = !open })
    if (!open) return
    TextInput(value = name, onValueChange = { name = it.take(40) }, label = Projects.w("bench_name"))
    Gap(6)
    TextInput(value = unit, onValueChange = { unit = it.take(16) }, label = Projects.w("bench_unit"))
    Gap(6)
    Label(Projects.w("bench_better"))
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for ((v, label) in listOf(null to Projects.w("better_either"), "higher" to Projects.w("better_higher"),
            "lower" to Projects.w("better_lower"))) {
            Quiet(
                if (better == v) "✓ $label" else label,
                color = if (better == v) null else chrome.textMid,
                onClick = { better = v },
            )
        }
    }
    TextInput(
        value = target,
        onValueChange = { target = it.take(20) },
        label = Projects.w("bench_target"),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
    )
    if (p.kind == "coding") {
        Text(Projects.w("command_on_pc"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    problem?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk) }
    Gap(6)
    Primary(Projects.w("add"), enabled = canAct && !busy && name.isNotBlank(), busy = busy, onClick = {
        val (json, error) = Projects.benchBody(name, unit, better, target)
        problem = error
        if (json != null) {
            change("bench_add", Projects.writePath("bench_add", p.id), json, "Added.", false, null) { out ->
                if (out.changed) {
                    name = ""
                    unit = ""
                    better = null
                    target = ""
                    open = false
                }
            }
        }
    })
}

/** "3 Oct", in the phone's own language. */
private fun shortDate(at: Double): String =
    java.text.SimpleDateFormat("d MMM", java.util.Locale.getDefault()).format(java.util.Date((at * 1000).toLong()))
