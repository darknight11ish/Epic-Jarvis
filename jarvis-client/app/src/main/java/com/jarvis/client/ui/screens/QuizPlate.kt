package com.jarvis.client.ui.screens

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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Quiz
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Quiz me on a text" on Brain ([Quiz], docs/STUDY-FROM-TEXT-DESIGN.md
 * sections 3 and 11) - beside "Goals" ([GoalsSection]), matching the
 * desktop's Quiz page.
 *
 * The owner pastes some text (200 to 20,000 characters, with a live count),
 * taps Write questions, then answers ONE question at a time by TYPING (a
 * client must not do speech-to-text). Check my answer shows the mark
 * (Got it / Partly / Not yet), the model's one-sentence comment and the
 * passage it was marked against; "Jarvis's guess" stays beside a mark until
 * the PC has measured its grader. Finish shows "Look at these again"; Stop
 * and forget this quiz ends it at once. No card is raised: it is the owner's
 * own pasted words, the local model only, and nothing leaves the PC.
 *
 * NOTHING IS SAVED ON THIS PHONE. The open quiz is held in memory by
 * [JarvisRuntime.quiz]; the pasted text, the answer being typed and the
 * summary live in this screen's memory only (plain `remember`, never
 * `rememberSaveable`, never a file or a preference).
 *
 * "Hide memory lists and chat history" blanks every question, comment and
 * passage and does not offer the paste box or the answer box (typing over
 * words you cannot see is not offered, like Goals); Finish and Stop keep
 * working blind. Screenshots are already blocked app-wide while it is on.
 * Changes are held on a stale link (rule 4).
 */
