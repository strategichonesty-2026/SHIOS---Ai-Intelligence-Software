import { intelligence } from "@/lib/intelligence";
import { shortDate } from "@/lib/format";
import { Card, Empty, Eyebrow, Stat, Table } from "@/components/ui";
import { ReliabilityBadge } from "@/components/trust";

export const dynamic = "force-dynamic";

/** §3 — the evidence base, broken down by what was actually collected. */
export default async function EvidencePage() {
  const data = await intelligence.evidenceBreakdown();

  if (!data || !data.categories.length) {
    return <Empty title="No evidence collected yet" action="Run the loop to collect and extract documents." />;
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Evidence base</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          What the system has actually read
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Every number elsewhere in this application is a count over these documents. Categories
          below are derived from what was collected — not from a menu of sources the system wishes
          it had.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Evidence records" value={data.total_evidence.toLocaleString()} note="entity mentions" />
        <Stat label="Documents" value={data.total_documents.toLocaleString()} note="collected and normalised" />
        <Stat label="Categories" value={String(data.categories.length)} note="with real data behind them" />
      </div>

      <Card eyebrow="By category" title="Where the evidence comes from">
        <Table head={["Category", "Evidence", "Documents", "Last updated", "Sources"]}>
          {data.categories.map((c) => (
            <tr key={c.category} className="border-b border-line/60 last:border-0">
              <td className="py-3 pr-4">
                <span className="font-medium">{c.category}</span>
                {c.synthetic_only ? (
                  <span className="ml-2 font-mono text-xs text-provisional">demo data — not real</span>
                ) : null}
              </td>
              <td className="py-3 pr-4 font-mono tabular-nums">{c.evidence_count.toLocaleString()}</td>
              <td className="py-3 pr-4 font-mono tabular-nums">{c.document_count.toLocaleString()}</td>
              <td className="py-3 pr-4 font-mono text-xs text-muted">
                {c.last_updated ? shortDate(c.last_updated) : "—"}
              </td>
              <td className="py-3 font-mono text-xs text-muted">{c.sources.join(", ")}</td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card eyebrow="By source" title="Reliability, with a stated basis">
        <div className="space-y-4">
          {data.sources.map((s) => (
            <div key={s.source} className="border-b border-line/60 pb-4 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">{s.label}</span>
                <ReliabilityBadge
                  label={s.reliability}
                  tone={
                    s.synthetic
                      ? "provisional"
                      : s.reliability === "high"
                        ? "proof"
                        : s.reliability === "moderate"
                          ? "provisional"
                          : "muted"
                  }
                />
                {s.primary_source ? (
                  <span className="font-mono text-xs text-proof">primary source</span>
                ) : null}
                <span className="font-mono text-xs text-muted tabular-nums">
                  {s.evidence_count.toLocaleString()} records · {s.document_count.toLocaleString()} docs
                </span>
              </div>
              <p className="mt-2 text-sm text-muted">{s.reliability_basis}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-muted">
          Ratings are stated editorial assessments with their reasoning attached — not computed
          scores. Nothing here is inferred from popularity or volume.
        </p>
      </Card>

      <Card eyebrow="Coverage gap" title="Source types this system does not read">
        <ul className="space-y-2">
          {data.not_collected.map((item) => (
            <li key={item.category} className="flex flex-wrap gap-x-3 text-sm">
              <span className="min-w-56 font-medium text-provisional">{item.category}</span>
              <span className="text-muted">{item.note}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">
          These are listed rather than hidden. Showing them as empty categories would imply
          coverage that does not exist; each one is a collector still to be built.
        </p>
      </Card>
    </div>
  );
}
