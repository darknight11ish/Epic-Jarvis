package com.jarvis.client

import com.jarvis.client.net.DeviceKey
import com.jarvis.client.net.Devices
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.KeyRefusal
import com.jarvis.client.net.PlainErrors
import kotlinx.serialization.json.JsonObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

/**
 * Settings -> Devices (docs/PAIRING-DESIGN.md §6.4), the refused-key
 * reasons (§5.3) and the device key's shape in the scrubbers (§5.1, §8.6).
 */
class DevicesTest {

    /** [KeyRefusal] is process-wide: never leave a reason behind for another test. */
    @After
    fun forget() = KeyRefusal.clear()

    private fun obj(text: String) = JarvisJson.parseToJsonElement(text) as JsonObject

    private val designList = obj(
        """
        {"you": "d3f9a1c2e",
         "devices": [
           {"id": "pc", "name": "This PC", "kind": "pc", "removable": false},
           {"id": "d3f9a1c2e", "name": "Pixel 9", "kind": "phone",
            "created": 1790000000, "last_seen": 1790003600,
            "this_device": true, "removable": true, "approval_key": false}],
         "shared": {"retired": false, "retired_at": null,
                    "last_other_seen": 1790003000, "last_other_address": "100.101.2.3",
                    "can_bring_back_here": false},
         "pairing": {"available": true, "why_not": null}}
        """,
    )

    @Test
    fun `the design's list reads`() {
        val v = Devices.parse(designList)
        assertEquals("d3f9a1c2e", v.you)
        assertTrue(v.usesOwnKey)
        assertEquals(2, v.devices.size)
        val pc = v.devices[0]
        assertEquals("pc", pc.id)
        assertFalse(pc.removable)
        assertFalse(pc.thisDevice)
        val phone = v.devices[1]
        assertEquals("Pixel 9", phone.name)
        assertTrue(phone.thisDevice)
        assertTrue(phone.removable)
        assertEquals(1790000000L, phone.created)
        assertEquals(1790003600L, phone.lastSeen)
        val shared = v.shared!!
        assertFalse(shared.retired)
        assertNull(shared.retiredAt)
        assertEquals("100.101.2.3", shared.lastOtherAddress)
        assertTrue(v.pairingAvailable)
        assertNull(v.pairingWhyNot)
    }

    @Test
    fun `a phone on the old shared key does not use its own key`() {
        val v = Devices.parse(obj("""{"you": "shared", "devices": []}"""))
        assertFalse(v.usesOwnKey)
        assertFalse(Devices.parse(obj("""{"you": "pc"}""")).usesOwnKey)
        assertFalse(Devices.parse(obj("""{}""")).usesOwnKey)
    }

    @Test
    fun `odd rows are skipped, and pc is never removable`() {
        val v = Devices.parse(
            obj("""{"devices": [{"name": "no id"}, {"id": "x"}, 3, {"id": "pc", "name": "This PC", "removable": true}]}"""),
        )
        assertEquals(1, v.devices.size)
        assertFalse(v.devices[0].removable)
    }

    @Test
    fun `the words`() {
        val v = Devices.parse(designList)
        assertEquals(
            "Remove this phone? This phone will stop reaching Jarvis at once and go back to the pairing screen.",
            Devices.removeQuestion(v.devices[1]),
        )
        assertEquals(
            "Remove Tab? It stops reaching Jarvis at once. To use it again, pair it again with the QR code.",
            Devices.removeQuestion(v.devices[1].copy(name = "Tab", thisDevice = false)),
        )
        val now = 1790003600L + 120L
        assertEquals(
            "phone · paired " + Devices.day(1790000000L, Locale.UK) + " · last used 2 minutes ago",
            Devices.detailLine(v.devices[1], now, Locale.UK),
        )
        assertTrue(Devices.day(1790000000L, Locale.UK).matches(Regex("\\d{1,2} \\w+")))
        assertTrue(
            Devices.sharedLine(v.shared!!, now).startsWith("Last used from another device (100.101.2.3) "),
        )
        assertTrue(Devices.sharedLine(v.shared!!.copy(retired = true, retiredAt = 1790000000L), now).endsWith(
            " - it now works on this PC only.",
        ))
        assertEquals("just now", Devices.ago(30))
        assertEquals("1 minute ago", Devices.ago(60))
        assertEquals("3 hours ago", Devices.ago(3 * 3600 + 5))
        assertEquals("2 days ago", Devices.ago(2 * 86400))
    }

