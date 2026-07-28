import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { Card, Eyebrow, Stat } from "@/components/ui";
import { TrustPanel } from "@/components/trust";
import { intelligence } from "@/lib/intelligence";

export const dynamic = "force-dynamic";

/**
 * Minimal markdown rendering. The reports use a fixed, known subset — headings, bullets,
 * pipe tables, bold — so a 40-line renderer is more predictable here than pulling in a
 * parser and sanitiser for text this system generated itself.
 */
function renderMarkdown(markdown: string): React.ReactNode[] {
  const lines = markdown.split("\n");
  const nodes: React.ReactNode[] = [];
  let list: string[] = [];
  let table: string[][] = [];

  const flushList = (key: string) => {
    if (!list.length) return;
    nodes.push(
      <ul key={key} className="my-3 list-disc space-y-1 pl-5 text-sm">
        {list.map((item, index) => (
          <li key={index}>{inline(item)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  const flushTable = (key: string) => {
    if (!table.length) return;
    const [head, ...body] = table;
    nodes.push(
      <div key={key} className="my-4 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              {head.map((cell, index) => (
                <th key={index} className="pb-2 pr-4 text-eyebrow font-mono uppercase text-muted">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line/60 last:border-0">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="py-2 pr-4 font-mono text-xs tabular-nums">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    table = [];
  };

  const inline = (text: string): React.ReactNode => {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, index) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={index}>{part.slice(2, -2)}</strong>
      ) : (
        <span key={index}>{part}</span>
      ),
    );
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("|")) {
      const cells = trimmed.split("|").slice(1, -1).map((cell) => cell.trim());
      if (!cells.every((cell) => /^-+$/.test(cell))) table.push(cells);
      return;
    }
    flushTable(`t${index}`);

    if (trimmed.startsWith("- ")) {
      list.push(trimmed.slice(2));
      return;
    }
    flushList(`l${index}`);

    if (trimmed.startsWith("### ")) {
      nodes.push(<h3 key={index} className="mt-5 font-display text-base font-bold">{trimmed.slice(4)}</h3>);
    } else if (trimmed.startsWith("## ")) {
      nodes.push(<h2 key={index} className="mt-6 font-display text-xl font-bold tracking-tight">{trimmed.slice(3)}</h2>);
    } else if (trimmed.startsWith("# ")) {
      nodes.push(<h1 key={index} className="font-display text-2xl font-bold tracking-tight">{trimmed.slice(2)}</h1>);
    } else if (trimmed.startsWith("*") && trimmed.endsWith("*") && trimmed.length > 2) {
      nodes.push(<p key={index} className="text-sm italic text-muted">{trimmed.slice(1, -1)}</p>);
    } else if (trimmed) {
      nodes.push(<p key={index} className="my-3 text-sm leading-relaxed">{inline(trimmed)}</p>);
    }
  });

  flushList("l-end");
  flushTable("t-end");
  return nodes;
}

export default async function ReportPage({ params }: { params: { id: string } }) {
  const report = await api.report(params.id);
  if (!report) notFound();

  const trust = await intelligence.trust("report", params.id);
  const stories: any[] = report.report_type === "executive_brief"
    ? (report.payload?.stories ?? [])
    : [];

  return (
    <article className="rise-in max-w-3xl">
      <Link href="/reports" className="font-mono text-xs text-muted hover:text-proof">
        ← All reports
      </Link>
      <div className="mt-4">
        <Eyebrow>
          {titleCase(report.report_type)} · {report.period_start} → {report.period_end}
        </Eyebrow>
      </div>

      <div className="mt-4 rounded-card border border-line bg-surface p-6">
        {renderMarkdown(report.body_markdown)}
      </div>

      {report.report_type === "executive_brief" && stories.length > 0 && (
        <div className="mt-6 space-y-4">
          <Eyebrow>Stories</Eyebrow>
          {stories.map((story: any) => (
            <Card key={story.document_id} className="p-5 space-y-3">
              <div className="flex items-start justify-between gap-4">
                <h3 className="font-display text-base font-bold leading-snug">{story.title}</h3>
                <Stat
                  label="Read"
                  value={`${story.reading_time_minutes}m`}
                />
              </div>
              <p className="font-mono text-xs text-muted">
                {story.source} · {story.published_at?.slice(0, 10)}{" "}
                {story.original_url ? (
                  <a href={story.original_url} className="text-proof hover:underline" target="_blank" rel="noopener noreferrer">
                    Read article →
                  </a>
                ) : (
                  <span className="text-muted">Source not linked</span>
                )}
              </p>
              {story.related_trends?.length > 0 && (
                <div className="flex flex-wrap gap-3">
                  {story.related_trends.map((t: any, i: number) => (
                    <Stat
                      key={i}
                      label={t.entity_name}
                      value={String(t.value)}
                      note={`${t.delta >= 0 ? "+" : ""}${t.delta} · ${t.direction}`}
                    />
                  ))}
                </div>
              )}
              <p className="text-sm leading-relaxed">{story.executive_summary}</p>
              <dl className="grid gap-2 sm:grid-cols-2 text-sm">
                <div><dt className="font-mono text-xs text-muted uppercase">Why it matters</dt><dd>{story.why_it_matters}</dd></div>
                <div><dt className="font-mono text-xs text-muted uppercase">Business impact</dt><dd>{story.business_impact}</dd></div>
                <div><dt className="font-mono text-xs text-muted uppercase">Technology impact</dt><dd>{story.technology_impact}</dd></div>
                <div><dt className="font-mono text-xs text-muted uppercase">Recommendation</dt><dd>{story.strategic_recommendation}</dd></div>
              </dl>
            </Card>
          ))}
        </div>
      )}

      {trust && (
        <div className="mt-6">
          <TrustPanel trust={trust} />
        </div>
      )}
    </article>
  );
}
