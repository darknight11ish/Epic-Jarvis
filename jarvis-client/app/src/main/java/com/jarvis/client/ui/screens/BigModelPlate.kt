package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.BigModel
import com.jarvis.client.ui.parts.FormattedAnswer
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Big model (slow)" on the Mind screen, next to the second-card plate:
 * what the PC found, the main switch and one switch per background job,
 * colibri's state, and the speeds it measured.
 *
 * A handful of approval-backed switches and nothing more - no config
 * editing, and no command lines (those are the PC's, in docs/BIG-MODEL.md).
 * The same flow as the second card ([SecondCardPlate]): ON asks the PC,
 * which raises one approval card and changes nothing until it is approved
 * (on the PC, or in this phone's own approvals, one at a time); OFF is
 * immediate. The switch always shows what the PC last REPORTED, and the
 * plate is re-read after a switch and after a card is decided. The main
 * switch cannot be turned on until the PC says it has everything it needs.
 *
 * Reads and acts through [JarvisRuntime] directly, like [WikiSection], so
 * [BrainScreen] needs one line for it. Every switch is greyed while
 * [canAct] is false (rule 4), and the runtime refuses again on the way out.
 */
@Composable
internal fun BigModelSection(canAct: Boolean, onOpenApprovals: ((cardId: String?) -> Unit)?) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.bigModel.collectAsState()
    // The switch whose request is in flight ("" for a plain re-read), and
    // what the last request came back with.
    var busy by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    val recheck: () -> Unit = {
        if (busy == null) {
            busy = ""
            scope.launch {
                try {
                    JarvisRuntime.refreshBigModel()
                } finally {
                    busy = null
                }
            }
        }
    }
    val onSet: (String, Boolean) -> Unit = { id, want ->
        if (busy == null) {
            busy = id
            notice = null
            scope.launch {
                try {
                    notice = JarvisRuntime.setBigModel(id, want)
                } finally {
                    busy = null
                }
            }
        }
    }

    Section("Big model (slow)", trailing = { Quiet("Refresh", enabled = busy == null, onClick = recheck) }) {
        val status = (read as? BigModel.Read.Loaded<BigModel.Status>)?.value
        if (status == null) {
            Plate {
                Text(
                    BigModel.readLine(read).orEmpty(),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (read is BigModel.Read.NotAsked) chrome.textMid else chrome.warnInk,
                )
                notice?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
            }
        } else {
            BigModelBody(status, busy, notice, canAct, onSet, recheck, onOpenApprovals)
        }
    }
}

@Composable
private fun BigModelBody(
    status: BigModel.Status,
    busy: String?,
    notice: String?,
    canAct: Boolean,
    onSet: (String, Boolean) -> Unit,
    recheck: () -> Unit,
    onOpenApprovals: ((cardId: String?) -> Unit)?,
) {
    val chrome = LocalChrome.current
    Plate {
        // 1. What was found.
        Kicker("What was found", Modifier.semantics { heading() })
        Gap(4)
        Text(
            BigModel.summaryLine(status),
            style = MaterialTheme.typography.bodyMedium,
            color = if (status.found.capable) chrome.okInk else chrome.textMid,
        )
        for (line in BigModel.foundLines(status)) {
            Gap(2)
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        for (m in BigModel.modelViews(status)) {
            Gap(8)
            Text(m.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Text(m.detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            if (m.why.isNotBlank()) {
                Text(m.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            m.warning?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            }
        }

        // 2. The main switch, then one per job.
        Gap(12)
        Rule()
        ApprovalSwitchRow(BigModel.master(status), busy, canAct, onSet)
        for (view in BigModel.switches(status)) {
            Rule()
            ApprovalSwitchRow(view, busy, canAct, onSet)
        }
        Rule()

        notice?.let {
            Gap(8)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        // A card is waiting: where it is, and a way to ask again. Neither
        // approves anything - the card itself is still one deliberate tap.
        if (status.pending.isNotEmpty()) {
            Gap(8)
            if (onOpenApprovals != null) {
                Quiet("Open the card →", color = chrome.warnInk, onClick = { onOpenApprovals(null) })
            }
            Secondary(
                text = if (busy != null) "Asking…" else "Ask the PC again",
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = recheck,
            )
        }

        // 3. colibri itself.
        Gap(12)
        Kicker("The big model's engine", Modifier.semantics { heading() })
        Gap(4)
        Text(
            BigModel.engineLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = if (status.engine.state == "failed") chrome.warnInk else chrome.textMid,
        )
        Gap(2)
        Text(
            BigModel.cudaLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = if (status.cudaSetting == "on" && !status.cudaUsable) chrome.warnInk else chrome.textLo,
        )

        // 4. How fast it really is on this PC - or that nobody knows yet.
        Gap(12)
        Kicker("Speed on this PC", Modifier.semantics { heading() })
        Gap(4)
        for (line in BigModel.speedLines(status)) {
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        if (status.unverified.isNotBlank()) {
            Gap(4)
            Text(status.unverified, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }

        Gap(10)
        Text(
            "Turning a switch on raises an approval card on your PC and phone. Nothing " +
                "changes until you approve it. Turning one off happens at once. The big " +
                "model runs on your PC only and sends nothing off it.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}

/**
 * "Deep questions" on the Mind screen: a question typed here is answered in
 * the background by the big model, and kept on the PC for reading later.
 *
 * The box and "Ask slowly" are offered only while `GET /api/deep` says
 * `available`; otherwise its `why` is shown instead. Below, the recent
 * questions, each with its state, the PC's line, the time taken and words a
 * second, and the answer as plain text once it is done - split into
 * paragraphs the way chat shows a reply, nothing more.
 *
 * Kept fresh by the `deep` event (the runtime re-reads on it), and while a
 * question is still going and this plate is on screen, by a gentle re-read
 * every [BigModel.DEEP_POLL_MS] - the state moves from waiting to starting
 * to thinking without an event of its own.
 */
@Composable
internal fun DeepQuestionsSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.deep.collectAsState()
    val deep = (read as? BigModel.Read.Loaded<BigModel.Deep>)?.value
    var question by remember { mutableStateOf("") }
    var asking by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<BigModel.Asked?>(null) }
    // Which finished answers are open. The newest one opens by itself.
    var opened by remember { mutableStateOf(setOf<String>()) }
    var closed by remember { mutableStateOf(setOf<String>()) }

    val running = deep?.anyRunning == true
    LaunchedEffect(running) {
        while (running) {
            delay(BigModel.DEEP_POLL_MS)
            JarvisRuntime.refreshDeep()
        }
    }

    Section(
        "Deep questions",
        trailing = { Quiet("Refresh", onClick = { scope.launch { JarvisRuntime.refreshDeep() } }) },
    ) {
        if (deep == null) {
            Plate {
                Text(
                    BigModel.readLine(read).orEmpty(),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (read is BigModel.Read.NotAsked) chrome.textLo else chrome.warnInk,
                )
            }
        } else {
            DeepBody(
                deep = deep,
                canAct = canAct,
                question = question,
                onQuestion = { question = it },
                asking = asking,
                said = said,
                isOpen = { job, newestDone ->
                    job.answer != null && (job.id in opened || (job.id == newestDone && job.id !in closed))
                },
                onToggle = { id, open ->
                    if (open) {
                        opened = opened - id
                        closed = closed + id
                    } else {
                        opened = opened + id
                        closed = closed - id
                    }
                },
                onAsk = {
                    if (!asking) {
                        asking = true
                        said = null
                        scope.launch {
                            try {
                                val r = JarvisRuntime.askDeep(question)
                                said = r
                                if (r.queued) question = ""
                            } finally {
                                asking = false
                            }
                        }
                    }
                },
            )
        }
    }
}

@Composable
private fun DeepBody(
    deep: BigModel.Deep,
    canAct: Boolean,
    question: String,
    onQuestion: (String) -> Unit,
    asking: Boolean,
    said: BigModel.Asked?,
    isOpen: (job: BigModel.DeepJob, newestDone: String?) -> Boolean,
    onToggle: (id: String, open: Boolean) -> Unit,
    onAsk: () -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Text(
            deep.why.ifBlank { if (deep.available) "Ready." else "Not available." },
            style = MaterialTheme.typography.bodySmall,
            color = if (deep.available) chrome.okInk else chrome.textMid,
        )
        if (deep.available) {
            Gap(8)
            TextInput(
                value = question,
                onValueChange = onQuestion,
                placeholder = "A question that deserves a careful answer",
                singleLine = false,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                supportingText = "Answered on your PC by the big model, with no tools, no internet " +
                    "and no memory of your chats. Expect minutes. Nothing leaves your PC.",
            )
            Gap(8)
            Secondary(
                text = if (deep.queueFull) "${deep.queue} questions are already waiting" else "Ask slowly",
                enabled = canAct && !asking && !deep.queueFull && question.isNotBlank(),
                busy = asking,
                modifier = Modifier.fillMaxWidth(),
                onClick = onAsk,
            )
        }
        said?.let {
            Gap(6)
            Text(
                it.text,
                style = MaterialTheme.typography.bodySmall,
                color = if (it.queued) chrome.textMid else chrome.warnInk,
                modifier = Modifier.liveStatus(),
            )
        }

        if (deep.jobs.isNotEmpty()) {
            Gap(12)
            Kicker("Recent questions", Modifier.semantics { heading() })
            val newestDone = deep.jobs.firstOrNull { it.answer != null }?.id
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                deep.jobs.forEach { job ->
                    Rule()
                    val open = isOpen(job, newestDone)
                    DeepJobRow(job = job, open = open, onToggle = { onToggle(job.id, open) })
                }
            }
        } else {
            Gap(8)
            Text("No questions asked yet.", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}

@Composable
private fun DeepJobRow(job: BigModel.DeepJob, open: Boolean, onToggle: () -> Unit) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Gap(4)
        Text(
            job.question,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
            // A reminder of the question, as chat shows it - not a transcript.
            maxLines = if (open) Int.MAX_VALUE else 3,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            BigModel.stateLabel(job.state),
            style = MaterialTheme.typography.labelMedium,
            color = when (job.state) {
                "done" -> chrome.okInk
                "failed" -> chrome.badInk
                else -> chrome.warnInk
            },
        )
        if (job.why.isNotBlank()) {
            Text(job.why, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        BigModel.jobMeta(job)?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        val answer = job.answer
        if (answer != null) {
            Quiet(if (open) "Hide the answer" else "Show the answer", onClick = onToggle)
            if (open) {
                // UI-AUDIT-2026-09-26 item 5: the same formatting the chat
                // reply uses (ui/parts/AnswerFormat.kt) - this is model
                // output too, and a link's real address matters just as much
                // in a deep answer as in a chat one.
                BigModel.paragraphs(answer).forEachIndexed { index, paragraph ->
                    if (index > 0) Gap(10)
                    FormattedAnswer(paragraph, style = MaterialTheme.typography.bodyLarge, color = chrome.textHi)
                }
                Gap(4)
            }
        }
    }
}
