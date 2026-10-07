/** The product's own site (bare domain). School portals live on {school}.<domain>. */
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-6 py-16">
      <p className="text-brand-ink text-sm font-medium tracking-wide uppercase">DigitalLearning360</p>
      <h1 className="text-3xl font-semibold tracking-tight text-balance">
        School management for Nigerian schools
      </h1>
      <p className="text-muted-foreground">
        Results and report cards, fees and payments, attendance and CBT, from creche to SS3.
        Each school gets its own branded portal for parents, students and staff.
      </p>
    </main>
  );
}
