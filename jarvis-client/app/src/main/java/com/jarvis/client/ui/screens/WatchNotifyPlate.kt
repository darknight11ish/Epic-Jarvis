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
import androidx.compose.ui.Modifier
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.WatchNotify
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The smartwatch notification setting ([WatchNotify], docs/JARVIS-API.md;
 * the owner's decision, 2026-09-25, reconfirmed 2026-09-27 Q17): OFF by
 * default (every notification stays on this phone), ON is one approval
 * card on the PC, OFF is instant - the same shape as [AutoLearnSwitches]
 * next to it.
 *
 * There is no Jarvis watch app: turning this on only stops the phone's own
 * notification builders refusing Android's own, already-built-in
 * notification bridging to a paired, compatible smartwatch.
 *
 * @param canAct the link is up and fresh: turning the switch ON waits for it.
 * @param refresh goes up when the plate's own Refresh is pressed.
 */
@Composable
internal fun WatchNotifySwitch(canAct: Boolean, refresh: Int) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var enabled by remember { mutableStateOf<Boolean?>(null) }
    var why by remember { mutableStateOf<String?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = WatchNotify.cardWaiting(queue.map { it.action })
    // A card leaving the queue (approved, denied or expired) re-reads the
    // switch, so the line says what really happened.
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads, refresh) {
        when (val r = JarvisRuntime.watchNotifySettings()) {
            is ApiResult.Ok -> {
                enabled = WatchNotify.enabled(r.value)
                why = WatchNotify.whyLine(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                unsupported = r.error == ApiError.NotFound
                readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    if (unsupported) {
        Text(
            "Your PC's Jarvis does not have the smartwatch notifications setting yet.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        return
    }
    Gap(8)
    SwitchRow(
        title = "Show notifications on a compatible watch",
        detail = "Off by default: every notification (approval cards, timers, reminders, " +
            "\"tell me when\") stays on this phone only.",
        // Waiting shows the switch ON, so it can be turned back off (which
        // takes the request back). The line under it says it is only
        // waiting, never that it is on.
        checked = enabled == true || cardWaiting,
        enabled = !busy && when {
            cardWaiting -> true
            enabled == true -> true
            enabled == false -> canAct
            else -> false
        },
        onChange = { want ->
            if (!(want && cardWaiting)) {          // never a second ON while one waits
                busy = true
                said = null
                scope.launch {
                    try {
                        said = JarvisRuntime.setWatchNotify(want)
                    } finally {
                        busy = false
                        reads += 1
                    }
                }
            }
        },
    )
    Text(
        if (busy) "Asking your PC…" else if (cardWaiting) WatchNotify.waitingLine()
        else WatchNotify.stateLine(enabled),
        style = MaterialTheme.typography.bodySmall,
        color = if (cardWaiting) chrome.warnInk else chrome.textMid,
    )
    readError?.let {
        Text("Couldn't read this switch: $it", style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk)
    }
    why?.let {
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    }
    said?.let {
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}

/**
 * "Notifications" - a section on its own on Brain, holding just the
 * smartwatch switch above. A section of its own (not folded into "What
 * Jarvis remembers") because this has nothing to do with memory: it decides
 * where an already-posted notification is allowed to go.
 */
@Composable
internal fun WatchNotifySection(canAct: Boolean = false) {
    var reads by remember { mutableIntStateOf(0) }
    Section("Notifications", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            WatchNotifySwitch(canAct = canAct, refresh = reads)
        }
    }
}
