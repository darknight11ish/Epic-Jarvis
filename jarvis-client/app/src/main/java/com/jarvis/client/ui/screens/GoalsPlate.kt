package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Goals
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Goals" on Brain ([Goals], the owner's "build it now", 2026-09-27;
 * docs/JARVIS-API.md section 59) - beside "Coming up" ([ComingUpSection]),
 * matching the desktop's own Brain -> Work.
 *
 * A new goal needs only the owner's own words ([Goals.createGoal] via
 * [JarvisRuntime.createGoal]) - no card, a draft is content, not action.
 * Its plan (a handful of steps, each with an optional rough date) is then
 * edited right here, in the draft's own card, before Accept - the only
 * point a plan can change; once active, it is fixed but for ticking a step
 * done. Accepting ([JarvisRuntime.acceptGoal]) starts a weekly, model-free
 * check-in through the PC's ONE scheduler - the SAME approval card
 * mechanism a repeating reminder already raises - approving nothing that
 * acts, and its "waiting" banner mirrors [ComingUpPlate]'s own
 * ([Schedule.WAITING]). Ticking a step ([JarvisRuntime.setGoalStep]) and
 * Stop tracking ([JarvisRuntime.stopGoal]) need no card and are immediate,
 * ONE goal per tap, with no confirm dialog before Stop tracking - the
 * backend's own design requires stopping to be one tap.
 *
 * NOTHING HERE EVER ACTS. A step that needs Jarvis to actually do
 * something (search installers, draft an email) is asked for in ordinary
 * chat, which already asks first for anything that acts - this screen adds
 * no button that could.
 *
 * Read from the PC when Brain shows it, on Refresh, and after every change
 * made from this phone ([JarvisRuntime.goalsTick]) - there is no push event
 * for a goal changing (Forget has none either), so the other app's own
 * edit shows on the next read. "Hide memory lists and chat history" blanks
 * every goal's and step's own words, the same way Coming up does, but
 * leaves ticking a step, Accept and Stop tracking working blind - none of
 * those needs the words on screen to be a safe action, unlike typing a new
 * one over words you cannot see, so the plan editor itself is not offered
 * while hidden.
 */
