import { notFound } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { percent, weekToDateRange, humanizeStatement } from "@/lib/format";
import { Card, Eyebrow, MoverTable, Table } from "@/components/ui";
import { BackLink } from "@/components/trust";

export const dynamic = "force-dynamic";

export default async function ArchiveWindowPage({ params }: { params: { period: string } }) {
  const detail = await api.archiveWindow(params.period);
  if (!detail) notFound();

  return (
    <div className="space-y-8">
      <BackLink href="/archive">Archive</BackLink>

      <header className="rise-in">
        <Eyebrow>Closed observation window · {detail.period}</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          {weekToDateRange(detail.period)}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          A frozen snapshot: the Rising and Falling tables as they were computed for this week, and
          every forecast that was scored against what actually happened in it.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card eyebrow={detail.period} title="Rising">
          <MoverTable movers={detail.risers} empty="Nothing rose this period." />
        </Card>
        <Card eyebrow={detail.period} title="Falling">
          <MoverTable movers={detail.fallers} empty="Nothing fell this period." />
        </Card>
      </div>

      <Card eyebrow={`${detail.scored_forecasts.length} forecasts`} title="Scored against this window">
        {detail.scored_forecasts.length ? (
          <Table head={["Forecast", "Target", "Predicted", "Actual", "Accuracy", "Direction"]}>
            {detail.scored_forecasts.map((f) => (
              <tr key={f.id} className="border-b border-line/60 align-top last:border-0">
                <td className="max-w-md py-3 pr-4">
                  {f.statement ? (
                    <Link href={`/forecasts/${f.id}`} className="hover:text-proof">
                      {humanizeStatement(f.statement)}
                    </Link>
                  ) : (
                    <span className="text-muted">Forecast no longer available</span>
                  )}
                </td>
                <td className="py-3 pr-4 font-mono text-xs tabular-nums">
                  {f.target_period ? weekToDateRange(f.target_period) : "—"}
                </td>
                <td className="py-3 pr-4 font-mono tabular-nums">{f.predicted_value.toLocaleString()}</td>
                <td className="py-3 pr-4 font-mono tabular-nums">{f.actual_value.toLocaleString()}</td>
                <td className="py-3 pr-4 font-mono tabular-nums">{percent(f.accuracy_score)}</td>
                <td className="py-3 font-mono text-xs">
                  {f.direction_correct ? (
                    <span className="text-proof">correct</span>
                  ) : (
                    <span className="text-fail">missed</span>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <p className="text-sm text-muted">No forecast had this week as its target — nothing to score.</p>
        )}
      </Card>
    </div>
  );
}
