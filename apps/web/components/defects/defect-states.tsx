"use client";

/**
 * Defect-queue state pieces (09-UI-SPEC §Copywriting) — the status badge + the inline error
 * state. Errors render INLINE in the content region, never as toasts (success toasts only for
 * applied/updated/rejected). Reachable Retry button (a11y).
 */

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type Status = "draft" | "applied" | "rejected";

const STATUS_TOKEN: Record<Status, string> = {
  draft: "var(--status-quarantine)",
  applied: "var(--status-pass)",
  rejected: "var(--status-neutral)",
};

const STATUS_WORD: Record<Status, string> = {
  draft: "Draft",
  applied: "Applied",
  rejected: "Rejected",
};

function isStatus(value: string): value is Status {
  return value === "draft" || value === "applied" || value === "rejected";
}

/**
 * Defect status badge (09-UI-SPEC §Color "Defect status → status-token mapping"). REUSES the
 * existing --status-* tokens. WCAG 1.4.1 — the WORD carries the meaning; the dot is aria-hidden.
 */
export function DefectStatusBadge({ status }: { status: string }) {
  const key: Status = isStatus(status) ? status : "draft";
  return (
    <Badge variant="outline" className="gap-1.5" aria-label={`Status: ${STATUS_WORD[key]}`}>
      <span
        aria-hidden
        className="size-1.5 rounded-full"
        style={{ backgroundColor: STATUS_TOKEN[key] }}
      />
      <span>{STATUS_WORD[key]}</span>
    </Badge>
  );
}

/** Inline error + Retry for a failed defects read (09-UI-SPEC error state — never a toast). */
export function DefectErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card py-16"
    >
      <p className="max-w-md text-center text-sm text-muted-foreground">
        Couldn&apos;t load defects. Try again — if it keeps failing, check that the API container
        is healthy (docker compose ps).
      </p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
