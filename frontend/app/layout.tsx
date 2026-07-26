import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SHIOS — Strategic Honesty Intelligence",
  description:
    "Counts before conclusions: trends, forecasts and recommendations with their evidence and their track record attached.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/trends", label: "Trends" },
  { href: "/predictions", label: "Forecasts" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/reports", label: "Reports" },
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
        <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-8 sm:px-8">
          <header className="mb-10 border-b border-line pb-6">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <Link href="/" className="font-display text-2xl font-bold tracking-tight">
                SHIOS
                <span className="ml-3 font-body text-sm font-normal text-muted">
                  Strategic Honesty Intelligence
                </span>
              </Link>
              <p className="font-mono text-xs text-muted">counts before conclusions</p>
            </div>
            <nav className="mt-5 flex flex-wrap gap-x-6 gap-y-2">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-eyebrow font-mono uppercase text-muted transition-colors hover:text-proof"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="mt-16 border-t border-line pt-5 font-mono text-xs text-muted">
            Every figure here traces to a document the system collected. Where it does not know, it
            says so.
          </footer>
        </div>
      </body>
    </html>
  );
}