    @Test
    fun `remove and retire answers`() {
        assertEquals("{\"id\":\"d3f9a1c2e\"}", Devices.removeBody("d3f9a1c2e"))
        assertEquals("Pixel 9 was removed. It can no longer reach Jarvis.", Devices.removeSaid(200, obj("{}"), "Pixel 9"))
        assertEquals("Pixel 9 was already removed.", Devices.removeSaid(404, obj("""{"reason":"no_such_device"}"""), "Pixel 9"))
        assertEquals("This PC cannot be removed.", Devices.removeSaid(400, obj("""{"reason":"not_removable"}"""), "x"))
        assertTrue(Devices.removedThisPhone(obj("""{"ok":true,"was_this_device":true}""")))
        assertFalse(Devices.removedThisPhone(obj("""{"ok":true}""")))
        assertTrue(Devices.retireSaid(409, obj("""{"reason":"uses_it_yourself"}""")).startsWith("This phone is still using"))
    }

    @Test
    fun `a 401 that says why is kept as a reason word only`() {
        assertEquals(KeyRefusal.DEVICE_REMOVED, KeyRefusal.reasonIn("""{"error":"bad or missing X-Jarvis-Token","key":"device_removed"}"""))
        assertEquals(KeyRefusal.SHARED_RETIRED, KeyRefusal.reasonIn("""{"key":"shared_retired"}"""))
        assertNull(KeyRefusal.reasonIn("""{"error":"bad or missing X-Jarvis-Token"}"""))
        assertNull(KeyRefusal.reasonIn("""{"key":"something_else"}"""))
        assertNull(KeyRefusal.reasonIn("not json"))
        assertNull(KeyRefusal.reasonIn(null))

        KeyRefusal.note("""{"key":"device_removed"}""")
        assertEquals(KeyRefusal.DEVICE_REMOVED_WORDS, KeyRefusal.words())
        assertTrue(KeyRefusal.isWords(KeyRefusal.words()))
        KeyRefusal.note("""{"key":"shared_retired"}""")
        assertEquals(KeyRefusal.SHARED_RETIRED_WORDS, KeyRefusal.words())
        KeyRefusal.clear()
        assertNull(KeyRefusal.words())
        assertFalse(KeyRefusal.isWords("The desktop refused this phone's token."))
    }

    @Test
    fun `naming a device - the label, and what it goes back to`() {
        // docs/MULTI-DEVICE-DESIGN.md, the first slice: the owner's own name
        // for a device he already paired, kept beside its key on the PC.
        val labelled = Devices.parse(
            obj(
                """
                {"you": "d3f9a1c2e",
                 "devices": [{"id": "d3f9a1c2e", "name": "Pixel 9", "shown": "Garden phone",
                              "label": "Garden phone", "kind": "phone", "removable": true},
                             {"id": "d11112222", "name": "Tablet", "shown": "Garden phone",
                              "label": "Garden phone", "kind": "tablet", "removable": true}]}
                """,
            ),
        )
        // This phone itself, named: the one-line "Remove this phone?" is
        // unchanged (it never names the phone, because the owner is holding it).
        assertEquals("Garden phone", labelled.devices[0].displayName)
        assertEquals(
            "Remove this phone? This phone will stop reaching Jarvis at once and go back to the pairing screen.",
            Devices.removeQuestion(labelled.devices[0]),
        )
        // Another device, named: the label is what the question asks about,
        // because that is the name the owner just pressed Remove on.
        val d = labelled.devices[1]
        assertEquals("Tablet", d.name)
        assertEquals("Garden phone", d.label)
        assertEquals("Garden phone", d.displayName)
        assertEquals(
            "Remove Garden phone? It stops reaching Jarvis at once. To use it again, pair it again with the QR code.",
            Devices.removeQuestion(d),
        )

        // A device with no label, and a PC too old to send `shown`: `name`.
        val plain = Devices.parse(
            obj("""{"you": "pc", "devices": [{"id": "d3f9a1c2e", "name": "Pixel 9", "kind": "phone"}]}"""),
        ).devices[0]
        assertEquals("", plain.label)
        assertEquals("Pixel 9", plain.displayName)
        val onlyShown = Devices.parse(
            obj("""{"devices": [{"id": "d1", "name": "Pixel 9", "shown": "Garden phone"}]}"""),
        ).devices[0]
        assertEquals("Garden phone", onlyShown.displayName)
    }

