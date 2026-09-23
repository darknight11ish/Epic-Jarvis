package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.FaceState
import com.jarvis.client.data.FaceTuning
import com.jarvis.client.face.Binding
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.Palette
import com.jarvis.client.face.Pattern
import com.jarvis.client.face.PatternKind
import com.jarvis.client.face.QualityTier
import com.jarvis.client.face.ResolvedBudget
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import kotlin.math.roundToInt

/**
 * The face editor: the reactor kit's controls for the face, in one dropdown
 * on the Appearance screen that starts closed.
 *
 * The owner asked for "all the settings" from the kit, and separately for the
 * Appearance screen to stay simple - so they are all here, and all behind one
 * switch. In the kit's own order: State, Pattern, Colour, then Quality,
 * Frame rate and All speeds, then Randomise and Reset. Auto adjust sits just
 * above Quality because it decides Quality and Frame rate; Battery saver
 * sits under them because it overrides all three.
 *
 * Two kinds of setting live here, and the last line says which is which:
 *  - Pattern and Colour edit the state colours - the same bindings the
 *    "State colours" list below shows and the desktop shares. There is no
 *    second colour system.
 *  - Everything else ([FaceTuning]) is this phone's own and never leaves it.
 *
 * Nothing here changes Jarvis's real state: State only picks what the preview
 * above shows, and which state Pattern and Colour are editing.
 */
@Composable
internal fun FaceEditor(
    open: Boolean,
    onOpenChange: (Boolean) -> Unit,
    previewState: FaceState,
    onPreviewState: (FaceState) -> Unit,
    bindings: Bindings,
    onEditBinding: (FaceState, Binding) -> Unit,
    tuning: FaceTuning,
    onTuningChange: (FaceTuning) -> Unit,
    /** What the face is running with right now: what Auto picked, or what battery saver forces. */
    live: ResolvedBudget,
    phoneBatterySaver: Boolean,
    desktopSyncs: Boolean,
    onRandomise: () -> Unit,
    onReset: () -> Unit,
    undoLine: @Composable () -> Unit,
) {
    val chrome = LocalChrome.current
    SwitchRow(
        title = "Face editor",
        detail = if (open) null else "Pattern, colour, quality, frame rate and speed.",
        checked = open,
        onChange = onOpenChange,
    )
    if (!open) return

    val saver = tuning.batterySaver || phoneBatterySaver
    val auto = tuning.autoAdjust
    val binding = bindings.of(previewState)
    val stateName = plainState(previewState)

    Gap(12)
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Setting(title = "State", caption = "Only changes the preview above, never Jarvis.") {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FaceState.entries.chunked(4).forEach { row ->
                    Choices(
                        options = row,
                        isSelected = { it == previewState },
                        label = { plainState(it) },
                        onPick = onPreviewState,
                    )
                }
            }
        }

        Setting(title = "Pattern for $stateName") {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Pattern.entries.chunked(3).forEach { row ->
                    Choices(
                        options = row,
                        isSelected = { it == binding.pattern },
                        label = { plainPattern(it) },
                        onPick = { picked ->
                            // As the kit does: the new pattern keeps the colour
                            // and starts from its own timing. Picking the one
                            // already chosen changes nothing, so it cannot wipe
                            // a tuned binding by accident.
                            if (picked != binding.pattern) {
                                onEditBinding(previewState, Binding(picked, binding.color))
                            }
                        },
                    )
                }
            }
        }

        Setting(
            title = "Colour for $stateName",
            caption = if (makesOwnColours(binding.pattern)) {
                "This pattern makes its own colours, so a colour here has no effect."
            } else {
                null
            },
        ) {
            PaletteGrid(
                selected = binding.color,
                onPick = { c -> onEditBinding(previewState, binding.copy(color = c)) },
            )
        }

        SwitchRow(
            title = "Auto adjust",
            detail = "Picks quality and frame rate for this phone, and steps down if the face runs slow.",
            checked = auto,
            onChange = { on ->
                // Turning Auto off keeps what it had picked, rather than
                // jumping to a quality this phone may not manage.
                onTuningChange(
                    if (on) {
                        tuning.copy(autoAdjust = true)
                    } else {
                        tuning.copy(autoAdjust = false, quality = if (live.governed) live.tier else tuning.quality)
                    },
                )
            },
            enabled = !saver,
        )

        Setting(
            title = "Quality",
            caption = when {
                saver -> null
                auto -> "Auto is using ${live.tier.label}. Picking one turns Auto adjust off."
                else -> "High matches the desktop kit. Low is easiest on the phone."
            },
        ) {
            Choices(
                options = QualityTier.entries,
                isSelected = {
                    when {
                        saver -> false
                        auto -> it == live.tier
                        else -> it == tuning.quality
                    }
                },
                label = { it.label },
                // Picking one is the kit's "an explicit choice is not
                // overridden": Auto adjust goes off, so it stays picked.
                onPick = { onTuningChange(tuning.copy(quality = it, autoAdjust = false)) },
                enabled = !saver,
            )
        }

        Setting(
            title = "Frame rate",
            caption = if (saver) {
                null
            } else {
                "This screen runs at ${live.panelHz.roundToInt()} Hz; the face draws up to ${live.fps} fps."
            },
        ) {
            Choices(
                options = FrameRateTarget.entries,
                isSelected = {
                    when {
                        saver -> false
                        auto -> it == FrameRateTarget.AUTO
                        else -> it == tuning.frameRate
                    }
                },
                label = { it.label },
                onPick = {
                    // Also turns Auto adjust off, keeping the quality it had
                    // picked (see the Auto adjust switch above).
                    onTuningChange(
                        tuning.copy(
                            frameRate = it,
                            autoAdjust = false,
                            quality = if (live.governed) live.tier else tuning.quality,
                        ),
                    )
                },
                enabled = !saver,
            )
        }

        Setting(title = "All speeds", caption = "How fast the face moves. Calm motion never goes above 1×.") {
            Choices(
                options = FaceTuning.SPEEDS,
                isSelected = { near(it, tuning.speed) },
                label = { speedLabel(it) },
                onPick = { onTuningChange(tuning.copy(speed = it)) },
            )
        }

        SwitchRow(
            title = "Battery saver",
            detail = if (phoneBatterySaver && !tuning.batterySaver) {
                "On while your phone's Battery Saver is on."
            } else {
                "Low detail, no glow, 30 fps, calm motion. Overrides the settings above."
            },
            checked = saver,
            onChange = { onTuningChange(tuning.copy(batterySaver = it)) },
            // Held on by the phone: switching it off here would do nothing.
            enabled = !(phoneBatterySaver && !tuning.batterySaver),
        )

        Column {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet("Randomise", onClick = onRandomise)
                Quiet("Reset", color = chrome.textMid, onClick = onReset)
            }
            undoLine()
            Gap(6)
            Text(
                if (desktopSyncs) {
                    "Pattern and colour are shared with your desktop. Everything else here stays on this phone."
                } else {
                    "Everything here stays on this phone for now."
                },
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
    }
}

