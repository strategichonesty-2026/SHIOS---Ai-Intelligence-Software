"use client";

import { useState } from "react";

export default function AdminPage() {
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [runLog, setRunLog] = useState<string>("");
  async function pollUntilDone() {
    const start = Date.now();
    const maxWait = 5 * 60 * 1000; // 5 minutes
    while (Date.now() - start < maxWait) {
      await new Promise((r) => setTimeout(r, 8000)); // check every 8 seconds
      try {
        const res = await fetch("/api/run-status");
        if (!res.ok) continue;
        const data = await res.json();
        const elapsed = Math.round((Date.now() - start) / 1000);
        setRunLog(
          `Loop running...\n\nJobs collected: ${data.jobs ?? "—"}\nDocuments: ${data.documents ?? "—"}\nElapsed: ${elapsed}s\n\nPage will update when complete.`
        );
        if (data.done) {
          setRunStatus("done");
          const errors = (data.source_errors ?? [])
            .filter((e: any) => e.error)
            .map((e: any) => `  • ${e.source}: ${e.error}`)
            .join("\n");
          setRunLog(
            `✓ Complete!\n\nJobs collected: ${data.jobs ?? "—"}\nDocuments: ${data.documents ?? "—"}\nTrends computed: ${data.trends ?? "—"}` +
            (errors ? `\n\nSource warnings:\n${errors}` : "") +
            `\n\nRefresh Jobs or Trends page to see real data.`
          );
          // Browser notification
          if (Notification.permission === "granted") {
            new Notification("SHIOS — Collection complete", {
              body: `Collected ${data.jobs ?? "?"} jobs. Refresh the Jobs or Trends page.`,
            });
          }
          return;
        }
      } catch {
        continue;
      }
    }
    setRunStatus("done");
    setRunLog("Loop is taking longer than expected. Check the Jobs or Trends page manually.");
  }

  async function runLoop() {
    setRunStatus("running");
    setRunLog("Triggering collection loop...");

    // Request notification permission
    if (Notification.permission === "default") {
      await Notification.requestPermission();
    }

    try {
      const res = await fetch("/api/run", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setRunLog("Loop accepted. Waiting for results...");
      pollUntilDone();
    } catch (err: any) {
      setRunStatus("error");
      setRunLog(`Error: ${err.message}`);
    }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <header>
        <p className="font-mono text-xs uppercase text-muted">Admin</p>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Collection controls
        </h1>
        <p className="mt-2 text-sm text-muted">
          Manage data collection and clean up demo data.
        </p>
      </header>

      {/* Collection loop */}
      <div className="rounded-card border border-line bg-surface p-6 space-y-4">
        <div>
          <p className="font-mono text-xs uppercase text-muted">Full collection loop</p>
          <p className="mt-1 text-sm text-muted">
            Collects real job postings from LinkedIn + GitHub repos + RSS articles, extracts entities, computes trends, publishes forecasts and recommendations. You'll get a browser notification when it's done.
          </p>
        </div>
        <button
          onClick={runLoop}
          disabled={runStatus === "running"}
          className={`rounded-card border px-4 py-2 font-mono text-sm transition-colors ${
            runStatus === "running"
              ? "border-line text-muted cursor-not-allowed"
              : runStatus === "done"
              ? "border-proof text-proof"
              : "border-proof text-proof hover:bg-proofSoft"
          }`}
        >
          {runStatus === "running" ? "Running — you'll get a notification when done..." : runStatus === "done" ? "✓ Complete" : "Run collection loop now →"}
        </button>
        {runLog && (
          <pre className="rounded-card border border-line bg-paper p-4 font-mono text-xs text-muted whitespace-pre-wrap">
            {runLog}
          </pre>
        )}
      </div>

      <div className="rounded-card border border-line bg-surface p-6 space-y-2">
        <p className="font-mono text-xs uppercase text-muted">Current data sources</p>
        <ul className="space-y-1 text-sm text-muted mt-2">
          <li><span className="text-proof font-medium">Job RSS</span> — real job postings from Indeed + LinkedIn RSS feeds</li>
          <li><span className="text-proof font-medium">GitHub</span> — repository momentum by topic</li>
          <li><span className="text-proof font-medium">RSS</span> — tech news and articles</li>
        </ul>
      </div>
    </div>
  );
}
