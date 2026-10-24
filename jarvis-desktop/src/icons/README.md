# PWA icons (jarvis-180 / jarvis-192 / jarvis-512)

These three PNGs are the home-screen tile for the browser HUD
(`../manifest.webmanifest`). They are drawn from the HUD's own monochrome
emblem - the `◈` mark the Studio rail shows, in the HUD's ice accent on the
deep-space well - and contain no third-party artwork, so there is no licence
to carry for them.

The names match the static whitelist merged with PWA Slice 3a
(`jarvis-backend/jarvis_hud.py`'s `STATIC_ASSETS`), so the manifest's `src`
values and the served URLs are the same set, exactly:

| file | size | purpose |
|---|---|---|
| `jarvis-180.png` | 180x180 | `any` (also the future `apple-touch-icon`) |
| `jarvis-192.png` | 192x192 | `any` |
| `jarvis-512.png` | 512x512 | `any maskable` - the mark is kept inside Android's 80% safe circle |

Colours come from the HUD's own theme tokens, not from typed hex here:

- background `#04070c` = `themes.deep-space.surfaceSunken` (`tokens/themes.tokens.json`)
- ink `#38f0ff` = `themes.deep-space.accent`

Regenerate after a palette or mark change (Pillow is needed only for this):

```powershell
cd jarvis-desktop
py -3 scripts/make-pwa-icons.py
```

The script is deterministic: same tokens in, byte-identical PNGs out. The
committed PNGs are what the manifest serves; nothing at build or test time
imports the script. The 512 tile uses the smaller maskable mark because
Android launchers crop maskable icons to a circle/rounded square - the mark
must stay inside the central 80% safe zone, and `tests/pwa-manifest.mjs`
checks that.

Delivery: `backend/static/` carries byte-identical copies under the leaf names
above, `jarvis-backend/` carries them beside the server (the `BESIDE` /
`BESIDE_BINARY` tables in `tools/gen_base_from_backend.py`), and
`backend/test_hud_static.py` fails if any copy drifts from these files or if
the whitelist and the manifest's icon set disagree.
