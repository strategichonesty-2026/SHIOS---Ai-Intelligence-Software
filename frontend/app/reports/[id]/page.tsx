import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { Eyebrow } from "@/components/ui";

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
    </article>
  );
}
