"use client";

/**
 * Defect detail / review (09-UI-SPEC §2) — /defects/[id].
 *
 * Breadcrumb + header (the proposed-issue summary + the class badge + the status badge + the mono
 * "Defect {id}" + "Updated {ts}"); the Proposed Jira issue card (Summary / Description [+ the
 * honest "written without an LLM" caption when not enriched] / Steps to reproduce / Expected /
 * Actual / Severity / Priority); the Evidence card (Error type / DOM diff / Healing history / Infra
 * health) + the cited-signals caption + the mono Fingerprint caption; the Attachments card (each an
 * AUTH-GATED URL the client builds from the run-relative basename via the Phase-7 artifact route —
 * NEVER a raw filesystem path, T-09-18); and the action bar — Apply (the create-vs-update label
 * from the server dedup; an HONEST pending → result, never fake-instant success; disabled with the
 * not-configured caption when Jira isn't set up) + Reject (destructive → confirm dialog).
 *
 * No optimistic updates (T-09-21): defect status, the Jira key, and the create-vs-update decision
 * render strictly from the server response after each mutation. invalidate() covers the detail +
 * list + calibration queries. Read/apply/404 errors render INLINE; success toasts only.
 */

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import {
  applyDefect,
  defectDetail,
  rejectDefect,
  type AttachmentRef,
  type DefectDetail,
} from "@/lib/api/defects";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Breadcrumb } from "@/components/graph/breadcrumb";
import { ClassBadge } from "@/components/defects/class-badge";
import { ConfidenceMeter } from "@/components/defects/confidence-meter";
import { DefectStatusBadge } from "@/components/defects/defect-states";

const NOT_CONFIGURED =
  "Jira isn't configured. Set the Jira email, API token, and project key in config to file issues. Until then defects stay in the review queue.";
const APPLY_FAILED =
  "Couldn't file the issue to Jira. Check the Jira config and that the instance is reachable, then apply again.";
const NO_LLM =
  "Description written without an LLM (no provider key) — a deterministic summary of the evidence.";

/** The artifact kinds the detail surfaces, in the UI-SPEC order. */
const KINDS: { key: string; label: string }[] = [
  { key: "screenshot", label: "Screenshot" },
  { key: "trace", label: "Trace" },
  { key: "video", label: "Video" },
  { key: "console", label: "Console log" },
  { key: "network", label: "Network log" },
];

/** The honest absent-artifact caption per kind (not a broken link). */
const ABSENT: Record<string, string> = {
  screenshot: "No screenshot for this run.",
  trace: "No trace for this run.",
  video: "Video captured on failure only.",
  console: "No console log for this run.",
  network: "No network log for this run.",
};

/**
 * Build the AUTH-GATED artifact URL from the RUN-RELATIVE basename (the Phase-7 route).
 * The run_id-derived /api/executions/{run_id}/artifacts/... path participates in the server-side
 * realpath containment guard; the client never holds or sends a raw filesystem path (T-09-18).
 * The backend AttachmentRef.path is run-relative (e.g. "flow-0/test/trace.zip"); each segment is
 * URL-encoded so it can never escape the route into an absolute path.
 */
function attachmentUrl(runId: string, ref: AttachmentRef): string {
  const segments = ref.path.split("/").filter(Boolean).map(encodeURIComponent);
  return `/api/executions/${encodeURIComponent(runId)}/artifacts/${segments.join("/")}`;
}

