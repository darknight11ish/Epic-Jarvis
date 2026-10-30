package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
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
import com.jarvis.client.LinkState
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.NotificationStyle
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Notification styles" on Brain, under "Notifications from Jarvis"
 * ([NotificationStyle], the owner's ask of 2026-10-30; docs/JARVIS-API.md
 * section 163).
 *
 * The saved styles (Delete, ONE per tap, at once), the previews waiting for
 * Add (Add keeps ONE exactly as shown; Discard drops it), what is live now,
 * and a box to describe a new one in the owner's own typed words. No approval
 * card - the PC's own sentence says why: a style shows nothing new, adds no
 * button and grants nothing. Add and Delete are held on a stale link; making a
 * preview is not (it adds nothing). "Hide memory lists and chat history" hides
 * the style names.
 *
 * This plate is only the LIST and the preview. The drawing is
 * [com.jarvis.client.service.StyledNotification]'s job, and the notifiers'
 * own: this screen never builds a notification.
 */
@Composable
internal fun NotificationStylesSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val link by JarvisRuntime.link.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val canAct = link == LinkState.CONNECTED && !stale
    val security by JarvisRuntime.settings.security.collectAsState()
    val privateHidden = security.privateLists
    val book by JarvisRuntime.notificationStyles.collectAsState()
    val tick by JarvisRuntime.stylesTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var making by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var words by remember { mutableStateOf("") }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.notificationStyleListing()) {
            is ApiResult.Ok -> {
                missing = false
                readError = null
            }
            is ApiResult.Failed -> if (r.error == ApiError.NotFound) {
                missing = true
                readError = null
            } else if (link == LinkState.CONNECTED) {
                readError = JarvisRuntime.noticeFor(r.error)
            } else {
                readError = null
            }
        }
    }

    fun run(block: suspend () -> Pair<Boolean, String>) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = block().second
            } finally {
                busy = false
            }
        }
    }

    fun make() {
        if (making) return
        making = true
        said = null
        scope.launch {
            try {
                val (made, sentence) = JarvisRuntime.notificationStyleDraft(words)
                if (made) words = ""
                said = sentence
            } finally {
                making = false
            }
        }
    }

    Section(NotificationStyle.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(NotificationStyle.DETAIL, style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo)
            Gap(6)
            when {
                missing -> Text(NotificationStyle.MISSING,
                    style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                else -> {
                    val err = readError
                    if (err != null) {
                        Text("Couldn't read styles: $err",
                            style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                        Gap(8)
                    }
                    // ---- What is live right now ----
                    Text(
                        NotificationStyle.liveLine(book),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                        modifier = Modifier.liveStatus(),
                    )
                    Gap(10)

                    if (book.drafts.isNotEmpty()) {
                        Text(NotificationStyle.PREVIEW_TITLE,
                            style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                        book.drafts.forEach { d ->
                            StyleRow(d, privateHidden) {
                                Quiet(NotificationStyle.DISCARD_LABEL, enabled = !busy,
                                    onClick = { run { JarvisRuntime.notificationStyleDiscard(d.id) } })
                                Quiet(NotificationStyle.ADD_LABEL, color = chrome.okInk,
                                    enabled = canAct && !busy,
                                    onClick = { run { JarvisRuntime.notificationStyleAdd(d.id) } })
                            }
                        }
                        if (book.noCard.isNotEmpty()) {
                            Text(book.noCard, style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo)
                        }
                        Gap(10)
                    }
                    if (book.styles.isEmpty()) {
                        Text(NotificationStyle.EMPTY, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    book.styles.forEach { s ->
                        StyleRow(s, privateHidden) {
                            Quiet(NotificationStyle.DELETE_LABEL, color = chrome.badInk,
                                enabled = canAct && !busy,
                                onClick = { run { JarvisRuntime.notificationStyleDelete(s.id) } })
                        }
                    }

                    // ---- Describe a style: the owner's own typed words ----
                    Gap(14)
                    TextInput(
                        value = words,
                        onValueChange = { words = it.take(NotificationStyle.MAX_WORDS) },
                        placeholder = "How they should look, like warm orange, a spark, pulsing",
                    )
                    Quiet(
                        if (making) NotificationStyle.MAKING_LABEL else NotificationStyle.MAKE_LABEL,
                        enabled = !making, onClick = { make() },
                    )
                    Text(NotificationStyle.PHONE_HINT, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                    if (book.noCard.isNotEmpty()) {
                        Text(NotificationStyle.CARD_NOTE,
                            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && !canAct) {
                Text(
                    "Not connected to the desktop, so adding and deleting wait until the link is " +
                        "back. Notifications keep the style this phone last read.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One style or preview: its name, its sentence and its choices, then its buttons. */
@Composable
private fun StyleRow(row: NotificationStyle.Row, privateHidden: Boolean, buttons: @Composable () -> Unit) {
    val chrome = LocalChrome.current
    Gap(10)
    Column(Modifier.fillMaxWidth()) {
        if (privateHidden) {
            Text(NotificationStyle.HIDDEN_WORDS, style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi)
        } else {
            Text(row.name.ifEmpty { "Style" }, style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi)
            if (row.said.isNotEmpty()) {
                Text(row.said, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            row.parts.forEach {
                Text("- $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
        buttons()
    }
}
