# Design drafts not yet built

Kept here so they are not lost: they used to live only in a temporary
folder (`/tmp/claude-0/research/out/`, named in
`docs/EXTRACTION-RESEARCH-2026-09-23.md`), which a container reset wipes.

- `mcp-bridge-draft-2026-09-23/` - the MCP bridge (queued). Before building
  it, read `docs/CUTTING-EDGE-2026-09-26-engine.md`: the 2026-07-28 MCP spec
  removed the start-up handshake this draft uses (`jarvis_mcp.py` ~115), and
  a "more tools on request" list should come first.
- `skills-draft-2026-09-23/` - script skills as tools (queued).

These are drafts, not shipped code: nothing here is copied to the PC, and
`backend/run_suites.py` does not run their tests.
