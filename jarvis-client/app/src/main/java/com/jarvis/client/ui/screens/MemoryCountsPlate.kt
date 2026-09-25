package com.jarvis.client.ui.screens

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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.MemoryCounts
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * How much Jarvis remembers, and whether it is learning - the desktop's
 * Memory pane numbers ([com.jarvis.client.net.MemoryCounts]) - and the
 * learning switch. Turning it ON raises an approval card on the PC, so it
 * reads "waiting" while that card is in the queue; OFF is immediate.
 *
 * Under it, automatic learning's two switches ([AutoLearnSwitches],
 * docs/JARVIS-API.md section 19) - the same shape - and, after a
 * `memory_saved` event, a quiet "Jarvis remembered N things" line. A count
 * only, never a fact's words - until it is tapped: since 2026-09-25 it opens
 * the facts themselves, read from the PC by id, with Forget beside each
 * ([UsedFactsList]), and "Show everything saved automatically" goes on to
 * the whole list. Hidden like the other memory lists.
 *
 * @param canAct the link is up and fresh: turning a switch ON waits for it.
 * @param onOpenAutoList brings "Saved automatically" into view.
 */
@Composable
internal fun MemoryCountsSection(
    canAct: Boolean = false,
    onOpenAutoList: () -> Unit = {},
    privateHidden: Boolean = false,
    showPrivateBusy: Boolean = false,
    onShowPrivate: () -> Unit = {},
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var rows by remember { mutableStateOf<List<Pair<String, String>>?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var learning by remember { mutableStateOf<Boolean?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val queue by JarvisRuntime.pending.collectAsState()
    val remembered by JarvisRuntime.autoRemembered.collectAsState()
    // The facts the line opened, by id, or null while it is closed.
    var opened by remember { mutableStateOf<List<Long>?>(null) }
    val cardWaiting = MemoryCounts.learningCardWaiting(queue.map { it.action })
    // The card leaving the queue (approved, denied or expired) re-reads the
    // switch, so the line says what really happened.
    LaunchedEffect(cardWaiting) { if (!cardWaiting) reads += 1 }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.memoryStatus()) {
            is ApiResult.Ok -> {
                rows = MemoryCounts.fields(r.value)
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
        learning = JarvisRuntime.memoryLearning()
    }

    Section("What Jarvis remembers", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val shown = rows
            val err = readError
            when {
                shown == null -> Text(
                    if (err != null) "Couldn't read the memory store: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                shown.isEmpty() -> Text(
                    "The memory store reported nothing.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                else -> shown.forEach { (label, value) -> Field(label, value) }
            }
            if (shown != null && err != null) {
                Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                    color = chrome.warnInk)
            }
            Gap(6)
            Text(
                if (cardWaiting) MemoryCounts.waitingLine() else MemoryCounts.learningLine(learning),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            val on = learning
            if (on != null && !cardWaiting) {
                Quiet(
                    if (on) "Stop learning" else "Start learning",
                    enabled = !busy,
                    onClick = {
                        busy = true
                        scope.launch {
                            said = JarvisRuntime.setLearning(!on)
                            busy = false
                            reads += 1
                        }
                    },
                )
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = androidx.compose.ui.Modifier.liveStatus())
            }
            AutoLearnSwitches(canAct = canAct, learningOn = learning, refresh = reads)
            com.jarvis.client.net.AutoLearn.rememberedLine(remembered)?.let { line ->
                Gap(6)
                Quiet(line, onClick = {
                    opened = JarvisRuntime.autoRememberedIds.value.takeIf { it.isNotEmpty() }
                    JarvisRuntime.clearAutoRemembered()
                    if (opened == null) onOpenAutoList()
                })
            }
            opened?.let { ids ->
                Gap(8)
                UsedFactsList(
                    title = com.jarvis.client.net.MemoryUsed.REMEMBERED_TITLE,
                    ids = ids,
                    canAct = canAct,
                    privateHidden = privateHidden,
                    showPrivateBusy = showPrivateBusy,
                    onShowPrivate = onShowPrivate,
                    load = { JarvisRuntime.memoryUsed(it) },
                    forget = { JarvisRuntime.forgetAutoFact(it) },
                )
                Quiet(com.jarvis.client.net.MemoryUsed.SHOW_ALL, onClick = {
                    opened = null
                    onOpenAutoList()
                })
                Quiet("Close", onClick = { opened = null })
            }
        }
    }
}
