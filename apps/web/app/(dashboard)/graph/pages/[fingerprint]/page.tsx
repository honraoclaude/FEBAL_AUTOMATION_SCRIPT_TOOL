"use client";

/**
 * Page detail (05-UI-SPEC §4 Page detail) — /graph/pages/[fingerprint]. Breadcrumb + the
 * page title/url/fingerprint/freshness, then sections: Elements (each → element detail),
 * Forms, Navigates to (each outbound edge → target page detail, with the `via` control as a
 * mono caption). States: loading · populated · not-found · error (inline + Retry).
 *
 * useParams resolves the dynamic segment on the client (this is a client component driving
 * useQuery). Page-derived text renders through React's default escaping (T-05-10).
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { pageDetail } from "@/lib/api/kg";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/graph/breadcrumb";
import { ErrorState } from "@/components/graph/graph-states";

export default function PageDetailView() {
  const params = useParams<{ fingerprint: string }>();
  const fingerprint = decodeURIComponent(params.fingerprint);

  const query = useQuery({
    queryKey: ["kg", "page", fingerprint],
    queryFn: () => pageDetail(fingerprint),
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
              { label: "Pages", href: "/graph" },
            ]}
          />
          <p className="text-sm text-muted-foreground">No page found.</p>
        </div>
      );
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }

  const page = query.data!;

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumb
        crumbs={[
          { label: "Knowledge graph", href: "/graph" },
          { label: "Pages", href: "/graph" },
          { label: page.title || "(untitled)" },
        ]}
      />

      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold leading-tight">
          {page.title || "(untitled)"}
        </h1>
        <span className="font-mono text-sm text-muted-foreground">{page.url}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {page.fingerprint}
        </span>
        <span className="text-xs text-muted-foreground">
          First seen <span className="font-mono">{page.first_seen}</span> · Last verified{" "}
          <span className="font-mono">{page.last_verified}</span>
        </span>
      </div>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Elements</h2>
        {page.elements.length === 0 ? (
          <p className="text-sm text-muted-foreground">No elements on this page.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {page.elements.map((el) => (
              <li key={el.key} className="text-sm">
                <Link
                  href={`/graph/elements/${encodeURIComponent(el.key)}`}
                  className="text-primary hover:underline"
                >
                  {el.label || "(unlabeled)"}
                </Link>
                <span className="text-muted-foreground"> · {el.role}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Forms</h2>
        {page.forms.length === 0 ? (
          <p className="text-sm text-muted-foreground">No forms on this page.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {page.forms.map((form) => (
              <li key={form.key} className="font-mono text-sm">
                {form.key}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Navigates to</h2>
        {page.navigates_to.length === 0 ? (
          <p className="text-sm text-muted-foreground">No outbound navigation edges.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {page.navigates_to.map((nav) => (
              <li key={nav.to} className="text-sm">
                <Link
                  href={`/graph/pages/${encodeURIComponent(nav.to)}`}
                  className="text-primary hover:underline"
                >
                  Navigates to {nav.url || nav.to.slice(0, 8)}
                </Link>
                {nav.via ? (
                  <span className="font-mono text-xs text-muted-foreground">
                    {" "}
                    via {nav.via}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
