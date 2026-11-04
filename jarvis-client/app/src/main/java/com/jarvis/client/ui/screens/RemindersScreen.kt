package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.AlsoOnPhone
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Reminders
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The phone's own Reminders screen (the owner's ask of 2026-11-02: *"I want a
 * custom reminders screen on the jarvis Android app ... I also want another
 * option within the reminders that includes a daily to-do list"*).
 *
 * Until this screen existed, Home's Reminders button opened Brain -> Coming up -
 * a subsection of the Brain. It now opens this screen, which has TWO choices
 * down the top, and the Brain plate is unchanged and still there behind its own
 * menu (`brain.work.coming-up`, which can never be hidden).
 *
 *  - **Reminders** ([Reminders.TAB_JOBS]) - the timers, alarms, reminders and
 *    repeating jobs, read from the one route the Brain plate reads
 *    ([Schedule.PATH]). "Just went off" comes first with Snooze and Delete, then
 *    the rows. Each row offers exactly the buttons the app offered before
 *    ([Schedule.actionsOf] - Pause, Resume, Delete, Done, "+5 minutes"), one job
 *    per tap, plus "Also on my phone" where an alarm or a reminder can be handed
 *    to the phone's own Clock or calendar. Nothing here asks for a new
 *    permission, raises a card, or adds a bulk action: a write that raises a card
 *    on the PC still raises it, and one that needed none still needs none.
 *  - **Daily to-do list** ([Reminders.TAB_TODO]) - the scheduler's to-do list in
 *    the PC's own two ways of showing it (JARVIS-API section 179): daily
 *    rollover, where each older item carries the PC's age tag, and day by day,
 *    where the same items sit under the day the PC says each was written. Add,
 *    Done and Delete are the API's own three writes; there is no delete-all and
 *    no bulk anything. The named lists ("shopping") stay in the Brain plate,
 *    where their one "Clear list" already lives, and this tab says where to find
 *    them rather than growing a second copy of that surface.
 *
 * THE SAME GUARDS AS THE REST OF THE APP. Every write is held while the link is
 * down or stale (rule 4): the buttons are drawn disabled and the screen says so
 * instead of offering a tap that cannot work. "Hide memory lists and chat
 * history" hides the words of the reminders and the to-do items exactly as the
 * Brain plate does ([Schedule.hide]), with a Show that asks for the fingerprint
 * or PIN first, and the times stay so a timer still counts down.
 *
 * ONE READ, ONE CLOCK. The whole screen - both choices - comes from ONE
 * `GET /api/schedule`, re-read when the screen opens, on Refresh, after every
 * change and on every `schedule` event ([JarvisRuntime.scheduleTick]). A running
 * timer counts down once a second from what the PC last said, never from a
 * clock this phone keeps.
 */
