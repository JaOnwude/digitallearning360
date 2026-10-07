"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { MeOut } from "@dl360/api-client";

const MeContext = createContext<MeOut | null>(null);

export function MeProvider({ me, children }: { me: MeOut; children: ReactNode }) {
  return <MeContext value={me}>{children}</MeContext>;
}

/** The signed-in user. Available on every page inside the app shell. */
export function useMe(): MeOut {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe must be used inside the app shell");
  return me;
}
