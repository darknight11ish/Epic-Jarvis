package com.jarvis.client.net

import kotlin.math.PI
import kotlin.math.asin
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The desktop's eight flat Galaxy layouts, ported - the phone's half of "the
 * Galaxy follows".
 *
 * ## Why these exist at all
 *
 * The owner's ask of 2026-10-28 was that the face model AND the Galaxy follow
 * one another between the desktop and the phone. The face is one id in
 * `/api/appearance`; the Galaxy's LOOK was, until this slice, a per-device
 * `localStorage` key on the PC (`galaxy-presets.js`'s `PRESET_STORAGE_KEY`)
 * that nothing else could see. So the look moved into the same appearance
 * document, and this file is what lets the phone actually draw the look it is
 * told about instead of showing one shape for all of them.
 *
 * ## Not a second picture
 *
 * These are ports of [`galaxy-presets.js`](../../../../../../../jarvis-desktop/src/galaxy-presets.js)'s
 * own `layoutStarMap`, `layoutCleanTree`, `layoutPlanetaryOrbit`,
 * `layoutNeuralArbor`, `layoutNebula`, `layoutDnaHelix` and `layoutRadarDome`,
 * the same functions the desktop falls back to on a machine with no WebGL. The
 * zen ring was already ported inside [GalaxyPicture]; the phone keeps that one
 * where it is and this file delegates to it, so there is still exactly ONE
 * zen-ring implementation on this phone.
 *
 * The numbers this file produces are checked against the real JavaScript by
 * `tools/gen_galaxy_picture_cases.py` + `GalaxyPictureTest`, the same way the
 * zen ring already was - "the same numbers, not merely similar". A look the
 * desktop adds later fails that test with its own name until it is ported here,
 * which is the guard against this file silently rotting.
 *
 * ## What is deliberately left out
 *
 * Only POSITIONS. The desktop's layouts also return decorations (rings, rows,
 * spokes, chords, rungs, dendrites) that `brain.js` paints under the map; the
 * phone's picture draws dots and the links a shared fact already makes, and it
 * has never drawn guides. Adding them would be a new visual claim, not a port,
 * so nothing here invents one.
 */
internal object GalaxyLayouts {

    /** `MIN_GAP`: two full dots plus air, the gap every layout keeps unless its
     *  own geometry justifies a different number. */
    const val MIN_GAP = 24.0

    // star-map
    private val STAR_RINGS = doubleArrayOf(34.0, 68.0, 108.0)
    private const val STAR_RING_PITCH = 34.0

    // clean-tree
    private val TREE_ROW_Y = doubleArrayOf(-62.0, -24.0, 14.0, 48.0)
    private const val TREE_COL_GAP = 26.0
    private const val TREE_CORE = 6

    // planetary-orbit
    private const val PLANET_B0 = 92.0
    private const val PLANET_PITCH = 30.0
    private const val PLANET_ASPECT = 1.85
    private const val PLANET_ARC_GAP = 1.2

    // neural-arbor
    private val ARBOR_ROWS = intArrayOf(1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144)
    private const val ARBOR_ROW_PITCH = 46.0
    private const val ARBOR_COL_PITCH = 30.0
    private const val ARBOR_ROW_WIDTH = 1200.0

    // nebula
    private const val NEBULA_SPACING = 1.6
    private const val NEBULA_WOBBLE = 0.06
    private const val NEBULA_GOLDEN = 2.399963229728653

    // dna-helix
    private const val HELIX_PITCH = 26.0
    private const val HELIX_STEPS_PER_TURN = 12.0
    private const val HELIX_AMPLITUDE = 62.0
    private const val HELIX_NAMES_PER_COLUMN = 6.0
    private const val HELIX_MAX_COLUMNS = 8
    private const val HELIX_COLUMN_GAP = 30.0

    // radar-dome
    private const val DOME_BASE = 72.0
    private const val DOME_PITCH = 36.0
    private const val DOME_GROUND_SHARE = 0.18
    private const val DOME_GROUND_GAP = 26.0
    private const val DOME_GROUND_DROP = 40.0

