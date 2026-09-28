package com.jarvis.client.face

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/**
 * Seasonal touches behind the character faces (the owner's decision of
 * 2026-09-28: "seasonal touches from the date (off by default)", one switch
 * in the animal options - `seasonal` in [com.jarvis.client.net.AnimalOptions]
 * - changeable by asking Jarvis).
 *
 * A LINE-FOR-LINE COPY of the desktop's `jarvis-desktop/src/season.js`:
 * which season it is and which few holiday touches are due, from this
 * phone's own date, time and time zone (the hemisphere from the sign of the
 * sky's saved latitude; north when no town is set), and the touches laid out
 * behind the face as a flat list of drawing steps. [SeasonDraw] paints it.
 * The two cannot share code, so they share ANSWERS: `tools/gen_season.py`
 * runs the JavaScript under node and writes `season-golden.json`, and
 * `SeasonTest` fails if this copy disagrees.
 *
 * Nothing goes online and nothing is stored: the clock is the phone's own.
 *
 * What is drawn (season.js's header has the full list and the reasons):
 * autumn leaves drifting down, fallen leaves gathering in the corners; in
 * winter light snowfall, a snow bank and, mid-winter, a tiny snowman; spring
 * blossom petals; summer a faint haze by day and a few fireflies at night; a
 * plain pumpkin 24-31 October; a string of soft lights along the top 18
 * December - 1 January; a few slow sparkles in the first minute of 1
 * January. Nothing flashes; colours are muted and kept away from the state
 * colours. Still or a serious moment hides it all ([hide]); an approval or
 * an error hides everything that moves and every holiday piece ([hold]);
 * calm motion means fewer pieces, held still.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Season {
    private const val DAY_MS = 86400000.0
    private const val TAU = 6.2832

    // ---- Small helpers (season.js has the same, in the same order) ----------

    private fun clamp(v: Double, lo: Double, hi: Double) = max(lo, min(hi, v))

    fun smoothstep(a: Double, b: Double, x: Double): Double {
        val k = clamp((x - a) / (b - a), 0.0, 1.0)
        return k * k * (3 - 2 * k)
    }

    private fun frac(x: Double) = x - floor(x)

    /** The animals' own hash (Sky.hash01), 0..1. */
    fun hash01(n: Int): Double = Sky.hash01(n)

    /** JavaScript's Math.round: halves go up. */
    private fun jsRound(x: Double): Int = floor(x + 0.5).toInt()

    // ---- The calendar ---------------------------------------------------------

    /** Days since 1970-01-01 of a calendar date (H. Hinnant's days_from_civil). */
    fun daysFromCivil(y: Int, m: Int, d: Int): Double {
        val yy = (if (m <= 2) y - 1 else y).toDouble()
        val era = floor(yy / 400)
        val yoe = yy - era * 400
        val doy = floor((153.0 * (if (m > 2) m - 3 else m + 9) + 2) / 5) + d - 1
        val doe = yoe * 365 + floor(yoe / 4) - floor(yoe / 100) + doy
        return era * 146097 + doe - 719468
    }

    /** The calendar date of a day number: [year, month 1-12, day 1-31]. */
    fun civilFromDays(days: Double): IntArray {
        val z = days + 719468
        val era = floor(z / 146097)
        val doe = z - era * 146097
        val yoe = floor((doe - floor(doe / 1460) + floor(doe / 36524) - floor(doe / 146096)) / 365)
        val doy = doe - (365 * yoe + floor(yoe / 4) - floor(yoe / 100))
        val mp = floor((5 * doy + 2) / 153)
        val d = doy - floor((153 * mp + 2) / 5) + 1
        val m = if (mp < 10) mp + 3 else mp - 9
        return intArrayOf((yoe + era * 400 + (if (m <= 2) 1 else 0)).toInt(), m.toInt(), d.toInt())
    }

    /** The phone's local moment - season.js localOf. [t] is local days since 1970 with the time of day as a fraction. */
    data class Local(val t: Double, val y: Int, val m: Int, val d: Int, val hour: Double)

    fun localOf(ms: Double, tzMin: Double): Local {
        val lms = ms + tzMin * 60000
        val days = floor(lms / DAY_MS)
        val c = civilFromDays(days)
        val t = lms / DAY_MS
        return Local(t, c[0], c[1], c[2], (t - days) * 24)
    }

    /** One hour, in days: how long a season or holiday takes to fade in and out. */
    const val FADE_DAYS = 1.0 / 24

    data class Window(val w: Double, val day: Double)

    /** season.js windowAt: from 00:00 on (sm, sd) up to 00:00 on (em, ed), each edge faded over its first hour. */
    fun windowAt(l: Local, sm: Int, sd: Int, em: Int, ed: Int): Window {
        var ys = l.y
        var s = daysFromCivil(ys, sm, sd)
        if (s > l.t) {
            ys -= 1
            s = daysFromCivil(ys, sm, sd)
        }
        var e = daysFromCivil(ys, em, ed)
        if (e <= s) e = daysFromCivil(ys + 1, em, ed)
        val w = smoothstep(0.0, FADE_DAYS, l.t - s) * (1 - smoothstep(0.0, FADE_DAYS, l.t - e))
        return Window(w, l.t - s)
    }

    /** [name, from month, to month], the northern half of the world. */
    val SEASONS: List<Triple<String, Int, Int>> = listOf(
        Triple("spring", 3, 6), Triple("summer", 6, 9), Triple("autumn", 9, 12), Triple("winter", 12, 3),
    )

    /** [month, day, to month, to day (not included)]. */
    val HOLIDAYS: List<Pair<String, IntArray>> = listOf(
        "pumpkin" to intArrayOf(10, 24, 11, 1), "lights" to intArrayOf(12, 18, 1, 2),
    )
    val SNOWMAN = intArrayOf(12, 15, 2, 1)
    const val SPARKLE_S = 60.0

    private fun shift6(m: Int) = ((m + 5) % 12) + 1

    class Calendar(
        val south: Boolean,
        val local: Local,
        val seasons: Map<String, Double>,
        val day: Map<String, Double>,
        val items: Map<String, Double>,
        val sparkleSec: Double,
        val season: String,
    )

    fun calendar(ms: Double, tzMin: Double, lat: Double?): Calendar {
        val l = localOf(ms, tzMin)
        val south = lat != null && lat.isFinite() && lat < 0
        val seasons = LinkedHashMap<String, Double>()
        val day = LinkedHashMap<String, Double>()
        for ((name, a, b) in SEASONS) {
            val w = windowAt(l, if (south) shift6(a) else a, 1, if (south) shift6(b) else b, 1)
            seasons[name] = w.w
            day[name] = w.day
        }
        val items = LinkedHashMap<String, Double>()
        for ((name, v) in HOLIDAYS) items[name] = windowAt(l, v[0], v[1], v[2], v[3]).w
        val sn = SNOWMAN
        items["snowman"] = windowAt(
            l, if (south) shift6(sn[0]) else sn[0], sn[1], if (south) shift6(sn[2]) else sn[2], sn[3],
        ).w
        val sec = (l.t - daysFromCivil(l.y, 1, 1)) * 86400
        items["sparkle"] = smoothstep(0.0, 3.0, sec) * (1 - smoothstep(SPARKLE_S - 6, SPARKLE_S, sec))
        var best = "spring"
        var bw = -1.0
        for ((name) in SEASONS) {
            val w = seasons.getValue(name)
            if (w > bw) {
                bw = w
                best = name
            }
        }
        return Calendar(south, l, seasons, day, items, sec, best)
    }

    // ---- The layout -----------------------------------------------------------

    const val FLOOR = -0.93
    const val LEFT_X = -0.80
    const val RIGHT_X = 0.80
    const val LIGHTS_TOP = 0.965
    const val LIGHTS_SAG = 0.055

    val LEAF_RGB = listOf(doubleArrayOf(196.0, 100.0, 52.0), doubleArrayOf(188.0, 150.0, 70.0), doubleArrayOf(172.0, 82.0, 48.0), doubleArrayOf(186.0, 120.0, 56.0))
    val PETAL_RGB = listOf(doubleArrayOf(248.0, 206.0, 218.0), doubleArrayOf(242.0, 186.0, 204.0), doubleArrayOf(250.0, 228.0, 234.0))
    val BULB_RGB = listOf(
        doubleArrayOf(255.0, 232.0, 196.0), doubleArrayOf(236.0, 168.0, 176.0), doubleArrayOf(168.0, 214.0, 170.0),
        doubleArrayOf(180.0, 184.0, 228.0), doubleArrayOf(255.0, 232.0, 196.0), doubleArrayOf(240.0, 212.0, 150.0),
    )
    private val SNOW_RGB = doubleArrayOf(232.0, 238.0, 246.0)

    const val HOLD_EASE_S = 0.8

    /**
     * season.js holdWeight: how far the "attentive" hold is on, 0..1. [state]
     * and [prevState] are state names ("approval", "error", ...), [since]
     * seconds since the change.
     */
    fun holdWeight(state: String, prevState: String, since: Double): Double {
        val isH = state == "approval" || state == "error"
        val wasH = prevState == "approval" || prevState == "error"
        val e = smoothstep(0.0, HOLD_EASE_S, since)
        if (isH && wasH) return 1.0
        if (isH) return e
        if (wasH) return 1 - e
        return 0.0
    }

    // ---- Shapes ---------------------------------------------------------------

    fun leafShape(): List<DoubleArray> {
        val pts = ArrayList<DoubleArray>()
        for (i in 0..6) {
            val u = -1 + i / 3.0
            pts.add(doubleArrayOf(u, (1 - u * u) * (1 + 0.25 * u)))
        }
        for (i in 5 downTo 1) {
            val u = -1 + i / 3.0
            pts.add(doubleArrayOf(u, -(1 - u * u) * (1 + 0.25 * u)))
        }
        return pts
    }

    fun petalShape(): List<DoubleArray> {
        val pts = ArrayList<DoubleArray>()
        for (i in 0..6) {
            val s = i / 6.0
            pts.add(doubleArrayOf(2 * s - 1, sin(PI * s.pow(0.65))))
        }
        for (i in 5 downTo 1) {
            val s = i / 6.0
            pts.add(doubleArrayOf(2 * s - 1, -sin(PI * s.pow(0.65))))
        }
        return pts
    }

    fun glintShape(): List<DoubleArray> {
        val pts = ArrayList<DoubleArray>()
        for (i in 0 until 8) {
            val a = PI / 2 - i * PI / 4
            val r = if (i % 2 == 0) 1.0 else 0.26
            pts.add(doubleArrayOf(r * cos(a), r * sin(a)))
        }
        return pts
    }

    fun ellipse(cx: Double, cy: Double, rx: Double, ry: Double, n: Int): List<DoubleArray> {
        val pts = ArrayList<DoubleArray>()
        for (i in 0 until n) {
            val a = TAU * i / n
            pts.add(doubleArrayOf(cx + rx * cos(a), cy + ry * sin(a)))
        }
        return pts
    }

    private val LEAF = leafShape()
    private val PETAL = petalShape()
    private val GLINT = glintShape()

    /** season.js place: a unit shape scaled, turned (radians, counter-clockwise, y up) and moved; flat x, y pairs. */
    fun place(shape: List<DoubleArray>, x: Double, y: Double, sx: Double, sy: Double, ang: Double): DoubleArray {
        val c = cos(ang)
        val s = sin(ang)
        val out = DoubleArray(shape.size * 2)
        shape.forEachIndexed { i, p ->
            val u = p[0] * sx
            val v = p[1] * sy
            out[2 * i] = x + u * c - v * s
            out[2 * i + 1] = y + u * s + v * c
        }
        return out
    }

    private fun flat(pts: List<DoubleArray>): DoubleArray {
        val out = DoubleArray(pts.size * 2)
        pts.forEachIndexed { i, p ->
            out[2 * i] = p[0]
            out[2 * i + 1] = p[1]
        }
        return out
    }

    // ---- The scene ------------------------------------------------------------

    /** Drawing steps - season.js: GLOW (x, y, r, R, G, B, a), DOT (the same), POLY (R, G, B, a, points), LINE (width, R, G, B, a, points). */
    const val GLOW = 0
    const val DOT = 1
    const val POLY = 2
    const val LINE = 3
    const val MIN_A = 0.002

    class Op(val k: Int, val v: DoubleArray) {
        /** The step's alpha - where it sits depends on the kind. */
        val alpha: Double get() = when (k) {
            POLY -> v[3]
            LINE -> v[4]
            else -> v[6]
        }
    }

    class Scene(
        val ax: Double, val ay: Double, val season: String, val south: Boolean,
        val calendar: Calendar, val ops: List<Op>,
    )

    /**
     * season.js scene(): the same arguments, the same numbers. [tzMin] is
     * this phone's offset from UTC now, minutes east; [t] the wall clock in
     * seconds. [hide] (Still, a serious moment) and [hold] (an approval, an
     * error) are 0..1, eased by the host; [snow] and [rain] the weather the
     * sky is drawing.
     */
    fun scene(
        ms: Double, tzMin: Double, t: Double,
        lat: Double? = null, calm: Boolean = false, hide: Double = 0.0, hold: Double = 0.0,
        ax0: Double = 1.0, ay0: Double = 1.0, sunAlt0: Double? = null,
        snow: Double = 0.0, rain: Double = 0.0,
    ): Scene {
        val ax = if (ax0 > 0) ax0 else 1.0
        val ay = if (ay0 > 0) ay0 else 1.0
        fun num(v: Double) = if (v.isFinite()) clamp(v, 0.0, 1.0) else 0.0
        val all = 1 - num(hide)
        val moving = all * (1 - num(hold))
        val snowW = num(snow)
        val rainW = num(rain)
        val latV = if (lat != null && lat.isFinite()) lat else null
        val sunAlt = if (sunAlt0 != null && sunAlt0.isFinite()) sunAlt0 else null
        val cal = calendar(ms, tzMin, latV)
        val s = cal.seasons
        val items = cal.items
        val tt = if (calm) 0.0 else t
        val hour = cal.local.hour
        val ops = ArrayList<Op>()
        fun put(k: Int, v: DoubleArray) = ops.add(Op(k, v))
        if (all <= 0) return Scene(ax, ay, cal.season, cal.south, cal, ops)
        val fall = 2 * ay + 0.2
        val summer = s.getValue("summer")
        val winter = s.getValue("winter")
        val autumn = s.getValue("autumn")
        val spring = s.getValue("spring")

        // Summer by day: a faint warm haze high on one side.
        val dayW = if (sunAlt != null) smoothstep(4.0, 14.0, sunAlt)
        else min(smoothstep(8.0, 10.0, hour), 1 - smoothstep(17.0, 19.0, hour))
        val hazeA = 0.07 * summer * dayW * (1 - smoothstep(0.1, 0.4, rainW)) * all
        if (hazeA > MIN_A) put(GLOW, doubleArrayOf(0.55 * ax, 0.72, 1.1, 255.0, 226.0, 178.0, hazeA))

        // Winter: a soft snow bank along the floor, higher in the corners.
        val bankA = winter * all
        if (bankA > MIN_A) {
            val n = 24
            val pts = ArrayList<Double>()
            for (i in 0..n) {
                val x = -ax + 2 * ax * i / n
                val bump = exp(-((x - LEFT_X) / 0.30).pow(2)) + 0.8 * exp(-((x - RIGHT_X) / 0.28).pow(2))
                pts.add(x)
                pts.add(FLOOR + 0.015 + 0.07 * bump)
            }
            val top = pts.toDoubleArray()
            pts.addAll(listOf(ax, -ay - 0.05, -ax, -ay - 0.05))
            put(POLY, doubleArrayOf(226.0, 234.0, 242.0, 0.13 * bankA) + pts.toDoubleArray())
            put(LINE, doubleArrayOf(0.012, 236.0, 242.0, 248.0, 0.10 * bankA) + top)
        }

        // Autumn: fallen leaves gathering in the corners.
        val autumnA = autumn * all
        if (autumnA > MIN_A) {
            val nFallen = floor(6 * clamp((cal.day.getValue("autumn") - 10) / 50, 0.0, 1.0)).toInt()
            for (i in 0 until nFallen) {
                val side = if (i % 2 == 0) -1.0 else 1.0
                val h1 = hash01(i * 7 + 1301)
                val h2 = hash01(i * 7 + 1302)
                val h3 = hash01(i * 7 + 1303)
                val c = LEAF_RGB[floor(h3 * 4).toInt() % 4]
                val len = 0.05 + 0.015 * h2
                put(
                    POLY,
                    doubleArrayOf(c[0] * 0.85, c[1] * 0.85, c[2] * 0.85, 0.55 * autumnA) +
                        place(LEAF, side * (0.64 + 0.28 * h1), FLOOR + 0.014 + 0.02 * h2, len, 0.32 * len, (h3 - 0.5) * 0.5),
                )
            }
        }

        // The pumpkin, 24-31 October.
        val pumpA = items.getValue("pumpkin") * moving
        if (pumpA > MIN_A) {
            val u = 0.0155
            val x = RIGHT_X
            val y = FLOOR + 3.4 * u
            put(POLY, doubleArrayOf(176.0, 90.0, 38.0, 0.8 * pumpA) + flat(ellipse(x - 2.5 * u, y, 3.1 * u, 3.1 * u, 20)))
            put(POLY, doubleArrayOf(176.0, 90.0, 38.0, 0.8 * pumpA) + flat(ellipse(x + 2.5 * u, y, 3.1 * u, 3.1 * u, 20)))
            put(POLY, doubleArrayOf(198.0, 106.0, 46.0, 0.85 * pumpA) + flat(ellipse(x, y, 3.4 * u, 3.4 * u, 20)))
            put(
                POLY,
                doubleArrayOf(
                    96.0, 104.0, 60.0, 0.85 * pumpA, x - 0.5 * u, y + 2.9 * u, x + 0.5 * u, y + 2.9 * u,
                    x + 1.1 * u, y + 4.9 * u, x + 0.2 * u, y + 5.1 * u,
                ),
            )
        }

        // The snowman, mid-winter.
        val snA = items.getValue("snowman") * winter * moving
        if (snA > MIN_A) {
            val u = 0.0145
            val x = LEFT_X
            val by = FLOOR + 0.07 + 3.0 * u
            val hy = by + 4.8 * u + 2.4 * u
            put(LINE, doubleArrayOf(0.4 * u, 120.0, 92.0, 70.0, 0.7 * snA, x - 4 * u, by + 1.2 * u, x - 7.5 * u, by + 3.5 * u))
            put(LINE, doubleArrayOf(0.4 * u, 120.0, 92.0, 70.0, 0.7 * snA, x + 4 * u, by + 1.2 * u, x + 7.5 * u, by + 4 * u))
            put(DOT, doubleArrayOf(x, by, 4.8 * u, 236.0, 240.0, 246.0, 0.72 * snA))
            put(DOT, doubleArrayOf(x, hy, 3.2 * u, 240.0, 243.0, 248.0, 0.76 * snA))
            put(
                POLY,
                doubleArrayOf(
                    110.0, 150.0, 160.0, 0.7 * snA, x - 3 * u, hy - 2.4 * u, x + 3 * u, hy - 2.4 * u,
                    x + 2.8 * u, hy - 3.4 * u, x - 2.8 * u, hy - 3.4 * u,
                ),
            )
            put(DOT, doubleArrayOf(x - 1.1 * u, hy + 0.7 * u, 0.45 * u, 44.0, 46.0, 54.0, 0.8 * snA))
            put(DOT, doubleArrayOf(x + 1.1 * u, hy + 0.7 * u, 0.45 * u, 44.0, 46.0, 54.0, 0.8 * snA))
            put(POLY, doubleArrayOf(190.0, 118.0, 78.0, 0.8 * snA, x, hy + 0.2 * u, x + 2.6 * u, hy - 0.4 * u, x, hy - 0.6 * u))
        }

        // A string of soft lights along the top, 18 December - 1 January.
        val lightA = items.getValue("lights") * moving
        if (lightA > MIN_A) {
            fun wire(x: Double) = LIGHTS_TOP - LIGHTS_SAG * abs(sin(PI * (x + ax) / ax))
            val n = 32
            val line = ArrayList<Double>()
            line.addAll(listOf(0.004, 70.0, 74.0, 66.0, 0.5 * lightA))
            for (i in 0..n) {
                val x = -ax + 2 * ax * i / n
                line.add(x)
                line.add(wire(x))
            }
            put(LINE, line.toDoubleArray())
            val nb = max(6, jsRound(2 * ax / 0.15))
            for (i in 0 until nb) {
                val x = -ax + 2 * ax * (i + 0.5) / nb
                val y = wire(x) - 0.013
                val c = BULB_RGB[i % BULB_RGB.size]
                val b = if (calm) 0.9 else 0.85 + 0.15 * sin(tt * TAU / 9 + i * 1.1)
                put(GLOW, doubleArrayOf(x, y, 0.048, c[0], c[1], c[2], 0.18 * b * lightA))
                put(DOT, doubleArrayOf(x, y, 0.012, c[0], c[1], c[2], 0.85 * b * lightA))
            }
        }

        // Summer at dusk and night: a few fireflies.
        val nightW = if (sunAlt != null) 1 - smoothstep(-6.0, 3.0, sunAlt)
        else max(smoothstep(19.5, 21.0, hour), 1 - smoothstep(4.0, 5.5, hour))
        val flyA = summer * nightW * (1 - smoothstep(0.1, 0.4, rainW)) * moving
        if (flyA > MIN_A) {
            val n = if (calm) 4 else 7
            for (i in 0 until n) {
                val hx = hash01(i * 11 + 1501)
                val hy = hash01(i * 11 + 1502)
                val hs = hash01(i * 11 + 1503)
                val hr = hash01(i * 11 + 1504)
                val x = (-0.92 + 1.84 * hx) * ax + 0.10 * sin(tt * 0.11 * (1 + hs) + hx * TAU) + 0.05 * sin(tt * 0.23 + hr * TAU)
                val y = -0.78 + 1.1 * hy + 0.08 * sin(tt * 0.13 * (1 + hr) + hy * TAU) + 0.04 * sin(tt * 0.29 + hs * TAU)
                val g = 0.5 - 0.5 * cos(tt * TAU / (5 + 3 * hs) + hr * TAU)
                val b = if (calm) 0.6 else 0.25 + 0.75 * g * g
                put(GLOW, doubleArrayOf(x, y, 0.055, 206.0, 236.0, 128.0, 0.24 * b * flyA))
                put(DOT, doubleArrayOf(x, y, 0.011, 236.0, 250.0, 190.0, 0.85 * b * flyA))
            }
        }

        // Autumn: leaves drifting down, turning and tumbling as they sway.
        val leafA = autumn * moving
        if (leafA > MIN_A) {
            val n = if (calm) 5 else 9
            for (i in 0 until n) {
                val hx = hash01(i * 13 + 1201)
                val hy = hash01(i * 13 + 1202)
                val hs = hash01(i * 13 + 1203)
                val hc = hash01(i * 13 + 1204)
                val hr = hash01(i * 13 + 1205)
                val speed = 0.045 + 0.03 * hs
                val ph = frac(tt * speed / fall + hy)
                val y = ay + 0.1 - ph * fall
                val w = tt * (0.5 + 0.3 * hr) + hy * TAU
                val sway = sin(w) * (0.05 + 0.04 * hs)
                val x = -ax + frac(hx + (0.10 * ph * fall + sway) / (2 * ax)) * 2 * ax
                val ang = hr * TAU + tt * 0.25 * (if (hr < 0.5) -1 else 1) * (0.5 + hs) + 0.5 * cos(w)
                val len = 0.045 + 0.02 * hs
                val tumble = 0.45 + 0.55 * abs(cos(tt * 0.7 * (0.6 + hr) + hx * TAU))
                val c = LEAF_RGB[floor(hc * 4).toInt() % 4]
                put(POLY, doubleArrayOf(c[0], c[1], c[2], 0.6 * leafA) + place(LEAF, x, y, len, 0.55 * len * tumble, ang))
            }
        }

        // Spring: blossom petals on a light breeze.
        val petalA = spring * moving
        if (petalA > MIN_A) {
            val n = if (calm) 5 else 10
            for (i in 0 until n) {
                val hx = hash01(i * 13 + 1601)
                val hy = hash01(i * 13 + 1602)
                val hs = hash01(i * 13 + 1603)
                val hc = hash01(i * 13 + 1604)
                val hr = hash01(i * 13 + 1605)
                val speed = 0.035 + 0.02 * hs
                val ph = frac(tt * speed / fall + hy)
                val y = ay + 0.1 - ph * fall
                val w = tt * (0.6 + 0.3 * hr) + hy * TAU
                val sway = sin(w) * (0.06 + 0.03 * hs)
                val x = -ax + frac(hx + (0.18 * ph * fall + sway) / (2 * ax)) * 2 * ax
                val ang = hr * TAU + tt * 0.35 * (if (hr < 0.5) -1 else 1) * (0.5 + hs) + 0.4 * cos(w)
                val len = 0.03 + 0.012 * hs
                val tumble = 0.5 + 0.5 * abs(cos(tt * 0.8 * (0.6 + hr) + hx * TAU))
                val c = PETAL_RGB[floor(hc * 3).toInt() % 3]
                put(POLY, doubleArrayOf(c[0], c[1], c[2], 0.62 * petalA) + place(PETAL, x, y, len, 0.7 * len * tumble, ang))
            }
        }

        // Winter: light snowfall, none while the sky draws real snow.
        val flakeA = winter * moving * (1 - smoothstep(0.02, 0.1, snowW))
        if (flakeA > MIN_A) {
            val n = if (calm) 7 else 14
            val fallS = 2 * ay + 0.1
            for (i in 0 until n) {
                val hx = hash01(i * 7 + 1701)
                val hy = hash01(i * 7 + 1702)
                val hs = hash01(i * 7 + 1703)
                val speed = 0.06 + 0.04 * hs
                val ph = frac(tt * speed / fallS + hy)
                val y = ay + 0.05 - ph * fallS
                val sway = sin(tt * 0.5 + hy * TAU) * (0.02 + 0.015 * hs)
                val x = -ax + frac(hx + sway / (2 * ax)) * 2 * ax
                put(DOT, doubleArrayOf(x, y, 0.008 + 0.008 * hs, SNOW_RGB[0], SNOW_RGB[1], SNOW_RGB[2], (0.32 + 0.12 * hs) * flakeA))
            }
        }

        // New Year: a few slow sparkles, once, in the first minute of 1 January.
        val spA = items.getValue("sparkle") * moving
        if (spA > MIN_A) {
            val n = if (calm) 6 else 16
            val sec = cal.sparkleSec
            for (i in 0 until n) {
                val h1 = hash01(i * 9 + 1401)
                val h2 = hash01(i * 9 + 1402)
                val h3 = hash01(i * 9 + 1403)
                val h4 = hash01(i * 9 + 1404)
                val u = (sec - h1 * 42) / 10
                val a = if (calm) 0.6 else (if (u > 0 && u < 1) sin(PI * u).pow(2) else 0.0)
                if (a * spA <= MIN_A) continue
                val x = (if (i % 2 == 0) -1 else 1) * (0.5 + 0.42 * h2) * ax
                val y = 0.1 + 0.75 * h3 + (if (calm) 0.0 else 0.05 * u)
                val r = (0.045 + 0.03 * h4) * (if (calm) 1.0 else 0.8 + 0.2 * sin(PI * u))
                val c = if (i % 2 == 0) doubleArrayOf(255.0, 236.0, 180.0) else doubleArrayOf(240.0, 244.0, 255.0)
                put(GLOW, doubleArrayOf(x, y, 2.2 * r, c[0], c[1], c[2], 0.22 * a * spA))
                put(POLY, doubleArrayOf(c[0], c[1], c[2], 0.85 * a * spA) + place(GLINT, x, y, r, r, h4 * PI / 4))
            }
        }

        // Drop what is too faint to see (the same rule in both apps).
        return Scene(ax, ay, cal.season, cal.south, cal, ops.filter { it.alpha > MIN_A })
    }
}
