package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Spending
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Spending summaries" on the phone ([Spending]; the owner's decision of
 * 2026-09-30, docs/JARVIS-API.md section 100, docs/FINANCE-DESIGN.md part A).
 *
 * Two things live here:
 *  - [SpendingSection], Brain's read-only plate: it says "Set up on the PC"
 *    and lists what the PC has (saved bank layouts, categories, files
 *    waiting for their columns to be checked). NO edit control, no form -
 *    the PC does that (ARCHITECTURE section 8, "One-sided on purpose").
 *  - [SpendingAnswerBlock], the table under a chat answer on Home. Drawn
 *    exactly as the PC sent it: every figure is a plain [Text] of the string
 *    it was given - never computed, rounded, sorted or re-worded. Held in
 *    this composable's memory only (plain `remember`, never
 *    `rememberSaveable`): a rotation refetches it (the PC keeps it two
 *    hours), a restart shows the sentence only. It has no Copy, no Share and
 *    no export, and it is never read aloud (the answer is private).
 */

/** What Home passes down for the table under the answer on screen. */
@Immutable
internal data class SpendingAnswer(
    /** The `: jarvis-table` id of THIS answer, or null when it has no table. */
    val tableId: String?,
    /** "Hide memory lists and chat history" is on: draw the fixed line, fetch nothing. */
    val hidden: Boolean,
    /** `GET /api/chat/table` ([JarvisRuntime.spendingTable]). */
    val load: suspend (String?) -> Spending.Read,
)

