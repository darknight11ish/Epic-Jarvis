package com.jarvis.client.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Progress
import com.jarvis.client.ui.parts.Gap
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
 * "Progress" at the top of Brain -> Projects ([Progress], the owner's tick of
 * 2026-09-30, docs/JARVIS-API.md section 105): an ACTIVITY grid of the last
 * weeks and a BALANCE chart of 3 to 8 areas the owner picks.
 *
 * Both are drawn with Compose's own Canvas from what the PC sends - the
 * shades, the columns and every sentence come from the PC, this file only
 * puts them on screen. A quiet day is a neutral outline (never red, never a
 * cross); there is no streak, no percentage and no overall score anywhere.
 *
 * TalkBack: the grid's Canvas is described by the PC's `summary`, and each
 * week is one focusable strip with that week's days read out. The radar is
 * decorative; the list under it carries every area's value.
 *
 * "Hide memory lists and chat history" - ONE rule, the same as the desktop's:
 * an answer the PC marks `keep_on_screen` is not drawn; only its hidden
 * sentence and a Show button are (Show asks for the fingerprint or PIN, as on
 * Brain's other private lists). While the lists are hidden the picker is not
 * offered and a save is refused ([JarvisRuntime.progressBalanceSave]).
 *
 * Nothing here is remembered beyond the screen (plain `remember`, no saved
 * state, nothing on disk), nothing is read aloud, and a PC without these
 * routes simply shows nothing.
 */
@Composable
internal fun ProgressSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var heat by remember { mutableStateOf<Progress.Heat?>(null) }
    var balance by remember { mutableStateOf<Progress.Balance?>(null) }
    var heatMissing by remember { mutableStateOf(false) }
    var balanceMissing by remember { mutableStateOf(false) }
    var heatProblem by remember { mutableStateOf<String?>(null) }
    var balanceProblem by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    // "Chart saved." / "Chart cleared." after a save, in the desktop's own words.
    var savedNote by remember { mutableStateOf<String?>(null) }
    val picks = remember { mutableStateListOf<Progress.Pick>() }

    LaunchedEffect(reads, privateHidden) {
        // The picker closes when the lists become hidden; it does not come back stale.
        if (privateHidden) editing = false
        when (val r = JarvisRuntime.progressActivity(Progress.WEEKS_DEFAULT)) {
            is ApiResult.Ok -> {
                val reply = r.value
                val parsed = if (reply.code in 200..299) reply.body?.let { Progress.parseHeat(it) } else null
                when {
                    parsed != null -> {
                        heat = if (privateHidden && parsed.keepOnScreen) Progress.blankedHeat(parsed) else parsed
                        heatMissing = false
                        heatProblem = null
                    }
                    Progress.isMissing(reply) -> {
                        heat = null
                        heatMissing = true
                        heatProblem = null
                    }
                    else -> heatProblem = Progress.readProblem(reply)
                }
            }
            is ApiResult.Failed -> heatProblem = JarvisRuntime.noticeFor(r.error)
        }
        when (val r = JarvisRuntime.progressBalance()) {
            is ApiResult.Ok -> {
                val reply = r.value
                val parsed = if (reply.code in 200..299) reply.body?.let { Progress.parseBalance(it) } else null
                when {
                    parsed != null -> {
                        balance = if (privateHidden) Progress.blankedBalance(parsed) else parsed
                        balanceMissing = false
                        balanceProblem = null
                    }
                    Progress.isMissing(reply) -> {
                        balance = null
                        balanceMissing = true
                        balanceProblem = null
                    }
                    else -> balanceProblem = Progress.readProblem(reply)
                }
            }
            is ApiResult.Failed -> balanceProblem = JarvisRuntime.noticeFor(r.error)
        }
    }

    // A PC without these routes: the section is simply not shown.
    if (heatMissing && balanceMissing) return

    // The picker is offered only while nothing is hidden (its names would be blanked).
    val showEditor = editing && Progress.canEdit(privateHidden)

    Section(Progress.w("title"), trailing = { Quiet(Progress.w("refresh"), onClick = { reads += 1 }) }) {
        Plate {
            val h = heat
            val b = balance

            // ------------------------------------------------ activity ----
            if (!heatMissing) {
                Text(Progress.w("heat_title"), style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
                Text(Progress.w("heat_under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Gap(8)
                when {
                    h == null -> Text(
                        heatProblem?.let { Progress.readFailedLine(it) } ?: "Reading…",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (heatProblem != null) chrome.warnInk else chrome.textLo,
                    )
                    Progress.hiddenOnly(privateHidden, h.keepOnScreen) -> HiddenLine(
                        h.hiddenWords, showPrivateBusy, onShowPrivate,
                    )
                    else -> ActivityGrid(h)
                }
            }

            // ------------------------------------------------ balance ----
            if (!balanceMissing) {
                if (!heatMissing) Gap(18)
                Text(Progress.w("balance_title"), style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
                Text(Progress.w("balance_under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Gap(8)
                when {
                    b == null -> Text(
                        balanceProblem?.let { Progress.readFailedLine(it) } ?: "Reading…",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (balanceProblem != null) chrome.warnInk else chrome.textLo,
                    )
                    showEditor -> BalanceEditor(
                        b = b,
                        picks = picks,
                        canAct = canAct,
                        busy = busy,
                        said = said,
                        onSave = {
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    val count = picks.size
                                    val out = JarvisRuntime.progressBalanceSave(Progress.saveBody(picks.toList()))
                                    if (out.ok && out.balance != null) {
                                        balance = out.balance
                                        editing = false
                                        savedNote = Progress.savedLine(count)
                                    } else {
                                        // Refused: nothing changed, the sentence stays beside the picker as sent.
                                        said = out.said
                                    }
                                } finally {
                                    busy = false
                                }
                            }
                        },
                        onCancel = {
                            editing = false
                            said = null
                        },
                    )
                    else -> {
                        if (Progress.hiddenOnly(privateHidden, b.keepOnScreen)) {
                            HiddenLine(b.hiddenWords, showPrivateBusy, onShowPrivate)
                        } else {
                            BalanceView(b)
                            if (b.words.isNotBlank()) {
                                Gap(4)
                                Text(b.words, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                            }
                        }
                        savedNote?.let {
                            Gap(4)
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid, modifier = Modifier.liveStatus())
                        }
                        if (Progress.canEdit(privateHidden)) {
                            Gap(6)
                            Quiet(Progress.w("balance_edit"), onClick = {
                                picks.clear()
                                picks.addAll(Progress.picksFrom(b))
                                said = null
                                savedNote = null
                                editing = true
                            })
                        }
                    }
                }
            }
        }
    }
}

/** A picture the PC marked private, while the lists are hidden: only its sentence and Show. */
@Composable
private fun HiddenLine(words: String, busy: Boolean, onShow: () -> Unit) {
    val chrome = LocalChrome.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            words, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        Quiet(if (busy) "Checking…" else Progress.w("show"), enabled = !busy, onClick = onShow)
    }
}

// ============================================================ activity ====

@Composable
private fun ActivityGrid(h: Progress.Heat) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    var tapped by remember(h) { mutableStateOf<String?>(null) }
    val rects = remember(h) { Progress.heatRects(h.days) }
    val rows = remember(h) { Progress.weekRows(h) }
    val widthDp = Progress.heatWidth(h.weeks)

    Box(Modifier.width(widthDp.dp).height(Progress.HEAT_HEIGHT.dp)) {
        // The picture: the Canvas is described by the PC's own summary.
        Canvas(
            Modifier
                .size(widthDp.dp, Progress.HEAT_HEIGHT.dp)
                .semantics { contentDescription = h.summary }
                .pointerInput(h) {
                    // Tap a day to read its words under the grid.
                    detectTapGestures { at ->
                        val u = 1.dp.toPx()
                        tapped = Progress.cellAt((at.x / u).toDouble(), (at.y / u).toDouble())
                            ?.let { (col, row) -> Progress.dayWords(h, col, row) }
                    }
                },
        ) {
            val cell = Progress.CELL.dp.toPx()
            val round = CornerRadius(3.dp.toPx())
            val outline = Stroke(width = 1.dp.toPx())
            for (r in rects) {
                val at = Offset(r.x.dp.toPx(), r.y.dp.toPx())
                if (r.level <= 0) {
                    // A quiet day: no fill, only the neutral outline.
                    drawRoundRect(chrome.hairlineStrong, at, Size(cell, cell), round, outline)
                } else {
                    drawRoundRect(chrome.surface2, at, Size(cell, cell), round)
                    drawRoundRect(accent.copy(alpha = Progress.alphaFor(r.level)), at, Size(cell, cell), round)
                }
            }
        }
        // One focusable strip per week for TalkBack, laid over that week's column.
        // They draw nothing and take no touch of their own (a finger on the grid
        // is the Canvas's tap, whole grid, far over 48 dp each way). Each strip
        // reads its week, and its actions menu lists that week's days, one action
        // per day: choosing one puts that day's words under the grid, the same as
        // a tap does - so every day is reachable without touching the tiny cells.
        Box(Modifier.size(widthDp.dp, Progress.HEAT_HEIGHT.dp)) {
            rows.forEachIndexed { i, row ->
                val col = h.columns.sortedBy { it.col }.getOrNull(i)?.col ?: i
                val days = Progress.weekDays(h, col)
                Box(
                    Modifier
                        .offset(x = (col * Progress.STEP).dp)
                        .size(Progress.CELL.dp, Progress.HEAT_HEIGHT.dp)
                        .semantics {
                            contentDescription = row.text
                            customActions = days.map { (_, words) ->
                                CustomAccessibilityAction(words) {
                                    tapped = words
                                    true
                                }
                            }
                        },
                )
            }
        }
    }

    Gap(6)
    // The legend: five swatches, no words. Decorative.
    Canvas(
        Modifier
            .size((5 * Progress.STEP - Progress.GAP).dp, Progress.CELL.dp)
            .clearAndSetSemantics { },
    ) {
        val cell = Progress.CELL.dp.toPx()
        val round = CornerRadius(3.dp.toPx())
        for (level in 0..4) {
            val at = Offset((level * Progress.STEP).dp.toPx(), 0f)
            if (level == 0) {
                drawRoundRect(chrome.hairlineStrong, at, Size(cell, cell), round, Stroke(width = 1.dp.toPx()))
            } else {
                drawRoundRect(chrome.surface2, at, Size(cell, cell), round)
                drawRoundRect(accent.copy(alpha = Progress.alphaFor(level)), at, Size(cell, cell), round)
            }
        }
    }

    Gap(6)
    Text(h.words, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
    tapped?.let {
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid, modifier = Modifier.liveStatus())
    }
    Text(
        h.note.ifBlank { Progress.w("heat_undated") },
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textLo,
    )
}

// ============================================================= balance ====

@Composable
private fun BalanceView(b: Progress.Balance) {
    val chrome = LocalChrome.current
    if (b.drawable) {
        RadarPicture(b)
        Gap(6)
    }
    // The list under the picture: one row per area, in the order picked. It is the
    // text for a screen reader, and it holds every value. No total, no ranking.
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        for (a in b.axes) {
            Column(Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}) {
                Text(Progress.axisLine(a), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                if (a.keepOnScreen) {
                    Text(Progress.w("private"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
        }
    }
}

/** The radar: rings, spokes, the shape and its dots on a Canvas, labels beside the spokes. Decorative. */
@Composable
private fun RadarPicture(b: Progress.Balance) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radar = remember(b) { Progress.radar(b.axes.map { it.fraction }) }
    // The contract's 260 square sits inside a wider box so the labels beside the
    // spokes have room; every label is placed from the contract's own x, y and anchor.
    val padX = Progress.RADAR_PAD_X
    val padY = 12

    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
        Box(
            Modifier
                .size((Progress.RADAR_SIZE + 2 * padX).dp, (Progress.RADAR_SIZE + 2 * padY + 8).dp)
                .clearAndSetSemantics { },
        ) {
            Canvas(Modifier.offset(x = padX.dp, y = padY.dp).size(Progress.RADAR_SIZE.dp)) {
                val u = 1.dp.toPx()
                fun at(x: Double, y: Double) = Offset(x.toFloat() * u, y.toFloat() * u)
                val centre = at(radar.center.x, radar.center.y)
                val last = radar.rings.size - 1
                radar.rings.forEachIndexed { i, r ->
                    if (i == last) {
                        // The outer ring is the target: dashed amber, like a benchmark's target line.
                        drawCircle(
                            chrome.warnMark, radius = r.toFloat() * u, center = centre,
                            style = Stroke(
                                width = 1.5.dp.toPx(),
                                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())),
                            ),
                        )
                    } else {
                        drawCircle(chrome.hairline, radius = r.toFloat() * u, center = centre, style = Stroke(1.dp.toPx()))
                    }
                }
                for (s in radar.spokes) {
                    drawLine(chrome.hairline, centre, at(s.x, s.y), 1.dp.toPx())
                }
                if (radar.polygon.size >= Progress.AXES_MIN) {
                    val shape = Path()
                    radar.polygon.forEachIndexed { i, v ->
                        val p = at(v.x, v.y)
                        if (i == 0) shape.moveTo(p.x, p.y) else shape.lineTo(p.x, p.y)
                    }
                    shape.close()
                    drawPath(shape, accent.copy(alpha = 0.20f))
                    drawPath(shape, accent, style = Stroke(width = 2.dp.toPx()))
                }
                for (v in radar.polygon) {
                    if (v.dot) {
                        // Nothing to measure yet: a small hollow circle in the middle, never a zero.
                        drawCircle(accent, radius = 4.dp.toPx(), center = centre, style = Stroke(1.5.dp.toPx()))
                    } else {
                        drawCircle(accent, radius = 3.dp.toPx(), center = at(v.x, v.y))
                    }
                }
            }
            b.axes.forEachIndexed { i, a ->
                val spot = radar.labels.getOrNull(i) ?: return@forEachIndexed
                // A column that never reaches past the picture's box: narrower at 3 and 9
                // o'clock, where a long value wraps onto more lines instead of running off.
                val box = Progress.labelBox(spot, padX)
                val align = when (spot.anchor) {
                    "start" -> TextAlign.Start
                    "end" -> TextAlign.End
                    else -> TextAlign.Center
                }
                Column(
                    Modifier
                        .offset(x = (box.left + padX).dp, y = (spot.y + padY - 12).dp)
                        .width(box.width.dp),
                ) {
                    Text(
                        a.short,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                        textAlign = align,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        if (a.valueWords.isNotBlank()) a.valueWords else Progress.w("no_numbers"),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textHi,
                        textAlign = align,
                        maxLines = Progress.valueLines(spot),
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

@Composable
private fun BalanceEditor(
    b: Progress.Balance,
    picks: androidx.compose.runtime.snapshots.SnapshotStateList<Progress.Pick>,
    canAct: Boolean,
    busy: Boolean,
    said: String?,
    onSave: () -> Unit,
    onCancel: () -> Unit,
) {
    val chrome = LocalChrome.current

    Text(Progress.w("balance_edit"), style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
    Text(Progress.w("balance_limit"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (b.choices.isEmpty()) {
        Gap(6)
        Text(Progress.w("no_choices"), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    for (c in b.choices) {
        val index = picks.indexOfFirst { it.kind == c.kind && it.ref == c.ref }
        val ticked = index >= 0
        val tickable = Progress.choiceTickable(c)
        Gap(8)
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(c.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                if (c.projectName.isNotBlank()) {
                    Text(c.projectName, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
            Toggle(
                checked = ticked,
                onCheckedChange = { on ->
                    // The chart keeps its order; a new tick goes after it (Progress.toggled).
                    val next = Progress.toggled(picks.toList(), c.kind, c.ref, on)
                    picks.clear()
                    picks.addAll(next)
                },
                // The 9th cannot be ticked; a ticked one can always be unticked.
                enabled = !busy && tickable && (ticked || Progress.canPickMore(picks.size)),
                modifier = Modifier.semantics { contentDescription = c.name },
            )
        }
        if (ticked) {
            TextInput(
                value = picks[index].label,
                onValueChange = { text ->
                    val at = picks.indexOfFirst { it.kind == c.kind && it.ref == c.ref }
                    if (at >= 0) picks[at] = picks[at].copy(label = Progress.clipLabel(text))
                },
                label = Progress.w("balance_rename"),
                placeholder = c.name,
            )
        }
    }

    Gap(10)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Primary(
            Progress.saveLabel(picks.size),
            enabled = canAct && !busy && Progress.canSave(picks.size),
            busy = busy,
            onClick = onSave,
        )
        Quiet("Cancel", enabled = !busy, onClick = onCancel)
    }
    if (!canAct) {
        JarvisRuntime.actionBlocker()?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    said?.let {
        Gap(6)
        // The PC's own sentence, exactly as sent.
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk, modifier = Modifier.liveStatus())
    }
}
