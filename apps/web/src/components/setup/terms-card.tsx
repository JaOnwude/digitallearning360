"use client";

import { useState, type FormEvent } from "react";
import {
  useSetupCreateSession,
  useSetupMakeTermCurrent,
  useSetupUpdateTerm,
  type TermOut,
} from "@dl360/api-client";
import { withToast } from "@/components/kit/notify";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSetup } from "./use-setup";

const TERM_NAME = ["", "First term", "Second term", "Third term"];

export function TermsCard() {
  const { overview, apply } = useSetup();
  const createSession = useSetupCreateSession();
  const [name, setName] = useState("");
  if (!overview) return null;

  async function addSession(e: FormEvent) {
    e.preventDefault();
    const res = await withToast(createSession.mutateAsync({ data: { name } }), `Session ${name} added`);
    if (res) {
      apply(res);
      setName("");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sessions and terms</CardTitle>
        <CardDescription>
          The current term decides which results and fees people see. &ldquo;Next term begins&rdquo; is
          printed on report cards.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {overview.sessions.map((session) => (
          <div key={session.id} className="grid gap-2">
            <h3 className="text-sm font-medium">{session.name}</h3>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full min-w-[40rem] text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-left text-xs">
                  <tr>
                    <th className="p-2 font-medium">Term</th>
                    <th className="p-2 font-medium">Starts</th>
                    <th className="p-2 font-medium">Ends</th>
                    <th className="p-2 font-medium">Next term begins</th>
                    <th className="p-2" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {session.terms.map((term) => (
                    <TermRow key={term.id} term={term} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        <form onSubmit={addSession} className="flex gap-2 sm:max-w-sm">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. 2027/2028"
            aria-label="New session"
            pattern="\d{4}/\d{4}"
            required
          />
          <Button type="submit" variant="outline" disabled={createSession.isPending}>
            Add session
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function TermRow({ term }: { term: TermOut }) {
  const { apply } = useSetup();
  const update = useSetupUpdateTerm();
  const makeCurrent = useSetupMakeTermCurrent();

  async function setDate(field: "starts_on" | "ends_on" | "next_term_begins", value: string) {
    apply(
      await withToast(update.mutateAsync({ termId: term.id, data: { [field]: value || null } }), "Saved"),
    );
  }

  return (
    <tr>
      <td className="p-2">
        <span className="flex items-center gap-2">
          {TERM_NAME[term.number]}
          {term.is_current && <Badge className="bg-brand text-brand-foreground">Current</Badge>}
        </span>
      </td>
      {(["starts_on", "ends_on", "next_term_begins"] as const).map((field) => (
        <td key={field} className="p-2">
          <Input
            type="date"
            defaultValue={term[field] ?? ""}
            onBlur={(e) => e.target.value !== (term[field] ?? "") && setDate(field, e.target.value)}
            aria-label={`${TERM_NAME[term.number]} ${field.replaceAll("_", " ")}`}
            className="h-8 w-40"
          />
        </td>
      ))}
      <td className="p-2 text-right">
        {!term.is_current && (
          <Button
            size="sm"
            variant="outline"
            onClick={async () =>
              apply(await withToast(makeCurrent.mutateAsync({ termId: term.id }), "Current term changed"))
            }
          >
            Make current
          </Button>
        )}
      </td>
    </tr>
  );
}
