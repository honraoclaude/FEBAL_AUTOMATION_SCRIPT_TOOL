"use client";

/**
 * Admin — Users (10-UI-SPEC §7, PLAT-04) — /admin/users (Admin role only).
 *
 * The users table (Email · Role · control) — each row the mono email + the role badge + a
 * dropdown-menu to change the role. The CURRENT admin's own row shows the control DISABLED with
 * "You can't change your own role." (the self-demote/lockout guard; the server 400 is the real
 * boundary, this is the mirror — T-10-28).
 *
 * Role-change flow: pick a new role from the dropdown -> the confirm dialog ("Change {email}'s
 * role?") -> on confirm useMutation POST /api/users/{id}/role with ["users"] + ["auth","me"]
 * invalidation, NO optimistic update -> on success the sonner toast + the badge repaints from the
 * server response -> on failure the inline error + the badge stays the OLD role.
 *
 * State machine: loading skeletons / only-the-admin caption / populated / changing (dialog
 * "Changing…" disabled) / change-failed (inline) / non-admin-who-reaches-the-URL (no-access — the
 * nav already hides Users; the API 403s and the client renders THIS, never the data — T-10-27).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import {
  getUsers,
  setRole,
  ROLES,
  type Role,
  type UserSummary,
} from "@/lib/api/users";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RoleBadge } from "@/components/dashboards/role-badge";
import { NoAccess } from "@/components/dashboards/dashboard-states";

const USERS_KEY = ["users"] as const;

type Me = { id: number; email: string; role: string };

/** The pending role change awaiting confirmation in the dialog. */
interface PendingChange {
  user: UserSummary;
  newRole: Role;
}

function roleLabel(role: string): string {
  return ROLES.find((r) => r.value === role)?.label ?? role;
}

export default function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [changeFailed, setChangeFailed] = useState(false);

  // Who am I? — to disable the self-row (the self-demote guard mirror).
  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<Me>("/api/auth/me"),
    staleTime: 5 * 60 * 1000,
  });
  const myId = meQuery.data?.id;

  const usersQuery = useQuery({
    queryKey: USERS_KEY,
    queryFn: getUsers,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ user, newRole }: PendingChange) => setRole(user.id, newRole),
    onMutate: () => setChangeFailed(false),
    onSuccess: async (updated: UserSummary) => {
      // No optimistic update — the badge repaints from the SERVER response on refetch.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: USERS_KEY }),
        queryClient.invalidateQueries({ queryKey: ["auth", "me"] }),
      ]);
      setPending(null);
      toast.success(`Role changed — ${updated.email} is now ${roleLabel(updated.role)}`);
    },
    onError: () => {
      // The change wasn't saved — render the inline error; the badge stays the OLD role.
      setChangeFailed(true);
    },
  });

  const forbidden =
    usersQuery.error instanceof ApiError && usersQuery.error.status === 403;
  const users = usersQuery.data;
  const onlyAdmin = !!users && users.length === 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold leading-tight">Users</h1>
      </div>

      {forbidden ? (
        <NoAccess role={meQuery.data?.role} />
      ) : usersQuery.isError ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-16">
          <p className="text-sm font-semibold">Couldn&apos;t load users</p>
          <Button
            variant="outline"
            className="mt-1"
            onClick={() => void usersQuery.refetch()}
          >
            Retry
          </Button>
        </div>
      ) : usersQuery.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : users ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Email</TableHead>
                <TableHead scope="col">Role</TableHead>
                <TableHead scope="col">
                  <span className="sr-only">Change role</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => {
                const isSelf = u.id === myId;
                return (
                  <TableRow key={u.id}>
                    <TableCell>
                      <span className="font-mono text-sm">{u.email}</span>
                    </TableCell>
                    <TableCell>
                      <RoleBadge role={u.role} />
                    </TableCell>
                    <TableCell>
                      {isSelf ? (
                        <span
                          className="text-xs text-muted-foreground"
                          data-testid="self-row-guard"
                        >
                          You can&apos;t change your own role.
                        </span>
                      ) : (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              aria-label={`Change role for ${u.email}`}
                            >
                              Change role
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {ROLES.map((r) => (
                              <DropdownMenuItem
                                key={r.value}
                                disabled={r.value === u.role}
                                onSelect={() =>
                                  setPending({ user: u, newRole: r.value })
                                }
                              >
                                {r.label}
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {onlyAdmin ? (
            <p className="text-xs text-muted-foreground">
              You&apos;re the only user so far.
            </p>
          ) : null}
        </>
      ) : null}

      {/* Role-change confirm dialog */}
      <Dialog
        open={!!pending}
        onOpenChange={(open) => {
          if (!open) {
            setPending(null);
            setChangeFailed(false);
          }
        }}
      >
        <DialogContent>
          {pending ? (
            <>
              <DialogHeader>
                <DialogTitle>Change {pending.user.email}&apos;s role?</DialogTitle>
                <DialogDescription>
                  They&apos;ll get {roleLabel(pending.newRole)} access on their next
                  request.
                  {pending.newRole === "admin"
                    ? " Admin can manage every user and see every dashboard."
                    : ""}
                </DialogDescription>
              </DialogHeader>
              {changeFailed ? (
                <p
                  className="text-sm"
                  style={{ color: "var(--status-fail)" }}
                  data-testid="change-failed"
                >
                  Couldn&apos;t change the role. Try again — the change wasn&apos;t
                  saved.
                </p>
              ) : null}
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setPending(null);
                    setChangeFailed(false);
                  }}
                  disabled={mutation.isPending}
                >
                  Keep {roleLabel(pending.user.role)}
                </Button>
                <Button
                  onClick={() => mutation.mutate(pending)}
                  disabled={mutation.isPending}
                >
                  {mutation.isPending ? "Changing…" : "Change role"}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
