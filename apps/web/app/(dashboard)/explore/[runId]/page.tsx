"use client";

/**
 * Live Exploration View (04-UI-SPEC — EXPL-01). The ONE new authenticated page this phase.
 *
 * On mount it makes ONE GET /api/executions/{runId} to resolve the unknown-run (404) state and
 * to render a terminal state immediately if the run already finished (it does NOT poll in
 * parallel during a live run — the SSE stream is the source of truth, UI-SPEC interaction
 * default). It then opens `new EventSource('/api/explore/${runId}/events')` over the same-origin
 * /api/* rewrite so the httpOnly cookie authenticates without any token handling (consistent
 * with lib/api/client.ts). Each event is parsed into exploreProgressEventSchema; counters take
 * the latest ABSOLUTE values; the feed appends feed_line capped to the last 200 rows; the
 * screenshot swaps with a ≤150ms opacity cross-fade. Terminal stop_reason closes the stream
 * and maps (L-2) to one of the 9 states. Full a11y: role="log" feed, role="status" pill,
 * counter aria-labels, dynamic screenshot alt, refused reason in text not color, reduced-motion.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ApiError, api } from "@/lib/api/client";
import {
  exploreProgressEventSchema,
  screenshotUrl,
  stopExplore,
  type ExploreProgressEvent,
} from "@/lib/api/explore";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CounterTile } from "@/components/explore/counter-tile";
import { FeedRow } from "@/components/explore/feed-row";
import {
  StatusPill,
  type PillState,
} from "@/components/explore/status-pill";
import {
  TerminalBanner,
  type BannerVariant,
} from "@/components/explore/terminal-banner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const FEED_CAP = 200;

/** A connection phase distinct from the run's terminal stop_reason. */
type ConnState =
  | "connecting"
  | "running"
  | "reconnecting"
  | "terminal"
  | "stream-lost"
  | "not-found";

interface FeedItem {
  step: number;
  line: string;
  timestamp: string;
}

/** L-2: map a backend STOP_REASONS value onto the terminal UI banner/pill variant. */
function mapStopReason(reason: string | null | undefined): {
  banner: BannerVariant;
  pill: PillState;
} {
  switch (reason) {
    case "saturation":
    case "converged":
      return { banner: "complete", pill: "complete" };
    case "failed":
      return { banner: "failed", pill: "failed" };
    case "stopped":
      return { banner: "stopped", pill: "stopped" };
    // max_steps / max_depth / wall_clock / budget -> a bounded, designed stop (amber).
    case "max_steps":
    case "max_depth":
    case "wall_clock":
    case "budget":
    default:
      return { banner: "budget", pill: "budget" };
  }
}

