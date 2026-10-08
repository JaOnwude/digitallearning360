"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  useFeesGetSetup,
  useFeesPutItems,
  useFeesPutSchedule,
  useFeesPutSettings,
  type FeeItemIO,
  type FeeSetupOut,
  type ScheduleCell,
} from "@dl360/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, CircleAlert, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Field, FormError } from "@/components/auth/field";
import { errorText } from "@/components/auth/steps";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toKobo } from "@/lib/money";

export default function FeeSetupPage() {
  const q = useFeesGetSetup({ query: { retry: false } });
  const setup = q.data?.data;
  return (
    <div className="grid max-w-5xl gap-6">
      <Link href="/fees" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> Fees
      </Link>
      <PageHeader title="Fee setup" description="What each class pays per term, and where parents send money. Issued invoices don't change; use a waiver or extra charge on the invoice instead." />
      {q.isError ? (
        <p className="text-muted-foreground">{errorText(q.error)}</p>
      ) : !setup ? (
        <Skeleton className="h-96" />
      ) : (
        // Keyed on the fetch time so each editor starts from the saved data after a save.
        <div key={q.dataUpdatedAt} className="grid gap-6">
          <ItemsCard setup={setup} />
          <ScheduleCard setup={setup} />
          <SettingsCard setup={setup} />
        </div>
      )}
    </div>
  );
}

function useSaved() {
  const queryClient = useQueryClient();
  return (data: FeeSetupOut) => {
    queryClient.setQueriesData({ predicate: (q) => q.queryKey[0] === "/api/fees/setup" }, { data, status: 200, headers: new Headers() });
    void queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/fees") });
  };
}

