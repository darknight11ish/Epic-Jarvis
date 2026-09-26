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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Folders
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Folders Jarvis may look in" on the Brain ([Folders], the owner's decisions
 * of 2026-09-26) - the desktop's Settings -> Folders Jarvis may look in, in
 * the same words.
 *
 * The list, the PC's line about reading PDF and Word files, and Remove on
 * each folder - at once, never held on a stale link. No Add and no Notion
 * import: both are the PC's alone (the PC refuses them from the phone), and
 * the PC's own line says where to do them. Asking Jarvis about the files
 * works from the phone like any question.
 */
@Composable
internal fun FoldersSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Folders.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    // A folder's card answered on the PC changes the list: read it again when
    // the approval queue changes, as the desktop does (onQueue).
    val queue by JarvisRuntime.pending.collectAsState()
    val queueKey = queue.map { it.id }

    LaunchedEffect(reads, queueKey) {
        when (val r = JarvisRuntime.folders()) {
            is ApiResult.Ok -> {
                val v = Folders.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Folders.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Folders.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            when {
                missing -> Text(Folders.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't ask Jarvis which folders it may look in: $err"
                    else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(v.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (v.folders.isEmpty()) {
                        Gap(8)
                        Text(v.why.ifEmpty { v.empty }, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    v.folders.forEach { f ->
                        Gap(8)
                        Column {
                            Text(f.name, style = MaterialTheme.typography.titleSmall,
                                color = chrome.textHi)
                            Folders.lines(f).forEach {
                                Text(it, style = MaterialTheme.typography.labelSmall,
                                    color = if (it == Folders.NOT_HERE) chrome.warnInk else chrome.textMid)
                            }
                            // Removing only lets Jarvis see less: never held.
                            Quiet(v.removeLabel, enabled = !busy, onClick = {
                                if (!busy) {
                                    busy = true
                                    said = null
                                    scope.launch {
                                        try {
                                            said = JarvisRuntime.removeFolder(f.path)
                                        } finally {
                                            busy = false
                                            reads += 1
                                        }
                                    }
                                }
                            })
                        }
                    }
                    if (v.waiting.isNotEmpty()) {
                        Gap(6)
                        Text("${v.waitingWords} (${v.waiting})",
                            style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                    }
                    Gap(8)
                    Text(v.phoneAdd, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    if (v.documentsSaid.isNotEmpty()) {
                        Gap(4)
                        Text(v.documentsSaid, style = MaterialTheme.typography.labelSmall,
                            color = if (v.documentsReady) chrome.okInk else chrome.textMid)
                    }
                    said?.let {
                        Gap(6)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                }
            }
        }
    }
}
