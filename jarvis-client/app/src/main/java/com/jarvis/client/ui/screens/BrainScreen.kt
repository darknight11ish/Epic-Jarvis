package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.BrainSnapshot
import com.jarvis.client.LinkState
import com.jarvis.client.net.Attention
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.net.VersionInfo
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Freshness
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Meter
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * State of Mind — what Jarvis is doing, thinking with, and holding.
 *
 * Deliberately a status board rather than an animated node graph, and that is a
 * measurement rather than a preference: there is no 60fps content in this data.
 * The active model changes every few seconds, the routing lane changes per
 * request, VRAM samples arrive around 1 Hz, and memory facts and jobs are
 * event-driven. Animating it at the display rate would spend the frame budget
 * interpolating nothing — and twenty node labels re-measured per frame costs an
 * estimated 3–12ms, more than everything else on screen combined.
 *
 * The live feeling comes from latency and from one or two things in motion: a
 * number that changes within 200ms of the event, and a needle that glides to
 * it. It does not come from a simulation. A graph that re-lays-out on every
 * glance also makes the data harder to read, because a fact you have to re-find
 * is worse than a row that stays put.
 *
 * The face is parked while this is open — two animated canvases on a mid-range
 * GPU is exactly where the budget goes.
 */
@Composable
fun BrainScreen(
    link: LinkState,
    stale: Boolean,
    activity: Activity,
    power: String,
    status: StatusInfo?,
    version: VersionInfo?,
    attention: Attention,
    jobs: List<JobRecord>,
    brain: BrainSnapshot,
    onRefresh: () -> Unit,
    onBack: () -> Unit,
    /** Which proposal, if any, has a decision in flight - never two at once. */
    memoryDecideBusyId: Long?,
    onDecideMemory: (id: Long, accept: Boolean) -> Unit,
    /**
     * The daily "tidy memory overnight?" card, or null to show none.
     *
     * Passed in already decided rather than read fresh from `brain.memory`
     * every recomposition: the server marks itself as having offered the
     * moment `/api/memory/pending` is polled at all, not when the owner
     * acts on it, so a second read - which any OTHER write on this screen
     * triggers via its own refresh - comes back with the offer already
     * gone. The caller holds the sticky, once-seen copy; this composable
     * only ever renders what it is handed.
     */
    sleepOffer: JsonObject? = null,
    sleepOfferBusy: Boolean = false,
    onSleepTimeAction: (enabled: Boolean?, remind: Boolean?) -> Unit = { _, _ -> },
    onDismissSleepOffer: () -> Unit = {},
    /** What a Keep/Discard send failed with, e.g. not connected. Null hides it. */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    /**
     * The model list, or null on a backend without the `models` capability -
     * in which case the section is not drawn at all, per §2's rule that a
     * capability reporting false means hide the UI for it.
     */
    models: ModelsInfo? = null,
    /** True while a switch or rollback is in flight, so neither can double-send. */
    modelBusy: Boolean = false,
    onSwitchModel: (ref: String) -> Unit = {},
    onRollbackModel: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("State of mind", onBack) { Quiet("Refresh", onClick = onRefresh) }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // 1. The rush latch, first, because it changes how everything below
            // should be read. Outside text that tried to raise the tier is the
            // one thing on this screen that is adversarial by construction.
            rushOf(brain.contentRisk)?.let { rush ->
                item(key = "rush") { RushBanner(rush) }
            }

            // 2. Whether any of this can be trusted at all. A stale board is
            // worse than no board: every number below is last-known, and on a
            // screen full of numbers that distinction has to lead.
            item(key = "freshness") {
                Freshness(link, stale, brain.fetchedAtMs)
            }

            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            item(key = "doing") {
                Section("Doing") {
                    Plate {
                        Field("Activity", activity.name.lowercase().replaceFirstChar { it.uppercase() })
                        Field("Power", power.replaceFirstChar { it.uppercase() })
                        val lane = status?.lane?.lowercase()
                        Field(
                            "Route",
                            when (lane) {
                                "cloud" -> "Cloud — this is leaving your machine"
                                "local" -> "Local"
                                "offline" -> "Offline"
                                null -> "Not reported"
                                else -> lane
                            },
                            valueColor = when (lane) {
                                "cloud" -> com.jarvis.client.face.Palette.VIOLET_4
                                "local" -> chrome.okInk
                                "offline" -> chrome.badInk
                                else -> null
                            },
                        )
                        status?.model?.let { Field("Model", it, machine = true) }
                        if (status?.held == true) {
                            Gap(4)
                            Text(
                                "Something is held — a message inside its send window.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                        }
                    }
                }
            }

            if (models != null) {
                item(key = "models") {
                    Section("Model") {
                        ModelsPlate(
                            models = models,
                            busy = modelBusy,
                            canAct = link == LinkState.CONNECTED && !stale,
                            onSwitch = onSwitchModel,
                            onRollback = onRollbackModel,
                        )
                    }
                }
            }

            item(key = "attention") {
                Section("Attention budget") { AttentionPlate(attention) }
            }

            if (jobs.isNotEmpty()) {
                item(key = "jobs") {
                    Section("Background work") {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            jobs.forEach { JobPlate(it) }
                        }
                    }
                }
            }

            // 4. The endpoints whose shape the contract does not fix. Rendered
            // from whatever actually came back — see JarvisApi.probe.
            item(key = "compute") {
                Probed("Compute", brain.compute, "GPU and VRAM plan")
            }
            item(key = "memory") {
                // The QUEUE, not the corpus. /api/graph is desktop-only by the
                // contract's own instruction, and a memory graph is not a thing
                // to read on a phone; what belongs here is the short list of
                // facts waiting for a yes or no - and, unlike every other
                // Probed section, this one actually answers them, the same
                // one-at-a-time way the desktop's own Memory tab does.
                MemoryQueue(
                    data = brain.memory,
                    busyId = memoryDecideBusyId,
                    onKeep = { id -> onDecideMemory(id, true) },
                    onDiscard = { id -> onDecideMemory(id, false) },
                    sleepOffer = sleepOffer,
                    sleepOfferBusy = sleepOfferBusy,
                    onSleepTimeAction = onSleepTimeAction,
                    onDismissSleepOffer = onDismissSleepOffer,
                )
            }
            item(key = "initiative") {
                Probed("Findings", brain.initiative, "What Jarvis noticed on its own")
            }
            item(key = "ledger") {
                Probed("Audit chain", brain.ledger, "Entry count and last verified point")
            }
            item(key = "skills") {
                Probed("Skills", brain.skills, "Installed, with scan verdicts")
            }

            item(key = "capabilities") {
                // Sorted once per handshake, not once per event. `version` holds a
                // JsonObject, which Compose treats as an unstable type, so this whole
                // screen re-runs on EVERY server event rather than being skipped — and
                // this block was doing a full sort of the capability key set plus two
                // passes of `can()` over it each time, for a list that only changes when
                // the backend is re-handshaked. Keyed on `capabilities` itself (not on
                // `version`) because that object is the only input `can()` reads; a
                // version number that moved without the capability set changing produces
                // an identical list, so re-deriving it would be pure waste.
                val caps: Pair<List<String>, List<String>> = remember(version?.capabilities) {
                    val v = version
                    if (v == null) {
                        emptyList<String>() to emptyList<String>()
                    } else {
                        val names = v.capabilities.keys.sorted()
                        names.filter { v.can(it) } to names.filterNot { v.can(it) }
                    }
                }
                Section("This backend") {
                    Plate {
                        if (version == null) {
                            Text(
                                "No handshake yet.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = chrome.textMid,
                            )
                        } else {
                            version.server.takeIf { it.isNotBlank() }
                                ?.let { Field("Server", it, machine = true) }
                            Field("API", version.api.toString(), machine = true)
                            Gap(6)
                            Kicker("Capabilities")
                            Gap(6)
                            // Branch on capabilities, never on version numbers —
                            // and show the user the same list the app branches
                            // on, so "why is that button missing" has an answer
                            // here. `can()` is the same call the app makes.
                            val (on, off) = caps
                            if (on.isEmpty()) {
                                Text(
                                    "None reported.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = chrome.textMid,
                                )
                            } else {
                                FlowChips(on)
                            }
                            if (off.isNotEmpty()) {
                                Gap(10)
                                Kicker("Not on this backend")
                                Gap(6)
                                FlowChips(off, muted = true)
                            }
                        }
                    }
                }
            }

            item(key = "tail") { Gap(24) }
        }
    }
}