@Composable
internal fun QuizSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val open by JarvisRuntime.quiz.collectAsState()
    var pasted by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var draft by remember { mutableStateOf("") }
    // The question just marked, shown with its mark until "Next question".
    var reviewing by remember { mutableStateOf<Int?>(null) }
    // The end-of-quiz summary and the questions it points at (the PC has
    // deleted the session by then, so the words are kept here for this view).
    var summary by remember { mutableStateOf<Quiz.Summary?>(null) }
    var summaryQuestions by remember { mutableStateOf<List<Quiz.Question>>(emptyList()) }

    // Coming back to Brain with a quiz still open: ask the PC whether it is
    // still there (it ends after 60 minutes unused).
    LaunchedEffect(open?.id) {
        if (open != null) {
            JarvisRuntime.refreshQuiz()?.let { said = it }
        }
    }

    fun shownQuiz(): Quiz.Session? = open?.let { if (privateHidden) Quiz.hide(it) else it }

    fun start() {
        if (!canAct || busy || !Quiz.validText(pasted)) return
        busy = true
        said = null
        scope.launch {
            try {
                val (ok, sentence) = JarvisRuntime.startQuiz(pasted)
                if (ok) {
                    // The text is not kept: it is cleared the moment it is sent on.
                    pasted = ""
                    draft = ""
                    reviewing = null
                    summary = null
                    summaryQuestions = emptyList()
                } else {
                    said = sentence
                }
            } finally {
                busy = false
            }
        }
    }

    Section(Quiz.TITLE) {
        Plate {
            Text(Quiz.INTRO, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val quiz = shownQuiz()
            val sum = summary
            if (privateHidden && (quiz != null || sum != null)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Words hidden. Tap Show and confirm it is you.",
                        style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                        modifier = Modifier.weight(1f),
                    )
                    Quiet(
                        if (showPrivateBusy) "Checking…" else "Show",
                        enabled = !showPrivateBusy, onClick = onShowPrivate,
                    )
                }
            }
            when {
                sum != null -> SummaryView(
                    summary = sum,
                    questions = summaryQuestions,
                    hidden = privateHidden,
                    onDone = {
                        summary = null
                        summaryQuestions = emptyList()
                        said = null
                    },
                )
                quiz != null -> {
                    val reviewN = reviewing
                    val current = if (reviewN != null) quiz.questions.firstOrNull { it.n == reviewN } else Quiz.next(quiz)
                    val total = quiz.questions.size
                    if (current != null) {
                        QuestionView(
                            q = current,
                            progress = if (privateHidden) "" else Quiz.progressLine(quiz),
                            verified = quiz.graderVerified,
                            hidden = privateHidden,
                            answer = draft,
                            onAnswerChange = { draft = it.take(Quiz.MAX_ANSWER) },
                            busy = busy,
                            enabled = canAct && !busy,
                            onCheck = {
                                if (canAct && !busy && Quiz.validAnswer(draft)) {
                                    busy = true
                                    said = null
                                    val n = current.n
                                    val typed = draft
                                    scope.launch {
                                        try {
                                            val (mark, sentence) = JarvisRuntime.answerQuiz(n, typed)
                                            if (mark != null) {
                                                reviewing = n
                                                draft = ""
                                            } else {
                                                said = sentence
                                            }
                                        } finally {
                                            busy = false
                                        }
                                    }
                                }
                            },
                            onNext = {
                                reviewing = null
                                draft = ""
                                said = null
                            },
                            moreToAnswer = quiz.questions.any { it.mark == null },
                        )
                    } else {
                        Text(
                            "Every question is answered. Tap Finish to see what to look at again.",
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                        )
                    }
                    Gap(6)
                    Text(Quiz.OUTSIDE_TEXT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Quiet(
                            Quiz.FINISH,
                            enabled = canAct && !busy,
                            onClick = {
                                busy = true
                                said = null
                                val questions = quiz.questions
                                scope.launch {
                                    try {
                                        val (s, sentence) = JarvisRuntime.finishQuiz()
                                        if (s != null) {
                                            summaryQuestions = questions
                                            summary = s
                                            reviewing = null
                                            draft = ""
                                        } else {
                                            said = sentence
                                        }
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                        )
                        Quiet(
                            Quiz.STOP,
                            color = chrome.badInk,
                            enabled = canAct && !busy,
                            onClick = {
                                busy = true
                                said = null
                                scope.launch {
                                    try {
                                        val (ok, sentence) = JarvisRuntime.stopQuiz()
                                        said = sentence
                                        if (ok) {
                                            reviewing = null
                                            draft = ""
                                        }
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                        )
                    }
                }
                open != null -> Unit
                else -> {
                    if (!privateHidden) {
                        TextInput(
                            value = pasted,
                            // Never cut silently: an over-long paste keeps its words, shows
                            // its real count and the too-long message, and Write questions waits.
                            onValueChange = { pasted = it },
                            placeholder = Quiz.PASTE_HINT,
                            singleLine = false,
                            maxLines = 8,
                        )
                        val n = Quiz.textLength(pasted)
                        val tooLong = n > Quiz.MAX_TEXT
                        Text(
                            Quiz.textNote(pasted),
                            style = MaterialTheme.typography.labelSmall,
                            color = if (tooLong || n in 1 until Quiz.MIN_TEXT) chrome.warnInk else chrome.textLo,
                            modifier = Modifier.liveStatus(),
                        )
                        if (tooLong) {
                            Text(
                                Quiz.messageFor(Quiz.E_TEXT_LONG).orEmpty(),
                                style = MaterialTheme.typography.labelSmall, color = chrome.warnInk,
                            )
                        }
                        Text(Quiz.OUTSIDE_TEXT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Quiet(
                            if (busy) Quiz.STARTING else Quiz.START,
                            enabled = canAct && !busy && Quiz.validText(pasted),
                            onClick = { start() },
                        )
                    } else {
                        Text(
                            "Show your lists to paste a text for a quiz.",
                            style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                        )
                        Quiet(
                            if (showPrivateBusy) "Checking…" else "Show",
                            enabled = !showPrivateBusy, onClick = onShowPrivate,
                        )
                    }
                }
            }
            said?.let {
                Gap(4)
                Text(
                    it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            if (!canAct) {
                Text(
                    "Not connected to the desktop, so changes wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One question: its words, then either the answer box or (once marked) the mark, comment and passage. */
@Composable
private fun QuestionView(
    q: Quiz.Question,
    progress: String,
    verified: Boolean,
    hidden: Boolean,
    answer: String,
    onAnswerChange: (String) -> Unit,
    busy: Boolean,
    enabled: Boolean,
    onCheck: () -> Unit,
    onNext: () -> Unit,
    moreToAnswer: Boolean,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        if (progress.isNotEmpty()) {
            Text(progress, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Quiz.kindWords(q.kind).takeIf { it.isNotEmpty() }?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Text(
            if (hidden) Quiz.HIDDEN_TEXT else q.prompt,
            style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
        )
        val mark = q.mark
        if (mark == null) {
            if (!hidden) {
                Gap(6)
                TextInput(
                    value = answer,
                    onValueChange = onAnswerChange,
                    placeholder = Quiz.ANSWER_HINT,
                    singleLine = false,
                    maxLines = 6,
                )
                Text(
                    Quiz.answerNote(answer),
                    style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                )
                Quiet(
                    if (busy) Quiz.CHECKING else Quiz.ANSWER,
                    enabled = enabled && Quiz.validAnswer(answer),
                    onClick = onCheck,
                )
            } else {
                Text(
                    "Show your lists to type an answer.",
                    style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                )
            }
        } else {
            Gap(6)
            Text(
                Quiz.markLine(mark, verified),
                style = MaterialTheme.typography.titleSmall,
                color = when (mark.level) {
                    "got_it" -> chrome.okInk
                    "partly" -> chrome.warnInk
                    else -> chrome.textHi
                },
                modifier = Modifier.liveStatus(),
            )
            if (!hidden && mark.comment.isNotEmpty()) {
                Text(mark.comment, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            if (!hidden && mark.passage.isNotEmpty()) {
                Gap(4)
                Text(Quiz.PASSAGE_LABEL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Text(mark.passage, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            if (moreToAnswer) {
                Quiet(Quiz.NEXT, enabled = enabled, onClick = onNext)
            }
        }
    }
}

/** "Look at these again": counts in words, then the questions to revisit. */
@Composable
private fun SummaryView(
    summary: Quiz.Summary,
    questions: List<Quiz.Question>,
    hidden: Boolean,
    onDone: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Text(Quiz.SUMMARY_TITLE, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Text(
            Quiz.countsLine(summary),
            style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus(),
        )
        Gap(4)
        if (summary.again.isEmpty()) {
            Text(Quiz.SUMMARY_EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        } else {
            summary.again.forEach { n ->
                Text(
                    Quiz.againLine(n, questions, hidden),
                    style = MaterialTheme.typography.bodySmall, color = chrome.textHi,
                )
            }
        }
        Gap(4)
        Text(Quiz.OUTSIDE_TEXT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Quiet(Quiz.CLOSE, onClick = onDone)
    }
}
