package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.Modifier
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.AsksFirst
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "What asks first" on Mind ([AsksFirst], the owner's decisions of
 * 2026-09-26) - the desktop's Settings -> What asks first, in the same words.
 *
 * Every action Jarvis can take and whether it asks first, grouped, in the
 * PC's words. On the phone:
 *  - "Ask me first" can be turned ON (stricter) for the short safe list: at
 *    once, never held on a stale link;
 *  - it cannot be turned OFF here: loosening is the PC's alone (one card plus
 *    Windows Hello), and the PC refuses it from the phone anyway. The row's
 *    note says where to do it;
 *  - "Lights, plugs and fans without a card": ON is one approval card on the
 *    PC, held on a stale link; OFF is at once.
 */
@Composable
internal fun AsksFirstSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<AsksFirst.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    // A card answered or raised - on either app - may have changed a tier or
    // the lights setting, so the queue changing reads it again, as the
    // desktop's Settings does (onQueue).
    val queue by JarvisRuntime.pending.collectAsState()
    val queueKey = queue.map { it.id }

    LaunchedEffect(reads, queueKey) {
        when (val r = JarvisRuntime.asksFirst()) {
            is ApiResult.Ok -> {
                val v = AsksFirst.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (AsksFirst.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun change(block: suspend () -> String) {
        busy = true
        said = null
        scope.launch {
            try {
                said = block()
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    Section(AsksFirst.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(AsksFirst.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            val err = readError
            when {
                missing -> Text(AsksFirst.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't ask Jarvis what asks first: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    v.groups.forEach { g ->
                        Gap(12)
                        Text(g.title, style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid)
                        g.rows.forEach { r ->
                            Gap(6)
                            Column {
                                Text(AsksFirst.heading(r), style = MaterialTheme.typography.titleSmall,
                                    color = chrome.textHi)
                                if (r.note.isNotEmpty()) {
                                    Text(r.note, style = MaterialTheme.typography.bodySmall,
                                        color = chrome.textMid)
                                }
                                AsksFirst.switchView(r, v)?.let { sw ->
                                    SwitchRow(
                                        title = AsksFirst.SWITCH_LABEL,
                                        detail = null,
                                        checked = sw.checked,
                                        // ON only: stricter, never held.
                                        enabled = !busy && sw.enabled,
                                        onChange = { want ->
                                            if (want) change { JarvisRuntime.makeAskFirst(r.action) }
                                        },
                                    )
                                    sw.lines.forEach {
                                        Text(it, style = MaterialTheme.typography.labelSmall,
                                            color = if (it == AsksFirst.WAITING) chrome.warnInk else chrome.textMid)
                                    }
                                }
                                if (r.lights) {
                                    val lv = AsksFirst.lightsView(v.lights, canAct)
                                    if (lv.show) {
                                        SwitchRow(
                                            title = AsksFirst.LIGHTS_LABEL,
                                            detail = AsksFirst.LIGHTS_DETAIL,
                                            checked = lv.checked,
                                            enabled = !busy && lv.canChange,
                                            onChange = { want ->
                                                change { JarvisRuntime.setLightsWithoutCard(want) }
                                            },
                                        )
                                        lv.lines.forEach {
                                            Text(it, style = MaterialTheme.typography.labelSmall,
                                                color = if (it == AsksFirst.LIGHTS_WAITING) chrome.warnInk else chrome.textMid)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            (if (busy) "Asking your PC…" else said)?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}
