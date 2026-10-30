package com.jarvis.client

import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.HistoryView
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Archive and Unarchive for chat history, and the phone's one-tap way into
 * History - the Android half of the owner's request of 2026-10-29: "i want the
 * chat history accessible directly from the jarvis hud on desktop, and one
 * click from the android jarvis app. make sure i can archive and delete chats
 * (with a confirm step)".
 *
 * The wire contract held here, as the backend half builds it:
 * - `GET /api/history?archived=1` lists ONLY archived chats (the default list
 *   never includes them), and every conversation row carries
 *   `"archived": true|false`;
 * - `POST /api/history/archive` body `{"id": "<id>", "archived": true|false}`
 *   answers `{"ok":true,"id","archived"}`, 404 for an unknown chat, 400 for a
 *   body it cannot read - and raises no approval card.
 *
 * Everything here is JVM-only. The screens are held by reading their source
 * (this project's own way for a render that needs a Compose host), and the
 * rules themselves are pure functions.
 */
class HistoryArchiveTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    private fun row(
        id: String,
        title: String = id,
        updated: Long = 1_000L,
        tagId: Int? = null,
        pinned: Boolean = false,
        archived: Boolean = false,
    ) = ChatLog.Summary(
        id = id,
        title = title,
        started = null,
        updated = updated,
        turns = 2,
        device = "phone",
        hasVoice = false,
        tainted = false,
        tagId = tagId,
        pinned = pinned,
        archived = archived,
    )

    // --------------------------------------------------------- reading ---

    @Test
    fun `the list and a word search read the row's archived flag, and only a JSON true is archived`() {
        val body = obj(
            """
            {"conversations": [
              {"id":"a1","updated":3,"archived":true},
              {"id":"a2","updated":2,"archived":false},
              {"id":"a3","updated":1},
              {"id":"a4","updated":0,"archived":"true"}
            ]}
            """.trimIndent(),
        )
        // A string, a missing field or null is NOT archived: nothing is guessed.
        assertEquals(listOf(true, false, false, false), ChatLog.page(body).conversations.map { it.archived })
        // The search route's rows are the same row shape, read the same way.
        val search = ChatLog.search(
            obj(
                """
                {"query_ok":true,"conversations":[
                  {"id":"s1","title":"Dentist","updated":9,"archived":true,
                   "snippet":{"role":"user","parts":[]}}
                ]}
                """.trimIndent(),
            ),
        )
        assertTrue(search.found.single().row.archived)
    }

    @Test
    fun `the list asks for the archived ones only when the view is on`() {
        assertEquals("/api/history?limit=30", ChatLog.listPath())
        assertEquals("/api/history?limit=30&archived=1", ChatLog.listPath(archived = true))
        // The archived flag rides beside the other filters, never replaces them.
        assertEquals(
            "/api/history?limit=30&before=97&kind=chat&tag=3&archived=1",
            ChatLog.listPath(97, kind = "chat", tag = "3", archived = true),
        )
        // False -- the live list -- sends nothing at all: an older PC's request
        // is byte for byte what it always was.
        assertFalse(ChatLog.listPath(archived = false).contains("archived"))
    }

    @Test
    fun `each chat belongs to exactly one view, and an older PC cannot leak a live chat into Archived`() {
        val live = listOf(row("live-1"), row("live-2"))
        val archived = listOf(row("old-1", archived = true))
        assertEquals(live, ChatLog.inView(live, archivedView = false))
        assertTrue(ChatLog.inView(live, archivedView = true).isEmpty())
        assertEquals(archived, ChatLog.inView(archived, archivedView = true))
        assertTrue(ChatLog.inView(archived, archivedView = false).isEmpty())
        // The row-level predicate is the same one, for one row.
        assertTrue(ChatLog.inView(row("x", archived = true), archivedView = true))
        assertFalse(ChatLog.inView(row("x", archived = true), archivedView = false))
        // An older PC sends no `archived` field (all false): in the archived
        // view that is the honest empty list, never a live chat shown as one.
        assertEquals(
            emptyList<String>(),
            ChatLog.inView(listOf(row("older-pc")), archivedView = true).map { it.id },
        )
    }

    // -------------------------------------------------------- request ---

    @Test
    fun `the archive request is the contract's route and exact body`() {
        assertEquals("/api/history/archive", ChatLog.ARCHIVE_PATH)
        assertEquals("""{"id":"conv-00000001","archived":true}""", ChatLog.archiveBody("conv-00000001", true))
        assertEquals("""{"id":"conv-00000001","archived":false}""", ChatLog.archiveBody("conv-00000001", false))
        // Built as JSON, so a quote in an id cannot break out of its field.
        assertEquals(
            """{"id":"a\"b","archived":true}""",
            ChatLog.archiveBody("a\"b", true),
        )
    }

    @Test
    fun `only the PC's yes moves an archive, and the PC's own words are read`() {
        assertEquals(
            ChatLog.Archive(ok = true, archived = true),
            ChatLog.archiveAnswer(200, obj("""{"ok":true,"id":"c-1","archived":true}""")),
        )
        assertEquals(
            ChatLog.Archive(ok = true, archived = false),
            ChatLog.archiveAnswer(200, obj("""{"ok":true,"id":"c-1","archived":false}""")),
        )
        // A 2xx that does not echo `archived` is still a yes; the request stands.
        assertEquals(
            ChatLog.Archive(ok = true, archived = null),
            ChatLog.archiveAnswer(200, obj("""{"ok":true,"id":"c-1"}""")),
        )
        // `ok: false` in a 2xx is NOT a yes.
        assertFalse(ChatLog.archiveAnswer(200, obj("""{"ok":false,"error":"bad_request"}""")).ok)
        assertEquals(
            ChatLog.ARCHIVE_REFUSED,
            ChatLog.archiveAnswer(200, obj("""{"ok":false,"error":"bad_request"}""")).said,
        )
        // The contract's 404: the chat is gone either way.
        assertEquals(ChatLog.ARCHIVE_GONE, ChatLog.archiveAnswer(404, null).said)
        assertEquals(ChatLog.ARCHIVE_GONE, ChatLog.archiveAnswer(404, obj("""{"ok":false,"error":"not_found"}""")).said)
        // The PC's own sentence wins over the phone's fallback; 400 asks again.
        assertEquals(
            "The archive change was not made. Chat history is off.",
            ChatLog.archiveAnswer(400, obj("""{"ok":false,"error":"off","message":"chat history is off"}""")).said,
        )
        // A bodyless 404 reaching the runtime is a PC without the route, not a
        // refusal - the runtime turns it into its own plain sentence.
        assertEquals(
            "This PC's Jarvis cannot archive chats yet. Update it by running apply-patches.ps1 on the PC.",
            ChatLog.ARCHIVE_OLD_PC,
        )
    }

    // ------------------------------------------------- the row's move ---

    @Test
    fun `archiving takes a row out of the live list, and unarchiving brings it back`() {
        val rows = listOf(row("a"), row("b"), row("c", archived = true))
        // The PC said yes to archiving "a".
        val afterArchive = HistoryView.withArchive(rows, "a", archived = true)
        assertEquals(
            listOf("b"),
            ChatLog.inView(afterArchive, archivedView = false).map { it.id },
        )
        assertEquals(
            listOf("a", "c"),
            ChatLog.inView(afterArchive, archivedView = true).map { it.id },
        )
        // The PC said yes to unarchiving "c": it leaves the archived view.
        val afterUnarchive = HistoryView.withArchive(afterArchive, "c", archived = false)
        assertEquals(
            listOf("b", "c"),
            ChatLog.inView(afterUnarchive, archivedView = false).map { it.id },
        )
        assertEquals(
            listOf("a"),
            ChatLog.inView(afterUnarchive, archivedView = true).map { it.id },
        )
        // Nothing else about a row changes: a pin and a tag survive the move.
        val pinned = listOf(row("p", tagId = 3, pinned = true))
        val moved = HistoryView.withArchive(pinned, "p", archived = true).single()
        assertTrue(moved.archived)
        assertTrue(moved.pinned)
        assertEquals(3, moved.tagId)
        // A refusal is never applied: the screen only calls withArchive when
        // the PC's answer is a yes, so a refused request leaves the list alone.
        val refusal = ChatLog.archiveAnswer(400, obj("""{"ok":false,"error":"bad_request"}"""))
        assertFalse(refusal.ok)
        val shown = if (refusal.ok) HistoryView.withArchive(rows, "a", archived = true) else rows
        assertEquals(rows, shown)
    }

    @Test
    fun `the two sentences after a yes say where the chat went`() {
        assertEquals("Archived. It is out of the main list.", ChatLog.archiveSaid(true))
        assertEquals("Unarchived. It is back in the list.", ChatLog.archiveSaid(false))
        assertEquals(ChatLog.ARCHIVED_SAID, ChatLog.archiveSaid(true))
        assertEquals(ChatLog.UNARCHIVED_SAID, ChatLog.archiveSaid(false))
        // The archived view's own empty lines never read as "no chats at all".
        assertEquals("No archived conversations.", ChatLog.ARCHIVED_EMPTY)
        assertEquals("No archived conversations match that filter.", ChatLog.ARCHIVED_NONE_FILTER)
        // The chip and the menu words.
        assertEquals("Archived", ChatLog.ARCHIVED)
        assertEquals("Archive", ChatLog.ARCHIVE)
        assertEquals("Unarchive", ChatLog.UNARCHIVE)
    }

    // ------------------------------------------------------ the wiring ---

    @Test
    fun `the phone's archive wiring holds the rules, and Delete keeps its confirm`() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val history = repoFile("$main/ui/screens/HistoryScreen.kt").readText()
        // The screen archives through the runtime, only after the PC says yes,
        // and moves the row by the view it is showing.
        assertTrue(history.contains("JarvisRuntime.archiveHistory(row.id, want)"))
        assertTrue(history.contains("if (w.ok)"))
        assertTrue(history.contains("HistoryView.withArchive(list, row.id, now)"))
        assertTrue(history.contains("ChatLog.inView("))
        // The archived list is the same read with the archived flag.
        assertTrue(history.contains("archived = archivedView,"))
        // The visible Archived view, beside the "Show" chips, and its own
        // empty words.
        assertTrue(history.contains("ChatLog.ARCHIVED"))
        assertTrue(history.contains("ChatLog.ARCHIVE_FILTER_TITLE"))
        assertTrue(history.contains("ChatLog.ARCHIVED_EMPTY"))
        // The menu reads the row's own state: Unarchive on an archived chat.
        assertTrue(history.contains("HistoryView.menu(tags, filing = false)"))
        assertTrue(history.contains("HistoryView.actionLabel(action, row.pinned, archived = row.archived)"))
        // NO confirm for archiving: the row menu goes straight to the request.
        assertTrue(history.contains("onArchive = { archiveChat(row) }"))
        assertFalse(history.contains("archiveConfirm"))
        // Delete's confirm is EXACTLY as it was, in the same words and the same
        // two buttons - archiving must not have softened the one that cannot
        // be undone.
        assertEquals(
            "Delete this conversation from your PC? This cannot be undone. " + ChatLog.DELETE_KEEPS_FACTS,
            ChatLog.DELETE_CONFIRM,
        )
        assertTrue(history.contains("ChatLog.DELETE_CONFIRM"))
        assertTrue(history.contains("\"Yes, delete it\""))
        assertTrue(history.contains("\"Keep it\""))
        // The archived chip is drawn in the SAME list-head the hidden-lists
        // guard already covers. Since 2026-10-30 it lives in the one Filters
        // sheet that head's button opens (the owner's choice: one row, one
        // Filters button); the head keeps the button and the single tag row.
        val head = history.substringAfter("item(key = \"list-head\")").substringBefore("// Delete from a row's menu")
        assertTrue("the guarded list head lost its Filters door", head.contains("ChatLog.FILTERS_TITLE"))
        assertTrue("the guarded list head lost its single tag row", head.contains("TagFilterChipsRow("))
        val filtersSheet = history.substringAfter("private fun HistoryFiltersSheet(")
        assertTrue("the Filters sheet lost the Archived view", filtersSheet.contains("ChatLog.ARCHIVED"))
        assertTrue("the Filters sheet lost the archived title", filtersSheet.contains("ChatLog.ARCHIVE_FILTER_TITLE"))
        assertTrue("the Filters sheet ignores the hidden-lists guard", history.contains("if (filtersOpen && !privateHidden)"))

        // The runtime holds the write on a stale link and behind the hidden
        // guard, sends only the id and the state, and tells an older PC apart.
        val runtime = repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(runtime.contains("suspend fun archiveHistory(chatId: String, archived: Boolean)"))
        assertTrue(runtime.contains("actionBlocker()?.let { return com.jarvis.client.net.ChatLog.Archive(false, said = it) }"))
        assertTrue(runtime.contains("api.historyArchive(words.archiveBody(chatId, archived))"))
        assertTrue(runtime.contains("words.ARCHIVE_OLD_PC"))
        val archiveRuntime = runtime.substring(runtime.indexOf("suspend fun archiveHistory("))
        assertTrue(
            "an archive is not refused while the lists are hidden",
            archiveRuntime.take(2_500).contains("privateListsHidden"),
        )
        // The API layer carries the archive body and the archived list read.
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun historyArchive(json: String)"))
        assertTrue(api.contains("historyWrite(ChatLog.ARCHIVE_PATH, json)"))
        assertTrue(api.contains("archived = archived"))
        // The route and the row field are read in ONE place, on the wire.
        val log = repoFile("$main/net/ChatLog.kt").readText()
        assertTrue(log.contains("const val ARCHIVE_PATH = \"/api/history/archive\""))
        assertTrue(log.contains("val archived: Boolean = false"))
        assertEquals(2, Regex("archived = o\\.flag\\(\"archived\"\\) == true").findAll(log).count())
        assertTrue(log.contains("(if (archived) \"&archived=1\" else \"\")"))
    }

    @Test
    fun `History is one tap from Home's always-on status line, and it is the one door`() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val home = repoFile("$main/ui/screens/HomeScreen.kt").readText()
        // The control is in StatusLine - the row no size, menu or setting
        // hides - and it calls the ONE action that already opens History.
        val status = home.substringAfter("private fun StatusLine(").substringBefore("private fun StatusWordsRow(")
        assertTrue("the History control is not on the status line", status.contains("ChatLog.HOME_ENTRY"))
        assertTrue(status.contains("onClick = actions.onEarlierChats"))
        assertTrue(status.contains("ChatLog.HOME_ENTRY_TITLE"))
        // It holds no word of a chat and is not gated on the hidden lists, so
        // History stays reachable while they are hidden - History itself hides
        // its list until Show is confirmed.
        assertFalse("Home's History control is gated on the hidden lists", status.contains("memoryHidden"))
        assertFalse("Home's History control draws a chat word", status.contains("lastUserText"))
        // ...and it goes straight to the History screen, not a second one.
        val activity = repoFile("$main/MainActivity.kt").readText()
        assertTrue(activity.contains("onEarlierChats = { nav.go(Screen.HISTORY) }"))
        // 2026-10-30: the More menu's "Earlier chats" row was REMOVED - it
        // opened this same History screen, so it said nothing the status line
        // did not. Home now has no copy of that word at all, and this one
        // control is the door (asserted again across the file, so a second
        // copy cannot come back unnoticed).
        assertFalse("the More menu's Earlier chats row came back", home.contains("ChatHistory.EARLIER_CHATS"))
        assertEquals(0, Regex("ChatHistory\\.EARLIER_CHATS").findAll(home).count())
    }

    /** A file of this repository, found from wherever the tests run. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
