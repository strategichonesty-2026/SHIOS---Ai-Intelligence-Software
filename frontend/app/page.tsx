import Link from "next/link";
import { api, type Trend } from "@/lib/api";
import { reliabilityBand } from "@/lib/intelligence";
import { ReliabilityBadge } from "@/components/trust";
import { percent, signed, weekToDateRange } from "@/lib/format";
import { Card, DirectionTag, Empty, EvidenceLedger, Eyebrow, Stat, Table } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const overview = await api.overview();

  if (!overview || !overview.window.latest_period) {
    return (
      <Empty
        title="No intelligence collected yet"
        action="Run one full loop to collect documents, compute trends and publish forecasts."
      />
    );
  }

  const { accuracy, counts, window } = overview;
  const band = reliabilityBand(accuracy.mean_calibration_delta);
  const trackRecord =
    accuracy.scored === 0
      ? "No forecast has reached its expiration date yet. Nothing here is proven."
      : `${accuracy.scored} forecasts scored against what actually happened.`;

  return (
    <div className="space-y-8">
      <section className="rise-in">
        <Eyebrow>
          Observation window {weekToDateRange(window.first_period ?? "")} → {weekToDateRange(window.latest_period ?? "")}
        </Eyebrow>
        <h1 className="mt-2 max-w-3xl font-display text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
          The system publishes its forecasts and its misses on the same page.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">{trackRecord}</p>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Link href="/forecasts" className="block transition-colors hover:border-proof">
          <Stat
            label="Forecast accuracy →"
            value={percent(accuracy.mean_accuracy)}
            note={`across ${accuracy.scored} scored forecasts`}
          />
        </Link>
        <Stat
          label="Direction called right"
          value={percent(accuracy.direction_hit_rate)}
          note="up, down or flat"
        />
        <div className="rounded-card border border-line bg-surface px-4 py-3">
          <Eyebrow>Confidence reliability</Eyebrow>
          <div className="mt-2">
            <ReliabilityBadge label={band.label} tone={band.tone} />
          </div>
          <p
            className="mt-2 text-xs text-muted"
            title="This measures how closely the system's confidence matched actual outcomes. Smaller differences indicate more reliable forecasting."
          >
            {band.meaning}
          </p>
        </div>
        <Link href="/evidence" className="block transition-colors hover:border-proof">
          <Stat
            label="Evidence base →"
            value={counts.documents.toLocaleString()}
            note={`${counts.tracked_entities} entities tracked`}
          />
        </Link>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card eyebrow="This week" title="Rising">
          <MoverTable movers={overview.risers} empty="Nothing rose this period." />
        </Card>
        <Card eyebrow="This week" title="Falling">
          <MoverTable movers={overview.fallers} empty="Nothing fell this period." />
        </Card>
      </div>

      <Card eyebrow="Standing caveat" title="What this cannot tell you">
        <ul className="space-y-2 text-sm text-muted">
          <li>
            It counts job postings, not hires. Posting volume leads actual hiring by weeks and
            overstates churn.
          </li>
          <li>
            It only sees the sources it is configured to read. Everything else is absent, which is
            not the same as zero.
          </li>
          <li>
            Forecasts are linear extrapolations. By construction they will miss an inflection point,
            and the accuracy figure above includes those misses.
          </li>
        </ul>
      </Card>
    </div>
  );
}

function MoverTable({ movers, empty }: { movers: Trend[]; empty: string }) {
  if (!movers.length) {
    return <p className="text-sm text-muted">{empty}</p>;
  }
  return (
    <Table head={["Signal", "Count", "Change", "Evidence"]}>
      {movers.map((trend) => (
        <tr key={trend.id} className="border-b border-line/60 last:border-0">
          <td className="py-2 pr-4">
            <span className="font-medium">{trend.entity_name}</span>
            <span className="ml-2 font-mono text-xs text-muted">{trend.entity_type}</span>
          </td>
          <td className="py-2 pr-4 font-mono tabular-nums">{trend.value.toFixed(0)}</td>
          <td className="py-2 pr-4">
            <DirectionTag direction={trend.direction} delta={trend.delta} />
            <span className="ml-2 font-mono text-xs text-muted tabular-nums">
              {signed(trend.delta_pct)}%
            </span>
          </td>
          <td className="py-2">
            <EvidenceLedger count={trend.evidence_count} max={12} />
          </td>
        </tr>
      ))}
    </Table>
  );
}
