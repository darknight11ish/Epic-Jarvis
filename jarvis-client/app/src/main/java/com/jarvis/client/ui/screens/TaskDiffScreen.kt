package com.jarvis.client.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.net.Projects
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome

/**
 * One app task, opened (docs/APPS-IN-PROJECTS-DESIGN.md section 5): its files,
 * then the WHOLE change in pages ([Projects.diffPages] - a change is at most
 * 60,000 characters, and every line of it is on some page), then Merge and
 * Discard.
 *
 * Merge stays shut until the last page has been shown ([Projects.mergeBlock]):
 * the owner's "after the whole change has been shown". It only asks the PC to
 * raise ONE approval card; the card is decided in the approval queue with the
 * fingerprint or PIN - never here, never from the widget or a notification.
 * Discard asks "are you sure?" first.
 *
 * Lines are separate plain [Text]s (never the whole diff as one), coloured by
 * their first character, with a sideways scroll instead of wrapping.
 */
@Composable
internal fun TaskView(
    p: Projects.Project,
    app: Projects.AppInfo,
    detail: Projects.TaskDetail,
    canAct: Boolean,
    busy: Boolean,
    change: Change,
    onClose: () -> Unit,
) {
    val chrome = LocalChrome.current
    val t = detail.summary
    val key = "${t.task}:${detail.diff.length}:${detail.diff.hashCode()}"
    val pages = remember(key) { Projects.diffPages(detail.diff) }
    var page by remember(key) { mutableIntStateOf(0) }
    var furthest by remember(key) { mutableIntStateOf(0) }
    var confirmDiscard by remember(t.task) { mutableStateOf(false) }

    fun goTo(n: Int) {
        page = n.coerceIn(0, (pages.size - 1).coerceAtLeast(0))
        if (page > furthest) furthest = page
    }

    Quiet("← ${Projects.aw("task_back")}", onClick = onClose)
    Text(t.title.ifBlank { "Untitled task" }, style = MaterialTheme.typography.titleMedium, color = chrome.textHi)
    Text(Projects.changeCounts(t), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    Text(Projects.sourceWords(t.source), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (t.olderMain) {
        Text(Projects.aw("app_older"), style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }

    if (detail.list.isNotEmpty()) {
        Gap(8)
        Text(Projects.aw("task_files").uppercase(), style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo)
        detail.list.forEach { f ->
            Text("${f.path}  (+${f.added.ifBlank { "0" }} -${f.removed.ifBlank { "0" }})",
                style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }

    Gap(8)
    if (detail.refused.isNotBlank()) {
        Text(detail.refused, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    } else if (detail.tooBig) {
        Text(Projects.aw("task_too_big"), style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    } else if (pages.isEmpty()) {
        Text(Projects.aw("task_none"), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    } else {
        Text(Projects.aw("task_read"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(
            Projects.fill(Projects.aw("task_page"), "n" to (page + 1), "total" to pages.size),
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textHi,
            modifier = Modifier.liveStatus(),
        )
        Gap(4)
        Column(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            for (line in pages[page.coerceIn(0, pages.size - 1)]) {
                Text(
                    text = line.text.ifEmpty { " " },
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 12.sp,
                    softWrap = false,
                    color = lineColour(line.kind),
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(Projects.aw("task_prev"), enabled = page > 0, onClick = { goTo(page - 1) })
            Quiet(Projects.aw("task_next"), enabled = page < pages.size - 1, onClick = { goTo(page + 1) })
        }
    }

    Gap(8)
    val block = Projects.mergeBlock(
        detail = detail,
        pageCount = pages.size,
        furthestShown = furthest,
        cardWaitingForApp = app.mergeWaiting,
        canAct = canAct,
    )
    Primary(
        Projects.aw("merge"),
        enabled = block == null && !busy,
        busy = busy,
        onClick = {
            change(
                "app_task_merge",
                Projects.writePath("app_task_merge", p.id, task = t.task),
                "{}",
                "Done.",
                false,
                null,
            ) {}
        },
    )
    Text(block ?: Projects.aw("merge_hint"), style = MaterialTheme.typography.labelSmall,
        color = if (block != null) chrome.textLo else chrome.textMid)

    Gap(6)
    Quiet(Projects.aw("discard"), color = chrome.badInk, enabled = canAct && !busy,
        onClick = { confirmDiscard = true })
    if (confirmDiscard) {
        Text(Projects.fill(Projects.aw("discard_q"), "title" to t.title.ifBlank { "Untitled task" }),
            style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(Projects.aw("discard_yes"), color = chrome.badInk, enabled = canAct && !busy, onClick = {
                confirmDiscard = false
                change(
                    "app_task_discard",
                    Projects.writePath("app_task_discard", p.id, task = t.task),
                    "{}",
                    "Discarded.",
                    false,
                    null,
                ) { out -> if (out.changed) onClose() }
            })
            Quiet(Projects.aw("discard_no"), onClick = { confirmDiscard = false })
        }
    }
}

@Composable
private fun lineColour(kind: Projects.DiffKind): Color {
    val chrome = LocalChrome.current
    return when (kind) {
        Projects.DiffKind.ADDED -> chrome.okInk
        Projects.DiffKind.REMOVED -> chrome.badInk
        Projects.DiffKind.HUNK -> chrome.textLo
        Projects.DiffKind.META -> chrome.textHi
        Projects.DiffKind.CONTEXT -> chrome.textMid
    }
}
