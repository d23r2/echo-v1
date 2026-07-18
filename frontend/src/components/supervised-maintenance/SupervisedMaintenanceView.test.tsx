import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CapabilityMode, MaintenancePolicy } from "../../api/client";
import { RoleProvider } from "../../state/roleContext";
import SupervisedMaintenanceView from "./SupervisedMaintenanceView";

const baseHealth = {
  supervised_maintenance_enabled: false,
  supervised_analysis_enabled: false,
  supervised_proposals_enabled: false,
  supervised_sandbox_enabled: false,
  supervised_local_commit_enabled: false,
  supervised_maintenance_frontend_enabled: false,
  registered_repository_count: 0,
  open_analysis_count: 0,
};

const basePolicy: MaintenancePolicy = {
  protected_paths: ["backend/app/constitution.py"],
  protected_path_prefixes: [".env"],
  protected_symbols: ["Value Invariants"],
  allowed_path_prefixes: ["backend/tests/"],
  secret_filename_patterns: ["^\\.env(\\..+)?$"],
  capability_modes: ["disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"] as CapabilityMode[],
};

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    getMaintenanceStatus: vi.fn(),
    getMaintenancePolicy: vi.fn(),
    listMaintenanceRepositories: vi.fn(),
    listMaintenanceAnalyses: vi.fn(),
    listMaintenanceAudit: vi.fn(),
  };
});

import * as client from "../../api/client";

function renderView() {
  return render(
    <RoleProvider>
      <SupervisedMaintenanceView />
    </RoleProvider>
  );
}

describe("SupervisedMaintenanceView", () => {
  it("shows the disabled-frontend banner and locks workflow controls when the flag is off", async () => {
    vi.mocked(client.getMaintenanceStatus).mockResolvedValue(baseHealth);
    vi.mocked(client.getMaintenancePolicy).mockResolvedValue(basePolicy);
    vi.mocked(client.listMaintenanceRepositories).mockResolvedValue([]);

    renderView();

    await waitFor(() => {
      expect(screen.getByText(/maintenance frontend is disabled by configuration/i)).toBeInTheDocument();
    });

    const registerButton = screen.getByRole("button", { name: /register repository/i });
    expect(registerButton).toBeDisabled();
  });

  it("shows the repository registration form when no repository is registered yet", async () => {
    vi.mocked(client.getMaintenanceStatus).mockResolvedValue({ ...baseHealth, supervised_maintenance_frontend_enabled: true });
    vi.mocked(client.getMaintenancePolicy).mockResolvedValue(basePolicy);
    vi.mocked(client.listMaintenanceRepositories).mockResolvedValue([]);

    renderView();

    await waitFor(() => {
      expect(screen.getByText(/registers this backend's own codebase/i)).toBeInTheDocument();
    });
  });

  it("surfaces a real error rather than a fake success state when the status call fails", async () => {
    vi.mocked(client.getMaintenanceStatus).mockRejectedValue(new Error("503 Service Unavailable"));
    vi.mocked(client.getMaintenancePolicy).mockResolvedValue(basePolicy);
    vi.mocked(client.listMaintenanceRepositories).mockResolvedValue([]);

    renderView();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("503 Service Unavailable");
    });
  });

  it("lists registered repositories and their capability mode", async () => {
    vi.mocked(client.getMaintenanceStatus).mockResolvedValue({ ...baseHealth, supervised_maintenance_frontend_enabled: true, registered_repository_count: 1 });
    vi.mocked(client.getMaintenancePolicy).mockResolvedValue(basePolicy);
    vi.mocked(client.listMaintenanceRepositories).mockResolvedValue([
      {
        id: "repo-1",
        display_name: "ECHO",
        root_path_reference: "C:/repo",
        fingerprint: "abc",
        approved_branches: ["master"],
        permitted_read_paths: ["backend/tests/"],
        permitted_proposal_paths: ["backend/tests/"],
        blocked_file_patterns: [".env*"],
        capability_mode: "analyse_only",
        owner: "founder",
        enabled: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_verified_at: null,
      },
    ]);
    vi.mocked(client.listMaintenanceAnalyses).mockResolvedValue([]);
    vi.mocked(client.listMaintenanceAudit).mockResolvedValue([]);

    renderView();

    await waitFor(() => {
      expect(screen.getByText("ECHO")).toBeInTheDocument();
      expect(screen.getAllByText("analyse_only").length).toBeGreaterThan(0);
    });
  });
});
