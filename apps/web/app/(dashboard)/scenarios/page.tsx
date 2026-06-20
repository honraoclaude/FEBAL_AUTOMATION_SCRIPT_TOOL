"use client";

/**
 * Scenario review queue list (06-UI-SPEC §1) — /scenarios.
 *
 * Page header "Scenario review" + the filter segments (Drafts · Approved · Rejected · All,
 * deep-linkable via ?status=, default Drafts) + the queue table. Columns: Scenario (accent
 * drill-in link → /scenarios/[id]) · Source flow (name/category + mono flow-id caption) · Risk
 * (REUSE the risk-badge) · Status (status badge + "Edited" muted caption) · Updated (mono ts).
 * Default sort: risk-desc, then most-recently-updated.
 *
 * States: loading (skeleton rows) · empty-no-scenarios ("No scenarios yet" → Go to knowledge
 * graph) · empty-filter-no-match (per-filter → View drafts) · populated · rejected rows muted ·
 * inline error + Retry. Errors render inline (never a toast). Zero new shadcn, zero new deps.
 */

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { listScenarios, type ScenarioSummary } from "@/lib/api/scenarios";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadingRows } from "@/components/graph/graph-states";
import { RiskBadge } from "@/components/graph/risk-badge";
import { ScenarioErrorState } from "@/components/scenarios/scenario-states";
import { StatusBadge } from "@/components/scenarios/status-badge";

const FILTERS: { label: string; status: string }[] = [
  { label: "Drafts", status: "draft" },
  { label: "Approved", status: "approved" },
  { label: "Rejected", status: "rejected" },
  { label: "All", status: "all" },
];

const COLUMNS = 5;

function sortScenarios(rows: ScenarioSummary[]): ScenarioSummary[] {
  return [...rows].sort((a, b) => {
    const ra = a.flow_risk_score ?? -1;
    const rb = b.flow_risk_score ?? -1;
    if (rb !== ra) {
      return rb - ra;
    }
    return b.updated_at.localeCompare(a.updated_at);
  });
}

export default function ScenarioReviewView() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "draft";

  const query = useQuery({
    queryKey: ["scenarios", status],
    queryFn: () => listScenarios(status),
    retry: false,
  });

  const rows = sortScenarios(query.data ?? []);
  const isEmpty = !query.isLoading && !query.isError && rows.length === 0;

  function setStatus(next: string) {
    const sp = new URLSearchParams(params.toString());
    sp.set("status", next);
    router.push(`/scenarios?${sp.toString()}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Scenario review</h1>
      </div>

      {/* Filter segments — accent-underlined segments over tokens (NOT a new tabs block). */}
      <nav className="flex items-center gap-4" aria-label="Filter scenarios by status">
        {FILTERS.map((f) => {
          const active = f.status === status;
          return (
            <button
              key={f.status}
              type="button"
              onClick={() => setStatus(f.status)}
              aria-current={active ? "true" : undefined}
              className={
                "border-b-2 pb-1 text-sm font-semibold outline-none transition-colors " +
                "focus-visible:ring-[3px] focus-visible:ring-ring/50 " +
                (active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground")
              }
            >
              {f.label}
            </button>
          );
        })}
      </nav>

      {query.isError ? (
        <ScenarioErrorState onRetry={() => void query.refetch()} />
      ) : isEmpty ? (
        status === "draft" ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
            <p className="text-sm font-semibold">No scenarios yet</p>
            <p className="max-w-md text-center text-sm text-muted-foreground">
              Nothing has been generated for review. Generate scenarios from a flow first —
              they&apos;ll show up here as drafts.
            </p>
            <Button asChild variant="link" className="mt-1 text-primary">
              <Link href="/graph/flows">Go to knowledge graph</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
            <p className="text-sm font-semibold">
              No {status} scenarios
            </p>
            <p className="max-w-md text-center text-sm text-muted-foreground">
              Nothing here yet. Review the drafts to approve or reject them.
            </p>
            <Button
              variant="link"
              className="mt-1 text-primary"
              onClick={() => setStatus("draft")}
            >
              View drafts
            </Button>
          </div>
        )
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead>Source flow</TableHead>
              <TableHead>Risk</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading ? (
              <LoadingRows columns={COLUMNS} />
            ) : (
              rows.map((row) => {
                const muted = row.status === "rejected";
                return (
                  <TableRow key={row.id} className={muted ? "text-muted-foreground" : undefined}>
                    <TableCell>
                      <Link
                        href={`/scenarios/${row.id}`}
                        className="text-primary hover:underline"
                      >
                        {row.feature_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>{row.flow_id}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {row.flow_id}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <RiskBadge score={row.flow_risk_score} tier={row.flow_risk_tier} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={row.status} />
                        {row.edited ? (
                          <span className="text-xs text-muted-foreground">Edited</span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs text-muted-foreground">
                        {row.updated_at}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
