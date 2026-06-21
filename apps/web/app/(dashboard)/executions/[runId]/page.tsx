"use client";

/**
 * Live execution view + terminal run detail (07-UI-SPEC §2/§3) — /executions/[runId] (EXEC-06).
 *
 * Mirrors the Phase-4 Live Exploration View verbatim, retargeted from per-STEP exploration events
 * to per-TEST execution events. On mount it makes ONE GET /api/executions/{runId} to resolve the
 * unknown-run (404) state (it does NOT poll in parallel during a live run — the SSE stream is the
 * source of truth). It then opens `new EventSource('/api/executions/{runId}/events')` over the
 * same-origin /api/* rewrite so the httpOnly cookie authenticates (no token handling). Each event
 * is parsed into executionProgressEventSchema; counters take the latest ABSOLUTE values; the
 * per-test list upserts rows by test id. A killed run shows a REAL "Stopping…" draining state from
 * a real flag — NEVER a fake-instant kill (D-07). No fabricated/optimistic status crosses the
 * boundary (T-07-17): green/amber/red appears only when the server reports it.
 *
 * Once the run is terminal the SAME route renders the run-detail layout (the live view "freezes"):
 * the final per-test results table (failures first, then flaky, then passed) with auth-gated
 * Screenshot/Trace/Video links (W4: console + network live INSIDE the trace — one "Trace" link +
 * the note, NOT separate console/network links) built via artifactUrl from run-relative segments
 * (never a raw path), and the honest "Video captured on failure only." caption for passed/flaky.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import {
  artifactBasename,
  artifactUrl,
  executionProgressEventSchema,
  getRun,
  killRun,
  type ExecutionProgressEvent,
  type RunDetail,
} from "@/lib/api/executions";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusPill, type PillState } from "@/components/executions/status-pill";
import {
  VerdictBadge,
  isFailure,
  type Verdict,
} from "@/components/executions/verdict-badge";

const ROW_CAP = 200;

type ConnState =
  | "connecting"
  | "running"
  | "stopping"
  | "reconnecting"
  | "terminal"
  | "stream-lost"
  | "not-found";

interface TestRow {
  testId: string;
  testName: string;
  flowId: string | null;
  verdict: Verdict;
  attempts: number;
  durationMs: number | null;
}

/** Order failures first, then flaky, then everything else (the actionable ordering, §3). */
const VERDICT_ORDER: Record<string, number> = {
  product_failure: 0,
  failed: 0,
  flaky: 1,
  passed: 2,
  running: 3,
  queued: 4,
  aborted: 5,
};

function fmtElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  return `${ms.toLocaleString()} ms`;
}

function CounterTile({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <Card className="gap-2 p-4">
      <p className="text-xs font-normal text-muted-foreground">{label}</p>
      <p
        className={mono ? "text-sm font-semibold font-mono" : "text-sm font-semibold"}
        aria-label={`${label}: ${value}`}
      >
        {value}
      </p>
    </Card>
  );
}

