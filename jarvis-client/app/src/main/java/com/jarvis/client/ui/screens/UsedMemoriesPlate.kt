package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.AutoLearn
import com.jarvis.client.net.MemoryUsed
import com.jarvis.client.net.TemporaryChat
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import kotlinx.coroutines.launch

/**
 * A temporary chat, above Home's chat box (the owner's decision, 2026-09-25;
 * [com.jarvis.client.net.TemporaryChat]).
 *
 * Off: one quiet "Temporary chat" to start one. On: the marker for the whole
 * chat - its name, with [TemporaryChat.LINE] while the chat is still empty
 * ([empty]) - and "End". Either way a new conversation starts. Not while an
 * answer is arriving ([enabled]): Stop is the control for that.
 */
@Composable
internal fun TemporaryChatStrip(on: Boolean, empty: Boolean, enabled: Boolean, onToggle: () -> Unit) {
    val chrome = LocalChrome.current
    if (!on) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Quiet(TemporaryChat.START, color = chrome.textMid, enabled = enabled, onClick = onToggle)
        }
        return
    }
    val accent = LocalAccent.current
    Row(
        Modifier
            .fillMaxWidth()
            .clip(LocalRadii.current.controlShape)
            .background(accent.copy(alpha = 0.10f))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(TemporaryChat.LABEL, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
            if (empty) {
                Text(TemporaryChat.LINE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
        Spacer(Modifier.width(8.dp))
        Quiet(TemporaryChat.END, color = chrome.textMid, enabled = enabled, onClick = onToggle)
    }
    Spacer(Modifier.height(8.dp))
}

/**
 * The facts behind "Used 2 memories" under an answer on Home, and behind
 * "Jarvis remembered 2 things" in Mind (the owner's decisions of
 * 2026-09-25; [MemoryUsed], docs/JARVIS-API.md sections 4, 6 and 19.5).
 *
 * Their words are read from the PC by id ([load]) when this is shown - the
 * answer's header and the `memory_saved` event carry ids only. Each fact
 * still in use gets a Forget, asked about first in the words Mind's Forget
 * uses ([AutoLearn.FORGET_CONFIRM]), one fact per tap, held on a stale link
 * ([canAct]; the runtime refuses it again). A pinned fact says so; a fact no
 * longer in use says so and offers nothing; an erased one never shows words.
 *
 * "Hide memory lists and chat history" (Security) hides it like Mind's other
 * memory lists, until Show is confirmed.
 *
 * [load] and [forget] are passed in, so Home stays free of the runtime.
 */
@Composable
internal fun UsedFactsList(
    title: String,
    ids: List<Long>,
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
    load: suspend (List<Long>) -> MemoryUsed.Read,
    forget: suspend (Long) -> Pair<Boolean, String>,
) {
    val chrome = LocalChrome.current
    if (privateHidden) {
        Column(Modifier.fillMaxWidth()) {
            Kicker(title)
            Gap(4)
            Text(MemoryUsed.HIDDEN, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Quiet(if (showPrivateBusy) "Checking…" else "Show", enabled = !showPrivateBusy, onClick = onShowPrivate)
        }
        return
    }
    Column(Modifier.fillMaxWidth()) {
        Kicker(title)
        Gap(4)
        val scope = rememberCoroutineScope()
        var reads by remember { mutableIntStateOf(0) }
        var read by remember(ids) { mutableStateOf<MemoryUsed.Read?>(null) }
        var confirmId by remember { mutableStateOf<Long?>(null) }
        var busyId by remember { mutableStateOf<Long?>(null) }
        var said by remember { mutableStateOf<String?>(null) }
        LaunchedEffect(ids, reads) { read = load(ids) }

        when (val r = read) {
            null -> Text("Reading…", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            MemoryUsed.Read.Missing ->
                Text(MemoryUsed.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            is MemoryUsed.Read.Failed ->
                Text("Couldn't read these facts: ${r.why}", style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk)
            is MemoryUsed.Read.Shown -> {
                if (!canAct && r.view.facts.any { it.canForget }) {
                    Text(MemoryUsed.HELD, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
                r.view.facts.forEach { fact ->
                    Gap(8)
                    Column(Modifier.fillMaxWidth()) {
                        Text(
                            if (fact.erasedAt != null) "Erased" else fact.text,
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (fact.current) chrome.textHi else chrome.textLo,
                        )
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (fact.pinned) Pill(MemoryUsed.PINNED_MARK)
                            if (!fact.current && fact.erasedAt == null) Pill(MemoryUsed.NOT_CURRENT_MARK)
                        }
                        if (confirmId == fact.id) {
                            Text(AutoLearn.FORGET_CONFIRM, style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Quiet(
                                    "Yes, forget it",
                                    color = chrome.badInk,
                                    enabled = canAct && busyId == null,
                                    onClick = {
                                        confirmId = null
                                        busyId = fact.id
                                        said = null
                                        scope.launch {
                                            try {
                                                said = forget(fact.id).second
                                                reads += 1
                                            } finally {
                                                busyId = null
                                            }
                                        }
                                    },
                                )
                                Quiet("Keep it", onClick = { confirmId = null })
                            }
                        } else if (fact.canForget) {
                            Quiet(
                                if (busyId == fact.id) "Forgetting…" else "Forget",
                                color = chrome.textMid,
                                enabled = canAct && busyId == null,
                                onClick = { confirmId = fact.id },
                            )
                        }
                    }
                }
                MemoryUsed.missingLine(r.view.missing.size)?.let {
                    Gap(6)
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
        }
        said?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                modifier = Modifier.liveStatus())
        }
    }
}
