package com.jarvis.client.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A bare Meshnet or Tailscale name used to become port 80, where nothing
 * listens, with no warning. It now gets Jarvis's port, 4719; anything the
 * owner typed explicitly is kept.
 */
class BaseUrlTest {

    @Test
    fun a_bare_meshnet_name_gets_jarvis_s_port() {
        assertEquals("http://marioirelan11-alps.nord:4719", BaseUrl.normalise("marioirelan11-alps.nord"))
        assertEquals("http://desktop.tail1234.ts.net:4719", BaseUrl.normalise("desktop.tail1234.ts.net/"))
    }

    @Test
    fun plain_http_with_no_port_gets_it_too() {
        assertEquals("http://desktop.ts.net:4719", BaseUrl.normalise("http://desktop.ts.net"))
    }

    /** CONTROL: a port the owner typed is never changed. */
    @Test
    fun a_typed_port_is_kept() {
        assertEquals("http://marioirelan11-alps.nord:4719", BaseUrl.normalise("marioirelan11-alps.nord:4719"))
        assertEquals("http://desktop.ts.net:8080", BaseUrl.normalise("desktop.ts.net:8080"))
        assertEquals("http://desktop.ts.net:80", BaseUrl.normalise("http://desktop.ts.net:80"))
        assertEquals("http://[fd7a:115c::1]:4719", BaseUrl.normalise("[fd7a:115c::1]:4719"))
    }

    /** https with no port means 443 on purpose. */
    @Test
    fun https_is_left_alone() {
        assertEquals("https://desktop.ts.net", BaseUrl.normalise("https://desktop.ts.net"))
    }

    @Test
    fun a_path_is_kept_after_the_added_port() {
        assertEquals("http://desktop.ts.net:4719/jarvis", BaseUrl.normalise("desktop.ts.net/jarvis"))
    }

    @Test
    fun empty_is_not_an_address() {
        assertNull(BaseUrl.normalise(""))
        assertNull(BaseUrl.normalise("   "))
    }

    @Test
    fun an_ipv6_literal_without_a_port_gets_one() {
        assertEquals("http://[fd7a:115c::1]:4719", BaseUrl.normalise("[fd7a:115c::1]"))
    }
}
