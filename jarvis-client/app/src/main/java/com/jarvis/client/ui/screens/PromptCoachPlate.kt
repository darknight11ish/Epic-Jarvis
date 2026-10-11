package com.jarvis.client.ui.screens

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
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
import com.jarvis.client.net.PromptCoach
import com.jarvis.client.net.ScreenPlateText
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Prompt coach" on Mind ([PromptCoach], docs/PROMPT-COACH-DESIGN.md,
 * docs/JARVIS-API.md section 119): the master switch for the "Coach this"
 * button, OFF by default, in the PC's own words - the label, the switch and
 * the detail paragraph under it ([PromptCoach.View.detail]).
 *
 * This slice is the switch and the four settings beside it (the owner's
 * answers, 2026-10-09: when it speaks up, how blunt it is, what it coaches on,
 * per-platform behaviour - all of them the PC's own words, drawn from
 * [PromptCoach.View.settings]). The button it turns on, the critique and
 * "Send mine" / "Send the suggestion" live in `PromptCoachBar.kt`: nothing on
 * this screen reads a prompt.
 *
 * Neither direction of the switch, and no direction of any of the four, raises
 * an approval card - the coach reads only words the chat is about to send to
 * the same local model, acts on nothing and opens no way out of the PC (the
 * owner's decision of 2026-10-08) - so they are held only by the link: greyed
 * while the desktop is not connected or the event stream is stale, under the
 * shared sentence that says so ([ScreenPlateText.WAITING_LINK]).
 *
 * @param canAct the link is up and fresh, the same gate every other write on
 *   this screen takes.
 */
@Composable
internal fun PromptCoachSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<PromptCoach.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.promptCoach()) {
            is ApiResult.Ok -> {
                val v = PromptCoach.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (PromptCoach.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(PromptCoach.HEADING, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            when {
                missing -> Text(
                    PromptCoach.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                v == null -> Text(
                    if (err != null) "Couldn't read the prompt coach: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    // The PC's own sentence when it could not read its setting
                    // file (a damaged prompt-coach.json): shown before the
                    // switch, because it explains why the switch reads "off".
                    if (v.why.isNotEmpty()) {
                        Text(v.why, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                        Gap(6)
                    }
                    SwitchRow(
                        title = v.label,
                        detail = v.detail,
                        checked = v.on,
                        // The link is the only thing that can hold this switch,
                        // and a change waits for itself.
                        enabled = canAct && !busy,
                        onChange = { want ->
                            if (!busy) {
                                busy = true
                                said = null
                                scope.launch {
                                    try {
                                        said = JarvisRuntime.setPromptCoach(want)
                                    } finally {
                                        busy = false
                                        // Read again, so the switch shows what
                                        // the PC really has - and its `why`.
                                        reads += 1
                                    }
                                }
                            }
                        },
                    )
                    // The four settings beside the switch (the owner's answers,
                    // 2026-10-09). EVERY word of every row - the setting's own
                    // name, each choice's name and its explanation - comes from
                    // the PC (`jarvis_prompt_coach.settings_rows()`); this
                    // screen holds no copy of any of them, so a new choice
                    // appears here by changing one Python tuple. A PC that
                    // answers without them (an older backend) leaves the list
                    // empty and nothing is drawn, exactly as before they
                    // existed.
                    for (group in v.settings) {
                        Gap(10)
                        Text(
                            group.name,
                            style = MaterialTheme.typography.labelLarge,
                            color = chrome.textMid,
                        )
                        for (choice in group.choices) {
                            Gap(2)
                            ChoiceRow(
                                name = choice.name,
                                detail = choice.detail,
                                picked = choice.value == group.value,
                                enabled = canAct && !busy,
                                onPick = {
                                    if (!busy && choice.value != group.value) {
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                said = JarvisRuntime.setPromptCoachChoice(
                                                    group.key,
                                                    choice.value,
                                                    v,
                                                )
                                            } finally {
                                                busy = false
                                                reads += 1
                                            }
                                        }
                                    }
                                },
                            )
                        }
                    }
                    val line = if (busy) "Asking your PC…" else said
                    line?.let {
                        Gap(4)
                        Text(
                            it,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                            modifier = Modifier.liveStatus(),
                        )
                    }
                    if (!canAct) {
                        Gap(4)
                        Text(
                            ScreenPlateText.WAITING_LINK,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                            modifier = Modifier.liveStatus(),
                        )
                    }
                }
            }
        }
    }
}

/**
 * One choice of one of the four settings: a radio, the choice's own name (the
 * PC's words, from `jarvis_prompt_coach.SETTINGS`), and the line explaining it.
 * Tapping anywhere on the row picks it, like every other choice on this screen.
 *
 * Nothing here decides what the choices ARE. This draws what it was handed, so
 * a new choice - or a new setting - appears on the phone by changing the
 * backend's own tuple.
 */
@Composable
private fun ChoiceRow(
    name: String,
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
                // No ripple, like every other control built on `pressable`.
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
                name,
                style = MaterialTheme.typography.bodyLarge,
                color = if (enabled) chrome.textHi else chrome.textLo,
            )
            if (detail.isNotBlank()) {
                Text(detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}
