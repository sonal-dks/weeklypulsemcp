# Scheduler Sub-phase (Phase 6.1)

This folder isolates weekly orchestration assets from phase code.

## Files

- `scheduler/scripts/install_deps.sh`  
  Installs Python dependencies across Phase 1 to Phase 6.
- `scheduler/scripts/run_weekly_pipeline.sh`  
  Executes Phase 1 → 2 → 3 → 4 → 4.5 → 5 → 6 in order.

## Runtime

- Triggering: GitHub Actions schedule + manual dispatch.
- Runner: self-hosted.
- Required runner prerequisites:
  - Python 3.11+
  - Node.js / `npx` for MCP stdio tools in Phase 5
  - Persisted OAuth tokens:
    - `~/.config/google-docs-mcp/`
    - `~/.gmail-mcp/`

## Secrets

Set in repository GitHub Actions secrets:

- `GROQ_API_KEY` (Phase 2, 3)
- `GEMINI_API_KEY` (Phase 4)
