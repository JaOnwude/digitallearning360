"use client";

import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getStaffListStaffQueryKey,
  useSetupSetupOverview,
  useStaffAddStaff,
  useStaffListStaff,
  useStaffRemoveRole,
  type Role,
  type StaffCreatedOut,
} from "@dl360/api-client";
import { ShieldCheck, UserPlus, X } from "lucide-react";
import { Field, FormError } from "@/components/auth/field";
import { errorText } from "@/components/auth/steps";
import { NativeSelect } from "@/components/kit/native-select";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { ROLE_LABEL } from "@/components/shell/nav";
import { useMe } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const STAFF_ROLES: Role[] = ["teacher", "section_head", "bursar", "counsellor", "school_admin"];

export default function StaffPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const staff = useStaffListStaff();
  const remove = useStaffRemoveRole();
  const [open, setOpen] = useState(false);

  const refresh = () => queryClient.invalidateQueries({ queryKey: getStaffListStaffQueryKey() });

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Staff"
        description="Who can sign in as staff, and what they can do."
        actions={
          <Button variant="brand" onClick={() => setOpen(true)}>
            <UserPlus /> Add staff
          </Button>
        }
      />
      {staff.isPending ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Email</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead className="hidden md:table-cell">Two-step sign-in</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {staff.data?.data.map((s) => (
                <TableRow key={s.user_id}>
                  <TableCell className="font-medium">{s.full_name}</TableCell>
                  <TableCell className="text-muted-foreground hidden sm:table-cell">{s.email}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {s.roles.map((r) => (
                        <Badge key={`${r.role}-${r.section_id}`} variant="secondary" className="gap-1 pr-1">
                          {ROLE_LABEL[r.role]}
                          {!(s.user_id === me.user_id && r.role === "school_admin") && (
                            <button
                              type="button"
                              aria-label={`Remove ${ROLE_LABEL[r.role]} role from ${s.full_name}`}
                              className="hover:bg-foreground/10 rounded"
                              onClick={async () => {
                                if (!confirm(`Remove ${ROLE_LABEL[r.role]} from ${s.full_name}?`)) return;
                                await withToast(remove.mutateAsync({ userId: s.user_id, role: r.role }), "Role removed");
                                await refresh();
                              }}
                            >
                              <X className="size-3" />
                            </button>
                          )}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {s.two_factor_enabled ? (
                      <span className="text-success-ink flex items-center gap-1 text-sm">
                        <ShieldCheck className="size-4" /> On
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-sm">Not set up</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <AddStaffDialog open={open} onOpenChange={setOpen} onAdded={refresh} />
    </div>
  );
}

function AddStaffDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}) {
  const add = useStaffAddStaff();
  const overview = useSetupSetupOverview({ query: { enabled: open } });
  const [role, setRole] = useState<Role>("teacher");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<StaffCreatedOut | null>(null);

  function close(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setCreated(null);
      setError(null);
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const section = String(form.get("section_id") ?? "");
    try {
      const res = await add.mutateAsync({
        data: {
          full_name: String(form.get("full_name")),
          email: String(form.get("email")),
          role,
          section_id: section || null,
        },
      });
      setCreated(res.data);
      onAdded();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>{created.staff.full_name} added</DialogTitle>
              <DialogDescription>
                {created.temporary_password
                  ? "Give them this temporary password privately. It is shown only once; they'll choose their own at first sign-in."
                  : "They already had an account, so they sign in with their existing password."}
              </DialogDescription>
            </DialogHeader>
            {created.temporary_password && (
              <p className="bg-muted rounded-lg p-4 text-center font-mono text-lg tracking-wider">
                {created.temporary_password}
              </p>
            )}
            <Button onClick={() => close(false)}>Done</Button>
          </>
        ) : (
          <form onSubmit={submit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>Add staff</DialogTitle>
              <DialogDescription>They&apos;ll sign in with their email on the Staff tab.</DialogDescription>
            </DialogHeader>
            <Field id="staff-name" name="full_name" label="Full name" required minLength={2} />
            <Field id="staff-email" name="email" label="Email" type="email" required />
            <div className="grid gap-1.5">
              <Label htmlFor="staff-role">Role</Label>
              <NativeSelect id="staff-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {STAFF_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {role === "section_head" && (
              <div className="grid gap-1.5">
                <Label htmlFor="staff-section">Section they head</Label>
                <NativeSelect id="staff-section" name="section_id" required>
                  {overview.data?.data.sections.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
            {(role === "school_admin" || role === "bursar") && (
              <p className="text-muted-foreground text-xs">
                This role must set up two-step sign-in with an authenticator app at first sign-in.
              </p>
            )}
            <FormError message={error} />
            <Button type="submit" variant="brand" disabled={add.isPending}>
              {add.isPending ? "Adding…" : "Add staff"}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
