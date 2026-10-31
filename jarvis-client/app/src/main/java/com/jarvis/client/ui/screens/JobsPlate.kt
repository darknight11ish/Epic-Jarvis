package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.Jobs
import com.jarvis.client.ui.parts.Affirm
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Meter
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Refuse
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.JarvisType
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Background jobs" on the Brain screen - Long Fuse, the queue of work that
 * outlives one chat turn.
 *
 * **The desktop's Work tab, in the phone's words.** Until 2026-10-30 the phone
 * could only LOOK at this list. `backend/jobs-routes.patch` gave the queue a
 * way in and a way out, the desktop's Work tab used both first
 * (`brain_create_job` / `brain_answer_job`, `src/brain.js` `renderJobStart` /
 * `jobGrantActions`), and this is the phone's half (docs/JARVIS-API.md section
 * 169): a "Start a background job" form offering ONLY the job bodies this PC
 * registered, and, under a job parked for a permission, the sentence it is
 * asking about and exactly two buttons - "No" and "Allow once".
 *
 * **NOTHING HERE APPROVES ANYTHING BY ITSELF.** The form sends no
 * capabilities, so a job started here begins with nothing frozen and stops at
 * its first need - which is what the two buttons are for. One job, one grant,
 * one USE: the answer is spent by the handler's next ask, it is not a rule,
 * and a No stops that job at once and leaves nothing behind for the next one.
 * There is deliberately no "Always allow" and no list form (ARCHITECTURE.md
 * section 3: one card per action).
 *
 * **Two things are replaced by a sentence rather than a button**, because the
 * server's own facts make the control a promise it cannot keep: no registered
 * body (`status.handlers` empty) and a stopped heartbeat (`ticking: false`, a
 * job started then would never run). An older PC - one whose GET has no
 * `ticking` key at all, so neither POST exists - keeps its read-only list and
 * says which patch it needs.
 *
 * The list is read when the section first draws and again after every write;
 * it is not kept in [JarvisRuntime]. Both writes are held while the link is
 * down or stale ([JarvisRuntime.startJob], [JarvisRuntime.answerJob], rule 4).
 */