    /**
     * The point for each name, in the list's own (ranked) order, or null when
     * the look has no flat layout of its own.
     *
     * Null is the honest answer for `constellation` - the desktop's default is
     * its force simulation, which this phone does not run - and for any id this
     * build has not ported. The caller keeps the zen ring in that case, exactly
     * as the desktop keeps its constellation, and says which look is showing.
     */
    fun layout(look: String, nodes: List<Entities.Entity>): List<GalaxyPicture.Pt>? =
        when (look) {
            "star-map" -> starMap(nodes.size)
            "clean-tree" -> cleanTree(nodes)
            "planetary-orbit" -> planetaryOrbit(nodes.size)
            "neural-arbor" -> neuralArbor(nodes.size)
            "nebula" -> nebula(nodes.size)
            "dna-helix" -> dnaHelix(nodes.size)
            "radar-dome" -> radarDome(nodes.size)
            "zen-ring" -> GalaxyPicture.layout(nodes.size)
            else -> null
        }

    /** Every look id this file draws, so a test (and the plate) can tell a look
     *  the phone can draw from one it cannot. `constellation` is not here: it is
     *  the absence of a flat layout. */
    val LOOKS: List<String> = listOf(
        "planetary-orbit", "neural-arbor", "nebula", "dna-helix",
        "radar-dome", "star-map", "clean-tree", "zen-ring",
    )

    /** `layoutStarMap`: concentric rings at R=34/68/108, extra rings outward at
     *  the same 34 pitch, every ring's phase offset so names do not line up
     *  into spokes. */
    private fun starMap(count: Int): List<GalaxyPicture.Pt> {
        val points = ArrayList<GalaxyPicture.Pt>(count)
        var ringIndex = 0
        while (points.size < count) {
            val radius = if (ringIndex < STAR_RINGS.size) {
                STAR_RINGS[ringIndex]
            } else {
                STAR_RINGS[STAR_RINGS.size - 1] + STAR_RING_PITCH * (ringIndex - STAR_RINGS.size + 1)
            }
            val capacity = GalaxyPicture.ringCapacity(radius, MIN_GAP)
            val here = min(capacity, count - points.size)
            val phase = (ringIndex * PI) / max(1, capacity * 2).toDouble()
            points.addAll(GalaxyPicture.ringPoints(here, radius, phase))
            ringIndex++
            if (ringIndex > 60) break // unreachable at 48; the desktop's own stop
        }
        GalaxyPicture.separate(points, MIN_GAP)
        return points
    }

    /** `cleanTreeRowFor`: the first [TREE_CORE] names are the core row; every
     *  other name goes to the row its kind belongs to. */
    fun cleanTreeRowFor(group: String, index: Int): Int {
        if (index < TREE_CORE) return 0
        return when (group) {
            "person", "pet" -> 1
            "organisation", "project" -> 2
            else -> 3
        }
    }

    /** `layoutCleanTree`: four fixed rows, each centred on its own count. The
     *  only look whose positions depend on the names' KINDS, which is why it
     *  takes the entities rather than a count. */
    private fun cleanTree(nodes: List<Entities.Entity>): List<GalaxyPicture.Pt> {
        val members = Array(TREE_ROW_Y.size) { ArrayList<Int>() }
        nodes.forEachIndexed { i, e ->
            members[cleanTreeRowFor(GalaxyPicture.groupFor(e.kind), i)].add(i)
        }
        val points = arrayOfNulls<GalaxyPicture.Pt>(nodes.size)
        for (row in TREE_ROW_Y.indices) {
            val count = members[row].size
            members[row].forEachIndexed { j, index ->
                points[index] = GalaxyPicture.Pt(
                    (j - (count - 1) / 2.0) * TREE_COL_GAP,
                    TREE_ROW_Y[row],
                )
            }
        }
        val out = points.map { it ?: GalaxyPicture.Pt(0.0, 0.0) }.toMutableList()
        GalaxyPicture.separate(out, MIN_GAP)
        return out
    }

    /** `layoutPlanetaryOrbit`: the sun at the centre, every other name on a
     *  homothetic ellipse, spaced by ARC LENGTH so no two neighbours crowd. */
    private fun planetaryOrbit(count: Int): List<GalaxyPicture.Pt> {
        val points = ArrayList<GalaxyPicture.Pt>(count)
        if (count > 0) points.add(GalaxyPicture.Pt(0.0, 0.0))
        var ring = 0
        while (points.size < count) {
            val b = PLANET_B0 + PLANET_PITCH * ring
            val a = b * PLANET_ASPECT
            val capacity = max(1, floor(ellipsePerimeter(a, b) / (MIN_GAP * PLANET_ARC_GAP)).toInt())
            val here = min(capacity, count - points.size)
            val phase = (ring * PI) / max(4, here * 2).toDouble()
            points.addAll(ellipsePoints(here, a, b, phase))
            ring++
            if (ring > 40) break // unreachable at 48; the desktop's own stop
        }
        GalaxyPicture.separate(points, MIN_GAP)
        return points
    }

