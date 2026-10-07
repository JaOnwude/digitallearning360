"use client";

import { useState, type FormEvent } from "react";
import {
  useAuthParentCode,
  useAuthParentVerify,
  useAuthStaffLogin,
  useAuthStudentLogin,
} from "@dl360/api-client";
import { Button } from "@/components/ui/button";
import { Field, FormError } from "./field";
import { errorText, useGoToStep } from "./steps";

export function StaffLoginForm() {
  const login = useAuthStaffLogin();
  const goTo = useGoToStep();
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    try {
      const res = await login.mutateAsync({
        data: { email: String(form.get("email")), password: String(form.get("password")) },
      });
      goTo(res.data.next);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field id="staff-email" name="email" label="Email" type="email" autoComplete="username" required />
      <Field
        id="staff-password"
        name="password"
        label="Password"
        type="password"
        autoComplete="current-password"
        required
      />
      <FormError message={error} />
      <Button type="submit" variant="brand" size="touch" disabled={login.isPending}>
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export function ParentLoginForm() {
  const sendCode = useAuthParentCode();
  const verify = useAuthParentVerify();
  const goTo = useGoToStep();
  const [email, setEmail] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    try {
      await sendCode.mutateAsync({ data: { email } });
      setCodeSent(true);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function submitCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const code = String(new FormData(e.currentTarget).get("code")).trim();
    try {
      const res = await verify.mutateAsync({ data: { email, code } });
      goTo(res.data.next);
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (!codeSent) {
    return (
      <form onSubmit={requestCode} className="grid gap-4">
        <Field
          id="parent-email"
          label="Your email"
          type="email"
          autoComplete="email"
          hint="Use the email address you gave the school."
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <FormError message={error} />
        <Button type="submit" variant="brand" size="touch" disabled={sendCode.isPending}>
          {sendCode.isPending ? "Sending…" : "Email me a sign-in code"}
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={submitCode} className="grid gap-4">
      <p className="text-muted-foreground text-sm">
        If <span className="text-foreground font-medium">{email}</span> is registered with the
        school, we&apos;ve sent it a 6-digit code. It expires in 10 minutes.
      </p>
      <Field
        id="parent-code"
        name="code"
        label="Sign-in code"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="\d{6}"
        maxLength={6}
        required
        autoFocus
      />
      <FormError message={error} />
      <Button type="submit" variant="brand" size="touch" disabled={verify.isPending}>
        {verify.isPending ? "Checking…" : "Sign in"}
      </Button>
      <Button type="button" variant="ghost" onClick={() => setCodeSent(false)}>
        Use a different email
      </Button>
    </form>
  );
}

export function StudentLoginForm() {
  const login = useAuthStudentLogin();
  const goTo = useGoToStep();
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    try {
      const res = await login.mutateAsync({
        data: {
          admission_no: String(form.get("admission_no")),
          password: String(form.get("password")),
        },
      });
      goTo(res.data.next);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field
        id="student-admission"
        name="admission_no"
        label="Admission number"
        autoComplete="username"
        autoCapitalize="characters"
        required
      />
      <Field
        id="student-password"
        name="password"
        label="Password"
        type="password"
        autoComplete="current-password"
        hint="First time? Use the password on the slip from your school."
        required
      />
      <FormError message={error} />
      <Button type="submit" variant="brand" size="touch" disabled={login.isPending}>
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
