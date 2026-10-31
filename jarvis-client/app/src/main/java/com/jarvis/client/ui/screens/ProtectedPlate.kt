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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Protected
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Protected from Jarvis" on the phone - the PC's owner-editable list of what
 * Jarvis may NOT touch (`.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`;
 * shapes in [com.jarvis.client.net.Protected]).
 *
 * Deliberately small, and the smallness is the contract: this screen LISTS the
 * entries and can ASK for one to be REMOVED. It cannot add - the pickers for
 * folders, files and programs are on the PC (the phone has no view of the PC's
 * files or programs, the same reason the folder allow-list is PC-added), and a
 * chat request from here raises the same card. There is no phone file browser
 * and no phone add route; `ProtectedContractTest` pins both.
 *
 * Removing is LOOSENING, so it always asks: the PC raises ONE approval card,
 * this screen shows its own words, and the entry stays protected until the
 * owner approves. Both modes are shown in the PC's words - "Blocked — no
 * access" and "Read-only" - with one line saying what each means for this kind.
 */
@Composable
internal fun ProtectedSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var view by remember { mutableStateOf<Protected.View?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var reads by remember { mutableIntStateOf(0) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.protection()) {
            is ApiResult.Ok -> {
                view = Protected.view(r.value)
                error = null
            }
            is ApiResult.Failed -> error = Protected.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    val job by JarvisRuntime.protectionLine.collectAsState()
    val said = job?.second
    val waitingId = job?.takeIf { it.second.removing }?.first
    // When the PC's answer is final the list has changed (removed) or has not
    // (denied / still waiting): read it again either way, so the rows are true.
    LaunchedEffect(said?.text, said?.removing) {
        if (said != null && !said.removing) reads += 1
    }

    Section("Protected from Jarvis", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(
                "What Jarvis may not touch. Each entry is a folder, a file or a program, " +
                    "blocked or read-only.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(4)
            Text(
                "Blocked: no access at all - for a program, no opening it and no screen reading " +
                    "of its windows. Read-only: Jarvis may read it, but never write, delete or " +
                    "rename it - for a program, see it but never act.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(10)

            error?.let {
                Text(
                    "Couldn't read the list: $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                Gap(8)
            }

            val v = view
            when {
                v == null -> Text(
                    "Reading the list…",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                v.items.isEmpty() -> Text(
                    "Nothing is protected yet. Add folders, files and programs on your PC - or ask " +
                        "Jarvis in chat from here and it will raise a card.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                else -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        "${v.count} protected ${if (v.count == 1) "entry" else "entries"}",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                    )
                    v.items.forEach { item ->
                        ProtectedRow(
                            item = item,
                            canAct = canAct,
                            waiting = waitingId != null,
                            onRemove = { scope.launch { JarvisRuntime.removeProtected(item.id) } },
                        )
                    }
                }
            }

            said?.let {
                Gap(10)
                Text(
                    it.text,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (it.removing) chrome.textHi else chrome.okInk,
                    modifier = Modifier.liveStatus(),
                )
                if (it.removing) {
                    Gap(2)
                    Text(
                        "The entry stays protected until you approve the card.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }
            if (!canAct) {
                Gap(4)
                Text(Protected.STALE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }

            Gap(10)
            Text(
                Protected.PICKERS,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            val changeCard = view?.changeCard.orEmpty()
            if (changeCard.isNotEmpty()) {
                Gap(2)
                Text(changeCard, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
    }
}

/** One protected entry: the target, what it is and its mode, and Remove. */
@Composable
private fun ProtectedRow(
    item: Protected.Item,
    canAct: Boolean,
    waiting: Boolean,
    onRemove: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                item.target,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Text(
                Protected.modeWord(item.mode),
                style = MaterialTheme.typography.labelSmall,
                color = if (item.mode.trim().lowercase() == Protected.MODE_BLOCKED) {
                    chrome.badInk
                } else {
                    chrome.textMid
                },
            )
        }
        Text(
            Protected.kindWord(item.kind),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Text(
            Protected.modeMeaning(item.kind, item.mode),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Gap(2)
        Quiet(
            "Remove",
            enabled = canAct && !waiting,
            onClick = onRemove,
        )
    }
}
