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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
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
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LocalTextStyle
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import com.jarvis.client.ui.theme.LocalPlateEdges
import com.jarvis.client.ui.theme.LocalSpacing
import com.jarvis.client.ui.theme.PlateEdges
import com.jarvis.client.ui.theme.contrastRatio
import androidx.compose.ui.graphics.compositeOver

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
    val edges = LocalPlateEdges.current
    val s = shape ?: radii.cardShape
    // The 1dp border the design always described ("flat plates and 1dp
    // borders") used to be drawn only where surface1 equals surface0, which
    // is High Contrast alone - Void's surface1 is #070A0F, not black, whatever
    // an older version of this comment said. Everywhere else a plate stood
    // off the page by tone only, about 1.06:1, so cards barely registered and
    // screens read as text floating on black. So every plate now gets the
    // decorative `hairline` (1.2-2.0:1, which is right for a card edge; the
    // words inside say what it is) unless the owner picks "Panel edges: None".
    //
    // A flat theme keeps the stronger edge under EVERY setting, None
    // included: with no tone difference, None would leave no boundary at all.
    // An explicit `outline` from the caller always wins.
    val flat = chrome.surface1 == chrome.surface0
    val effectiveOutline = outline ?: when {
        flat -> chrome.hairlineStrong
        edges == PlateEdges.NONE -> null
        else -> chrome.hairline
    }
    // Bevel's "light catch": one static 1dp line just inside the top edge,
    // drawn once per draw of the plate - no blur, no shadow, no animation.
    // Inset by the corner radius at both ends so it never pokes out past a
    // rounded corner. On a light theme a line lighter than a white card is
    // invisible, so there it is the plain hairline and reads as an engraved
    // top edge instead.
    val catchColor = if (chrome.dark) chrome.hairlineStrong else chrome.hairline
    val catchInset = radii.card
    Column(
        modifier
            .fillMaxWidth()
            .clip(s)
            .background(tone ?: chrome.surface1)
            .then(
                if (edges == PlateEdges.BEVEL) {
                    Modifier.drawBehind {
                        val stroke = 1.dp.toPx()
                        // Below the 1dp border when there is one, so the two
                        // lines sit side by side instead of on top of each other.
                        val y = (if (effectiveOutline != null) stroke else 0f) + stroke / 2f
                        val inset = catchInset.toPx()
                        if (size.width > inset * 2f) {
                            drawLine(
                                color = catchColor,
                                start = Offset(inset, y),
                                end = Offset(size.width - inset, y),
                                strokeWidth = stroke,
                            )
                        }
                    }
                } else {
                    Modifier
                },
            )
            .then(
                if (effectiveOutline != null) {
                    Modifier.border(1.dp, effectiveOutline, s)
                } else {
                    Modifier
                },
            )
            .padding(LocalSpacing.current.plate),
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
 *
 * "Live." on its own describes the event stream, not the data under it. Mind
 * and Inbox are read once when they open, so ten minutes later a bare "Live."
 * sat over ten-minute-old numbers. Given [readWhat], the line splits into its
 * two halves - "Link live · board read 2 min ago" - and the age ticks on a
 * slow timer (see [rememberTickingNow]), not every frame.
 *
 * @param fetchedAtMs when the data below was read. 0 means not yet, and reads
 *   "Reading…". The default, 1, means the caller does not time its data, and
 *   keeps the old bare "Live.".
 * @param readWhat what was read, e.g. "Board" or "Inbox". Null keeps the old
 *   wording.
 * @param refreshing true while a re-read is in flight.
 */
@Composable
fun Freshness(
    link: LinkState,
    stale: Boolean,
    fetchedAtMs: Long = 1L,
    readWhat: String? = null,
    refreshing: Boolean = false,
) {
    val chrome = LocalChrome.current
    val bad = stale || link != LinkState.CONNECTED
    val timed = readWhat != null && fetchedAtMs > 1L
    // Only a line that shows an age needs a clock. Called conditionally on
    // purpose: an untimed line should not wake up every few seconds.
    val age = if (timed) ageText(rememberTickingNow(fetchedAtMs) - fetchedAtMs) else null
    val what = readWhat?.lowercase()
    Row(verticalAlignment = Alignment.CenterVertically) {
        Dot(if (bad) chrome.warnMark else chrome.okMark)
        Spacer(Modifier.width(10.dp))
        Text(
            when {
                link != LinkState.CONNECTED && age != null ->
                    "Not connected. Everything below is last known, read $age."
                link != LinkState.CONNECTED -> "Not connected. Everything below is last known."
                stale && age != null ->
                    "The stream is stale. Everything below is last known, read $age."
                stale -> "The stream is stale. Everything below is last known."
                fetchedAtMs == 0L -> "Reading…"
                age != null && refreshing -> "Link live · $what read $age · refreshing…"
                age != null -> "Link live · $what read $age"
                else -> "Live."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = if (bad) chrome.warnInk else chrome.textMid,
        )
    }
}

/**
 * The wall clock, re-read every [periodMs] rather than every frame - for
 * "read 2 min ago" lines, which only need to move once a minute. Restarts
 * (and so re-reads at once) whenever [key] changes, so a fresh read never
 * shows an age worked out from a clock that is still up to a period behind.
 */
@Composable
fun rememberTickingNow(key: Any? = null, periodMs: Long = 15_000L): Long {
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(key, periodMs) {
        while (true) {
            now = System.currentTimeMillis()
            delay(periodMs)
        }
    }
    return now
}

/** "just now", "4 min ago", "2 h ago" - coarse on purpose, and never negative. */
fun ageText(elapsedMs: Long): String {
    val s = elapsedMs.coerceAtLeast(0L) / 1000L
    return when {
        s < 60L -> "just now"
        s < 3_600L -> "${s / 60L} min ago"
        s < 86_400L -> "${s / 3_600L} h ago"
        else -> "${s / 86_400L} d ago"
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
        modifier.fillMaxWidth().padding(vertical = LocalSpacing.current.field),
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
 *
 * It used to be a bare `surface1` box: 1.06:1 against the page on Reactor and
 * 1.00:1 inside a plate, so "Connect" - the first thing a new owner must
 * press - looked like a floating label, and it was the same box as "Platform
 * checks" beside it. Now it is filled with its own tint at 12% and ringed in
 * `hairlineFocus`, which clears the 3:1 a control's boundary needs on every
 * theme. The quieter choice beside it is [Secondary].
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
) = BoxedAction(text, modifier, color, enabled, busy, emphasised = true, onClick = onClick)

/**
 * The quieter boxed action, for the second choice beside a [Primary]:
 * "Platform checks" next to "Connect", "Ask the desktop again".
 *
 * Told apart from Primary by shape and fill, not by text colour alone - a
 * hairline outline and no fill, against Primary's tinted fill and stronger
 * ring - so the pair reads correctly in greyscale and to a colour-blind eye.
 * Same signature as [Primary], so a call site switches by changing the name.
 */
@Composable
fun Secondary(
    text: String,
    modifier: Modifier = Modifier,
    color: Color? = null,
    enabled: Boolean = true,
    busy: Boolean = false,
    onClick: () -> Unit,
) = BoxedAction(text, modifier, color, enabled, busy, emphasised = false, onClick = onClick)

@Composable
private fun BoxedAction(
    text: String,
    modifier: Modifier,
    color: Color?,
    enabled: Boolean,
    busy: Boolean,
    emphasised: Boolean,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.controlShape
    val tint = color ?: accent
    // Disabled drops the fill and falls back to the decorative hairline, so
    // "not yet" is visible in the shape too and not only in the grey text.
    val edge = when {
        !enabled -> chrome.hairline
        emphasised -> chrome.hairlineFocus
        else -> chrome.hairline
    }
    val fill = if (emphasised && enabled) {
        tint.copy(alpha = 0.12f).compositeOver(chrome.surface1)
    } else {
        chrome.surface1
    }
    // The tinted fill costs the label some contrast: measured across every
    // palette family, an accent that clears 4.5:1 on a plain card can fall
    // to about 3.9:1 on its own 12% fill (Daylight is the worst). Where that
    // happens the label takes the theme's main text colour instead, so the
    // fill never makes a button harder to read.
    val ink = when {
        !enabled -> chrome.textLo
        contrastRatio(tint, fill) >= 4.5f -> tint
        else -> chrome.textHi
    }
    Box(
        modifier
            .heightIn(min = 48.dp)
            .clip(shape)
            .background(fill)
            .border(1.dp, edge, shape)
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
                color = ink,
                textAlign = TextAlign.Center,
                // Now that the box has a visible edge, a long label in a
                // half-width button must not run into it.
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
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
    /** False for prose: the field grows to [maxLines] lines, then scrolls. */
    singleLine: Boolean = true,
    maxLines: Int = 6,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    // The field's edge. It used to be marked out by tone alone - surface2 on
    // surface1, 1.06:1 - although Chrome names "an input border" as exactly
    // what `hairlineFocus` (3:1 or better on every theme) exists for. With
    // focus it becomes a 2dp ring in the accent: a change of width as well as
    // colour, so it does not rely on colour alone. The focus flag changes only
    // when focus moves, so this costs nothing per frame.
    var focused by remember { mutableStateOf(false) }
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
                .border(
                    width = if (focused) 2.dp else 1.dp,
                    color = if (focused) accent else chrome.hairlineFocus,
                    shape = radii.controlShape,
                )
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
                singleLine = singleLine,
                maxLines = if (singleLine) 1 else maxLines,
                modifier = Modifier
                    .fillMaxWidth()
                    .onFocusChanged { focused = it.isFocused },
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
fun Notice(
    text: String,
    onDismiss: () -> Unit,
    /**
     * A failure's technical detail for a bug report, already scrubbed of
     * tokens, keys, passwords, email addresses and user names
     * ([com.jarvis.client.net.PlainErrors.scrubDetails]). Behind "Details",
     * closed until tapped. Null or blank: no toggle.
     */
    details: String? = null,
    /** The failure's ONE fix button ("Try again", "Check the connection settings"...). */
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    var open by remember(text) { mutableStateOf(false) }
    Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
                // Spoken when it appears or changes. A refused theme change or
                // a failed send used to appear in silence for a TalkBack user.
                modifier = Modifier.weight(1f).liveStatus(),
            )
            Spacer(Modifier.width(8.dp))
            Quiet("Dismiss", onClick = onDismiss)
        }
        val hasDetails = !details.isNullOrBlank()
        if ((onAction != null && !actionLabel.isNullOrBlank()) || hasDetails) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (onAction != null && !actionLabel.isNullOrBlank()) {
                    Quiet(actionLabel, onClick = onAction)
                    Spacer(Modifier.width(8.dp))
                }
                if (hasDetails) {
                    Quiet(if (open) "Hide details" else "Details", onClick = { open = !open })
                }
            }
        }
        if (hasDetails && open) {
            // Selectable, so it can be copied by hand into a bug report
            // (ease-of-use audit 2026-09-27, #6). No Copy button: the
            // desktop's clipboard can sync off the PC, and one wording and
            // one way for both apps.
            SelectionContainer {
                Text(
                    details.orEmpty(),
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/**
 * Marks text as a status that TalkBack should read out when it changes,
 * without interrupting what it is already saying ("polite").
 *
 * For news the owner has to hear - a warning, a link going stale, a reason a
 * button just stopped working. Never for something that changes every second,
 * such as a countdown: a polite region that updates each second never stops
 * talking. The face's own description is the only other live region in the
 * app (FaceView).
 */
fun Modifier.liveStatus(): Modifier = semantics { liveRegion = LiveRegionMode.Polite }

/**
 * An on/off switch drawn in this app's own parts, replacing Material's
 * `Switch` - the last recognisably stock control, a pill track with a round
 * thumb sitting beside hand-built plates.
 *
 * State is shown three ways, so it never rests on colour alone: the word ON
 * or OFF inside the track, the thumb's side, and the colour (accent when on).
 * The track's edge is `hairlineFocus` when off, which is the token for "the
 * only thing marking this control's boundary" and clears 3:1 on every theme.
 *
 * TalkBack hears it as a switch with its on/off state (Role.Switch). The ON/
 * OFF word is hidden from TalkBack, because the state is already spoken and
 * would otherwise be read twice. Give it a label where it is used - the text
 * beside it, or a contentDescription on [modifier] - because a switch with no
 * name is only "switch, on".
 *
 * No ripple, and no auto-anything: it changes only when tapped.
 */
@Composable
fun Toggle(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val motion = LocalMotion.current
    val interaction = remember { MutableInteractionSource() }
    val trackShape = LocalRadii.current.insetShape
    val thumbShape = RoundedCornerShape(3.dp)
    // Read in the draw phase below, so the slide never recomposes anything.
    val position by animateFloatAsState(
        targetValue = if (checked) 1f else 0f,
        animationSpec = motion.micro(),
        label = "toggle",
    )
    val onColor = if (enabled) accent else chrome.textLo
    val trackEdge = when {
        !enabled -> chrome.hairline
        checked -> accent
        else -> chrome.hairlineFocus
    }
    val trackFill = if (checked && enabled) {
        accent.copy(alpha = 0.15f).compositeOver(chrome.surface2)
    } else {
        chrome.surface2
    }
    // Same guard as the boxed actions: the accent word on its own tinted
    // track can dip under 4.5:1, and then it takes the main text colour.
    val word = when {
        !checked -> chrome.textMid
        !enabled -> chrome.textLo
        contrastRatio(accent, trackFill) >= 4.5f -> accent
        else -> chrome.textHi
    }
    // The 48dp touch target wraps a smaller drawn track, the same way the
    // Quiet action does: the control looks compact and is still easy to hit.
    Box(
        modifier
            .heightIn(min = 48.dp)
            .widthIn(min = 48.dp)
            .toggleable(
                value = checked,
                interactionSource = interaction,
                // Null, deliberately: no Material ripple (see pressable).
                indication = null,
                enabled = enabled,
                role = Role.Switch,
                onValueChange = onCheckedChange,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .size(width = TOGGLE_WIDTH, height = TOGGLE_HEIGHT)
                .clip(trackShape)
                .background(trackFill)
                .border(1.dp, trackEdge, trackShape),
        ) {
            Text(
                if (checked) "ON" else "OFF",
                style = com.jarvis.client.ui.theme.JarvisType.telemetry,
                color = word,
                modifier = Modifier
                    // On: the word on the left, thumb on the right. Off: the
                    // other way round, so the word is never under the thumb.
                    .align(if (checked) Alignment.CenterStart else Alignment.CenterEnd)
                    .padding(horizontal = 7.dp)
                    .clearAndSetSemantics { },
            )
            Box(
                Modifier
                    .align(Alignment.CenterStart)
                    .padding(horizontal = TOGGLE_INSET)
                    .graphicsLayer {
                        val travel = (TOGGLE_WIDTH - TOGGLE_THUMB - TOGGLE_INSET * 2).toPx()
                        translationX = travel * position
                    }
                    .size(TOGGLE_THUMB)
                    .clip(thumbShape)
                    .background(if (checked) onColor else chrome.textLo),
            )
        }
    }
}

private val TOGGLE_WIDTH = 56.dp
private val TOGGLE_HEIGHT = 28.dp
private val TOGGLE_THUMB = 18.dp
private val TOGGLE_INSET = 5.dp

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

/**
 * Section spacing, so the screens do not each invent their own. Tightens by
 * a third under Density: Compact (see `Spacing.gap`).
 */
@Composable
fun Gap(dp: Int = 12) = Spacer(Modifier.height(LocalSpacing.current.gap(dp)))

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
            // A heading for TalkBack's "jump by heading" gesture. Mind, Checks
            // and Help are long lists, and with no headings anywhere in the app
            // the only way through them was one swipe per row. Here rather than
            // in Kicker, because a Kicker is also a field label and a "Jarvis"
            // tag on a reply, and those are not headings.
            Kicker(title, Modifier.semantics { heading() })
            if (trailing != null) {
                Row(verticalAlignment = Alignment.CenterVertically, content = trailing)
            }
        }
        Gap(8)
        content()
    }
}
