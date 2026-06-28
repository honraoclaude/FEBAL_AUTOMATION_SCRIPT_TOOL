"use client";

/**
 * Defect class badge (09-UI-SPEC §Color "Defect class → status-token mapping").
 *
 * The single most important color decision of the phase: the three classes are distinct in HUE
 * AND WORD AND ICON. Product defect is RED (a real bug — the actionable signal), Automation is
 * AMBER (fix the suite — needs attention, not a product fault), Infrastructure is MUTED/NEUTRAL
 * (environmental noise). WCAG 1.4.1: a class is NEVER conveyed by color alone — the WORD and the
 * lucide icon always accompany the hue (the icon is aria-hidden; the text carries the meaning).
 *
 * REUSES the existing --status-* tokens (no new colors); a plain composition over the vendored
 * `badge` + lucide icons (no new shadcn).
 *
 *   infrastructure  -> muted  ServerCog  "Infrastructure"  (--status-neutral)
 *   automation      -> amber  Wrench     "Automation"      (--status-quarantine)
 *   product_defect  -> red    Bug        "Product defect"  (--status-fail)
 */

import { Bug, ServerCog, Wrench, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

type DefectClass = "infrastructure" | "automation" | "product_defect";

interface ClassMeta {
  word: string;
  token: string;
  Icon: LucideIcon;
}

const META: Record<DefectClass, ClassMeta> = {
  infrastructure: { word: "Infrastructure", token: "var(--status-neutral)", Icon: ServerCog },
  automation: { word: "Automation", token: "var(--status-quarantine)", Icon: Wrench },
  product_defect: { word: "Product defect", token: "var(--status-fail)", Icon: Bug },
};

function normalize(value: string): DefectClass {
  return (value in META ? value : "infrastructure") as DefectClass;
}

export function ClassBadge({ classification }: { classification: string }) {
  const { word, token, Icon } = META[normalize(classification)];
  return (
    <Badge variant="outline" className="gap-1.5" aria-label={`Class: ${word}`}>
      <Icon aria-hidden className="size-3.5" style={{ color: token }} />
      <span style={{ color: token }}>{word}</span>
    </Badge>
  );
}
