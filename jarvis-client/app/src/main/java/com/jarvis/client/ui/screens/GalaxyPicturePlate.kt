package com.jarvis.client.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.Entities
import com.jarvis.client.net.GalaxyPicture as GalaxyPictureData
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome

/** How tall the picture is: a square-ish picture on a thumb-width plate, tall
 *  enough for a 48-name halo to stay legible. Whether the band and the list
 *  need a scroll on a given phone is a field-test question, not a promise made
 *  here. */
private val PICTURE_HEIGHT = 264.dp

/** Air between the outermost dot and the plate's own edge. */
private val PICTURE_PADDING = 14.dp

/** How far from a dot's edge a finger still counts as touching it. A dot is
 *  only a few dp across, and a thumb is not; the nearest dot within this reach
 *  wins, so two neighbouring names never need pixel-precise aim. */
private val TOUCH_SLACK = 14.dp

/** The touch target laid over each dot for TalkBack. It carries no touch of its
 *  own - a finger on the picture is the Canvas's tap - so it can overlap its
 *  neighbours without stealing anything from them. */
private val DOT_TARGET = 48.dp

/**
 * The phone's Galaxy PICTURE - the read-only drawing the owner asked for on
 * 2026-10-26.
 *
 * It is a picture of the same list below: each dot is one person, pet, place,
 * organisation, project or thing a saved fact names, a dot's size is how many
 * facts name it (and how many names it shares them with), and a line joins two
 * dots when one saved fact names both - the desktop's own rule, worked out from
 * the `/api/memory/entities` answer the plate already holds. Position is
 * deterministic: [GalaxyPictureData] lays the names out with the desktop's
 * `zen-ring` layout, so the same list always draws the same picture, twice, with
 * no force simulation and no animation.
 *
 * **Read-only, like everything on this plate.** A dot is a door to the name's
 * existing facts/connections view ([onOpen] opens that name exactly as the list
 * row does); there is nothing to drag, pin, hide, merge or forget here, and
 * nothing is written. The names themselves are also all in the list below, so a
 * picture that leaves some out at [GalaxyPictureData.MAX_NODES] hides no fact -
 * the caption says "Showing 48 of 312" when it does.
 *
 * **TalkBack.** No name is drawn as text on the canvas - at thumb size a 32-name
 * halo is about 21 layout units apart (roughly 18dp after the fit on the
 * 264dp-tall picture as it is sized here), where labels would collide into an
 * unreadable smear. Instead every dot has a real semantics node over it that
 * announces the same line the band uses ([Entities.galaxyNameLine]) and opens
 * the name when double-tapped, so the picture is not a surface only a sighted
 * finger can use. The whole picture also carries one sentence saying what it is
 * ([Entities.pictureSaid]).
 *
 * It reads nothing and keeps nothing: [entities] are the list the plate has
 * already fetched, and the picture is dropped with the plate.
 */
@Composable
internal fun GalaxyPicture(entities: List<Entities.Entity>, onOpen: (String) -> Unit) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val picture = remember(entities) { GalaxyPictureData.build(entities) }
    if (picture.dots.isEmpty()) return

    Column(Modifier.fillMaxWidth()) {
        BoxWithConstraints(
            Modifier
                .fillMaxWidth()
                .height(PICTURE_HEIGHT),
        ) {
            val density = LocalDensity.current
            val widthPx = constraints.maxWidth.toFloat()
            val heightPx = constraints.maxHeight.toFloat()
            val paddingPx = with(density) { PICTURE_PADDING.toPx() }
            val slackPx = with(density) { TOUCH_SLACK.toPx() }
            val dots = remember(picture, widthPx, heightPx, paddingPx) {
                GalaxyPictureData.fit(picture, widthPx, heightPx, paddingPx)
            }
            val byId = remember(dots) { dots.associateBy { it.id } }
            val said = remember(picture) {
                Entities.pictureSaid(picture.dots.size, picture.connections)
            }

            Canvas(
                Modifier
                    .fillMaxSize()
                    .semantics { contentDescription = said }
                    .pointerInput(dots) {
                        detectTapGestures { at ->
                            GalaxyPictureData.hit(dots, at.x, at.y, slackPx)?.let(onOpen)
                        }
                    },
            ) {
                // Lines first, so every dot sits on top of the lines that reach
                // it - the desktop's canvas does the same.
                for (edge in picture.edges) {
                    val a = byId[edge.source] ?: continue
                    val b = byId[edge.target] ?: continue
                    val strong = edge.shared >= 2
                    drawLine(
                        color = accent.copy(alpha = if (strong) 0.34f else 0.20f),
                        start = Offset(a.x, a.y),
                        end = Offset(b.x, b.y),
                        strokeWidth = if (strong) 1.6.dp.toPx() else 1.dp.toPx(),
                    )
                }
                for (dot in dots) {
                    val colour = dotColour(dot.group, accent)
                    if (GalaxyPictureData.disc(dot.group)) {
                        drawCircle(
                            color = colour,
                            radius = dot.r,
                            center = Offset(dot.x, dot.y),
                        )
                    } else {
                        // A ring is stroked INSIDE its radius, so a ring and a
                        // disc of the same size read as the same size.
                        val stroke = maxOf(1.4f.dp.toPx(), dot.r * 0.42f)
                        drawCircle(
                            color = colour,
                            radius = maxOf(1f, dot.r - stroke / 2f),
                            center = Offset(dot.x, dot.y),
                            style = Stroke(width = stroke),
                        )
                    }
                }
            }

            // The accessible controls: one per dot, invisible, over the drawing.
            // They add no touch handling (the Canvas above owns the finger), only
            // the announcement and the accessibility action.
            for (dot in dots) {
                val x = with(density) { dot.x.toDp() } - DOT_TARGET / 2
                val y = with(density) { dot.y.toDp() } - DOT_TARGET / 2
                Box(
                    Modifier
                        .offset(x = x, y = y)
                        .size(DOT_TARGET)
                        .semantics {
                            contentDescription =
                                Entities.galaxyNameLine(dot.name, dot.facts, dot.shared)
                            onClick(label = Entities.openName(dot.name)) {
                                onOpen(dot.id)
                                true
                            }
                        },
                )
            }
        }
        if (picture.dots.size < picture.total) {
            Gap(2)
            Text(
                Entities.showingLine(picture.dots.size, picture.total),
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
                modifier = Modifier.semantics {
                    contentDescription = Entities.showingLine(picture.dots.size, picture.total)
                },
            )
        }
    }
}

/**
 * A dot's colour: the theme's accent, dimmed a step for each kind family, so a
 * picture is readable in every theme rather than carrying its own palette. The
 * KIND is not decided by this colour - the shape decides it ([GalaxyPictureData.disc])
 * and the list below says it in words - so a theme change cannot change what
 * the picture means.
 */
private fun dotColour(group: String, accent: Color): Color = when (group) {
    "person" -> accent
    "pet" -> accent.copy(alpha = 0.90f)
    "place" -> accent.copy(alpha = 0.80f)
    "organisation" -> accent.copy(alpha = 0.70f)
    "project" -> accent.copy(alpha = 0.62f)
    else -> accent.copy(alpha = 0.55f)
}
