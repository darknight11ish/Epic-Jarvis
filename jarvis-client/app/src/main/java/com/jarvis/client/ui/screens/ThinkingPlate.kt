package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Thinking
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Thinking levels" on Settings (Section 5.5).
 * Shows one row per running model with level controls (Off, Quick, Deep, Auto).
 * Only supported levels are enabled. No approval card required.
 */
@Composable
internal fun ThinkingSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Thinking.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.thinking()) {
            is ApiResult.Ok -> {
                val v = Thinking.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Thinking.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun choose(role: String, level: String) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setThinking(role, level)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    val v = view
    Section(Thinking.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(v?.detail ?: Thinking.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(4)
            Text(v?.notice ?: Thinking.NOTICE, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            Gap(10)
            when {
                missing -> Text(
                    Thinking.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                readError != null -> Text(
                    readError ?: "",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                v != null -> {
                    if (v.models.isEmpty()) {
                        Text(
                            "No models currently running.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    } else {
                        v.models.forEachIndexed { idx, model ->
                            if (idx > 0) {
                                Gap(8)
                                Rule()
                                Gap(8)
                            }
                            Column(Modifier.fillMaxWidth()) {
                                Row(
                                    Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        Text(
                                            model.name,
                                            style = MaterialTheme.typography.titleSmall,
                                            color = chrome.textHi,
                                        )
                                        if (model.model.isNotBlank()) {
                                            Text(
                                                model.model,
                                                style = MaterialTheme.typography.labelSmall,
                                                color = chrome.textLo,
                                            )
                                        }
                                    }
                                    Spacer(Modifier.width(8.dp))
                                    Pill(
                                        Thinking.LEVEL_LABELS[model.level] ?: model.level,
                                        color = if (model.level == "off") chrome.textMid else chrome.okInk,
                                    )
                                }
                                Gap(4)
                                Text(
                                    model.why,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textMid,
                                )
                                Gap(8)
                                Row(Modifier.fillMaxWidth()) {
                                    Thinking.LEVELS.forEach { lvl ->
                                        val supported = model.supported.contains(lvl)
                                        val selected = model.level == lvl
                                        Quiet(
                                            Thinking.LEVEL_LABELS[lvl] ?: lvl,
                                            enabled = canAct && !busy && supported,
                                            color = if (selected) chrome.textHi else chrome.textLo,
                                            onClick = { choose(model.role, lvl) },
                                        )
                                        Spacer(Modifier.width(8.dp))
                                    }
                                }
                            }
                        }
                    }
                }
                else -> Text(
                    "Asking Jarvis…",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            }
            said?.let {
                Gap(6)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }
}
