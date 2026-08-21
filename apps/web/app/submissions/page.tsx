"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface Submission {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

export default function SubmissionsPage() {
  const router = useRouter();
  const { user, loading, csrfToken, logout } = useAuth();
  const [submissions, setSubmissions] = useState<Submission[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadSubmissions = useCallback(async () => {
    try {
      const data = await api.get<Submission[]>("/submissions");
      setSubmissions(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load submissions");
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (user) {
      void loadSubmissions();
    }
  }, [user, loadSubmissions]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csrfToken) return;
    setError(null);
    setCreating(true);
    try {
      await api.post("/submissions", { title }, csrfToken);
      setTitle("");
      await loadSubmissions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create submission");
    } finally {
      setCreating(false);
    }
  }

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading...</p>
      </main>
    );
  }

  return (
    <main className="wide">
      <div className="page-header">
        <h1>Submissions</h1>
        <div>
          <span className="muted">{user.email}</span>{" "}
          <button className="secondary" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </div>

      <form onSubmit={handleCreate}>
        <label>
          New submission title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={creating}>
          {creating ? "Creating..." : "Create submission"}
        </button>
      </form>

      {submissions === null ? (
        <p className="muted">Loading submissions...</p>
      ) : submissions.length === 0 ? (
        <p className="muted">No submissions yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {submissions.map((submission) => (
              <tr key={submission.id}>
                <td>
                  <Link href={`/submissions/${submission.id}`}>{submission.title}</Link>
                </td>
                <td>
                  <span className="status-badge">{submission.status}</span>
                </td>
                <td className="muted">{new Date(submission.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
