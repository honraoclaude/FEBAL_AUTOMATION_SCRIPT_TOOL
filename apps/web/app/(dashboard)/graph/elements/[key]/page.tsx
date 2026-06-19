"use client";

/**
 * Element detail (05-UI-SPEC §4 Element detail) — /graph/elements/[key]. Breadcrumb + the
 * element label + role + host page (link), then sections: Locator chain (the prioritized
 * chain as an ordered list — data-testid → aria-label → role → text → xpath, each row a mono
 * priority label → mono value, the winning/top locator flagged) and Locator history (prior
 * step-stamped locator values, so the user sees how a locator changed across runs — KG-05).
 * States: loading · populated · not-found · error (inline + Retry).
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { elementDetail } from "@/lib/api/kg";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/graph/breadcrumb";
import { ErrorState } from "@/components/graph/graph-states";

export default function ElementDetailView() {
  const params = useParams<{ key: string }>();
  const key = decodeURIComponent(params.key);

  const query = useQuery({
    queryKey: ["kg", "element", key],
    queryFn: () => elementDetail(key),
    retry: false,
  });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <div className="flex flex-col gap-4">
          <Breadcrumb
            crumbs={[
              { label: "Knowledge graph", href: "/graph" },
              { label: "Element repository", href: "/graph/elements" },
            ]}
          />
          <p className="text-sm text-muted-foreground">No element found.</p>
        </div>
      );
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }

  const element = query.data!;

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumb
        crumbs={[
          { label: "Knowledge graph", href: "/graph" },
          { label: "Element repository", href: "/graph/elements" },
          { label: element.label || "(unlabeled)" },
        ]}
      />

      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold leading-tight">
          {element.label || "(unlabeled)"}
        </h1>
        <span className="text-sm text-muted-foreground">{element.role}</span>
        {element.page_fingerprint ? (
          <Link
            href={`/graph/pages/${encodeURIComponent(element.page_fingerprint)}`}
            className="text-sm text-primary hover:underline"
          >
            {element.page_url || element.page_fingerprint.slice(0, 8)}
          </Link>
        ) : null}
      </div>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Locator chain</h2>
        {element.locator_chain.length === 0 ? (
          <p className="text-sm text-muted-foreground">No locator chain recorded.</p>
        ) : (
          <ol className="flex flex-col gap-1">
            {element.locator_chain.map((loc, i) => (
              <li
                key={`${loc.strategy}-${i}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="font-mono text-muted-foreground">{loc.strategy}</span>
                <span className="font-mono">{loc.value ?? loc.name ?? ""}</span>
                {i === 0 ? (
                  <Badge variant="outline" className="text-xs">
                    Top priority
                  </Badge>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Card>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Locator history</h2>
        {element.locator_history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No locator history recorded.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {element.locator_history.map((entry, i) => (
              <li key={`hist-${entry.step ?? i}`} className="text-sm">
                <span className="text-xs text-muted-foreground">
                  Step <span className="font-mono">{entry.step ?? "—"}</span>
                </span>
                <ul className="ml-4 flex flex-col gap-0.5">
                  {entry.chain.map((loc, j) => (
                    <li key={`${loc.strategy}-${j}`} className="flex gap-2">
                      <span className="font-mono text-muted-foreground">
                        {loc.strategy}
                      </span>
                      <span className="font-mono">{loc.value ?? loc.name ?? ""}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
