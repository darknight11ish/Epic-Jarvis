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
import com.jarvis.client.LinkState
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii
import androidx.compose.foundation.clickable
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LocalTextStyle
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation

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
    // A card colour equal to the background draws no visible edge from tone
    // alone - true of Void and true of Contrast, whose own doc comment
    // already promises "depth comes from borders rather than tone" without
    // anything here ever supplying one. Every `Plate` on those two themes had
    // no edge at all unless its call site happened to pass `outline`, which
    // most do not. This activates only where tone genuinely cannot show a
    // boundary; an explicit `outline` from the caller always wins.
    val flat = chrome.surface1 == chrome.surface0
    val effectiveOutline = outline ?: if (flat) chrome.hairlineStrong else null
    Column(
        modifier
            .fillMaxWidth()
            .clip(s)
            .background(tone ?: chrome.surface1)
            .then(
                if (effectiveOutline != null) {
                    Modifier.border(1.dp, effectiveOutline, s)
                } else {
                    Modifier
                },
            )
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

/**
 * Whether what is on the screen below can be trusted, said in words.
 *
 * Lifted out of BrainScreen, where it was private and therefore used on one
 * screen out of five. Rule 4 blocks *acting* on a stale stream; it does not
 * stop a screen showing what it last knew - but a screen that shows last-known
 * data and does not say so is the one thing that rule cannot tolerate, because
 * the owner cannot tell "nothing is waiting" from "I stopped being told".
 */
@Composable
fun Freshness(link: LinkState, stale: Boolean, fetchedAtMs: Long = 1L) {
    val chrome = LocalChrome.current
    val bad = stale || link != LinkState.CONNECTED
    Row(verticalAlignment = Alignment.CenterVertically) {
        Dot(if (bad) chrome.warnMark else chrome.okMark)
        Spacer(Modifier.width(10.dp))
        Text(
            when {
                link != LinkState.CONNECTED -> "Not connected. Everything below is last known."
                stale -> "The stream is stale. Everything below is last known."
                fetchedAtMs == 0L -> "Reading…"
                else -> "Live."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = if (bad) chrome.warnInk else chrome.textMid,
        )
    }
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
            .heightIn(min = 48.dp)
            .widthIn(min = 48.dp)
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

/**
 * The boxed, full-width action: Connect, Start link, Allow notifications.
 *
 * Every button on Pairing and Checks used to be a stock Material `Button` -
 * its own ripple, a 40dp default minimum, colours from `ButtonDefaults`
 * reaching outside this file's tokens entirely. It was never actually
 * "primary" in a fixed sense across those two screens: the original code
 * painted six different buttons on the same plate background with six
 * different text tints, so [color] says which one this is rather than the
 * component insisting on the accent. Same flat-plate shape as [Plate], same
 * spring-press as every other control here, sized to the 48dp touch minimum.
 */
@Composable
fun Primary(
    text: String,
    modifier: Modifier = Modifier,
    color: Color? = null,
    enabled: Boolean = true,
    /** Shows a spinner instead of the label. The click target stays put. */
    busy: Boolean = false,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.controlShape
    val tint = color ?: accent
    Box(
        modifier
            .heightIn(min = 48.dp)
            .clip(shape)
            .background(chrome.surface1)
            .pressable(enabled = enabled && !busy, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (busy) {
            CircularProgressIndicator(
                strokeWidth = 2.dp,
                color = tint,
                modifier = Modifier.size(18.dp),
            )
        } else {
            Text(
                text,
                style = MaterialTheme.typography.labelLarge,
                color = if (enabled) tint else chrome.textLo,
            )
        }
    }
}

/**
 * A flat text field: `BasicTextField` in a `surface2` box, the same shape
 * the composer already uses and the same reasoning that composer's own
 * comment gives - the Material text field brings its own container, its own
 * 56dp minimum, its own floating-label animation and its own notched
 * outline, none of which belong in a design made of flat plates and
 * hairlines. Pairing was the one screen still paying for all four.
 */
@Composable
fun TextInput(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    label: String? = null,
    placeholder: String? = null,
    supportingText: String? = null,
    supportingColor: Color? = null,
    /** Masks the value and disables suggestions - for a token, never for prose. */
    password: Boolean = false,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    Column(modifier.fillMaxWidth()) {
        if (label != null) {
            Kicker(label)
            Gap(6)
        }
        Box(
            Modifier
                .fillMaxWidth()
                .clip(radii.controlShape)
                .background(chrome.surface2)
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            if (value.isEmpty() && placeholder != null) {
                Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = chrome.textLo)
            }
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                textStyle = LocalTextStyle.current.merge(
                    MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                ),
                cursorBrush = SolidColor(accent),
                visualTransformation = if (password) {
                    PasswordVisualTransformation()
                } else {
                    VisualTransformation.None
                },
                keyboardOptions = keyboardOptions,
                keyboardActions = keyboardActions,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (supportingText != null) {
            Gap(4)
            Text(
                supportingText,
                style = MaterialTheme.typography.labelSmall,
                color = supportingColor ?: chrome.textLo,
            )
        }
    }
}

/**
 * A dismissible warning line: what went wrong, or what the desktop said no to.
 *
 * Lifted out of HomeScreen, where it was private and therefore used on one
 * screen out of five — the same gap [Freshness] closed for staleness. Every
 * other screen either had nowhere to put `JarvisRuntime.notice` at all
 * (Appearance's own comment used to say the store "refuses the change
 * anyway - the notice explains it in words instead", except nothing on that
 * screen rendered one) or reinvented it.
 */
@Composable
fun Notice(text: String, onDismiss: () -> Unit) {
    val chrome = LocalChrome.current
    Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet("Dismiss", onClick = onDismiss)
        }
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
