# ECHO Repository Stabilisation Plan — Pass 1 of 3

Read-only audit performed before any implementation, per the stabilisation task's own Step 1/Step 2
ordering. This plan documents what was found; `repository_stabilisation_report.md` documents what was
done about it.

## 1. Repository state at audit time

- Branch: `master`, at `083ebc49` (`fix(chat): mobile voice input/output — ...`), pushed and in sync
  with `origin/master` (`git status -sb` showed no ahead/behind divergence).
- Working tree: clean. No staged or unstaged changes, no untracked files, no stashes.
- No in-progress merge, rebase, or cherry-pick state (`.git/MERGE_HEAD` / `rebase-apply` /
  `rebase-merge` all absent).
- No conflict markers in any tracked file (`git grep` for `<<<<<<<`/`=======`/`>>>>>>>` returned
  nothing).
- No tracked file over 5 MB.
- Several other local branches exist with their own worktrees checked out elsewhere
  (`agents/code-diagnosis-testing`, `agents/generous-lark`, `codex/layer3a-governance-foundation`,
  `claude/reverent-northcutt-d172e4`, `claude/ECHO-DEV-001-dual-agent`,
  `add/tests-ci-pwa-capacitor`) — per this repo's dual-agent workflow rules (`AGENTS.md`,
  `docs/development/DUAL_AGENT_WORKFLOW.md`), these belong to other agents/sessions and were not
  touched or inspected further; `master` is the only branch in scope for this pass.
- `tasks/ACTIVE_TASK.md`: "No task loaded" — the prior task (`ECHO-SUPMAINT-001`, Supervised
  Maintenance Workspace v1) is archived with a GREEN verdict.

## 2. Migration system

This repo does not use Alembic or any versioned-head migration tool. `backend/app/db.py`'s `init_db()`
runs `Base.metadata.create_all()` (idempotent — no-op on existing tables) followed by a long, explicit
sequence of idempotent `_ensure_column()` calls (add-column-if-missing) and seed functions, then
`_ensure_schema_version()` stamps `CURRENT_SCHEMA_VERSION = 12` into a singleton `SchemaVersion` row.
There is exactly one linear history in code, not multiple heads — "verify one valid head" from the
task's Step 4 doesn't apply to this migration style as literally stated; the equivalent guarantee is
that `init_db()` is called at every startup and is safe to run against both a brand-new empty database
and an already-migrated one. This was directly exercised: `init_db()` was run against the app's own
dev database as part of the backend startup check (Section 5 below) with no error, and is exercised
continuously by the ~1,700-test suite, which builds a fresh isolated SQLite database per test via
`conftest.py`.

## 3. Incomplete work found — classified

Full-repository grep for `TODO|FIXME|HACK|XXX` across `backend/app` and `frontend/src` (excluding
tests): **zero matches.** Grep for `NotImplementedError`: zero matches in application code. Grep for
placeholder/stub/temporary-bypass language: 18 matches, all in `backend/app`, all read and individually
classified:

| Finding | Classification | Notes |
|---|---|---|
| `tool_registry.py`: `_camera_capture_placeholder`, `_voice_input_placeholder` | **Intentional placeholder** | Both explicitly return `{"available": False, "reason": "..."}` — honest non-functionality, not a silent stub. `voice_input_placeholder`'s reason text correctly documents that voice runs entirely client-side in the browser. |
| `models.py`/`schemas.py`/`persona_service.py`: `hands_free_placeholder` voice mode literal | **Intentional placeholder** | A real, selectable `VoiceMode` enum value already wired into `persona_service.py`'s TTS-enablement check — the "placeholder" in the name flags that hands-free behavior isn't a distinct implementation yet (falls back to the same path as `tts_enabled`), not that the value itself is unhandled. |
| `image_router.py`: ComfyUI "reachability-check-only stub" | **Intentional placeholder** | Documented in the module docstring; `IMAGE_PROVIDER=comfyui` only checks the configured URL is reachable, doesn't generate — consistent with `.env.example`'s own comment on the same setting. |
| `plan_engine.py`: "a single honest placeholder step" | **Intentional placeholder** | Part of `plan_engine.py`'s documented fallback behavior when no skill-library template matches a task — an explicit, labeled fallback, not missing logic. |

