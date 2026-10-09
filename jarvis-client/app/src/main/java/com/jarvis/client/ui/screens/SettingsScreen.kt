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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.ui.MenuPlaces
import com.jarvis.client.ui.parts.ScrollToKeyOnce
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
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
 * Every `item(key = ...)` below, by its position in the `LazyColumn` with
 * nothing hidden - kept as one small map rather than computed, so a
 * reordering of the items below is a visible two-line diff here too, not a
 * silent mismatch. Nothing scrolls by these numbers: "Open <a settings
 * section>" (docs/JARVIS-API.md section 58.1) and the "Jump to:" list both go
 * BY KEY, because a hidden menu shifts every item below it. OpenPlaceTest and
 * `backend/test_settings_registry.py` read this map as the record of which
 * rows exist, and `SettingsJumpTest` holds it to their real order.
 *
 * Bug audit 2026-09-27: this went stale the moment "floating-avatar" was
 * inserted at position 3 by a concurrent piece of work - every index from
 * "manner" down was one item too early, unnoticed because the merge that
 * combined both pieces of work was a clean auto-merge with no text
 * conflict here. Fixed by re-reading the real `item(key = ...)` order
 * below rather than hand-adjusting the old numbers.
 *
 * UI audit 2026-10-05 (finding A3): the "Jump to:" handler was the last
 * reader of these numbers, so with Voice hidden - `settings.voice` is
 * hideable - "What asks first" landed on "What Jarvis can reach". It now
 * scrolls to [SettingsJump.key] like the voice-and-chat jumps always have.
 */
