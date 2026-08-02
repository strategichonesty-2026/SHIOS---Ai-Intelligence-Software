import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SHIOS — Strategic Honesty Intelligence",
  description:
    "Counts before conclusions: trends, forecasts and recommendations with their evidence and their track record attached.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/trends", label: "Trends" },
  { href: "/forecasts", label: "Forecasts" },
  { href: "/archive", label: "Archive" },
  { href: "/jobs", label: "Jobs" },
  { href: "/evidence", label: "Evidence" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/reports", label: "Reports" },
  { href: "/sources", label: "Sources" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-5 sm:px-8 sm:py-8">
          <header className="mb-6 border-b border-line pb-4 sm:mb-10 sm:pb-6">
            <div className="flex items-center justify-between gap-3">
              <Link href="/" className="font-display text-lg font-bold tracking-tight sm:text-2xl">
                SHIOS
                <span className="ml-2 font-body text-xs font-normal text-muted sm:ml-3 sm:text-sm">
                  Strategic Honesty Intelligence
                </span>
              </Link>
              <p className="hidden font-mono text-xs text-muted sm:block">counts before conclusions</p>
            </div>
            {/* Mobile: horizontally scrollable pill nav */}
            <nav className="mt-3 flex overflow-x-auto pb-1 gap-1 sm:mt-5 sm:flex-wrap sm:gap-x-6 sm:gap-y-2 sm:overflow-visible sm:pb-0">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="shrink-0 rounded-full border border-line px-3 py-1.5 font-mono text-[10px] uppercase text-muted transition-colors hover:border-proof hover:text-proof active:bg-proofSoft sm:rounded-none sm:border-0 sm:px-0 sm:py-0 sm:text-eyebrow"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="mt-12 border-t border-line pt-4 font-mono text-xs text-muted sm:mt-16 sm:pt-5">
            Every figure here traces to a document the system collected. Where it does not know, it
            says so.
          </footer>
        </div>
      </body>
    </html>
  );
}
