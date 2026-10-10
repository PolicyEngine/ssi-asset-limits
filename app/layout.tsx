import type { Metadata, Viewport } from "next";
import AppShell from "@/src/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSI asset limits | PolicyEngine",
  description:
    "PolicyEngine analysis of removing Supplemental Security Income asset limits.",
  authors: [{ name: "PolicyEngine" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
