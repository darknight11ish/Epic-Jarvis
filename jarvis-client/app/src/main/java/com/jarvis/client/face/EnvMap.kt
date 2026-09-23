package com.jarvis.client.face

import android.graphics.Bitmap
import android.graphics.BitmapFactory

/**
 * The reflection panorama the three GPU faces (Nucleus, Tokamak, Membrane)
 * sample for their environment term - the same 128x64 picture the reactor
 * kit and the desktop's `faces.html` carry as `ENV_HDRI`, byte for byte.
 *
 * It is a real Poly Haven HDRI (`venice_sunset`), CC0 - public domain, no
 * attribution owed, safe to ship in a sideloaded app - tonemapped, blurred
 * slightly and downsampled by the kit's author. The kit's own note on why it
 * is the one picture in an otherwise procedural renderer: at this size it
 * costs ~11 KB, and it is the difference between a surface that reflects a
 * sky and one that reflects a flat grey.
 *
 * All three faces used to take the kit's no-texture FALLBACK tone instead
 * (`vec3(22, 24, 30) / 255`), on the reasoning that "there is no panorama to
 * sample on a phone". There is - it is this one, and the kit's shaders sample
 * it on every phone that runs the kit. Without it the rims of the torus, the
 * drum and the nucleus mirror a uniform dark grey; with it they pick up the
 * warm horizon and the pale sky, which is most of what made those three read
 * as metal rather than as matte plastic.
 *
 * Held as base64 text rather than as an `res/` drawable because two of the
 * three readers have no `Context` to load a resource with: `Face.draw` is
 * handed a `DrawScope`, and a mesh renderer is built by `MeshFaces` before it
 * is attached to anything. The picture is static, so this costs the same
 * either way.
 */
internal object EnvMap {

    /** The kit's own fallback tone, for the one case where decoding fails. */
    private const val FALLBACK_RGB = 0xFF16181E.toInt()

    /**
     * The decoded panorama, or a 1x1 bitmap of the kit's fallback tone.
     *
     * Never null, on purpose: an AGSL child shader and a GL sampler both have
     * to be bound to SOMETHING, and a 1x1 texture of the fallback tone gives
     * exactly the colour the kit's `envSample` returns when `uHasEnv` is 0 -
     * every tap of the four-tap filter lands on the same texel. So a failed
     * decode degrades to the kit's own fallback picture instead of to a
     * special case in three shaders.
     *
     * Lazy, and thread-safe lazy: the GL faces first touch it on their GL
     * thread, Nucleus on the main thread, and either may be first.
     */
    val bitmap: Bitmap by lazy {
        val bytes = runCatching { java.util.Base64.getMimeDecoder().decode(PNG_B64) }.getOrNull()
        val decoded = bytes?.let {
            // Not premultiplied-sensitive (the picture is opaque RGB), but
            // asked for ARGB_8888 explicitly so both GLUtils.texImage2D and
            // BitmapShader get the format they handle best.
            BitmapFactory.decodeByteArray(
                it, 0, it.size,
                BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888 },
            )
        }
        decoded ?: Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888).apply {
            setPixel(0, 0, FALLBACK_RGB)
        }
    }

    /**
     * `ENV_HDRI` from the kit, without its `data:image/png;base64,` prefix.
     * Wrapped at 100 columns; the MIME decoder skips the line breaks and the
     * indentation.
     */
    private const val PNG_B64 = """
        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
        cfb6Z8OiHZ8+f/fyh99YrM7GNLipmX75f/mf/8yf/pNvvvOZX/vVv7v58dNHD19//1tf5c2H6cXTqPvVaqHP3v+//tu/ufzMn132
        i/uf+8L547dYYrtYm9PsKsjJHK5OQsJoHIEhAFkNwYRqJrmAn5JIWAjWAWvG+b9UwX/l0QLnisGgDjYPjkyUzcE0qlvgYZ+++3/+
        6j/97b+3i2f/Snv95z/9WhfwWM4evPnmYRi++dH2eyFftJtxc/NPd+OodjsOevhwefGYOuEYW7jFtnOS3e4mMHex6eBJ4uXmZr1Y
        rLq48PSpe/1qdZ5BTQjM+ODDZ5fbtOp6Wl4sH761Xp//W//hf3P+5i8Mh11WE4mH7S2LNO3CzDiG2MUYOTAxqgYIuwiFgBioWP8u
        oA8463DeYRV/hljTP6a47R/XS3r3L1MJwTjhO1/51kCLZnV/n/12P+zG1C7Obrc7luZ2s3nyw+//H3/7v//ud7/29MXzP7EOf+WT
        Z5tBn+V24NCRDtlkf/uZR+tG6AfPbn/j/ZsbYzc1y8FAYxr6ID5s4VgKEbnl/a37drtl4Zvd1nI4u3eG0IFIwNshjeYPHz5+uD5s
        Nzuk69v3frwh+p/+uw/f+OwXQ+xuri/N9P3vf/3h47d+6S/8tdfe/Ey/PIvLVbNcC9w0sRuTM5V8p8QoUThGioEbodhwaIk6Rsdo
        BYGd72R36Kcmu99tcXI/6fOg+e0rLZ9OMCDDRkoJh5GuttjjB1/7x7y4f3b/8f/6m3/vK7//e4f9/p0/8YWvf/OfdP3i+UcfPHv2
        Ycvy8ur5fj/umwWv7q96vfnoWdPfWy5WcXcZu/7s9bcM9Gl6kt97mUwJcHAgcndn4VKbFocI3EwNzAJ3IY7MC7YAZVdiG8fhep/O
        +0aZk1mQQN3yw5vbJ1/+h1/5ym8zhTGNBYG+S7/79d/9zTfe/kzXLe/df/1zv/jFR4/e/MRrPxeECCaAMEXhKNwIN0yd0CLQPvK+
        4XWkvuG2E1lEWjToIzpBExACuObc/FhQoMllnrTAVcJn4KvAA+BNohK4ZzfdX18t7j8CMqAEq4WYbBjT5tlV7459Gm4Pu824Pdiz
        2/23v//+N977rW/98Aff/97XF5ZeZPuHX/oHmk9Ch755/bU3zvbDgne38Ux9eLheDOsHt8lfX5/vrl9+OHJWv2cITGTO5ACCiJgb
        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
"""
}
