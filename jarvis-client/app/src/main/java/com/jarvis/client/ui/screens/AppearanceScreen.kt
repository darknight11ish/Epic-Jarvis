package com.jarvis.client.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.client.FaceState
import com.jarvis.client.data.EdgePref
import com.jarvis.client.data.FaceSize
import com.jarvis.client.data.Look
import com.jarvis.client.data.LookPreset
import com.jarvis.client.data.MotionPref
import com.jarvis.client.data.calmFace
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceThumbnail
import com.jarvis.client.face.FaceView
import com.jarvis.client.face.Faces
import com.jarvis.client.face.Pattern
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.Chrome
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii
import com.jarvis.client.ui.theme.Themes
import kotlinx.coroutines.delay
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * How long the Undo notice after Randomise or Reset stays up. The desktop is
 * only sent the new colours once it closes, so a roll the owner did not like
 * never reaches the other screen at all.
 */
private const val UNDO_WINDOW_MS = 10_000L

/**
 * Appearance — the theme, the look, the face and the state colours.
 *
 * Named "Look" until docs/UI-AUDIT-2026-09-18.md choice A1: a word from
 * outside the app's own vocabulary is exactly the "'Look' is not a word
 * anyone would guess means 'appearance settings'" finding that section
 * names. The screen and its nav entry are renamed together. ("Look" is back,
 * but only as the name of the preset card, where it sits under the heading
 * "On this phone" and next to Focus, Night and the rest - it names a thing
 * on the screen rather than the screen.)
 *
 * Split into two groups, and it says which is which. This screen used to end
 * with "Nothing here is sent anywhere", which stopped being true when
 * `/api/appearance` sync landed: picking a face, Randomise and Reset all post
 * the face and the state colours to the desktop, and a change made there
 * comes back here (the audit's custom-9). So:
 *
 * - **On this phone**: theme, look preset, Home layout, glow, motion, density,
 *   shape, text size. Stored in [com.jarvis.client.data.AppearanceStore] and
 *   never in its sync document.
 * - **Shared with your desktop**: the face and the state colours - a shared
 *   vocabulary rather than a taste, because a phone whose `thinking` is violet
 *   while the desktop's is green has learned a private language. When the
 *   backend lacks the `appearance` capability [desktopSyncs] is false and the
 *   group says, in words, that it is not synced yet.
 *
 * Nothing here edits the desktop's configuration. The phone's rule against
 * deep config editing is about the backend; every control on this screen is
 * a paint choice.
 */
