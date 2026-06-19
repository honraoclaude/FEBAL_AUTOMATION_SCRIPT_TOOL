"use client";

/**
 * Flows browse table (05-UI-SPEC §2 Flows view). Columns: Flow · Category · Risk · Steps ·
 * First seen. The flow name row links to flow detail; Steps is a drill-in link to the
 * flow-detail Steps section. The Risk column is the RiskBadge (dot + mono score + tier word,
 * never color alone). Default sort: risk DESCENDING (highest-risk first — the actionable
 * order); the Risk header carries aria-sort="descending". Page-derived names render through
 * React's default escaping only (T-05-10).
 */

import Link from "next/link";

import type { Flow } from "@/lib/api/kg";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RiskBadge } from "@/components/graph/risk-badge";
import { LoadingRows } from "@/components/graph/graph-states";

interface FlowsTableProps {
  flows: Flow[];
  isLoading: boolean;
}

export function FlowsTable({ flows, isLoading }: FlowsTableProps) {
  // Default sort: risk descending (UI-SPEC). The API already sorts, but re-sort defensively.
  const sorted = [...flows].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <div className="rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="text-xs font-normal">Flow</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Category</TableHead>
            <TableHead
              scope="col"
              aria-sort="descending"
              className="text-xs font-normal"
            >
              Risk
            </TableHead>
            <TableHead scope="col" className="text-xs font-normal">Steps</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <LoadingRows columns={4} />
          ) : (
            sorted.map((flow) => {
              const href = `/graph/flows/${encodeURIComponent(flow.flow_id)}`;
              return (
                <TableRow key={flow.flow_id}>
                  <TableCell className="font-medium">
                    <Link href={href} className="text-primary hover:underline">
                      {flow.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {flow.category ? (
                      flow.category
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <RiskBadge
                      score={flow.risk_score}
                      tier={flow.risk_tier}
                      signals={flow.signals as Record<string, unknown>}
                    />
                  </TableCell>
                  <TableCell>
                    <Link href={href} className="text-primary hover:underline">
                      {flow.step_count} steps
                    </Link>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );
}
