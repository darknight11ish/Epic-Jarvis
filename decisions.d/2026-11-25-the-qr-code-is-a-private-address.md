- **2026-11-25 — The QR code is a private address, not a credential:**
  The owner asked (2026-11-13) to open Atlas's web page on his phone without
  typing its private-network address into the browser. The code therefore
  encodes `http://<bind>:<port>/` and nothing else — no token, no key, no query
  string, and never a public tunnel. That is the only honest shape: the address
  is already printed under the picture, so the code cannot carry anything the
  page does not show, and a scan only opens the page. It does not sign the
  browser in, and the feature must not grow a route that mints one: a browser's
  pairing key is made on this PC at a terminal (`jarvis_devices.py
  --add-device`) and exchanged for the `jarvis_token` cookie by `POST
  /api/devices/web-session` (JARVIS-API section 90), and a remote way to create
  credentials is exactly what the `pair_device` card gates. The picture is drawn
  in Rust with `qrcodegen`, the same path as phone pairing; the page gets the
  finished SVG and the address; a blank, wildcard, loopback or home-network
  address draws nothing and shows the card's plain "nothing for the phone to
  reach" sentence. The control is the desktop's alone — the other half is
  Atlas's own web page in a phone's browser, not the Android app — so no parity
  route is involved.
