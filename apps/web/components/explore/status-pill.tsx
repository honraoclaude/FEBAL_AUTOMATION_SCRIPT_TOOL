/**
 * Connection / run-state status pill (04-UI-SPEC §1 + Color table) — plain composition.
 *
 * role="status" aria-live="polite" so state changes ("Live" -> "Reconnecting…" -> "Complete")
 * are announced (a11y contract). Colors REUSE the existing --status-* tokens (no new palette):
 * Live = green with a subtle pulse; Reconnecting/Budget = amber; Complete = green; Failed = red;
 * Stopped = neutral; Connecting = muted (no pulse). The pulse respects prefers-reduced-motion
 * (Tailwind motion-reduce:animate-none drops it to a steady dot).
 */

export type PillState =
  | "connecting"
  | "live"
  | "reconnecting"
  | "complete"
  | "failed"
  | "budget"
  | "stopped";

const LABELS: Record<PillState, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  complete: "Complete",
  failed: "Failed",
  budget: "Budget reached",
  stopped: "Stopped",
};

/** Dot color token per state (Budget = amber: a designed stop, not red). */
const DOT: Record<PillState, string> = {
  connecting: "var(--status-neutral)",
  live: "var(--status-pass)",
  reconnecting: "var(--status-quarantine)",
  complete: "var(--status-pass)",
  failed: "var(--status-fail)",
  budget: "var(--status-quarantine)",
  stopped: "var(--status-neutral)",
};

export function StatusPill({ state }: { state: PillState }) {
  return (
    <span
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-sm font-semibold"
    >
      <span className="relative inline-flex size-1.5">
        {state === "live" ? (
          <span
            aria-hidden
            className="absolute inline-flex size-full animate-ping rounded-full opacity-75 motion-reduce:animate-none"
            style={{ backgroundColor: DOT[state] }}
          />
        ) : null}
        <span
          aria-hidden
          className="relative inline-flex size-1.5 rounded-full"
          style={{ backgroundColor: DOT[state] }}
        />
      </span>
      {LABELS[state]}
    </span>
  );
}
