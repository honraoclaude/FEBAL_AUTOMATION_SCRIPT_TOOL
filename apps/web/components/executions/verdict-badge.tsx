/**
 * Per-test verdict badge (07-UI-SPEC §Color per-test verdict mapping) — the HONEST, server-
 * authoritative flaky display (D-05). REUSES the existing --status-* tokens (no new colors).
 *
 * The single most important color decision of the phase: **Flaky is AMBER, never red** — a flake
 * is infra noise that PASSED on retry, NOT a product failure. WCAG 1.4.1: every verdict carries
 * its WORD ("Passed"/"Flaky"/"Failed"/…) AND a distinct icon — never conveyed by color alone (the
 * icon is aria-hidden; the text carries the meaning).
 *
 *   passed          -> green  CheckCircle2  "Passed"
 *   flaky           -> amber  AlertTriangle "Flaky"   (passed on a retry)
 *   product_failure -> red    XCircle       "Failed"  (all attempts failed)
 *   running         -> green  Loader2 spin  "Running"
 *   queued          -> muted  Circle        "Queued"
 *   aborted         -> muted  MinusCircle   "Aborted" (drained by the kill switch)
 */

import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Loader2,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

export type Verdict =
  | "passed"
  | "flaky"
  | "product_failure"
  | "failed"
  | "running"
  | "queued"
  | "aborted";

interface VerdictMeta {
  word: string;
  token: string;
  Icon: LucideIcon;
  spin?: boolean;
}

const META: Record<Verdict, VerdictMeta> = {
  passed: { word: "Passed", token: "var(--status-pass)", Icon: CheckCircle2 },
  // Amber — distinct from BOTH passed (green) and failed (red).
  flaky: { word: "Flaky", token: "var(--status-quarantine)", Icon: AlertTriangle },
  product_failure: { word: "Failed", token: "var(--status-fail)", Icon: XCircle },
  failed: { word: "Failed", token: "var(--status-fail)", Icon: XCircle },
  running: { word: "Running", token: "var(--status-pass)", Icon: Loader2, spin: true },
  queued: { word: "Queued", token: "var(--status-neutral)", Icon: Circle },
  aborted: { word: "Aborted", token: "var(--status-neutral)", Icon: MinusCircle },
};

function normalize(value: string): Verdict {
  return (value in META ? value : "queued") as Verdict;
}

/** True for a product failure — the row gets the highlighted (left red border + tint) treatment. */
export function isFailure(verdict: string): boolean {
  const v = normalize(verdict);
  return v === "product_failure" || v === "failed";
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const { word, token, Icon, spin } = META[normalize(verdict)];
  return (
    <span
      className="inline-flex items-center gap-1 text-sm font-semibold"
      aria-label={`Verdict: ${word}`}
    >
      <Icon
        aria-hidden
        className={cn("size-4", spin && "animate-spin motion-reduce:animate-none")}
        style={{ color: token }}
      />
      <span style={{ color: token }}>{word}</span>
    </span>
  );
}
