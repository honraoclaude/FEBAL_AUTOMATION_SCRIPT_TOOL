"use client";

/**
 * Execution history table (07-UI-SPEC §1) — Tier · Started · Duration · Results · Status.
 *
 * REUSES the vendored shadcn table (real <table> semantics, <th scope="col">). The Results cell
 * shows "{p} passed · {f} failed · {k} flaky" where FLAKY is amber and FAILED is red, each
 * carrying its WORD (WCAG 1.4.1 — never color-only). Each row drills into /executions/{run_id}
 * via an accent run-id link; a still-running row drills into the LIVE view. Default sort:
 * most-recently-started first (the list arrives newest-first from the server).
 */

import Link from "next/link";

import type { TestRun } from "@/lib/api/executions";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/** Run status -> {word, token} (07-UI-SPEC run-status mapping; reuse --status-* tokens). */
function runStatusMeta(run: TestRun): { word: string; token: string } {
  switch (run.status) {
    case "queued":
      return { word: "Queued", token: "var(--status-neutral)" };
    case "running":
      return { word: "Running", token: "var(--status-pass)" };
    case "killed":
      return { word: "Stopped", token: "var(--status-neutral)" };
    case "failed":
      return { word: "Failed", token: "var(--status-fail)" };
    case "passed":
    default:
      // A passed run with flakes still reads green (flakes are infra noise, not a failure).
      return { word: "Passed", token: "var(--status-pass)" };
  }
}

/** Run duration mm:ss from started/finished; "—" while running or missing. */
function fmtDuration(run: TestRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const ms = Math.max(0, Date.parse(run.finished_at) - Date.parse(run.started_at));
  const total = Math.floor(ms / 1000);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function fmtTier(tier: string): string {
  if (!tier) return tier;
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

export function RunsTable({ runs }: { runs: TestRun[] }) {
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
          const status = runStatusMeta(run);
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
