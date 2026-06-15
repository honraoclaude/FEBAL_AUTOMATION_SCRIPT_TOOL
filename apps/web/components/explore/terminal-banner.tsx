/**
 * Terminal / stream-lost banner (04-UI-SPEC Copywriting Contract) — plain composition over
 * card + existing tokens. One variant per terminal UI state with the EXACT spec copy:
 *   complete (green) · failed (red) · budget (amber) · stopped (neutral) · stream-lost.
 * Errors render INLINE here (never a toast). The complete variant shows a "View knowledge
 * graph" link that degrades gracefully (Phase-5 placeholder). stream-lost offers "Reload".
 */

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type BannerVariant =
  | "complete"
  | "failed"
  | "budget"
  | "stopped"
  | "stream-lost";

interface TerminalBannerProps {
  variant: BannerVariant;
  pagesFound?: number;
  actionsTaken?: number;
  error?: string;
  onReload?: () => void;
}

/** Left accent border token per variant (budget = amber designed stop, not red). */
const ACCENT: Record<BannerVariant, string> = {
  complete: "var(--status-pass)",
  failed: "var(--status-fail)",
  budget: "var(--status-quarantine)",
  stopped: "var(--status-neutral)",
  "stream-lost": "var(--status-quarantine)",
};

export function TerminalBanner({
  variant,
  pagesFound = 0,
  actionsTaken = 0,
  error,
  onReload,
}: TerminalBannerProps) {
  return (
    <Card
      role="alert"
      data-variant={variant}
      data-testid="terminal-banner"
      className={cn("gap-2 border-l-2 p-4")}
      style={{ borderLeftColor: ACCENT[variant] }}
    >
      {variant === "complete" ? (
        <>
          <p className="text-sm">
            Exploration complete — found {pagesFound} pages across {actionsTaken}{" "}
            actions.
          </p>
          {/* Link present but may route to a Phase-5 placeholder; degrade gracefully. */}
          <Link
            href="/explore"
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            View knowledge graph
          </Link>
        </>
      ) : null}

      {variant === "failed" ? (
        <p className="text-sm">
          Exploration failed. {error ?? "An unexpected error occurred"}. Try
          starting it again — if it keeps failing, check the API and Neo4j
          containers (<code className="font-mono">docker compose ps</code>).
        </p>
      ) : null}

      {variant === "budget" ? (
        <p className="text-sm">
          Stopped — budget reached. The run hit its configured limit before fully
          converging. Raise the target&apos;s budget overrides to explore further.
        </p>
      ) : null}

      {variant === "stopped" ? (
        <p className="text-sm">Exploration stopped.</p>
      ) : null}

      {variant === "stream-lost" ? (
        <>
          <p className="text-sm">
            Lost connection to the live feed. The exploration may still be
            running — reload to reconnect.
          </p>
          <Button variant="outline" className="mt-2 w-fit" onClick={onReload}>
            Reload
          </Button>
        </>
      ) : null}
    </Card>
  );
}
