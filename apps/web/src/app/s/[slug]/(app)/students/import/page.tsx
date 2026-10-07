"use client";

import Link from "next/link";
import { useState, type ChangeEvent } from "react";
import { useStudentsImportStudents, type ImportResultOut } from "@dl360/api-client";
import { CheckCircle2, Download, FileWarning, Upload } from "lucide-react";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** Upload → preview problems by row → import the valid rows (spec R11, AC10). */
export default function ImportStudentsPage() {
  const importer = useStudentsImportStudents();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResultOut | null>(null);
  const [done, setDone] = useState<ImportResultOut | null>(null);

  async function check(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setPreview(null);
    setDone(null);
    if (!f) return;
    const res = await withToast(importer.mutateAsync({ data: { file: f, dry_run: true } }));
    if (res) setPreview(res.data);
  }

  async function runImport() {
    if (!file) return;
    const res = await withToast(
      importer.mutateAsync({ data: { file, dry_run: false } }),
      "Import finished",
    );
    if (res) {
      setDone(res.data);
      setPreview(null);
    }
  }

  return (
    <div className="grid max-w-4xl gap-6">
      <PageHeader
        title="Import students"
        description="Upload a CSV saved from Excel or Google Sheets. Nothing is saved until you confirm."
      />

      <Card>
        <CardHeader>
          <CardTitle>1. Get the template</CardTitle>
          <CardDescription>
            Required columns: admission_no, first_name, last_name, class (e.g. JSS1) and arm (e.g.
            A). Parent details are optional; brothers and sisters with the same parent email or
            phone share one parent account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <a href="/api/students/import-template" className={buttonVariants({ variant: "outline" })}>
            <Download /> Download template
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Upload and check</CardTitle>
          <CardDescription>Every row is checked first. Fix problems in your spreadsheet and upload again, or import the good rows now.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <label className={buttonVariants({ variant: "brand", className: "w-fit cursor-pointer" })}>
            <Upload /> {file ? "Choose another file" : "Choose CSV file"}
            <input type="file" accept=".csv,text/csv" className="sr-only" onChange={check} />
          </label>
          {file && <p className="text-muted-foreground text-sm">{file.name}</p>}
          {importer.isPending && <p className="text-sm">Checking…</p>}

          {preview && (
            <div className="grid gap-4">
              <div className="flex flex-wrap gap-6 text-sm">
                <p>
                  <span className="text-2xl font-semibold">{preview.valid_rows}</span> of {preview.total_rows} rows ready
                </p>
                {preview.errors.length > 0 && (
                  <p className="text-destructive flex items-center gap-1">
                    <FileWarning className="size-4" />
                    {new Set(preview.errors.map((e) => e.row)).size} row(s) have problems
                  </p>
                )}
              </div>
              {preview.errors.length > 0 && (
                <div className="max-h-96 overflow-y-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-20">Row</TableHead>
                        <TableHead className="w-40">Column</TableHead>
                        <TableHead>Problem</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.errors.map((e, i) => (
                        <TableRow key={i}>
                          <TableCell>{e.row}</TableCell>
                          <TableCell className="font-mono text-xs">{e.column ?? "—"}</TableCell>
                          <TableCell>{e.message}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              {preview.valid_rows > 0 && (
                <Button variant="brand" className="w-fit" onClick={runImport} disabled={importer.isPending}>
                  Import {preview.valid_rows} student{preview.valid_rows === 1 ? "" : "s"}
                  {preview.errors.length > 0 && " (skip rows with problems)"}
                </Button>
              )}
            </div>
          )}

          {done && (
            <div className="bg-success/10 grid gap-2 rounded-lg p-4 text-sm">
              <p className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="text-success size-5" /> {done.students_created} students imported
              </p>
              <p className="text-muted-foreground">
                {done.guardians_created} parent records created, {done.guardians_linked} parent links made.
                {done.errors.length > 0 && ` ${new Set(done.errors.map((e) => e.row)).size} row(s) were skipped.`}
              </p>
              <Link href="/students" className="font-medium underline">
                View students
              </Link>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
