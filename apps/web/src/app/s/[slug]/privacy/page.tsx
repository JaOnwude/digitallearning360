"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useSchool } from "@/components/school/school-context";

/**
 * Privacy notice (Nigeria Data Protection Act 2023; spec "Security baseline").
 * The school is the data controller; DigitalLearning360 processes data on its behalf.
 * Retention periods below are the platform defaults; a school can publish stricter ones.
 */
export default function PrivacyPage() {
  const school = useSchool();
  return (
    <main className="mx-auto grid w-full max-w-2xl gap-6 px-4 py-10 text-sm leading-relaxed sm:px-6">
      <Link href="/login" className="text-muted-foreground flex w-fit items-center gap-1 hover:underline">
        <ArrowLeft className="size-4" /> Sign in
      </Link>
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">How {school.name} uses your data</h1>
        <p className="text-muted-foreground">Privacy notice under the Nigeria Data Protection Act 2023.</p>
      </header>

      <Section title="Who is responsible">
        {school.name} decides what student and family data is collected and why (the
        &ldquo;data controller&rdquo;). DigitalLearning360 runs this portal for the school and
        uses the data only to provide it (the &ldquo;data processor&rdquo;).
      </Section>

      <Section title="What we hold">
        <ul className="list-disc space-y-1 pl-5">
          <li>Students: name, admission number, class, date of birth and gender where given, scores, report cards, attendance.</li>
          <li>Parents and guardians: name, relationship, email address and phone number.</li>
          <li>Staff: name, email address, role and the classes they teach.</li>
          <li>Fees: invoices, payments, receipts and any bank-transfer receipts you upload.</li>
          <li>Security records: sign-in times and IP addresses, and an audit log of changes to results and payments.</li>
        </ul>
      </Section>

      <Section title="Why">
        To run the school: record and publish results, issue invoices and receipts, take
        payments, keep parents informed, and keep the portal secure. The legal basis is the
        school&apos;s contract with each family and its legitimate interest in running the school.
        We do not sell data or use it for advertising.
      </Section>

      <Section title="Who else sees it">
        <ul className="list-disc space-y-1 pl-5">
          <li>Paystack, if you pay online (it receives the amount, invoice number and your email).</li>
          <li>Our email provider, to send sign-in codes and notices.</li>
          <li>Our hosting providers, which store the data securely in Europe on our behalf.</li>
        </ul>
        Anyone scanning the QR code on a report card sees only the student&apos;s name, the
        term, and whether the card is genuine.
      </Section>

      <Section title="How long we keep it">
        Results and report cards are kept for the life of the school&apos;s records, because
        former students ask for them years later. Fee records are kept for six years, as
        Nigerian tax law requires. Transfer-receipt images are deleted one year after the
        payment is reviewed. Sign-ins and changes to results and payments are kept in a
        tamper-proof audit log for as long as the records they protect.
      </Section>

      <Section title="Your rights">
        You can ask to see the data held about you or your child, have it corrected, or ask
        for it to be deleted where the law allows. Ask the school office; the school will
        respond within 30 days. You can also complain to the Nigeria Data Protection Commission.
      </Section>

      <Section title="Security">
        Passwords are never stored in readable form; school staff who manage results or money
        must use two-step sign-in; data is encrypted in transit; and each school&apos;s data is
        kept separate from every other school&apos;s.
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-2">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="text-muted-foreground grid gap-2">{children}</div>
    </section>
  );
}
