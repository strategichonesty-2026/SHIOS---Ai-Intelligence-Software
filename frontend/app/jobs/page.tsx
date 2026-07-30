import { intelligence, type JobRow } from "@/lib/intelligence";
import { percent, shortDate } from "@/lib/format";
import { Card, Empty, Eyebrow, Stat, Table } from "@/components/ui";
import { SourceChip } from "@/components/trust";

export const dynamic = "force-dynamic";

const PER_PAGE = 25;

export default async function JobsPage({
  searchParams,
}: {
  searchParams: { role?: string; remote?: string; salary?: string; page?: string };
}) {
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10));
  const offset = (page - 1) * PER_PAGE;

  const params = new URLSearchParams();
  if (searchParams.role) params.set("role", searchParams.role);
  if (searchParams.remote) params.set("remote_type", searchParams.remote);
  if (searchParams.salary === "yes") params.set("has_salary", "true");
  params.set("offset", String(offset));
  const qs = `&${params.toString()}`;

  const [jobs, facets] = await Promise.all([intelligence.jobs(qs), intelligence.jobFacets()]);

  if (!jobs || !facets) {
    return <Empty title="No jobs collected yet" action="Run the loop to collect and extract job postings." />;
  }

  const totalPages = Math.ceil(jobs.total / PER_PAGE);

  // Build pagination URL helper
  const pageUrl = (p: number) => {
    const q = new URLSearchParams();
    if (searchParams.role) q.set("role", searchParams.role);
    if (searchParams.remote) q.set("remote", searchParams.remote);
    if (searchParams.salary) q.set("salary", searchParams.salary);
    if (p > 1) q.set("page", String(p));
    const s = q.toString();
    return s ? `/jobs?${s}` : "/jobs";
  };

  return (
    <div className="space-y-6">
      <header>
        <Eyebrow>Job intelligence</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          The postings behind every trend
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Each row traces to a document the system read. Trends are counts over exactly this
          corpus — nothing in the dashboard exists that cannot be traced back here.
        </p>
      </header>

      {jobs.items.every((j: JobRow) => j.synthetic) && (
        <div className="rounded-card border border-provisional bg-provisional/10 px-4 py-3 text-sm">
          <strong className="text-provisional">Demo data only.</strong>{" "}
          All job postings shown are computer-generated samples, not real listings.
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Postings" value={facets.total_jobs.toLocaleString()} note="in the corpus" />
        <Stat
          label="Salary disclosed"
          value={facets.salary_coverage !== null ? percent(facets.salary_coverage) : "—"}
          note={`${facets.with_salary.toLocaleString()} of ${facets.total_jobs.toLocaleString()}`}
        />
        <Stat label="Distinct roles" value={String(facets.roles.length)} note="normalised" />
      </div>

      <nav className="flex flex-wrap gap-2">
        <FilterLink href="/jobs" label="All" active={!searchParams.role && !searchParams.remote && !searchParams.salary} />
        <FilterLink href="/jobs?remote=remote" label="Remote" active={searchParams.remote === "remote"} />
        <FilterLink href="/jobs?remote=hybrid" label="Hybrid" active={searchParams.remote === "hybrid"} />
        <FilterLink href="/jobs?salary=yes" label="Salary disclosed" active={searchParams.salary === "yes"} />
        {facets?.roles.slice(0, 6).map((role) => (
          <FilterLink
            key={role}
            href={`/jobs?role=${encodeURIComponent(role)}`}
            label={role}
            active={searchParams.role === role}
          />
        ))}
      </nav>

      <Card eyebrow={`${(offset + 1).toLocaleString()}–${Math.min(offset + jobs.returned, jobs.total).toLocaleString()} of ${jobs.total.toLocaleString()}`} title="Postings">
        <Table head={["Position", "Company", "Location", "Salary", "Posted", "Skills"]}>
          {jobs.items.map((job: JobRow) => (
            <tr key={job.id} className="border-b border-line/60 align-top last:border-0">
              <td className="py-3 pr-4 min-w-[200px] max-w-[280px]">
                {job.url ? (
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-proof hover:underline"
                  >
                    {job.position}
                  </a>
                ) : (
                  <span className="font-medium">{job.position}</span>
                )}
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {job.seniority && job.seniority !== "unknown" && (
                    <span className="font-mono text-xs text-muted">{job.seniority}</span>
                  )}
                  <SourceChip source={job.source} synthetic={job.synthetic} />
                </div>
              </td>
              <td className="py-3 pr-4 text-sm max-w-[160px]">{job.company ?? "—"}</td>
              <td className="py-3 pr-4 text-sm whitespace-nowrap">
                {job.location}
                {job.remote_type && job.remote_type !== "unknown" && (
                  <span className="ml-1 font-mono text-xs text-muted">{job.remote_type}</span>
                )}
              </td>
              <td className="py-3 pr-4 font-mono text-xs tabular-nums whitespace-nowrap">
                {job.salary_known
                  ? `$${((job.salary_min ?? 0) / 1000).toFixed(0)}k–$${((job.salary_max ?? 0) / 1000).toFixed(0)}k`
                  : <span className="text-muted">—</span>}
              </td>
              <td className="py-3 pr-4 font-mono text-xs text-muted whitespace-nowrap">{shortDate(job.posted_at)}</td>
              <td className="py-3">
                <div className="flex flex-wrap gap-1">
                  {job.skills.slice(0, 3).map((s) => (
                    <span key={s} className="rounded-card border border-line px-[6px] py-[1px] font-mono text-xs text-muted">
                      {s}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </Table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
            <a
              href={page > 1 ? pageUrl(page - 1) : "#"}
              className={`font-mono text-xs ${page <= 1 ? "pointer-events-none text-muted opacity-40" : "text-proof hover:underline"}`}
            >
              ← Previous
            </a>
            <span className="font-mono text-xs text-muted">
              Page {page} of {totalPages}
            </span>
            <a
              href={page < totalPages ? pageUrl(page + 1) : "#"}
              className={`font-mono text-xs ${page >= totalPages ? "pointer-events-none text-muted opacity-40" : "text-proof hover:underline"}`}
            >
              Next →
            </a>
          </div>
        )}
      </Card>
    </div>
  );
}

function FilterLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <a
      href={href}
      className={`rounded-card border px-3 py-1 font-mono text-xs transition-colors ${
        active ? "border-proof bg-proofSoft text-proof" : "border-line text-muted hover:border-proof hover:text-proof"
      }`}
    >
      {label}
    </a>
  );
}
