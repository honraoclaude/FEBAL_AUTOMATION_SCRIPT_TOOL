"use client";

/**
 * Search UI (10-UI-SPEC §6, DASH-06) — /search.
 *
 * A labeled <input type="search"> (the placeholder + an accent "Search" submit; Enter submits),
 * deep-linkable via ?q=, with an optional index segment (All · Executions · Failures · Logs,
 * default All). The results region (role="region" aria-label="Search results") shows the
 * "{n} results for "{q}"" count (role="status" aria-live="polite").
 *
 * State machine:
 *   resting             — before a query (the muted centered caption)
 *   loading             — skeleton result cards
 *   no-results          — the echoed query (never a fabricated hit)
 *   populated           — the typed, highlighted hit list
 *   search-unavailable  — the honest ES-503 state (the "Search is unavailable…" + Retry) —
 *                         DISTINGUISHED from no-results (NEVER an empty list pretending zero hits)
 *   403 no-access / isError inline + Retry
 *
 * The URL (?q=&index=) is the SINGLE source of truth for the SUBMITTED query — no effect needed.
 */

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { search, type SearchIndex } from "@/lib/api/search";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { SearchResults } from "@/components/dashboards/search-results";
import {
  DashboardError,
  NoAccess,
} from "@/components/dashboards/dashboard-states";

const INDEXES: { value: SearchIndex; label: string }[] = [
  { value: "all", label: "All" },
  { value: "executions", label: "Executions" },
  { value: "failures", label: "Failures" },
  { value: "logs", label: "Logs" },
];

function isValidIndex(v: string | null): v is SearchIndex {
  return v === "all" || v === "executions" || v === "failures" || v === "logs";
}

/** The honest "search unavailable" 503 state — distinct from no-results (never a fake empty list). */
function SearchUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16"
      role="alert"
      data-testid="search-unavailable"
    >
      <p className="text-sm font-semibold">Search is unavailable</p>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        It runs under the <code className="font-mono">search</code> profile — start it
        with{" "}
        <code className="font-mono">docker compose --profile search up -d</code>, then
        search again.
      </p>
      <Button variant="outline" className="mt-1" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

function SearchInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const urlQ = searchParams.get("q");
  const urlIndex = searchParams.get("index");
  const submittedQ = urlQ?.trim() ? urlQ : null;
  const submittedIndex: SearchIndex = isValidIndex(urlIndex) ? urlIndex : "all";

  // The form state (the typing buffer + the index segment), seeded from the URL deep-link.
  const [formQ, setFormQ] = useState(urlQ ?? "");
  const [formIndex, setFormIndex] = useState<SearchIndex>(submittedIndex);

  const query = useQuery({
    queryKey: ["search", submittedQ, submittedIndex],
    queryFn: () => search(submittedQ!, submittedIndex),
    enabled: !!submittedQ,
    retry: false,
  });

  function submit() {
    const q = formQ.trim();
    if (!q) return;
    const params = new URLSearchParams({ q });
    if (formIndex !== "all") params.set("index", formIndex);
    router.replace(`/search?${params.toString()}`);
  }

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const unavailable = query.error instanceof ApiError && query.error.status === 503;
  const data = query.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Search</h1>
      </div>

      {/* Query box */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="search"
            value={formQ}
            onChange={(e) => setFormQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder="Search executions, failures, and logs…"
            aria-label="Search executions, failures, and logs"
            className="flex-1 min-w-64"
          />
          <Button onClick={submit} disabled={!formQ.trim()}>
            Search
          </Button>
        </div>
        <div className="flex gap-1" role="group" aria-label="Search scope">
          {INDEXES.map((idx) => {
            const active = idx.value === formIndex;
            return (
              <button
                key={idx.value}
                type="button"
                onClick={() => setFormIndex(idx.value)}
                aria-pressed={active}
                className={`rounded-md border px-3 py-1.5 text-sm ${
                  active
                    ? "border-primary text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {idx.label}
              </button>
            );
          })}
        </div>
      </section>

      {/* Results region */}
      <section
        role="region"
        aria-label="Search results"
        className="flex flex-col gap-4"
      >
        {!submittedQ ? (
          <p
            className="py-16 text-center text-sm text-muted-foreground"
            data-testid="search-resting"
          >
            Search executions, failures, and logs. Type a query above to start.
          </p>
        ) : forbidden ? (
          <NoAccess role={undefined} />
        ) : unavailable ? (
          <SearchUnavailable onRetry={() => void query.refetch()} />
        ) : query.isError ? (
          <DashboardError onRetry={() => void query.refetch()} />
        ) : query.isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : data ? (
          <>
            <p
              className="font-mono text-xs text-muted-foreground"
              role="status"
              aria-live="polite"
            >
              {data.count} results for &quot;{data.query}&quot;
            </p>
            {data.hits.length === 0 ? (
              <div
                className="flex flex-col items-center gap-2 py-16"
                data-testid="search-no-results"
              >
                <p className="text-sm font-semibold">No results</p>
                <p className="max-w-md text-center text-sm text-muted-foreground">
                  Nothing matched &quot;{data.query}&quot;. Try fewer or different
                  words.
                </p>
              </div>
            ) : (
              <SearchResults hits={data.hits} />
            )}
          </>
        ) : null}
      </section>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<Skeleton className="h-16 w-full" />}>
      <SearchInner />
    </Suspense>
  );
}
