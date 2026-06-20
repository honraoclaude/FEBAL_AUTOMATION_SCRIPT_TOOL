"use client";

/**
 * Scenario-queue state pieces (06-UI-SPEC §Copywriting error states). Errors render INLINE in
 * the content region — never as toasts. The copy is scenario-specific (the reused graph error
 * state carries graph copy; this surface gets its own). Reachable Retry button (a11y).
 */

import { Button } from "@/components/ui/button";

/** Inline error + Retry for a failed scenarios read (06-UI-SPEC error state). */
export function ScenarioErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card py-16"
    >
      <p className="max-w-md text-center text-sm text-muted-foreground">
        Couldn&apos;t load scenarios. Try again — if it keeps failing, check that the API
        container is healthy (docker compose ps).
      </p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
