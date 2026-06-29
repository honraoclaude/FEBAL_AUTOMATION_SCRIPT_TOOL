"use client";

/**
 * Coverage panel (10-UI-SPEC §4, DASH-04) — /coverage.
 *
 * Two DISTINCT coverage metrics, NEVER merged (Pitfall 5 / T-10-31):
 *
 *   1. Flow coverage (lifecycle) card — the mono "{n}%" + the green/muted meter + the honest
 *      definition DISPLAYED inline (D-02) + the covered/total mono counts, followed by the per-flow
 *      drill-down table (Flow · Approved scenario · Passing execution · Covered — a green check /
 *      muted dash per condition + the resolved word, flow name -> /graph/flows/{id}).
 *   2. Exploration completeness card — the SEPARATE Phase-5 ground-truth metric with its OWN
 *      definition, clearly labeled so the two are never read as one number.
 *
 * Every value is server-authoritative (the Plan-02 /api/coverage/flows + the Phase-5 /api/coverage
 * payloads); loading shows skeletons, never a fabricated number. State machine (the executive
 * precedent): useQuery({ retry:false }) -> 403 no-access / 503 graph-down (honest) / isError inline
 * + Retry / isLoading skeletons / empty (no flows -> Go to targets) / populated.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import {
  getCoverageFlows,
  getGroundTruthCoverage,
  type FlowCoverageRow,
} from "@/lib/api/coverage";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MeterKpiTile } from "@/components/dashboards/kpi-tile";
import {
  DashboardEmpty,
  DashboardError,
  DashboardSkeletonStrip,
  NoAccess,
} from "@/components/dashboards/dashboard-states";

const FLOWS_KEY = ["coverage", "flows"] as const;
const GT_KEY = ["coverage", "ground-truth"] as const;

/** The honest graph-down state — coverage needs the graph (mirrors the executive GraphDown). */
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

/** A green check (condition met) / muted dash (not met), each carrying its WORD (never color alone). */
function ConditionCell({ met, label }: { met: boolean; label: string }) {
  return met ? (
    <span
      className="inline-flex items-center gap-1.5 text-sm"
      style={{ color: "var(--status-pass)" }}
    >
      <Check aria-hidden className="size-4" />
      {label}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
      <Minus aria-hidden className="size-4" />
      None
    </span>
  );
}

/** The covered cell — green "Covered" / muted "Not covered" (word + dot, never color alone). */
function CoveredCell({ covered }: { covered: boolean }) {
  const token = covered ? "var(--status-pass)" : "var(--status-neutral)";
  return (
    <span
      className="inline-flex items-center gap-1.5 text-sm font-semibold"
      aria-label={covered ? "Covered" : "Not covered"}
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full"
        style={{ backgroundColor: token }}
      />
      <span style={{ color: token }}>{covered ? "Covered" : "Not covered"}</span>
    </span>
  );
}

function FlowTable({ flows }: { flows: FlowCoverageRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Flow</TableHead>
          <TableHead scope="col">Approved scenario</TableHead>
          <TableHead scope="col">Passing execution</TableHead>
          <TableHead scope="col">Covered</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {flows.map((f) => (
          <TableRow key={f.flow_id}>
            <TableCell>
              <Link
                href={`/graph/flows/${f.flow_id}`}
                className="font-mono text-xs text-primary underline-offset-4 hover:underline"
              >
                {f.flow_id}
              </Link>
            </TableCell>
            <TableCell>
              <ConditionCell met={f.has_approved} label="Approved" />
            </TableCell>
            <TableCell>
              <ConditionCell met={f.has_passing} label="Passing" />
            </TableCell>
            <TableCell>
              <CoveredCell covered={f.covered} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** The SEPARATE Phase-5 ground-truth card (its OWN definition; never merged — Pitfall 5). */
function GroundTruthCard() {
  const query = useQuery({
    queryKey: GT_KEY,
    queryFn: getGroundTruthCoverage,
    retry: false,
  });

  const definition =
    "Exploration completeness = discovered screens ÷ the committed ground-truth set. This measures how much of the app the explorer found — a different question from lifecycle coverage above.";

  return (
    <Card className="gap-3 p-4" data-testid="ground-truth-card">
      <p className="text-sm font-semibold">Exploration completeness</p>
      {query.isError ? (
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t load exploration completeness. It needs the knowledge graph.
        </p>
      ) : query.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : query.data ? (
        query.data.measured ? (
          <>
            <MeterKpiTile
              label="Exploration completeness"
              percent={query.data.coverage_percent}
              measures="of the ground-truth screens"
              remainder="gap"
            />
            <p className="font-mono text-xs text-muted-foreground">
              {query.data.screens_covered} of {query.data.screens_total} screens
            </p>
            <p className="text-sm text-muted-foreground">{definition}</p>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Not yet measured. Explore a target first — completeness is measured once
              the graph has discovered screens.
            </p>
            <p className="text-sm text-muted-foreground">{definition}</p>
          </>
        )
      ) : null}
    </Card>
  );
}

export default function CoveragePage() {
  const query = useQuery({
    queryKey: FLOWS_KEY,
    queryFn: getCoverageFlows,
    retry: false,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const graphDown = query.error instanceof ApiError && query.error.status === 503;
  const data = query.data;
  const isEmpty = !!data && data.total_discovered === 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Coverage</h1>
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
          heading="No discovered flows yet"
          body="Coverage needs discovered flows. Explore a target first, then approve scenarios and run them."
          linkHref="/targets"
          linkLabel="Go to targets"
        />
      ) : data ? (
        <>
          {/* Lifecycle coverage card */}
          <section className="flex flex-col gap-4" data-testid="lifecycle-card">
            <p className="text-sm font-semibold">Flow coverage</p>
            <MeterKpiTile
              label="Coverage"
              percent={data.coverage_percent}
              measures="of discovered flows"
              remainder="gap"
              caption={data.definition}
            />
            <p className="font-mono text-xs text-muted-foreground">
              {data.covered} of {data.total_discovered} flows covered
            </p>
            <FlowTable flows={data.flows} />
            <p className="text-xs text-muted-foreground">{data.measured_against}</p>
          </section>

          {/* Exploration completeness — SEPARATE card, its OWN definition (NEVER merged). */}
          <GroundTruthCard />
        </>
      ) : null}
    </div>
  );
}