@Composable
private fun RushBanner(rush: JsonObject) {
    val chrome = LocalChrome.current
    val text = rush.str("text")
        ?: "Outside text raised the current tier."
    Plate(
        tone = chrome.badInk.copy(alpha = 0.10f),
        outline = chrome.badInk.copy(alpha = 0.40f),
    ) {
        Kicker("Tier raised", color = chrome.badInk)
        Gap(6)
        Text(text, style = MaterialTheme.typography.bodyLarge, color = chrome.badInk)
        rush.str("quote")?.let {
            Gap(8)
            // Quoted, because it is a quote — and never rendered as if Jarvis
            // said it.
            Text("“$it”", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        }
        rush.str("source")?.let {
            Gap(4)
            // Named, never quoted. A source string is attacker-controlled.
            Text("from $it", style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Gap(8)
        Text(
            "Nothing is approved from here. A latch is cleared where the scanner runs.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}

/**
 * The installed models, with a switch that ASKS.
 *
 * The owner's 2026-09-18 amendment to the standing rules: changing the local
 * model from the phone is allowed. The catalogue is not - there is no install
 * here, nothing downloads, and the list is whatever the desktop already
 * holds. `Use` raises an approval card (tier `ask` on the server), so the
 * change is decided the same way every other change is; `Roll back` is tier
 * `auto` and never waits, because returning to the previous model is the safe
 * direction.
 *
 * The cost is said on the plate rather than discovered: a swap unloads one
 * model and loads another, which the desktop's own topology doc measures at
 * six to ten seconds of silence. That is a scene change, not a route - fine
 * once per mode, wrong per request.
 */
@Composable
private fun ModelsPlate(
    models: ModelsInfo,
    busy: Boolean,
    canAct: Boolean,
    onSwitch: (String) -> Unit,
    onRollback: () -> Unit,
) {
    val chrome = LocalChrome.current
    val current = models.currentRef
    val entries = models.entries
    Plate {
        // Is the model actually ON the graphics card? Nothing else on the
        // phone says, and the only symptom of a spill is that everything got
        // slow - which reads as "Jarvis is slow", not "the model is on the CPU".
        val off = models.offload
        if (off != null && off.bad) {
            Text(
                off.note ?: "The model is not on the graphics card, so replies are slow.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
            )
            Gap(10)
        }
        if (entries.isEmpty()) {
            Text(
                "No models reported.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
            return@Plate
        }
        entries.forEachIndexed { i, entry ->
            if (i > 0) Rule()
            val isCurrent = entry.ref == current
            Row(
                Modifier.fillMaxWidth().padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        entry.ref,
                        style = com.jarvis.client.ui.theme.JarvisType.machine,
                        color = chrome.textHi,
                    )
                    val meta = listOfNotNull(
                        entry.family,
                        entry.sizeBytes?.let { bytes(it) },
                        if (entry.ref == models.previous && !isCurrent) "the previous model" else null,
                    )
                    if (meta.isNotEmpty()) {
                        Gap(2)
                        Text(
                            meta.joinToString(" · "),
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                    }
                }
                Spacer(Modifier.width(8.dp))
                if (isCurrent) {
                    Pill("Active", color = chrome.okInk)
                } else {
                    Quiet(
                        if (busy) "…" else "Use",
                        enabled = !busy && canAct,
                        onClick = { onSwitch(entry.ref) },
                    )
                }
            }
        }
        val previous = models.previous?.takeIf { it.isNotBlank() && it != current }
        if (previous != null) {
            Gap(6)
            Quiet(
                if (busy) "…" else "Roll back to $previous",
                color = chrome.textMid,
                enabled = !busy && canAct,
                onClick = onRollback,
            )
        }
        Gap(8)
        Text(
            "Use asks the desktop and raises a card here to approve, like any " +
                "other change. A switch takes six to ten seconds while one model " +
                "unloads and the next loads - fine once, not per question. " +
                "Installing new models stays on the desktop.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
    }
}

/** 4.7 GB, 812 MB. Enough precision for a list; a byte count is noise. */
private fun bytes(n: Long): String = when {
    n >= 1_000_000_000L -> "%.1f GB".format(n / 1_000_000_000.0)
    n >= 1_000_000L -> "%.0f MB".format(n / 1_000_000.0)
    else -> "$n B"
}

@Composable
private fun AttentionPlate(attention: Attention) {
    val chrome = LocalChrome.current
    Plate {
        val limit = attention.limit
        if (limit > 0) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${attention.remaining} of $limit spoken interruptions left today",
                    style = MaterialTheme.typography.bodyLarge,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
            }
            Gap(8)
            Meter(
                fraction = attention.remaining.toFloat() / limit,
                color = if (attention.remaining == 0) chrome.warnMark else chrome.okMark,
            )
        } else {
            Text(
                "No interruption budget reported.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        }
        if (attention.muted || attention.blockedBy != null) {
            Gap(10)
            Row {
                if (attention.muted) Pill("Muted until tomorrow", color = chrome.warnInk)
                attention.blockedBy?.let {
                    if (attention.muted) Spacer(Modifier.width(6.dp))
                    Pill("Blocked by $it", color = chrome.textMid)
                }
            }
        }
        if (attention.pending > 0) {
            Gap(10)
            Text(
                if (attention.pending == 1) {
                    "1 thing waiting to be told"
                } else {
                    "${attention.pending} things waiting to be told"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        }
        if (attention.banked) {
            Gap(6)
            Text(
                // A fact, not a mood. The reactor says the same thing by going
                // still, and neither should imply something is wrong.
                "Banked: they are waiting for a better moment, not being ignored.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}

@Composable
private fun JobPlate(job: JobRecord) {
    val chrome = LocalChrome.current
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                job.label.ifBlank { job.id },
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Pill(job.state.ifBlank { "running" })
        }
        job.progress?.let {
            Gap(10)
            Meter(it)
        }
        if (job.capabilities.isNotEmpty()) {
            Gap(10)
            // Frozen for the job's life. A job can never gain more while it
            // runs: approving something on Tuesday is not approving it on
            // Wednesday, and showing the frozen set is how that promise is
            // checkable rather than merely stated.
            Kicker("Approved with")
            Gap(6)
            FlowChips(job.capabilities)
        }
        if (job.private) {
            Gap(8)
            Text(
                "Private — the phone is not shown what this is working on.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}

/**
 * A section rendered from whatever the server sent.
 *
 * Scalars become rows, arrays become a count and their readable entries, and
 * anything nested one level deep is flattened with its parent's name. No field
 * is assumed to exist, so nothing here can be quietly wrong about a key.
 */
@Composable
private fun Probed(title: String, data: JsonObject?, blurb: String) {
    val chrome = LocalChrome.current
    // The expensive part of this composable, done once per payload instead of once
    // per recomposition. `flatten` walks the object and everything nested under it
    // (two levels), builds a growing list and re-`humanise`s every key — and five
    // of these sections are on screen at once. Because `BrainSnapshot` carries
    // JsonObject fields, Compose cannot mark this screen skippable, so before this
    // remember all five re-flattened on every single SSE event, which is the
    // steadiest source of them. Keyed on the JsonObject itself: JsonObject is a
    // Map, so `==` is a structural compare and a genuinely new payload — the only
    // thing that can change these rows — always misses the key and re-flattens.
    // Computed ABOVE the null branch on purpose, so the remember is never behind a
    // conditional return.
    val rows = remember(data) { data?.let { flatten(it) }.orEmpty() }
    Section(title) {
        Plate {
            if (data == null) {
                Text(
                    "Not available on this backend.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                Gap(4)
                Text(blurb, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                return@Plate
            }
            if (rows.isEmpty()) {
                Text(
                    "Nothing to report.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                return@Plate
            }
            rows.forEachIndexed { i, (label, value) ->
                if (i > 0) Rule()
                Field(label, value, machine = value.looksMachine())
            }
        }
    }
}

/**
 * The one section on this screen that answers back rather than only
 * reporting. `data` is `/api/memory/pending`'s own JSON — the SAME payload
 * `JarvisRuntime.refreshBrain()` already fetched for the generic [Probed]
 * view this replaces — read directly rather than through a typed model, for
 * the reason [JarvisApi.probe] gives: the contract names this route with no
 * field list, and a data class would mean inventing keys.
 *
 * One fact, one decision, same as [com.jarvis.client.ui.approval.ApprovalCard]
 * - no "keep all" here either, and `busyId` exists so a second tap on the
 * same row before the first decision lands cannot fire twice.
 */
@Composable
private fun MemoryQueue(
    data: JsonObject?,
    busyId: Long?,
    onKeep: (id: Long) -> Unit,
    onDiscard: (id: Long) -> Unit,
    sleepOffer: JsonObject?,
    sleepOfferBusy: Boolean,
    onSleepTimeAction: (enabled: Boolean?, remind: Boolean?) -> Unit,
    onDismissSleepOffer: () -> Unit,
) {
    val chrome = LocalChrome.current
    // Two allocating passes (a cast-filter and a new list) over the pending array,
    // previously redone on every recomposition of an unskippable screen — i.e. on
    // every server event, including the many that have nothing to do with memory.
    // Keyed on the raw payload so a real change to the queue still rebuilds it;
    // hoisted above the null branch so the remember is not behind a conditional
    // return.
    val items = remember(data) {
        (data?.get("pending") as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
    }
    Section("Memory awaiting review") {
        if (sleepOffer != null) {
            SleepOfferCard(
                offer = sleepOffer,
                busy = sleepOfferBusy,
                onEnable = { onSleepTimeAction(true, null) },
                onNotNow = onDismissSleepOffer,
                onStopAsking = { onSleepTimeAction(null, false) },
            )
            Gap(10)
        }
        Plate {
            if (data == null) {
                Text(
                    "Not available on this backend.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                Gap(4)
                Text("Proposed facts", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                return@Plate
            }
            if (items.isEmpty()) {
                Text(
                    "Nothing is waiting. Either Jarvis has not heard anything " +
                        "worth keeping, or learning is off.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                return@Plate
            }
            items.forEachIndexed { i, item ->
                if (i > 0) Rule()
                val id = item.str("id")?.toLongOrNull()
                MemoryProposalRow(
                    text = item.str("text") ?: "(no text)",
                    source = item.str("source"),
                    busy = id != null && id == busyId,
                    // A row with no readable id can be shown but not decided -
                    // the same "say what you can, act on what you know" rule
                    // as a section with no data at all.
                    onKeep = id?.let { { onKeep(it) } },
                    onDiscard = id?.let { { onDiscard(it) } },
                )
            }
        }
    }
}

/**
 * The daily overnight-tidy offer. `offer` is `setup.sleep_time_offer` from
 * `/api/memory/pending`, verbatim - the same object [MemoryQueue]'s caller
 * decided to keep showing, so this composable never reads staleness or
 * once-a-day tracking itself.
 */
@Composable
private fun SleepOfferCard(
    offer: JsonObject,
    busy: Boolean,
    onEnable: () -> Unit,
    onNotNow: () -> Unit,
    onStopAsking: () -> Unit,
) {
    val chrome = LocalChrome.current
    Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Text(
            offer.str("title") ?: "Let Jarvis tidy its memory overnight?",
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
        )
        offer.str("body")?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Gap(10)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Quiet(
                if (busy) "Enabling…" else "Enable",
                color = chrome.okInk,
                enabled = !busy,
                onClick = onEnable,
            )
            Quiet("Not now", color = chrome.textMid, enabled = !busy, onClick = onNotNow)
            Quiet(
                if (busy) "Working…" else "Stop asking",
                color = chrome.textLo,
                enabled = !busy,
                onClick = onStopAsking,
            )
        }
    }
}

@Composable
private fun MemoryProposalRow(
    text: String,
    source: String?,
    busy: Boolean,
    onKeep: (() -> Unit)?,
    onDiscard: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    Column {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        if (source != null) {
            Gap(2)
            Text("from $source", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Gap(6)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Quiet(
                if (busy) "Keeping…" else "Keep",
                color = chrome.okInk,
                enabled = !busy && onKeep != null,
                onClick = { onKeep?.invoke() },
            )
            Quiet(
                if (busy) "Discarding…" else "Discard",
                color = chrome.badInk,
                enabled = !busy && onDiscard != null,
                onClick = { onDiscard?.invoke() },
            )
        }
    }
}

@Composable
private fun FlowChips(items: Collection<String>, muted: Boolean = false) {
    val chrome = LocalChrome.current
    // A simple wrapping run. FlowRow would do it in one line but is still
    // experimental in this BOM, and an opt-in on a layout is not worth it.
    // `chunked` allocates the outer list plus one inner list per row, and this is
    // called once per capability list and once per running job — on a screen that
    // cannot skip recomposition, so it was rebuilding those lists on every server
    // event for chips whose text never moved. Keyed on the input collection, whose
    // `==` is a structural compare, so the chips still re-chunk the moment the set
    // of capabilities actually differs.
    val rows = remember(items) { items.chunked(3) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        rows.forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.forEach {
                    Pill(it, color = if (muted) chrome.textLo else chrome.textMid)
                }
            }
        }
    }
}

@Composable
fun TopBar(
    title: String,
    onBack: () -> Unit,
    trailing: (@Composable () -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Quiet("← Back", color = LocalAccent.current, onClick = onBack)
        Spacer(Modifier.width(4.dp))
        Text(
            title,
            style = MaterialTheme.typography.titleMedium,
            color = chrome.textHi,
            modifier = Modifier.weight(1f),
        )
        trailing?.invoke()
    }
}

// ------------------------------------------------------------- json ------

private fun JsonObject.str(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotBlank() }

private fun rushOf(contentRisk: JsonObject?): JsonObject? =
    contentRisk?.get("rush") as? JsonObject

/** Human-facing key: `last_verified_at` becomes "Last verified at". */
private fun humanise(key: String): String =
    key.replace('_', ' ').replace('-', ' ')
        .replaceFirstChar { it.uppercase() }

private fun flatten(obj: JsonObject, prefix: String = "", depth: Int = 0): List<Pair<String, String>> {
    val out = mutableListOf<Pair<String, String>>()
    for ((key, value) in obj) {
        val label = if (prefix.isEmpty()) humanise(key) else "$prefix · ${humanise(key)}"
        when (value) {
            is JsonPrimitive -> {
                if (value is JsonNull) continue
                out += label to value.content
            }
            is JsonObject -> if (depth < 2) out += flatten(value, label, depth + 1)
            is JsonArray -> {
                val scalars = value.mapNotNull { (it as? JsonPrimitive)?.content }
                out += if (scalars.size == value.size && scalars.isNotEmpty()) {
                    label to scalars.joinToString(", ")
                } else {
                    label to "${value.size}"
                }
            }
        }
    }
    return out
}

/** True for ids, hashes and paths — the strings a monospace face is for. */
private fun String.looksMachine(): Boolean =
    length > 6 && none { it == ' ' } && any { it.isDigit() || it == '/' || it == ':' || it == '-' }
