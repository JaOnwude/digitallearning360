"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Server-sent events from /api/events (spec R28). Events are hints: on any of them the
 * matching data is re-fetched, so a payment confirmed elsewhere shows up within seconds.
 * The browser's EventSource reconnects by itself if the connection drops.
 */
export function useLiveUpdates(enabled: boolean) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events");
    const refresh = () => {
      // Fee and result views read from these endpoints; refetch whichever are on screen.
      void queryClient.invalidateQueries({
        predicate: (q) => {
          const key = String(q.queryKey[0] ?? "");
          return key.startsWith("/api/fees") || key.startsWith("/api/portal");
        },
      });
    };
    for (const name of ["invoice.updated", "proof.reviewed", "proof.submitted"]) {
      source.addEventListener(name, refresh);
    }
    return () => source.close();
  }, [enabled, queryClient]);
}
