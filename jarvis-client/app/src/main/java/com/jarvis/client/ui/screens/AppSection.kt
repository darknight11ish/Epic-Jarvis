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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Projects
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.theme.LocalChrome

/**
 * The "App" part of a project page (docs/APPS-IN-PROJECTS-DESIGN.md section
 * 5): a Jarvis-built app's latest saved version, its open tasks, and the last
 * merge's outcome. One task opens [TaskView] - the whole change, in pages,
 * then Merge (one approval card) or Discard.
 *
 * What is left to the PC, said as words and never as a button: making an app
 * project, starting a task, and pasting a change into one (deep editing stays
 * off the phone). This page never approves anything: the merge card is
 * decided in the approval queue, with the fingerprint or PIN.
 *
 * Everything from the PC (a title, a file path, a line of code) is drawn as
 * plain [Text], never parsed as anything else.
 */
@Composable
internal fun AppSection(
    p: Projects.Project,
    app: Projects.AppInfo,
    canAct: Boolean,
    busy: Boolean,
    change: Change,
) {
    val chrome = LocalChrome.current
    val tick by JarvisRuntime.projectsTick.collectAsState()
    val pending by JarvisRuntime.pending.collectAsState()
    var openTask by remember(p.id) { mutableStateOf<String?>(null) }
    var detail by remember(p.id) { mutableStateOf<Projects.TaskDetail?>(null) }
    var readError by remember(p.id) { mutableStateOf<String?>(null) }

    // A merge card is answered elsewhere; read the task again when the queue
    // changes while one waits (the task is gone, or still there).
    val queueKey = if (app.mergeWaiting) pending.size else -1

    LaunchedEffect(p.id, openTask, tick, queueKey) {
        val id = openTask
        if (id == null) {
            detail = null
            readError = null
            return@LaunchedEffect
        }
        val path = Projects.taskPath(p.id, id) ?: return@LaunchedEffect
        when (val r = JarvisRuntime.projectsRead(path)) {
            is ApiResult.Ok -> {
                val d = if (r.value.code in 200..299) Projects.taskOf(r.value) else null
                when {
                    d != null -> {
                        detail = d
                        readError = null
                    }
                    r.value.code == 404 -> openTask = null
                    else -> readError = Projects.said(r.value, "").said
                }
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    Gap(10)
    Text(Projects.aw("app").uppercase(), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    Text(
        listOf(Projects.typeWords(app), app.title).filter { it.isNotBlank() }.joinToString(" · "),
        style = MaterialTheme.typography.bodyMedium,
        color = chrome.textHi,
    )
    if (!app.gitOk && app.said.isNotBlank()) {
        Text(app.said, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    val main = app.main
    Text(
        if (main == null) {
            Projects.aw("app_no_version")
        } else {
            buildString {
                append(Projects.aw("app_latest")).append(": ").append(main.subject.ifBlank { main.head })
                savedDate(main.at)?.let { append(", ").append(it) }
                if (main.versions > 0) {
                    append(" · ").append(Projects.fill(Projects.aw("app_versions"), "n" to main.versions))
                }
            }
        },
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Text(Projects.aw("app_where"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    app.last?.let { last ->
        val words = Projects.mergeSentence(last)
        if (words.isNotBlank()) {
            Gap(4)
            Text(words, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
    }

    val open = openTask
    val shown = detail?.takeIf { open != null && it.summary.task == open }
    if (open != null) {
        Gap(10)
        if (shown == null) {
            Quiet("← ${Projects.aw("task_back")}", onClick = { openTask = null })
            Text(readError ?: "Reading…", style = MaterialTheme.typography.bodySmall,
                color = if (readError != null) chrome.warnInk else chrome.textLo)
        } else {
            TaskView(
                p = p,
                app = app,
                detail = shown,
                canAct = canAct,
                busy = busy,
                change = change,
                onClose = { openTask = null },
            )
        }
        return
    }

    Gap(10)
    Text(Projects.aw("app_tasks").uppercase(), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (app.tasks.isEmpty()) {
        Text(Projects.aw("app_no_tasks"), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
    app.tasks.forEach { t ->
        Gap(6)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text(t.title.ifBlank { "Untitled task" }, style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi)
                Text(Projects.changeCounts(t), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                if (t.olderMain) {
                    Text(Projects.aw("app_older"), style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk)
                }
                if (t.waiting) Pill(Projects.aw("app_waiting"), color = chrome.warnInk)
            }
            Quiet(Projects.aw("app_open"), modifier = Modifier.semantics {
                contentDescription = "${Projects.aw("app_open")} task ${t.title}"
            }, onClick = { openTask = t.task })
        }
    }
    Text(Projects.aw("app_start_on_pc"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
}

/** "3 Oct 2026", in the phone's own language; null without a time. */
private fun savedDate(at: Double?): String? =
    at?.let { java.text.SimpleDateFormat("d MMM yyyy", java.util.Locale.getDefault()).format(java.util.Date((it * 1000).toLong())) }
