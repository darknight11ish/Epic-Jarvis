package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.clickable
import androidx.compose.material3.Text

/**
 * What broke, on the phone, in words.
 *
 * Deliberately built out of nothing: hardcoded colours, no theme, no tokens, no
 * shared components. A diagnostic screen must not depend on the machinery it
 * might be diagnosing — if the theme system or the design tokens are what
 * failed, a screen that reads `LocalChrome` fails with them and the owner is
 * back to "it closed".
 *
 * It is shown before the app's own root modifier, which is what normally
 * keeps content clear of the status and navigation bars, so it clears them
 * itself with [safeDrawingPadding]. That is a plain layout modifier with no
 * theme behind it, so the "built out of nothing" rule above still holds.
 * Without it, the app draws edge to edge and the Copy button could sit under
 * a three-button navigation bar.
 *
 * @param dismissLabel what the second button says. "Close app" when
 *   [onDismiss] ends the app (the startup failures, where there is nothing to
 *   continue to); "Continue" only when the app really does carry on.
 */
@Composable
fun CrashScreen(
    title: String,
    detail: String,
    onDismiss: () -> Unit,
    dismissLabel: String = "Continue",
) {
    val clipboard = LocalClipboardManager.current
    Column(
        Modifier
            .fillMaxSize()
            // Background first, so the dark fills behind the system bars too;
            // the insets then move only the content.
            .background(Color(0xFF04070C))
            .safeDrawingPadding()
            .padding(20.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Text(
            title,
            color = Color(0xFFFF7B86),
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "This is the app telling you what happened instead of vanishing. " +
                "Tap Copy and send it to whoever is fixing Jarvis.",
            color = Color(0xFF8FA3B8),
            fontSize = 14.sp,
        )
        Spacer(Modifier.height(14.dp))
        Box(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(Color(0xFF0A1119))
                .padding(12.dp),
        ) {
            Text(
                detail,
                color = Color(0xFFDDE7F2),
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.verticalScroll(rememberScrollState()),
            )
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Action("Copy", Color(0xFF6FE3FF)) {
                clipboard.setText(AnnotatedString(detail))
            }
            Action(dismissLabel, Color(0xFF8FA3B8), onDismiss)
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun Action(label: String, tint: Color, onClick: () -> Unit) {
    Box(
        Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(tint.copy(alpha = 0.16f))
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 14.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = tint, fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}
