package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Antislop
import com.jarvis.client.net.ApiResult
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Anti-Slop filter", drawn under the existing "How Jarvis talks" card on
 * Settings ([MannerSection]) - the desktop's Settings -> How Jarvis talks ->
 * Anti-Slop filter, and the same route (2026-10-28; docs/JARVIS-API.md section
 * 159; backend `jarvis_antislop.py`).
 *
 * The PHONE has the master switch, the em-dash exemption and the During/After
 * mode. The desktop's card also carries the three scopes, the Delivery Gate
 * switch and the three Liveliness dials; those are not mirrored here on purpose
 * - this is a settings mirror, not a second editor, and it grows no catalogue
 * (CLAUDE.md's standing rule; docs/ARCHITECTURE.md section 8).
 *
 * Two sentences here are honesty rather than decoration (2026-10-28, Gemini
 * review Q1/Q3): the line under the description names which rules are really
 * checked in code and which are only guidance, and the "Allow em-dashes (—)"
 * row's detail says that Write Like Me's own habit already wins - the box is
 * the blanket "keep them everywhere", not the voiceprint rule.
 *
 * One tap is one change, held on a stale link ([JarvisRuntime.setAntislop],
 * [JarvisRuntime.setAntislopMode] and [JarvisRuntime.setAntislopEmDashes]) and
 * re-read after every write, so what is on screen is the PC's truth and never
 * the tap's. Neither direction raises an approval card: it changes only the
 * wording of an answer.
 */
@Composable
internal fun AntislopPlate(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Antislop.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.antislop()) {
            is ApiResult.Ok -> {
                val v = Antislop.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Antislop.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun write(action: suspend () -> String) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = action()
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    Gap(16)
    Text(Antislop.TITLE, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
    Gap(4)
    val v = view
    val err = readError
    when {
        missing -> {
            Text(Antislop.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        v == null && err != null -> {
            Text("Couldn't read it: $err", style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk)
        }
        v == null -> {
            Text("Reading…", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        }
        else -> {
            Text(v.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(4)
            // The enforcement reality, in one sentence: the fixed list really is
            // checked in code, the layout and taste rules are guidance only.
            Text(Antislop.REALITY, style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo)
            Gap(8)
            // One switch with its words: the row takes the taps and TalkBack
            // reads the title with its on/off state - the same shape as the
            // Humour row directly above it.
            Row(
                Modifier
                    .fillMaxWidth()
                    .toggleable(
                        value = v.enabled,
                        enabled = canAct && !busy,
                        role = Role.Switch,
                        onValueChange = { on -> write { JarvisRuntime.setAntislop(on) } },
                    ),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(Antislop.TITLE, style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi, modifier = Modifier.weight(1f))
                Switch(checked = v.enabled, enabled = canAct && !busy, onCheckedChange = null)
            }
            Gap(4)
            Text(
                if (v.enabled) "Filtering now. Applies from the next turn." else v.offNote,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            // The mode only means anything while the filter is on, so it is
            // drawn with the switch's own state rather than offered over an
            // off filter - the desktop card does the same.
            if (v.enabled) {
                // The em-dash exemption (2026-10-28, Gemini review Q3). ON-only,
                // like the desktop card's row: an exemption from a filter that
                // is not running would be a control that does nothing. The row
                // reads "Allow em-dashes (—)", and its detail line says who
                // already wins - Write Like Me's own habit - so the box is
                // never read as that rule.
                Gap(12)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .toggleable(
                            value = v.allowEmDashes,
                            enabled = canAct && !busy,
                            role = Role.Switch,
                            onValueChange = { on ->
                                write { JarvisRuntime.setAntislopEmDashes(on) }
                            },
                        ),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(Antislop.EM_DASH_LABEL, style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi, modifier = Modifier.weight(1f))
                    Switch(checked = v.allowEmDashes, enabled = canAct && !busy,
                        onCheckedChange = null)
                }
                Text(Antislop.EM_DASH_DETAIL, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                Gap(12)
                Text("How it applies", style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi)
                Antislop.MODES.forEach { id ->
                    Gap(8)
                    val chosen = id == v.mode
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // "(in use)" as well as the colour: never by colour alone.
                        Text(
                            if (chosen) "${Antislop.MODE_LABEL.getValue(id)} (in use)"
                            else Antislop.MODE_LABEL.getValue(id),
                            style = MaterialTheme.typography.titleSmall,
                            color = if (chosen) chrome.okInk else chrome.textHi,
                            modifier = Modifier.weight(1f),
                        )
                        if (!chosen) {
                            Quiet("Use this", enabled = canAct && !busy,
                                onClick = { write { JarvisRuntime.setAntislopMode(id) } })
                        }
                    }
                    Text(Antislop.MODE_WHY.getValue(id),
                        style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
            }
        }
    }
    said?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}
