- **2026-11-06 — STOP is proved by `LISTENING=0`, not "zero lines":** The owner
  accepted the refined Q7 stop proof in a clickable decision card on 2026-11-06
  at 11:33 PT, "Accept the refined stop proof". The proof, in exactly this
  wording: STOP is proved by `LISTENING=0` on `127.0.0.1:4719` and on the
  tailnet `:4719` address **and** the HTTP probe getting no status at all; a
  long `TIME_WAIT` list is explicitly **not** a failure. The refinement is
  needed because Q7's literal "zero lines" cannot pass on this PC: when the
  stack is stopped, `netstat -ano | findstr :4719` still returns 244-264
  `:4719` rows - nearly all `TIME_WAIT` with PID 0, kernel-held sockets the
  server already closed - while `LISTENING=0`. It is not a loosening for real
  listeners: ANY line that says `LISTENING`, `ESTABLISHED` or `SYN_SENT`, or
  that carries a non-zero PID, still stops the deploy, and a skipped half, an
  empty block or a count that prints nothing is never a pass. This replaces the
  earlier state, where the 2026-11-06 wave-six result still recorded the owner's
  written confirmation as outstanding.
