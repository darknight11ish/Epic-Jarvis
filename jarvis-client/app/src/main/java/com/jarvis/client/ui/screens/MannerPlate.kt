package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
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
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Manner
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "How Jarvis talks" on Mind ([Manner], the owner's decision of 2026-09-25) -
 * the desktop's Settings -> How Jarvis talks, in the same words: on the
 * phone, settings for a PC feature live on Mind.
 *
 * Two choices, each with the PC's own "why" line: "Warm and brief (default)"
 * and "Plain". Wording only - never what Jarvis does, asks or remembers - so
 * neither raises an approval card. ONE tap is ONE change, held on a stale
 * link ([JarvisRuntime.setManner]).
 */
@Composable
internal fun MannerSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Manner.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.manner()) {
            is ApiResult.Ok -> {
                val v = Manner.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Manner.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun choose(id: String) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setManner(id)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    Section(Manner.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val v = view
            val err = readError
            Text(v?.detail ?: Manner.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            when {
                missing -> Text(Manner.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    v.choices.forEach { c ->
                        Gap(8)
                        val chosen = c.id == v.manner
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(if (chosen) "${c.label} (in use)" else c.label,
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f))
                            if (!chosen) {
                                Quiet("Use this", enabled = canAct && !busy, onClick = { choose(c.id) })
                            }
                        }
                        Text(c.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    Text(v.spoken, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}
