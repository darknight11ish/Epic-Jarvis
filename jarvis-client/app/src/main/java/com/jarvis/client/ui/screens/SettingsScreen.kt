package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.LinkState
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Settings" - the ease-of-use audit's row 16 (`docs/EASE-OF-USE-AUDIT-2026-09-27.md`):
 * voice, security, look and the small settings that used to sit under
 * Brain's own "Settings" group, in one place instead of scattered across
 * Brain and "Platform checks" (the audit calls the latter "Checks and
 * setup" - that rename has not actually landed on this branch; see this
 * task's report).
 *
 * Moved HERE, in full, from Brain's old "Settings" group: "How Jarvis
 * talks", web search, "What asks first", "What Jarvis can reach", "Sending
 * email", "Folders Jarvis may look in" and the smartwatch notification
 * setting. All seven are the exact composables Brain used to render
 * ([MannerSection], [WebSearchSection], [AsksFirstSection], [ReachSection],
 * [EmailSendingSection], [FoldersSection], [WatchNotifySection]) - moved
 * here rather than duplicated, so there is one copy of each, same as before.
 *
 * Kept as SEPARATE screens, only LINKED from here: voice training, the
 * voice check's strictness and custom voices (all three talk to the
 * desktop, so - exactly as on "Platform checks" - the callbacks below are
 * null until a desktop is paired); Security (App lock, screen-lock
 * messaging - this phone's own, so it works whether or not it is paired);
 * and Appearance (theme, the reactor's face, how it looks). Nothing about
 * those screens changed, only the way in.
 *
 * "Platform checks" keeps its own Security card and voice buttons too -
 * nothing that already worked there was removed - and gets one new plate
 * pointing here, so this screen is reachable from both of the places the
 * audit named. Diagnostics (connection status, hardware, the audit chain,
 * capabilities) are deliberately NOT here: the audit's own point is a real
 * Settings screen, not a second Brain.
 */
@Composable
fun SettingsScreen(
    link: LinkState,
    stale: Boolean,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    /**
     * "Train my voice", "Voice check: how strict...", and "Jarvis's voice" -
     * null until a desktop is paired, the same rule
     * [com.jarvis.client.MainActivity] already applies for the same three
     * buttons on "Platform checks".
     */
    onTrainVoice: (() -> Unit)? = null,
    onVoiceCheck: (() -> Unit)? = null,
    onVoices: (() -> Unit)? = null,
    /** The same sentence "Platform checks" shows above its own Security card. */
    securitySummary: String,
    onOpenSecurity: () -> Unit,
    /**
     * Null until a desktop is paired - Appearance can push the shared face
     * and colours to it, and (like the app's own pairing gate) is not shown
     * as a destination before there is a desktop to push to.
     */
    onOpenAppearance: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    // The same gate every other write on this screen already uses
    // (Manner/WebSearch/AsksFirst/WatchNotify all take it) - rule 4.
    val canAct = link == LinkState.CONNECTED && !stale

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Settings", onBack)

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item(key = "voice") {
                Section("Voice") {
                    Plate {
                        Text(
                            "Whether Jarvis knows your voice, how strict that check is, and " +
                                "the voice Jarvis answers in.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        val any = onTrainVoice != null || onVoiceCheck != null || onVoices != null
                        if (any) Gap(10)
                        onTrainVoice?.let {
                            Secondary("Train my voice", modifier = Modifier.fillMaxWidth(), onClick = it)
                            Gap(8)
                        }
                        onVoiceCheck?.let {
                            Secondary(
                                "Voice check: how strict, private answers",
                                modifier = Modifier.fillMaxWidth(),
                                onClick = it,
                            )
                            Gap(8)
                        }
                        onVoices?.let {
                            Secondary("Jarvis's voice", modifier = Modifier.fillMaxWidth(), onClick = it)
                        }
                        if (!any) {
                            Gap(6)
                            Text(
                                "Pair with your desktop first - these settings live on it.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }

            item(key = "security") {
                Section("Security") {
                    Plate {
                        Text(securitySummary, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        Gap(10)
                        Secondary(
                            "Lock and fingerprint settings",
                            modifier = Modifier.fillMaxWidth(),
                            onClick = onOpenSecurity,
                        )
                    }
                }
            }

            item(key = "appearance") {
                Section("Appearance") {
                    Plate {
                        Text(
                            "Theme, the reactor's face, and how it all looks.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        Gap(10)
                        val openAppearance = onOpenAppearance
                        if (openAppearance != null) {
                            Secondary("Appearance", modifier = Modifier.fillMaxWidth(), onClick = openAppearance)
                        } else {
                            Text(
                                "Pair with your desktop first - Appearance shares the face and " +
                                    "colours with it.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }

            // The seven sections moved whole from Brain's old "Settings"
            // group - see this file's own doc comment.
            item(key = "manner") { MannerSection(canAct = canAct) }
            item(key = "web-search") { WebSearchSection(canAct = canAct) }
            item(key = "asks-first") { AsksFirstSection(canAct = canAct) }
            item(key = "reach") { ReachSection() }
            item(key = "email-sending") { EmailSendingSection() }
            item(key = "folders") { FoldersSection() }
            item(key = "watch-notify") { WatchNotifySection(canAct = canAct) }

            item(key = "tail") { Gap(24) }
        }
    }
}
