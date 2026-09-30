package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.toggleable
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Goals
import com.jarvis.client.net.Projects
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
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
    // The numbers a draft's step could follow (benchmarks with a target),
    // read only while a draft is on screen and the lists are shown.
    var options by remember { mutableStateOf<List<Goals.MeasureOption>>(emptyList()) }
    // The step just ticked, so an Undo can untick it (by its id).
    var undo by remember { mutableStateOf<TickUndo?>(null) }
    val hasDraft = view?.goals?.any { it.status == "draft" } == true

    LaunchedEffect(hasDraft, privateHidden, reads) {
        if (!hasDraft || privateHidden) return@LaunchedEffect
        val listed = (JarvisRuntime.projectsRead(Projects.PATH) as? ApiResult.Ok)?.value
            ?.takeIf { it.code in 200..299 }?.body?.let { Projects.parseList(it) }
            ?: return@LaunchedEffect
        val full = listed.projects.take(20).mapNotNull { p ->
            val path = Projects.projectPath(p.id) ?: return@mapNotNull null
            (JarvisRuntime.projectsRead(path) as? ApiResult.Ok)?.value
                ?.takeIf { it.code in 200..299 }?.let { Projects.projectOf(it) }
        }
        options = Goals.measureOptions(full)
    }

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
                            maxNeeds = shown.limits?.needs ?: Goals.MAX_NEEDS,
                            options = options,
                            undo = undo?.takeIf { it.goalId == goal.id },
                            onSay = { said = it },
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
                            onStep = { step, index, done ->
                                busyId = goal.id
                                said = null
                                undo = null
                                scope.launch {
                                    var ok = false
                                    try {
                                        // By the step's id when the PC gave one; else by position.
                                        val r = JarvisRuntime.setGoalStep(goal.id, step.id, index, done)
                                        ok = r.first
                                        val name = if (privateHidden) "" else step.step
                                        if (!ok) {
                                            // The PC's own sentence, as sent (a locked step's 409 too).
                                            said = r.third
                                        } else if (done) {
                                            // A tick can be taken back at once; the Undo untick is the same route.
                                            undo = TickUndo(goal.id, step.id, index, name)
                                        } else {
                                            said = if (name.isEmpty()) r.third else Goals.w("unticked", step = name)
                                        }
                                    } finally {
                                        busyId = null
                                        // A refused tick (a stale screen) reads the list again to catch up.
                                        if (!ok) reads += 1
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

/** The step just ticked: which goal, its id (its position if the PC gave none) and its words ("" while hidden). */
private data class TickUndo(val goalId: String, val stepId: String, val index: Int, val name: String)

/** One goal: its own words, its plan, and whichever of its own controls apply to its status. */
@Composable
private fun GoalRow(
    goal: Goals.Goal,
    plan: List<Goals.Step>,
    maxSteps: Int,
    maxNeeds: Int,
    options: List<Goals.MeasureOption>,
    undo: TickUndo?,
    onSay: (String) -> Unit,
    hidden: Boolean,
    enabled: Boolean,
    waiting: Schedule.Job?,
    onPlanChange: (List<Goals.Step>) -> Unit,
    onAccept: () -> Unit,
    onStep: (Goals.Step, Int, Boolean) -> Unit,
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
                        onClick = {
                            val name = s.step.trim()
                            val (next, touched) = Goals.removeStep(plan, i)
                            onPlanChange(next)
                            // The PC does not clean the others' "Do these first": done here, and said.
                            if (touched) onSay(Goals.w("needs_cleaned", step = name.ifEmpty { "the step" }))
                        },
                    )
                }
                StepLinks(plan, i, maxNeeds, options, enabled, onPlanChange)
            } else {
                // The whole row is one checkbox with its words (the box itself
                // takes no taps), so TalkBack reads the step and its state.
                val shownStep = if (hidden) Goals.HIDDEN_TEXT else s.step
                val stepEnabled = enabled && goal.status == "active" && Goals.canTick(s)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .toggleable(
                            value = s.done,
                            enabled = stepEnabled,
                            role = Role.Checkbox,
                            onValueChange = { onStep(s, i, it) },
                        ),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = s.done,
                        enabled = stepEnabled,
                        onCheckedChange = null,
                    )
                    // One spoken line per row: "<step>, locked, after: <steps>".
                    Column(Modifier.weight(1f).clearAndSetSemantics { contentDescription = Goals.spoken(s, shownStep) }) {
                        Text(
                            shownStep,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (s.locked) chrome.textMid else chrome.textHi,
                        )
                        if (!hidden && s.by.isNotEmpty()) {
                            Text(s.by, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        // Greyed is never the only signal: the word "locked" and the PC's own reason.
                        // "number reached" is the desktop's tag too: a met number, not a tick.
                        val reachedTag = s.reached && s.state != "done"
                        if (s.locked || reachedTag || s.lockWords.isNotEmpty()) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                if (s.locked) Pill(Goals.w("locked"), color = chrome.textMid)
                                if (reachedTag) Pill(Goals.w("reached_tag"), color = chrome.textMid)
                                if (s.lockWords.isNotEmpty()) {
                                    Text(
                                        s.lockWords, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                                        modifier = Modifier.weight(1f),
                                    )
                                }
                            }
                        }
                        // Reached is not a tick: the owner still ticks it.
                        if (s.reached && s.reachedWords.isNotEmpty()) {
                            Text(s.reachedWords, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        }
                        if (s.measure != null) {
                            if (s.measureGone) {
                                Text(Goals.w("measure_gone"), style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                            } else if (s.measureName.isNotEmpty()) {
                                Text(
                                    "${Goals.FOLLOWS_LABEL}: ${s.measureName}",
                                    style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                                )
                            }
                        }
                    }
                }
            }
        }
        if (editable) {
            Gap(6)
            if (plan.size < maxSteps) {
                Quiet(Goals.ADD_STEP, enabled = enabled, onClick = { onPlanChange(plan + Goals.newStep(plan)) })
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
            if (undo != null) {
                // The tick just made, said plainly, with one tap to take it back (no card).
                Text(
                    if (undo.name.isEmpty()) Goals.TICKED_GENERIC else Goals.w("ticked", step = undo.name),
                    style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (undo != null) {
                    Quiet(Goals.UNDO, enabled = enabled, onClick = {
                        // The step that was ticked, found by its id (its position if the PC gave none).
                        val i = plan.indexOfFirst { undo.stepId.isNotEmpty() && it.id == undo.stepId }
                            .takeIf { it >= 0 } ?: undo.index
                        plan.getOrNull(i)?.let { onStep(it, i, false) }
                    })
                }
                Quiet(Goals.STOP, color = chrome.badInk, enabled = enabled, onClick = onStop)
            }
        }
    }
}

