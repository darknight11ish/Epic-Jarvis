package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.NotionImport
import com.jarvis.client.net.Upload
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Bring in a Notion export" from the phone (the owner's ask of 2026-11-05;
 * DESIGN.md C1; docs/JARVIS-API.md section 152).
 *
 * The phone carries the `.zip` the owner exported himself and calls the PC's
 * two no-path routes. This suite holds the wire bodies, the plan sentence, the
 * PC's own one-card + Undo words, and every refusal on a plain JVM - and, on
 * the path-taking routes, that the phone still names neither `source` nor
 * `vault` as a path.
 */
class NotionImportTest {

    private fun json(text: String): JsonObject =
        JarvisJson.parseToJsonElement(text) as JsonObject

    private val vaultsAnswer = json(
        """
        {"ok":true,"ready":true,
         "vaults":[
           {"id":"v1","name":"My Vault","path":"C:\\Users\\owner\\My Vault"},
           {"id":"v2","name":"Notes","path":"D:\\Obsidian\\Notes"}
         ],
         "said":"Choose the vault."}
        """.trimIndent(),
    )

    @Test
    fun `the two phone routes are the PC's`() {
        assertEquals("/api/notion/vaults", NotionImport.VAULTS_PATH)
        assertEquals("/api/notion/phone-import", NotionImport.IMPORT_PATH)
        assertEquals("Bring in a Notion export", NotionImport.TITLE)
    }

    @Test
    fun `the vault list is read by name, and the phone never shows a path as the name`() {
        val v = requireNotNull(NotionImport.parseVaults(vaultsAnswer))
        assertTrue(v.ready)
        assertEquals(listOf("My Vault", "Notes"), v.vaults.map { it.name })
        assertEquals("v1", v.vaults[0].id)
        assertEquals("C:\\Users\\owner\\My Vault", v.vaults[0].path)
        assertEquals("My Vault", NotionImport.vaultName("C:\\Users\\owner\\My Vault"))
        assertEquals("Notes", NotionImport.vaultName("D:\\Obsidian\\Notes"))
        assertEquals("Notes", NotionImport.vaultName("/home/owner/Notes"))
    }

    @Test
    fun `a PC with no vault says so in its own sentence`() {
        val v = requireNotNull(
            NotionImport.parseVaults(
                json("""{"ok":true,"ready":false,"vaults":[],"said":"Choose your Obsidian vault on the PC first - Settings, Notes."}"""),
            ),
        )
        assertFalse(v.ready)
        assertTrue(v.vaults.isEmpty())
        assertTrue(v.said.contains("Settings, Notes"))
        // ...and the app has the same sentence as a fallback of its own.
        assertTrue(NotionImport.NO_VAULT.contains("Settings, Notes"))
    }

    @Test
    fun `an answer that is not the route's shape is not read as an empty vault list`() {
        assertNull(NotionImport.parseVaults(json("""{"available":false}""")))
        // An object that says nothing this route knows is not "no vaults yet".
        assertNull(NotionImport.parseVaults(json("""{"hello":"there"}""")))
    }

    @Test
    fun `the plan is read with its counts, its vault and its digest`() {
        val reply = Upload.Reply(
            200,
            json(
                """
                {"ok":true,"said":"Jarvis would like to bring your Notion export into the vault \"My Vault\".",
                 "plan":{"source":"C:\\stage\\Export.zip","vault":"C:\\Users\\owner\\My Vault",
                         "name":"Notion export 2026-11-05","notes":312,"attachments":44,
                         "databases":6,"rows":12,"html_pages":3,"renamed":27,
                         "digest":"9f2c","refused":"","said":""}}
                """.trimIndent(),
            ),
        )
        val ready = NotionImport.readPreview(reply) as NotionImport.Preview.Ready
        val p = ready.plan
        assertEquals(312, p.notes)
        assertEquals(44, p.attachments)
        assertEquals(6, p.databases)
        assertEquals(12, p.rows)
        assertEquals(3, p.htmlPages)
        assertEquals(27, p.renamed)
        assertEquals("9f2c", p.digest)
        assertEquals("My Vault", NotionImport.vaultName(p.vault))
        // The sentence DESIGN.md C1.3 gives, word for word for this plan.
        assertEquals(
            "Your export has 312 notes, 44 attachments and 6 databases. Bring it into \"My Vault\"?",
            NotionImport.planSentence(p),
        )
    }

