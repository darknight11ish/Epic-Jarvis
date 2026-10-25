package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SandboxExec
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The data and maths sandbox's switch ([SandboxExec], docs/JARVIS-API.md
 * section 142; LM-1C, 2026-10-18): whether the AI model is OFFERED the small
 * read-only Python tool at all. OFF by default, ON is ONE normal approval card
 * on the PC, OFF is instant - the same shape as [ScreenPictureSection] and
 * [BrowserEngineSection].
 *
 * This phone shows what the PC says and nothing more: the state line (which
 * includes what the last card did - denied, timed out, refused) and the one
 * switch. It never runs a script and never sees a file or a piece of data.
 *
 * @param canAct the link is up and fresh: turning the switch ON waits for it.
 */
@Composable
internal fun SandboxSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<SandboxExec.Panel?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.sandboxExecSettings()) {
            is ApiResult.Ok -> {
                panel = SandboxExec.panel(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                unsupported = SandboxExec.missing(r.error)
                readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }
    // While a card waits, read again every 3 s so the switch follows the answer
    // and the line says what the card really did (denied, timed out, approved).
    // This plate cannot watch change_own_config in the approval queue: that
    // action is shared by many settings, so the PC's own `waiting` is the fact.
    //
    // The effect is keyed on `waiting` only to START the loop. It must not be
    // keyed on it for the loop itself: a re-read that still says "waiting"
    // leaves the key unchanged, so the single-shot version ran exactly once and
    // the plate kept the pre-decision panel for ever (the 2026-10-24 round-2
    // audit, M10). `while` keeps reading; the keyed restart only happens when
    // the plate's own composition changes.
    LaunchedEffect(panel?.waiting) {
        while (panel?.waiting == true) {
            delay(3000)
            reads += 1
        }
    }

    Section(SandboxExec.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            if (unsupported) {
                Text(
                    SandboxExec.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            } else {
                SandboxBody(
                    panel = panel,
                    readError = readError,
                    said = said,
                    busy = busy,
                    canAct = canAct,
                    onChange = { want ->
                        if (!(want && panel?.waiting == true)) {   // never a second ON while one waits
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    said = JarvisRuntime.setSandboxExec(want)
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}

/** The plate's body: the words, the switch, the PC's line and what it said. */
@Composable
private fun SandboxBody(
    panel: SandboxExec.Panel?,
    readError: String?,
    said: String?,
    busy: Boolean,
    canAct: Boolean,
    onChange: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Text(SandboxExec.DETAIL, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    Gap(8)
    SwitchRow(
        title = SandboxExec.SWITCH,
        detail = null,
        // Waiting shows the switch ON, so it can be turned back off (which takes
        // the request back). The line under it says it is only waiting, never
        // that it is on.
        checked = panel?.checked == true,
        enabled = !busy && when {
            panel == null -> false
            panel.enabled -> true
            else -> canAct
        },
        onChange = onChange,
    )
    // The reason is on the screen: turning it ON waits for a fresh link to the PC.
    if (panel != null && !panel.enabled && !canAct) {
        Text(
            SandboxExec.WAITING_LINK,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk,
        )
    }
    Text(
        when {
            busy -> "Asking your PC…"
            else -> panel?.line ?: SandboxExec.UNREAD
        },
        style = MaterialTheme.typography.bodySmall,
        color = if (panel?.waiting == true) chrome.warnInk else chrome.textMid,
    )
    if (panel != null && panel.status.isNotEmpty() && panel.status != panel.line) {
        Gap(4)
        Text(panel.status, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    if (panel != null && panel.why.isNotEmpty()) {
        Text(panel.why, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    readError?.let {
        Text(
            "Couldn't read this switch: $it",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk,
        )
    }
    said?.let {
        Gap(4)
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
}
