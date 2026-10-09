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
import com.jarvis.client.net.HandoffFront
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * What a captcha does about the browser window it is blocking ([HandoffFront],
 * backend/jarvis_handoff_front.py; the owner's decision of 2026-10-09: "1 by
 * default with the option for 2 in the settings of Jarvis"). When a captcha or
 * a sign-in page blocks the browser window Jarvis is driving:
 *
 *  * "Leave it where it is" (the DEFAULT, and the narrower one): the window is
 *    not touched - it keeps its size, its place and whatever is in front of it -
 *    and the PC says which window Jarvis is stuck on, so the owner solves it
 *    there when they are ready;
 *  * "Bring it to the front": that one window is raised and activated the moment
 *    Jarvis is stuck. It takes the owner's screen and their keyboard away from
 *    whatever they were doing, so choosing it is ONE approval card on the PC
 *    with Windows Hello. Going back to leaving the window alone is instant,
 *    from either app.
 *
 * This phone shows what the PC says and nothing more - the two choice labels and
 * their lines, which is chosen now, a card waiting, and the PC's own `why` line
 * when its settings file is damaged. It never raises a window itself and never
 * pictures anything. The two-choice row is the same shape "How Jarvis talks"
 * already uses: the chosen one marked "(in use)" and a "Use this" on the other.
 *
 * @param canAct the link is up and fresh: choosing "Bring it to the front" waits
 *   for it. Choosing "Leave it where it is" never does - it touches no window.
 */
@Composable
internal fun HandoffFrontSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<HandoffFront.View?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = queue.any { it.action == HandoffFront.ACTION }
    // A card leaving the queue (approved, denied or expired) re-reads the
    // setting, so the lines say what really happened.
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.handoffFrontSettings()) {
            is ApiResult.Ok -> {
                panel = HandoffFront.view(r.value)
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    val waiting = cardWaiting || panel?.waiting == true
    Section(HandoffFront.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(
                HandoffFront.DETAIL,
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
                    HandoffFront.UNREAD,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                else -> {
                    HandoffFront.MODES.forEach { id ->
                        Gap(6)
                        val chosen = id == p.mode
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(
                                if (chosen) "${HandoffFront.LABELS[id].orEmpty()} (in use)"
                                else HandoffFront.LABELS[id].orEmpty(),
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            if (!chosen) {
                                // "Leave it where it is" is never held on a stale
                                // link; bringing the window forward waits for a
                                // fresh one (rule 4).
                                val loosening = id != HandoffFront.LEAVE_IN_PLACE
                                Quiet(
                                    "Use this",
                                    enabled = !busy && !(loosening && (!canAct || waiting)),
                                    onClick = {
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                said = JarvisRuntime.setHandoffFront(id)
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
                            HandoffFront.HELP[id].orEmpty(),
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                    Gap(6)
                    Text(
                        when {
                            busy -> HandoffFront.ASKING
                            waiting -> HandoffFront.WAITING_LINE
                            else -> p.line
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = if (waiting) chrome.warnInk else chrome.textMid,
                    )
                    p.why.takeIf { it.isNotEmpty() && p.line != it }?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                    }
                    // The reason is on the screen: bringing the window forward
                    // always asks for approval on the PC, and waits for a fresh
                    // link.
                    Text(
                        HandoffFront.OPENS_WINDOWS_HELLO,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    if (!canAct && !p.raises) {
                        Text(
                            HandoffFront.WAITING_LINK,
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
