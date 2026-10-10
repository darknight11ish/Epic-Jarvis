package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.jarvis.client.data.ScreenRate
// Choices lives in this same package (AppearanceScreen.kt) - no import.
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Screen refresh rate" (Settings; [ScreenRate]).
 *
 * ## What this promises, and what it must never promise
 *
 * The setting is **"while Jarvis is on screen, ask the screen for this rate"**.
 * It is not "change my phone's refresh rate", and it never can be: a
 * sideloaded app has no `WRITE_SECURE_SETTINGS` and no
 * `CAPABILITY_CONTROL_DISPLAY_MODES`, and `DisplayManager.setUserPreferredDisplayMode()`
 * (the API that *would* change the phone) throws `SecurityException` for an
 * ordinary app. [ScreenRate]'s own doc has the whole story, with the evidence
 * read off the owner's phone. The two sentences at the top of this plate say
 * the same thing in the owner's own words rather than in API names, because a
 * setting that quietly promises more than it can do is the exact failure this
 * app is not allowed to make.
 *
 * ## Not the face's frame rate
 *
 * Appearance -> the face editor also has a "Frame rate", and it is a different
 * thing: that one is how often the **animal is drawn**, this one is what the
 * **panel runs at**. Picking 30 there animates the animal at 30 frames a
 * second on a screen still running at 120; picking 60 here asks the panel to
 * run at 60 and does not slow the animal at all. They are two rows on two
 * screens on purpose - see [ScreenRate]'s doc, which says what merging them
 * would break.
 *
 * ## Shapes
 *
 * Saved on this phone only, like Floating Jarvis and Quick Settings tiles
 * above it, so nothing here checks `canAct`: there is no route, no approval
 * card and nothing that reaches the PC. "Follow the phone" is always offered
 * first - that is the way back to whatever the phone was using.
 *
 * @param chosen the owner's pick, or null to follow the phone.
 * @param rates the distinct rates the panel offers, ascending ([ScreenRate.rates]).
 * @param panelHz what the panel is running at right now, from the platform.
 * @param note the readback sentence ([ScreenRate.tookNote]) - including, when
 *   the system refused the rate, that it did not take effect.
 * @param checked true once [note] is a real observation rather than a promise.
 * @param onPick saves the pick and asks the panel for it; null means follow the phone.
 * @param onRecheck re-reads what the panel settled on (the phone's own display
 *   settings can change it at any time, and nothing can tell us when).
 */
@Composable
internal fun ScreenRateSection(
    chosen: Float?,
    rates: List<Float>,
    panelHz: Float,
    note: String,
    checked: Boolean,
    onPick: (Float?) -> Unit,
    onRecheck: () -> Unit,
) {
    val chrome = LocalChrome.current
    // "Check again": the phone's own display settings, battery saver and heat
    // can change the real rate at any moment, and nothing tells the app when -
    // so this re-reads rather than leaving a stale sentence on screen.
    Section("Screen refresh rate", trailing = { Quiet("Check again", onClick = onRecheck) }) {
        Plate {
            Text(
                ScreenRate.HONEST_NOTE,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(12)

            if (rates.isEmpty()) {
                // Nothing detected: say so. A picker with no rates in it would
                // be a control that cannot do anything.
                Text(
                    "This phone has not reported which refresh rates its screen offers, so there " +
                        "is nothing to choose from yet.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                Gap(6)
                Text(
                    "Open Settings again in a moment, or on a screen that is awake, and the list " +
                        "should appear.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            } else {
                // "Follow the phone" first, then every rate the panel really
                // offers, ascending. Null stands for it, exactly as it is
                // stored.
                val options: List<Float?> = listOf<Float?>(null) + rates
                Text(
                    if (chosen == null) "Now: the phone decides." else "Now: asking for ${ScreenRate.label(chosen)} Hz.",
                    style = MaterialTheme.typography.labelLarge,
                    color = chrome.textHi,
                )
                Gap(6)
                options.chunked(4).forEachIndexed { i, row ->
                    if (i > 0) Gap(6)
                    Choices(
                        options = row,
                        isSelected = { it == chosen },
                        // The rate the panel is running at right now is marked
                        // as well as the pick, so the owner can see at a glance
                        // whether their choice actually took.
                        label = { hz ->
                            when {
                                hz == null -> "Follow the phone"
                                ScreenRate.took(hz, panelHz) -> "${ScreenRate.label(hz)} Hz · now"
                                else -> "${ScreenRate.label(hz)} Hz"
                            }
                        },
                        onPick = onPick,
                    )
                }
                if (rates.size > 1) {
                    Gap(6)
                    Text(
                        "This screen offers ${rates.joinToString(", ") { ScreenRate.label(it) }} Hz.",
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textLo,
                    )
                }
            }

            Gap(12)
            // The honest readback. Before the first check it is a promise and
            // says "asks"; afterwards it is an observation, and when the panel
            // refused the rate it says exactly that.
            Text(
                if (note.isBlank()) {
                    if (chosen == null) {
                        "Jarvis is leaving the screen's refresh rate to your phone."
                    } else {
                        "Asking the screen for ${ScreenRate.label(chosen)} Hz while Jarvis is on screen."
                    }
                } else {
                    note
                },
                style = MaterialTheme.typography.bodySmall,
                color = if (checked && chosen != null && !ScreenRate.took(chosen, panelHz)) {
                    chrome.textHi
                } else {
                    chrome.textMid
                },
            )
            Gap(6)
            Text(ScreenRate.BATTERY_NOTE, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            Gap(6)
            Text(
                "This is not the animal's frame rate. Appearance sets how often the animal is " +
                    "drawn; this sets how often the screen refreshes. They are separate settings.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
    }
}
