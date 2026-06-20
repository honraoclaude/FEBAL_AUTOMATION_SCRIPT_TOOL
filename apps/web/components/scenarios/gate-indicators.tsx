"use client";

/**
 * Per-Then no-vacuous gate indicators (06-UI-SPEC §2 "Assertion checks" + §Color, D-03).
 *
 * Renders the per-Then results STRICTLY from the server's `then_results` — green ONLY when the
 * server confirmed resolution; the client NEVER fabricates a "Resolved" (T-06-10). Each row
 * carries the WORD ("Resolved" / "Vacuous" / "Pending re-check") + an icon with an accessible
 * label + the mono kg_ref/reason as real text (WCAG 1.4.1 — never color alone). Offending Thens
 * are highlighted (left red border + muted-red tint).
 *
 * `pending` (an unsaved edit) shows every Then as muted "Pending re-check" — never green until
 * the gate actually runs server-side.
 */

import { CheckCircle2, Circle, XCircle } from "lucide-react";

import type { ThenRefResult } from "@/lib/api/scenarios";
import { Card } from "@/components/ui/card";

interface GateIndicatorsProps {
  results: ThenRefResult[];
  /** True when the editor is dirty/unsaved — show "Pending re-check" instead of stale results. */
  pending?: boolean;
}

export function GateIndicators({ results, pending = false }: GateIndicatorsProps) {
  const vacuousCount = results.filter((r) => !r.resolved).length;
  const allPass = !pending && results.length > 0 && vacuousCount === 0;

  return (
    <Card className="gap-3 p-4">
      <h2 className="text-sm font-semibold">Assertion checks</h2>

      {pending ? (
        <p className="text-sm text-muted-foreground">
          Edits aren&apos;t saved yet — save to re-run the assertion checks.
        </p>
      ) : results.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This scenario has no Then steps to assert.
        </p>
      ) : allPass ? (
        <p className="text-sm text-[var(--status-pass)]">
          All Then steps assert a graph-backed outcome.
        </p>
      ) : (
        <p className="text-sm text-[var(--status-fail)]">
          {vacuousCount} Then step(s) assert nothing recorded in the knowledge graph. Fix or
          remove them before approving.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {results.map((r, i) => {
          if (pending) {
            return (
              <li
                key={`${r.then_text}-${i}`}
                className="flex flex-col gap-0.5 rounded-md p-2"
              >
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Circle aria-label="Pending re-check" className="size-3.5" />
                  <span className="font-semibold">Pending re-check</span>
                </div>
                <span className="font-mono text-xs text-muted-foreground">
                  {r.then_text}
                </span>
              </li>
            );
          }
          if (r.resolved) {
            return (
              <li
                key={`${r.then_text}-${i}`}
                className="flex flex-col gap-0.5 rounded-md p-2"
              >
                <div className="flex items-center gap-1 text-sm text-[var(--status-pass)]">
                  <CheckCircle2 aria-label="Resolved" className="size-3.5" />
                  <span className="font-semibold">Resolved</span>
                </div>
                <span className="font-mono text-xs text-muted-foreground">
                  {r.then_text}
                </span>
                {r.kg_ref ? (
                  <span className="font-mono text-xs text-muted-foreground">
                    {r.kg_ref}
                  </span>
                ) : null}
              </li>
            );
          }
          return (
            <li
              key={`${r.then_text}-${i}`}
              className="flex flex-col gap-0.5 rounded-md border-l-2 border-l-[var(--status-fail)] bg-[var(--status-fail)]/10 p-2"
            >
              <div className="flex items-center gap-1 text-sm text-[var(--status-fail)]">
                <XCircle aria-label="Vacuous" className="size-3.5" />
                <span className="font-semibold">Vacuous</span>
              </div>
              <span className="font-mono text-xs text-muted-foreground">
                {r.then_text}
              </span>
              {r.reason ? (
                <span className="font-mono text-xs text-muted-foreground">{r.reason}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
