package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * Settings -> "To-do list carry-over" (2026-11-02; the owner's choice of BOTH
 * ways, full daily rollover as the DEFAULT; Gemini's ruling 8;
 * docs/JARVIS-API.md section 178; backend `jarvis_schedule.py`; the desktop's
 * `todo-carryover-settings.js` draws the same two from the same route).
 *
 * EVERY to-do item keeps the day it was written, for good. This picks only how
 * the SAME rows are drawn:
 *
 *  * "Daily rollover" (the default): today's list is every open item written
 *    today or earlier, each older one tagged "from yesterday", "from Friday
 *    (3d ago)" or "from Oct 26" by the PC;
 *  * "Day by day": each item stays on the day it was written, grouped under
 *    that day's heading.
 *
 * NO APPROVAL CARD EITHER WAY, and the PC decides that: the change moves no
 * item, deletes nothing, re-stamps no day and loosens no rule. `created_date`
 * is written once when an item is created, so switching back and forth loses
 * nothing - the switch is lossless by construction.
 *
 * THE TWO MODES' OWN WORDS COME FROM THE PC (`todo_modes` on GET
 * /api/schedule), so this screen cannot invent a third one or rename one; the
 * plain fallback below is only for a PC from before this feature, whose one
 * real behaviour is rollover.
 *
 * The change rides [Schedule.ACT_PATH] (`{"do": "todo_mode", "mode": ...}`),
 * which is the SAME method a typed or spoken sentence runs on the PC through
 * the settings registry - so a tap here and "set the to-do list mode to day by
 * day" cannot disagree. Held on a stale link, like every write here.
 */
@Composable
internal fun TodoCarryoverSection(canAct: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var mode by remember { mutableStateOf(Schedule.MODE_ROLLOVER) }
    var modes by remember { mutableStateOf(Schedule.todoModes(null)) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    // A change made anywhere (the PC, the desktop, a spoken sentence) rings the
    // same tick this phone follows for the whole Coming up list.
    val tick by JarvisRuntime.scheduleTick.collectAsState()
    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.schedule()) {
            is ApiResult.Ok -> {
                val view = Schedule.parse(r.value)
                if (view != null) {
                    mode = view.todoMode
                    modes = Schedule.todoModes(view)
                }
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    fun choose(value: String) {
        if (busy || !canAct || value == mode) return
        busy = true
        said = null
        scope.launch {
            try {
                val (changed, sentence) = JarvisRuntime.setTodoMode(value)
                if (changed) {
                    mode = value
                    reads += 1
                }
                said = sentence
            } finally {
                busy = false
            }
        }
    }

    Section(Schedule.MODE_TITLE) {
        Plate {
            Text(
                Schedule.MODE_DETAIL,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            val problem = readError
            if (problem != null) {
                Gap(4)
                Text(
                    "Couldn't read it: $problem",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
            }
            modes.forEach { m ->
                Gap(6)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Quiet(
                        if (m.value == mode) "${m.label} (now)" else m.label,
                        enabled = canAct && !busy && m.value != mode,
                        onClick = { choose(m.value) },
                    )
                }
                if (m.detail.isNotEmpty()) {
                    Text(
                        m.detail,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }
            Gap(4)
            Text(
                when {
                    busy -> "Saving…"
                    said != null -> said.orEmpty()
                    else -> Schedule.MODE_SAVED_ON_PC
                },
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}