@Composable
internal fun JobsSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var read by remember { mutableStateOf<Jobs.Read>(Jobs.Read.NotAsked) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    // Which registered body the form would start. Only meaningful when the PC
    // registered more than one; a name that is no longer on the list falls back
    // to the first, so a stale choice can never start the wrong thing.
    var chosen by remember { mutableStateOf("") }
    var words by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        if (read is Jobs.Read.NotAsked) {
            // The first read is in flight, and says so (the same line TasksSection
            // draws). `read` is only ever assigned the call's own result after
            // that, so without this the "Reading…" state would exist and never
            // be constructed.
            read = Jobs.Read.Reading
            read = JarvisRuntime.jobsRead()
        }
    }

    fun reread() {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                read = JarvisRuntime.jobsRead()
            } finally {
                busy = false
            }
        }
    }

    /** One write, one answer: show the line it came back with, then re-read what landed. */
    fun act(block: suspend () -> Jobs.Said) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                val result = block()
                said = when (result) {
                    is Jobs.Said.Landed -> result.words
                    is Jobs.Said.Refused -> result.words
                }
                if (result is Jobs.Said.Landed) {
                    // Something changed on the PC: read it back rather than
                    // describing a state it may not be in. The line above is the
                    // answer's own words, not a claim about the new state.
                    read = JarvisRuntime.jobsRead()
                    words = ""
                }
            } finally {
                busy = false
            }
        }
    }

    Section(Jobs.HEADING) {
        Plate {
            val feed = Jobs.feedOf(read)
            val kinds = feed?.status?.handlers.orEmpty()
            val kind = chosen.takeIf { it in kinds } ?: kinds.firstOrNull().orEmpty()
            val problem = Jobs.startProblem(feed)
            val form = read as? Jobs.Read.Loaded

            // ---- The way in. Above the list, like the desktop's Work tab, so
            // starting a job is not something the owner must know to look for
            // at the bottom. ----
            if (form != null) {
                Kicker(Jobs.START_HEAD)
                Gap(6)
                when {
                    problem != null -> Text(
                        problem,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    else -> {
                        if (kinds.size > 1) {
                            // A closed list, never a typed kind: nothing here can
                            // name a body this PC has not registered.
                            Kicker(Jobs.KIND_QUESTION)
                            kinds.forEach { name ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(
                                        name,
                                        style = JarvisType.machine,
                                        color = if (name == kind) chrome.okInk else chrome.textHi,
                                        modifier = Modifier.weight(1f),
                                    )
                                    if (name == kind) {
                                        // By words as well as tone, so the choice
                                        // does not rest on colour alone.
                                        Text(
                                            Jobs.CHOSEN,
                                            style = MaterialTheme.typography.labelSmall,
                                            color = chrome.textMid,
                                        )
                                    } else {
                                        Quiet(
                                            Jobs.CHOOSE,
                                            enabled = canAct && !busy,
                                            onClick = { chosen = name },
                                        )
                                    }
                                }
                            }
                            Gap(6)
                        } else if (kind.isNotBlank()) {
                            Field(Jobs.WHAT_IT_DOES, kind, machine = true)
                        }
                        TextInput(
                            value = words,
                            onValueChange = { words = it.take(80) },
                            label = Jobs.WORDS_LABEL,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Gap(8)
                        Primary(
                            Jobs.START,
                            modifier = Modifier.fillMaxWidth(),
                            enabled = canAct && !busy && kind.isNotBlank(),
                            busy = busy,
                            onClick = { act { JarvisRuntime.startJob(kind, words) } },
                        )
                        Gap(6)
                        Text(
                            Jobs.START_NOTE,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            if (feed != null && feed.jobs.isEmpty()) {
                Text(
                    Jobs.EMPTY,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }

            Jobs.readLine(read)?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (read is Jobs.Read.Reading) chrome.textMid else chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }
            said?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            if (!canAct) {
                Gap(6)
                Text(
                    "Not connected to the desktop, so Start and the two answers wait until " +
                        "the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            Gap(8)
            Secondary(
                text = "Check again",
                enabled = !busy,
                busy = busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = { reread() },
            )
        }

        // ---- The list, one card per job, below the form's card: the shape the
        // phone has always drawn, so a job reads the same as it did before the
        // controls arrived. ----
        val listed = Jobs.feedOf(read)
        val rows = listed?.jobs.orEmpty()
        if (listed != null && rows.isNotEmpty()) {
            Gap(10)
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                rows.forEach { job ->
                    JobPlate(
                        job = job,
                        grant = listed.grantFor(job.id),
                        answered = listed.answered(job),
                        enabled = canAct && !busy,
                        onAnswer = { approved ->
                            act { JarvisRuntime.answerJob(job.id, approved) }
                        },
                    )
                }
            }
        }
    }
}

/**
 * One background job: what it is, how far it got, the permissions it was
 * approved with (frozen for its life and shown because that promise is
 * checkable), and - when it is parked - the one question it is waiting on with
 * exactly two answers.
 *
 * The action's own words come from [Jobs.actionWords], which is the phone's
 * existing card wording ([com.jarvis.client.net.CardWords.fallbackTitle]), so
 * this reads like every other approval on this phone.
 */
@Composable
private fun JobPlate(
    job: JobRecord,
    grant: Jobs.Grant?,
    answered: Boolean,
    enabled: Boolean,
    onAnswer: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                job.title,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            // A parked job says what it is waiting for in words; the plain state
            // word otherwise. The raw state stays for everything but that one,
            // which the desktop also words differently ("waiting for you").
            Pill(
                if (grant != null) "waiting for you" else Jobs.stateWords(job.state.ifBlank { "running" }),
            )
        }
        job.progress?.let {
            Gap(10)
            Meter(it)
        }
        if (job.frozen.isNotEmpty()) {
            Gap(10)
            // Frozen for the job's life. A job can never gain more while it
            // runs: approving something on Tuesday is not approving it on
            // Wednesday, and showing the frozen set is how that promise is
            // checkable rather than merely stated.
            Kicker("Approved with")
            Gap(6)
            FlowChips(job.frozen)
        }
        if (job.tainted) {
            Gap(8)
            Text(
                "Read private data, so it stays on the PC.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (job.private) {
            Gap(8)
            Text(
                "Private — the phone is not shown what this is working on.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (grant != null) {
            Gap(8)
            // What it is asking for, and that one answer covers ONE use. The
            // line comes before the buttons on purpose: the buttons must never be
            // the only place the question is named.
            Text(
                Jobs.wantLine(grant),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
            Gap(8)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                // Deny left, approve right - the order every screen uses
                // (CardWords.BUTTONS, ARCHITECTURE.md section 3), and the same
                // two answers the desktop draws.
                Refuse(Jobs.NO, enabled = enabled, onClick = { onAnswer(false) })
                Affirm(Jobs.ALLOW_ONCE, enabled = enabled, onClick = { onAnswer(true) })
            }
        } else if (answered) {
            Gap(8)
            Text(
                Jobs.ANSWERED_LINE,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
    }
}
