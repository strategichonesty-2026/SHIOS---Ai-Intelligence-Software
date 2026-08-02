import Link from "next/link";
import { api } from "@/lib/api";
import { weekToDateRange } from "@/lib/format";
import { Card, Empty, Eyebrow, Table } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function ArchivePage() {
  const archive = await api.archive();

  if (!archive || !archive.items.length) {
    return (
      <Empty
        title="No closed observation windows yet"
        action="An observation window closes once a newer one has been computed. Run more collection loops over time to build up history here."
      />
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Archive</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Closed observation windows
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Each row is a past week, frozen as it was computed at the time — its Rising and Falling
          tables, plus the forecasts that were scored against it.
        </p>
      </header>

      <Card eyebrow={`${archive.items.length} windows`} title="Windows">
        <Table head={["Window", "Tracked signals", "Forecasts scored", ""]}>
          {archive.items.map((item) => (
            <tr key={item.period} className="border-b border-line/60 last:border-0">
              <td className="py-2 pr-4">
                <Link href={`/archive/${encodeURIComponent(item.period)}`} className="hover:text-proof">
                  {weekToDateRange(item.period)}
                </Link>
                <p className="mt-1 font-mono text-xs text-muted">{item.period}</p>
              </td>
              <td className="py-2 pr-4 font-mono tabular-nums">{item.trend_count}</td>
              <td className="py-2 pr-4 font-mono tabular-nums">{item.scored_forecasts}</td>
              <td className="py-2">
                <Link
                  href={`/archive/${encodeURIComponent(item.period)}`}
                  className="font-mono text-xs text-proof hover:underline"
                >
                  View →
                </Link>
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