function basename(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/** Evidence value reader — the snapshot is opaque JSON; pull a string field or fall back. */
function ev(evidence: Record<string, unknown> | null, key: string): string | null {
  if (!evidence) {
    return null;
  }
  const value = evidence[key];
  if (value === null || value === undefined) {
    return null;
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}

export default function DefectDetailView() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const queryClient = useQueryClient();

  const [confirmReject, setConfirmReject] = useState(false);
  const [applyError, setApplyError] = useState(false);

  const query = useQuery({
    queryKey: ["defects", "detail", id],
    queryFn: () => defectDetail(id),
    retry: false,
  });

  function invalidate() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ["defects", "detail", id] }),
      queryClient.invalidateQueries({ queryKey: ["defects"] }),
    ]);
  }

  const applyMutation = useMutation({
    mutationFn: () => applyDefect(id),
    onMutate: () => {
      setApplyError(false);
    },
    onSuccess: async (result: DefectDetail) => {
      await invalidate();
      const key = result.jira_key ?? "the issue";
      toast.success(
        result.last_action === "update" ? `Issue updated — ${key}` : `Issue filed — ${key}`,
      );
    },
    onError: () => {
      // Apply failed (e.g. Jira error or not-configured 400) → render INLINE; the defect stays a
      // draft (never a fabricated "Applied"). The not-configured case is detected up front below.
      setApplyError(true);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectDefect(id),
    onSuccess: async () => {
      setConfirmReject(false);
      await invalidate();
      toast.success("Defect rejected");
    },
  });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-80" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <div className="flex flex-col gap-4">
          <Breadcrumb crumbs={[{ label: "Defects", href: "/defects" }]} />
          <p className="text-sm text-muted-foreground">No defect found for this id.</p>
          <Link href="/defects" className="text-sm text-primary hover:underline">
            Back to defects
          </Link>
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-4">
        <Breadcrumb crumbs={[{ label: "Defects", href: "/defects" }]} />
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t load this defect. Try again.
        </p>
        <Button variant="outline" className="w-fit" onClick={() => void query.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const defect = query.data!;
  const proposed = defect.proposed_issue;
  const isDraft = defect.status === "draft";
  const isRejected = defect.status === "rejected";
  const isApplied = defect.status === "applied";

  // The Apply label honors the server dedup: an existing Jira key on a draft means a re-apply
  // updates that issue; otherwise it creates one. The label is never fabricated.
  const applyLabel = defect.jira_key
    ? `Apply — update ${defect.jira_key}`
    : "Apply — create Jira issue";

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumb
        crumbs={[{ label: "Defects", href: "/defects" }, { label: proposed.summary }]}
      />

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold leading-tight">{proposed.summary}</h1>
          <ClassBadge classification={defect.classification} />
          <DefectStatusBadge status={defect.status} />
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted-foreground">Defect {defect.id}</span>
          <span className="font-mono text-xs text-muted-foreground">
            Updated {defect.updated_at}
          </span>
          <ConfidenceMeter
            confidence={defect.confidence}
            threshold={defect.confidence_threshold}
          />
        </div>
      </div>

      {/* Proposed Jira issue */}
      <Card className="gap-3 p-4">
        <h2 className="text-sm font-semibold">Proposed Jira issue</h2>

        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold">Summary</span>
          <span className="text-sm">{proposed.summary}</span>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold">Description</span>
          <p className="text-sm whitespace-pre-wrap">{proposed.description}</p>
          {!proposed.enriched ? (
            <span className="text-xs text-muted-foreground">{NO_LLM}</span>
          ) : null}
        </div>

        {proposed.steps.length > 0 ? (
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Steps to reproduce</span>
            <ol className="list-decimal flex flex-col gap-2 pl-5 text-sm">
              {proposed.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Expected</span>
            <span className="text-sm">{proposed.expected}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Actual</span>
            <span className="text-sm">{proposed.actual}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Severity</span>
            <span className="text-sm">{proposed.severity}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Priority</span>
            <span className="text-sm">{proposed.priority}</span>
          </div>
        </div>
      </Card>

      {/* Evidence */}
      <Card className="gap-3 p-4">
        <h2 className="text-sm font-semibold">Evidence</h2>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Error type</span>
            <span className="text-sm">
              {ev(defect.evidence, "error_type") ??
                ev(defect.evidence, "error_text") ??
                "Not recorded."}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">DOM diff</span>
            <span className="font-mono text-sm whitespace-pre-wrap">
              {ev(defect.evidence, "dom_diff") ?? "No DOM diff for this run."}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Healing history</span>
            <span className="text-sm">
              {ev(defect.evidence, "healing_history") ?? "No healing attempted for this run."}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">Infra health</span>
            <span className="text-sm">{ev(defect.evidence, "infra_health") ?? "Unknown"}</span>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">
          Classified {defect.classification} at {defect.confidence} confidence from the signals
          above.
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          Fingerprint {defect.fingerprint}
        </span>
      </Card>

      {/* Attachments — auth-gated URLs from run-relative basenames (never raw paths). */}
      <Card className="gap-3 p-4">
        <h2 className="text-sm font-semibold">Attachments</h2>
        <div className="flex flex-col gap-2">
          {KINDS.map((kind) => {
            const ref = defect.attachments.find((a) => a.kind === kind.key);
            if (!ref || !ref.path) {
              return (
                <div key={kind.key} className="flex flex-col">
                  <span className="text-sm">{kind.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {ABSENT[kind.key] ?? "Not captured for this run."}
                  </span>
                </div>
              );
            }
            return (
              <div key={kind.key} className="flex flex-col">
                <a
                  href={attachmentUrl(defect.run_id, ref)}
                  className="text-sm text-primary hover:underline"
                  aria-label={`${kind.label} for defect ${defect.id}`}
                >
                  {kind.label}
                </a>
                <span className="font-mono text-xs text-muted-foreground">
                  {basename(ref.path)}
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Action bar */}
      {isRejected ? (
        <p className="text-sm text-muted-foreground">Rejected — not filed to Jira.</p>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Button
              onClick={() => applyMutation.mutate()}
              disabled={!isDraft || applyMutation.isPending}
              aria-busy={applyMutation.isPending}
            >
              {applyMutation.isPending ? "Filing…" : applyLabel}
            </Button>
            {!isRejected ? (
              <Button variant="destructive" onClick={() => setConfirmReject(true)}>
                Reject defect
              </Button>
            ) : null}
          </div>

          {isApplied && defect.jira_key ? (
            <p className="text-sm text-muted-foreground">
              Filed to{" "}
              <span className="font-mono text-primary">{defect.jira_key}</span>
            </p>
          ) : null}

          {applyError ? (
            <div role="alert" className="flex flex-col gap-2">
              <p className="text-sm text-muted-foreground">
                {applyMutation.error instanceof ApiError &&
                applyMutation.error.status === 400
                  ? NOT_CONFIGURED
                  : APPLY_FAILED}
              </p>
              <Button
                variant="outline"
                className="w-fit"
                onClick={() => applyMutation.mutate()}
              >
                Retry
              </Button>
            </div>
          ) : null}
        </div>
      )}

      <Dialog open={confirmReject} onOpenChange={setConfirmReject}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this defect?</DialogTitle>
            <DialogDescription>
              It won&apos;t be filed to Jira. You can still see it under the Rejected filter.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmReject(false)}>
              Keep in queue
            </Button>
            <Button
              variant="destructive"
              onClick={() => rejectMutation.mutate()}
              disabled={rejectMutation.isPending}
            >
              Reject defect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
