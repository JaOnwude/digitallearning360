"use client";

import { useRouter } from "next/navigation";
import { startTransition } from "react";
import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Shown when a school page can't load, most often because the API is down or still
 * waking up (free hosting sleeps when idle). Catches errors from app/s/[slug]/layout.tsx.
 */
export default function SchoolError({ reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  // The failure happened on the server, so re-request it there, then re-render.
  const retry = () =>
    startTransition(() => {
      router.refresh();
      reset();
    });
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-xl font-semibold">We can&apos;t reach the school&apos;s server right now</h1>
      <p className="text-muted-foreground text-sm">
        It may be starting up. Please wait a few seconds and try again. If this keeps
        happening, contact the school.
      </p>
      <Button size="touch" onClick={retry}>
        <RotateCw /> Try again
      </Button>
    </main>
  );
}
