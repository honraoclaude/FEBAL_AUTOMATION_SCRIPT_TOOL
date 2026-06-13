"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import type {
  TargetCreate,
  TargetResponse,
  TargetUpdate,
} from "@/lib/api/targets";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

/**
 * Register/edit target dialog (01-UI-SPEC §4). Write-only credentials (D-06):
 * in edit mode the username/password inputs are NEVER prefilled (TargetResponse
 * carries no credential material), both show the "••••••••" placeholder, and
 * `credentials` is omitted from the PATCH body unless the user typed new values.
 */

const URL_ERROR = "Enter a valid URL (including http:// or https://)";

/**
 * Numeric-or-blank field: an empty string clears to undefined; otherwise it must
 * be a positive integer. Kept as a string in the form for controlled inputs.
 */
const optionalPositiveInt = z
  .string()
  .trim()
  .refine(
    (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 1),
    "Enter a whole number ≥ 1",
  );

const formSchema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  base_url: z
    .string()
    .trim()
    .min(1, URL_ERROR)
    .url(URL_ERROR)
    .refine((v) => /^https?:\/\//i.test(v), URL_ERROR),
  username: z.string(),
  password: z.string(),
  origin_allowlist: z.string(),
  sandbox: z.boolean(),
  max_steps: optionalPositiveInt,
  max_depth: optionalPositiveInt,
  wall_clock_seconds: optionalPositiveInt,
  token_budget: optionalPositiveInt,
});

type FormValues = z.infer<typeof formSchema>;

const EMPTY: FormValues = {
  name: "",
  base_url: "",
  username: "",
  password: "",
  origin_allowlist: "",
  sandbox: false,
  max_steps: "",
  max_depth: "",
  wall_clock_seconds: "",
  token_budget: "",
};

interface TargetDialogProps {
  /** null => create mode; a target => edit mode (credentials never prefilled). */
  target: TargetResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (body: TargetCreate) => Promise<void>;
  onUpdate: (id: number, body: TargetUpdate) => Promise<void>;
}

function numOrUndef(v: string): number | undefined {
  const t = v.trim();
  return t === "" ? undefined : Number(t);
}

/** Build the budget_overrides object, or undefined if every field is blank. */
function buildBudgets(values: FormValues) {
  const budgets = {
    max_steps: numOrUndef(values.max_steps),
    max_depth: numOrUndef(values.max_depth),
    wall_clock_seconds: numOrUndef(values.wall_clock_seconds),
    token_budget: numOrUndef(values.token_budget),
  };
  const anySet = Object.values(budgets).some((v) => v !== undefined);
  return anySet ? budgets : undefined;
}

