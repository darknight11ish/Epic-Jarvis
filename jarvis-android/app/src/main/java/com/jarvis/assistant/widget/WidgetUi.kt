package com.jarvis.assistant.widget

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.clickable
import androidx.glance.appwidget.cornerRadius
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/**
 * Shared widget primitives.
 *
 * Glance's own Button renders through the platform's RemoteViews button, which
 * carries a light-theme background that fights an AMOLED card. A clickable Box
 * gives full control of the surface.
 *
 * Note that `cornerRadius` is a no-op below API 31; on 28-30 these render square,
 * which is cosmetic rather than broken.
 */
@Composable
fun PillButton(
    label: String,
    tint: ColorProvider,
    background: ColorProvider,
    onClick: Action,
    modifier: GlanceModifier = GlanceModifier,
) {
    Box(
        modifier = modifier
            .background(background)
            .cornerRadius(10.dp)
            .clickable(onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = label, style = TextStyle(color = tint, fontSize = 12.sp))
    }
}

@Composable
fun StatusDot(online: Boolean, size: Int = 10) {
    Box(
        modifier = GlanceModifier
            .size(size.dp)
            .background(if (online) JarvisGlanceTheme.StatusOk else JarvisGlanceTheme.StatusBad)
            .cornerRadius((size / 2).dp),
        contentAlignment = Alignment.Center,
    ) {}
}
