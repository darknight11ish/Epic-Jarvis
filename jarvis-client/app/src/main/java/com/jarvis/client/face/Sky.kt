package com.jarvis.client.face

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.tan

/**
 * The sun, the moon and the weather behind the animal faces (the owner's
 * decisions of 2026-09-28: "Sun and moon behind the animals" and "Weather in
 * the animals' scene" - both optional, both off by default).
 *
 * A LINE-FOR-LINE COPY of the desktop's `jarvis-desktop/src/sky.js`: where
 * the real sun and moon are for a moment and a place, when each next rises
 * and sets, and the scene laid out behind the animal as plain numbers.
 * [SkyDraw] paints it. The two cannot share code, so they share ANSWERS:
 * `tools/gen_sky.py` runs the JavaScript under node and writes
 * `sky-golden.json`, and `SkyTest` fails if this copy disagrees.
 *
 * Nothing here goes online. The place is a latitude and longitude, rounded
 * to 0.1 degree, that the PC worked out from the town the owner typed there
 * (backend `jarvis_sky.py`); this phone keeps the last one it heard, so the
 * sky keeps working while the PC cannot be reached.
 *
 * The formulas (implemented from the published formulas; sky.js's header
 * has the full list): the sun from NOAA's Solar Calculator (Meeus,
 * "Astronomical Algorithms", ch. 22 and 25, low precision); the moon from
 * the Astronomical Almanac's low-precision lunar formulas; its lit fraction
 * and the angle of its bright side from Meeus ch. 48, turned to the screen
 * by the parallactic angle (ch. 14); sidereal time Meeus 12.4; rising and
 * setting at -0.833 degree (the sun) and 0.7275 x parallax - 0.5667 (the
 * moon), Meeus ch. 15, found by stepping and halving.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Sky {
    private const val D = PI / 180.0
    private const val DAY_MS = 86400000.0

    // ---- Small helpers (sky.js has the same, in the same order) -------------

    fun norm360(x: Double): Double {
        val y = x % 360.0
        return if (y < 0) y + 360.0 else y
    }

    /** -180 up to (not including) 180. */
    fun wrap180(x: Double): Double = norm360(x + 180.0) - 180.0

    private fun clamp(v: Double, lo: Double, hi: Double) = max(lo, min(hi, v))

    fun smoothstep(a: Double, b: Double, x: Double): Double {
        val k = clamp((x - a) / (b - a), 0.0, 1.0)
        return k * k * (3 - 2 * k)
    }

    private fun mix(a: Double, b: Double, k: Double) = a + (b - a) * k
    private fun frac(x: Double) = x - floor(x)

    /** The animals' own hash (CritterPose.hash01), 0..1, as a Double. */
    fun hash01(n: Int): Double {
        var x = n xor 0x5bd1e995
        x = (x xor (x ushr 15)) * 0x2c1b3c6d
        x = (x xor (x ushr 12)) * 0x297a2d39
        x = x xor (x ushr 15)
        return (x.toLong() and 0xffffffffL).toDouble() / 4294967296.0
    }

    /** JavaScript's Math.round: halves go up. */
    private fun jsRound(x: Double): Int = floor(x + 0.5).toInt()

    // ---- Time ---------------------------------------------------------------

    fun julianDay(ms: Double): Double = ms / DAY_MS + 2440587.5
    fun centuries(ms: Double): Double = (julianDay(ms) - 2451545.0) / 36525.0

    /** Greenwich mean sidereal time, degrees (Meeus 12.4). */
    fun gmst(ms: Double): Double {
        val d = julianDay(ms) - 2451545.0
        val t = d / 36525.0
        return norm360(280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - t * t * t / 38710000.0)
    }

    // ---- Coordinates --------------------------------------------------------

    data class Equatorial(val ra: Double, val dec: Double)
    data class Horizontal(val alt: Double, val az: Double, val h: Double)

    fun toEquatorial(lambda: Double, beta: Double, eps: Double): Equatorial {
        val l = lambda * D
        val b = beta * D
        val e = eps * D
        val ra = atan2(sin(l) * cos(e) - tan(b) * sin(e), cos(l)) / D
        val dec = asin(sin(b) * cos(e) + cos(b) * sin(e) * sin(l)) / D
        return Equatorial(norm360(ra), dec)
    }

    fun toHorizontal(ra: Double, dec: Double, ms: Double, lat: Double, lon: Double): Horizontal {
        val hDeg = wrap180(gmst(ms) + lon - ra)
        val f = clamp(lat, -89.9, 89.9) * D
        val d = dec * D
        val h = hDeg * D
        val alt = asin(clamp(sin(f) * sin(d) + cos(f) * cos(d) * cos(h), -1.0, 1.0)) / D
        val az = norm360(atan2(sin(h), cos(h) * sin(f) - tan(d) * cos(f)) / D + 180.0)
        return Horizontal(alt, az, hDeg)
    }

    // ---- The sun ------------------------------------------------------------

    private class SunEcl(val lambda: Double, val eps: Double)

    private fun sunEcliptic(t: Double): SunEcl {
        val l0 = norm360(280.46646 + t * (36000.76983 + t * 0.0003032))
        val m = (357.52911 + t * (35999.05029 - 0.0001537 * t)) * D
        val c = sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
            sin(2 * m) * (0.019993 - 0.000101 * t) + sin(3 * m) * 0.000289
        val omega = (125.04 - 1934.136 * t) * D
        val lambda = norm360(l0 + c - 0.00569 - 0.00478 * sin(omega))
        val eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
        val eps = eps0 + 0.00256 * cos(omega)
        return SunEcl(lambda, eps)
    }

    data class Sun(val alt: Double, val az: Double, val h: Double, val ra: Double, val dec: Double, val lambda: Double)

    fun sun(ms: Double, lat: Double, lon: Double): Sun {
        val t = centuries(ms)
        val e = sunEcliptic(t)
        val q = toEquatorial(e.lambda, 0.0, e.eps)
        val h = toHorizontal(q.ra, q.dec, ms, lat, lon)
        return Sun(h.alt, h.az, h.h, q.ra, q.dec, e.lambda)
    }

    // ---- The moon -----------------------------------------------------------

    private class MoonEcl(val lambda: Double, val beta: Double, val parallax: Double)

    private fun moonEcliptic(t: Double): MoonEcl {
        fun s(a: Double, b: Double) = sin((a + b * t) * D)
        fun c(a: Double, b: Double) = cos((a + b * t) * D)
        val lambda = norm360(
            218.32 + 481267.881 * t +
                6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36) +
                0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) -
                0.19 * s(357.5, 35999.05) - 0.11 * s(186.5, 966404.03),
        )
        val beta = 5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) -
            0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21)
        val parallax = 0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36) +
            0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74)
        return MoonEcl(lambda, beta, parallax)
    }

    /** The eight names, in order round the month (new moon first). */
    val PHASES = listOf(
        "New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
        "Full moon", "Waning gibbous", "Last quarter", "Waning crescent",
    )

    fun phaseIndex(elong: Double): Int {
        val e = norm360(elong)
        for (i in 0 until 4) {
            if (abs(wrap180(e - i * 90.0)) < 12.0) return i * 2
        }
        return 1 + 2 * floor(e / 90.0).toInt()
    }

    data class Moon(
        val alt: Double, val altGeo: Double, val az: Double, val h: Double, val ra: Double, val dec: Double,
        val parallax: Double, val elong: Double, val fraction: Double, val waxing: Boolean, val phase: Int,
        val chi: Double, val tilt: Double,
    )

    fun moon(ms: Double, lat: Double, lon: Double): Moon {
        val t = centuries(ms)
        val se = sunEcliptic(t)
        val m = moonEcliptic(t)
        val q = toEquatorial(m.lambda, m.beta, se.eps)
        val h = toHorizontal(q.ra, q.dec, ms, lat, lon)
        val sq = toEquatorial(se.lambda, 0.0, se.eps)
        val elong = norm360(m.lambda - se.lambda)
        val cosPsi = cos(m.beta * D) * cos((m.lambda - se.lambda) * D)
        val fraction = clamp((1 - cosPsi) / 2, 0.0, 1.0)
        val a0 = sq.ra * D
        val d0 = sq.dec * D
        val a = q.ra * D
        val d = q.dec * D
        val chi = norm360(
            atan2(cos(d0) * sin(a0 - a), sin(d0) * cos(d) - cos(d0) * sin(d) * cos(a0 - a)) / D,
        )
        val f = clamp(lat, -89.9, 89.9) * D
        val hr = h.h * D
        val pq = atan2(sin(hr), tan(f) * cos(d) - sin(d) * cos(hr)) / D
        val alt = h.alt - m.parallax * cos(h.alt * D)
        return Moon(
            alt, h.alt, h.az, h.h, q.ra, q.dec, m.parallax, elong, fraction, elong < 180,
            phaseIndex(elong), chi, norm360(chi - pq),
        )
    }

    // ---- Rising and setting -------------------------------------------------

    const val SUN_H0 = -0.833
    const val STEP_MS = 10 * 60 * 1000.0
    private const val HALVINGS = 14

    private fun aboveLine(body: String, ms: Double, lat: Double, lon: Double): Double {
        if (body == "sun") return sun(ms, lat, lon).alt - SUN_H0
        val m = moon(ms, lat, lon)
        return m.altGeo - (0.7275 * m.parallax - 0.5667)
    }

    private fun cross(body: String, a0: Double, b0: Double, lat: Double, lon: Double, up: Boolean): Long {
        var a = a0
        var b = b0
        repeat(HALVINGS) {
            val mid = (a + b) / 2
            val v = aboveLine(body, mid, lat, lon)
            if ((v >= 0) == up) b = mid else a = mid
        }
        return floor((a + b) / 2 + 0.5).toLong()
    }

    data class RiseSet(val rise: Long?, val set: Long?, val up: Boolean)

    /** The next rising and setting after [ms] within [hours] - sky.js nextRiseSet. */
    fun nextRiseSet(body: String, ms: Double, lat: Double, lon: Double, hours: Double = 30.0): RiseSet {
        val n = ceil(hours * 3600000.0 / STEP_MS).toInt()
        var prev = aboveLine(body, ms, lat, lon)
        val up = prev >= 0
        var rise: Long? = null
        var set: Long? = null
        var i = 1
        while (i <= n && (rise == null || set == null)) {
            val t = ms + i * STEP_MS
            val v = aboveLine(body, t, lat, lon)
            if (prev < 0 && v >= 0 && rise == null) rise = cross(body, t - STEP_MS, t, lat, lon, true)
            if (prev >= 0 && v < 0 && set == null) set = cross(body, t - STEP_MS, t, lat, lon, false)
            prev = v
            i++
        }
        return RiseSet(rise, set, up)
    }

    data class Summary(
        val sunUp: Boolean, val sunrise: Long?, val sunset: Long?,
        val moonUp: Boolean, val moonrise: Long?, val moonset: Long?,
        val phase: Int, val phaseName: String, val percent: Int, val waxing: Boolean,
    )

    fun summary(ms: Double, lat: Double, lon: Double): Summary {
        val s = nextRiseSet("sun", ms, lat, lon)
        val m = nextRiseSet("moon", ms, lat, lon)
        val mo = moon(ms, lat, lon)
        return Summary(
            s.up, s.rise, s.set, m.up, m.rise, m.set,
            mo.phase, PHASES[mo.phase], jsRound(mo.fraction * 100), mo.waxing,
        )
    }

    /** sky.js todayWords: the settings line, the same words in both apps. [fmt] turns milliseconds into clock time. */
    fun todayWords(sm: Summary, fmt: (Long) -> String): String {
        val sun = ArrayList<String>()
        sm.sunrise?.let { sun.add("rises ${fmt(it)}") }
        sm.sunset?.let { sun.add("sets ${fmt(it)}") }
        val first = if (sun.isNotEmpty()) "Sun ${sun.joinToString(", ")}."
        else if (sm.sunUp) "The sun stays up all day." else "The sun stays down all day."
        val moon = ArrayList<String>()
        sm.moonrise?.let { moon.add("rises ${fmt(it)}") }
        sm.moonset?.let { moon.add("sets ${fmt(it)}") }
        return "$first Moon: ${sm.phaseName.lowercase()}, ${sm.percent}% lit" +
            (if (moon.isNotEmpty()) ", ${moon.joinToString(", ")}" else "") + "."
    }

    // ---- The scene ----------------------------------------------------------

    const val HORIZON = -0.32
    const val RX = 0.84
    const val RY = 1.21
    const val SUN_R = 0.075
    const val MOON_R = 0.066

    /** [alt, top r, g, b, a, bottom r, g, b, a] - sky.js TINT. */
    val TINT: List<DoubleArray> = listOf(
        doubleArrayOf(-18.0, 12.0, 18.0, 40.0, 0.10, 12.0, 18.0, 40.0, 0.04),
        doubleArrayOf(-8.0, 22.0, 32.0, 74.0, 0.16, 40.0, 40.0, 80.0, 0.10),
        doubleArrayOf(-2.0, 30.0, 44.0, 90.0, 0.18, 120.0, 70.0, 60.0, 0.16),
        doubleArrayOf(6.0, 36.0, 70.0, 118.0, 0.20, 140.0, 96.0, 70.0, 0.14),
        doubleArrayOf(20.0, 36.0, 78.0, 122.0, 0.20, 60.0, 100.0, 138.0, 0.12),
    )

    fun tintAt(alt: Double): DoubleArray {
        val a = clamp(alt, TINT[0][0], TINT[TINT.size - 1][0])
        var i = 0
        while (i < TINT.size - 2 && a > TINT[i + 1][0]) i++
        val lo = TINT[i]
        val hi = TINT[i + 1]
        val k = (a - lo[0]) / (hi[0] - lo[0])
        return DoubleArray(8) { j -> mix(lo[j + 1], hi[j + 1], k) }
    }

    data class Share(val s: Double, val h0: Double)

    fun arcShare(h: Double, dec: Double, lat: Double, h0: Double): Share {
        val f = clamp(lat, -89.9, 89.9) * D
        val d = dec * D
        val c = (sin(h0 * D) - sin(f) * sin(d)) / (cos(f) * cos(d))
        val bigH0 = max(1.0, acos(clamp(c, -1.0, 1.0)) / D)
        return Share((h + bigH0) / (2 * bigH0), bigH0)
    }

    data class ArcPoint(val x: Double, val y: Double, val wrapFade: Double)

    /** sky.js arcPoint: one fixed arc for every season, topping out above the heads and the monkey's vine. */
    fun arcPoint(share: Share, h0: Double, lat: Double): ArcPoint {
        val ang = PI * (1 - share.s)
        val east = if (lat >= 0) 1.0 else -1.0
        val x = east * RX * cos(ang)
        val y = HORIZON + RY * sin(ang)
        val wrapFade = if (h0 >= 179.9) clamp(min(share.s, 1 - share.s) / 0.03, 0.0, 1.0) else 1.0
        return ArcPoint(x, y, wrapFade)
    }

    /** The weather as numbers 0..1 - sky.js cleanWeather. [dir] +1 drifts right on screen, -1 left. */
    data class Weather(
        val rain: Double = 0.0, val snow: Double = 0.0, val wind: Double = 0.0,
        val cloud: Double = 0.0, val fog: Double = 0.0, val dir: Int = 1,
    ) {
        fun clean(): Weather {
            fun n(v: Double) = if (v.isFinite()) clamp(v, 0.0, 1.0) else 0.0
            return Weather(n(rain), n(snow), n(wind), n(cloud), n(fog), if (dir == -1) -1 else 1)
        }
    }

    data class Place(val lat: Double, val lon: Double)

    data class SunDisc(val x: Double, val y: Double, val r: Double, val alpha: Double, val glow: Double, val warm: Double)
    data class MoonDisc(
        val x: Double, val y: Double, val r: Double, val alpha: Double, val glow: Double,
        val fraction: Double, val phase: Int, val bx: Double, val by: Double,
    )
    data class Glow(val x: Double, val y: Double, val r: Double, val alpha: Double)

    class Scene(
        val ax: Double, val ay: Double,
        val tint: DoubleArray?, val glow: Glow?, val sun: SunDisc?, val moon: MoonDisc?,
        /** [x, y, rx, ry, alpha] each. */
        val clouds: List<DoubleArray>, val cloudDay: Double, val fog: Double,
        /** [x, y, dx, dy, alpha] each: a streak from (x, y) to (x - dx, y + dy). */
        val rain: List<DoubleArray>,
        /** [x, y, r, alpha] each. */
        val snow: List<DoubleArray>,
        /** [x, y, length, alpha] each. */
        val wisps: List<DoubleArray>,
        val sunAlt: Double,
    )

    /** sky.js scene(): the same arguments, the same numbers. */
    fun scene(
        ms: Double, t: Double, place: Place?, weather: Weather?,
        calm: Boolean = false, ax0: Double = 1.0, ay0: Double = 1.0,
    ): Scene {
        val ax = if (ax0 > 0) ax0 else 1.0
        val ay = if (ay0 > 0) ay0 else 1.0
        val w = (weather ?: Weather()).clean()
        var dayW = 0.0
        var sunAlt = -90.0
        var tint: DoubleArray? = null
        var glow: Glow? = null
        var sunDisc: SunDisc? = null
        var moonDisc: MoonDisc? = null
        if (place != null && place.lat.isFinite() && place.lon.isFinite()) {
            val lat = clamp(place.lat, -90.0, 90.0)
            val lon = place.lon
            val s = sun(ms, lat, lon)
            sunAlt = s.alt
            dayW = smoothstep(-4.0, 10.0, s.alt)
            tint = tintAt(s.alt)
            val sh = arcShare(s.h, s.dec, lat, SUN_H0)
            val sp = arcPoint(sh, sh.h0, lat)
            val clouded = 1 - 0.65 * w.cloud
            val sunVis = smoothstep(-1.2, 0.8, s.alt) * sp.wrapFade
            val warm = 1 - smoothstep(2.0, 14.0, s.alt)
            sunDisc = SunDisc(sp.x, sp.y, SUN_R, sunVis * clouded, 0.28 * sunVis * (1 - 0.8 * w.cloud), warm)
            val bell = smoothstep(-10.0, -3.0, s.alt) * (1 - smoothstep(3.0, 12.0, s.alt))
            if (bell > 0) {
                glow = Glow(clamp(sp.x, -0.95 * ax, 0.95 * ax), HORIZON, 0.95, 0.20 * bell * (1 - 0.6 * w.cloud))
            }
            val m = moon(ms, lat, lon)
            val mh = arcShare(m.h, m.dec, lat, 0.7275 * m.parallax - 0.5667)
            val mp = arcPoint(mh, mh.h0, lat)
            val moonVis = smoothstep(-1.0, 1.0, m.alt) * mp.wrapFade
            val tr = m.tilt * D
            moonDisc = MoonDisc(
                mp.x, mp.y, MOON_R,
                moonVis * mix(1.0, 0.45, dayW) * clouded,
                0.16 * m.fraction * moonVis * (1 - dayW) * (1 - 0.8 * w.cloud),
                m.fraction, m.phase, -sin(tr), cos(tr),
            )
        }
        val tt = if (calm) 0.0 else t
        val clouds = ArrayList<DoubleArray>()
        if (w.cloud > 0.15) {
            val n = 2 + jsRound(3 * w.cloud)
            val speed = 0.004 + 0.010 * w.wind
            val span = 2 * ax + 0.8
            for (i in 0 until n) {
                val hx = hash01(i * 11 + 101)
                val hy = hash01(i * 11 + 102)
                val hs = hash01(i * 11 + 103)
                val x = -ax - 0.4 + frac(hx + w.dir * tt * speed * (0.7 + 0.6 * hs) / span) * span
                clouds.add(
                    doubleArrayOf(
                        x, 0.22 + 0.5 * hy, 0.26 + 0.12 * hs, 0.09 + 0.04 * hs,
                        (0.08 + 0.10 * w.cloud) * (0.7 + 0.3 * hs),
                    ),
                )
            }
        }
        val rain = ArrayList<DoubleArray>()
        if (w.rain > 0.02) {
            val n = jsRound(8 + 36 * w.rain)
            val slant = w.wind * 0.55 * w.dir
            val fall = 2 * ay + 0.3
            for (i in 0 until n) {
                val hx = hash01(i * 7 + 1)
                val hy = hash01(i * 7 + 2)
                val hs = hash01(i * 7 + 3)
                val speed = 0.9 + 0.5 * hs
                val ph = frac(tt * speed / fall + hy)
                val y = ay + 0.15 - ph * fall
                val x = -ax + frac(hx + slant * ph * fall / (2 * ax)) * 2 * ax
                val len = 0.07 + 0.04 * hs
                rain.add(doubleArrayOf(x, y, slant * len, len, 0.16 + 0.12 * w.rain))
            }
        }
        val snow = ArrayList<DoubleArray>()
        if (w.snow > 0.02) {
            val n = jsRound(10 + 30 * w.snow)
            val fall = 2 * ay + 0.1
            for (i in 0 until n) {
                val hx = hash01(i * 7 + 501)
                val hy = hash01(i * 7 + 502)
                val hs = hash01(i * 7 + 503)
                val speed = 0.10 + 0.08 * hs
                val ph = frac(tt * speed / fall + hy)
                val y = ay + 0.05 - ph * fall
                val sway = sin(tt * 0.6 + hy * 6.2832) * (0.03 + 0.02 * hs)
                val x = -ax + frac(hx + (w.wind * 0.25 * w.dir * ph * fall + sway) / (2 * ax)) * 2 * ax
                snow.add(doubleArrayOf(x, y, 0.010 + 0.010 * hs, 0.35 + 0.25 * w.snow))
            }
        }
        val wisps = ArrayList<DoubleArray>()
        if (w.wind > 0.25) {
            val n = jsRound(6 * w.wind)
            val span = 2 * ax + 0.5
            for (i in 0 until n) {
                val hx = hash01(i * 5 + 901)
                val hy = hash01(i * 5 + 902)
                val hs = hash01(i * 5 + 903)
                val speed = 0.12 + 0.10 * w.wind
                val x = -ax - 0.25 + frac(hx + w.dir * tt * speed * (0.8 + 0.4 * hs) / span) * span
                wisps.add(doubleArrayOf(x, -0.7 + 1.4 * hy, 0.14 + 0.08 * hs, 0.07 * w.wind))
            }
        }
        return Scene(
            ax, ay, tint, glow, sunDisc, moonDisc, clouds, dayW, 0.10 * w.fog,
            rain, snow, wisps, sunAlt,
        )
    }

    /** sky.js moonOutline: the lit part as a closed outline, radius 1, y up. */
    fun moonOutline(fraction: Double, bx: Double, by: Double, n: Int): List<DoubleArray> {
        val e = 2 * clamp(fraction, 0.0, 1.0) - 1
        val pts = ArrayList<DoubleArray>(2 * n)
        fun put(u: Double, v: Double) = pts.add(doubleArrayOf(u * bx - v * by, u * by + v * bx))
        for (i in 0..n) {
            val a = PI / 2 - PI * i / n
            put(cos(a), sin(a))
        }
        for (i in 1 until n) {
            val a = -PI / 2 + PI * i / n
            put(-e * cos(a), sin(a))
        }
        return pts
    }

    /** Weather older than this is not drawn - sky.js WEATHER_STALE_MS. */
    const val WEATHER_STALE_MS = 90L * 60 * 1000

    /** What to draw now - sky.js liveInput. Null when nothing is. */
    data class Live(val place: Place?, val weather: Weather?)

    fun liveInput(show: Boolean, place: Place?, weather: Weather?, weatherAtMs: Long, nowMs: Long): Live? {
        if (!show && weather == null) return null
        val w = if (weather != null && nowMs - weatherAtMs <= WEATHER_STALE_MS) weather.clean() else null
        val p = if (show) place else null
        if (p == null && w == null) return null
        return Live(p, w)
    }

    /** A place as the phone keeps it: rounded to 0.1 degree, or null if it is not a place on Earth. */
    fun placeOf(lat: Double?, lon: Double?): Place? {
        if (lat == null || lon == null || !lat.isFinite() || !lon.isFinite()) return null
        if (abs(lat) > 90 || abs(lon) > 180) return null
        return Place(jsRound(lat * 10) / 10.0, jsRound(lon * 10) / 10.0)
    }
}
