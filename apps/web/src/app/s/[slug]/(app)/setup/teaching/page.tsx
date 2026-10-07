"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  getResultsGetAssignmentsQueryKey,
  useResultsGetAssignments,
  useResultsSetFormTeacher,
  useResultsSetSubjectTeacher,
} from "@dl360/api-client";
import { ArrowLeft } from "lucide-react";
import { NativeSelect } from "@/components/kit/native-select";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Who teaches what: a form teacher per class, a teacher per class + subject. */
export default function TeachingPage() {
  const queryClient = useQueryClient();
  const q = useResultsGetAssignments();
  const setForm = useResultsSetFormTeacher();
  const setSubject = useResultsSetSubjectTeacher();
  const data = q.data?.data;

  function apply(res: unknown) {
    if (res) queryClient.setQueryData(getResultsGetAssignmentsQueryKey(), res);
  }

  const people = data?.teachers ?? [];
  const options = (
    <>
      <option value="">— Not assigned —</option>
      {people.map((t) => (
        <option key={t.user_id} value={t.user_id}>
          {t.full_name}
        </option>
      ))}
    </>
  );

  return (
    <div className="grid gap-6">
      <Link href="/setup" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> School setup
      </Link>
      <PageHeader
        title="Teaching"
        description="Give each class a form teacher and each subject a teacher. Teachers then see their classes under My classes."
      />
      {!data ? (
        <Skeleton className="h-96" />
      ) : data.arms.length === 0 ? (
        <p className="text-muted-foreground">No classes this session yet. Add arms in School setup.</p>
      ) : (
        data.arms.map((arm) => (
          <Card key={arm.arm_id}>
            <CardHeader>
              <CardTitle>{arm.label}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <label className="flex flex-wrap items-center gap-3 text-sm">
                <span className="w-44 font-medium">Form teacher</span>
                <NativeSelect
                  value={arm.form_teacher_user_id ?? ""}
                  onChange={async (e) =>
                    apply(
                      await withToast(
                        setForm.mutateAsync({ data: { arm_id: arm.arm_id, teacher_user_id: e.target.value || null } }),
                        "Form teacher saved",
                      ),
                    )
                  }
                  className="min-w-56"
                >
                  {options}
                </NativeSelect>
              </label>
              <div className="grid gap-2 sm:grid-cols-2">
                {arm.subjects.map((s) => (
                  <label key={s.subject_id} className="flex items-center gap-3 text-sm">
                    <span className="w-44 truncate" title={s.subject_name}>
                      {s.subject_name}
                    </span>
                    <NativeSelect
                      value={s.teacher_user_id ?? ""}
                      onChange={async (e) =>
                        apply(
                          await withToast(
                            setSubject.mutateAsync({
                              data: { arm_id: arm.arm_id, subject_id: s.subject_id, teacher_user_id: e.target.value || null },
                            }),
                          ),
                        )
                      }
                      className="min-w-0 flex-1"
                    >
                      {options}
                    </NativeSelect>
                  </label>
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