@Composable
fun AppearanceScreen(
    current: Chrome,
    followSystem: Boolean,
    face: Face,
    bindings: Bindings,
    onPickTheme: (Chrome) -> Unit,
    onFollowSystem: (Boolean) -> Unit,
    onPickFace: (Face) -> Unit,
    onRandomise: () -> Unit,
    onResetBindings: () -> Unit,
    /** How big the face is drawn on Home. Stored on this phone only. */
    faceSize: FaceSize = FaceSize.DEFAULT,
    onPickFaceSize: (FaceSize) -> Unit = {},
    onBack: () -> Unit,
    /** What the store refused, e.g. "one theme change at a time". Null hides it. */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    modifier: Modifier = Modifier,
    /** Everything else about this phone's look. See [Look]. */
    look: Look = Look(),
    /** A fine control changed. The whole new record, ready for `AppearanceStore.setLook`. */
    onLookChange: (Look) -> Unit = {},
    /** A preset was tapped, including "Back to X". The store decides whether the theme may change now. */
    onApplyPreset: (LookPreset) -> Unit = {},
    /** The theme Follow the system uses when the phone is dark. */
    preferredDark: Chrome = if (current.dark) current else Themes.DEFAULT,
    /**
     * A theme picked from the "Theme for dark mode" list shown while
     * following the system. Should set the preferred dark theme and leave
     * following ON. Defaults to [onPickTheme], which is what this list did
     * before it existed.
     */
    onPickDarkTheme: (Chrome) -> Unit = onPickTheme,
    /** Whether the desktop takes the shared part: the backend's `appearance` capability. */
    desktopSyncs: Boolean = true,
    /**
     * The Undo window after Randomise or Reset has closed - by running out,
     * by Undo, or by leaving this screen. This is when the state colours
     * should be pushed to the desktop, and not before.
     */
    onBindingsSettled: () -> Unit = {},
    /**
     * Undo: put these bindings back. They are what the store held before the
     * roll. Null - the default - offers no Undo at all, because an Undo button
     * wired to nothing would be a control that lies; that is also the only
     * safe default while the caller still pushes to the desktop straight away.
     */
    onUndoBindings: ((Bindings) -> Unit)? = null,
    /**
     * One cell of the face picker. Null keeps the name-only chips.
     *
     * The placeholder for the still-picture picker (visual-11, "specimen
     * cards"): pass a composable that draws a still frame of the face - never
     * a live one, see the ONE-live-preview note below - and calls onClick when
     * tapped. It is laid out three to a row, each cell the same width.
     */
    faceTile: (@Composable (face: Face, selected: Boolean, onClick: () -> Unit) -> Unit)? = null,
) {
    val chrome = LocalChrome.current

    // Cycle states: steps the one live preview through all eight states every
    // four seconds, so picking colours doesn't mean tapping through them by
    // hand. Ported from the reactor kit's solo view, where the same toggle
    // sits next to its speed slider - this screen has no speed slider, so it
    // sits with the preview itself instead.
    //
    // Reset on picking a different face, matching the kit's "resets to off
    // whenever you open a new face": done at the pick site below, not via a
    // LaunchedEffect keyed on face.id, so it is one direct write rather than
    // two effects racing to agree on whose reset wins.
    var cyclingStates by remember { mutableStateOf(false) }
    var previewState by remember { mutableStateOf(FaceState.IDLE) }
    LaunchedEffect(cyclingStates) {
        if (!cyclingStates) return@LaunchedEffect
        val states = FaceState.entries
        while (true) {
            delay(4_000)
            val next = (states.indexOf(previewState) + 1) % states.size
            previewState = states[next]
        }
    }
    val pickFace: (Face) -> Unit = { picked ->
        cyclingStates = false
        previewState = FaceState.IDLE
        onPickFace(picked)
    }

    // Undo for Randomise and Reset (custom-10). Every roll used to overwrite
    // the desktop's colours at once with no way back, so a combination the
    // owner liked was lost on both screens by one more tap.
    //
    // `undoTo` is what the store held just before the last roll. While it is
    // set, the new colours exist only on this phone; [onBindingsSettled] -
    // the push to the desktop - runs once the window closes, whichever way it
    // closes. A second roll inside the window moves `undoTo` to the colours
    // just before THAT roll and restarts the clock, so there is still exactly
    // one push, of whatever the owner ended up with.
    //
    // Held in `remember`, not saved: a rotation ends the window early through
    // the dispose path below, which pushes. Losing an Undo is the safe way
    // round; losing the push would leave the desktop silently out of step.
    var undoTo by remember { mutableStateOf<Bindings?>(null) }
    var undoMessage by remember { mutableStateOf("") }
    val settle by rememberUpdatedState(onBindingsSettled)
    LaunchedEffect(undoTo) {
        if (undoTo == null) return@LaunchedEffect
        delay(UNDO_WINDOW_MS)
        settle()
        undoTo = null
    }
    DisposableEffect(Unit) {
        onDispose {
            if (undoTo != null) settle()
        }
    }
    val roll: (String, () -> Unit) -> Unit = { message, action ->
        undoTo = bindings
        undoMessage = message
        action()
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Appearance", onBack)

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            // ------------------------------------------------ On this phone --

            item(key = "group-phone") {
                GroupHeader(
                    "On this phone",
                    "Only how this phone looks. None of it is sent to your desktop, " +
                        "and none of it changes your desktop's settings.",
                )
            }

            item(key = "look") {
                Section("Look") {
                    Plate {
                        val custom = look.isCustom(current.id)
                        Text(
                            look.label(current.id),
                            style = MaterialTheme.typography.bodyLarge,
                            color = chrome.textHi,
                        )
                        Gap(2)
                        Text(
                            if (custom) {
                                "You changed something below. The preset it started " +
                                    "from is kept, so you can go back to it."
                            } else {
                                look.basedOn.blurb
                            },
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        Gap(10)
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            LookPreset.entries.chunked(2).forEach { pair ->
                                Row(
                                    Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    pair.forEach { preset ->
                                        OptionChip(
                                            label = preset.label,
                                            isSelected = !custom && preset == look.basedOn,
                                            modifier = Modifier.weight(1f),
                                            onClick = { onApplyPreset(preset) },
                                        )
                                    }
                                }
                            }
                        }
                        if (custom) {
                            Gap(4)
                            Quiet(
                                "Back to ${look.basedOn.label}",
                                onClick = { onApplyPreset(look.basedOn) },
                            )
                        }
                        Gap(6)
                        Text(
                            "Night and Outdoor also pick a theme, and turn off " +
                                "Follow the system.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            // Above the theme list now, not below it: whether the list means
            // "the theme" or "the theme for dark mode" depends on this switch,
            // so it has to be read first.
            item(key = "system") {
                Plate {
                    SwitchRow(
                        title = "Follow the system",
                        detail = "Daylight when the phone is light, your dark theme when it is dark. " +
                            "A switch is held until Jarvis is resting, never mid-approval.",
                        checked = followSystem,
                        onChange = onFollowSystem,
                    )
                }
            }

            item(key = "themes") {
                // While following, this list picks the theme for dark mode
                // (custom-8). Daylight is left out of it, because Daylight is
                // what light mode uses and is never "the theme for dark mode".
                // Picking here keeps following on; picking from the full list
                // with following off is the deliberate one-theme-always choice.
                val shown = if (followSystem) Themes.ALL.filter { it.dark } else Themes.ALL
                Section(if (followSystem) "Theme for dark mode" else "Theme") {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        shown.forEach { theme ->
                            ThemeRow(
                                theme = theme,
                                isSelected = if (followSystem) {
                                    theme.id == preferredDark.id
                                } else {
                                    theme.id == current.id
                                },
                                // Never disabled on the dwell. A control that
                                // greys out for half a second reads as broken,
                                // and the store refuses the change anyway — the
                                // notice explains it in words instead.
                                enabled = true,
                                onClick = {
                                    if (followSystem) onPickDarkTheme(theme) else onPickTheme(theme)
                                },
                            )
                        }
                        if (followSystem) {
                            Text(
                                "Daylight is used while the phone is in light mode. To keep " +
                                    "one theme all day, turn off Follow the system.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                }
            }

            item(key = "accent") {
                Section("Accent") {
                    Plate {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier
                                    .size(28.dp)
                                    .clip(CircleShape)
                                    .background(LocalAccent.current),
                            )
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "Follows your Idle colour",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = chrome.textHi,
                                )
                                Gap(2)
                                // There is deliberately no accent picker. The
                                // accent is a function of the bindings, which is
                                // what stops the chrome ever disagreeing with the
                                // face about what colour Jarvis is.
                                Text(
                                    "Not a separate setting: the caret, focus ring and " +
                                        "selection take the face's idle colour, stepped until " +
                                        "it is legible on this theme.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textMid,
                                )
                            }
                        }
                    }
                }
            }

            item(key = "home-layout") {
                Section("Home layout") {
                    Plate {
                        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            val share = (look.faceFraction * 100).roundToInt()
                            Setting(
                                title = "Face share of Home · $share%",
                                caption = "How much of Home the face's panel takes. Dragging " +
                                    "the handle on Home sets this too.",
                            ) {
                                Choices(
                                    options = FACE_SHARES,
                                    isSelected = { near(it, look.faceFraction) },
                                    label = { "${(it * 100).roundToInt()}%" },
                                    onPick = { onLookChange(look.copy(faceFraction = it)) },
                                )
                            }
                            Setting(
                                title = "Face size on Home",
                                caption = "Extra large fills the face's panel. Full screen is for " +
                                    "talking: just Jarvis and the microphone, and the chat comes " +
                                    "back on its own when something needs you. Both use more " +
                                    "battery than Large. Hidden takes Jarvis off Home entirely " +
                                    "and gives the chat the whole screen.",
                            ) {
                                // Rows of three: five options in one row leaves too
                                // little room for "Extra large" at normal text size,
                                // let alone at 200%.
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    FaceSize.entries.chunked(3).forEach { row ->
                                        Choices(
                                            options = row,
                                            isSelected = { it == faceSize },
                                            label = { it.label },
                                            onPick = onPickFaceSize,
                                        )
                                    }
                                }
                            }
                            Setting(title = "Tabs row") {
                                Choices(
                                    options = listOf(false, true),
                                    isSelected = { it == look.navAlwaysShown },
                                    label = { if (it) "Always shown" else "Hidden until swiped" },
                                    onPick = { onLookChange(look.copy(navAlwaysShown = it)) },
                                )
                            }
                            // Not a setting, on purpose, and said here so its
                            // absence from this list does not read as an
                            // oversight. The status line is how rule 4 shows
                            // on screen: without it, Home would show old data
                            // without saying so.
                            Text(
                                "The status line at the top of Home is always shown. It is how " +
                                    "Jarvis tells you the link is down or out of date, so it " +
                                    "cannot be turned off.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textLo,
                            )
                            Column {
                                SwitchRow(
                                    title = "Make room for approvals",
                                    detail = "Shrinks the face while something is waiting for you, " +
                                        "so Approve and Deny are on screen. It never decides anything.",
                                    checked = look.makeRoomForApprovals,
                                    onChange = { onLookChange(look.copy(makeRoomForApprovals = it)) },
                                )
                                SwitchRow(
                                    title = "Shrink the face while typing",
                                    detail = null,
                                    checked = look.shrinkWhileTyping,
                                    onChange = { onLookChange(look.copy(shrinkWhileTyping = it)) },
                                )
                                SwitchRow(
                                    title = "Follow the reply",
                                    detail = "Keeps the newest words of a reply in view as they arrive.",
                                    checked = look.followReply,
                                    onChange = { onLookChange(look.copy(followReply = it)) },
                                )
                            }
                            Setting(title = "Tapping the face") {
                                Choices(
                                    options = listOf(true, false),
                                    isSelected = { it == look.tapFaceOpensMind },
                                    label = { if (it) "Opens Mind" else "Does nothing" },
                                    onPick = { onLookChange(look.copy(tapFaceOpensMind = it)) },
                                )
                            }
                        }
                    }
                }
            }

            item(key = "adjust") {
                Section("Adjust") {
                    Plate {
                        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            Setting(
                                title = "Glow",
                                caption = "A share of the theme's own glow. It can only dim it, " +
                                    "never brighten it.",
                            ) {
                                Choices(
                                    options = GLOWS,
                                    isSelected = { near(it, look.glow) },
                                    label = { "${(it * 100).roundToInt()}%" },
                                    onPick = { onLookChange(look.copy(glow = it)) },
                                )
                            }
                            // Full is not offered. See MotionPref: the only thing
                            // it could add is overriding the phone's own request
                            // for less motion, and these settings only reduce.
                            // A stored FULL shows as Follow phone, which is how
                            // every reader treats it.
                            Setting(
                                title = "Motion",
                                caption = "Calm slows the face down. Nothing here speeds anything up.",
                            ) {
                                Choices(
                                    options = listOf(MotionPref.FOLLOW, MotionPref.CALM),
                                    isSelected = {
                                        it == look.motion ||
                                            (it == MotionPref.FOLLOW && look.motion == MotionPref.FULL)
                                    },
                                    label = { it.label },
                                    onPick = { onLookChange(look.copy(motion = it)) },
                                )
                            }
                            Setting(title = "Spacing") {
                                Choices(
                                    options = listOf(false, true),
                                    isSelected = { it == look.compact },
                                    label = { if (it) "Compact" else "Comfortable" },
                                    onPick = { onLookChange(look.copy(compact = it)) },
                                )
                            }
                            Setting(title = "Corners") {
                                Choices(
                                    options = listOf(false, true),
                                    isSelected = { it == look.sharp },
                                    label = { if (it) "Sharp" else "Rounded" },
                                    onPick = { onLookChange(look.copy(sharp = it)) },
                                )
                            }
                            Setting(
                                title = "Text size",
                                caption = "100% follows your phone's own text size. The others are " +
                                    "a step up or down from it.",
                            ) {
                                Choices(
                                    options = TEXT_SCALES,
                                    isSelected = { near(it, look.textScale) },
                                    label = { "${(it * 100).roundToInt()}%" },
                                    onPick = { onLookChange(look.copy(textScale = it)) },
                                )
                            }
                            Setting(title = "Panel edges") {
                                Choices(
                                    options = EdgePref.entries,
                                    isSelected = { it == look.edges },
                                    label = { it.label },
                                    onPick = { onLookChange(look.copy(edges = it)) },
                                )
                            }
                            Setting(
                                title = "Screen transitions",
                                caption = "Always off when the phone asks for less animation.",
                            ) {
                                Choices(
                                    options = listOf(true, false),
                                    isSelected = { it == look.transitions },
                                    label = { if (it) "Standard" else "Off" },
                                    onPick = { onLookChange(look.copy(transitions = it)) },
                                )
                            }
                        }
                    }
                }
            }

            // ------------------------------------- Shared with your desktop --

            item(key = "group-shared") {
                GroupHeader(
                    "Shared with your desktop",
                    if (desktopSyncs) {
                        "The face and the state colours are sent to your desktop, and a " +
                            "change made there shows up here too. Nothing else on this " +
                            "screen leaves the phone."
                    } else {
                        "Not synced: your desktop doesn't support it yet. For now the face " +
                            "and the state colours stay on this phone."
                    },
                )
            }

            item(key = "face") {
                Section("Face") {
                    Plate {
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            // ONE live preview, not six.
                            //
                            // limits.flash.scope_why records the exact bug a grid
                            // of live reactors caused: twenty faces with twenty
                            // clocks fed one window, spent the budget on
                            // cross-surface transitions, then held one face's
                            // colour on another. A picker must give each face its
                            // own governor — and a phone can afford one animated
                            // surface, so it gets one.
                            FaceView(
                                state = previewState,
                                face = face,
                                bindings = bindings,
                                notches = 0,
                                modifier = Modifier.size(160.dp),
                                // So this preview matches what Home actually
                                // shows for the theme being looked at right
                                // now, rather than always the same near-black.
                                background = chrome.well,
                                // The same glow and pace Home uses, so moving
                                // the Glow or Motion control shows its effect
                                // here instead of only after going back to
                                // Home. Both can only dim and slow the face.
                                glow = chrome.postScale * look.glow,
                                calmMotion = look.motion.calmFace(LocalMotion.current.reduced),
                            )
                        }
                        Gap(8)
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            CycleStatesChip(
                                active = cyclingStates,
                                previewing = previewState,
                                onClick = { cyclingStates = !cyclingStates },
                            )
                        }
                        Gap(12)
                        // The still-picture picker goes here: see [faceTile].
                        // Until something passes one, the name-only chips stay.
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Faces.all.chunked(3).forEach { row ->
                                Row(
                                    Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    row.forEach { f ->
                                        if (faceTile != null) {
                                            Box(Modifier.weight(1f)) {
                                                faceTile(f, f.id == face.id, { pickFace(f) })
                                            }
                                        } else {
                                            FaceChip(f, f.id == face.id) { pickFace(f) }
                                        }
                                    }
                                    // Keep the last row's cells the same width as
                                    // the rows above, rather than stretching.
                                    if (faceTile != null) {
                                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                                    }
                                }
                            }
                        }
                        Gap(6)
                        Text(
                            // API §6's own rule: the phone's picker shows only the
                            // faces Android actually renders, not all twenty with
                            // most of them missing.
                            //
                            // Counted from the list rather than written out. This
                            // line said "Six" while Faces.all held eight: adding a
                            // face is one edit, and prose is not something a drift
                            // test can check, so the caption told the owner a
                            // number contradicted by the grid directly above it.
                            //
                            // The seven that looked stateful (spectrum, coreplate,
                            // workbench, swarm, shoal, accretion, cascade) turned
                            // out portable without a shader or new state
                            // machinery. Nucleus needed a real GPU fragment
                            // shader (AGSL) and got one. Tokamak and membrane
                            // needed more than that - a real OpenGL mesh, GLES
                            // 3.0, with membrane's own live physics step run on
                            // top of it - and both got that too. All twenty are
                            // offered now, which is why this caption stopped
                            // explaining a gap: there isn't one left to explain.
                            //
                            // Still counted rather than written as a bare
                            // "Twenty", for the same reason the "Six" bug
                            // happened in the first place - if a face is ever
                            // archived or the desktop's own count changes, this
                            // sentence is prose a drift test cannot check, and
                            // it is the number that has to stay honest, not the
                            // word "twenty" next to it.
                            "All ${Faces.all.size} of the desktop's twenty faces render here now " +
                                "- line and stroke art, one GPU shader, and a real OpenGL mesh, " +
                                "whichever each one needed.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            item(key = "colours") {
                Section("State colours") {
                    Plate {
                        FaceState.entries.forEach { state ->
                            val binding = bindings.of(state)
                            Row(
                                Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Box(
                                    Modifier
                                        .size(16.dp)
                                        .clip(CircleShape)
                                        .background(
                                            binding.tint ?: chrome.textMid,
                                        )
                                        .then(
                                            if (binding.tint == null) {
                                                Modifier.border(1.dp, chrome.hairlineFocus, CircleShape)
                                            } else {
                                                Modifier
                                            },
                                        ),
                                )
                                Spacer(Modifier.width(12.dp))
                                Text(
                                    state.name.lowercase().replaceFirstChar { it.uppercase() },
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = chrome.textHi,
                                    modifier = Modifier.weight(1f),
                                )
                                // Plain words, not the spec's ids: "sweep" and
                                // "temperature" are jargon to anyone who has not
                                // read the visual spec (custom-10).
                                Pill(plainPattern(binding.pattern))
                            }
                        }
                        Gap(10)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Quiet("Randomise", onClick = { roll("New colours.", onRandomise) })
                            Quiet(
                                "Reset",
                                color = chrome.textMid,
                                onClick = { roll("Colours reset to the defaults.", onResetBindings) },
                            )
                        }
                        // Shown only when the roll actually changed something:
                        // forty tries that found nothing separated enough leave
                        // the colours alone, and Reset on the defaults is a
                        // no-op - an Undo for either would undo nothing.
                        val previous = undoTo
                        val undo = onUndoBindings
                        if (undo != null && previous != null && previous != bindings) {
                            Gap(6)
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .semantics { liveRegion = LiveRegionMode.Polite },
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    undoMessage + if (desktopSyncs) {
                                        " Sent to your desktop when this goes away."
                                    } else {
                                        ""
                                    },
                                    style = MaterialTheme.typography.bodySmall,
                                    color = chrome.textMid,
                                    modifier = Modifier.weight(1f),
                                )
                                Spacer(Modifier.width(8.dp))
                                Quiet(
                                    "Undo",
                                    onClick = {
                                        undo(previous)
                                        settle()
                                        undoTo = null
                                    },
                                )
                            }
                        }
                        Gap(6)
                        Text(
                            // Convention, never randomised. A green alarm is a
                            // design you have to explain.
                            "Approval, error, standby and banked keep their colours. " +
                                "Waiting on you is amber; something wrong is rose.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            item(key = "tail") { Gap(24) }
        }
    }
}

