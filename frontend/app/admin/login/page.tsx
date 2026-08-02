"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function AdminLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/admin";
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("submitting");
    setError("");
    try {
      const res = await fetch("/api/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      router.push(next);
      router.refresh();
    } catch (err: any) {
      setStatus("error");
      setError(err.message || "Login failed.");
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-8">
      <header>
        <p className="font-mono text-xs uppercase text-muted">Admin</p>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-muted">
          This device will stay signed in for 180 days.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-4 rounded-card border border-line bg-surface p-6">
        <div>
          <label htmlFor="password" className="font-mono text-xs uppercase text-muted">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-2 w-full rounded-card border border-line bg-paper px-3 py-2 text-sm outline-none focus-visible:border-proof"
          />
        </div>
        <button
          type="submit"
          disabled={status === "submitting" || !password}
          className={`w-full rounded-card border px-4 py-2 font-mono text-sm transition-colors ${
            status === "submitting" || !password
              ? "border-line text-muted cursor-not-allowed"
              : "border-proof text-proof hover:bg-proofSoft"
          }`}
        >
          {status === "submitting" ? "Signing in..." : "Sign in →"}
        </button>
        {error && <p className="text-sm text-fail">{error}</p>}
      </form>
    </div>
  );
}

export default function AdminLoginPage() {
  return (
    <Suspense fallback={null}>
      <AdminLoginForm />
    </Suspense>
  );
}
