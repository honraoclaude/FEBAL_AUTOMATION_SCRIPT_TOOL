/**
 * Counter tile (04-UI-SPEC §2 counters strip) — a plain composition over the installed
 * card + existing tokens (NOT a new shadcn block). Caption label (12px muted) on top, a
 * Label-weight value (14px/600) below; cost/elapsed values render mono. The value carries an
 * aria-label combining label + value since the visual split is two elements (a11y contract).
 */

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface CounterTileProps {
  label: string;
  value: string;
  /** Cost/Elapsed render in Geist Mono (numerals + budget ratio); Pages/Actions are sans. */
  mono?: boolean;
}

export function CounterTile({ label, value, mono = false }: CounterTileProps) {
  return (
    <Card className="gap-2 p-4">
      <p className="text-xs font-normal text-muted-foreground">{label}</p>
      <p
        className={cn("text-sm font-semibold leading-normal", mono && "font-mono")}
        aria-label={`${label}: ${value}`}
      >
        {value}
      </p>
    </Card>
  );
}
