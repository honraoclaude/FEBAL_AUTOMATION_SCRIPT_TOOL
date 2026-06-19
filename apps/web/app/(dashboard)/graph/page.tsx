"use client";

/**
 * Pages browse view (05-UI-SPEC §1) — the /graph index. Renders the page header with the
 * honest coverage stat, the view switcher, and the Pages table. States: loading (skeleton
 * rows + skeleton coverage) · empty-no-graph ("No knowledge graph yet", coverage shows "Not
 * yet measured") · populated · error (inline + Retry) · graph-profile-down (neo4j copy +
 * Retry). Read-only: useQuery against the fetchers, no mutations, no auto-poll (manual Retry).
 */

import { useQuery } from "@tanstack/react-query";

import { getCoverage, listPages } from "@/lib/api/kg";
import { GraphShell } from "@/components/graph/graph-shell";
import { PagesTable } from "@/components/graph/pages-table";
import { ErrorState, NoGraphEmpty } from "@/components/graph/graph-states";

export default function GraphPagesView() {
  const pagesQuery = useQuery({
    queryKey: ["kg", "pages"],
    queryFn: listPages,
    retry: false,
  });
  const coverageQuery = useQuery({
    queryKey: ["kg", "coverage"],
    queryFn: getCoverage,
    retry: false,
  });

  const pages = pagesQuery.data ?? [];

  return (
    <GraphShell
      showCoverage
      coverage={coverageQuery.data}
      coverageLoading={coverageQuery.isLoading}
    >
      {pagesQuery.isError ? (
        <ErrorState
          error={pagesQuery.error}
          onRetry={() => void pagesQuery.refetch()}
        />
      ) : !pagesQuery.isLoading && pages.length === 0 ? (
        <NoGraphEmpty />
      ) : (
        <PagesTable pages={pages} isLoading={pagesQuery.isLoading} />
      )}
    </GraphShell>
  );
}
