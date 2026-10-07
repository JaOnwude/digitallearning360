"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, getAuthMeQueryKey, type NextStep } from "@dl360/api-client";

/** Where the browser goes after each login step the API reports. */
export const routeForStep: Record<NextStep, string> = {
  done: "/dashboard",
  totp_enroll: "/two-factor",
  totp_verify: "/two-factor",
  change_password: "/change-password",
};

/**
 * Navigate to the screen for `next`. Drops the cached "who am I" first: it describes the
 * session *before* this step, and the next page would otherwise act on stale state.
 */
export function useGoToStep() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return (next: NextStep) => {
    queryClient.removeQueries({ queryKey: getAuthMeQueryKey() });
    router.replace(routeForStep[next]);
  };
}

export function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Couldn't reach the school's server. Check your connection and try again.";
}
