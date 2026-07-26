import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface p-10 text-center">
      <p className="font-display text-2xl font-bold">That record does not exist</p>
      <p className="mt-2 text-sm text-muted">
        It may have been removed by a schema reset, or the id is wrong.
      </p>
      <Link href="/" className="mt-5 inline-block font-mono text-xs text-proof hover:underline">
        Back to overview
      </Link>
    </div>
  );
}
