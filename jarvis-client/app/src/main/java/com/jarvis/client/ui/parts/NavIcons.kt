package com.jarvis.client.ui.parts

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * Four drawn glyphs, in the shape `VoiceButton`'s own microphone already
 * set the precedent for: composed `Box` shapes, not an icon-font dependency
 * and not a vector path asset. `docs/UI-AUDIT-2026-09-18.md` choice A1 - "no
 * icon font... drawn in-app like the microphone glyph is."
 *
 * All four are drawn inside a 24dp square so a `Row` of them lines up
 * without each icon needing its own size math at the call site.
 */
private val ICON_SIZE = 24.dp

/** State of mind: a bulb - the closest plain shape to "an idea", and this
 *  screen is the one that shows what Jarvis has learned and is holding. */
@Composable
fun MindIcon(tint: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(ICON_SIZE), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .padding(bottom = 6.dp)
                .size(14.dp)
                .clip(CircleShape)
                .border(1.5.dp, tint, CircleShape),
        )
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .size(width = 8.dp, height = 4.dp)
                .clip(RoundedCornerShape(percent = 40))
                .background(tint),
        )
    }
}

/** Inbox: a tray outline with a slot - things waiting to be looked at,
 *  sitting in a container rather than floating loose. */
@Composable
fun InboxIcon(tint: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(ICON_SIZE), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(width = 20.dp, height = 14.dp)
                .clip(RoundedCornerShape(3.dp))
                .border(1.5.dp, tint, RoundedCornerShape(3.dp)),
        )
        Box(
            Modifier
                .size(width = 12.dp, height = 2.dp)
                .background(tint),
        )
    }
}

/** Appearance ("Look"): an aperture - a ring with a bright centre, the same
 *  reading as "how this looks" that the old label's own word implied. */
@Composable
fun AppearanceIcon(tint: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(ICON_SIZE), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(20.dp)
                .clip(CircleShape)
                .border(1.5.dp, tint, CircleShape),
        )
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(tint),
        )
    }
}

/** Help: an "i" - the plain, universal mark for "read more here", not the
 *  question-mark-as-decoration a FAQ page usually reaches for. */
@Composable
fun HelpIcon(tint: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(ICON_SIZE), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .align(Alignment.TopCenter)
                .padding(top = 3.dp)
                .size(3.dp)
                .clip(CircleShape)
                .background(tint),
        )
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 3.dp)
                .size(width = 3.dp, height = 10.dp)
                .clip(RoundedCornerShape(percent = 50))
                .background(tint),
        )
    }
}