**No critical blockers, no broken imports, no disconnected frontend/backend wiring, and no
API-schema mismatches were found.** This is a materially different starting state than the task's own
Step 1 template assumes is typical — it reflects that every major feature merged onto `master` in this
repo's history has gone through its own "final verification + docs + smoke test + report" cycle before
being considered done (see `PROGRESS.md`'s per-feature entries), including the two systems this pass
exists to protect (Supervised Maintenance Workspace v1: 8 phases, GREEN; mobile audio fixes: this
session, YELLOW pending real-device testing only).

## 4. Obsolete code found

`frontend/src/components/chat/ReasoningTrace.tsx` and `frontend/src/components/chat/AtlasNotes.tsx`
are **not imported or referenced anywhere** outside their own files (confirmed via repo-wide grep).
Reading `MessageBubble.tsx` explains why: a later, deliberate product decision (documented inline in a
code comment at `MessageBubble.tsx:212-220`) replaced the separate-component reasoning/Atlas-notes UI
with a decision to *not* render that internal detail in the normal chat view at all — "it's for ECHO's
own memory/tools/debugging, not the person using the chat." The two component files are leftover dead
code from before that decision, not a broken or incomplete integration. **Classification: obsolete
code.** Per the task's own instruction not to perform broad refactoring or automatically implement/undo
unrelated work, these were left in place and are only noted here — deleting them is optional, low-risk,
zero-behavior-change cleanup that the repository owner can do at their discretion, not a stabilisation
blocker.

## 5. Repository hygiene gaps found (real, previously flagged, never resolved)

1. **`.gitattributes` missing.** `PROGRESS.md`'s "Blockers"/"Gaps" sections flag this across four
   separate check-ins (2026-07-16, 17, 18, 19) as a source of CRLF/LF diff noise, never fixed. Local
   `core.autocrlf=true` already handles checkout/commit conversion correctly for this one contributor,
   which is why the working tree is currently clean — but the policy was never made explicit and
   repo-tracked, so it depends on every future contributor's local git config matching. **Fixed this
   pass**: added `.gitattributes` with `* text=auto` plus explicit `binary` markers for image/font/db/
   archive extensions. Deliberately did **not** run a `git add --renormalize .` pass over the existing
   tree — the tree is currently clean with no noisy diff to resolve, and renormalizing now would touch
   a large number of unrelated files for a purely cosmetic, zero-behavior-change gain, which the task's
   own "prefer the smallest reliable correction" / "do not perform broad refactoring" instructions argue
   against doing unprompted.
2. **`.github/workflows/ci.yml`'s header comment was stale and factually wrong.** It claimed the
   workflow "has NOT been pushed to GitHub" and warned against pushing it — but `git log` shows it has
   been on `origin/master` since `ec2ac484`, well before this session. The workflow's actual content
   (lint + pytest + typecheck + build + `docker compose config` validation + the repo's own secret
   scanner; no deploy job, no secrets required) was already reviewed and is safe. **Fixed this pass**:
   corrected the comment to state the true, current, safe status instead of a stale warning that no
   longer matches reality and could mislead a future session into treating an already-public,
   already-running CI workflow as still-secret.
3. **`Echo_Code_Review.zip`** sits in the repository root, correctly covered by the existing `*.zip`
   `.gitignore` rule (confirmed via `git check-ignore -v`) — it has never been tracked and poses no
   commit/push risk. `PROGRESS.md` flagged it as "stale" starting 2026-07-16 purely as local disk
   hygiene, not a repository-safety issue. **Left untouched** — it's a local file this task didn't
   create, its full contents weren't reviewed, and removing files outside the git-tracked tree isn't
   necessary for repository stability; noted here only for completeness.

## 6. Security/secret scan

`scripts/check_secrets.ps1` (the repo's own pre-existing scanner) was run and returned exit code 1 with
15 findings — **every single one is inside `backend/tests/*.py`**, and manual inspection of each
confirmed they are synthetic fixture values that exist specifically to test the app's own
secret-redaction/detection logic (e.g. `assert "sk-should-never-be-in-registry-output" not in
serialized`, `assert memory_privacy.is_secret("-----BEGIN RSA PRIVATE KEY-----...")`). **No real
credential was found.** `.env` is correctly gitignored and not tracked; `.env.example` (both
backend and frontend) contain placeholder/empty values only, confirmed by direct read.

## 7. Baseline test/build results referenced by this plan

See `repository_stabilisation_report.md` for exact commands and pass/fail counts from this pass's run.

## 8. Work order followed

Per the task's own Step 2 ordering — sections 1 (config/hygiene) and 3-5 (audit/classification) above
are this pass's actual work; sections 6-9 of the prescribed order (permission/feature-flag enforcement,
governance integrations, Supervised Maintenance wiring, mobile audio wiring) required no changes because
the audit found no incompleteness in any of them — both systems already carry their own GREEN/YELLOW
verification reports from earlier in this same day's work
(`ECHO_SUPERVISED_MAINTENANCE_WORKSPACE_V1_REPORT.md`, `docs/audio/mobile_audio_test_report.md`).

## 9. Work intentionally deferred (not this pass's job)

- Deleting the two obsolete frontend files (Section 4) — cosmetic, zero-risk, owner's call.
- Renormalizing existing file line endings under the new `.gitattributes` — no current noise to fix.
- `Echo_Code_Review.zip` local cleanup — outside git's tracked tree, not this task's concern.
- Any of the "Gaps / next up" items in `PROGRESS.md` that describe genuinely new feature work
  (ComfyUI real image generation, Groq/OpenRouter providers, Schedule background notifications,
  `npm audit fix`, ESLint setup) — these are legitimate future work, explicitly out of scope for a
  stabilisation pass per the task's own instruction not to start a new roadmap milestone.

## 10. Stop conditions

None were triggered. No real secret was found, no unresolved merge/rebase state existed, no critical
startup blocker was found, and no safety system required modification to pass a test.
