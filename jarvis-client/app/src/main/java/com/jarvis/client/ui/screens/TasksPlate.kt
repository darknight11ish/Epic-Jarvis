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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Tasks
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * The job list on the Brain screen, under "Background jobs" (docs/JARVIS-API.md
 * section 118): work that outlives one chat turn - a job runs one step at a
 * time, remembers where it got to through a restart, and every step still asks
 * before it acts.
 *
 * **WHAT THIS SCREEN CANNOT SHOW.** The PC sends counts only - ids, states,
 * step counts and tool names. There is no task title and no step text in the
 * reply at all, so there is nothing here to hide behind "Hide memory lists and
 * chat history" and nothing private to leak ([Tasks.Row] has no field for a
 * title because the PC does not send one).
 *
 * **NOTHING HERE APPROVES ANYTHING.** Pause and Cancel stop something
 * unfinished. Resume and Retry put the job back in the queue, and every step
 * still raises its own approval card when its turn comes. This screen never
 * reports a job as paused or resumed on a click: it re-reads, and says only
 * what the PC then says - the same rule [TaskControl] was written for. The
 * steers are held back while the link cannot be confirmed live (rule 4).
 *
 * The list is read once when the screen opens and again after every steer. It
 * is not kept in [JarvisRuntime]: it is small, and nothing in it is worth
 * holding in memory longer than the screen is open.
 */
@Composable
internal fun TasksSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var read by remember { mutableStateOf<Tasks.Read>(Tasks.Read.NotAsked) }
    var busy by remember { mutableStateOf(false) }
    var line by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        if (read is Tasks.Read.NotAsked) {
            // The plate has a "Reading…" line and a colour for it, and neither
            // could ever appear: `read` was only ever assigned the call's own
            // result, so the state existed and was never constructed (first
            // Android audit, finding 10). This is also the truth: the first read
            // is in flight. The assignment is visible while the call suspends.
            read = Tasks.Read.Reading
            read = JarvisRuntime.tasks()
        }
    }

    Section(Tasks.HEADING) {
        Plate {
            val loaded = read as? Tasks.Read.Loaded
            if (loaded == null) {
                Text(Tasks.INTRO, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            } else {
                loaded.answer.headline()?.let {
                    Kicker(it, Modifier.semantics { heading() })
                }
                loaded.answer.rows.forEachIndexed { i, row ->
                    if (i > 0) {
                        Gap(6)
                        Rule()
                        Gap(6)
                    }
                    TaskRowPlate(
                        row = row,
                        enabled = canAct && !busy,
                        onAct = { act ->
                            busy = true
                            line = null
                            scope.launch {
                                when (val out = JarvisRuntime.taskAct(row.id, act)) {
                                    is ApiResult.Ok -> read = JarvisRuntime.tasks()
                                    is ApiResult.Failed -> line = Tasks.actFailureLine(out.error)
                                }
                                busy = false
                            }
                        },
                        onAnswer = { answer ->
                            busy = true
                            line = null
                            scope.launch {
                                when (val out = JarvisRuntime.taskAnswer(row.id, answer)) {
                                    is ApiResult.Ok -> read = JarvisRuntime.tasks()
                                    is ApiResult.Failed -> line = Tasks.actFailureLine(out.error)
                                }
                                busy = false
                            }
                        },
                    )
                }
            }
            Tasks.readLine(read)?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (read is Tasks.Read.Reading) chrome.textMid else chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }
            line?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }
            Gap(8)
            Secondary(
                text = "Check again",
                enabled = !busy,
                busy = busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    if (!busy) {
                        busy = true
                        line = null
                        scope.launch {
                            read = JarvisRuntime.tasks()
                            busy = false
                        }
                    }
                },
            )
        }
    }
}

/** One job: how far it got, which tools it will use, and its four steers. */
@Composable
private fun TaskRowPlate(
    row: Tasks.Row,
    enabled: Boolean,
    onAct: (String) -> Unit,
    onAnswer: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    var answer by remember { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Kicker(Tasks.stateWords(row.state))
        Text(row.shape(), style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        if (row.attempts > 1) {
            Text(
                "tried ${row.attempts} times",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
        // The PC's own sentence about an interrupted step or a question it
        // needs answered. It names a tool or asks for a value, never the
        // owner's words - there is nothing else for it to carry.
        if (row.needsAttention && row.question.isNotBlank()) {
            Text(row.question, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
        // A job that stopped to ask gets a box, and only that job: the answer
        // is the one thing here that carries the owner's own words.
        if (row.state == "waiting_input") {
            TextInput(
                value = answer,
                onValueChange = { answer = it },
                label = "Your answer",
                modifier = Modifier.fillMaxWidth(),
            )
            Secondary(
                text = "Send answer",
                enabled = enabled && answer.isNotBlank(),
                onClick = { onAnswer(answer) },
            )
        }
        val acts = Tasks.actsFor(row.state)
        if (acts.isNotEmpty()) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (act in acts) {
                    Secondary(
                        text = Tasks.actWords(act),
                        enabled = enabled,
                        onClick = { onAct(act) },
                    )
                }
            }
        }
    }
}
