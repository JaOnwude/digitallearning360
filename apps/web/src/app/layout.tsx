import type { Metadata } from "next";
import { connection } from "next/server";
import { Geist, Geist_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "DigitalLearning360", template: "%s · DigitalLearning360" },
  description: "School management for Nigerian schools: results, fees, attendance and CBT.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Render per request so the CSP nonce (src/proxy.ts) reaches every script tag.
  await connection();
  return (
    <html lang="en-NG" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
