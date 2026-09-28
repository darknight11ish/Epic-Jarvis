package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.face.Sky
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SkySettings
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

/**
 * Appearance -> "Sun, moon and weather" (the owner's decisions of 2026-09-28;
 * [SkySettings]) - the desktop's Settings -> Appearance -> "Sun, moon and
 * weather", in the same words (the PC's own).
 *
 * "Show the sun and moon behind the face": one switch, at once either way
 * (showing waits for a live link). The town is typed on the PC only - this
 * shows which one, today's rise and set times worked out on this phone, and
 * "Forget my town" (at once). The weather: three choices; "Open-Meteo
 * (online)" raises ONE approval card on the PC (it sends the rough position
 * to the internet); off and "My Home Assistant" are at once.
 */
@Composable
internal fun SkySection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val link by JarvisRuntime.link.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    val canAct = link == LinkState.CONNECTED && !stale
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<SkySettings.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        if (!JarvisRuntime.isInitialized) {
            missing = true
            return@LaunchedEffect
        }
        when (val r = JarvisRuntime.sky()) {
            is ApiResult.Ok -> {
                val v = SkySettings.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (SkySettings.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun send(body: String?) {
        if (busy || body == null) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setSky(body)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    val v = view
    Section(v?.title ?: SkySettings.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val err = readError
            when {
                missing -> Text(SkySettings.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    // Showing adds something, so it waits for a live link;
                    // hiding never does.
                    SwitchRow(
                        title = v.showLabel,
                        detail = v.showDetail,
                        checked = v.show,
                        onChange = { send(SkySettings.showBody(it)) },
                        enabled = !busy && (v.show || canAct),
                    )
                    Gap(10)
                    Text(v.placeLabel, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                    val place = v.place
                    Text(
                        if (place != null) "${place.name} (${"%.1f".format(java.util.Locale.ROOT, place.lat)}, ${"%.1f".format(java.util.Locale.ROOT, place.lon)})"
                        else v.placeNone,
                        style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    )
                    Text(v.placeDetail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (place != null) {
                        val fmt = remember { DateFormat.getTimeInstance(DateFormat.SHORT) }
                        val line = remember(place, reads) {
                            Sky.todayWords(Sky.summary(System.currentTimeMillis().toDouble(), place.lat, place.lon)) {
                                fmt.format(Date(it))
                            }
                        }
                        Gap(4)
                        Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        Gap(4)
                        Quiet(v.forgetLabel, enabled = !busy, onClick = { send(SkySettings.forgetBody()) })
                    }
                    Gap(12)
                    Text(v.weatherLabel, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                    Text(v.weatherDetail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    v.choices.forEach { c ->
                        Gap(8)
                        val chosen = c.id == v.source
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(
                                if (chosen) "${c.label} (in use)" else c.label,
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            if (!chosen) {
                                Quiet(
                                    "Use this",
                                    enabled = !busy && (c.id == "off" || canAct),
                                    onClick = { send(SkySettings.weatherBody(c.id)) },
                                )
                            }
                        }
                        Text(c.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    val lines = listOf(v.status, if (!v.waiting) v.lastMessage else "").filter { it.isNotBlank() }
                    if (lines.isNotEmpty()) {
                        Gap(8)
                        Text(
                            lines.joinToString(" "), style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid, modifier = Modifier.liveStatus(),
                        )
                    }
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid, modifier = Modifier.liveStatus())
            }
        }
    }
}
