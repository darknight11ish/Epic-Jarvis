package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Notifications from Jarvis": one line and one button into Android's own
 * per-app notification screen.
 *
 * The owner's decision of 2026-10-09, after
 * `docs/SETTINGS-COVERAGE-AUDIT-2026-10-09.md` (GAP 1) found that the PC's
 * Notifications card had no phone counterpart. The audit's own three options
 * are in that file; the owner chose the first: **point at Android's screen**
 * rather than build a second copy of the PC's four switches, quiet hours and
 * Test button, which would then have to agree with Android's own settings and
 * could drift.
 *
 * So the two halves are named plainly, because they are genuinely different
 * jobs:
 *
 *  - **The PC decides what Jarvis sends** - the four kinds and quiet hours on
 *    the PC's Notifications card, which the desktop's Rust really honours.
 *  - **Android decides whether this phone shows it** - per channel, under
 *    Jarvis's own entry in Android's Settings, because the phone's channels
 *    (alarm, schedule, approval, handoff) are Android's, and quiet hours here
 *    are Android's own Do Not Disturb.
 *
 * Nothing is written from here and nothing reaches the desktop: it is a way
 * in, like the "Open Android's notification access" button in the Phone
 * notifications row above it. That is also why the row is not a hideable
 * menu (see `MenuVisibilityTest`'s deliberately-not-menus list).
 */
@Composable
internal fun NotificationsFromJarvisSection(onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    Section("Notifications from Jarvis") {
        Plate {
            Text(
                // The kinds named here are the app's real Android channels,
                // measured on the owner's phone on 2026-10-09 with
                // `dumpsys notification --noredact`: jarvis_alarm ("Alarms and
                // urgent alerts"), jarvis_schedule ("Reminders and timers" - the
                // morning briefing arrives there too, which is why it is not
                // named as a fourth switch of its own), jarvis_approval
                // ("Approvals") and jarvis_needs_you ("A website needs you").
                // The last one appears in Android's own screen only after the
                // first hand-off, because it is created when it is first needed.
                "Android decides whether this phone shows what Jarvis sends from your " +
                    "PC: alarms, reminders (the morning briefing arrives as one), approvals " +
                    "and \"a website needs you\" are separate switches there, and quiet " +
                    "hours are Android's own Do Not Disturb. Which kinds your PC sends at " +
                    "all is the PC's own Notifications card.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(12)
            Secondary(
                text = "Open Android's notification settings",
                color = chrome.textMid,
                modifier = Modifier.fillMaxWidth(),
                onClick = onOpen,
            )
        }
    }
}
