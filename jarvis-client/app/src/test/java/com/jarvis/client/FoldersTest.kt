package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.Folders
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

/**
 * "Folders Jarvis may look in" on the phone (the owner's decisions of
 * 2026-09-26), read from what the PC REALLY answers.
 *
 * `contract/folders-cases.json` is the real `GET /api/folders` answer
 * (jarvis_documents.view()) in named situations, and the PC's refusal of an
 * add from the phone, written by tools/gen_folders_cases.py - byte for byte
 * the file the desktop builds against.
 */
class FoldersTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/folders-cases.json")) {
            "contract/folders-cases.json is missing - run tools/gen_folders_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject

    @Test
    fun `every real answer is read in the PC's own words`() {
        assertTrue(cases.size >= 6)
        for ((name, body) in cases) {
            val v = requireNotNull(Folders.parse(body.jsonObject)) { "$name did not parse" }
            assertEquals(name, body.jsonObject["title"]!!.jsonPrimitive.content, v.title)
            assertEquals(name, Folders.TITLE, v.title)
        }
        val two = Folders.parse(cases["two_folders_phone"]!!.jsonObject)!!
        assertEquals(2, two.folders.size)
        assertEquals("Documents", two.folders[0].name)
        assertEquals("C:\\Users\\owner\\Documents", two.folders[0].path)
        assertTrue(two.detail.contains("outside text"))
        assertTrue(two.phoneAdd.contains("on the PC"))
    }

    @Test
    fun `the phone is never told it may add`() {
        val o = cases["two_folders_phone"]!!.jsonObject
        assertEquals("false", o["can_add"]!!.jsonPrimitive.content)
        val refused = doc["add_from_phone"]!!.jsonObject
        assertEquals(403, refused["status"]!!.jsonPrimitive.content.toInt())
    }

    @Test
    fun `a waiting card, a damaged list and a folder gone from the PC are said`() {
        val w = Folders.parse(cases["waiting"]!!.jsonObject)!!
        assertTrue(w.waiting.endsWith("Notion"))
        assertTrue(w.waitingWords.isNotEmpty())
        val d = Folders.parse(cases["damaged"]!!.jsonObject)!!
        assertTrue(d.folders.isEmpty())
        assertTrue(d.why.contains("damaged"))
        val gone = Folders.Folder("C:\\Gone", "Gone", exists = false)
        assertEquals(listOf("C:\\Gone", Folders.NOT_HERE), Folders.lines(gone))
    }

    @Test
    fun `remove sends one path, quoted properly`() {
        val body = Folders.removeBody("C:\\Users\\owner\\My \"Docs\"")
        val o = JarvisJson.parseToJsonElement(body).jsonObject
        assertEquals("C:\\Users\\owner\\My \"Docs\"", o["path"]!!.jsonPrimitive.content)
        assertEquals(setOf("path"), o.keys)
        assertEquals("Removed.", Folders.said(DesktopWrite.Outcome.Done(null)))
        assertTrue(Folders.said(DesktopWrite.Outcome.Refused("No.")).startsWith("Not changed."))
    }

    @Test
    fun `a PC without it says what to do`() {
        assertTrue(Folders.missing(ApiError.NotFound))
        assertFalse(Folders.missing(ApiError.BadToken))
        assertNull(Folders.parse(JarvisJson.parseToJsonElement("""{"available": false}""").jsonObject))
        assertNotNull(Folders.MISSING)
        assertTrue(Folders.MISSING.contains("apply-patches.ps1"))
    }
}
