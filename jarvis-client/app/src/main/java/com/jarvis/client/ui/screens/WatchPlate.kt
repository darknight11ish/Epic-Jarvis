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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Watch
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
 * Watches on Mind - the GitHub topics Jarvis keeps an eye on, and what it has
 * found. The desktop's Brain window, Watch tab, on the same five routes
 * ([com.jarvis.client.net.Watch]).
 *
 * Adding a topic is held while the link is down or stale (rule 4: it turns
 * something on), greyed here and refused again by the runtime. Forget and
 * "Mark these read" always go. If the PC asks first, the line under the plate
 * says so and where the card is; nothing on this plate approves anything.
 *
 * Reads and acts through [JarvisRuntime] directly, so [BrainScreen] needs one
 * line for it.
 */
@Composable
internal fun WatchSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.watchTick.collectAsState()
    var view by remember { mutableStateOf<Watch.View?>(null) }
    var findings by remember { mutableStateOf<List<Watch.Finding>?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var reads by remember { mutableIntStateOf(0) }
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var formOpen by rememberSaveable { mutableStateOf(false) }
    var confirmForget by remember { mutableStateOf<String?>(null) }

    // Read when the plate opens, when asked, after every change, and on each
    // `finding` event.
    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.watch()) {
            is ApiResult.Ok -> {
                view = Watch.read(r.value)
                readError = null
            }
            is ApiResult.Failed ->
                readError = Watch.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
        when (val r = JarvisRuntime.watchReport()) {
            is ApiResult.Ok -> findings = Watch.findings(r.value)
            is ApiResult.Failed -> Unit // the topics line above already says why
        }
    }

    fun act(block: suspend () -> String) {
        if (busy) return
        busy = true
        scope.launch {
            said = block()
            busy = false
            reads += 1
        }
    }

    val badge = view?.waitingForYou?.takeIf { it > 0 }?.let { "Watches · $it new" } ?: "Watches"
    Section(badge, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(
                "Jarvis checks GitHub for new projects on these topics. Nothing here is ever " +
                    "spoken aloud. A project with no licence stated gives you no permission to use it.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(8)
            val v = view
            val err = readError
            if (v == null) {
                Text(
                    if (err != null) "Couldn't read the watch list: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
            } else {
                Text(Watch.headLine(v), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                if (err != null) {
                    Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk)
                }
                Gap(8)
                if (v.list.isEmpty()) {
                    Text("No topics watched.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                }
                val now = System.currentTimeMillis() / 1000.0
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    v.list.forEach { t ->
                        TopicRow(
                            t = t,
                            nowSeconds = now,
                            confirming = confirmForget == t.name,
                            busy = busy,
                            onForget = { confirmForget = t.name },
                            onConfirm = {
                                confirmForget = null
                                act { JarvisRuntime.removeWatch(t.name) }
                            },
                            onCancel = { confirmForget = null },
                        )
                    }
                }
            }

            Gap(8)
            if (formOpen) {
                AddTopicForm(
                    canAct = canAct,
                    busy = busy,
                    onAdd = { name, query, stars, language, notify ->
                        act {
                            val (taken, out) = JarvisRuntime.addWatch(name, query, stars, language, notify)
                            // Kept open, still filled in, when the PC did not take it.
                            if (taken) formOpen = false
                            out
                        }
                    },
                    onCancel = { formOpen = false },
                )
            } else {
                Quiet("Add a topic", enabled = canAct && !busy, onClick = { formOpen = true })
            }
            if (!canAct) {
                Text(
                    "Adding a topic waits until the link to your PC is live again.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }

            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textHi,
                    modifier = Modifier.liveStatus())
            }

            Gap(12)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("What is new", style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                    modifier = Modifier.weight(1f))
                Quiet(
                    "Mark these read",
                    enabled = !busy && !findings.isNullOrEmpty(),
                    onClick = { act { JarvisRuntime.markWatchSeen() } },
                )
            }
            Text(
                "Looking here marks nothing read. Only \"Mark these read\" does.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(6)
            val list = findings
            when {
                list == null -> Unit
                list.isEmpty() -> Text(
                    "Nothing new since you last marked the list read.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                else -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    list.forEach { f -> FindingRow(f) }
                }
            }
        }
    }
}

@Composable
private fun TopicRow(
    t: Watch.Topic,
    nowSeconds: Double,
    confirming: Boolean,
    busy: Boolean,
    onForget: () -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(t.name, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                modifier = Modifier.weight(1f))
            Text(
                if (t.error != null) "error" else "watching",
                style = MaterialTheme.typography.labelSmall,
                color = if (t.error != null) chrome.badInk else chrome.okInk,
            )
        }
        Watch.topicLines(t, nowSeconds).forEach {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (confirming) {
            Text(Watch.forgetWarning(t.name), style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet("Yes, forget it", color = chrome.badInk, enabled = !busy, onClick = onConfirm)
                Quiet("Keep it", onClick = onCancel)
            }
        } else {
            Quiet("Forget", color = chrome.badInk, enabled = !busy, onClick = onForget)
        }
    }
}

@Composable
private fun FindingRow(f: Watch.Finding) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(f.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                modifier = Modifier.weight(1f))
            Text(
                f.licence ?: "no licence",
                style = MaterialTheme.typography.labelSmall,
                color = if (f.licence != null) chrome.okInk else chrome.warnInk,
            )
        }
        Watch.findingLines(f).forEach {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}

@Composable
private fun AddTopicForm(
    canAct: Boolean,
    busy: Boolean,
    onAdd: (name: String, query: String, stars: String, language: String, notify: Boolean) -> Unit,
    onCancel: () -> Unit,
) {
    val chrome = LocalChrome.current
    var name by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var stars by rememberSaveable { mutableStateOf("") }
    var language by rememberSaveable { mutableStateOf("") }
    var notify by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        TextInput(value = name, onValueChange = { name = it }, label = "Name",
            placeholder = "e.g. local speech models")
        TextInput(value = query, onValueChange = { query = it }, label = "Search for",
            supportingText = "Leave empty to search for the name.")
        TextInput(
            value = stars,
            onValueChange = { stars = it },
            label = "Min stars",
            supportingText = "Leave empty for any.",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        )
        TextInput(value = language, onValueChange = { language = it }, label = "Language",
            supportingText = "A programming language, e.g. Python. Leave empty for any.")
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Notify me", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                modifier = Modifier.weight(1f))
            Toggle(
                checked = notify,
                onCheckedChange = { notify = it },
                modifier = Modifier.semantics { contentDescription = "Notify me" },
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Quiet(
                "Add topic",
                enabled = canAct && !busy && name.isNotBlank(),
                onClick = { onAdd(name, query, stars, language, notify) },
            )
            Quiet("Cancel", color = chrome.textMid, onClick = onCancel)
        }
    }
}
