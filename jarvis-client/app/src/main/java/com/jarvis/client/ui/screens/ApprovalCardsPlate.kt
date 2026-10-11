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
import com.jarvis.client.net.CardSummary
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Approval cards" - how much of an approval card is shown at first.
 *
 * THE OWNER'S REQUEST (their own words, 2026-10-09): "for approval cards, there
 * should be a more simple summary, with an explain more button that expands the
 * approval card total word length and explains the details more. and approval
 * card preferences such as this should be changeable in the settings"
 *
 * Two choices, both cosmetic:
 *
 *  * "Start short" (the DEFAULT): a card shows one short line - "Jarvis wants to
 *    send the email shown." - and an "Explain more" button opens the whole card,
 *    which is everything a person is agreeing to: the exact line or value being
 *    changed, why it matters, whether Windows Hello is asked for, and what
 *    saying no does.
 *  * "Always show everything": every card is drawn open, as cards were before,
 *    with its whole text and no control.
 *
 * WHERE IT LIVES. On this phone: **Settings, the "Approval cards" row, right
 * under "Appearance"** - the neighbouring display preferences, because what it
 * changes is how much of a card is drawn. Its own row in the jump list, so
 * "Jump to: Approval cards" and a search for "approval" both find it.
 *
 * THE VALUE IS THE PC'S, NOT THIS PHONE'S. It is kept in card-prefs.json in the
 * Jarvis settings folder, beside appearance.json and animal.json, and read over
 * `GET /api/card-prefs` (backend/jarvis_card_summary.py) - so the desktop's own
 * switch and this row are the same setting. Cosmetic, so it changes at once with
 * no approval card, both ways, from either app or by asking Jarvis.
 */
@Composable
internal fun ApprovalCardsSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var panel by remember { mutableStateOf<CardSummary.View?>(null) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.cardPrefsRead()) {
            is ApiResult.Ok -> {
                panel = CardSummary.parse(r.value)
                readError = null
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    Section(CardSummary.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(
                "Cards that ask for your OK. This only changes how much of a card is shown at " +
                    "first - the same card, the same words underneath, the same buttons.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            val p = panel
            when {
                p == null && readError != null -> Text(
                    "Couldn't read it: ${readError.orEmpty()}",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                p == null -> Text(
                    "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                else -> {
                    p.choices.forEach { choice ->
                        Gap(6)
                        val chosen = choice.id == p.mode
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // "(in use)" as well as the colour: never by colour alone.
                            Text(
                                if (chosen) "${choice.label} (in use)" else choice.label,
                                style = MaterialTheme.typography.titleSmall,
                                color = if (chosen) chrome.okInk else chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            if (!chosen) {
                                Quiet(
                                    "Use this",
                                    // Both directions are at once and neither is
                                    // held: cosmetic, so no card, and no reason
                                    // to wait for a fresh link to make a card
                                    // easier to read.
                                    enabled = !busy,
                                    onClick = {
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                said = JarvisRuntime.setCardMode(choice.id)
                                            } finally {
                                                busy = false
                                                reads += 1
                                            }
                                        }
                                    },
                                )
                            }
                        }
                        Text(
                            choice.detail,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                    }
                    Gap(6)
                    // What the PC really holds, in its own words: a real choice,
                    // or the default in use because nothing was saved.
                    Text(
                        if (p.stored) {
                            "Kept on your PC, and the same setting on your desktop."
                        } else {
                            "Nothing chosen yet, so cards start short. Kept on your PC, and the " +
                                "same setting on your desktop."
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }
            said?.let {
                Gap(4)
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }
}
