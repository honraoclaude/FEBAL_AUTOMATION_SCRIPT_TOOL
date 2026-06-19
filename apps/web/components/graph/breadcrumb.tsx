"use client";

/**
 * Drill-in breadcrumb (05-UI-SPEC: "Knowledge graph / Pages / {title}"). Each segment is a
 * link except the current, which is marked aria-current="page". Rendered as an
 * aria-label="Breadcrumb" nav (a11y).
 */

import Link from "next/link";

export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumb({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={`${crumb.label}-${i}`}>
            {crumb.href && !isLast ? (
              <Link href={crumb.href} className="text-primary hover:underline">
                {crumb.label}
              </Link>
            ) : (
              <span aria-current={isLast ? "page" : undefined}>{crumb.label}</span>
            )}
            {isLast ? null : <span className="px-1">/</span>}
          </span>
        );
      })}
    </nav>
  );
}
