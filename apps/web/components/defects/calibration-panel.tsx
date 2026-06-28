"use client";

/**
 * Calibration panel (09-UI-SPEC §0 — the DEF-03 / QUAL-03 read-only display).
 *
 * Four read-only tiles atop the queue: Classification accuracy (vs the ≥85% gate), Draft precision
 * (vs the ≥90% gate), the calibrated Confidence threshold, and the Autonomous-filing flag state
 * (on/off + the gate caption). It surfaces — READ-ONLY — whether both gates are met and states
 * that filing stays draft-only until a human flips the flag in config (D-04). The autonomy flag is
 * DISPLAY-ONLY here: there is NO write toggle (the human flips it deliberately in config after
 * reviewing the numbers — a write control is a Phase-10 concern).
 *
 * Every number renders STRICTLY from the server (classification_accuracy / draft_precision /
 * confidence_threshold / autonomous_enabled) — never a client literal. Honest nulls render the
 * "not measured yet" copy. WCAG 1.4.1: the met/unmet indicator carries its WORD ("Met"/"Not met
 * yet"/"—"), not color alone; the dot is aria-hidden; the flag indicator is role="status" text.
 */

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type Calibration } from "@/lib/api/defects";

const ACCURACY_TARGET = 85;
const PRECISION_TARGET = 90;

const FLAG_ON_CAPTION =
  "On — product defects at or above the threshold file automatically; the rest stay drafts for review.";
const FLAG_OFF_CAPTION =
  "Off — every defect stays a draft for your review. Turn it on in config once both gates are met.";
const NOT_MEASURED_CAPTION =
  "Not measured yet. Run the accuracy harness to measure classification accuracy and calibrate the threshold.";

/** The met/unmet/not-measured indicator (word + colored dot — never color alone). */
function GateIndicator({ value, target }: { value: number | null; target: number }) {
  if (value === null) {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs"
        style={{ color: "var(--status-neutral)" }}
      >
        <span aria-hidden className="size-1.5 rounded-full bg-current" />
        <span>—</span>
      </span>
    );
  }
  const met = value >= target;
  const token = met ? "var(--status-pass)" : "var(--status-quarantine)";
  const word = met ? "Met" : "Not met yet";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" style={{ color: token }}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      <span>{word}</span>
    </span>
  );
}

function gateAria(label: string, value: number | null, target: number): string {
  if (value === null) {
    return `${label}, not measured yet, target ${target} percent`;
  }
  const met = value >= target ? "met" : "not met yet";
  return `${label} ${value} percent, target ${target} percent, ${met}`;
}

/** One percentage tile (accuracy / precision) with its target + met/unmet indicator. */
function PercentTile({
  label,
  value,
  target,
  caption,
}: {
  label: string;
  value: number | null;
  target: number;
  caption: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-secondary p-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-semibold" aria-label={gateAria(label, value, target)}>
        {value === null ? "—" : `${value}%`}
      </span>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{caption}</span>
        <GateIndicator value={value} target={target} />
      </div>
    </div>
  );
}

export function CalibrationPanel({
  data,
  isLoading,
}: {
  data?: Calibration;
  isLoading: boolean;
}) {
  return (
    <Card className="gap-4 p-4">
      <h2 className="text-sm font-semibold">Calibration</h2>

      {isLoading || !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <PercentTile
            label="Classification accuracy"
            value={data.classification_accuracy}
            target={ACCURACY_TARGET}
            caption="Target ≥ 85%"
          />
          <PercentTile
            label="Draft precision"
            value={data.draft_precision}
            target={PRECISION_TARGET}
            caption="Target ≥ 90%"
          />

          {/* Confidence threshold — the calibrated 0-100 floor (server value, never a literal). */}
          <div className="flex flex-col gap-1 rounded-lg bg-secondary p-4">
            <span className="text-xs text-muted-foreground">Confidence threshold</span>
            <span
              className="font-mono text-sm font-semibold"
              aria-label={`Confidence threshold ${data.confidence_threshold}`}
            >
              {data.confidence_threshold}
            </span>
            <span className="text-xs text-muted-foreground">Calibrated from the labeled set.</span>
          </div>

          {/* Autonomous filing — DISPLAY-ONLY (no write toggle here, D-04). */}
          <div className="flex flex-col gap-1 rounded-lg bg-secondary p-4">
            <span className="text-xs text-muted-foreground">Autonomous filing</span>
            <span
              role="status"
              className="text-sm font-semibold"
              style={{
                color: data.autonomous_enabled
                  ? "var(--status-pass)"
                  : "var(--status-neutral)",
              }}
              aria-label={`Autonomous filing: ${data.autonomous_enabled ? "On" : "Off"}`}
            >
              {data.autonomous_enabled ? "On" : "Off"}
            </span>
            <span className="text-xs text-muted-foreground">
              {data.classification_accuracy === null && data.draft_precision === null
                ? NOT_MEASURED_CAPTION
                : data.autonomous_enabled
                  ? FLAG_ON_CAPTION
                  : FLAG_OFF_CAPTION}
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
