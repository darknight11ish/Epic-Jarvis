package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.MemoryCounts
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * How much Jarvis remembers, and whether it is learning - the desktop's
 * Memory pane numbers ([com.jarvis.client.net.MemoryCounts]). Read-only: no
 * learning switch here, and the line under the numbers says why.
 */
@Composable
internal fun MemoryCountsSection() {
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var rows by remember { mutableStateOf<List<Pair<String, String>>?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var learning by remember { mutableStateOf<Boolean?>(null) }
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
                MemoryCounts.learningLine(learning),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}
