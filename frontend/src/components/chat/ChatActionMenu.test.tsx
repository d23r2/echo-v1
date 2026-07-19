import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatActionMenu from "./ChatActionMenu";

// Mobile audio diagnosis fix: voiceUnavailableReason replaced a plain
// voiceSupported boolean so the mic control explains *why* it's
// unavailable (unsupported browser / insecure context / turned off)
// instead of just vanishing with no feedback — see
// docs/audio/mobile_audio_test_plan.md.

function baseProps(overrides: Partial<Parameters<typeof ChatActionMenu>[0]> = {}) {
  return {
    onAttachFile: vi.fn(),
    onToggleVoice: vi.fn(),
    onGenerateImage: vi.fn(),
    voiceUnavailableReason: null,
    listening: false,
    canGenerateImage: true,
    imageGenerationUnavailableReason: null,
    ...overrides,
  };
}

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
}

describe("ChatActionMenu voice control", () => {
  it("is enabled with a plain label when voice is available", () => {
    render(<ChatActionMenu {...baseProps()} />);
    openMenu();
    const item = screen.getByRole("menuitem", { name: /voice input/i });
    expect(item).not.toBeDisabled();
    expect(item).toHaveTextContent("🎤 Voice input");
  });

  it("shows a specific reason instead of vanishing when unsupported", () => {
    render(<ChatActionMenu {...baseProps({ voiceUnavailableReason: "not supported in this browser" })} />);
    openMenu();
    const item = screen.getByRole("menuitem", { name: /voice input/i });
    expect(item).toBeDisabled();
    expect(item).toHaveTextContent("not supported in this browser");
    expect(item).toHaveAttribute("title", "not supported in this browser");
  });

  it("shows the insecure-context reason distinctly from unsupported", () => {
    render(
      <ChatActionMenu
        {...baseProps({ voiceUnavailableReason: "requires a secure connection (HTTPS) on mobile" })}
      />
    );
    openMenu();
    const item = screen.getByRole("menuitem", { name: /voice input/i });
    expect(item).toBeDisabled();
    expect(item).toHaveTextContent("requires a secure connection (HTTPS) on mobile");
  });

  it("does not call onToggleVoice when disabled and clicked", () => {
    const onToggleVoice = vi.fn();
    render(<ChatActionMenu {...baseProps({ voiceUnavailableReason: "turned off in Settings", onToggleVoice })} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: /voice input/i }));
    expect(onToggleVoice).not.toHaveBeenCalled();
  });

  it("calls onToggleVoice when available and clicked", () => {
    const onToggleVoice = vi.fn();
    render(<ChatActionMenu {...baseProps({ onToggleVoice })} />);
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: /voice input/i }));
    expect(onToggleVoice).toHaveBeenCalledTimes(1);
  });

  it("shows 'Stop voice input' while listening and available", () => {
    render(<ChatActionMenu {...baseProps({ listening: true })} />);
    openMenu();
    expect(screen.getByRole("menuitem", { name: /stop voice input/i })).toBeInTheDocument();
  });
});
