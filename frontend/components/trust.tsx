import Link from "next/link";
import type { TrustPayload } from "@/lib/intelligence";
import { percent, shortDate, titleCase } from "@/lib/format";
import { ConfidenceBar, EvidenceLedger, Eyebrow } from "./ui";

/** §9 — the standard Trust Panel. Same shape for every artefact in the system. */
export function TrustPanel({ trust }: { trust: TrustPayload }) {
  const diversity = trust.source_diversity;
  const reality = (trust.reality_validation ?? {}) as Record<string, any>;
  const explain = trust.explainability as Record<string, any>;

  return (
    <section className="rise-in rounded-card border border-line bg-surface">
      <header className="border-b border-line px-5 py-3">
        <Eyebrow>How we know</Eyebrow>
      </header>

      <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
        <Cell label="Evidence">
          <EvidenceLedger count={trust.evidence_count} max={14} />
        </Cell>
        <Cell label="Confidence">
          {trust.confidence === null ? (
            <span className="font-mono text-xs text-muted">not claimed — this is a count</span>
          ) : (
            <ConfidenceBar confidence={trust.confidence} />
          )}
        </Cell>
        <Cell label="Source diversity">
          <p className="font-mono text-sm tabular-nums">
            {diversity.distinct_sources} source{diversity.distinct_sources === 1 ? "" : "s"}
          </p>
          {diversity.concentration !== null && diversity.concentration > 0.8 ? (
            <p className="mt-1 text-xs text-provisional">
              {percent(diversity.concentration)} from one source — treat as narrow
            </p>
          ) : null}
        </Cell>
        <Cell label="Last updated">
          <p className="font-mono text-sm">{trust.last_updated ? shortDate(trust.last_updated) : "—"}</p>
        </Cell>
      </div>

      <div className="grid gap-6 px-5 py-5 lg:grid-cols-2">
        <div>
          <Eyebrow>Reality validation</Eyebrow>
          {reality.scored ? (
            <dl className="mt-2 space-y-1 text-sm">
              <Row k="Predicted" v={String(reality.predicted_value)} />
              <Row k="Actual" v={String(reality.actual_value)} />
              <Row k="Accuracy" v={percent(reality.accuracy_score)} />
              <Row k="Direction" v={reality.direction_correct ? "called correctly" : "missed"} />
            </dl>
          ) : (
            <p className="mt-2 text-sm text-muted">
              {reality.note ??
                (reality.validated === undefined
                  ? "Not yet scored against reality."
                  : reality.validated
                    ? "Passed governance validation."
                    : "Held for review — failed a governance check.")}
            </p>
          )}
          {Array.isArray(reality.unknowns_noted) && reality.unknowns_noted.length ? (
            <ul className="mt-3 space-y-1 text-xs text-muted">
              {reality.unknowns_noted.map((u: string, i: number) => (
                <li key={i}>· {u}</li>
              ))}
            </ul>
          ) : null}
        </div>

        <div>
          <Eyebrow>How this forecast was made</Eyebrow>
          <dl className="mt-2 space-y-1 text-sm">
            <Row k="Approach" v="Linear trend fitted to recent weekly counts, with a range to account for uncertainty" />
            {explain.horizon ? <Row k="How far ahead" v={String(explain.horizon).replace("w", " weeks")} /> : null}
            {explain.review_date ? <Row k="Checked against reality by" v={shortDate(String(explain.review_date))} /> : null}
            <Row k="Can it be edited?" v="No — forecasts are locked at publication and scored as-is" />
          </dl>
        </div>
      </div>

      {trust.prediction_history ? (
        <div className="border-t border-line px-5 py-4">
          <Eyebrow>Track record for {trust.prediction_history.entity}</Eyebrow>
          <p className="mt-1 text-sm">
            {trust.prediction_history.forecasts_published} forecast
            {trust.prediction_history.forecasts_published === 1 ? "" : "s"} published,{" "}
            {trust.prediction_history.forecasts_scored} scored
            {trust.prediction_history.mean_accuracy !== null
              ? `, mean accuracy ${percent(trust.prediction_history.mean_accuracy)}.`
              : " — none scored yet, so this entity's forecasts are unproven."}
          </p>
        </div>
      ) : null}

      {trust.related_sources.length ? (
        <div className="border-t border-line px-5 py-4">
          <Eyebrow>Primary sources</Eyebrow>
          <ul className="mt-2 space-y-1">
            {trust.related_sources.map((doc) => (
              <li key={doc.document_id} className="text-sm">
                <span className="font-mono text-xs text-muted uppercase">{doc.source.replace(/_/g, " ")}</span>
                <span className="mx-2 text-muted">·</span>
                <span>{doc.title}</span>
                <span className="ml-2 font-mono text-xs text-muted">{shortDate(doc.observed_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="border-t border-line px-5 py-4">
          <p className="text-sm text-fail">No source documents resolve for this artefact.</p>
        </div>
      )}
    </section>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface px-5 py-4">
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="min-w-24 text-muted">{k}</dt>
      <dd className="font-mono text-xs tabular-nums">{v}</dd>
    </div>
  );
}

/** §2 — Confidence Reliability badge, replacing the raw "calibration delta" number. */
export function ReliabilityBadge({
  label,
  tone,
}: {
  label: string;
  tone: "proof" | "provisional" | "fail" | "muted";
}) {
  const palette = {
    proof: "border-proof bg-proofSoft text-proof",
    provisional: "border-provisional bg-provisionalSoft text-provisional",
    fail: "border-fail bg-failSoft text-fail",
    muted: "border-line bg-paper text-muted",
  }[tone];
  return (
    <span className={`inline-block rounded-card border px-2 py-[2px] font-mono text-xs ${palette}`}>
      {label}
    </span>
  );
}

export function SourceChip({ source, synthetic }: { source: string; synthetic?: boolean }) {
  return (
    <span
      className={`inline-block rounded-card border px-2 py-[1px] font-mono text-xs ${
        synthetic ? "border-provisional text-provisional" : "border-line text-muted"
      }`}
      title={synthetic ? "Synthetic data — not market signal" : undefined}
    >
      {titleCase(source)}
      {synthetic ? " · synthetic" : ""}
    </span>
  );
}

export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="font-mono text-xs text-muted hover:text-proof">
      ← {children}
    </Link>
  );
}
