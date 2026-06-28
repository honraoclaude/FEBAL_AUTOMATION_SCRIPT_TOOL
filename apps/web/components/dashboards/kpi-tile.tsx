/**
 * KPI tile (10-UI-SPEC §1 KPI strip + "Coverage / pass-rate meters") — a card with a caption
 * label, a mono value, an optional honest-definition caption, and (for coverage / pass-rate) a
 * token-styled NATIVE meter.
 *
 * The meter is a styled-native `role="progressbar"` over the --status-* tokens (the Phase-7
 * progress-bar / Phase-9 confidence-meter precedent — NOT a Recharts gauge), with
 * aria-valuenow/min/max and an accessible name combining the value and what it measures. The
 * covered/passing portion fills --status-pass green; the remainder is --status-neutral muted (a gap)
 * for coverage OR --status-fail red (a real failure share) for pass rate. The numeral is the source
 * of truth; the color is supplementary (WCAG 1.4.1). The band/fill comes from the SERVER value
 * (the percent prop) — never a hardcoded client cutoff.
 *
 * `<KpiTile>` renders a plain scalar (e.g. open defects); `<MeterKpiTile>` adds the meter.
 */

import { Card } from "@/components/ui/card";

interface KpiTileProps {
  label: string;
  value: string;
  caption?: string;
}

export function KpiTile({ label, value, caption }: KpiTileProps) {
  return (
    <Card className="gap-2 p-4">
      <p className="text-xs font-normal text-muted-foreground">{label}</p>
      <p className="font-mono text-sm font-semibold" aria-label={`${label}: ${value}`}>
        {value}
      </p>
      {caption ? (
        <p className="text-xs font-normal text-muted-foreground">{caption}</p>
      ) : null}
    </Card>
  );
}

interface MeterKpiTileProps {
  label: string;
  /** The percentage 0..100 (server-authoritative — the meter fill + the mono numeral). */
  percent: number;
  /** What the meter measures, for the accessible name (e.g. "of discovered flows"). */
  measures: string;
  /** The remainder semantic: a coverage GAP reads muted; a pass-rate failing share reads red. */
  remainder: "gap" | "failure";
  caption?: string;
}

export function MeterKpiTile({
  label,
  percent,
  measures,
  remainder,
  caption,
}: MeterKpiTileProps) {
  // Clamp defensively to a sane 0..100 (the server already bounds it; this guards a bad payload).
  const pct = Math.max(0, Math.min(100, percent));
  const remainderToken =
    remainder === "failure" ? "var(--status-fail)" : "var(--status-neutral)";

  return (
    <Card className="gap-2 p-4">
      <p className="text-xs font-normal text-muted-foreground">{label}</p>
      <p
        className="font-mono text-sm font-semibold"
        aria-label={`${label}: ${pct}%`}
      >
        {pct}%
      </p>
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} ${Math.round(pct)} percent ${measures}`}
        className="h-2 w-full overflow-hidden rounded-full"
        style={{ backgroundColor: remainderToken }}
      >
        <div
          className="h-full rounded-full transition-[width] motion-reduce:transition-none"
          style={{
            width: `${pct}%`,
            backgroundColor: "var(--status-pass)",
          }}
        />
      </div>
      {caption ? (
        <p className="text-xs font-normal text-muted-foreground">{caption}</p>
      ) : null}
    </Card>
  );
}