@Composable
internal fun RemindersScreen(
    /** The link is live and not stale: every write is held until it is (rule 4). */
    canAct: Boolean,
    /** App lock or "Hide memory lists and chat history": the words are blanked. */
    privateHidden: Boolean,
    /** A Show is asking for the fingerprint or PIN right now. */
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.scheduleTick.collectAsState()

    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Schedule.View?>(null) }
    var readAt by remember { mutableLongStateOf(0L) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busyId by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    // Which of the two choices is on show. Saved by value, so a rotation comes
    // back on the same one instead of jumping to the reminders.
    var tab by rememberSaveable { mutableStateOf(Reminders.DEFAULT_TAB) }
    var todoText by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var modeBusy by remember { mutableStateOf(false) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.schedule()) {
            is ApiResult.Ok -> {
                val v = Schedule.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    readAt = System.currentTimeMillis()
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Schedule.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }
    // A running timer counts down here, once a second, from what the PC said.
    val ticking = Schedule.anyTicking(view)
    LaunchedEffect(ticking) {
        while (ticking) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }

    /** ONE job, one tap - the same call the Brain plate makes, held on a stale link. */
    fun act(job: Schedule.Job, action: String) {
        busyId = job.id
        said = null
        scope.launch {
            try {
                val (_, sentence) = JarvisRuntime.scheduleAct(job.id, action)
                said = sentence
            } finally {
                busyId = null
            }
        }
    }

    /**
     * ONE button of ONE part of a routine (2026-11-03): the same `answer` verb a
     * reminder's own question uses, with the part's index added - one part, one
     * button, one log line on the PC, and no card. The phone only ever ANSWERS a
     * part: making or changing a routine is the PC's job, because a part's
     * destination can be this PC's Obsidian vault or a goal/habit id.
     */
    fun answer(job: Schedule.Job, part: Int, button: Int) {
        busyId = job.id
        said = null
        scope.launch {
            try {
                val (_, sentence) = JarvisRuntime.scheduleAnswer(job.id, button, part)
                said = sentence
            } finally {
                busyId = null
            }
        }
    }

    /** ONE new to-do item, in the owner's words. */
    fun add() {
        if (todoText.isBlank() || !canAct || adding) return
        adding = true
        said = null
        scope.launch {
            try {
                val (changed, sentence) = JarvisRuntime.addTodo(todoText)
                if (changed) todoText = ""
                said = sentence
            } finally {
                adding = false
            }
        }
    }

    /**
     * ONE write of how the list is shown - the scheduler's own `todo_mode` on
     * [Schedule.ACT_PATH], the same value the Settings card and a spoken
     * sentence reach. No card either way: it moves no item and re-stamps no day.
     */
    fun chooseMode(value: String) {
        if (modeBusy || !canAct || value == view?.todoMode) return
        modeBusy = true
        said = null
        scope.launch {
            try {
                val (_, sentence) = JarvisRuntime.setTodoMode(value)
                said = sentence
            } finally {
                modeBusy = false
            }
        }
    }

    // The list with every word replaced while the private lists are hidden. The
    // times stay, so a timer still counts down; only the owner's words go.
    val shown = view?.let { if (privateHidden) Schedule.hide(it) else it }

    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(
            Reminders.TITLE,
            onBack,
            subtitle = if (tab == Reminders.TAB_JOBS && shown != null && !missing) {
                Reminders.countLine(Reminders.jobs(shown).size)
            } else {
                null
            },
            trailing = { Quiet("Refresh", onClick = { reads += 1 }) },
        )

        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            // ------------------------------------------------ the two choices ---
            // Two boxed choices, the one on show filled: the same pair of
            // controls every other two-way choice on this app uses, so neither
            // reads as the ordinary action and the other as an afterthought.
            // Tapping the one already on show does nothing, and a screen reader
            // is told which one that is.
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Reminders.TABS.forEach { name ->
                    val open = { tab = name }
                    if (name == tab) {
                        Primary(
                            name,
                            Modifier
                                .weight(1f)
                                .semantics { stateDescription = Reminders.SHOWN },
                            onClick = open,
                        )
                    } else {
                        Secondary(name, Modifier.weight(1f), onClick = open)
                    }
                }
            }
            Gap(12)

            if (tab == Reminders.TAB_TODO) {
                // -------------------------------------------- the to-do list ---
                Section(Reminders.TAB_TODO) {
                    Plate {
                        Text(
                            Reminders.TODO_UNDER,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        // Only once there is a list to talk about: a PC with no
                        // scheduler at all gets the honest "run apply-patches"
                        // line below instead of a sentence about how a list that
                        // does not exist is drawn.
                        if (!missing && shown != null) {
                            Gap(8)
                            ToDoModeChoices(
                                view = shown,
                                canAct = canAct,
                                busy = modeBusy,
                                onChoose = { chooseMode(it) },
                            )
                        }
                        // The same one Show as the reminders tab: the to-do items
                        // are the owner's own words, so while the private lists
                        // are hidden this tab must offer the way back too rather
                        // than leaving him to find the other choice first.
                        if (privateHidden) HiddenWordsRow(showPrivateBusy, onShowPrivate)
                    }
                }
                Gap(10)
                if (missing) {
                    Text(
                        Schedule.MISSING,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                } else if (shown == null) {
                    Text(
                        if (readError != null) "Couldn't read your to-do list: $readError" else "Reading…",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (readError != null) chrome.warnInk else chrome.textLo,
                    )
                } else {
                    val list = shown
                    // A refresh that failed keeps the list the owner last saw -
                    // but says so, so a stale row is never mistaken for a live
                    // one (the same line the reminders tab shows).
                    readError?.let {
                        Text(
                            "Couldn't read it again: $it",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    }
                    val items = Reminders.todoItems(list)
                    if (items.isEmpty()) {
                        Text(
                            Schedule.EMPTY_TODO,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    } else if (Reminders.isDayMode(list)) {
                        // Day by day: the PC's own headings ("Today",
                        // "Yesterday", "Friday (3d ago)"), each over the items
                        // written that day. The heading already names the day, so
                        // the rows carry no tag.
                        Reminders.dayGroups(list).forEach { day ->
                            if (day.label.isNotEmpty()) {
                                Gap(4)
                                Text(
                                    day.label,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo,
                                )
                            }
                            day.items.forEach { job ->
                                ScheduleRow(
                                    job,
                                    now - readAt,
                                    canAct && busyId == null,
                                    onSaid = { s -> said = s },
                                ) { a -> act(job, a) }
                            }
                        }
                    } else {
                        // Daily rollover: one list, each older item carrying the
                        // PC's own tag ("from yesterday", "from Friday (3d ago)").
                        items.forEach { job ->
                            ScheduleRow(
                                job,
                                now - readAt,
                                canAct && busyId == null,
                                carry = Reminders.itemTag(job, list.todoMode),
                            ) { a -> act(job, a) }
                        }
                    }
                    Gap(8)
                    TextInput(
                        value = todoText,
                        onValueChange = { todoText = it.take(Schedule.MAX_TEXT) },
                        placeholder = Schedule.ADD_HINT,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { add() }),
                    )
                    Quiet(
                        if (adding) "Adding…" else Schedule.ADD,
                        enabled = canAct && !adding && todoText.isNotBlank(),
                        onClick = { add() },
                    )
                    Gap(6)
                    Text(
                        Reminders.NAMED_LISTS_WHERE,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            } else {
                // ---------------------------------------------- the reminders ---
                Section(Schedule.TITLE) {
                    Plate {
                        Text(
                            Reminders.JOBS_UNDER,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                        Gap(6)
                        if (privateHidden) HiddenWordsRow(showPrivateBusy, onShowPrivate)
                        if (missing) {
                            Text(
                                Schedule.MISSING,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        } else if (shown == null) {
                            Text(
                                if (readError != null) {
                                    "Couldn't read Coming up: $readError"
                                } else {
                                    "Reading…"
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = if (readError != null) chrome.warnInk else chrome.textLo,
                            )
                        } else {
                            val list = shown
                            readError?.let {
                                Text(
                                    "Couldn't read it again: $it",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.warnInk,
                                )
                            }
                            // Just went off (the last hour): Snooze and Delete,
                            // one job per tap - the same rows and words the Brain
                            // plate draws.
                            if (list.wentOff.isNotEmpty()) {
                                Text(
                                    Schedule.WENT_OFF_TITLE,
                                    style = MaterialTheme.typography.labelMedium,
                                    color = chrome.textMid,
                                )
                                Text(
                                    Schedule.WENT_OFF_DETAIL,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo,
                                )
                                list.wentOff.forEach { job ->
                                    WentOffRow(
                                        job,
                                        canAct && busyId == null,
                                        onAnswer = { p, b -> answer(job, p, b) },
                                    ) { a -> act(job, a) }
                                }
                                Gap(14)
                            }
                            val jobs = Reminders.jobs(list)
                            if (jobs.isEmpty()) {
                                Gap(4)
                                Text(
                                    Schedule.EMPTY_JOBS,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textMid,
                                )
                            }
                            jobs.forEach { job ->
                                ScheduleRow(
                                    job,
                                    now - readAt,
                                    canAct && busyId == null,
                                    onSaid = { s -> said = s },
                                    onAnswer = { p, b -> answer(job, p, b) },
                                ) { a -> act(job, a) }
                            }
                            // "Also on my phone": the one line saying what it
                            // does and warning about two alarms and Google, once,
                            // while a row offers it.
                            if (AlsoOnPhone.anyOffered(jobs, System.currentTimeMillis())) {
                                Gap(6)
                                Text(
                                    AlsoOnPhone.NOTE,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo,
                                )
                            }
                        }
                    }
                }
            }

            Gap(8)
            said?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            if (!missing && shown != null && !canAct) {
                Text(
                    Reminders.NOT_CONNECTED,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/**
 * How the to-do list is shown: the PC's own two modes as two words, the one in
 * force marked "(now)" with the PC's own sentence under it - the same shape and
 * words as Settings' "To-do list carry-over" card
 * (ui/screens/TodoCarryoverPlate.kt), on the same one value.
 *
 * A PC from before the two ways sends no `todo_modes`: it has one real
 * behaviour (daily rollover) and no route to change it, so this says so instead
 * of offering a button that could only fail.
 */
@Composable
private fun ToDoModeChoices(
    view: Schedule.View?,
    canAct: Boolean,
    busy: Boolean,
    onChoose: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    Text(
        Reminders.SHOWING_TITLE,
        style = MaterialTheme.typography.labelMedium,
        color = chrome.textMid,
    )
    if (!Reminders.canChangeMode(view)) {
        Text(
            Reminders.SHOWING_FIXED,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        return
    }
    val current = view?.todoMode ?: Schedule.MODE_ROLLOVER
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Reminders.modeChoices(view).forEach { mode ->
            Quiet(
                Reminders.modeLabel(mode, current),
                enabled = canAct && !busy && mode.value != current,
                onClick = { onChoose(mode.value) },
            )
        }
    }
    Reminders.modeChoices(view).firstOrNull { it.value == current }
        ?.detail
        ?.takeIf { it.isNotEmpty() }
        ?.let {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    Text(
        if (busy) "Saving…" else Reminders.SHOWING_ON_PC,
        style = MaterialTheme.typography.labelSmall,
        color = chrome.textLo,
    )
}

/**
 * "Words hidden. Tap Show and confirm it is you." - drawn on BOTH choices, so
 * neither is a dead end while App lock or "Hide memory lists and chat history"
 * is on. The Show is the app's one owner check, handed in by MainActivity
 * (`::showPrivateLists`): a fingerprint or PIN, and nothing is revealed until it
 * passes. The same sentence and the same control the Brain's Coming up plate
 * draws.
 */
@Composable
private fun HiddenWordsRow(busy: Boolean, onShow: () -> Unit) {
    val chrome = LocalChrome.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            Reminders.HIDDEN_WORDS,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        Quiet(
            if (busy) "Checking…" else "Show",
            enabled = !busy,
            onClick = onShow,
        )
    }
}
