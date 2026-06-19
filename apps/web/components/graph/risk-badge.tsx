"use client";

/**
 * Risk-score badge (05-UI-SPEC Color §risk mapping). The deterministic 0-100 flow risk
 * score (D-04) maps onto the SAME `--status-*` tokens Phase 1 pre-reserved:
 *   high (>=67) → --status-fail (red) · medium (34-66) → --status-quarantine (amber) ·
 *   low (<34) → --status-pass (green) · unscored → --status-neutral (muted, label "—").
 *
 * WCAG 1.4.1 (never color alone): the badge carries the colored dot AND the mono numeric
 * score AND the tier WORD as text — the dot is aria-hidden, the text carries the meaning.
 * A tooltip surfaces the auditable risk-breakdown signals so the score is explainable.
 */

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type Tier = "high" | "medium" | "low";

const TIER_TOKEN: Record<Tier, string> = {
  high: "var(--status-fail)",
  medium: "var(--status-quarantine)",
  low: "var(--status-pass)",
};

const TIER_WORD: Record<Tier, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

function isTier(value: string): value is Tier {
  return value === "high" || value === "medium" || value === "low";
}

/** Human-readable risk-breakdown lines from the deterministic signal dict (auditable). */
function breakdownLines(signals: Record<string, unknown>): string[] {
  const lines: string[] = [];
  if (signals.has_destructive !== undefined) {
    lines.push(`Destructive action: ${signals.has_destructive ? "yes" : "no"}`);
  }
  if (signals.state_change_edges !== undefined) {
    lines.push(`State-changing edges: ${String(signals.state_change_edges)}`);
  }
  if (signals.auth_gated_steps !== undefined) {
    lines.push(`Auth-gated steps: ${String(signals.auth_gated_steps)}`);
  }
  if (signals.form_count !== undefined) {
    lines.push(`Forms: ${String(signals.form_count)}`);
  }
  if (signals.path_length !== undefined) {
    lines.push(`Path length: ${String(signals.path_length)}`);
  }
  return lines;
}

interface RiskBadgeProps {
  /** The 0-100 score; null/undefined renders the unscored "—" badge. */
  score?: number | null;
  tier?: string | null;
  /** The deterministic signal dict for the breakdown tooltip (optional). */
  signals?: Record<string, unknown>;
}

export function RiskBadge({ score, tier, signals }: RiskBadgeProps) {
  // Unscored: muted neutral badge with "—" — never a fabricated number (UI-SPEC).
  if (score === null || score === undefined || !tier || !isTier(tier)) {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[var(--status-neutral)]"
        aria-label="Risk: unscored"
      >
        <span
          aria-hidden
          className="size-1.5 rounded-full bg-[var(--status-neutral)]"
        />
        <span className="font-mono">—</span>
        <span>Unscored</span>
      </Badge>
    );
  }

  const lines = signals ? breakdownLines(signals) : [];
  const badge = (
    <Badge
      variant="outline"
      className="gap-1.5"
      aria-label={`Risk: ${score}, ${TIER_WORD[tier]}`}
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full"
        style={{ backgroundColor: TIER_TOKEN[tier] }}
      />
      <span className="font-mono">{score}</span>
      <span>{TIER_WORD[tier]}</span>
    </Badge>
  );

  if (lines.length === 0) {
    return badge;
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>{badge}</span>
        </TooltipTrigger>
        <TooltipContent>
          <div className="flex flex-col gap-0.5 text-xs">
            {lines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
