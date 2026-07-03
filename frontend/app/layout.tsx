import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Argus",
  description: "Enterprise intelligence platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <nav className="border-b border-slate-200 bg-white px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center gap-6">
            <span className="text-sm font-semibold text-slate-950">Argus</span>
            <div className="flex gap-4">
              <Link href="/query" className="text-sm text-slate-600 hover:text-slate-950">
                Query
              </Link>
              <Link href="/dashboard" className="text-sm text-slate-600 hover:text-slate-950">
                Dashboard
              </Link>
              <Link href="/ingest" className="text-sm text-slate-600 hover:text-slate-950">
                Ingest
              </Link>
              <Link href="/login" className="text-sm text-slate-600 hover:text-slate-950">
                Sign in
              </Link>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