/** Choices for the face's share of Home. 35% and 75% are the presets' own values. */
private val FACE_SHARES = listOf(0.20f, 0.35f, 0.50f, 0.65f, 0.75f, 0.85f)

/** Glow levels. 60% is Night's. Never above 100%: glow only dims. */
private val GLOWS = listOf(0.25f, 0.40f, 0.60f, 0.80f, 1f)

/** Text size, on top of the phone's own. 110% is Outdoor's. */
private val TEXT_SCALES = listOf(0.90f, 1f, 1.10f, 1.20f, 1.30f)

/**
 * Close enough to count as the same choice. A dragged face share is any
 * number at all, so exact equality would light up nothing even when the drag
 * landed on 75% to the eye.
 */
private fun near(a: Float, b: Float): Boolean = abs(a - b) < 0.005f

/** The spec's pattern ids, in words a person would use. Unknown ids fall back to the id. */
private val PLAIN_PATTERN_NAMES: Map<Pattern, String> = mapOf(
    Pattern.SOLID to "Steady",
    Pattern.RAINBOW to "Rainbow",
    Pattern.CYCLE to "Colour steps",
    Pattern.BREATHE to "Slow breath",
    Pattern.PULSE to "Pulse",
    Pattern.GRADIENT to "Two-colour drift",
    Pattern.SWEEP to "Colour sweep",
    Pattern.COMET to "Comet",
    Pattern.FLICKER to "Flicker",
    Pattern.REACTIVE to "Follows the voice",
    Pattern.TEMPERATURE to "Warms up",
    Pattern.STROBE to "Flash",
)

