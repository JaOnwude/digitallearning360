"use client";

import { useState } from "react";
import {
  useResultsSaveComment,
  useResultsSavePromotion,
  useResultsSaveRatings,
  type ReportEntryOut,
  type StudentReportEntry,
} from "@dl360/api-client";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const RATING_LABEL = ["", "Very poor", "Poor", "Fair", "Good", "Excellent"];

/** One student at a time: trait ratings, comment boxes, promotion (R16a–c). */
export function ReportNotes({ data, onChanged }: { data: ReportEntryOut; onChanged: () => void }) {
  const [index, setIndex] = useState(0);
  const student = data.students[index];
  if (!student) return <p className="text-muted-foreground text-sm">No students in this class.</p>;

  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Previous student" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          <ChevronLeft />
        </Button>
        <select
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="border-input h-9 flex-1 rounded-lg border bg-transparent px-2 text-sm sm:max-w-xs"
          aria-label="Choose student"
        >
          {data.students.map((s, i) => (
            <option key={s.enrollment_id} value={i}>
              {s.full_name}
            </option>
          ))}
        </select>
        <Button variant="outline" size="icon" aria-label="Next student" disabled={index === data.students.length - 1} onClick={() => setIndex(index + 1)}>
          <ChevronRight />
        </Button>
        <span className="text-muted-foreground text-sm">
          {index + 1} / {data.students.length}
        </span>
      </div>
      <StudentNotes key={student.enrollment_id} data={data} student={student} onChanged={onChanged} />
    </div>
  );
}

function StudentNotes({ data, student, onChanged }: { data: ReportEntryOut; student: StudentReportEntry; onChanged: () => void }) {
  const saveRatings = useResultsSaveRatings();
  const saveComment = useResultsSaveComment();
  const savePromotion = useResultsSavePromotion();
  const [ratings, setRatings] = useState(student.ratings);
  const [error, setError] = useState<string | null>(null);


  async function rate(traitId: string, value: number) {
    const next = ratings[traitId] === value ? null : value;
    setRatings((r) => {
      const copy = { ...r };
      if (next === null) delete copy[traitId];
      else copy[traitId] = next;
      return copy;
    });
    try {
      await saveRatings.mutateAsync({ data: { enrollment_id: student.enrollment_id, ratings: [{ trait_id: traitId, value: next }] } });
      setError(null);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="grid gap-6">
      {error && <p className="text-destructive text-sm" role="alert">{error}</p>}
      {data.trait_groups.map((g) => (
        <section key={g.name} className="grid gap-2">
          <h3 className="text-sm font-semibold">{g.name}</h3>
          <ul className="divide-y rounded-lg border">
            {g.traits.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="min-w-40 flex-1 text-sm">{t.name}</span>
                <div className="flex gap-1" role="radiogroup" aria-label={t.name}>
                  {[1, 2, 3, 4, 5].map((v) => (
                    <button
                      key={v}
                      type="button"
                      role="radio"
                      aria-checked={ratings[t.id] === v}
                      title={RATING_LABEL[v]}
                      disabled={!data.can_rate}
                      onClick={() => rate(t.id, v)}
                      className={cn(
                        "size-9 rounded-md border text-sm font-medium transition-colors disabled:opacity-60",
                        ratings[t.id] === v ? "bg-brand text-brand-foreground border-transparent" : "hover:bg-muted",
                      )}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="text-muted-foreground -mt-4 text-xs">5 Excellent · 4 Good · 3 Fair · 2 Poor · 1 Very poor. Tap again to clear.</p>

      {data.slots.map((slot) => (
        <CommentBox key={slot.id} slotId={slot.id} label={slot.label} editable={slot.editable} initial={student.comments[slot.id] ?? ""} enrollmentId={student.enrollment_id} save={saveComment.mutateAsync} onSaved={onChanged} />
      ))}

      {data.term_number === 3 && (
        <section className="grid gap-2">
          <h3 className="text-sm font-semibold">Promotion</h3>
          <div className="flex gap-2">
            {[
              [true, "Promoted"],
              [false, "Not promoted"],
            ].map(([value, label]) => (
              <Button
                key={String(value)}
                variant={student.promoted === value ? "brand" : "outline"}
                disabled={!data.can_decide_promotion || savePromotion.isPending}
                onClick={async () => {
                  await savePromotion.mutateAsync({ data: { enrollment_id: student.enrollment_id, promoted: value as boolean } });
                  onChanged();
                }}
              >
                {label as string}
              </Button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function CommentBox(props: {
  slotId: string;
  label: string;
  editable: boolean;
  initial: string;
  enrollmentId: string;
  save: ReturnType<typeof useResultsSaveComment>["mutateAsync"];
  onSaved: () => void;
}) {
  const [text, setText] = useState(props.initial);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function persist() {
    if (text === props.initial) return;
    setState("saving");
    try {
      await props.save({ data: { enrollment_id: props.enrollmentId, slot_id: props.slotId, text } });
      setState("saved");
      props.onSaved();
    } catch {
      setState("error");
    }
  }

  return (
    <section className="grid gap-1.5">
      <label htmlFor={`c-${props.slotId}`} className="text-sm font-semibold">
        {props.label}
      </label>
      <Textarea
        id={`c-${props.slotId}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={persist}
        disabled={!props.editable}
        rows={2}
        maxLength={600}
        placeholder={props.editable ? "Write a short comment…" : "Written by the responsible staff member"}
      />
      <span className="text-muted-foreground text-xs">
        {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : state === "error" ? "Couldn't save. Try again." : props.editable ? "Saves when you click away." : ""}
      </span>
    </section>
  );
}
