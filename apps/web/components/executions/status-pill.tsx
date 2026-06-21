/**
 * Execution run/connection status pill (07-UI-SPEC §Color run-status mapping) — plain composition.
 *
 * Mirrors components/explore/status-pill.tsx, retargeted to the EXECUTION run lifecycle. It is a
 * role="status" aria-live="polite" region so state changes ("Running" -> "Stopping…" -> "Complete")
 * are announced (a11y). Colors REUSE the existing --status-* tokens (no new palette). The single
 * most important addition is `stopping` -> --status-quarantine AMBER: the HONEST draining state
 * (D-07), never a fake-instant kill. Running pulses (motion-reduce drops it to a steady dot).
 */

export type PillState =
  | "connecting"
  | "queued"
  | "running"
  | "stopping"
  | "reconnecting"
  | "complete"
  | "stopped";

const LABELS: Record<PillState, string> = {
  connecting: "Connecting…",
  queued: "Queued",
  running: "Running",
  stopping: "Stopping…",
  reconnecting: "Reconnecting…",
  complete: "Complete",
  stopped: "Stopped",
};

/** Dot color token per state. stopping = amber (the honest drain); stopped/queued = neutral. */
const DOT: Record<PillState, string> = {
  connecting: "var(--status-neutral)",
  queued: "var(--status-neutral)",
  running: "var(--status-pass)",
  stopping: "var(--status-quarantine)",
  reconnecting: "var(--status-quarantine)",
  complete: "var(--status-pass)",
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
        {state === "running" ? (
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
