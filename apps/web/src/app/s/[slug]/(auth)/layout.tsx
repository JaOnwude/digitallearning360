import { AuthFrame } from "@/components/auth/auth-frame";

export default function AuthLayout({ children }: LayoutProps<"/s/[slug]">) {
  return <AuthFrame>{children}</AuthFrame>;
}
