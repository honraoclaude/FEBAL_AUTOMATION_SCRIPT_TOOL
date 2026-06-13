"use client";

import type { TargetResponse } from "@/lib/api/targets";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Deactivate confirmation (01-UI-SPEC Copywriting Contract — destructive
 * confirmation). Reactivate needs no confirmation and is handled directly by
 * the table's row menu (PATCH is_active=true), so this dialog is deactivate-only.
 */

interface DeactivateDialogProps {
  target: TargetResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isPending: boolean;
}

export function DeactivateDialog({
  target,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: DeactivateDialogProps) {
  const name = target?.name ?? "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Deactivate {name}?</DialogTitle>
          <DialogDescription>
            The platform will stop running against this target. Its history is
            kept and you can reactivate it later.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Keep target
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={isPending}
          >
            Deactivate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
