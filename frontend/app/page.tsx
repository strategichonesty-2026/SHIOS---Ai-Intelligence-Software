import Link from "next/link";
import { api } from "@/lib/api";
import { reliabilityBand } from "@/lib/intelligence";
import { ReliabilityBadge } from "@/components/trust";
import { percent, weekToDateRange } from "@/lib/format";
import { Card, Empty, Eyebrow, MoverTable, Stat } from "@/components/ui";

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
  const thisWeekLabel = `This week (${weekToDateRange(window.latest_period ?? "")})`;
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

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
            note={`job postings analyzed · ${counts.tracked_entities} entities tracked`}
          />
        </Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card eyebrow={thisWeekLabel} title="Rising">
          <MoverTable movers={overview.risers} empty="Nothing rose this period." />
        </Card>
        <Card eyebrow={thisWeekLabel} title="Falling">
          <MoverTable movers={overview.fallers} empty="Nothing fell this period." />
        </Card>
      </div>

      <Card eyebrow="Standing caveat" title="What this can't tell you (and why that's okay)">
        <ul className="space-y-2 text-sm text-muted">
          <li>
            We count job posts, not hires — postings move faster than actual hiring, so treat this
            as an early signal, not a final number.
          </li>
          <li>
            We only see the sources we're connected to — "not in our data" isn't the same as "not
            happening."
          </li>
          <li>
            Our forecasts are straight-line projections — they're built to miss sudden turns, and we
            count those misses against ourselves in the accuracy score above.
          </li>
        </ul>
      </Card>
    </div>
  );
}
