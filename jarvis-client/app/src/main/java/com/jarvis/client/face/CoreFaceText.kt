package com.jarvis.client.face

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb

/**
 * Text drawn as part of a face - Workbench's caliper reading and its two
 * labels, which the reference draws into its canvas with `fillText`
 * (artifact 3831-3836).
 *
 * Through the platform canvas rather than Compose text, because a `Face`
 * draws inside a plain `DrawScope`: Compose's `drawText` needs a
 * `TextMeasurer`, which only a composable can create, and threading one
 * through `Face.draw` would change the signature every other face shares.
 * One cached `Paint`, so a frame allocates nothing here but the string.
 *
 * Monospace because the reference asks for Space Mono, which this app does
 * not bundle; the system monospace face is the closest thing it has.
 *
 * Its own file so the Android-only imports stay out of Faces.kt, which is
 * otherwise plain Compose.
 */
private val labelPaint by lazy {
    // Lazy: `android.graphics.Paint` is a stub that throws in plain JVM unit
    // tests, and those touch `Faces.all` without ever drawing a face.
    android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        typeface = android.graphics.Typeface.MONOSPACE
        textAlign = android.graphics.Paint.Align.LEFT
    }
}

/** Draws [text] with its left end and baseline at ([x], [y]), like `fillText`. */
internal fun DrawScope.drawCoreLabel(text: String, x: Float, y: Float, sizePx: Float, color: Color) {
    if (sizePx < 1f) return
    val p = labelPaint
    p.textSize = sizePx
    p.color = color.toArgb()
    drawIntoCanvas { it.nativeCanvas.drawText(text, x, y, p) }
}
