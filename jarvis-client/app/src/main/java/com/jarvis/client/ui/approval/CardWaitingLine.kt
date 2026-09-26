package com.jarvis.client.ui.approval

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.CardWords
import com.jarvis.client.net.PendingItem
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * "Open the card" - one line on every screen but Home while an approval card
 * waits, with a link that goes to it on Home.
 *
 * Many buttons away from Home raise a card: a switch in Mind that loosens a
 * rule, the morning briefing's Set up, a voice setting, a model to install.
 * Only a few of those screens had a link to the card; the rest said "Approve
 * it on your PC or on this phone's Home screen" and left the owner to go and
 * find it, and a card could run out of time unseen (the creativity audit,
 * 2026-09-25, finding 5). One line for every screen means no button that
 * raises a card can be missed - including ones added later.
 *
 * The link DECIDES NOTHING: it opens Home on that card, where Deny and
 * Approve are (and the fingerprint, for a risky one). The line shows the
 * card's title only - the PC builds it from its own tables - never the
 * summary or the detail. The desktop's Settings and Brain have the same line
 * (card-link.js), with the same words ([CardWords]).
 */
@Composable
fun CardWaitingLine(
    pending: List<PendingItem>,
    onOpen: (id: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val waiting = CardWords.waiting(pending) ?: return
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.cardShape
    Column(
        modifier
            .fillMaxWidth()
            .clip(shape)
            .background(chrome.surface1)
            .border(1.dp, chrome.warnInk.copy(alpha = 0.55f), shape)
            .padding(horizontal = 12.dp, vertical = 8.dp)
            // Said once as it appears, politely - not on every recomposition.
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(CardWords.KICKER, style = MaterialTheme.typography.labelMedium, color = chrome.warnInk)
        Text(waiting.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        if (waiting.more.isNotEmpty()) {
            Text(waiting.more, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Quiet(
            "${CardWords.OPEN_CARD} →",
            color = chrome.warnInk,
            modifier = Modifier.padding(top = 2.dp),
            onClick = { onOpen(waiting.id) },
        )
    }
}
