"use client";

/**
 * Developer dashboard (10-UI-SPEC §3, DASH-03) — /dashboards/developer.
 *
 * Three sections: Root-cause groupings (mono "fp-{hash}" + the Phase-9 class badge + mono
 * "{n} occurrences" + a representative /defects/{id} link, count desc), the Errors-over-time chart
 * (per-day series, accent line), and the Module breakdown (Flow {flow_id} + mono "{n} failures" +
 * a proportional --status-fail bar, count desc). The Phase-9 class mapping is REUSED verbatim
 * (ClassBadge — Infrastructure muted / Automation amber / Product defect red, word+icon never color
 * alone). Server-authoritative throughout.
 *
 * State machine: useQuery({ retry:false }) -> 403 no-access / isError + Retry / isLoading skeletons
 * / empty (no failures grouped -> Go to executions) / populated.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { getDeveloperDashboard } from "@/lib/api/dashboards";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ClassBadge } from "@/components/defects/class-badge";
import { CountTrendCard } from "@/components/dashboards/dashboard-charts";
import {
  DashboardEmpty,
  DashboardError,
  NoAccess,
} from "@/components/dashboards/dashboard-states";

const KEY = ["dashboards", "developer"] as const;

export default function DeveloperDashboardPage() {
  const query = useQuery({
    queryKey: KEY,
    queryFn: getDeveloperDashboard,
    retry: false,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const data = query.data;
  const isEmpty =
    !!data &&
    data.root_cause_groups.length === 0 &&
    data.errors_trend.length === 0 &&
    data.module_breakdown.length === 0;

  // The max failure count drives the proportional module-breakdown bar widths.
  const maxFailures = data
    ? Math.max(1, ...data.module_breakdown.map((m) => m.failure_count))
    : 1;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Developer dashboard</h1>
      </div>

      {forbidden ? (
        <NoAccess role={undefined} />
      ) : query.isError ? (
        <DashboardError onRetry={() => void query.refetch()} />
      ) : query.isLoading ? (
        <div className="flex flex-col gap-6">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : isEmpty ? (
        <DashboardEmpty
          heading="No failures grouped yet"
          body="Once runs produce classified failures, their root-cause groupings and trends show up here."
          linkHref="/executions"
          linkLabel="Go to executions"
        />
      ) : data ? (
        <>
          {/* Root-cause groupings */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Root-cause groupings</p>
            {data.root_cause_groups.length === 0 ? (
              <p className="py-12 text-center text-xs text-muted-foreground">
                No grouped failures.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Fingerprint</TableHead>
                    <TableHead scope="col">Class</TableHead>
                    <TableHead scope="col">Occurrences</TableHead>
                    <TableHead scope="col">Defect</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.root_cause_groups.map((g) => (
                    <TableRow key={`${g.classification}:${g.fingerprint}`}>
                      <TableCell>
                        <span className="font-mono text-xs">fp-{g.fingerprint}</span>
                      </TableCell>
                      <TableCell>
                        <ClassBadge classification={g.classification} />
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-xs">
                          {g.count} occurrences
                        </span>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/defects/${g.rep_defect_id}`}
                          className="font-mono text-xs text-primary hover:underline"
                        >
                          #{g.rep_defect_id}
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>

          {/* Error trends */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Error trends</p>
            <CountTrendCard
              title="Errors over time"
              noun="errors"
              points={data.errors_trend}
            />
          </section>

          {/* Module breakdown */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Module breakdown</p>
            {data.module_breakdown.length === 0 ? (
              <p className="py-12 text-center text-xs text-muted-foreground">
                No module failures.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {data.module_breakdown.map((m) => {
                  const pct = (m.failure_count / maxFailures) * 100;
                  return (
                    <Card key={m.flow_id} className="gap-2 p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Flow {m.flow_id}</span>
                        <span className="font-mono text-xs">
                          {m.failure_count} failures
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-valuenow={m.failure_count}
                        aria-valuemin={0}
                        aria-valuemax={maxFailures}
                        aria-label={`Flow ${m.flow_id}: ${m.failure_count} failures`}
                        className="h-2 w-full overflow-hidden rounded-full bg-secondary"
                      >
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: "var(--status-fail)",
                          }}
                        />
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