private fun plainPattern(p: Pattern): String = PLAIN_PATTERN_NAMES[p] ?: p.id

/**
 * The two top-level groups, "On this phone" and "Shared with your desktop".
 * Marked as headings so a screen reader can jump between them.
 */
@Composable
private fun GroupHeader(title: String, detail: String) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Text(
            title,
            style = MaterialTheme.typography.titleMedium,
            color = chrome.textHi,
            modifier = Modifier.semantics { heading() },
        )
        Gap(4)
        Text(
            detail,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}

/** One labelled control inside a plate: a title, the control, and an optional line under it. */
@Composable
private fun Setting(
    title: String,
    caption: String? = null,
    content: @Composable () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Text(
            title,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
        )
        Gap(6)
        content()
        if (caption != null) {
            Gap(4)
            Text(
                caption,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
    }
}

/** A row of equal-width [OptionChip]s, exactly one of which is normally selected. */
@Composable
private fun <T> Choices(
    options: List<T>,
    isSelected: (T) -> Boolean,
    label: (T) -> String,
    onPick: (T) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        options.forEach { option ->
            OptionChip(
                label = label(option),
                isSelected = isSelected(option),
                modifier = Modifier.weight(1f),
                onClick = { onPick(option) },
            )
        }
    }
}

/**
 * One choice among several.
 *
 * Told apart by fill as well as colour, and announced as a selected or
 * unselected radio button (a11y-8) rather than as one more "button" - which
 * is all `pressable`'s default role could say, so the chosen option sounded
 * exactly like every other one.
 *
 * The touch-target modifier comes FIRST (a11y-12): placed after the padding
 * it grows the painted pill itself to 48dp; placed first it grows only the
 * area that answers a tap.
 */
