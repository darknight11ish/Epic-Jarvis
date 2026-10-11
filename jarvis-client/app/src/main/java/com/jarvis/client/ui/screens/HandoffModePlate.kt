package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.HandoffMode
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * How long "Solve it here" stays on offer ([HandoffMode], backend/jarvis_handoff_mode.py;
 * the owner's decision of 2026-10-08: "make this a setting for both options with
 * 1 as the default"). The captcha hand-off shows a live picture of ONE of the
 * owner's browser windows on this phone, over their private network, and this
 * picks how long it keeps offering it when nobody answers:
 *
 *  * "Stop early" (the DEFAULT): about a minute with nobody looking, then the
 *    hand-off ends and the PC says which window Jarvis is stuck on, so the owner
 *    solves it there;
 *  * "Keep offering it": the full 15-minute ceiling, so the owner can pick their
 *    phone up late. That is more exposure for a window that may show the owner's
 *    own account details, so choosing it is ONE approval card on the PC with
 *    Windows Hello. Going back to "Stop early" is instant, from either app.
 *
 * This phone shows what the PC says and nothing more - the two choice labels and
 * their lines, which is chosen now, a card waiting, and the PC's own `why` line
 * when its settings file is damaged. It never pictures anything itself. The
 * two-choice row is the same shape "How Jarvis talks" already uses: the chosen
 * one marked "(in use)" and a "Use this" on the other.
 *
 * @param canAct the link is up and fresh: choosing "Keep offering it" waits for
 *   it. Choosing "Stop early" never does - it only makes Jarvis do less.
 */
@Composable
internal fun HandoffModeSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<HandoffMode.View?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = queue.any { it.action == HandoffMode.ACTION }
    // A card leaving the queue (approved, denied or expired) re-reads the
    // setting, so the lines say what really happened.
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.handoffModeSettings()) {
            is ApiResult.Ok -> {
                panel = HandoffMode.view(r.value)
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    val waiting = cardWaiting || panel?.waiting == true
    Section(HandoffMode.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(
                HandoffMode.DETAIL,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            val p = panel
            when {
                p == null && readError != null -> Text(
                    "Couldn't read it: ${readError.orEmpty()}",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                p == null -> Text(
                    "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                p.available.not() -> Text(
                    HandoffMode.UNREAD,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                else -> {
                    HandoffMode.MODES.forEach { id ->
                        Gap(6)
                        val chosen = id == p.mode
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(
                                if (chosen) "${HandoffMode.LABELS[id].orEmpty()} (in use)"
                                else HandoffMode.LABELS[id].orEmpty(),
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            if (!chosen) {
                                // "Stop early" is never held on a stale link; the
                                // longer choice waits for a fresh one (rule 4).
                                val loosening = id != HandoffMode.STOP_EARLY
                                Quiet(
                                    "Use this",
                                    enabled = !busy && !(loosening && (!canAct || waiting)),
                                    onClick = {
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                said = JarvisRuntime.setHandoffMode(id)
                                            } finally {
                                                busy = false
                                                reads += 1
                                            }
                                        }
                                    },
                                )
                            }
                        }
                        Text(
                            HandoffMode.HELP[id].orEmpty(),
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                    Gap(6)
                    Text(
                        when {
                            busy -> HandoffMode.ASKING
                            waiting -> HandoffMode.WAITING_LINE
                            else -> p.line
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = if (waiting) chrome.warnInk else chrome.textMid,
                    )
                    p.why.takeIf { it.isNotEmpty() && p.line != it }?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                    }
                    // The reason is on the screen: the longer choice always asks
                    // for approval on the PC, and waits for a fresh link.
                    Text(
                        HandoffMode.OPENS_WINDOWS_HELLO,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    if (!canAct && !p.patient) {
                        Text(
                            HandoffMode.WAITING_LINK,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    }
                    p.lastWords.takeIf { it.isNotEmpty() }?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                }
            }
            said?.let {
                Gap(4)
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }
}
