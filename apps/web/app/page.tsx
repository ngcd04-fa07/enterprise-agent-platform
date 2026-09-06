"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PlatformOverview } from "@/components/PlatformOverview";
import { useAuth } from "@/lib/auth-context";

export default function HomePage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/submissions");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <main>
        <p className="muted">Loading...</p>
      </main>
    );
  }

  return (
    <main className="wide">
      <h1>Enterprise Agent Platform</h1>
      <p>
        Evidence-grounded underwriting document intelligence — upload submission documents,
        search across them, and see exactly which page backs every result.
      </p>
      <p>
        <Link href="/login">Log in</Link> · <Link href="/register">Register</Link>
      </p>
      <PlatformOverview />
    </main>
  );
}
