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
import androidx.compose.runtime.saveable.rememberSaveable
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
 * Jarvis learned, chats, or both), then the list from the PC with every item
 * ticked - and the pinned chats it is KEEPING beside them (owner, 2026-11-04):
 * drawn as kept, never tickable, never counted, never sent. The owner unticks
 * anything to keep and taps "Forget these"; the PC raises ONE approval card
 * carrying the COUNT and the days (this list is where every title and date
 * stays - the owner's ruling of 2026-11-13, "Show the count, allow it"),
 * answered on the card like any other - never by voice, and never from here.
 *
 * The two yeses: the card is the FIRST and changes nothing. Approving it makes
 * the PC hold the checked items for two minutes and the status carries
 * `confirm` - this plate then shows the PC's own sentence, the minutes left
 * and one more tap ("Yes, forget them"), which sends the held id and a literal
 * `true`. Only that deletes. A refusal at either step is shown in the PC's own
 * words, never swallowed.
 *
 * After it, an Undo line shows for 10 minutes: one tap, no card.
 *
 * "Forget these" and the second yes are greyed on a stale link (rule 4;
 * JarvisRuntime holds them too); Undo never is. "Hide memory lists and chat
 * history" (Settings) hides the list until Show is confirmed, like Brain's
 * other private lists - and takes the words this plate already holds out of
 * its state, pinned chats' titles included ([ForgetRange.redact]). An open
 * Undo still shows (it carries only counts).
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
    // Saveable (the chat audit, 2026-09-28, phone B3): this plate sits in
    // Brain's scrolling list, and plain `remember` lost the typed days when it
    // scrolled away or the phone turned. The ticks are not kept that way: a
    // list read afresh starts from the PC's own list.
    var choice by rememberSaveable { mutableStateOf("last_week") }
    var from by rememberSaveable { mutableStateOf("") }
    var to by rememberSaveable { mutableStateOf("") }
    // A set of strings is Serializable, so a Bundle can hold it.
    var kinds by rememberSaveable { mutableStateOf(setOf("facts", "chats")) }
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
                    // What the owner unticked stays unticked when the list is
                    // read again (after a card, an Undo, "the list changed");
                    // anything new is ticked - except a customer-support
                    // record, which stays as the owner left it: one they
                    // ticked stays ticked (the chat audit, 2026-09-28).
                    val had = preview?.let { ForgetRange.allTicked(it) }
                    val unticked = had?.let { it - ticked }.orEmpty()
                    val tickedExtra = had?.let { ticked - it }.orEmpty()
                    val p = ForgetRange.parsePreview(reply.body)
                    preview = p
                    val listed = p.chats.map { "chat:${it.id}" }.toSet()
                    ticked = ForgetRange.allTicked(p) - unticked + tickedExtra.filter { it in listed }
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
    // queue changes while it waits - and again when the private lists are
    // shown, so Show always ends with a list read over the wire rather than
    // the redacted one hiding left behind.
    val queueKey = if (status?.waiting == true) pending.size else -1

    LaunchedEffect(reads, tick, queueKey, privateHidden) {
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

    // While Undo is open: the minutes left, and the moment it is over. Only
    // the status is read again - never the list, so ticks are not disturbed.
    val undoOpen = status?.undo != null
    LaunchedEffect(undoOpen) {
        while (undoOpen) {
            delay(20_000)
            val r = JarvisRuntime.forgetRangeRead(ForgetRange.PATH)
            val reply = (r as? ApiResult.Ok)?.value
            if (reply != null && reply.code in 200..299) status = ForgetRange.parseStatus(reply.body)
        }
    }

    // While the PC holds the second yes: the same, so its minutes run down and
    // an expired hold stops being offered. The PC owns the clock; this only
    // asks it again, and the status says "the second yes timed out" itself.
    val holdOpen = status?.confirm != null
    LaunchedEffect(holdOpen) {
        while (holdOpen) {
            delay(20_000)
            val r = JarvisRuntime.forgetRangeRead(ForgetRange.PATH)
            val reply = (r as? ApiResult.Ok)?.value
            if (reply != null && reply.code in 200..299) status = ForgetRange.parseStatus(reply.body)
        }
    }

    // "Hide memory lists and chat history" takes the words this plate is
    // already holding out of its state, not just off the screen: a pinned chat
    // carries a TITLE, so it is hidden with the facts and the chats
    // (ForgetRange.redact, the desktop's Rust redact() rule). Show reads a
    // fresh list (the effect above is keyed on `privateHidden`).
    LaunchedEffect(privateHidden) {
        val p = preview
        if (privateHidden && p != null && !p.hidden) preview = ForgetRange.redact(p)
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
            val confirm = s?.confirm
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
                    when {
                        s.waiting -> {
                            Gap(6)
                            Text(ForgetRange.w("waiting"), style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk)
                        }
                        confirm != null -> {
                            // The SECOND yes (owner, 2026-11-04): the card is
                            // approved and the PC is holding the ticked items.
                            // Not a card - one more line and one more tap.
                            Gap(6)
                            Text(confirm.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                            Text(ForgetRange.holdLeftLine(confirm),
                                style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                            Gap(6)
                            Primary(
                                ForgetRange.x("confirm_yes"),
                                color = chrome.badInk,
                                enabled = canAct && !busy,
                                onClick = { act("confirm", ForgetRange.confirmBody(confirm.id)) },
                            )
                        }
                        undo == null && s.last != null && s.last.outcome != "done" && s.last.message.isNotEmpty() -> {
                            Gap(6)
                            Text(s.last.message, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
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
                    // Not the redacted copy hiding left behind: after Show the
                    // list appears when the fresh read lands, never as rows
                    // with their words taken out.
                    preview?.takeIf { !it.hidden }?.let { p ->
                        ListPart(
                            p = p,
                            ticked = ticked,
                            onTick = { key, on -> ticked = if (on) ticked + key else ticked - key },
                            // A second yes already held means the PC would
                            // refuse another card (409), so it is not offered.
                            canForget = canAct && !busy && !s.waiting && confirm == null && undo == null,
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
    // A LARGE selection is said in the PC's own words before anything is sent
    // (owner's 2026-11-08 ruling: no cap, but a big wipe keeps the two yesses).
    if (p.largeWipe) {
        Gap(4)
        Text(p.largeWords, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    }
    if (p.empty) return
    if (p.chatsWhy.isNotEmpty()) {
        Gap(4)
        Text(p.chatsWhy, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    // The chats this Forget is KEEPING (owner, 2026-11-04), above the tickable
    // lists on purpose: the owner sees what stays before what goes. Nothing
    // here has a box, and nothing here is ever sent.
    if (p.pinnedKept.isNotEmpty()) {
        Gap(10)
        Text(ForgetRange.pinnedKeptLine(p.pinnedKeptCount).uppercase(),
            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(ForgetRange.x("pinned_why"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        for (x in p.pinnedKept) KeptRow(x)
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
            // What kind of chat, when it is not an ordinary one; a support
            // record starts unticked and says so (the owner, 2026-09-28).
            val under = listOfNotNull(ForgetRange.chatKindTag(c.kind), c.label.ifEmpty { null }).joinToString(" · ")
            val warn = listOfNotNull(
                ForgetRange.w("support").takeIf { c.kind == "support" },
                ForgetRange.w("spills").takeIf { c.spills },
            ).joinToString(" ").ifEmpty { null }
            CheckRow(c.title, under, key in ticked, warn = warn) { on ->
                onTick(key, on)
            }
        }
    }
    val n = ForgetRange.tickedCount(p, ticked)
    // How long it takes, measured by the PC from the counts just read, said
    // BEFORE the owner is asked for the card (owner, 2026-11-04).
    if (p.estimate.text.isNotEmpty()) {
        Gap(8)
        Text(p.estimate.text, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    }
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
 * One pinned chat, drawn as KEPT: its title and how many messages stay. No
 * check box and no tap - there is nothing here to tick or untick.
 */
@Composable
private fun KeptRow(x: ForgetRange.PinnedChat) {
    val chrome = LocalChrome.current
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(x.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            Text(ForgetRange.messagesLine(x.messages), style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo)
        }
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
