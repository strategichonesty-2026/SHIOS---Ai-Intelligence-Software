import Link from "next/link";
import { api, type Prediction } from "@/lib/api";
import { percent, shortDate, humanizeStatement, weekToDateRange } from "@/lib/format";
import { Card, ConfidenceBar, Empty, EvidenceLedger, Eyebrow, Stat, Table } from "@/components/ui";
import { ReliabilityBadge } from "@/components/trust";
import { reliabilityBand } from "@/lib/intelligence";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

/** §1 — Forecast History. Every published forecast, scored or pending, immutable. */
export default async function ForecastHistoryPage({
  searchParams,
}: {
  searchParams: { page?: string };
}) {
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const [predictions, accuracy] = await Promise.all([
    api.predictions(PAGE_SIZE, offset),
    api.accuracy(),
  ]);

  if (!predictions || !predictions.total) {
    return <Empty title="No forecast has been published" action="Run the loop to fit and publish forecasts." />;
  }

  const totalPages = Math.max(1, Math.ceil(predictions.total / PAGE_SIZE));
  const band = reliabilityBand(accuracy?.mean_calibration_delta ?? null);

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Forecast history · complete register</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Every forecast this system has published
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Forecasts are immutable once published — never edited, never quietly withdrawn. When the
          target period arrives each one is scored against the observed count, and the misses stay
          on this page alongside the hits.
        </p>
      </header>

      {accuracy ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Published" value={String(predictions.total)} note="in the register" />
          <Stat label="Scored" value={String(accuracy.scored)} note="past their expiry" />
          <Stat label="Mean accuracy" value={percent(accuracy.mean_accuracy)} note="1.00 is exact" />
          <div className="rounded-card border border-line bg-surface px-4 py-3">
            <Eyebrow>Confidence reliability</Eyebrow>
            <div className="mt-2">
              <ReliabilityBadge label={band.label} tone={band.tone} />
            </div>
            <p className="mt-2 text-xs text-muted">{band.meaning}</p>
          </div>
        </div>
      ) : null}

      <Card eyebrow={`${predictions.total} forecasts · sorted by target week`} title="Register">
        <Table head={["Forecast", "Target", "Confidence", "Review by", "Evidence", "Status"]}>
          {predictions.items.map((p: Prediction) => (
            <tr key={p.id} className="border-b border-line/60 align-top last:border-0">
              <td className="max-w-md py-3 pr-4">
                <Link href={`/forecasts/${p.id}`} className="hover:text-proof">
                  {humanizeStatement(p.statement)}
                </Link>
                <p className="mt-1 font-mono text-xs text-muted">{p.id.slice(0, 8)}</p>
              </td>
              <td className="py-3 pr-4 font-mono text-xs tabular-nums">{weekToDateRange(p.target_period)}</td>
              <td className="py-3 pr-4">
                <ConfidenceBar confidence={p.confidence} />
              </td>
              <td className="py-3 pr-4 font-mono text-xs text-muted tabular-nums">
                {shortDate(p.review_date)}
              </td>
              <td className="py-3 pr-4">
                <EvidenceLedger count={p.evidence_count} max={10} href={`/forecasts/${p.id}`} />
              </td>
              <td className="py-3">
                <StatusTag status={p.status} />
              </td>
            </tr>
          ))}
        </Table>
        <Pagination page={page} totalPages={totalPages} />
      </Card>
    </div>
  );
}

function Pagination({ page, totalPages }: { page: number; totalPages: number }) {
  if (totalPages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between font-mono text-xs text-muted">
      {page > 1 ? (
        <Link href={`/forecasts?page=${page - 1}`} className="text-proof hover:underline">
          ← Previous
        </Link>
      ) : (
        <span className="cursor-not-allowed opacity-40">← Previous</span>
      )}
      <span>
        Page {page} of {totalPages}
      </span>
      {page < totalPages ? (
        <Link href={`/forecasts?page=${page + 1}`} className="text-proof hover:underline">
          Next →
        </Link>
      ) : (
        <span className="cursor-not-allowed opacity-40">Next →</span>
      )}
    </div>
  );
}

function StatusTag({ status }: { status: string }) {
  const tone =
    status === "evaluated"
      ? "text-proof"
      : status === "needs_review" || status === "unverifiable"
        ? "text-provisional"
        : "text-muted";
  const label =
    status === "published"
      ? "pending review"
      : status === "evaluated"
        ? "scored"
        : status.replace("_", " ");
  return <span className={`font-mono text-xs uppercase ${tone}`}>{label}</span>;
}
