package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Retirement
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Meter
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Retirement what-if" on the Brain ([Retirement]; the owner's decision of
 * 2026-09-30, docs/JARVIS-API.md section 103, docs/FINANCE-DESIGN.md part B
 * and its frozen "Retirement contract").
 *
 * A form drawn from the PC's `GET /api/retirement/defaults` (labels, units,
 * limits and help lines are the PC's), a "Work it out" button, and the answer
 * drawn exactly as the PC sent it. NOTHING is computed on the phone.
 *
 * THE NUMBERS ARE NEVER SAVED. The boxes, the answer and every note live in
 * this composable's memory only (plain `remember`, never `rememberSaveable`,
 * never a file, a preference, saved state or a log). They go when the owner
 * leaves the screen (the list item leaves the composition) and are emptied at
 * once when "Hide memory lists and chat history" turns on. There is no Copy,
 * no Share and no export; the answer is never read aloud.
 *
 * Under "Hide memory lists and chat history" only "Retirement what-if hidden"
 * is drawn (with the Show button every hidden section has); the form is not
 * offered. Screenshots are already blocked app-wide while that is on. The run
 * is held on a stale link (rule 4). No card: it is the owner's own numbers.
 */
@Composable
internal fun RetirementSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()

    if (Retirement.hiddenNow(hideLists = privateHidden, locked = false)) {
        // No fetch and nothing held: this branch composes no state, so the
        // typed boxes and any answer are dropped the moment the lists hide.
        Section(Retirement.TITLE) {
            Plate {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        Retirement.HIDDEN,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                        modifier = Modifier.weight(1f),
                    )
                    Quiet(
                        if (showPrivateBusy) "Checking…" else "Show",
                        enabled = !showPrivateBusy,
                        onClick = onShowPrivate,
                    )
                }
            }
        }
        return
    }

    var reads by remember { mutableIntStateOf(0) }
    var defaults by remember { mutableStateOf<Retirement.Defaults?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    // Plain remember, on purpose: never saved state, never a file.
    var values by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var started by remember { mutableStateOf(false) }
    var fieldNotes by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var note by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<Retirement.Result?>(null) }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.retirementDefaults()) {
            is ApiResult.Ok -> {
                val d = Retirement.parseDefaults(r.value)
                if (d == null) missing = true else {
                    defaults = d
                    missing = false
                    // The made-up figures start filled in; the required boxes start empty.
                    if (!started) {
                        values = Retirement.startingValues(d)
                        started = true
                    }
                }
                readError = null
            }
            is ApiResult.Failed -> if (Retirement.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(defaults?.title ?: Retirement.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val d = defaults
            val err = readError
            when {
                missing -> Text(Retirement.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                d == null -> Text(
                    if (err != null) "Couldn't read the what-if form: $err" else Retirement.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (d.detail.isNotEmpty()) {
                        Text(d.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Gap(4)
                    }
                    if (d.todaysMoney.isNotEmpty()) {
                        Text(d.todaysMoney, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                    Gap(8)
                    d.fields.forEach { f ->
                        FieldBox(
                            field = f,
                            value = values[f.key].orEmpty(),
                            note = fieldNotes[f.key],
                            enabled = !busy,
                            onChange = { text ->
                                values = values + (f.key to text)
                                // A note is about what WAS typed: it goes when the box changes.
                                if (fieldNotes.containsKey(f.key)) fieldNotes = fieldNotes - f.key
                            },
                        )
                        Gap(6)
                    }
                    if (d.placeholderNote.isNotEmpty()) {
                        Text(d.placeholderNote, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid)
                        Gap(8)
                    }

                    Primary(
                        text = if (busy) Retirement.WORKING else Retirement.RUN,
                        enabled = canAct && !busy,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            if (busy) return@Primary
                            val slips = Retirement.check(d, values)
                            if (slips.isNotEmpty()) {
                                fieldNotes = slips
                                note = Retirement.CHECK_BOXES
                                return@Primary
                            }
                            fieldNotes = emptyMap()
                            note = null
                            busy = true
                            scope.launch {
                                try {
                                    when (val out = JarvisRuntime.retirementRun(values, privateHidden, d.words)) {
                                        is Retirement.Outcome.Done -> result = out.result
                                        is Retirement.Outcome.FieldProblem -> {
                                            if (d.fields.any { it.key == out.key }) {
                                                fieldNotes = mapOf(out.key to out.message)
                                                note = Retirement.CHECK_BOXES
                                            } else {
                                                note = out.message
                                            }
                                        }
                                        is Retirement.Outcome.Problem -> note = out.message
                                        Retirement.Outcome.Missing -> {
                                            missing = true
                                            result = null
                                        }
                                    }
                                } finally {
                                    busy = false
                                }
                            }
                        },
                    )
                    // The link is stale (rule 4): the button is grey, and this says why.
                    if (!canAct) {
                        Gap(6)
                        Text(Retirement.STALE_LINE, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid, modifier = Modifier.liveStatus())
                    }
                    // Spoken when it appears or changes: "Working it out", or what went wrong.
                    if (busy) {
                        Gap(6)
                        Text(Retirement.WORKING, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid, modifier = Modifier.liveStatus())
                    }
                    note?.let {
                        Gap(6)
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
                            modifier = Modifier.liveStatus())
                    }
                    Quiet(
                        "Clear the numbers",
                        enabled = !busy,
                        onClick = {
                            values = Retirement.startingValues(d)
                            fieldNotes = emptyMap()
                            note = null
                            result = null
                        },
                    )

                    result?.let {
                        Gap(10)
                        ResultView(it)
                    }
                }
            }
        }
    }
}

/**
 * One box: the PC's label, unit and limits above it, its help line and any
 * note below. The keyboard is a number pad for ages and money; the percent
 * boxes take a plain keyboard so a minus sign and a "%" can be typed.
 */
@Composable
private fun FieldBox(
    field: Retirement.Field,
    value: String,
    note: String?,
    enabled: Boolean,
    onChange: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    val unit = Retirement.unitText(field)
    val limits = Retirement.limitsText(field)
    Column(
        Modifier
            .fillMaxWidth()
            // One thing for TalkBack: the label, the box to type in, its help and limits, "assumed".
            .semantics(mergeDescendants = true) {},
    ) {
        TextInput(
            value = value,
            onValueChange = { if (enabled) onChange(it) },
            label = if (unit.isEmpty()) field.label else "${field.label} ($unit)",
            placeholder = Retirement.hintFor(field),
            supportingText = listOf(field.help, "Limits: $limits.").filter { it.isNotEmpty() }.joinToString(" "),
            keyboardOptions = KeyboardOptions(
                keyboardType = if (field.kind == "percent") KeyboardType.Text else KeyboardType.Number,
            ),
        )
        if (field.placeholder) {
            Text(Retirement.ASSUMED, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    if (note != null) {
        // Announced when it appears: a field problem is news the owner has to hear.
        Text(note, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
            modifier = Modifier.liveStatus())
    }
}

/**
 * The answer, in the contract's order: the PC's sentences exactly as sent
 * (the first one is the headline), the fixed disclaimer straight after (always
 * shown, never collapsible), an optional plain bar of the shares, "What I
 * used" with the "assumed" mark, then the placeholder note and "all amounts in
 * today's money". No colour means good or bad; no Copy, no Share.
 */
@Composable
private fun ResultView(r: Retirement.Result) {
    val chrome = LocalChrome.current
    val spoken = Retirement.spoken(r)

    // The sentences and the disclaimer are one live region: TalkBack reads them
    // when they appear, and once more if a new run changes them.
    Column(
        Modifier.fillMaxWidth().clearAndSetSemantics {
            liveRegion = LiveRegionMode.Polite
            contentDescription = spoken
        },
    ) {
        r.summary.forEachIndexed { i, line ->
            if (i == 0) {
                Text(line, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            } else {
                Gap(4)
                Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
        Gap(8)
        Text(r.disclaimer, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
    }

    // A plain bar of the shares, only from the numbers the PC sent. TalkBack has
    // the same facts in the sentences above, so the bars are skipped there.
    val shareRows = Retirement.shareRows(r)
    if (shareRows.isNotEmpty()) {
        Gap(10)
        Column(Modifier.fillMaxWidth().clearAndSetSemantics {}, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            shareRows.forEach { (caption, share) ->
                Column {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(caption, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        Text(share.label, style = MaterialTheme.typography.labelSmall, color = chrome.textHi)
                    }
                    Meter(
                        fraction = share.per100 / 100f,
                        color = chrome.textMid,
                        track = chrome.hairline,
                        height = 6,
                    )
                }
            }
        }
    }

    val balances = Retirement.balanceRows(r)
    if (balances.isNotEmpty()) {
        Gap(10)
        Column(Modifier.fillMaxWidth().clearAndSetSemantics {}) {
            Retirement.balanceHeading(r)?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
            balances.forEach { (caption, text) ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(caption, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    Text(text, style = MaterialTheme.typography.labelSmall, color = chrome.textHi)
                }
            }
        }
    }

    if (r.used.isNotEmpty()) {
        Gap(12)
        Text(
            Retirement.USED_HEADING,
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textMid,
            modifier = Modifier.semantics { heading() },
        )
        Gap(4)
        r.used.forEach { u ->
            Row(
                Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = Retirement.usedReading(u) },
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    u.label,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    if (u.assumed) "${u.value}  ${Retirement.ASSUMED}" else u.value,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (u.assumed) chrome.textLo else chrome.textHi,
                )
            }
        }
    }

    if (r.placeholderNote.isNotEmpty()) {
        Gap(8)
        Text(r.placeholderNote, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
    }
    if (r.todaysMoney.isNotEmpty()) {
        Gap(4)
        Text(r.todaysMoney, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
    }
}
