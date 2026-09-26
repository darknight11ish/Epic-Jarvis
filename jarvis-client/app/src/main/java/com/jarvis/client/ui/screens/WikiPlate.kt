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
import com.jarvis.client.net.Wiki
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The wiki builder on Mind - the desktop's `/api/wiki` (`backend/wiki.patch`).
 *
 * The documents in the desktop's `Jarvis Wiki/Sources`, each with its state,
 * and "Add to wiki" for a new or changed one. That raises ONE approval card
 * on the desktop; nothing is written until it is answered, and the line
 * above the list says how it is going in the desktop's own words
 * ([com.jarvis.client.net.Wiki.describe]). No file browsing and no page
 * reading here: the vault reaches the phone through Syncthing already.
 *
 * Reads and acts through [JarvisRuntime] directly, so [BrainScreen] needs one
 * line for it. "Add to wiki" is greyed while [canAct] is false (rule 4), and
 * the runtime refuses it again on the way out.
 */
@Composable
internal fun WikiSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val job by JarvisRuntime.wikiJob.collectAsState()
    var view by remember { mutableStateOf<Wiki.View?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var reads by remember { mutableIntStateOf(0) }
    // Read when the plate opens, when asked again, and when a job ends - the
    // list's states change then ("new" becomes "in the wiki").
    val jobFinal = job?.second?.final
    LaunchedEffect(reads, jobFinal) {
        val r = JarvisRuntime.wiki()
        if (r is ApiResult.Ok) {
            view = Wiki.read(r.value)
            readError = null
        } else if (r is ApiResult.Failed) {
            readError = Wiki.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    Section("Wiki", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            if (v == null) {
                Text(
                    if (err != null) "Couldn't read the wiki builder: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
            } else {
                WikiBody(
                    v = v,
                    err = err,
                    job = job,
                    canAct = canAct,
                    onAdd = { name -> scope.launch { JarvisRuntime.addToWiki(name) } },
                )
            }
        }
    }
}

@Composable
private fun WikiBody(
    v: Wiki.View,
    err: String?,
    job: Pair<String, Wiki.Said>?,
    canAct: Boolean,
    onAdd: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    Text(
        v.why.ifEmpty { if (v.available) "Ready." else "The wiki builder is not ready." },
        style = MaterialTheme.typography.bodySmall,
        color = if (v.available) chrome.okInk else chrome.textMid,
    )
    if (err != null) {
        Text(
            "Couldn't read it again: $err",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk,
        )
    }
    if (!v.folderOk) {
        Gap(8)
        Text(v.folderWhy, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    } else {
        if (job != null) {
            Gap(8)
            Text(
                "${job.first}: ${job.second.text}",
                style = MaterialTheme.typography.bodySmall,
                color = if (job.second.done) {
                    chrome.okInk
                } else if (job.second.final) {
                    chrome.badInk
                } else {
                    chrome.textHi
                },
                modifier = Modifier.liveStatus(),
            )
        } else if (v.runningSource != null) {
            Gap(8)
            Text(
                "Working on ${v.runningSource}.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textHi,
            )
        }
        val jobRunning = job != null && !job.second.final
        Gap(8)
        if (v.sources.isEmpty()) {
            Text(
                "Sources is empty. Put .md or .txt files in Jarvis Wiki/Sources in your " +
                    "vault. Other kinds of file are not read yet.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            v.sources.forEach { s ->
                WikiSourceRow(s, offerAdd = v.canAdd(s) && !jobRunning, canAct = canAct, onAdd = onAdd)
            }
        }
        Gap(8)
        Field("Pages", v.pages.toString())
        if (v.recent.isNotEmpty()) {
            Gap(4)
            Text("Recently added", style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            v.recent.forEach { line ->
                Text(Wiki.logLine(line), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
    }
}

@Composable
private fun WikiSourceRow(s: Wiki.Source, offerAdd: Boolean, canAct: Boolean, onAdd: (String) -> Unit) {
    val chrome = LocalChrome.current
    val tagColor = when (s.state) {
        "in_wiki" -> chrome.okInk
        "too_big", "unreadable" -> chrome.badInk
        "changed" -> chrome.warnInk
        else -> chrome.textMid
    }
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                s.name,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Text(Wiki.label(s.state), style = MaterialTheme.typography.labelSmall, color = tagColor)
        }
        if (s.why.isNotEmpty()) {
            Text(s.why, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (offerAdd) {
            Quiet("Add to wiki", enabled = canAct, onClick = { onAdd(s.name) })
        }
    }
}
