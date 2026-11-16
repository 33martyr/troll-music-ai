import type { Metadata } from "next";
import { Geist, Geist_Mono, Unbounded } from "next/font/google";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const unbounded = Unbounded({ variable: "--font-unbounded", subsets: ["latin"], weight: ["600", "800"] });

export const metadata: Metadata = {
  title: { default: "TROLL-MUSIC-AI", template: "%s · TROLL-MUSIC-AI" },
  description: "Turn any roast into a banger. Generate lyrics, beats, songs and music videos with AI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${unbounded.variable} antialiased`}>
      <body className="min-h-dvh">
        <Suspense>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}
