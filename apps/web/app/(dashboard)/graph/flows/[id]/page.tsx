"use client";

/**
 * Flow detail (05-UI-SPEC §4 Flow detail) — /graph/flows/[id]. Breadcrumb + flow name +
 * category + the risk badge, then sections: Steps (the ordered page sequence as a numbered
 * list, each step → that page's detail) and Risk breakdown (the deterministic signals behind
 * the score, so the number is AUDITABLE — D-04 explainable). States: loading · populated ·
 * not-found · error (inline + Retry).
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { flowDetail } from "@/lib/api/kg";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/graph/breadcrumb";
import { ErrorState } from "@/components/graph/graph-states";
import { RiskBadge } from "@/components/graph/risk-badge";

/** Auditable risk-breakdown rows from the deterministic signal dict. */
function breakdownRows(signals: Record<string, unknown>): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (signals.has_destructive !== undefined) {
    rows.push({ label: "Destructive action", value: signals.has_destructive ? "yes" : "no" });
  }
  if (signals.state_change_edges !== undefined) {
    rows.push({ label: "State-changing edges", value: String(signals.state_change_edges) });
  }
  if (signals.auth_gated_steps !== undefined) {
    rows.push({ label: "Auth-gated steps", value: String(signals.auth_gated_steps) });
  }
  if (signals.form_count !== undefined) {
    rows.push({ label: "Forms", value: String(signals.form_count) });
  }
  if (signals.path_length !== undefined) {
    rows.push({ label: "Path length", value: String(signals.path_length) });
  }
  return rows;
}

export default function FlowDetailView() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);

  const query = useQuery({
    queryKey: ["kg", "flow", id],
    queryFn: () => flowDetail(id),
    retry: false,
  });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <div className="flex flex-col gap-4">
          <Breadcrumb
            crumbs={[
              { label: "Knowledge graph", href: "/graph" },
              { label: "Flows", href: "/graph/flows" },
            ]}
          />
          <p className="text-sm text-muted-foreground">No flow found.</p>
        </div>
      );
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }

  const flow = query.data!;
  const rows = breakdownRows(flow.signals as Record<string, unknown>);

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumb
        crumbs={[
          { label: "Knowledge graph", href: "/graph" },
          { label: "Flows", href: "/graph/flows" },
          { label: flow.name },
        ]}
      />

      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold leading-tight">{flow.name}</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {flow.category || "Uncategorized"}
          </span>
          <RiskBadge
            score={flow.risk_score}
            tier={flow.risk_tier}
            signals={flow.signals as Record<string, unknown>}
          />
        </div>
      </div>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Steps</h2>
        {flow.steps.length === 0 ? (
          <p className="text-sm text-muted-foreground">No steps in this flow.</p>
        ) : (
          <ol className="flex list-inside list-decimal flex-col gap-1">
            {flow.steps.map((step) => (
              <li key={step.fingerprint} className="text-sm">
                <Link
                  href={`/graph/pages/${encodeURIComponent(step.fingerprint)}`}
                  className="text-primary hover:underline"
                >
                  {step.title || step.url || step.fingerprint.slice(0, 8)}
                </Link>
              </li>
            ))}
          </ol>
        )}
      </Card>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Risk breakdown</h2>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No risk signals recorded.</p>
        ) : (
          <dl className="flex flex-col gap-1">
            {rows.map((row) => (
              <div key={row.label} className="flex justify-between text-sm">
                <dt className="text-muted-foreground">{row.label}</dt>
                <dd className="font-mono">{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>
    </div>
  );
}
