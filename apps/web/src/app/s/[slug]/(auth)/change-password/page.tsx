"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuthChangePassword, useAuthMe } from "@dl360/api-client";
import { Field, FormError } from "@/components/auth/field";
import { errorText, routeForStep, useGoToStep } from "@/components/auth/steps";
import { Button } from "@/components/ui/button";

export default function ChangePasswordPage() {
  const router = useRouter();
  const goTo = useGoToStep();
  const me = useAuthMe({ query: { retry: false } });
  const change = useAuthChangePassword();
  const [error, setError] = useState<string | null>(null);
  const step = me.data?.data.next;

  useEffect(() => {
    if (me.isError) router.replace("/login");
    else if (step && step !== "change_password") router.replace(routeForStep[step]);
  }, [me.isError, step, router]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const next = String(form.get("new_password"));
    if (next !== String(form.get("confirm"))) {
      setError("The two passwords don't match.");
      return;
    }
    try {
      const res = await change.mutateAsync({ data: { new_password: next } });
      goTo(res.data.next);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Choose your own password</h2>
        <p className="text-muted-foreground text-sm">
          You signed in with a temporary password. Pick a new one only you know.
        </p>
      </div>
      <Field
        id="new-password"
        name="new_password"
        label="New password"
        type="password"
        autoComplete="new-password"
        minLength={8}
        hint="At least 8 characters, not only numbers."
        required
        autoFocus
      />
      <Field id="confirm-password" name="confirm" label="Type it again" type="password" autoComplete="new-password" required />
      <FormError message={error} />
      <Button type="submit" variant="brand" size="touch" disabled={change.isPending}>
        {change.isPending ? "Saving…" : "Save password"}
      </Button>
    </form>
  );
}
