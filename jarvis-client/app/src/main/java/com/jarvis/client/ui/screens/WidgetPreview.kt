package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.net.JarvisWidgets
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome

/**
 * The DRAWN preview of a described widget, and the three look pickers that go
 * under it (Brain -> Widgets, the owner's request of 2026-11-14: "see and
 * choose a widget's look before adding it").
 *
 * It is a picture, not a widget: nothing here can be tapped, and it adds
 * nothing. It draws the SAME thing the home-screen widget draws
 * (`widget/JarvisBoardWidget.kt`) - the same blocks, the same look, the same
 * arrangement - because it asks the same pure rule, [JarvisWidgets.boardOf],
 * for the arrangement instead of arranging anything itself. That is the point
 * of reusing it: a preview that could disagree with the real widget about
 * which block is big, or in what order the rest go, would be worse than no
 * preview.
 *
 * The look is drawn exactly as the widget draws it: the contrast gives the
 * base colours, the accent the accent colour, and the shade gives the ALPHA on
 * the card and on the panels - and on nothing else. Every word is fully
 * opaque (WIDGET-LOOK-SPEC section 3, rule 3).
 *
 * The literal hex parse lives in [JarvisWidgets.argb], pure Kotlin, so the JVM
 * tests hold the colour this preview draws to the PC's closed lists.
 */
@Composable
internal fun WidgetPreview(
    view: JarvisWidgets.View,
    look: JarvisWidgets.Look,
    modifier: Modifier = Modifier,
) {
    // ONE arrangement rule, shared with the home-screen widget.
    val board = remember(view) { JarvisWidgets.boardOf(view) }
    val colours = PreviewColours(look)
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(colours.background)
            .padding(12.dp),
    ) {
        board.big?.let { BigNumber(it, colours) }
        for (b in board.blocks) {
            PreviewPart(b, colours)
            Spacer(Modifier.height(3.dp))
        }
        // Two to a row, as the widget's own board puts them. Drawn, never
        // tappable.
        for (pair in board.buttons.chunked(2)) {
            Spacer(Modifier.height(4.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                for (b in pair) {
                    Box(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(10.dp))
                            .background(colours.surface)
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            b.label,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            style = TextStyle(
                                color = colours.accentColor,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                            ),
                        )
                    }
                }
            }
        }
    }
}

