/**
 * Action-feed row (04-UI-SPEC §3 action feed) — plain composition over existing tokens.
 *
 * A small lucide verb icon, a mono/muted step index + timestamp caption, and the Body action
 * line. The verb icon is inferred from the feed_line text (Navigation/MousePointerClick/
 * FileText/Type). A REFUSED row (risk gate / off-origin, EXPL-07/08) renders an amber
 * Ban icon + muted text; per WCAG 1.4.1 the refusal meaning lives in the TEXT (the word
 * "Refused" is in feed_line), not color alone — the icon is aria-hidden. feed_line is
 * rendered as React text (auto-escaped) — never dangerouslySetInnerHTML (T-04-20).
 */

import type { ReactElement } from "react";
import {
  Ban,
  FileText,
  MousePointerClick,
  Navigation,
  Type,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface FeedRowProps {
  step: number;
  /** The full per-step line from ExploreProgressEvent.feed_line (carries the verb + target). */
  line: string;
  /** Client-side arrival timestamp (mono caption); the event has no per-step clock. */
  timestamp: string;
}

/** True when the line is a risk-gate / allowlist refusal (amber + Ban, EXPL-07/08). */
function isRefused(line: string): boolean {
  return /\brefused\b/i.test(line);
}

/** Render the verb icon element inferred from the feed line text (defaults to Navigation).
 *
 * Returns a JSX ELEMENT (not a component reference) so no component is "created during render"
 * — the lucide components are stable module-level references invoked through fixed JSX here.
 */
function verbIconElement(line: string, className: string): ReactElement {
  const l = line.toLowerCase();
  if (isRefused(line)) return <Ban aria-hidden="true" className={className} />;
  if (l.includes("form") || l.includes("validation")) {
    return <FileText aria-hidden="true" className={className} />;
  }
  if (l.includes("fill") || l.includes("typ")) {
    return <Type aria-hidden="true" className={className} />;
  }
  if (l.includes("chose") || l.includes("click") || l.includes("button")) {
    return <MousePointerClick aria-hidden="true" className={className} />;
  }
  return <Navigation aria-hidden="true" className={className} />;
}

export function FeedRow({ step, line, timestamp }: FeedRowProps) {
  const refused = isRefused(line);
  const iconClass = cn(
    "mt-0.5 size-4 shrink-0",
    refused ? "text-[var(--status-quarantine)]" : "text-muted-foreground",
  );

  return (
    <li className="flex items-start gap-1 py-2">
      {verbIconElement(line, iconClass)}
      <div className="min-w-0 flex-1">
        <span className="mr-2 font-mono text-xs text-muted-foreground">
          [{step}] {timestamp}
        </span>
        <span
          className={cn(
            "text-sm",
            refused ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {line}
        </span>
      </div>
    </li>
  );
}
