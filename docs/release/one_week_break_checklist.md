# ECHO — One-Week Break Checklist

Read `docs/release/ECHO_stabilisation_release_report.md` for the full picture. This is the short,
practical version.

## 1. Final branch

`master`

## 2. Final pushed commit

See the confirmation at the end of this session's work — the exact hash is recorded in the release
report's "Remote Push Status" section once the push completes. `git log -1 origin/master` will always
show the true current state regardless of what's written here.

## 3. Backend start command

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in whichever API keys you have; none are required to run
uvicorn app.main:app --reload
```
API docs at http://localhost:8000/docs

Or via Docker: `cp backend/.env.example backend/.env && docker compose up --build`.

## 4. Frontend start command

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
App at **http://localhost:5174** (not 5173 — `README.md`'s wrong port number was fixed this pass).

## 5. Mobile access URL requirements

- The frontend must be reached over **HTTPS** (or `localhost`) for the browser to allow microphone
  access via `SpeechRecognition` — plain HTTP on a LAN/Tailscale IP will not offer voice input on a real
  phone browser. The mic control now says so explicitly instead of just not appearing.
- The packaged Capacitor (Android) and Tauri (Windows) apps have their own WebView origin exemptions and
  are not subject to this the same way — see `capacitor.config.ts`'s `androidScheme: 'http'` and
  `PROGRESS.md`'s 2026-07-12 entry for why that's already handled for those specific packaging paths.
- Voice output (`speechSynthesis`) does not have the same HTTPS requirement, but mobile browsers may
  still block automatic playback outside a user-gesture context — this is what the new "Tap to play"
  banner (Pass 2) handles.

## 6. Known issues

- **Mobile voice input/output has not been verified on a real phone.** Fixes are in place and tested in
  emulation only. See item 12 below.
- Two obsolete, unused frontend files (`ReasoningTrace.tsx`, `AtlasNotes.tsx`) remain in the tree —
  harmless, safe to delete whenever convenient.
- No audit hash-chaining exists anywhere in the codebase — a disclosed, long-standing limitation, not
  something newly introduced.

## 7. Disabled capabilities

All of the following are `false` by default in `backend/app/config.py` and require explicit `.env`
changes to enable, one at a time, in dependency order — do not enable more than one at once without
reading `docs/supervised_maintenance/policy.md` first:

- `SUPERVISED_SELF_MODIFICATION_ENABLED`
- `SELF_MODIFICATION_SANDBOX_ENABLED`
- `SELF_MODIFICATION_DEPLOYMENT_ENABLED`
- `SELF_MODIFICATION_FRONTEND_ENABLED`
- `PUBLIC_PUSH_ENABLED`
- `CODE_EXECUTION_ENABLED`
- `FILE_WRITE_ENABLED`
- `DESTRUCTIVE_ACTIONS_ENABLED`

None of these were touched this session. Push, merge, and deployment are not implemented capabilities
at all (not merely disabled) — there is no code path for ECHO to perform any of them regardless of flag
state.

## 8. Rollback instructions

```bash
git log --oneline -10             # find the commit to undo
git revert <commit-hash>          # safe, creates a new commit — never reset --hard on shared history
```

No destructive git operation is ever needed for anything done this session. No database migration
requires rollback (none was applied).

## 9. Where logs are located

- Backend: stdout/stderr of the `uvicorn` process, or `docker compose logs backend` under Docker.
  `REQUEST_LOGGING_ENABLED=true` and `DIAGNOSTICS_ENABLED=true` by default (see `.env.example`).
- Frontend: browser DevTools console; the app's own `logger.ts` also gates verbosity.
- Supervised Maintenance audit trail: `GET /api/governance/supervised-maintenance/audit` once the
  feature is enabled (it's disabled by default, so there's nothing to review unless you turned it on).

## 10. How to activate the kill switch

Supervised Maintenance's kill switch (only relevant once the feature is enabled — it's off by default):
`POST /api/governance/self-modification/kill-switch/activate` with an authenticated owner request and a
reason string. It immediately blocks new proposal creation, sandbox runs, and approvals; it does not
delete audit history or conceal active sandboxes. Reset via the matching `/deactivate` endpoint, also
owner-only.

## 11. What not to enable while the owner is away

- Do not enable any Supervised Maintenance flag beyond `Analyse Only` without being present to review
  proposals — nothing in this system can act without a human approval step, but leaving Sandbox/Local
  Commit enabled unattended is still not the intended operating mode for a single-user app with no
  second human to catch a mistaken approval.
- Do not enable `PUBLIC_PUSH_ENABLED`, `CODE_EXECUTION_ENABLED`, `FILE_WRITE_ENABLED`, or
  `DESTRUCTIVE_ACTIONS_ENABLED`.
- Do not merge or push from any of the other local branches with active worktrees
  (`agents/code-diagnosis-testing`, `agents/generous-lark`, `codex/layer3a-governance-foundation`,
  `claude/reverent-northcutt-d172e4`) without reviewing what's actually in them first — they belong to
  other agent sessions per this repo's dual-agent workflow.

## 12. Recommended next development after the break

Real-device mobile voice testing (see the release report's "Recommended First Task After Break" for
detail) — this is the one thing this session could not do itself and is the most valuable next step
before treating mobile voice as fully done.
