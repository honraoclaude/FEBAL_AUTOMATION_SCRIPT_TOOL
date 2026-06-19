"use client";

/**
 * Pages browse table (05-UI-SPEC §1 Pages view). Columns: Page · URL · Fingerprint ·
 * Elements · First seen · Last verified. The page title row links to page detail; the
 * element count is a drill-in link to the page-detail Elements section. URL/fingerprint
 * are mono (truncated with a title for the full value); timestamps are caption mono; stale
 * rows render muted with a Clock icon + tooltip (text, not color-only). All page-derived
 * text renders through React's default escaping only — no dangerouslySetInnerHTML (T-05-10).
 */

import Link from "next/link";
import { Clock } from "lucide-react";

import type { Page } from "@/lib/api/kg";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isStale, LoadingRows } from "@/components/graph/graph-states";

interface PagesTableProps {
  pages: Page[];
  isLoading: boolean;
}

function StaleMark({ lastVerified }: { lastVerified: string | null }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1" tabIndex={0}>
            <Clock aria-hidden className="size-3" />
            <span className="font-mono text-xs">{lastVerified}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          Last verified {lastVerified} — not seen in the most recent exploration.
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function PagesTable({ pages, isLoading }: PagesTableProps) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="text-xs font-normal">Page</TableHead>
            <TableHead scope="col" className="text-xs font-normal">URL</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Fingerprint</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Elements</TableHead>
            <TableHead scope="col" className="text-xs font-normal">First seen</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Last verified</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <LoadingRows columns={6} />
          ) : (
            pages.map((page) => {
              const stale = isStale(page.last_verified);
              const href = `/graph/pages/${encodeURIComponent(page.fingerprint)}`;
              return (
                <TableRow
                  key={page.fingerprint}
                  className={cn(stale && "text-muted-foreground")}
                >
                  <TableCell className="font-medium">
                    <Link href={href} className="text-primary hover:underline">
                      {page.title || "(untitled)"}
                    </Link>
                  </TableCell>
                  <TableCell
                    className="max-w-[16rem] truncate font-mono text-sm"
                    title={page.url ?? undefined}
                  >
                    {page.url}
                  </TableCell>
                  <TableCell
                    className="font-mono text-sm"
                    title={page.fingerprint}
                  >
                    {page.fingerprint.slice(0, 8)}
                  </TableCell>
                  <TableCell>
                    <Link href={href} className="text-primary hover:underline">
                      {page.element_count} elements
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {page.first_seen}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {stale ? (
                      <StaleMark lastVerified={page.last_verified} />
                    ) : (
                      <span className="font-mono">{page.last_verified}</span>
                    )}
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
