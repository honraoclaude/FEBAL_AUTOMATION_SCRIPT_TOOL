"use client";

/**
 * QA dashboard (10-UI-SPEC §2, DASH-02) — /dashboards/qa.
 *
 * Three sections: the Execution-history table (the Phase-7 styled `table` via RunsTable, drill to
 * /executions/{run_id}, flaky amber / failed red word+icon), the Failed-tests panel (name + mono
 * test id + the "Failed" verdict + a mono "{n} attempts" chip + an accent "View run" link), and the
 * Screenshots & videos links — each an AUTH-GATED URL built from the run-relative basename via the
 * Phase-7 artifactUrl (/api/executions/{run_id}/artifacts/{flow_id}/{kind}), the mono basename
 * caption, NEVER a raw filesystem path (T-10-24). CHECKER LOW-3: render ONLY the 3 real artifact
 * kinds — screenshot | trace | video — plus the honest "console + network captured in the trace"
 * note; an absent video -> "Video captured on failure only." (NOT 5 link slots).
 *
 * State machine: useQuery({ retry:false }) -> 403 no-access / isError + Retry / isLoading skeletons
 * / empty (no runs -> Go to executions) / populated. Server-authoritative throughout.
 */

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import {
  asArtifactKind,
  getQaDashboard,
  type FailedTest,
  type QaRun,
} from "@/lib/api/dashboards";
import { artifactBasename, artifactUrl } from "@/lib/api/executions";
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
import { VerdictBadge } from "@/components/executions/verdict-badge";
import {
  DashboardEmpty,
  DashboardError,
  NoAccess,
} from "@/components/dashboards/dashboard-states";
import Link from "next/link";

const KEY = ["dashboards", "qa"] as const;

