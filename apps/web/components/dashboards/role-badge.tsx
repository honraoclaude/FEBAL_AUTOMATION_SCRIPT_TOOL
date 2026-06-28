/**
 * Role badge (10-UI-SPEC "Role -> status-token mapping") — the current role rendered as a WORD +
 * its lucide icon + its --status-* token hue. Role is NEVER conveyed by color alone (WCAG 1.4.1):
 * the WORD always carries the meaning; the icon is aria-hidden.
 *
 *   admin       -> red    ShieldCheck    "Admin"        (highest privilege; the attention semantic)
 *   qa_lead     -> green  ClipboardCheck "QA Lead"
 *   qa_engineer -> amber  FlaskConical   "QA Engineer"
 *   developer   -> muted  Code2          "Developer"
 *
 * Reuses the --status-* tokens (no new colors) and the word+icon discipline from the Phase-7/9
 * verdict/class badges. An unknown role renders its raw string in the neutral hue (honest, never a
 * fabricated role).
 */

import {
  ClipboardCheck,
  Code2,
  FlaskConical,
  ShieldCheck,
  UserCircle2,
  type LucideIcon,
} from "lucide-react";

interface RoleMeta {
  word: string;
  token: string;
  Icon: LucideIcon;
}

const META: Record<string, RoleMeta> = {
  admin: { word: "Admin", token: "var(--status-fail)", Icon: ShieldCheck },
  qa_lead: { word: "QA Lead", token: "var(--status-pass)", Icon: ClipboardCheck },
  qa_engineer: {
    word: "QA Engineer",
    token: "var(--status-quarantine)",
    Icon: FlaskConical,
  },
  developer: { word: "Developer", token: "var(--status-neutral)", Icon: Code2 },
};

/** Resolve the role meta, falling back to an honest neutral rendering of the raw role string. */
function metaFor(role: string): RoleMeta {
  return (
    META[role] ?? { word: role, token: "var(--status-neutral)", Icon: UserCircle2 }
  );
}

export function RoleBadge({ role }: { role: string }) {
  const { word, token, Icon } = metaFor(role);
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold"
      aria-label={`Role: ${word}`}
      data-testid="role-badge"
    >
      <Icon aria-hidden className="size-3.5" style={{ color: token }} />
      <span style={{ color: token }}>{word}</span>
    </span>
  );
}
