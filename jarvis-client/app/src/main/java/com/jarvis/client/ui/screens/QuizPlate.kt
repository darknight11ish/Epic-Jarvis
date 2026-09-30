package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Checkbox
import androidx.compose.material3.LocalTextStyle
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Decks
import com.jarvis.client.net.Quiz
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
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
 *
 * Spanish practice and Keep (docs/QUIZ-DECKS-DESIGN.md, contract C2-C3): a
 * mode chooser (Text / Spanish practice), a level, an exercise, an optional
 * topic and Spanish text, an accent row under the answer box, "Answer: ..."
 * after a mark, and "Keep these questions" beside Finish - a sheet listing
 * every answered question word for word, with a tick each, the owner's own
 * words for the back and a deck to keep them in. Nothing is sent until "Keep
 * and finish". The answers this screen sent are held in this screen's memory
 * until the quiz ends (never a crisis answer, never a file).
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
    val spanishSupported by JarvisRuntime.spanishSupported.collectAsState()
    val rememberedNotice by JarvisRuntime.spanishNotice.collectAsState()
    var pasted by remember { mutableStateOf("") }
    // Spanish practice's start form (the level and exercise are requests; the PC's default otherwise).
    var mode by remember { mutableStateOf(Quiz.MODE_TEXT) }
    var level by remember { mutableStateOf(Quiz.DEFAULT_LEVEL) }
    var exercise by remember { mutableStateOf(Quiz.DEFAULT_EXERCISE) }
    var topic by remember { mutableStateOf("") }
    var spanishText by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    // A crisis answer's help words (the PC's own text, JARVIS-API 98.4), shown
    // in place of a mark until the next action. Memory of this screen only.
    var crisis by remember { mutableStateOf<String?>(null) }
    var draft by remember { mutableStateOf("") }
    // The question just marked, shown with its mark until "Next question".
    var reviewing by remember { mutableStateOf<Int?>(null) }
    // The end-of-quiz summary and the questions it points at (the PC has
    // deleted the session by then, so the words are kept here for this view).
    var summary by remember { mutableStateOf<Quiz.Summary?>(null) }
    var summaryQuestions by remember { mutableStateOf<List<Quiz.Question>>(emptyList()) }
    var keptCount by remember { mutableStateOf<Int?>(null) }
    // The owner's own typed answers that were marked, by question number, held
    // only for the Keep sheet's prefill. Never a crisis answer; gone when the quiz ends.
    var answers by remember { mutableStateOf(mapOf<Int, String>()) }
    // The Keep sheet (contract C3).
    var keeping by remember { mutableStateOf(false) }
    var keepTicks by remember { mutableStateOf(mapOf<Int, Boolean>()) }
    var keepBacks by remember { mutableStateOf(mapOf<Int, String>()) }
    var deckChoice by remember { mutableStateOf<String?>(null) }
    var newDeckName by remember { mutableStateOf("") }
    var nameError by remember { mutableStateOf<String?>(null) }
    var deckList by remember { mutableStateOf<Decks.DeckList?>(null) }
    var deckReadError by remember { mutableStateOf<String?>(null) }

    // Coming back to Brain with a quiz still open: ask the PC whether it is
    // still there (it ends after 60 minutes unused).
    LaunchedEffect(open?.id) {
        if (open != null) {
            JarvisRuntime.refreshQuiz()?.let { said = it }
        }
    }

    // An older PC has no Spanish practice: Text mode only.
    LaunchedEffect(spanishSupported) {
        if (spanishSupported == false) mode = Quiz.MODE_TEXT
    }

    // The Keep sheet lists the owner's words, so it closes when the lists are hidden.
    LaunchedEffect(privateHidden) {
        if (privateHidden) keeping = false
    }

    // The quiz is over (or was never there): nothing of it stays in this screen.
    LaunchedEffect(open == null) {
        if (open == null) {
            answers = emptyMap()
            keeping = false
        }
    }

    fun shownQuiz(): Quiz.Session? = open?.let { if (privateHidden) Quiz.hide(it) else it }

    suspend fun readDecks() {
        val out = JarvisRuntime.decksList()
        val v = out.value
        if (out.ok && v != null) {
            deckList = v
            deckReadError = null
            if (deckChoice != null && v.decks.none { it.id == deckChoice }) deckChoice = null
        } else {
            deckReadError = out.said
        }
    }

    fun openKeep(q: Quiz.Session) {
        // Ticked by default for Partly / Not yet; the back is the owner's own answer
        // only for Got it (and only if this screen still has it), empty otherwise.
        val marked = q.questions.mapNotNull { qu -> qu.mark?.let { qu.n to it } }
        keepTicks = marked.associate { (n, m) -> n to (m.level != "got_it") }
        keepBacks = marked.associate { (n, m) -> n to (if (m.level == "got_it") answers[n].orEmpty() else "") }
        deckChoice = null
        newDeckName = Quiz.defaultDeckName(q.title)
        nameError = null
        deckList = null
        deckReadError = null
        said = null
        keeping = true
        scope.launch { readDecks() }
    }

    fun start() {
        val spanish = mode == Quiz.MODE_SPANISH && spanishSupported != false
        val text = if (spanish) spanishText else pasted
        val valid = if (spanish) Quiz.validSpanishText(text) else Quiz.validText(text)
        if (!canAct || busy || !valid) return
        busy = true
        said = null
        scope.launch {
            try {
                val (ok, sentence) = JarvisRuntime.startQuiz(
                    text,
                    mode = if (spanish) Quiz.MODE_SPANISH else Quiz.MODE_TEXT,
                    level = level,
                    exercise = exercise,
                    topic = topic,
                )
                if (ok) {
                    crisis = null
                    // The text is not kept: it is cleared the moment it is sent on.
                    pasted = ""
                    spanishText = ""
                    draft = ""
                    reviewing = null
                    summary = null
                    summaryQuestions = emptyList()
                    keptCount = null
                    answers = emptyMap()
                    keeping = false
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
                    kept = keptCount,
                    onDone = {
                        summary = null
                        summaryQuestions = emptyList()
                        keptCount = null
                        said = null
                    },
                )
                quiz != null -> {
                    if (quiz.mode == Quiz.MODE_SPANISH) {
                        quiz.level?.let {
                            Text(
                                Quiz.levelLine(it),
                                style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            )
                        }
                        quiz.notice?.let {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                    }
                    val help = crisis
                    if (help != null) CrisisView(help)
                    val answeredQs = open?.questions?.filter { it.mark != null }.orEmpty()
                    if (keeping) {
                        KeepSheet(
                            session = quiz,
                            answered = answeredQs.map { a -> quiz.questions.firstOrNull { it.n == a.n } ?: a },
                            ticks = keepTicks,
                            backs = keepBacks,
                            onTick = { n, on -> keepTicks = keepTicks + (n to on) },
                            onBack = { n, v -> keepBacks = keepBacks + (n to v.take(Quiz.MAX_ANSWER)) },
                            decks = deckList,
                            deckReadError = deckReadError,
                            choice = deckChoice,
                            onChoice = {
                                deckChoice = it
                                nameError = null
                            },
                            newName = newDeckName,
                            onNewName = {
                                newDeckName = it.take(Quiz.MAX_DECK_NAME)
                                nameError = null
                            },
                            nameError = nameError,
                            busy = busy,
                            enabled = canAct && !busy,
                            onCancel = {
                                keeping = false
                                said = null
                            },
                            onKeep = {
                                val cards = answeredQs
                                    .filter { keepTicks[it.n] == true }
                                    .map { Quiz.KeepCard(it.n, keepBacks[it.n].orEmpty()) }
                                val questions = quiz.questions
                                busy = true
                                said = null
                                nameError = null
                                scope.launch {
                                    try {
                                        val out = JarvisRuntime.keepQuiz(
                                            deck = deckChoice,
                                            newDeck = if (deckChoice == null) newDeckName else null,
                                            cards = cards,
                                        )
                                        val done = out.value
                                        if (out.ok && done != null) {
                                            val words = done.crisis
                                            if (words != null) {
                                                // Nothing was kept and the quiz is still open: the
                                                // PC's help words, calmly, with the sheet as it was.
                                                crisis = words
                                            } else {
                                                crisis = null
                                                summaryQuestions = questions
                                                summary = done.summary
                                                keptCount = done.kept
                                                keeping = false
                                                answers = emptyMap()
                                                draft = ""
                                                reviewing = null
                                            }
                                        } else {
                                            said = out.said
                                            if (out.code == "bad_deck_name") nameError = out.said
                                            if (out.code == Decks.E_NOT_FOUND) {
                                                deckChoice = null
                                                readDecks()
                                            }
                                            if (out.gone) keeping = false
                                        }
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                        )
                    } else {
                        val reviewN = reviewing
                        val current = if (reviewN != null) quiz.questions.firstOrNull { it.n == reviewN } else Quiz.next(quiz)
                        if (current != null) {
                            QuestionView(
                                q = current,
                                session = quiz,
                                progress = if (privateHidden) "" else Quiz.progressLine(quiz),
                                hidden = privateHidden,
                                answer = draft,
                                onAnswerChange = { draft = it.take(Quiz.MAX_ANSWER) },
                                busy = busy,
                                enabled = canAct && !busy,
                                onCheck = {
                                    if (canAct && !busy && Quiz.validAnswer(draft)) {
                                        busy = true
                                        said = null
                                        crisis = null
                                        val n = current.n
                                        val typed = draft
                                        scope.launch {
                                            try {
                                                val (result, sentence) = JarvisRuntime.answerQuiz(n, typed)
                                                val helpWords = result?.crisis
                                                if (helpWords != null) {
                                                    // Not marked: the PC's help words, the question stays
                                                    // open, and the typed words are let go.
                                                    crisis = helpWords
                                                    reviewing = null
                                                    draft = ""
                                                } else if (result?.mark != null) {
                                                    reviewing = n
                                                    draft = ""
                                                    // Held in memory for the Keep sheet only; never a crisis answer.
                                                    answers = answers + (n to typed)
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
                                    crisis = null
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
                        if (quiz.mode != Quiz.MODE_SPANISH || quiz.keySource != "model") {
                            Text(Quiz.OUTSIDE_TEXT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
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
                                            val (sm, sentence) = JarvisRuntime.finishQuiz()
                                            if (sm != null) {
                                                crisis = null
                                                summaryQuestions = questions
                                                summary = sm
                                                keptCount = null
                                                reviewing = null
                                                draft = ""
                                                answers = emptyMap()
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
                                Quiz.KEEP_OPEN,
                                enabled = canAct && !busy && !privateHidden && answeredQs.isNotEmpty(),
                                onClick = { open?.let { openKeep(it) } },
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
                                                crisis = null
                                                reviewing = null
                                                draft = ""
                                                answers = emptyMap()
                                            }
                                        } finally {
                                            busy = false
                                        }
                                    }
                                },
                            )
                        }
                        if (privateHidden && answeredQs.isNotEmpty()) {
                            Text(Quiz.KEEP_HIDDEN, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                    }
                }
                open != null -> Unit
                else -> {
                    if (!privateHidden) {
                        StartForm(
                            mode = mode,
                            onMode = { mode = it; said = null },
                            supported = spanishSupported,
                            notice = rememberedNotice,
                            pasted = pasted,
                            onPasted = { pasted = it },
                            spanishText = spanishText,
                            onSpanishText = { spanishText = it },
                            level = level,
                            onLevel = { level = it },
                            exercise = exercise,
                            onExercise = { exercise = it },
                            topic = topic,
                            onTopic = { topic = it.take(Quiz.MAX_TOPIC) },
                            busy = busy,
                            canAct = canAct,
                            onStart = { start() },
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

/**
 * A row of one-of-several choices: the chosen one carries a tick in front and
 * its words for a screen reader end in "selected". 48dp targets (Quiet).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoiceRow(
    choices: List<Pair<String, String>>,
    selected: String,
    enabled: Boolean = true,
    onPick: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        choices.forEach { (id, label) ->
            val on = id == selected
            Quiet(
                if (on) "✓ $label" else label,
                modifier = Modifier.semantics { contentDescription = if (on) "$label, selected" else label },
                color = if (on) null else chrome.textMid,
                enabled = enabled,
                onClick = { onPick(id) },
            )
        }
    }
}

/** The start form: the mode chooser, then Text mode's paste box or Spanish practice's options. */
@Composable
private fun StartForm(
    mode: String,
    onMode: (String) -> Unit,
    supported: Boolean?,
    notice: String?,
    pasted: String,
    onPasted: (String) -> Unit,
    spanishText: String,
    onSpanishText: (String) -> Unit,
    level: String,
    onLevel: (String) -> Unit,
    exercise: String,
    onExercise: (String) -> Unit,
    topic: String,
    onTopic: (String) -> Unit,
    busy: Boolean,
    canAct: Boolean,
    onStart: () -> Unit,
) {
    val chrome = LocalChrome.current
    val spanish = mode == Quiz.MODE_SPANISH && supported != false
    if (supported == false) {
        // An older PC: Text mode only, and it says why (contract C2).
        Text(Quiz.OLD_PC, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    } else {
        ChoiceRow(
            choices = listOf(Quiz.MODE_TEXT to Quiz.MODE_TEXT_LABEL, Quiz.MODE_SPANISH to Quiz.MODE_SPANISH_LABEL),
            selected = if (spanish) Quiz.MODE_SPANISH else Quiz.MODE_TEXT,
            enabled = !busy,
            onPick = onMode,
        )
        if (spanish && notice != null) {
            Text(notice, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    if (!spanish) {
        TextInput(
            value = pasted,
            // Never cut silently: an over-long paste keeps its words, shows
            // its real count and the too-long message, and Write questions waits.
            onValueChange = onPasted,
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
            onClick = onStart,
        )
        return
    }
    Gap(4)
    Text(Quiz.LEVEL_HEADING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    ChoiceRow(Quiz.LEVELS.map { it to it }, level, enabled = !busy, onPick = onLevel)
    Text(Quiz.levelLine(level), style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
    Gap(4)
    Text(Quiz.EXERCISE_HEADING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    ChoiceRow(Quiz.EXERCISES, exercise, enabled = !busy, onPick = onExercise)
    Gap(4)
    TextInput(
        value = topic,
        onValueChange = onTopic,
        label = Quiz.TOPIC_LABEL,
        supportingText = "${topic.length} / ${Quiz.MAX_TOPIC}",
    )
    Gap(4)
    TextInput(
        value = spanishText,
        onValueChange = onSpanishText,
        placeholder = Quiz.SPANISH_HINT,
        singleLine = false,
        maxLines = 8,
    )
    if (spanishText.isNotBlank()) {
        val n = Quiz.textLength(spanishText)
        val bad = n < Quiz.MIN_TEXT || n > Quiz.MAX_TEXT
        Text(
            Quiz.textNote(spanishText),
            style = MaterialTheme.typography.labelSmall,
            color = if (bad) chrome.warnInk else chrome.textLo,
        )
        Text(Quiz.OUTSIDE_TEXT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    Quiet(
        if (busy) Quiz.STARTING else Quiz.START,
        enabled = canAct && !busy && Quiz.validSpanishText(spanishText),
        onClick = onStart,
    )
}

/**
 * A crisis answer's help words, in place of a mark: the PC's own text (the same
 * words chat shows), drawn calmly - no warning colour, no mark, no "Jarvis's
 * guess". `**bold**` in the text is drawn bold; nothing else is interpreted.
 */
@Composable
private fun CrisisView(message: String) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().liveStatus()) {
        for (para in Quiz.crisisParagraphs(message)) {
            Text(
                buildAnnotatedString {
                    for (run in para) {
                        if (run.bold) withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(run.text) }
                        else append(run.text)
                    }
                },
                style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
            )
            Gap(6)
        }
    }
}

/**
 * The Spanish answer box: the same flat field as the other text boxes, with a
 * row of nine buttons under it that put an accented letter or ¿ ¡ in at the
 * cursor. The box's limit is still [Quiz.MAX_ANSWER]; nothing is cut silently
 * (a button that would go over the limit does nothing).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AccentInput(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    enabled: Boolean,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    var focused by remember { mutableStateOf(false) }
    var field by remember { mutableStateOf(TextFieldValue(value, TextRange(value.length))) }
    // The screen clears or trims the draft: the box follows.
    LaunchedEffect(value) {
        if (field.text != value) field = TextFieldValue(value, TextRange(value.length))
    }
    Column(Modifier.fillMaxWidth()) {
        Box(
            Modifier
                .fillMaxWidth()
                .clip(radii.controlShape)
                .background(chrome.surface2)
                .border(
                    width = if (focused) 2.dp else 1.dp,
                    color = if (focused) accent else chrome.hairlineFocus,
                    shape = radii.controlShape,
                )
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            if (value.isEmpty()) {
                Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = chrome.textLo)
            }
            BasicTextField(
                value = field,
                onValueChange = { next ->
                    field = next
                    if (next.text != value) onValueChange(next.text)
                },
                textStyle = LocalTextStyle.current.merge(
                    MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                ),
                cursorBrush = SolidColor(accent),
                singleLine = false,
                maxLines = 6,
                modifier = Modifier
                    .fillMaxWidth()
                    .onFocusChanged { focused = it.isFocused },
            )
        }
        Text(
            Quiz.ACCENT_ROW_LABEL,
            style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            Quiz.ACCENTS.forEach { ch ->
                Quiet(
                    ch,
                    modifier = Modifier.semantics { contentDescription = "Insert $ch" },
                    enabled = enabled,
                    onClick = {
                        val r = Quiz.insertAt(field.text, field.selection.min, field.selection.max, ch)
                        if (r != null) {
                            field = TextFieldValue(r.first, TextRange(r.second))
                            onValueChange(r.first)
                        }
                    },
                )
            }
        }
    }
}

/** One question: its words, then either the answer box or (once marked) the mark, comment and passage. */
@Composable
private fun QuestionView(
    q: Quiz.Question,
    session: Quiz.Session,
    progress: String,
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
    val spanish = session.mode == Quiz.MODE_SPANISH
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
                if (spanish) {
                    session.notice?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    AccentInput(
                        value = answer,
                        onValueChange = onAnswerChange,
                        placeholder = Quiz.ANSWER_HINT,
                        enabled = enabled,
                    )
                } else {
                    TextInput(
                        value = answer,
                        onValueChange = onAnswerChange,
                        placeholder = Quiz.ANSWER_HINT,
                        singleLine = false,
                        maxLines = 6,
                    )
                }
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
                Quiz.markLine(mark, session.graderVerified),
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
            val expected = mark.expected
            if (!hidden && expected != null) {
                Text(
                    Quiz.ANSWER_PREFIX + expected,
                    style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                )
                mark.keyLabel?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
            if (!hidden && mark.passage.isNotEmpty()) {
                Gap(4)
                Text(Quiz.passageHeading(session), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Text(mark.passage, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            if (moreToAnswer) {
                Quiet(Quiz.NEXT, enabled = enabled, onClick = onNext)
            }
        }
    }
}

/**
 * The Keep sheet (contract C3): every answered question with a tick, its
 * passage, and a box for the back in the owner's own words; then a deck to
 * keep them in. Nothing is sent until "Keep and finish".
 */
@Composable
private fun KeepSheet(
    session: Quiz.Session,
    answered: List<Quiz.Question>,
    ticks: Map<Int, Boolean>,
    backs: Map<Int, String>,
    onTick: (Int, Boolean) -> Unit,
    onBack: (Int, String) -> Unit,
    decks: Decks.DeckList?,
    deckReadError: String?,
    choice: String?,
    onChoice: (String?) -> Unit,
    newName: String,
    onNewName: (String) -> Unit,
    nameError: String?,
    busy: Boolean,
    enabled: Boolean,
    onCancel: () -> Unit,
    onKeep: () -> Unit,
) {
    val chrome = LocalChrome.current
    val ticked = answered.count { ticks[it.n] == true }
    val unavailable = decks != null && !decks.available
    val nameOk = choice != null || Decks.validName(newName)
    val backsOk = answered.all { (backs[it.n] ?: "").length <= Quiz.MAX_ANSWER }
    Column(Modifier.fillMaxWidth()) {
        Text(Quiz.KEEP_OPEN, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        answered.forEach { qu ->
            Gap(10)
            val on = ticks[qu.n] == true
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = on,
                    onCheckedChange = { onTick(qu.n, it) },
                    enabled = enabled,
                    modifier = Modifier.semantics { contentDescription = "Keep question ${qu.n}: ${qu.prompt}" },
                )
                Text(
                    qu.prompt,
                    style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
            }
            val passage = qu.mark?.passage.orEmpty()
            if (passage.isNotEmpty()) {
                Text(Quiz.passageHeading(session), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Text(passage, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            val back = backs[qu.n].orEmpty()
            TextInput(
                value = back,
                onValueChange = { onBack(qu.n, it) },
                placeholder = Quiz.KEEP_HINT,
                singleLine = false,
                maxLines = 4,
            )
            Text(
                Quiz.answerNote(back),
                style = MaterialTheme.typography.labelSmall,
                color = if (back.length > Quiz.MAX_ANSWER) chrome.warnInk else chrome.textLo,
            )
        }
        Gap(12)
        Text(Quiz.CHOOSE_DECK, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        when {
            deckReadError != null -> Text(deckReadError, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            decks == null -> Text(Decks.READING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            unavailable -> Text(decks.why, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            else -> {
                ChoiceRow(
                    choices = decks.decks.map { it.id to "${it.name} (${Decks.cardsWords(it.cards)})" } +
                        listOf("" to Quiz.NEW_DECK),
                    selected = choice ?: "",
                    enabled = enabled,
                    onPick = { onChoice(it.ifEmpty { null }) },
                )
                if (choice == null) {
                    TextInput(
                        value = newName,
                        onValueChange = onNewName,
                        placeholder = Quiz.DECK_NAME,
                        supportingText = nameError ?: "${newName.length} / ${Quiz.MAX_DECK_NAME}",
                        supportingColor = if (nameError != null) chrome.warnInk else null,
                    )
                }
            }
        }
        Gap(6)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Quiet(
                if (busy) Quiz.KEEPING else Quiz.KEEP_DO,
                enabled = enabled && ticked > 0 && decks != null && decks.available && deckReadError == null &&
                    nameOk && backsOk,
                onClick = onKeep,
            )
            Quiet(Quiz.CANCEL, enabled = !busy, onClick = onCancel)
        }
    }
}

/** "Look at these again": counts in words, then the questions to revisit; after a Keep, how many were kept. */
@Composable
private fun SummaryView(
    summary: Quiz.Summary,
    questions: List<Quiz.Question>,
    hidden: Boolean,
    kept: Int?,
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
        if (kept != null) {
            Text(
                Quiz.keptLine(kept),
                style = MaterialTheme.typography.bodySmall, color = chrome.okInk,
                modifier = Modifier.liveStatus(),
            )
        }
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
