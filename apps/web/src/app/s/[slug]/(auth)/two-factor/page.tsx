"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  useAuthMe,
  useAuthTotpEnroll,
  useAuthTotpVerify,
  type NextStep,
  type TotpEnrollOut,
} from "@dl360/api-client";
import { Field, FormError } from "@/components/auth/field";
import { errorText, routeForStep, useGoToStep } from "@/components/auth/steps";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export default function TwoFactorPage() {
  const router = useRouter();
  const goTo = useGoToStep();
  const me = useAuthMe({ query: { retry: false } });
  const enroll = useAuthTotpEnroll();
  const verify = useAuthTotpVerify();
  const [setup, setSetup] = useState<TotpEnrollOut | null>(null);
  const [recovery, setRecovery] = useState<{ codes: string[]; next: NextStep } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const step = me.data?.data.next;
  const enrolling = step === "totp_enroll";

  useEffect(() => {
    if (me.isError) router.replace("/login");
    else if (step && step !== "totp_enroll" && step !== "totp_verify") router.replace(routeForStep[step]);
  }, [me.isError, step, router]);

  useEffect(() => {
    if (!enrolling || started.current) return;
    started.current = true;
    enroll.mutateAsync().then((r) => setSetup(r.data), (err) => setError(errorText(err)));
  }, [enrolling, enroll]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const code = String(new FormData(e.currentTarget).get("code")).trim();
    try {
      const res = await verify.mutateAsync({ data: { code } });
      if (res.data.recovery_codes?.length) {
        setRecovery({ codes: res.data.recovery_codes, next: res.data.next });
      } else {
        goTo(res.data.next);
      }
    } catch (err) {
      setError(errorText(err));
    }
  }

  if (recovery) {
    return (
      <div className="grid gap-4">
        <h2 className="text-2xl font-semibold tracking-tight">Save your recovery codes</h2>
        <p className="text-muted-foreground text-sm">
          If you lose your phone, each code lets you sign in once. Write them down or print
          this page and keep it somewhere safe. You won&apos;t see them again.
        </p>
        <ul className="bg-muted grid grid-cols-2 gap-2 rounded-lg p-4 font-mono text-sm">
          {recovery.codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <Button variant="brand" size="touch" onClick={() => goTo(recovery.next)}>
          I&apos;ve saved them, continue
        </Button>
      </div>
    );
  }

  if (!step) return <Skeleton className="h-64 w-full" />;

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">
          {enrolling ? "Set up two-step sign-in" : "Enter your sign-in code"}
        </h2>
        <p className="text-muted-foreground text-sm">
          {enrolling
            ? "Admins and bursars protect school data with an authenticator app (Google Authenticator, Microsoft Authenticator, or similar). Scan the code, then enter the 6 digits it shows."
            : "Open your authenticator app and enter the 6-digit code, or one of your recovery codes."}
        </p>
      </div>
      {enrolling &&
        (setup ? (
          <div className="grid justify-items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={setup.qr_svg_data_uri} alt="QR code for your authenticator app" className="size-48 rounded-md bg-white p-2" />
            <details className="text-muted-foreground text-xs">
              <summary className="cursor-pointer">Can&apos;t scan? Enter the key manually</summary>
              <code className="break-all">{new URL(setup.otpauth_uri).searchParams.get("secret")}</code>
            </details>
          </div>
        ) : (
          <Skeleton className="mx-auto size-48" />
        ))}
      <Field
        id="totp-code"
        name="code"
        label="Code"
        inputMode={enrolling ? "numeric" : "text"}
        autoComplete="one-time-code"
        maxLength={12}
        required
        autoFocus
      />
      <FormError message={error} />
      <Button type="submit" variant="brand" size="touch" disabled={verify.isPending}>
        {verify.isPending ? "Checking…" : "Continue"}
      </Button>
    </form>
  );
}
