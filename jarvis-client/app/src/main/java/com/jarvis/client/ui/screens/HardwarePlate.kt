package com.jarvis.client.ui.screens

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
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Hardware
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Hardware" on the Mind screen (docs/HARDWARE-PROFILES.md 4.6, "Phone"):
 * the PC's cards (names and memory), what runs now and whether it was
 * measured, the three setups the PC worked out for its own cards with the
 * recommended one marked, "Use this", and then the steps of the chosen one.
 *
 * Not a model catalogue (CLAUDE.md): the PC sends three setups for ITS
 * cards, as words - there is no list of models, no search and no picker.
 * Choosing changes nothing by itself; each step is ONE tap that asks the PC
 * for that step, and the PC raises that step's own approval card, decided
 * on the PC or in this phone's approvals, one at a time. Only the next step
 * has a button. The PowerShell line is for the PC: shown here to read.
 *
 * Reads and acts through [JarvisRuntime] directly, like [BigModelSection],
 * so [BrainScreen] needs one line for it. Everything that asks is greyed
 * while [canAct] is false (rule 4), and the runtime refuses again on the way
 * out. The words are [Hardware]'s, which are the desktop's.
 */
@Composable
internal fun HardwareSection(canAct: Boolean, onOpenApprovals: ((cardId: String?) -> Unit)?) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val read by JarvisRuntime.hardware.collectAsState()
    // What is in flight ("" for a plain re-read), and what it came back with.
    var busy by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    // Steps asked for from this screen, and when (Hardware.shown).
    var asked by remember { mutableStateOf(mapOf<String, Long>()) }
    val now = rememberTickingNow(asked, 15_000L)

    val act: (String, suspend () -> String) -> Unit = { id, work ->
        if (busy == null) {
            busy = id
            notice = null
            scope.launch {
                try {
                    notice = work()
                } finally {
                    busy = null
                }
            }
        }
    }
    val recheck: () -> Unit = {
        if (busy == null) {
            busy = ""
            scope.launch {
                try {
                    JarvisRuntime.refreshHardware()
                } finally {
                    busy = null
                }
            }
        }
    }

    val status = (read as? Hardware.Read.Loaded)?.status
    // While a step's card waits, or a measurement runs, read again gently:
    // neither has an event of its own.
    val waiting = status != null && (
        status.measureState == "running" ||
            status.applying?.steps?.any { Hardware.shown(it, asked[it.id], now).state == "waiting" } == true
        )
    LaunchedEffect(waiting) {
        while (waiting) {
            delay(5_000L)
            JarvisRuntime.refreshHardware()
        }
    }

    Section("Hardware", trailing = { Quiet("Refresh", enabled = busy == null, onClick = recheck) }) {
        if (status == null) {
            Plate {
                Text(
                    Hardware.readLine(read).orEmpty(),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (read is Hardware.Read.NotAsked) chrome.textMid else chrome.warnInk,
                )
                notice?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
            }
        } else {
            Plate {
                // 1. The cards: names and memory only.
                Kicker("Your cards", Modifier.semantics { heading() })
                Gap(4)
                Text(status.found, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                for (card in status.cards) {
                    Gap(2)
                    Text(Hardware.cardLine(card), style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }

                // 2. What runs now.
                Gap(12)
                Kicker("Now running", Modifier.semantics { heading() })
                Gap(4)
                Text(
                    "${status.nowLabel}. ${status.nowWords}".trim(),
                    style = MaterialTheme.typography.bodySmall,
                    color = if ((status.nowOnCardPercent ?: 100) < 100) chrome.warnInk else chrome.textMid,
                )

                // 3. The three setups.
                Gap(12)
                Kicker("Three choices", Modifier.semantics { heading() })
                status.chosenStale?.let {
                    Gap(4)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
                for (p in status.presets) {
                    Gap(6)
                    Rule()
                    Gap(6)
                    val title = buildString {
                        append(p.name)
                        if (p.recommended) append(" ").append(Hardware.RECOMMENDED)
                        if (status.chosen == p.id) append(" - ").append(Hardware.CHOSEN)
                    }
                    Text(title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                    Text(p.summary, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    if (p.recommended) {
                        p.recommendedWhy?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }
                    Gap(4)
                    for (line in Hardware.presetLines(p)) {
                        Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Text(Hardware.measuredLine(p), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    for (why in p.bestEffortWhy) {
                        Text(
                            Hardware.bestEffortLine(why),
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk,
                        )
                    }
                    val off = p.off + p.notes
                    if (off.isNotEmpty()) {
                        Gap(4)
                        Text(Hardware.OFF_TITLE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        for (o in off) {
                            Text("- $o", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }
                    if (Hardware.canChoose(status, p)) {
                        Gap(6)
                        Secondary(
                            text = if (busy == "use:${p.id}") "Asking…" else Hardware.USE_THIS,
                            enabled = canAct && busy == null,
                            modifier = Modifier.fillMaxWidth(),
                            onClick = { act("use:${p.id}") { JarvisRuntime.chooseHardware(p.id) } },
                        )
                    }
                }

                // 4. The steps of the chosen setup - one at a time.
                val applying = status.applying
                if (applying != null) {
                    Gap(12)
                    Rule()
                    Gap(6)
                    Kicker("Steps for \"${applying.name}\"", Modifier.semantics { heading() })
                    applying.steps.forEachIndexed { i, raw ->
                        val step = Hardware.shown(raw, asked[raw.id], now)
                        Gap(6)
                        Text(
                            "${i + 1}. ${step.title}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (step.state == "later") chrome.textMid else chrome.textHi,
                        )
                        Text(
                            Hardware.stepWords(step),
                            style = MaterialTheme.typography.bodySmall,
                            color = when (step.state) {
                                "done" -> chrome.okInk
                                "waiting" -> chrome.warnInk
                                else -> chrome.textMid
                            },
                        )
                        if (step.state == "next" && step.route != null) {
                            Gap(4)
                            Secondary(
                                text = if (busy == "step:${step.id}") "Asking…" else Hardware.ASK,
                                enabled = canAct && busy == null,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = {
                                    act("step:${step.id}") {
                                        val said = JarvisRuntime.hardwareStep(step.id)
                                        if (said == Hardware.WAITING || said == Hardware.ASKED) {
                                            asked = asked + (step.id to System.currentTimeMillis())
                                        }
                                        said
                                    }
                                },
                            )
                        }
                        if (step.state == "waiting" && onOpenApprovals != null) {
                            Quiet("Open the card →", color = chrome.warnInk, onClick = { onOpenApprovals(null) })
                        }
                    }
                    Gap(6)
                    Quiet(
                        Hardware.STOP,
                        enabled = busy == null,
                        onClick = { act("stop") { JarvisRuntime.chooseHardware(null) } },
                    )
                }

                notice?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
                        modifier = Modifier.liveStatus())
                }

                // 5. The one command: for the PC, shown to read.
                status.commandLine?.let { line ->
                    Gap(12)
                    Kicker("The one command", Modifier.semantics { heading() })
                    Gap(4)
                    Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                        fontFamily = FontFamily.Monospace)
                    Gap(2)
                    Text(Hardware.COMMAND_ON_PC, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (status.restartPending == true) {
                        Gap(4)
                        Text(Hardware.RESTART, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                }

                // 6. Measuring.
                Gap(12)
                Kicker("Measure", Modifier.semantics { heading() })
                Gap(4)
                Text(
                    Hardware.measureLine(status),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (status.measureSpilled) chrome.warnInk else chrome.textMid,
                )
                Gap(4)
                Secondary(
                    text = if (busy == "measure") "Asking…" else Hardware.MEASURE,
                    enabled = canAct && busy == null && status.measureState != "running",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { act("measure") { JarvisRuntime.measureHardware() } },
                )

                Gap(10)
                Text(
                    "Nothing changes until you pick a setup, and then each step asks with its own " +
                        "approval card on your PC and phone. Every number is calculated, not " +
                        "measured, until you press Measure. Nothing here sends anything off your PC.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}