export default function ExecutionRunPage() {
  const { runId } = useParams<{ runId: string }>();

  const [conn, setConn] = useState<ConnState>("connecting");
  const [latest, setLatest] = useState<ExecutionProgressEvent | null>(null);
  const [rows, setRows] = useState<Map<string, TestRow>>(new Map());
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const esRef = useRef<EventSource | null>(null);
  const closedRef = useRef(false);

  const killMutation = useMutation({
    mutationFn: () => killRun(runId),
    onSuccess: () => {
      toast.success("Stopping the run");
      setConfirmOpen(false);
      // No optimistic terminal state — show the honest draining state until the stream confirms.
      setConn((c) => (c === "terminal" ? c : "stopping"));
    },
  });

  // Resolve the unknown-run / already-terminal state once on mount (no parallel polling).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const run = await getRun(runId);
        if (cancelled) return;
        setDetail(run);
        // An already-terminal run renders the detail layout directly (opened after it finished).
        if (run.status === "passed" || run.status === "failed" || run.status === "killed") {
          setConn("terminal");
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setConn("not-found");
        }
        // Any other error: fall through and let the stream try (it owns its error path).
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const applyEvent = useCallback((ev: ExecutionProgressEvent) => {
    setLatest(ev);
    // Upsert the per-test row by its test id (the frame's per-test delta — null on a snapshot).
    if (ev.test_id) {
      const id = ev.test_id;
      setRows((prev) => {
        const next = new Map(prev);
        next.set(id, {
          testId: id,
          testName: ev.test_name ?? id,
          flowId: ev.flow_id ?? null,
          verdict: (ev.test_status ?? "queued") as Verdict,
          attempts: ev.attempt || 1,
          durationMs: ev.duration_ms ?? null,
        });
        // Bound the in-DOM list to a sensible cap (a full suite is normally far smaller).
        if (next.size > ROW_CAP) {
          const firstKey = next.keys().next().value;
          if (firstKey !== undefined) next.delete(firstKey);
        }
        return next;
      });
    }
    // The RUN status drives the connection state (server-authoritative — never optimistic).
    if (ev.status === "passed" || ev.status === "failed" || ev.status === "killed") {
      setConn("terminal");
      closedRef.current = true;
      esRef.current?.close();
      // Refresh the detail payload so the terminal table has the final per-flow results.
      void getRun(runId)
        .then((run) => setDetail(run))
        .catch(() => {});
    } else if (ev.status === "stopping") {
      setConn("stopping");
    } else {
      setConn((c) => (c === "stopping" ? "stopping" : "running"));
    }
  }, [runId]);

  const notFound = conn === "not-found";
  useEffect(() => {
    if (notFound) return;
    const es = new EventSource(`/api/executions/${runId}/events`);
    esRef.current = es;
    closedRef.current = false;

    const onMessage = (e: MessageEvent<string>) => {
      try {
        const parsed = executionProgressEventSchema.parse(JSON.parse(e.data));
        applyEvent(parsed);
      } catch {
        // A malformed frame is dropped — never crash the stream on bad data.
      }
    };

    es.addEventListener("test", onMessage as EventListener);
    es.addEventListener("snapshot", onMessage as EventListener);
    es.onmessage = onMessage;
    es.onerror = () => {
      if (closedRef.current) return;
      if (es.readyState === EventSource.CONNECTING) {
        setConn((c) => (c === "terminal" ? c : "reconnecting"));
      } else if (es.readyState === EventSource.CLOSED) {
        setConn((c) => (c === "terminal" ? c : "stream-lost"));
      }
    };

    return () => {
      closedRef.current = true;
      es.close();
    };
  }, [runId, notFound, applyEvent]);

  const pill: PillState = useMemo(() => {
    if (conn === "terminal") {
      if (latest?.status === "killed" || detail?.status === "killed") return "stopped";
      return "complete";
    }
    if (conn === "stopping") return "stopping";
    if (conn === "reconnecting") return "reconnecting";
    if (conn === "running") return "running";
    return "connecting";
  }, [conn, latest, detail]);

  const passed = latest?.passed ?? detail?.passed ?? 0;
  const failed = latest?.failed ?? detail?.failed ?? 0;
  const flaky = latest?.flaky ?? detail?.flaky ?? 0;
  const total = latest?.total ?? detail?.total ?? 0;
  const completed = latest?.completed ?? passed + failed + flaky;
  const elapsedValue = latest ? fmtElapsed(latest.elapsed_s) : "—";
  const tier = detail?.tier ?? runId;
  const isLive = conn === "running" || conn === "reconnecting" || conn === "stopping";
  const isTerminal = conn === "terminal";
  const killed = latest?.status === "killed" || detail?.status === "killed";

  // ---- unknown run / 404 ---------------------------------------------------------------
  if (conn === "not-found") {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <p className="text-sm font-semibold">No run found for this id.</p>
        <Link
          href="/executions"
          className="text-sm text-primary underline-offset-4 hover:underline"
        >
          Back to executions
        </Link>
      </div>
    );
  }

  // The live per-test rows, ordered failures-first then flaky then passed (the actionable order).
  const liveRows = [...rows.values()].sort(
    (a, b) =>
      (VERDICT_ORDER[a.verdict] ?? 9) - (VERDICT_ORDER[b.verdict] ?? 9),
  );

  // The terminal table reads from the server detail payload (failures first, then flaky, passed).
  const detailRows = detail
    ? [...detail.results].sort(
        (a, b) =>
          (VERDICT_ORDER[a.verdict] ?? 9) - (VERDICT_ORDER[b.verdict] ?? 9),
      )
    : [];

  return (
    <div className="flex flex-col gap-6">
      {/* Header block */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-xl font-semibold leading-tight">
              {isTerminal ? `${tier} run` : `Running ${tier} suite`}
            </h1>
            <p className="font-mono text-xs text-muted-foreground">Run {runId}</p>
          </div>
          <StatusPill state={pill} />
        </div>
        <div className="flex items-center gap-4">
          {isLive && !killed ? (
            <Button
              variant="destructive"
              disabled={conn === "stopping"}
              onClick={() => setConfirmOpen(true)}
            >
              {conn === "stopping" ? "Stopping…" : "Kill run"}
            </Button>
          ) : null}
          <Link
            href="/executions"
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            Back to executions
          </Link>
        </div>
      </div>

      {/* Draining banner — the HONEST stopping state (amber, inline; never a fake-instant kill). */}
      {conn === "stopping" ? (
        <Card
          role="alert"
          className="gap-2 border-l-2 p-4"
          style={{ borderLeftColor: "var(--status-quarantine)" }}
        >
          <p className="text-sm">
            Stopping the run… finishing the current test and dropping the rest.
          </p>
        </Card>
      ) : null}

      {/* Terminal banner (inline; never a toast). */}
      {isTerminal ? (
        <Card
          role="alert"
          data-testid="terminal-banner"
          className="gap-2 border-l-2 p-4"
          style={{
            borderLeftColor: killed
              ? "var(--status-neutral)"
              : failed > 0
                ? "var(--status-fail)"
                : "var(--status-pass)",
          }}
        >
          {killed ? (
            <p className="text-sm">
              Run stopped. {completed} of {total} tests ran before you stopped it;
              their results are kept.
            </p>
          ) : failed > 0 ? (
            <p className="text-sm">
              Run complete — {failed} of {total} tests failed. Open a failed test to
              see its trace and screenshot.
            </p>
          ) : (
            <p className="text-sm">
              Run complete — {total} tests passed.
              {flaky > 0
                ? ` ${flaky} were flaky and passed on retry.`
                : ""}
            </p>
          )}
        </Card>
      ) : null}

      {conn === "stream-lost" ? (
        <Card
          role="alert"
          className="gap-2 border-l-2 p-4"
          style={{ borderLeftColor: "var(--status-quarantine)" }}
        >
          <p className="text-sm">
            Lost connection to the live feed. The run may still be going — reload to
            reconnect.
          </p>
          <Button
            variant="outline"
            className="mt-2 w-fit"
            onClick={() => window.location.reload()}
          >
            Reload
          </Button>
        </Card>
      ) : null}

      {/* Counters strip */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <CounterTile label="Passed" value={String(passed)} mono />
        <CounterTile label="Failed" value={String(failed)} mono />
        <CounterTile label="Flaky" value={String(flaky)} mono />
        <CounterTile label="Total" value={String(total)} mono />
        <CounterTile label="Elapsed" value={elapsedValue} mono />
      </div>

      {/* Progress affordance (styled-native bar over tokens). */}
      <div className="flex flex-col gap-1">
        <p className="font-mono text-xs text-muted-foreground">
          {completed} of {total} tests
        </p>
        <div
          role="progressbar"
          aria-valuenow={completed}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-label={`${completed} of ${total} tests`}
          className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
        >
          <div
            className="h-full rounded-full transition-[width] motion-reduce:transition-none"
            style={{
              width: total > 0 ? `${(completed / total) * 100}%` : "0%",
              backgroundColor: "var(--status-pass)",
            }}
          />
        </div>
      </div>

      {/* Terminal run detail OR the live per-test list. */}
      {isTerminal ? (
        <Card className="gap-4 p-4">
          <p className="text-sm font-semibold">Test results</p>
          {detailRows.length === 0 ? (
            <p className="py-12 text-center text-xs text-muted-foreground">
              No tests ran.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Test</TableHead>
                  <TableHead scope="col">Verdict</TableHead>
                  <TableHead scope="col">Attempts</TableHead>
                  <TableHead scope="col">Duration</TableHead>
                  <TableHead scope="col">Artifacts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detailRows.map((r) => {
                  const failure = isFailure(r.verdict);
                  return (
                    <TableRow
                      key={r.flow_id}
                      style={
                        failure
                          ? {
                              borderLeft: "2px solid var(--status-fail)",
                              backgroundColor: "color-mix(in oklab, var(--status-fail) 8%, transparent)",
                            }
                          : undefined
                      }
                    >
                      <TableCell>
                        <span className="font-mono text-xs">{r.flow_id}</span>
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict={r.verdict} />
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-xs">{r.attempts}</span>
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-xs">{fmtMs(r.duration_ms)}</span>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <a
                            href={artifactUrl(runId, r.flow_id, "screenshot")}
                            className="text-sm text-primary hover:underline"
                            aria-label={`Screenshot for ${r.flow_id}`}
                          >
                            Screenshot{" "}
                            <span className="font-mono text-xs text-muted-foreground">
                              {artifactBasename("screenshot")}
                            </span>
                          </a>
                          <a
                            href={artifactUrl(runId, r.flow_id, "trace")}
                            className="text-sm text-primary hover:underline"
                            aria-label={`Trace for ${r.flow_id}`}
                          >
                            Trace{" "}
                            <span className="font-mono text-xs text-muted-foreground">
                              {artifactBasename("trace")}
                            </span>
                          </a>
                          <p className="text-xs text-muted-foreground">
                            console + network captured in the trace
                          </p>
                          {failure ? (
                            <a
                              href={artifactUrl(runId, r.flow_id, "video")}
                              className="text-sm text-primary hover:underline"
                              aria-label={`Video for ${r.flow_id}`}
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
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Card>
      ) : (
        <Card className="gap-2 p-4">
          <p className="text-sm font-semibold">Test results</p>
          {liveRows.length === 0 ? (
            <p className="py-12 text-center text-xs text-muted-foreground">
              Waiting for the first test…
            </p>
          ) : (
            <ul
              role="log"
              aria-live="polite"
              aria-relevant="additions text"
              className="divide-y divide-border"
            >
              {liveRows.map((r) => (
                <li
                  key={r.testId}
                  className="flex items-center justify-between gap-2 py-2"
                >
                  <div className="flex flex-col">
                    <span className="text-sm">{r.testName}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {r.testId}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <VerdictBadge verdict={r.verdict} />
                    {r.attempts > 1 ? (
                      <span className="font-mono text-xs text-muted-foreground">
                        {r.attempts} attempts
                      </span>
                    ) : null}
                    {r.durationMs != null ? (
                      <span className="font-mono text-xs text-muted-foreground">
                        {fmtMs(r.durationMs)}
                      </span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* Kill confirmation (focus-trapped Dialog; "Keep running" is the default focus). */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Kill this run?</DialogTitle>
            <DialogDescription>
              Tests already finished are kept in the history. The current test drains
              to a clean stop — no results are corrupted.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={killMutation.isPending}
            >
              Keep running
            </Button>
            <Button
              variant="destructive"
              onClick={() => killMutation.mutate()}
              disabled={killMutation.isPending}
            >
              Kill run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