/**
 * A draft step's two pickers, before Accept: "Do these first" (the other
 * steps it waits on, at most [maxNeeds]) and "Follows a number" (a
 * benchmark with a target). Shown under a tap so seven steps stay short.
 */
@Composable
private fun StepLinks(
    plan: List<Goals.Step>,
    i: Int,
    maxNeeds: Int,
    options: List<Goals.MeasureOption>,
    enabled: Boolean,
    onPlanChange: (List<Goals.Step>) -> Unit,
) {
    val chrome = LocalChrome.current
    val s = plan[i]
    var open by remember(s.id, i) { mutableStateOf(false) }
    val others = plan.withIndex().filter { it.index != i && it.value.id.isNotEmpty() }
    val summary = buildList {
        if (s.needs.isNotEmpty()) add("${Goals.DO_FIRST}: ${s.needs.size}")
        if (s.measure != null) add(Goals.FOLLOWS_LABEL)
    }.joinToString(" · ")
    Quiet(
        if (open) "Hide links" else if (summary.isEmpty()) "${Goals.DO_FIRST} / ${Goals.FOLLOWS}" else summary,
        color = chrome.textMid,
        onClick = { open = !open },
    )
    if (!open) return
    Text(Goals.DO_FIRST.uppercase(), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (others.isEmpty()) {
        Text(Goals.w("needs_none"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    } else {
        Text(Goals.w("needs_under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        if (s.needs.size >= maxNeeds) {
            Text(Goals.w("needs_limit", max = maxNeeds), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        others.forEach { (j, o) ->
            val on = o.id in s.needs
            Quiet(
                if (on) "✓ ${Goals.label(plan, j)}" else Goals.label(plan, j),
                color = if (on) null else chrome.textMid,
                // The picker stops at the limit; the PC would refuse a fourth.
                enabled = enabled && (on || s.needs.size < maxNeeds),
                onClick = { onPlanChange(Goals.toggleNeed(plan, i, o.id, maxNeeds)) },
            )
        }
    }
    Gap(4)
    Text(Goals.FOLLOWS.uppercase(), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    if (options.isEmpty() && s.measure == null) {
        Text(Goals.w("follows_empty"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    } else {
        Text(Goals.w("follows_under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Quiet(
            if (s.measure == null) "✓ ${Goals.w("follows_none")}" else Goals.w("follows_none"),
            color = if (s.measure == null) null else chrome.textMid,
            enabled = enabled,
            onClick = { onPlanChange(Goals.setMeasure(plan, i, null)) },
        )
        options.forEach { o ->
            val on = s.measure == o.measure
            Quiet(
                if (on) "✓ ${o.label}" else o.label,
                color = if (on) null else chrome.textMid,
                enabled = enabled,
                onClick = { onPlanChange(Goals.setMeasure(plan, i, o.measure)) },
            )
        }
        if (s.measure != null && options.none { it.measure == s.measure } && s.measureName.isNotEmpty()) {
            Text("${Goals.FOLLOWS_LABEL}: ${s.measureName}", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}
