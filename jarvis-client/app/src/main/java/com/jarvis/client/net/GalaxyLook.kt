package com.jarvis.client.net

/**
 * The Galaxy's looks, as the phone names them (the owner's "galaxy models",
 * 2026-10-28).
 *
 * ## Why this list exists here
 *
 * The look used to be a `localStorage` key on the PC and nothing else
 * (`galaxy-presets.js`'s `PRESET_STORAGE_KEY`), so the phone could not know it,
 * let alone draw it. It is now one key in `/api/appearance`, so both apps share
 * it - and a picker on the phone needs names to show, which is this file.
 *
 * ## Not a hand-kept copy
 *
 * The ids and labels are the desktop module's own: `galaxy-presets.js`'s
 * `BUILT_PRESETS`, written into
 * `app/src/test/resources/contract/galaxy-picture-cases.json` by
 * `tools/gen_galaxy_picture_cases.py`, and compared with this list by
 * `GalaxyPictureTest`. So a look renamed on the desktop fails that test here
 * instead of going quietly stale, and a look added there fails it naming the
 * look this phone has never heard of.
 *
 * [Constellation] is the desktop's own default (`DEFAULT_PRESET`). It is NOT a
 * flat layout - the desktop draws its force simulation - so the phone draws its
 * zen ring for it and says so; see
 * [com.jarvis.client.net.GalaxyPicture.Picture.drawn].
 */
enum class GalaxyLook(val id: String, val label: String) {
    Constellation("constellation", "Constellation"),
    PlanetaryOrbit("planetary-orbit", "Planetary orbit"),
    NeuralArbor("neural-arbor", "Neural arbor"),
    Nebula("nebula", "Nebula"),
    DnaHelix("dna-helix", "DNA helix"),
    RadarDome("radar-dome", "Radar dome"),
    StarMap("star-map", "Star map"),
    CleanTree("clean-tree", "Clean tree"),
    ZenRing("zen-ring", "Zen ring"),
    ;

    /** True when this phone can draw the look. The constellation's picture is
     *  the desktop's simulation, which the phone does not run. */
    val drawable: Boolean get() = this != Constellation

    companion object {
        /** Every look the desktop's module builds, in its own order. */
        val BUILT: List<GalaxyLook> = entries.filter { it.drawable }

        /** What the desktop's `storedPreset()` does with a value it does not
         *  recognise: anything unknown, stale or corrupt is the constellation -
         *  the safe fallback, which can never produce a broken picture. */
        fun byId(id: String?): GalaxyLook =
            entries.firstOrNull { it.id == id } ?: Constellation
    }
}
