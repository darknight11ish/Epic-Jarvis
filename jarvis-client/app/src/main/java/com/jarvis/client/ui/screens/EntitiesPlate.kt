package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Entities
import com.jarvis.client.net.MemoryUsed
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "People and things" on Brain ([Entities], the owner's decision of
 * 2026-09-30, docs/GALAXY-PANEL-DESIGN.md option B): a plain list, grouped by
 * kind - People, Pets, Places, Organisations, Projects, Things, Other - each
 * row a name and how many facts name it. Tap one to read those facts, newest
 * first, 20 at a time ("Show 20 more"). No picture, no links, and read-only:
 * Forget, Erase and Pin stay where they already are.
 *
 * Two reads, no new route: the names from `GET /api/memory/entities`, the
 * words from `GET /api/memory/used?ids=` ([JarvisRuntime.memoryUsed]). Both
 * are read when this is shown and dropped when it is left; nothing is kept on
 * the phone.
 *
 * "Hide memory lists and chat history" (Security) replaces the whole thing
 * with [HiddenSection] until Show is confirmed, and because the panel is part
 * of this composable, its words go with it.
 */
@Composable
internal fun PeopleAndThingsSection(
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(Entities.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var entities by remember { mutableStateOf<List<Entities.Entity>?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.memoryEntities()) {
            is ApiResult.Ok -> {
                val list = Entities.parse(r.value)
                if (list == null) {
                    missing = true
                } else {
                    entities = list
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Entities.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Entities.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Entities.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = entities
            val err = readError
            val open = shown?.firstOrNull { it.id == openId }
            when {
                missing -> Text(Entities.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read the list: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                open != null -> {
                    Quiet(Entities.BACK, color = chrome.textMid, onClick = { openId = null })
                    EntityFacts(open)
                }
                else -> {
                    if (err != null) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (shown.isEmpty()) {
                        Text(Entities.EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Entities.groups(shown).forEach { group ->
                        Gap(10)
                        Kicker(group.title)
                        group.entities.forEach { e ->
                            Quiet(Entities.rowLine(e), color = chrome.textHi, onClick = { openId = e.id })
                        }
                    }
                }
            }
        }
    }
}

/**
 * The facts behind one name: the first 20 ids read on arrival, "Show 20 more"
 * for the next 20. An erased fact says [Entities.ERASED] and keeps its date; a
 * forgotten one is marked and sorted after the current ones; a fact hidden by
 * an Off topic is not shown, only counted.
 */
@Composable
private fun EntityFacts(entity: Entities.Entity) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var rows by remember(entity.id) { mutableStateOf<List<Entities.Row>>(emptyList()) }
    var consumed by remember(entity.id) { mutableIntStateOf(0) }
    var hiddenByTopic by remember(entity.id) { mutableIntStateOf(0) }
    var loading by remember(entity.id) { mutableStateOf(false) }
    var failed by remember(entity.id) { mutableStateOf<String?>(null) }
    var attempt by remember(entity.id) { mutableIntStateOf(0) }

    suspend fun loadNext() {
        val ids = Entities.pageIds(entity, consumed)
        if (ids.isEmpty()) return
        loading = true
        failed = null
        try {
            when (val r = JarvisRuntime.memoryUsed(ids)) {
                is MemoryUsed.Read.Shown -> {
                    val page = Entities.page(r.view)
                    rows = Entities.arrange(rows + page.rows)
                    hiddenByTopic += page.hiddenByTopic
                    consumed += ids.size
                }
                MemoryUsed.Read.Missing -> failed = MemoryUsed.MISSING
                is MemoryUsed.Read.Failed -> failed = Entities.FAILED
            }
        } finally {
            loading = false
        }
    }

    LaunchedEffect(entity.id, attempt) {
        if (consumed == 0) loadNext()
    }

    Gap(6)
    Text(entity.name, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
    Text(Entities.heading(entity.count), style = MaterialTheme.typography.labelLarge, color = chrome.textMid)
    val err = failed
    when {
        err != null -> {
            Gap(6)
            Text(err, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            Quiet(Entities.RETRY, enabled = !loading, onClick = {
                if (consumed == 0) attempt += 1 else scope.launch { loadNext() }
            })
        }
        loading && rows.isEmpty() -> {
            Gap(6)
            Text(Entities.READING, style = MaterialTheme.typography.bodySmall, color = chrome.textLo,
                modifier = Modifier.liveStatus())
        }
        consumed > 0 && rows.isEmpty() && !Entities.hasMore(entity, consumed) -> {
            Gap(6)
            Text(Entities.NO_FACTS, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
    rows.forEach { row ->
        Gap(8)
        Column(Modifier.fillMaxWidth()) {
            Text(
                if (row.erased) Entities.ERASED else row.text,
                style = MaterialTheme.typography.bodyMedium,
                color = if (row.forgotten || row.erased) chrome.textLo else chrome.textHi,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.saved?.let {
                    Text("Saved $it", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
                if (row.pinned) Pill(Entities.PINNED)
                if (row.forgotten) Pill(Entities.FORGOTTEN)
            }
        }
    }
    Entities.topicsHiddenLine(hiddenByTopic)?.let {
        Gap(8)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    if (consumed > 0) {
        Gap(8)
        Text(
            Entities.showingLine(consumed, entity.count),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
            modifier = Modifier.liveStatus(),
        )
        if (Entities.hasMore(entity, consumed)) {
            Quiet(Entities.MORE, enabled = !loading, onClick = { scope.launch { loadNext() } })
        }
    }
}
