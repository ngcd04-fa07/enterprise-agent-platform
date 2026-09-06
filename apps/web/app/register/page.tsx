"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { DEMO_ACCOUNT_EMAIL, DEMO_ACCOUNT_PASSWORD, DEMO_MODE } from "@/lib/demo";

export default function RegisterPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [organisationName, setOrganisationName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.post("/auth/register", {
        email,
        full_name: fullName,
        organisation_name: organisationName,
        password,
      });
      await refresh();
      router.push("/submissions");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (DEMO_MODE) {
    return (
      <main>
        <h1>Registration disabled</h1>
        <p className="muted">
          This is a public demo with synthetic data only — registration is disabled to keep it
          that way. Log in with the shared demo account instead: <code>{DEMO_ACCOUNT_EMAIL}</code>{" "}
          / <code>{DEMO_ACCOUNT_PASSWORD}</code>.
        </p>
        <p>
          <Link href="/login">Go to login</Link>
        </p>
      </main>
    );
  }

  return (
    <main>
      <h1>Create your organisation</h1>
      <p className="muted">
        Registering creates both your account and a new organisation, with you as its admin.
      </p>
      <form onSubmit={handleSubmit}>
        <label>
          Full name
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </label>
        <label>
          Organisation name
          <input
            value={organisationName}
            onChange={(e) => setOrganisationName(e.target.value)}
            required
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating account..." : "Create account"}
        </button>
      </form>
      <p className="muted">
        Already have an account? <Link href="/login">Log in</Link>
      </p>
    </main>
  );
}
