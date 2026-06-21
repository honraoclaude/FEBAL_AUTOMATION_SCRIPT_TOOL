"use client";

/**
 * Trend charts (07-UI-SPEC §1 Trends) — the EXEC-05 surface, built on Recharts (the ONE
 * sanctioned frontend dep, named in CLAUDE.md's locked stack for these dashboards).
 *
 * Two cards: "Pass rate over time" (accent line series) + "Run duration over time" (muted line).
 * The series are DERIVED from the server-authoritative runs list (deriveTrends) — the runs table
 * remains the source of truth and the chart is SUPPLEMENTARY (WCAG 1.4.1 / non-text): each Card
 * has a caption title AND a visually-hidden accessible summary describing the trend, so the data
 * is never readable only via the chart. Empty trend data renders the honest "Trends appear after
 * your first run." caption — never an empty axis with fabricated points. Chart entrance animation
 * is disabled (isAnimationActive=false) to respect prefers-reduced-motion without extra wiring.
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

import type { TrendPoint } from "@/lib/api/executions";
import { Card } from "@/components/ui/card";

const AXIS_STYLE = { fontSize: 12, fontFamily: "var(--font-geist-mono)" } as const;

function passRateSummary(points: TrendPoint[]): string {
  if (points.length === 0) return "No pass-rate data yet.";
  const latest = points[points.length - 1];
  return `Pass rate over the last ${points.length} run${
    points.length === 1 ? "" : "s"
  }; most recent run ${Math.round(latest.passRate * 100)}% passed.`;
}

function durationSummary(points: TrendPoint[]): string {
  const withDuration = points.filter((p) => p.durationMs != null);
  if (withDuration.length === 0) return "No run-duration data yet.";
  const latest = withDuration[withDuration.length - 1];
  const seconds = Math.round((latest.durationMs ?? 0) / 1000);
  return `Run duration over the last ${withDuration.length} run${
    withDuration.length === 1 ? "" : "s"
  }; most recent run took ${seconds} seconds.`;
}

function EmptyTrends() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {["Pass rate over time", "Run duration over time"].map((title) => (
        <Card key={title} className="gap-4 p-4">
          <p className="text-sm font-semibold">{title}</p>
          <p className="py-12 text-center text-xs text-muted-foreground">
            Trends appear after your first run.
          </p>
        </Card>
      ))}
    </div>
  );
}

export function TrendCharts({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) {
    return <EmptyTrends />;
  }

  const durationData = points.map((p) => ({
    label: p.label,
    seconds: p.durationMs != null ? Math.round(p.durationMs / 1000) : null,
  }));
  const passRateData = points.map((p) => ({
    label: p.label,
    pct: Math.round(p.passRate * 100),
  }));

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="gap-4 p-4">
        <p className="text-sm font-semibold">Pass rate over time</p>
        <span className="sr-only">{passRateSummary(points)}</span>
        <div className="h-64 w-full" role="img" aria-label={passRateSummary(points)}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={passRateData}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS_STYLE} stroke="var(--muted-foreground)" />
              <YAxis
                domain={[0, 100]}
                tick={AXIS_STYLE}
                stroke="var(--muted-foreground)"
                width={36}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="pct"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="gap-4 p-4">
        <p className="text-sm font-semibold">Run duration over time</p>
        <span className="sr-only">{durationSummary(points)}</span>
        <div className="h-64 w-full" role="img" aria-label={durationSummary(points)}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={durationData}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS_STYLE} stroke="var(--muted-foreground)" />
              <YAxis tick={AXIS_STYLE} stroke="var(--muted-foreground)" width={36} />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="seconds"
                stroke="var(--status-neutral)"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