/** The table under an answer, or the fixed hidden line in its place. Nothing when there is none. */
@Composable
internal fun SpendingAnswerBlock(spending: SpendingAnswer) {
    val id = spending.tableId ?: return
    if (!Spending.isTableId(id)) return
    if (Spending.hiddenNow(hideLists = spending.hidden, locked = false)) {
        // No fetch, and nothing held: this branch never composes the loader,
        // so a table already fetched is dropped the moment the lists hide.
        val chrome = LocalChrome.current
        Gap(8)
        Text(
            Spending.TABLE_HIDDEN,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        return
    }
    SpendingTableLoader(id, spending.load)
}

@Composable
private fun SpendingTableLoader(id: String, load: suspend (String?) -> Spending.Read) {
    val chrome = LocalChrome.current
    // Plain remember, on purpose: never saved state, never a file.
    var read by remember(id) { mutableStateOf<Spending.Read?>(null) }
    LaunchedEffect(id) { read = load(id) }
    Gap(8)
    when (val r = read) {
        null -> Text(Spending.READING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        is Spending.Read.Gone -> Text(r.message, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        is Spending.Read.Failed -> Text(r.why, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        is Spending.Read.Shown -> SpendingTableView(r.table)
    }
}

/** Width of a column of [chars] characters, growing with the owner's font size so no figure is cut off. */
private fun columnWidth(chars: Int, fontScale: Float, min: Int, max: Int): Dp =
    (chars * 8f * fontScale + 20f).coerceIn(min * fontScale, max * fontScale).dp

@Composable
private fun SpendingTableView(table: Spending.Table) {
    val chrome = LocalChrome.current
    val fontScale = LocalDensity.current.fontScale
    // One horizontal scroll position for every row: drag any row and the whole
    // table moves; the first column stays where it is.
    val scroll = rememberScrollState()
    val widths = remember(table, fontScale) {
        table.columns.indices.map { i ->
            var longest = table.columns[i].label.length
            for (b in table.blocks) for (l in b.rows + b.totals + b.also) {
                val n = l.cells.getOrNull(i)?.length ?: 0
                if (n > longest) longest = n
            }
            if (i == 0) columnWidth(longest, fontScale, 96, 168) else columnWidth(longest, fontScale, 72, 260)
        }
    }

    Column(Modifier.fillMaxWidth()) {
        // Title (strong), then the period (muted). TalkBack gets one summary line.
        Text(
            table.title,
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
            modifier = Modifier.clearAndSetSemantics {
                heading()
                contentDescription = Spending.summary(table)
            },
        )
        if (table.period.isNotBlank()) {
            Text(table.period, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Gap(6)

        table.blocks.forEachIndexed { index, block ->
            if (index > 0) Gap(10)
            if (block.heading.isNotBlank()) {
                Text(
                    block.heading,
                    style = MaterialTheme.typography.labelMedium,
                    color = chrome.textMid,
                    modifier = Modifier.clearAndSetSemantics {
                        heading()
                        contentDescription = block.heading
                    },
                )
            }
            // Column names once, above the rows; TalkBack hears them inside every row instead.
            TableLine(
                cells = table.columns.map { it.label },
                table = table,
                widths = widths,
                scroll = scroll,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                weight = FontWeight.Normal,
                reading = null,
            )
            block.rows.forEach { l ->
                TableLine(l.cells, table, widths, scroll, MaterialTheme.typography.bodySmall, chrome.textHi,
                    FontWeight.Normal, Spending.rowReading(table, l))
            }
            // A rule above the totals; totals in bold.
            if (block.totals.isNotEmpty()) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(chrome.hairlineStrong))
            }
            block.totals.forEach { l ->
                TableLine(l.cells, table, widths, scroll, MaterialTheme.typography.bodySmall, chrome.textHi,
                    FontWeight.Bold, Spending.rowReading(table, l, isTotal = true))
            }
            // Refunds, income, transfers: shown apart from spending, smaller and muted.
            block.also.forEach { l ->
                TableLine(l.cells, table, widths, scroll, MaterialTheme.typography.labelSmall, chrome.textMid,
                    FontWeight.Normal, Spending.rowReading(table, l))
            }
        }

        // Each caveat is already a full sentence: one line each, never joined or reworded.
        if (table.caveats.isNotEmpty()) {
            Gap(8)
            table.caveats.forEach { c ->
                Text(c, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
        }
        Spending.sourcesLine(table)?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}

/**
 * One row of the table: the first column fixed, the rest scrolling sideways
 * on the shared [scroll]. [reading] is what TalkBack says for the whole row
 * (null: the header row, which it skips because every row names its columns).
 */
@Composable
private fun TableLine(
    cells: List<String>,
    table: Spending.Table,
    widths: List<Dp>,
    scroll: androidx.compose.foundation.ScrollState,
    style: androidx.compose.ui.text.TextStyle,
    color: androidx.compose.ui.graphics.Color,
    weight: FontWeight,
    reading: String?,
) {
    Row(
        Modifier.fillMaxWidth().clearAndSetSemantics {
            if (reading != null) contentDescription = reading
        },
        verticalAlignment = androidx.compose.ui.Alignment.Top,
    ) {
        Text(
            cells.firstOrNull().orEmpty(),
            style = style,
            color = color,
            fontWeight = weight,
            modifier = Modifier.width(widths[0]).padding(end = 8.dp, top = 6.dp, bottom = 6.dp),
        )
        Row(Modifier.weight(1f).horizontalScroll(scroll)) {
            for (i in 1 until cells.size) {
                Text(
                    cells[i],
                    style = style,
                    color = color,
                    fontWeight = weight,
                    softWrap = false,
                    textAlign = if (table.columns.getOrNull(i)?.rightAligned == true) TextAlign.End else TextAlign.Start,
                    modifier = Modifier.width(widths[i]).padding(horizontal = 8.dp, vertical = 6.dp),
                )
            }
        }
    }
}

/**
 * Brain -> Spending: read-only. The PC's own words, in the PC's own order:
 * "Set up on the PC", the layouts it has saved (label, columns, what the sign
 * rule means), the files still waiting for their columns to be checked, and
 * the category words. Nothing here can be changed from the phone.
 */
@Composable
internal fun SpendingSection(
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Spending.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.spendingView()) {
            is ApiResult.Ok -> {
                val v = Spending.parseView(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Spending.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Spending.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            when {
                missing -> Text(Spending.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read Spending: $err" else Spending.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(v.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Gap(6)
                    Text(v.pcOnly, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                    if (privateHidden) {
                        // File names and shop words are the owner's own lists.
                        Gap(6)
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Text(
                                "Words hidden. Tap Show and confirm it is you.",
                                style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                                modifier = Modifier.weight(1f),
                            )
                            Quiet(
                                if (showPrivateBusy) "Checking…" else "Show",
                                enabled = !showPrivateBusy, onClick = onShowPrivate,
                            )
                        }
                    } else {
                        Gap(8)
                        if (v.layouts.isEmpty()) {
                            Text(v.emptyProfiles, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                        v.layouts.forEach { l ->
                            Gap(6)
                            Text(l.label, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                            if (l.columns.isNotEmpty()) {
                                Text(l.columns.joinToString(", "), style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid)
                            }
                            if (l.signSentence.isNotBlank()) {
                                Text(l.signSentence, style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid)
                            }
                        }
                        v.waiting.forEach { name ->
                            Gap(6)
                            Text(name, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                            Text(v.needsSetup, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                        }
                        if (v.categories.isNotEmpty()) {
                            Gap(10)
                            v.categories.forEach { c ->
                                Text(
                                    if (c.words.isEmpty()) c.name else c.name + ": " + c.words.joinToString(", "),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid,
                                )
                            }
                        }
                        v.starterNote?.let {
                            Gap(6)
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        // Where the things above are changed (2026-10-08): the
                        // card showed the PC's own layouts and categories and
                        // never said which screen sets them. One plain
                        // sentence, the same voice as Backups' own line - no
                        // control, the PC does the changing.
                        Gap(8)
                        Text(
                            "Nothing here can be changed on the phone: the bank layouts, the shop " +
                                "categories and the folders are set on your PC, in Settings → Spending.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                }
            }
        }
    }
}