/**
 * The kit's palette: ten families across, five steps down (deepest at the
 * top), as the kit lays it out. Each swatch is one choice, announced by name
 * and as selected or not.
 */
@Composable
private fun PaletteGrid(selected: Color?, onPick: (Color) -> Unit) {
    val shape = RoundedCornerShape(4.dp)
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        for (step in 1..5) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                for (family in Palette.families) {
                    val colour = Palette.byId["$family-$step"]
                    if (colour == null) {
                        // Never happens with the spec's palette; keeps the
                        // columns lined up if a colour were ever missing.
                        Box(Modifier.weight(1f))
                    } else {
                        Swatch(colour, family, step, colour == selected, shape, onPick)
                    }
                }
            }
        }
    }
}

/** One palette colour: a square, ringed when chosen, named for TalkBack. */
@Composable
private fun RowScope.Swatch(
    colour: Color,
    family: String,
    step: Int,
    isSelected: Boolean,
    shape: RoundedCornerShape,
    onPick: (Color) -> Unit,
) {
    val chrome = LocalChrome.current
    val name = family.replaceFirstChar { it.uppercase() } + " $step"
    Box(
        Modifier
            .weight(1f)
            .aspectRatio(1f)
            .semantics {
                contentDescription = name
                selected = isSelected
            }
            .clip(shape)
            .background(colour)
            .then(
                if (isSelected) {
                    Modifier
                        .border(2.dp, chrome.textHi, shape)
                        .padding(2.dp)
                        .border(1.dp, chrome.surface0, shape)
                } else {
                    Modifier
                },
            )
            .pressable(role = Role.RadioButton, onClick = { onPick(colour) }),
    )
}

/**
 * Patterns whose colour does not come from the bound colour: the two hue
 * sweeps and Warms up make their own, Colour steps walks its own list, and
 * Flicker walks a family (see `resolveRaw`).
 */
private fun makesOwnColours(p: Pattern): Boolean = when (p.kind) {
    PatternKind.HUE_SWEEP, PatternKind.TEMPERATURE, PatternKind.STEP_CYCLE, PatternKind.FLICKER -> true
    else -> false
}

private fun plainState(s: FaceState): String = s.name.lowercase().replaceFirstChar { it.uppercase() }

private fun speedLabel(v: Float): String = when (v) {
    0.25f -> "¼×"
    0.5f -> "½×"
    0.75f -> "¾×"
    1f -> "1×"
    1.5f -> "1½×"
    2f -> "2×"
    else -> "${(v * 100).roundToInt() / 100f}×"
}