    @Test
    fun `one of a thing is singular, none is still said`() {
        val p = NotionImport.Plan(
            name = "Export", vault = "C:\\Vaults\\V",
            notes = 1, attachments = 0, databases = 1, rows = 0, htmlPages = 0,
            renamed = 0, digest = "d", said = "",
        )
        assertEquals(
            "Your export has 1 note, 0 attachments and 1 database. Bring it into \"V\"?",
            NotionImport.planSentence(p),
        )
    }

    @Test
    fun `a dry-run refusal is the PC's own reason`() {
        val r = NotionImport.readPreview(
            Upload.Reply(200, json("""{"ok":false,"reason":"there is already a folder called \"Notion export 2026-11-05\" in that vault"}""")),
        ) as NotionImport.Preview.Refused
        assertTrue(r.why.contains("already a folder"))
        assertTrue(NotionImport.readPreview(Upload.Reply(404, null)) is NotionImport.Preview.NotHere)
        assertTrue(NotionImport.readPreview(Upload.Reply(503, null)) is NotionImport.Preview.NotHere)
    }

    @Test
    fun `the import body names an upload id and a vault id - never a path`() {
        val dry = json(NotionImport.body("u9", "v1"))
        assertEquals("u9", dry["upload"]!!.jsonPrimitive.content)
        assertEquals("v1", dry["vault"]!!.jsonPrimitive.content)
        assertEquals(setOf("upload", "vault"), dry.keys)
        assertFalse("no source path may cross the wire", dry.containsKey("source"))

        val real = json(NotionImport.body("u9", "v1", "9f2c"))
        assertEquals("9f2c", real["digest"]!!.jsonPrimitive.content)
        assertEquals(setOf("upload", "vault", "digest"), real.keys)
        assertFalse("no vault path may cross the wire", real.containsKey("path"))
    }

    @Test
    fun `what was brought in is the PC's sentence, and Undo is said with it`() {
        val answer = json(
            """{"ok":true,"folder":"C:\\Users\\owner\\My Vault\\Notion export 2026-11-05","notes":312,
                "attachments":44,"databases":6,"said":"Brought 312 note(s) into \"Notion export 2026-11-05\"."}""",
        )
        assertEquals(
            "Brought 312 note(s) into \"Notion export 2026-11-05\".",
            NotionImport.imported(answer, null),
        )
        // A PC that sent no sentence gets one built from its own numbers, and Undo is named.
        val built = NotionImport.imported(
            json("""{"ok":true,"folder":"C:\\Vault\\Notion export","notes":7}"""),
            null,
        )
        assertTrue(built.contains("Brought 7 notes into \"Notion export\"."))
        assertTrue(built.contains(NotionImport.UNDO))
        assertNull(NotionImport.refusal(answer))
    }

    @Test
    fun `a denied or refused import changes nothing, in the PC's words`() {
        val denial = NotionImport.refusal(json("""{"ok":false,"reason":"not approved; nothing was brought in"}"""))
        assertEquals("not approved; nothing was brought in", denial)
        assertEquals(
            "Nothing was brought in: Not approved; nothing was brought in.",
            NotionImport.nothing(denial!!),
        )
        assertNull(NotionImport.refusal(json("""{"ok":true,"imported":true}""")))
        assertEquals("Nothing was brought in.", NotionImport.nothing(""))
    }

    @Test
    fun `the one-card and Undo words are the PC's, from section 152`() {
        // Copied, not invented: "writes the vault after ONE person's yes",
        // "a denied, timed-out or refused card brings nothing in", "so Undo
        // takes the folder back off".
        assertTrue(NotionImport.ONE_YES.contains("after one person's yes"))
        assertTrue(NotionImport.DENIED.contains("denied, timed-out or refused card brings nothing in"))
        assertTrue(NotionImport.UNDO.contains("Undo takes the folder back off"))
        assertEquals(
            "${NotionImport.ONE_YES} ${NotionImport.DENIED} ${NotionImport.UNDO}",
            NotionImport.promise(),
        )
    }

    @Test
    fun `the phone asks the PC first, and a PC without the routes writes nothing`() {
        assertTrue(NotionImport.NOT_HERE.contains("not available on this PC"))
        assertTrue(NotionImport.WAITING.contains("approve the card"))
        assertTrue(NotionImport.CONFIRM.isNotEmpty())
        assertTrue(NotionImport.CANCEL.isNotEmpty())
        assertTrue(NotionImport.HOW.contains("Markdown & CSV"))
    }
}
