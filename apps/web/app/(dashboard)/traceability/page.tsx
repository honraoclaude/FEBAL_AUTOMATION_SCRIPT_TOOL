"use client";

/**
 * Traceability viewer (10-UI-SPEC §5, DASH-05) — /traceability.
 *
 * The entry picker (a type segment Flow · Scenario · Execution · Defect + a mono id input +
 * "Show chain", deep-linkable via ?type=&id=) feeds the chain-view. The chain renders flow ->
 * scenario -> script -> execution -> defect with honest "No {segment} linked." gaps; a graph-down
 * degrades the flow node to the honest note while the relational segments still render.
 *
 * State machine:
 *   resting           — before any lookup (the muted "Pick an artifact above…" caption)
 *   loading           — skeleton chain nodes after submit
 *   no-chain-for-id   — the looked-up id resolved NOTHING (every segment empty + no flow) -> the
 *                       honest "No chain found for this {type} id." (the backend returns 200, not 404)
 *   populated         — the chain (with honest missing segments)
 *   403 no-access / isError inline + Retry
 *
 * The viewer maps the picker's "Execution" label to the run_id entry param (run). Server-authoritative
 * throughout — no fabricated node.
 */

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import {
  getTraceability,
  type EntryType,
  type TraceabilityResponse,
} from "@/lib/api/traceability";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ChainView } from "@/components/dashboards/chain-view";
import {
  DashboardError,
  NoAccess,
} from "@/components/dashboards/dashboard-states";

/** The picker segments — label + the EntryType (Execution -> the run_id entry param). */
const SEGMENTS: { type: EntryType; label: string }[] = [
  { type: "flow", label: "Flow" },
  { type: "scenario", label: "Scenario" },
  { type: "run", label: "Execution" },
  { type: "defect", label: "Defect" },
];

function isValidType(t: string | null): t is EntryType {
  return t === "flow" || t === "scenario" || t === "run" || t === "defect";
}

/** A chain is "no chain found" when nothing resolved: no flow node AND every relational segment empty. */
function isEmptyChain(data: TraceabilityResponse): boolean {
  const hasFlow = Array.isArray(data.flow) ? data.flow.length > 0 : !!data.flow;
  return (
    !hasFlow &&
    data.scenarios.length === 0 &&
    data.scripts.length === 0 &&
    data.executions.length === 0 &&
    data.artifacts.length === 0 &&
    data.defects.length === 0
  );
}

function TraceabilityInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // The URL (?type=&id=) is the SINGLE source of truth for the SUBMITTED entry — no effect needed
  // to sync it (deep-link + back/forward just re-read the params). The form state below is only the
  // not-yet-submitted typing buffer, seeded once from the URL.
  const urlType = searchParams.get("type");
  const urlId = searchParams.get("id");
  const entry: { type: EntryType; id: string } | null =
    isValidType(urlType) && urlId ? { type: urlType, id: urlId } : null;

  // The form state (the segment + the id input) — initialized from the URL deep-link.
  const [formType, setFormType] = useState<EntryType>(
    isValidType(urlType) ? urlType : "flow",
  );
  const [formId, setFormId] = useState(urlId ?? "");

  const query = useQuery({
    queryKey: ["traceability", entry?.type, entry?.id],
    queryFn: () => getTraceability(entry!.type, entry!.id),
    enabled: !!entry,
    retry: false,
  });

  function submit() {
    const id = formId.trim();
    if (!id) return;
    // The URL drives the submitted entry; updating it re-renders with the new `entry` derived above.
    const qs = new URLSearchParams({ type: formType, id }).toString();
    router.replace(`/traceability?${qs}`);
  }

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const data = query.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Traceability</h1>
      </div>

      {/* Entry picker */}
      <section className="flex flex-col gap-3" aria-label="Find the chain for an artifact">
        <p className="text-sm font-semibold">Find the chain for…</p>
        <div className="flex flex-wrap items-center gap-2">
          <div
            className="flex gap-1"
            role="group"
            aria-label="Artifact type"
          >
            {SEGMENTS.map((s) => {
              const active = s.type === formType;
              return (
                <button
                  key={s.type}
                  type="button"
                  onClick={() => setFormType(s.type)}
                  aria-pressed={active}
                  className={`rounded-md border px-3 py-1.5 text-sm ${
                    active
                      ? "border-primary text-primary"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
          <Input
            value={formId}
            onChange={(e) => setFormId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder="Artifact id"
            aria-label="Artifact id"
            className="w-56 font-mono"
          />
          <Button onClick={submit} disabled={!formId.trim()}>
            Show chain
          </Button>
        </div>
      </section>

      {/* Chain region */}
      <section className="flex flex-col gap-4" aria-label="Chain">
        {!entry ? (
          <p
            className="py-16 text-center text-sm text-muted-foreground"
            data-testid="trace-resting"
          >
            Pick an artifact above to trace its flow → scenario → script → execution →
            defect chain.
          </p>
        ) : forbidden ? (
          <NoAccess role={undefined} />
        ) : query.isError ? (
          <DashboardError onRetry={() => void query.refetch()} />
        ) : query.isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : data && isEmptyChain(data) ? (
          <p
            className="py-16 text-center text-sm text-muted-foreground"
            data-testid="trace-no-chain"
          >
            No chain found for this {entry.type} id. Check the id, or pick a different
            artifact.
          </p>
        ) : data ? (
          <>
            <p className="text-sm font-semibold">Chain</p>
            <ChainView data={data} />
          </>
        ) : null}
      </section>
    </div>
  );
}

export default function TraceabilityPage() {
  // useSearchParams requires a Suspense boundary (Next App Router).
  return (
    <Suspense fallback={<Skeleton className="h-16 w-full" />}>
      <TraceabilityInner />
    </Suspense>
  );
}
