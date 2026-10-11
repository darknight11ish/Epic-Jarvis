package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ContentRisk
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.ageText
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Content risk" - the desktop's read-only Trust panel, on the phone
 * (`brain.html`:901, `brain.js`'s `renderContentRisk`; [ContentRisk] holds
 * every word and every decision).
 *
 * WHY IT LIVES ON "PAST APPROVALS". This is the phone's own read-only record of
 * what the gate did, which is the family the desktop's Content risk card
 * belongs to - and the one screen on the phone that already hides its list
 * under "Hide memory lists and chat history" with a Show that asks for the
 * fingerprint or PIN ([HiddenSection]). Its natural home is the Brain's Trust
 * area beside the rush banner, and it is a self-contained plate for exactly
 * that reason: when `BrainScreen.kt` is next free, moving it there is one line
 * in that file and nothing here.
 *
 * The desktop puts the rush latch first on every view "because it changes how
 * everything below should be read"; this screen follows that rule and draws the
 * same panel first, before the past approvals themselves.
 *
 * READ-ONLY, ALWAYS. There is no button that clears a latch and none that
 * approves a pinned text - the card's own note says so - and the only control
 * here is Retry, which reads again.
 *
 * WHILE HIDDEN, NOTHING IS EVEN READ: the same rule [ApprovalsScreen] follows
 * for its own list, so a hidden panel cannot leave a copy of the flagged text
 * in memory behind the hidden line.
 *
 * @param hidden "Hide memory lists and chat history" is on.
 * @param busy a fingerprint or PIN check for Show is up.
 * @param onShow asks for that check, lifted from where the screen already does it.
 */
@Composable
internal fun ContentRiskSection(
    hidden: Boolean,
    busy: Boolean = false,
    onShow: () -> Unit = {},
) {
    val chrome = LocalChrome.current
    val brain by JarvisRuntime.brain.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var reading by remember { mutableStateOf(false) }

    // The one read. It runs when the section appears and again on Retry - and
    // never while hidden, so the read itself respects the setting.
    LaunchedEffect(hidden, reads) {
        if (!hidden) {
            reading = true
            try {
                JarvisRuntime.refreshContentRisk()
            } finally {
                reading = false
            }
        }
    }

    // Hidden wins over everything, and it is decided in ContentRisk.body so the
    // same decision is what the tests hold: nothing of the list is composed.
    when (val body = ContentRisk.body(brain.contentRisk, brain.contentRiskRead, hidden)) {
        ContentRisk.Body.Hidden -> HiddenSection(ContentRisk.TITLE, busy = busy, onShow = onShow)

        ContentRisk.Body.Reading -> Section(ContentRisk.TITLE) {
            Plate {
                Text(ContentRisk.READING, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            }
        }

        ContentRisk.Body.NotHere -> Section(ContentRisk.TITLE) {
            Plate {
                Text(ContentRisk.NOT_HERE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }

        is ContentRisk.Body.Failed -> Section(ContentRisk.TITLE) {
            Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
                Text(
                    ContentRisk.failed(body.reason),
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.warnInk,
                )
                Gap(6)
                // Reads again; clears nothing. The stale list is deliberately
                // not drawn under it: an old list is not the answer to "what is
                // pinned now", and the panel is a record of what IS.
                Quiet(
                    if (reading) "Retrying…" else "Retry",
                    enabled = !reading,
                    onClick = { reads += 1 },
                )
            }
        }

        is ContentRisk.Body.Ready -> Section(ContentRisk.TITLE) {
            Plate {
                Text(ContentRisk.NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Gap(8)
                RushLines(body)
                Gap(10)
                Text(
                    ContentRisk.PINNED_HEADING,
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi,
                    modifier = Modifier.semantics { heading() },
                )
                // The empty case says so in words (ContentRisk.pinnedSummary):
                // a heading over nothing reads as a panel that failed to load.
                ContentRisk.pinnedSummary(body.pins)?.let {
                    Gap(4)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                val now = rememberTickingNow(body.pins)
                body.pins.forEach { pin ->
                    Gap(8)
                    Column(Modifier.fillMaxWidth()) {
                        Text(pin.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        val line = ContentRisk.pinLine(pin)
                        if (line.isNotBlank()) {
                            Text(line, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        }
                        if (pin.atMs > 0L) {
                            Text(
                                "Approved ${ageText(now - pin.atMs)}",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * The latch, in the desktop's own words: its sentence, the attacker's words
 * quoted (never rendered as if Jarvis said them), who it came from, and the
 * line that says there is deliberately no control here.
 */
@Composable
private fun RushLines(body: ContentRisk.Body.Ready) {
    val chrome = LocalChrome.current
    val rush = body.rush
    Text(
        rush?.text ?: ContentRisk.RUSH_OFF,
        style = MaterialTheme.typography.bodyLarge,
        color = if (rush != null) chrome.badInk else chrome.textHi,
    )
    if (rush == null) return
    rush.phrase?.let {
        Gap(6)
        // Quoted, because it is a quote.
        Text("“$it”", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
    }
    ContentRisk.rushSourceLine(rush)?.let {
        Gap(4)
        // Named, never quoted: a source string is attacker-controlled.
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
    }
    Gap(6)
    Row(Modifier.fillMaxWidth()) {
        Text(
            ContentRisk.RUSH_TAIL,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}
