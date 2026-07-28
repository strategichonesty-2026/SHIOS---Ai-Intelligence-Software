import { notFound } from "next/navigation";
import { safeGet } from "@/lib/api";
import { intelligence } from "@/lib/intelligence";
import { percent, shortDate, humanizeStatement, weekToDateRange } from "@/lib/format";
import { Card, ConfidenceBar, Eyebrow, Sparkline } from "@/components/ui";
import { BackLink, TrustPanel } from "@/components/trust";

export const dynamic = "force-dynamic";

type PredictionDetail = {
  id: string;
  statement: string;
  entity_name: string;
  entity_type: string;
  target_period: string;
  predicted_value: number;
  predicted_direction: string;
  confidence: number;
  method: string;
  review_date: string;
  expiration_date: string;
  status: string;
  created_at: string;
  series: { period: string; value: number }[];
  result: {
    actual_value: number;
    accuracy_score: number;
    deviation: number;
    direction_correct: boolean;
    notes: string;
  } | null;
};

export default async function ForecastDetailPage({ params }: { params: { id: string } }) {
  const [detail, trust] = await Promise.all([
    safeGet<PredictionDetail>(`/predictions/${params.id}`),
    intelligence.trust("prediction", params.id),
  ]);

  if (!detail) notFound();

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <BackLink href="/forecasts">All forecasts</BackLink>
        <div className="mt-4">
          <Eyebrow>
            Forecast {detail.id.slice(0, 8)} · published {shortDate(detail.created_at)}
          </Eyebrow>
        </div>
        <h1 className="mt-2 font-display text-2xl font-bold leading-snug tracking-tight">
          {humanizeStatement(detail.statement)}
        </h1>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card eyebrow="What was claimed" title="The forecast">
          <dl className="space-y-2 text-sm">
            <Row k="Target period" v={weekToDateRange(detail.target_period)} />
            <Row k="Predicted value" v={detail.predicted_value.toFixed(1)} />
            <Row k="Direction" v={detail.predicted_direction} />
            <Row k="Method" v={detail.method} />
            <Row k="Review by" v={shortDate(detail.review_date)} />
            <Row k="Expires" v={shortDate(detail.expiration_date)} />
          </dl>
          <div className="mt-4">
            <Eyebrow>Confidence at publication</Eyebrow>
            <div className="mt-2">
              <ConfidenceBar confidence={detail.confidence} />
            </div>
          </div>
        </Card>

        <Card eyebrow="What happened" title="Outcome">
          {detail.result ? (
            <>
              <dl className="space-y-2 text-sm">
                <Row k="Actual value" v={detail.result.actual_value.toFixed(1)} />
                <Row k="Deviation" v={detail.result.deviation.toFixed(1)} />
                <Row k="Accuracy" v={percent(detail.result.accuracy_score)} />
                <Row
                  k="Direction"
                  v={detail.result.direction_correct ? "called correctly" : "missed"}
                />
              </dl>
              <p className="mt-4 text-sm text-muted">{detail.result.notes}</p>
            </>
          ) : (
            <p className="text-sm text-muted">
              Not yet scored. This forecast is still inside its review window, so nothing here is
              proven — it is a claim awaiting a verdict.
            </p>
          )}
        </Card>
      </div>

      {detail.series?.length > 1 ? (
        <Card eyebrow="Observed history" title={`${detail.entity_name} — the series behind the fit`}>
          <Sparkline values={detail.series.map((p) => p.value)} width={520} height={60} />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted">
            {detail.series.map((p) => (
                <span key={p.period}>
                {weekToDateRange(p.period)}: {p.value.toFixed(0)}
              </span>
            ))}
          </div>
        </Card>
      ) : null}

      {trust ? <TrustPanel trust={trust} /> : null}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="min-w-32 text-muted">{k}</dt>
      <dd className="font-mono text-xs tabular-nums">{v}</dd>
    </div>
  );
}
