package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.MemoryShared
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Between us" on Brain ([MemoryShared], the owner's decision of
 * 2026-09-27): facts the owner tagged as a shared joke or nickname. The
 * one line under the title says so ([MemoryShared.UNDER], both apps'
 * words), then each tagged fact with "Not between us" and Forget.
 *
 * A shared joke is an ordinary fact - "Remember: we call the printer 'the
 * beast'" is saved exactly as any other "Remember: ..." is - with a label
 * the owner's own tap adds ([SavedAutomaticallySection]'s "Between us"
 * toggle, the one list of current facts the phone shows; the desktop can
 * tag any current fact, docs/ARCHITECTURE.md section 8). Both "Not between
 * us" and Forget ask nothing first, and are held while the link is down
 * or stale, like every memory write ([JarvisRuntime.setShared],
 * [JarvisRuntime.forgetAutoFact]).
 *
 * Read from the PC when Brain shows it, on Refresh, and after a tag, an
 * untag or a Forget from this phone ([JarvisRuntime.sharedTick]). Nothing
 * of it is kept on the phone.
 *
 * "Hide memory lists and chat history" (Settings) replaces it with
 * [HiddenSection] until Show is confirmed, like Brain's other memory lists.
 */
@Composable
internal fun BetweenUsSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(MemoryShared.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.sharedTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var shared by remember { mutableStateOf<MemoryShared.Shared?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busyId by remember { mutableStateOf<Long?>(null) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.memoryShared()) {
            is ApiResult.Ok -> {
                val s = MemoryShared.parse(r.value)
                if (s == null) {
                    missing = true
                } else {
                    shared = s
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (MemoryShared.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(MemoryShared.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(MemoryShared.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = shared
            val err = readError
            when {
                missing -> Text(MemoryShared.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read the list: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (err != null) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (shown.facts.isEmpty()) {
                        Text(MemoryShared.EMPTY, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && !shown?.facts.isNullOrEmpty() && !canAct) {
                Text(
                    "Not connected to the desktop, so \"Not between us\" and Forget wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            if (!missing) {
                shown?.facts.orEmpty().forEach { fact ->
                    Gap(10)
                    Column(Modifier.fillMaxWidth()) {
                        Text(fact.text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Quiet(
                                MemoryShared.UNSHARE,
                                enabled = canAct && busyId == null,
                                onClick = {
                                    busyId = fact.id
                                    said = null
                                    scope.launch {
                                        try {
                                            val (changed, sentence) =
                                                JarvisRuntime.setShared(fact.id, shared = false)
                                            if (changed) shared = shown?.let { s ->
                                                s.copy(facts = s.facts.filterNot { it.id == fact.id })
                                            }
                                            said = sentence
                                        } finally {
                                            busyId = null
                                        }
                                    }
                                },
                            )
                            Quiet(
                                "Forget",
                                color = chrome.badInk,
                                enabled = canAct && busyId == null,
                                onClick = {
                                    busyId = fact.id
                                    said = null
                                    scope.launch {
                                        try {
                                            val (gone, sentence) = JarvisRuntime.forgetAutoFact(fact.id)
                                            if (gone) shared = shown?.let { s ->
                                                s.copy(facts = s.facts.filterNot { it.id == fact.id })
                                            }
                                            said = sentence
                                        } finally {
                                            busyId = null
                                        }
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
    }
}
