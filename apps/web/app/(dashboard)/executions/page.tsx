"use client";

/**
 * Run launcher + history list (07-UI-SPEC §1) — /executions, the section home (EXEC-05).
 *
 * Top: the "Run a suite" launcher card — a styled-native <select> tier picker (Smoke/Sanity/
 * Regression/Full/Risk-based, default Smoke) reusing the vendored input.tsx token classes (NO new
 * shadcn block — the styled-native discipline) + the honest resolved-count helper + an accent
 * "Start run" CTA. On start: POST /api/executions {tier} -> "Run started" toast -> navigate to the
 * live view. A queue-down start failure surfaces INLINE in the launcher (never a toast) with the
 * `--profile queue up` next step. No optimistic state — run state is server-authoritative.
 *
 * Below: the history runs table (newest-first) + the Trends region (Recharts pass-rate + duration,
 * derived from the server runs). States: loading (skeleton) · empty-no-runs (launcher stays
 * usable; charts show "Trends appear after your first run.") · populated · error (inline + Retry).
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  TIERS,
  deriveTrends,
  listRuns,
  startRun,
} from "@/lib/api/executions";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { RunsTable } from "@/components/executions/runs-table";
import { TrendCharts } from "@/components/executions/trend-charts";

const RUNS_KEY = ["executions", "runs"] as const;

export default function ExecutionsListPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tier, setTier] = useState<string>("smoke");

  const runsQuery = useQuery({
    queryKey: RUNS_KEY,
    queryFn: listRuns,
    retry: false,
  });

  const startMutation = useMutation({
    mutationFn: () => startRun(tier),
    onSuccess: async ({ run_id }) => {
      toast.success("Run started");
      await queryClient.invalidateQueries({ queryKey: RUNS_KEY });
      router.push(`/executions/${run_id}`);
    },
  });

  const runs = runsQuery.data ?? [];
  const trends = deriveTrends(runs);
  const isEmpty =
    !runsQuery.isLoading && !runsQuery.isError && runs.length === 0;

  // Honest helper copy: the resolved count is not exposed pre-run, so describe the selection.
  const helper =
    tier === "risk-based"
      ? "Top flows by risk and recent failures (resolved at run time)."
      : "The suite is selected when the run starts.";

  // A start failure (queue/worker down) surfaces inline in the launcher, not as a toast.
  const startError = startMutation.isError
    ? startMutation.error instanceof ApiError
      ? startMutation.error.detail
      : "Couldn't start the run."
    : null;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Executions</h1>
      </div>

      {/* Launcher card */}
      <Card className="gap-4 p-4">
        <p className="text-sm font-semibold">Run a suite</p>
        <div className="flex flex-col gap-2">
          <label htmlFor="tier" className="text-sm font-semibold">
            Suite tier
          </label>
          <select
            id="tier"
            value={tier}
            onChange={(e) => setTier(e.target.value)}
            disabled={startMutation.isPending}
            className="h-9 w-full max-w-xs rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30"
          >
            {TIERS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <p className="text-sm text-muted-foreground">{helper}</p>
        </div>
        <div className="flex flex-col gap-2">
          <Button
            className="w-fit"
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
          >
            Start run
          </Button>
          {startError ? (
            <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
              <p className="text-sm">
                Couldn&apos;t start the run. The execution worker and queue run under
                the <code className="font-mono">queue</code> profile — bring them up
                (<code className="font-mono">docker compose --profile queue up -d</code>)
                and start again.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => startMutation.mutate()}
              >
                Retry
              </Button>
            </div>
          ) : null}
        </div>
      </Card>

      {/* History + trends */}
      {runsQuery.isError ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
          <p className="text-sm font-semibold">Couldn&apos;t load executions</p>
          <p className="max-w-md text-center text-sm text-muted-foreground">
            Try again — if it keeps failing, check that the API container is healthy
            (<code className="font-mono">docker compose ps</code>).
          </p>
          <Button
            variant="outline"
            className="mt-1"
            onClick={() => void runsQuery.refetch()}
          >
            Retry
          </Button>
        </div>
      ) : runsQuery.isLoading ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      ) : isEmpty ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
            <p className="text-sm font-semibold">No runs yet</p>
            <p className="max-w-md text-center text-sm text-muted-foreground">
              Start a suite above to run your approved automation. Runs and their
              trends show up here.
            </p>
          </div>
          <TrendCharts points={[]} />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <RunsTable runs={runs} />
          <div className="flex flex-col gap-4">
            <p className="text-sm font-semibold">Trends</p>
            <TrendCharts points={trends} />
          </div>
        </div>
      )}
    </div>
  );
}