function ItemsCard({ setup }: { setup: FeeSetupOut }) {
  const save = useFeesPutItems();
  const saved = useSaved();
  const [items, setItems] = useState<FeeItemIO[]>(setup.items.length ? setup.items : [{ name: "Tuition", is_optional: false }]);
  const update = (i: number, patch: Partial<FeeItemIO>) => setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const removed = setup.items.filter((s) => !items.some((i) => i.id === s.id));
    if (removed.length && !confirm(`Remove ${removed.map((r) => r.name).join(", ")}? Their amounts in the schedule are deleted too.`)) return;
    const res = await withToast(save.mutateAsync({ data: items.filter((i) => i.name.trim()) }), "Fee items saved");
    if (res) saved(res.data);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Fee items</CardTitle>
        <CardDescription>Tuition, PTA levy, uniform… Optional items are listed but not added to every invoice.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3">
          {items.map((item, i) => (
            <div key={item.id ?? `new-${i}`} className="flex items-center gap-2">
              <Input value={item.name} onChange={(e) => update(i, { name: e.target.value })} aria-label="Fee item name" maxLength={100} className="flex-1" required />
              <label className="flex items-center gap-2 text-sm whitespace-nowrap">
                <Checkbox checked={item.is_optional ?? false} onCheckedChange={(v) => update(i, { is_optional: v === true })} /> Optional
              </label>
              <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${item.name || "item"}`} onClick={() => setItems(items.filter((_, j) => j !== i))}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setItems([...items, { name: "", is_optional: false }])}>
              <Plus /> Add item
            </Button>
            <Button type="submit" variant="brand" disabled={save.isPending}>Save items</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

const cellKey = (item: string, level: string, term: string) => `${item}|${level}|${term}`;

function ScheduleCard({ setup }: { setup: FeeSetupOut }) {
  const save = useFeesPutSchedule();
  const saved = useSaved();
  const [termId, setTermId] = useState(setup.terms.find((t) => t.is_current)?.id ?? setup.terms[0]?.id ?? "");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      setup.schedule
        .filter((c) => c.amount_kobo != null)
        .map((c) => [cellKey(c.fee_item_id, c.class_level_id, c.term_id), String((c.amount_kobo ?? 0) / 100)]),
    ),
  );
  const [error, setError] = useState<string | null>(null);
  const items = setup.items.filter((i): i is FeeItemIO & { id: string } => !!i.id);

  if (!items.length || !setup.levels.length || !setup.terms.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Amounts</CardTitle>
          <CardDescription>
            {!items.length ? "Save at least one fee item first." : "Set up classes and terms in School setup first."}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const cells: ScheduleCell[] = [];
    for (const item of items) {
      for (const level of setup.levels) {
        const raw = (values[cellKey(item.id, level.id, termId)] ?? "").trim();
        const kobo = raw ? toKobo(raw) : null;
        if (raw && kobo === null) return setError(`"${raw}" for ${item.name}, ${level.name} isn't an amount.`);
        cells.push({ fee_item_id: item.id, class_level_id: level.id, term_id: termId, amount_kobo: kobo || null });
      }
    }
    try {
      const res = await save.mutateAsync({ data: cells });
      toast.success("Amounts saved");
      saved(res.data);
    } catch (err) {
      setError(errorText(err));
    }
  }

  function copyToOtherTerms() {
    const next = { ...values };
    for (const term of setup.terms) {
      if (term.id === termId) continue;
      for (const item of items) for (const level of setup.levels) next[cellKey(item.id, level.id, term.id)] = values[cellKey(item.id, level.id, termId)] ?? "";
    }
    setValues(next);
    toast("Copied. Save each term to keep it.");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Amounts per term (₦)</CardTitle>
        <CardDescription>Leave a box empty if that class doesn&apos;t pay the item that term.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Tabs value={termId} onValueChange={(v) => setTermId(String(v))}>
            <TabsList>
              {setup.terms.map((t) => (
                <TabsTrigger key={t.id} value={t.id}>{t.label}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className="overflow-x-auto">
            <table className="text-sm">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-card py-2 pr-3 text-left font-medium">Item</th>
                  {setup.levels.map((l) => (
                    <th key={l.id} className="px-1 py-2 text-left font-medium">{l.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <th scope="row" className="sticky left-0 bg-card py-1 pr-3 text-left font-normal whitespace-nowrap">{item.name}</th>
                    {setup.levels.map((l) => {
                      const k = cellKey(item.id, l.id, termId);
                      return (
                        <td key={l.id} className="px-1 py-1">
                          <Input
                            value={values[k] ?? ""}
                            onChange={(e) => setValues({ ...values, [k]: e.target.value })}
                            inputMode="decimal"
                            className="w-28 text-right tabular-nums"
                            aria-label={`${item.name}, ${l.name}`}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <FormError message={error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="brand" disabled={save.isPending}>Save this term</Button>
            {setup.terms.length > 1 && (
              <Button type="button" variant="outline" onClick={copyToOtherTerms}>Copy to other terms</Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SettingsCard({ setup }: { setup: FeeSetupOut }) {
  const save = useFeesPutSettings();
  const saved = useSaved();
  const [withhold, setWithhold] = useState(setup.settings.withhold_results_for_debt ?? true);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const text = (name: string) => String(f.get(name) ?? "").trim() || null;
    const accountNumber = text("account_number");
    if (accountNumber && !/^\d{10}$/.test(accountNumber)) return setError("Account numbers (NUBAN) are 10 digits.");
    try {
      const res = await save.mutateAsync({
        data: {
          bank_name: text("bank_name"),
          account_name: text("account_name"),
          account_number: accountNumber,
          paystack_subaccount_code: text("paystack_subaccount_code"),
          withhold_results_for_debt: withhold,
        },
      });
      toast.success("Payment settings saved");
      saved(res.data);
    } catch (err) {
      setError(errorText(err));
    }
  }

  const s = setup.settings;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Payments</CardTitle>
        <CardDescription>Shown to parents on every invoice.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <Field id="bank_name" name="bank_name" label="Bank" defaultValue={s.bank_name ?? ""} placeholder="e.g. First Bank" />
          <Field id="account_number" name="account_number" label="Account number" defaultValue={s.account_number ?? ""} inputMode="numeric" maxLength={10} />
          <div className="sm:col-span-2">
            <Field id="account_name" name="account_name" label="Account name" defaultValue={s.account_name ?? ""} />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Field
              id="paystack_subaccount_code"
              name="paystack_subaccount_code"
              label="Paystack subaccount code"
              defaultValue={s.paystack_subaccount_code ?? ""}
              placeholder="ACCT_…"
              hint="Online payments settle into this subaccount. Paystack's fee is taken from the school's share."
            />
            <p className="flex items-center gap-2 text-sm">
              {setup.paystack_configured ? (
                <><CircleCheck className="text-success size-4" /> Online payment is available to parents.</>
              ) : (
                <><CircleAlert className="text-warning-foreground size-4" /> Online payment is off until Paystack is configured. Bank transfer still works.</>
              )}
            </p>
          </div>
          <label className="flex items-center justify-between gap-4 rounded-lg border p-3 sm:col-span-2">
            <span className="grid gap-0.5">
              <span className="text-sm font-medium">Withhold results while fees are owed</span>
              <span className="text-muted-foreground text-xs">Parents and students see the balance instead of the report card. You can exempt a student on their invoice.</span>
            </span>
            <Switch checked={withhold} onCheckedChange={setWithhold} />
          </label>
          <div className="sm:col-span-2">
            <FormError message={error} />
            <Button type="submit" variant="brand" disabled={save.isPending}>Save payment settings</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
