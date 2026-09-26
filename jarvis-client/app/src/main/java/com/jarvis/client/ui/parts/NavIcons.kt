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
 * Four drawn glyphs. `docs/UI-AUDIT-2026-09-18.md` choice A1 - "no icon
 * font... drawn in-app like the microphone glyph is." - still holds: no icon
 * font, no vector asset.
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

/** Appearance: an eye - "how this looks", the reading the label's old name
 *  ("Look") gave it, in outline to match the other three. */
@Composable
fun AppearanceIcon(tint: Color, modifier: Modifier = Modifier) {
    Glyph(modifier) { stroke, u ->
        val lids = Path().apply {
            moveTo(2.5f * u, 12f * u)
            cubicTo(6f * u, 6f * u, 18f * u, 6f * u, 21.5f * u, 12f * u)
            cubicTo(18f * u, 18f * u, 6f * u, 18f * u, 2.5f * u, 12f * u)
            close()
        }
        drawPath(lids, tint, style = stroke)
        drawCircle(tint, radius = 3f * u, center = Offset(12f * u, 12f * u), style = stroke)
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
