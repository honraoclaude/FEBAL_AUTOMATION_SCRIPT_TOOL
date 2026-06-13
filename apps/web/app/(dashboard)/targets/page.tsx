import { Button } from "@/components/ui/button";

/**
 * Targets page stub (01-04): real table + register dialog arrive in plan
 * 01-06. This keeps the login redirect target real — page header per
 * 01-UI-SPEC §3 above the empty-state copy.
 */
export default function TargetsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        {/* Heading role: 20px/600 (UI-SPEC typography) */}
        <h1 className="text-xl font-semibold leading-tight">
          Target Applications
        </h1>
        {/* Disabled until plan 01-06 wires the register dialog */}
        <Button disabled>Register target</Button>
      </div>
      <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
        <p className="text-sm font-semibold">No target applications yet</p>
        <p className="text-sm text-muted-foreground">
          Register a target application to give the platform something to
          explore.
        </p>
      </div>
    </div>
  );
}
