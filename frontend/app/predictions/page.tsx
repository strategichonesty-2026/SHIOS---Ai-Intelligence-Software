import { api, type Prediction } from "@/lib/api";
import { percent, shortDate } from "@/lib/format";
import { Card, ConfidenceBar, Empty, EvidenceLedger, Eyebrow, Stat, Table } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function PredictionsPage() {
  const [predictions, accuracy] = await Promise.all([api.predictions(), api.accuracy()]);

  if (!predictions || !predictions.items.length) {
    return <Empty title="No forecast has been published" action="Run the loop to fit and publish forecasts." />;
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Forecast register</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Every forecast carries a review date and a score
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Forecasts are immutable once published. When the target period arrives, the system scores
          itself against the observed count and adjusts the confidence it will claim next time.
        </p>
      </header>

      {accuracy ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Scored" value={String(accuracy.scored)} note="forecasts past expiry" />
          <Stat label="Mean accuracy" value={percent(accuracy.mean_accuracy)} note="1.00 is exact" />
          <Stat
            label="Direction hit rate"
            value={percent(accuracy.direction_hit_rate)}
            note="the number that survives volatility"
          />
        </div>
      ) : null}

      <Card eyebrow="Open" title="Published forecasts">
        <Table head={["Statement", "Target", "Confidence", "Review by", "Evidence"]}>
          {predictions.items.map((prediction: Prediction) => (
            <tr key={prediction.id} className="border-b border-line/60 align-top last:border-0">
              <td className="max-w-md py-3 pr-4">{prediction.statement}</td>
              <td className="py-3 pr-4 font-mono text-xs tabular-nums">{prediction.target_period}</td>
              <td className="py-3 pr-4">
                <ConfidenceBar confidence={prediction.confidence} />
              </td>
              <td className="py-3 pr-4 font-mono text-xs text-muted tabular-nums">
                {shortDate(prediction.review_date)}
              </td>
              <td className="py-3">
                <EvidenceLedger count={prediction.evidence_count} max={12} />
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {accuracy?.calibration?.length ? (
        <Card eyebrow="Learning" title="How confidence is being corrected">
          <Table head={["Slice", "Samples", "Mean accuracy", "Calibration delta", "Applied multiplier"]}>
            {accuracy.calibration.map((row) => (
              <tr key={`${row.metric}-${row.entity_type}`} className="border-b border-line/60 last:border-0">
                <td className="py-2 pr-4 font-mono text-xs">{row.entity_type}</td>
                <td className="py-2 pr-4 font-mono tabular-nums">{row.samples}</td>
                <td className="py-2 pr-4 font-mono tabular-nums">{row.mean_accuracy.toFixed(2)}</td>
                <td className="py-2 pr-4 font-mono tabular-nums">
                  {row.mean_calibration_delta > 0 ? "+" : ""}
                  {row.mean_calibration_delta.toFixed(2)}
                </td>
                <td className="py-2 font-mono tabular-nums">×{row.multiplier.toFixed(2)}</td>
              </tr>
            ))}
          </Table>
          <p className="mt-4 text-xs text-muted">
            A negative delta means the system claimed more certainty than it earned. The multiplier is
            applied to the next forecast in that slice automatically.
          </p>
        </Card>
      ) : null}
    </div>
  );
}