    @Test
    fun `naming a device - the body, the rule, and the answers`() {
        assertEquals("""{"id":"d3f9a1c2e","label":"Garden phone"}""", Devices.labelBody("d3f9a1c2e", "Garden phone"))
        assertEquals("""{"id":"d3f9a1c2e","label":""}""", Devices.labelBody("d3f9a1c2e", ""))

        // The same rule as a paired name: 1-40 characters of letters and
        // digits in any script, space, and - _ . ' ( ) - and the empty string
        // is how a label is cleared, so it is always allowed.
        assertNull(Devices.labelProblem(""))
        assertNull(Devices.labelProblem("Garden phone"))
        assertNull(Devices.labelProblem("Sam's (old) phone"))
        assertNull(Devices.labelProblem("A".repeat(40)))
        assertEquals(Devices.LABEL_BAD, Devices.labelProblem("A".repeat(41)))
        assertEquals(Devices.LABEL_BAD, Devices.labelProblem("Phone\nsecond line"))
        assertEquals(Devices.LABEL_BAD, Devices.labelProblem("Phone | Fake card"))
        assertEquals(Devices.LABEL_BAD, Devices.labelProblem("<b>Phone</b>"))

        assertEquals(
            "Garden phone is what this device is called now.",
            Devices.labelSaid(200, obj("""{"shown": "Garden phone"}"""), "Pixel 9"),
        )
        // The PC's own words for a refusal, never invented here.
        assertEquals(Devices.LABEL_BAD, Devices.labelSaid(400, obj("""{"reason": "bad_label"}"""), "x"))
        assertEquals("This PC has no label - it is always this PC.", Devices.labelSaid(400, obj("""{"reason": "not_labelable"}"""), "x"))
        assertEquals("Pixel 9 is no longer on the list.", Devices.labelSaid(404, obj("""{"reason": "no_such_device"}"""), "Pixel 9"))
        assertTrue(Devices.labelSaid(503, obj("""{"error": "The device list could not be written."}"""), "x").startsWith("Not named."))
    }

    @Test
    fun `the design's sentences, word for word`() {
        assertEquals(
            "This phone's key was removed on your PC, so Jarvis no longer answers it. Pair again with the QR " +
                "code in Settings, Devices, on your PC.",
            KeyRefusal.DEVICE_REMOVED_WORDS,
        )
        assertEquals(
            "This phone was using the old shared key, which has been retired on your PC. Pair it with the QR " +
                "code in Settings, Devices, on your PC.",
            KeyRefusal.SHARED_RETIRED_WORDS,
        )
    }

    @Test
    fun `a device key has its own shape, and the scrubbers hide it`() {
        val key = "jdk1.d3f9a1c2e." + "A".repeat(20) + "b_-" + "9".repeat(20)
        assertEquals(58, key.length)
        assertTrue(DeviceKey.isDeviceKey(key))
        assertEquals("d3f9a1c2e", DeviceKey.idOf(key))
        assertFalse(DeviceKey.isDeviceKey("jdk1.D3F9A1C2E." + "A".repeat(43)))
        assertFalse(DeviceKey.isDeviceKey("jdk1.d3f9a1c2." + "A".repeat(43)))
        assertFalse(DeviceKey.isDeviceKey("jdk1.d3f9a1c2e." + "A".repeat(42)))
        assertFalse(DeviceKey.isDeviceKey("A".repeat(43)))
        assertNull(DeviceKey.idOf("A".repeat(43)))

        assertEquals("sent «token» then", DeviceKey.scrub("sent $key then", "«token»"))
        val shown = PlainErrors.scrubDetails("failed with $key at 100.64.0.1")
        assertFalse(shown, key in shown)
        assertFalse(shown, "AAAAAAAAAAAAAAAAAAAAb_-" in shown)
        assertTrue(shown, "100.64.0.1" in shown)
    }
}
