import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { humanizeStatement, shortDate, weekToDateRange } from "@/lib/format";
import { Card, ConfidenceBar, Empty, EvidenceLedger, Eyebrow } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function RecommendationPage({ params }: { params: { id: string } }) {
  const rec = await api.recommendation(params.id);
  if (!rec) notFound();

  return (
    <article className="rise-in max-w-3xl space-y-6">
      <Link href="/recommendations" className="font-mono text-xs text-muted hover:text-proof">
        ← All recommendations
      </Link>

      {/* Main recommendation */}
      <div className="rounded-card border border-line bg-surface p-4 sm:p-6">
        <Eyebrow>{rec.audience_type}</Eyebrow>
        <p className="mt-3 text-base leading-relaxed sm:text-lg">{rec.recommendation_text}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
          <ConfidenceBar confidence={rec.confidence} />
          <EvidenceLedger count={rec.evidence_count} max={16} />
          <span className="font-mono text-xs text-muted">{shortDate(rec.created_at)}</span>
        </div>
      </div>

      {/* Rationale / risks / outcomes if present */}
      {(rec.rationale || rec.risks || rec.expected_outcomes) && (
        <Card eyebrow="Reasoning">
          {rec.rationale && (
            <div className="mb-4">
              <p className="font-mono text-xs uppercase text-muted mb-1">Rationale</p>
              <p className="text-sm leading-relaxed">{rec.rationale}</p>
            </div>
          )}
          {rec.expected_outcomes && (
            <div className="mb-4">
              <p className="font-mono text-xs uppercase text-muted mb-1">Expected outcomes</p>
              <p className="text-sm leading-relaxed">{rec.expected_outcomes}</p>
            </div>
          )}
          {rec.risks && (
            <div>
              <p className="font-mono text-xs uppercase text-muted mb-1">Risks</p>
              <p className="text-sm leading-relaxed text-provisional">{rec.risks}</p>
            </div>
          )}
        </Card>
      )}

      {/* Linked forecast */}
      {rec.prediction && (
        <Card eyebrow="Forecast this is based on">
          <p className="text-sm leading-relaxed">{humanizeStatement(rec.prediction.statement)}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
            <ConfidenceBar confidence={rec.prediction.confidence} />
            <span className="font-mono text-xs text-muted">
              Target: {weekToDateRange(rec.prediction.target_period)}
            </span>
            <Link
              href={`/forecasts/${rec.prediction.id}`}
              className="font-mono text-xs text-proof hover:underline"
            >
              Full forecast →
            </Link>
          </div>
        </Card>
      )}

      {/* Evidence sources */}
      {rec.evidence.length > 0 && (
        <Card eyebrow={`${rec.evidence.length} evidence record${rec.evidence.length !== 1 ? "s" : ""}`} title="What this is built on">
          <ul className="space-y-4">
            {rec.evidence.map((e) => (
              <li key={e.id} className="border-b border-line/60 pb-4 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-medium text-sm">{e.entity_name}</span>
                  <span className="font-mono text-xs text-muted">{weekToDateRange(e.period)}</span>
                </div>
                {e.snippet && (
                  <p className="mt-1 text-sm text-muted leading-relaxed line-clamp-3">{e.snippet}</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {rec.evidence.length === 0 && (
        <Empty
          title="No evidence records attached"
          action="Evidence is linked when the recommendation is generated from trends and forecasts."
        />
      )}
    </article>
  );
}
