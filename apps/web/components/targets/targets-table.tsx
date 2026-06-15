"use client";

import { MoreHorizontal } from "lucide-react";

import type { TargetResponse } from "@/lib/api/targets";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
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

/**
 * Target registry table (01-UI-SPEC §3). Renders all four states: loading
 * (skeleton rows), empty (contract copy + Register CTA), populated, and
 * inactive (muted row + Inactive badge). All target text is rendered through
 * React's default escaping only — no dangerouslySetInnerHTML anywhere (threat
 * T-01-24: XSS via target names/URLs).
 */

interface TargetsTableProps {
  targets: TargetResponse[];
  isLoading: boolean;
  onRegister: () => void;
  onExplore: (target: TargetResponse) => void;
  onEdit: (target: TargetResponse) => void;
  onDeactivate: (target: TargetResponse) => void;
  onReactivate: (target: TargetResponse) => void;
}

/** Active: green-dot badge (--status-pass); Inactive: muted (--status-neutral). */
function StatusBadge({ isActive }: { isActive: boolean }) {
  if (isActive) {
    return (
      <Badge variant="outline" className="gap-1.5">
        <span
          aria-hidden
          className="size-1.5 rounded-full bg-[var(--status-pass)]"
        />
        Active
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="gap-1.5 text-[var(--status-neutral)]"
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full bg-[var(--status-neutral)]"
      />
      Inactive
    </Badge>
  );
}

/** Amber-outline "Sandbox" badge (--status-quarantine) when sandbox is on. */
function SandboxBadge({ sandbox }: { sandbox: boolean }) {
  if (!sandbox) {
    return null;
  }
  return (
    <Badge
      variant="outline"
      className="border-[var(--status-quarantine)] text-[var(--status-quarantine)]"
    >
      Sandbox
    </Badge>
  );
}

function EmptyState({ onRegister }: { onRegister: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
      <p className="text-sm font-semibold">No target applications yet</p>
      <p className="text-sm text-muted-foreground">
        Register a target application to give the platform something to explore.
      </p>
      <Button className="mt-2" onClick={onRegister}>
        Register target
      </Button>
    </div>
  );
}

function LoadingRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <TableRow key={i}>
          <TableCell>
            <Skeleton className="h-4 w-32" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-48" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-16" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-16" />
          </TableCell>
          <TableCell>
            <Skeleton className="ml-auto h-8 w-8" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

export function TargetsTable({
  targets,
  isLoading,
  onRegister,
  onExplore,
  onEdit,
  onDeactivate,
  onReactivate,
}: TargetsTableProps) {
  // Empty state replaces the table entirely (only once we know the list is empty).
  if (!isLoading && targets.length === 0) {
    return <EmptyState onRegister={onRegister} />;
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            {/* Caption role: 12px column headers (UI-SPEC typography). */}
            <TableHead className="text-xs font-normal">Name</TableHead>
            <TableHead className="text-xs font-normal">Base URL</TableHead>
            <TableHead className="text-xs font-normal">Sandbox</TableHead>
            <TableHead className="text-xs font-normal">Status</TableHead>
            <TableHead className="w-12 text-right text-xs font-normal">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <LoadingRows />
          ) : (
            targets.map((target) => (
              <TableRow
                key={target.id}
                // Inactive rows: entire row text muted (UI-SPEC §3 inactive state).
                className={cn(!target.is_active && "text-muted-foreground")}
              >
                <TableCell className="font-medium">{target.name}</TableCell>
                {/* Base URL: Geist Mono at body size (UI-SPEC monospace rule). */}
                <TableCell className="font-mono text-sm">
                  {target.base_url}
                </TableCell>
                <TableCell>
                  <SandboxBadge sandbox={target.sandbox} />
                </TableCell>
                <TableCell>
                  <StatusBadge isActive={target.is_active} />
                </TableCell>
                <TableCell className="text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        aria-label={`Actions for ${target.name}`}
                      >
                        <MoreHorizontal className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {/* "Explore" above "Edit"; disabled + tooltip when inactive
                          (UI-SPEC §3 shared additions). */}
                      {target.is_active ? (
                        <DropdownMenuItem onSelect={() => onExplore(target)}>
                          Explore
                        </DropdownMenuItem>
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            {/* A disabled item can't host a tooltip trigger directly; wrap a
                                focusable span so the tooltip + disabled affordance both work. */}
                            <span>
                              <DropdownMenuItem disabled>
                                Explore
                              </DropdownMenuItem>
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            Activate this target to explore it
                          </TooltipContent>
                        </Tooltip>
                      )}
                      <DropdownMenuItem onSelect={() => onEdit(target)}>
                        Edit
                      </DropdownMenuItem>
                      {target.is_active ? (
                        <DropdownMenuItem
                          variant="destructive"
                          onSelect={() => onDeactivate(target)}
                        >
                          Deactivate
                        </DropdownMenuItem>
                      ) : (
                        <DropdownMenuItem
                          onSelect={() => onReactivate(target)}
                        >
                          Reactivate
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
