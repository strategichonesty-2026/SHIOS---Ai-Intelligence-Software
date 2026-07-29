import { NextResponse } from "next/server";

const BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_KEY = process.env.SHIOS_API_KEY ?? process.env.API_KEY ?? "";

export async function GET() {
  try {
    const [runsRes, countsRes] = await Promise.all([
      fetch(`${BASE_URL}/runs?limit=1`, {
        headers: API_KEY ? { "x-api-key": API_KEY } : {},
        cache: "no-store",
      }),
      fetch(`${BASE_URL}/dashboard/overview`, {
        headers: API_KEY ? { "x-api-key": API_KEY } : {},
        cache: "no-store",
      }),
    ]);

    const runs = runsRes.ok ? await runsRes.json() : null;
    const overview = countsRes.ok ? await countsRes.json() : null;

    const latestRun = runs?.items?.[0];
    const done = latestRun?.status === "success" || latestRun?.status === "completed";

    return NextResponse.json({
      done,
      status: latestRun?.status ?? "unknown",
      jobs: overview?.counts?.jobs ?? null,
      documents: overview?.counts?.documents ?? null,
      trends: overview?.counts?.trends ?? null,
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message, done: false }, { status: 500 });
  }
}
