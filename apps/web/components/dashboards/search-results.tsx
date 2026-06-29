"use client";

/**
 * Search results (10-UI-SPEC §6, DASH-06) — the typed, highlighted hit list. Each result card:
 *   - the type badge (Execution PlayCircle/neutral · Failure XCircle/--status-fail · Log
 *     ScrollText/neutral — WORD + icon + hue, never color alone, WCAG 1.4.1)
 *   - the hit title (Label)
 *   - the ES `highlight` fragment rendered as SAFE emphasized text (T-10-29): the server emphasizes
 *     the matched term with <em>…</em>; we PARSE that into plain-text + <em> spans rather than
 *     injecting HTML, so a crafted source value can NEVER execute as markup. We do NOT re-highlight
 *     client-side — the emphasis is exactly what the server returned.
 *   - the mono "{index} · {id}" caption
 *   - (where resolvable) an accent drill-in link to the source detail page
 *     (executions -> /executions/{id}, failures/defects -> /defects/{id})
 *
 * Every hit renders STRICTLY from the server payload — never a fabricated hit.
 */

import { PlayCircle, ScrollText, XCircle, type LucideIcon } from "lucide-react";

import {
  firstHighlight,
  hitTitle,
  type SearchHit,
} from "@/lib/api/search";
import { Card } from "@/components/ui/card";
import Link from "next/link";

interface TypeMeta {
  word: string;
  token: string;
  Icon: LucideIcon;
}

/** Map the ES `_index` to its type badge (word + icon + hue). Unknown -> an honest neutral "Result". */
function typeMeta(index: string): TypeMeta {
  if (index.startsWith("execution"))
    return { word: "Execution", token: "var(--status-neutral)", Icon: PlayCircle };
  if (index.startsWith("failure"))
    return { word: "Failure", token: "var(--status-fail)", Icon: XCircle };
  if (index.startsWith("log"))
    return { word: "Log", token: "var(--status-neutral)", Icon: ScrollText };
  return { word: "Result", token: "var(--status-neutral)", Icon: ScrollText };
}

/**
 * SAFELY render a server highlight fragment: split on the literal <em>…</em> the ES highlighter
 * emits and emphasize ONLY those runs; every other run is plain text (React escapes it). No HTML is
 * ever injected, so a source value containing markup cannot execute (T-10-29).
 */
function HighlightedFragment({ fragment }: { fragment: string }) {
  const parts = fragment.split(/(<em>.*?<\/em>)/g).filter((p) => p.length > 0);
  return (
    <span className="text-sm text-muted-foreground">
      {parts.map((part, i) => {
        const m = /^<em>(.*?)<\/em>$/.exec(part);
        return m ? (
          <em key={i} className="font-semibold not-italic text-foreground">
            {m[1]}
          </em>
        ) : (
          <span key={i}>{part}</span>
        );
      })}
    </span>
  );
}

/** The drill-in href for a hit, where the index resolves to an existing detail page (else null). */
function drillHref(hit: SearchHit): string | null {
  const src = hit.source;
  const runId = typeof src.run_id === "string" ? src.run_id : null;
  const defectId =
    typeof src.defect_id === "number"
      ? String(src.defect_id)
      : typeof src.id === "number"
        ? String(src.id)
        : null;
  if (hit.index.startsWith("execution") && runId) return `/executions/${runId}`;
  if (hit.index.startsWith("failure") && defectId) return `/defects/${defectId}`;
  if (hit.index.startsWith("failure") && runId) return `/executions/${runId}`;
  return null;
}

function ResultCard({ hit }: { hit: SearchHit }) {
  const meta = typeMeta(hit.index);
  const fragment = firstHighlight(hit);
  const href = drillHref(hit);

  return (
    <Card className="gap-2 p-4" data-testid="search-result">
      <div className="flex items-center gap-2">
        <span
          className="inline-flex items-center gap-1 text-xs font-semibold"
          aria-label={`Type: ${meta.word}`}
        >
          <meta.Icon aria-hidden className="size-3.5" style={{ color: meta.token }} />
          <span style={{ color: meta.token }}>{meta.word}</span>
        </span>
      </div>
      <p className="text-sm font-semibold">{hitTitle(hit)}</p>
      {fragment ? <HighlightedFragment fragment={fragment} /> : null}
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-muted-foreground">
          {hit.index} · {hit.id}
        </span>
        {href ? (
          <Link
            href={href}
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            Open
          </Link>
        ) : null}
      </div>
    </Card>
  );
}

export function SearchResults({ hits }: { hits: SearchHit[] }) {
  return (
    <div className="flex flex-col gap-2">
      {hits.map((hit) => (
        <ResultCard key={`${hit.index}:${hit.id}`} hit={hit} />
      ))}
    </div>
  );
}
