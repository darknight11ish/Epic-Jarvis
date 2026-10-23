# PWA icons (192 / 512 / maskable 512)

These three PNGs are the home-screen tile for the browser HUD (`../manifest.webmanifest`).
They are drawn from the HUD's own monochrome emblem - the `◈` mark the Studio
rail shows, in the HUD's ice accent on the deep-space well - and contain no
third-party artwork, so there is no licence to carry for them.

| file | size | purpose |
|---|---|---|
| `pwa-192.png` | 192x192 | `any` |
| `pwa-512.png` | 512x512 | `any` |
| `pwa-maskable-512.png` | 512x512 | `maskable` (mark kept inside Android's safe circle) |

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
imports the script. The maskable tile uses a smaller mark because Android
launchers crop maskable icons to a circle/rounded square - the mark must stay
inside the central 80% safe zone, and `tests/pwa-manifest.mjs` checks that.

The static-serving slice must serve these files (and `manifest.webmanifest`)
beside `jarvis_hud.py` with the right content types: `image/png` for the
icons, `application/manifest+json` for the manifest.
