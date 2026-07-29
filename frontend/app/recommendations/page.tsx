import Link from "next/link";
import { api, type Recommendation } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { Card, ConfidenceBar, Empty, EvidenceLedger, Eyebrow } from "@/components/ui";

export const dynamic = "force-dynamic";

const AUDIENCE_ORDER = ["individual", "manager", "executive", "investor", "student"];

export default async function RecommendationsPage() {
  const data = await api.recommendations();

  if (!data || !data.items.length) {
    return (
      <Empty
        title="No recommendation clears the evidence rule"
        action="A recommendation needs at least two evidence records and a trend or forecast behind it."
      />
    );
  }

  const grouped = new Map<string, Recommendation[]>();
  for (const item of data.items) {
    grouped.set(item.audience_type, [...(grouped.get(item.audience_type) ?? []), item]);
  }
  const audiences = AUDIENCE_ORDER.filter((audience) => grouped.has(audience));

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Recommendations by audience</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Same evidence, five different decisions
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Nothing appears here without at least two evidence records and a traceable forecast. Items
          marked <span className="font-mono text-provisional">needs review</span> failed a governance
          check and are held back rather than deleted.
        </p>
      </header>

      {audiences.map((audience) => (
        <Card key={audience} eyebrow={`${grouped.get(audience)!.length} items`} title={titleCase(audience)}>
          <ul className="space-y-5">
            {grouped.get(audience)!.map((item) => (
              <li key={item.id} className="border-b border-line/60 pb-5 last:border-0 last:pb-0">
                <p className="text-sm leading-relaxed">{item.recommendation_text}</p>
                <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
                  <ConfidenceBar confidence={item.confidence} />
                  <EvidenceLedger count={item.evidence_count} max={16} />
                  <span
                    className={`font-mono text-xs uppercase ${
                      item.status === "needs_review" ? "text-provisional" : "text-muted"
                    }`}
                  >
                    {item.status.replace("_", " ")}
                  </span>
                  <Link
                    href={`/recommendations/${item.id}`}
                    className="font-mono text-xs text-proof hover:underline"
                  >
                    {item.evidence_count} source{item.evidence_count !== 1 ? "s" : ""} →
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
