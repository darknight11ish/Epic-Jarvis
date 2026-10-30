package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Calendar
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * The Jarvis Calendar screen (the owner's ask of 2026-10-29; design brief
 * `.dsh-scratch/JARVIS-CALENDAR-DESIGN-2026-10-29/REPORT.md` Part 5.6; API
 * section 163).
 *
 * A MONTH, A DAY, AND ONE EVENT AT A TIME. The top is a real 7-column month
 * grid - today ringed in the accent, a dot on every day that has an event, the
 * selected day filled - with the month's name and Previous / Today / Next
 * beside it. Under the grid sits the selected day's list: the all-day events
 * first, then the timed ones from earliest to latest. One event can be added,
 * changed or deleted at a time; there is no "delete all" and no bulk anything,
 * the same rule `/api/schedule/act` has and for the same reason.
 *
 * THE WHOLE SCREEN IS ONE `LazyVerticalGrid`. A grid nested inside a scrolling
 * Column cannot be measured - Compose refuses it, because a vertical scroller
 * inside a vertical scroller has no finite height - so the heading, the day
 * list and the form are full-width items spanning all seven columns, and the
 * 42 day cells are the only items that use a column. The add/edit sheet is a
 * real `ModalBottomSheet`, drawn outside the grid so opening it never disturbs
 * the scroll position.
 *
 * NO CARD, AND HELD ON A STALE LINK. Adding an event writes one row on the
 * owner's own PC and changes nothing outside it, so it raises no approval card
 * - the reasoning the cardless list already gives for "one job on the
 * schedule", and decision D1 of the brief. Rule 4 is unchanged: every write is
 * held while the link is down or catching up, exactly as `scheduleAct` is
 * ([JarvisRuntime.calendarAdd]), and the screen says so instead of offering a
 * button that cannot work.
 *
 * A TITLE IS THE OWNER'S OWN WORDS, so while App lock or "Hide memory lists
 * and chat history" is on every title reads "(hidden)" - but the times stay,
 * because the shape of a day is not the private part ("the schedule's words go
 * and the times stay", the desktop's own redaction rule).
 *
 * THE "PC" WARNING IS ONLY WHERE IT IS TRUE. When the feature is off the
 * screen says so and offers the switch. A PC without the route at all says
 * that instead ([Calendar.MISSING]) - never "you have no events".
 */
@Composable
internal fun CalendarScreen(
    /** The link is live and not stale: every write is held until it is (rule 4). */
    canAct: Boolean,
    /** App lock or "Hide memory lists and chat history": titles become "(hidden)". */
    privateHidden: Boolean,
    onBack: () -> Unit,
    /** Where the off state's button goes. Null when the screen cannot offer it. */
    onOpenSettings: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    val scope = rememberCoroutineScope()

    val today = remember { Calendar.todayNow() }
    val tick by JarvisRuntime.calendarTick.collectAsState()

    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Calendar.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    // The month on show, and the day under it. Saved by value, so a rotation
    // comes back on the month and day the owner was looking at.
    var year by rememberSaveable { mutableIntStateOf(today.year) }
    var month by rememberSaveable { mutableIntStateOf(today.monthValue) }
    var selectedIso by rememberSaveable { mutableStateOf(today.toString()) }
    val shown = Calendar.Month(year, month)
    val selected = runCatching { LocalDate.parse(selectedIso) }.getOrDefault(today)
    // The sheet: a new event on a day, or one being changed.
    var editing by remember { mutableStateOf<Calendar.Event?>(null) }
    var addingOn by remember { mutableStateOf<LocalDate?>(null) }
    var confirmDelete by remember { mutableStateOf<Calendar.Event?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.calendar(Calendar.SCREEN_DAYS)) {
            is ApiResult.Ok -> {
                val v = Calendar.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Calendar.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    /** One write, with the busy flag and the PC's own sentence - Coming up's own shape. */
    fun write(block: suspend () -> Pair<Boolean, String>) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                val (_, sentence) = block()
                said = sentence
            } finally {
                busy = false
            }
        }
    }

    Column(Modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(Calendar.TITLE, onBack, trailing = { Quiet("Refresh", onClick = { reads += 1 }) })

        LazyVerticalGrid(
            columns = GridCells.Fixed(7),
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            contentPadding = PaddingValues(top = 8.dp, bottom = 40.dp),
        ) {
            // ---------------------------------------------------- heading ----
            item(span = { GridItemSpan(maxLineSpan) }, key = "calendar-head") {
                Column(Modifier.fillMaxWidth()) {
                    Text(
                        Calendar.UNDER,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Gap(10)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            shown.words,
                            style = MaterialTheme.typography.titleMedium,
                            color = chrome.textHi,
                            modifier = Modifier.weight(1f),
                        )
                        Quiet("‹", onClick = {
                            val p = shown.previous()
                            year = p.year
                            month = p.month
                        })
                        Quiet(Calendar.TODAY, onClick = {
                            year = today.year
                            month = today.monthValue
                            selectedIso = today.toString()
                        })
                        Quiet("›", onClick = {
                            val n = shown.next()
                            year = n.year
                            month = n.month
                        })
                    }
                    Gap(6)
                    // The seven weekday letters, in the grid's own order.
                    Row(Modifier.fillMaxWidth()) {
                        Calendar.weekdayLetters().forEach { letter ->
                            Text(
                                letter,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                    val err = readError
                    val v = view
                    when {
                        missing -> {
                            Gap(8)
                            Text(
                                Calendar.MISSING,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        // The PC's own switch is off: the screen still opens and
                        // says so, with the one button that fixes it. Nothing was
                        // deleted, and the line says that too.
                        v != null && !v.on -> {
                            Gap(8)
                            Plate {
                                Text(
                                    Calendar.OFF,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = chrome.textHi,
                                )
                                Text(
                                    Calendar.OFF_DETAIL,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textLo,
                                )
                                Gap(6)
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Quiet(
                                        if (busy) "Turning on…" else Calendar.TURN_ON,
                                        enabled = canAct && !busy,
                                        onClick = { write { JarvisRuntime.calendarSettings(true) } },
                                    )
                                    if (onOpenSettings != null) {
                                        Quiet("Settings", onClick = onOpenSettings)
                                    }
                                }
                            }
                        }
                        v == null && err != null -> {
                            Gap(8)
                            Text(
                                "Couldn't read the calendar: $err",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                        }
                        v == null -> {
                            Gap(8)
                            Text(
                                "Reading…",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textLo,
                            )
                        }
                        err != null -> {
                            Gap(4)
                            Text(
                                "Couldn't read it again: $err",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                            )
                        }
                    }
                    Gap(8)
                }
            }

            // ------------------------------------------------ month grid ----
            val lit = if (view != null && view?.on == true) Calendar.daysWithEvents(view!!) else emptySet()
            items(items = Calendar.cells(shown)) { cell ->
                when (cell) {
                    // A padding square: as wide as a column and as tall as a day,
                    // so the weekdays stay under their letters.
                    is Calendar.Cell.Blank -> Box(Modifier.fillMaxWidth().heightIn(min = 48.dp))
                    is Calendar.Cell.Day -> {
                        val d = cell.date
                        val isToday = d == today
                        val isSelected = d == selected
                        val count = if (d in lit) Calendar.eventsOn(view!!, d).size else 0
                        var label = Calendar.dayA11y(d, count, today)
                        if (privateHidden && count > 0) label += ", hidden"
                        // A seventh of the grid's width, and the app's own 48dp
                        // touch minimum in the direction it can afford: the
                        // shared `pressable` minimum is not opted out of here,
                        // because a calendar day is a target the owner taps
                        // again and again and the grid already gives it 48dp of
                        // height.
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .clip(radii.controlShape)
                                .background(
                                    if (isSelected) accent.copy(alpha = 0.16f) else chrome.surface1,
                                )
                                .border(
                                    width = if (isToday) 2.dp else 1.dp,
                                    color = when {
                                        isToday -> accent
                                        isSelected -> accent.copy(alpha = 0.55f)
                                        else -> chrome.hairline
                                    },
                                    shape = radii.controlShape,
                                )
                                .semantics { contentDescription = label }
                                .pressable { selectedIso = d.toString() },
                            contentAlignment = Alignment.Center,
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    d.dayOfMonth.toString(),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (isSelected || isToday) accent else chrome.textHi,
                                )
                                Box(
                                    Modifier
                                        .size(4.dp)
                                        .clip(CircleShape)
                                        .background(
                                            when {
                                                count == 0 -> androidx.compose.ui.graphics.Color.Transparent
                                                isToday -> accent
                                                else -> chrome.textMid
                                            },
                                        ),
                                )
                            }
                        }
                    }
                }
            }

            // ------------------------------------------------ the day list ----
            item(span = { GridItemSpan(maxLineSpan) }, key = "calendar-day") {
                Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
                    val v = view
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            Calendar.dayWords(selected, today),
                            style = MaterialTheme.typography.titleSmall,
                            color = chrome.textHi,
                            modifier = Modifier.weight(1f),
                        )
                        if (v != null && v.on && !missing) {
                            Quiet(
                                Calendar.ADD,
                                enabled = canAct && !busy,
                                onClick = { addingOn = selected },
                            )
                        }
                    }
                    // Only a real, switched-on calendar draws a day list: the
                    // three other states were already said in words above.
                    if (v != null && v.on && v.available && !missing) {
                        val events = Calendar.eventsOn(v, selected)
                        if (events.isEmpty()) {
                            Gap(4)
                            Text(
                                Calendar.EMPTY_DAY,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        events.forEach { e ->
                            CalendarEventRow(
                                event = e,
                                hidden = privateHidden,
                                enabled = canAct && !busy,
                                onEdit = { editing = e },
                                onDelete = { confirmDelete = e },
                            )
                        }
                    } else if (v != null && !v.available) {
                        Gap(6)
                        Text(
                            "Your PC could not read the calendar just now.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                    said?.let {
                        Gap(6)
                        Text(
                            it,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }
                    if (!canAct && v != null && !missing) {
                        Gap(4)
                        Text(
                            "Not connected to the desktop, so changes wait until the link is back.",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                    }
                    Gap(8)
                }
            }
        }
    }

    // -------------------------------------------------------------- sheets ----
    val openFor = addingOn
    if (openFor != null) {
        CalendarEventSheet(
            initial = null,
            defaultDate = openFor,
            privateHidden = privateHidden,
            busy = busy,
            onDismiss = { addingOn = null },
            onSave = { fields ->
                write {
                    val (ok, sentence) = JarvisRuntime.calendarAdd(fields)
                    if (ok) addingOn = null
                    ok to sentence
                }
            },
        )
    }
    val edit = editing
    if (edit != null) {
        CalendarEventSheet(
            initial = edit,
            defaultDate = selected,
            privateHidden = privateHidden,
            busy = busy,
            onDismiss = { editing = null },
            onSave = { fields ->
                write {
                    val (ok, sentence) = JarvisRuntime.calendarUpdate(edit.id, fields)
                    if (ok) editing = null
                    ok to sentence
                }
            },
        )
    }
    confirmDelete?.let { victim ->
        AlertDialog(
            onDismissRequest = { confirmDelete = null },
            title = { Text("Delete this event?") },
            text = {
                Text(
                    if (privateHidden) {
                        "One event on your PC. This cannot be undone."
                    } else {
                        "\"${victim.title}\" on " +
                            Calendar.datedWords(runCatching { LocalDate.parse(victim.date) }.getOrDefault(today), today) +
                            ". One event on your PC. This cannot be undone."
                    },
                )
            },
            confirmButton = {
                Quiet(
                    if (busy) "Deleting…" else Calendar.REMOVE_YES,
                    color = chrome.badInk,
                    enabled = canAct && !busy,
                    onClick = {
                        confirmDelete = null
                        write { JarvisRuntime.calendarDelete(victim.id) }
                    },
                )
            },
            dismissButton = { Quiet(Calendar.REMOVE_NO) { confirmDelete = null } },
        )
    }
}

/**
 * One event on the selected day: its time, its title, its place and its repeat,
 * and its own Edit / Delete - ONE event per tap, held while [enabled] is false.
 *
 * The time is drawn first and stays while [hidden] is on: a reminder's times
 * stay too under "Hide memory lists and chat history", because the shape of a
 * day is not the private part - the words are.
 */
@Composable
private fun CalendarEventRow(
    event: Calendar.Event,
    hidden: Boolean,
    enabled: Boolean,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    Gap(10)
    Column(Modifier.fillMaxWidth()) {
        Text(
            Calendar.timeWords(event),
            style = MaterialTheme.typography.labelSmall,
            color = accent,
        )
        Text(
            if (hidden) Calendar.HIDDEN_TITLE else event.title,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
        )
        if (!hidden) {
            event.place.trim().takeIf { it.isNotEmpty() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            Calendar.recurrenceWords(event).takeIf { it.isNotEmpty() }?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Quiet(Calendar.EDIT, enabled = enabled, onClick = onEdit)
            Quiet(Calendar.DELETE, color = chrome.badInk, enabled = enabled, onClick = onDelete)
        }
    }
}

/**
 * What the sheet hands back. A plain holder, so the sheet can own no route and
 * a half-typed box can never leave the phone.
 *
 * Public rather than internal because [JarvisRuntime.calendarAdd] and
 * `calendarUpdate` take it, and those two are the runtime's public API (the
 * same reason `Schedule.Reply` and `Goals.Reply` are public).
 */
data class CalendarFields(
    val title: String,
    val date: String,
    val time: String?,
    val allDay: Boolean,
    val endDate: String?,
    val endTime: String?,
    val place: String,
    val notes: String,
    val remind: String,
    val recurrence: String,
)

/**
 * The add/edit sheet: every field the backend takes, in the order the owner
 * fills them, with "All day" and "Repeats" as the two things that change what
 * the other boxes mean.
 *
 * It sends nothing itself - [onSave] gets the raw fields and the screen turns
 * them into one body ([Calendar.addBody]) - so validation happens in one place,
 * and `Calendar.problem` is the one thing that decides whether a half-typed
 * time can become an event.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CalendarEventSheet(
    initial: Calendar.Event?,
    defaultDate: LocalDate,
    privateHidden: Boolean,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSave: (CalendarFields) -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val start = initial?.day ?: defaultDate
    var title by remember { mutableStateOf(if (privateHidden) "" else initial?.title ?: "") }
    var date by remember { mutableStateOf(start.toString()) }
    var time by remember { mutableStateOf(initial?.time ?: "09:00") }
    var allDay by remember { mutableStateOf(initial?.allDay ?: false) }
    var endDate by remember { mutableStateOf(initial?.endDate ?: "") }
    var endTime by remember { mutableStateOf(initial?.endTime ?: "") }
    var place by remember { mutableStateOf(if (privateHidden) "" else initial?.place ?: "") }
    var notes by remember { mutableStateOf(if (privateHidden) "" else initial?.notes ?: "") }
    var remind by remember { mutableStateOf(initial?.remindMinutes?.toString() ?: "") }
    var recurrence by remember { mutableStateOf(initial?.recurrence?.ifEmpty { "none" } ?: "none") }
    var wrong by remember { mutableStateOf<String?>(null) }

    fun save() {
        val problem = Calendar.problem(title, date, if (allDay) null else time, allDay, endDate, endTime)
        if (problem != null) {
            wrong = problem
            return
        }
        wrong = null
        onSave(
            CalendarFields(
                title = title,
                date = date,
                time = if (allDay) null else Calendar.tidyTime(time),
                allDay = allDay,
                endDate = endDate.trim().takeIf { it.isNotEmpty() },
                endTime = if (allDay) null else Calendar.tidyTime(endTime),
                place = place,
                notes = notes,
                remind = remind,
                recurrence = recurrence,
            ),
        )
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = chrome.surface1,
        contentColor = chrome.textHi,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp)
                .padding(bottom = 28.dp),
        ) {
            Text(
                if (initial == null) "New event" else "Change this event",
                style = MaterialTheme.typography.titleMedium,
                color = chrome.textHi,
            )
            Text(
                "Kept on your PC, beside your reminders. No card, and nothing leaves this PC.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(12)
            TextInput(
                value = title,
                onValueChange = { title = it.take(Calendar.MAX_TITLE) },
                label = Calendar.FIELD_TITLE,
                placeholder = "Dentist",
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            )
            Gap(10)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextInput(
                    value = date,
                    onValueChange = { date = it.take(10) },
                    label = Calendar.FIELD_DATE,
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Number,
                        imeAction = ImeAction.Next,
                    ),
                )
                if (!allDay) {
                    TextInput(
                        value = time,
                        onValueChange = { time = it.take(5) },
                        label = Calendar.FIELD_TIME,
                        modifier = Modifier.weight(1f),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Number,
                            imeAction = ImeAction.Next,
                        ),
                    )
                }
            }
            Gap(6)
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    Calendar.ALL_DAY,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                Toggle(checked = allDay, onCheckedChange = { allDay = it })
            }
            Gap(6)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextInput(
                    value = endDate,
                    onValueChange = { endDate = it.take(10) },
                    label = Calendar.FIELD_END_DATE,
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Number,
                        imeAction = ImeAction.Next,
                    ),
                )
                if (!allDay) {
                    TextInput(
                        value = endTime,
                        onValueChange = { endTime = it.take(5) },
                        label = Calendar.FIELD_END_TIME,
                        modifier = Modifier.weight(1f),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Number,
                            imeAction = ImeAction.Next,
                        ),
                    )
                }
            }
            Gap(10)
            TextInput(
                value = place,
                onValueChange = { place = it.take(Calendar.MAX_PLACE) },
                label = Calendar.FIELD_PLACE,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            )
            Gap(10)
            TextInput(
                value = notes,
                onValueChange = { notes = it.take(Calendar.MAX_NOTES) },
                label = Calendar.FIELD_NOTES,
                singleLine = false,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
            )
            Gap(10)
            TextInput(
                value = remind,
                onValueChange = { remind = it.filter { c -> c.isDigit() }.take(5) },
                label = Calendar.FIELD_REMIND,
                placeholder = "30",
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Number,
                    imeAction = ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(onDone = { save() }),
            )
            Gap(10)
            Text(
                Calendar.REPEATS,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            // Five choices as words, the current one marked. A list rather than
            // a dropdown: five is few enough to show, and a dropdown hides the
            // one the owner is on - the same argument the four-choice topic
            // picker uses.
            Calendar.REPEAT_CHOICES.forEach { (wire, words) ->
                val chosen = recurrence == wire
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 40.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        words,
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (chosen) accent else chrome.textMid,
                        modifier = Modifier.weight(1f).pressable { recurrence = wire },
                    )
                    if (chosen) {
                        Text(
                            "Chosen",
                            style = MaterialTheme.typography.labelSmall,
                            color = accent,
                        )
                    }
                }
            }
            wrong?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            }
            Gap(12)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet(
                    if (busy) "Saving…" else Calendar.SAVE,
                    enabled = !busy,
                    onClick = { save() },
                )
                Quiet("Cancel", onClick = onDismiss)
            }
        }
    }
}

/**
 * The Brain's own row for the calendar, right beside "Coming up": today's
 * date, one line of what is on, and the way in.
 *
 * It is a READ, so it is never held on a stale link - it says nothing has been
 * checked rather than drawing a guess. Titles are hidden while App lock or
 * "Hide memory lists" is on, exactly as the calendar screen's are.
 */
@Composable
internal fun CalendarSection(
    canAct: Boolean,
    privateHidden: Boolean,
    onOpen: () -> Unit,
) {
    val chrome = LocalChrome.current
    val tick by JarvisRuntime.calendarTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Calendar.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    val today = remember { Calendar.todayNow() }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.calendar(7)) {
            is ApiResult.Ok -> {
                val v = Calendar.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Calendar.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Calendar.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Calendar.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            when {
                missing -> Text(
                    Calendar.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                v == null -> Text(
                    readError?.let { "Couldn't read it: $it" } ?: "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (readError != null) chrome.warnInk else chrome.textLo,
                )
                !v.on -> Text(
                    Calendar.OFF,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                else -> {
                    Text(
                        Calendar.datedWords(today, today),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Text(
                        Calendar.todayLine(v, today, privateHidden),
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                    )
                }
            }
            Gap(6)
            Quiet(Calendar.OPEN, enabled = !missing, onClick = onOpen)
            if (!canAct) {
                Text(
                    Calendar.STALE,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}
