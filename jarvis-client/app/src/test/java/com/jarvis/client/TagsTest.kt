package com.jarvis.client

import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.ChatTags
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.pow

/**
 * Chat tags on the phone (docs/CHAT-TAGS-DESIGN.md, section 10 - the frozen
 * contract). The values held here are the contract's own; the shared
 * fixture (contract/history-cases.json) is read by HistoryContractTest where
 * it carries the same keys.
 */
class TagsTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private fun row(id: String, updated: Long, tagId: Int?) = ChatLog.Summary(
        id = id, title = "t$id", started = updated, updated = updated, turns = 2, device = null,
        hasVoice = false, tainted = false, tagId = tagId,
    )

    // ------------------------------------------------------- the look ---

    @Test
    fun `eight colours, ten icons, twelve tags, 24 characters`() {
        assertEquals(listOf("blue", "green", "amber", "violet", "teal", "rose", "slate", "orange"), ChatTags.COLOUR_NAMES)
        assertEquals(
            listOf("briefcase", "book", "home", "folder", "lightbulb", "star", "flag", "wrench", "leaf", "music"),
            ChatTags.ICONS,
        )
        assertEquals(12, ChatTags.MAX_TAGS)
        assertEquals(24, ChatTags.NAME_MAX)
        assertEquals(0.12f, ChatTags.TINT_LIGHT, 0f)
        assertEquals(0.16f, ChatTags.TINT_DARK, 0f)
    }

    @Test
    fun `the palette is section 10's table`() {
        assertEquals(
            listOf("#1d4ed8", "#146c36", "#8a5300", "#6d28d9", "#0f766e", "#be123c", "#475569", "#b43a00"),
            ChatTags.INK_LIGHT.map { "#" + "%06x".format(it) },
        )
        assertEquals(
            listOf("#93b4ff", "#86e0a6", "#f5c26b", "#c4a8ff", "#7adfd3", "#ff9ab5", "#b6c2d1", "#ffb385"),
            ChatTags.INK_DARK.map { "#" + "%06x".format(it) },
        )
    }

    private fun channel(v: Int): Double {
        val c = v / 255.0
        return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
    }

    private fun luminance(rgb: Int): Double =
        0.2126 * channel((rgb shr 16) and 0xFF) + 0.7152 * channel((rgb shr 8) and 0xFF) + 0.0722 * channel(rgb and 0xFF)

    private fun blend(ink: Int, surface: Int, alpha: Double): Int {
        fun mix(shift: Int): Int {
            val a = (ink shr shift) and 0xFF
            val b = (surface shr shift) and 0xFF
            return Math.round(alpha * a + (1 - alpha) * b).toInt()
        }
        return (mix(16) shl 16) or (mix(8) shl 8) or mix(0)
    }

    private fun ratio(a: Int, b: Int): Double {
        val la = luminance(a)
        val lb = luminance(b)
        return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
    }

    @Test
    fun `every ink reads at 4_5 to 1 or better on its own tint, light and dark`() {
        // The app's real surfaces are themes' own; these stand in for a white
        // page and three common dark grounds (the contract's table was checked
        // by the backend builder against both apps' surfaces).
        val lights = listOf(0xFFFFFF)
        val darks = listOf(0x000000, 0x0B0F14, 0x282C34)
        for (slot in 0 until 8) {
            for (s in lights) {
                val ink = ChatTags.ink(slot, dark = false)
                val r = ratio(ink, blend(ink, s, ChatTags.TINT_LIGHT.toDouble()))
                assertTrue("light slot $slot is $r", r >= 4.5)
            }
            for (s in darks) {
                val ink = ChatTags.ink(slot, dark = true)
                val r = ratio(ink, blend(ink, s, ChatTags.TINT_DARK.toDouble()))
                assertTrue("dark slot $slot on ${"%06x".format(s)} is $r", r >= 4.5)
            }
        }
    }

    @Test
    fun `an odd colour slot is slate, never a crash`() {
        assertEquals(ChatTags.INK_LIGHT[6], ChatTags.ink(99, dark = false))
        assertEquals(ChatTags.INK_DARK[6], ChatTags.ink(-1, dark = true))
        assertEquals("slate", ChatTags.colourName(42))
    }

    @Test
    fun `the starter tags are the contract's`() {
        val s = ChatTags.STARTER
        assertEquals(listOf(1, 2, 3, 4, 5), s.map { it.id })
        assertEquals(listOf("Work", "Learning", "Personal", "Projects", "Ideas"), s.map { it.name })
        assertEquals(listOf(0, 1, 2, 3, 4), s.map { it.colour })
        assertEquals(listOf("briefcase", "book", "home", "folder", "lightbulb"), s.map { it.icon })
    }

    // ----------------------------------------------------------- words ---

    @Test
    fun `the shared words, word for word`() {
        assertEquals("Untagged", ChatTags.UNTAGGED)
        assertEquals("All", ChatTags.ALL)
        assertEquals("Tags", ChatTags.EDITOR_TITLE)
        assertEquals("Add a tag", ChatTags.ADD)
        assertEquals("Rename", ChatTags.RENAME)
        assertEquals("Delete this tag", ChatTags.DELETE)
        assertEquals("Move to", ChatTags.MOVE_TO)
        assertEquals("No tag", ChatTags.NO_TAG)
        assertEquals("Work (12)", ChatTags.header("Work", 12))
        assertEquals("Work, 12 chats, collapsed", ChatTags.headerSpoken("Work", 12, expanded = false))
        assertEquals("Work, 12 chats, expanded", ChatTags.headerSpoken("Work", 12, expanded = true))
        assertEquals("Delete the tag Work? Its 3 chats become untagged.", ChatTags.deleteConfirm("Work", 3))
        assertEquals("Tap the chat to file it under Home.", ChatTags.banner("Home"))
    }

    @Test
    fun `the filter chip values: All, Untagged and a tag id`() {
        assertNull(ChatTags.filterKey(""))
        assertEquals(ChatTags.UNTAGGED_KEY, ChatTags.filterKey(ChatTags.NONE_FILTER))
        assertEquals(3, ChatTags.filterKey("3"))
        assertNull(ChatTags.filterKey("x"))
        val rows = listOf(row("a", 2L, null), row("b", 1L, 3))
        val only = ChatTags.group(rows, ChatTags.STARTER, untagged = 1, only = ChatTags.filterKey("none"))
        assertEquals(listOf<Int?>(null), only.map { it.tag?.id })
        assertEquals(listOf("a"), only[0].rows.map { it.id })
    }

    @Test
    fun `each error code has one plain sentence, and the PC's own wins`() {
        val codes = listOf(
            "bad_name", "name_taken", "too_many_tags", "bad_colour", "bad_icon", "tag_not_found", "not_found", "bad_request",
        )
        for (c in codes) {
            val s = ChatTags.errorSentence(c)
            assertTrue("$c has a sentence", s.isNotBlank() && s.endsWith("."))
            assertFalse("$c is plain, not a code", s.contains("_"))
        }
        // A code the app has a sentence for wins; bad_request and unknown codes
        // say what the PC said (the desktop's errorWords is the same rule).
        assertEquals(ChatTags.ERRORS.getValue("bad_name"), ChatTags.errorSentence("bad_name", "Mine."))
        assertEquals(
            "Chat history is off. Tags are not changed.",
            ChatTags.errorSentence("bad_request", "Chat history is off. Tags are not changed."),
        )
        assertEquals("Try later.", ChatTags.errorSentence("weird", "Try later."))
        assertEquals(ChatTags.ERRORS.getValue("bad_request"), ChatTags.errorSentence("bad_request", "  "))
        assertEquals(ChatTags.ERROR_FALLBACK, ChatTags.errorSentence("something_new"))
        assertEquals(ChatTags.ERROR_FALLBACK, ChatTags.errorSentence(null))
    }

    // --------------------------------------------------------- reading ---

    @Test
    fun `the tag list is read in the owner's order, robust to missing and extra fields`() {
        val v = ChatTags.view(
            obj(
                """{"ok":true,"untagged":4,"tags":[
                  {"id":2,"name":"Learning","colour":1,"icon":"book","order":1,"count":3,"extra":"x"},
                  {"id":1,"name":"Work","colour":0,"icon":"briefcase","order":0,"count":9},
                  {"id":7,"name":"  Odd  ","colour":99,"icon":"nope","order":2},
                  {"name":"no id"},
                  {"id":8},
                  {"id":2,"name":"Duplicate","colour":0,"icon":"book","order":5},
                  "junk"
                ]}""",
            ),
        )
        assertNotNull(v)
        v!!
        assertEquals(4, v.untagged)
        assertEquals(listOf(1, 2, 7), v.tags.map { it.id })
        assertEquals(9, v.tags[0].count)
        val odd = v.tags[2]
        assertEquals("Odd", odd.name)
        assertEquals(6, odd.colour) // an unknown slot is slate
        assertEquals("folder", odd.icon) // an unknown icon is a folder
        assertEquals(0, odd.count)
    }

    @Test
    fun `a body that is not the list is not read as one`() {
        assertNull(ChatTags.view(obj("""{"ok":false,"error":"bad_request"}""")))
        assertNull(ChatTags.view(obj("""{"ok":true}""")))
        assertNull(ChatTags.view(obj("""{"conversations":[]}""")))
        val empty = ChatTags.view(obj("""{"ok":true,"tags":[],"untagged":0}"""))
        assertNotNull(empty)
        assertTrue(empty!!.tags.isEmpty())
    }

    @Test
    fun `a write's answer`() {
        val ok = ChatTags.write(
            200,
            obj("""{"ok":true,"tag":{"id":9,"name":"Garage","colour":7,"icon":"wrench","order":5},"tags":[{"id":9,"name":"Garage"}]}"""),
        )
        assertTrue(ok.ok)
        assertEquals("Garage", ok.tag?.name)
        assertEquals(7, ok.tag?.colour)
        assertEquals(1, ok.tags?.size)
        // A file-one-chat answer has neither.
        val filed = ChatTags.write(200, obj("""{"ok":true,"id":"abc","tag_id":3}"""))
        assertTrue(filed.ok)
        assertNull(filed.tag)
        val refused = ChatTags.write(409, obj("""{"ok":false,"error":"name_taken","message":"That name is in use."}"""))
        assertFalse(refused.ok)
        assertEquals(ChatTags.ERRORS.getValue("name_taken"), refused.said)
        val off = ChatTags.write(
            503,
            obj("""{"ok":false,"error":"bad_request","message":"Chat history is off. Tags are not changed."}"""),
        )
        assertEquals("Chat history is off. Tags are not changed.", off.said)
        val noWords = ChatTags.write(400, obj("""{"ok":false,"error":"too_many_tags"}"""))
        assertEquals(ChatTags.errorSentence("too_many_tags"), noWords.said)
        val odd = ChatTags.write(500, null)
        assertFalse(odd.ok)
        assertTrue(odd.said!!.isNotBlank())
    }

    // -------------------------------------------------------- requests ---

    @Test
    fun `names are trimmed and limited to 1 to 24 characters`() {
        assertEquals("Work", ChatTags.validName("  Work "))
        assertNull(ChatTags.validName("   "))
        assertNull(ChatTags.validName(""))
        assertEquals("a".repeat(24), ChatTags.validName("a".repeat(24)))
        assertNull(ChatTags.validName("a".repeat(25)))
        assertNull(ChatTags.addBody(""))
        assertNull(ChatTags.renameBody(3, "x".repeat(30)))
    }

    @Test
    fun `the limit counts code points, never cuts a pair, and a name needs something visible`() {
        val emoji24 = "\uD83D\uDE00".repeat(24)              // 24 code points, 48 UTF-16 units
        assertEquals(emoji24, ChatTags.validName(emoji24))
        assertNull(ChatTags.validName(emoji24 + "\uD83D\uDE00"))
        assertEquals(24, ChatTags.nameLength(ChatTags.clipName("\uD83D\uDE00".repeat(30))))
        val cut = ChatTags.clipName("a".repeat(23) + "\uD83D\uDE00\uD83D\uDE00")
        assertEquals(24, ChatTags.nameLength(cut))
        assertFalse("not cut inside a pair", Character.isHighSurrogate(cut.last()))
        assertEquals("short names are left alone", "Work", ChatTags.clipName("Work"))
        assertNull(ChatTags.validName("\u3164"))
        assertNull(ChatTags.validName("\u200D\u200D"))
        assertNull(ChatTags.validName("  \u3164 "))
        assertNull(ChatTags.validName("\u2800"))
        val family = "\uD83D\uDC68\u200D\uD83D\uDC69\u200D\uD83D\uDC67\u200D\uD83D\uDC66"
        assertEquals(family, ChatTags.validName(family))
        assertEquals("NFC", "Caf\u00E9", ChatTags.validName("Cafe\u0301"))
    }

    @Test
    fun `request bodies are section 10's`() {
        assertEquals(mapOf("op" to "add", "name" to "Garage"), flat(ChatTags.addBody(" Garage ")!!))
        assertEquals(
            mapOf("op" to "add", "name" to "Garage", "colour" to "7", "icon" to "wrench"),
            flat(ChatTags.addBody("Garage", 7, "wrench")!!),
        )
        // An out-of-range colour or unknown icon is not sent at all.
        assertEquals(mapOf("op" to "add", "name" to "G"), flat(ChatTags.addBody("G", 9, "nope")!!))
        assertEquals(mapOf("op" to "rename", "id" to "3", "name" to "Home"), flat(ChatTags.renameBody(3, "Home")!!))
        assertEquals(mapOf("op" to "style", "id" to "3", "colour" to "2"), flat(ChatTags.styleBody(3, colour = 2)!!))
        assertEquals(mapOf("op" to "style", "id" to "3", "icon" to "star"), flat(ChatTags.styleBody(3, icon = "star")!!))
        assertNull(ChatTags.styleBody(3))
        assertNull(ChatTags.styleBody(3, colour = 8))
        assertNull(ChatTags.styleBody(3, icon = "emoji"))
        assertEquals(mapOf("op" to "delete", "id" to "3"), flat(ChatTags.deleteBody(3)))
        assertEquals(mapOf("id" to "chat1", "tag_id" to "4"), flat(ChatTags.fileBody("chat1", 4)))
        assertEquals(mapOf("id" to "chat1", "tag_id" to "null"), flat(ChatTags.fileBody("chat1", null)))
    }

    private fun flat(json: String): Map<String, String> =
        obj(json).mapValues { (_, v) -> v.jsonPrimitive.content }

    @Test
    fun `reordering asks to go before a tag, or to the end`() {
        val t = (1..4).map { ChatTags.Tag(it, "T$it", 0, "folder", it) }
        assertNull(ChatTags.moveUpBody(t, 1))
        assertEquals(mapOf("op" to "move", "id" to "3", "before" to "2"), flat(ChatTags.moveUpBody(t, 3)!!))
        // Down: before the tag two places on, or the end.
        assertEquals(mapOf("op" to "move", "id" to "1", "before" to "3"), flat(ChatTags.moveDownBody(t, 1)!!))
        assertEquals(mapOf("op" to "move", "id" to "3", "before" to "null"), flat(ChatTags.moveDownBody(t, 3)!!))
        assertNull(ChatTags.moveDownBody(t, 4))
        assertNull(ChatTags.moveDownBody(t, 99))
    }

    @Test
    fun `the list path carries only a tag id or none`() {
        assertTrue(ChatLog.listPath(tag = "3").endsWith("&tag=3"))
        assertTrue(ChatLog.listPath(tag = "none").endsWith("&tag=none"))
        assertFalse(ChatLog.listPath(tag = "3&x=1").contains("tag"))
        assertFalse(ChatLog.listPath(tag = "").contains("tag"))
        assertFalse(ChatLog.listPath(tag = "0").contains("tag"))
        assertFalse(ChatLog.listPath(tag = "-2").contains("tag"))
        assertFalse(ChatLog.listPath().contains("tag"))
        assertEquals(
            "/api/history?limit=30&before=99&kind=live&tag=2",
            ChatLog.listPath(99, kind = "live", tag = "2"),
        )
    }

    @Test
    fun `the routes are spelled as the contract has them`() {
        assertEquals("/api/history/tags", ChatTags.TAGS_PATH)
        assertEquals("/api/history/tag", ChatTags.TAG_PATH)
    }

    @Test
    fun `rows and a conversation carry their tag_id, or none from an older PC`() {
        val page = ChatLog.page(
            obj(
                """{"enabled":true,"conversations":[
                  {"id":"a","title":"A","updated":5,"tag_id":3},
                  {"id":"b","title":"B","updated":4,"tag_id":null},
                  {"id":"c","title":"C","updated":3}
                ]}""",
            ),
        )
        assertEquals(listOf(3, null, null), page.conversations.map { it.tagId })
        val t = ChatLog.transcript(obj("""{"id":"a","title":"A","turns":[],"tag_id":3}"""))
        assertEquals(3, t?.tagId)
        assertNull(ChatLog.transcript(obj("""{"id":"a","title":"A","turns":[]}"""))?.tagId)
    }

    // -------------------------------------------------------- grouping ---

    @Test
    fun `sections follow the owner's order, newest first inside, Untagged last`() {
        val tags = listOf(
            ChatTags.Tag(2, "Learning", 1, "book", 0, count = 2),
            ChatTags.Tag(1, "Work", 0, "briefcase", 1, count = 5),
        )
        val rows = listOf(
            row("w-old", 10, 1), row("l1", 50, 2), row("u1", 70, null), row("w-new", 90, 1), row("gone", 60, 99),
        )
        val sections = ChatTags.group(rows, tags, untagged = 2)
        assertEquals(listOf("Learning", "Work", null), sections.map { it.tag?.name })
        assertEquals(listOf("w-new", "w-old"), sections[1].rows.map { it.id })
        // A row whose tag was deleted elsewhere counts as untagged.
        assertEquals(listOf("u1", "gone"), sections[2].rows.map { it.id })
        assertEquals(ChatTags.UNTAGGED_KEY, sections[2].key)
        // The header shows the PC's count, or the loaded rows when that is more.
        assertEquals(5, sections[1].count)
        assertEquals(2, sections[2].count)
        // A filter (Show, or title words) narrows what "N chats" would mean:
        // the header then counts the rows shown, and an empty section goes.
        val narrowed = ChatTags.group(rows, tags, untagged = 2, exact = false)
        assertEquals(listOf(1, 2, 2), narrowed.map { it.count })
        val none = ChatTags.group(listOf(row("w", 1, 1)), tags, untagged = 4, exact = false)
        assertEquals(listOf(1), none.map { it.key })
        assertEquals("nothing loaded, nothing counted: no Untagged section", 1, none.size)
    }

    @Test
    fun `a tag with chats on older pages still shows its count, unless narrowed`() {
        val tags = listOf(ChatTags.Tag(1, "Work", 0, "briefcase", 0, count = 4), ChatTags.Tag(2, "Empty", 1, "book", 1))
        val rows = listOf(row("u", 5, null))
        val all = ChatTags.group(rows, tags, untagged = 1)
        assertEquals(listOf(1, ChatTags.UNTAGGED_KEY), all.map { it.key })
        assertEquals(4, all[0].count)
        assertTrue(all[0].rows.isEmpty())
        assertEquals(listOf(ChatTags.UNTAGGED_KEY), ChatTags.group(rows, tags, untagged = 1, exact = false).map { it.key })
    }

    @Test
    fun `a chat filed elsewhere leaves a list a tag chip is narrowing`() {
        assertTrue(ChatTags.matchesFilter("", 3))
        assertTrue(ChatTags.matchesFilter("", null))
        assertTrue(ChatTags.matchesFilter("3", 3))
        assertFalse(ChatTags.matchesFilter("3", 4))
        assertFalse(ChatTags.matchesFilter("3", null))
        assertTrue(ChatTags.matchesFilter(ChatTags.NONE_FILTER, null))
        assertFalse(ChatTags.matchesFilter(ChatTags.NONE_FILTER, 3))
    }

    @Test
    fun `with no tags at all there are no sections - the list is flat`() {
        assertTrue(ChatTags.group(listOf(row("a", 1, null)), emptyList(), untagged = 1).isEmpty())
    }

    @Test
    fun `Untagged shows only when there is something in it, and one tag can be chosen`() {
        val tags = listOf(ChatTags.Tag(1, "Work", 0, "briefcase", 0))
        val onlyTagged = listOf(row("a", 1, 1))
        assertEquals(listOf(1), ChatTags.group(onlyTagged, tags, untagged = 0).map { it.key })
        assertEquals(listOf(1, ChatTags.UNTAGGED_KEY), ChatTags.group(onlyTagged, tags, untagged = 3).map { it.key })
        assertEquals(listOf(1), ChatTags.group(onlyTagged, tags, untagged = 3, only = 1).map { it.key })
        assertEquals(
            listOf(ChatTags.UNTAGGED_KEY),
            ChatTags.group(listOf(row("z", 1, null)), tags, untagged = 1, only = ChatTags.UNTAGGED_KEY).map { it.key },
        )
    }

    // ------------------------------------------------- "file it" flow ---

    @Test
    fun `an older chat to file is read off the route header`() {
        val f = ChatTags.fileUnderFromRoute(
            """{"open_brain":"history","file_under":3,"history_q":"boiler","quick":true}""",
        )
        assertEquals(ChatTags.FileUnder(3, "boiler"), f)
        assertNull(ChatTags.fileUnderFromRoute(null))
        assertNull(ChatTags.fileUnderFromRoute(""))
        assertNull(ChatTags.fileUnderFromRoute("not json"))
        // Each of the three must be usable.
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"forget-range","file_under":3,"history_q":"x"}"""))
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"history","history_q":"x"}"""))
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"history","file_under":0,"history_q":"x"}"""))
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"history","file_under":3}"""))
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"history","file_under":3,"history_q":"  "}"""))
        // The search words are capped like the search box.
        val long = ChatTags.fileUnderFromRoute(
            """{"open_brain":"history","file_under":3,"history_q":"${"w".repeat(300)}"}""",
        )
        assertEquals(ChatLog.SEARCH_MAX_CHARS, long?.query?.length)
    }

    @Test
    fun `an unrelated route is not a filing request`() {
        assertNull(ChatTags.fileUnderFromRoute("""{"open_settings":"hardware"}"""))
        assertNull(ChatTags.fileUnderFromRoute("""{"open_brain":"history"}"""))
    }
}
