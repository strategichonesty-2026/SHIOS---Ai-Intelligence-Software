import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { weekToDateRange } from "@/lib/format";
import { Card, Empty, Eyebrow } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function TrendEvidencePage({ params }: { params: { id: string } }) {
  const data = await api.trendEvidence(params.id);
  if (!data) notFound();

  return (
    <article className="rise-in max-w-3xl space-y-6">
      <Link href="/trends" className="font-mono text-xs text-muted hover:text-proof">
        ← All trends
      </Link>

      <div className="rounded-card border border-line bg-surface p-4 sm:p-6">
        <Eyebrow>Evidence for</Eyebrow>
        <h1 className="mt-2 font-display text-2xl font-bold tracking-tight">
          {data.entity_name}
        </h1>
        <p className="mt-1 font-mono text-xs text-muted">
          Week of {weekToDateRange(data.period)}
        </p>
        <p className="mt-3 text-sm text-muted">
          These are the actual documents the system read that mentioned{" "}
          <strong>{data.entity_name}</strong> this week. Every count on the trends page traces
          back to records like these — no estimates, no interpolation.
        </p>
      </div>

      {data.evidence.length > 0 ? (
        <Card
          eyebrow={`${data.evidence.length} record${data.evidence.length !== 1 ? "s" : ""}`}
          title="Source documents"
        >
          <ul className="space-y-4">
            {data.evidence.map((e) => (
              <li key={e.id} className="border-b border-line/60 pb-4 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="font-mono text-xs text-proof uppercase">{e.source.replace(/_/g, " ")}</span>
                  {e.source === "github" && e.snippet?.includes("/") ? (
                    <a
                      href={`https://github.com/${e.snippet.split("\n")[0].trim()}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-xs text-proof hover:underline"
                    >
                      {e.snippet.split("\n")[0].trim()} ↗
                    </a>
                  ) : null}
                </div>
                {e.snippet ? (
                  <p className="mt-1 text-sm text-muted leading-relaxed line-clamp-2">
                    {e.source === "github"
                      ? e.snippet.split("\n").slice(1).join(" ").trim()
                      : e.snippet}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-muted italic">No snippet available.</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <Empty
          title="No evidence records attached"
          action="Evidence is linked when trends are computed from collected documents."
        />
      )}
    </article>
  );
}
