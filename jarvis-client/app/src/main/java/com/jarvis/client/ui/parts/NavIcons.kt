package com.jarvis.client.ui.parts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.unit.dp

/**
 * Six drawn glyphs (Mind, Inbox, Reminders, Live, Help, Settings - Settings
 * joined the row on 2026-10-08, and the count here moved with it).
 * `docs/UI-AUDIT-2026-09-18.md` choice A1 - "no icon
 * font... drawn in-app like the microphone glyph is." - still holds: no icon
 * font, no vector asset.
 *
 * Reminders is the newest (2026-11-02): the owner asked for Appearance to be
 * reachable only in Settings and for a Reminders button in its place on Home's
 * row, so the eye that was here is gone with the button it belonged to. The
 * set is still six, and still drawn to the one rule below.
 *
 * They used to be built from clipped `Box`es, and it showed: a bulb with a
 * filled base, a ring with a filled centre, a tray with a filled slot, an "i"
 * that was all fill - outline and fill mixed at random, and no shared stroke
 * ends, because boxes have none. Now each is drawn on one [Canvas] to a single
 * rule, so the four read as one instrument set:
 *
 * - a 24-unit grid, one unit = 1/24 of the icon's width;
 * - one 1.5dp stroke, round caps, round joins;
 * - outlines only. The one exception is a round dot the width of a stroke
 *   (the dot on the "i", the node on Mind's orbit), which is what a
 *   round-capped point looks like anyway.
 *
 * A Canvas redraws only when its tint or size changes, so these cost nothing
 * per frame.
 */
private val ICON_SIZE = 24.dp
private val ICON_STROKE = 1.5.dp

/** Draws [block] on a 24dp canvas with the shared stroke; `u` is one grid unit in px. */
@Composable
private fun Glyph(
    modifier: Modifier,
    block: DrawScope.(stroke: Stroke, u: Float) -> Unit,
) {
    Canvas(modifier.size(ICON_SIZE)) {
        val stroke = Stroke(
            width = ICON_STROKE.toPx(),
            cap = StrokeCap.Round,
            join = StrokeJoin.Round,
        )
        // The receiver passed explicitly: this Canvas's DrawScope.
        block(this, stroke, size.minDimension / 24f)
    }
}

/**
 * Mind: a node inside a tilted orbit, echoing the reactor's own ring.
 *
 * It used to be a lightbulb, which in nearly every app means "tip" or "idea".
 * This screen shows what Jarvis is doing and holding right now - an engine
 * with something in orbit, not a hint.
 */
@Composable
fun MindIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        val c = Offset(12f * u, 12f * u)
        drawCircle(tint, radius = 2.75f * u, center = c, style = stroke)
        rotate(degrees = -30f, pivot = c) {
            drawOval(
                color = tint,
                topLeft = Offset(2f * u, 7.5f * u),
                size = Size(20f * u, 9f * u),
                style = stroke,
            )
            // A satellite on the orbit's leading end.
            drawCircle(tint, radius = stroke.width * 0.9f, center = Offset(22f * u, 12f * u))
        }
    }
}

/** Inbox: a tray with a dip in its front edge - things waiting to be looked
 *  at, sitting in a container rather than floating loose. */
@Composable
fun InboxIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        drawRoundRect(
            color = tint,
            topLeft = Offset(3f * u, 5f * u),
            size = Size(18f * u, 14f * u),
            cornerRadius = CornerRadius(2.5f * u, 2.5f * u),
            style = stroke,
        )
        val lip = Path().apply {
            moveTo(3f * u, 13f * u)
            lineTo(8f * u, 13f * u)
            lineTo(9.5f * u, 15.5f * u)
            lineTo(14.5f * u, 15.5f * u)
            lineTo(16f * u, 13f * u)
            lineTo(21f * u, 13f * u)
        }
        drawPath(lip, tint, style = stroke)
    }
}

/**
 * Reminders: a bell - the plain, universal mark for "something will go off".
 *
 * It opens Brain -> Coming up ("Reminders, alarms, timers and repeating jobs"),
 * and it took Appearance's place in Home's row on 2026-11-02. A bell rather
 * than a clock: Coming up is not one appointment at one time - it is the list
 * of things that will interrupt the owner, and it is the mark every phone's
 * own alarm screen uses.
 */
@Composable
fun RemindersIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        // The body: two sides rising from the rim, over a round top.
        val bell = Path().apply {
            moveTo(6.5f * u, 17.2f * u)
            lineTo(6.5f * u, 11.5f * u)
            cubicTo(6.5f * u, 8.4f * u, 8.9f * u, 6.2f * u, 12f * u, 6.2f * u)
            cubicTo(15.1f * u, 6.2f * u, 17.5f * u, 8.4f * u, 17.5f * u, 11.5f * u)
            lineTo(17.5f * u, 17.2f * u)
        }
        drawPath(bell, tint, style = stroke)
        // The rim it stands on, a little wider than the body on both sides.
        drawLine(
            color = tint,
            start = Offset(4.5f * u, 17.2f * u),
            end = Offset(19.5f * u, 17.2f * u),
            strokeWidth = stroke.width,
            cap = StrokeCap.Round,
        )
        // The clapper: a short arc hanging under the rim, in outline like the rest.
        val clapper = Path().apply {
            moveTo(10f * u, 17.2f * u)
            quadraticTo(10f * u, 20.4f * u, 12f * u, 20.4f * u)
            quadraticTo(14f * u, 20.4f * u, 14f * u, 17.2f * u)
        }
        drawPath(clapper, tint, style = stroke)
        // The hanger at the top, so the bell reads as hung rather than stood.
        drawLine(
            color = tint,
            start = Offset(12f * u, 3.6f * u),
            end = Offset(12f * u, 6.2f * u),
            strokeWidth = stroke.width,
            cap = StrokeCap.Round,
        )
    }
}

/** Jarvis Live: five sound bars - a conversation going on. */
@Composable
fun LiveIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        val bars = listOf(4f to 2.5f, 8f to 5f, 12f to 7.5f, 16f to 5f, 20f to 2.5f)
        for ((x, half) in bars) {
            drawLine(
                color = tint,
                start = Offset(x * u, (12f - half) * u),
                end = Offset(x * u, (12f + half) * u),
                strokeWidth = stroke.width,
                cap = StrokeCap.Round,
            )
        }
    }
}

/** Help: an "i" in a ring - the plain, universal mark for "read more here",
 *  not the question-mark-as-decoration a FAQ page usually reaches for. */
@Composable
fun HelpIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        drawCircle(tint, radius = 9f * u, center = Offset(12f * u, 12f * u), style = stroke)
        drawCircle(tint, radius = stroke.width * 0.7f, center = Offset(12f * u, 7.75f * u))
        drawLine(
            color = tint,
            start = Offset(12f * u, 11f * u),
            end = Offset(12f * u, 16.5f * u),
            strokeWidth = stroke.width,
            cap = StrokeCap.Round,
        )
    }
}

/** Settings: a cog - the plain, universal mark for "the switches for
 *  everything else", an outline like the other five. Its eight teeth are one
 *  line each, drawn round the ring, so it never looks busier than they do. */
@Composable
fun SettingsIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        val c = Offset(12f * u, 12f * u)
        drawCircle(tint, radius = 6.5f * u, center = c, style = stroke)
        for (i in 0 until 8) {
            rotate(degrees = i * 45f, pivot = c) {
                drawLine(
                    color = tint,
                    start = Offset(12f * u, 3f * u),
                    end = Offset(12f * u, 5.5f * u),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
            }
        }
    }
}
