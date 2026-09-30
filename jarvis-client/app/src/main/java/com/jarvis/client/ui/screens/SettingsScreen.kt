package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.LinkState
import com.jarvis.client.data.FloatingAvatarMode
import com.jarvis.client.data.QuickTiles
import com.jarvis.client.data.TileAction
import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

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

/**
 * Every `item(key = ...)` below, by its position in the `LazyColumn` - kept
 * as one small map rather than computed, so a reordering of the items below
 * is a visible two-line diff here too, not a silent mismatch. "Open <a
 * settings section>" (docs/JARVIS-API.md section 58.1) is this map's only
 * reader.
 *
 * Bug audit 2026-09-27: this went stale the moment "floating-avatar" was
 * inserted at position 3 by a concurrent piece of work - every index from
 * "manner" down was one item too early, unnoticed because the merge that
 * combined both pieces of work was a clean auto-merge with no text
 * conflict here. Fixed by re-reading the real `item(key = ...)` order
 * below rather than hand-adjusting the old numbers.
 */
private val SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(
    // Item 0 is the jump list ([SettingsJump]), added 2026-09-30.
    "voice" to 1,
    "security" to 2,
    "appearance-card" to 3,
    // "Animal options" lives inside Appearance on the phone (2026-09-28):
    // the Appearance row, whose button opens it.
    "animal-options" to 3,
    "floating-avatar" to 4,
    "manner" to 5,
    "web-search" to 6,
    "asks-first" to 7,
    "reach" to 8,
    "email-sending" to 9,
    "folders" to 10,
    "backup" to 11,
    "watch-notify" to 12,
    "phone-notify" to 13,
    "screen-look" to 14,
    "browser-engine" to 15,
    "devices" to 16,
    "quick-tiles" to 17,
)

/**
 * The jump list's own keys are the screen's item keys, except that the
 * Appearance row is "appearance" on the screen and "appearance-card" in the
 * map above (the desktop's id for the same card).
 */
private fun jumpIndex(key: String): Int? =
    SETTINGS_ITEM_INDEX[if (key == "appearance") "appearance-card" else key]

/**
 * The Voice section's line about Android 17's assistant volume slider. Said
 * with its one exception: while "Listen on this phone" is on together with
 * "Interrupt Jarvis while it talks", an answer plays as a voice call
 * (WakeWordService -> Speaker.beginVoiceCall), so the call volume sets it.
 * The slider's name on the phone is Android's, not checked on a real
 * Android 17 phone - so the line does not quote one.
 */
