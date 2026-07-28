import { intelligence, type JobRow } from "@/lib/intelligence";
import { percent, shortDate } from "@/lib/format";
import { Card, Empty, Eyebrow, Stat, Table } from "@/components/ui";
import { SourceChip } from "@/components/trust";

export const dynamic = "force-dynamic";

/** §8 — Job Intelligence: the corpus as a first-class surface, not just trend fuel. */
export default async function JobsPage({
  searchParams,
}: {
  searchParams: { role?: string; remote?: string; salary?: string };
}) {
  const params = new URLSearchParams();
  if (searchParams.role) params.set("role", searchParams.role);
  if (searchParams.remote) params.set("remote_type", searchParams.remote);
  if (searchParams.salary === "yes") params.set("has_salary", "true");
  const qs = params.toString() ? `&${params.toString()}` : "";

  const [jobs, facets] = await Promise.all([intelligence.jobs(qs), intelligence.jobFacets()]);

  if (!jobs || !jobs.items.length) {
    return <Empty title="No jobs collected yet" action="Run the loop to collect and extract job postings." />;
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Job intelligence</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          The postings behind every trend
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Each row here is a document the system read. Trends are counts over exactly this corpus —
          nothing in the dashboard exists that cannot be traced back to a posting on this page.
        </p>
      </header>

      {jobs.items.every((j: JobRow) => j.synthetic) && (
        <div className="rounded-card border border-provisional bg-provisional/10 px-4 py-3 text-sm">
          <strong className="text-provisional">Demo data only.</strong>{" "}
          All job postings shown are computer-generated samples, not real job listings. Company names,
          salaries, and skills are synthetic. Trends built from this data show how the system works,
          but should not be used for real career or hiring decisions until a live data source is connected.
        </div>
      )}

      {facets ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Postings" value={facets.total_jobs.toLocaleString()} note="in the corpus" />
          <Stat
            label="Salary disclosed"
            value={facets.salary_coverage !== null ? percent(facets.salary_coverage) : "—"}
            note={`${facets.with_salary.toLocaleString()} of ${facets.total_jobs.toLocaleString()}`}
          />
          <Stat label="Distinct roles" value={String(facets.roles.length)} note="normalised" />
        </div>
      ) : null}

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

      <Card eyebrow={`${jobs.returned} of ${jobs.total} shown`} title="Postings">
        <Table head={["Position", "Company", "Location", "Salary", "Posted", "Skills"]}>
          {jobs.items.map((job: JobRow) => (
            <tr key={job.id} className="border-b border-line/60 align-top last:border-0">
              <td className="py-3 pr-4">
                <span className="font-medium">{job.position}</span>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{job.seniority}</span>
                  <SourceChip source={job.source} synthetic={job.synthetic} />
                </div>
              </td>
              <td className="py-3 pr-4 text-sm">{job.company ?? "—"}</td>
              <td className="py-3 pr-4 text-sm">
                {job.location}
                <span className="ml-2 font-mono text-xs text-muted">{job.remote_type}</span>
              </td>
              <td className="py-3 pr-4 font-mono text-xs tabular-nums">
                {job.salary_known
                  ? `$${((job.salary_min ?? 0) / 1000).toFixed(0)}k–$${((job.salary_max ?? 0) / 1000).toFixed(0)}k`
                  : "not disclosed"}
              </td>
              <td className="py-3 pr-4 font-mono text-xs text-muted">{shortDate(job.posted_at)}</td>
              <td className="py-3">
                <div className="flex flex-wrap gap-1">
                  {job.skills.slice(0, 4).map((s) => (
                    <span key={s} className="rounded-card border border-line px-[6px] py-[1px] font-mono text-xs text-muted">
                      {s}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </Table>
        <p className="mt-4 text-xs text-muted">{jobs.note}</p>
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
