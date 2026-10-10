package com.jarvis.client.net

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Settings -> Devices on the phone (docs/PAIRING-DESIGN.md §6.4, §7.2): every
 * device that has its own key, with Remove, and the old shared key's row.
 * The shapes and the words; [com.jarvis.client.ui.screens.DevicesSection]
 * draws them. Pure Kotlin, so the JVM tests read it.
 *
 * Never a key and never a hash in any of this - the PC does not send them.
 */
object Devices {

    const val PATH = "/api/devices"
    const val REMOVE_PATH = "/api/devices/remove"
    const val LABEL_PATH = "/api/devices/label"
    const val SHARED_PATH = "/api/devices/shared"
    const val SHARED_PROMPT_RETIRE =
        "Your phone now signs risky approvals. Retire the old shared key now so unverified devices cannot approve risky actions."

    data class Device(
        val id: String,
        val name: String,
        val kind: String,
        val created: Long?,
        val lastSeen: Long?,
        val thisDevice: Boolean,
        val removable: Boolean,
        /**
         * The owner's own name for this device (docs/MULTI-DEVICE-DESIGN.md,
         * the first slice): what he typed on the PC or on the phone, kept
         * beside the key. Empty on the wire when there is none - which is how
         * every device read before this feature arrived reads too, so an older
         * PC needs nothing from here.
         */
        val label: String = "",
        /**
         * What to put on screen: the label when there is one, else the name
         * the device gave itself at pairing ("Pixel 9"). Sent by the PC
         * (`shown`), so this phone and the PC's Settings page can never word
         * one device differently; computed here only for a PC too old to send
         * it, which is exactly `label ?: name`.
         */
        val shown: String = "",
        /**
         * Signed approvals (design §11): "waiting", "true" or "false" -
         * null when the PC's row has no such field (an older PC).
         */
        val approvalKey: String? = null,
    ) {
        /** The name to show, working the same way on an older PC. */
        val displayName: String get() = shown.ifBlank { label.ifBlank { name } }
    }

    data class Shared(
        val retired: Boolean,
        val retiredAt: Long?,
        /**
         * A device holds a key of its own, so the old shared key now works
         * from this PC only - whether or not the owner ever pressed Retire
         * (backend 2026-10-05). False on an older PC that does not say.
         */
        val firstPairOnly: Boolean = false,
        val lastOtherSeen: Long?,
        val lastOtherAddress: String?,
    )

    data class View(
        /** "pc", "shared", or this device's id. */
        val you: String?,
        val devices: List<Device>,
        val shared: Shared?,
        val pairingAvailable: Boolean,
        val pairingWhyNot: String?,
    ) {
        /** True when this phone talks with a key of its own, not the old shared one. */
        val usesOwnKey: Boolean get() = you != null && you != "pc" && you != "shared"
    }

