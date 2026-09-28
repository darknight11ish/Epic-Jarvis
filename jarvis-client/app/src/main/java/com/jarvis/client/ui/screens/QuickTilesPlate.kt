package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.jarvis.client.data.QuickTiles
import com.jarvis.client.data.TileAction
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Quick Settings tiles" (Settings; [QuickTiles], docs/JARVIS-API.md
 * section 81.2): what each of the three Jarvis tiles does, chosen from the
 * short safe list. Saved on this phone only - nothing here reaches the PC,
 * so, like Floating Jarvis above it, it never checks `canAct`. The tiles
 * themselves hold every action on a stale link.
 */
@Composable
internal fun QuickTilesSection(
    tiles: List<TileAction?>,
    onChange: (slot: Int, action: TileAction?) -> Unit,
) {
    val chrome = LocalChrome.current
    // "Nothing" first, then the safe list, three to a row so the words fit.
    val options: List<TileAction?> = listOf<TileAction?>(null) + TileAction.entries
    Section(QuickTiles.TITLE) {
        Plate {
            Text(QuickTiles.HINT, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            for (slot in 0 until QuickTiles.SLOTS) {
                val chosen = tiles.getOrNull(slot)
                Gap(12)
                Text(
                    "Jarvis tile ${slot + 1}",
                    style = MaterialTheme.typography.labelLarge,
                    color = chrome.textHi,
                )
                Gap(6)
                options.chunked(3).forEachIndexed { i, row ->
                    if (i > 0) Gap(6)
                    Choices(
                        options = row,
                        isSelected = { it == chosen },
                        label = { it?.choiceLabel ?: QuickTiles.NOTHING },
                        onPick = { onChange(slot, it) },
                    )
                }
            }
            Gap(12)
            Text(QuickTiles.SAFETY, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            Gap(6)
            Text(QuickTiles.LOCK_NOTE, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        }
    }
}
