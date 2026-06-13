"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createTarget,
  deactivateTarget,
  listTargets,
  reactivateTarget,
  updateTarget,
  type TargetCreate,
  type TargetResponse,
  type TargetUpdate,
} from "@/lib/api/targets";
import { Button } from "@/components/ui/button";
import { DeactivateDialog } from "@/components/targets/deactivate-dialog";
import { TargetDialog } from "@/components/targets/target-dialog";
import { TargetsTable } from "@/components/targets/targets-table";

/**
 * Target registry page (01-UI-SPEC §3/§4 — PLAT-01 UI half). Owns the TanStack
 * query/mutations; every mutation invalidates ["targets"] (no optimistic
 * updates, Phase 1). Toasts are success-only (sonner, bottom-right); errors
 * surface inline inside the dialogs, never as toasts.
 */

const TARGETS_KEY = ["targets"] as const;

export default function TargetsPage() {
  const queryClient = useQueryClient();

  // include_inactive=true so soft-deleted rows render muted with the menu's
  // Reactivate action (UI-SPEC §3 inactive state).
  const { data: targets = [], isLoading } = useQuery({
    queryKey: TARGETS_KEY,
    queryFn: () => listTargets(true),
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<TargetResponse | null>(null);
  const [deactivating, setDeactivating] = useState<TargetResponse | null>(null);

  function invalidate() {
    return queryClient.invalidateQueries({ queryKey: TARGETS_KEY });
  }

  const createMutation = useMutation({
    mutationFn: (body: TargetCreate) => createTarget(body),
    onSuccess: async () => {
      await invalidate();
      toast.success("Target registered");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: TargetUpdate }) =>
      updateTarget(id, body),
    onSuccess: async () => {
      await invalidate();
      toast.success("Target updated");
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => deactivateTarget(id),
    onSuccess: async () => {
      await invalidate();
      toast.success("Target deactivated");
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: (id: number) => reactivateTarget(id),
    onSuccess: async () => {
      await invalidate();
      toast.success("Target updated");
    },
  });

  function openRegister() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(target: TargetResponse) {
    setEditing(target);
    setDialogOpen(true);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        {/* Heading role: 20px/600 (UI-SPEC typography). */}
        <h1 className="text-xl font-semibold leading-tight">
          Target Applications
        </h1>
        <Button onClick={openRegister}>Register target</Button>
      </div>

      <TargetsTable
        targets={targets}
        isLoading={isLoading}
        onRegister={openRegister}
        onEdit={openEdit}
        onDeactivate={(t) => setDeactivating(t)}
        onReactivate={(t) => reactivateMutation.mutate(t.id)}
      />

      <TargetDialog
        target={editing}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        // Throw on failure so the dialog renders its inline error and stays open.
        onCreate={(body) => createMutation.mutateAsync(body).then(() => {})}
        onUpdate={(id, body) =>
          updateMutation.mutateAsync({ id, body }).then(() => {})
        }
      />

      <DeactivateDialog
        target={deactivating}
        open={deactivating !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeactivating(null);
          }
        }}
        isPending={deactivateMutation.isPending}
        onConfirm={() => {
          if (!deactivating) {
            return;
          }
          deactivateMutation.mutate(deactivating.id, {
            onSuccess: () => setDeactivating(null),
          });
        }}
      />
    </div>
  );
}