    private fun JsonObject?.str(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject?.long(key: String): Long? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull

    private fun JsonObject?.bool(key: String): Boolean? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    /** `approval_key`: true, false or "waiting" on the wire; anything else is "not said". */
    private fun approvalKeyOf(el: kotlinx.serialization.json.JsonElement?): String? {
        val p = el as? JsonPrimitive ?: return null
        if (p.isString) return p.content.takeIf { it == "waiting" || it == "true" || it == "false" }
        return p.booleanOrNull?.toString()
    }

    /** `GET /api/devices`, read. A row without an id or a name is left out. */
    fun parse(obj: JsonObject): View {
        val you = obj.str("you")
        val rows = (obj["devices"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            val name = o.str("name") ?: return@mapNotNull null
            Device(
                id = id,
                name = name,
                kind = o.str("kind") ?: "phone",
                created = o.long("created"),
                lastSeen = o.long("last_seen"),
                thisDevice = o.bool("this_device") == true || (you != null && id == you),
                removable = o.bool("removable") == true && id != "pc",
                label = o.str("label").orEmpty(),
                shown = o.str("shown").orEmpty(),
                approvalKey = approvalKeyOf(o["approval_key"]),
            )
        }
        val s = obj["shared"] as? JsonObject
        val shared = s?.let {
            Shared(
                retired = it.bool("retired") == true,
                retiredAt = it.long("retired_at"),
                firstPairOnly = it.bool("first_pair_only") == true,
                lastOtherSeen = it.long("last_other_seen"),
                lastOtherAddress = it.str("last_other_address"),
            )
        }
        val pairing = obj["pairing"] as? JsonObject
        return View(
            you = you,
            devices = rows,
            shared = shared,
            pairingAvailable = pairing.bool("available") == true,
            pairingWhyNot = pairing.str("why_not"),
        )
    }

    // ── Words ─────────────────────────────────────────────────────────────

    const val MISSING = "Your PC's Jarvis does not have a device list yet."

    const val SHARED_ROW = "Old shared key - used by this PC, and by devices paired before per-device keys."

    /**
     * The row's line once the first device has a key of its own, so the shared
     * key now works on this PC only - the PC's own words (`DEVICES_WORDS[
     * "shared_first_pair_row"]`, 2026-10-05). Not "Retired": nobody retired it,
     * and saying so would teach the owner the wrong thing about what to do.
     */
    const val SHARED_FIRST_PAIR_ROW =
        "The first device has its own key, so the old shared key now works on this PC only."

    const val THIS_PHONE = "This phone"

    /** "Remove Pixel 9? ..." - asked in place before anything is sent. */
    fun removeQuestion(device: Device): String =
        if (device.thisDevice) {
            "Remove this phone? This phone will stop reaching Jarvis at once and go back to the pairing screen."
        } else {
            "Remove ${device.displayName}? It stops reaching Jarvis at once. To use it again, pair it again with " +
                "the QR code."
        }

    /** The line under a device's name: "phone · paired 3 Sep · last used 2 min ago". */
    fun detailLine(device: Device, nowSec: Long, locale: Locale = Locale.getDefault()): String {
        val parts = mutableListOf(if (device.kind == "pc") "PC" else device.kind)
        device.created?.let { parts += "paired " + day(it, locale) }
        device.lastSeen?.let { parts += "last used " + ago(nowSec - it) }
        return parts.joinToString(" · ")
    }

    /** "3 Sep". */
    fun day(sec: Long, locale: Locale = Locale.getDefault()): String =
        SimpleDateFormat("d MMM", locale).format(Date(sec * 1000L))

    /** "just now", "4 minutes ago", "2 hours ago", "3 days ago". */
    fun ago(seconds: Long): String {
        val s = seconds.coerceAtLeast(0L)
        fun n(v: Long, unit: String) = if (v == 1L) "1 $unit ago" else "$v ${unit}s ago"
        return when {
            s < 60L -> "just now"
            s < 3_600L -> n(s / 60L, "minute")
            s < 86_400L -> n(s / 3_600L, "hour")
            else -> n(s / 86_400L, "day")
        }
    }

    /** The shared key row's state line (design §7.1's three states, plus the
     *  first-pairing one the backend reports from 2026-10-05). */
    fun sharedLine(shared: Shared, nowSec: Long, locale: Locale = Locale.getDefault()): String = when {
        shared.retired ->
            "Retired" + (shared.retiredAt?.let { " on " + day(it, locale) } ?: "") +
                " - it now works on this PC only."
        shared.firstPairOnly -> SHARED_FIRST_PAIR_ROW
        shared.lastOtherSeen != null && nowSec - shared.lastOtherSeen < 30L * 86_400L ->
            "Last used from another device" +
                (shared.lastOtherAddress?.let { " ($it)" } ?: "") + " " + ago(nowSec - shared.lastOtherSeen) +
                ". Pair that device first."
        shared.lastOtherSeen != null ->
            "No other device has used it since " + day(shared.lastOtherSeen, locale) + "."
        else -> "No other device has used it."
    }

    /** Asked in place before "Retire for other devices". */
    fun retireQuestion(shared: Shared, nowSec: Long): String {
        val recent = shared.lastOtherSeen != null && nowSec - shared.lastOtherSeen < 30L * 86_400L
        val base = "Retire the old shared key for other devices? Any device still using it stops reaching Jarvis " +
            "at once. This PC keeps using it."
        return if (recent && shared.lastOtherAddress != null) {
            "$base It was used from ${shared.lastOtherAddress} " + ago(nowSec - shared.lastOtherSeen!!) + "."
        } else {
            base
        }
    }

    fun removeBody(id: String): String = JsonObject(mapOf("id" to JsonPrimitive(id))).toString()

    const val RETIRE_BODY = "{\"retired\":true}"

    /** What `POST /api/devices/remove` said, in words. */
    fun removeSaid(code: Int, body: JsonObject?, name: String): String = when (code) {
        200 -> "$name was removed. It can no longer reach Jarvis."
        404 -> if (body.str("reason") == "no_such_device") "$name was already removed." else MISSING
        400 -> if (body.str("reason") == "not_removable") "This PC cannot be removed." else "Not removed. Try again."
        else -> body.str("error")?.let { "Not removed. $it" } ?: "Not removed. Try again."
    }

    /** Was the removed device this phone itself? */
    fun removedThisPhone(body: JsonObject?): Boolean = body.bool("was_this_device") == true

    // ── Naming a device (docs/MULTI-DEVICE-DESIGN.md, the first slice) ────
    //
    // The owner's own name for a device he already paired: kept beside its key
    // on the PC, shown here and on the PC. No approval card - a label grants
    // nothing and revokes nothing - and never held on a stale link, exactly
    // like Remove. A device can never approve another device: that stays the
    // PC's pairing card, on the PC, with Windows Hello.
    //
    // The four sentences are the PC's own (`DEVICES_WORDS` in
    // backend/jarvis_devices.py), checked word for word by
    // backend/test_devices.py, so a reworded backend cannot leave this phone
    // behind.

    /** Plain ASCII "..." on purpose: this sentence is compared word for word
     *  with the PC's own by backend/test_devices.py, which reads this file as
     *  UTF-8 while devices.rs is read under the machine's own encoding. */
    const val LABEL_BUTTON = "Name this device..."

    const val LABEL_PROMPT =
        "What should Jarvis call this device? Leave it empty to go back to the name it gave itself."

    const val LABEL_BAD =
        "Use a shorter label, with letters, numbers, spaces and - _ . ' ( ) only. Leave it empty to go back " +
            "to the name the device gave itself."

    /** One label, quoted: the same rule the PC applies (letters and digits of
     *  any script, space, and `- _ . ' ( )`, 1-40 characters, or empty). */
    fun labelProblem(label: String): String? {
        if (label.isEmpty()) return null
        if (label.codePointCount(0, label.length) > 40) return LABEL_BAD
        var i = 0
        while (i < label.length) {
            val cp = label.codePointAt(i)
            val ok = Character.isLetterOrDigit(cp) || (cp < 0x80 && cp.toChar() in LABEL_EXTRA)
            if (!ok) return LABEL_BAD
            i += Character.charCount(cp)
        }
        return null
    }

    private val LABEL_EXTRA = setOf(' ', '-', '_', '.', '\'', '(', ')')

    fun labelBody(id: String, label: String): String =
        JsonObject(mapOf("id" to JsonPrimitive(id), "label" to JsonPrimitive(label))).toString()

    /** "{name} is what this device is called now." */
    fun labelDone(shown: String): String = "$shown is what this device is called now."

    /** What `POST /api/devices/label` said, in words. `shown` is the name the
     *  PC says the device has now, or the one this phone already had. */
    fun labelSaid(code: Int, body: JsonObject?, shown: String): String = when (code) {
        200 -> labelDone(body.str("shown") ?: shown)
        404 -> if (body.str("reason") == "no_such_device") "$shown is no longer on the list." else MISSING
        400 -> if (body.str("reason") == "bad_label") LABEL_BAD
        else if (body.str("reason") == "not_labelable") "This PC has no label - it is always this PC."
        else "Not named. Try again."
        else -> body.str("error")?.let { "Not named. $it" } ?: "Not named. Try again."
    }

    /** What `POST /api/devices/shared {"retired": true}` said, in words. */
    fun retireSaid(code: Int, body: JsonObject?): String = when {
        code == 200 -> "The old shared key is retired for other devices. This PC keeps using it."
        code == 409 && body.str("reason") == "uses_it_yourself" ->
            "This phone is still using the old shared key. Pair it with the QR code first, or it would cut " +
                "itself off."
        code == 404 -> MISSING
        else -> body.str("error")?.let { "Not changed. $it" } ?: "Not changed. Try again."
    }
}

/**
 * Why the PC refused this phone's key, when it said (design §5.3): the
 * backend adds `"key": "device_removed"` or `"key": "shared_retired"` to a
 * 401. Every request's 401 passes through [note] (an OkHttp interceptor in
 * [JarvisApi]), and every answered request made with a key clears it
 * ([clear]), so [reason] is always about the latest answer. Only the reason
 * word is kept - never the body, never the key.
 */
object KeyRefusal {

    const val DEVICE_REMOVED = "device_removed"
    const val SHARED_RETIRED = "shared_retired"
    const val SHARED_FIRST_PAIR_ONLY = "shared_first_pair_only"

    const val DEVICE_REMOVED_WORDS =
        "This phone's key was removed on your PC, so Jarvis no longer answers it. Pair again with the QR " +
            "code in Settings, Devices, on your PC."
    const val SHARED_RETIRED_WORDS =
        "This phone was using the old shared key, which has been retired on your PC. Pair it with the QR " +
            "code in Settings, Devices, on your PC."
    const val SHARED_FIRST_PAIR_ONLY_WORDS =
        "This PC gives every device its own key now, so the old shared key works on this PC only. Pair " +
            "this phone with the QR code in Settings, Devices, on your PC."

    private val _reason = MutableStateFlow<String?>(null)
    val reason: StateFlow<String?> = _reason.asStateFlow()

    /** The reason word in a 401's body, or null. */
    fun reasonIn(bodyText: String?): String? {
        val obj = runCatching { JarvisJson.parseToJsonElement(bodyText.orEmpty()) as? JsonObject }.getOrNull()
        val key = (obj?.get("key") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return key?.takeIf { it == DEVICE_REMOVED || it == SHARED_RETIRED || it == SHARED_FIRST_PAIR_ONLY }
    }

    /** A 401 arrived, with this body. */
    fun note(bodyText: String?) {
        _reason.value = reasonIn(bodyText)
    }

    /** A request made with the key was answered without a 401. */
    fun clear() {
        if (_reason.value != null) _reason.value = null
    }

    /** The sentence for [reason], or null when the PC gave none. */
    fun words(reason: String? = _reason.value): String? = when (reason) {
        DEVICE_REMOVED -> DEVICE_REMOVED_WORDS
        SHARED_RETIRED -> SHARED_RETIRED_WORDS
        SHARED_FIRST_PAIR_ONLY -> SHARED_FIRST_PAIR_ONLY_WORDS
        else -> null
    }

    /** Is [text] one of this object's sentences? (MainActivity matches notices as strings.) */
    fun isWords(text: String?): Boolean = text == DEVICE_REMOVED_WORDS ||
        text == SHARED_RETIRED_WORDS || text == SHARED_FIRST_PAIR_ONLY_WORDS
}
