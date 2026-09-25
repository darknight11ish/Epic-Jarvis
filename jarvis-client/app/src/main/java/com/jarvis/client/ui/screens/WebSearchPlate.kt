package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.WebSearch
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Web search" on Mind ([WebSearch], the owner's decisions of 2026-09-25) -
 * the desktop's Settings -> Web search, in the same words: on the phone,
 * settings for a PC feature live on Mind.
 *
 * The four providers, each with the PC's own "why use this one" line, which
 * one is in use and what stands in the way of each; Whoogle's reason for
 * being left out; "Ask before every web search" (on at once, off through ONE
 * approval card on the PC); the SearXNG address; and Test search. Every
 * change is ONE tap, held on a stale link ([JarvisRuntime.setWebSearch]).
 *
 * NO KEY BOX. A Tavily or Brave key is typed on the PC only; this screen says
 * whether one is saved and where to add it ([WebSearch.KEY_ENTRY]).
 */
@Composable
internal fun WebSearchSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<WebSearch.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var testing by remember { mutableStateOf(false) }
    var tested by remember { mutableStateOf<Pair<Boolean, String>?>(null) }
    var address by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.webSearch()) {
            is ApiResult.Ok -> {
                val v = WebSearch.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                    if (address == null) address = v.address
                }
                readError = null
            }
            is ApiResult.Failed -> if (WebSearch.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun change(body: String?) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setWebSearch(body)
            } finally {
                busy = false
                reads += 1
            }
        }
    }

    Section(WebSearch.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(WebSearch.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            val err = readError
            when {
                missing -> Text(WebSearch.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read web search: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (v.why.isNotEmpty()) {
                        Text(v.why, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    }
                    v.providers.forEach { p ->
                        Gap(8)
                        val chosen = p.id == v.provider
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: not by colour alone.
                            Text(if (chosen) "${p.label} (in use)" else p.label,
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f))
                            if (!chosen) {
                                Quiet("Use this", enabled = canAct && !busy,
                                    onClick = { change(WebSearch.providerBody(p.id)) })
                            }
                        }
                        Text(p.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        Text(WebSearch.providerLine(p, v.provider), style = MaterialTheme.typography.labelSmall,
                            color = if (p.ready) chrome.textLo else chrome.warnInk)
                        if (p.needsKey) {
                            Text(WebSearch.keyLine(p), style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo)
                        }
                    }
                    Gap(8)
                    Text(v.defaultWhy, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    Gap(8)
                    Text(WebSearch.LEFT_OUT_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    v.leftOut.forEach {
                        Text("${it.label}: ${it.why}", style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }

                    // ---- When a search asks first ----
                    Gap(14)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(v.askLabel, style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                            modifier = Modifier.weight(1f))
                        Spacer(Modifier.width(8.dp))
                        Toggle(
                            // Shown as the PC says it is: off waits for a card,
                            // so the switch does not claim "off" before that.
                            checked = v.askEveryTime,
                            onCheckedChange = { want -> change(WebSearch.askBody(want)) },
                            enabled = canAct && !busy,
                            modifier = Modifier.semantics { contentDescription = v.askLabel },
                        )
                    }
                    Text(v.askDetail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    val cardLine = if (v.waiting) WebSearch.WAITING_CARD else v.last
                    if (cardLine.isNotEmpty()) {
                        Text(cardLine, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            modifier = Modifier.liveStatus())
                    }

                    // ---- Test ----
                    Gap(14)
                    Quiet(if (testing) WebSearch.TEST_BUSY else WebSearch.TEST_LABEL,
                        enabled = canAct && !testing,
                        onClick = {
                            testing = true
                            tested = null
                            scope.launch {
                                try {
                                    tested = JarvisRuntime.testWebSearch()
                                } finally {
                                    testing = false
                                }
                            }
                        })
                    tested?.let { (ok, line) ->
                        Text(line, style = MaterialTheme.typography.bodySmall,
                            color = if (ok) chrome.okInk else chrome.warnInk,
                            modifier = Modifier.liveStatus())
                    }
                    Text(WebSearch.TEST_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)

                    // ---- SearXNG ----
                    Gap(14)
                    Column(Modifier.fillMaxWidth()) {
                        TextInput(
                            value = address ?: v.address,
                            onValueChange = { address = it.take(200) },
                            label = WebSearch.ADDRESS_LABEL,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                        )
                        Text(WebSearch.ADDRESS_NOTE, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo)
                        Quiet(WebSearch.ADDRESS_SAVE, enabled = canAct && !busy,
                            onClick = { change(WebSearch.addressBody(address ?: v.address)) })
                    }

                    // ---- Keys: where they are entered (never here) ----
                    Gap(14)
                    Text(WebSearch.KEYS_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    Text(v.keyEntry, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && view != null && !canAct) {
                Text(WebSearch.STALE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
    }
}