    /** `layoutNeuralArbor`: a root at the bottom and rows widening upward on a
     *  Fibonacci ladder (`arborRowCounts`), each row one flat line. */
    private fun neuralArbor(count: Int): List<GalaxyPicture.Pt> {
        val counts = arborRowCounts(count)
        val depth = counts.size
        val points = ArrayList<GalaxyPicture.Pt>(count)
        var index = 0
        counts.forEachIndexed { row, here ->
            // The root sits at the BOTTOM: canvas y grows downward, so the last
            // row is the lowest one.
            val y = ((depth - 1) / 2.0 - row) * ARBOR_ROW_PITCH
            val pitch = if (here > 1) {
                max(MIN_GAP, min(ARBOR_COL_PITCH, ARBOR_ROW_WIDTH / (here - 1)))
            } else {
                0.0
            }
            for (j in 0 until here) {
                index++
                points.add(GalaxyPicture.Pt((j - (here - 1) / 2.0) * pitch, y))
            }
        }
        GalaxyPicture.separate(points, MIN_GAP)
        return points
    }

    /** `arborRowCounts`: the Fibonacci widening, a remainder too small for its
     *  own row merged into the row under it so the crown never pinches. */
    fun arborRowCounts(total: Int): List<Int> {
        val want = max(0, total)
        if (want == 0) return emptyList()
        val rows = ArrayList<Int>()
        var left = want
        var i = 0
        while (i < ARBOR_ROWS.size && left > 0) {
            val count = min(ARBOR_ROWS[i], left)
            rows.add(count)
            left -= count
            i++
        }
        while (left > 0) {
            val count = min(ARBOR_ROWS[ARBOR_ROWS.size - 1], left)
            rows.add(count)
            left -= count
        }
        while (rows.size > 1 && rows[rows.size - 1] < rows[rows.size - 2]) {
            val last = rows.removeAt(rows.size - 1)
            rows[rows.size - 1] = rows[rows.size - 1] + last
        }
        return rows
    }

    /** `layoutNebula`: a Vogel (golden-angle) spiral, radius growing as
     *  sqrt(index) so the cloud is evenly dense, with the desktop's own 6%
     *  wobble so it does not read as a disc. */
    private fun nebula(count: Int): List<GalaxyPicture.Pt> {
        val spread = MIN_GAP * NEBULA_SPACING
        val points = (0 until count).map { i ->
            val radius = spread * sqrt(i + 0.5)
            val wobble = 1 + NEBULA_WOBBLE * sin(i * NEBULA_GOLDEN)
            val angle = i * NEBULA_GOLDEN
            GalaxyPicture.Pt(radius * wobble * cos(angle), radius * wobble * sin(angle))
        }.toMutableList()
        GalaxyPicture.separate(points, MIN_GAP)
        return points
    }

    /** `layoutDnaHelix`: one or more double helices side by side; each name
     *  keeps its own row ladder, so the strands' curves may cross but names
     *  never do. */
    private fun dnaHelix(count: Int): List<GalaxyPicture.Pt> {
        val wanted = floor(sqrt(count / HELIX_NAMES_PER_COLUMN) + 0.5).toInt()
        val columns = max(1, min(HELIX_MAX_COLUMNS, if (wanted == 0) 1 else wanted))
        val pitch = max(MIN_GAP * 1.05, HELIX_PITCH)
        val columnPitch = HELIX_AMPLITUDE * 2 + max(MIN_GAP, HELIX_COLUMN_GAP)
        val wave = PI * 2 / HELIX_STEPS_PER_TURN
        val points = arrayOfNulls<GalaxyPicture.Pt>(count)
        val perColumn = ceil(count / columns.toDouble()).toInt()
        for (column in 0 until columns) {
            val first = column * perColumn
            val rows = max(0, min(perColumn, count - first))
            val centreX = (column - (columns - 1) / 2.0) * columnPitch
            // Each column is centred on its own axis, so a short last column
            // still stands beside the others instead of hanging off the bottom.
            val top = -((rows - 1) / 2.0) * pitch
            for (k in 0 until rows) {
                val index = first + k
                val strand = if (k % 2 == 0) 1.0 else -1.0
                val sideways = strand * HELIX_AMPLITUDE * cos(k * wave)
                points[index] = GalaxyPicture.Pt(centreX + sideways, top + k * pitch)
            }
        }
        val out = points.map { it ?: GalaxyPicture.Pt(0.0, 0.0) }.toMutableList()
        GalaxyPicture.separate(out, MIN_GAP)
        return out
    }

