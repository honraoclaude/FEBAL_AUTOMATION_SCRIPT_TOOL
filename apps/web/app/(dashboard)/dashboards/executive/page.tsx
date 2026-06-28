"use client";

/**
 * Executive dashboard (10-UI-SPEC §1, DASH-01) — /dashboards/executive.
 *
 * The KPI strip (Coverage with the honest definition caption + the meter, Pass rate, Open defects) +
 * the Trends region (Pass rate over time, Defects filed over time) + BOTH coverage numbers as
 * SEPARATE tiles, each with its own definition (NEVER merged — Pitfall 5 / T-10-26). Every value is
 * server-authoritative (the Plan-02 payload); loading shows skeletons, never a fabricated number.
 *
 * State machine (the executions/page.tsx precedent): useQuery({ retry:false }) -> 403 no-access
 * (defense-in-depth; the API is the boundary) / isError inline + Retry / isLoading skeletons /
 * empty (no data yet -> Go to executions) / populated.
 *
 * Graph-down note: the executive coverage tile depends on the graph; a 503 surfaces the honest
 * "Graph unavailable" message on the coverage tiles while the relational KPIs/charts still render
 * — but since the whole payload is one request, a graph-503 fails the request; we map 503 to the
 * honest graph-down message and still render the relational KPIs/charts from… (the payload is
 * all-or-nothing here, so 503 renders the graph-down state with a Retry).
 */

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { getExecutiveDashboard } from "@/lib/api/dashboards";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KpiTile, MeterKpiTile } from "@/components/dashboards/kpi-tile";
import {
  CountTrendCard,
  PassRateTrendCard,
} from "@/components/dashboards/dashboard-charts";
import {
  DashboardEmpty,
  DashboardError,
  DashboardSkeletonStrip,
  NoAccess,
} from "@/components/dashboards/dashboard-states";

const KEY = ["dashboards", "executive"] as const;

function GraphDown({ onRetry }: { onRetry: () => void }) {
  return (
    <Card role="alert" className="gap-2 p-4">
      <p className="text-sm font-semibold">Graph unavailable</p>
      <p className="text-sm text-muted-foreground">
        Coverage needs the knowledge graph — start it with{" "}
        <code className="font-mono">docker compose --profile graph up -d</code>, then
        retry.
      </p>
      <Button variant="outline" size="sm" className="mt-1 w-fit" onClick={onRetry}>
        Retry
      </Button>
    </Card>
  );
}

export default function ExecutiveDashboardPage() {
  const query = useQuery({
    queryKey: KEY,
    queryFn: getExecutiveDashboard,
    retry: false,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const graphDown = query.error instanceof ApiError && query.error.status === 503;
  const data = query.data;

  // Empty = no run history AND no discovered flows (truly nothing to show yet).
  const isEmpty =
    !!data &&
    data.pass_rate_trend.length === 0 &&
    data.coverage.total_discovered === 0 &&
    data.defects_trend.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Executive dashboard</h1>
      </div>

      {forbidden ? (
        <NoAccess role={undefined} />
      ) : graphDown ? (
        <GraphDown onRetry={() => void query.refetch()} />
      ) : query.isError ? (
        <DashboardError onRetry={() => void query.refetch()} />
      ) : query.isLoading ? (
        <DashboardSkeletonStrip />
      ) : isEmpty ? (
        <DashboardEmpty
          heading="No data yet"
          body="Dashboards fill in after you run a suite and classify failures. Run a suite, then come back."
          linkHref="/executions"
          linkLabel="Go to executions"
        />
      ) : data ? (
        <>
          {/* KPI strip */}
          <div className="grid gap-4 sm:grid-cols-3">
            <MeterKpiTile
              label="Coverage"
              percent={data.coverage.coverage_percent}
              measures="of discovered flows"
              remainder="gap"
              caption={data.coverage.definition}
            />
            <MeterKpiTile
              label="Pass rate"
              percent={data.kpis.pass_rate_percent}
              measures="of all tests run"
              remainder="failure"
              caption="Passing tests ÷ all tests run."
            />
            <KpiTile
              label="Open defects"
              value={String(data.kpis.open_defects)}
              caption="Product defects not yet resolved."
            />
          </div>

          {/* Exploration completeness — SEPARATE, its own definition (NEVER merged, Pitfall 5). */}
          <div className="grid gap-4 sm:grid-cols-2">
            <KpiTile
              label="Discovered flows"
              value={String(data.coverage.total_discovered)}
              caption={data.coverage.measured_against}
            />
            <KpiTile
              label="Covered flows"
              value={`${data.coverage.covered} of ${data.coverage.total_discovered}`}
              caption="Flows with an approved scenario AND a passing execution."
            />
          </div>

          {/* Trends region */}
          <div className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Trends</p>
            <div className="grid gap-4 md:grid-cols-2">
              <PassRateTrendCard points={data.pass_rate_trend} />
              <CountTrendCard
                title="Defects filed over time"
                noun="defects"
                points={data.defects_trend}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