internal const val ASSISTANT_VOLUME_LINE =
    "On Android 17 and later, Jarvis's spoken answers have their own volume " +
        "slider for assistants in the phone's volume panel, apart from music. When " +
        "this phone listens with \"Interrupt Jarvis while it talks\" on, answers play " +
        "as a call, so the call volume sets them instead."

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
    /** "Floating Jarvis" - saved on this phone only, so it needs no `canAct` gate. */
    floatingAvatar: FloatingAvatarMode = FloatingAvatarMode.OFF,
    onFloatingAvatarChange: (FloatingAvatarMode) -> Unit = {},
    overlayGranted: Boolean = false,
    onRequestOverlay: () -> Unit = {},
    onOpenBubbleSettings: () -> Unit = {},
    /** "Quick Settings tiles" - saved on this phone only, like Floating Jarvis. */
    quickTiles: List<TileAction?> = List(QuickTiles.SLOTS) { null },
    onQuickTileChange: (slot: Int, action: TileAction?) -> Unit = { _, _ -> },
    /**
     * "Reading phone notifications" (docs/JARVIS-API.md §61): whether
     * Android's own "Notification access" is currently granted
     * (`NotificationManagerCompat.getEnabledListenerPackages`, re-read on
     * resume - the same `tick` pattern [overlayGranted] already uses), and
     * the button that opens that OS screen.
     */
    notificationAccessGranted: Boolean = false,
    onOpenNotificationAccess: () -> Unit = {},
    /**
     * "Open <a settings section>" by voice or chat
     * (`jarvis_settings_registry.py`, docs/JARVIS-API.md section 58.1): the
     * section id `MainActivity` read off `ChatSession.openSettings`, or
     * null. A new (distinct) value scrolls to that item once. Since the
     * phone walk-through of 2026-09-27 only ids with a row here arrive -
     * [com.jarvis.client.ui.OpenPlace] sends the rest to Help, Checks,
     * Brain or "Jarvis's voice", or says the place is only on the PC - but
     * an unknown id (one newer than this app) is still a harmless no-op
     * here. Voice, Security and Appearance (above) are real
     * `item(key = ...)` rows too, with their own entries in
     * [SETTINGS_ITEM_INDEX], so an id naming one of them scrolls to it like
     * any other section - it does not fall into that no-op case.
     */
    initialSection: String? = null,
    /**
     * Called once, right after [initialSection] has been acted on (scrolled
     * to, or found to have no row here) - never again for that same value.
     * `MainActivity` uses this to clear its own copy of the target, bug
     * audit 2026-09-27 finding #4: without it, a manual reopen of Settings
     * later scrolled to the same place again, because `initialSection`
     * itself never changed.
     */
    onSectionConsumed: () -> Unit = {},
    /**
     * The "hey Jarvis" switches (turn it on or off, Listen on this phone,
     * interrupting, "One moment", the "I heard you" sound), drawn under Voice.
     * They moved here from Platform checks (settings audit 2026-09-30) and need
     * a desktop, so this is null until one is paired.
     */
    voiceSwitches: (@Composable () -> Unit)? = null,
    /**
     * Opens the Security screen at its "Looking at your screen" switch, from
     * Picture mode (which also needs it). Null hides the button.
     */
    onOpenLookSwitch: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val jumpScope = rememberCoroutineScope()
    // The same gate every other write on this screen already uses
    // (Manner/WebSearch/AsksFirst/WatchNotify all take it) - rule 4.
    val canAct = link == LinkState.CONNECTED && !stale
    val listState = rememberLazyListState()

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Settings", onBack)

        LaunchedEffect(initialSection) {
            val section = initialSection ?: return@LaunchedEffect
            val index = SETTINGS_ITEM_INDEX[section]
            if (index != null) listState.animateScrollToItem(index)
            onSectionConsumed()
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = listState,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item(key = "jump-list") {
                SettingsJumpList { key ->
                    jumpIndex(key)?.let { i -> jumpScope.launch { listState.animateScrollToItem(i) } }
                }
            }

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
                        Gap(8)
                        // Android 17 (docs/JARVIS-API.md section 81.3): Jarvis
                        // already plays its answers as assistant sound
                        // (audio/Speaker.kt, USAGE_ASSISTANT), which Android 17
                        // gives its own volume slider. Nothing to switch on.
                        Text(
                            ASSISTANT_VOLUME_LINE,
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo,
                        )
                    }
                    // "Hey Jarvis" and how this phone listens: moved here from
                    // Platform checks, next to the other voice settings.
                    voiceSwitches?.let {
                        Gap(12)
                        it()
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
                            "Theme, the reactor's face, the animal options, and how it all looks.",
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

            item(key = "floating-avatar") {
                FloatingAvatarSection(
                    mode = floatingAvatar,
                    onModeChange = onFloatingAvatarChange,
                    overlayGranted = overlayGranted,
                    onRequestOverlay = onRequestOverlay,
                    onOpenBubbleSettings = onOpenBubbleSettings,
                )
            }

            // The seven sections moved whole from Brain's old "Settings"
            // group - see this file's own doc comment.
            item(key = "manner") { MannerSection(canAct = canAct) }
            item(key = "web-search") { WebSearchSection(canAct = canAct) }
            item(key = "asks-first") { AsksFirstSection(canAct = canAct) }
            item(key = "reach") { ReachSection() }
            item(key = "email-sending") { EmailSendingSection() }
            item(key = "folders") { FoldersSection() }
            item(key = "backup") { BackupSection() }
            item(key = "watch-notify") { WatchNotifySection(canAct = canAct) }
            item(key = "phone-notify") {
                PhoneNotificationsSection(
                    canAct = canAct,
                    notificationAccessGranted = notificationAccessGranted,
                    onOpenNotificationAccess = onOpenNotificationAccess,
                )
            }

            // Picture mode for "Look at this" and "Watch with me" (the owner's
            // decision of 2026-09-29): a slow picture model on the PC's processor.
            item(key = "screen-look") {
                ScreenPictureSection(canAct = canAct, onOpenLookSwitch = onOpenLookSwitch)
            }

            // The headless browser, Obscura (the owner's decision of 2026-09-29):
            // Jarvis may choose a browser with no window for plain reading.
            item(key = "browser-engine") { BrowserEngineSection(canAct = canAct) }

            // Every device with its own key (docs/PAIRING-DESIGN.md section 7.2),
            // shown only when the PC reports pairing (section 5.5).
            item(key = "devices") {
                val version by com.jarvis.client.JarvisRuntime.version.collectAsState()
                if (version?.can("pairing") == true) {
                    DevicesSection()
                } else {
                    Section("Devices") {
                        Plate {
                            Text(
                                com.jarvis.client.net.Devices.MISSING,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }

            item(key = "quick-tiles") {
                QuickTilesSection(tiles = quickTiles, onChange = onQuickTileChange)
            }

            item(key = "tail") { Gap(24) }
        }
    }
}

/**
 * "Jump to:" - one small button per section, wrapped over as many lines as it
 * needs, like the desktop's list. A tap scrolls the screen to that section
 * ([SettingsJump.ENTRIES]); it changes nothing.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SettingsJumpList(onJump: (String) -> Unit) {
    val chrome = LocalChrome.current
    Section(SettingsJump.TITLE) {
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            SettingsJump.ENTRIES.forEach { e ->
                Quiet(e.label, onClick = { onJump(e.key) })
            }
        }
        Text(
            "Chat history, saved facts and background learning are in Brain, not here.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}
