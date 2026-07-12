export type PresenceState = "idle" | "thinking" | "listening" | "speaking";

const STATE_LABEL: Record<PresenceState, string> = {
  idle: "Echo",
  thinking: "Echo is thinking…",
  listening: "Echo is listening…",
  speaking: "Echo is speaking…",
};

/**
 * Echo's visual presence — an abstract glowing orb, not a mascot/avatar.
 * Pure CSS (radial-gradient glow + keyframe transforms), so it costs nothing
 * on mobile and respects prefers-reduced-motion via the `motion-safe:`
 * variant on every animation class (Tailwind strips the animation entirely
 * under reduced-motion; the orb still renders, just static).
 */
export default function EchoPresence({
  state,
  size = "md",
  showLabel = false,
}: {
  state: PresenceState;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}) {
  const dims = size === "lg" ? "h-16 w-16" : size === "sm" ? "h-8 w-8" : "h-10 w-10";
  const glowDims = size === "lg" ? "h-28 w-28" : size === "sm" ? "h-14 w-14" : "h-18 w-18";

  const coreAnimation =
    state === "thinking"
      ? "motion-safe:animate-orb-think"
      : state === "listening"
        ? "motion-safe:animate-orb-listen"
        : state === "speaking"
          ? "motion-safe:animate-orb-speak"
          : "motion-safe:animate-orb-breathe";

  return (
    <div className="flex items-center gap-2.5">
      <div className={`relative flex ${dims} shrink-0 items-center justify-center`}>
        {/* Outer soft glow field */}
        <div
          className={`absolute ${glowDims} rounded-full blur-xl transition-colors duration-700`}
          style={{
            background:
              state === "listening"
                ? "radial-gradient(circle, rgba(124,158,255,0.55) 0%, rgba(124,158,255,0) 70%)"
                : state === "speaking"
                  ? "radial-gradient(circle, rgba(168,192,255,0.5) 0%, rgba(124,158,255,0) 70%)"
                  : state === "thinking"
                    ? "radial-gradient(circle, rgba(124,158,255,0.45) 0%, rgba(124,158,255,0) 70%)"
                    : "radial-gradient(circle, rgba(124,158,255,0.3) 0%, rgba(124,158,255,0) 70%)",
          }}
        />
        {/* Listening: expanding ripple ring */}
        {state === "listening" && (
          <span className="motion-safe:animate-ring-ripple absolute inset-0 rounded-full border border-accent/70" />
        )}
        {/* Core orb */}
        <div
          className={`relative ${dims} rounded-full ${coreAnimation}`}
          style={{
            background:
              "radial-gradient(circle at 35% 30%, #c7d5ff 0%, #7c9eff 45%, #4b5fa8 100%)",
            boxShadow: "0 0 18px rgba(124,158,255,0.55), inset 0 0 10px rgba(255,255,255,0.25)",
          }}
        />
        {/* Speaking: three small bars overlaid, independent stagger for a waveform feel */}
        {state === "speaking" && (
          <div className="absolute flex items-center gap-[3px]">
            <span className="motion-safe:animate-orb-speak h-3 w-[3px] rounded-full bg-zinc-950/70 [animation-delay:-0.3s]" />
            <span className="motion-safe:animate-orb-speak h-3 w-[3px] rounded-full bg-zinc-950/70" />
            <span className="motion-safe:animate-orb-speak h-3 w-[3px] rounded-full bg-zinc-950/70 [animation-delay:-0.15s]" />
          </div>
        )}
      </div>
      {showLabel && (
        <span className="text-sm font-medium text-zinc-300">{STATE_LABEL[state]}</span>
      )}
    </div>
  );
}