/** Run duration mm:ss (the runs-table idiom; "—" while running/missing). */
function fmtDuration(run: QaRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const ms = Math.max(0, Date.parse(run.finished_at) - Date.parse(run.started_at));
  const total = Math.floor(ms / 1000);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function fmtTier(tier: string): string {
  return tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : tier;
}

function runStatusMeta(status: string): { word: string; token: string } {
  switch (status) {
    case "queued":
      return { word: "Queued", token: "var(--status-neutral)" };
    case "running":
      return { word: "Running", token: "var(--status-pass)" };
    case "killed":
      return { word: "Stopped", token: "var(--status-neutral)" };
    case "failed":
      return { word: "Failed", token: "var(--status-fail)" };
    default:
      return { word: "Passed", token: "var(--status-pass)" };
  }
}

/** The execution-history table (Tier · Started · Duration · Results · Status; row -> /executions/{id}). */
function HistoryTable({ runs }: { runs: QaRun[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Tier</TableHead>
          <TableHead scope="col">Started</TableHead>
          <TableHead scope="col">Duration</TableHead>
          <TableHead scope="col">Results</TableHead>
          <TableHead scope="col">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => {
          const status = runStatusMeta(run.status);
          return (
            <TableRow key={run.run_id}>
              <TableCell>
                <div className="flex flex-col">
                  <span>{fmtTier(run.tier)}</span>
                  <Link
                    href={`/executions/${run.run_id}`}
                    className="font-mono text-xs text-primary hover:underline"
                  >
                    {run.run_id}
                  </Link>
                </div>
              </TableCell>
              <TableCell>
                <span className="font-mono text-xs text-muted-foreground">
                  {run.started_at ?? "—"}
                </span>
              </TableCell>
              <TableCell>
                <span className="font-mono text-xs">{fmtDuration(run)}</span>
              </TableCell>
              <TableCell>
                <span className="font-mono text-xs">
                  <span>{run.passed} passed</span>
                  {" · "}
                  <span style={{ color: "var(--status-fail)" }}>
                    {run.failed} failed
                  </span>
                  {" · "}
                  <span style={{ color: "var(--status-quarantine)" }}>
                    {run.flaky} flaky
                  </span>
                </span>
              </TableCell>
              <TableCell>
                <span
                  className="inline-flex items-center gap-1.5 text-sm font-semibold"
                  aria-label={`Status: ${status.word}`}
                >
                  <span
                    aria-hidden
                    className="size-1.5 rounded-full"
                    style={{ backgroundColor: status.token }}
                  />
                  <span>{status.word}</span>
                </span>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** The artifact links for one failed test — the 3 real kinds, auth-gated URLs, the trace note. */
function ArtifactLinks({ test }: { test: FailedTest }) {
  // The kinds the server reports for this (run, flow), narrowed to the 3 real TestArtifact kinds.
  const kinds = new Set(
    test.artifacts
      .map((a) => asArtifactKind(a.kind))
      .filter((k): k is "screenshot" | "trace" | "video" => k !== null),
  );

  return (
    <div className="flex flex-col gap-1">
      <p className="font-mono text-xs text-muted-foreground">
        {test.flow_id} · {test.run_id}
      </p>
      {kinds.has("screenshot") ? (
        <a
          href={artifactUrl(test.run_id, test.flow_id, "screenshot")}
          className="text-sm text-primary hover:underline"
          aria-label={`Screenshot for ${test.flow_id}`}
        >
          Screenshot{" "}
          <span className="font-mono text-xs text-muted-foreground">
            {artifactBasename("screenshot")}
          </span>
        </a>
      ) : null}
      {kinds.has("trace") ? (
        <a
          href={artifactUrl(test.run_id, test.flow_id, "trace")}
          className="text-sm text-primary hover:underline"
          aria-label={`Trace for ${test.flow_id}`}
        >
          Trace{" "}
          <span className="font-mono text-xs text-muted-foreground">
            {artifactBasename("trace")}
          </span>
        </a>
      ) : null}
      <p className="text-xs text-muted-foreground">
        console + network captured in the trace
      </p>
      {kinds.has("video") ? (
        <a
          href={artifactUrl(test.run_id, test.flow_id, "video")}
          className="text-sm text-primary hover:underline"
          aria-label={`Video for ${test.flow_id}`}
        >
          Video{" "}
          <span className="font-mono text-xs text-muted-foreground">
            {artifactBasename("video")}
          </span>
        </a>
      ) : (
        <p className="text-xs text-muted-foreground">
          Video captured on failure only.
        </p>
      )}
    </div>
  );
}

export default function QaDashboardPage() {
  const query = useQuery({
    queryKey: KEY,
    queryFn: getQaDashboard,
    retry: false,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const data = query.data;
  const isEmpty = !!data && data.runs.length === 0 && data.failed_tests.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">QA dashboard</h1>
      </div>

      {forbidden ? (
        <NoAccess role={undefined} />
      ) : query.isError ? (
        <DashboardError onRetry={() => void query.refetch()} />
      ) : query.isLoading ? (
        <div className="flex flex-col gap-6">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : isEmpty ? (
        <DashboardEmpty
          heading="No runs yet"
          body="Run a suite to see execution history, failed tests, and their screenshots here."
          linkHref="/executions"
          linkLabel="Go to executions"
        />
      ) : data ? (
        <>
          {/* Execution history */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Execution history</p>
            {data.runs.length === 0 ? (
              <p className="py-12 text-center text-xs text-muted-foreground">
                No runs yet.
              </p>
            ) : (
              <HistoryTable runs={data.runs} />
            )}
          </section>

          {/* Failed tests */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Failed tests</p>
            {data.failed_tests.length === 0 ? (
              <p className="py-12 text-center text-xs text-muted-foreground">
                No failed tests.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {data.failed_tests.map((t) => (
                  <Card
                    key={`${t.run_id}:${t.flow_id}`}
                    className="flex-row items-center justify-between gap-2 p-3"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm">{t.flow_id}</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {t.run_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <VerdictBadge verdict={t.verdict} />
                      <span className="font-mono text-xs text-muted-foreground">
                        {t.attempts} attempts
                      </span>
                      <Link
                        href={`/executions/${t.run_id}`}
                        className="text-sm text-primary underline-offset-4 hover:underline"
                      >
                        View run
                      </Link>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </section>

          {/* Screenshots & videos */}
          <section className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Screenshots &amp; videos</p>
            {data.failed_tests.length === 0 ? (
              <p className="py-12 text-center text-xs text-muted-foreground">
                Artifacts show up for failed tests.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {data.failed_tests.map((t) => (
                  <Card key={`art:${t.run_id}:${t.flow_id}`} className="p-3">
                    <ArtifactLinks test={t} />
                  </Card>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
