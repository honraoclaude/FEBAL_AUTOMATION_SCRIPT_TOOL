"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  // Silent session resume (D-04): a returning browser whose 30-min access
  // cookie expired gets bounced here by proxy.ts, but its 7-day refresh
  // cookie (path=/api/auth) may still be valid. Probe the refresh endpoint
  // directly with a plain fetch (NOT the client wrapper's retry path); on
  // 200 a new access cookie is set and we resume without re-typing
  // credentials. On non-200, stay on the form silently — no error UI.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/refresh", { method: "POST" })
      .then((res) => {
        if (!cancelled && res.ok) {
          router.replace("/targets");
        }
      })
      .catch(() => {
        /* probe is best-effort; stay on the form */
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function onSubmit(values: LoginValues) {
    setServerError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      if (res.ok) {
        router.push("/targets");
        return;
      }
      // Uniform message for unknown user vs wrong password (UI-SPEC
      // copywriting contract / anti-enumeration posture).
      setServerError("Invalid email or password.");
      form.resetField("password"); // retain email, clear password
    } catch {
      setServerError("Invalid email or password.");
      form.resetField("password");
    }
  }

  const submitting = form.formState.isSubmitting;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          {/* Display role: 28px/600 — login product heading only (UI-SPEC typography) */}
          <h1 className="text-[28px] font-semibold leading-[1.2]">
            Autonomous QA Engineer Platform
          </h1>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="flex flex-col gap-4"
              noValidate
            >
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        autoComplete="email"
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
                        autoComplete="current-password"
                        disabled={submitting}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {serverError ? (
                <p className="text-sm text-destructive" role="alert">
                  {serverError}
                </p>
              ) : null}
              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : null}
                Log in
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
      <p className="mt-4 text-xs text-muted-foreground">
        Admin account is provisioned from environment configuration.
      </p>
    </main>
  );
}
