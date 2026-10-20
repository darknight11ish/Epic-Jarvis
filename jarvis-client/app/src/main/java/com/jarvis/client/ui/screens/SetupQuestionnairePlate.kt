package com.jarvis.client.ui.screens

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SetupQuestionnaire
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "First-time setup" on Settings (docs/JARVIS-API.md section 147; the PC's
 * module is `backend/jarvis_setup.py`; [SetupQuestionnaire] holds every rule).
 *
 * READ-ONLY. The same fourteen questions, the same prefill from the last
 * accepted answers, and the PC's own read-only plan: "See what this would
 * change" posts `POST /api/setup/plan`, which writes nothing and raises no
 * card, and draws each change with its effect - Instant, Asks you on a card, or
 * Blocked - plus what would NOT change and why.
 *
 * THERE IS NO APPLY BUTTON HERE, deliberately. Applying works through the
 * changes one at a time and waits on each existing approval card; some changes
 * (a loosening rule, offering a reading tool) are the PC's alone. A phone
 * button would either fail halfway or sit for minutes behind a card it cannot
 * answer, so the last step stays on the PC and [SetupQuestionnaire.PLAIN_ONLY]
 * says so on the screen.
 *
 * The plan is a read, so a stale link does not hide it - but the plan is drawn
 * from what the PC answers NOW, and the screen never claims an old plan is
 * current: any change to an answer clears it until it is asked for again.
 */
