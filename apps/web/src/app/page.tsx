import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-8 px-6 py-16">
      <div className="space-y-2">
        <p className="text-brand-ink text-sm font-medium tracking-wide uppercase">
          DigitalLearning360
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance">
          School management for Nigerian schools
        </h1>
        <p className="text-muted-foreground">
          Results, report cards, fees and payments, attendance and CBT, from creche to SS3.
        </p>
      </div>
      <section className="bg-card rounded-lg border p-5">
        <h2 className="mb-3 text-sm font-medium">Development status</h2>
        <SystemStatus />
      </section>
    </main>
  );
}
