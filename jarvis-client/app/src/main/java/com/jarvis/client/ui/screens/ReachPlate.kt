package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
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
import com.jarvis.client.net.Reach
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "What Jarvis can reach" on Mind ([Reach], the Muse audit, 2026-09-25) -
 * the desktop's Settings -> "What Jarvis can reach", in the same words: on
 * the phone, settings and status for a PC feature live on Mind.
 *
 * Every way Jarvis can reach something outside itself, whether each is on,
 * where it goes (a host name only) and whether it asks first, then the tools
 * the AI model is offered. The PC writes every word of it from its settings;
 * this shows them as they are.
 *
 * A read: there is nothing to change here, so it is shown on a stale link
 * too, with nothing to hold. Each setting is changed where it lives.
 */
@Composable
internal fun ReachSection() {
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Reach.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.reach()) {
            is ApiResult.Ok -> {
                val v = Reach.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Reach.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Reach.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Reach.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            val err = readError
            when {
                missing -> Text(Reach.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't ask Jarvis what it can reach: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    v.rows.forEach { r ->
                        Gap(8)
                        Column {
                            Text(Reach.heading(r), style = MaterialTheme.typography.titleSmall,
                                color = if (r.on) chrome.okInk else chrome.textHi)
                            Reach.lines(r, v).forEach { line ->
                                Text(line, style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textMid)
                            }
                        }
                    }
                    Gap(14)
                    Text(v.toolsTitle, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    if (v.tools.isEmpty()) {
                        Text(v.toolsNone, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    } else {
                        Text(v.tools.joinToString(", ") { it.name },
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    Text(v.everythingElse, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                }
            }
        }
    }
}
