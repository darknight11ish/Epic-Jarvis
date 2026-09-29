package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.selection.SelectionContainer
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ScreenPicture
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * Picture mode for "Look at this" and "Watch with me" ([ScreenPicture],
 * docs/JARVIS-API.md section 96.1; the owner's decision, 2026-09-29): with one
 * graphics card, let a small picture model on the PC's processor also look at
 * the picture of the screen - slowly. OFF by default, ON is one approval card
 * on the PC (a model must be downloaded first), OFF is instant - the same shape
 * as [WatchNotifySwitch].
 *
 * This phone shows what the PC says and nothing more: the state line, the
 * measured seconds per look (never a guessed one) and the one PowerShell line
 * the owner pastes on the PC to install and measure the model. The picture
 * itself never comes through here.
 *
 * @param canAct the link is up and fresh: turning the switch ON waits for it.
 */
@Composable
internal fun ScreenPictureSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<ScreenPicture.Panel?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = ScreenPicture.cardWaiting(queue.map { it.action })
    // A card leaving the queue (approved, denied or expired) re-reads the
    // switch, so the line says what really happened.
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.screenPictureSettings()) {
            is ApiResult.Ok -> {
                panel = ScreenPicture.panel(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                unsupported = ScreenPicture.missing(r.error)
                readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section("Looking at your screen: pictures", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            if (unsupported) {
                Text(
                    ScreenPicture.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            } else {
                PictureBody(
                    panel = panel,
                    readError = readError,
                    said = said,
                    busy = busy,
                    cardWaiting = cardWaiting,
                    canAct = canAct,
                    onChange = { want ->
                        if (!(want && cardWaiting)) {          // never a second ON while one waits
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    said = JarvisRuntime.setScreenPicture(want)
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        }
                    },
                    onCopy = { line -> clipboard.setText(AnnotatedString(line)) },
                )
            }
        }
    }
}

/** The plate's body: the words, the switch, the PC's line, the measured speed and the one line to paste. */
@Composable
private fun PictureBody(
    panel: ScreenPicture.Panel?,
    readError: String?,
    said: String?,
    busy: Boolean,
    cardWaiting: Boolean,
    canAct: Boolean,
    onChange: (Boolean) -> Unit,
    onCopy: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    Text(ScreenPicture.TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Gap(4)
    Text(ScreenPicture.DETAIL, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    Gap(8)
    SwitchRow(
        title = ScreenPicture.SWITCH,
        detail = null,
        // Waiting shows the switch ON, so it can be turned back off (which takes
        // the request back). The line under it says it is only waiting, never
        // that it is on.
        checked = (panel?.checked == true) || cardWaiting,
        enabled = !busy && when {
            cardWaiting -> true
            panel == null -> false
            panel.enabled -> true
            else -> canAct
        },
        onChange = onChange,
    )
    Text(
        when {
            busy -> "Asking your PC…"
            cardWaiting -> ScreenPicture.waitingLine()
            else -> panel?.line ?: ScreenPicture.UNREAD
        },
        style = MaterialTheme.typography.bodySmall,
        color = if (cardWaiting) chrome.warnInk else chrome.textMid,
    )
    readError?.let {
        Text(
            "Couldn't read this switch: $it",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk,
        )
    }
    if (panel != null && panel.measured.isNotEmpty()) {
        Gap(6)
        Text(panel.measured, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    if (panel != null && panel.installLine.isNotEmpty()) {
        Gap(8)
        Text(ScreenPicture.STEPS_TITLE, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        Gap(4)
        SelectionContainer {
            Text(
                panel.installLine,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Quiet(ScreenPicture.COPY, onClick = { onCopy(panel.installLine) })
        Gap(4)
        Text(ScreenPicture.STEPS_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    said?.let {
        Gap(4)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}
