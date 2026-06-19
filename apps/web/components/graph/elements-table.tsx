"use client";

/**
 * Element Repository table (05-UI-SPEC §3 Element repository view). Columns: Element · Role ·
 * Page · Locator (top priority) · Last verified. The element label row links to element
 * detail; the host Page links to that page's detail. The locator column shows the
 * highest-priority chain entry (mono, truncated with a title). Stale rows render muted with a
 * Clock icon + tooltip. Page-derived text renders through React's default escaping (T-05-10).
 */

import Link from "next/link";
import { Clock } from "lucide-react";

import type { Element } from "@/lib/api/kg";
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

interface ElementsTableProps {
  elements: Element[];
  isLoading: boolean;
}

/** The highest-priority locator value (the first chain entry — data-testid first). */
function topLocator(element: Element): string {
  const first = element.locator_chain[0];
  if (!first) {
    return "";
  }
  return first.value ? `${first.strategy}=${first.value}` : first.strategy;
}

export function ElementsTable({ elements, isLoading }: ElementsTableProps) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="text-xs font-normal">Element</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Role</TableHead>
            <TableHead scope="col" className="text-xs font-normal">Page</TableHead>
            <TableHead scope="col" className="text-xs font-normal">
              Locator (top priority)
            </TableHead>
            <TableHead scope="col" className="text-xs font-normal">Last verified</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <LoadingRows columns={5} />
          ) : (
            elements.map((element) => {
              const stale = isStale(element.last_verified);
              const locator = topLocator(element);
              return (
                <TableRow
                  key={element.key}
                  className={cn(stale && "text-muted-foreground")}
                >
                  <TableCell className="font-medium">
                    <Link
                      href={`/graph/elements/${encodeURIComponent(element.key)}`}
                      className="text-primary hover:underline"
                    >
                      {element.label || "(unlabeled)"}
                    </Link>
                  </TableCell>
                  <TableCell>{element.role}</TableCell>
                  <TableCell>
                    {element.page_fingerprint ? (
                      <Link
                        href={`/graph/pages/${encodeURIComponent(element.page_fingerprint)}`}
                        className="text-primary hover:underline"
                      >
                        {element.page_url || element.page_fingerprint.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell
                    className="max-w-[18rem] truncate font-mono text-sm"
                    title={locator}
                  >
                    {locator}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {stale ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="inline-flex items-center gap-1" tabIndex={0}>
                              <Clock aria-hidden className="size-3" />
                              <span className="font-mono">{element.last_verified}</span>
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            Last verified {element.last_verified} — not seen in the most
                            recent exploration.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : (
                      <span className="font-mono">{element.last_verified}</span>
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
