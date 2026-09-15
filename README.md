# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced .

A local-first personal assistant. A Python backend on a Windows 11 desktop, a
Tauri 2 shell around it, an 8B model in Ollama on the same machine, and an
Android companion reachable over Tailscale. Nothing private leaves the
machine, there is no public tunnel, there are no API keys in the app, and
there is no approve-all control anywhere. Non-commercial.

## Where to start

| document | what it is |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **The source of truth.** How the pieces fit, the invariants, and the one permission model everything must use. Read this before adding anything; where another document disagrees, this one wins. |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Getting it running, including the parts that are rough. |
| [`docs/PEERS.md`](docs/PEERS.md) | What twenty comparable projects did about memory, approval gates, voice and packaging — read from their source. What to copy, what to refuse, where Jarvis is behind. |
| [`docs/MODEL-TOPOLOGY.md`](docs/MODEL-TOPOLOGY.md) | Which model, at what context length, and why — including what does not fit. |
| [`backend/README.md`](backend/README.md) | The thirteen backend patches, what each fixes, and how to apply them. |
| [`docs/AUDIT.md`](docs/AUDIT.md) | Findings from the audits, and which are fixed. |

## Layout

- `backend/` — patches against the OpenJarvis backend, one executable test
  each, plus `jarvis_research.py`. The backend itself lives outside this repo;
  `docs/ARCHITECTURE.md` §9 says where.
- `jarvis-desktop/` — the Tauri 2 shell: Rust commands in `src-tauri/`, the
  windows in `src/`.
- `docs/` — everything above.
- `scripts/` — build-time generators.

Licence: see [`LICENSE`](LICENSE) and
[`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt).
