import Link from "next/link";
import { api } from "@/lib/api";
import { shortDate, titleCase, humanizeStatement, weekToDateRange } from "@/lib/format";
import { Card, Empty, Eyebrow } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const data = await api.reports();

  if (!data || !data.items.length) {
    return <Empty title="No report generated yet" action="Run the loop to produce this period's reports." />;
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Report library</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Drafts, with the track record included
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Weekly and monthly reviews, an executive summary, and publishing drafts. Every one states
          the accuracy record alongside the forecast, including the misses.
        </p>
      </header>

      <Card>
        <ul className="divide-y divide-line/60">
          {data.items.map((report) => (
            <li key={report.id} className="py-4 first:pt-0 last:pb-0">
              <Link href={`/reports/${report.id}`} className="group block">
                <p className="text-eyebrow font-mono uppercase text-muted">
                  {titleCase(report.report_type)} · {weekToDateRange(report.period_start)} → {weekToDateRange(report.period_end)}
                </p>
                <p className="mt-1 font-display text-lg font-bold tracking-tight group-hover:text-proof">
                  {humanizeStatement(report.title)}
                </p>
                {report.subtitle ? <p className="mt-1 text-sm text-muted">{humanizeStatement(report.subtitle)}</p> : null}
                <p className="mt-1 font-mono text-xs text-muted">{shortDate(report.created_at)}</p>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
