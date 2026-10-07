import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { PublicSchoolOut } from "@dl360/api-client";
import { SchoolProvider } from "@/components/school/school-context";
import { brandCss, brandTokens } from "@/lib/brand";
import { serverFetch } from "@/lib/server-api";

async function loadSchool(slug: string) {
  return serverFetch<PublicSchoolOut>(slug, "/api/public/school");
}

export async function generateMetadata({ params }: LayoutProps<"/s/[slug]">): Promise<Metadata> {
  const school = await loadSchool((await params).slug);
  return school
    ? { title: { default: school.name, template: `%s · ${school.name}` } }
    : { title: "School not found" };
}

/** Every page on a school's site: loads the school and applies its brand colours. */
export default async function SchoolLayout({ params, children }: LayoutProps<"/s/[slug]">) {
  const school = await loadSchool((await params).slug);
  if (!school) notFound();
  const tokens = brandTokens(school.branding.primary, school.branding.ink);
  return (
    <SchoolProvider school={school}>
      {tokens && <style>{brandCss(tokens)}</style>}
      {children}
    </SchoolProvider>
  );
}
