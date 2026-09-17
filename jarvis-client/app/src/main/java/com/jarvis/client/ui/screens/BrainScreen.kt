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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.BrainSnapshot
import com.jarvis.client.LinkState
import com.jarvis.client.net.Attention
import com.jarvis.client.net.JobRecord
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
    /** What a Keep/Discard send failed with, e.g. not connected. Null hides it. */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
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
                            val names = version.capabilities.keys.sorted()
                            val on = names.filter { version.can(it) }
                            val off = names.filterNot { version.can(it) }
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
            val rows = flatten(data)
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
) {
    val chrome = LocalChrome.current
    Section("Memory awaiting review") {
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
            val items = (data["pending"] as? JsonArray).orEmpty()
                .mapNotNull { it as? JsonObject }
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
    val rows = items.chunked(3)
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