@Composable
private fun OptionChip(
    label: String,
    isSelected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.chipShape
    Box(
        modifier
            .minimumInteractiveComponentSize()
            .semantics { selected = isSelected }
            .clip(shape)
            .background(if (isSelected) accent else chrome.surface2)
            .pressable(role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 6.dp, vertical = 9.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = if (isSelected) chrome.surface0 else chrome.textMid,
            textAlign = TextAlign.Center,
        )
    }
}

/**
 * A label and a switch, where the WHOLE row is the control.
 *
 * a11y-8: the switch used to be a separate focus stop with no name - TalkBack
 * read "Switch, off" and then, separately, the words beside it. Now the row
 * is one toggleable with the Switch role, so it is read as "Follow the
 * system, switch, on", and a tap anywhere on the words flips it.
 *
 * visual-11: the drawn switch is this app's own `Toggle` now, not the stock
 * Material one. It is hidden from TalkBack (the row already is the switch)
 * but still answers a finger with the same [onChange]. It is NOT given a
 * no-op callback: the Toggle's own touch area takes the tap before the row
 * sees it, so a no-op there would make the one part that looks like a switch
 * the one part that does nothing.
 */
@Composable
private fun SwitchRow(
    title: String,
    detail: String?,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .toggleable(
                value = checked,
                interactionSource = remember { MutableInteractionSource() },
                // No ripple, like every other control built on `pressable`.
                indication = null,
                role = Role.Switch,
                onValueChange = onChange,
            )
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                title,
                style = MaterialTheme.typography.bodyLarge,
                color = chrome.textHi,
            )
            if (detail != null) {
                Gap(2)
                Text(
                    detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }
        }
        Spacer(Modifier.width(12.dp))
        // This app's own Toggle, in a box that hides it from TalkBack: the
        // row above is already the one switch a screen reader hears, with
        // its name, so the Toggle's own switch node would be a second, nameless
        // stop for the same setting. A finger on the Toggle itself still flips
        // it - semantics are only what TalkBack reads, not what takes touches -
        // and it calls the same `onChange` the row does.
        Box(Modifier.clearAndSetSemantics { }) {
            Toggle(checked = checked, onCheckedChange = onChange)
        }
    }
}

