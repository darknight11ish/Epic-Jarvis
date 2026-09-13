package com.jarvis.assistant.widget.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceModifier
import androidx.glance.background
import androidx.glance.unit.ColorProvider
import androidx.glance.text.FontWeight
import androidx.glance.text.TextStyle

/**
 * Widget palette.
 *
 * Home screens sit on the user's own wallpaper, so widgets use a near-black
 * surface rather than the HUD's true black: a pure #000000 card reads as a hole
 * punched in the wallpaper, while the app's own full-screen background does not.
 */
object JarvisGlanceTheme {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface = ColorProvider(Color(0xFF0A1119))
    val SurfaceRaised = ColorProvider(Color(0xFF121A24))
    val Line = ColorProvider(Color(0xFF172836))
    val Primary = ColorProvider(Color(0xFF6FE3FF))
    val AccentGold = ColorProvider(Color(0xFFFFB648))
    val StatusOk = ColorProvider(Color(0xFF3DDC97))
    val StatusWarn = ColorProvider(Color(0xFFFFB648))
    val StatusBad = ColorProvider(Color(0xFFFF6B7A))
    val TextPrimary = ColorProvider(Color(0xFFCFE4EE))
    val TextMuted = ColorProvider(Color(0xFF6B8496))

    val Label = TextStyle(color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Medium)
    val Body = TextStyle(color = TextPrimary, fontSize = 12.sp)
    val Title = TextStyle(color = TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.Bold)
    val Metric = TextStyle(color = Primary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
}

fun GlanceModifier.appWidgetBackground(): GlanceModifier =
    this.background(JarvisGlanceTheme.Background)
