# Early vision drafts (superseded)

These four files were an early planning pass, written before this repo's actual implementation was reviewed. They no longer reflect the real state of the project — the code below is the source of truth:

- Constitution → `backend/app/constitution.py` (ranked core values, immutable Value Invariants, edge-case protocols)
- Atlas memory → `backend/app/atlas.py` (SQLite + ChromaDB semantic search, epistemic status + confidence)
- Guardian Council → `backend/app/council.py` (proposal guard + 2-of-3 Guardian vote + Verifier)
- Persona/behavior directives → `backend/app/persona.py`

Kept here only as a historical record of the original planning pass. See `PROGRESS.md` at the repo root and `CLAUDE.md` for the current state.
