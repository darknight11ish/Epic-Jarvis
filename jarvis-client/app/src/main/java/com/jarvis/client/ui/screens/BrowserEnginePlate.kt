package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.BrowserEngine
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The windowless browser (Obscura) ([BrowserEngine], docs/JARVIS-API.md section
 * 97; the owner's decision, 2026-09-29): let Jarvis choose a browser with no
 * window, instead of the visible one, for plain web reading. OFF by default, ON
 * is one approval card on the PC (a new program on the PC that reaches the web),
 * OFF is instant - the same shape as [ScreenPictureSection]. A second control
 * picks which browser Jarvis uses by default (Automatic, Visible, Headless).
 *
 * This phone shows what the PC says and nothing more: the state line, the
 * install status, the honest stealth line and the one PowerShell line the owner
 * pastes on the PC. It never runs a browser, sees a web page or holds a proxy
 * or an address - there is no such field, and none can be added.
 *
 * @param canAct the link is up and fresh: turning the switch ON, or picking a
 *   mode, waits for it.
 */
@Composable
internal fun BrowserEngineSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<BrowserEngine.Panel?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = BrowserEngine.cardWaiting(queue.map { it.action })
    // A card leaving the queue (approved, denied or expired) re-reads the
    // switch, so the line says what really happened.
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.browserEngineSettings()) {
            is ApiResult.Ok -> {
                panel = BrowserEngine.panel(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                unsupported = BrowserEngine.missing(r.error)
                readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(BrowserEngine.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            if (unsupported) {
                Text(
                    BrowserEngine.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            } else {
                EngineBody(
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
                                    said = JarvisRuntime.setBrowserEngine(want)
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        }
                    },
                    onMode = { mode ->
                        busy = true
                        said = null
                        scope.launch {
                            try {
                                said = JarvisRuntime.setBrowserEngineMode(mode)
                            } finally {
                                busy = false
                                reads += 1
                            }
                        }
                    },
                    onCopy = { line -> clipboard.setText(AnnotatedString(line)) },
                )
            }
        }
    }
}

/** The plate's body: the words, the switch, the PC's line, the mode choice and the one line to paste. */
@Composable
private fun EngineBody(
    panel: BrowserEngine.Panel?,
    readError: String?,
    said: String?,
    busy: Boolean,
    cardWaiting: Boolean,
    canAct: Boolean,
    onChange: (Boolean) -> Unit,
    onMode: (String) -> Unit,
    onCopy: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    Text(BrowserEngine.TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Text(BrowserEngine.SUBTITLE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    Gap(4)
    Text(BrowserEngine.DETAIL, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    Gap(8)
    SwitchRow(
        title = BrowserEngine.SWITCH,
        detail = null,
        // Waiting shows the switch ON, so it can be turned back off (which takes
        // the request back). The line under it says it is only waiting, never
        // that it is on.
        checked = (panel?.checked == true) || cardWaiting,
        enabled = !busy && when {
            cardWaiting -> true
            panel == null -> false
            panel.obscura -> true
            else -> canAct
        },
        onChange = onChange,
    )
    // The reason is on the screen: turning it ON waits for a fresh link to the PC.
    if (!cardWaiting && panel != null && !panel.obscura && !canAct) {
        Text(
            BrowserEngine.WAITING_LINK,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk,
        )
    }
    Text(
        when {
            busy -> "Asking your PC…"
            cardWaiting -> BrowserEngine.waitingLine()
            else -> panel?.line ?: BrowserEngine.UNREAD
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
    if (panel != null && panel.status.isNotEmpty()) {
        Gap(4)
        Text(panel.status, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    if (panel != null && panel.installLine.isNotEmpty() && panel.needsInstall) {
        Gap(8)
        Text(BrowserEngine.STEPS_TITLE, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        Gap(4)
        SelectionContainer {
            Text(
                panel.installLine,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Quiet(BrowserEngine.COPY, onClick = { onCopy(panel.installLine) })
        Gap(4)
        Text(BrowserEngine.STEPS_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    Gap(8)
    Text(BrowserEngine.STEALTH, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    if (panel != null) {
        Gap(10)
        Text(BrowserEngine.MODE_TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
        if (!panel.checked) {
            Text(
                BrowserEngine.MODE_NOTE,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
        BrowserEngine.MODES.forEach { id ->
            Gap(6)
            val chosen = id == panel.mode
            Row(verticalAlignment = Alignment.CenterVertically) {
                // "(in use)" as well as the colour: not by colour alone.
                val label = BrowserEngine.MODE_LABELS[id].orEmpty()
                Text(
                    if (chosen) "$label (in use)" else label,
                    style = MaterialTheme.typography.titleSmall,
                    color = if (chosen) chrome.okInk else chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                if (!chosen) {
                    Quiet("Use this", enabled = canAct && !busy, onClick = { onMode(id) })
                }
            }
            Text(
                BrowserEngine.MODE_HELP[id].orEmpty(),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
    said?.let {
        Gap(4)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}
