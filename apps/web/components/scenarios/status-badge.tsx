"use client";

/**
 * Scenario status badge (06-UI-SPEC §Color "Scenario status → status-token mapping").
 *
 * REUSES the existing `--status-*` tokens (no new colors): Draft → amber (--status-quarantine),
 * Approved → green (--status-pass), Rejected → muted (--status-neutral). WCAG 1.4.1 — the badge
 * carries the WORD + a colored dot (the dot is aria-hidden; the text carries the meaning).
 */

import { Badge } from "@/components/ui/badge";

type Status = "draft" | "approved" | "rejected";

const STATUS_TOKEN: Record<Status, string> = {
  draft: "var(--status-quarantine)",
  approved: "var(--status-pass)",
  rejected: "var(--status-neutral)",
};

const STATUS_WORD: Record<Status, string> = {
  draft: "Draft",
  approved: "Approved",
  rejected: "Rejected",
};

function isStatus(value: string): value is Status {
  return value === "draft" || value === "approved" || value === "rejected";
}

export function StatusBadge({ status }: { status: string }) {
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
