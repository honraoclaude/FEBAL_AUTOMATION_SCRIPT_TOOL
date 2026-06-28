"use client";

/**
 * Defect review queue (list) (09-UI-SPEC §0 + §1) — /defects.
 *
 * Page header "Defects" + the read-only calibration panel (atop the queue) + two filter segment
 * groups (status: Drafts · Applied · Rejected · All, default Drafts via ?status=; class: All classes
 * · Infrastructure · Automation · Product defect, default All via ?class= — both deep-linkable,
 * accent-underlined styled-native buttons, NOT a tabs block) + the queue table. Columns: Defect
 * (accent drill-in link → /defects/[id] + mono defect-id caption) · Class (the class badge) ·
 * Confidence (the token meter banded off the row's threshold) · Source ("Flow {id}" + the mono
 * "run {run_id} · {flow_id}" refs) · Status (the status badge; an applied row shows the mono Jira
 * key) · Updated (mono ts). Default sort: drafts-first → confidence-desc → updated-desc.
 *
 * States: loading (skeleton rows / skeleton tiles) · empty-no-defects ("No defects yet" → Go to
 * executions) · empty-filter-no-match (per-filter → View drafts) · populated · rejected rows muted ·
 * inline error + Retry. Errors render inline (never a toast). Zero new shadcn, zero new deps —
 * the confidence meter is the styled-native progressbar, not a Recharts chart.
 */

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { calibration, listDefects, type DefectSummary } from "@/lib/api/defects";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadingRows } from "@/components/graph/graph-states";
import { CalibrationPanel } from "@/components/defects/calibration-panel";
import { ClassBadge } from "@/components/defects/class-badge";
import { ConfidenceMeter } from "@/components/defects/confidence-meter";
import { DefectErrorState, DefectStatusBadge } from "@/components/defects/defect-states";

const STATUS_FILTERS: { label: string; status: string }[] = [
  { label: "Drafts", status: "draft" },
  { label: "Applied", status: "applied" },
  { label: "Rejected", status: "rejected" },
  { label: "All", status: "all" },
];

const CLASS_FILTERS: { label: string; klass: string }[] = [
  { label: "All classes", klass: "all" },
  { label: "Infrastructure", klass: "infrastructure" },
  { label: "Automation", klass: "automation" },
  { label: "Product defect", klass: "product_defect" },
];

const COLUMNS = 6;

const STATUS_ORDER: Record<string, number> = { draft: 0, applied: 1, rejected: 2 };

function sortDefects(rows: DefectSummary[]): DefectSummary[] {
  return [...rows].sort((a, b) => {
    const sa = STATUS_ORDER[a.status] ?? 9;
    const sb = STATUS_ORDER[b.status] ?? 9;
    if (sa !== sb) {
      return sa - sb;
    }
    if (b.confidence !== a.confidence) {
      return b.confidence - a.confidence;
    }
    return b.updated_at.localeCompare(a.updated_at);
  });
}

const SEGMENT_CLASS =
  "border-b-2 pb-1 text-sm font-semibold outline-none transition-colors " +
  "focus-visible:ring-[3px] focus-visible:ring-ring/50";

export default function DefectReviewView() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "draft";
  const klass = params.get("class") ?? "all";

  const calibrationQuery = useQuery({
    queryKey: ["defects", "calibration"],
    queryFn: () => calibration(),
    retry: false,
  });

  const query = useQuery({
    queryKey: ["defects", status, klass],
    queryFn: () => listDefects(status, klass),
    retry: false,
  });

  const rows = sortDefects(query.data ?? []);
  const isEmpty = !query.isLoading && !query.isError && rows.length === 0;
  const threshold = calibrationQuery.data?.confidence_threshold ?? 0;

  function setParam(key: "status" | "class", next: string) {
    const sp = new URLSearchParams(params.toString());
    sp.set(key, next);
    router.push(`/defects?${sp.toString()}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Defects</h1>
      </div>

      <CalibrationPanel
        data={calibrationQuery.data}
        isLoading={calibrationQuery.isLoading}
      />

      <div className="flex flex-col gap-4">
        {/* Status filter — accent-underlined segments over tokens (NOT a new tabs block). */}
        <nav className="flex items-center gap-4" aria-label="Filter defects by status">
          {STATUS_FILTERS.map((f) => {
            const active = f.status === status;
            return (
              <button
                key={f.status}
                type="button"
                onClick={() => setParam("status", f.status)}
                aria-current={active ? "true" : undefined}
                className={
                  SEGMENT_CLASS +
                  (active
                    ? " border-primary text-primary"
                    : " border-transparent text-muted-foreground hover:text-foreground")
                }
              >
                {f.label}
              </button>
            );
          })}
        </nav>

        {/* Class filter — same styled-native segment treatment. */}
        <nav className="flex items-center gap-4" aria-label="Filter defects by class">
          {CLASS_FILTERS.map((f) => {
            const active = f.klass === klass;
            return (
              <button
                key={f.klass}
                type="button"
                onClick={() => setParam("class", f.klass)}
                aria-current={active ? "true" : undefined}
                className={
                  SEGMENT_CLASS +
                  (active
                    ? " border-primary text-primary"
                    : " border-transparent text-muted-foreground hover:text-foreground")
                }
              >
                {f.label}
              </button>
            );
          })}
        </nav>
      </div>

      {query.isError ? (
        <DefectErrorState onRetry={() => void query.refetch()} />
      ) : isEmpty ? (
        status === "draft" && klass === "all" ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
            <p className="text-sm font-semibold">No defects yet</p>
            <p className="max-w-md text-center text-sm text-muted-foreground">
              Defects appear here after a run produces a classified product failure. Run a suite,
              then come back.
            </p>
            <Button asChild variant="link" className="mt-1 text-primary">
              <Link href="/executions">Go to executions</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
            <p className="text-sm font-semibold">No matching defects</p>
            <p className="max-w-md text-center text-sm text-muted-foreground">
              Nothing here yet. Review the drafts to apply or reject them.
            </p>
            <Button
              variant="link"
              className="mt-1 text-primary"
              onClick={() => {
                router.push("/defects?status=draft&class=all");
              }}
            >
              View drafts
            </Button>
          </div>
        )
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Defect</TableHead>
              <TableHead>Class</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading ? (
              <LoadingRows columns={COLUMNS} />
            ) : (
              rows.map((row) => {
                const muted = row.status === "rejected";
                return (
                  <TableRow key={row.id} className={muted ? "text-muted-foreground" : undefined}>
                    <TableCell>
                      <div className="flex flex-col">
                        <Link
                          href={`/defects/${row.id}`}
                          className="text-primary hover:underline"
                        >
                          {row.flow_id} failed
                        </Link>
                        <span className="font-mono text-xs text-muted-foreground">
                          Defect {row.id}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <ClassBadge classification={row.classification} />
                    </TableCell>
                    <TableCell>
                      <ConfidenceMeter confidence={row.confidence} threshold={threshold} />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>Flow {row.flow_id}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          run {row.run_id} · {row.flow_id}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <DefectStatusBadge status={row.status} />
                        {row.status === "applied" && row.jira_key ? (
                          <span className="font-mono text-xs text-primary">{row.jira_key}</span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs text-muted-foreground">
                        {row.updated_at}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
