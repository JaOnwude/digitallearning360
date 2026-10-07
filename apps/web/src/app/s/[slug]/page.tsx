import { redirect } from "next/navigation";

/** The school's home address goes straight to the portal; the app shell sends guests to /login. */
export default function SchoolHome() {
  redirect("/dashboard");
}