/**
 * A theme row with a STATIC swatch.
 *
 * Static on purpose: a picker showing six live mini-reactors is the
 * cross-surface flash bug the spec already recorded, and six animated canvases
 * is several times the frame budget a phone has.
 *
 * The chosen row is marked three ways, none of them colour alone: a thicker
 * accent border, a drawn check mark (visual-11, replacing a "●" glyph that
 * TalkBack read aloud as a character), and the selected state a screen reader
 * announces (a11y-8).
 */
@Composable
private fun ThemeRow(
    theme: Chrome,
    isSelected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.cardShape
    Row(
        Modifier
            .fillMaxWidth()
            .semantics { selected = isSelected }
            .clip(shape)
            .background(chrome.surface1)
            .border(
                if (isSelected) 1.5.dp else 1.dp,
                if (isSelected) accent else chrome.hairline,
                shape,
            )
            .pressable(enabled = enabled, role = Role.RadioButton, onClick = onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Swatch(theme)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                theme.label,
                style = MaterialTheme.typography.bodyLarge,
                color = chrome.textHi,
            )
            Gap(2)
            Text(
                theme.blurb,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (isSelected) {
            Spacer(Modifier.width(8.dp))
            CheckMark(accent)
        }
    }
}

/**
 * A drawn tick. Two strokes rather than a font glyph, so it looks the same on
 * every phone's font and is never read aloud - the row's selected state says
 * it in words instead.
 */
@Composable
private fun CheckMark(color: Color) {
    Canvas(Modifier.size(18.dp)) {
        val w = size.width
        val h = size.height
        val stroke = 2.dp.toPx()
        val corner = Offset(w * 0.40f, h * 0.74f)
        drawLine(
            color = color,
            start = Offset(w * 0.16f, h * 0.50f),
            end = corner,
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
        drawLine(
            color = color,
            start = corner,
            end = Offset(w * 0.86f, h * 0.24f),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
    }
}

/** Four flat bands: the ground, a card, the text, and the semantic trio. */
@Composable
private fun Swatch(theme: Chrome) {
    Column(
        Modifier
            .size(width = 44.dp, height = 44.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(theme.surface0),
    ) {
        Box(Modifier.fillMaxWidth().height(14.dp).background(theme.surface1))
        Row(Modifier.fillMaxWidth().height(8.dp)) {
            Box(Modifier.weight(1f).fillMaxWidth().background(theme.textHi))
            Box(Modifier.weight(1f).fillMaxWidth().background(theme.textMid))
        }
        Spacer(Modifier.weight(1f))
        Row(Modifier.fillMaxWidth().height(10.dp)) {
            Box(Modifier.weight(1f).fillMaxWidth().background(theme.okMark))
            Box(Modifier.weight(1f).fillMaxWidth().background(theme.warnMark))
            Box(Modifier.weight(1f).fillMaxWidth().background(theme.badMark))
        }
    }
}

/**
 * One face in the still-picture picker (visual-11's "specimen cards"): a
 * still frame of the face on the theme's well, with its name under it. Handed
 * to [AppearanceScreen] as its `faceTile` by MainActivity.
 *
 * Still, never live - see the ONE-live-preview note on the preview above.
 * [FaceThumbnail] draws a single frame and runs no animation loop, so twenty
 * of these are twenty drawings made once, not twenty clocks and twenty flash
 * governors.
 *
 * The chosen face is marked without relying on colour alone: a thicker border
 * (2dp against 1dp) in the accent, the name in the main text colour, and the
 * selected state a screen reader announces (a11y-8). The picture has no
 * description of its own; the name under it is the tile's label.
 */
@Composable
fun FaceSpecimen(
    face: Face,
    bindings: Bindings,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    Column(
        modifier
            .fillMaxWidth()
            .semantics { selected = isSelected }
            .clip(radii.controlShape)
            .border(
                if (isSelected) 2.dp else 1.dp,
                if (isSelected) accent else chrome.hairline,
                radii.controlShape,
            )
            .pressable(role = Role.RadioButton, onClick = onClick)
            .padding(6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        FaceThumbnail(
            face = face,
            bindings = bindings,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .clip(radii.insetShape)
                .background(chrome.well),
            // The same ground Home and the live preview use.
            background = chrome.well,
        )
        Gap(4)
        Text(
            face.name,
            style = MaterialTheme.typography.labelMedium,
            color = if (isSelected) chrome.textHi else chrome.textMid,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/**
 * One face in the name-only picker.
 *
 * a11y-12: `minimumInteractiveComponentSize` used to sit at the END of this
 * chain, innermost, where it grew the text's own box to 48dp before the
 * padding and background wrapped it - so the painted pill came out about
 * 66dp tall, not the ~38dp its comment promised. First in the chain, it
 * grows only the area that answers a tap, and the pill keeps its size.
 */
@Composable
private fun FaceChip(face: Face, isSelected: Boolean, onClick: () -> Unit) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.chipShape
    Text(
        face.name,
        style = MaterialTheme.typography.labelMedium,
        color = if (isSelected) chrome.surface0 else chrome.textMid,
        modifier = Modifier
            .minimumInteractiveComponentSize()
            .semantics { selected = isSelected }
            .clip(shape)
            .background(if (isSelected) accent else chrome.surface2)
            .pressable(role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp),
    )
}

/**
 * Steps the preview above through all eight states on its own, four seconds
 * apart, so trying out colours doesn't mean tapping through them by hand. The
 * label names whichever state is currently showing once running, since that
 * is the one piece of information a glance at the chip cannot otherwise give.
 *
 * An on/off control, so it is announced as a switch with its state in words
 * (a11y-8) rather than as a button whose label happens to change. Touch
 * target first in the chain, for the reason [FaceChip] gives.
 */
@Composable
private fun CycleStatesChip(active: Boolean, previewing: FaceState, onClick: () -> Unit) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.chipShape
    val label = if (active) {
        "Cycling · " + previewing.name.lowercase().replaceFirstChar { it.uppercase() }
    } else {
        "Cycle states"
    }
    Text(
        label,
        style = MaterialTheme.typography.labelMedium,
        color = if (active) chrome.surface0 else chrome.textMid,
        modifier = Modifier
            .minimumInteractiveComponentSize()
            .semantics { stateDescription = if (active) "On" else "Off" }
            .clip(shape)
            .background(if (active) accent else chrome.surface2)
            .pressable(role = Role.Switch, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp),
    )
}
