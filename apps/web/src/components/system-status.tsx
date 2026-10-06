"use client";

import { ApiError, useHealthReadiness, type Readiness } from "@dl360/api-client";

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2.5 rounded-full ${ok ? "bg-success" : "bg-destructive"}`}
    />
  );
}

/** Shows whether the web app can reach the API, and the API its database and Redis. */
export function SystemStatus() {
  const { data, error, isPending } = useHealthReadiness();

  if (isPending) return <p className="text-muted-foreground text-sm">Checking services…</p>;

  // /readyz returns 503 with the same body when a dependency is down.
  const readiness: Readiness | undefined =
    data?.data ?? (error instanceof ApiError ? (error.body as Readiness) : undefined);

  const rows = [
    { label: "API", ok: Boolean(readiness) },
    { label: "Database", ok: readiness?.database ?? false },
    { label: "Redis", ok: readiness?.redis ?? false },
  ];

  return (
    <ul className="grid gap-2 text-sm" aria-label="Service status">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-2">
          <Dot ok={r.ok} />
          <span>{r.label}</span>
          <span className="text-muted-foreground">{r.ok ? "connected" : "unreachable"}</span>
        </li>
      ))}
    </ul>
  );
}
