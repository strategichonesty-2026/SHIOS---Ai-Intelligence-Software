import Link from "next/link";
import { confidenceLabel, percent, signed } from "@/lib/format";
import type { Trend } from "@/lib/api";

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-eyebrow font-mono uppercase text-muted">{children}</p>;
}

export function Card({
  title,
  eyebrow,
  children,
  className = "",
}: {
  title?: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rise-in rounded-card border border-line bg-surface p-5 ${className}`}>
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      {title ? <h2 className="mt-1 font-display text-lg font-bold tracking-tight">{title}</h2> : null}
      <div className={title || eyebrow ? "mt-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-card border border-line bg-surface px-3 py-3 sm:px-4">
      <Eyebrow>{label}</Eyebrow>
      <p className="mt-1 font-mono text-xl font-semibold tabular-nums sm:text-2xl">{value}</p>
      {note ? <p className="mt-1 text-xs text-muted">{note}</p> : null}
    </div>
  );
}

/** Signature element: one tick per piece of evidence, capped, with the exact count beside it. */
export function EvidenceLedger({ count, max = 24, href }: { count: number; max?: number; href?: string }) {
  const ticks = Math.min(count, max);
  const inner = (
    <div
      className={`flex items-center gap-2 ${href ? "group hover:opacity-80 transition-opacity" : ""}`}
      title={href ? `View ${count} source documents` : `${count} evidence records`}
    >
      <div className="flex items-end gap-[2px]" aria-hidden>
        {Array.from({ length: ticks }).map((_, index) => (
          <span key={index} className="ledger-tick" />
        ))}
        {count === 0 ? <span className="text-xs text-fail">no evidence</span> : null}
      </div>
      <span className="font-mono text-xs text-muted tabular-nums">
        {count}
        {count > max ? "+" : ""}
      </span>
      {href ? <span className="font-mono text-xs text-proof opacity-0 group-hover:opacity-100 transition-opacity">→</span> : null}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export function ConfidenceBar({ confidence }: { confidence: number }) {
  const tone = confidenceLabel(confidence);
  const palette = {
    proof: { bar: "bg-proof", track: "bg-proofSoft", text: "text-proof" },
    provisional: { bar: "bg-provisional", track: "bg-provisionalSoft", text: "text-provisional" },
    fail: { bar: "bg-fail", track: "bg-failSoft", text: "text-fail" },
  }[tone];

  return (
    <div className="flex items-center gap-2">
      <div className={`h-[6px] w-24 rounded-full ${palette.track}`}>
        <div
          className={`h-full rounded-full ${palette.bar}`}
          style={{ width: `${Math.max(2, Math.round(confidence * 100))}%` }}
        />
      </div>
      <span className={`font-mono text-xs tabular-nums ${palette.text}`}>{percent(confidence)}</span>
    </div>
  );
}

export function DirectionTag({ direction, delta }: { direction: string; delta?: number }) {
  const tone =
    direction === "up" ? "text-proof" : direction === "down" ? "text-fail" : "text-muted";
  const glyph = direction === "up" ? "▲" : direction === "down" ? "▼" : "—";
  return (
    <span className={`font-mono text-xs tabular-nums ${tone}`}>
      {glyph} {delta === undefined ? direction : signed(delta)}
    </span>
  );
}

/** Inline SVG sparkline. No chart library: six lines of maths beats 400kB of dependency. */
export function Sparkline({ values, width = 120, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="font-mono text-xs text-muted">insufficient history</span>;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((value, index) => `${(index * step).toFixed(1)},${(height - ((value - min) / span) * height).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="trend sparkline">
      <polyline points={points} fill="none" stroke="#0F766E" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function Empty({ title, action }: { title: string; action: string }) {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface p-8 text-center">
      <p className="font-display text-lg font-bold">{title}</p>
      <p className="mt-2 text-sm text-muted">{action}</p>
      <a
        href="/admin"
        className="mt-4 inline-block rounded-card border border-proof px-4 py-2 font-mono text-xs text-proof hover:bg-proofSoft"
      >
        Go to Admin → Run collection loop
      </a>
    </div>
  );
}

/** Rising/Falling signal table, shared by the Overview page and the frozen Archive detail view. */
export function MoverTable({ movers, empty }: { movers: Trend[]; empty: string }) {
  if (!movers.length) {
    return <p className="text-sm text-muted">{empty}</p>;
  }
  return (
    <Table head={["Signal", "Count", "Change", "Evidence"]}>
      {movers.map((trend) => (
        <tr key={trend.id} className="border-b border-line/60 last:border-0">
          <td className="py-2 pr-4">
            <span className="font-medium">{trend.entity_name}</span>
            <span className="ml-2 font-mono text-xs text-muted">{trend.entity_type}</span>
          </td>
          <td className="py-2 pr-4 font-mono tabular-nums">
            {trend.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            <span className="ml-1 text-xs text-muted font-sans">mentions</span>
          </td>
          <td className="py-2 pr-4">
            <DirectionTag direction={trend.direction} delta={trend.delta} />
            <span className="ml-2 font-mono text-xs text-muted tabular-nums">
              {signed(trend.delta_pct)}%
            </span>
          </td>
          <td className="py-2">
            <EvidenceLedger count={trend.evidence_count} max={12} href={`/trends/${trend.id}`} />
          </td>
        </tr>
      ))}
    </Table>
  );
}

export function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            {head.map((label) => (
              <th key={label} className="pb-2 pr-3 text-eyebrow font-mono text-xs uppercase text-muted sm:pr-4">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