/** "big": the number at 28sp, as the widget draws it - the eye lands on a count. */
@Composable
private fun BigNumber(b: JarvisWidgets.Block.Count, c: PreviewColours) {
    Column(Modifier.fillMaxWidth()) {
        Text(b.label, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
        if (b.value.isNotEmpty()) {
            Text(
                b.value, maxLines = 1,
                style = TextStyle(color = c.accentColor, fontSize = 28.sp, fontWeight = FontWeight.Bold),
            )
        }
        if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
    }
}

/** One block, drawn the one way the widget draws it - whatever the layout. */
@Composable
private fun PreviewPart(b: JarvisWidgets.Block, c: PreviewColours) {
    when (b) {
        is JarvisWidgets.Block.Title -> Text(
            b.text, maxLines = 1, overflow = TextOverflow.Ellipsis,
            style = TextStyle(color = c.textHi, fontSize = 14.sp, fontWeight = FontWeight.Bold),
        )
        is JarvisWidgets.Block.Count -> {
            Row(Modifier.fillMaxWidth()) {
                Text(b.label, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
                Spacer(Modifier.weight(1f))
                if (b.value.isNotEmpty()) {
                    Text(
                        b.value,
                        style = TextStyle(color = c.accentColor, fontSize = 13.sp, fontWeight = FontWeight.Bold),
                    )
                }
            }
            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
        }
        is JarvisWidgets.Block.Items -> {
            Text(b.label, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
            for ((words, whenWords) in b.items) {
                Text(
                    if (whenWords.isEmpty()) words else "$whenWords  $words",
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                    style = TextStyle(color = c.textHi, fontSize = 11.sp),
                )
            }
            if (b.more > 0) Text("+${b.more} more", style = TextStyle(color = c.accentColor, fontSize = 11.sp))
            if (b.items.isEmpty() && b.note.isEmpty() && b.empty.isNotEmpty()) {
                Text(b.empty, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
            }
            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
        }
        is JarvisWidgets.Block.Progress -> {
            Row(Modifier.fillMaxWidth()) {
                Text(b.label, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
                Spacer(Modifier.weight(1f))
                if (b.value.isNotEmpty()) {
                    Text(b.value, maxLines = 1, style = TextStyle(color = c.textHi, fontSize = 11.sp))
                }
            }
            // The widget's own 4dp bar, drawn rather than an animated Material
            // indicator: a preview must not move.
            Box(
                Modifier.fillMaxWidth().height(4.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(c.surface),
            ) {
                Box(
                    Modifier.fillMaxWidth(b.fraction.toFloat().coerceIn(0f, 1f))
                        .height(4.dp)
                        .background(c.accentColor),
                )
            }
            if (b.note.isNotEmpty()) Text(b.note, maxLines = 1, overflow = TextOverflow.Ellipsis, style = muted(c))
        }
        is JarvisWidgets.Block.Button -> Unit
    }
}

private fun muted(c: PreviewColours) = TextStyle(color = c.textMuted, fontSize = 11.sp)

/**
 * The three pickers under a preview, built only from the closed lists the PC
 * uses ([JarvisWidgets.ACCENTS], [JarvisWidgets.SHADES],
 * [JarvisWidgets.CONTRASTS]) - so the app can never choose a value the PC
 * would refuse. Changing one calls [onPick] with the whole new look, and the
 * preview above redraws at once because it draws from that value.
 */
@Composable
internal fun LookPickers(
    look: JarvisWidgets.Look,
    enabled: Boolean,
    onPick: (JarvisWidgets.Look) -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Text(JarvisWidgets.LOOK_ACCENT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        AccentPicker(look.accent, enabled) { onPick(look.copy(accent = it)) }
        Spacer(Modifier.height(6.dp))
        Text(JarvisWidgets.LOOK_SHADE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Choices(
            options = JarvisWidgets.SHADES,
            isSelected = { it.id == look.shade },
            label = { it.label },
            enabled = enabled,
            onPick = { onPick(look.copy(shade = it.id)) },
        )
        Spacer(Modifier.height(6.dp))
        Text(JarvisWidgets.LOOK_CONTRAST, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Choices(
            options = JarvisWidgets.CONTRASTS,
            isSelected = { it.id == look.contrast },
            label = { it.label },
            enabled = enabled,
            onPick = { onPick(look.copy(contrast = it.id)) },
        )
    }
}

/**
 * The eight accents as tappable swatches. A dot AND the accent's name, so the
 * colour is never the only signal; TalkBack hears "Accent colour: Violet,
 * radio button, selected" ([contentDescription] + `selected`), because the dot
 * alone would say nothing.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AccentPicker(selected: String, enabled: Boolean, onPick: (String) -> Unit) {
    val chrome = LocalChrome.current
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        for (a in JarvisWidgets.ACCENTS) {
            val chosen = a.id == selected
            Row(
                Modifier
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .pressable(enabled = enabled, role = Role.RadioButton, onClick = { onPick(a.id) })
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .semantics(mergeDescendants = true) {
                        contentDescription = "${JarvisWidgets.LOOK_ACCENT}: ${a.label}"
                        this.selected = chosen
                    },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Dot(Color(JarvisWidgets.argb(a.color)), size = 14)
                Text(
                    if (chosen) "• ${a.label}" else a.label,
                    style = MaterialTheme.typography.labelMedium,
                    color = if (chosen) chrome.textHi else chrome.textMid,
                )
            }
        }
    }
}

/**
 * A preview's colours, resolved exactly as the home-screen widget's
 * `BoardPalette` resolves them: the shade's two alphas go on the card and on
 * the panels, and never on any word.
 */
private class PreviewColours(look: JarvisWidgets.Look) {
    private val contrast = JarvisWidgets.contrastOf(look.contrast)
    private val shade = JarvisWidgets.shadeOf(look.shade)
    private val accent = JarvisWidgets.accentOf(look.accent)

    val background = Color(JarvisWidgets.argb(contrast.bg, shade.alpha))
    val surface = Color(JarvisWidgets.argb(contrast.surface, shade.surfaceAlpha))
    val textHi = Color(JarvisWidgets.argb(contrast.textHi))
    val textMuted = Color(JarvisWidgets.argb(contrast.textMuted))
    val accentColor = Color(JarvisWidgets.argb(accent.color))
}
