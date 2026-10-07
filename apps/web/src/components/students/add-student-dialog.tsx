"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useStudentsCreateStudent, type Gender } from "@dl360/api-client";
import { Field, FormError } from "@/components/auth/field";
import { errorText } from "@/components/auth/steps";
import { NativeSelect } from "@/components/kit/native-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ArmOptions, HouseOptions } from "./arm-options";

export function AddStudentDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useStudentsCreateStudent();
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const text = (k: string) => String(f.get(k) ?? "").trim() || null;
    const guardianName = text("guardian_name");
    try {
      const res = await create.mutateAsync({
        data: {
          admission_no: String(f.get("admission_no")),
          first_name: String(f.get("first_name")),
          middle_name: text("middle_name"),
          last_name: String(f.get("last_name")),
          gender: (text("gender") as Gender | null) ?? null,
          date_of_birth: text("date_of_birth"),
          arm_id: String(f.get("arm_id")),
          house_id: text("house_id"),
          guardian: guardianName
            ? {
                full_name: guardianName,
                email: text("guardian_email"),
                phone: text("guardian_phone"),
                relationship: text("guardian_relationship"),
              }
            : null,
        },
      });
      onOpenChange(false);
      router.push(`/students/${res.data.id}`);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add a student</DialogTitle>
            <DialogDescription>For many students at once, use Import CSV.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="s-adm" name="admission_no" label="Admission number" required />
            <div className="grid gap-1.5">
              <Label htmlFor="s-arm">Class</Label>
              <NativeSelect id="s-arm" name="arm_id" required className="h-11">
                <ArmOptions />
              </NativeSelect>
            </div>
            <Field id="s-first" name="first_name" label="First name" required />
            <Field id="s-last" name="last_name" label="Surname" required />
            <Field id="s-middle" name="middle_name" label="Other names" />
            <div className="grid gap-1.5">
              <Label htmlFor="s-gender">Gender</Label>
              <NativeSelect id="s-gender" name="gender" className="h-11" defaultValue="">
                <option value="">—</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </NativeSelect>
            </div>
            <Field id="s-dob" name="date_of_birth" label="Date of birth" type="date" />
            <div className="grid gap-1.5">
              <Label htmlFor="s-house">House</Label>
              <NativeSelect id="s-house" name="house_id" className="h-11" defaultValue="">
                <option value="">—</option>
                <HouseOptions />
              </NativeSelect>
            </div>
          </div>
          <fieldset className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2">
            <legend className="px-1 text-sm font-medium">Parent / guardian</legend>
            <Field id="g-name" name="guardian_name" label="Name" />
            <Field id="g-rel" name="guardian_relationship" label="Relationship" placeholder="Mother" />
            <Field id="g-email" name="guardian_email" label="Email" type="email" hint="Used to sign in to the parent portal." />
            <Field id="g-phone" name="guardian_phone" label="Phone" inputMode="tel" placeholder="0803 123 4567" />
          </fieldset>
          <FormError message={error} />
          <Button type="submit" variant="brand" disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Add student"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