    /** `layoutRadarDome`: names on arcs above the horizon, the rest on one
     *  ground row below the pole. */
    private fun radarDome(count: Int): List<GalaxyPicture.Pt> {
        val groundCount = if (count <= 2) {
            count
        } else {
            min(count - 1, max(2, floor(count * DOME_GROUND_SHARE + 0.5).toInt()))
        }
        val domeCount = count - groundCount
        // The arcs, each outer than the last, then the ground row: the desktop
        // pushes the ground row LAST, so the index order must too.
        val arcs = ArrayList<Pair<Double, Int>>()
        var need = domeCount
        var ring = 0
        while (need > 0) {
            val radius = DOME_BASE + DOME_PITCH * ring
            val capacity = arcCapacity(radius, MIN_GAP)
            val here = min(capacity, need)
            arcs.add(radius to here)
            need -= here
            ring++
            if (ring > 60) break // unreachable at 48; the desktop's own stop
        }
        val points = ArrayList<GalaxyPicture.Pt>(count)
        for ((radius, here) in arcs) {
            // The upper half, strictly between PI and 2PI: every name is above
            // the horizon. Half a step of offset keeps a name off both feet.
            for (k in 0 until here) {
                val angle = PI + ((k + 0.5) / here) * PI
                points.add(GalaxyPicture.Pt(cos(angle) * radius, sin(angle) * radius))
            }
        }
        if (groundCount > 0) {
            val outer = if (arcs.isEmpty()) DOME_BASE else arcs[arcs.size - 1].first
            val pitch = if (groundCount > 1) {
                max(DOME_GROUND_GAP, (outer * 2) / (groundCount - 1))
            } else {
                0.0
            }
            for (g in 0 until groundCount) {
                points.add(GalaxyPicture.Pt((g - (groundCount - 1) / 2.0) * pitch, DOME_GROUND_DROP))
            }
        }
        GalaxyPicture.separate(points, MIN_GAP)
        return points
    }

    /** `arcCapacity`: half a full ring's capacity, because only half the circle
     *  is used. */
    fun arcCapacity(radius: Double, gap: Double): Int =
        max(1, GalaxyPicture.ringCapacity(radius, gap) / 2)

    /** `ellipsePerimeter`: Ramanujan's approximation, the desktop's own. */
    fun ellipsePerimeter(a: Double, b: Double): Double {
        val h = ((a - b) * (a - b)) / ((a + b) * (a + b))
        return PI * (a + b) * (1 + (3 * h) / (10 + sqrt(4 - 3 * h)))
    }

    /**
     * `ellipsePoints`: `count` points on the ellipse (a cos t, b sin t) spaced
     * evenly by ARC LENGTH rather than by angle, because equal angles crowd the
     * ends of the long axis.
     *
     * The desktop walks the perimeter in at least 360 steps and interpolates
     * between two of them; so does this, in the same order, so the two agree to
     * the same numbers.
     */
    fun ellipsePoints(count: Int, a: Double, b: Double, phase: Double = 0.0): List<GalaxyPicture.Pt> {
        if (count <= 0) return emptyList()
        val steps = max(360, count * 12)
        val s = DoubleArray(steps + 1)
        val ts = DoubleArray(steps + 1)
        var walked = 0.0
        var lastX = a
        var lastY = 0.0
        ts[0] = 0.0
        s[0] = 0.0
        for (i in 1..steps) {
            val t = (i.toDouble() / steps) * PI * 2
            val x = a * cos(t)
            val y = b * sin(t)
            walked += sqrt((x - lastX) * (x - lastX) + (y - lastY) * (y - lastY))
            lastX = x
            lastY = y
            s[i] = walked
            ts[i] = t
        }
        val out = ArrayList<GalaxyPicture.Pt>(count)
        var at = 0
        for (k in 0 until count) {
            val want = (k.toDouble() / count) * walked
            while (at + 1 < s.size && s[at + 1] < want) at++
            val fromS = s[at]
            val toIndex = min(at + 1, s.size - 1)
            val toS = s[toIndex]
            val span = toS - fromS
            val f = if (span > 1e-9) (want - fromS) / span else 0.0
            val t = ts[at] + (ts[toIndex] - ts[at]) * f + phase
            out.add(GalaxyPicture.Pt(a * cos(t), b * sin(t)))
        }
        return out
    }
}
