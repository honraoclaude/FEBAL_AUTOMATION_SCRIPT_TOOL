"use client";

/**
 * Element Repository browse view (05-UI-SPEC §3) — /graph/elements. The elements table with
 * the prioritized locator chain. States: loading · empty-no-elements ("No elements captured
 * yet") · empty-no-graph (shared) · populated · error (inline + Retry).
 */

import { useQuery } from "@tanstack/react-query";

import { getGraphSummary, listElements } from "@/lib/api/kg";
import { GraphShell } from "@/components/graph/graph-shell";
import { ElementsTable } from "@/components/graph/elements-table";
import {
  ErrorState,
  MessageEmpty,
  NoGraphEmpty,
} from "@/components/graph/graph-states";

export default function GraphElementsView() {
  const elementsQuery = useQuery({
    queryKey: ["kg", "elements"],
    queryFn: listElements,
    retry: false,
  });
  const summaryQuery = useQuery({
    queryKey: ["kg", "graph"],
    queryFn: getGraphSummary,
    retry: false,
  });

  const elements = elementsQuery.data ?? [];
  const discovered = summaryQuery.data?.discovered ?? false;

  return (
    <GraphShell>
      {elementsQuery.isError ? (
        <ErrorState
          error={elementsQuery.error}
          onRetry={() => void elementsQuery.refetch()}
        />
      ) : !elementsQuery.isLoading && elements.length === 0 ? (
        discovered ? (
          <MessageEmpty
            heading="No elements captured yet"
            body="No interactive elements were recorded. Run a fuller exploration to populate the element repository."
          />
        ) : (
          <NoGraphEmpty />
        )
      ) : (
        <ElementsTable elements={elements} isLoading={elementsQuery.isLoading} />
      )}
    </GraphShell>
  );
}
