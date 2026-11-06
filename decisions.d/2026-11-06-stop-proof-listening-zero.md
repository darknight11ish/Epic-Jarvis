- **2026-11-06 — STOP is proved by all three together: zero `LISTENING` on both addresses, zero `ESTABLISHED` on `:4719`, and HTTP refused:** The owner
  accepted the refined Q7 stop proof in a clickable decision card on 2026-11-06
  at 11:33 PT, "Accept the refined stop proof", and the Principal Architect
  ratified it formally at 11:35 PT (Q3). The canonical proof, in exactly this
  wording, is the three conditions TOGETHER: (1) `LISTENING` count **0 on both**
  `127.0.0.1:4719` **and** the tailnet `:4719` address; (2) `ESTABLISHED` count
  **0 with local port `:4719`** - `TIME_WAIT` rows are explicitly allowed; (3)
  the HTTP probe gets **no status at all** (`Invoke-WebRequest
  http://127.0.0.1:4719/api/status` failing to connect, i.e. connection
  refused). All three are the gate, and a missing one of them is a skipped half,
  never a pass. The refinement is needed because Q7's literal "zero lines"
  cannot pass on this PC: when the stack is stopped, `netstat -ano | findstr
  :4719` still returns 244-264 `:4719` rows - nearly all `TIME_WAIT` with PID 0,
  kernel-held sockets the server already closed - while `LISTENING=0`. It is not
  a loosening for real listeners: ANY line that says `LISTENING`, `ESTABLISHED`
  or `SYN_SENT`, or that carries a non-zero PID, still stops the deploy, and a
  skipped half, an empty block or a count that prints nothing is never a pass.
  This replaces the earlier state, where the 2026-11-06 wave-six result still
  recorded the owner's written confirmation as outstanding.
