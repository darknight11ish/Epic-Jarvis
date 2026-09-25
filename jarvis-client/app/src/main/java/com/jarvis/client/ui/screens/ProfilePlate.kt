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
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.MemoryProfile
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Always keep in mind" on Mind ([MemoryProfile], the owner's decision of
 * 2026-09-24): the facts the owner pinned, which Jarvis reads with every
 * question, word for word. The one line under the title says so
 * ([MemoryProfile.UNDER], both apps' words), then how many of the list's
 * 1,200 characters are used, then each pinned fact with an Unpin.
 *
 * Facts are pinned from "Saved automatically" just above
 * ([SavedAutomaticallySection]) - the one list of current facts the phone
 * shows; the desktop can pin any current fact (docs/ARCHITECTURE.md section
 * 8). Unpin asks nothing first - it only takes the pin off, the fact stays -
 * and is held while the link is down or stale, like every memory write
 * ([JarvisRuntime.pinFact]).
 *
 * Read from the PC when Mind shows it, on Refresh, and after a pin, an
 * unpin, a Forget or an erase from this phone ([JarvisRuntime.profileTick]).
 * Nothing of it is kept on the phone.
 *
 * "Hide memory lists and chat history" (Security) replaces it with
 * [HiddenSection] until Show is confirmed, like Mind's other memory lists.
 */
@Composable
internal fun AlwaysKeepInMindSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(MemoryProfile.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.profileTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var profile by remember { mutableStateOf<MemoryProfile.Profile?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busyId by remember { mutableStateOf<Long?>(null) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.memoryProfile()) {
            is ApiResult.Ok -> {
                val p = MemoryProfile.parse(r.value)
                if (p == null) {
                    missing = true
                } else {
                    profile = p
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (MemoryProfile.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(MemoryProfile.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(MemoryProfile.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = profile
            val err = readError
            when {
                missing -> Text(MemoryProfile.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read the list: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(MemoryProfile.usedLine(shown.chars, shown.limit),
                        style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    if (err != null) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (shown.facts.isEmpty()) {
                        Gap(4)
                        Text(MemoryProfile.EMPTY, style = MaterialTheme.typography.bodySmall,
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
                    "Not connected to the desktop, so Unpin waits until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            if (!missing) {
                shown?.facts.orEmpty().forEach { fact ->
                    Gap(10)
                    Column(Modifier.fillMaxWidth()) {
                        Text(fact.text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        Quiet(
                            if (busyId == fact.id) MemoryProfile.UNPINNING else MemoryProfile.UNPIN,
                            enabled = canAct && busyId == null,
                            onClick = {
                                busyId = fact.id
                                said = null
                                scope.launch {
                                    try {
                                        val (changed, sentence) = JarvisRuntime.pinFact(fact.id, pinned = false)
                                        if (changed) profile = shown?.let { p ->
                                            p.copy(facts = p.facts.filterNot { it.id == fact.id })
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
