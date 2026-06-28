"use client";

/**
 * Shared dashboard state blocks (10-UI-SPEC Copywriting + Screen & State Inventory) — the honest
 * loading / error / empty / no-access regions the three dashboard pages reuse. Every region is real
 * text with a reachable action link/button (never icon-only or color-only); no fabricated number,
 * chart, or row ever renders in place of real data (the honesty rule).
 *
 *   - <DashboardError>   inline (never a toast), centered, + a Retry button (read failure)
 *   - <DashboardEmpty>   the honest "no data yet" + a path-forward link
 *   - <NoAccess>         defense-in-depth for a 403: the role can't open this view (the nav already
 *                        hides it). The API 403 is the real boundary; this renders, NEVER the data.
 *   - <DashboardSkeletonStrip> the KPI/row skeletons for the loading state
 */

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function DashboardError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
      <p className="text-sm font-semibold">Couldn&apos;t load this dashboard</p>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        Try again — if it keeps failing, check that the API container is healthy
        (<code className="font-mono">docker compose ps</code>).
      </p>
      <Button variant="outline" className="mt-1" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

export function DashboardEmpty({
  heading,
  body,
  linkHref,
  linkLabel,
}: {
  heading: string;
  body: string;
  linkHref: string;
  linkLabel: string;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
      <p className="text-sm font-semibold">{heading}</p>
      <p className="max-w-md text-center text-sm text-muted-foreground">{body}</p>
      <Link
        href={linkHref}
        className="mt-1 text-sm text-primary underline-offset-4 hover:underline"
      >
        {linkLabel}
      </Link>
    </div>
  );
}

/**
 * The no-access state for a 403 (the role hit a forbidden dashboard URL directly). The nav already
 * hides it; this is the defense-in-depth state — the API 403s and the client renders THIS, never the
 * data. `role` is echoed honestly; the link points to a permitted home.
 */
export function NoAccess({
  role,
  homeHref = "/targets",
  homeLabel = "Go to targets",
}: {
  role: string | undefined;
  homeHref?: string;
  homeLabel?: string;
}) {
  return (
    <div
      className="flex flex-col items-center gap-2 py-16 text-center"
      data-testid="no-access"
    >
      <p className="text-sm font-semibold">You don&apos;t have access to this</p>
      <p className="max-w-md text-sm text-muted-foreground">
        Your role ({role ?? "unknown"}) can&apos;t open this dashboard. Ask an admin
        if you need access.
      </p>
      <Link
        href={homeHref}
        className="mt-1 text-sm text-primary underline-offset-4 hover:underline"
      >
        {homeLabel}
      </Link>
    </div>
  );
}

/** A simple skeleton block for the loading state (KPI tiles + a chart row). */
export function DashboardSkeletonStrip() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  );
}
