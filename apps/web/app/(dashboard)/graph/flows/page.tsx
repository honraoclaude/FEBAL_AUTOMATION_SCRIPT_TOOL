"use client";

/**
 * Flows browse view (05-UI-SPEC §2) — /graph/flows. The flows table with risk badges,
 * default-sorted risk descending. States: loading · empty-no-flows ("No flows derived yet")
 * · empty-no-graph (shared "No knowledge graph yet") · populated · error (inline + Retry).
 *
 * We distinguish "no flows" from "no graph" via the graph summary: if the graph has no nodes
 * at all → no-graph state; if it has pages but mining produced no flows → no-flows state.
 */

import { useQuery } from "@tanstack/react-query";

import { getGraphSummary, listFlows } from "@/lib/api/kg";
import { GraphShell } from "@/components/graph/graph-shell";
import { FlowsTable } from "@/components/graph/flows-table";
import {
  ErrorState,
  MessageEmpty,
  NoGraphEmpty,
} from "@/components/graph/graph-states";

export default function GraphFlowsView() {
  const flowsQuery = useQuery({
    queryKey: ["kg", "flows"],
    queryFn: listFlows,
    retry: false,
  });
  const summaryQuery = useQuery({
    queryKey: ["kg", "graph"],
    queryFn: getGraphSummary,
    retry: false,
  });

  const flows = flowsQuery.data ?? [];
  const discovered = summaryQuery.data?.discovered ?? false;

  return (
    <GraphShell>
      {flowsQuery.isError ? (
        <ErrorState error={flowsQuery.error} onRetry={() => void flowsQuery.refetch()} />
      ) : !flowsQuery.isLoading && flows.length === 0 ? (
        discovered ? (
          <MessageEmpty
            heading="No flows derived yet"
            body="The graph has pages but no business flows were mined. Explore more of the app, or check back after a fuller exploration."
          />
        ) : (
          <NoGraphEmpty />
        )
      ) : (
        <FlowsTable flows={flows} isLoading={flowsQuery.isLoading} />
      )}
    </GraphShell>
  );
}
