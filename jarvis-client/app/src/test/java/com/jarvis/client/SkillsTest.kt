package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Approvals
import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Skills
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Skills on Mind, read the way the desktop's Brain window reads them
 * (`brain.js`, the skills list), and removed the way it removes them
 * (`brain.rs`, `brain_remove_skill`).
 */
class SkillsTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun eachSkillIsReadAsTheDesktopReadsIt() {
        val list = Skills.read(
            obj(
                """{"skills":[
                    {"name":"weather","verdict":"clean","description":"Looks up the forecast",
                     "path":"skills/weather.py","notes":["asks for a city first",{"note":"slow on Mondays"},{"text":""}]},
                    {"id":"mailer","scan":"flagged: sends email","summary":"Sends mail"},
                    {"ok":false},
                    {}]}""",
            ),
        )!!
        assertEquals(listOf("weather", "mailer", "(unnamed)", "(unnamed)"), list.map { it.title })
        assertEquals(
            listOf(
                "Looks up the forecast", "skills/weather.py",
                "Jarvis's note: “asks for a city first”",
                "Jarvis's note: “slow on Mondays”",
            ),
            list[0].lines,
        )
        assertTrue(list[0].clean)
        assertEquals("mailer", list[1].name)
        assertFalse(list[1].clean)
        assertEquals("flagged", list[2].verdict)
        assertEquals("clean", list[3].verdict)
    }

    @Test
    fun aSkillWithNoNameOffersNothingToRemove() {
        val list = Skills.read(obj("""{"skills":[{"verdict":"clean"}]}"""))!!
        assertNull(list.single().name)
    }

    @Test
    fun aBareListIsReadToo() {
        // `probe` hands a bare array over as `items`.
        assertEquals(1, Skills.read(obj("""{"items":[{"name":"x"}]}"""))!!.size)
    }

    @Test
    fun anAnswerWithNoListIsLeftToTheOldView() {
        assertNull(Skills.read(obj("""{"available":true,"dir":"skills"}""")))
    }

    @Test
    fun theRemoveBodyIsTheDesktops() {
        val body = obj(Skills.removeBody("weather \"v2\""))
        assertEquals(setOf("name", "remove"), body.keys)
        assertEquals("weather \"v2\"", body["name"]!!.jsonPrimitive.content)
        assertTrue(body["remove"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun whatIsSaidAfterwardsFollowsTheAnswer() {
        assertEquals("Removed weather.", Skills.removeSaid("weather", DesktopWrite.Outcome.Done(null)))
        val waiting = Skills.removeSaid("weather", DesktopWrite.Outcome.Waiting(null))
        assertTrue(waiting.startsWith("Waiting for your approval to remove weather."))
        assertTrue(waiting.contains(Approvals.WHERE))
        assertEquals("Not removed. It is in use.", Skills.removeSaid("weather", DesktopWrite.Outcome.Refused("It is in use.")))
        assertTrue(Skills.removeWarning("weather").contains("cannot be undone"))
        assertTrue(Skills.failure(ApiError.NotFound)!!.contains("cannot remove skills"))
        assertNull(Skills.failure(ApiError.BadToken))
    }
}
