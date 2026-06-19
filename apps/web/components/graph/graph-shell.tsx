"use client";

/**
 * KG-browse layout shell (05-UI-SPEC Layout shell): the page header ("Knowledge graph")
 * with the coverage stat (Pages view only), and the deep-linkable view switcher
 * ("Pages" · "Flows" · "Element repository") as accent-underlined route links. The active
 * segment carries the accent indicator via pathname matching. Composition over existing
 * tokens — NOT a new tabs registry block (UI-SPEC: composition is sufficient).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { Coverage } from "@/lib/api/kg";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const SEGMENTS = [
  { label: "Pages", href: "/graph" },
  { label: "Flows", href: "/graph/flows" },
  { label: "Element repository", href: "/graph/elements" },
] as const;

/** The honest coverage stat card (UI-SPEC): "Not yet measured" when measured=false. */
export function CoverageStat({
  coverage,
  isLoading,
}: {
  coverage?: Coverage;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card className="min-w-[14rem] gap-1 p-4">
        <span className="text-xs text-muted-foreground">Coverage</span>
        <Skeleton className="h-6 w-24" />
      </Card>
    );
  }

  const measured = coverage?.measured ?? false;
  const ariaLabel = measured
    ? `Coverage: ${coverage?.coverage_percent} percent, ${coverage?.screens_covered} of ${coverage?.screens_total} ground-truth pages discovered`
    : "Coverage: not yet measured";

  return (
    <Card className="min-w-[14rem] gap-1 p-4" aria-label={ariaLabel}>
      <span className="text-xs text-muted-foreground">Coverage</span>
      {measured ? (
        <>
          <span className="font-mono text-sm font-semibold">
            {coverage?.coverage_percent.toFixed(1)}%
          </span>
          <span className="text-xs text-muted-foreground">
            {coverage?.screens_covered} of {coverage?.screens_total} ground-truth pages
            discovered — measured against the hand-labeled SauceDemo graph.
          </span>
        </>
      ) : (
        <>
          <span className="text-sm font-semibold text-muted-foreground">
            Not yet measured
          </span>
          <span className="text-xs text-muted-foreground">
            Run an exploration to measure coverage against the ground-truth graph.
          </span>
        </>
      )}
    </Card>
  );
}

/** The page header + view switcher. `coverage` is rendered only on the Pages view. */
export function GraphShell({
  children,
  coverage,
  coverageLoading,
  showCoverage = false,
}: {
  children: React.ReactNode;
  coverage?: Coverage;
  coverageLoading?: boolean;
  showCoverage?: boolean;
}) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <h1 className="text-xl font-semibold leading-tight">Knowledge graph</h1>
        {showCoverage ? (
          <CoverageStat coverage={coverage} isLoading={coverageLoading ?? false} />
        ) : null}
      </div>

      <nav aria-label="Knowledge graph views" className="flex gap-4 border-b border-border">
        {SEGMENTS.map((seg) => {
          // Pages is the exact "/graph"; flows/elements match by startsWith.
          const active =
            seg.href === "/graph"
              ? pathname === "/graph"
              : pathname.startsWith(seg.href);
          return (
            <Link
              key={seg.href}
              href={seg.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "-mb-px border-b-2 pb-2 text-sm",
                active
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {seg.label}
            </Link>
          );
        })}
      </nav>

      <div>{children}</div>
    </div>
  );
}
