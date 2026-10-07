"use client";

import { ParentLoginForm, StaffLoginForm, StudentLoginForm } from "@/components/auth/login-forms";
import { useSchool } from "@/components/school/school-context";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function LoginPage() {
  const school = useSchool();
  const studentsCanSignIn = school.sections.some((s) => s.student_login_enabled);

  return (
    <div className="grid gap-6">
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
        <p className="text-muted-foreground text-sm">Choose who you are to continue.</p>
      </div>
      {/* Parents are the largest group, so their tab comes first. */}
      <Tabs defaultValue="parent">
        <TabsList className="w-full">
          <TabsTrigger value="parent">Parent</TabsTrigger>
          {studentsCanSignIn && <TabsTrigger value="student">Student</TabsTrigger>}
          <TabsTrigger value="staff">Staff</TabsTrigger>
        </TabsList>
        <TabsContent value="parent" className="pt-4">
          <ParentLoginForm />
        </TabsContent>
        {studentsCanSignIn && (
          <TabsContent value="student" className="pt-4">
            <StudentLoginForm />
          </TabsContent>
        )}
        <TabsContent value="staff" className="pt-4">
          <StaffLoginForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}
