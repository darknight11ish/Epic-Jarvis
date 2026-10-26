package com.jarvis.client.net

import java.util.Locale
import kotlin.math.PI
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The phone's Galaxy PICTURE - the pure half (no Compose, no Android types).
 *
 * The owner's decision of 2026-10-26 asked for "a picture" of the Galaxy on
 * the phone. That deliberately reverses only the "no canvas on the phone" part
 * of the standing rule: this file computes a picture, it draws nothing, keeps
 * nothing and writes nothing. [com.jarvis.client.ui.screens.GalaxyPictureView]
 * paints what this returns; the list plate keeps every word it had.
 *
 * ## Where the picture comes from
 *
 * The same two reads the list already makes - no new route, no new field:
 *
 * - `GET /api/memory/entities` supplies the names (`id`, `name`, `kind`,
 *   `fact_ids`). Nodes are names; EDGES are shared facts, worked out exactly
 *   as the desktop's `buildEntityGraph` does (`galaxy-view.js`): one saved
 *   fact naming two names joins them, and a fact naming more than
 *   [Entities.MAX_NAMES_PER_FACT] names is a list rather than a connection, so
 *   it joins nothing. A dropped name gets no dot, and an edge only ever joins
 *   dots that are really drawn.
 * - `GET /api/memory/used?ids=` supplies the fact WORDS, and only when a name
 *   is opened. The picture never reads it.
 *
 * ## Deterministic, on purpose
 *
 * There is no force simulation and no animation on the phone: the same list
 * must draw the same picture every time. The positions are the desktop's own
 * deterministic flat layout, `zen-ring` (`jarvis-desktop/src/galaxy-presets.js`,
 * Phase G0 of the Galaxy rework, 2026-10-23): the best-known name at the
 * centre, the others evenly spaced on one R=108 halo, and a list too large for
 * that halo grows OUTWARD at a 24 pitch. The port here is checked against the
 * real desktop JavaScript by `tools/gen_galaxy_picture_cases.py` +
 * `GalaxyPictureTest`, so the two apps' positions are the same numbers, not
 * merely "similar".
 *
 * Which names are drawn, and in what order, is the desktop's
 * `orderedEntities` rule too: most facts first, then the newest fact id, then
 * the name A-Z, then the entity id - so the picture never depends on the order
 * the PC happened to send. The phone caps the picture at [MAX_NODES] names
 * (the desktop's own cap is 240): 48 is one centre + 32 on the halo + 15 on
 * the first outward ring, which is as many dots as a thumb-width canvas can
 * keep apart; every other name stays in the list below.
 *
 * Two stated differences from the desktop, neither hidden: the desktop ranks
 * names with locale-aware `localeCompare` while this file compares
 * case-insensitively A-Z (`lowercase(Locale.ROOT)`), so two names differing
 * only in case could order differently - the picture is still deterministic;
 * and the desktop's fit scale starts at its own zoom, while [fit] shrinks or
 * grows the layout to the canvas (never past [MAX_SCALE]).
 */
object GalaxyPicture {

    /** The most names the picture draws: 1 centre + 32 halo + 15 first ring. */
    const val MAX_NODES = 48

    /** zen-ring: the one halo, the pitch of any overflow ring, and the gap the
     *  layout keeps between two dots. The values are the desktop's own
     *  (`galaxy-presets.js`: ZEN_RADIUS, ZEN_RING_PITCH, ZEN_HALO_GAP). */
    const val ZEN_RADIUS = 108.0
    const val ZEN_RING_PITCH = 24.0
    const val ZEN_HALO_GAP = 21.0

    /** [fit] never grows the layout past this, so a two-name picture is two
     *  dots rather than two blobs filling the screen. */
    const val MAX_SCALE = 2.0

    /** One drawn name. [x], [y] and [radius] are the layout's own units; the
     *  UI's [fit] turns them into pixels. [facts] is `fact_ids.size`,
     *  [shared] is how many drawn names it shares a fact with (the desktop's
     *  `deg`, which sizes a dot alongside its facts). */
    data class Dot(
        val id: String,
        val name: String,
        val group: String,
        val facts: Int,
        val shared: Int,
        val radius: Double,
        val x: Double,
        val y: Double,
    )

    /** One line between two drawn names, and how many facts they share. */
    data class Edge(val source: String, val target: String, val shared: Int)

    /** The whole picture: what to paint, and the real total so the plate can
     *  say "Showing 48 of 312" when the cap hides names. */
    data class Picture(
        val dots: List<Dot>,
        val edges: List<Edge>,
        /** How many names the plate holds, drawn or not. */
        val total: Int,
    ) {
        val connections: Int get() = edges.size
    }

    /** A dot placed on the canvas, in pixels, ready to paint and to hit-test. */
    data class ScreenDot(
        val id: String,
        val name: String,
        val group: String,
        val facts: Int,
        val shared: Int,
        val x: Float,
        val y: Float,
        val r: Float,
    )

    /** The desktop's kind -> group rule (`galaxy-view.js` KIND_GROUPS): an
     *  unknown or missing kind is "other", never invented. */
    fun groupFor(kind: String?): String = when (kind) {
        "person", "pet", "place", "organisation", "project", "thing" -> kind
        else -> "other"
    }

    /** The desktop's shape rule (`GROUP_STYLE`): a filled disc for a person,
     *  place or project; a hollow ring for a pet, organisation, thing or an
     *  unknown kind. Shape is how the two apps encode the kind without relying
     *  on colour, which a theme may change. */
    fun disc(group: String): Boolean =
        group == "person" || group == "place" || group == "project"

    /**
     * The names the picture draws, in the order the cap keeps: the desktop's
     * `orderedEntities` rule, cut to [MAX_NODES].
     *
     * The desktop's retired-fact branch is deliberately not here: a
     * `/api/memory/entities` answer already lists only current, unerased
     * facts (`galaxy-view.js` says the branch cannot arise from today's PC),
     * and the phone has no fact rows in this answer to judge.
     */
    fun ordered(entities: List<Entities.Entity>): List<Entities.Entity> {
        data class Ranked(
            val e: Entities.Entity,
            val facts: Int,
            val newest: Long,
            val name: String,
            val id: Long,
            val at: Int,
        )

        val scored = entities.mapIndexed { i, e ->
            Ranked(
                e = e,
                facts = e.factIds.size,
                newest = e.factIds.maxOrNull() ?: 0L,
                name = e.name,
                id = e.id.toLongOrNull() ?: 0L,
                at = i,
            )
        }
        return scored
            .sortedWith(
                compareByDescending<Ranked> { it.facts }
                    .thenByDescending { it.newest }
                    .thenBy { it.name.lowercase(Locale.ROOT) }
                    .thenBy { it.name }
                    .thenBy { it.id }
                    .thenBy { it.at },
            )
            .take(MAX_NODES)
            .map { it.e }
    }

    /**
     * The whole deterministic picture: rank, cap, join, lay out.
     *
     * Blank names are kept as dots (the list below draws them the same way)
     * but they are not given a caption - the desktop clips a label at 34
     * characters and the phone draws no labels at all, so nothing here is
     * clipped or fake.
     */
    fun build(entities: List<Entities.Entity>): Picture {
        val kept = ordered(entities)
        val edges = edges(kept)
        val degree = HashMap<String, Int>(kept.size)
        for (l in edges) {
            degree[l.source] = (degree[l.source] ?: 0) + 1
            degree[l.target] = (degree[l.target] ?: 0) + 1
        }
        val points = layout(kept.size)
        val dots = kept.mapIndexed { i, e ->
            val weight = e.factIds.size
            val deg = degree[e.id] ?: 0
            // `radiusOf` in the desktop's brain.js: 3 + min(9, sqrt(2 * facts + degree)).
            val radius = 3.0 + min(9.0, sqrt(weight * 2.0 + deg))
            Dot(
                id = e.id,
                name = e.name,
                group = groupFor(e.kind),
                facts = weight,
                shared = deg,
                radius = radius,
                x = points[i].x,
                y = points[i].y,
            )
        }
        return Picture(dots = dots, edges = edges, total = entities.size)
    }

    /**
     * The desktop's `buildEntityGraph` links, over the drawn names only:
     * every saved fact that names two or more of them joins each pair, except
     * a fact naming more than [Entities.MAX_NAMES_PER_FACT] names (that is a
     * list, not a connection). The order is the desktop's: strongest first,
     * then by the two names, so the drawing order never depends on the PC's
     * order.
     */
    fun edges(kept: List<Entities.Entity>): List<Edge> {
        val namesByFact = HashMap<Long, MutableList<String>>()
        for (e in kept) {
            for (f in e.factIds) {
                // One name counts ONCE per fact, however many times that id is
                // repeated on it - the desktop's buildEntityGraph does the same
                // (`if (!names.includes(n.id)) names.push(n.id)`). Without
                // this, a repeated id would make a name its own partner and
                // inflate both the share count and the dot's size.
                val names = namesByFact.getOrPut(f) { ArrayList() }
                if (e.id !in names) names.add(e.id)
            }
        }
        val shared = LinkedHashMap<Pair<String, String>, Int>()
        for (names in namesByFact.values) {
            if (names.size < 2 || names.size > Entities.MAX_NAMES_PER_FACT) continue
            for (i in names.indices) {
                for (j in i + 1 until names.size) {
                    val a = names[i]
                    val b = names[j]
                    val key = if (a < b) a to b else b to a
                    shared[key] = (shared[key] ?: 0) + 1
                }
            }
        }
        return shared.entries
            .map { Edge(source = it.key.first, target = it.key.second, shared = it.value) }
            .sortedWith(
                compareByDescending<Edge> { it.shared }
                    .thenBy { it.source }
                    .thenBy { it.target },
            )
    }

    /** A point in the layout's own units. */
    internal data class Pt(val x: Double, val y: Double)

    /**
     * The desktop's `layoutZenRing`, ported: one name at the centre (the
     * best-known, because the list arrives in `ordered`'s order), the rest on
     * R=108, and a list too large for that halo grows outward at 24.
     */
    internal fun layout(count: Int): List<Pt> {
        val rings = ArrayList<Pair<Double, Int>>()
        var need = max(0, count - 1)
        var index = 0
        while (need > 0) {
            val radius = ZEN_RADIUS + ZEN_RING_PITCH * index
            val capacity = ringCapacity(radius, ZEN_HALO_GAP)
            val here = min(capacity, need)
            rings.add(radius to here)
            need -= here
            index += 1
            if (index > 40) break // unreachable at 48; the desktop's own stop
        }
        val points = ArrayList<Pt>(count)
        if (count > 0) points.add(Pt(0.0, 0.0))
        for ((ringIndex, ring) in rings.withIndex()) {
            val (radius, here) = ring
            points.addAll(ringPoints(here, radius, ringIndex * (PI / max(2, here).toDouble())))
        }
        separate(points, ZEN_HALO_GAP)
        return points
    }

    /**
     * The desktop's `ringCapacity`: how many dots fit on a circle of [radius]
     * with [gap] air between neighbours. Adjacent centres are
     * `2R sin(pi / n)` apart, so the largest n that still clears the gap is
     * `pi / asin(gap / 2R)`.
     */
    internal fun ringCapacity(radius: Double, gap: Double): Int {
        if (radius <= 0.0) return 1
        val ratio = gap / (2.0 * radius)
        if (ratio >= 1.0) return 1
        return max(1, floor(PI / asin(ratio)).toInt())
    }

    /** `count` points on a circle, evenly spaced, starting at -90 degrees plus
     *  [phase] - the desktop's `ringPoints`, unchanged. */
    internal fun ringPoints(count: Int, radius: Double, phase: Double = 0.0): List<Pt> =
        List(count) { i ->
            val angle = -PI / 2.0 + phase + (i.toDouble() / count) * PI * 2.0
            Pt(cos(angle) * radius, sin(angle) * radius)
        }

    /**
     * The desktop's `separate`, ported as the same belt-and-braces no-overlap
     * guarantee: the construction above already clears the gap, and if a
     * future edit breaks that formula this pushes the offenders apart instead
     * of drawing two names as one blob - deterministically, never with a
     * random jitter. Internal so a test can prove the fallback really works.
     */
    internal fun separate(points: MutableList<Pt>, gap: Double) {
        val want = gap * gap
        for (pass in 0 until 80) {
            var moved = false
            for (i in points.indices) {
                for (j in i + 1 until points.size) {
                    var a = points[i]
                    var b = points[j]
                    var dx = b.x - a.x
                    var dy = b.y - a.y
                    var d2 = dx * dx + dy * dy
                    if (d2 >= want) continue
                    if (d2 < 1e-9) {
                        // Exactly on top of each other: a stable direction from
                        // the indices, so the same list separates the same way.
                        var sx = ((i * 31 + j * 17) % 5) - 2
                        var sy = ((i * 13 + j * 7) % 5) - 2
                        if (sx == 0) sx = 1
                        if (sy == 0) sy = 1
                        dx = sx.toDouble()
                        dy = sy.toDouble()
                        d2 = dx * dx + dy * dy
                    }
                    val d = sqrt(d2)
                    val push = (gap - d) / 2.0
                    val ux = dx / d
                    val uy = dy / d
                    a = Pt(a.x - ux * push, a.y - uy * push)
                    b = Pt(b.x + ux * push, b.y + uy * push)
                    points[i] = a
                    points[j] = b
                    moved = true
                }
            }
            if (!moved) break
        }
    }

    /**
     * The layout scaled to a canvas: uniform scale (never past [MAX_SCALE]),
     * centred, with [padding] pixels of air. Every dot's own radius is scaled
     * with it, so a dot and the space around it keep their proportion.
     */
    fun fit(picture: Picture, width: Float, height: Float, padding: Float): List<ScreenDot> {
        if (picture.dots.isEmpty() || width <= 0f || height <= 0f) return emptyList()
        var minX = Double.MAX_VALUE
        var maxX = -Double.MAX_VALUE
        var minY = Double.MAX_VALUE
        var maxY = -Double.MAX_VALUE
        for (d in picture.dots) {
            minX = min(minX, d.x - d.radius)
            maxX = max(maxX, d.x + d.radius)
            minY = min(minY, d.y - d.radius)
            maxY = max(maxY, d.y + d.radius)
        }
        val spanX = max(1e-6, maxX - minX)
        val spanY = max(1e-6, maxY - minY)
        val roomX = max(1.0, width - 2.0 * padding).toDouble()
        val roomY = max(1.0, height - 2.0 * padding).toDouble()
        val scale = min(min(roomX / spanX, roomY / spanY), MAX_SCALE)
        val centreX = (minX + maxX) / 2.0
        val centreY = (minY + maxY) / 2.0
        val ox = width / 2.0
        val oy = height / 2.0
        return picture.dots.map { d ->
            ScreenDot(
                id = d.id,
                name = d.name,
                group = d.group,
                facts = d.facts,
                shared = d.shared,
                x = (ox + (d.x - centreX) * scale).toFloat(),
                y = (oy + (d.y - centreY) * scale).toFloat(),
                r = (d.radius * scale).toFloat(),
            )
        }
    }

    /**
     * Which dot a finger at ([x], [y]) hit: the nearest one whose dot plus
     * [slack] pixels of forgiveness reaches the point, or null for a miss. A
     * tie goes to the dot earlier in `fit`'s order, so a tap can never be
     * decided by map-iteration luck.
     */
    fun hit(dots: List<ScreenDot>, x: Float, y: Float, slack: Float): String? {
        var best: ScreenDot? = null
        var bestD2 = Double.MAX_VALUE
        val forgive = max(0f, slack)
        for (d in dots) {
            val dx = x - d.x
            val dy = y - d.y
            val d2 = dx.toDouble() * dx + dy.toDouble() * dy
            val reach = d.r + forgive
            if (d2 > reach.toDouble() * reach) continue
            if (d2 < bestD2) {
                best = d
                bestD2 = d2
            }
        }
        return best?.id
    }
}
