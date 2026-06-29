"use client";

/**
 * Traceability chain view (10-UI-SPEC §5, DASH-05) — the ordered lifecycle chain rendered as an
 * <ol> so the Flow -> Scenario -> Script -> Execution -> Defect order is conveyed STRUCTURALLY
 * (a11y). Each present segment is a small secondary tile with its Label + the artifact's mono id +
 * an accent drill-in link to the existing detail page:
 *
 *   Flow      -> /graph/flows/{flow_id}
 *   Scenario  -> /scenarios/{id}
 *   Script    -> (convention-derived path; no detail page — shown as a mono path, no link)
 *   Execution -> /executions/{run_id}
 *   Defect    -> /defects/{id}
 *
 * A MISSING segment renders a MUTED "No {segment} linked." node — an HONEST gap, never a fabricated
 * node or a dead link (T-10-30). A segment that fans out (multiple scenarios / executions / defects)
 * renders the SET. The flow segment, when the graph is down, renders the honest `flowNote` instead
 * of a fabricated flow node (the relational segments still render).
 *
 * Every node renders STRICTLY from the server payload — green/present vs muted/missing comes only
 * from what the server reported.
 */

import Link from "next/link";

import {
  flowSegments,
  type TraceabilityResponse,
} from "@/lib/api/traceability";

/** A present chain node: a Label + a mono id + (optional) an accent drill-in link. */
function ChainNode({
  label,
  id,
  href,
  meta,
}: {
  label: string;
  id: string;
  href?: string;
  meta?: string;
}) {
  return (
    <li
      className="rounded-lg border border-border bg-card p-4"
      data-testid="chain-node"
      data-segment={label}
    >
      <p className="text-sm font-semibold">{label}</p>
      <div className="mt-1 flex items-baseline gap-2">
        {href ? (
          <Link
            href={href}
            className="font-mono text-xs text-primary underline-offset-4 hover:underline"
          >
            {id}
          </Link>
        ) : (
          <span className="font-mono text-xs">{id}</span>
        )}
        {meta ? (
          <span className="text-xs text-muted-foreground">{meta}</span>
        ) : null}
      </div>
    </li>
  );
}

/** A muted honest "No {segment} linked." gap node — never a fabricated node or dead link. */
function MissingNode({ label, note }: { label: string; note?: string }) {
  return (
    <li
      className="rounded-lg border border-dashed border-border p-4"
      data-testid="chain-gap"
      data-segment={label}
    >
      <p className="text-sm font-semibold text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {note ?? `No ${label.toLowerCase()} linked.`}
      </p>
    </li>
  );
}

export function ChainView({ data }: { data: TraceabilityResponse }) {
  const flows = flowSegments(data);

  return (
    <ol className="flex flex-col gap-2" aria-label="Traceability chain">
      {/* Flow — graph-down degrades to the honest flow_note, never a fabricated node. */}
      {flows.length > 0 ? (
        flows.map((f, i) => (
          <ChainNode
            key={`flow:${f.flow_id ?? i}`}
            label="Flow"
            id={f.flow_id ?? "—"}
            href={f.flow_id ? `/graph/flows/${f.flow_id}` : undefined}
            meta={f.name ?? undefined}
          />
        ))
      ) : (
        <MissingNode label="Flow" note={data.flow_note ?? undefined} />
      )}

      {/* Scenario (fan-out: render the set). */}
      {data.scenarios.length > 0 ? (
        data.scenarios.map((s) => (
          <ChainNode
            key={`scenario:${s.id}`}
            label="Scenario"
            id={String(s.id)}
            href={`/scenarios/${s.id}`}
            meta={s.feature_name}
          />
        ))
      ) : (
        <MissingNode label="Scenario" />
      )}

      {/* Script — convention-derived path (no detail page; the mono path, no link). */}
      {data.scripts.length > 0 ? (
        data.scripts.map((sc) => (
          <ChainNode key={`script:${sc.run_id}`} label="Script" id={sc.path} />
        ))
      ) : (
        <MissingNode label="Script" />
      )}

      {/* Execution (fan-out). */}
      {data.executions.length > 0 ? (
        data.executions.map((e) => (
          <ChainNode
            key={`exec:${e.run_id}:${e.flow_id}`}
            label="Execution"
            id={e.run_id}
            href={`/executions/${e.run_id}`}
            meta={e.verdict}
          />
        ))
      ) : (
        <MissingNode label="Execution" />
      )}

      {/* Defect (fan-out). */}
      {data.defects.length > 0 ? (
        data.defects.map((d) => (
          <ChainNode
            key={`defect:${d.id}`}
            label="Defect"
            id={`#${d.id}`}
            href={`/defects/${d.id}`}
            meta={d.jira_key ?? d.classification}
          />
        ))
      ) : (
        <MissingNode label="Defect" />
      )}
    </ol>
  );
}
