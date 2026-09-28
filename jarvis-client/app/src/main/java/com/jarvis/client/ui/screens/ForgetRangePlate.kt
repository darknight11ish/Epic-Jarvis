package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ForgetRange
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Forget a time frame" on Brain ([ForgetRange], the owner's decision of
 * 2026-09-28) - the desktop's Brain -> History -> "Forget a time frame", in
 * the same words (both apps are checked against the contract file).
 *
 * The days (a quick choice, or two typed dates), what to look for (what
 * Jarvis learned, chats, or both), then the list from the PC with every
 * item ticked. The owner unticks anything to keep and taps "Forget these";
 * the PC raises ONE approval card listing every item, answered on the
 * card like any other - never by voice, and never from here. Approved, an
 * Undo line shows for 10 minutes: one tap, no card.
 *
 * "Forget these" is greyed on a stale link (rule 4; JarvisRuntime holds it
 * too); Undo never is. "Hide memory lists and chat history" (Settings)
 * hides the list until Show is confirmed, like Brain's other private
 * lists; an open Undo still shows (it carries only counts).
 *
 * "forget what you learned last week", said or typed, fills in the days
 * here (the PC's `asked`) and opens this item (OpenPlace, "forget-range").
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun ForgetRangeSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.forgetRangeTick.collectAsState()
    val pending by JarvisRuntime.pending.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf<ForgetRange.Status?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var preview by remember { mutableStateOf<ForgetRange.Preview?>(null) }
    var ticked by remember { mutableStateOf<Set<String>>(emptySet()) }
    var choice by remember { mutableStateOf("last_week") }
    var from by remember { mutableStateOf("") }
    var to by remember { mutableStateOf("") }
    var kinds by remember { mutableStateOf(setOf("facts", "chats")) }
    var askedSeen by remember { mutableStateOf("") }
    var askedSaid by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    suspend fun readList() {
        val path = ForgetRange.previewPath(if (choice == "custom") null else choice, from, to, kinds)
        if (path == null) {
            said = if (kinds.isEmpty()) "Choose what Jarvis learned, chats, or both." else ForgetRange.w("bad_date")
            return
        }
        when (val r = JarvisRuntime.forgetRangeRead(path)) {
            is ApiResult.Ok -> {
                val reply = r.value
                if (reply.code in 200..299) {
                    val p = ForgetRange.parsePreview(reply.body)
                    preview = p
                    ticked = ForgetRange.allTicked(p)
                    said = null
                } else {
                    preview = null
                    said = ForgetRange.said(reply, "").said
                }
            }
            is ApiResult.Failed -> said = JarvisRuntime.noticeFor(r.error)
        }
    }

    // A card this plate caused is answered elsewhere: read again when the
    // queue changes while it waits.
    val queueKey = if (status?.waiting == true) pending.size else -1

    LaunchedEffect(reads, tick, queueKey) {
        when (val r = JarvisRuntime.forgetRangeRead(ForgetRange.PATH)) {
            is ApiResult.Ok -> {
                val reply = r.value
                status = if (reply.code in 200..299) {
                    ForgetRange.parseStatus(reply.body)
                } else if (ForgetRange.isMissing(reply)) {
                    ForgetRange.parseStatus(null)
                } else {
                    status
                }
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
        val a = status?.asked
        if (a != null && a.id.isNotEmpty() && a.id != askedSeen && !privateHidden) {
            // "forget what you learned last week": the days filled in and the
            // list read - nothing more.
            askedSeen = a.id
            askedSaid = a.said
            choice = "custom"
            from = a.from
            to = a.to
            kinds = a.kinds.toSet().ifEmpty { setOf("facts", "chats") }
            readList()
        } else if (preview != null && !privateHidden && status?.waiting == false) {
            readList()
        }
    }

    // While Undo is open: the minutes left, and the moment it is over.
    val undoOpen = status?.undo != null
    LaunchedEffect(undoOpen, reads) {
        if (undoOpen) {
            delay(20_000)
            reads += 1
        }
    }

    fun act(action: String, json: String) {
        busy = true
        said = null
        scope.launch {
            try {
                val out = JarvisRuntime.forgetRangeWrite(action, json)
                said = out.said
                if (out.listChanged) readList()
            } finally {
                busy = false
            }
        }
    }

    Section(ForgetRange.w("title"), trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val s = status
            val undo = s?.undo
            if (undo != null) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(ForgetRange.undoLine(undo), style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi, modifier = Modifier.weight(1f))
                    Quiet(ForgetRange.w("undo"), enabled = !busy, onClick = { act("undo", "{}") })
                }
                Gap(8)
            }
            when {
                s == null -> Text(
                    readError?.let { "Couldn't read it: $it" } ?: "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (readError != null) chrome.warnInk else chrome.textLo,
                )
                !s.available -> Text(s.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                privateHidden -> {
                    Text("Hidden. Tap Show and confirm it is you.", style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid)
                    Gap(6)
                    Quiet(if (showPrivateBusy) "Checking…" else "Show", enabled = !showPrivateBusy,
                        onClick = onShowPrivate)
                }
                else -> {
                    Text(ForgetRange.w("under"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    if (s.waiting) {
                        Gap(6)
                        Text(ForgetRange.w("waiting"), style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk)
                    } else if (undo == null && s.last != null && s.last.outcome != "done" && s.last.message.isNotEmpty()) {
                        Gap(6)
                        Text(s.last.message, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    if (askedSaid.isNotEmpty() && choice == "custom") {
                        Gap(6)
                        Text(ForgetRange.fill(ForgetRange.w("asked"), "said" to askedSaid),
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (p in s.presets) {
                            OptionChip(p.label, isSelected = choice == p.id, onClick = {
                                choice = p.id
                                askedSaid = ""
                            })
                        }
                        OptionChip(ForgetRange.w("custom"), isSelected = choice == "custom", onClick = {
                            choice = "custom"
                        })
                    }
                    if (choice == "custom") {
                        Gap(8)
                        TextInput(
                            value = from,
                            onValueChange = { from = it.take(16).trim() },
                            label = ForgetRange.w("from"),
                            placeholder = "2026-09-01",
                            supportingText = ForgetRange.w("date_hint"),
                        )
                        Gap(6)
                        TextInput(
                            value = to,
                            onValueChange = { to = it.take(16).trim() },
                            label = ForgetRange.w("to"),
                            placeholder = "2026-09-15",
                        )
                    }
                    Gap(8)
                    Text(ForgetRange.w("kinds"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    for ((k, label) in listOf("facts" to ForgetRange.w("kind_facts"), "chats" to ForgetRange.w("kind_chats"))) {
                        CheckRow(label, null, kinds.contains(k)) { on ->
                            kinds = if (on) kinds + k else kinds - k
                        }
                    }
                    Quiet(ForgetRange.w("show"), enabled = !busy, onClick = {
                        scope.launch { readList() }
                    })
                    preview?.let { p ->
                        ListPart(
                            p = p,
                            ticked = ticked,
                            onTick = { key, on -> ticked = if (on) ticked + key else ticked - key },
                            canForget = canAct && !busy && !s.waiting && undo == null,
                            canAct = canAct,
                            onForget = { act("forget", ForgetRange.forgetBody(p, ticked)) },
                        )
                    }
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}

@Composable
private fun ListPart(
    p: ForgetRange.Preview,
    ticked: Set<String>,
    onTick: (String, Boolean) -> Unit,
    canForget: Boolean,
    canAct: Boolean,
    onForget: () -> Unit,
) {
    val chrome = LocalChrome.current
    Gap(8)
    if (!p.available) {
        Text(p.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        return
    }
    Text(p.said, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
    if (p.tooMany || p.empty) return
    if (p.chatsWhy.isNotEmpty()) {
        Gap(4)
        Text(p.chatsWhy, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    if ("facts" in p.kinds && p.facts.isNotEmpty()) {
        Gap(10)
        Text("${ForgetRange.w("facts_head")} (${p.facts.size})".uppercase(),
            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(ForgetRange.w("erase_note"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        for (f in p.facts) {
            val tags = listOfNotNull(
                f.label,
                ForgetRange.w("pinned").takeIf { f.pinned },
                ForgetRange.w("between_us").takeIf { f.betweenUs },
            ).joinToString(" · ")
            val key = "fact:${f.id}"
            CheckRow(f.text, tags, key in ticked) { on -> onTick(key, on) }
        }
    }
    if ("chats" in p.kinds && p.chats.isNotEmpty()) {
        Gap(10)
        Text("${ForgetRange.w("chats_head")} (${p.chats.size})".uppercase(),
            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        for (c in p.chats) {
            val key = "chat:${c.id}"
            CheckRow(c.title, c.label, key in ticked, warn = ForgetRange.w("spills").takeIf { c.spills }) { on ->
                onTick(key, on)
            }
        }
    }
    val n = ForgetRange.tickedCount(p, ticked)
    Gap(10)
    Primary(ForgetRange.forgetLabel(n), color = chrome.badInk, enabled = canForget && n > 0, onClick = onForget)
    if (!canAct) {
        Gap(4)
        Text(ForgetRange.w("stale"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    } else if (n == 0) {
        Gap(4)
        Text(ForgetRange.w("none_ticked"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
}

/**
 * One tickable line: the whole row answers a tap and TalkBack reads it as
 * one checkbox with its words (the box itself takes no taps of its own).
 */
@Composable
private fun CheckRow(
    main: String,
    under: String?,
    checked: Boolean,
    warn: String? = null,
    onChange: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .toggleable(value = checked, role = Role.Checkbox, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = null)
        Column(Modifier.weight(1f)) {
            Text(main, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            if (!under.isNullOrEmpty()) {
                Text(under, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
            if (warn != null) {
                Text(warn, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            }
        }
    }
}
