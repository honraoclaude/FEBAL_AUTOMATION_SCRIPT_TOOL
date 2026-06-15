import Link from "next/link";

/**
 * Explorations index placeholder (plan 04-04 Task 3). A run-less /explore listing page is OUT
 * of scope this phase (UI-SPEC §3 shared additions — planner's discretion, kept minimal): the
 * "Explorations" sidebar item lands here and directs the user to start a run from the Targets
 * page, which then navigates to the live view at /explore/{runId}.
 */
export default function ExploreIndexPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold leading-tight">Explorations</h1>
      <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16 text-center">
        <p className="text-sm font-semibold">No exploration open</p>
        <p className="text-sm text-muted-foreground">
          Start an exploration from the Targets page to watch it live here.
        </p>
        <Link
          href="/targets"
          className="mt-2 text-sm text-primary underline-offset-4 hover:underline"
        >
          Go to Targets
        </Link>
      </div>
    </div>
  );
}