private val SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(
    "voice" to 1,
    "security" to 2,
    // "Show or hide menus" (docs/JARVIS-API.md section 109) sits right after Security.
    "menu-visibility" to 3,
    "appearance-card" to 4,
    // "Animal options" lives inside Appearance on the phone (2026-09-28):
    // the Appearance row, whose button opens it.
    "animal-options" to 4,
    "floating-avatar" to 5,
    "manner" to 6,
    "web-search" to 7,
    // "Prompt coach" (docs/JARVIS-API.md section 119) sits right after Web search.
    "prompt-coach" to 8,
    "asks-first" to 9,
    "reach" to 10,
    "email-sending" to 11,
    "folders" to 12,
    "backup" to 13,
    "watch-notify" to 14,
    "phone-notify" to 15,
    "screen-look" to 16,
    "browser-engine" to 17,
    // How long the captcha hand-off stays on offer (the owner's decision of
    // 2026-10-08). Sits with the browser it belongs to, so the two exposure
    // rows are together; every index below it moved down by one on that day.
    "handoff" to 18,
    "devices" to 19,
    "quick-tiles" to 20,
    // "Limits and how often Jarvis does things" (the PC's own
    // backend/jarvis_limits.py table, 2026-10-08; LimitsPlate.kt) sits last:
    // it is about how much Jarvis does rather than about one feature.
    "limits" to 21,
)

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
     * `item(key = ...)` rows too, listed in [SETTINGS_ITEM_INDEX] like every
     * other row, so an id naming one of them scrolls to it like any other
     * section - it does not fall into that no-op case.
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
    // The same gate every other write on this screen already uses
    // (Manner/WebSearch/AsksFirst/WatchNotify all take it) - rule 4.
    val canAct = link == LinkState.CONNECTED && !stale
    val listState = rememberLazyListState()
    // Which menus this phone has hidden or folded ("Show or hide menus"). A link that opened a
    // hidden one shows it for THIS visit only; leaving the screen ends the visit.
    val menus by JarvisRuntime.menus.view.collectAsState()
    DisposableEffect(Unit) { onDispose { JarvisRuntime.menus.endVisit() } }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Settings", onBack)

        // Scrolls BY KEY, not by position: a hidden menu (docs/JARVIS-API.md section 109) moves
        // every item below it, so SETTINGS_ITEM_INDEX above is only a record of the
        // rows that exist (OpenPlaceTest and backend/test_settings_registry.py read it).
        val target = initialSection?.let { MenuPlaces.SETTINGS_ALIAS[it] ?: it }
        val known = target != null && target in MenuPlaces.SETTINGS.keys
        ScrollToKeyOnce(listState, if (known) target else null, onDone = onSectionConsumed)
        LaunchedEffect(initialSection, known) {
            // An id newer than this app has no row here: nothing to scroll to, but it is done.
            if (initialSection != null && !known) onSectionConsumed()
        }
        // "3 hidden - Show" jumps to the list below.
        var jumpTo by remember { mutableStateOf<String?>(null) }
        // Bumped on every tap and handed to ScrollToKeyOnce as `tick`: returning
        // to the SAME row after scrolling away - tapping "Voice" again from the
        // bottom of the screen - is a new value for the effect, so the second
        // tap scrolls instead of doing nothing. 0 while idle, so nothing runs
        // on opening the screen.
        var jumpTick by remember { mutableIntStateOf(0) }
        ScrollToKeyOnce(listState, jumpTo, tick = jumpTick) { jumpTo = null }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = listState,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item(key = "jump-list") {
                if (menus.hiddenCount > 0) {
                    HiddenMenusLine(menus.hiddenCount) {
                        jumpTo = "menu-visibility"
                        jumpTick += 1
                    }
                    Gap(12)
                }
                SettingsJumpList { key ->
                    // BY KEY, like every other jump on this screen - a hidden
                    // menu above this one shifts every item below it, so the
                    // old `animateScrollToItem(jumpIndex(key))` quietly landed
                    // on a DIFFERENT panel: with Voice hidden, "What asks first"
                    // stopped on "What Jarvis can reach" and said nothing
                    // (UI audit 2026-10-05, finding A3). The comment at the top
                    // of this screen has promised BY KEY since 2026-09-30; this
                    // is the handler that had not been changed with it. A key
                    // that is not drawn - the owner hid that very menu - now
                    // scrolls nowhere instead of somewhere wrong.
                    jumpTo = key
                    jumpTick += 1
                }
            }

            if (menus.shows("settings.voice")) item(key = "voice") {
                MenuFrame(menus, "settings.voice") {
                    Section("Voice") {
                        Plate {
                            Text(
                                "Whether Jarvis knows your voice, how strict that check is, and " +
                                    "the voice Jarvis answers in.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                            val voiceCheck = onVoiceCheck?.takeIf { menus.shows("entry.voice-check") }
                            val voices = onVoices?.takeIf { menus.shows("entry.voices") }
                            val any = onTrainVoice != null || voiceCheck != null || voices != null
                            if (any) Gap(10)
                            onTrainVoice?.let {
                                Secondary("Train my voice", modifier = Modifier.fillMaxWidth(), onClick = it)
                                Gap(8)
                            }
                            voiceCheck?.let {
                                Secondary(
                                    "Voice check: how strict, private answers",
                                    modifier = Modifier.fillMaxWidth(),
                                    onClick = it,
                                )
                                Gap(8)
                            }
                            voices?.let {
                                Secondary("Jarvis's voice", modifier = Modifier.fillMaxWidth(), onClick = it)
                            }
                            // Not "paired": a row the owner hid is not the same as no desktop.
                            if (onTrainVoice == null && onVoiceCheck == null && onVoices == null) {
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

// "Show or hide menus" (docs/JARVIS-API.md section 109): never hideable itself.
            item(key = "menu-visibility") { MenuVisibilitySection() }

                        if (menus.shows("settings.appearance-card")) item(key = "appearance") {
                MenuFrame(menus, "settings.appearance-card") {
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
            }

            if (menus.shows("settings.floating-avatar")) item(key = "floating-avatar") {
                MenuFrame(menus, "settings.floating-avatar") {
                    FloatingAvatarSection(
                        mode = floatingAvatar,
                        onModeChange = onFloatingAvatarChange,
                        overlayGranted = overlayGranted,
                        onRequestOverlay = onRequestOverlay,
                        onOpenBubbleSettings = onOpenBubbleSettings,
                    )
                }
            }

            // The seven sections moved whole from Brain's old "Settings"
            // group - see this file's own doc comment.
            if (menus.shows("settings.manner")) item(key = "manner") {
                MenuFrame(menus, "settings.manner") {
                    MannerSection(canAct = canAct)
                    Gap(16)
                    ThinkingSection(canAct = canAct)
                }
            }
            if (menus.shows("settings.web-search")) item(key = "web-search") { MenuFrame(menus, "settings.web-search") { WebSearchSection(canAct = canAct) } }
            // "Prompt coach" (docs/PROMPT-COACH-DESIGN.md, docs/JARVIS-API.md section 119):
            // the master switch for the "Coach this" button, off by default,
            // decided on the PC and shown in the PC's own words here.
            if (menus.shows("settings.prompt-coach")) item(key = "prompt-coach") { MenuFrame(menus, "settings.prompt-coach") { PromptCoachSection(canAct = canAct) } }
            item(key = "asks-first") { AsksFirstSection(canAct = canAct) }
            if (menus.shows("settings.reach")) item(key = "reach") { MenuFrame(menus, "settings.reach") { ReachSection() } }
            if (menus.shows("settings.email-sending")) item(key = "email-sending") { MenuFrame(menus, "settings.email-sending") { EmailSendingSection() } }
            if (menus.shows("settings.folders")) item(key = "folders") { MenuFrame(menus, "settings.folders") { FoldersSection() } }
            if (menus.shows("settings.backup")) item(key = "backup") { MenuFrame(menus, "settings.backup") { BackupSection() } }
            if (menus.shows("settings.watch-notify")) item(key = "watch-notify") { MenuFrame(menus, "settings.watch-notify") { WatchNotifySection(canAct = canAct) } }
            if (menus.shows("settings.phone-notify")) item(key = "phone-notify") {
                MenuFrame(menus, "settings.phone-notify") {
                    PhoneNotificationsSection(
                        canAct = canAct,
                        notificationAccessGranted = notificationAccessGranted,
                        onOpenNotificationAccess = onOpenNotificationAccess,
                    )
                }
            }

            // Picture mode for "Look at this" and "Watch with me" (the owner's
            // decision of 2026-09-29): a slow picture model on the PC's processor.
            if (menus.shows("settings.screen-look")) item(key = "screen-look") {
                MenuFrame(menus, "settings.screen-look") {
                    ScreenPictureSection(canAct = canAct, onOpenLookSwitch = onOpenLookSwitch)
                }
            }

            // The headless browser, Obscura (the owner's decision of 2026-09-29):
            // Jarvis may choose a browser with no window for plain reading.
            if (menus.shows("settings.browser-engine")) item(key = "browser-engine") { MenuFrame(menus, "settings.browser-engine") { BrowserEngineSection(canAct = canAct) } }

            // How long the captcha hand-off stays on offer (the owner's own
            // decision of 2026-10-08: "make this a setting for both options with
            // 1 as the default"). "Stop early" is the default; "Keep offering it"
            // is one approval card on the PC with Windows Hello.
            if (menus.shows("settings.handoff")) item(key = "handoff") {
                MenuFrame(menus, "settings.handoff") { HandoffModeSection(canAct = canAct) }
            }

            // Every device with its own key (docs/PAIRING-DESIGN.md section 7.2),
            // shown only when the PC reports pairing (section 5.5).
            if (menus.shows("settings.devices")) item(key = "devices") {
                MenuFrame(menus, "settings.devices") {
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
            }

            if (menus.shows("settings.quick-tiles")) item(key = "quick-tiles") {
                MenuFrame(menus, "settings.quick-tiles") {
                    QuickTilesSection(tiles = quickTiles, onChange = onQuickTileChange)
                }
            }

            // "Limits and how often Jarvis does things" (the PC's own
            // backend/jarvis_limits.py table, 2026-10-08): the limits and
            // frequencies the owner can change, in the PC's own words. It reads
            // and writes through JarvisRuntime directly (LimitsPlate.kt), so
            // this is its only line. Behind `menus.shows("settings.limits")`
            // like every other hideable row: the menu is declared once in
            // backend/jarvis_menus.py and generated into MenuCatalog.kt, and
            // MenuVisibilityTest checks both halves - the place in MenuPlaces
            // and this check in a real screen.
            if (menus.shows("settings.limits")) item(key = "limits") {
                MenuFrame(menus, "settings.limits") { LimitsSection(canAct = canAct) }
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
