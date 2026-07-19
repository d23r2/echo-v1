"""One-off LIVE verification script (not a pytest test — deliberately named
with a leading underscore so pytest's default discovery skips it). Run
manually, once, as evidence for docs/supervised_maintenance/test_report.md:
drives a real analysis-originated proposal through governance.run_sandbox()
WITHOUT mocking sandbox.run_patch_in_sandbox() — i.e. a genuine Docker
container executes the patch's checks. This has never been done in this
codebase's test history: even Part 2D's own dedicated sandbox test suite
(test_layer3a_selfmod_sandbox.py) only mocks subprocess.run() for its
Docker-related assertions.

Safety: run_patch_in_sandbox() creates an isolated git *worktree* off the
real repo's current HEAD in a separate directory — it never touches the
primary working tree. Deleted automatically by the sandbox's own teardown
before this script exits. Prints a before/after HEAD and working-tree
diff to prove that.

Usage: .venv\\Scripts\\python.exe tests\\_live_docker_sandbox_check.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="echo_live_sandbox_check_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DATA_DIR, 'session.db').as_posix()}"
os.environ["CHROMA_DIR"] = str(Path(_TEST_DATA_DIR, "chroma"))
os.environ["ATTACHMENTS_DIR"] = str(Path(_TEST_DATA_DIR, "attachments"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401
from app.config import Settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.services import (  # noqa: E402
    maintenance_analysis,
    maintenance_policy,
    maintenance_proposal,
    permission_center,
)
from app.services import self_modification_governance as governance  # noqa: E402
from app.services import self_modification_sandbox as sandbox  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
db = sessionmaker(bind=engine)()


def _settings(**overrides):
    base = dict(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
        supervised_proposals_enabled=True, supervised_sandbox_enabled=True,
        supervised_local_commit_enabled=False, supervised_maintenance_frontend_enabled=False,
        supervised_maintenance_max_read_bytes=512_000, supervised_self_modification_enabled=True,
        self_modification_sandbox_enabled=True, self_modification_deployment_enabled=False,
        self_modification_frontend_enabled=False, self_modification_approval_expiry_hours=24,
        self_modification_sandbox_image="echo-selfmod-sandbox:local",
    )
    base.update(overrides)
    return Settings(**base)


def main():
    for module in (maintenance_analysis, maintenance_policy, maintenance_proposal, governance):
        module.get_settings = _settings

    # run_patch_in_sandbox() checks out a fresh git *worktree* from the
    # committed HEAD, not the live working directory — so the patch must
    # be a NEW-FILE creation diff (nothing to modify exists in that
    # worktree's history), and nothing needs to be pre-written to the real
    # repo on disk at all.
    fixture_rel = "backend/tests/_live_sandbox_fixture.py"

    pre_head = sandbox.current_head()
    pre_status = subprocess.run(["git", "status", "--short"], cwd=Path(__file__).resolve().parent.parent.parent,
                                 capture_output=True, text=True).stdout

    permission_center.ensure_defaults(db)
    repo = maintenance_policy.register_repository(db, display_name="Live Sandbox Check", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db, repo.id, "sandbox_verify", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db, repository_id=repo.id, objective="Live Docker sandbox check.")
    maintenance_analysis.add_finding(
        db, analysis.id, epistemic_status="verified",
        description="No fixture file exists yet for a live end-to-end Docker sandbox check.",
        affected_files=[fixture_rel], evidence_reference="docs/supervised_maintenance/test_run_plan.md",
    )
    maintenance_analysis.complete_analysis(db, analysis.id)

    rationale = (
        "Problem: no fixture exists for a live sandbox check.\nEvidence: file absent from the tree.\n"
        "Assumptions: none.\nProposed change: add a trivial new test fixture file.\nRisk: low.\n"
        "Rollback: revert commit.\nTest plan: sandbox pytest/ruff run."
    )
    patch = (
        f"diff --git a/{fixture_rel} b/{fixture_rel}\n"
        f"new file mode 100644\n"
        f"index 0000000..1111111\n"
        f"--- /dev/null\n"
        f"+++ b/{fixture_rel}\n"
        f"@@ -0,0 +1,2 @@\n"
        f'+"""Fixture file created by the live Docker sandbox check."""\n'
        f"+value = 1\n"
    )
    proposal = maintenance_proposal.create_proposal_from_analysis(
        db, analysis_id=analysis.id, title="Live sandbox check", description="d", rationale=rationale,
        patch_text=patch,
    )
    print(f"Proposal created: {proposal.id}, analysis_id={proposal.analysis_id}")

    revision = governance._require_active_revision(db, proposal)
    governance.run_scope_check(db, revision.id)
    db.refresh(revision)
    print(f"scope_check_status = {revision.scope_check_status}")

    governance.run_compliance_check(db, revision.id)
    db.refresh(revision)
    print(f"compliance_check_status = {revision.compliance_check_status}")

    governance.mark_ready_for_sandbox(db, proposal.id)
    db.refresh(proposal)
    print(f"proposal.status = {proposal.status}, risk_level = {proposal.risk_level}")

    print("Invoking REAL Docker sandbox (no mocking)...")
    execution = governance.run_sandbox(db, proposal.id, confirmed=True)
    print(f"sandbox execution status = {execution.status}")
    print(f"sandbox_type = {execution.sandbox_type}, runner_image = {execution.runner_image}")
    print(f"network_disabled = {execution.network_disabled}")
    print(f"summary = {execution.summary}")

    from app.models import VerificationRun

    verification = (
        db.query(VerificationRun)
        .filter(VerificationRun.sandbox_execution_id == execution.id)
        .order_by(VerificationRun.created_at.desc())
        .first()
    )
    if verification is not None:
        print(f"verification status = {verification.status}")
        for check in verification.checks_json:
            print(f"  check: {check}")

    post_head = sandbox.current_head()
    post_status = subprocess.run(["git", "status", "--short"], cwd=Path(__file__).resolve().parent.parent.parent,
                                  capture_output=True, text=True).stdout
    print(f"\npre_head  = {pre_head}")
    print(f"post_head = {post_head}")
    print(f"HEAD unchanged: {pre_head == post_head}")
    print(f"pre working-tree status:  {pre_status!r}")
    print(f"post working-tree status: {post_status!r}")
    print(f"Working tree unchanged: {pre_status == post_status}")


if __name__ == "__main__":
    main()