@Composable
internal fun GoalsSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.goalsTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Goals.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busyId by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var newText by remember { mutableStateOf("") }
    var starting by remember { mutableStateOf(false) }
    // A draft's plan as the owner edits it, by goal id - seeded from the
    // goal's own plan the first time it is shown. There is no "save the
    // edit" route of its own: accept() is the only place an edited plan is
    // ever sent, so this is kept here, in memory, until then.
    var edits by remember { mutableStateOf(mapOf<String, List<Goals.Step>>()) }
    // The check-in job [JarvisRuntime.acceptGoal] just raised, by goal id,
    // for as long as it says "waiting" - see [Goals]'s own doc comment for
    // why this is the one place that state is kept once read.
    var waitingCheckins by remember { mutableStateOf(mapOf<String, Schedule.Job>()) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.goals()) {
            is ApiResult.Ok -> {
                val v = Goals.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Goals.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    // Re-checks each still-waiting check-in whenever the approval queue
    // changes (a card answered anywhere, on either app) - the only way
    // this screen can tell it is no longer waiting.
    val queue by JarvisRuntime.pending.collectAsState()
    val queueKey = queue.map { it.id }
    LaunchedEffect(queueKey) {
        if (waitingCheckins.isEmpty()) return@LaunchedEffect
        val next = mutableMapOf<String, Schedule.Job>()
        waitingCheckins.forEach { (goalId, job) ->
            val fresh = JarvisRuntime.scheduleJob(job.id)
            if (fresh != null && fresh.state == "waiting") next[goalId] = fresh
        }
        waitingCheckins = next
    }

    fun startGoal() {
        if (!canAct || starting || newText.isBlank()) return
        starting = true
        said = null
        scope.launch {
            try {
                val (ok, _, sentence) = JarvisRuntime.createGoal(newText)
                said = sentence
                if (ok) newText = ""
            } finally {
                starting = false
                reads += 1
            }
        }
    }

    Section(Goals.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Goals.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = view?.let { if (privateHidden) Goals.hide(it) else it }
            val err = readError
            when {
                missing -> Text(Goals.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read Goals: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (err != null) {
                        Text(
                            "Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    }
                    if (privateHidden) {
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
                    val ordered = Goals.ordered(view)
                    if (ordered.isEmpty()) {
                        Gap(4)
                        Text(Goals.EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    ordered.forEach { goal ->
                        Gap(10)
                        GoalRow(
                            goal = goal,
                            plan = edits[goal.id] ?: goal.plan,
                            maxSteps = shown.limits?.steps ?: Goals.MAX_STEPS,
                            hidden = privateHidden,
                            enabled = canAct && busyId == null,
                            waiting = waitingCheckins[goal.id],
                            onPlanChange = { p -> edits = edits + (goal.id to p) },
                            onAccept = {
                                val plan = edits[goal.id] ?: goal.plan
                                busyId = goal.id
                                said = null
                                scope.launch {
                                    try {
                                        val (ok, accepted, sentence) = JarvisRuntime.acceptGoal(goal.id, plan)
                                        said = sentence
                                        if (ok && accepted != null) {
                                            edits = edits - goal.id
                                            val checkin = accepted.checkin
                                            waitingCheckins = if (checkin != null && checkin.state == "waiting") {
                                                waitingCheckins + (goal.id to checkin)
                                            } else {
                                                waitingCheckins - goal.id
                                            }
                                        }
                                    } finally {
                                        busyId = null
                                    }
                                }
                            },
                            onStep = { index, done ->
                                busyId = goal.id
                                said = null
                                scope.launch {
                                    try {
                                        said = JarvisRuntime.setGoalStep(goal.id, index, done).third
                                    } finally {
                                        busyId = null
                                    }
                                }
                            },
                            onStop = {
                                busyId = goal.id
                                said = null
                                scope.launch {
                                    try {
                                        said = JarvisRuntime.stopGoal(goal.id).third
                                    } finally {
                                        busyId = null
                                    }
                                }
                            },
                        )
                    }
                    Gap(14)
                    val openCount = shown.goals.count { it.status == "draft" || it.status == "active" }
                    val goalsMax = shown.limits?.goals ?: Goals.MAX_GOALS
                    val atGoalLimit = openCount >= goalsMax
                    if (!privateHidden) {
                        TextInput(
                            value = newText,
                            onValueChange = { newText = it.take(shown.limits?.text ?: Goals.MAX_TEXT) },
                            placeholder = Goals.NEW_HINT,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { startGoal() }),
                        )
                        if (atGoalLimit) {
                            Text(
                                "There are already $goalsMax goals - stop tracking one before adding another.",
                                style = MaterialTheme.typography.labelSmall, color = chrome.warnInk,
                            )
                        }
                        Quiet(
                            if (starting) Goals.STARTING else Goals.START,
                            enabled = canAct && !starting && newText.isNotBlank() && !atGoalLimit,
                            onClick = { startGoal() },
                        )
                    }
                }
            }
            said?.let {
                Text(
                    it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            if (!missing && shown != null && !canAct) {
                Text(
                    "Not connected to the desktop, so changes wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One goal: its own words, its plan, and whichever of its own controls apply to its status. */
@Composable
private fun GoalRow(
    goal: Goals.Goal,
    plan: List<Goals.Step>,
    maxSteps: Int,
    hidden: Boolean,
    enabled: Boolean,
    waiting: Schedule.Job?,
    onPlanChange: (List<Goals.Step>) -> Unit,
    onAccept: () -> Unit,
    onStep: (Int, Boolean) -> Unit,
    onStop: () -> Unit,
) {
    val chrome = LocalChrome.current
    val editable = !hidden && goal.status == "draft"
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (hidden) Goals.HIDDEN_TEXT else goal.text,
                style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Goals.statusTag(goal.status).takeIf { it.isNotEmpty() }?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
        if (goal.status == "draft" && hidden) {
            Text(
                "Show your lists to review and edit this draft.",
                style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
            )
            return@Column
        }
        if (waiting != null) {
            Text(Goals.WAITING, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            Text(Goals.ALSO_IN_COMING_UP, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        val allDone = goal.status == "active" && plan.isNotEmpty() && plan.all { it.done }
        if (allDone) {
            Text(Goals.ALL_STEPS_DONE, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        plan.forEachIndexed { i, s ->
            Gap(4)
            if (editable) {
                TextInput(
                    value = s.step,
                    onValueChange = { v ->
                        onPlanChange(
                            plan.mapIndexed { idx, it -> if (idx == i) it.copy(step = v.take(Goals.MAX_TEXT)) else it },
                        )
                    },
                    placeholder = Goals.STEP_HINT,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextInput(
                        value = s.by,
                        onValueChange = { v ->
                            onPlanChange(plan.mapIndexed { idx, it -> if (idx == i) it.copy(by = v.take(Goals.MAX_BY)) else it })
                        },
                        placeholder = Goals.BY_HINT,
                        modifier = Modifier.weight(1f),
                    )
                    Quiet(
                        Goals.REMOVE_STEP,
                        color = chrome.badInk,
                        enabled = enabled && plan.size > 1,
                        onClick = { onPlanChange(plan.filterIndexed { idx, _ -> idx != i }) },
                    )
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = s.done,
                        enabled = enabled && goal.status == "active",
                        onCheckedChange = { onStep(i, it) },
                    )
                    Column(Modifier.weight(1f)) {
                        Text(
                            if (hidden) Goals.HIDDEN_TEXT else s.step,
                            style = MaterialTheme.typography.bodySmall, color = chrome.textHi,
                        )
                        if (!hidden && s.by.isNotEmpty()) {
                            Text(s.by, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                    }
                }
            }
        }
        if (editable) {
            Gap(6)
            if (plan.size < maxSteps) {
                Quiet(Goals.ADD_STEP, enabled = enabled, onClick = { onPlanChange(plan + Goals.Step("", "", false)) })
            } else {
                Text(Goals.TOO_MANY_STEPS, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
            Gap(6)
            Text(Goals.ACCEPT_DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Quiet(
                Goals.ACCEPT,
                enabled = enabled && Goals.validPlan(plan, maxSteps),
                onClick = onAccept,
            )
        } else if (goal.status == "active") {
            Gap(6)
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Quiet(Goals.STOP, color = chrome.badInk, enabled = enabled, onClick = onStop)
            }
        }
    }
}