@Composable
internal fun SetupQuestionnaireSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<SetupQuestionnaire.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var draft by remember { mutableStateOf<Map<String, List<String>>>(emptyMap()) }
    var plan by remember { mutableStateOf<SetupQuestionnaire.Plan?>(null) }
    var planning by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val result = JarvisRuntime.setupQuestionnaire()) {
            is ApiResult.Ok -> {
                val got = SetupQuestionnaire.parse(result.value)
                if (got == null) {
                    missing = true
                } else {
                    view = got
                    draft = SetupQuestionnaire.initialDraft(got)
                    plan = null
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (SetupQuestionnaire.missing(result.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(result.error)
            }
        }
    }

    Section(
        SetupQuestionnaire.HEADING,
        trailing = { Quiet(SetupQuestionnaire.REFRESH, onClick = { reads += 1 }) },
    ) {
        Plate {
            val got = view
            val err = readError
            when {
                missing -> Text(
                    SetupQuestionnaire.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                got == null -> Text(
                    if (err != null) "Couldn't read the setup questionnaire: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    Text(
                        SetupQuestionnaire.KICKER,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                    if (got.about.isNotBlank()) {
                        Gap(6)
                        Text(
                            got.about,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                    if (!got.available) {
                        Gap(6)
                        Text(
                            got.reason.ifBlank { SetupQuestionnaire.UPDATE_WORDS },
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk,
                        )
                    } else {
                        for (question in got.questions) {
                            QuestionBlock(
                                question = question,
                                draft = draft,
                                enabled = !planning,
                                onDraft = { next ->
                                    draft = next
                                    plan = null
                                    said = null
                                },
                            )
                        }
                        Gap(12)
                        Secondary(
                            text = SetupQuestionnaire.PLAN_ACTION,
                            enabled = !planning,
                            busy = planning,
                            onClick = {
                                val multiIds = got.questions
                                    .filter { it.multi }
                                    .map { it.id }
                                    .toSet()
                                val body = SetupQuestionnaire.planBody(draft, multiIds)
                                planning = true
                                said = SetupQuestionnaire.PLAN_READING
                                scope.launch {
                                    try {
                                        when (val answer = JarvisRuntime.setupPlan(body)) {
                                            is ApiResult.Ok -> {
                                                plan = SetupQuestionnaire.parsePlan(answer.value)
                                                said = null
                                            }
                                            is ApiResult.Failed -> {
                                                // A 404 is an older backend, said in
                                                // the PC's own words; never a plan.
                                                said = JarvisRuntime.noticeFor(answer.error)
                                            }
                                        }
                                    } finally {
                                        planning = false
                                    }
                                }
                            },
                        )
                        Gap(4)
                        Text(
                            SetupQuestionnaire.cardWaitWords(got.cardWaitS),
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                        plan?.let { drawn ->
                            PlanBlock(drawn)
                        }
                        LastRunBlock(got)
                    }
                    Gap(6)
                    Text(
                        SetupQuestionnaire.PLAIN_ONLY,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textLo,
                    )
                }
            }
            val line = when {
                planning -> SetupQuestionnaire.PLAN_READING
                said != null -> said
                else -> null
            }
            line?.let {
                Gap(4)
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }
}

/** One question: its title and help in the PC's words, then its choices. */
@Composable
private fun QuestionBlock(
    question: SetupQuestionnaire.Question,
    draft: Map<String, List<String>>,
    enabled: Boolean,
    onDraft: (Map<String, List<String>>) -> Unit,
) {
    val chrome = LocalChrome.current
    Gap(10)
    Text(
        question.title,
        style = MaterialTheme.typography.labelLarge,
        color = chrome.textHi,
    )
    if (question.help.isNotBlank()) {
        Text(
            question.help,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
    for (option in question.options) {
        val picked = SetupQuestionnaire.picked(draft, question, option.id)
        if (question.multi) {
            CheckRow(
                label = option.label,
                detail = option.detail,
                picked = picked,
                enabled = enabled,
                onPick = { onDraft(SetupQuestionnaire.toggle(draft, question, option.id)) },
            )
        } else {
            PickRow(
                label = option.label,
                detail = option.detail,
                picked = picked,
                enabled = enabled,
                onPick = { onDraft(SetupQuestionnaire.chooseOne(draft, question.id, option.id)) },
            )
        }
    }
    if (question.allNone) {
        val state = SetupQuestionnaire.allNoneState(draft, question.id)
        Row {
            Quiet(
                SetupQuestionnaire.ALL,
                color = if (state == "all") chrome.textHi else chrome.textLo,
                enabled = enabled,
                onClick = { onDraft(SetupQuestionnaire.chooseAll(draft, question.id)) },
            )
            Spacer(Modifier.width(12.dp))
            Quiet(
                SetupQuestionnaire.NONE,
                color = if (state == "none") chrome.textHi else chrome.textLo,
                enabled = enabled,
                onClick = { onDraft(SetupQuestionnaire.chooseNone(draft, question.id)) },
            )
        }
    }
}

/** One radio: a one-choice question's answer. */
@Composable
private fun PickRow(
    label: String,
    detail: String,
    picked: Boolean,
    enabled: Boolean,
    onPick: () -> Unit,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .selectable(
                selected = picked,
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                enabled = enabled,
                role = Role.RadioButton,
                onClick = onPick,
            )
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = picked, onClick = null, enabled = enabled)
        Gap(8)
        Column(Modifier.fillMaxWidth()) {
            Text(
                label,
                style = MaterialTheme.typography.bodyLarge,
                color = if (enabled) chrome.textHi else chrome.textLo,
            )
            if (detail.isNotBlank()) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}

/** One checkbox: a choose-any question's answer. */
@Composable
private fun CheckRow(
    label: String,
    detail: String,
    picked: Boolean,
    enabled: Boolean,
    onPick: () -> Unit,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .toggleable(
                value = picked,
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                enabled = enabled,
                role = Role.Checkbox,
                onValueChange = { onPick() },
            )
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = picked, onCheckedChange = null, enabled = enabled)
        Gap(8)
        Column(Modifier.fillMaxWidth()) {
            Text(
                label,
                style = MaterialTheme.typography.bodyLarge,
                color = if (enabled) chrome.textHi else chrome.textLo,
            )
            if (detail.isNotBlank()) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}

/** The PC's read-only plan: changes with their effect, then what would not change. */
@Composable
private fun PlanBlock(plan: SetupQuestionnaire.Plan) {
    val chrome = LocalChrome.current
    Gap(8)
    if (!plan.ok) {
        Text(plan.error, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        return
    }
    if (plan.changes.isEmpty()) {
        Text(
            SetupQuestionnaire.NOTHING_TO_APPLY,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        return
    }
    Text(
        SetupQuestionnaire.PLAN_HEADING,
        style = MaterialTheme.typography.labelLarge,
        color = chrome.textHi,
    )
    for (change in plan.changes) {
        val effect = SetupQuestionnaire.effectWords(change.effect)
        Text(
            "$effect: ${change.sentence.ifBlank { change.label }}",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
    if (plan.skipped.isNotEmpty()) {
        Gap(6)
        Text(
            SetupQuestionnaire.SKIPPED_HEADING,
            style = MaterialTheme.typography.labelLarge,
            color = chrome.textHi,
        )
        for (skip in plan.skipped) {
            Text(skip.reason, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
    plan.recommendation?.let { recommendation ->
        Gap(6)
        Text(
            SetupQuestionnaire.RECOMMENDATION_HEADING,
            style = MaterialTheme.typography.labelLarge,
            color = chrome.textHi,
        )
        Text(
            "${recommendation.title} - a recommendation only. ${recommendation.why}",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}

/** What the last accepted run did on the PC - including a card still waiting. */
@Composable
private fun LastRunBlock(view: SetupQuestionnaire.View) {
    val chrome = LocalChrome.current
    if (view.lastOutcomes.isEmpty()) return
    Gap(8)
    Text(
        SetupQuestionnaire.LAST_RUN_HEADING,
        style = MaterialTheme.typography.labelLarge,
        color = chrome.textHi,
    )
    for (row in view.lastOutcomes) {
        val words = row.message.ifBlank { SetupQuestionnaire.outcomeWords(row.state) }
        Text(
            "${row.label}: $words",
            style = MaterialTheme.typography.bodySmall,
            color = if (row.state == "asked-no-answer") chrome.warnInk else chrome.textMid,
        )
    }
}
