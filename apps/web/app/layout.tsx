import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "ScriptGenie",
    template: "%s · ScriptGenie",
  },
  description:
    "Constraint-aware script ideation: structurally diverse plot variants that respect genre, audience rating, production budget and territory censorship constraints.",
  authors: [{ name: "Samarth D Kolur" }],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // `next-themes` writes the resolved theme onto <html> before paint, which
      // React then compares against the server-rendered markup and reports as a
      // hydration mismatch. The suppression is scoped to this element's own
      // attributes and is what the library documents; the alternatives are a
      // flash of the wrong theme, or not server-rendering at all.
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
