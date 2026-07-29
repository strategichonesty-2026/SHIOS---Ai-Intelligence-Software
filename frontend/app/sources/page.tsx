import { safeGet } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { Card, Empty, Eyebrow, Stat, Table } from "@/components/ui";

export const dynamic = "force-dynamic";

type RepoDoc = {
  id: string;
  title: string;
  source: string;
  observed_at: string;
  entities: Record<string, string[]>;
};

type DocsResponse = {
  items: RepoDoc[];
};

export default async function SourcesPage() {
  const [repos, articles] = await Promise.all([
    safeGet<DocsResponse>("/documents?doc_type=repo&limit=50"),
    safeGet<DocsResponse>("/documents?doc_type=article&limit=10"),
  ]);

  const repoItems = repos?.items ?? [];
  const articleCount = articles?.items.length ?? 0;

  // Extract unique languages and topics from entities
  const languages = new Set<string>();
  const topics = new Set<string>();
  for (const r of repoItems) {
    (r.entities?.languages ?? []).forEach((l: string) => languages.add(l));
    (r.entities?.topics ?? []).forEach((t: string) => topics.add(t));
  }

  return (
    <div className="space-y-8">
      <header>
        <Eyebrow>Sources scanned</Eyebrow>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          What the system actually read
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Every trend, forecast, and recommendation on this site traces back to one of these
          documents. Nothing is inferred from a model's prior knowledge — only from what was
          collected and listed here.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="GitHub repos scanned"
          value={repoItems.length.toLocaleString()}
          note="open-source repositories"
        />
        <Stat
          label="Languages seen"
          value={String(languages.size || "—")}
          note="programming languages"
        />
        <Stat
          label="Topics tracked"
          value={String(topics.size || "—")}
          note="GitHub topic tags"
        />
      </div>

      {repoItems.length > 0 ? (
        <Card eyebrow={`${repoItems.length} repositories`} title="GitHub repos scanned">
          <Table head={["Repository", "Language", "Topics", "Scanned"]}>
            {repoItems.map((repo) => {
              const lang = (repo.entities?.languages ?? [])[0] ?? "—";
              const repoTopics = (repo.entities?.topics ?? []).slice(0, 3);
              return (
                <tr key={repo.id} className="border-b border-line/60 last:border-0">
                  <td className="py-3 pr-4">
                    <a
                      href={`https://github.com/${repo.title}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-proof hover:underline"
                    >
                      {repo.title}
                    </a>
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs text-muted">{lang}</td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {repoTopics.length > 0 ? repoTopics.map((t: string) => (
                        <span
                          key={t}
                          className="rounded-card border border-line px-[6px] py-[1px] font-mono text-xs text-muted"
                        >
                          {t}
                        </span>
                      )) : <span className="font-mono text-xs text-muted">—</span>}
                    </div>
                  </td>
                  <td className="py-3 font-mono text-xs text-muted">
                    {shortDate(repo.observed_at)}
                  </td>
                </tr>
              );
            })}
          </Table>
        </Card>
      ) : (
        <Card eyebrow="GitHub repos" title="No repositories scanned yet">
          <p className="text-sm text-muted">
            The GitHub collector has not run yet or no topics are configured. Once a{" "}
            <code className="font-mono text-xs">GITHUB_TOKEN</code> and topic list are set,
            repositories will appear here automatically after the next collection loop.
          </p>
        </Card>
      )}

      <Card eyebrow="What we do not read" title="Known gaps in coverage">
        <ul className="space-y-2 text-sm text-muted">
          <li>
            <span className="font-medium text-foreground">LinkedIn job postings</span> — requires
            a paid API license. Currently substituted with demo data.
          </li>
          <li>
            <span className="font-medium text-foreground">Indeed / Glassdoor</span> — scraping
            violates their terms of service. Not collected.
          </li>
          <li>
            <span className="font-medium text-foreground">SEC filings</span> — hiring plans in
            earnings reports are not yet parsed.
          </li>
          <li>
            <span className="font-medium text-foreground">Academic papers</span> — arXiv and
            similar preprint servers are not yet connected.
          </li>
        </ul>
        <p className="mt-4 text-xs text-muted">
          These gaps are listed here rather than hidden. A source that is absent is not the same
          as a source that returned zero — and this system does not pretend otherwise.
        </p>
      </Card>
    </div>
  );
}
