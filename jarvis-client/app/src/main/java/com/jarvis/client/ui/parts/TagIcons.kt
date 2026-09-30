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
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * The ten chat-tag icons (docs/CHAT-TAGS-DESIGN.md section 10's shared list:
 * briefcase book home folder lightbulb star flag wrench leaf music), drawn on
 * a [Canvas] the way NavIcons.kt draws its glyphs: no icon font, no vector
 * asset, no new dependency. A 24-unit grid, one round-capped outline stroke,
 * no fill. The desktop draws the same names with its own icon set.
 *
 * A name this app does not know is drawn as a plain ring, so an icon added on
 * the PC later never leaves a hole or crashes the list.
 *
 * Purely decorative: the tag's NAME is always beside it, so the icon carries
 * no description of its own (colour and icon are never the only clue).
 */
@Composable
fun TagIcon(name: String, tint: Color, modifier: Modifier = Modifier, size: Dp = 18.dp) {
    Canvas(modifier.size(size)) {
        val u = this.size.minDimension / 24f
        val stroke = Stroke(width = 1.6f * u.coerceAtLeast(0.75f), cap = StrokeCap.Round, join = StrokeJoin.Round)
        drawTag(name, tint, stroke, u)
    }
}

private fun DrawScope.line(c: Color, s: Stroke, u: Float, x1: Float, y1: Float, x2: Float, y2: Float) =
    drawLine(c, Offset(x1 * u, y1 * u), Offset(x2 * u, y2 * u), strokeWidth = s.width, cap = StrokeCap.Round)

private fun poly(u: Float, close: Boolean, vararg xy: Float): Path = Path().apply {
    moveTo(xy[0] * u, xy[1] * u)
    var i = 2
    while (i + 1 < xy.size) {
        lineTo(xy[i] * u, xy[i + 1] * u)
        i += 2
    }
    if (close) close()
}

private fun DrawScope.drawTag(name: String, c: Color, s: Stroke, u: Float) {
    when (name) {
        "briefcase" -> {
            drawRoundRect(c, Offset(3f * u, 8f * u), Size(18f * u, 12f * u), CornerRadius(2f * u), style = s)
            drawPath(poly(u, false, 9f, 8f, 9f, 5.5f, 15f, 5.5f, 15f, 8f), c, style = s)
            line(c, s, u, 3f, 13f, 21f, 13f)
        }
        "book" -> {
            drawRoundRect(c, Offset(5f * u, 3.5f * u), Size(14f * u, 17f * u), CornerRadius(2f * u), style = s)
            line(c, s, u, 9f, 3.5f, 9f, 20.5f)
            line(c, s, u, 12f, 8f, 16f, 8f)
        }
        "home" -> {
            drawPath(poly(u, false, 3f, 11f, 12f, 4f, 21f, 11f), c, style = s)
            drawPath(poly(u, false, 5.5f, 9.5f, 5.5f, 20f, 18.5f, 20f, 18.5f, 9.5f), c, style = s)
            drawPath(poly(u, false, 10f, 20f, 10f, 14f, 14f, 14f, 14f, 20f), c, style = s)
        }
        "folder" -> {
            drawPath(poly(u, true, 3f, 6.5f, 10f, 6.5f, 12f, 9f, 21f, 9f, 21f, 19f, 3f, 19f), c, style = s)
        }
        "lightbulb" -> {
            drawCircle(c, radius = 6f * u, center = Offset(12f * u, 10f * u), style = s)
            line(c, s, u, 10f, 18f, 14f, 18f)
            line(c, s, u, 10.5f, 21f, 13.5f, 21f)
        }
        "star" -> {
            val p = Path()
            for (i in 0 until 10) {
                val r = if (i % 2 == 0) 9f else 4f
                val a = -PI / 2 + i * PI / 5
                val x = (12f + r * cos(a).toFloat()) * u
                val y = (12.5f + r * sin(a).toFloat()) * u
                if (i == 0) p.moveTo(x, y) else p.lineTo(x, y)
            }
            p.close()
            drawPath(p, c, style = s)
        }
        "flag" -> {
            line(c, s, u, 6f, 3f, 6f, 21f)
            drawPath(poly(u, true, 6f, 4f, 18f, 4f, 15f, 8f, 18f, 12f, 6f, 12f), c, style = s)
        }
        "wrench" -> {
            line(c, s, u, 5f, 19f, 13.5f, 10.5f)
            drawCircle(c, radius = 3.5f * u, center = Offset(16.5f * u, 7.5f * u), style = s)
        }
        "leaf" -> {
            val p = Path().apply {
                moveTo(5f * u, 19f * u)
                cubicTo(5f * u, 10f * u, 10f * u, 5f * u, 20f * u, 4f * u)
                cubicTo(20f * u, 14f * u, 15f * u, 19f * u, 5f * u, 19f * u)
                close()
            }
            drawPath(p, c, style = s)
            line(c, s, u, 5f, 19f, 13f, 11f)
        }
        "music" -> {
            line(c, s, u, 9f, 17f, 9f, 6f)
            line(c, s, u, 9f, 6f, 19f, 4f)
            line(c, s, u, 19f, 4f, 19f, 15f)
            drawCircle(c, radius = 2.2f * u, center = Offset(7f * u, 17.5f * u), style = s)
            drawCircle(c, radius = 2.2f * u, center = Offset(17f * u, 15.5f * u), style = s)
        }
        else -> drawCircle(c, radius = 6f * u, center = Offset(12f * u, 12f * u), style = s)
    }
}
