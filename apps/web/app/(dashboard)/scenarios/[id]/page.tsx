"use client";

/**
 * Scenario detail / review (06-UI-SPEC §2) — /scenarios/[id].
 *
 * Breadcrumb + title + status badge + "Edited" caption + timestamps; the Gherkin editor; the
 * "Assertion checks" gate-indicators (honest, server-authoritative); the "Source flow" section
 * (risk badge + link into the KG); and the action bar — "Approve scenario" (accent, DISABLED
 * unless the Gherkin parses AND every Then resolves AND there is no unsaved edit) · "Reject
 * scenario" (destructive → confirm dialog) · Save/Cancel live with the editor.
 *
 * The defining interaction (D-02): edit → "Save edits" → POST /edit re-runs BOTH gates
 * server-side. On 422 the failure renders INLINE (parser error above the editor / offending
 * Thens flagged red) — NEVER a toast — and the reviewer's text is preserved. On success the
 * gate panel repaints with fresh honest results and Approve enables iff all checks pass.
 * Mutations invalidate the list + detail queries (no optimistic updates — the gate result is
 * server-authoritative, D-03). Success toasts (sonner) for saved/approved/rejected only.
 */

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import {
  approveScenario,
  editScenario,
  rejectScenario,
  scenarioDetail,
} from "@/lib/api/scenarios";
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
import { RiskBadge } from "@/components/graph/risk-badge";
import { GateIndicators } from "@/components/scenarios/gate-indicators";
import { GherkinEditor } from "@/components/scenarios/gherkin-editor";
import { ScenarioErrorState } from "@/components/scenarios/scenario-states";
import { StatusBadge } from "@/components/scenarios/status-badge";

const APPROVE_HELP =
  "Approve is available once the Gherkin parses and every Then asserts a recorded outcome.";

export default function ScenarioDetailView() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const router = useRouter();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["scenarios", "detail", id],
    queryFn: () => scenarioDetail(id),
    retry: false,
  });

  // Editor state: the working text + the inline lint error (only set on a save 422).
  // The editor is seeded from the server's saved text and RESET to it whenever the saved text
  // changes (initial load + after a successful save) using React's "adjust state during render"
  // pattern (https://react.dev/learn/you-might-not-need-an-effect) — no effect, no cascade.
  const saved = query.data?.gherkin_text ?? "";
  const [draftText, setDraftText] = useState<string>(saved);
  const [seededFrom, setSeededFrom] = useState<string>(saved);
  const [lintError, setLintError] = useState<string | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);

  if (query.data && saved !== seededFrom) {
    setSeededFrom(saved);
    setDraftText(saved);
    setLintError(null);
  }

  function invalidate() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ["scenarios", "detail", id] }),
      queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
    ]);
  }

  const editMutation = useMutation({
    mutationFn: () =>
      editScenario(id, {
        gherkin_text: draftText,
        // Forward the row's OWN structured refs unchanged — the server re-runs the no-vacuous
        // gate against them alongside the edited Gherkin (D-02). The reviewer edits the Gherkin
        // text; the sidecar refs ride along unchanged this slice.
        then_refs: query.data?.then_refs ?? [],
      }),
    onSuccess: async () => {
      setLintError(null);
      await invalidate();
      toast.success("Edits saved");
    },
    onError: (err) => {
      // 422 → render the failure INLINE (parser/vacuous detail above the editor), keep the text.
      if (err instanceof ApiError && err.status === 422) {
        setLintError(err.detail);
      }
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveScenario(id),
    onSuccess: async () => {
      await invalidate();
      toast.success("Scenario approved");
      router.push("/scenarios");
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectScenario(id),
    onSuccess: async () => {
      setConfirmReject(false);
      await invalidate();
      toast.success("Scenario rejected");
      router.push("/scenarios");
    },
  });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <div className="flex flex-col gap-4">
          <Breadcrumb crumbs={[{ label: "Scenario review", href: "/scenarios" }]} />
          <p className="text-sm text-muted-foreground">No scenario found.</p>
        </div>
      );
    }
    return <ScenarioErrorState onRetry={() => void query.refetch()} />;
  }

  const scenario = query.data!;
  const dirty = draftText !== saved;
  const allResolved =
    scenario.then_results.length > 0 && scenario.then_results.every((r) => r.resolved);
  const approveDisabled = dirty || !allResolved || approveMutation.isPending;

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumb
        crumbs={[
          { label: "Scenario review", href: "/scenarios" },
          { label: scenario.feature_name },
        ]}
      />

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold leading-tight">{scenario.feature_name}</h1>
          <StatusBadge status={scenario.status} />
          {scenario.edited ? (
            <span className="text-xs text-muted-foreground">Edited</span>
          ) : null}
        </div>
        <span className="font-mono text-xs text-muted-foreground">
          Updated {scenario.updated_at}
        </span>
      </div>

      <GherkinEditor
        value={draftText}
        saved={saved}
        onChange={(next) => {
          setDraftText(next);
          if (lintError) {
            setLintError(null);
          }
        }}
        onSave={() => editMutation.mutate()}
        onCancel={() => {
          setDraftText(saved);
          setLintError(null);
        }}
        saving={editMutation.isPending}
        lintError={lintError}
      />

      {/* Honest server-authoritative per-Then results; "Pending re-check" while the edit is unsaved. */}
      <GateIndicators results={scenario.then_results} pending={dirty} />

      <Card className="gap-2 p-4">
        <h2 className="text-sm font-semibold">Source flow</h2>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-muted-foreground">{scenario.flow_id}</span>
          <RiskBadge score={scenario.flow_risk_score} tier={scenario.flow_risk_tier} />
        </div>
        <Link
          href={`/graph/flows/${encodeURIComponent(scenario.flow_id)}`}
          className="text-sm text-primary hover:underline"
        >
          View in knowledge graph
        </Link>
      </Card>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Button
            onClick={() => approveMutation.mutate()}
            disabled={approveDisabled}
            aria-describedby="approve-help"
          >
            Approve scenario
          </Button>
          <Button variant="destructive" onClick={() => setConfirmReject(true)}>
            Reject scenario
          </Button>
        </div>
        {approveDisabled ? (
          <p id="approve-help" className="text-xs text-muted-foreground">
            {APPROVE_HELP}
          </p>
        ) : null}
      </div>

      <Dialog open={confirmReject} onOpenChange={setConfirmReject}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject {scenario.feature_name}?</DialogTitle>
            <DialogDescription>
              It won&apos;t feed automation generation. You can still see it under the Rejected
              filter.
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
              Reject scenario
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
