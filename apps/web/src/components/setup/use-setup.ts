"use client";

import { useQueryClient } from "@tanstack/react-query";
import { getSetupSetupOverviewQueryKey, useSetupSetupOverview } from "@dl360/api-client";

/** The setup overview plus a way to swap in the fresh copy every setup mutation returns. */
export function useSetup() {
  const queryClient = useQueryClient();
  const query = useSetupSetupOverview();
  function apply(response: unknown) {
    if (response) queryClient.setQueryData(getSetupSetupOverviewQueryKey(), response);
  }
  return { overview: query.data?.data, isPending: query.isPending, error: query.error, apply };
}
