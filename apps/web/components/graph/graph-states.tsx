"use client";

/**
 * Shared KG-browse state pieces (05-UI-SPEC Screen & State Inventory): loading skeleton
 * rows, the empty states (no-graph / no-flows / no-elements), and the inline error surface
 * with a Retry button. Errors render INLINE in the content region — never as toasts
 * (UI-SPEC: read-only surface, no mutations, no success toasts). Every empty/error region
 * is real text with a reachable action link/button (never icon- or color-only — a11y).
 */

import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

/** Skeleton rows in the table body while a query is loading. */
export function LoadingRows({ columns }: { columns: number }) {
  return (
    <>
      {[0, 1, 2].map((r) => (
        <TableRow key={r}>
          {Array.from({ length: columns }).map((_, c) => (
            <TableCell key={c}>
              <Skeleton className="h-4 w-24" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

/** The shared "no knowledge graph yet" empty state → Go to targets. */
export function NoGraphEmpty() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
      <p className="text-sm font-semibold">No knowledge graph yet</p>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        Nothing has been explored. Run an exploration to discover pages, flows, and
        elements — they&apos;ll show up here.
      </p>
      <Button asChild variant="link" className="mt-1 text-primary">
        <Link href="/targets">Go to targets</Link>
      </Button>
    </div>
  );
}

/** A simple heading + body empty state (flows / elements variants). */
export function MessageEmpty({ heading, body }: { heading: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
      <p className="text-sm font-semibold">{heading}</p>
      <p className="max-w-md text-center text-sm text-muted-foreground">{body}</p>
    </div>
  );
}

/**
 * Inline error surface + Retry. A 503/Bolt-unreachable error (graph profile down) gets the
 * neo4j-specific copy; any other failure gets the generic copy (UI-SPEC error states).
 */
export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  const graphDown =
    error instanceof ApiError && (error.status === 503 || error.status === 502);
  const body = graphDown
    ? "The knowledge graph database isn't reachable. Neo4j runs under the graph profile — bring it up (graph_mode up) and retry."
    : "Couldn't load the knowledge graph. Try again — if it keeps failing, check that the API and Neo4j containers are healthy (docker compose ps).";
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card py-16"
    >
      <p className="max-w-md text-center text-sm text-muted-foreground">{body}</p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

/**
 * Stale freshness: a node's last_verified recency is a caption timestamp, NOT a color cue.
 * Stale = older than the freshness window; rows render muted + a Clock icon + tooltip
 * (reinforced by text, never color alone). Conservatively flags > 30 days.
 */
const STALE_MS = 30 * 24 * 60 * 60 * 1000;

export function isStale(lastVerified: string | null): boolean {
  if (!lastVerified) {
    return false;
  }
  const t = Date.parse(lastVerified);
  if (Number.isNaN(t)) {
    return false;
  }
  return Date.now() - t > STALE_MS;
}
