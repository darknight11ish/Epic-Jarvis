package com.jarvis.client.net

import com.jarvis.client.face.Sky
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Sun, moon and weather" behind the animal faces (the owner's decisions of
 * 2026-09-28; docs/JARVIS-API.md section 59; backend `jarvis_sky.py`,
 * `sky.patch`). Both off by default.
 *
 * The PC keeps the settings: whether the sun and moon show, the owner's town
 * (typed on the PC only - this phone never sends one), and the weather
 * source (off, the owner's own Home Assistant, or Open-Meteo online - whose
 * ON is ONE approval card, since it sends the rough position to the
 * internet). `GET /api/sky` hands them over with the PC's own words, which
 * Appearance shows ([com.jarvis.client.ui.screens.SkySection]); the copies
 * below are used only when an answer lacks them.
 *
 * The sun and moon are worked out on this phone ([Sky], a copy of the
 * desktop's sky.js), from the position rounded to 0.1 degree. The phone keeps
 * the last one it heard ([Stored], in its own settings) so the sky keeps
 * moving while the PC cannot be reached; the weather it keeps is dropped once
 * it is 90 minutes old ([Sky.WEATHER_STALE_MS]).
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object SkySettings {
    const val PATH = "/api/sky"

    /** How often the phone asks while connected (the PC reads the weather at most every 20 minutes). */
    const val POLL_MS = 10L * 60 * 1000

    const val TITLE = "Sun, moon and weather"
    const val SHOW_LABEL = "Show the sun and moon behind the animal"
    const val SHOW_DETAIL =
        "The real sun and moon for your town - sunrise and sunset, and the moon's shape (full, " +
            "waxing, waning) - worked out on your own devices. Nothing goes online for it. For the " +
            "animal faces; the others are not changed."
    const val PLACE_LABEL = "Your town"
    const val PLACE_PHONE = "Your town is typed on the PC, in Settings, Animal options."
    const val PLACE_NONE = "No town yet, so there is no sun or moon to show. Type your town on the PC."
    const val FORGET_LABEL = "Forget my town"
    const val WEATHER_LABEL = "Weather in the animal's scene"
    const val WEATHER_DETAIL = "Rain, snow or wind behind the animal. Off by default."
    const val MISSING = "Your PC's Jarvis cannot show the sun, moon or weather yet - run apply-patches.ps1 on the PC."

    val SOURCES = listOf("off", "home_assistant", "open_meteo")

    data class Choice(val id: String, val label: String, val why: String)

    val CHOICES = listOf(
        Choice("off", "Off (default)", "No weather is drawn."),
        Choice(
            "home_assistant", "My Home Assistant",
            "Reads the weather device your Home Assistant already has. Stays on your home network. " +
                "Needs Home Assistant set up for Jarvis on the PC.",
        ),
        Choice(
            "open_meteo", "Open-Meteo (online)",
            "Free, no key. Sends your rough position (about 11 km) to api.open-meteo.com about every " +
                "20 minutes while a face is showing - nothing else. Turning it on takes an approval " +
                "card; turning it off is instant.",
        ),
    )

    data class Place(val name: String, val lat: Double, val lon: Double)

    data class View(
        val title: String,
        val show: Boolean,
        val showLabel: String,
        val showDetail: String,
        val place: Place?,
        val placeLabel: String,
        val placeDetail: String,
        val placeNone: String,
        val forgetLabel: String,
        val source: String,
        val choices: List<Choice>,
        val weatherLabel: String,
        val weatherDetail: String,
        /** The weather now as numbers, or null (off, failed, not read yet). */
        val now: Sky.Weather?,
        /** When [now] was read, ms since 1970. */
        val nowAtMs: Long,
        val status: String,
        val waiting: Boolean,
        /** How the last Open-Meteo card went, in the PC's words, or "". */
        val lastMessage: String,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    /** The weather numbers of `weather.now`, checked - sky.js cleanWeather. */
    fun weatherOf(o: JsonObject?): Pair<Sky.Weather, Long>? {
        if (o == null) return null
        val at = o.num("at") ?: return null
        val dir = (o["dir"] as? JsonPrimitive)?.intOrNull ?: 1
        val w = Sky.Weather(
            o.num("rain") ?: 0.0, o.num("snow") ?: 0.0, o.num("wind") ?: 0.0,
            o.num("cloud") ?: 0.0, o.num("fog") ?: 0.0, dir,
        ).clean()
        return w to (at * 1000).toLong()
    }

    /** `GET /api/sky`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val show = body.flag("show") ?: return null
        val weather = body["weather"] as? JsonObject ?: return null
        val placeObj = body["place"] as? JsonObject
        val place = placeObj?.let { p ->
            val ll = Sky.placeOf(p.num("lat"), p.num("lon")) ?: return@let null
            Place(p.text("name") ?: "", ll.lat, ll.lon)
        }
        val given = (weather["choices"] as? JsonArray)?.mapNotNull { it as? JsonObject }?.associateBy { it.text("id") }
        val choices = CHOICES.map { c ->
            val g = given?.get(c.id)
            Choice(c.id, g?.text("label") ?: c.label, g?.text("why") ?: c.why)
        }
        val now = weatherOf(weather["now"] as? JsonObject)
        return View(
            title = body.text("title") ?: TITLE,
            show = show,
            showLabel = body.text("show_label") ?: SHOW_LABEL,
            showDetail = body.text("show_detail") ?: SHOW_DETAIL,
            place = place,
            placeLabel = body.text("place_label") ?: PLACE_LABEL,
            placeDetail = body.text("place_detail") ?: PLACE_PHONE,
            placeNone = body.text("place_none") ?: PLACE_NONE,
            forgetLabel = body.text("forget_label") ?: FORGET_LABEL,
            source = weather.text("source")?.takeIf { it in SOURCES } ?: "off",
            choices = choices,
            weatherLabel = weather.text("label") ?: WEATHER_LABEL,
            weatherDetail = weather.text("detail") ?: WEATHER_DETAIL,
            now = now?.first,
            nowAtMs = now?.second ?: 0L,
            status = weather.text("status") ?: "",
            waiting = weather.flag("waiting") ?: false,
            lastMessage = (weather["last"] as? JsonObject)?.text("message") ?: "",
        )
    }

    /** A read that failed because this PC has no sky settings. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    // ---- The changes this phone may send (never a town) -----------------------

    fun showBody(on: Boolean): String = JsonObject(mapOf("show" to JsonPrimitive(on))).toString()
    fun forgetBody(): String = JsonObject(mapOf("forget_place" to JsonPrimitive(true))).toString()

    /** Null for anything but the three choices. */
    fun weatherBody(source: String): String? =
        if (source in SOURCES) JsonObject(mapOf("weather" to JsonPrimitive(source))).toString() else null

    /** Whether a change adds something (and so waits for a live link, rule 4). */
    fun adds(body: String): Boolean =
        !(body == showBody(false) || body == forgetBody() || body == weatherBody("off"))

    /** What to say after a change: the PC's sentence, or the plain words of the failure. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.text("said") ?: result.value.text("error") ?: "Done."
        is ApiResult.Failed -> if (missing(result.error)) MISSING else PlainErrors.forApiError(result.error).text
    }

    // ---- What the phone keeps for the face ---------------------------------------

    /** On or off, the rounded position, the weather numbers and when they were read. Never the town's name. */
    data class Stored(val show: Boolean, val place: Sky.Place?, val weather: Sky.Weather?, val weatherAtMs: Long) {
        fun live(nowMs: Long): Sky.Live? = Sky.liveInput(show, place, weather, weatherAtMs, nowMs)
    }

    fun storedOf(v: View?): Stored =
        if (v == null) Stored(false, null, null, 0L)
        else Stored(v.show, v.place?.let { Sky.Place(it.lat, it.lon) }, v.now, v.nowAtMs)

    /** One line of JSON for the phone's own settings. */
    fun encode(s: Stored): String {
        val m = LinkedHashMap<String, kotlinx.serialization.json.JsonElement>()
        m["show"] = JsonPrimitive(s.show)
        s.place?.let {
            m["lat"] = JsonPrimitive(it.lat)
            m["lon"] = JsonPrimitive(it.lon)
        }
        s.weather?.let { w ->
            m["w"] = JsonObject(
                mapOf(
                    "rain" to JsonPrimitive(w.rain), "snow" to JsonPrimitive(w.snow),
                    "wind" to JsonPrimitive(w.wind), "cloud" to JsonPrimitive(w.cloud),
                    "fog" to JsonPrimitive(w.fog), "dir" to JsonPrimitive(w.dir),
                    "at" to JsonPrimitive(s.weatherAtMs / 1000.0),
                ),
            )
        }
        return JsonObject(m).toString()
    }

    /** [encode] read back; anything damaged is "nothing kept". */
    fun decode(text: String?): Stored {
        val o = runCatching { JarvisJson.parseToJsonElement(text ?: "") as? JsonObject }.getOrNull()
            ?: return Stored(false, null, null, 0L)
        val w = weatherOf(o["w"] as? JsonObject)
        return Stored(o.flag("show") ?: false, Sky.placeOf(o.num("lat"), o.num("lon")), w?.first, w?.second ?: 0L)
    }
}
