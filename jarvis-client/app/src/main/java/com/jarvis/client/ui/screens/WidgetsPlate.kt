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
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisWidgets
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Widgets" on Brain ([JarvisWidgets], the owner's choice of 2026-09-28,
 * the SAFE version) - the desktop's Brain -> Work -> Widgets, in the same
 * words, just below Today.
 *
 * The saved widgets (Delete, ONE per tap, at once), the previews waiting for
 * Add (Add keeps ONE exactly as shown; Discard drops it), a box to describe
 * a new one in the owner's own typed words, and which saved widget each
 * home-screen "Jarvis widget" slot shows. No approval card - the PC's own
 * sentence says why. Add and Delete are held on a stale link; making a
 * preview is not (it adds nothing). "Hide memory lists and chat history"
 * hides the names and parts.
 */
@Composable
internal fun WidgetsSection(canAct: Boolean, privateHidden: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.widgetsTick.collectAsState()
    val slots by JarvisRuntime.settings.homeWidgets.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var listing by remember { mutableStateOf<JarvisWidgets.Listing?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var making by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var words by remember { mutableStateOf("") }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.widgets()) {
            is ApiResult.Ok -> {
                val v = JarvisWidgets.readList(r.value)
                missing = v == null
                listing = v
                readError = null
            }
            is ApiResult.Failed -> if (r.error == ApiError.NotFound) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
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
                val (made, sentence) = JarvisRuntime.widgetDraft(words)
                if (made) words = ""
                said = sentence
            } finally {
                making = false
            }
        }
    }

    Section(JarvisWidgets.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(JarvisWidgets.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = listing
            val err = readError
            when {
                missing -> Text(JarvisWidgets.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read Widgets: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (v.drafts.isNotEmpty()) {
                        Text(JarvisWidgets.PREVIEW_TITLE, style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid)
                        v.drafts.forEach { d ->
                            WidgetRow(d, privateHidden) {
                                Quiet(JarvisWidgets.DISCARD_LABEL, enabled = !busy,
                                    onClick = { run { JarvisRuntime.widgetDiscard(d.id) } })
                                Quiet(JarvisWidgets.ADD_LABEL, color = chrome.okInk, enabled = canAct && !busy,
                                    onClick = { run { JarvisRuntime.widgetAdd(d.id) } })
                            }
                        }
                        if (v.noCard.isNotEmpty()) {
                            Text(v.noCard, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        Gap(10)
                    }
                    if (v.widgets.isEmpty()) {
                        Text(JarvisWidgets.EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    v.widgets.forEach { w ->
                        WidgetRow(w, privateHidden) {
                            Quiet(JarvisWidgets.DELETE_LABEL, color = chrome.badInk, enabled = canAct && !busy,
                                onClick = { run { JarvisRuntime.widgetDelete(w.id) } })
                        }
                    }

                    // ---- Which widget each home-screen slot shows ----
                    Gap(14)
                    Text(JarvisWidgets.SLOTS_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    val options: List<String?> = listOf<String?>(null) + v.widgets.map { it.id }
                    for (slot in 0 until JarvisWidgets.SLOTS) {
                        Gap(6)
                        Text("Jarvis widget ${slot + 1}", style = MaterialTheme.typography.labelSmall,
                            color = chrome.textHi)
                        options.chunked(3).forEach { row ->
                            Choices(
                                options = row,
                                isSelected = { it == slots.getOrNull(slot) },
                                label = { id ->
                                    if (id == null) {
                                        JarvisWidgets.NOTHING
                                    } else {
                                        val i = v.widgets.indexOfFirst { it.id == id }
                                        v.widgets.getOrNull(i)?.name?.takeIf { it.isNotEmpty() && !privateHidden }
                                            ?: "Widget ${i + 1}"
                                    }
                                },
                                onPick = { JarvisRuntime.settings.setHomeWidget(slot, it) },
                            )
                        }
                    }
                    Text(JarvisWidgets.SLOT_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }

            // ---- Describe a widget: the owner's own typed words ----
            if (!missing) {
                Gap(14)
                TextInput(
                    value = words,
                    onValueChange = { words = it.take(JarvisWidgets.MAX_WORDS) },
                    placeholder = "What it should show, like my next 3 reminders and a timer button",
                )
                Quiet(if (making) JarvisWidgets.MAKING_LABEL else JarvisWidgets.MAKE_LABEL,
                    enabled = !making, onClick = { make() })
                Text(JarvisWidgets.PHONE_HINT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && !canAct) {
                Text(
                    "Not connected to the desktop, so adding and deleting wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One widget or preview: its name, its sentence and parts, then its buttons. */
@Composable
private fun WidgetRow(row: JarvisWidgets.Row, privateHidden: Boolean, buttons: @Composable () -> Unit) {
    val chrome = LocalChrome.current
    Gap(10)
    Column(Modifier.fillMaxWidth()) {
        if (privateHidden) {
            Text("(hidden) widget", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        } else {
            Text(row.name.ifEmpty { "Widget" }, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
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