/** Format elapsed seconds as mm:ss for the Elapsed counter. */
function fmtElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export default function ExploreRunPage() {
  const { runId } = useParams<{ runId: string }>();

  const [conn, setConn] = useState<ConnState>("connecting");
  const [latest, setLatest] = useState<ExploreProgressEvent | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [stopReason, setStopReason] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [atBottom, setAtBottom] = useState(true);

  const esRef = useRef<EventSource | null>(null);
  const feedScrollRef = useRef<HTMLDivElement | null>(null);
  const atBottomRef = useRef(true);
  const closedRef = useRef(false);

  // Resolve the unknown-run / already-terminal state once on mount (no parallel polling).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.get<{ run_id: string; status: string; error: string | null }>(
          `/api/executions/${runId}`,
        );
        // Run exists (terminal or in-flight). The SSE snapshot carries the precise terminal
        // stop_reason on (re)subscribe, so we don't need to branch on status here.
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setConn("not-found");
        }
        // Any other error: fall through and let the stream try (it has its own error path).
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const applyEvent = useCallback((ev: ExploreProgressEvent) => {
    setLatest(ev);
    if (ev.feed_line) {
      setFeed((prev) => {
        const next = [
          ...prev,
          {
            step: ev.step,
            line: ev.feed_line,
            timestamp: new Date().toLocaleTimeString(),
          },
        ];
        return next.length > FEED_CAP ? next.slice(next.length - FEED_CAP) : next;
      });
    }
    if (ev.stop_reason) {
      setStopReason(ev.stop_reason);
      setConn("terminal");
      closedRef.current = true;
      esRef.current?.close();
    } else {
      setConn("running");
    }
  }, []);

  // Open the SSE stream (cookie auth via same-origin proxy). EventSource auto-reconnects;
  // we never tear down state on transient errors — we show the amber "Reconnecting…" pill.
  const notFound = conn === "not-found";
  useEffect(() => {
    if (notFound) return;
    const es = new EventSource(`/api/explore/${runId}/events`);
    esRef.current = es;
    closedRef.current = false;

    const onMessage = (e: MessageEvent<string>) => {
      try {
        const parsed = exploreProgressEventSchema.parse(JSON.parse(e.data));
        applyEvent(parsed);
      } catch {
        // A malformed frame is dropped — never crash the stream on bad data.
      }
    };

    es.addEventListener("step", onMessage as EventListener);
    es.addEventListener("snapshot", onMessage as EventListener);
    es.onmessage = onMessage;
    es.onerror = () => {
      // Terminal already handled (we closed it) — ignore. Otherwise EventSource is in its
      // native retry backoff: show amber "Reconnecting…" and freeze last-known values.
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

  // Auto-scroll the feed to the latest row ONLY when the user is at the bottom.
  useEffect(() => {
    if (atBottomRef.current && feedScrollRef.current) {
      feedScrollRef.current.scrollTop = feedScrollRef.current.scrollHeight;
    }
  }, [feed]);

  function onFeedScroll() {
    const el = feedScrollRef.current;
    if (!el) return;
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    atBottomRef.current = bottom;
    setAtBottom(bottom);
  }

  function jumpToLatest() {
    const el = feedScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      atBottomRef.current = true;
      setAtBottom(true);
    }
  }

  async function confirmStop() {
    setStopping(true);
    try {
      await stopExplore(runId);
      setConfirmOpen(false);
      // The stream emits the terminal `stopped` event; no optimistic state change here.
    } finally {
      setStopping(false);
    }
  }

  const pill: PillState = useMemo(() => {
    if (conn === "terminal") return mapStopReason(stopReason).pill;
    if (conn === "reconnecting") return "reconnecting";
    if (conn === "running") return "live";
    return "connecting";
  }, [conn, stopReason]);

  const pagesFound = latest?.pages_found ?? 0;
  const actionsTaken = latest?.actions_taken ?? 0;
  const costValue = latest ? `$${latest.cost_usd.toFixed(4)}` : "—";
  const elapsedValue = latest ? fmtElapsed(latest.elapsed_s) : "—";
  const isRunning = conn === "running" || conn === "reconnecting";
  const targetTitle = latest?.current_title || runId;
  const screenshotName = latest?.screenshot_path ?? null;
  const screenshotSrc = screenshotName
    ? screenshotUrl(runId, screenshotName)
    : null;

  // ---- unknown run / 404 ---------------------------------------------------------------
  if (conn === "not-found") {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <p className="text-sm font-semibold">No exploration found for this run.</p>
        <Link
          href="/targets"
          className="text-sm text-primary underline-offset-4 hover:underline"
        >
          Back to targets
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header block */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-xl font-semibold leading-tight">
              {conn === "terminal" ? "Exploration of" : "Exploring"} {targetTitle}
            </h1>
            <p className="font-mono text-xs text-muted-foreground">Run {runId}</p>
          </div>
          <StatusPill state={pill} />
        </div>
        <div className="flex items-center gap-4">
          {isRunning ? (
            <Button
              variant="destructive"
              onClick={() => setConfirmOpen(true)}
            >
              Stop exploration
            </Button>
          ) : null}
          <Link
            href="/targets"
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            Back to targets
          </Link>
        </div>
      </div>

      {/* Terminal banner (inline; never a toast) */}
      {conn === "terminal" ? (
        <TerminalBanner
          variant={mapStopReason(stopReason).banner}
          pagesFound={pagesFound}
          actionsTaken={actionsTaken}
          error={undefined}
        />
      ) : null}
      {conn === "stream-lost" ? (
        <TerminalBanner
          variant="stream-lost"
          onReload={() => window.location.reload()}
        />
      ) : null}

      {/* Counters strip */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <CounterTile label="Pages found" value={String(pagesFound)} />
        <CounterTile label="Actions" value={String(actionsTaken)} />
        <CounterTile label="Cost" value={costValue} mono />
        <CounterTile label="Elapsed" value={elapsedValue} mono />
      </div>

      {/* Panels grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Action feed */}
        <Card className="gap-2 p-4">
          <p className="text-sm font-semibold">Action feed</p>
          {feed.length >= FEED_CAP ? (
            <p className="text-xs text-muted-foreground">
              Showing the latest 200 steps
            </p>
          ) : null}
          <div className="relative">
            <div
              ref={feedScrollRef}
              onScroll={onFeedScroll}
              className="max-h-96 overflow-y-auto"
            >
              {feed.length === 0 ? (
                <p className="py-12 text-center text-xs text-muted-foreground">
                  Waiting for the first step…
                </p>
              ) : (
                <ul
                  role="log"
                  aria-live="polite"
                  aria-relevant="additions"
                  className="divide-y divide-border"
                >
                  {feed.map((item, i) => (
                    <FeedRow
                      key={`${item.step}-${i}`}
                      step={item.step}
                      line={item.line}
                      timestamp={item.timestamp}
                    />
                  ))}
                </ul>
              )}
            </div>
            {!atBottom && feed.length > 0 ? (
              <Button
                variant="outline"
                size="sm"
                className="absolute bottom-2 right-2 text-primary"
                onClick={jumpToLatest}
              >
                Jump to latest
              </Button>
            ) : null}
          </div>
        </Card>

        {/* Current page */}
        <Card className="gap-2 p-4">
          <p className="text-sm font-semibold">Current page</p>
          <p className="text-sm">{latest?.current_title || "—"}</p>
          <p
            className="truncate font-mono text-xs text-muted-foreground"
            title={latest?.current_url || ""}
          >
            {latest?.current_url || "—"}
          </p>
          <div className="mt-2 flex aspect-[16/10] w-full items-center justify-center overflow-hidden rounded-md border border-border bg-background">
            {screenshotSrc ? (
              /* eslint-disable-next-line @next/next/no-img-element -- the screenshot is served
                 by the auth-gated /api proxy route, not a static/optimizable asset; a plain
                 <img> with an onLoad opacity cross-fade is exactly the UI-SPEC behavior. */
              <img
                key={screenshotSrc}
                src={screenshotSrc}
                alt={`Latest captured screenshot: ${latest?.current_title || "current page"}`}
                className="size-full object-contain opacity-0 transition-opacity duration-150 motion-reduce:transition-none"
                onLoad={(e) => {
                  (e.currentTarget as HTMLImageElement).style.opacity = "1";
                }}
              />
            ) : (
              <p className="text-xs text-muted-foreground">No screenshot yet</p>
            )}
          </div>
        </Card>
      </div>

      {/* Stop confirmation (reuse the DeactivateDialog pattern / Dialog focus trap) */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stop this exploration?</DialogTitle>
            <DialogDescription>
              The run will halt where it is. Pages found so far are kept in the
              knowledge graph.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={stopping}
            >
              Keep exploring
            </Button>
            <Button
              variant="destructive"
              onClick={confirmStop}
              disabled={stopping}
            >
              Stop exploration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
