"use client";

/**
 * Confidence meter (09-UI-SPEC §Color "Confidence (0-100) → band color" + §Accessibility).
 *
 * A token-styled NATIVE meter — a bg-secondary track + a fill colored GREEN at/above the
 * calibrated threshold (autonomous-filing-eligible) else AMBER below it (classified but below the
 * floor → stays human-reviewed). The band edge is the SERVER `confidence_threshold` passed in,
 * NEVER a client literal (the heal-band/threshold precedent). Below-threshold is amber (caution:
 * machine is less sure), not red (red is reserved for the Product-defect CLASS — a different axis).
 *
 * NO recharts, NO new dep — a styled-native `role="progressbar"` over --status-* tokens (the
 * Phase-7 styled-native progress precedent). The mono numeral is ALWAYS present as text (the
 * source of truth; the color is supplementary). The accessible name combines the value and
 * whether it clears the threshold (WCAG — never a decorative-only bar).
 */

interface ConfidenceMeterProps {
  confidence: number;
  /** The calibrated band edge — sourced from the server `confidence_threshold`, never a literal. */
  threshold: number;
}

export function ConfidenceMeter({ confidence, threshold }: ConfidenceMeterProps) {
  const clamped = Math.max(0, Math.min(100, confidence));
  const clears = clamped >= threshold;
  const token = clears ? "var(--status-pass)" : "var(--status-quarantine)";
  const label = `Confidence ${clamped} of 100, ${
    clears ? "at or above" : "below"
  } the filing threshold ${threshold}`;

  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 w-24 overflow-hidden rounded-full bg-secondary"
      >
        <div
          className="h-full rounded-full motion-reduce:transition-none"
          style={{ width: `${clamped}%`, backgroundColor: token }}
        />
      </div>
      <span className="font-mono text-sm font-semibold" style={{ color: token }}>
        {clamped}
      </span>
    </div>
  );
}