/** Split the allowlist textarea into trimmed non-empty origins. */
function buildAllowlist(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function TargetDialog({
  target,
  open,
  onOpenChange,
  onCreate,
  onUpdate,
}: TargetDialogProps) {
  const isEdit = target !== null;
  const [serverError, setServerError] = useState<string | null>(null);
  const [budgetsOpen, setBudgetsOpen] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY,
  });

  // Reset the form whenever the dialog opens. Edit mode prefills the non-secret
  // fields ONLY — credentials stay blank (write-only D-06). The amber budget
  // group auto-expands if the target already carries overrides.
  useEffect(() => {
    if (!open) {
      return;
    }
    setServerError(null);
    if (target) {
      const b = target.budget_overrides;
      form.reset({
        name: target.name,
        base_url: target.base_url,
        username: "",
        password: "",
        origin_allowlist: target.origin_allowlist.join("\n"),
        sandbox: target.sandbox,
        max_steps: b?.max_steps != null ? String(b.max_steps) : "",
        max_depth: b?.max_depth != null ? String(b.max_depth) : "",
        wall_clock_seconds:
          b?.wall_clock_seconds != null ? String(b.wall_clock_seconds) : "",
        token_budget: b?.token_budget != null ? String(b.token_budget) : "",
      });
      setBudgetsOpen(b != null);
    } else {
      form.reset(EMPTY);
      setBudgetsOpen(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, target]);

  async function onSubmit(values: FormValues) {
    setServerError(null);

    // Credentials: required on create; on edit, sent ONLY if the user typed
    // both fields — otherwise omitted entirely so the stored secret is kept.
    const typedCreds =
      values.username.length > 0 && values.password.length > 0;

    if (!isEdit && !typedCreds) {
      if (values.username.length === 0) {
        form.setError("username", { message: "Username is required" });
      }
      if (values.password.length === 0) {
        form.setError("password", { message: "Password is required" });
      }
      return;
    }

    const allowlist = buildAllowlist(values.origin_allowlist);
    const budgets = buildBudgets(values);

    try {
      if (isEdit && target) {
        const body: TargetUpdate = {
          name: values.name.trim(),
          base_url: values.base_url.trim(),
          sandbox: values.sandbox,
          budget_overrides: budgets ?? null,
        };
        if (allowlist.length > 0) {
          body.origin_allowlist = allowlist;
        }
        if (typedCreds) {
          body.credentials = {
            username: values.username,
            password: values.password,
          };
        }
        await onUpdate(target.id, body);
      } else {
        const body: TargetCreate = {
          name: values.name.trim(),
          base_url: values.base_url.trim(),
          credentials: {
            username: values.username,
            password: values.password,
          },
          sandbox: values.sandbox,
        };
        if (allowlist.length > 0) {
          body.origin_allowlist = allowlist;
        }
        if (budgets) {
          body.budget_overrides = budgets;
        }
        await onCreate(body);
      }
      onOpenChange(false);
    } catch {
      // Errors render inline at the top of the dialog body — never a toast.
      setServerError(
        "Couldn't save the target. Try again — if it keeps failing, check that the API container is healthy (`docker compose ps`).",
      );
    }
  }

  const submitting = form.formState.isSubmitting;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit target" : "Register target"}
          </DialogTitle>
        </DialogHeader>

        {serverError ? (
          <div
            role="alert"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {serverError}
          </div>
        ) : null}

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-6"
            noValidate
          >
            {/* ── Section: Target ── */}
            <section className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold">Target</h3>
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input disabled={submitting} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="base_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Base URL</FormLabel>
                    <FormControl>
                      <Input
                        className="font-mono"
                        placeholder="https://example.com"
                        disabled={submitting}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </section>

            {/* ── Section: Credentials (write-only, never prefilled) ── */}
            <section className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold">Credentials</h3>
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Username</FormLabel>
                    <FormControl>
                      <Input
                        autoComplete="off"
                        placeholder="••••••••"
                        disabled={submitting}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Password</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        autoComplete="new-password"
                        placeholder="••••••••"
                        disabled={submitting}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {isEdit ? (
                <p className="text-xs text-muted-foreground">
                  Stored encrypted and never shown. Enter new values to replace
                  them.
                </p>
              ) : null}
            </section>

            {/* ── Section: Exploration rules ── */}
            <section className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold">Exploration rules</h3>
              <FormField
                control={form.control}
                name="origin_allowlist"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Origin allowlist</FormLabel>
                    <FormControl>
                      <textarea
                        className="border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive flex min-h-20 w-full rounded-md border bg-transparent px-3 py-2 font-mono text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
                        rows={3}
                        disabled={submitting}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Defaults to the base URL&apos;s origin
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="sandbox"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start justify-between gap-4">
                    <div className="flex flex-col gap-1">
                      <FormLabel>Sandbox</FormLabel>
                      <FormDescription>
                        Allows destructive actions during exploration — only
                        enable for restorable targets
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                        disabled={submitting}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              {/* Collapsible budget overrides — 4 optional numeric fields. */}
              <div className="flex flex-col gap-3">
                <button
                  type="button"
                  className="flex items-center gap-1 text-sm font-semibold"
                  onClick={() => setBudgetsOpen((o) => !o)}
                  aria-expanded={budgetsOpen}
                >
                  {budgetsOpen ? (
                    <ChevronDown className="size-4" aria-hidden />
                  ) : (
                    <ChevronRight className="size-4" aria-hidden />
                  )}
                  Budget overrides
                </button>
                {budgetsOpen ? (
                  <div className="grid grid-cols-2 gap-4">
                    {(
                      [
                        ["max_steps", "Max steps"],
                        ["max_depth", "Max depth"],
                        ["wall_clock_seconds", "Wall-clock seconds"],
                        ["token_budget", "Token budget"],
                      ] as const
                    ).map(([fieldName, label]) => (
                      <FormField
                        key={fieldName}
                        control={form.control}
                        name={fieldName}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{label}</FormLabel>
                            <FormControl>
                              <Input
                                type="number"
                                min={1}
                                inputMode="numeric"
                                disabled={submitting}
                                {...field}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            </section>

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : null}
                {isEdit ? "Save changes" : "Register target"}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
