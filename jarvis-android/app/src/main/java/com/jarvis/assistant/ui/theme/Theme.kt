package com.jarvis.assistant.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** True black: on AMOLED these pixels draw no current at all. */
val JarvisBlack = Color(0xFF000000)
val JarvisSurface = Color(0xFF0B0B0D)
val JarvisOutline = Color(0xFF1F2124)
val JarvisCyan = Color(0xFF22D3EE)
val JarvisAmber = Color(0xFFFBBF24)
val JarvisRed = Color(0xFFF87171)
val JarvisGreen = Color(0xFF34D399)
val JarvisTextPrimary = Color(0xFFE7E9EA)
val JarvisTextMuted = Color(0xFF8A9096)

private val JarvisColors = darkColorScheme(
    primary = JarvisCyan,
    onPrimary = JarvisBlack,
    secondary = JarvisCyan,
    onSecondary = JarvisBlack,
    background = JarvisBlack,
    onBackground = JarvisTextPrimary,
    surface = JarvisBlack,
    onSurface = JarvisTextPrimary,
    surfaceVariant = JarvisSurface,
    onSurfaceVariant = JarvisTextMuted,
    outline = JarvisOutline,
    error = JarvisRed,
    onError = JarvisBlack,
)

private val JarvisTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        letterSpacing = 0.4.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontSize = 11.sp,
        letterSpacing = 1.sp,
    ),
)

/**
 * Always dark. The HUD is meant to be readable at 3am without lighting the room,
 * so the system light theme is deliberately ignored.
 */
@Composable
fun JarvisTheme(
    @Suppress("UNUSED_PARAMETER") darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = JarvisColors,
        typography = JarvisTypography,
        content = content,
    )
}
