- **Jarvis knows whether it is talking to the phone or the desktop program, and
  tailors its answers by default:** both clients now send one plain
  `X-Jarvis-Surface` header (`phone` from the Android app, `desktop` from the
  desktop program) beside the unchanged `X-Jarvis-Client: hud`. The PC reads it
  once per request in the shipped origin gate and uses it in the deterministic
  quick answers, in the feature/limits answers (each row's own `surface` and
  `where`), and in one system sentence for the model - so "open the second
  brain" from the phone names the phone's Brain, a PC-only feature asked from
  the phone says where the PC door is, and a phone-only feature asked from the
  desktop says it is on the phone only. No setting, no opt-in and no first-run
  step; a request with no header is `unknown` and behaves exactly as before. The
  header is not authentication and never logged. Docs/JARVIS-API.md section 173;
  `backend/test_surface.py`, `SurfaceHeaderTest.kt` and the Rust
  `surface_header_tests` prove it.
