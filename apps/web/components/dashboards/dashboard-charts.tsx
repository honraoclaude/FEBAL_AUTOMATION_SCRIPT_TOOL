"use client";

/**
 * Dashboard trend charts (10-UI-SPEC "Charts") — reuses the Phase-7 trend-charts.tsx Recharts Card
 * pattern VERBATIM (Card-wrapped LineChart, ResponsiveContainer in an h-64 box, mono axis numerals,
 * accent-primary line, isAnimationActive={false} to respect prefers-reduced-motion without extra
 * wiring, role="img" + an sr-only accessible summary). ZERO new dependency — recharts is already
 * installed (Phase 7). The chart is SUPPLEMENTARY (WCAG 1.4.1): the KPI/table is the source of
 * truth and each card carries a visually-hidden summary so the data is never readable only via the
 * chart. Empty series render the honest "appears after…" caption — never a fabricated axis/points.
 *
 *   - <PassRateTrendCard>  pass-rate-over-time (0..100 % domain, accent line) — DASH-01
 *   - <CountTrendCard>     a per-day count series (defects filed / errors over time) — DASH-01/03
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CountPoint, PassRatePoint } from "@/lib/api/dashboards";
import { Card } from "@/components/ui/card";

const AXIS_STYLE = { fontSize: 12, fontFamily: "var(--font-geist-mono)" } as const;

const TOOLTIP_STYLE = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  fontSize: 12,
} as const;

function ChartShell({
  title,
  summary,
  empty,
  children,
}: {
  title: string;
  summary: string;
  empty: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card className="gap-4 p-4">
      <p className="text-sm font-semibold">{title}</p>
      {empty ? (
        <p className="py-12 text-center text-xs text-muted-foreground">
          Trends appear after your first run.
        </p>
      ) : (
        <>
          <span className="sr-only">{summary}</span>
          <div className="h-64 w-full" role="img" aria-label={summary}>
            <ResponsiveContainer width="100%" height="100%">
              {children as React.ReactElement}
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  );
}

/** Pass rate over time — 0..100 % domain, accent line (DASH-01). pass_rate is 0..1 -> %. */
export function PassRateTrendCard({ points }: { points: PassRatePoint[] }) {
  const data = points.map((p) => ({
    label: p.day ?? "—",
    pct: Math.round(p.pass_rate * 100),
  }));
  const summary =
    data.length === 0
      ? "No pass-rate data yet."
      : `Pass rate over ${data.length} day${data.length === 1 ? "" : "s"}; most recent ${
          data[data.length - 1].pct
        }% passed.`;

  return (
    <ChartShell title="Pass rate over time" summary={summary} empty={data.length === 0}>
      <LineChart data={data}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={AXIS_STYLE} stroke="var(--muted-foreground)" />
        <YAxis
          domain={[0, 100]}
          tick={AXIS_STYLE}
          stroke="var(--muted-foreground)"
          width={36}
        />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Line
          type="monotone"
          dataKey="pct"
          stroke="var(--primary)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartShell>
  );
}

/** A per-day count series (defects filed / errors over time) — accent line (DASH-01/03). */
export function CountTrendCard({
  title,
  noun,
  points,
}: {
  title: string;
  /** The plural noun for the accessible summary (e.g. "defects", "errors"). */
  noun: string;
  points: CountPoint[];
}) {
  const data = points.map((p) => ({ label: p.day ?? "—", count: p.count }));
  const summary =
    data.length === 0
      ? `No ${noun} data yet.`
      : `${title} over ${data.length} day${data.length === 1 ? "" : "s"}; most recent ${
          data[data.length - 1].count
        } ${noun}.`;

  return (
    <ChartShell title={title} summary={summary} empty={data.length === 0}>
      <LineChart data={data}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={AXIS_STYLE} stroke="var(--muted-foreground)" />
        <YAxis
          allowDecimals={false}
          tick={AXIS_STYLE}
          stroke="var(--muted-foreground)"
          width={36}
        />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Line
          type="monotone"
          dataKey="count"
          stroke="var(--primary)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartShell>
  );
}
