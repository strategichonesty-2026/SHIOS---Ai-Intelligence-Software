import { api, type Trend } from "@/lib/api";
import { signed, weekToDateRange } from "@/lib/format";
import { Card, DirectionTag, Empty, EvidenceLedger, Eyebrow, Sparkline, Table } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: { type?: string };
}) {
  const entityType = searchParams.type === "technology" ? "technology" : searchParams.type === "role" ? "role" : "skill";
  const [latest, explorer] = await Promise.all([
    api.latestTrends(entityType),
    api.explorer(entityType),
  ]);

  if (!latest || !latest.items.length) {
    return <Empty title="No trends computed" action="Collect documents first, then recompute trends." />;
  }

  const seriesByName = new Map((explorer?.series ?? []).map((series) => [series.name, series.values]));

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Trend explorer · week of {weekToDateRange(latest.period ?? "")}</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          What the documents actually mention
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          One count per entity per ISO week. No estimates, no smoothing, no model in the loop — the
          number is how many collected documents mentioned it.
        </p>
        <nav className="mt-4 flex gap-2">
          {["skill", "technology", "role"].map((type) => (
            <a
              key={type}
              href={`/trends?type=${type}`}
              className={`rounded-card border px-3 py-1 font-mono text-xs uppercase transition-colors ${
                type === entityType
                  ? "border-proof bg-proofSoft text-proof"
                  : "border-line text-muted hover:border-proof hover:text-proof"
              }`}
            >
              {type}
            </a>
          ))}
        </nav>
      </header>

      <Card eyebrow={`${explorer?.periods.length ?? 0} weeks observed`} title="Series">
        <Table head={["Signal", "History", "Latest", "Week change", "Evidence"]}>
          {latest.items.map((trend: Trend) => (
            <tr key={trend.id} className="border-b border-line/60 last:border-0">
              <td className="py-3 pr-4 font-medium">{trend.entity_name}</td>
              <td className="py-3 pr-4">
                <Sparkline values={seriesByName.get(trend.entity_name) ?? []} />
              </td>
              <td className="py-3 pr-4 font-mono tabular-nums">
                {trend.value.toFixed(0)}
                <span className="ml-1 text-xs text-muted font-sans">mentions</span>
              </td>
              <td className="py-3 pr-4">
                <DirectionTag direction={trend.direction} delta={trend.delta} />
                <span className="ml-2 font-mono text-xs text-muted tabular-nums">
                  {signed(trend.delta_pct)}%
                </span>
              </td>
              <td className="py-3">
                <EvidenceLedger count={trend.evidence_count} max={16} />
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
