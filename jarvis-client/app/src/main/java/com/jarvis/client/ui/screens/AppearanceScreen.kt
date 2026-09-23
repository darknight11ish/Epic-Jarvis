package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.jarvis.client.FaceState
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.face.Faces
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.Chrome
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import com.jarvis.client.ui.theme.Themes
import kotlinx.coroutines.delay

/**
 * Appearance — the theme, the face and the state colours.
 *
 * Named "Look" until docs/UI-AUDIT-2026-09-18.md choice A1: a word from
 * outside the app's own vocabulary is exactly the "'Look' is not a word
 * anyone would guess means 'appearance settings'" finding that section
 * names. The screen and its nav entry are renamed together.
 *
 * Per device, and it says so. There is no route in the contract that syncs a UI
 * preference (`POST /api/config` is 501 by design, and none of the 38 endpoints
 * reads or writes one), so this does not pretend to sync. The *bindings* are
 * the part that should eventually — they are a shared vocabulary rather than a
 * taste, and a phone whose `thinking` is violet while the desktop's is green
 * has learned a private language. That needs a backend route first.
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
    onBack: () -> Unit,
    /** What the store refused, e.g. "one theme change at a time". Null hides it. */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    modifier: Modifier = Modifier,
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

            item(key = "themes") {
                Section("Theme") {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Themes.ALL.forEach { theme ->
                            ThemeRow(
                                theme = theme,
                                selected = theme.id == current.id,
                                // Never disabled on the dwell. A control that
                                // greys out for half a second reads as broken,
                                // and the store refuses the change anyway — the
                                // notice explains it in words instead.
                                enabled = true,
                                onClick = { onPickTheme(theme) },
                            )
                        }
                    }
                }
            }

            item(key = "system") {
                Plate {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Follow the system",
                                style = MaterialTheme.typography.bodyLarge,
                                color = chrome.textHi,
                            )
                            Gap(2)
                            Text(
                                "Daylight when the phone is light, your dark theme when it is dark. " +
                                    "A switch is held until Jarvis is resting, never mid-approval.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Switch(
                            checked = followSystem,
                            onCheckedChange = onFollowSystem,
                            colors = SwitchDefaults.colors(
                                checkedTrackColor = LocalAccent.current.copy(alpha = 0.45f),
                                checkedThumbColor = LocalAccent.current,
                                uncheckedBorderColor = chrome.hairlineFocus,
                            ),
                        )
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
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Faces.all.chunked(3).forEach { row ->
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    row.forEach { f ->
                                        FaceChip(f, f.id == face.id) { pickFace(f) }
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
                                Pill(binding.pattern.id)
                            }
                        }
                        Gap(10)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Quiet("Randomise", onClick = onRandomise)
                            Quiet("Reset", color = chrome.textMid, onClick = onResetBindings)
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

            item(key = "note") {
                Text(
                    "These are stored on this phone only. Nothing here is sent anywhere.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
            }

            item(key = "tail") { Gap(24) }
        }
    }
}

/**
 * A theme row with a STATIC swatch.
 *
 * Static on purpose: a picker showing six live mini-reactors is the
 * cross-surface flash bug the spec already recorded, and six animated canvases
 * is several times the frame budget a phone has.
 */
@Composable
private fun ThemeRow(
    theme: Chrome,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.cardShape
    Row(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(chrome.surface1)
            .border(
                if (selected) 1.5.dp else 1.dp,
                if (selected) accent else chrome.hairline,
                shape,
            )
            .pressable(enabled = enabled, onClick = onClick)
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
        if (selected) {
            Spacer(Modifier.width(8.dp))
            Text("●", style = MaterialTheme.typography.labelMedium, color = accent)
        }
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

@Composable
private fun FaceChip(face: Face, selected: Boolean, onClick: () -> Unit) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val shape = LocalRadii.current.chipShape
    Text(
        face.name,
        style = MaterialTheme.typography.labelMedium,
        color = if (selected) chrome.surface0 else chrome.textMid,
        modifier = Modifier
            .clip(shape)
            .background(if (selected) accent else chrome.surface2)
            .pressable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp)
            // The visible pill stays this size; the touch target grows
            // around it to the 48dp platform minimum. Measured at ~38dp
            // without this - twenty of these sit in a grid on this screen.
            .minimumInteractiveComponentSize(),
    )
}

/**
 * Steps the preview above through all eight states on its own, four seconds
 * apart, so trying out colours doesn't mean tapping through them by hand. The
 * label names whichever state is currently showing once running, since that
 * is the one piece of information a glance at the chip cannot otherwise give.
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
            .clip(shape)
            .background(if (active) accent else chrome.surface2)
            .pressable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp)
            .minimumInteractiveComponentSize(),
    )
}
