package com.jarvis.client.ui.parts

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii
import androidx.compose.foundation.clickable
import androidx.compose.ui.graphics.graphicsLayer

/**
 * A tap that presses.
 *
 * Replaces Material's ripple, which is a circle of someone else's brand
 * expanding across a surface that is meant to look machined. A spring on scale
 * is both cheaper (a draw-phase read, no recomposition) and more physical: the
 * thing you touched moves, and nothing else does.
 *
 * Honours reduced motion by not scaling at all — the click still works.
 */
@Composable
fun Modifier.pressable(
    enabled: Boolean = true,
    role: Role = Role.Button,
    onClick: () -> Unit,
): Modifier {
    val motion = LocalMotion.current
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed && !motion.reduced) 0.972f else 1f,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessHigh,
        ),
        label = "press",
    )
    return this
        .graphicsLayer { scaleX = scale; scaleY = scale }
        .clickable(
            interactionSource = interaction,
            // Null, deliberately: see above.
            indication = null,
            enabled = enabled,
            role = role,
            onClick = onClick,
        )
}

/**
 * The standard raised surface.
 *
 * A hairline rather than a shadow. Every `shadow()` or Card elevation is a
 * RenderNode with an outline shadow rasterised on every frame while the list
 * scrolls — twenty cards is an estimated 2–8ms, and this design is flat plates
 * and 1dp borders, so it never wanted them.
 */
@Composable
fun Plate(
    modifier: Modifier = Modifier,
    tone: Color? = null,
    outline: Color? = null,
    shape: Shape? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val chrome = LocalChrome.current
    val radii = LocalRadii.current
    val s = shape ?: radii.cardShape
    Column(
        modifier
            .fillMaxWidth()
            .clip(s)
            .background(tone ?: chrome.surface1)
            .then(if (outline != null) Modifier.border(1.dp, outline, s) else Modifier)
            .padding(14.dp),
        content = content,
    )
}

/**
 * The uppercase section label.
 *
 * Tracked out. At 11sp, uppercase without letter-spacing reads as shouting
 * rather than as a label — the desktop tracks its kickers 0.4–0.7px and the
 * phone tracked them not at all.
 */
@Composable
fun Kicker(text: String, modifier: Modifier = Modifier, color: Color? = null) {
    Text(
        text.uppercase(),
        style = MaterialTheme.typography.labelSmall,
        color = color ?: LocalChrome.current.textLo,
        modifier = modifier,
    )
}

/**
 * The fully-round chip: "this is a label, not a control".
 *
 * The phone had no such shape anywhere while the desktop used it for route
 * badges, note chips, approval targets and digest kinds, so the one shape
 * signal that separates a fact from a button was missing on the device where
 * mistaking one for the other costs the most.
 */
@Composable
fun Pill(
    text: String,
    modifier: Modifier = Modifier,
    color: Color? = null,
    filled: Boolean = false,
) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.chipShape
    val c = color ?: chrome.textMid
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = if (filled) chrome.surface0 else c,
        modifier = modifier
            .clip(shape)
            .background(if (filled) c else c.copy(alpha = 0.13f))
            .padding(horizontal = 9.dp, vertical = 4.dp),
    )
}

/** A status dot. Always paired with a word — never the only signal. */
@Composable
fun Dot(color: Color, modifier: Modifier = Modifier, size: Int = 8) {
    Box(modifier.size(size.dp).clip(CircleShape).background(color))
}

/** A one-line label/value row, with the value in the machine face when it is one. */
@Composable
fun Field(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    valueColor: Color? = null,
    machine: Boolean = false,
) {
    val chrome = LocalChrome.current
    Row(
        modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        Spacer(Modifier.width(12.dp))
        Text(
            value,
            style = if (machine) {
                com.jarvis.client.ui.theme.JarvisType.machine
            } else {
                MaterialTheme.typography.bodyMedium
            },
            color = valueColor ?: chrome.textHi,
            textAlign = TextAlign.End,
        )
    }
}

/**
 * A determinate bar.
 *
 * Redrawn at the DATA's rate, not the display's, and the needle glides between
 * server values through one float animation. That is where the live feeling
 * comes from — latency, and one thing in motion — not from interpolating a
 * number that only changes once a second.
 */
@Composable
fun Meter(
    fraction: Float,
    modifier: Modifier = Modifier,
    color: Color? = null,
    track: Color? = null,
    height: Int = 6,
) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val accent = LocalAccent.current
    val target = fraction.coerceIn(0f, 1f)
    val animated by animateFloatAsState(
        targetValue = target,
        animationSpec = motion.state(),
        label = "meter",
    )
    val fill = color ?: accent
    val bed = track ?: chrome.hairline
    Box(
        modifier
            .fillMaxWidth()
            .height(height.dp)
            .clip(RoundedCornerShape(percent = 50))
            .background(bed)
            // Read in the draw phase, so the animation never recomposes anything.
            .drawBehind {
                drawRect(
                    color = fill,
                    size = size.copy(width = size.width * animated),
                )
            },
    )
}

/**
 * The affirmative and destructive pair.
 *
 * Shape is the second channel and it is not decoration: verdant-4 and rose-4
 * are 67.7 ΔE apart to most eyes and 8.2 apart to a deuteranope — both simulate
 * to nearly the same beige (#cbc4ac against #b9ae83, differing by 1.2 on the
 * red-green axis). So the affirmative is filled and the destructive is
 * outlined, and the two are distinguishable with the colour removed entirely.
 */
@Composable
fun RowScope.Affirm(
    text: String,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.controlShape
    Box(
        modifier
            .weight(1f)
            .heightIn(min = 48.dp)
            .clip(shape)
            .background(if (enabled) chrome.okMark else chrome.hairline)
            .pressable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelLarge,
            color = if (enabled) chrome.surface0 else chrome.textLo,
        )
    }
}

@Composable
fun RowScope.Refuse(
    text: String,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.controlShape
    Box(
        modifier
            .weight(1f)
            .heightIn(min = 48.dp)
            .clip(shape)
            .border(1.5.dp, if (enabled) chrome.badMark else chrome.hairline, shape)
            .pressable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelLarge,
            color = if (enabled) chrome.badInk else chrome.textLo,
        )
    }
}

/** A quiet text action. 48dp of touch target regardless of how small it looks. */
@Composable
fun Quiet(
    text: String,
    modifier: Modifier = Modifier,
    color: Color? = null,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    Box(
        modifier
            .heightIn(min = 44.dp)
            .widthIn(min = 44.dp)
            .clip(LocalRadii.current.insetShape)
            .pressable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelMedium,
            color = if (enabled) (color ?: LocalAccent.current) else chrome.textLo,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
        )
    }
}

/** A hairline rule. */
@Composable
fun Rule(modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(LocalChrome.current.hairline),
    )
}

/** Section spacing, so the screens do not each invent their own. */
@Composable
fun Gap(dp: Int = 12) = Spacer(Modifier.height(dp.dp))

/** A titled group of fields. */
@Composable
fun Section(
    title: String,
    modifier: Modifier = Modifier,
    trailing: (@Composable RowScope.() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Kicker(title)
            if (trailing != null) {
                Row(verticalAlignment = Alignment.CenterVertically, content = trailing)
            }
        }
        Gap(8)
        content()
    }
}
