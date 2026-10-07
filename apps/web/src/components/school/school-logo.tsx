"use client";

import { cn } from "@/lib/utils";
import { useSchool } from "./school-context";

/** The school's crest, or its initials on the brand colour when no logo is set. */
export function SchoolLogo({ className }: { className?: string }) {
  const school = useSchool();
  const logo = school.branding.logo_url;
  if (logo) {
    // Plain <img>: logos are small, already sized, and may later come from object storage.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={logo} alt={`${school.name} crest`} className={cn("object-contain", className)} />;
  }
  const initials = school.name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
  return (
    <div
      aria-hidden
      className={cn(
        "bg-brand text-brand-foreground grid place-items-center rounded-md font-semibold",
        className,
      )}
    >
      {initials}
    </div>
  );
}
